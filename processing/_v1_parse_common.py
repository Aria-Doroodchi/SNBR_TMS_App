"""Shared parsing helpers for MEM and CSP .MEM readers."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

SECTION_DERIVED = "DERIVED EXCITABILITY VARIABLES"
SECTION_EXTRA_VARS = "EXTRA VARIABLES"
SECTION_WAVEFORMS = "EXTRA WAVEFORMS"


def extract_id_from_text(text, pattern: re.Pattern) -> float | int:
    """Extract an integer participant ID when *pattern* matches *text*."""
    if text is None:
        return np.nan
    match = pattern.search(str(text))
    if match:
        # Support both 1-group (legacy) and 2-group (study+id) patterns
        return int(match.group(match.lastindex))
    return np.nan


def extract_study_from_text(text, pattern: re.Pattern) -> str:
    """Extract the study name (group 1) from text using a 2-group pattern."""
    if text is None:
        return np.nan
    match = pattern.search(str(text))
    if match and match.lastindex and match.lastindex >= 2:
        return match.group(1).upper()
    return np.nan


def extract_id_from_filename(filename, pattern: re.Pattern) -> float | int:
    """Extract an integer participant ID from one filename when possible."""
    if filename is None:
        return np.nan
    return extract_id_from_text(Path(str(filename)).name, pattern)


def extract_study_from_filename(filename, pattern: re.Pattern) -> str:
    """Extract the study name from one filename when possible."""
    if filename is None:
        return np.nan
    return extract_study_from_text(Path(str(filename)).name, pattern)


def extract_date(stripped: str):
    """Parse one `Date:` line and normalize it to `dd/mm/YYYY`."""
    match = re.search(r"Date:\s+(\d{1,2}/\d{1,2}/\d{2,4})", stripped)
    if match:
        parsed_date = pd.to_datetime(match.group(1), dayfirst=True, errors="coerce")
        if not pd.isna(parsed_date):
            return parsed_date.strftime("%d/%m/%Y")
    return np.nan


def extract_int(pattern: str, stripped: str):
    """Extract one integer group from *stripped*."""
    match = re.search(pattern, stripped)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    return np.nan


def extract_match(pattern: str, stripped: str):
    """Extract the first regex match group from *stripped*."""
    match = re.search(pattern, stripped)
    return match.group(1) if match else np.nan


def extract_subject_type(stripped: str):
    """Parse the MEM/CSP subject type from one header line."""
    match = re.search(r"Subject type:\s+(Control|Patient)\b", stripped, flags=re.IGNORECASE)
    return match.group(1).capitalize() if match else np.nan


def extract_stimulated_cortex(stripped: str):
    """Parse the stimulated cortex label from one header line."""
    match = re.search(r"Stim/record:\s*(.*?)\s*->", stripped)
    if match:
        cortex = match.group(1).strip()
        if cortex:
            return cortex
    return np.nan


def build_header_parsers(
    id_parser: Callable[[str], object],
    study_parser: Callable[[str], object] | None = None,
) -> dict[str, tuple | Callable]:
    """Build the shared header-field parser map for one MEM-like file format.

    When *study_parser* is provided, the "Name:" entry becomes a multi-field
    parser that sets both "Study" and "ID" on the record.
    """
    parsers: dict[str, tuple | Callable] = {
        "Date:": ("Date", extract_date),
        "Age:": ("Age", lambda s: extract_int(r"Age:\s+(\d+)", s)),
        "Sex:": ("Sex", lambda s: extract_match(r"Sex:\s+([MF])", s)),
        "Subject type:": ("Subject_type", extract_subject_type),
        "Stim/record:": ("Stimulated_cortex", extract_stimulated_cortex),
    }
    if study_parser is not None:
        # Multi-field parser: returns dict of updates
        parsers["Name:"] = ("__multi__", lambda s: {"Study": study_parser(s), "ID": id_parser(s)})
    else:
        parsers["Name:"] = ("ID", id_parser)
    return parsers


def parse_header_field(stripped: str, record: dict, header_parsers: dict):
    """Parse one header line into *record* using the provided parser mapping."""
    for prefix, entry in header_parsers.items():
        if stripped.startswith(prefix):
            key, parser = entry
            if key == "__multi__":
                updates = parser(stripped)
                for k, v in updates.items():
                    if v is not None and not bool(pd.isna(v)):
                        record[k] = v
            else:
                value = parser(stripped)
                if value is not None and not bool(pd.isna(value)):
                    record[key] = value
            return
