"""SQLite continuity store, isolated from the rebuildable index database."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast

from auto_pm.contracts.continuity import (
    CheckpointItem,
    HandoffV2,
    LeaseItem,
    RunItem,
    WorkItem,
)
from auto_pm.contracts.mission import Mission, MissionState


class ContinuityStoreError(RuntimeError):
    """Raised when a continuity transaction cannot be completed safely."""


_DDL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    schema_version TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    tool_version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS schema_migrations (
    from_version TEXT NOT NULL,
    to_version TEXT NOT NULL,
    applied_at TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    PRIMARY KEY (from_version, to_version)
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
CREATE TABLE IF NOT EXISTS run_items (
    run_id TEXT PRIMARY KEY,
    work_id TEXT NOT NULL REFERENCES work_items(work_id),
    state TEXT NOT NULL,
    executor_id TEXT NOT NULL,
    adapter TEXT NOT NULL,
    owned_paths_json TEXT NOT NULL,
    declared_dirty_paths_json TEXT NOT NULL,
    git_head TEXT NOT NULL,
    worktree_path TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS execution_leases (
    run_id TEXT PRIMARY KEY REFERENCES run_items(run_id),
    owner_id TEXT NOT NULL,
    lease_token TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    version INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checkpoints (
    checkpoint_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES run_items(run_id),
    sequence INTEGER NOT NULL,
    summary TEXT NOT NULL,
    git_head TEXT NOT NULL,
    dirty_paths_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (run_id, sequence)
);
CREATE TABLE IF NOT EXISTS handoffs_v2 (
    handoff_id TEXT PRIMARY KEY,
    work_id TEXT NOT NULL REFERENCES work_items(work_id),
    run_id TEXT NOT NULL REFERENCES run_items(run_id),
    checkpoint_id TEXT NOT NULL REFERENCES checkpoints(checkpoint_id),
    from_owner TEXT NOT NULL,
    to_owner TEXT NOT NULL,
    owned_paths_json TEXT NOT NULL,
    git_head TEXT NOT NULL,
    worktree_path TEXT NOT NULL,
    lease_expires_at TEXT NOT NULL,
    snapshot_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
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
CREATE TABLE IF NOT EXISTS mission_items (
    mission_id TEXT PRIMARY KEY,
    subject_project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    objective TEXT NOT NULL,
    state TEXT NOT NULL,
    root_work_id TEXT,
    acceptance_criteria_json TEXT NOT NULL,
    authority_json TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_work_project_state
ON work_items(subject_project_id, state);
CREATE INDEX IF NOT EXISTS idx_events_aggregate
ON events(aggregate_type, aggregate_id, created_at);
CREATE INDEX IF NOT EXISTS idx_runs_work_state ON run_items(work_id, state);
CREATE INDEX IF NOT EXISTS idx_checkpoints_run ON checkpoints(run_id, sequence);
CREATE INDEX IF NOT EXISTS idx_mission_project_state
ON mission_items(subject_project_id, state);
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_open_mission_per_project
ON mission_items(subject_project_id)
WHERE state NOT IN ('ACCEPTED', 'CLOSED', 'CANCELLED');
"""

_LEGACY_SCHEMA_VERSION = "continuity-store.v2"
_CURRENT_SCHEMA_VERSION = "continuity-store.v3"
_KNOWN_SCHEMA_VERSIONS = frozenset({_LEGACY_SCHEMA_VERSION, _CURRENT_SCHEMA_VERSION})


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
        migrated = False
        with self._transaction() as conn:
            versions = self._schema_versions(conn)
            if versions and not versions.issubset(_KNOWN_SCHEMA_VERSIONS):
                rendered = ", ".join(sorted(versions))
                raise ContinuityStoreError(f"未知或未来 Continuity Store schema: {rendered}")
            conn.executescript(_DDL)
            if not versions:
                conn.execute(
                    "INSERT INTO schema_meta VALUES (?, ?, ?)",
                    (_CURRENT_SCHEMA_VERSION, now, tool_version),
                )
            elif versions == {_LEGACY_SCHEMA_VERSION}:
                conn.execute(
                    "UPDATE schema_meta SET schema_version=? WHERE schema_version=?",
                    (_CURRENT_SCHEMA_VERSION, _LEGACY_SCHEMA_VERSION),
                )
                conn.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
                    (_LEGACY_SCHEMA_VERSION, _CURRENT_SCHEMA_VERSION, now, tool_version),
                )
                migrated = True
        if migrated:
            self._checkpoint_completed_migration()

    def _checkpoint_completed_migration(self) -> None:
        """Make a completed migration visible to strict immutable readers before return."""
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        try:
            result = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            if result is None or int(result[0]) != 0:
                raise ContinuityStoreError("Continuity Store 迁移后 WAL 无法安全合并")
        finally:
            conn.close()

    @staticmethod
    def _schema_versions(conn: sqlite3.Connection) -> set[str]:
        metadata = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_meta'"
        ).fetchone()
        if metadata is None:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            if tables:
                raise ContinuityStoreError("Continuity Store 缺少 schema_meta，拒绝推断迁移")
            return set()
        rows = conn.execute("SELECT schema_version FROM schema_meta").fetchall()
        versions = {str(row[0]) for row in rows}
        if not versions:
            raise ContinuityStoreError("Continuity Store schema_meta 为空，拒绝推断迁移")
        return versions

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

    @contextmanager
    def _read_connection(self) -> Iterator[sqlite3.Connection]:
        """Open the existing store without creating or mutating database files."""
        wal_path = Path(f"{self.db_path}-wal")
        if wal_path.is_file() and wal_path.stat().st_size:
            raise ContinuityStoreError("Continuity Store 存在未合并 WAL，拒绝非一致的严格只读读取")
        conn = sqlite3.connect(
            f"{self.db_path.as_uri()}?mode=ro&immutable=1", uri=True, timeout=5.0
        )
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            yield conn
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

    def create_mission(
        self, values: dict[str, Any], idempotency_key: str, now: str
    ) -> Mission:
        """Persist one Mission and its append-only creation event atomically."""
        with self._transaction() as conn:
            existing = self._event_by_key(conn, idempotency_key)
            if existing is not None:
                if (
                    existing["aggregate_type"] != "mission"
                    or existing["aggregate_id"] != values["mission_id"]
                ):
                    raise ContinuityStoreError("idempotency_key 已用于其他聚合对象")
                return self._get_mission(conn, values["mission_id"])
            try:
                self._insert_mapping(conn, "mission_items", values)
            except sqlite3.IntegrityError as error:
                raise ContinuityStoreError("同一项目已有未终结 Mission，拒绝并发创建") from error
            self._append_event(
                conn,
                values["mission_id"],
                "MISSION_CREATED",
                values,
                idempotency_key,
                now,
                aggregate_type="mission",
            )
            return self._get_mission(conn, values["mission_id"])

    def transition_mission(
        self,
        mission_id: str,
        expected_version: int,
        new_state: MissionState,
        root_work_id: str | None,
        idempotency_key: str,
        now: str,
    ) -> Mission:
        """Advance a Mission with optimistic locking and an immutable event."""
        with self._transaction() as conn:
            existing = self._event_by_key(conn, idempotency_key)
            if existing is not None:
                if existing["aggregate_type"] != "mission" or existing["aggregate_id"] != mission_id:
                    raise ContinuityStoreError("idempotency_key 已用于其他聚合对象")
                return self._get_mission(conn, mission_id)
            cursor = conn.execute(
                """UPDATE mission_items
                SET state=?, root_work_id=?, version=version+1, updated_at=?
                WHERE mission_id=? AND version=?""",
                (new_state.value, root_work_id, now, mission_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise ContinuityStoreError("Mission 不存在或版本冲突")
            self._append_event(
                conn,
                mission_id,
                "MISSION_TRANSITIONED",
                {"state": new_state.value, "root_work_id": root_work_id},
                idempotency_key,
                now,
                aggregate_type="mission",
            )
            return self._get_mission(conn, mission_id)

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
        with self._read_connection() as conn:
            return self._get_work(conn, work_id)

    def get_mission(self, mission_id: str) -> Mission:
        with self._read_connection() as conn:
            return self._get_mission(conn, mission_id)

    def create_run(
        self,
        values: dict[str, Any],
        lease: dict[str, Any],
        idempotency_key: str,
        now: str,
    ) -> RunItem:
        with self._transaction() as conn:
            existing = self._event_by_key(conn, idempotency_key)
            if existing is not None:
                if existing["aggregate_id"] != values["run_id"]:
                    raise ContinuityStoreError("idempotency_key 已用于其他 Run")
                return self._get_run(conn, values["run_id"])
            self._get_work(conn, values["work_id"])
            self._insert_mapping(conn, "run_items", values)
            self._insert_mapping(conn, "execution_leases", lease)
            self._append_event(
                conn,
                values["run_id"],
                "RUN_CREATED",
                values,
                idempotency_key,
                now,
                aggregate_type="run",
            )
            return self._get_run(conn, values["run_id"])

    def transition_run(
        self,
        run_id: str,
        expected_version: int,
        new_state: str,
        idempotency_key: str,
        now: str,
    ) -> RunItem:
        with self._transaction() as conn:
            existing = self._event_by_key(conn, idempotency_key)
            if existing is not None:
                if existing["aggregate_id"] != run_id:
                    raise ContinuityStoreError("idempotency_key 已用于其他 Run")
                return self._get_run(conn, run_id)
            cursor = conn.execute(
                """UPDATE run_items SET state=?, version=version+1, updated_at=?
                WHERE run_id=? AND version=?""",
                (new_state, now, run_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise ContinuityStoreError("Run 不存在或版本冲突")
            self._append_event(
                conn,
                run_id,
                "RUN_TRANSITIONED",
                {"state": new_state},
                idempotency_key,
                now,
                aggregate_type="run",
            )
            return self._get_run(conn, run_id)

    def renew_lease(
        self,
        run_id: str,
        owner_id: str,
        lease_token: str,
        expected_version: int,
        expires_at: str,
        idempotency_key: str,
        now: str,
    ) -> LeaseItem:
        with self._transaction() as conn:
            existing = self._event_by_key(conn, idempotency_key)
            if existing is not None:
                if existing["aggregate_id"] != run_id:
                    raise ContinuityStoreError("idempotency_key 已用于其他 Run")
                return self._get_lease(conn, run_id)
            cursor = conn.execute(
                """UPDATE execution_leases SET expires_at=?, version=version+1, updated_at=?
                WHERE run_id=? AND owner_id=? AND lease_token=? AND version=?""",
                (expires_at, now, run_id, owner_id, lease_token, expected_version),
            )
            if cursor.rowcount != 1:
                raise ContinuityStoreError("lease owner、token 或版本冲突")
            self._append_event(
                conn,
                run_id,
                "LEASE_RENEWED",
                {"owner_id": owner_id, "expires_at": expires_at},
                idempotency_key,
                now,
                aggregate_type="run",
            )
            return self._get_lease(conn, run_id)

    def transfer_lease(
        self,
        run_id: str,
        expected_owner: str,
        new_owner: str,
        new_token: str,
        expected_version: int,
        expires_at: str,
        idempotency_key: str,
        now: str,
    ) -> LeaseItem:
        with self._transaction() as conn:
            existing = self._event_by_key(conn, idempotency_key)
            if existing is not None:
                if existing["aggregate_id"] != run_id:
                    raise ContinuityStoreError("idempotency_key 已用于其他 Run")
                return self._get_lease(conn, run_id)
            cursor = conn.execute(
                """UPDATE execution_leases
                SET owner_id=?, lease_token=?, expires_at=?, version=version+1, updated_at=?
                WHERE run_id=? AND owner_id=? AND version=?""",
                (
                    new_owner,
                    new_token,
                    expires_at,
                    now,
                    run_id,
                    expected_owner,
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                raise ContinuityStoreError("lease transfer owner 或版本冲突")
            self._append_event(
                conn,
                run_id,
                "LEASE_TRANSFERRED",
                {"from_owner": expected_owner, "to_owner": new_owner, "expires_at": expires_at},
                idempotency_key,
                now,
                aggregate_type="run",
            )
            return self._get_lease(conn, run_id)

    def create_checkpoint(
        self, values: dict[str, Any], idempotency_key: str, now: str
    ) -> CheckpointItem:
        with self._transaction() as conn:
            existing = self._event_by_key(conn, idempotency_key)
            if existing is not None:
                if existing["aggregate_id"] != values["run_id"]:
                    raise ContinuityStoreError("idempotency_key 已用于其他 Run")
                return self._get_checkpoint(conn, values["checkpoint_id"])
            self._get_run(conn, values["run_id"])
            stored = dict(values)
            row = conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM checkpoints WHERE run_id=?",
                (values["run_id"],),
            ).fetchone()
            stored["sequence"] = int(row[0])
            self._insert_mapping(conn, "checkpoints", stored)
            self._append_event(
                conn,
                values["run_id"],
                "CHECKPOINT_CREATED",
                stored,
                idempotency_key,
                now,
                event_id=values["checkpoint_id"],
                aggregate_type="run",
            )
            return self._get_checkpoint(conn, values["checkpoint_id"])

    def create_handoff(
        self, values: dict[str, Any], idempotency_key: str, now: str
    ) -> HandoffV2:
        with self._transaction() as conn:
            existing = self._event_by_key(conn, idempotency_key)
            if existing is not None:
                if existing["aggregate_id"] != values["run_id"]:
                    raise ContinuityStoreError("idempotency_key 已用于其他 Run")
                return self._get_handoff(conn, values["handoff_id"])
            checkpoint = self._get_checkpoint(conn, values["checkpoint_id"])
            if checkpoint.run_id != values["run_id"]:
                raise ContinuityStoreError("Checkpoint 不属于目标 Run")
            self._insert_mapping(conn, "handoffs_v2", values)
            self._append_event(
                conn,
                values["run_id"],
                "HANDOFF_CREATED",
                values,
                idempotency_key,
                now,
                event_id=values["handoff_id"],
                aggregate_type="run",
            )
            return self._get_handoff(conn, values["handoff_id"])

    def get_run(self, run_id: str) -> RunItem:
        with self._read_connection() as conn:
            return self._get_run(conn, run_id)

    def get_lease(self, run_id: str) -> LeaseItem:
        with self._read_connection() as conn:
            return self._get_lease(conn, run_id)

    def get_checkpoint(self, checkpoint_id: str) -> CheckpointItem:
        with self._read_connection() as conn:
            return self._get_checkpoint(conn, checkpoint_id)

    def get_handoff(self, handoff_id: str) -> HandoffV2:
        with self._read_connection() as conn:
            return self._get_handoff(conn, handoff_id)

    def list_works(self, subject_project_id: str) -> tuple[WorkItem, ...]:
        with self._read_connection() as conn:
            rows = conn.execute(
                """SELECT work_id FROM work_items WHERE subject_project_id=?
                AND state NOT IN ('CLOSED', 'CANCELLED') ORDER BY updated_at DESC, work_id""",
                (subject_project_id,),
            ).fetchall()
            return tuple(self._get_work(conn, str(row["work_id"])) for row in rows)

    def list_active_missions(self, subject_project_id: str) -> tuple[Mission, ...]:
        with self._read_connection() as conn:
            versions = self._schema_versions(conn)
            if not versions.issubset(_KNOWN_SCHEMA_VERSIONS):
                rendered = ", ".join(sorted(versions))
                raise ContinuityStoreError(f"未知或未来 Continuity Store schema: {rendered}")
            if versions == {_LEGACY_SCHEMA_VERSION}:
                # Strict reads must not upgrade a legacy store. It has no Mission table yet.
                return ()
            rows = conn.execute(
                """SELECT mission_id FROM mission_items WHERE subject_project_id=?
                AND state NOT IN ('ACCEPTED', 'CLOSED', 'CANCELLED')
                ORDER BY updated_at DESC, mission_id""",
                (subject_project_id,),
            ).fetchall()
            return tuple(self._get_mission(conn, str(row["mission_id"])) for row in rows)

    def list_runs(self, work_id: str) -> tuple[RunItem, ...]:
        with self._read_connection() as conn:
            rows = conn.execute(
                """SELECT run_id FROM run_items WHERE work_id=?
                AND state NOT IN ('SUCCEEDED', 'FAILED', 'CANCELLED')
                ORDER BY updated_at DESC, run_id""",
                (work_id,),
            ).fetchall()
            return tuple(self._get_run(conn, str(row["run_id"])) for row in rows)

    def latest_checkpoint(self, run_id: str) -> CheckpointItem | None:
        with self._read_connection() as conn:
            row = conn.execute(
                """SELECT checkpoint_id FROM checkpoints WHERE run_id=?
                ORDER BY sequence DESC LIMIT 1""",
                (run_id,),
            ).fetchone()
            return self._get_checkpoint(conn, str(row["checkpoint_id"])) if row else None

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
    def _get_mission(conn: sqlite3.Connection, mission_id: str) -> Mission:
        row = conn.execute("SELECT * FROM mission_items WHERE mission_id=?", (mission_id,)).fetchone()
        if row is None:
            raise ContinuityStoreError(f"Mission 不存在: {mission_id}")
        data = dict(row)
        data["acceptance_criteria"] = tuple(json.loads(data.pop("acceptance_criteria_json")))
        data["authority"] = json.loads(data.pop("authority_json"))
        return Mission.model_validate(data)

    @staticmethod
    def _get_run(conn: sqlite3.Connection, run_id: str) -> RunItem:
        row = conn.execute("SELECT * FROM run_items WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise ContinuityStoreError(f"Run 不存在: {run_id}")
        data = dict(row)
        data["owned_paths"] = tuple(json.loads(data.pop("owned_paths_json")))
        data["declared_dirty_paths"] = tuple(json.loads(data.pop("declared_dirty_paths_json")))
        return RunItem.model_validate(data)

    @staticmethod
    def _get_lease(conn: sqlite3.Connection, run_id: str) -> LeaseItem:
        row = conn.execute("SELECT * FROM execution_leases WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise ContinuityStoreError(f"Run lease 不存在: {run_id}")
        return LeaseItem.model_validate(dict(row))

    @staticmethod
    def _get_checkpoint(conn: sqlite3.Connection, checkpoint_id: str) -> CheckpointItem:
        row = conn.execute(
            "SELECT * FROM checkpoints WHERE checkpoint_id=?", (checkpoint_id,)
        ).fetchone()
        if row is None:
            raise ContinuityStoreError(f"Checkpoint 不存在: {checkpoint_id}")
        data = dict(row)
        data["dirty_paths"] = tuple(json.loads(data.pop("dirty_paths_json")))
        data["evidence"] = tuple(json.loads(data.pop("evidence_json")))
        return CheckpointItem.model_validate(data)

    @staticmethod
    def _get_handoff(conn: sqlite3.Connection, handoff_id: str) -> HandoffV2:
        row = conn.execute("SELECT * FROM handoffs_v2 WHERE handoff_id=?", (handoff_id,)).fetchone()
        if row is None:
            raise ContinuityStoreError(f"Handoff 不存在: {handoff_id}")
        data = dict(row)
        data["owned_paths"] = tuple(json.loads(data.pop("owned_paths_json")))
        return HandoffV2.model_validate(data)

    @staticmethod
    def _insert_mapping(conn: sqlite3.Connection, table: str, values: dict[str, Any]) -> None:
        columns = ",".join(values)
        placeholders = ",".join("?" for _ in values)
        conn.execute(
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", tuple(values.values())
        )

    @staticmethod
    def _append_event(
        conn: sqlite3.Connection,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
        idempotency_key: str,
        now: str,
        event_id: str = "",
        aggregate_type: str = "work",
    ) -> None:
        previous = conn.execute("SELECT event_hash FROM events ORDER BY rowid DESC LIMIT 1").fetchone()
        previous_hash = str(previous[0]) if previous else ""
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        event_hash = hashlib.sha256(
            f"{previous_hash}|{aggregate_id}|{event_type}|{canonical}|{now}".encode()
        ).hexdigest()
        resolved_event_id = event_id or f"EVT-{event_hash[:16].upper()}"
        conn.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                resolved_event_id,
                aggregate_type,
                aggregate_id,
                event_type,
                canonical,
                previous_hash,
                event_hash,
                now,
                idempotency_key,
            ),
        )
