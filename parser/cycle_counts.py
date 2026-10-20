"""Number of cycles run for each paired-pulse protocol (T-SICI, A-SICI, T-SICF, A-SICF).

The two SICI counts come from the ``.MEM``: Qtrac writes ``(n=N)`` at the end
of the descriptor line under ``!T-SICIvISI(%RMT)(Parallel)`` and under both
``!A-SICIvISI(rel)`` and ``!A-SICIvISI(abs)``. It is the number of cycles
actually run, not the number planned, and it first appears in March 2022, so
older files simply have none.

The two SICF counts exist **only** in the QtracP per-stimulus Excel export:
the MEM never carries one, and an unfinished SICF run still lists every ISI.
The count is the number of conditioned pulses per ISI, taking the most common
count across the ISIs rather than the largest (one ISI can absorb stray
pulses). A tie goes to the larger count — the run reached that cycle.

Nothing here is persisted in the DataFrame; the REDCap export reads these on
demand. Parsers return plain dicts, never DataFrames.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from parser._common import read_source_lines

CYCLE_MEASURES = ("T_SICI", "A_SICI", "T_SICF", "A_SICF")
MEM_CYCLE_MEASURES = ("T_SICI", "A_SICI")
XLSX_CYCLE_MEASURES = ("T_SICF", "A_SICF")

# Block markers whose descriptor line carries the count, in order of preference.
_MEM_MARKERS = {
    "T_SICI": ("!T-SICIvISI(%RMT)(Parallel)",),
    "A_SICI": ("!A-SICIvISI(rel)", "!A-SICIvISI(abs)"),
}
_COUNT_RE = re.compile(r"\(n=(\d+)\)")

# xlsx_parser.split_phases keys -> our measure names.
_XLSX_PHASE_KEY = {"T_SICF": "t_sicf", "A_SICF": "a_sicf"}


def mem_cycle_counts(lines: list[str]) -> dict[str, int]:
    """``{measure: n}`` for the SICI blocks in *lines* that carry a count."""
    stripped = [line.strip() for line in lines]
    counts: dict[str, int] = {}
    for measure, markers in _MEM_MARKERS.items():
        for marker in markers:
            n = _count_after_marker(stripped, marker)
            if n is not None:
                counts[measure] = n
                break
    return counts


def _count_after_marker(stripped: list[str], marker: str) -> int | None:
    for index, line in enumerate(stripped):
        if line != marker:
            continue
        descriptor = index + 1
        while descriptor < len(stripped) and not stripped[descriptor]:
            descriptor += 1
        if descriptor >= len(stripped) or stripped[descriptor].startswith("!"):
            return None
        match = _COUNT_RE.search(stripped[descriptor])
        return int(match.group(1)) if match else None
    return None


def read_mem_cycle_counts(path: str | Path) -> dict[str, int]:
    """The SICI cycle counts of one ``.MEM`` file; ``{}`` if unreadable or absent."""
    try:
        lines = read_source_lines(Path(path))
    except OSError:
        return {}
    return mem_cycle_counts(lines)


def phase_cycle_counts(phases: dict[str, dict[float, list[dict]]]) -> dict[str, int]:
    """``{measure: n}`` for the SICF phases in ``xlsx_parser.split_phases`` output."""
    counts: dict[str, int] = {}
    for measure, key in _XLSX_PHASE_KEY.items():
        per_isi = [len(pulses) for pulses in (phases.get(key) or {}).values() if pulses]
        if not per_isi:
            continue
        tally = Counter(per_isi)
        counts[measure] = max(tally, key=lambda n: (tally[n], n))
    return counts


def read_xlsx_cycle_counts(path: str | Path) -> dict[str, int]:
    """The SICF cycle counts of one Qtrac per-stimulus export; ``{}`` if unreadable."""
    from parser.xlsx_parser import read_stimulus_workbook, split_phases

    try:
        channels = read_stimulus_workbook(path)
    except Exception:
        return {}
    return phase_cycle_counts(split_phases(channels))
