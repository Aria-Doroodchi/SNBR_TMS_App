#!/usr/bin/env bash
# Build the SNBR TMS App as a macOS .app bundle.
#
# Run from either the repository root or the SNBR_TMS_App directory —
# the script resolves paths relative to itself.
set -euo pipefail

# ---------------------------------------------------------------------------
# Resolve paths
# ---------------------------------------------------------------------------
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "${SCRIPT_DIR}/.." && pwd )"
SPEC_FILE="${SCRIPT_DIR}/SNBR_TMS_App_macos.spec"

# Keep macOS outputs completely separate from the Windows build so both can
# coexist on the same repo without clobbering each other:
#   Windows:  build/         dist/         (default PyInstaller paths)
#   macOS:    build_macos/   dist_macos/
DIST_DIR="${PROJECT_DIR}/dist_macos"
WORK_DIR="${PROJECT_DIR}/build_macos"

echo "============================================"
echo " Building SNBR TMS App (macOS)"
echo " Project dir: ${PROJECT_DIR}"
echo "============================================"
echo

# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------
if [[ "$(uname)" != "Darwin" ]]; then
    echo "ERROR: this build script only runs on macOS (detected $(uname))." >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 not found on PATH." >&2
    exit 1
fi

# Confirm Tk is available (missing Tk is the #1 cause of failed Mac builds).
if ! python3 -c "import tkinter; tkinter.Tcl()" >/dev/null 2>&1; then
    cat >&2 <<'EOF'
ERROR: Tk is not available in this Python install.
       Homebrew's python sometimes ships without Tk.
       Either:
         brew install python-tk         (matches your brew python version)
       or install Python from https://www.python.org/downloads/macos/
       which bundles a working Tk.
EOF
    exit 1
fi

# ---------------------------------------------------------------------------
# Install dependencies
# ---------------------------------------------------------------------------
cd "${PROJECT_DIR}"
echo "Installing requirements..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
python3 -m pip install pyinstaller
echo

# ---------------------------------------------------------------------------
# Clean any previous output and build
# ---------------------------------------------------------------------------
echo "Cleaning previous macOS build/dist directories..."
rm -rf "${WORK_DIR}" "${DIST_DIR}"
mkdir -p "${DIST_DIR}"
echo

echo "Running PyInstaller..."
python3 -m PyInstaller \
    --clean --noconfirm \
    --distpath "${DIST_DIR}" \
    --workpath "${WORK_DIR}" \
    "${SPEC_FILE}"
echo

# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
APP_PATH="${DIST_DIR}/SNBR_TMS_App.app"
if [[ -d "${APP_PATH}" ]]; then
    SIZE_H=$(du -sh "${APP_PATH}" | cut -f1)
    echo "============================================"
    echo " Build complete!"
    echo " Output:  ${APP_PATH}"
    echo " Size:    ${SIZE_H}"
    echo ""
    echo " Launch:  open \"${APP_PATH}\""
    echo "============================================"
else
    echo "ERROR: expected bundle not found at ${APP_PATH}" >&2
    exit 1
fi
