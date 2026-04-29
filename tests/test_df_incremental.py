"""Regression tests for ``build_combined_dataframe_incremental``.

Covers the case where a MEM file is present in the archive CSV but has since
been deleted from the MEM folder — the stale row must NOT survive a re-parse.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parser.mem_parser import output_column_order
from processing.df_builder import build_combined_dataframe_incremental


_MIN_MEM = """\
Name: SNBR-999
Date: 01/01/2026
Age: 40
Sex: M
Subject type: Patient
Stim/record: L-APB -> APB

DERIVED EXCITABILITY VARIABLES

EXTRA VARIABLES
RMT50 = 50
RMT200 = 55
RMT1000 = 60
T-SICI(70%)1.0ms = -10.0

EXTRA WAVEFORMS
"""


def _write_mem(dirpath: Path, filename: str, pid: int) -> None:
    content = _MIN_MEM.replace("SNBR-999", f"SNBR-{pid:03d}")
    (dirpath / filename).write_text(content, encoding="utf-8")


def test_deleted_mem_file_does_not_persist_in_incremental_reparse(tmp_path):
    mem_dir = tmp_path / "mem"
    mem_dir.mkdir()

    # Two participants in the initial MEM folder.
    _write_mem(mem_dir, "SNBR-031-TP1C50101A.MEM", 31)
    _write_mem(mem_dir, "SNBR-032-TH2C30628A.MEM", 32)

    # First pass: full parse, export to CSV (simulating the archive).
    df1 = build_combined_dataframe_incremental(mem_dir=mem_dir)
    assert set(df1["ID"]) == {31, 32}

    csv_path = tmp_path / "SNBR_MEM_parsed_2026-01-02.csv"
    df1[output_column_order()].to_csv(csv_path, index=False)

    # Delete participant 32's MEM file.
    (mem_dir / "SNBR-032-TH2C30628A.MEM").unlink()

    # Second pass: reparse incrementally against the archive CSV. The stale
    # row for participant 32 must be dropped — before the fix it survived
    # because the fast-path "nothing changed" gate never detected deletions.
    df2 = build_combined_dataframe_incremental(
        mem_dir=mem_dir,
        existing_csv=csv_path,
    )
    assert 32 not in set(df2["ID"].dropna().astype(int)), (
        "Deleted MEM file's row leaked through the incremental fast path"
    )
    assert set(df2["ID"].dropna().astype(int)) == {31}


def test_no_changes_takes_fast_path(tmp_path):
    """Sanity check: when nothing on disk changed, the fast path still fires."""
    mem_dir = tmp_path / "mem"
    mem_dir.mkdir()
    _write_mem(mem_dir, "SNBR-031-TP1C50101A.MEM", 31)

    df1 = build_combined_dataframe_incremental(mem_dir=mem_dir)
    csv_path = tmp_path / "SNBR_MEM_parsed_2026-01-02.csv"
    df1[output_column_order()].to_csv(csv_path, index=False)

    df2 = build_combined_dataframe_incremental(
        mem_dir=mem_dir,
        existing_csv=csv_path,
    )
    assert df2.attrs.get("reused_existing") is True
    assert df2.attrs.get("new_files_parsed") == 0
