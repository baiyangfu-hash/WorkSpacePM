"""Who is at the keyboard, without ever crashing on a stripped environment (D-197).

``getpass.getuser()`` reads LOGNAME, USER, LNAME, USERNAME and then falls back to the ``pwd`` module.  On Windows
there is no ``pwd``, so a child process whose environment lost all four names dies with
``ModuleNotFoundError: No module named 'pwd'`` (an ImportError, which ``except OSError`` does not catch).
"""

from __future__ import annotations

import getpass
import os

UNKNOWN_USER = "unknown"


def current_user_name(default: str = UNKNOWN_USER) -> str:
    """The login name, or ``default`` when the platform cannot tell (no env name and no ``pwd`` / no console)."""
    try:
        name = getpass.getuser()
    except (ImportError, KeyError, OSError):
        name = ""
    if not name and hasattr(os, "getlogin"):
        try:
            name = os.getlogin()
        except OSError:
            name = ""
    return name or default
