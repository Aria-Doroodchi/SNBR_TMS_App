"""Cycle counts for T-SICI / A-SICI (from the .MEM) and T-SICF / A-SICF (from the
Qtrac Excel export), and their path into the REDCap import.

Every file here is synthetic: real .MEM files and Qtrac workbooks are patient
data and must never be committed.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd
import pytest

from parser.cycle_counts import (
    mem_cycle_counts,
    phase_cycle_counts,
    read_mem_cycle_counts,
    read_xlsx_cycle_counts,
)
from parser.mem_parser import initialize_record
from processing.redcap_mapper import cycles_to_redcap, to_redcap_dataframe
from tests import _xlsx_fixtures as fx

TOKEN = fx.TOKEN  # TP3C60520A


def _mem_lines(tsici: str | None = "(n=10)", asici_rel: str | None = "(n=6)",
               asici_abs: str | None = "(n=6)") -> list[str]:
    lines = ["Name: SNBR-001", "", "EXTRA WAVEFORMS", ""]
    lines += ["!T-SICFvISI(%RMT)(Parallel)", "14\t200\t70\tLogRegress", "1.0\t95.1", ""]
    if tsici is not None:
        lines += ["!T-SICIvISI(%RMT)(Parallel)", f"6\t200\t70\tLogRegress\t{tsici}".rstrip(),
                  "1.0\t80.0", "2.5\t70.0", ""]
    if asici_abs is not None:
        lines += ["!A-SICIvISI(abs)", f"7\t200\t70\t1100\tGeometric\t{asici_abs}".rstrip(),
                  "1.0\t0.4", ""]
    if asici_rel is not None:
        lines += ["!A-SICIvISI(rel)", f"7\t200\t70\t1100\tGeometric\t{asici_rel}".rstrip(),
                  "1.0\t40.0", ""]
    return [line + "\n" for line in lines]


# ---------------------------------------------------------------------------
# .MEM
# ---------------------------------------------------------------------------

def test_mem_counts_are_read_from_the_descriptor_line():
    assert mem_cycle_counts(_mem_lines("(n=10)", "(n=6)")) == {"T_SICI": 10, "A_SICI": 6}


def test_rel_block_is_preferred_and_abs_is_the_fallback():
    assert mem_cycle_counts(_mem_lines(None, "(n=7)", "(n=9)"))["A_SICI"] == 7
    assert mem_cycle_counts(_mem_lines(None, None, "(n=9)"))["A_SICI"] == 9


def test_files_before_march_2022_have_no_count():
    assert mem_cycle_counts(_mem_lines("", "", "")) == {}


def test_sicf_is_never_read_from_the_mem():
    assert "T_SICF" not in mem_cycle_counts(_mem_lines())
    assert "A_SICF" not in mem_cycle_counts(_mem_lines())


def test_unreadable_file_gives_nothing(tmp_path):
    assert read_mem_cycle_counts(tmp_path / "missing.MEM") == {}


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------

def test_sicf_count_is_the_most_common_per_isi_count():
    pulse = {"time": 0.0}
    phases = {"t_sicf": {1.0: [pulse] * 10, 1.3: [pulse] * 10, 1.6: [pulse] * 42},
              "a_sicf": {1.0: [pulse] * 2, 1.3: [pulse] * 3}}
    # a stray-pulse ISI does not win; a tie goes to the larger count
    assert phase_cycle_counts(phases) == {"T_SICF": 10, "A_SICF": 3}


def test_counts_from_a_synthetic_workbook(tmp_path):
    path = fx.write_tsici_workbook(tmp_path)
    # the fixture's A-SICF phase has three pairs per ISI and there is no T-SICF
    assert read_xlsx_cycle_counts(path) == {"A_SICF": 3}


# ---------------------------------------------------------------------------
# REDCap coding
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n, expected", [
    (10, (10, None)), (6, (6, None)),
    (7, (6, None)), (8, (6, None)), (9, (6, None)),   # 10 cut short is recorded as 6
    (3, (999, 3)), (5, (999, 5)), (11, (999, 11)), (24, (999, 24)), (1, (999, 1)), (30, (999, 30)),
    (0, (None, None)), (31, (None, None)), (None, (None, None)), (float("nan"), (None, None)),
])
def test_cycles_to_redcap(n, expected):
    assert cycles_to_redcap(n) == expected


def test_mapper_turns_counts_into_radio_and_other():
    df = pd.DataFrame([{**initialize_record(), "T_SICI_cycles_n": 8, "A_SICF_cycles_n": 3}])
    out = to_redcap_dataframe(df).iloc[0]
    assert out["t_sici_p_cycles_n"] == 6 and pd.isna(out["t_sici_p_cycles_n_oth"])
    assert out["a_sicf_cycles_n"] == 999 and out["a_sicf_cycles_n_oth"] == 3
    assert pd.isna(out["t_sicf_p_cycles_n"])
    assert "T_SICI_cycles_n" not in out.index


# ---------------------------------------------------------------------------
# End to end through the exporter
# ---------------------------------------------------------------------------

_CYCLE_FIELDS = [
    "t_sici_p_cycles_n", "t_sici_p_cycles_n_oth", "a_sici_1000_cycles_n",
    "a_sici_1000_cycles_n_oth", "a_sicf_cycles_n", "a_sicf_cycles_n_oth",
    "t_sicf_p_cycles_n", "t_sicf_p_cycles_n_oth",
]
_GATES = ["tsicip_completion", "asici1000_completion", "asicf_completion", "tsicfp_completion"]


def _world(tmp_path, *, tsici="(n=8)", asici="(n=3)", rc_extra=None, xlsx=True):
    mem = tmp_path / "mem" / f"SNBR-001-{TOKEN}.MEM"
    mem.parent.mkdir()
    mem.write_text("".join(_mem_lines(tsici, asici, asici)), encoding="utf-8")
    xlsx_index = {TOKEN: fx.write_tsici_workbook(tmp_path / "xlsx")} if xlsx else None

    record = initialize_record()
    record.update(Study="SNBR", ID=1, Date="20/05/2026", Stimulated_cortex="L",
                  source_file=mem.name)
    py_df = pd.DataFrame([record])

    # A REDCap export from before the cycle fields existed, unless told otherwise.
    rc_cols = ["record_id", "redcap_event_name", "tt_test_date", "cortex",
               "tt_operator"] + _GATES
    rc_vals = ["001", "visit_1_arm_1", "2026-05-20", "1", "AD", "", "", "", ""]
    for col, val in (rc_extra or {}).items():
        rc_cols.append(col)
        rc_vals.append(val)
    rc_export = tmp_path / "rc.csv"
    with open(rc_export, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(rc_cols)
        w.writerow(rc_vals)
    dict_csv = tmp_path / "dict.csv"
    with open(dict_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Variable / Field Name", "Form Name"])
        w.writerow(["tt_operator", "tms_testing"])
        for col in _GATES + _CYCLE_FIELDS:
            w.writerow([col, "tms_values"])
    template_csv = tmp_path / "template.csv"
    with open(template_csv, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(["record_id", "redcap_event_name", "tt_operator"]
                               + _GATES + _CYCLE_FIELDS)
    return py_df, rc_export, dict_csv, template_csv, {mem.name: mem}, xlsx_index


def _export(tmp_path, **kwargs):
    from reports.redcap_exporter import generate_redcap_import

    py_df, rc, dd, tpl, mem_files, xlsx_index = _world(tmp_path, **kwargs)
    import_df, path, summary = generate_redcap_import(
        py_df, rc, dd, tpl, tmp_path / "out", mem_files=mem_files, xlsx_index=xlsx_index,
    )
    return import_df, path, summary


def test_all_four_counts_reach_the_import(tmp_path):
    import_df, path, summary = _export(tmp_path)
    row = import_df.iloc[0]
    assert row["record_id"] == "001"
    assert row["t_sici_p_cycles_n"] == 6                         # MEM 8 -> 6
    assert row["a_sici_1000_cycles_n"] == 999 and row["a_sici_1000_cycles_n_oth"] == 3
    assert row["a_sicf_cycles_n"] == 999 and row["a_sicf_cycles_n_oth"] == 3   # from the Excel
    assert "t_sicf_p_cycles_n" not in import_df.columns or pd.isna(row["t_sicf_p_cycles_n"])
    # the gates that make the fields visible are set
    assert row["tsicip_completion"] == 1 and row["asicf_completion"] == 1
    # integers, never "6.0"
    text = path.read_text(encoding="utf-8")
    assert ".0" not in text
    assert summary["cycle_counts"]["found"] == {"T_SICI": 1, "A_SICI": 1, "T_SICF": 0, "A_SICF": 1}
    assert summary["quality_checks"]["status"] == "PASS"


def test_tms_testing_fields_are_never_written(tmp_path):
    import_df, _, _ = _export(tmp_path)
    assert "tt_operator" not in import_df.columns
    assert set(import_df.columns) - {"record_id", "redcap_event_name"} <= set(
        _GATES + _CYCLE_FIELDS
    )


def test_no_excel_export_leaves_sicf_blank(tmp_path):
    import_df, _, summary = _export(tmp_path, xlsx=False)
    assert "a_sicf_cycles_n" not in import_df.columns
    assert "asicf_completion" not in import_df.columns
    assert import_df.iloc[0]["t_sici_p_cycles_n"] == 6
    assert any("Excel" in w for w in summary["quality_checks"]["warnings"])


def test_a_differing_redcap_value_is_overwritten(tmp_path):
    import_df, _, summary = _export(
        tmp_path, tsici="(n=10)", rc_extra={"t_sici_p_cycles_n": "6"},
    )
    assert import_df.iloc[0]["t_sici_p_cycles_n"] == 10
    assert summary["per_column"]["t_sici_p_cycles_n"] == 1


def test_a_matching_redcap_value_is_not_resent(tmp_path):
    import_df, _, _ = _export(tmp_path, tsici="(n=7)", rc_extra={"t_sici_p_cycles_n": "6"})
    assert "t_sici_p_cycles_n" not in import_df.columns


def test_a_count_redcap_cannot_hold_is_left_blank_and_named(tmp_path):
    import_df, _, summary = _export(tmp_path, tsici="(n=0)")
    assert "t_sici_p_cycles_n" not in import_df.columns
    assert summary["cycle_counts"]["unrecordable"] == [
        {"record_id": 1, "date": "20/05/2026", "measure": "T_SICI", "cycles": 0}
    ]
    assert any("T-SICI has 0 cycles" in w for w in summary["quality_checks"]["warnings"])


def test_without_folders_the_export_is_unchanged(tmp_path):
    from reports.redcap_exporter import generate_redcap_import

    py_df, rc, dd, tpl, _, _ = _world(tmp_path)
    import_df, _, summary = generate_redcap_import(py_df, rc, dd, tpl, tmp_path / "out")
    assert import_df.empty
    assert summary["cycle_counts"]["found"] == {m: 0 for m in ("T_SICI", "A_SICI", "T_SICF", "A_SICF")}


def test_panel_status_names_what_was_read():
    from gui.redcap_panel import cycle_count_lines

    text = cycle_count_lines({
        "found": {"T_SICI": 4, "A_SICI": 2, "T_SICF": 0, "A_SICF": 1},
        "mem_folder": True, "xlsx_folder": False,
        "unrecordable": [{"record_id": 5, "date": "01/02/2026", "measure": "A_SICI", "cycles": 0}],
    })
    assert "T-SICI 4, A-SICI 2, T-SICF 0, A-SICF 1" in text
    assert "no Qtrac Excel folder" in text
    assert "record 005 01/02/2026 A-SICI = 0 cycles" in text
