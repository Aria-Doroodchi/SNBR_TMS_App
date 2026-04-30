"""Password storage via the OS keyring (Windows Credential Manager / DPAPI).

All functions swallow keyring backend failures and return None / no-op so a
misconfigured machine never crashes the GUI. The caller decides how to surface
the absence of a stored password.
"""

from __future__ import annotations

import sys

SERVICE_NAME = "snbr_tms_email"


def keyring_backend_name() -> str:
    """Human-readable name of the OS keyring backend used for password storage."""
    if sys.platform == "darwin":
        return "macOS Keychain"
    if sys.platform.startswith("win"):
        return "Windows Credential Manager"
    return "system keyring"


def _kr():
    """Lazy import of keyring; returns None if unavailable."""
    try:
        import keyring
        return keyring
    except Exception:
        return None


def save_password(username: str, password: str) -> bool:
    if not username or password is None:
        return False
    kr = _kr()
    if kr is None:
        return False
    try:
        kr.set_password(SERVICE_NAME, username, password)
        return True
    except Exception:
        return False


def load_password(username: str) -> str | None:
    if not username:
        return None
    kr = _kr()
    if kr is None:
        return None
    try:
        return kr.get_password(SERVICE_NAME, username)
    except Exception:
        return None


def delete_password(username: str) -> bool:
    if not username:
        return False
    kr = _kr()
    if kr is None:
        return False
    try:
        kr.delete_password(SERVICE_NAME, username)
        return True
    except Exception:
        return False
