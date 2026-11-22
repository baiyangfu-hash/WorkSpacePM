"""Per-control-root storage for detached full-gate attempts."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class GateAttempt:
    id: str
    key: str
    number: int
    backend: str
    state: str
    handle: str
    detail: str
    approval: str


class GateTaskStore:
    def __init__(self, root: Path) -> None:
        self.path = root / ".auto-pm/reports/gate-tasks/ledger.sqlite3"

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                db.execute("""
                    CREATE TABLE IF NOT EXISTS attempts (
                        id TEXT PRIMARY KEY, key TEXT NOT NULL, number INTEGER NOT NULL,
                        backend TEXT NOT NULL, state TEXT NOT NULL, handle TEXT NOT NULL,
                        detail TEXT NOT NULL, approval TEXT NOT NULL,
                        UNIQUE (key, number)
                    )
                """)
                yield db
        finally:
            db.close()

    def latest(self, key: str) -> GateAttempt | None:
        with self._connect() as db:
            return self._latest(db, key)

    @staticmethod
    def _latest(db: sqlite3.Connection, key: str) -> GateAttempt | None:
        row = db.execute(
            "SELECT * FROM attempts WHERE key = ? ORDER BY number DESC LIMIT 1", (key,)
        ).fetchone()
        return GateAttempt(**row) if row else None

    def get(self, attempt_id: str) -> GateAttempt | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM attempts WHERE id = ?", (attempt_id,)).fetchone()
            return GateAttempt(**row) if row else None

    def reserve(
        self, key: str, backend: str, *, previous_id: str = "", approval: str = ""
    ) -> tuple[GateAttempt, bool]:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = self._latest(db, key)
            if previous and (
                previous.id != previous_id
                or previous.state not in {"failed", "stopped", "unavailable"}
            ):
                return previous, False
            if backend == "local":
                active = db.execute(
                    "SELECT id FROM attempts WHERE backend = 'local' AND state IN ('unknown', 'queued', 'running')"
                ).fetchone()
                if active:
                    raise ValueError(f"已有本机全量门禁 {active['id']}，请先查状态")
            # A partial launch may have happened after this transaction commits.
            # Persist uncertainty before calling the external dispatcher.
            attempt_id = uuid4().hex
            number = previous.number + 1 if previous else 1
            db.execute(
                "INSERT INTO attempts VALUES (?, ?, ?, ?, 'unknown', '', '', ?)",
                (attempt_id, key, number, backend, approval),
            )
            return GateAttempt(attempt_id, key, number, backend, "unknown", "", "", approval), True

    def observe(self, attempt: GateAttempt, state: str, handle: str = "", detail: str = "") -> GateAttempt:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                """UPDATE attempts SET state = ?, handle = ?, detail = ?
                   WHERE id = ? AND state = ? AND handle = ?""",
                (state, handle or attempt.handle, detail, attempt.id,
                 attempt.state, attempt.handle),
            )
            row = db.execute("SELECT * FROM attempts WHERE id = ?", (attempt.id,)).fetchone()
            return GateAttempt(**row)
