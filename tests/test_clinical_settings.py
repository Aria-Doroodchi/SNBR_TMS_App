"""clinical/settings.py -- its own file, its own keys.

``tests/conftest.py`` points ``_SETTINGS_FILE`` at a temp file for every
test, as it does for the other two apps' settings.
"""

from __future__ import annotations

import json

import pytest

from clinical import settings as cs


def test_defaults_are_the_lab_headers_and_empty_paths():
    s = cs.load_settings()
    assert s[cs.KEY_ROSTER_SHEET] == "SNBR enrolment log"
    assert s[cs.KEY_COL_PATIENT_ID] == "Patient ID"
    assert s[cs.KEY_COL_PATIENT_NAME] == "Patient Name"
    assert s[cs.KEY_COL_MRN] == "MRN"
    assert s[cs.KEY_SELECTED_GRAPHS] == []
    for key in cs.PATH_KEYS:
        assert s[key] == ""


def test_settings_are_isolated_from_the_repo_file(tmp_path):
    assert tmp_path in cs._SETTINGS_FILE.parents


def test_save_merges_and_round_trips():
    cs.save_settings(**{cs.KEY_CSV_PATH: "Y:/df.csv"})
    cs.save_settings(**{cs.KEY_SELECTED_GRAPHS: ["profile__t_sici", "visit_table"]})
    s = cs.load_settings()
    assert s[cs.KEY_CSV_PATH] == "Y:/df.csv"
    assert s[cs.KEY_SELECTED_GRAPHS] == ["profile__t_sici", "visit_table"]
    raw = json.loads(cs._SETTINGS_FILE.read_text(encoding="utf-8"))
    assert set(raw) == {cs.KEY_CSV_PATH, cs.KEY_SELECTED_GRAPHS}


def test_unknown_key_is_rejected():
    """The analysis app's keys, or the dispatch app's, do not belong here."""
    with pytest.raises(KeyError):
        cs.save_settings(mem_dir="x")
    with pytest.raises(KeyError):
        cs.save_settings(ledger_path="x")


def test_corrupt_values_fall_back_to_defaults():
    cs._SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    cs._SETTINGS_FILE.write_text(
        json.dumps({cs.KEY_SELECTED_GRAPHS: "not a list", cs.KEY_CSV_PATH: None}),
        encoding="utf-8",
    )
    s = cs.load_settings()
    assert s[cs.KEY_SELECTED_GRAPHS] == []
    assert s[cs.KEY_CSV_PATH] == ""


def test_the_two_inputs_are_required_and_named_for_the_user():
    assert cs.missing_required(cs.load_settings()) == [
        "Archive CSV (full data frame)", "Enrolment workbook",
    ]
    cs.save_settings(**{cs.KEY_CSV_PATH: "Y:/df.csv"})
    assert cs.missing_required(cs.load_settings()) == ["Enrolment workbook"]
    cs.save_settings(**{cs.KEY_ROSTER_PATH: "Y:/log.xlsx"})
    assert cs.missing_required(cs.load_settings()) == []
