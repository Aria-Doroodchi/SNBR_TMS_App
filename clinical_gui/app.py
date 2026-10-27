"""The clinical window: a Report tab and a Settings tab.

Report: type a name, an MRN or a study ID; pick the patient, then the visit
(the latest is picked for you); the graphs page on the right fills with every
graph that visit can draw; untick what you do not want; **Export report**
writes the PDF with the patient's identity stamped on its cover.

All backend work goes through :class:`clinical_gui.controller.ClinicalController`
on a background thread; results come back via ``after(0, ...)``.
"""

from __future__ import annotations

import sys
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from clinical_gui.controller import ClinicalController
from clinical_gui.graphs_panel import ClinicalGraphsPanel
from gui.page_shell import FOOTER_BORDER_COLOR, FOOTER_FG_COLOR
from gui.theme import (
    ACCENT_COLOR, ACCENT_HOVER, BUTTON_HEIGHT, CORNER_RADIUS, DISABLED_FG, ENTRY_HEIGHT,
    ERROR_COLOR, FONT_BODY, FONT_BUTTON, FONT_HEADING, FONT_SMALL, FONT_SUBTITLE,
    FONT_TITLE, PAD_X, PAD_Y, SECTION_PAD_Y, SUBTITLE_COLOR, SUCCESS_COLOR,
)

# Settings keys are addressed by name so this module needs no clinical import.
_S = {
    "csv_path": ("Archive CSV (full data frame)", "csv"),
    "roster_path": ("Enrolment workbook (.xlsx)", "xlsx"),
    "roster_sheet": ("Worksheet name", "text"),
    "col_patient_id": ("Patient ID column header", "text"),
    "col_patient_name": ("Patient Name column header", "text"),
    "col_mrn": ("MRN column header", "text"),
    "export_dir": ("Default export folder (reports and figures)", "dir"),
}

_WARN_COLOR = "#B7791F"
_ROW_TEXT = ("gray10", "gray90")
# Past this many hits the list stops being something to scroll through.
_MAX_RESULTS = 150


def _resolve_logo_dir() -> Path:
    """The clinical app's own mark (``icons/logo_clinical/``).

    Not the coil and not the envelope: three executables, three icons. In a
    bundle ``sys._MEIPASS`` is the extracted data root, where the spec's
    ``('icons', 'icons')`` entry lands.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "icons" / "logo_clinical"
    return Path(__file__).resolve().parent.parent / "icons" / "logo_clinical"


class ClinicalApp(ctk.CTk):
    WIDTH = 1340
    HEIGHT = 840

    def __init__(self, controller: ClinicalController | None = None, autoload: bool = True):
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("SNBR Clinical Reports")
        self.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        self.minsize(1000, 660)
        self._apply_window_icon()

        self._controller = controller or ClinicalController()
        self._busy = False
        self._results: list = []
        self._result_buttons: list[tuple[object, ctk.CTkButton]] = []
        self._visit_buttons: list[tuple[datetime, ctk.CTkButton]] = []
        self._selected = None
        self._selected_date: datetime | None = None
        self._setting_vars: dict[str, ctk.StringVar] = {}

        self._build()
        missing = self._controller.missing_configuration()
        if missing:
            self._tabs.set("Settings")
            self._set_status("Fill in the settings first: " + ", ".join(missing), warn=True)
        elif autoload:
            # The window is up before the slow read starts, so a large archive
            # does not look like a hung launch.
            self.after(150, self._on_load)

    def _apply_window_icon(self) -> None:
        """Windows only and purely cosmetic: a missing file must not stop the app."""
        if not sys.platform.startswith("win"):
            return
        try:
            self.iconbitmap(str(_resolve_logo_dir() / "clinical.ico"))
        except Exception:
            pass

    # -- layout ------------------------------------------------------------------

    def _build(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=PAD_X, pady=(SECTION_PAD_Y, 0))
        ctk.CTkLabel(header, text="SNBR Clinical Reports", font=FONT_TITLE, anchor="w").pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="Find a patient by name, MRN or study ID, review their graphs, and export "
                 "a report with the patient's identity on its cover.",
            font=FONT_SUBTITLE, text_color=SUBTITLE_COLOR, anchor="w", wraplength=1100, justify="left",
        ).pack(anchor="w")

        self._tabs = ctk.CTkTabview(self, corner_radius=CORNER_RADIUS)
        self._tabs.grid(row=1, column=0, sticky="nsew", padx=PAD_X, pady=(PAD_Y, 0))
        self._build_report_tab(self._tabs.add("Report"))
        self._build_settings_tab(self._tabs.add("Settings"))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=PAD_X, pady=(4, PAD_Y))
        self._status_var = ctk.StringVar(value="")
        self._status_label = ctk.CTkLabel(
            footer, textvariable=self._status_var, font=FONT_SMALL, anchor="w",
            wraplength=1200, justify="left",
        )
        self._status_label.pack(anchor="w", fill="x")
        # configure(text_color=None) is rejected by CTk; keep the default to restore.
        self._status_default_color = self._status_label.cget("text_color")

    # -- report tab --------------------------------------------------------------

    def _build_report_tab(self, tab):
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(tab, width=340, corner_radius=CORNER_RADIUS)
        left.grid(row=0, column=0, sticky="nsw", padx=(0, PAD_Y), pady=(0, 4))
        left.grid_propagate(False)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(2, weight=3)
        left.grid_rowconfigure(4, weight=2)

        ctk.CTkLabel(left, text="Find a patient", font=FONT_HEADING, anchor="w").grid(
            row=0, column=0, sticky="w", padx=PAD_Y, pady=(PAD_Y, 2),
        )
        self._query = ctk.StringVar()
        self._search_entry = ctk.CTkEntry(
            left, textvariable=self._query, height=ENTRY_HEIGHT, corner_radius=CORNER_RADIUS,
            font=FONT_BODY,
        )
        self._search_entry.grid(row=1, column=0, sticky="ew", padx=PAD_Y)
        self._query.trace_add("write", self._on_query_changed)

        self._results_frame = ctk.CTkScrollableFrame(left, corner_radius=CORNER_RADIUS)
        self._results_frame.grid(row=2, column=0, sticky="nsew", padx=PAD_Y, pady=(4, 0))
        self._results_frame.grid_columnconfigure(0, weight=1)
        self._results_hint = ctk.CTkLabel(
            self._results_frame, text="Type a name, an MRN or a study ID.",
            font=FONT_SMALL, text_color=DISABLED_FG, anchor="w", wraplength=280, justify="left",
        )
        self._results_hint.grid(row=0, column=0, sticky="w", padx=6, pady=6)

        ctk.CTkLabel(left, text="Visit", font=FONT_HEADING, anchor="w").grid(
            row=3, column=0, sticky="w", padx=PAD_Y, pady=(PAD_Y, 2),
        )
        self._visits_frame = ctk.CTkScrollableFrame(left, corner_radius=CORNER_RADIUS)
        self._visits_frame.grid(row=4, column=0, sticky="nsew", padx=PAD_Y)
        self._visits_frame.grid_columnconfigure(0, weight=1)

        self._card = ctk.CTkFrame(left, corner_radius=CORNER_RADIUS)
        self._card.grid(row=5, column=0, sticky="ew", padx=PAD_Y, pady=(PAD_Y, 0))
        self._card.grid_columnconfigure(1, weight=1)
        self._card_rows: list = []

        self._caveat = ctk.CTkLabel(
            left, text="", font=FONT_SMALL, text_color=_WARN_COLOR, anchor="w",
            wraplength=300, justify="left",
        )
        self._caveat.grid(row=6, column=0, sticky="w", padx=PAD_Y, pady=(4, 0))

        self._load_btn = ctk.CTkButton(
            left, text="Reload data", width=120, height=BUTTON_HEIGHT, font=FONT_SMALL,
            fg_color="transparent", border_width=1, command=self._on_load,
        )
        self._load_btn.grid(row=7, column=0, sticky="w", padx=PAD_Y, pady=PAD_Y)

        # The pinned bar the graphs page puts its status line and export row
        # into. Built before the page, which grids into it.
        separator = ctk.CTkFrame(tab, height=1, fg_color=FOOTER_BORDER_COLOR, corner_radius=0)
        separator.grid(row=1, column=0, columnspan=2, sticky="ew")
        self._report_footer = ctk.CTkFrame(tab, fg_color=FOOTER_FG_COLOR, corner_radius=0, height=1)
        self._report_footer.grid(row=2, column=0, columnspan=2, sticky="ew")
        self._report_footer.grid_columnconfigure(0, weight=1)

        self._graphs = ClinicalGraphsPanel(
            tab, self._controller, on_export=self._on_export, footer=self._report_footer,
        )
        self._graphs.grid(row=0, column=1, sticky="nsew")

    def _render_results(self, participants: list):
        for widget in self._results_frame.winfo_children():
            widget.destroy()
        self._result_buttons = []
        self._results = list(participants)
        if not participants:
            ctk.CTkLabel(
                self._results_frame,
                text="No patient matches." if self._query.get().strip() else "Nothing loaded.",
                font=FONT_SMALL, text_color=DISABLED_FG, anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=6, pady=6)
            return
        for row, p in enumerate(participants[:_MAX_RESULTS]):
            visits = len(p.visits)
            detail = " · ".join(
                part for part in (
                    f"MRN {p.mrn}" if p.mrn else "no MRN",
                    p.label,
                    f"{visits} visit{'s' if visits != 1 else ''}" if visits else "no data",
                )
            )
            btn = ctk.CTkButton(
                self._results_frame, text=f"{p.display_name}\n{detail}",
                font=FONT_SMALL, height=44, corner_radius=4, anchor="w",
                fg_color="transparent", text_color=_ROW_TEXT if p.has_data else DISABLED_FG,
                hover_color=ACCENT_COLOR, command=lambda q=p: self._on_pick(q),
            )
            btn.grid(row=row, column=0, sticky="ew", pady=1)
            self._result_buttons.append((p, btn))
        if len(participants) > _MAX_RESULTS:
            ctk.CTkLabel(
                self._results_frame,
                text=f"... and {len(participants) - _MAX_RESULTS} more. Keep typing to narrow the list.",
                font=FONT_SMALL, text_color=DISABLED_FG, anchor="w", wraplength=280, justify="left",
            ).grid(row=_MAX_RESULTS, column=0, sticky="w", padx=6, pady=4)
        self._highlight_result()

    def _highlight_result(self):
        for p, btn in self._result_buttons:
            if self._selected is not None and p.key == self._selected.key:
                btn.configure(fg_color=ACCENT_COLOR, text_color="white")
            else:
                btn.configure(fg_color="transparent", text_color=_ROW_TEXT if p.has_data else DISABLED_FG)

    def _render_visits(self, participant):
        for widget in self._visits_frame.winfo_children():
            widget.destroy()
        self._visit_buttons = []
        if participant is None:
            return
        dates = self._controller.visit_dates(participant)
        if not dates:
            ctk.CTkLabel(
                self._visits_frame, text="No visits in the data frame.",
                font=FONT_SMALL, text_color=DISABLED_FG, anchor="w",
            ).grid(row=0, column=0, sticky="w", padx=6, pady=4)
            return
        for row, when in enumerate(dates):
            text = when.strftime("%d/%m/%Y") + ("   (latest)" if row == 0 else "")
            btn = ctk.CTkButton(
                self._visits_frame, text=text, font=FONT_BODY, height=30, corner_radius=4,
                anchor="w", fg_color="transparent", text_color=_ROW_TEXT, hover_color=ACCENT_COLOR,
                command=lambda d=when: self._on_pick_visit(d),
            )
            btn.grid(row=row, column=0, sticky="ew", pady=1)
            self._visit_buttons.append((when, btn))

    def _highlight_visit(self):
        for when, btn in self._visit_buttons:
            if self._selected_date is not None and when == self._selected_date:
                btn.configure(fg_color=ACCENT_COLOR, text_color="white")
            else:
                btn.configure(fg_color="transparent", text_color=_ROW_TEXT)

    def _render_card(self, participant):
        for widget in self._card.winfo_children():
            widget.destroy()
        self._card_rows = []
        lines = self._controller.identity_lines(participant)
        if not lines:
            ctk.CTkLabel(
                self._card, text="No patient selected.", font=FONT_SMALL,
                text_color=DISABLED_FG, anchor="w",
            ).grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=6)
            return
        for row, (label, value) in enumerate(lines):
            ctk.CTkLabel(self._card, text=f"{label}:", font=FONT_SMALL, anchor="w").grid(
                row=row, column=0, sticky="nw", padx=(8, 6), pady=(4 if row == 0 else 1, 0),
            )
            val = ctk.CTkLabel(
                self._card, text=value, font=FONT_BODY, anchor="w", wraplength=200, justify="left",
            )
            val.grid(row=row, column=1, sticky="w", padx=(0, 8), pady=(4 if row == 0 else 1, 0))
            self._card_rows.append((label, val))
        ctk.CTkFrame(self._card, height=4, fg_color="transparent").grid(row=len(lines), column=0)

    # -- settings tab ------------------------------------------------------------

    def _build_settings_tab(self, tab):
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)
        scroll = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(1, weight=1)

        settings = self._controller.settings
        for row, (key, (label, kind)) in enumerate(_S.items()):
            ctk.CTkLabel(scroll, text=label, font=FONT_BODY, anchor="w").grid(
                row=row, column=0, sticky="w", padx=(0, PAD_Y), pady=4,
            )
            var = ctk.StringVar(value=str(settings.get(key, "")))
            self._setting_vars[key] = var
            ctk.CTkEntry(
                scroll, textvariable=var, height=ENTRY_HEIGHT, corner_radius=CORNER_RADIUS,
                font=FONT_BODY,
            ).grid(row=row, column=1, sticky="ew", pady=4)
            if kind in ("csv", "xlsx", "dir"):
                ctk.CTkButton(
                    scroll, text="Browse", width=90, height=ENTRY_HEIGHT - 6, font=FONT_SMALL,
                    fg_color="transparent", border_width=1,
                    command=lambda k=key, kd=kind: self._browse(k, kd),
                ).grid(row=row, column=2, padx=(6, 0), pady=4)

        row = len(_S)
        ctk.CTkLabel(
            scroll,
            text="The archive CSV is the full data frame the analysis app exports; the "
                 "enrolment workbook is the lab's master log of names and MRNs. Names and "
                 "MRNs are read from the workbook on every run and written only onto the "
                 "exported PDFs.",
            font=FONT_SMALL, text_color=SUBTITLE_COLOR, anchor="w", wraplength=900, justify="left",
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(PAD_Y, 4))
        row += 1
        self._save_btn = ctk.CTkButton(
            scroll, text="Save settings", width=150, height=BUTTON_HEIGHT, font=FONT_BUTTON,
            fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, command=self._on_save_settings,
        )
        self._save_btn.grid(row=row, column=0, sticky="w", pady=(PAD_Y, 0))
        self._settings_msg = ctk.CTkLabel(
            scroll, text="", font=FONT_SMALL, anchor="w", wraplength=900, justify="left",
        )
        self._settings_msg.grid(row=row, column=1, columnspan=2, sticky="w", pady=(PAD_Y, 0))

    def _browse(self, key: str, kind: str):
        var = self._setting_vars[key]
        current = var.get()
        initial = str(Path(current).parent) if current else None
        if kind == "csv":
            chosen = filedialog.askopenfilename(
                title="Archive CSV (full data frame)",
                filetypes=[("CSV", "*.csv"), ("All files", "*.*")], initialdir=initial,
            )
        elif kind == "xlsx":
            chosen = filedialog.askopenfilename(
                title="Enrolment workbook",
                filetypes=[("Excel workbook", "*.xlsx *.xlsm"), ("All files", "*.*")],
                initialdir=initial,
            )
        else:
            chosen = filedialog.askdirectory(initialdir=current or None)
        if chosen:
            var.set(chosen)

    def _settings_values(self) -> dict:
        return {key: var.get().strip() for key, var in self._setting_vars.items()}

    def _on_save_settings(self):
        problems = self._controller.save_settings(self._settings_values())
        if problems:
            self._settings_msg.configure(text="\n".join(problems), text_color=ERROR_COLOR)
            return
        self._settings_msg.configure(text="Saved.", text_color=SUCCESS_COLOR)
        self._set_status("Settings saved.")
        if not self._controller.missing_configuration():
            self._tabs.set("Report")
            self._on_load()

    # -- actions -----------------------------------------------------------------

    def _set_busy(self, busy: bool):
        self._busy = busy
        state = "disabled" if busy else "normal"
        for btn in (self._load_btn, self._save_btn):
            btn.configure(state=state)

    def _set_status(self, text: str, warn: bool = False, error: bool = False):
        self._status_var.set(text)
        color = ERROR_COLOR if error else (_WARN_COLOR if warn else self._status_default_color)
        self._status_label.configure(text_color=color)

    def _run_in_thread(self, work, on_done, on_error=None):
        on_error = on_error or self._on_error

        def target():
            try:
                result = work()
            except Exception as exc:   # surfaced to the status line, never lost
                # Passed as an argument, not read by a lambda later: Python
                # unbinds ``exc`` when this block ends, so a lambda raised
                # NameError inside Tk and the window stayed busy for good.
                self.after(0, on_error, exc)
                return
            self.after(0, self._deliver, on_done, on_error, result)
        threading.Thread(target=target, daemon=True).start()

    def _deliver(self, on_done, on_error, result):
        """Hand *result* to *on_done*; a failure there must still free the window."""
        try:
            on_done(result)
        except Exception as exc:
            on_error(exc)

    def _on_error(self, exc: Exception):
        self._set_busy(False)
        self._graphs.set_exporting(False)
        self._set_status(f"{type(exc).__name__}: {exc}", error=True)

    def _on_load_error(self, exc: Exception):
        # The usual cause is a file being replaced while it is read: the
        # workbook mid-save in Excel, or a new CSV still being copied in.
        self._on_error(exc)
        self._set_status(
            f"Could not read the archive CSV or the enrolment workbook. "
            f"{type(exc).__name__}: {exc}. If either file is open in Excel or still "
            f"being saved or copied, wait for it to finish, then press Reload data.",
            error=True,
        )

    def _on_load(self):
        if self._busy:
            return
        missing = self._controller.missing_configuration()
        if missing:
            self._tabs.set("Settings")
            self._set_status("Fill in the settings first: " + ", ".join(missing), warn=True)
            return
        self._set_busy(True)
        self._set_status("Reading the archive CSV and the enrolment workbook...")
        self._run_in_thread(self._controller.load, self._on_loaded, self._on_load_error)

    def _on_loaded(self, directory):
        self._selected = None
        self._selected_date = None
        self._controller.clear_selection()
        self._render_visits(None)
        self._render_card(None)
        self._caveat.configure(text="")
        self._graphs.refresh()
        self._graphs.set_last_export_folder(None)
        self._render_results(self._controller.search(self._query.get()))
        self._set_busy(False)
        issues = self._controller.issues_lines()
        summary = self._controller.load_summary()
        if issues:
            self._set_status(summary + " " + " ".join(issues), warn=True)
        else:
            self._set_status(summary)
        self._search_entry.focus_set()

    def _on_query_changed(self, *_args):
        if self._controller.directory is None:
            return
        self._render_results(self._controller.search(self._query.get()))

    def _on_pick(self, participant):
        self._selected = participant
        self._selected_date = None
        self._highlight_result()
        self._render_card(participant)
        self._caveat.configure(text=self._controller.caveat_for(participant))
        self._render_visits(participant)
        dates = self._controller.visit_dates(participant)
        if dates:
            self._on_pick_visit(dates[0])
        else:
            self._controller.clear_selection()
            self._graphs.refresh()
            self._set_status(
                f"{participant.display_name} ({participant.label}) is enrolled but has no "
                f"visits in the archive CSV.", warn=True,
            )

    def _on_pick_visit(self, when: datetime):
        if self._selected is None:
            return
        self._selected_date = when
        self._controller.select_visit(self._selected, when)
        self._highlight_visit()
        self._graphs.refresh()
        self._graphs.set_last_export_folder(None)
        self._set_status(
            f"{self._selected.display_name} ({self._selected.label}), visit "
            f"{when.strftime('%d/%m/%Y')}: tick the graphs for the report, then Export."
        )

    def _on_export(self):
        """Called by the graphs page once every ticked graph has been built."""
        folder, name = self._graphs.report_target()
        self._graphs.set_exporting(True)
        self._graphs.show_note("Writing the report...")
        self._run_in_thread(
            lambda: self._controller.export_report(folder, name), self._on_exported,
        )

    def _on_exported(self, result):
        self._graphs.set_exporting(False)
        notes = []
        if not result.identified:
            notes.append(f"de-identified: {result.unresolved_reason}")
        elif result.partial:
            notes.append(f"incomplete identification: {result.unresolved_reason}")
        if result.overlaps:
            notes.append("the identity box overlaps the cover's content; check page 1")
        text = f"Report written: {result.path}"
        if notes:
            text += "  (" + "; ".join(notes) + ")"
        self._graphs.show_export_result(text)
        self._graphs.set_last_export_folder(result.path.parent)
        self._set_status(text, warn=bool(notes))
