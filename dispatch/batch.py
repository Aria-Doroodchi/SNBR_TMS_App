"""Assemble a hand-off batch: stamped PDFs packed into size-capped folders.

The app identifies reports and tracks what was sent; it does not send. The
operator emails the files by hand, so the app's job ends at a folder::

    <identified_dir>/2026-09-08_batch_<run>/
        part_1_of_2/  John_Smith_1234567_20260818.pdf ...
        part_2_of_2/  ...

Each part folder is sized to fit one email: parts are filled first-fit in
worklist order against the cap on **raw file bytes**, which is what a browser
upload enforces. A single report over the cap gets a part to itself and a
warning; it is never silently dropped.

Attachment names carry the identity exactly as the roster spells it
(``First Last`` -> ``First_Last``), then the MRN and the visit date; whichever
of the two the enrolment log lacks is simply left out. Only a report with
neither keeps its de-identified ``report_<Study>_<ID>_<date>`` name, so the
kinds are distinguishable in the mailbox as well as on their cover pages.

Sending is recorded per report: :func:`mark_sent` declares any subset of the
batch sent, and :func:`mark_part_sent` is that for one part folder.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from dispatch.ledger import Ledger, new_run_id
from dispatch.stamp import stamp_report
from dispatch.worklist import WorklistItem, week_start_of
from reports.export_naming import sanitize_token

MB = 1024 * 1024


@dataclass
class BatchEntry:
    item: WorklistItem
    filename: str
    path: Path
    size: int


@dataclass
class Part:
    index: int          # 1-based
    parts: int
    folder: Path
    entries: list[BatchEntry]
    warnings: list[str] = field(default_factory=list)

    @property
    def total_bytes(self) -> int:
        return sum(e.size for e in self.entries)


@dataclass
class Batch:
    run_id: str
    folder: Path
    week_start: date
    parts: list[Part]
    warnings: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return sum(len(p.entries) for p in self.parts)

    @property
    def entries(self) -> list[BatchEntry]:
        return [e for p in self.parts for e in p.entries]

    def part_of(self, entry: BatchEntry) -> Part:
        for part in self.parts:
            if any(e is entry for e in part.entries):
                return part
        raise ValueError(f"{entry.filename} is not in batch {self.run_id}")


# -- naming ----------------------------------------------------------------

def attachment_filename(item: WorklistItem) -> str:
    """``First_Last_MRN_YYYYMMDD.pdf``, dropping whichever field the log lacks.

    A roster row with a name but no MRN gives ``First_Last_YYYYMMDD.pdf``, and
    one with only an MRN gives ``MRN_YYYYMMDD.pdf`` -- the recipient can still
    tell the attachments apart. Only
    a report with neither keeps its de-identified source name.
    """
    if not item.identifying:
        return item.report.path.name
    ident = item.identity
    parts = (sanitize_token(ident.name), sanitize_token(ident.mrn), item.report.visit_token)
    return "_".join(p for p in parts if p) + ".pdf"


def _unique_in(name: str, taken: set[str]) -> str:
    """Never let two attachments in one batch share a name."""
    if name.lower() not in taken:
        taken.add(name.lower())
        return name
    stem, dot, ext = name.rpartition(".")
    counter = 2
    while True:
        candidate = f"{stem}_{counter}.{ext}"
        if candidate.lower() not in taken:
            taken.add(candidate.lower())
            return candidate
        counter += 1


# -- packing ---------------------------------------------------------------

def plan_parts(entries: list[BatchEntry], cap_bytes: int) -> tuple[list[list[BatchEntry]], list[str]]:
    """First-fit in order. Oversize entries go alone, with a warning."""
    parts: list[list[BatchEntry]] = []
    current: list[BatchEntry] = []
    current_bytes = 0
    warnings: list[str] = []
    for entry in entries:
        if entry.size > cap_bytes:
            if current:
                parts.append(current)
                current, current_bytes = [], 0
            parts.append([entry])
            warnings.append(
                f"{entry.filename} is {entry.size / MB:.1f} MB, over the "
                f"{cap_bytes / MB:.0f} MB cap; it has a part to itself and may be "
                f"refused by the mail server"
            )
            continue
        if current and current_bytes + entry.size > cap_bytes:
            parts.append(current)
            current, current_bytes = [], 0
        current.append(entry)
        current_bytes += entry.size
    if current:
        parts.append(current)
    return parts, warnings


# -- the batch -------------------------------------------------------------

def write_batch(
    items: list[WorklistItem],
    identified_dir: str | Path,
    size_cap_mb: int,
    ledger: Ledger | None = None,
    when: datetime | None = None,
) -> Batch:
    """Stamp *items*, pack them into parts and write the batch folder.

    Stamping happens first into a staging folder so parts are planned on
    the **actual** stamped sizes, then files are moved into their part
    folders. The staging folder is removed afterwards.
    """
    if not items:
        raise ValueError("nothing selected for the batch")
    when = when or datetime.now()
    run_id = new_run_id(when)
    week_start = week_start_of(when.date())
    root = Path(identified_dir) / f"{when.strftime('%Y-%m-%d')}_batch_{run_id}"
    staging = root / "_staging"
    staging.mkdir(parents=True, exist_ok=False)

    taken: set[str] = set()
    entries: list[BatchEntry] = []
    overlapped: list[str] = []
    for item in items:
        name = _unique_in(attachment_filename(item), taken)
        stamped = stamp_report(
            item.report.path, staging / name,
            item.report.key, item.report.visit_date,
            item.identity, item.unresolved_reason,
        )
        if stamped.overlaps:
            overlapped.append(name)
        path = stamped.path
        entries.append(BatchEntry(item=item, filename=name, path=path, size=path.stat().st_size))

    grouped, warnings = plan_parts(entries, int(size_cap_mb) * MB)
    for name in overlapped:
        warnings.append(
            f"{name}: no ink-free band on the cover page fit the identity box, so it "
            f"was placed at the bottom and may overlap cover content -- open and check"
        )
    total = len(grouped)
    parts: list[Part] = []
    for index, group in enumerate(grouped, start=1):
        folder = root / f"part_{index}_of_{total}"
        folder.mkdir()
        for entry in group:
            dest = folder / entry.filename
            shutil.move(str(entry.path), str(dest))
            entry.path = dest
        parts.append(Part(index=index, parts=total, folder=folder, entries=group))
    shutil.rmtree(staging, ignore_errors=True)

    batch = Batch(
        run_id=run_id, folder=root, week_start=week_start, parts=parts,
        warnings=warnings,
    )
    if ledger is not None:
        ledger.record_run(run_id, total, batch.count, str(root))
    return batch


def mark_sent(
    ledger: Ledger, batch: Batch, entries: list[BatchEntry],
) -> list[tuple[BatchEntry, bool, str]]:
    """Declare each of *entries* sent; every row is re-checked against the ledger.

    The app cannot see the send -- it happens in the operator's mailbox --
    so this records their declaration. A report someone else has already
    marked is refused, not recorded twice, and the message says who did.
    """
    results = []
    for entry in entries:
        part = batch.part_of(entry)
        recorded, message = ledger.mark_sent(entry.item.report, batch.run_id, part.index, part.parts)
        results.append((entry, recorded, message))
    return results


def mark_part_sent(ledger: Ledger, batch: Batch, part: Part) -> list[tuple[BatchEntry, bool, str]]:
    """Declare every report in one part folder sent."""
    return mark_sent(ledger, batch, part.entries)
