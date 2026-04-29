"""Unit tests for the motor nerve conduction study (CMAP) parser."""

import json
import sys
from pathlib import Path

import pytest

# Allow imports from the SNBR_TMS_App package root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parser.cmap_parser import parse_cmap_file
from processing.df_builder import (
    build_cmap_dataframe,
    build_mem_dataframe,
    merge_cmap_into_mem,
)

# Example files provided by the lab. Tests are skipped when the share is not
# mounted (e.g. CI) so the suite stays green off the Windows lab machine.
_SAMPLE_PDF = Path(
    r"Y:\Merged Data\Viking\EMGRQ\AA-SNBR-186 AA-SNBR-186, AA-SNBR-186   14-Apr-26 9-26 AM.pdf"
)
_SAMPLE_DOCX = Path(
    r"Y:\Merged Data\Viking\Industry\AA-SNBR-136 AA-SNBR- (AA-SNBR-136) 3_27_2025 12_27_44 PM R1.docx"
)
_SAMPLE_PDF_MUNIX = Path(
    r"Y:\Merged Data\Viking\EMGRQ\AA-SNBR-187 AA-SNBR-187, AA-SNBR-187   20-Apr-26 10-42 AM.pdf"
)

pytestmark = pytest.mark.skipif(
    not (_SAMPLE_PDF.exists() and _SAMPLE_DOCX.exists()),
    reason="Sample CMAP files on the Y: share are not available.",
)


def test_parse_pdf_extracts_participant_date_and_rows():
    record = parse_cmap_file(_SAMPLE_PDF)

    assert record["Study"] == "SNBR"
    assert record["ID"] == 186
    assert record["Date"] == "14/04/2026"
    assert record["source_file"] == _SAMPLE_PDF.name

    rows = json.loads(record["CMAP_table"])
    assert len(rows) == 2

    first = rows[0]
    assert "Ulnar" in first["nerve_site"]
    assert first["muscle"] == "FDI"
    assert first["latency_ms"] == pytest.approx(4.21)
    assert first["amplitude_mv"] == pytest.approx(2.2)


def test_parse_docx_extracts_participant_date_and_rows():
    record = parse_cmap_file(_SAMPLE_DOCX)

    assert record["Study"] == "SNBR"
    assert record["ID"] == 136
    assert record["Date"] == "27/03/2025"

    rows = json.loads(record["CMAP_table"])
    assert len(rows) >= 1
    first = rows[0]
    assert "Median" in first["nerve_site"]
    # The docx file shows Median APB on the Wrist site
    assert first["muscle"] == "APB"
    assert first["latency_ms"] == pytest.approx(2.77)
    assert first["amplitude_mv"] == pytest.approx(14.3)


def test_merge_cmap_writes_onto_matching_mem_row():
    record = parse_cmap_file(_SAMPLE_PDF)
    cmap_df = build_cmap_dataframe([record])

    mem_df = build_mem_dataframe([{
        "Study": "SNBR", "ID": 186, "Date": "14/04/2026",
        "Age": 55, "Sex": "M", "Subject_type": "Patient",
        "Stimulated_cortex": "LM", "source_file": "SNBRMC186A.MEM",
    }])

    merged = merge_cmap_into_mem(mem_df, cmap_df)

    assert merged.attrs["cmap_rows_merged"] == 1
    assert merged.attrs["cmap_rows_dropped"] == 0

    row = merged[merged["ID"] == 186].iloc[0]
    assert row["CMAP_table"], "Expected CMAP_table to be populated"
    parsed = json.loads(row["CMAP_table"])
    assert len(parsed) == 2
    assert parsed[0]["muscle"] == "FDI"


def test_parse_pdf_extracts_munix_when_present():
    if not _SAMPLE_PDF_MUNIX.exists():
        pytest.skip("SNBR-187 sample PDF with MUNIX not available.")
    record = parse_cmap_file(_SAMPLE_PDF_MUNIX)

    assert record["ID"] == 187
    assert record["Date"] == "20/04/2026"
    assert record["MUNIX_table"], "Expected MUNIX_table to be populated"

    rows = json.loads(record["MUNIX_table"])
    assert len(rows) == 1
    row = rows[0]
    assert row["num_sip"] == pytest.approx(9)
    assert row["a"] == pytest.approx(5587)
    assert row["alpha"] == pytest.approx(-0.99)
    assert row["munix"] == pytest.approx(287)
    assert row["musix"] == pytest.approx(63)


def test_parse_cmap_without_munix_leaves_munix_none():
    record = parse_cmap_file(_SAMPLE_PDF)
    assert record["MUNIX_table"] is None


def test_merge_writes_munix_onto_matching_mem_row():
    if not _SAMPLE_PDF_MUNIX.exists():
        pytest.skip("SNBR-187 sample PDF with MUNIX not available.")
    record = parse_cmap_file(_SAMPLE_PDF_MUNIX)
    cmap_df = build_cmap_dataframe([record])

    mem_df = build_mem_dataframe([{
        "Study": "SNBR", "ID": 187, "Date": "20/04/2026",
        "Age": 50, "Sex": "F", "Subject_type": "Patient",
        "Stimulated_cortex": "L", "source_file": "SNBRMC187A.MEM",
    }])

    merged = merge_cmap_into_mem(mem_df, cmap_df)

    row = merged[merged["ID"] == 187].iloc[0]
    assert row["MUNIX_table"], "Expected MUNIX_table to be populated on merged row"
    munix = json.loads(row["MUNIX_table"])
    assert munix[0]["munix"] == pytest.approx(287)


def test_merge_drops_unmatched_cmap_rows():
    """Unmatched CMAP records must be dropped, not appended.

    Appending them would create phantom visit dates with no MEM data that
    the participant panel and Quick Start would then select, blocking every
    other graph type for that visit.
    """
    record = parse_cmap_file(_SAMPLE_PDF)
    cmap_df = build_cmap_dataframe([record])

    # MEM row has a different ID — no match.
    mem_df = build_mem_dataframe([{
        "Study": "SNBR", "ID": 999, "Date": "01/01/2020",
        "Age": 60, "Sex": "F", "Subject_type": "Control",
        "Stimulated_cortex": "LM", "source_file": "SNBRMC999A.MEM",
    }])

    merged = merge_cmap_into_mem(mem_df, cmap_df)

    assert merged.attrs["cmap_rows_merged"] == 0
    assert merged.attrs["cmap_rows_dropped"] == 1
    # Only the original MEM row — no phantom CMAP row appended.
    assert len(merged) == 1
    assert int(merged["ID"].iloc[0]) == 999
