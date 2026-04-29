"""
Export parsed TMS DataFrames to timestamped CSV files.

Handles the CSV archive directory convention used throughout the project:
each export produces a file named ``<stem>_YYYYMMDDHHMM.csv``.  Helper
functions locate the latest archive file so that
``processing.df_builder.build_combined_dataframe_incremental`` can reuse it.

Public API
----------
export_dataframe(df, output_dir, stem)   -> Path
find_latest_csv(csv_dir)                 -> Path | None
export_incremental(mem_dir, csp_dir, csv_dir, stem) -> tuple[pd.DataFrame, Path]
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from processing.df_builder import build_combined_dataframe_incremental

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_OUTPUT_STEM = "SNBR_MEM_parsed"


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------

def _timestamp_sort_key(csv_path: Path) -> datetime:
    """Return the best available timestamp for a CSV file.

    Timestamped filenames use ``<stem>_YYYYMMDDHHMMSS.csv``.  When that
    pattern is absent the file modification time is used instead.
    """
    match = re.search(r"(\d{12,14}|\d{8}_\d{6}(?:_\d{6})?)$", csv_path.stem)
    if match:
        for fmt in ("%Y%m%d%H%M%S", "%Y%m%d%H%M", "%Y%m%d_%H%M%S_%f", "%Y%m%d_%H%M%S"):
            try:
                return datetime.strptime(match.group(1), fmt)
            except ValueError:
                continue
    return datetime.fromtimestamp(csv_path.stat().st_mtime)


def _build_timestamped_path(
    output_dir: Path,
    stem: str = DEFAULT_OUTPUT_STEM,
) -> Path:
    """Create a timestamped CSV path inside *output_dir*."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return output_dir / f"{stem}_{timestamp}.csv"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def find_latest_csv(csv_dir: str | Path) -> Path | None:
    """Return the most recent CSV in *csv_dir*, or ``None`` if empty."""
    csv_dir_path = Path(csv_dir)
    if not csv_dir_path.exists():
        return None
    csv_files = list(csv_dir_path.glob("*.csv"))
    if not csv_files:
        return None
    return max(csv_files, key=_timestamp_sort_key)


# ---------------------------------------------------------------------------
# Export functions
# ---------------------------------------------------------------------------

def export_dataframe(
    df: pd.DataFrame,
    output_dir: str | Path,
    stem: str = DEFAULT_OUTPUT_STEM,
) -> Path:
    """Write *df* to a new timestamped CSV inside *output_dir*.

    Parameters
    ----------
    df : pd.DataFrame
        The DataFrame to export (typically from ``df_builder``).
    output_dir : path
        Directory where the CSV will be created.
    stem : str
        Filename prefix (default ``SNBR_MEM_parsed``).

    Returns
    -------
    Path
        The path of the newly written CSV file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = _build_timestamped_path(output_dir, stem)
    df.to_csv(output_path, index=False)
    return output_path


def export_incremental(
    mem_dir: str | Path,
    csv_dir: str | Path,
    csp_dir: str | Path | None = None,
    stem: str = DEFAULT_OUTPUT_STEM,
) -> tuple[pd.DataFrame, Path | None]:
    """Build an incremental DataFrame and export it to a timestamped CSV.

    This is the main entry point for the typical archive workflow:

    1. Find the latest CSV in *csv_dir*.
    2. Ask ``df_builder`` to parse only new .MEM files.
    3. If nothing changed, return the existing DataFrame and its path
       (no new file is written).
    4. Otherwise, write a new timestamped CSV and return it.

    Parameters
    ----------
    mem_dir : path
        Folder containing .MEM files.
    csv_dir : path
        Archive directory for timestamped CSV exports.
    csp_dir : path, optional
        Folder containing CSP .MEM files.
    stem : str
        Filename prefix for exported CSVs.

    Returns
    -------
    (pd.DataFrame, Path)
        The resulting DataFrame and the path it was written to (or the
        path of the reused existing CSV).
    """
    csv_dir_path = Path(csv_dir)
    latest = find_latest_csv(csv_dir_path)

    df = build_combined_dataframe_incremental(
        mem_dir=mem_dir,
        csp_dir=csp_dir,
        existing_csv=latest,
    )

    if df.attrs.get("reused_existing", False) and latest is not None:
        return df, latest

    output_path = export_dataframe(df, csv_dir_path, stem)
    return df, output_path
