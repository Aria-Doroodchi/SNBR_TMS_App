"""
Compare freshly-parsed Python TMS DataFrame against REDCap exported data.

Matches records on (record_id, date, cortex) and reports per-column match
rates and per-participant mismatches.

Usage
-----
    python scripts/compare_redcap.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Ensure project root is on path
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from processing.df_builder import build_combined_dataframe
from processing.redcap_mapper import to_redcap_dataframe, REDCAP_COLUMN_ORDER

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MEM_DIR = Path(r"C:\Users\Ali D\Desktop\Claude_App\1_Raw_Data\SNBR_MEM")
CSP_DIR = Path(r"C:\Users\Ali D\Desktop\Claude_App\1_Raw_Data\SNBR_CSP_RAW")
REDCAP_CSV = Path(r"C:\Users\Ali D\Downloads\SNBR_DATA_2026-04-08_1040.csv")
REPORT_PATH = _PROJECT_ROOT / "reports" / "redcap_value_comparison_report.txt"

# REDCap encodes cortex as numeric: 1 = L, 2 = R
RC_CORTEX_MAP = {"1": "L", "2": "R", "1.0": "L", "2.0": "R"}

TOLERANCE = 0.01  # values within this are considered matching


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_py_date(d: str) -> str | None:
    """Convert Python DD/MM/YYYY to YYYY-MM-DD."""
    try:
        return datetime.strptime(str(d).strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return None


def _normalise_cortex(val) -> str | None:
    """Normalise cortex to L/R regardless of source format."""
    s = str(val).strip()
    if s in RC_CORTEX_MAP:
        return RC_CORTEX_MAP[s]
    if s.upper() in ("L", "R"):
        return s.upper()
    return None


# ---------------------------------------------------------------------------
# Main comparison
# ---------------------------------------------------------------------------

def run_comparison() -> str:
    """Run the full comparison and return the report as a string."""
    lines: list[str] = []

    def p(text: str = "") -> None:
        lines.append(text)

    # -- 1. Parse fresh data --------------------------------------------------
    p("Parsing MEM files...")
    py_df = build_combined_dataframe(str(MEM_DIR), str(CSP_DIR))
    py_snbr = py_df[py_df["Study"] == "SNBR"].copy()

    py_snbr["ID"] = pd.to_numeric(py_snbr["ID"], errors="coerce").astype("Int64")
    py_snbr["date_iso"] = py_snbr["Date"].apply(_parse_py_date)
    py_snbr["cortex_norm"] = py_snbr["Stimulated_cortex"].apply(_normalise_cortex)

    py_rc = to_redcap_dataframe(py_snbr)
    py_rc["record_id"] = pd.to_numeric(py_rc["record_id"], errors="coerce").astype("Int64")
    py_rc["date_iso"] = py_snbr["date_iso"].values
    py_rc["cortex_norm"] = py_snbr["cortex_norm"].values

    # -- 2. Load REDCap data --------------------------------------------------
    rc_df = pd.read_csv(REDCAP_CSV, low_memory=False)
    rc_df["record_id"] = pd.to_numeric(rc_df["record_id"], errors="coerce").astype("Int64")
    rc_df["tt_test_date"] = rc_df["tt_test_date"].astype(str).str.strip()
    rc_df["cortex_norm"] = rc_df["cortex"].astype(str).str.strip().apply(_normalise_cortex)

    # -- 3. Match on (ID, date, cortex) ----------------------------------------
    tms_cols = [c for c in REDCAP_COLUMN_ORDER if c in py_rc.columns and c in rc_df.columns]

    col_stats: dict[str, dict[str, int]] = {
        c: {"match": 0, "mismatch": 0, "total": 0, "py_only": 0, "rc_only": 0}
        for c in tms_cols
    }

    mismatches: list[dict] = []
    matched_records = 0
    unmatched_py = 0

    for _, py_row in py_rc.iterrows():
        pid = py_row["record_id"]
        py_date = py_row.get("date_iso", "")
        py_cortex = py_row.get("cortex_norm", "")
        if pd.isna(pid) or not py_date:
            continue

        # Find RC rows matching ID + date + cortex
        mask = (
            (rc_df["record_id"] == pid)
            & (rc_df["tt_test_date"] == py_date)
            & (rc_df["cortex_norm"] == py_cortex)
        )
        rc_match = rc_df[mask]

        if len(rc_match) == 0:
            unmatched_py += 1
            continue

        matched_records += 1
        rc_row = rc_match.iloc[0]

        for col in tms_cols:
            py_val = pd.to_numeric(py_row.get(col), errors="coerce")
            rc_val = pd.to_numeric(rc_row.get(col), errors="coerce")

            py_has = pd.notna(py_val)
            rc_has = pd.notna(rc_val)

            if py_has and rc_has:
                col_stats[col]["total"] += 1
                diff = abs(py_val - rc_val)
                if diff <= TOLERANCE:
                    col_stats[col]["match"] += 1
                else:
                    col_stats[col]["mismatch"] += 1
                    mismatches.append({
                        "record_id": int(pid),
                        "date": py_date,
                        "cortex": py_cortex,
                        "rc_event": rc_row.get("redcap_event_name", ""),
                        "column": col,
                        "python_value": round(float(py_val), 2),
                        "redcap_value": round(float(rc_val), 2),
                        "difference": round(float(py_val - rc_val), 2),
                        "abs_diff": round(float(diff), 2),
                    })
            elif py_has and not rc_has:
                col_stats[col]["py_only"] += 1
            elif rc_has and not py_has:
                col_stats[col]["rc_only"] += 1

    # -- 4. Build report -------------------------------------------------------
    p("=" * 80)
    p("  REDCAP vs PYTHON TMS VALUE COMPARISON REPORT")
    p(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    p(f"  Parser: reads A-SICI from !A-SICIvISI(rel), A-SICF from !A-SICFvISI(rel)")
    p(f"  Matching: (record_id, date, cortex)")
    p("=" * 80)
    p()

    p("1. DATA SUMMARY")
    p("-" * 40)
    p(f"  Python SNBR records:       {len(py_snbr)}")
    p(f"  REDCap total rows:         {len(rc_df)}")
    p(f"  Matched (ID+Date+Cortex):  {matched_records}")
    p(f"  Unmatched Python records:  {unmatched_py}")
    p(f"  Shared TMS columns:        {len(tms_cols)}")
    p()

    # Totals
    total_compared = sum(s["total"] for s in col_stats.values())
    total_match = sum(s["match"] for s in col_stats.values())
    total_mismatch = sum(s["mismatch"] for s in col_stats.values())
    p("2. OVERALL MATCH STATISTICS")
    p("-" * 40)
    p(f"  Total value comparisons:   {total_compared}")
    p(f"  Exact matches (diff <= {TOLERANCE}): {total_match}")
    p(f"  Mismatches:                {total_mismatch}")
    if total_compared > 0:
        p(f"  Overall match rate:        {100 * total_match / total_compared:.1f}%")
    p()

    # Per-column table
    p("3. PER-COLUMN MATCH RATES")
    p("-" * 80)
    header = f"  {'Column':<30s} {'Compared':>8s} {'Match':>6s} {'Diff':>6s} {'Match%':>7s} {'PyOnly':>7s} {'RCOnly':>7s}"
    p(header)
    p("  " + "-" * 76)

    current_group = ""
    for col in tms_cols:
        s = col_stats[col]
        if s["total"] == 0 and s["py_only"] == 0 and s["rc_only"] == 0:
            continue
        # Group header
        if col.startswith("rmt"):
            group = "RMT"
        elif col.startswith("csp_"):
            group = "CSP"
        elif col.startswith("t_sici_p_"):
            group = "T-SICI"
        elif col.startswith("t_sicf_p_"):
            group = "T-SICF"
        elif col.startswith("a_sici_1000_"):
            group = "A-SICI"
        elif col.startswith("a_sicf_"):
            group = "A-SICF"
        else:
            group = "Other"

        if group != current_group:
            p(f"  [{group}]")
            current_group = group

        pct = f"{100 * s['match'] / s['total']:.1f}%" if s["total"] > 0 else "N/A"
        p(f"  {col:<30s} {s['total']:>8d} {s['match']:>6d} {s['mismatch']:>6d} {pct:>7s} {s['py_only']:>7d} {s['rc_only']:>7d}")

    p()

    # Mismatch details
    if mismatches:
        mm_df = pd.DataFrame(mismatches).sort_values(["record_id", "date", "cortex", "column"])

        # Categorise
        placeholder = mm_df[mm_df["redcap_value"].abs() <= 1.0]
        large = mm_df[(mm_df["abs_diff"] > 20) & (mm_df["redcap_value"].abs() > 1.0)]
        small = mm_df[(mm_df["abs_diff"] > 1.0) & (mm_df["abs_diff"] <= 20) & (mm_df["redcap_value"].abs() > 1.0)]
        rounding = mm_df[(mm_df["abs_diff"] > TOLERANCE) & (mm_df["abs_diff"] <= 1.0) & (mm_df["redcap_value"].abs() > 1.0)]

        p("4. MISMATCH CATEGORIES")
        p("-" * 40)
        p(f"  Rounding (diff {TOLERANCE}-1.0):     {len(rounding)}")
        p(f"  Small (diff 1.0-20):          {len(small)}")
        p(f"  Large (diff >20):             {len(large)}")
        p(f"  REDCap placeholder (val<=1):  {len(placeholder)}")
        p()

        p("5. MISMATCH DETAILS BY PARTICIPANT")
        p("-" * 80)
        for (pid, date, cortex), group in mm_df.groupby(["record_id", "date", "cortex"]):
            event = group.iloc[0]["rc_event"]
            p(f"  --- ID {pid} | {date} | cortex={cortex} | event={event} ---")
            for _, row in group.iterrows():
                if abs(row["redcap_value"]) <= 1.0:
                    cat = "PLACEHOLDER"
                elif row["abs_diff"] > 20:
                    cat = "LARGE"
                elif row["abs_diff"] <= 1.0:
                    cat = "ROUNDING"
                else:
                    cat = "SMALL"
                p(f"    {row['column']:<30s}  Py={row['python_value']:>10.2f}  RC={row['redcap_value']:>10.2f}  diff={row['difference']:>+10.2f}  [{cat}]")
            p()

        # Summary of affected participants per category
        if len(large) > 0:
            large_pids = sorted(large["record_id"].unique())
            p("6. PARTICIPANTS WITH LARGE DIFFERENCES (>20)")
            p("-" * 40)
            p(f"  Count: {len(large_pids)} participants")
            p(f"  IDs: {', '.join(str(x) for x in large_pids)}")
            p()

            # Check for ratio patterns
            p("  Ratio analysis (Python / REDCap) for large diffs:")
            for pid in large_pids[:10]:
                pid_rows = large[large["record_id"] == pid]
                ratios = []
                for _, r in pid_rows.iterrows():
                    if r["redcap_value"] != 0:
                        ratios.append(r["python_value"] / r["redcap_value"])
                if ratios:
                    mean_ratio = np.mean(ratios)
                    std_ratio = np.std(ratios)
                    p(f"    ID {pid}: mean ratio={mean_ratio:.3f}, std={std_ratio:.3f} ({len(ratios)} values)")
            p()

    else:
        p("4. NO MISMATCHES FOUND")
        p()

    p("=" * 80)
    p("END OF REPORT")
    p("=" * 80)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    report = run_comparison()
    print(report)

    # Write report file
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"\nReport saved to: {REPORT_PATH}")
