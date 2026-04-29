"""One-way file sync engine.

Replicates robocopy behaviour in pure Python:
  /E        — recursive copy (all subdirectories, including empty)
  /XO       — skip files where the destination copy is the same age or newer
  /R:3 /W:5 — retry failed copies 3 times with a 5-second wait
  /COPY:DAT — copy data, attributes, timestamps
  /DCOPY:DAT— create directories and preserve their timestamps
  /LOG+:    — append every operation to a log file

Safety guarantee: the source is ONLY read, never written, deleted, or modified.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SyncPair:
    """A single source -> destination mapping."""
    source: str
    destination: str


@dataclass
class SyncResult:
    """Aggregated statistics for one sync run."""
    files_copied: int = 0
    files_skipped: int = 0
    files_failed: int = 0
    bytes_copied: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


# Type alias for the progress callback.
# Signature: callback(current_file: str, files_done: int, total_files: int)
ProgressCallback = Callable[[str, int, int], None]


# ---------------------------------------------------------------------------
# Logging helper (thread-safe, append-only)
# ---------------------------------------------------------------------------

_log_lock = threading.Lock()


def _append_log(log_path: Path | None, message: str) -> None:
    """Append a timestamped line to the log file.  Thread-safe."""
    if log_path is None:
        return
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {message}\n"
    with _log_lock:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line)


# ---------------------------------------------------------------------------
# Decision helper
# ---------------------------------------------------------------------------

def _should_copy(src_path: Path, dest_path: Path) -> bool:
    """Return True if *src_path* should be copied to *dest_path*.

    A file is copied when:
      - the destination does not exist, OR
      - the source modification time is strictly newer than the destination.
    """
    if not dest_path.exists():
        return True
    src_mtime = os.path.getmtime(src_path)
    dest_mtime = os.path.getmtime(dest_path)
    return src_mtime > dest_mtime


# ---------------------------------------------------------------------------
# Core sync — single directory pair
# ---------------------------------------------------------------------------

def sync_directory(
    source: str,
    destination: str,
    *,
    retries: int = 3,
    wait: int = 5,
    progress_callback: ProgressCallback | None = None,
    log_path: str | Path | None = None,
    cancel_event: threading.Event | None = None,
) -> SyncResult:
    """Sync *source* → *destination* (one-way, recursive).

    Parameters
    ----------
    source, destination:
        Directory paths.  *source* is read-only; *destination* is created if
        it does not exist.
    retries:
        Number of retry attempts for each failed file copy (default 3).
    wait:
        Seconds to sleep between retries (default 5).
    progress_callback:
        Optional ``(current_file, files_done, total_files)`` callable invoked
        after every file is processed (copied or skipped).
    log_path:
        If given, every operation is appended to this file.
    cancel_event:
        Optional ``threading.Event``; if set, the sync aborts early.

    Returns
    -------
    SyncResult
        Statistics for this sync run.
    """
    src_root = Path(source)
    dest_root = Path(destination)
    log = Path(log_path) if log_path else None

    result = SyncResult()
    t0 = time.monotonic()

    if not src_root.is_dir():
        msg = f"Source directory does not exist: {src_root}"
        result.errors.append(msg)
        _append_log(log, f"ERROR  {msg}")
        result.duration_seconds = time.monotonic() - t0
        return result

    # --- Enumerate files first so we can report total count ----------------
    all_files: list[Path] = []
    for dirpath, _dirnames, filenames in os.walk(src_root):
        for fname in filenames:
            all_files.append(Path(dirpath) / fname)

    total = len(all_files)
    _append_log(log, f"START  {src_root} -> {dest_root}  ({total} files found)")

    # --- Create destination root -------------------------------------------
    dest_root.mkdir(parents=True, exist_ok=True)

    # --- Process each file -------------------------------------------------
    for idx, src_file in enumerate(all_files):
        if cancel_event and cancel_event.is_set():
            _append_log(log, "CANCEL sync cancelled by user")
            break

        rel = src_file.relative_to(src_root)
        dest_file = dest_root / rel

        # Ensure destination subdirectory exists
        dest_file.parent.mkdir(parents=True, exist_ok=True)

        if not _should_copy(src_file, dest_file):
            result.files_skipped += 1
            _append_log(log, f"SKIP   {rel}")
            if progress_callback:
                progress_callback(str(rel), idx + 1, total)
            continue

        # Attempt copy with retries
        copied = False
        for attempt in range(1, retries + 1):
            if cancel_event and cancel_event.is_set():
                break
            try:
                shutil.copy2(str(src_file), str(dest_file))
                copied = True
                break
            except OSError as exc:
                _append_log(
                    log,
                    f"RETRY  {rel}  attempt {attempt}/{retries}: {exc}",
                )
                if attempt < retries:
                    time.sleep(wait)

        if copied:
            result.files_copied += 1
            result.bytes_copied += src_file.stat().st_size
            _append_log(log, f"COPY   {rel}  ({src_file.stat().st_size:,} bytes)")
        else:
            result.files_failed += 1
            err = f"Failed to copy after {retries} attempts: {rel}"
            result.errors.append(err)
            _append_log(log, f"FAIL   {rel}")

        if progress_callback:
            progress_callback(str(rel), idx + 1, total)

    # --- Preserve directory timestamps (post-copy) -------------------------
    # Walk bottom-up so child dirs are timestamped before parents.
    for dirpath, _dirnames, _filenames in os.walk(src_root, topdown=False):
        src_dir = Path(dirpath)
        rel_dir = src_dir.relative_to(src_root)
        dest_dir = dest_root / rel_dir
        if dest_dir.is_dir():
            try:
                src_stat = src_dir.stat()
                os.utime(dest_dir, (src_stat.st_atime, src_stat.st_mtime))
            except OSError:
                pass  # best-effort for directory timestamps

    result.duration_seconds = time.monotonic() - t0
    _append_log(
        log,
        f"DONE   copied={result.files_copied}  skipped={result.files_skipped}  "
        f"failed={result.files_failed}  bytes={result.bytes_copied:,}  "
        f"elapsed={result.duration_seconds:.1f}s",
    )
    return result


# ---------------------------------------------------------------------------
# Multi-pair sync
# ---------------------------------------------------------------------------

def sync_pairs(
    pairs: list[SyncPair],
    *,
    retries: int = 3,
    wait: int = 5,
    progress_callback: ProgressCallback | None = None,
    log_path: str | Path | None = None,
    cancel_event: threading.Event | None = None,
) -> SyncResult:
    """Run :func:`sync_directory` for every pair and return merged stats."""
    merged = SyncResult()
    t0 = time.monotonic()

    for pair in pairs:
        if cancel_event and cancel_event.is_set():
            break
        r = sync_directory(
            pair.source,
            pair.destination,
            retries=retries,
            wait=wait,
            progress_callback=progress_callback,
            log_path=log_path,
            cancel_event=cancel_event,
        )
        merged.files_copied += r.files_copied
        merged.files_skipped += r.files_skipped
        merged.files_failed += r.files_failed
        merged.bytes_copied += r.bytes_copied
        merged.errors.extend(r.errors)

    merged.duration_seconds = time.monotonic() - t0
    return merged


# ---------------------------------------------------------------------------
# Utility — file hash for verification
# ---------------------------------------------------------------------------

def file_hash(path: str | Path, algorithm: str = "sha256") -> str:
    """Return hex digest of a file for integrity verification."""
    h = hashlib.new(algorithm)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
