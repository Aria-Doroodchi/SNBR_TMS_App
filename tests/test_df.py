"""Build a combined MEM + CSP DataFrame and export it to CSV."""

import sys
from pathlib import Path

# Allow imports from the SNBR_TMS_App package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from processing.df_builder import build_combined_dataframe
from reports.csv_exporter import export_dataframe

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MEM_DIR    = PROJECT_ROOT / "1_Raw_Data" / "SNBR_MEM"
CSP_DIR    = PROJECT_ROOT / "1_Raw_Data" / "SNBR_CSP_RAW"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

df = build_combined_dataframe(MEM_DIR, CSP_DIR)
csv_path = export_dataframe(df, OUTPUT_DIR)

print(f"DataFrame shape: {df.shape}")
print(f"Exported to: {csv_path}")
