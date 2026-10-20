"""Entry point for SNBR Clinical Reports, the clinical collaborators' app."""

import sys
from pathlib import Path

# Ensure the SNBR_TMS_App package is importable when running directly.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from clinical_gui.app import ClinicalApp


def main():
    app = ClinicalApp()
    app.mainloop()


if __name__ == "__main__":
    main()
