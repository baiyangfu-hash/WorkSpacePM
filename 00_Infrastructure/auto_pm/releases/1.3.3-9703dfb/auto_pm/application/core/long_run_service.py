"""Application-layer door to ``main.py long-run``: the command line reaches the process machinery only through here (layer rule TD-SW008-058).

Everything real lives in :mod:`auto_pm.infrastructure.long_run_core`; this module adds nothing but the one read-only listing the command needs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from auto_pm.infrastructure import long_run_core as _core

__all__ = [
    "DEFAULT_TIMEOUT_MINUTES",
    "LongRunError",
    "list_tasks",
    "read_status",
    "run_directory",
    "start",
    "stop",
]

DEFAULT_TIMEOUT_MINUTES = _core.DEFAULT_TIMEOUT_MINUTES
LongRunError = _core.LongRunError
read_status = _core.read_status
run_directory = _core.run_directory
start = _core.start
stop = _core.stop


def list_tasks(control_root: str | Path) -> list[dict[str, Any]]:
    """One row per task under ``.auto-pm/long-run`` (read-only); a record that cannot be read is listed as UNREADABLE, not left out."""

    base = Path(control_root) / _core.RUN_ROOT
    names = sorted(path.name for path in base.iterdir() if path.is_dir()) if base.is_dir() else []
    rows: list[dict[str, Any]] = []
    for task in names:
        try:
            state = _core.read_status(base / task)
            rows.append({"name": task, "state": state.get("state"), "exit_code": state.get("exit_code"), "started_at": state.get("started_at")})
        except _core.LongRunError as error:
            rows.append({"name": task, "state": "UNREADABLE", "error": str(error)})
    return rows
