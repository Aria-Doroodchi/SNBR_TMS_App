"""
Parse .MEM files from TMS recordings and extract participant data into a wide DataFrame.

Extracts participant demographics, RMT thresholds, stimulated cortex, individual T-SICI
values, additional waveform-based T-SICF / A-SICI / A-SICF values when present, and
optionally merges CSP timing data from the dedicated CSP raw-data folder.

Usage:
    python parse_mem_files.py
    python parse_mem_files.py --input <folder> --output <file.csv>
    python parse_mem_files.py --input <folder> --csv-dir <folder_with_csvs>

Function usage:
    from parse_mem_files import parse_mem_directory

    df = parse_mem_directory(
        input_dir=r"C:\\path\\to\\MEM_folder",
        output_csv=r"C:\\path\\to\\parsed_output.csv",
    )

    from parse_mem_files import update_mem_csv_directory

    df = update_mem_csv_directory(
        input_dir=r"C:\\path\\to\\MEM_folder",
        csv_dir=r"C:\\path\\to\\csv_archive",
    )

    from visualization import (
        plot_tsici_profile,
        plot_tsici_group_comparison,
        plot_tsici_grouped_graph,
        plot_participant_tsici_over_time,
        plot_participant_tsici_visit_profiles,
        plot_tsici_graph,
    )

    fig, ax, matched_rows = plot_tsici_profile(
        mem_filename="SNBR-005-TP2C30426B.MEM",
        input_dir=r"C:\\path\\to\\MEM_folder",
    )

    fig, ax, plot_data = plot_tsici_group_comparison(
        mem_filename="SNBR-005-TP2C30426B.MEM",
        input_dir=r"C:\\path\\to\\MEM_folder",
    )

    fig, ax, plot_data = plot_tsici_grouped_graph(
        mem_filename="SNBR-005-TP2C30426B.MEM",
        input_dir=r"C:\\path\\to\\MEM_folder",
        match_by=["sex", "age"],
        age_window=5,
    )

    fig, ax, plot_data = plot_participant_tsici_over_time(
        participant_id=130,
        input_dir=r"C:\\path\\to\\MEM_folder",
    )

    fig, axes, plot_data = plot_participant_tsici_visit_profiles(
        participant_id=130,
        input_dir=r"C:\\path\\to\\MEM_folder",
    )

    fig, ax, plot_data = plot_tsici_graph(
        graph_type="participant_over_time",
        participant_id=130,
        input_dir=r"C:\\path\\to\\MEM_folder",
    )
"""

from collections import defaultdict
import re
import argparse
from datetime import datetime
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Callable
from processing._v1_parse_common import (
    SECTION_DERIVED as _SECTION_DERIVED,
    SECTION_EXTRA_VARS as _SECTION_EXTRA_VARS,
    SECTION_WAVEFORMS as _SECTION_WAVEFORMS,
    build_header_parsers,
    extract_id_from_text,
    extract_study_from_text,
    extract_study_from_filename,
    parse_header_field,
)

from processing._v1_parse_csp_files import (
    CSP_RMT_LEVELS,
    CSP_VALUE_COLUMNS,
    parse_csp_directory,
    recompute_csp_duration_columns,
)

# T-SICI ISIs to extract (individual values only)
TSICI_ISIS = ["1.0ms", "1.5ms", "2ms", "2.5ms", "3.0ms", "3.5ms"]
TSICF_ISIS = [f"{tenths / 10:.1f}ms" for tenths in range(10, 71, 3)]
A_SICI_ISIS = ["1.0ms", "1.5ms", "2.0ms", "2.5ms", "3.0ms", "3.5ms", "4.0ms", "5.0ms"]
ASICF_ISIS = [f"{tenths / 10:.1f}ms" for tenths in range(10, 71, 3)]
DEFAULT_OUTPUT_STEM = "SNBR_MEM_parsed"
TSICF_BLOCK_MARKER = "!T-SICFvISI(%RMT)(Parallel)"
A_SICI_BLOCK_MARKER = "!A-SICIvISI(rel)"
ASICF_BLOCK_MARKER = "!A-SICFvISI(rel)"
ACQUISITION_TOKEN_PATTERN = re.compile(r"([A-Z]+(?:\d+C|C)\d+[A-Z])", flags=re.IGNORECASE)
_STUDY_ID_PATTERN = re.compile(r"([A-Za-z]+)\d*-0*(\d+)", flags=re.IGNORECASE)

# Regex patterns for each T-SICI ISI
TSICI_PATTERNS = {
    isi: re.compile(rf"^T-SICI\(70%\){re.escape(isi)}\s*=\s*([-\d.]+)")
    for isi in TSICI_ISIS
}

NUMERIC_OUTPUT_COLUMNS = (
    ["ID", "Age", "RMT50", "RMT200", "RMT1000"]
    + [f"T_SICI_{isi}" for isi in TSICI_ISIS]
    + [f"T_SICF_{isi}" for isi in TSICF_ISIS]
    + [f"A_SICI_{isi}" for isi in A_SICI_ISIS]
    + [f"A_SICF_{isi}" for isi in ASICF_ISIS]
    + list(CSP_VALUE_COLUMNS)
    + ["T_SICI_avg", "T_SICF_avg", "A_SICI_avg", "A_SICF_avg"]
)


def default_csp_input_dir() -> Path:
    """Return the default CSP raw-data directory relative to this script."""
    script_dir = Path(__file__).resolve().parent
    project_dir = script_dir.parent
    return project_dir / "1_Raw_Data" / "SNBR_CSP_RAW"


def initialize_record() -> dict:
    """Return an empty parsed-record dict with the full output schema."""
    record = {
        "Study": np.nan,
        "ID": np.nan,
        "Date": np.nan,
        "Age": np.nan,
        "Sex": np.nan,
        "Subject_type": np.nan,
        "Stimulated_cortex": np.nan,
        "RMT50": np.nan,
        "RMT200": np.nan,
        "RMT1000": np.nan,
        "T_SICI_avg": np.nan,
        "T_SICF_avg": np.nan,
        "A_SICI_avg": np.nan,
        "A_SICF_avg": np.nan,
    }

    for isi in TSICI_ISIS:
        record[f"T_SICI_{isi}"] = np.nan
    for isi in TSICF_ISIS:
        record[f"T_SICF_{isi}"] = np.nan
    for isi in A_SICI_ISIS:
        record[f"A_SICI_{isi}"] = np.nan
    for isi in ASICF_ISIS:
        record[f"A_SICF_{isi}"] = np.nan
    for level in CSP_RMT_LEVELS:
        record[f"CSPs_{level}"] = np.nan
        record[f"CSPe_{level}"] = np.nan
        record[f"CSP_{level}"] = np.nan

    return record


def normalize_decimal_isi_label(raw_isi) -> str:
    """Normalize an ISI token from a waveform block to one decimal-place ms notation."""
    return f"{float(raw_isi):.1f}ms"


def identity_waveform_value(raw_value: float) -> float:
    """Return a waveform value unchanged as a float."""
    return float(raw_value)


def percentage_waveform_value(raw_value: float) -> float:
    """Convert an absolute waveform ratio to a percentage."""
    return float(raw_value) * 100.0


def extract_waveform_block_values(
    lines,
    marker: str,
    target_isis,
    value_transform: Callable[[float], float],
) -> dict:
    """
    Extract ISI/value pairs from a waveform block.

    The parser looks for *marker*, skips the block's metadata row, and then reads data rows
    until the next blank line or the next waveform marker. Only requested ISIs are returned.
    """
    extracted_values = {}
    target_isi_set = set(target_isis)

    for line_index, line in enumerate(lines):
        if line.strip() != marker:
            continue

        metadata_index = line_index + 1
        while metadata_index < len(lines) and not lines[metadata_index].strip():
            metadata_index += 1

        if metadata_index >= len(lines):
            return extracted_values

        data_index = metadata_index + 1
        while data_index < len(lines):
            stripped = lines[data_index].strip()
            if not stripped or stripped.startswith("!"):
                break

            parts = re.split(r"\s+", stripped)
            if len(parts) >= 2:
                try:
                    normalized_isi = normalize_decimal_isi_label(parts[0])
                    raw_value = float(parts[1])
                except ValueError:
                    data_index += 1
                    continue

                if normalized_isi in target_isi_set:
                    extracted_values[normalized_isi] = value_transform(raw_value)

            data_index += 1

        return extracted_values

    return extracted_values


def assign_waveform_values(record: dict, prefix: str, extracted_values: dict):
    """Write extracted waveform values into *record* using the given column prefix."""
    for isi_label, value in extracted_values.items():
        record[f"{prefix}_{isi_label}"] = value


def compute_record_average(record: dict, prefix: str, isis, average_column: str):
    """Compute one waveform-family average for a parsed-record dict."""
    value_columns = [f"{prefix}_{isi}" for isi in isis]
    values = [record[column_name] for column_name in value_columns if not pd.isna(record[column_name])]
    record[average_column] = float(np.mean(values)) if values else np.nan


def recompute_average_column(
    data_df: pd.DataFrame,
    value_columns,
    average_column: str,
) -> pd.DataFrame:
    """Recompute one average column from its individual wide-value columns."""
    updated_df = data_df.copy()
    updated_df[value_columns] = updated_df[value_columns].apply(pd.to_numeric, errors="coerce")
    updated_df[average_column] = updated_df[value_columns].mean(axis=1, skipna=True)
    rows_without_values = updated_df[value_columns].isna().all(axis=1)
    updated_df.loc[rows_without_values, average_column] = np.nan
    return updated_df


def _extract_id_from_name(stripped: str):
    return extract_id_from_text(stripped, _STUDY_ID_PATTERN)


def _extract_study_from_name(stripped: str):
    return extract_study_from_text(stripped, _STUDY_ID_PATTERN)


_HEADER_PARSERS = build_header_parsers(_extract_id_from_name, _extract_study_from_name)


def _parse_header_field(stripped: str, record: dict):
    """Parse a single header line using field mapping."""
    parse_header_field(stripped, record, _HEADER_PARSERS)


def _parse_extra_vars_line(stripped: str, record: dict):
    """Parse a line from the EXTRA VARIABLES section (RMT summaries and T-SICI values)."""
    # RMT50 summary (not individual trials)
    if re.match(r"^RMT50\s*=", stripped):
        match = re.search(r"RMT50\s*=\s*([-\d.]+)", stripped)
        if match:
            try:
                record["RMT50"] = float(match.group(1))
            except ValueError:
                pass
        return

    # RMT200 summary (not individual trials)
    if re.match(r"^RMT200\s*=", stripped):
        match = re.search(r"RMT200\s*=\s*([-\d.]+)", stripped)
        if match:
            try:
                record["RMT200"] = float(match.group(1))
            except ValueError:
                pass
        return

    # RMT1000 summary (not individual trials)
    if re.match(r"^RMT1000\s*=", stripped):
        match = re.search(r"RMT1000\s*=\s*([-\d.]+)", stripped)
        if match:
            try:
                record["RMT1000"] = float(match.group(1))
            except ValueError:
                pass
        return

    # T-SICI individual ISI values
    for isi, pattern in TSICI_PATTERNS.items():
        match = pattern.match(stripped)
        if match:
            try:
                record[f"T_SICI_{isi}"] = adjust_tsici_value(float(match.group(1)))
            except ValueError:
                pass
            return


def parse_mem_file(filepath: str) -> dict:
    """Parse a single .MEM file and return extracted values as a dict."""
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    filepath_obj = Path(filepath)
    filename_study = extract_study_from_filename(filepath_obj.name, _STUDY_ID_PATTERN)
    filename_id = extract_id_from_text(filepath_obj.name, _STUDY_ID_PATTERN)

    record = initialize_record()

    # Section-aware parsing: only match fields in the correct section
    current_section = "header"

    for line in lines:
        stripped = line.strip()

        # Detect section boundaries
        if _SECTION_DERIVED in stripped:
            current_section = "derived"
            continue
        if _SECTION_EXTRA_VARS in stripped:
            current_section = "extra_vars"
            continue
        if _SECTION_WAVEFORMS in stripped:
            current_section = "waveforms"
            break  # waveform blocks are handled separately below

        if not stripped:
            continue

        if current_section == "header":
            _parse_header_field(stripped, record)
        elif current_section == "extra_vars":
            _parse_extra_vars_line(stripped, record)

    assign_waveform_values(
        record,
        prefix="T_SICF",
        extracted_values=extract_waveform_block_values(
            lines=lines,
            marker=TSICF_BLOCK_MARKER,
            target_isis=TSICF_ISIS,
            value_transform=identity_waveform_value,
        ),
    )
    assign_waveform_values(
        record,
        prefix="A_SICI",
        extracted_values=extract_waveform_block_values(
            lines=lines,
            marker=A_SICI_BLOCK_MARKER,
            target_isis=A_SICI_ISIS,
            value_transform=identity_waveform_value,
        ),
    )
    assign_waveform_values(
        record,
        prefix="A_SICF",
        extracted_values=extract_waveform_block_values(
            lines=lines,
            marker=ASICF_BLOCK_MARKER,
            target_isis=ASICF_ISIS,
            value_transform=identity_waveform_value,
        ),
    )

    # Fall back to filename Study/ID only when the file content does not provide one.
    if pd.isna(record["Study"]) and not pd.isna(filename_study):
        record["Study"] = filename_study
    if pd.isna(record["ID"]) and not pd.isna(filename_id):
        record["ID"] = filename_id

    compute_record_average(record, prefix="T_SICI", isis=TSICI_ISIS, average_column="T_SICI_avg")
    compute_record_average(record, prefix="T_SICF", isis=TSICF_ISIS, average_column="T_SICF_avg")
    compute_record_average(record, prefix="A_SICI", isis=A_SICI_ISIS, average_column="A_SICI_avg")
    compute_record_average(record, prefix="A_SICF", isis=ASICF_ISIS, average_column="A_SICF_avg")

    return record


def output_column_order():
    """Return the standard output column order for parsed MEM data."""
    return (
        ["Study", "ID", "Date", "Age", "Sex", "Subject_type", "Stimulated_cortex", "RMT50", "RMT200", "RMT1000"]
        + [column_name for level in CSP_RMT_LEVELS for column_name in (f"CSPs_{level}", f"CSPe_{level}", f"CSP_{level}")]
        + [f"T_SICI_{isi}" for isi in TSICI_ISIS]
        + ["T_SICI_avg"]
        + [f"T_SICF_{isi}" for isi in TSICF_ISIS]
        + ["T_SICF_avg"]
        + [f"A_SICI_{isi}" for isi in A_SICI_ISIS]
        + ["A_SICI_avg"]
        + [f"A_SICF_{isi}" for isi in ASICF_ISIS]
        + ["A_SICF_avg", "source_file"]
    )


def adjust_tsici_value(raw_value: float) -> float:
    """Convert a T-SICI delta value to its 100-based percentage representation."""
    return 100.0 + float(raw_value)


def recompute_tsici_average(df: pd.DataFrame) -> pd.DataFrame:
    """Recompute T-SICI averages from the current individual T-SICI columns."""
    tsici_cols = [f"T_SICI_{isi}" for isi in TSICI_ISIS]
    return recompute_average_column(df, value_columns=tsici_cols, average_column="T_SICI_avg")


def recompute_waveform_averages(df: pd.DataFrame) -> pd.DataFrame:
    """Recompute all waveform-family averages from their current individual columns."""
    updated_df = recompute_tsici_average(df)
    updated_df = recompute_average_column(
        updated_df,
        value_columns=[f"T_SICF_{isi}" for isi in TSICF_ISIS],
        average_column="T_SICF_avg",
    )
    updated_df = recompute_average_column(
        updated_df,
        value_columns=[f"A_SICI_{isi}" for isi in A_SICI_ISIS],
        average_column="A_SICI_avg",
    )
    updated_df = recompute_average_column(
        updated_df,
        value_columns=[f"A_SICF_{isi}" for isi in ASICF_ISIS],
        average_column="A_SICF_avg",
    )
    return updated_df


def normalize_output_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Align a DataFrame to the parser's output schema."""
    normalized_df = df.copy()
    for column in output_column_order():
        if column not in normalized_df.columns:
            normalized_df[column] = np.nan
    for column_name in NUMERIC_OUTPUT_COLUMNS:
        if column_name in normalized_df.columns:
            normalized_df[column_name] = pd.to_numeric(normalized_df[column_name], errors="coerce")
    normalized_df = normalized_df[output_column_order()]
    normalized_df = recompute_waveform_averages(normalized_df)
    normalized_df = recompute_csp_duration_columns(normalized_df)
    return normalized_df.sort_values(["ID", "source_file"], na_position="last").reset_index(drop=True)


def build_mem_dataframe(records) -> pd.DataFrame:
    """Build the parsed output DataFrame with a stable column order."""
    return normalize_output_dataframe(pd.DataFrame(records, columns=output_column_order()))


def acquisition_token_from_source_name(source_name) -> str:
    """Extract the acquisition token used for conservative MEM/CSP file matching."""
    if source_name is None:
        return ""
    stem = Path(str(source_name)).stem.upper()
    token_matches = ACQUISITION_TOKEN_PATTERN.findall(stem)
    return token_matches[-1] if token_matches else ""


def _list_optional_csp_files(csp_input_dir=None) -> tuple[Path, list[Path]]:
    """Return the resolved CSP directory plus any available CSP .MEM files."""
    resolved_dir = Path(csp_input_dir) if csp_input_dir is not None else default_csp_input_dir()
    if not resolved_dir.exists():
        return resolved_dir, []
    return resolved_dir, sorted(resolved_dir.glob("*.MEM"))


def load_optional_csp_dataframe(csp_input_dir=None) -> pd.DataFrame:
    """Load CSP data when the folder exists, otherwise return an empty normalized dataframe."""
    resolved_dir, csp_files = _list_optional_csp_files(csp_input_dir=csp_input_dir)
    if not csp_files:
        empty_df = normalize_output_dataframe(pd.DataFrame(columns=output_column_order()))
        empty_df.attrs["csp_input_dir"] = str(resolved_dir)
        empty_df.attrs["csp_file_count"] = 0
        return empty_df

    csp_df = normalize_output_dataframe(parse_csp_directory(resolved_dir))
    csp_df.attrs["csp_input_dir"] = str(resolved_dir)
    csp_df.attrs["csp_file_count"] = len(csp_files)
    return csp_df


def _match_key_maps(data_df: pd.DataFrame, key_columns, allowed_indices=None) -> dict[tuple, list[int]]:
    """Build a mapping from one tuple key to row indices, ignoring incomplete keys."""
    if allowed_indices is None:
        index_iterable = list(data_df.index)
    else:
        index_iterable = list(allowed_indices)

    key_map = defaultdict(list)
    for row_index in index_iterable:
        row = data_df.loc[row_index]
        key_values = []
        skip_row = False
        for column_name in key_columns:
            value = row[column_name]
            if pd.isna(value):
                skip_row = True
                break
            if isinstance(value, str) and not value.strip():
                skip_row = True
                break
            key_values.append(value)
        if skip_row:
            continue
        key_map[tuple(key_values)].append(row_index)
    return key_map


def merge_csp_into_mem_dataframe(data_df: pd.DataFrame, csp_df: pd.DataFrame) -> pd.DataFrame:
    """Merge CSP rows into the main parsed MEM dataframe using conservative matching."""
    main_df = normalize_output_dataframe(data_df)
    csp_values_df = normalize_output_dataframe(csp_df)
    if csp_values_df.empty:
        result_df = main_df.copy()
        result_df.attrs["csp_rows_loaded"] = 0
        result_df.attrs["csp_rows_merged"] = 0
        result_df.attrs["csp_rows_appended"] = 0
        return result_df

    main_work = main_df.copy()
    csp_work = csp_values_df.copy()

    for frame in (main_work, csp_work):
        frame["_match_id"] = pd.to_numeric(frame["ID"], errors="coerce")
        frame["_match_date"] = frame["Date"].astype("string").fillna("").str.strip()
        frame["_match_token"] = frame["source_file"].apply(acquisition_token_from_source_name)

    matched_pairs = []
    matched_main_indices = set()
    matched_csp_indices = set()

    exact_main_map = _match_key_maps(main_work, ["_match_id", "_match_date", "_match_token"])
    exact_csp_map = _match_key_maps(csp_work, ["_match_id", "_match_date", "_match_token"])
    for key in sorted(set(exact_main_map) & set(exact_csp_map)):
        main_indices = exact_main_map[key]
        csp_indices = exact_csp_map[key]
        if len(main_indices) == 1 and len(csp_indices) == 1:
            main_index = main_indices[0]
            csp_index = csp_indices[0]
            matched_pairs.append((main_index, csp_index))
            matched_main_indices.add(main_index)
            matched_csp_indices.add(csp_index)

    unmatched_main_indices = [index for index in main_work.index if index not in matched_main_indices]
    unmatched_csp_indices = [index for index in csp_work.index if index not in matched_csp_indices]
    fallback_main_map = _match_key_maps(main_work, ["_match_id", "_match_date"], allowed_indices=unmatched_main_indices)
    fallback_csp_map = _match_key_maps(csp_work, ["_match_id", "_match_date"], allowed_indices=unmatched_csp_indices)
    for key in sorted(set(fallback_main_map) & set(fallback_csp_map)):
        main_indices = fallback_main_map[key]
        csp_indices = fallback_csp_map[key]
        if len(main_indices) == 1 and len(csp_indices) == 1:
            main_index = main_indices[0]
            csp_index = csp_indices[0]
            matched_pairs.append((main_index, csp_index))
            matched_main_indices.add(main_index)
            matched_csp_indices.add(csp_index)

    for main_index, csp_index in matched_pairs:
        for column_name in CSP_VALUE_COLUMNS:
            csp_value = csp_work.at[csp_index, column_name]
            if not pd.isna(csp_value):
                main_work.at[main_index, column_name] = csp_value

        for column_name in ["Date", "Age", "Sex", "Subject_type", "Stimulated_cortex"]:
            if pd.isna(main_work.at[main_index, column_name]):
                csp_value = csp_work.at[csp_index, column_name]
                if not pd.isna(csp_value):
                    main_work.at[main_index, column_name] = csp_value

    appended_csp_rows = csp_work.loc[
        [index for index in csp_work.index if index not in matched_csp_indices],
        output_column_order(),
    ].copy()
    combined_df = pd.concat([main_work[output_column_order()], appended_csp_rows], ignore_index=True)
    combined_df = normalize_output_dataframe(combined_df)
    combined_df.attrs["csp_rows_loaded"] = int(len(csp_work))
    combined_df.attrs["csp_rows_merged"] = int(len(matched_pairs))
    combined_df.attrs["csp_rows_appended"] = int(len(appended_csp_rows))
    return combined_df


def build_combined_mem_dataframe(mem_files, csp_input_dir=None) -> pd.DataFrame:
    """Parse the requested MEM files and conservatively merge any available CSP data."""
    records = []
    for filepath in mem_files:
        record = parse_mem_file(str(filepath))
        record["source_file"] = filepath.name
        records.append(record)

    main_df = build_mem_dataframe(records)
    csp_df = load_optional_csp_dataframe(csp_input_dir=csp_input_dir)
    combined_df = merge_csp_into_mem_dataframe(main_df, csp_df)
    combined_df.attrs["csp_input_dir"] = str(csp_df.attrs.get("csp_input_dir", ""))
    combined_df.attrs["csp_file_count"] = int(csp_df.attrs.get("csp_file_count", 0))
    return combined_df


def plot_tsici_profile(*args, **kwargs):
    """Backward-compatible wrapper for the plotting helper now hosted in visualization.py."""
    from visualization import plot_tsici_profile as _plot_tsici_profile

    return _plot_tsici_profile(*args, **kwargs)


def plot_tsici_group_comparison(*args, **kwargs):
    """Backward-compatible wrapper for the cohort comparison plot hosted in visualization.py."""
    from visualization import plot_tsici_group_comparison as _plot_tsici_group_comparison

    return _plot_tsici_group_comparison(*args, **kwargs)


def plot_tsici_grouped_graph(*args, **kwargs):
    """Backward-compatible wrapper for the one-line grouped graph helper hosted in visualization.py."""
    from visualization import plot_tsici_grouped_graph as _plot_tsici_grouped_graph

    return _plot_tsici_grouped_graph(*args, **kwargs)


def plot_participant_tsici_over_time(*args, **kwargs):
    """Backward-compatible wrapper for the participant-over-time helper hosted in visualization.py."""
    from visualization import plot_participant_tsici_over_time as _plot_participant_tsici_over_time

    return _plot_participant_tsici_over_time(*args, **kwargs)


def plot_participant_tsici_visit_profiles(*args, **kwargs):
    """Backward-compatible wrapper for the visit-profile helper hosted in visualization.py."""
    from visualization import plot_participant_tsici_visit_profiles as _plot_participant_tsici_visit_profiles

    return _plot_participant_tsici_visit_profiles(*args, **kwargs)


def plot_tsici_graph(*args, **kwargs):
    """Backward-compatible wrapper for the graph-type dispatcher hosted in visualization.py."""
    from visualization import plot_tsici_graph as _plot_tsici_graph

    return _plot_tsici_graph(*args, **kwargs)


def timestamp_sort_key(csv_path: Path) -> datetime:
    """
    Return the best available timestamp for a CSV file.

    Timestamped filenames written by this script use:
        <stem>_YYYYMMDDHHMM.csv
    If that pattern is missing, the file modification time is used.
    """
    match = re.search(r"(\d{12}|\d{8}_\d{6}(?:_\d{6})?)$", csv_path.stem)
    if match:
        for timestamp_format in ("%Y%m%d%H%M", "%Y%m%d_%H%M%S_%f", "%Y%m%d_%H%M%S"):
            try:
                return datetime.strptime(match.group(1), timestamp_format)
            except ValueError:
                continue
    return datetime.fromtimestamp(csv_path.stat().st_mtime)


def find_latest_csv(csv_dir):
    """Find the latest CSV in *csv_dir* using the embedded timestamp or file modified time."""
    csv_dir_path = Path(csv_dir)
    if not csv_dir_path.exists():
        return None
    csv_files = list(csv_dir_path.glob("*.csv"))
    if not csv_files:
        return None
    return max(csv_files, key=timestamp_sort_key)


def build_timestamped_csv_path(csv_dir, output_stem: str = DEFAULT_OUTPUT_STEM) -> Path:
    """Create a timestamped output path inside *csv_dir*."""
    csv_dir_path = Path(csv_dir)
    timestamp = datetime.now().strftime("%Y%m%d%H%M")
    return csv_dir_path / f"{output_stem}_{timestamp}.csv"


def build_timestamped_output_file_path(output_csv) -> Path:
    """Create a timestamped output file path from a base CSV filename."""
    output_path = Path(output_csv)
    timestamp = datetime.now().strftime("%Y%m%d%H%M")
    suffix = output_path.suffix if output_path.suffix else ".csv"
    return output_path.with_name(f"{output_path.stem}_{timestamp}{suffix}")


def load_existing_output_csv(csv_path) -> pd.DataFrame:
    """Load a previously generated CSV so new files can be appended to it."""
    existing_df = pd.read_csv(csv_path)
    if "source_file" not in existing_df.columns:
        raise ValueError(f"Existing CSV is missing required column 'source_file': {csv_path}")

    missing_output_columns = [column for column in output_column_order() if column not in existing_df.columns]

    tsici_cols = [f"T_SICI_{isi}" for isi in TSICI_ISIS if f"T_SICI_{isi}" in existing_df.columns]
    if tsici_cols:
        tsici_numeric = existing_df[tsici_cols].apply(pd.to_numeric, errors="coerce")
        tsici_values = tsici_numeric.to_numpy(dtype=float)
        finite_values = tsici_values[np.isfinite(tsici_values)]
        if finite_values.size > 0:
            # Older CSVs stored raw deltas (for example 3.6 instead of 103.6).
            # Upgrade them automatically so incremental runs keep one consistent scale.
            if float(np.nanmin(finite_values)) < 0.0 or float(np.nanmax(finite_values)) <= 60.0:
                existing_df[tsici_cols] = tsici_numeric + 100.0

    normalized_df = normalize_output_dataframe(existing_df)
    normalized_df.attrs["missing_output_columns"] = missing_output_columns
    return normalized_df


def source_file_name_set(data_df: pd.DataFrame) -> set[str]:
    """Return the normalized non-empty source filenames present in a parsed MEM dataframe."""
    if "source_file" not in data_df.columns:
        return set()
    source_files = set(data_df["source_file"].astype("string").fillna("").str.strip())
    source_files.discard("")
    return source_files


def parse_mem_directory(input_dir, output_csv=None, csp_input_dir=None) -> pd.DataFrame:
    """
    Parse all .MEM files in *input_dir* and optionally merge any available CSP data.

    Parameters
    ----------
    input_dir : str or Path
        Folder containing .MEM files.
    output_csv : str or Path, optional
        If provided, the parsed DataFrame is saved beside this path using a
        timestamped filename based on the supplied stem.
    csp_input_dir : str or Path, optional
        Folder containing CSP .MEM files. When omitted, the default CSP raw-data
        folder is used when it exists.

    Returns
    -------
    pd.DataFrame
        One row per .MEM file.
    """
    input_folder = Path(input_dir)
    if not input_folder.exists():
        raise FileNotFoundError(f"Input folder does not exist: {input_folder}")

    mem_files = sorted(input_folder.glob("*.MEM"))
    if not mem_files:
        raise FileNotFoundError(f"No .MEM files found in {input_folder}")

    df = build_combined_mem_dataframe(mem_files, csp_input_dir=csp_input_dir)

    if output_csv is not None:
        output_path = build_timestamped_output_file_path(output_csv)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        df.attrs["output_csv"] = str(output_path)

    return df


def update_mem_csv_directory(
    input_dir,
    csv_dir,
    output_stem: str = DEFAULT_OUTPUT_STEM,
    csp_input_dir=None,
) -> pd.DataFrame:
    """
    Load the latest timestamped CSV from *csv_dir* and keep the archive in sync with *input_dir*.

    Behavior:
    - If the latest CSV contains exactly the same main MEM filenames and already matches the
      current schema, reuse it as-is when CSP auto-loading is not active.
    - If CSP auto-loading is active, rebuild from the current MEM and CSP folders so merged rows
      stay accurate even when file-to-row matching changes.
    - Otherwise, if the latest CSV and the MEM folder differ in any way, rebuild from the current
      MEM files and save a new timestamped CSV.
    """
    input_folder = Path(input_dir)
    if not input_folder.exists():
        raise FileNotFoundError(f"Input folder does not exist: {input_folder}")

    mem_files = sorted(input_folder.glob("*.MEM"))
    if not mem_files:
        raise FileNotFoundError(f"No .MEM files found in {input_folder}")

    csv_dir_path = Path(csv_dir)
    latest_csv = find_latest_csv(csv_dir_path)
    mem_file_names = {filepath.name for filepath in mem_files}
    resolved_csp_dir, csp_files = _list_optional_csp_files(csp_input_dir=csp_input_dir)
    csp_auto_merge_active = bool(csp_files)

    if latest_csv is None:
        existing_df = pd.DataFrame(columns=output_column_order())
        existing_source_files = set()
        missing_output_columns = []
    else:
        existing_df = load_existing_output_csv(latest_csv)
        existing_source_files = source_file_name_set(existing_df)
        missing_output_columns = list(existing_df.attrs.get("missing_output_columns", []))

    new_file_names = mem_file_names - existing_source_files
    removed_file_names = existing_source_files - mem_file_names

    archive_action = "created_new_archive"
    output_path = None

    if csp_auto_merge_active:
        combined_df = build_combined_mem_dataframe(mem_files, csp_input_dir=resolved_csp_dir)
        output_path = build_timestamped_csv_path(csv_dir_path, output_stem=output_stem)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        combined_df.to_csv(output_path, index=False)
        archive_action = "rebuilt_from_current_mem_files" if latest_csv is not None else "created_new_archive"
    elif latest_csv is not None and not new_file_names and not removed_file_names:
        if missing_output_columns:
            combined_df = build_combined_mem_dataframe(mem_files, csp_input_dir=resolved_csp_dir)
            output_path = build_timestamped_csv_path(csv_dir_path, output_stem=output_stem)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            combined_df.to_csv(output_path, index=False)
            archive_action = "rebuilt_from_current_mem_files"
        else:
            combined_df = existing_df.copy()
            output_path = latest_csv
            archive_action = "reused_latest_csv"
    else:
        combined_df = build_combined_mem_dataframe(mem_files, csp_input_dir=resolved_csp_dir)
        output_path = build_timestamped_csv_path(csv_dir_path, output_stem=output_stem)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        combined_df.to_csv(output_path, index=False)
        archive_action = "rebuilt_from_current_mem_files"

    combined_df.attrs["latest_csv_loaded"] = str(latest_csv) if latest_csv is not None else ""
    combined_df.attrs["output_csv"] = str(output_path) if output_path is not None else ""
    combined_df.attrs["new_files_added"] = len(new_file_names)
    combined_df.attrs["removed_files_detected"] = len(removed_file_names)
    combined_df.attrs["existing_rows_loaded"] = len(existing_df)
    combined_df.attrs["input_file_count"] = len(mem_files)
    combined_df.attrs["csp_input_dir"] = str(resolved_csp_dir)
    combined_df.attrs["csp_file_count"] = len(csp_files)
    combined_df.attrs["archive_action"] = archive_action
    combined_df.attrs["reused_existing_csv"] = archive_action == "reused_latest_csv"

    return combined_df


def main(input_dir=None, output_csv=None, csv_dir=None, csp_input_dir=None):
    # Default paths relative to this script's location
    script_dir = Path(__file__).resolve().parent
    project_dir = script_dir.parent
    default_input = project_dir / "1_Raw_Data" / "SNBR_MEM"
    default_output = project_dir / "2_Processed_Data" / "SNBR_MEM_parsed.csv"
    default_csp_input = default_csp_input_dir()

    if input_dir is None and output_csv is None and csv_dir is None and csp_input_dir is None:
        parser = argparse.ArgumentParser(description="Parse .MEM files into a wide DataFrame.")
        parser.add_argument("--input", type=str, default=str(default_input),
                            help="Folder containing .MEM files")
        parser.add_argument("--output", type=str, default=str(default_output),
                            help="Output CSV file path")
        parser.add_argument("--csv-dir", type=str, default=None,
                            help="Directory containing timestamped CSV outputs for incremental updates")
        parser.add_argument("--csp-input", type=str, default=str(default_csp_input),
                            help="Optional folder containing CSP .MEM files")
        args = parser.parse_args()
        input_folder = Path(args.input)
        output_path = Path(args.output)
        csv_dir = args.csv_dir
        csp_input_dir = args.csp_input
    else:
        input_folder = Path(input_dir) if input_dir is not None else default_input
        output_path = Path(output_csv) if output_csv is not None else default_output
        csp_input_dir = csp_input_dir if csp_input_dir is not None else default_csp_input

    mem_count = len(list(input_folder.glob("*.MEM")))
    _, csp_files = _list_optional_csp_files(csp_input_dir=csp_input_dir)
    csp_count = len(csp_files)

    try:
        if csv_dir is not None:
            df = update_mem_csv_directory(
                input_dir=input_folder,
                csv_dir=csv_dir,
                csp_input_dir=csp_input_dir,
            )
            output_path = Path(df.attrs.get("output_csv", ""))
        else:
            df = parse_mem_directory(
                input_dir=input_folder,
                output_csv=output_path,
                csp_input_dir=csp_input_dir,
            )
            output_path = Path(df.attrs.get("output_csv", output_path))
    except (FileNotFoundError, ValueError) as exc:
        print(exc)
        return None

    if csv_dir is not None:
        latest_csv_loaded = df.attrs.get("latest_csv_loaded", "")
        new_files_added = int(df.attrs.get("new_files_added", 0))
        removed_files_detected = int(df.attrs.get("removed_files_detected", 0))
        archive_action = str(df.attrs.get("archive_action", ""))
        if latest_csv_loaded:
            print(f"Loaded latest CSV: {latest_csv_loaded}")
        else:
            print("No existing CSV found. Parsed all available .MEM files.")
        if archive_action == "reused_latest_csv":
            print("Latest CSV already matches the MEM folder. Reused it without writing a new archive file.")
        elif archive_action == "rebuilt_from_current_mem_files":
            print(
                "MEM files differed from the latest CSV archive; rebuilt a new CSV from the current MEM folder "
                f"(new files: {new_files_added}, removed files detected: {removed_files_detected})."
            )

    print(f"Found {mem_count} .MEM files in {input_folder}")
    if csp_count:
        print(f"Loaded {csp_count} CSP .MEM files from {Path(csp_input_dir)}")
    else:
        print(f"No CSP .MEM files loaded from {Path(csp_input_dir)}")
    if csv_dir is not None and str(df.attrs.get("archive_action", "")) == "reused_latest_csv":
        print(f"\nReused {len(df)} rows from {output_path}")
    else:
        print(f"\nSaved {len(df)} rows to {output_path}")
    print(f"\nPreview:\n{df.to_string(index=False)}")
    return df


if __name__ == "__main__":
    main()
