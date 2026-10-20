"""Tests for the Data Import page's fourth option: the archive + today's visits.

The option exists to make a report for the patients seen today without
re-reading every folder, so the tests pin both halves of that promise:

* only the day's files are opened — a parse counter, not a timing, proves it;
* what it builds for today is exactly what a full parse builds for today, and
  every other row is the archive as stored.

Then the wiring: the page offers it and saves its own slug, Quick Start replays
it, and a stale archive or an empty day is said out loud rather than producing
a report for the wrong visit.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import gui.controller as controller_module
import processing.df_builder as df_builder
from core.user_settings import DATA_MODE_TODAY_ONLY, KEY_DATA_MODE, save_defaults
from gui.controller import AppController
from gui.data_mode_panel import MODE_TODAY_ONLY
from parser.mem_parser import output_column_order
from processing.df_builder import (
    build_combined_dataframe,
    build_today_dataframe,
    files_recorded_on,
)

TODAY = dt.date(2026, 10, 14)
TODAY_STR = "14/10/2026"

_MIN_MEM = """\
Name: SNBR-999
Date: 01/01/2026
Age: 40
Sex: M
Subject type: Patient
Stim/record: L-APB -> APB

DERIVED EXCITABILITY VARIABLES

EXTRA VARIABLES
RMT50 = 50
RMT200 = 55
RMT1000 = 60
T-SICI(70%)1.0ms = -10.0

EXTRA WAVEFORMS
"""


def _write_mem(folder: Path, name: str, pid: int, date: str, rmt200: int = 55):
    text = (
        _MIN_MEM.replace("SNBR-999", f"SNBR-{pid:03d}")
        .replace("01/01/2026", date)
        .replace("RMT200 = 55", f"RMT200 = {rmt200}")
    )
    (folder / name).write_text(text, encoding="utf-8")


def _old_mtime(path: Path) -> None:
    """Age a file so only its token/header can make it 'today's'."""
    stamp = time.mktime((2025, 1, 1, 12, 0, 0, 0, 0, -1))
    os.utime(path, (stamp, stamp))


@pytest.fixture
def world(tmp_path):
    """A MEM folder with two archived visits and two recorded today."""
    mem = tmp_path / "mem"
    mem.mkdir()
    _write_mem(mem, "SNBR-031-TP3C60101A.MEM", 31, "01/01/2026")
    _write_mem(mem, "SNBR-032-TP3C60315A.MEM", 32, "15/03/2026")
    for f in mem.iterdir():
        _old_mtime(f)

    archive = build_combined_dataframe(mem)
    csv = tmp_path / "archive.csv"
    archive[output_column_order()].to_csv(csv, index=False)

    # Recorded today, after the archive was exported.
    _write_mem(mem, "SNBR-040-TP3C61014A.MEM", 40, TODAY_STR)
    _write_mem(mem, "SNBR-041-LCX-TP3C61014B.MEM", 41, TODAY_STR)
    for name in ("SNBR-040-TP3C61014A.MEM", "SNBR-041-LCX-TP3C61014B.MEM"):
        _old_mtime(mem / name)
    return mem, csv


def _count_parses(monkeypatch) -> list[str]:
    opened: list[str] = []
    real = df_builder.parse_mem_file

    def spy(path):
        opened.append(Path(path).name)
        return real(path)

    monkeypatch.setattr(df_builder, "parse_mem_file", spy)
    return opened


# --------------------------------------------------------------------------
# The builder
# --------------------------------------------------------------------------

def test_only_todays_files_are_opened(world, monkeypatch):
    mem, csv = world
    opened = _count_parses(monkeypatch)

    build_today_dataframe(csv, mem, today=TODAY)

    assert sorted(opened) == [
        "SNBR-040-TP3C61014A.MEM", "SNBR-041-LCX-TP3C61014B.MEM",
    ]


def test_todays_rows_match_a_full_parse_and_the_rest_is_the_archive(world):
    mem, csv = world

    got = build_today_dataframe(csv, mem, today=TODAY)
    full = build_combined_dataframe(mem)

    def rows(df, today):
        mask = df["Date"] == TODAY_STR
        part = df[mask] if today else df[~mask]
        return part.sort_values("ID").reset_index(drop=True).astype(str)

    assert rows(got, True).equals(rows(full, True))
    archive = df_builder.load_existing_csv(csv)
    assert rows(got, False).equals(rows(archive, False))
    assert got.attrs["today_rows"] == 2
    assert got.attrs["today_mem_files"] == 2


def test_running_again_later_replaces_todays_archived_rows(world, tmp_path):
    """An archive exported mid-day must not keep a stale copy of today."""
    mem, csv = world
    midday = build_today_dataframe(csv, mem, today=TODAY)
    midday[output_column_order()].to_csv(csv, index=False)

    # Participant 40's file is re-analysed in the afternoon.
    _write_mem(mem, "SNBR-040-TP3C61014A.MEM", 40, TODAY_STR, rmt200=70)

    got = build_today_dataframe(csv, mem, today=TODAY)

    p40 = got[got["ID"] == 40]
    assert len(p40) == 1
    assert float(p40["RMT200"].iloc[0]) == 70
    assert got.attrs["archive_rows_replaced"] == 2
    assert len(got) == 4


def test_a_day_with_no_recordings_returns_the_archive(world):
    mem, csv = world

    got = build_today_dataframe(csv, mem, today=dt.date(2026, 10, 15))

    assert got.attrs["today_rows"] == 0
    assert len(got) == 2


def test_a_token_naming_another_day_is_never_opened(tmp_path):
    """Even when the file was touched today (re-saved files are common)."""
    f = tmp_path / "SNBR-031-TP3C60101A.MEM"
    f.write_text("x", encoding="utf-8")
    noon = time.mktime((TODAY.year, TODAY.month, TODAY.day, 12, 0, 0, 0, 0, -1))
    os.utime(f, (noon, noon))

    assert files_recorded_on([f], TODAY) == []


def test_a_file_without_a_token_is_judged_by_its_modified_date(tmp_path):
    fresh = tmp_path / "SNBR-050 session.MEM"
    fresh.write_text("x", encoding="utf-8")
    old = tmp_path / "SNBR-051 session.MEM"
    old.write_text("x", encoding="utf-8")
    _old_mtime(old)

    assert files_recorded_on([fresh, old], dt.date.today()) == [fresh]


def test_a_candidate_whose_header_names_another_day_is_left_out(world):
    """The token is a pre-filter; the header Date decides."""
    mem, csv = world
    _write_mem(mem, "SNBR-060-TP3C61014C.MEM", 60, "13/10/2026")

    got = build_today_dataframe(csv, mem, today=TODAY)

    assert 60 not in set(got["ID"].astype(int))


# --------------------------------------------------------------------------
# The controller
# --------------------------------------------------------------------------

def _controller(mem, csv):
    c = AppController()
    c.set_paths(mem_path=[str(mem)], csv_path=str(csv))
    return c


def test_the_controller_names_who_was_seen_today(world):
    mem, csv = world
    c = _controller(mem, csv)

    df = c.load_today_dataframe(today=TODAY)

    assert df.attrs["today_visits"] == ["SNBR-040", "SNBR-041"]
    assert df.attrs["today_fallback"] is False
    assert c.get_dataframe() is df


def test_a_stale_archive_falls_back_to_the_incremental_build(world, monkeypatch):
    mem, csv = world
    c = _controller(mem, csv)
    monkeypatch.setattr(controller_module, "csv_schema_is_current", lambda p: False)
    calls = []
    real = c.parse_and_build

    def spy():
        calls.append("parse")
        return real()

    monkeypatch.setattr(c, "parse_and_build", spy)

    df = c.load_today_dataframe(today=TODAY)

    assert calls == ["parse"]
    assert df.attrs["today_fallback"] is True
    assert df.attrs["today_visits"] == ["SNBR-040", "SNBR-041"]


def test_quick_start_replays_the_saved_today_mode(world, monkeypatch):
    mem, csv = world
    save_defaults(**{KEY_DATA_MODE: DATA_MODE_TODAY_ONLY})
    c = _controller(mem, csv)
    real = c.load_today_dataframe
    monkeypatch.setattr(c, "load_today_dataframe", lambda: real(today=TODAY))

    summary = c.run_default_phases(2, 3)

    assert summary["today_visits"] == ["SNBR-040", "SNBR-041"]


def test_quick_start_refuses_a_day_with_no_visits(world, monkeypatch):
    """Otherwise the most-recent-visit step would report an old visit."""
    mem, csv = world
    save_defaults(**{KEY_DATA_MODE: DATA_MODE_TODAY_ONLY})
    c = _controller(mem, csv)
    real = c.load_today_dataframe
    monkeypatch.setattr(
        c, "load_today_dataframe", lambda: real(today=dt.date(2026, 10, 15)),
    )

    with pytest.raises(ValueError, match="No visits recorded today"):
        c.run_default_phases(2, 3)


# --------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------

def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def _panel(tk_root, controller):
    import customtkinter as ctk

    from gui.data_mode_panel import DataModePanel

    return DataModePanel(
        ctk.CTkFrame(tk_root), controller,
        on_next=lambda: None, on_back=lambda: None,
    )


def _today_radio(panel):
    import customtkinter as ctk

    radios = [
        w for w in _walk(panel)
        if isinstance(w, ctk.CTkRadioButton) and "today" in w.cget("text").lower()
    ]
    assert len(radios) == 1, "the page has no 'today's visits' option"
    return radios[0]


def test_the_page_offers_the_option_only_with_an_archive(tk_root):
    with_csv = AppController()
    with_csv.set_paths(mem_path=[], csv_path="archive.csv")
    without = AppController()
    without.set_paths(mem_path=[], csv_path="")
    a, b = _panel(tk_root, with_csv), _panel(tk_root, without)

    a.refresh()
    b.refresh()

    assert _today_radio(a).cget("state") == "normal"
    assert _today_radio(b).cget("state") == "disabled"


def test_saving_the_option_stores_its_own_slug_and_reopens_on_it(
    tk_root, monkeypatch,
):
    import customtkinter as ctk

    c = AppController()
    c.set_paths(mem_path=[], csv_path="archive.csv")
    panel = _panel(tk_root, c)
    monkeypatch.setattr(panel, "_run_import", lambda *a, **k: None)
    panel.refresh()

    _today_radio(panel).invoke()
    next(
        w for w in _walk(panel)
        if isinstance(w, ctk.CTkCheckBox) and w.cget("text") == "Save as default"
    ).select()
    panel._handle_next()

    assert c.get_data_mode_default() == DATA_MODE_TODAY_ONLY
    reopened = _panel(tk_root, c)
    reopened.refresh()
    assert reopened._mode_var.get() == MODE_TODAY_ONLY
