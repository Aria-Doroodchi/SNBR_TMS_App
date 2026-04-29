"""First page of the TMS App — lets the user set import paths."""

import customtkinter as ctk
from tkinter import filedialog
from pathlib import Path

from core.user_settings import (
    save_defaults, KEY_MEM_DIR, KEY_CSP_DIR, KEY_CMAP_DIR, KEY_CSV_FILE,
)
from gui.theme import (
    FONT_TITLE, FONT_HEADING, FONT_BODY, FONT_SMALL, FONT_SUBTITLE, FONT_BUTTON,
    ACCENT_COLOR, ACCENT_HOVER, ERROR_COLOR, DISABLED_FG, SUBTITLE_COLOR,
    PAD_X, PAD_Y, SECTION_PAD_Y, ENTRY_HEIGHT, BUTTON_HEIGHT, CORNER_RADIUS,
)


class FilePanel(ctk.CTkFrame):
    """Path selection panel — page 1 of the workflow."""

    def __init__(self, parent, controller, on_next, on_back=None):
        super().__init__(parent, fg_color="transparent")
        self._controller = controller
        self._on_next = on_next
        self._on_back = on_back

        self._mem_var = ctk.StringVar()
        self._csp_var = ctk.StringVar()
        self._cmap_var = ctk.StringVar()
        self._csv_var = ctk.StringVar()
        self._error_var = ctk.StringVar()

        self._save_mem = ctk.BooleanVar(value=False)
        self._save_csp = ctk.BooleanVar(value=False)
        self._save_cmap = ctk.BooleanVar(value=False)
        self._save_csv = ctk.BooleanVar(value=False)

        self._load_defaults()
        self._build_ui()

    def _load_defaults(self):
        """Pre-fill entries from controller defaults."""
        paths = self._controller.get_paths()
        self._mem_var.set(paths["mem_path"])
        self._csp_var.set(paths["csp_path"])
        self._cmap_var.set(paths.get("cmap_path", ""))
        self._csv_var.set(paths["csv_path"])

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Title ──────────────────────────────────────────────
        title = ctk.CTkLabel(
            self, text="Import Settings", font=FONT_TITLE, anchor="w",
        )
        title.grid(row=0, column=0, sticky="w", padx=PAD_X, pady=(SECTION_PAD_Y, 4))

        subtitle = ctk.CTkLabel(
            self,
            text="Set the directories where your data files are located.",
            font=FONT_SUBTITLE,
            text_color=SUBTITLE_COLOR,
            anchor="w",
        )
        subtitle.grid(row=1, column=0, sticky="w", padx=PAD_X, pady=(0, SECTION_PAD_Y))

        # ── Fields container ───────────────────────────────────
        fields = ctk.CTkFrame(self, fg_color="transparent")
        fields.grid(row=2, column=0, sticky="nsew", padx=PAD_X)
        fields.grid_columnconfigure(0, weight=1)

        self._add_path_row(
            fields, row=0,
            label="MEM Files Directory *",
            helper="Folder containing .MEM files from Qtrack sessions. (Required)",
            var=self._mem_var,
            save_var=self._save_mem,
        )
        self._add_path_row(
            fields, row=1,
            label="CSP MEM Files Directory",
            helper="Folder containing CSP-specific .MEM files. (Optional)",
            var=self._csp_var,
            save_var=self._save_csp,
        )
        self._add_path_row(
            fields, row=2,
            label="CMAP Files Directory",
            helper=(
                "Folder containing motor nerve-conduction study .pdf or "
                ".docx files. (Optional)"
            ),
            var=self._cmap_var,
            save_var=self._save_cmap,
        )
        self._add_path_row(
            fields, row=3,
            label="Archive CSV File",
            helper="Select a .csv archive file to build on. (Optional)",
            var=self._csv_var,
            browse_file=True,
            save_var=self._save_csv,
        )

        # ── Error label ───────────────────────────────────────
        self._error_label = ctk.CTkLabel(
            self,
            textvariable=self._error_var,
            font=FONT_SMALL,
            text_color=ERROR_COLOR,
            anchor="w",
            wraplength=500,
        )
        self._error_label.grid(
            row=3, column=0, sticky="w", padx=PAD_X, pady=(PAD_Y, 0),
        )

        # ── Navigation bar ────────────────────────────────────
        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.grid(row=4, column=0, sticky="ew", padx=PAD_X, pady=(PAD_Y, SECTION_PAD_Y))
        nav.grid_columnconfigure(0, weight=1)

        if self._on_back:
            self._back_btn = ctk.CTkButton(
                nav,
                text="Back",
                width=100,
                height=BUTTON_HEIGHT,
                corner_radius=CORNER_RADIUS,
                font=FONT_BUTTON,
                fg_color=ACCENT_COLOR,
                hover_color=ACCENT_HOVER,
                command=self._on_back,
            )
        else:
            self._back_btn = ctk.CTkButton(
                nav,
                text="Back",
                width=100,
                height=BUTTON_HEIGHT,
                corner_radius=CORNER_RADIUS,
                font=FONT_BUTTON,
                state="disabled",
                fg_color=DISABLED_FG,
                hover=False,
            )
        self._back_btn.grid(row=0, column=0, sticky="w")

        self._next_btn = ctk.CTkButton(
            nav,
            text="Next",
            width=100,
            height=BUTTON_HEIGHT,
            corner_radius=CORNER_RADIUS,
            font=FONT_BUTTON,
            fg_color=ACCENT_COLOR,
            hover_color=ACCENT_HOVER,
            command=self._handle_next,
        )
        self._next_btn.grid(row=0, column=1, sticky="e")

    def _add_path_row(
        self, parent, row: int, label: str, helper: str,
        var: ctk.StringVar, browse_file: bool = False,
        save_var: ctk.BooleanVar | None = None,
    ):
        """Create a labeled path entry with a Browse button and optional save-default checkbox."""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, SECTION_PAD_Y))
        frame.grid_columnconfigure(0, weight=1)

        lbl = ctk.CTkLabel(frame, text=label, font=FONT_HEADING, anchor="w")
        lbl.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))

        entry = ctk.CTkEntry(
            frame,
            textvariable=var,
            height=ENTRY_HEIGHT,
            corner_radius=CORNER_RADIUS,
            font=FONT_BODY,
        )
        entry.grid(row=1, column=0, sticky="ew", padx=(0, 8))

        if browse_file:
            cmd = lambda v=var: self._browse_file(v)
        else:
            cmd = lambda v=var: self._browse_dir(v)

        browse_btn = ctk.CTkButton(
            frame,
            text="Browse",
            width=90,
            height=ENTRY_HEIGHT,
            corner_radius=CORNER_RADIUS,
            font=FONT_BODY,
            fg_color=ACCENT_COLOR,
            hover_color=ACCENT_HOVER,
            command=cmd,
        )
        browse_btn.grid(row=1, column=1, sticky="e")

        hlp = ctk.CTkLabel(
            frame, text=helper, font=FONT_SUBTITLE, text_color=SUBTITLE_COLOR, anchor="w",
        )
        hlp.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))

        if save_var is not None:
            ctk.CTkCheckBox(
                frame,
                text="Save as default",
                variable=save_var,
                font=FONT_SMALL,
            ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(4, 0))

    def _browse_dir(self, var: ctk.StringVar):
        """Open a folder-selection dialog and write the result into var."""
        initial = var.get() if var.get() and Path(var.get()).is_dir() else None
        path = filedialog.askdirectory(
            title="Select Directory",
            initialdir=initial,
        )
        if path:
            var.set(path)

    def _browse_file(self, var: ctk.StringVar):
        """Open a file-selection dialog filtered to .csv files."""
        current = var.get()
        initial_dir = None
        if current:
            p = Path(current)
            if p.is_file():
                initial_dir = str(p.parent)
            elif p.is_dir():
                initial_dir = current

        path = filedialog.askopenfilename(
            title="Select CSV File",
            initialdir=initial_dir,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if path:
            var.set(path)

    def refresh(self):
        """Re-load defaults and show any Quick Start redirect message."""
        self._load_defaults()
        msg = self._controller.consume_quick_start_message()
        if msg:
            self._error_var.set(msg)
            self._error_label.configure(text_color="#F39C12")
        else:
            self._error_var.set("")
            self._error_label.configure(text_color=ERROR_COLOR)

    def _handle_next(self):
        """Validate inputs, save to controller, persist defaults, and advance."""
        self._error_var.set("")

        self._controller.set_paths(
            mem_path=self._mem_var.get().strip(),
            csp_path=self._csp_var.get().strip(),
            cmap_path=self._cmap_var.get().strip(),
            csv_path=self._csv_var.get().strip(),
        )

        errors = self._controller.validate_paths()
        if errors:
            self._error_var.set("\n".join(errors))
            return

        # Persist checked paths as defaults for next session.
        to_save = {}
        if self._save_mem.get():
            to_save[KEY_MEM_DIR] = self._mem_var.get().strip()
        if self._save_csp.get():
            to_save[KEY_CSP_DIR] = self._csp_var.get().strip()
        if self._save_cmap.get():
            to_save[KEY_CMAP_DIR] = self._cmap_var.get().strip()
        if self._save_csv.get():
            to_save[KEY_CSV_FILE] = self._csv_var.get().strip()
        if to_save:
            save_defaults(**to_save)

        self._on_next()
