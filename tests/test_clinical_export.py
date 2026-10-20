"""clinical/export.py and clinical_gui/controller.py -- the identified report.

The controller is driven exactly as the window drives it: load, search,
select a visit, build the figures the graphs page would build, export. The
PDF is then opened with pypdf and its cover read back, so what is asserted
is the report a clinician would receive, not a code path.
"""

from __future__ import annotations

from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

openpyxl = pytest.importorskip("openpyxl")
pypdf = pytest.importorskip("pypdf")

from clinical import settings as cs
from clinical.directory import Participant
from clinical.export import identified_report_filename, resolve_report_path
from dispatch.identity import Identity, ParticipantKey
from gui.visualization_panel import GRAPH_REGISTRY
from reports.captions import caption_for
from reports.pdf_layout import ReportItem
from tests._clinical_fixtures import write_world

VISIT = datetime(2026, 8, 18)


def _participant(name="Jane Doe", mrn="1234567", *, identity=True, study="SNBR"):
    key = ParticipantKey(study, 80)
    ident = Identity(key=key, patient_id_raw="AA-SNBR-080", name=name, mrn=mrn) if identity else None
    reason = "" if (ident and ident.identifying) else "not in the roster"
    return Participant(key=key, identity=ident, unresolved_reason=reason, visits=(VISIT,))


# -- naming --------------------------------------------------------------------

def test_identified_name_is_name_mrn_and_visit():
    assert identified_report_filename(_participant(), VISIT) == "Jane_Doe_1234567_20260818.pdf"


def test_a_missing_field_is_simply_left_out():
    assert identified_report_filename(_participant(mrn=""), VISIT) == "Jane_Doe_20260818.pdf"
    assert identified_report_filename(_participant(name=""), VISIT) == "1234567_20260818.pdf"


def test_an_unidentified_report_keeps_the_de_identified_name():
    assert identified_report_filename(_participant(identity=False), VISIT) == "report_SNBR_080_20260818.pdf"
    assert identified_report_filename(_participant(name="", mrn=""), VISIT) == "report_SNBR_080_20260818.pdf"


def test_an_automatic_name_never_overwrites(tmp_path):
    first = resolve_report_path(_participant(), VISIT, tmp_path)
    assert first == tmp_path / "Jane_Doe_1234567_20260818.pdf"
    first.write_bytes(b"x")
    assert resolve_report_path(_participant(), VISIT, tmp_path) == tmp_path / "Jane_Doe_1234567_20260818_2.pdf"


def test_a_typed_name_gets_the_analysis_apps_suffix_and_extension(tmp_path):
    assert resolve_report_path(_participant(), VISIT, tmp_path, "for Dr A") == (
        tmp_path / "for Dr A_SNBR_ID80_20260818.pdf"
    )
    assert resolve_report_path(_participant(), VISIT, tmp_path, "x.pdf").name == "x_SNBR_ID80_20260818.pdf"
    assert resolve_report_path(_participant(), VISIT, tmp_path, "x_SNBR_ID80_20260818").name == (
        "x_SNBR_ID80_20260818.pdf"
    ), "an already-suffixed name is not suffixed twice"


# -- the controller --------------------------------------------------------------

@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


@pytest.fixture
def world(tmp_path):
    return write_world(tmp_path / "world")


@pytest.fixture
def controller(world):
    from clinical_gui.controller import ClinicalController

    cs.save_settings(**{
        cs.KEY_CSV_PATH: str(world["csv"]),
        cs.KEY_ROSTER_PATH: str(world["roster"]),
        cs.KEY_EXPORT_DIR: str(world["export"]),
    })
    c = ClinicalController()
    c.load()
    return c


def _entry(key):
    return next(e for e in GRAPH_REGISTRY if e.key == key)


def _items_for(controller, keys=("profile__t_sici",)):
    """What the graphs page hands over: the header plus one item per figure."""
    items = [ReportItem(figure=controller.build_header_figure(), caption=None, section_key="summary")]
    for key in keys:
        e = _entry(key)
        figs, _axes, data = controller.generate_figure(e.graph_type, e.measure, match_by=e.match_by)
        fig = figs[0] if isinstance(figs, list) else figs
        items.append(ReportItem(
            figure=fig, caption=caption_for(e.graph_type, e.measure, data, None), section_key=key,
        ))
    return items


def _cover_text(path) -> str:
    return pypdf.PdfReader(str(path)).pages[0].extract_text()


def test_loading_needs_both_inputs(tmp_path):
    from clinical_gui.controller import ClinicalController

    c = ClinicalController()
    assert c.missing_configuration() == ["Archive CSV (full data frame)", "Enrolment workbook"]
    with pytest.raises(ValueError, match="Fill in the settings"):
        c.load()


def test_load_joins_and_reports(controller):
    assert controller.load_summary() == "Loaded 10 participant(s) with visits and 1 enrolled without data."
    [issue] = controller.issues_lines()
    assert issue.startswith("6 participant(s) with visits are not in the enrolment log")
    assert controller.get_dataframe() is not None


def test_select_visit_seeds_the_recording_targets(controller):
    [jane] = controller.search("jane doe")
    dates = controller.visit_dates(jane)
    assert dates == [datetime(2026, 8, 18), datetime(2024, 4, 22)], "newest first"
    controller.select_visit(jane, dates[0])
    assert controller.get_selected_participant() == (80, dates[0])
    assert controller.get_selected_targets() == ["Right FDI"]
    assert controller.get_selected_cortex() is None
    with pytest.raises(ValueError, match="has no visit on"):
        controller.select_visit(jane, datetime(2020, 1, 1))


def test_every_available_graph_is_ticked_by_default(controller):
    """The person opening this app wants the report, not forty tick boxes."""
    assert controller.get_selected_graphs_default() == [e.key for e in GRAPH_REGISTRY]
    controller.save_selected_graphs_default(["visit_table", "profile__t_sici"])
    assert controller.get_selected_graphs_default() == ["visit_table", "profile__t_sici"], "registry order"


def test_the_pulse_overlay_is_never_offered(controller):
    assert controller.get_pulse_variability_default() is False
    assert controller.pulse_overlay_note() == ""


def test_the_export_folder_is_the_saved_folder_even_before_it_exists(controller, world):
    assert not world["export"].exists()
    assert controller.default_export_folder("pdf") == str(world["export"])
    assert controller.default_export_folder("graph") == str(world["export"])
    assert controller.get_default_export_paths() == {"csv": str(world["export"]), "pdf": str(world["export"])}


def test_export_writes_an_identified_pdf_into_the_export_folder(controller, world):
    [jane] = controller.search("jane doe")
    controller.select_visit(jane, jane.latest_visit)
    controller.set_report_figures(_items_for(controller))

    result = controller.export_report()

    assert result.path == world["export"] / "Jane_Doe_1234567_20260818.pdf"
    assert result.identified and not result.partial and not result.overlaps
    text = _cover_text(result.path)
    assert "PATIENT IDENTIFICATION" in text and "Jane Doe" in text and "1234567" in text
    assert "SNBR-080" in text and "18/08/2026" in text
    assert len(pypdf.PdfReader(str(result.path)).pages) == 2
    assert controller.get_last_exported_pdf() == str(result.path)
    assert controller.last_export is result


def test_a_second_export_does_not_overwrite_the_first(controller):
    [jane] = controller.search("jane doe")
    controller.select_visit(jane, jane.latest_visit)
    controller.set_report_figures(_items_for(controller))
    first = controller.export_report().path
    second = controller.export_report().path
    assert first.exists() and second.exists() and first != second
    assert second.name == "Jane_Doe_1234567_20260818_2.pdf"


def test_a_typed_folder_and_name_are_honoured(controller, tmp_path):
    [jane] = controller.search("jane doe")
    controller.select_visit(jane, jane.latest_visit)
    controller.set_report_figures(_items_for(controller))
    result = controller.export_report(str(tmp_path / "elsewhere"), "for Dr A")
    assert result.path == tmp_path / "elsewhere" / "for Dr A_SNBR_ID80_20260818.pdf"
    assert result.path.is_file()


def test_an_incomplete_identity_is_stamped_with_what_the_log_has(controller):
    [jose] = controller.search("jose")
    controller.select_visit(jose, jose.latest_visit)
    controller.set_report_figures(_items_for(controller, keys=()))
    result = controller.export_report()
    assert result.path.name == "José_Müller_20260201.pdf"
    assert result.identified and result.partial
    text = _cover_text(result.path)
    assert "PATIENT IDENTIFICATION (INCOMPLETE)" in text
    assert "not recorded in the enrolment log" in text


def test_an_unidentified_participant_gets_the_unresolved_box_and_name(controller):
    [p] = controller.search("snbr-010")
    assert p.identity is None
    controller.select_visit(p, p.latest_visit)
    controller.set_report_figures(_items_for(controller, keys=()))
    result = controller.export_report()
    assert result.path.name == "report_SNBR_010_20260601.pdf"
    assert not result.identified
    assert result.unresolved_reason == "SNBR-010 is not in the roster"
    assert "IDENTITY NOT RESOLVED" in _cover_text(result.path)


def test_export_refuses_without_a_selection_or_figures(controller):
    with pytest.raises(ValueError, match="Choose a patient"):
        controller.export_report()
    [jane] = controller.search("jane doe")
    controller.select_visit(jane, jane.latest_visit)
    with pytest.raises(ValueError, match="No figures"):
        controller.export_report()


def test_clear_selection_forgets_the_visit(controller):
    [jane] = controller.search("jane doe")
    controller.select_visit(jane, jane.latest_visit)
    controller.clear_selection()
    assert controller.selected_visit() == (None, None)
    assert controller.get_selected_participant() == (None, None)
    assert controller.get_report_figures() == []


def test_the_analysis_apps_settings_are_never_written(controller):
    """This app has its own file; the one the lab app keeps must stay untouched."""
    from core import user_settings

    [jane] = controller.search("jane doe")
    controller.select_visit(jane, jane.latest_visit)
    controller.set_report_figures(_items_for(controller))
    controller.export_report()
    controller.save_selected_graphs_default(["visit_table"])
    assert not user_settings._SETTINGS_FILE.exists()
    assert cs._SETTINGS_FILE.exists()


def test_caveats_describe_each_identity_state(controller):
    [jane] = controller.search("jane doe")
    [jose] = controller.search("jose")
    [never] = controller.search("never tested")
    [p10] = controller.search("snbr-010")
    assert controller.caveat_for(jane) == ""
    assert "Incomplete identification" in controller.caveat_for(jose)
    assert "no report can be made" in controller.caveat_for(never)
    assert "Identity not resolved" in controller.caveat_for(p10)
    assert controller.caveat_for(None) == ""


def test_identity_lines_for_the_card(controller):
    [jane] = controller.search("jane doe")
    lines = dict(controller.identity_lines(jane))
    assert lines["Patient name"] == "Jane Doe"
    assert lines["MRN"] == "1234567"
    assert lines["Study ID"] == "SNBR-080"
    assert lines["Patient type"] == "Patient"
    assert lines["Visits"] == "2"
    assert lines["First visit"] == "22/04/2024" and lines["Latest visit"] == "18/08/2026"
    [bob] = controller.search("bob jones")
    assert dict(controller.identity_lines(bob))["Visits"] == "1 (05/03/2026)"
    [never] = controller.search("never tested")
    assert dict(controller.identity_lines(never))["Visits"] == "none in the data frame"
    assert controller.identity_lines(None) == []
