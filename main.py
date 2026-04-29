"""Entry point for the SNBR TMS App."""

import sys
from pathlib import Path

# Ensure the SNBR_TMS_App package is importable when running directly.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from gui.app import TMSApp


def main():
    app = TMSApp()
    app.mainloop()


if __name__ == "__main__":
    main()
