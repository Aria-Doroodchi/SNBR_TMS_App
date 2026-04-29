"""Shared path constants for the SNBR TMS App."""

import sys
from pathlib import Path

# Detect whether we're running from a PyInstaller bundle or source.
if getattr(sys, "frozen", False):
    # PyInstaller --onedir: sys._MEIPASS is the bundle's internal data dir.
    # The executable sits next to the bundle folder.
    _APP_DIR = Path(sys.executable).resolve().parent
else:
    # Development: SNBR_TMS_App/ is the app directory.
    _APP_DIR = Path(__file__).resolve().parents[1]

# In development the project root is 3 levels above config.py;
# in a frozen build it's the folder containing the executable.
if getattr(sys, "frozen", False):
    PROJECT_ROOT = _APP_DIR
else:
    PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Default data directories — used as initial suggestions only.
# The user always picks their own paths in the GUI.
MEM_DIR = PROJECT_ROOT / "1_Raw_Data" / "SNBR_MEM"
CSP_DIR = PROJECT_ROOT / "1_Raw_Data" / "SNBR_CSP_RAW"
