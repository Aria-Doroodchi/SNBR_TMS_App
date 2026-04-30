"""Run with either:
    python -m scripts.email_test        (from SNBR_TMS_App/)
    python scripts/email_test/__main__.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# When launched as a script (not `-m`), put SNBR_TMS_App/ on sys.path so
# absolute imports like `scripts.email_test.gui` and `gui.theme` resolve.
if __package__ in (None, ""):
    _project_root = Path(__file__).resolve().parents[2]
    if str(_project_root) not in sys.path:
        sys.path.insert(0, str(_project_root))

from scripts.email_test.gui import EmailTestApp


def main() -> None:
    app = EmailTestApp()
    app.mainloop()


if __name__ == "__main__":
    main()
