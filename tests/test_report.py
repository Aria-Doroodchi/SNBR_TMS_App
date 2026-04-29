"""Load a DataFrame from CSV and generate a participant PDF report."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import MEM_DIR as _DEFAULT_MEM_DIR, CSP_DIR as _DEFAULT_CSP_DIR
from processing.df_builder import load_participant_dataframe
from reports.csv_exporter import find_latest_csv
from reports.pdf_renderer import generate_participant_report

# --- Configuration (edit these) ---
PARTICIPANT_ID = 107                    # SNBR ID to report on
VISIT_DATE = None                       # None = most recent visit; or e.g. "01/04/2025"
SECTIONS = "all"                       # None = default; "all" = everything; or ["summary", "rmt_over_time", ...]
FORCE_REBUILD = False                   # True = rebuild DataFrame even if CSV is current

# --- Directories (override to use custom paths, or leave as defaults) ---
MEM_DIR = _DEFAULT_MEM_DIR              # Folder containing .MEM files
CSP_DIR = _DEFAULT_CSP_DIR              # Folder containing CSP .MEM files
OUTPUT_DIR = Path(__file__).resolve().parent / "output"   # CSV + report output

csv_path = find_latest_csv(OUTPUT_DIR)
df = load_participant_dataframe(PARTICIPANT_ID, MEM_DIR, csv_path, CSP_DIR, force_rebuild=FORCE_REBUILD, export_csv=FORCE_REBUILD, output_dir=OUTPUT_DIR)
pdf_path = generate_participant_report(PARTICIPANT_ID, df, reports_dir=OUTPUT_DIR, included_sections=SECTIONS, mem_date=VISIT_DATE)

print(f"Participant: SNBR-{PARTICIPANT_ID:03d}")
print(f"Report saved to: {pdf_path}")

