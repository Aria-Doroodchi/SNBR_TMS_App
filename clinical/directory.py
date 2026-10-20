"""Who is in the data frame, who is in the enrolment log, and finding them.

The two sources name a participant differently and neither is complete on
its own: the archive CSV knows the visits but no names, the enrolment
workbook knows the names but nothing about what was recorded. This module
joins them on the :class:`~dispatch.identity.ParticipantKey` -- the study
token and the number -- exactly as the dispatch app joins a report to the
roster, and answers the one question the clinical collaborators ask: *find
this patient*, by whatever they happen to know.

Search rules (:meth:`Directory.search`), all case- and accent-insensitive:

* **Name** -- every word typed must be the start of a word of the name, in
  any order, so ``doe j`` finds ``Jane Doe``; a run of text inside the name
  (``ane do``) also matches.
* **MRN** -- the digits typed are the start of the MRN. A prefix rather than a
  substring: a two-digit query matching *inside* every MRN would bury the
  study-ID hits it was meant for.
* **Study ID** -- ``SNBR-080``, ``snbr 80``, ``snbr080`` or just ``80``; a
  run of digits also matches inside the three-digit number (``80`` finds
  ``080`` and ``180``), which is how the analysis app's picker behaves.

A roster row with no visits is still listed -- flagged as having no data --
so a clinician whose patient is enrolled but not yet recorded learns that,
rather than "not found". A participant with visits but no roster row is
listed too, by study ID alone, so the data is never unreachable.

Visits are grouped by the study the analysis app resolves for them
(:func:`processing.cohort_filters.participant_study`), because participant
numbers repeat across studies: SNBR-003 and NIALS-003 are different people
and must stay different entries.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from dispatch.identity import Identity, ParticipantKey, parse_patient_id
from dispatch.roster import Roster, RosterProblem
from processing.cohort_filters import participant_study

DATE_FORMAT = "%d/%m/%Y"
_SUBJECT_TYPE_COLUMN = "Subject_type"


@dataclass(frozen=True)
class Participant:
    """One person: their key, what the enrolment log says, and their visits."""

    key: ParticipantKey
    identity: Identity | None
    unresolved_reason: str          # "" when the roster identifies them
    visits: tuple[datetime, ...]    # ascending
    subject_type: str = ""          # from the latest visit that records one

    @property
    def number(self) -> int:
        return self.key.number

    @property
    def study(self) -> str:
        return self.key.study

    @property
    def label(self) -> str:
        """``SNBR-080`` -- the study ID as the reports print it."""
        return self.key.label()

    @property
    def name(self) -> str:
        return self.identity.name.strip() if self.identity else ""

    @property
    def mrn(self) -> str:
        return self.identity.mrn.strip() if self.identity else ""

    @property
    def has_data(self) -> bool:
        return bool(self.visits)

    @property
    def latest_visit(self) -> datetime | None:
        return self.visits[-1] if self.visits else None

    @property
    def identifying(self) -> bool:
        """A name, an MRN, or both: something the cover can carry."""
        return self.identity is not None and self.identity.identifying

    @property
    def partial(self) -> bool:
        return self.identity is not None and self.identity.partial

    @property
    def unidentified(self) -> bool:
        return not self.identifying

    @property
    def display_name(self) -> str:
        return self.name or "(name not in the enrolment log)"

    def visit_labels(self) -> list[str]:
        return [v.strftime(DATE_FORMAT) for v in self.visits]


@dataclass
class Directory:
    participants: list[Participant]
    roster_problems: list[RosterProblem]
    roster_size: int = 0

    def __len__(self) -> int:
        return len(self.participants)

    def with_data(self) -> list[Participant]:
        return [p for p in self.participants if p.has_data]

    def find(self, key: ParticipantKey) -> Participant | None:
        for p in self.participants:
            if p.key == key:
                return p
        return None

    def search(self, query: str) -> list[Participant]:
        """The participants matching *query*, best matches first.

        An empty query lists everyone, by name. Exact hits (the whole study ID
        or the whole MRN) come first, then name matches, then partial ID and
        MRN matches; ties are broken by name and then key so the order is
        stable for the same query.
        """
        folded = _fold(query)
        if not folded:
            return sorted(self.participants, key=_sort_key)
        ranked = []
        for p in self.participants:
            rank = _match_rank(p, folded)
            if rank is not None:
                ranked.append((rank, _sort_key(p), p))
        ranked.sort(key=lambda t: (t[0], t[1]))
        return [p for _, _, p in ranked]


# -- building ----------------------------------------------------------------

def build_directory(df: pd.DataFrame, roster: Roster) -> Directory:
    """Join the data frame's visits to the roster's identities."""
    visits = _visits_by_key(df)
    participants: list[Participant] = []
    claimed: set[ParticipantKey] = set()

    for key, dated in sorted(visits.items(), key=lambda kv: (kv[0].number, kv[0].study)):
        identity, reason = roster.lookup(key)
        resolved = identity.key if identity is not None else key
        claimed.add(resolved)
        dates = tuple(sorted(dated))
        participants.append(Participant(
            key=resolved,
            identity=identity,
            unresolved_reason=_unresolved_reason(identity, reason),
            visits=dates,
            subject_type=_latest_subject_type(df, key.number, dates),
        ))

    for key, identity in roster.entries.items():
        if key in claimed:
            continue
        participants.append(Participant(
            key=key, identity=identity,
            unresolved_reason=_unresolved_reason(identity, ""),
            visits=(),
        ))

    return Directory(
        participants=participants,
        roster_problems=list(roster.problems),
        roster_size=len(roster),
    )


def _unresolved_reason(identity: Identity | None, lookup_reason: str) -> str:
    if identity is None:
        return lookup_reason or "not in the enrolment log"
    if identity.identifying:
        return ""
    return f"roster row lacks {' and '.join(identity.missing_fields())}"


def _visits_by_key(df: pd.DataFrame) -> dict[ParticipantKey, set[datetime]]:
    """``{(study, number): {visit dates}}`` for every dated row in *df*.

    The study of a visit is what the analysis app would print on that visit's
    report, so a participant whose rows carry no study name at all gets an
    empty study token and is matched to the roster on the number alone.
    """
    out: dict[ParticipantKey, set[datetime]] = {}
    if df is None or df.empty or "ID" not in df.columns or "Date" not in df.columns:
        return out
    ids = pd.to_numeric(df["ID"], errors="coerce")
    for pid in sorted(ids.dropna().unique()):
        pid = int(pid)
        rows = df[ids == pid]
        for raw in rows["Date"].dropna().unique():
            text = str(raw).strip()
            try:
                when = datetime.strptime(text, DATE_FORMAT)
            except ValueError:
                continue
            study = participant_study(rows, pid, visit_date=text) or ""
            key = ParticipantKey(study.strip().upper(), pid)
            out.setdefault(key, set()).add(when)
    return out


def _latest_subject_type(df: pd.DataFrame, pid: int, dates: tuple[datetime, ...]) -> str:
    """The subject type of the latest visit that records one, else ``""``.

    By visit date, not row order: the frame is not date-sorted and the
    analysis app types a participant from their latest visit.
    """
    if _SUBJECT_TYPE_COLUMN not in df.columns:
        return ""
    ids = pd.to_numeric(df["ID"], errors="coerce")
    rows = df[ids == pid]
    for when in reversed(dates):
        dated = rows[rows["Date"].astype("string").str.strip() == when.strftime(DATE_FORMAT)]
        values = dated[_SUBJECT_TYPE_COLUMN].astype("string").fillna("").str.strip()
        values = values[values != ""]
        if not values.empty:
            return str(values.iloc[0])
    return ""


# -- matching ----------------------------------------------------------------

def _fold(text) -> str:
    """Lower-case, accent-stripped, single-spaced."""
    if text is None:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(text))
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(plain.casefold().split())


def _compact(text: str) -> str:
    return "".join(ch for ch in text if ch.isalnum())


def _sort_key(p: Participant):
    # Named participants first, alphabetically; the unnamed after, by key.
    return (0 if p.name else 1, _fold(p.name), p.key)


def _match_rank(p: Participant, folded: str) -> int | None:
    """``0`` exact, ``1`` name, ``2`` partial ID/MRN; ``None`` for no match."""
    compact = _compact(folded)

    # The whole study ID ("snbr-080", "snbr 80", "SNBR080").
    parsed = parse_patient_id(folded)
    if parsed is not None and parsed.number == p.number and (
        not parsed.study or parsed.study.upper() == p.study.upper()
    ):
        return 0

    if compact.isdigit() and compact:
        if p.mrn and compact == p.mrn:
            return 0
        if compact.lstrip("0") == str(p.number) and compact.lstrip("0"):
            return 0

    name = _fold(p.name)
    if name:
        words = name.split()
        tokens = folded.split()
        if all(any(w.startswith(t) for w in words) for t in tokens):
            return 1
        if folded in name:
            return 1

    if compact.isdigit() and compact:
        if p.mrn and p.mrn.startswith(compact):
            return 2
        if compact in f"{p.number:03d}":
            return 2
    elif compact and compact in _compact(_fold(p.label)):
        return 2
    return None
