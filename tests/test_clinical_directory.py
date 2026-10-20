"""clinical/directory.py -- joining the data frame to the roster, and search.

Hermetic: the frame is built from synthetic records and the roster is
constructed in memory, so neither openpyxl nor a workbook is needed.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from clinical.directory import Directory, Participant, build_directory
from dispatch.identity import Identity, ParticipantKey
from dispatch.roster import Roster, RosterProblem
from tests._clinical_fixtures import ROSTER_ROWS, dataframe, record
from processing.df_builder import build_mem_dataframe


def _roster(rows=ROSTER_ROWS, problems=()):
    from dispatch.identity import parse_patient_id

    roster = Roster(problems=list(problems))
    for raw, name, mrn in rows:
        key = parse_patient_id(raw)
        roster.entries[key] = Identity(key=key, patient_id_raw=raw, name=name or "", mrn=mrn or "")
    return roster


@pytest.fixture(scope="module")
def directory() -> Directory:
    return build_directory(dataframe(), _roster())


def _by_label(directory, label) -> Participant:
    return next(p for p in directory.participants if p.label == label)


# -- the join ------------------------------------------------------------------

def test_every_participant_with_visits_is_listed_once(directory):
    labels = sorted(p.label for p in directory.with_data())
    assert labels == sorted(
        ["SNBR-080", "SNBR-081", "SNBR-003", "NIALS-003"] + [f"SNBR-{n:03d}" for n in range(10, 16)]
    )


def test_the_roster_identity_is_attached_and_the_prefix_ignored(directory):
    jane = _by_label(directory, "SNBR-080")
    assert jane.name == "Jane Doe" and jane.mrn == "1234567"
    assert jane.identifying and not jane.partial and jane.unresolved_reason == ""
    assert jane.identity.patient_id_raw == "AA-SNBR-080"


def test_the_same_number_in_two_studies_is_two_people(directory):
    """41 of the archive's numeric IDs name several people; the key is (study, number)."""
    ann, bob = _by_label(directory, "SNBR-003"), _by_label(directory, "NIALS-003")
    assert ann.name == "Ann Smith" and bob.name == "Bob Jones"
    assert ann.visits == (datetime(2026, 3, 1),)
    assert bob.visits == (datetime(2026, 3, 5),)


def test_visits_are_ascending_and_the_subject_type_is_the_latest_visits(directory):
    jane = _by_label(directory, "SNBR-080")
    assert jane.visit_labels() == ["22/04/2024", "18/08/2026"]
    assert jane.latest_visit == datetime(2026, 8, 18)
    assert jane.subject_type == "Patient"
    assert _by_label(directory, "SNBR-081").subject_type == "Control"


def test_a_roster_row_without_an_mrn_still_identifies(directory):
    jose = _by_label(directory, "SNBR-081")
    assert jose.identifying and jose.partial
    assert jose.unresolved_reason == ""   # the stamp says what is missing, the join does not
    assert jose.mrn == ""


def test_a_participant_with_no_roster_row_is_listed_by_study_id(directory):
    p = _by_label(directory, "SNBR-010")
    assert p.identity is None and p.unidentified
    assert p.unresolved_reason == "SNBR-010 is not in the roster"
    assert p.display_name == "(name not in the enrolment log)"


def test_a_roster_row_with_no_visits_is_listed_as_having_no_data(directory):
    never = _by_label(directory, "SNBR-099")
    assert never.name == "Never Tested"
    assert not never.has_data and never.visits == () and never.latest_visit is None
    assert len(directory) == len(directory.with_data()) + 1
    assert directory.roster_size == len(ROSTER_ROWS)


def test_rows_with_no_study_name_match_the_roster_on_the_number_alone():
    df = build_mem_dataframe([record(80, "18/08/2026", 95.0, study="")])
    roster = _roster([("AA-SNBR-080", "Jane Doe", "1234567")])
    d = build_directory(df, roster)
    [jane] = d.with_data()
    assert jane.key == ParticipantKey("SNBR", 80), "the roster's key is adopted"
    assert jane.name == "Jane Doe"


def test_an_ambiguous_number_without_a_study_is_not_guessed():
    df = build_mem_dataframe([record(3, "18/08/2026", 95.0, study="")])
    d = build_directory(df, _roster())
    [p] = d.with_data()
    assert p.identity is None
    assert "matches several studies" in p.unresolved_reason


def test_roster_problems_are_carried_through():
    problems = [RosterProblem(7, "080", "Patient ID does not end in a study token and number")]
    d = build_directory(dataframe(), _roster(problems=problems))
    assert d.roster_problems == problems


def test_find_by_key(directory):
    assert directory.find(ParticipantKey("SNBR", 80)).name == "Jane Doe"
    assert directory.find(ParticipantKey("SNBR", 1)) is None


# -- search --------------------------------------------------------------------

def _labels(results):
    return [p.label for p in results]


def test_empty_query_lists_everyone_named_first_alphabetically(directory):
    labels = _labels(directory.search(""))
    assert labels[:5] == ["SNBR-003", "NIALS-003", "SNBR-080", "SNBR-081", "SNBR-099"]
    assert labels[5:] == [f"SNBR-{n:03d}" for n in range(10, 16)]


@pytest.mark.parametrize("query", ["doe", "jane", "Jane Doe", "doe j", "JANE", "ane do", "  jane   "])
def test_name_matches_by_word_prefix_in_any_order(directory, query):
    assert _labels(directory.search(query)) == ["SNBR-080"]


@pytest.mark.parametrize("query", ["jose", "José", "muller", "Müller", "mul jos"])
def test_name_matching_ignores_accents(directory, query):
    assert _labels(directory.search(query)) == ["SNBR-081"]


def test_mrn_matches_by_prefix_not_substring(directory):
    assert _labels(directory.search("1234567")) == ["SNBR-080"]
    assert _labels(directory.search("1234")) == ["SNBR-080"]
    # "34" is inside Jane's MRN but is not a prefix of it; it does match 034.
    assert "SNBR-080" not in _labels(directory.search("34"))


@pytest.mark.parametrize("query", ["SNBR-080", "snbr-080", "snbr 80", "SNBR080", "80", "080"])
def test_study_id_in_any_spelling(directory, query):
    assert _labels(directory.search(query))[0] == "SNBR-080"


def test_a_bare_number_finds_both_studies_and_partial_ids(directory):
    labels = _labels(directory.search("3"))
    assert labels[:2] == ["SNBR-003", "NIALS-003"], "exact number first, by name"
    assert labels[2:] == ["SNBR-013"], "then the number containing the digit"


def test_a_study_qualified_id_finds_one_person(directory):
    assert _labels(directory.search("nials 3")) == ["NIALS-003"]
    assert _labels(directory.search("NIALS-003")) == ["NIALS-003"]


def test_exact_hits_outrank_partial_ones():
    """A participant whose MRN starts with the digits of someone else's number."""
    df = build_mem_dataframe([record(80, "18/08/2026", 95.0), record(12, "18/08/2026", 90.0)])
    roster = _roster([("SNBR-080", "Jane Doe", "1250000"), ("SNBR-012", "Pat Lee", "8000001")])
    d = build_directory(df, roster)
    assert _labels(d.search("80")) == ["SNBR-080", "SNBR-012"], "080 exact before the 8000001 prefix hit"
    assert _labels(d.search("12")) == ["SNBR-012", "SNBR-080"], "012 exact before the 1250000 prefix hit"


def test_no_match_is_an_empty_list(directory):
    assert directory.search("zzz") == []
    assert directory.search("999") == ["SNBR-099"] or _labels(directory.search("999")) == ["SNBR-099"]
