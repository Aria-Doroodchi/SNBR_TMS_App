"""clinical_gui -- the window wired to a synthetic data frame and enrolment log.

Behavioural, like the other GUI tests: a real ``ClinicalApp`` is built
against a live Tk root and its widget tree inspected. The background work
(loading, generating graphs, writing the PDF) is run synchronously here so
the assertions do not race and no thread calls ``after`` with no mainloop
running. Skips when Tk cannot open a display.
"""

from __future__ import annotations

import pytest

openpyxl = pytest.importorskip("openpyxl")
pypdf = pytest.importorskip("pypdf")
ctk = pytest.importorskip("customtkinter")

from clinical import settings as cs
from tests._clinical_fixtures import write_world


def _synchronous_generate_async(self, entry):
    """Generate on the calling thread; same callbacks, no thread, no ``after``."""
    try:
        result = self._controller.generate_figure(entry.graph_type, entry.measure, match_by=entry.match_by)
    except Exception as exc:  # the parent routes failures to _on_gen_error
        self._on_gen_error(entry.key, str(exc))
        return
    self._on_gen_success(entry.key, result)


def _synchronous_run(self, work, on_done):
    try:
        result = work()
    except Exception as exc:
        self._on_error(exc)
        return
    on_done(result)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    return write_world(tmp_path_factory.mktemp("clinical_world"))


@pytest.fixture(scope="module")
def app(world):
    """A real ClinicalApp with settings pointed at the synthetic world."""
    from clinical_gui.app import ClinicalApp
    from clinical_gui.graphs_panel import ClinicalGraphsPanel

    # Module scope means the autouse settings isolation is not in effect here,
    # so isolate by hand: the clinical settings file goes under the world dir.
    original = cs._SETTINGS_FILE
    cs._SETTINGS_FILE = world["csv"].parent / "settings.json"
    cs.save_settings(**{
        cs.KEY_CSV_PATH: str(world["csv"]),
        cs.KEY_ROSTER_PATH: str(world["roster"]),
        cs.KEY_EXPORT_DIR: str(world["export"]),
    })
    patched = {
        (ClinicalGraphsPanel, "_generate_async"): _synchronous_generate_async,
        (ClinicalApp, "_run_in_thread"): _synchronous_run,
    }
    saved = {(cls, name): getattr(cls, name) for (cls, name) in patched}
    for (cls, name), func in patched.items():
        setattr(cls, name, func)
    try:
        instance = ClinicalApp(autoload=False)
    except Exception as exc:  # pragma: no cover - headless CI
        for (cls, name), func in saved.items():
            setattr(cls, name, func)
        cs._SETTINGS_FILE = original
        pytest.skip(f"no display available: {exc}")
    instance.update()
    instance.update_idletasks()
    yield instance
    try:
        instance.destroy()
    finally:
        for (cls, name), func in saved.items():
            setattr(cls, name, func)
        cs._SETTINGS_FILE = original


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


def _labels(widget):
    return [w.cget("text") for w in _walk(widget) if isinstance(w, ctk.CTkLabel)]


def _buttons(widget):
    return [w for w in _walk(widget) if isinstance(w, ctk.CTkButton)]


def _checkboxes(widget):
    return [w for w in _walk(widget) if isinstance(w, ctk.CTkCheckBox)]


def _is_inside(widget, container):
    w = widget
    while w is not None:
        if w is container:
            return True
        w = w.master
    return False


# -- shape ---------------------------------------------------------------------

def test_a_configured_app_opens_on_the_report_tab(app):
    assert app._tabs.get() == "Report"
    assert app.title() == "SNBR Clinical Reports"


def test_the_graphs_page_is_the_analysis_apps_page_without_the_lab_controls(app):
    page = app._graphs
    texts = [cb.cget("text") for cb in _checkboxes(page)]
    assert "Select All" in texts
    assert "Save as default" not in texts
    assert not any("individual pulses" in t for t in texts)
    assert not any("Pulse" in t or "pulse" in t for t in _labels(page))
    # Every registry graph is offered, grouped as on the analysis app's page.
    from gui.visualization_panel import GRAPH_REGISTRY
    assert set(page._check_vars) == {e.key for e in GRAPH_REGISTRY}
    assert "Waveform Profiles" in _labels(page) and "Cohort Comparisons" in _labels(page)


def test_the_footer_holds_the_export_row_and_no_wizard_buttons(app):
    names = [b.cget("text") for b in _buttons(app._report_footer)]
    assert "Export report (PDF)" in names and "Browse" in names
    assert "Next" not in names and "Back" not in names
    assert app._graphs._next_page_btn.cget("text") == "Export report (PDF)"
    assert _is_inside(app._graphs._next_page_btn, app._report_footer)
    assert not app._graphs._open_folder_btn.winfo_ismapped(), "nothing exported yet"


def test_no_calendar_anywhere(app):
    assert not any(type(w).__name__ == "Calendar" for w in _walk(app))


# -- loading and searching ----------------------------------------------------------

def test_load_lists_everyone_and_says_so(app):
    app._on_load()
    app.update_idletasks()
    assert app._status_var.get().startswith("Loaded 10 participant(s) with visits and 1 enrolled without data.")
    rows = [b.cget("text") for b in _buttons(app._results_frame)]
    assert len(rows) == 11
    assert rows[0].startswith("Ann Smith\nMRN 7654321 · SNBR-003 · 1 visit")
    assert any(r.startswith("Jane Doe\nMRN 1234567 · SNBR-080 · 2 visits") for r in rows)
    assert any(r.startswith("Never Tested\nMRN 9999999 · SNBR-099 · no data") for r in rows)
    assert any(r.startswith("(name not in the enrolment log)\nno MRN · SNBR-010") for r in rows)


@pytest.mark.parametrize("query, expected", [
    ("doe", ["Jane Doe"]),
    ("1234", ["Jane Doe"]),
    ("snbr-081", ["José Müller"]),
    ("müller", ["José Müller"]),
    ("3", ["Ann Smith", "Bob Jones", "(name not in the enrolment log)"]),
])
def test_typing_filters_the_list(app, query, expected):
    app._query.set(query)
    app.update_idletasks()
    rows = [b.cget("text").split("\n")[0] for b in _buttons(app._results_frame)]
    assert rows == expected


def test_no_match_says_so(app):
    app._query.set("zzz")
    app.update_idletasks()
    assert "No patient matches." in _labels(app._results_frame)
    assert _buttons(app._results_frame) == []


# -- picking a patient and a visit ---------------------------------------------------

def test_picking_a_patient_selects_the_latest_visit_and_fills_the_card(app):
    app._query.set("jane doe")
    app.update_idletasks()
    [row] = _buttons(app._results_frame)
    row.invoke()
    app.update_idletasks()

    visits = [b.cget("text") for b in _buttons(app._visits_frame)]
    assert visits == ["18/08/2026   (latest)", "22/04/2024"]
    assert app._selected_date.strftime("%d/%m/%Y") == "18/08/2026"
    assert app._controller.get_selected_participant()[0] == 80
    card = _labels(app._card)
    assert "Jane Doe" in card and "1234567" in card and "SNBR-080" in card and "Patient" in card
    assert app._caveat.cget("text") == ""
    assert "visit 18/08/2026" in app._status_var.get()
    # The graphs page refreshed for the visit: available graphs ticked, first one drawn.
    page = app._graphs
    assert page._available_keys, "no graph available for the synthetic visit"
    assert all(page._check_vars[k].get() for k in page._available_keys)
    assert page._nav_list and page._nav_list[0].figure is not None
    assert page._current_canvas is not None


def test_picking_the_other_visit_moves_the_selection(app):
    older = next(b for d, b in app._visit_buttons if d.strftime("%d/%m/%Y") == "22/04/2024")
    older.invoke()
    app.update_idletasks()
    assert app._controller.get_selected_participant()[1].strftime("%d/%m/%Y") == "22/04/2024"
    assert older.cget("fg_color") != "transparent"


def test_an_enrolled_patient_with_no_data_cannot_make_a_report(app):
    app._query.set("never tested")
    app.update_idletasks()
    [row] = _buttons(app._results_frame)
    row.invoke()
    app.update_idletasks()
    assert "No visits in the data frame." in _labels(app._visits_frame)
    assert "no report can be made" in app._caveat.cget("text")
    assert "enrolled but has no visits" in app._status_var.get()
    assert app._controller.get_selected_participant() == (None, None)
    page = app._graphs
    assert page._available_keys == set()
    assert all(cb.cget("state") == "disabled" for k, cb in page._check_widgets.items())


# -- export --------------------------------------------------------------------

def test_export_writes_the_identified_report_and_offers_its_folder(app, world):
    app._query.set("jane doe")
    app.update_idletasks()
    [row] = _buttons(app._results_frame)
    row.invoke()
    app.update_idletasks()
    page = app._graphs
    # Two graphs are enough to prove the path; the full set is the default.
    # They are generated here rather than by the export step: the page's
    # collect step runs the missing ones on a thread, which has no mainloop
    # to come back to in a test (see CLAUDE.md on stubbing the worker).
    page._select_all_var.set(False)
    page._on_select_all()
    from gui.visualization_panel import GRAPH_REGISTRY
    for key in ("profile__t_sici", "visit_table"):
        page._check_vars[key].set(True)
        entry = next(e for e in GRAPH_REGISTRY if e.key == key)
        page._cache_result(key, app._controller.generate_figure(
            entry.graph_type, entry.measure, match_by=entry.match_by,
        ))
    page._rebuild_nav_list()

    page._next_page_btn.invoke()
    app.update_idletasks()

    expected = world["export"] / "Jane_Doe_1234567_20260818.pdf"
    assert expected.is_file()
    assert page._status_var.get().startswith(f"Report written: {expected}")
    assert app._status_var.get().startswith("Report written:")
    assert page._open_folder_btn.winfo_ismapped()
    assert page._next_page_btn.cget("state") == "normal"
    reader = pypdf.PdfReader(str(expected))
    assert len(reader.pages) == 2, "cover + one half-page body page holding the two graphs"
    cover = reader.pages[0].extract_text()
    assert "PATIENT IDENTIFICATION" in cover and "Jane Doe" in cover and "1234567" in cover
    assert app._controller.get_report_figures(), "the ReportItems the page collected"


def test_export_with_nothing_ticked_is_refused_in_place(app):
    page = app._graphs
    page._select_all_var.set(False)
    page._on_select_all()
    page._next_page_btn.invoke()
    assert page._status_var.get() == "Please select at least one graph."


# -- settings --------------------------------------------------------------------

def test_settings_tab_has_the_two_inputs_and_the_export_folder_only(app):
    assert set(app._setting_vars) == {
        "csv_path", "roster_path", "roster_sheet", "col_patient_id", "col_patient_name",
        "col_mrn", "export_dir",
    }
    texts = " ".join(_labels(app._tabs.tab("Settings"))).lower()
    assert "mem" not in texts.split() and "redcap" not in texts and "ledger" not in texts


def test_unconfigured_app_opens_on_settings(world):
    original = cs._SETTINGS_FILE
    cs._SETTINGS_FILE = world["csv"].parent / "empty_settings.json"
    try:
        from clinical_gui.app import ClinicalApp
        try:
            instance = ClinicalApp(autoload=False)
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"no display available: {exc}")
        try:
            instance.update_idletasks()
            assert instance._tabs.get() == "Settings"
            assert "Fill in the settings first" in instance._status_var.get()
        finally:
            instance.destroy()
    finally:
        cs._SETTINGS_FILE = original
