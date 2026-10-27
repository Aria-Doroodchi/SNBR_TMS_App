"""Run a Tk root's real ``mainloop`` until a condition holds.

The GUI tests normally swap a window's worker for a synchronous stand-in, so
no thread ever calls ``after`` while nothing runs ``mainloop``. That
stand-in also hides whatever the *real* worker does with the result, which
is where a window can wedge itself busy for good. A test that has to cover
that path runs the genuine thread and lets the loop deliver its callback.
"""

from __future__ import annotations

import time


def run_mainloop_until(root, done, timeout: float = 20.0, poll_ms: int = 25) -> bool:
    """Run *root*'s mainloop until ``done()`` is true or *timeout* passes.

    Returns ``done()`` at exit, so a callback that never lands reads as
    ``False`` rather than as a hung test run.
    """
    deadline = time.monotonic() + timeout

    def check():
        if done() or time.monotonic() > deadline:
            root.quit()
        else:
            root.after(poll_ms, check)

    root.after(poll_ms, check)
    root.mainloop()
    return bool(done())
