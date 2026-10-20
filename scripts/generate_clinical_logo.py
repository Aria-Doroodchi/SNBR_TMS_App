"""Render the SNBR Clinical Reports mark to PNG and ICO.

Standalone developer utility -- not imported by the application. Third of the
family after ``scripts/generate_logo.py`` (the coil) and
``scripts/generate_dispatch_logo.py`` (the envelope): same 64x64 user units
(y increasing downward), same palette, same round caps and joins, same
matplotlib rasteriser, so the three executables read as one set in a taskbar.

The silhouette is what has to survive at 16px, and it is a different one
again: a **portrait page with a folded corner** -- the report itself, which
is what this app exists to hand a clinician -- carrying the MEP trace across
its middle. The full cut adds an identity line under the fold, a small disc
and a rule like a name field on a form: the page is *identified*. The small
cut drops that line and uses a plainer trace and a heavier stroke, as the
other two marks do, so 16px stays a clean page.

    .venv312/Scripts/python.exe scripts/generate_clinical_logo.py
    .venv312/Scripts/python.exe scripts/generate_clinical_logo.py --preview

Writing to icons/logo_clinical/ keeps it clear of the other two; the
PyInstaller specs bundle the whole icons/ tree, so it rides along without a
spec change.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

OUT_DIR = Path(__file__).resolve().parent.parent / "icons" / "logo_clinical"

VIEWBOX = 64.0
PNG_SIZES = (16, 32, 48, 64, 128, 256, 512, 1024)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

# Below this the identity line and the trace's small deflections fall under
# a pixel and turn to mush, so the plain cut is used instead. Same cutoff as
# the other two marks.
SMALL_SIZE_CUTOFF = 32

# Identical to the other generators -- the family is the palette.
LIGHT = {"ink": "#0F2E52", "accent": "#12A594"}
DARK = {"ink": "#E8EEF6", "accent": "#2DD4BF"}

# Page outline: a portrait sheet whose top-right corner is cut off by the
# fold. Drawn as one closed polyline so the round joins radius the corners.
PAGE = [(16, 6), (40, 6), (50, 16), (50, 58), (16, 58), (16, 6)]
# The fold itself: the turned-down corner, a small closed triangle.
FOLD = [(40, 6), (40, 16), (50, 16)]

# Primary cut: the MEP trace across the lower half of the page (the same
# spike-and-recover shape the coil carries), plus the identity line under the
# fold -- a disc for the person and a rule for the name.
FULL = {
    "stroke": 3.4,
    "page": PAGE,
    "fold": FOLD,
    "trace": [(21, 41), (28, 41), (30, 44), (33, 29), (37, 51), (40, 41), (45, 41)],
    "id_disc": (24.5, 22.5, 2.6),       # cx, cy, radius
    "id_rule": [(31, 22.5), (44, 22.5)],
}
# Small cut: page and fold only with a plainer trace and a heavier stroke.
SMALL = {
    "stroke": 5.0,
    "page": [(17, 7), (39, 7), (49, 17), (49, 57), (17, 57), (17, 7)],
    "fold": [(39, 7), (39, 17), (49, 17)],
    "trace": [(22, 40), (29, 40), (33, 27), (37, 50), (40, 40), (44, 40)],
    "id_disc": None,
    "id_rule": None,
}


def render(size: int, cut: dict, palette: dict[str, str], dpi: int = 100) -> Image.Image:
    """Return an RGBA image of the mark at ``size`` x ``size`` pixels."""
    fig = plt.figure(figsize=(size / dpi, size / dpi), dpi=dpi)
    fig.patch.set_alpha(0.0)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, VIEWBOX)
    ax.set_ylim(VIEWBOX, 0)  # SVG orientation: y grows downward
    ax.set_axis_off()
    ax.patch.set_alpha(0.0)

    width = cut["stroke"] * (size / VIEWBOX) * 72.0 / dpi
    line = dict(solid_capstyle="round", solid_joinstyle="round", linewidth=width)
    ax.plot(*zip(*cut["page"]), color=palette["ink"], **line)
    ax.plot(*zip(*cut["fold"]), color=palette["ink"], **line)
    if cut["id_disc"] is not None:
        cx, cy, r = cut["id_disc"]
        t = np.linspace(0.0, 2.0 * np.pi, 200)
        ax.fill(cx + r * np.cos(t), cy + r * np.sin(t), color=palette["ink"], linewidth=0)
        ax.plot(*zip(*cut["id_rule"]), color=palette["ink"], **line)
    ax.plot(*zip(*cut["trace"]), color=palette["accent"], **line)

    scratch = OUT_DIR / f"._render_{size}.png"
    fig.savefig(scratch, dpi=dpi, transparent=True)
    plt.close(fig)
    img = Image.open(scratch).convert("RGBA")
    img.load()
    scratch.unlink()
    return img


def render_at(size: int, palette: dict[str, str]) -> Image.Image:
    """Render at ``size``, picking the cut and supersampling the small sizes."""
    cut = SMALL if size <= SMALL_SIZE_CUTOFF else FULL
    scale = 8 if size <= 64 else 1
    img = render(size * scale, cut, palette)
    return img.resize((size, size), Image.LANCZOS) if scale > 1 else img


def preview(path: Path) -> Path:
    """A contact sheet of the real sizes on light and dark, for eyeballing."""
    sizes = (16, 24, 32, 48, 64, 128)
    pad, gap = 24, 20
    width = pad * 2 + sum(sizes) + gap * (len(sizes) - 1)
    row = max(sizes)
    sheet = Image.new("RGBA", (width, pad * 3 + row * 2), (255, 255, 255, 255))
    dark_band = Image.new("RGBA", (width, row + pad), (24, 28, 34, 255))
    sheet.paste(dark_band, (0, pad * 2 + row))
    for band, palette in ((0, LIGHT), (1, DARK)):
        x = pad
        for size in sizes:
            img = render_at(size, palette)
            y = pad + band * (row + pad) + (row - size)
            sheet.paste(img, (x, y), img)
            x += size + gap
    sheet.save(path)
    return path


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if "--preview" in sys.argv:
        # Into the temp dir, not OUT_DIR: the specs bundle icons/ wholesale, so
        # anything left there ships inside the executables.
        import tempfile

        target = Path(tempfile.gettempdir()) / "snbr_clinical_mark_preview.png"
        print(f"wrote {preview(target)}")
        return 0

    for name, palette in (("clinical", LIGHT), ("clinical-dark", DARK)):
        for size in PNG_SIZES:
            render_at(size, palette).save(OUT_DIR / f"{name}-{size}.png")
            print(f"wrote {name}-{size}.png")

    # Windows .ico: each frame rendered with the cut appropriate to its size,
    # rather than downsampling one master (which loses the small sizes).
    frames = [render_at(s, LIGHT) for s in ICO_SIZES]
    frames[-1].save(
        OUT_DIR / "clinical.ico",
        sizes=[(s, s) for s in ICO_SIZES],
        append_images=frames[:-1],
    )
    print("wrote clinical.ico")
    return 0


if __name__ == "__main__":
    sys.exit(main())
