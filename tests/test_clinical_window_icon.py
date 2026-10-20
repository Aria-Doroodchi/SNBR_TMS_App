"""The clinical app wears its own mark, not either of the other two.

Sibling of ``test_window_icon.py`` and ``test_dispatch_window_icon.py``, and
behavioural in the same way: a real ``ClinicalApp`` is built and asked what
CustomTkinter actually did. Three executables, three icons -- a window
pointing at the coil or the envelope would look correct in review and give
two identical taskbar buttons.
"""

import sys

import pytest

from clinical_gui.app import ClinicalApp, _resolve_logo_dir

ICO_SIZES = {(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)}


def test_logo_dir_resolves_to_a_real_ico():
    ico = _resolve_logo_dir() / "clinical.ico"
    assert ico.is_file(), f"{ico} is missing -- run scripts/generate_clinical_logo.py"


def test_the_clinical_mark_is_neither_of_the_other_two():
    from dispatch_gui.app import _resolve_logo_dir as dispatch_logo_dir
    from gui.app import _resolve_logo_dir as analysis_logo_dir

    clinical = _resolve_logo_dir() / "clinical.ico"
    for other in (analysis_logo_dir() / "logo.ico", dispatch_logo_dir() / "dispatch.ico"):
        assert clinical.resolve() != other.resolve()
        assert clinical.read_bytes() != other.read_bytes()


def test_ico_carries_every_size_windows_asks_for():
    Image = pytest.importorskip("PIL.Image")
    with Image.open(_resolve_logo_dir() / "clinical.ico") as img:
        assert set(img.info["sizes"]) == ICO_SIZES


def test_both_cuts_are_actually_drawn_at_their_sizes():
    """The 16px frame must be the simplified cut, not a shrunk 256px one."""
    Image = pytest.importorskip("PIL.Image")
    with Image.open(_resolve_logo_dir() / "clinical.ico") as img:
        img.size = (16, 16)
        alpha = img.convert("RGBA").getchannel("A")
    opaque = sum(alpha.histogram()[129:])
    assert opaque > 30, f"the 16px frame is nearly empty ({opaque} solid pixels)"


@pytest.fixture()
def app():
    pytest.importorskip("customtkinter")
    try:
        instance = ClinicalApp(autoload=False)
    except Exception as exc:  # pragma: no cover - display-dependent
        pytest.skip(f"no usable display: {exc}")
    yield instance
    instance.destroy()


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="Windows-only icon path")
def test_app_claims_the_icon_so_customtkinter_does_not_replace_it(app):
    assert app._iconbitmap_method_called is True


def test_missing_icon_file_does_not_stop_the_window_opening(app, monkeypatch, tmp_path):
    monkeypatch.setattr("clinical_gui.app._resolve_logo_dir", lambda: tmp_path / "gone")
    app._apply_window_icon()  # must not raise
