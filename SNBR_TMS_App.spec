# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for SNBR TMS App (--onedir --windowed)."""

import os
import sys
import customtkinter

block_cipher = None

# Locate customtkinter package data (themes, assets).
ctk_path = os.path.dirname(customtkinter.__file__)

# Locate Python DLLs and VC++ runtime to bundle them explicitly.
_python_dir = os.path.dirname(sys.executable)
_runtime_dlls = []
for _dll in ('python3.dll', 'python312.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'):
    _path = os.path.join(_python_dir, _dll)
    if os.path.isfile(_path):
        _runtime_dlls.append((_path, '.'))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=_runtime_dlls,
    datas=[
        # CustomTkinter theme/assets
        (ctk_path, 'customtkinter/'),
        # User-settings template
        ('core/saved_defaults.json', 'core/'),
        # Institutional letterhead PNGs used on the report cover page
        ('icons', 'icons'),
    ],
    hiddenimports=[
        'matplotlib.backends.backend_tkagg',
        'matplotlib.backends.backend_agg',
        'matplotlib.backends.backend_pdf',
        'tkcalendar',
        'babel.numbers',
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
    [],
    exclude_binaries=True,
    name='SNBR_TMS_App',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,   # --windowed
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SNBR_TMS_App',
)
