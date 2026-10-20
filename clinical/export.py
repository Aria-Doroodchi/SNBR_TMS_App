"""Write an identified report: the de-identified PDF plus the identity stamp.

The report body is assembled exactly as the analysis app assembles it
(:func:`reports.pdf_renderer.render_figures_to_pdf`, from the same
``ReportItem`` list the Visualization page builds), then the cover page is
stamped with the patient's identity box by the dispatch app's
:func:`dispatch.stamp.stamp_report`. So an identified report looks the same
whichever app produced it, and the box's three variants -- identified,
incomplete, unresolved -- mean the same thing in both.

The de-identified intermediate PDF is written to a temporary directory and
deleted; only the stamped file lands in the user's folder.

File names follow the dispatch app's attachment convention
(:func:`identified_report_filename`): ``<First_Last>_<MRN>_<YYYYMMDD>.pdf``,
dropping whichever of the two the enrolment log lacks, and the analysis app's
de-identified ``report_<Study>_<ID>_<date>.pdf`` when it has neither. A name
the user types is kept and given the analysis app's
``_<Study>_ID<n>_<date>`` suffix, exactly as the Export page does.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from clinical.directory import Participant
from reports.export_naming import default_report_stem, sanitize_token, unique_path


@dataclass(frozen=True)
class ExportedReport:
    path: Path
    identified: bool       # the cover carries a name, an MRN, or both
    partial: bool          # one of the two was blank in the enrolment log
    overlaps: bool         # the box could not find an ink-free band on page 1
    unresolved_reason: str


def visit_token(visit_date: datetime) -> str:
    return visit_date.strftime("%Y%m%d")


def identified_report_filename(participant: Participant, visit_date: datetime) -> str:
    """``First_Last_1234567_20260818.pdf``; de-identified when nothing identifies."""
    if not participant.identifying:
        return f"{default_report_stem(participant.study, participant.number, visit_date)}.pdf"
    parts = (
        sanitize_token(participant.name), sanitize_token(participant.mrn),
        visit_token(visit_date),
    )
    return "_".join(p for p in parts if p) + ".pdf"


def export_suffix(participant: Participant, visit_date: datetime) -> str:
    """The analysis app's ``_<Study>_ID<n>_<date>`` stamp for a typed name."""
    study = sanitize_token(participant.study)
    return (f"_{study}" if study else "") + f"_ID{participant.number}_{visit_token(visit_date)}"


def resolve_report_path(
    participant: Participant, visit_date: datetime, folder: str | Path, name: str = "",
) -> Path:
    """Where the report goes: the automatic name made unique, or the typed one."""
    base = Path(folder)
    name = (name or "").strip()
    if not name:
        return unique_path(base / identified_report_filename(participant, visit_date))
    chosen = Path(name)
    if not chosen.suffix:
        chosen = chosen.with_suffix(".pdf")
    suffix = export_suffix(participant, visit_date)
    if not chosen.stem.endswith(suffix):
        chosen = chosen.with_stem(chosen.stem + suffix)
    return base / chosen.name


def export_identified_report(
    items: list, participant: Participant, visit_date: datetime,
    folder: str | Path, name: str = "",
) -> ExportedReport:
    """Render *items* to a PDF at *folder* and stamp the cover with the identity.

    Raises ``ValueError`` when there is nothing to render, and lets a missing
    ``pypdf`` surface as its ``ImportError``: an app whose purpose is the
    identified report must not quietly write a de-identified one instead.
    """
    from dispatch.stamp import stamp_report
    from reports.pdf_renderer import render_figures_to_pdf

    if not items:
        raise ValueError("No figures to put in the report.")
    target = resolve_report_path(participant, visit_date, folder, name)
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="snbr_clinical_") as tmp:
        plain = Path(tmp) / "deidentified.pdf"
        render_figures_to_pdf(items, plain)
        stamped = stamp_report(
            plain, target, participant.key, visit_date.date(),
            participant.identity, participant.unresolved_reason,
        )

    return ExportedReport(
        path=stamped.path,
        identified=participant.identifying,
        partial=participant.partial,
        overlaps=stamped.overlaps,
        unresolved_reason=participant.unresolved_reason,
    )
