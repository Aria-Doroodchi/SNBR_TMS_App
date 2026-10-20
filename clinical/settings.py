"""Persisted settings for the clinical reports app.

Its own JSON file, like the dispatch app's (``dispatch/settings.py``): the
analysis app's ``KEY_*`` schema is frozen, and this app is installed on the
collaborators' machines, which have neither the ``.MEM`` folders nor the
analysis app's saved defaults. Same storage policy: repo-local in
development, per-user ``%APPDATA%`` when frozen, and every write is atomic.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_APP_NAME = "SNBR_Clinical_Reports"


def _resolve_settings_file() -> Path:
    if not getattr(sys, "frozen", False):
        return Path(__file__).resolve().parent / "saved_settings.json"
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or str(Path.home())
        return Path(base) / _APP_NAME / "settings.json"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / _APP_NAME / "settings.json"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / _APP_NAME / "settings.json"


_SETTINGS_FILE = _resolve_settings_file()

# ── Keys ───────────────────────────────────────────────────────────────
KEY_CSV_PATH = "csv_path"                  # the archive CSV (full data frame)
KEY_ROSTER_PATH = "roster_path"            # the enrolment workbook (.xlsx)
KEY_ROSTER_SHEET = "roster_sheet"          # worksheet name inside it
KEY_COL_PATIENT_ID = "col_patient_id"      # header of the study-ID column
KEY_COL_PATIENT_NAME = "col_patient_name"  # header of the name column
KEY_COL_MRN = "col_mrn"                    # header of the MRN column
KEY_EXPORT_DIR = "export_dir"              # where reports and figures go by default
KEY_SELECTED_GRAPHS = "selected_graphs"    # graph keys ticked by default ([] = every graph)

DEFAULTS: dict = {
    KEY_CSV_PATH: "",
    KEY_ROSTER_PATH: "",
    KEY_ROSTER_SHEET: "SNBR enrolment log",
    KEY_COL_PATIENT_ID: "Patient ID",
    KEY_COL_PATIENT_NAME: "Patient Name",
    KEY_COL_MRN: "MRN",
    KEY_EXPORT_DIR: "",
    KEY_SELECTED_GRAPHS: [],
}

# Keys whose value is a filesystem path.
PATH_KEYS = (KEY_CSV_PATH, KEY_ROSTER_PATH, KEY_EXPORT_DIR)
# The two inputs the app cannot do anything without.
REQUIRED_KEYS = (KEY_CSV_PATH, KEY_ROSTER_PATH)


def _read() -> dict:
    if _SETTINGS_FILE.exists():
        try:
            data = json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _write(data: dict) -> None:
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(_SETTINGS_FILE.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, str(_SETTINGS_FILE))
    except BaseException:
        os.unlink(tmp)
        raise


def load_settings() -> dict:
    """Return every setting, defaults filled in for anything unset or malformed."""
    raw = _read()
    out = {}
    for key, default in DEFAULTS.items():
        value = raw.get(key, default)
        if isinstance(default, list):
            value = [str(v) for v in value] if isinstance(value, list) else list(default)
        elif not isinstance(value, str):
            value = default if value is None else str(value)
        out[key] = value
    return out


def save_settings(**kwargs) -> None:
    """Merge the given key=value pairs into the saved settings (atomic)."""
    data = _read()
    for key, value in kwargs.items():
        if key not in DEFAULTS:
            raise KeyError(f"unknown clinical setting: {key}")
        data[key] = value
    _write(data)


def missing_required(settings: dict) -> list[str]:
    """The required settings still blank, as the labels the window shows."""
    labels = {
        KEY_CSV_PATH: "Archive CSV (full data frame)",
        KEY_ROSTER_PATH: "Enrolment workbook",
    }
    return [labels[key] for key in REQUIRED_KEYS if not str(settings.get(key, "")).strip()]
