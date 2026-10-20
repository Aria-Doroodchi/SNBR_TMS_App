# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for SNBR Clinical Reports -- Windows single-file executable.

The third app (see SNBR_TMS_App.spec and SNBR_Report_Dispatch.spec). Same
``--onefile --windowed`` shape, a different entry point. It reaches the
analysis app's graph pipeline through ``gui.controller``, so pandas,
matplotlib and the TkAgg preview backend are all needed; openpyxl reads the
enrolment workbook and pypdf stamps the cover. No tkcalendar: this app has
no calendar.

Output: ``dist/SNBR_Clinical_Reports.exe``
"""

import os
import sys

import customtkinter

block_cipher = None

# The spec's own directory: PyInstaller injects SPECPATH, but a spec executed
# some other way still has to find the project.
_project_root = globals().get('SPECPATH') or os.getcwd()
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from scripts.build_assets import ensure_icon

# Prepare the mark BEFORE EXE() is constructed. PyInstaller only notices a
# missing icon inside EXE.assemble -- after it has written the executable --
# so a build that discovers it there leaves an un-iconned binary in dist/ and
# exits 1. Regenerated every build so the shipped icon always matches the
# geometry in scripts/generate_clinical_logo.py rather than whatever is on
# disk. Raises BuildAssetError, failing the build, if it cannot be produced.
CLINICAL_ICON = ensure_icon('clinical', regenerate=True)

ctk_path = os.path.dirname(customtkinter.__file__)

_python_dir = os.path.dirname(sys.executable)
_runtime_dlls = []
for _dll in ('python3.dll', 'python312.dll', 'python313.dll', 'python314.dll',
             'vcruntime140.dll', 'vcruntime140_1.dll'):
    _path = os.path.join(_python_dir, _dll)
    if os.path.isfile(_path):
        _runtime_dlls.append((_path, '.'))

a = Analysis(
    ['clinical_main.py'],
    pathex=[],
    binaries=_runtime_dlls,
    datas=[
        (ctk_path, 'customtkinter/'),
        # icons/logo_clinical/ for the *window* icon, which the exe's own
        # embedded icon does not provide: clinical_gui.app._resolve_logo_dir
        # reads it back from sys._MEIPASS/icons/logo_clinical at runtime. The
        # whole tree rides along, keeping this in step with the other specs.
        ('icons', 'icons'),
    ],
    hiddenimports=[
        'matplotlib.backends.backend_tkagg',
        'matplotlib.backends.backend_agg',
        'matplotlib.backends.backend_pdf',
        'pypdf',
        'openpyxl',
        'PIL._tkinter_finder',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pytest', 'IPython', 'notebook', 'sphinx',
        'matplotlib.backends.backend_qt5agg',
        'matplotlib.backends.backend_wxagg',
        'matplotlib.backends.backend_gtk3agg',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SNBR_Clinical_Reports',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # The page mark, not the coil or the envelope: the three .exe files sit
    # in the same dist/ and must be distinguishable in Explorer and the
    # taskbar. Taken from ensure_icon() above rather than written out here, so
    # the path cannot drift from the file the build actually prepared.
    icon=str(CLINICAL_ICON),
)
