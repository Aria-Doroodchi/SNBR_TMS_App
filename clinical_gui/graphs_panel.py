"""The graphs page of the clinical app: the analysis app's Visualization page, trimmed.

A subclass of :class:`gui.visualization_panel.VisualizationPanel` rather than
a copy. The graph registry, the recording-target boxes, availability, the
preview canvas, arrow navigation, lazy generation and the figure cache are
all inherited, so this app draws exactly what the analysis app draws and any
fix there reaches here. What is replaced are the three parts the parent
splits out for that purpose:

* the heading -- no pulse-variability tick box, because the Qtrac Excel
  exports it needs never leave the lab machine;
* the option boxes above the graph list -- *Select All* only, no
  "Save as default" (there is no Quick Start to save it for);
* the footer -- no Back/Next; instead the report's folder and optional name
  and the **Export report** button, which runs the parent's own
  generate-everything-then-collect step and then hands over to the window's
  export callback.

Arrow keys are also ignored while the user is typing in an entry, since this
is a single window and the search box sits beside the graphs.
"""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from gui.theme import (
    ACCENT_COLOR, ACCENT_HOVER, BUTTON_HEIGHT, CORNER_RADIUS, ERROR_COLOR, FONT_BUTTON,
    FONT_SMALL, FONT_SUBTITLE, FONT_TITLE, PAD_X, PAD_Y, SUBTITLE_COLOR, SUCCESS_COLOR,
)
from gui.visualization_panel import VisualizationPanel


class ClinicalGraphsPanel(VisualizationPanel):
    """Graph selection and preview, ending in an identified report."""

    def __init__(self, parent, controller, on_export, footer):
        # ``on_next`` is what the parent's collect step calls once every ticked
        # graph has been generated and wrapped as a ReportItem; here that is
        # the window's export routine.
        super().__init__(parent, controller, on_next=on_export, on_back=lambda: None, footer=footer)

    # -- the parts replaced ------------------------------------------------------

    def _build_title(self, title_frame):
        ctk.CTkLabel(title_frame, text="Report graphs", font=FONT_TITLE, anchor="w").pack(
            side="top", anchor="w",
        )
        ctk.CTkLabel(
            title_frame,
            text="Tick the graphs to include in the report, then browse them with the arrows.",
            font=FONT_SUBTITLE, text_color=SUBTITLE_COLOR, anchor="w",
        ).pack(side="top", anchor="w", pady=(0, 4))

    def _build_sidebar_options(self, sidebar, sidebar_row: int) -> int:
        ctk.CTkCheckBox(
            sidebar, text="Select All", variable=self._select_all_var,
            font=FONT_BUTTON, command=self._on_select_all,
        ).grid(row=sidebar_row, column=0, sticky="w", pady=(0, PAD_Y))
        return sidebar_row + 1

    def _build_footer(self):
        self._report_dir = ctk.StringVar()
        self._report_name = ctk.StringVar()
        self._open_folder_path: Path | None = None

        self._status_label = ctk.CTkLabel(
            self._footer, textvariable=self._status_var, font=FONT_SMALL,
            text_color=SUBTITLE_COLOR, anchor="w", wraplength=900, justify="left",
        )
        self._status_label.grid(row=1, column=0, sticky="w", padx=PAD_X, pady=(4, 0))
        self._status_default_color = self._status_label.cget("text_color")

        row = ctk.CTkFrame(self._footer, fg_color="transparent")
        row.grid(row=2, column=0, sticky="ew", padx=PAD_X, pady=(4, PAD_Y))
        row.grid_columnconfigure(1, weight=2)
        row.grid_columnconfigure(4, weight=1)

        ctk.CTkLabel(row, text="Folder", font=FONT_SMALL, text_color=SUBTITLE_COLOR).grid(
            row=0, column=0, sticky="w", padx=(0, 4),
        )
        ctk.CTkEntry(
            row, textvariable=self._report_dir, height=30, corner_radius=CORNER_RADIUS,
            font=FONT_SMALL,
        ).grid(row=0, column=1, sticky="ew", padx=(0, 6))
        ctk.CTkButton(
            row, text="Browse", width=70, height=30, corner_radius=CORNER_RADIUS,
            font=FONT_SMALL, fg_color="transparent", border_width=1,
            command=self._browse_report_dir,
        ).grid(row=0, column=2, padx=(0, 12))
        ctk.CTkLabel(
            row, text="Name (optional)", font=FONT_SMALL, text_color=SUBTITLE_COLOR,
        ).grid(row=0, column=3, sticky="w", padx=(0, 4))
        ctk.CTkEntry(
            row, textvariable=self._report_name, height=30, corner_radius=CORNER_RADIUS,
            font=FONT_SMALL,
        ).grid(row=0, column=4, sticky="ew", padx=(0, 12))

        self._open_folder_btn = ctk.CTkButton(
            row, text="Open folder", width=100, height=BUTTON_HEIGHT,
            corner_radius=CORNER_RADIUS, font=FONT_SMALL,
            fg_color="transparent", border_width=1, command=self._open_last_folder,
        )
        self._open_folder_btn.grid(row=0, column=5, padx=(0, 8))
        self._open_folder_btn.grid_remove()   # until a report has been written

        # The parent's collect step disables ``_next_page_btn`` while it
        # generates the remaining graphs, so the export button takes that name.
        self._next_page_btn = ctk.CTkButton(
            row, text="Export report (PDF)", width=170, height=BUTTON_HEIGHT,
            corner_radius=CORNER_RADIUS, font=FONT_BUTTON,
            fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, command=self._handle_next,
        )
        self._next_page_btn.grid(row=0, column=6, sticky="e")

    # -- keys ----------------------------------------------------------------

    def _typing_in_an_entry(self) -> bool:
        try:
            focused = self.focus_get()
        except (KeyError, tk.TclError):
            return False
        return isinstance(focused, tk.Entry)

    def _on_left_key(self, event):
        if not self._typing_in_an_entry():
            super()._on_left_key(event)

    def _on_right_key(self, event):
        if not self._typing_in_an_entry():
            super()._on_right_key(event)

    # -- what the window needs ---------------------------------------------------

    def report_target(self) -> tuple[str, str]:
        """The folder and optional name typed for the report (either may be empty)."""
        return self._report_dir.get().strip(), self._report_name.get().strip()

    def set_exporting(self, busy: bool) -> None:
        """Disable the export and arrow buttons while the PDF is being written."""
        self._set_busy_for_export(busy)

    def show_export_result(self, text: str, *, error: bool = False) -> None:
        self._status_var.set(text)
        self._status_label.configure(
            text_color=ERROR_COLOR if error else SUCCESS_COLOR,
        )

    def show_note(self, text: str) -> None:
        self._status_var.set(text)
        self._status_label.configure(text_color=self._status_default_color)

    def set_last_export_folder(self, folder: Path | None) -> None:
        self._open_folder_path = folder
        if folder is None:
            self._open_folder_btn.grid_remove()
        else:
            self._open_folder_btn.grid()

    def refresh(self):
        # A new visit: the previous report's note no longer applies.
        self._status_label.configure(text_color=self._status_default_color)
        super().refresh()

    # -- helpers -------------------------------------------------------------

    def _browse_report_dir(self):
        initial = self._report_dir.get().strip() or self._controller.default_export_folder("pdf")
        chosen = filedialog.askdirectory(
            title="Choose a folder for the report", initialdir=initial or None, mustexist=False,
        )
        if chosen:
            self._report_dir.set(chosen)

    def _open_last_folder(self):
        if self._open_folder_path is not None:
            _open_path(self._open_folder_path)


def _open_path(path: Path) -> None:
    import os
    import subprocess
    import sys

    if sys.platform.startswith("win"):
        os.startfile(str(path))  # noqa: S606 - opening a folder the app wrote
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
