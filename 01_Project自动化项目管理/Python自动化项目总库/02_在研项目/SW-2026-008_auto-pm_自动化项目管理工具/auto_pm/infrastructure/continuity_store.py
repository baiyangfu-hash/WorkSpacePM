"""SQLite continuity store, isolated from the rebuildable index database."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from auto_pm.contracts.continuity import WorkItem


class ContinuityStoreError(RuntimeError):
    """Raised when a continuity transaction cannot be completed safely."""


_DDL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    schema_version TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    tool_version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS work_items (
    work_id TEXT PRIMARY KEY,
    subject_project_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    state TEXT NOT NULL,
    owner TEXT NOT NULL,
    read_only INTEGER NOT NULL CHECK (read_only IN (0, 1)),
    authorization_ref TEXT NOT NULL,
    scope_json TEXT NOT NULL,
    scope_hash TEXT NOT NULL,
    source_fingerprint TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS work_relations (
    from_work_id TEXT NOT NULL REFERENCES work_items(work_id),
    to_work_id TEXT NOT NULL REFERENCES work_items(work_id),
    relation TEXT NOT NULL,
    created_event_id TEXT NOT NULL,
    PRIMARY KEY (from_work_id, to_work_id, relation)
);
CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    previous_hash TEXT NOT NULL,
    event_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_work_project_state
ON work_items(subject_project_id, state);
CREATE INDEX IF NOT EXISTS idx_events_aggregate
ON events(aggregate_type, aggregate_id, created_at);
"""


class ContinuityStore:
    """Transactional persistence for Work state and its append-only events."""

    def __init__(self, workspace_root: str | Path, db_path: str | Path | None = None) -> None:
        root = Path(workspace_root).resolve()
        selected = Path(db_path) if db_path is not None else root / ".auto-pm" / "continuity.db"
        self.db_path = selected.resolve()
        try:
            self.db_path.relative_to(root)
        except ValueError as error:
            raise ContinuityStoreError("continuity.db 必须位于工作空间内") from error

    def initialize(self, now: str, tool_version: str) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as conn:
            conn.executescript(_DDL)
            conn.execute(
                "INSERT OR IGNORE INTO schema_meta VALUES ('continuity-store.v1', ?, ?)",
                (now, tool_version),
            )

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def create_work(self, values: dict[str, Any], idempotency_key: str, now: str) -> WorkItem:
        with self._transaction() as conn:
            existing = self._event_by_key(conn, idempotency_key)
            if existing is not None:
                if existing["aggregate_id"] != values["work_id"]:
                    raise ContinuityStoreError("idempotency_key 已用于其他 Work")
                return self._get_work(conn, values["work_id"])
            columns = ",".join(values)
            placeholders = ",".join("?" for _ in values)
            conn.execute(
                f"INSERT INTO work_items ({columns}) VALUES ({placeholders})",
                tuple(values.values()),
            )
            self._append_event(conn, values["work_id"], "WORK_CREATED", values, idempotency_key, now)
            return self._get_work(conn, values["work_id"])

    def transition(
        self,
        work_id: str,
        expected_version: int,
        new_state: str,
        authorization_ref: str,
        idempotency_key: str,
        now: str,
    ) -> WorkItem:
        with self._transaction() as conn:
            existing = self._event_by_key(conn, idempotency_key)
            if existing is not None:
                if existing["aggregate_id"] != work_id:
                    raise ContinuityStoreError("idempotency_key 已用于其他 Work")
                return self._get_work(conn, work_id)
            cursor = conn.execute(
                """UPDATE work_items SET state=?, authorization_ref=?, version=version+1,
                updated_at=? WHERE work_id=? AND version=?""",
                (new_state, authorization_ref, now, work_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise ContinuityStoreError("Work 不存在或版本冲突")
            payload = {"state": new_state, "authorization_ref": authorization_ref}
            self._append_event(conn, work_id, "WORK_TRANSITIONED", payload, idempotency_key, now)
            return self._get_work(conn, work_id)

    def add_relation(
        self,
        from_work_id: str,
        to_work_id: str,
        relation: str,
        event_id: str,
        idempotency_key: str,
        now: str,
    ) -> None:
        with self._transaction() as conn:
            existing = self._event_by_key(conn, idempotency_key)
            if existing is not None:
                if existing["aggregate_id"] != from_work_id:
                    raise ContinuityStoreError("idempotency_key 已用于其他 Work")
                return
            self._get_work(conn, from_work_id)
            self._get_work(conn, to_work_id)
            conn.execute(
                "INSERT INTO work_relations VALUES (?, ?, ?, ?)",
                (from_work_id, to_work_id, relation, event_id),
            )
            self._append_event(
                conn,
                from_work_id,
                "WORK_RELATION_ADDED",
                {"to_work_id": to_work_id, "relation": relation},
                idempotency_key,
                now,
                event_id,
            )

    def get_work(self, work_id: str) -> WorkItem:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return self._get_work(conn, work_id)

    @staticmethod
    def _event_by_key(conn: sqlite3.Connection, key: str) -> sqlite3.Row | None:
        row = conn.execute("SELECT * FROM events WHERE idempotency_key=?", (key,)).fetchone()
        return cast(sqlite3.Row | None, row)

    @staticmethod
    def _get_work(conn: sqlite3.Connection, work_id: str) -> WorkItem:
        row = conn.execute("SELECT * FROM work_items WHERE work_id=?", (work_id,)).fetchone()
        if row is None:
            raise ContinuityStoreError(f"Work 不存在: {work_id}")
        data = dict(row)
        data["read_only"] = bool(data["read_only"])
        data["scope_paths"] = tuple(json.loads(data.pop("scope_json")))
        return WorkItem.model_validate(data)

    @staticmethod
    def _append_event(
        conn: sqlite3.Connection,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
        idempotency_key: str,
        now: str,
        event_id: str = "",
    ) -> None:
        previous = conn.execute("SELECT event_hash FROM events ORDER BY rowid DESC LIMIT 1").fetchone()
        previous_hash = str(previous[0]) if previous else ""
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        event_hash = hashlib.sha256(
            f"{previous_hash}|{aggregate_id}|{event_type}|{canonical}|{now}".encode()
        ).hexdigest()
        resolved_event_id = event_id or f"EVT-{event_hash[:16].upper()}"
        conn.execute(
            "INSERT INTO events VALUES (?, 'work', ?, ?, ?, ?, ?, ?, ?)",
            (
                resolved_event_id,
                aggregate_id,
                event_type,
                canonical,
                previous_hash,
                event_hash,
                now,
                idempotency_key,
            ),
        )
