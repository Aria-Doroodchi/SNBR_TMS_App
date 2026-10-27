"""The participant page shows the selected participant's type under the calendar.

The type is read from the selected *visit*: a participant's rows can disagree
(SNBR-080 is a Control at baseline and a Patient at both follow-ups), so the
label must follow the date as well as the ID.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gui.controller import AppController


def _df():
    return pd.DataFrame([
        {"Study": "SNBR", "ID": 80, "Date": "22/04/2024", "Subject_type": "Control"},
        {"Study": "SNBR", "ID": 80, "Date": "18/08/2026", "Subject_type": "Patient"},
        {"Study": "SNBR", "ID": 81, "Date": "18/08/2026", "Subject_type": None},
        {"Study": "NIALS", "ID": 80, "Date": "01/01/2025", "Subject_type": "Control"},
    ])


@pytest.fixture
def controller():
    c = AppController()
    c.set_dataframe(_df())
    return c


def test_type_follows_the_visit(controller):
    assert controller.get_subject_type(80, datetime(2024, 4, 22)) == "Control"
    assert controller.get_subject_type(80, datetime(2026, 8, 18)) == "Patient"


def test_without_a_visit_the_latest_dated_one_wins(controller):
    # By date, not by the dd/mm/yyyy string ("22/04/2024" > "18/08/2026").
    assert controller.get_subject_type(80, study_filter="SNBR") == "Patient"
    assert controller.get_subject_type(80, datetime(2020, 1, 1), "SNBR") == "Patient"


def test_study_filter_separates_shared_numbers(controller):
    assert controller.get_subject_type(80, study_filter="NIALS") == "Control"


def test_unrecorded_and_unknown(controller):
    assert controller.get_subject_type(81, datetime(2026, 8, 18)) is None
    assert controller.get_subject_type(999) is None


def test_label_under_the_calendar_tracks_the_selection(tk_root, controller):
    from gui.participant_panel import ParticipantPanel

    panel = ParticipantPanel(tk_root, controller, on_next=lambda: None, on_back=lambda: None)
    try:
        panel.refresh()
        # The calendar's column holds the label, below the calendar itself.
        cal_row = panel._calendar.grid_info()["row"]
        label = panel._subject_type_label
        assert label.master is panel._calendar.master
        assert label.grid_info()["row"] > cal_row

        panel._study_var.set("SNBR")
        panel._on_study_changed("SNBR")
        panel._select_id(81)
        assert panel._subject_type_var.get() == "Participant type: not recorded"

        panel._select_id(80)
        assert panel._subject_type_var.get() == "Participant type: Patient"

        panel._calendar.selection_set(datetime(2024, 4, 22))
        panel._on_date_changed(None)
        assert panel._subject_type_var.get() == "Participant type: Control"
    finally:
        panel.destroy()
