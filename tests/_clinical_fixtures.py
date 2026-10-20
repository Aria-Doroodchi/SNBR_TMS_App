"""Synthetic data for the clinical app's tests: a data frame and an enrolment log.

Shared by the directory, export and window tests so they all describe the
same small world:

* SNBR-080 **Jane Doe**, MRN 1234567 -- two visits, a patient (the
  identified case; the roster spells her ``AA-SNBR-080`` to exercise the
  prefix rule).
* SNBR-081 **José Müller**, no MRN -- one visit, a control (the incomplete
  case, and an accented name).
* SNBR-003 **Ann Smith** and NIALS-003 **Bob Jones** -- the same number in
  two studies, one visit each (the collision case).
* SNBR-010..015 -- a cohort with two visits each and **no roster row** (the
  unidentified case, and enough people for the cohort graphs to draw).
* SNBR-099 **Never Tested** -- in the roster, nowhere in the data.

Nothing here is real. Never replace it with a lab file: two public remotes.
"""

from __future__ import annotations

from pathlib import Path

from parser.mem_parser import TSICI_ISIS, initialize_record
from processing.df_builder import build_mem_dataframe

ROSTER_ROWS = [
    ("AA-SNBR-080", "Jane Doe", "1234567"),
    ("SNBR-081", "José Müller", None),
    ("SNBR-003", "Ann Smith", "7654321"),
    ("NIALS-003", "Bob Jones", "1111111"),
    ("SNBR-099", "Never Tested", "9999999"),
]


def record(pid, date, value, *, study="SNBR", cortex="L", side="R", muscle="FDI",
           subject_type="Patient"):
    r = initialize_record()
    r.update(
        Study=study, ID=pid, Date=date, Subject_type=subject_type,
        Stimulated_cortex=cortex, Muscle=muscle, Recorded_side=side, Age=60, Sex="M",
        source_file=f"{study}-{pid:03d}-{date.replace('/', '')}-{cortex}.MEM",
    )
    for isi in TSICI_ISIS:
        r[f"T_SICI_{isi}"] = value
    r["RMT200"] = 45 + pid % 7
    return r


def records():
    out = [
        record(80, "22/04/2024", 96.5),
        record(80, "18/08/2026", 95.2),
        record(81, "01/02/2026", 90.0, subject_type="Control"),
        record(3, "01/03/2026", 88.0),
        record(3, "05/03/2026", 70.0, study="NIALS"),
    ]
    for pid in range(10, 16):
        out += [record(pid, "01/01/2026", 80.0 + pid), record(pid, "01/06/2026", 82.0 + pid)]
    return out


def dataframe():
    return build_mem_dataframe(records())


def write_roster(path: Path, rows=ROSTER_ROWS, sheet="SNBR enrolment log") -> Path:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(["Patient ID", "Patient Name", "MRN"])
    for row in rows:
        ws.append(list(row))
    wb.save(path)
    return path


def write_world(root: Path) -> dict:
    """The CSV and the workbook under *root*; returns their paths."""
    root.mkdir(parents=True, exist_ok=True)
    csv = root / "df.csv"
    dataframe().to_csv(csv, index=False)
    roster = write_roster(root / "roster.xlsx")
    return {"csv": csv, "roster": roster, "export": root / "reports"}
