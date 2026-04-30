"""Sample letterheaded PDF used by the standalone email tester."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from reports.pdf_layout import LAB_LETTERHEAD_PATH, SUNNYBROOK_LOGO_PATH

PAGE_SIZE = (8.5, 11.0)


def build_sample_pdf(output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=PAGE_SIZE, dpi=200)

    lab_img = mpimg.imread(str(LAB_LETTERHEAD_PATH))
    sb_img = mpimg.imread(str(SUNNYBROOK_LOGO_PATH))

    ax_lab = fig.add_axes((0.05, 0.82, 0.55, 0.13))
    ax_lab.imshow(lab_img)
    ax_lab.axis("off")

    ax_sb = fig.add_axes((0.65, 0.82, 0.30, 0.13))
    ax_sb.imshow(sb_img)
    ax_sb.axis("off")

    fig.text(
        0.5, 0.74,
        "SNBR TMS — Email Permissions Test",
        ha="center", va="center",
        fontsize=18, fontweight="bold",
    )
    fig.text(
        0.5, 0.69,
        f"Generated {date.today().isoformat()}",
        ha="center", va="center",
        fontsize=11,
    )
    fig.text(
        0.1, 0.55,
        "This PDF is a test artifact produced by the standalone email module.\n"
        "It exists to verify that the lab user can attach and send a PDF\n"
        "report through their organizational SMTP server. No clinical data\n"
        "is contained in this document.",
        ha="left", va="top",
        fontsize=12,
    )

    with PdfPages(str(output_path)) as pdf:
        pdf.savefig(fig)
    plt.close(fig)

    return output_path
