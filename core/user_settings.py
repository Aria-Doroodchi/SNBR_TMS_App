"""Persist user-selected default paths across sessions.

Settings are stored as a small JSON file in the app's own directory
so they travel with the project folder on lab machines.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

_SETTINGS_FILE = Path(__file__).resolve().parent / "saved_defaults.json"

# Keys used in the JSON file.
KEY_MEM_DIR = "mem_dir"
KEY_CSP_DIR = "csp_dir"
KEY_CMAP_DIR = "cmap_dir"
KEY_CSV_FILE = "csv_file"
KEY_EXPORT_CSV = "export_csv_path"
KEY_EXPORT_PDF = "export_pdf_path"
KEY_SYNC_PAIRS = "sync_pairs"
KEY_REDCAP_DATA_DIR = "redcap_data_dir"
KEY_REDCAP_DICT_DIR = "redcap_dict_dir"
KEY_REDCAP_TEMPLATE_DIR = "redcap_template_dir"
KEY_REDCAP_EXPORT_DIR = "redcap_export_dir"
KEY_REDCAP_XLSX_DIR = "redcap_xlsx_dir"


def _read() -> dict:
    if _SETTINGS_FILE.exists():
        try:
            return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _write(data: dict) -> None:
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: write to temp file, then rename.
    fd, tmp = tempfile.mkstemp(
        dir=str(_SETTINGS_FILE.parent), suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, str(_SETTINGS_FILE))
    except BaseException:
        os.unlink(tmp)
        raise


def load_defaults() -> dict[str, str]:
    """Return all saved default paths (empty string for unset keys)."""
    raw = _read()
    return {
        KEY_MEM_DIR: raw.get(KEY_MEM_DIR, ""),
        KEY_CSP_DIR: raw.get(KEY_CSP_DIR, ""),
        KEY_CMAP_DIR: raw.get(KEY_CMAP_DIR, ""),
        KEY_CSV_FILE: raw.get(KEY_CSV_FILE, ""),
        KEY_EXPORT_CSV: raw.get(KEY_EXPORT_CSV, ""),
        KEY_EXPORT_PDF: raw.get(KEY_EXPORT_PDF, ""),
        KEY_SYNC_PAIRS: raw.get(KEY_SYNC_PAIRS, []),
        KEY_REDCAP_DATA_DIR: raw.get(KEY_REDCAP_DATA_DIR, ""),
        KEY_REDCAP_DICT_DIR: raw.get(KEY_REDCAP_DICT_DIR, ""),
        KEY_REDCAP_TEMPLATE_DIR: raw.get(KEY_REDCAP_TEMPLATE_DIR, ""),
        KEY_REDCAP_EXPORT_DIR: raw.get(KEY_REDCAP_EXPORT_DIR, ""),
        KEY_REDCAP_XLSX_DIR: raw.get(KEY_REDCAP_XLSX_DIR, ""),
    }


def save_defaults(**kwargs: str) -> None:
    """Merge the given key=value pairs into the saved defaults.

    Only the keys passed are updated; others are left unchanged.
    Pass an empty string to clear a saved default.
    """
    data = _read()
    for key, value in kwargs.items():
        if value:
            data[key] = value
        else:
            data.pop(key, None)
    _write(data)


def clear_all_defaults() -> None:
    """Remove all saved defaults by writing an empty JSON object."""
    _write({})
