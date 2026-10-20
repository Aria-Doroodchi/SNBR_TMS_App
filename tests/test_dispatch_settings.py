"""dispatch/settings.py -- its own file, its own guards.

``tests/conftest.py`` points ``_SETTINGS_FILE`` at a temp file for every
test, the same way it isolates the analysis app's settings.
"""

from __future__ import annotations

import json

import pytest

from dispatch import settings as ds


def test_defaults_are_the_lab_headers_and_a_20mb_cap():
    s = ds.load_settings()
    assert s[ds.KEY_ROSTER_SHEET] == "SNBR enrolment log"
    assert s[ds.KEY_COL_PATIENT_ID] == "Patient ID"
    assert s[ds.KEY_COL_PATIENT_NAME] == "Patient Name"
    assert s[ds.KEY_COL_MRN] == "MRN"
    assert s[ds.KEY_SIZE_CAP_MB] == 20
    for key in ds.PATH_KEYS:
        assert s[key] == ""


def test_settings_are_isolated_from_the_repo_file(tmp_path):
    assert tmp_path in ds._SETTINGS_FILE.parents


def test_save_merges_and_round_trips():
    ds.save_settings(**{ds.KEY_ROSTER_PATH: "Y:/roster.xlsx"})
    ds.save_settings(**{ds.KEY_SIZE_CAP_MB: 15})
    s = ds.load_settings()
    assert s[ds.KEY_ROSTER_PATH] == "Y:/roster.xlsx"
    assert s[ds.KEY_SIZE_CAP_MB] == 15
    raw = json.loads(ds._SETTINGS_FILE.read_text(encoding="utf-8"))
    assert set(raw) == {ds.KEY_ROSTER_PATH, ds.KEY_SIZE_CAP_MB}


def test_unknown_key_is_rejected():
    with pytest.raises(KeyError):
        ds.save_settings(smtp_host="x")


def test_corrupt_values_fall_back_to_defaults():
    ds._SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ds._SETTINGS_FILE.write_text(
        json.dumps({ds.KEY_SIZE_CAP_MB: "lots"}),
        encoding="utf-8",
    )
    s = ds.load_settings()
    assert s[ds.KEY_SIZE_CAP_MB] == 20


def test_email_settings_are_gone_and_dropped_from_an_old_file():
    """Sending is manual: no To list, domain guard or subject template remains.

    A settings file saved by the earlier version still carries them; they are
    ignored on load and removed the next time the file is written.
    """
    ds._SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ds._SETTINGS_FILE.write_text(json.dumps({
        ds.KEY_ROSTER_PATH: "Y:/roster.xlsx",
        "recipients": ["dr.a@sunnybrook.ca"],
        "allowed_domain": "sunnybrook.ca",
        "subject_template": "week of {week_start}",
    }), encoding="utf-8")
    loaded = ds.load_settings()
    assert set(loaded) == set(ds.DEFAULTS)
    assert not set(ds.RETIRED_KEYS) & set(ds.DEFAULTS)
    with pytest.raises(KeyError):
        ds.save_settings(recipients=["x@sunnybrook.ca"])

    ds.save_settings(**{ds.KEY_SIZE_CAP_MB: 10})
    raw = json.loads(ds._SETTINGS_FILE.read_text(encoding="utf-8"))
    assert raw == {ds.KEY_ROSTER_PATH: "Y:/roster.xlsx", ds.KEY_SIZE_CAP_MB: 10}


def test_identified_folder_inside_a_sync_source_is_refused(tmp_path):
    source = tmp_path / "Y_share" / "Reports"
    (source / "identified").mkdir(parents=True)
    pairs = [{"source": str(source), "destination": str(tmp_path / "backup")}]
    assert ds.sync_source_conflicts(source / "identified", pairs) == [str(source)]
    assert ds.sync_source_conflicts(source, pairs) == [str(source)]
    assert ds.sync_source_conflicts(tmp_path / "elsewhere", pairs) == []
    assert ds.sync_source_conflicts("", pairs) == []


def test_analysis_app_sync_pairs_are_read_not_written(tmp_path):
    """The dispatch app reads the analysis app's saved pairs and nothing else."""
    from core import user_settings
    user_settings.save_defaults(**{user_settings.KEY_SYNC_PAIRS: [{"source": "S", "destination": "D"}]})
    before = user_settings._SETTINGS_FILE.read_bytes()
    assert ds.analysis_app_sync_pairs() == [{"source": "S", "destination": "D"}]
    assert user_settings._SETTINGS_FILE.read_bytes() == before
