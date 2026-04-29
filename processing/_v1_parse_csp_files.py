"""
Parse CSP-focused .MEM files into a wide dataframe.

This module extracts CSP start/end timings at fixed %RMT levels and derives CSP
durations so the values can be merged into the main parsed MEM dataframe.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
from processing._v1_parse_common import (
    SECTION_DERIVED as _SECTION_DERIVED,
    SECTION_EXTRA_VARS as _SECTION_EXTRA_VARS,
    SECTION_WAVEFORMS as _SECTION_WAVEFORMS,
    build_header_parsers,
    extract_id_from_filename,
    extract_id_from_text,
    extract_study_from_text,
    parse_header_field,
)

CSP_RMT_LEVELS = ["80", "100", "120", "140", "160"]
CSP_VALUE_COLUMNS = (
    [f"CSPs_{level}" for level in CSP_RMT_LEVELS]
    + [f"CSPe_{level}" for level in CSP_RMT_LEVELS]
    + [f"CSP_{level}" for level in CSP_RMT_LEVELS]
)
CSP_NUMERIC_COLUMNS = ["ID", "Age"] + list(CSP_VALUE_COLUMNS)

_STUDY_ID_PATTERN = re.compile(r"([A-Za-z]+)\d*-0*(\d+)", flags=re.IGNORECASE)
_CSP_VALUE_PATTERN = re.compile(r"^(CSPs|CSPe)-(\d+)\(ms\)\s*=\s*([-\d.]+)")


def csp_output_columns() -> list[str]:
    """Return the stable output schema for parsed CSP records."""
    return (
        ["Study", "ID", "Date", "Age", "Sex", "Subject_type", "Stimulated_cortex"]
        + list(CSP_VALUE_COLUMNS)
        + ["source_file"]
    )


def initialize_csp_record() -> dict:
    """Return an empty parsed CSP record."""
    record = {
        "Study": np.nan,
        "ID": np.nan,
        "Date": np.nan,
        "Age": np.nan,
        "Sex": np.nan,
        "Subject_type": np.nan,
        "Stimulated_cortex": np.nan,
    }
    for column_name in CSP_VALUE_COLUMNS:
        record[column_name] = np.nan
    return record


def extract_csp_id_from_name(name_text) -> float | int:
    """Extract the participant ID from one CSP Name field when possible."""
    return extract_id_from_text(name_text, _STUDY_ID_PATTERN)


def extract_csp_study_from_name(name_text) -> str:
    """Extract the study name from one CSP Name field when possible."""
    return extract_study_from_text(name_text, _STUDY_ID_PATTERN)


def extract_csp_id_from_filename(filename) -> float | int:
    """Extract the participant ID from one CSP filename when possible."""
    return extract_id_from_filename(filename, _STUDY_ID_PATTERN)


_HEADER_PARSERS = build_header_parsers(extract_csp_id_from_name, extract_csp_study_from_name)


def _parse_header_field(stripped: str, record: dict):
    """Parse one CSP header line into the target record."""
    parse_header_field(stripped, record, _HEADER_PARSERS)


def _parse_extra_vars_line(stripped: str, record: dict):
    """Parse one EXTRA VARIABLES line for CSPs/CSPe values."""
    match = _CSP_VALUE_PATTERN.match(stripped)
    if match is None:
        return

    value_prefix, level, raw_value = match.groups()
    if level not in CSP_RMT_LEVELS:
        return

    try:
        record[f"{value_prefix}_{level}"] = float(raw_value)
    except ValueError:
        return


def recompute_csp_duration_columns(data_df: pd.DataFrame) -> pd.DataFrame:
    """Recompute derived CSP duration columns from the current start/end values."""
    updated_df = data_df.copy()
    for level in CSP_RMT_LEVELS:
        start_column = f"CSPs_{level}"
        end_column = f"CSPe_{level}"
        value_column = f"CSP_{level}"
        if start_column not in updated_df.columns:
            updated_df[start_column] = np.nan
        if end_column not in updated_df.columns:
            updated_df[end_column] = np.nan
        updated_df[start_column] = pd.to_numeric(updated_df[start_column], errors="coerce")
        updated_df[end_column] = pd.to_numeric(updated_df[end_column], errors="coerce")
        updated_df[value_column] = updated_df[end_column] - updated_df[start_column]
        missing_mask = updated_df[start_column].isna() | updated_df[end_column].isna()
        updated_df.loc[missing_mask, value_column] = np.nan
    return updated_df


def normalize_csp_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Align one dataframe to the CSP parser schema."""
    normalized_df = df.copy()
    for column_name in csp_output_columns():
        if column_name not in normalized_df.columns:
            normalized_df[column_name] = np.nan
    for column_name in CSP_NUMERIC_COLUMNS:
        if column_name in normalized_df.columns:
            normalized_df[column_name] = pd.to_numeric(normalized_df[column_name], errors="coerce")
    normalized_df = recompute_csp_duration_columns(normalized_df)
    normalized_df = normalized_df[csp_output_columns()]
    return normalized_df.sort_values(["ID", "source_file"], na_position="last").reset_index(drop=True)


def parse_csp_file(filepath) -> dict:
    """Parse one CSP .MEM file and return the extracted record."""
    filepath_obj = Path(filepath)
    with filepath_obj.open("r", encoding="utf-8", errors="replace") as handle:
        lines = handle.readlines()

    record = initialize_csp_record()
    filename_id = extract_csp_id_from_filename(filepath_obj.name)
    filename_study = extract_study_from_text(filepath_obj.name, _STUDY_ID_PATTERN)
    current_section = "header"

    for raw_line in lines:
        stripped = raw_line.strip()

        if _SECTION_DERIVED in stripped:
            current_section = "derived"
            continue
        if _SECTION_EXTRA_VARS in stripped:
            current_section = "extra_vars"
            continue
        if _SECTION_WAVEFORMS in stripped:
            break
        if not stripped:
            continue

        if current_section == "header":
            _parse_header_field(stripped, record)
        elif current_section == "extra_vars":
            _parse_extra_vars_line(stripped, record)

    if pd.isna(record["Study"]) and not pd.isna(filename_study):
        record["Study"] = filename_study
    if pd.isna(record["ID"]) and not pd.isna(filename_id):
        record["ID"] = filename_id

    normalized_record = recompute_csp_duration_columns(pd.DataFrame([record])).iloc[0].to_dict()
    return normalized_record


def parse_csp_directory(input_dir) -> pd.DataFrame:
    """Parse every CSP .MEM file in one folder into a stable dataframe."""
    input_folder = Path(input_dir)
    if not input_folder.exists():
        raise FileNotFoundError(f"CSP input folder does not exist: {input_folder}")

    mem_files = sorted(input_folder.glob("*.MEM"))
    if not mem_files:
        raise FileNotFoundError(f"No CSP .MEM files found in {input_folder}")

    records = []
    for filepath in mem_files:
        record = parse_csp_file(filepath)
        record["source_file"] = filepath.name
        records.append(record)

    return normalize_csp_dataframe(pd.DataFrame(records, columns=csp_output_columns()))
