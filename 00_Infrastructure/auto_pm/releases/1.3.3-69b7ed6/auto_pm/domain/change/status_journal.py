"""auto_pm.domain.change.status_journal - the append-only record of change-order status transitions.

Every status change of a change order made through ``ChangeService`` (command line, ``pm`` commands, SDK, GUI) appends one
row here, *before* the order's file is written.  The commit hook reads the same rows to tell a real transition from a hand
edit of the §3.4 status line (audit 524, point 3).

The record lives in its own file, ``<control root>/.auto-pm/status_journal.db`` -- not in ``index.db``.  ``index.db`` is a
cache that a rescan may clear (``approval_history`` there has a cascading foreign key); this file has no foreign key, nothing
deletes from it, and no code rebuilds it.  Standard library only (the domain layer imports nothing else).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

JOURNAL_RELATIVE = (".auto-pm", "status_journal.db")
TABLE = "status_journal"
_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      TEXT NOT NULL,
    change_number   TEXT NOT NULL,
    from_status     TEXT NOT NULL DEFAULT '',
    to_status       TEXT NOT NULL,
    approver        TEXT NOT NULL DEFAULT '',
    comment         TEXT NOT NULL DEFAULT '',
    transition_date TEXT NOT NULL
)
"""


def journal_path(control_root: str | Path) -> Path:
    return Path(control_root).joinpath(*JOURNAL_RELATIVE)


def record_transition(
    control_root: str | Path,
    *,
    change_number: str,
    project_id: str,
    from_status: str,
    to_status: str,
    approver: str = "",
    comment: str = "",
) -> None:
    """Append one transition; the folder and the table are created when missing.  Raises on any failure -- the caller stops."""

    path = journal_path(control_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    try:
        connection.execute(_DDL)
        connection.execute(
            f"INSERT INTO {TABLE} (project_id, change_number, from_status, to_status, approver, comment, transition_date) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (project_id, change_number, from_status, to_status, approver, comment, datetime.now().isoformat()),
        )
        connection.commit()
    finally:
        connection.close()


def last_recorded_status(control_root: str | Path, change_number: str, project_id: str = "") -> str | None:
    """The ``to_status`` of the newest row of this order, or None when there is none.

    Read-only: the file is opened ``mode=ro`` and never created.  None covers: no journal file, no table, an unreadable file,
    and an order without rows -- the caller must treat all of them alike, never as approval.
    """

    path = journal_path(control_root)
    if not path.is_file():
        return None
    try:
        connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    except (sqlite3.Error, OSError, ValueError):
        return None
    try:
        row = connection.execute(
            f"SELECT to_status FROM {TABLE} WHERE change_number = ? "
            "AND (? = '' OR project_id = ? OR project_id = '') ORDER BY id DESC LIMIT 1",
            (change_number, project_id, project_id),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        connection.close()
    return str(row[0]) if row else None
