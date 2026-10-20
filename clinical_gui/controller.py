"""The one bridge between the clinical window and everything beneath it.

Subclasses :class:`gui.controller.AppController` rather than wrapping it: the
graph pipeline the Visualization page drives -- availability, recording
targets, cohort restriction, every figure builder -- is the analysis app's
and is inherited whole, so the two apps draw the same graph for the same
visit. What this class adds is the clinical side: its own settings, the
enrolment roster, the participant directory and search, and the identified
export. What it *overrides* are the few hooks the Visualization page uses to
read or write the analysis app's saved defaults, so this app never touches
that file.

Every method is synchronous; the window runs the slow ones (``load``,
``export_report``) on a thread and marshals results back with ``after``.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from clinical import settings as cs
from clinical.directory import Directory, Participant, build_directory
from clinical.export import ExportedReport, export_identified_report
from dispatch.roster import load_roster
from gui.controller import AppController
from gui.visualization_panel import GRAPH_REGISTRY


class ClinicalController(AppController):
    def __init__(self):
        super().__init__()
        self.settings: dict = cs.load_settings()
        self.roster = None
        self.directory: Directory | None = None
        self.participant: Participant | None = None
        self.last_export: ExportedReport | None = None

    # -- settings ------------------------------------------------------------

    def missing_configuration(self) -> list[str]:
        return cs.missing_required(self.settings)

    def validate(self, values: dict) -> list[str]:
        """Problems that must be fixed before *values* can be saved."""
        problems = []
        csv_path = values.get(cs.KEY_CSV_PATH, "")
        if csv_path and not Path(csv_path).is_file():
            problems.append(f"Archive CSV not found: {csv_path}")
        roster = values.get(cs.KEY_ROSTER_PATH, "")
        if roster and not Path(roster).is_file():
            problems.append(f"Enrolment workbook not found: {roster}")
        export_dir = values.get(cs.KEY_EXPORT_DIR, "")
        if export_dir and Path(export_dir).exists() and not Path(export_dir).is_dir():
            problems.append(f"Export folder is not a folder: {export_dir}")
        return problems

    def save_settings(self, values: dict) -> list[str]:
        """Validate then persist; returns the problems (nothing saved if any)."""
        problems = self.validate(values)
        if problems:
            return problems
        cs.save_settings(**values)
        self.settings = cs.load_settings()
        return []

    # -- the hooks the Visualization page calls --------------------------------
    #
    # AppController reads and writes the analysis app's saved defaults for
    # these. On a collaborator's machine that file does not exist and must not
    # be created, so each is redirected to this app's own settings or made
    # inert.

    def get_default_export_paths(self) -> dict[str, str]:
        folder = self.settings.get(cs.KEY_EXPORT_DIR, "")
        return {"csv": folder, "pdf": folder}

    def default_export_folder(self, kind: str) -> str:
        """The saved export folder, else beside the archive CSV, else Documents.

        The parent's rule treats a saved default that is not an existing
        directory as a *file* path and uses its parent, because the analysis
        app once saved full file paths. Here the setting is always a folder,
        and one the user has not created yet must still be where the report
        goes (the export creates it), not its parent.
        """
        saved = self.settings.get(cs.KEY_EXPORT_DIR, "").strip()
        if saved:
            return saved
        return super().default_export_folder(kind)

    def get_pulse_variability_default(self) -> bool:
        # The individual pulses need the Qtrac Excel exports, which live with
        # the .MEM files on the lab side. Never available here.
        return False

    def pulse_overlay_note(self) -> str:
        return ""

    def save_pulse_variability_default(self, enabled: bool) -> None:
        pass

    def get_selected_graphs_default(self) -> list[str]:
        """The graphs ticked when a visit is chosen: the saved set, else every graph.

        Every graph rather than none, because the person opening this app
        wants *the* report, and ticking forty boxes first is not that.
        Availability still decides what the page can actually draw.
        """
        saved = [str(k) for k in self.settings.get(cs.KEY_SELECTED_GRAPHS, [])]
        keys = [e.key for e in GRAPH_REGISTRY if e.key in saved]
        return keys or [e.key for e in GRAPH_REGISTRY]

    def save_selected_graphs_default(self, keys: list[str]) -> None:
        cs.save_settings(**{cs.KEY_SELECTED_GRAPHS: [str(k) for k in keys]})
        self.settings = cs.load_settings()

    # -- loading -------------------------------------------------------------

    def load(self) -> Directory:
        """Read the archive CSV and the roster, then join them. Slow: thread it."""
        s = self.settings
        missing = self.missing_configuration()
        if missing:
            raise ValueError("Fill in the settings first: " + ", ".join(missing))
        self.set_paths([], "", s[cs.KEY_CSV_PATH], "", "")
        df = self.load_csv_dataframe(merge_cmap=False)
        self.roster = load_roster(
            s[cs.KEY_ROSTER_PATH], s[cs.KEY_ROSTER_SHEET],
            s[cs.KEY_COL_PATIENT_ID], s[cs.KEY_COL_PATIENT_NAME], s[cs.KEY_COL_MRN],
        )
        self.directory = build_directory(df, self.roster)
        self.participant = None
        self.set_report_figures([])
        return self.directory

    def search(self, query: str) -> list[Participant]:
        if self.directory is None:
            return []
        return self.directory.search(query)

    # -- selection -----------------------------------------------------------

    def visit_dates(self, participant: Participant) -> list[datetime]:
        """Newest first: the visit a clinician usually wants is the latest."""
        return sorted(participant.visits, reverse=True)

    def select_visit(self, participant: Participant, visit_date: datetime) -> None:
        """Make *participant*'s *visit_date* the one the graphs describe.

        Seeds the recording-target selection the way the analysis app's
        participant page does: every target of the visit, or the cortex
        options for an archive that predates recording targets.
        """
        if visit_date not in participant.visits:
            raise ValueError(
                f"{participant.label} has no visit on {visit_date.strftime('%d/%m/%Y')}"
            )
        self.participant = participant
        self.set_selected_participant(participant.number, visit_date)
        self.set_report_figures([])
        targets = self.get_target_options(participant.number, visit_date)
        if targets:
            self.set_selected_targets(targets)
            self.set_selected_cortex(None)
            return
        self.set_selected_targets([])
        cortices = self.get_cortex_options(participant.number, visit_date)
        if len(cortices) > 1:
            self.set_selected_cortex(cortices)
        else:
            self.set_selected_cortex(cortices[0] if cortices else None)

    def clear_selection(self) -> None:
        """Forget the selected patient and visit (after a reload, or a no-data pick)."""
        self.participant = None
        self._selected_id = None
        self._selected_date = None
        self.set_selected_targets([])
        self.set_selected_cortex(None)
        self.set_report_figures([])

    def selected_visit(self) -> tuple[Participant | None, datetime | None]:
        _, date = self.get_selected_participant()
        return self.participant, date

    def identity_lines(self, participant: Participant | None) -> list[tuple[str, str]]:
        """What the identity card shows for *participant*."""
        if participant is None:
            return []
        absent = "not in the enrolment log"
        lines = [
            ("Patient name", participant.name or absent),
            ("MRN", participant.mrn or absent),
            ("Study ID", participant.label),
        ]
        if participant.subject_type:
            lines.append(("Patient type", participant.subject_type))
        n = len(participant.visits)
        if n == 0:
            lines.append(("Visits", "none in the data frame"))
        elif n == 1:
            lines.append(("Visits", f"1 ({participant.visits[0].strftime('%d/%m/%Y')})"))
        else:
            lines.append(("Visits", str(n)))
            lines.append(("First visit", participant.visits[0].strftime("%d/%m/%Y")))
            lines.append(("Latest visit", participant.visits[-1].strftime("%d/%m/%Y")))
        return lines

    def caveat_for(self, participant: Participant | None) -> str:
        """The amber note beside a participant, or ``""``."""
        if participant is None:
            return ""
        if not participant.has_data:
            return "No visits for this patient in the archive CSV; no report can be made."
        if participant.unidentified:
            return (
                f"Identity not resolved ({participant.unresolved_reason}); the report "
                f"cover will say so and the file keeps its de-identified name."
            )
        if participant.partial:
            return (
                f"Incomplete identification ({participant.unresolved_reason}); the "
                f"cover will print what the log has."
            )
        return ""

    # -- export --------------------------------------------------------------

    def export_report(self, folder: str = "", name: str = "") -> ExportedReport:
        """Write the identified PDF from the figures the graphs page built."""
        participant, date = self.selected_visit()
        if participant is None or date is None:
            raise ValueError("Choose a patient and a visit first.")
        items = self.get_report_figures()
        if not items:
            raise ValueError("No figures to put in the report.")
        folder = (folder or "").strip() or self.default_export_folder("pdf")
        result = export_identified_report(items, participant, date, folder, name)
        self.last_export = result
        self.set_last_exported_pdf(str(result.path))
        return result

    # -- text for the window -----------------------------------------------------

    def issues_lines(self) -> list[str]:
        """Things the user should know after a load."""
        lines: list[str] = []
        d = self.directory
        if d is None:
            return lines
        df = self.get_dataframe()
        attrs = getattr(df, "attrs", {}) if df is not None else {}
        if attrs.get("schema_stale") or attrs.get("targets_stale"):
            lines.append(
                "The archive CSV predates some of the app's columns, so some graphs "
                "may be unavailable. Ask the lab for a freshly exported data frame."
            )
        for p in d.roster_problems:
            lines.append(f"Enrolment log row {p.row}: {p.message} ({p.patient_id_raw or 'blank'})")
        unmatched = [p for p in d.participants if p.has_data and p.identity is None]
        if unmatched:
            lines.append(
                f"{len(unmatched)} participant(s) with visits are not in the enrolment "
                f"log: " + ", ".join(p.label for p in unmatched[:12])
                + (" ..." if len(unmatched) > 12 else "")
            )
        return lines

    def load_summary(self) -> str:
        d = self.directory
        if d is None:
            return "Nothing loaded."
        with_data = len(d.with_data())
        return (
            f"Loaded {with_data} participant(s) with visits and "
            f"{len(d) - with_data} enrolled without data."
        )
