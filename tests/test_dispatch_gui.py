"""dispatch_gui -- the window wired to a synthetic roster, reports and ledger.

Behavioural, like the other GUI tests: a real ``DispatchApp`` is built against
a live Tk root and its widget tree inspected. The slow backend calls are run
synchronously here (the thread wrappers are one line each) so the assertions
do not race. Skips when Tk cannot open a display.
"""

from __future__ import annotations

from datetime import date

import pytest

openpyxl = pytest.importorskip("openpyxl")
pypdf = pytest.importorskip("pypdf")
ctk = pytest.importorskip("customtkinter")

from dispatch import settings as ds


def _workbook(path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "SNBR enrolment log"
    ws.append(["Patient ID", "Patient Name", "MRN"])
    ws.append(["AA-SNBR-080", "John Smith", "1234567"])
    ws.append(["BB-SNBR-081", "Jane Doe", None])
    ws.append(["CC-SNBR-099", "Never Tested", "9"])
    wb.save(path)


def _pdf(path, label):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(8.5, 11))
    fig.text(0.1, 0.9, label)
    fig.savefig(path, format="pdf")
    plt.close(fig)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    root = tmp_path_factory.mktemp("dispatch_world")
    exports = root / "exports"
    exports.mkdir()
    _workbook(root / "roster.xlsx")
    for name in ("report_SNBR_080_20260818.pdf", "report_SNBR_081_20260818.pdf", "report_SNBR_082_20260818.pdf"):
        _pdf(exports / name, name)
    (exports / "SNBR_080_T-SICI_20260818.pdf").write_bytes(b"%PDF-1.4 not a report")
    return root


@pytest.fixture(scope="module")
def app(world):
    """A real DispatchApp with settings pointed at the synthetic world."""
    # Module scope means the autouse settings isolation is not in effect here,
    # so isolate by hand: the dispatch settings file goes under the world dir.
    original = ds._SETTINGS_FILE
    ds._SETTINGS_FILE = world / "settings.json"
    ds.save_settings(**{
        ds.KEY_ROSTER_PATH: str(world / "roster.xlsx"),
        ds.KEY_REPORTS_DIR: str(world / "exports"),
        ds.KEY_IDENTIFIED_DIR: str(world / "identified"),
        ds.KEY_LEDGER_PATH: str(world / "share" / "ledger.jsonl"),
    })
    try:
        from dispatch_gui.app import DispatchApp
        instance = DispatchApp()
    except Exception as exc:  # pragma: no cover - headless CI
        ds._SETTINGS_FILE = original
        pytest.skip(f"no display available: {exc}")
    instance.update()
    instance.update_idletasks()
    yield instance
    try:
        instance.destroy()
    finally:
        ds._SETTINGS_FILE = original


def _labels(widget):
    out = []
    for child in widget.winfo_children():
        if isinstance(child, ctk.CTkLabel):
            out.append(child.cget("text"))
        out += _labels(child)
    return out


def _buttons(widget):
    out = []
    for child in widget.winfo_children():
        if isinstance(child, ctk.CTkButton):
            out.append(child)
        out += _buttons(child)
    return out


def test_configured_app_opens_on_the_worklist_tab(app):
    assert app._tabs.get() == "Worklist"
    assert app._prepare_btn.cget("state") == "disabled"


def test_load_renders_rows_with_identity_status_and_notes(app):
    worklist = app._controller.load()
    app._apply_worklist(worklist)
    app.update_idletasks()

    texts = _labels(app._table)
    assert "SNBR-080" in texts and "John Smith" in texts and "1234567" in texts
    assert "SNBR-081" in texts and "roster row lacks MRN" in texts
    assert "SNBR-082" in texts and any("not in the roster" in t for t in texts)
    assert texts.count("UNSENT") == 3
    assert "3 unsent, 0 revised, 0 sent, 0 closed" == app._counts_var.get()
    assert app._prepare_btn.cget("state") == "normal"

    issues = app._issues.get("1.0", "end")
    assert "No report exported for SNBR-099 (Never Tested)" in issues
    assert "Not a report, ignored: SNBR_080_T-SICI_20260818.pdf" in issues
    assert len([v for v, _ in app._row_vars if v.get()]) == 3, "proposed rows are ticked by default"


def test_prepare_builds_a_part_card_with_no_email_actions(app):
    app._tick_all(True)
    items = app._selected_items()
    assert len(items) == 3
    batch = app._controller.prepare_batch(items)
    app._apply_batch(batch)
    app.update_idletasks()

    assert len(batch.parts) == 1
    part_texts = _labels(app._parts_frame)
    assert any("Part 1 of 1" in t and "3 report(s)" in t for t in part_texts)
    assert any("John_Smith_1234567_20260818.pdf" in t for t in part_texts)
    # 081's roster row has a name but no MRN: the name is kept, the MRN dropped.
    assert any("Jane_Doe_20260818.pdf" in t and "incomplete identification (roster row lacks MRN)" in t
               for t in part_texts)
    # 082 has no roster row at all, so it keeps its de-identified name.
    assert any("report_SNBR_082_20260818.pdf" in t and "de-identified" in t for t in part_texts)
    names = [b.cget("text") for b in _buttons(app._parts_frame)]
    assert names == [
        "Open batch folder", "Mark all as sent",
        "Open folder", "Mark part as sent",
        "Mark as sent", "Mark as sent", "Mark as sent",
    ]
    # Nothing to paste into an email any more: the batch is the PDFs alone.
    assert [p.name for p in batch.folder.iterdir()] == ["part_1_of_1"]


def _entry_button(app, entry):
    return next(btn for e, btn in app._entry_buttons if e is entry)


def test_one_report_can_be_marked_sent_on_its_own(app):
    batch = app._controller.batch
    first = batch.entries[0]
    app._on_mark_entry(first)
    app.update_idletasks()

    state = app._controller.ledger.state()
    assert state.status(first.item.report) == "sent"
    assert sum(1 for e in batch.entries if state.status(e.item.report) == "sent") == 1
    assert _entry_button(app, first).cget("state") == "disabled"
    assert _entry_button(app, first).cget("text") == "Sent"
    assert all(_entry_button(app, e).cget("state") == "normal" for e in batch.entries[1:])
    assert app._counts_var.get() == "2 unsent, 0 revised, 1 sent, 0 closed"
    assert "1 report(s) recorded as sent" in app._status_var.get()


def test_someone_else_marking_meanwhile_is_refused_not_duplicated(app):
    """The re-read before each write: a report another machine recorded is not
    recorded twice, and the status line says so."""
    from dispatch.ledger import Ledger
    batch = app._controller.batch
    second = batch.entries[1]
    Ledger(app._controller.ledger.path).mark_sent(second.item.report, "other-run", 1, 1)

    app._on_mark_entry(second)
    events, _ = app._controller.ledger.events()
    assert sum(1 for e in events if e["event"] == "sent") == 2
    assert "already marked by someone else" in app._status_var.get()
    assert _entry_button(app, second).cget("state") == "disabled"


def test_mark_all_records_only_what_is_left(app):
    batch = app._controller.batch
    app._on_mark_all()
    app.update_idletasks()

    events, _ = app._controller.ledger.events()
    assert sum(1 for e in events if e["event"] == "sent") == 3, "each report recorded exactly once"
    state = app._controller.ledger.state()
    assert all(state.status(i.report) == "sent" for i in app._controller.worklist.items)
    texts = _labels(app._table)
    assert texts.count("UNSENT") == 0
    assert sum(1 for t in texts if t.startswith("SENT (")) == 3
    assert app._counts_var.get() == "0 unsent, 0 revised, 3 sent, 0 closed"
    assert app._prepare_btn.cget("state") == "disabled"
    assert "Batch: 1 report(s) recorded as sent" in app._status_var.get()
    assert all(btn.cget("state") == "disabled" for _, btn in app._entry_buttons)
    assert all(btn.cget("text") == "Part sent" for _, btn in app._part_buttons)
    assert app._mark_all_btn.cget("state") == "disabled"

    app._on_mark_sent(batch.parts[0])
    assert "already recorded" in app._status_var.get()
    events, _ = app._controller.ledger.events()
    assert sum(1 for e in events if e["event"] == "sent") == 3


def test_a_re_exported_report_shows_as_a_revision(app, world):
    _pdf(world / "exports" / "report_SNBR_080_20260818.pdf", "corrected")
    app._apply_worklist(app._controller.load())
    texts = _labels(app._table)
    assert "REVISION" in texts
    assert any("revised since a version was sent" in t for t in texts)
    assert app._counts_var.get() == "0 unsent, 1 revised, 2 sent, 0 closed"
    assert app._prepare_btn.cget("state") == "normal"


def test_settings_tab_has_no_email_fields(app):
    assert set(app._setting_vars) == set(ds.DEFAULTS)
    texts = " ".join(_labels(app._tabs.tab("Settings"))).lower()
    assert "recipient" not in texts and "subject" not in texts


def test_unconfigured_app_opens_on_settings(world):
    original = ds._SETTINGS_FILE
    ds._SETTINGS_FILE = world / "empty_settings.json"
    try:
        from dispatch_gui.app import DispatchApp
        try:
            instance = DispatchApp()
        except Exception as exc:  # pragma: no cover
            pytest.skip(f"no display available: {exc}")
        try:
            instance.update_idletasks()
            assert instance._tabs.get() == "Settings"
            assert "Fill in the settings first" in instance._status_var.get()
        finally:
            instance.destroy()
    finally:
        ds._SETTINGS_FILE = original
