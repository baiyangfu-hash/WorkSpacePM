"""SQLite continuity store, isolated from the rebuildable index database."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any, cast

from auto_pm.contracts.continuity import (
    CheckpointItem,
    HandoffV2,
    LeaseItem,
    RunItem,
    RunState,
    WorkItem,
    WorkState,
)
from auto_pm.contracts.decision_package import (
    DecisionPackageDTO,
    RuntimeDecisionAction,
    RuntimeDecisionOutcome,
    is_canonical_decision_id,
    is_canonical_runtime_change_id,
)
from auto_pm.contracts.execution_adapter import ExecutionIntent, ExecutionStartEvidence
from auto_pm.contracts.mission import Mission, MissionState
from auto_pm.contracts.orchestration import OrchestrationOutcome
from auto_pm.contracts.pm_facade import PlanningDraft
from auto_pm.infrastructure.control_root_guard import (
    ControlRootGuardError,
    authority_path_parts,
    clean_git_environment,
    governed_worktree_snapshot,
    is_link_like,
    require_control_root,
    require_safe_workspace_path,
)


class ContinuityStoreError(RuntimeError):
    """Raised when a continuity transaction cannot be completed safely."""


class _ReadSnapshotDriftError(RuntimeError):
    """Internal bounded-retry signal for a changing SQLite source snapshot."""


_FileInventory = tuple[bool, int, int, int, int, str]
_StoreInventory = tuple[_FileInventory, _FileInventory, _FileInventory, _FileInventory]


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
CREATE TABLE IF NOT EXISTS planning_drafts (
    request_id TEXT PRIMARY KEY,
    subject_project_id TEXT NOT NULL,
    objective TEXT NOT NULL,
    acceptance_criteria_json TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS planning_draft_chg_bindings (
    request_id TEXT PRIMARY KEY REFERENCES planning_drafts(request_id),
    change_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS planning_draft_spec_bindings (
    request_id TEXT NOT NULL REFERENCES planning_drafts(request_id),
    spec_id TEXT NOT NULL,
    canonical_path TEXT NOT NULL,
    version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (request_id, spec_id)
);
CREATE TABLE IF NOT EXISTS planning_draft_decision_bindings (
    request_id TEXT PRIMARY KEY REFERENCES planning_drafts(request_id),
    decision_id TEXT NOT NULL UNIQUE,
    change_id TEXT NOT NULL,
    plan_hash TEXT NOT NULL,
    approver TEXT NOT NULL,
    approval_evidence_ref TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_work_project_state
ON work_items(subject_project_id, state);
CREATE INDEX IF NOT EXISTS idx_events_aggregate
ON events(aggregate_type, aggregate_id, created_at);
CREATE INDEX IF NOT EXISTS idx_runs_work_state ON run_items(work_id, state);
CREATE INDEX IF NOT EXISTS idx_checkpoints_run ON checkpoints(run_id, sequence);
CREATE INDEX IF NOT EXISTS idx_mission_project_state
ON mission_items(subject_project_id, state);
CREATE INDEX IF NOT EXISTS idx_planning_drafts_project_state
ON planning_drafts(subject_project_id, state);
CREATE UNIQUE INDEX IF NOT EXISTS idx_one_open_mission_per_project
ON mission_items(subject_project_id)
WHERE state NOT IN ('ACCEPTED', 'CLOSED', 'CANCELLED');
"""

_LEGACY_SCHEMA_VERSION = "continuity-store.v2"
_V3_SCHEMA_VERSION = "continuity-store.v3"
_V4_SCHEMA_VERSION = "continuity-store.v4"
_V5_SCHEMA_VERSION = "continuity-store.v5"
_V6_SCHEMA_VERSION = "continuity-store.v6"
_CURRENT_SCHEMA_VERSION = "continuity-store.v7"
_KNOWN_SCHEMA_VERSIONS = frozenset(
    {
        _LEGACY_SCHEMA_VERSION,
        _V3_SCHEMA_VERSION,
        _V4_SCHEMA_VERSION,
        _V5_SCHEMA_VERSION,
        _V6_SCHEMA_VERSION,
        _CURRENT_SCHEMA_VERSION,
    }
)
_CANONICAL_RUNTIME_DB = ".auto-pm/continuity.db"
_FULL_GIT_COMMIT = re.compile(r"[0-9a-f]{40}")
_RUN_CREATION_REQUEST_FIELDS = frozenset(
    {
        "run_id",
        "work_id",
        "executor_id",
        "adapter",
        "owned_paths",
        "declared_dirty_paths",
        "observed_dirty_paths",
        "git_head",
        "worktree_path",
        "lease_seconds",
    }
)
_LEGACY_RUN_CREATION_FIELDS = frozenset(
    {
        "run_id",
        "work_id",
        "state",
        "executor_id",
        "adapter",
        "owned_paths_json",
        "declared_dirty_paths_json",
        "git_head",
        "worktree_path",
        "version",
        "created_at",
        "updated_at",
    }
)
_SETTLEMENT_REQUEST_FIELDS = frozenset(
    {
        "schema_version",
        "action",
        "target_run_id",
        "recovery_run_id",
        "recovery_owner_id",
        "decision_id",
        "outcome",
        "reason",
    }
)
_STORE_RUN_TRANSITIONS = {
    RunState.READY: {RunState.RUNNING, RunState.BLOCKED, RunState.CANCELLED},
    RunState.RUNNING: {RunState.BLOCKED, RunState.VERIFYING, RunState.FAILED},
    RunState.BLOCKED: {RunState.RUNNING, RunState.CANCELLED},
    RunState.VERIFYING: {RunState.RUNNING, RunState.SUCCEEDED, RunState.FAILED},
    RunState.SUCCEEDED: set(),
    RunState.FAILED: set(),
    RunState.CANCELLED: set(),
}


class ContinuityStore:
    """Transactional persistence for Work state and its append-only events."""

    def __init__(
        self,
        workspace_root: str | Path,
        db_path: str | Path | None = None,
        *,
        _clock: Callable[[], datetime] | None = None,
    ) -> None:
        root = Path(workspace_root).resolve()
        selected = Path(db_path) if db_path is not None else root / ".auto-pm" / "continuity.db"
        self.workspace_root = root
        self._clock = _clock or (lambda: datetime.now(UTC))
        try:
            self.db_path = require_safe_workspace_path(
                root,
                selected,
                label="Continuity Store path",
            )
        except ControlRootGuardError as error:
            raise ContinuityStoreError(str(error)) from error

    def _utc_now(self) -> datetime:
        current = self._clock()
        if not isinstance(current, datetime) or current.tzinfo is None:
            raise ContinuityStoreError("Continuity Store clock 必须返回带时区 datetime")
        return current.astimezone(UTC)

    def _require_control_root(self) -> None:
        try:
            require_control_root(self.workspace_root)
        except ControlRootGuardError as error:
            raise ContinuityStoreError(str(error)) from error

    def _validated_db_path(self) -> Path:
        try:
            db_path = require_safe_workspace_path(
                self.workspace_root,
                self.db_path,
                label="Continuity Store path",
            )
            checked_paths = [db_path]
            for suffix in ("-wal", "-shm", "-journal"):
                checked_paths.append(
                    require_safe_workspace_path(
                        self.workspace_root,
                        Path(f"{db_path}{suffix}"),
                        label=f"Continuity Store sidecar {suffix}",
                    )
                )
            for checked in checked_paths:
                try:
                    metadata = checked.stat()
                except FileNotFoundError:
                    continue
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                    raise ContinuityStoreError(
                        f"Continuity Store DB/sidecar 必须是唯一链接的普通文件: {checked.name}"
                    )
            return db_path
        except ControlRootGuardError as error:
            raise ContinuityStoreError(str(error)) from error

    def _validated_run_snapshot(
        self,
        path: object,
        git_head: object,
        owned_paths: tuple[str, ...],
        declared_dirty_paths: tuple[str, ...],
        observed_dirty_paths: tuple[str, ...],
    ) -> Path:
        if not isinstance(path, (str, Path)) or not isinstance(git_head, str):
            raise ContinuityStoreError("Run worktree_path 与 git_head 类型非法")
        try:
            worktree, actual_head, actual_dirty = governed_worktree_snapshot(
                self.workspace_root,
                path,
            )
        except ControlRootGuardError as error:
            raise ContinuityStoreError(str(error)) from error
        if actual_head != git_head:
            raise ContinuityStoreError("Run git_head 与受管 worktree 当前 HEAD 不一致")
        actual_observed = tuple(
            dirty
            for dirty in actual_dirty
            if any(self._authority_path_covered(dirty, (owned,)) for owned in owned_paths)
        )
        if {self._authority_path_key(path) for path in actual_observed} != {
            self._authority_path_key(path) for path in observed_dirty_paths
        }:
            raise ContinuityStoreError("Run observed_dirty_paths 与受管 worktree 不一致")
        if not all(
            self._authority_path_covered(path, declared_dirty_paths)
            for path in observed_dirty_paths
        ):
            raise ContinuityStoreError("存在未声明的 dirty path")
        if not all(
            self._authority_path_covered(path, owned_paths) for path in declared_dirty_paths
        ):
            raise ContinuityStoreError("declared_dirty_paths 超出 owned_paths")
        return worktree

    @classmethod
    def _run_paths(cls, value: object, *, label: str, allow_empty: bool) -> tuple[str, ...]:
        if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
            raise ContinuityStoreError(f"Run {label} 必须是字符串数组")
        normalized_items: list[str] = []
        seen: set[tuple[str, ...]] = set()
        for item in value:
            normalized_item = cls._normalize_authority_path(item)
            key = cls._authority_path_key(normalized_item)
            if key not in seen:
                seen.add(key)
                normalized_items.append(normalized_item)
        normalized = tuple(normalized_items)
        if not normalized and not allow_empty:
            raise ContinuityStoreError(f"Run {label} 不能为空")
        return normalized

    def runtime_target_path(self) -> str:
        """Return the only workspace-relative database target eligible for settlement."""

        db_path = self._validated_db_path()
        try:
            relative = db_path.relative_to(self.workspace_root).as_posix()
        except ValueError as error:  # pragma: no cover - constructor already guards this
            raise ContinuityStoreError("continuity.db 必须位于工作空间内") from error
        if self._authority_path_key(relative) != self._authority_path_key(_CANONICAL_RUNTIME_DB):
            raise ContinuityStoreError("过期 Run 结算只能作用于 canonical .auto-pm/continuity.db")
        return _CANONICAL_RUNTIME_DB

    @classmethod
    def authority_paths_hash(cls, paths: tuple[str, ...]) -> str:
        """Hash normalized persisted authority paths without filesystem access."""

        normalized = tuple(cls._normalize_authority_path(path) for path in paths)
        return hashlib.sha256(
            json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()

    @classmethod
    def _authority_path_covered(cls, path: str, roots: tuple[str, ...]) -> bool:
        path_parts = cls._authority_path_key(path)
        for root in roots:
            root_parts = cls._authority_path_key(root)
            if path_parts[: len(root_parts)] == root_parts:
                return True
        return False

    @classmethod
    def _authority_path_key(cls, raw: str) -> tuple[str, ...]:
        return authority_path_parts(cls._normalize_authority_path(raw))

    @staticmethod
    def _normalize_authority_path(raw: str) -> str:
        text = str(raw).replace("\\", "/")
        raw_segments = text.split("/")
        path = PurePosixPath(text)
        if (
            path.is_absolute()
            or (path.parts and path.parts[0].endswith(":"))
            or any(part in {".", ".."} for part in raw_segments)
            or str(path) in {"", "."}
            or any(part != part.rstrip(" .") for part in path.parts)
        ):
            raise ContinuityStoreError(f"非法 authority path: {raw}")
        return path.as_posix()

    @staticmethod
    def _validate_settlement_authority_identity(
        *,
        target_decision_id: str,
        target_decision_sha256: str,
        target_change_id: str,
        decision_id: str,
        decision_sha256: str,
        decision_change_id: str,
        decision_project_id: str,
    ) -> None:
        if not is_canonical_decision_id(target_decision_id) or not is_canonical_decision_id(
            decision_id
        ):
            raise ContinuityStoreError("目标与恢复 Work 必须绑定 canonical Decision ID")
        if target_decision_id == decision_id:
            raise ContinuityStoreError("恢复 Decision 不得复用目标 Work 的授权链")
        if not is_canonical_runtime_change_id(
            target_change_id
        ) or not is_canonical_runtime_change_id(decision_change_id):
            raise ContinuityStoreError("目标与恢复 Decision 必须绑定 canonical CHG ID")
        if target_change_id == decision_change_id:
            raise ContinuityStoreError("恢复 CHG 必须独立于目标 Work 的原 CHG")
        if (
            not isinstance(decision_project_id, str)
            or not decision_project_id
            or decision_project_id != decision_project_id.strip()
        ):
            raise ContinuityStoreError("Decision project_id 必须是规范非空字符串")
        for digest in (target_decision_sha256, decision_sha256):
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise ContinuityStoreError("Decision SHA256 格式非法")

    def _decision_snapshot(self, decision_id: str) -> tuple[DecisionPackageDTO, str]:
        """Re-read an immutable Decision through the canonical safe-path reader."""

        from auto_pm.domain.change.decision_service import DecisionError, DecisionService

        try:
            return DecisionService(self.workspace_root).get_decision_with_sha256(decision_id)
        except DecisionError as error:
            raise ContinuityStoreError(
                f"Decision immutable snapshot 无法复核: {decision_id}"
            ) from error

    @staticmethod
    def _validate_recovery_git_head(git_head: object) -> str:
        if not isinstance(git_head, str) or _FULL_GIT_COMMIT.fullmatch(git_head) is None:
            raise ContinuityStoreError("恢复 Run git_head 必须是完整小写 Git commit OID")
        return git_head

    def _git_bytes(self, *args: str) -> bytes:
        try:
            result = subprocess.run(
                ["git", "-C", str(self.workspace_root), *args],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                check=False,
                shell=False,
                env=clean_git_environment(),
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ContinuityStoreError("Decision Git immutable 事实无法复核") from error
        if result.returncode != 0:
            raise ContinuityStoreError("Decision Git commit/blob 不存在或无法读取")
        diagnostic = result.stderr.decode("utf-8", errors="replace").strip()
        if diagnostic:
            raise ContinuityStoreError(f"Decision Git 事实包含诊断: {diagnostic[:1000]}")
        return result.stdout

    def _decision_git_snapshots(
        self,
        *,
        recovery_git_head: str,
        target_decision_id: str,
        target_decision_sha256: str,
        recovery_decision_id: str,
        recovery_decision_sha256: str,
        require_current_head: bool,
    ) -> tuple[DecisionPackageDTO, DecisionPackageDTO]:
        """Bind both current Decision byte snapshots to the recovery Run commit."""

        head = self._validate_recovery_git_head(recovery_git_head)
        self._require_control_root()
        try:
            resolved_head = (
                self._git_bytes("rev-parse", "--verify", f"{head}^{{commit}}")
                .decode("ascii", errors="strict")
                .strip()
            )
        except UnicodeDecodeError as error:
            raise ContinuityStoreError("恢复 Run git_head 不是规范 ASCII commit OID") from error
        if resolved_head != head:
            raise ContinuityStoreError("恢复 Run git_head 不是完整 commit OID")
        if require_current_head:
            try:
                current_head = (
                    self._git_bytes("rev-parse", "--verify", "HEAD^{commit}")
                    .decode("ascii", errors="strict")
                    .strip()
                )
            except UnicodeDecodeError as error:
                raise ContinuityStoreError("当前 Git HEAD 不是规范 commit OID") from error
            if current_head != head:
                raise ContinuityStoreError("首次结算要求当前 Git HEAD 精确匹配恢复 Run git_head")

        target_path = f".auto-pm/decisions/{target_decision_id}.json"
        recovery_path = f".auto-pm/decisions/{recovery_decision_id}.json"
        for path in (target_path, recovery_path):
            tracked = self._git_bytes("ls-files", "--error-unmatch", "--", path)
            if tracked.decode("utf-8", errors="replace").strip() != path:
                raise ContinuityStoreError("Decision 文件必须在当前 Git index 中精确跟踪")
        dirty = self._git_bytes(
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            target_path,
            recovery_path,
        )
        if dirty:
            raise ContinuityStoreError(
                "Decision immutable snapshot 未跟踪或相对恢复 Run git_head 存在脏改漂移"
            )

        target_before, target_before_sha256 = self._decision_snapshot(target_decision_id)
        recovery_before, recovery_before_sha256 = self._decision_snapshot(recovery_decision_id)
        for path, expected_sha256, current_sha256 in (
            (target_path, target_decision_sha256, target_before_sha256),
            (recovery_path, recovery_decision_sha256, recovery_before_sha256),
        ):
            blob = self._git_bytes("cat-file", "blob", f"{head}:{path}")
            blob_sha256 = hashlib.sha256(blob).hexdigest()
            if blob_sha256 != expected_sha256 or current_sha256 != expected_sha256:
                raise ContinuityStoreError("Decision 字节未绑定恢复 Run git_head 的 immutable blob")

        target_after, target_after_sha256 = self._decision_snapshot(target_decision_id)
        recovery_after, recovery_after_sha256 = self._decision_snapshot(recovery_decision_id)
        if (
            target_after_sha256 != target_before_sha256
            or recovery_after_sha256 != recovery_before_sha256
            or target_after != target_before
            or recovery_after != recovery_before
        ):
            raise ContinuityStoreError("Decision 或 Git HEAD 在结算复核期间发生漂移")
        if require_current_head:
            try:
                final_head = (
                    self._git_bytes("rev-parse", "--verify", "HEAD^{commit}")
                    .decode("ascii", errors="strict")
                    .strip()
                )
            except UnicodeDecodeError as error:
                raise ContinuityStoreError("当前 Git HEAD 不是规范 commit OID") from error
            if final_head != head:
                raise ContinuityStoreError("首次结算复核期间 Git HEAD 发生漂移")
        return target_after, recovery_after

    def initialize(self, now: str, tool_version: str) -> None:
        self._require_control_root()
        db_path = self._validated_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
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
                    (_V3_SCHEMA_VERSION, _LEGACY_SCHEMA_VERSION),
                )
                conn.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
                    (_LEGACY_SCHEMA_VERSION, _V3_SCHEMA_VERSION, now, tool_version),
                )
                conn.execute(
                    "UPDATE schema_meta SET schema_version=? WHERE schema_version=?",
                    (_V4_SCHEMA_VERSION, _V3_SCHEMA_VERSION),
                )
                conn.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
                    (_V3_SCHEMA_VERSION, _V4_SCHEMA_VERSION, now, tool_version),
                )
                versions = {_V4_SCHEMA_VERSION}
            if versions == {_V3_SCHEMA_VERSION}:
                conn.execute(
                    "UPDATE schema_meta SET schema_version=? WHERE schema_version=?",
                    (_V4_SCHEMA_VERSION, _V3_SCHEMA_VERSION),
                )
                conn.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
                    (_V3_SCHEMA_VERSION, _V4_SCHEMA_VERSION, now, tool_version),
                )
                versions = {_V4_SCHEMA_VERSION}
            if versions == {_V4_SCHEMA_VERSION}:
                conn.execute(
                    "UPDATE schema_meta SET schema_version=? WHERE schema_version=?",
                    (_V5_SCHEMA_VERSION, _V4_SCHEMA_VERSION),
                )
                conn.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
                    (_V4_SCHEMA_VERSION, _V5_SCHEMA_VERSION, now, tool_version),
                )
                versions = {_V5_SCHEMA_VERSION}
            if versions == {_V5_SCHEMA_VERSION}:
                conn.execute(
                    "UPDATE schema_meta SET schema_version=? WHERE schema_version=?",
                    (_V6_SCHEMA_VERSION, _V5_SCHEMA_VERSION),
                )
                conn.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
                    (_V5_SCHEMA_VERSION, _V6_SCHEMA_VERSION, now, tool_version),
                )
                versions = {_V6_SCHEMA_VERSION}
            if versions == {_V6_SCHEMA_VERSION}:
                conn.execute(
                    "UPDATE schema_meta SET schema_version=? WHERE schema_version=?",
                    (_CURRENT_SCHEMA_VERSION, _V6_SCHEMA_VERSION),
                )
                conn.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?, ?)",
                    (_V6_SCHEMA_VERSION, _CURRENT_SCHEMA_VERSION, now, tool_version),
                )
                migrated = True
        if migrated:
            self._checkpoint_completed_migration()

    def _checkpoint_completed_migration(self) -> None:
        """Make a completed migration visible to strict immutable readers before return."""
        self._require_control_root()
        db_path = self._validated_db_path()
        conn = sqlite3.connect(db_path, timeout=5.0)
        try:
            self._validated_db_path()
            result = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            self._validated_db_path()
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
        self._require_control_root()
        db_path = self._validated_db_path()
        conn = sqlite3.connect(db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            self._validated_db_path()
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("BEGIN IMMEDIATE")
            self._validated_db_path()
            yield conn
            self._validated_db_path()
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def _read_connection(self) -> Iterator[sqlite3.Connection]:
        """Read one byte-stable off-workspace snapshot without touching source sidecars."""

        db_path = self._validated_db_path()
        temporary, snapshot_path = self._stable_read_snapshot(db_path)
        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(
                f"{snapshot_path.as_uri()}?mode=ro&cache=private",
                uri=True,
                timeout=5.0,
            )
        except sqlite3.Error as error:
            temporary.cleanup()
            raise ContinuityStoreError("Continuity Store 严格只读快照无法打开") from error
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("BEGIN")
            integrity = conn.execute("PRAGMA quick_check").fetchall()
            if len(integrity) != 1 or str(integrity[0][0]) != "ok":
                raise ContinuityStoreError("Continuity Store 严格只读快照完整性检查失败")
            yield conn
        except sqlite3.Error as error:
            raise ContinuityStoreError("Continuity Store 严格只读查询失败") from error
        finally:
            if conn is not None:
                conn.rollback()
                conn.close()
            temporary.cleanup()

    @staticmethod
    def _file_inventory(path: Path, *, required: bool) -> _FileInventory:
        try:
            metadata = path.stat()
        except FileNotFoundError:
            if required:
                raise ContinuityStoreError(f"Continuity Store 必需文件不存在: {path.name}")
            return (False, 0, 0, 0, 0, "")
        except OSError as error:
            raise ContinuityStoreError(f"Continuity Store 文件无法读取: {path.name}") from error
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise ContinuityStoreError(
                f"Continuity Store 路径必须是唯一链接的普通文件: {path.name}"
            )
        digest = hashlib.sha256()
        try:
            with path.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
        except FileNotFoundError as error:
            raise _ReadSnapshotDriftError(path.name) from error
        except OSError as error:
            raise ContinuityStoreError(f"Continuity Store 文件无法读取: {path.name}") from error
        return (
            True,
            int(metadata.st_size),
            int(metadata.st_mtime_ns),
            int(metadata.st_dev),
            int(metadata.st_ino),
            digest.hexdigest(),
        )

    @classmethod
    def _source_inventory(cls, db_path: Path) -> _StoreInventory:
        facts = (
            cls._file_inventory(db_path, required=True),
            cls._file_inventory(Path(f"{db_path}-wal"), required=False),
            cls._file_inventory(Path(f"{db_path}-shm"), required=False),
            cls._file_inventory(Path(f"{db_path}-journal"), required=False),
        )
        if facts[3][0] and facts[3][1] > 0:
            raise ContinuityStoreError(
                "Continuity Store 存在非空 rollback journal，拒绝严格只读读取"
            )
        return facts

    @staticmethod
    def _content_inventory(fact: _FileInventory) -> tuple[bool, int, str]:
        return fact[0], fact[1], fact[5]

    @staticmethod
    def _path_is_within(path: Path, parent: Path) -> bool:
        path_key = os.path.normcase(os.path.normpath(str(path)))
        parent_key = os.path.normcase(os.path.normpath(str(parent)))
        try:
            common = os.path.commonpath((path_key, parent_key))
        except ValueError:
            return False
        if os.name == "nt":
            return common.casefold() == parent_key.casefold()
        return common == parent_key

    def _validated_snapshot_temp_root(self) -> Path:
        raw = Path(os.path.abspath(tempfile.gettempdir()))
        cursor = Path(raw.anchor)
        try:
            for part in raw.parts[1:]:
                cursor /= part
                if is_link_like(cursor):
                    raise ContinuityStoreError(
                        "Continuity Store 严格只读临时根不得经过 reparse path"
                    )
            resolved = raw.resolve(strict=True)
        except OSError as error:
            raise ContinuityStoreError("Continuity Store 严格只读临时根不可用") from error
        if not resolved.is_dir() or self._path_is_within(resolved, self.workspace_root):
            raise ContinuityStoreError("Continuity Store 严格只读临时根必须位于 workspace 外")
        return resolved

    @staticmethod
    @contextmanager
    def _source_read_locks(db_path: Path) -> Iterator[None]:
        """Deny source DB/WAL/journal writes during a Windows snapshot capture."""

        if os.name != "nt":
            yield
            return
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create_file = kernel32.CreateFileW
        create_file.argtypes = (
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        )
        create_file.restype = wintypes.HANDLE
        close_handle = kernel32.CloseHandle
        close_handle.argtypes = (wintypes.HANDLE,)
        close_handle.restype = wintypes.BOOL
        generic_read = 0x80000000
        share_read = 0x00000001
        open_existing = 3
        normal_attribute = 0x00000080
        invalid_handle = ctypes.c_void_p(-1).value
        handles: list[int] = []
        try:
            for path in (
                db_path,
                Path(f"{db_path}-wal"),
                Path(f"{db_path}-journal"),
            ):
                if not path.exists():
                    continue
                handle = create_file(
                    str(path),
                    generic_read,
                    share_read,
                    None,
                    open_existing,
                    normal_attribute,
                    None,
                )
                if handle == invalid_handle:
                    raise _ReadSnapshotDriftError(f"sharing violation: {path.name}")
                handles.append(int(handle))
            yield
        finally:
            for handle in reversed(handles):
                close_handle(handle)

    def _stable_read_snapshot(
        self,
        db_path: Path,
    ) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        """Copy a stable DB/WAL byte set with bounded fail-closed retries."""

        temp_root = self._validated_snapshot_temp_root()
        for _attempt in range(3):
            temporary = tempfile.TemporaryDirectory(
                prefix="auto-pm-continuity-read-",
                dir=temp_root,
            )
            snapshot_dir = Path(temporary.name)
            snapshot_path = snapshot_dir / db_path.name
            try:
                resolved_snapshot_dir = snapshot_dir.resolve(strict=True)
                if (
                    is_link_like(snapshot_dir)
                    or not self._path_is_within(resolved_snapshot_dir, temp_root)
                    or self._path_is_within(resolved_snapshot_dir, self.workspace_root)
                ):
                    raise ContinuityStoreError("Continuity Store 严格只读快照临时路径越界")
                # Revalidate every acquisition attempt so a late reparse swap fails closed.
                if self._validated_db_path() != db_path:
                    raise ContinuityStoreError("Continuity Store path 在读取期间发生漂移")
                # Detect a hot journal before attempting Windows share-deny handles.
                self._source_inventory(db_path)
                with self._source_read_locks(db_path):
                    before = self._source_inventory(db_path)
                    source_paths = (db_path, Path(f"{db_path}-wal"))
                    snapshot_paths = (snapshot_path, Path(f"{snapshot_path}-wal"))
                    for source, target, fact in zip(
                        source_paths,
                        snapshot_paths,
                        before[:2],
                        strict=True,
                    ):
                        if fact[0]:
                            try:
                                shutil.copyfile(source, target)
                            except FileNotFoundError as error:
                                raise _ReadSnapshotDriftError(source.name) from error
                    copied = tuple(
                        self._file_inventory(path, required=fact[0])
                        if fact[0]
                        else self._file_inventory(path, required=False)
                        for path, fact in zip(snapshot_paths, before[:2], strict=True)
                    )
                    after = self._source_inventory(db_path)
                    if before != after or any(
                        self._content_inventory(copied_fact) != self._content_inventory(source_fact)
                        for copied_fact, source_fact in zip(copied, before[:2], strict=True)
                    ):
                        raise _ReadSnapshotDriftError("source changed during snapshot")
                return temporary, snapshot_path
            except _ReadSnapshotDriftError:
                temporary.cleanup()
                continue
            except Exception:
                temporary.cleanup()
                raise
        raise ContinuityStoreError("Continuity Store BUSY: 无法取得稳定只读快照")

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
            self._append_event(
                conn, values["work_id"], "WORK_CREATED", values, idempotency_key, now
            )
            return self._get_work(conn, values["work_id"])

    def create_planning_draft(self, draft: PlanningDraft) -> PlanningDraft:
        """Persist one pre-authorization draft with request-keyed replay protection."""

        now = self._utc_now().isoformat()
        with self._transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM planning_drafts WHERE request_id=?", (draft.request_id,)
            ).fetchone()
            if existing is not None:
                persisted = self._get_planning_draft(existing)
                if not hmac.compare_digest(persisted.input_fingerprint, draft.input_fingerprint):
                    raise ContinuityStoreError(
                        "request_id 已绑定不同输入，拒绝覆盖既有 PlanningDraft"
                    )
                return persisted

            values = {
                "request_id": draft.request_id,
                "subject_project_id": draft.subject_project_id,
                "objective": draft.objective,
                "acceptance_criteria_json": json.dumps(
                    draft.acceptance_criteria, ensure_ascii=False, separators=(",", ":")
                ),
                "input_fingerprint": draft.input_fingerprint,
                "state": draft.state,
                "created_at": now,
                "updated_at": now,
            }
            self._insert_mapping(conn, "planning_drafts", values)
            self._append_event(
                conn,
                draft.request_id,
                "PLANNING_DRAFT_CREATED",
                draft.model_dump(mode="json"),
                f"planning-draft-create:{draft.request_id}:{draft.input_fingerprint}",
                now,
                aggregate_type="planning_draft",
            )
            return draft

    def reserve_planning_draft_change(self, request_id: str, change_id: str) -> str:
        """Bind one draft to exactly one CHG identifier before its file is created.

        The durable reservation makes a failed file write safely retryable: later
        calls receive the original identifier instead of allocating a second CHG.
        """

        now = self._utc_now().isoformat()
        with self._transaction() as conn:
            if conn.execute(
                "SELECT 1 FROM planning_drafts WHERE request_id=?", (request_id,)
            ).fetchone() is None:
                raise ContinuityStoreError(f"PlanningDraft 不存在: {request_id}")
            existing = conn.execute(
                "SELECT change_id FROM planning_draft_chg_bindings WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if existing is not None:
                return str(existing["change_id"])
            conflicting = conn.execute(
                "SELECT request_id FROM planning_draft_chg_bindings WHERE change_id=?",
                (change_id,),
            ).fetchone()
            if conflicting is not None:
                raise ContinuityStoreError("候选 CHG 已绑定其他 PlanningDraft")
            conn.execute(
                "INSERT INTO planning_draft_chg_bindings VALUES (?, ?, ?)",
                (request_id, change_id, now),
            )
            self._append_event(
                conn,
                request_id,
                "PLANNING_DRAFT_CHG_RESERVED",
                {"request_id": request_id, "change_id": change_id},
                f"planning-draft-chg-reserve:{request_id}",
                now,
                aggregate_type="planning_draft",
            )
            return change_id

    def bind_planning_draft_specs(
        self, request_id: str, specs: tuple[tuple[str, str, str], ...]
    ) -> tuple[tuple[str, str, str], ...]:
        """Persist the effective spec sources for one pre-authorization draft."""

        if not specs:
            raise ContinuityStoreError("PlanningDraft 必须绑定至少一条有效规范")
        now = self._utc_now().isoformat()
        with self._transaction() as conn:
            if conn.execute(
                "SELECT 1 FROM planning_drafts WHERE request_id=?", (request_id,)
            ).fetchone() is None:
                raise ContinuityStoreError(f"PlanningDraft 不存在: {request_id}")
            existing = conn.execute(
                """SELECT spec_id, canonical_path, version
                FROM planning_draft_spec_bindings WHERE request_id=? ORDER BY spec_id""",
                (request_id,),
            ).fetchall()
            if existing:
                return tuple((str(row["spec_id"]), str(row["canonical_path"]), str(row["version"])) for row in existing)
            for spec_id, canonical_path, version in specs:
                conn.execute(
                    "INSERT INTO planning_draft_spec_bindings VALUES (?, ?, ?, ?, ?)",
                    (request_id, spec_id, canonical_path, version, now),
                )
            self._append_event(
                conn,
                request_id,
                "PLANNING_DRAFT_SPECS_BOUND",
                {"request_id": request_id, "specs": specs},
                f"planning-draft-spec-bind:{request_id}",
                now,
                aggregate_type="planning_draft",
            )
            return specs

    def reserve_planning_draft_decision(
        self,
        request_id: str,
        change_id: str,
        plan_hash: str,
        approver: str,
        approval_evidence_ref: str,
    ) -> str:
        """Reserve one immutable Decision identity for one exact human approval."""

        if re.fullmatch(r"[0-9a-f]{64}", plan_hash) is None:
            raise ContinuityStoreError("PlanningScopeCard plan_hash 必须是 64 位小写 SHA256")
        values = (change_id, plan_hash, approver, approval_evidence_ref)
        if any(not value or value != value.strip() for value in values):
            raise ContinuityStoreError("Planning Decision 绑定字段必须是规范非空字符串")
        now = self._utc_now()
        with self._transaction() as conn:
            bound_change = conn.execute(
                "SELECT change_id FROM planning_draft_chg_bindings WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if bound_change is None or str(bound_change["change_id"]) != change_id:
                raise ContinuityStoreError("PlanningDraft 未绑定指定真实 CHG")
            spec_count = conn.execute(
                "SELECT COUNT(*) FROM planning_draft_spec_bindings WHERE request_id=?",
                (request_id,),
            ).fetchone()[0]
            if int(spec_count) == 0:
                raise ContinuityStoreError("PlanningDraft 尚未绑定真实规范版本")
            existing = conn.execute(
                "SELECT * FROM planning_draft_decision_bindings WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if existing is not None:
                persisted = (
                    str(existing["change_id"]),
                    str(existing["plan_hash"]),
                    str(existing["approver"]),
                    str(existing["approval_evidence_ref"]),
                )
                if persisted != values:
                    raise ContinuityStoreError("PlanningDraft 已绑定不同批准，拒绝覆盖")
                return str(existing["decision_id"])
            identity = "\n".join((request_id, *values)).encode("utf-8")
            decision_id = f"DEC-{now:%Y%m%d}-{hashlib.sha256(identity).hexdigest()[:8].upper()}"
            conn.execute(
                "INSERT INTO planning_draft_decision_bindings VALUES (?, ?, ?, ?, ?, ?, ?)",
                (request_id, decision_id, *values, now.isoformat()),
            )
            self._append_event(
                conn,
                request_id,
                "PLANNING_DECISION_RESERVED",
                {
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "change_id": change_id,
                    "plan_hash": plan_hash,
                    "approver": approver,
                    "approval_evidence_ref": approval_evidence_ref,
                },
                f"planning-decision-reserve:{request_id}",
                now.isoformat(),
                aggregate_type="planning_draft",
            )
            return decision_id

    def get_planning_draft(self, request_id: str) -> PlanningDraft:
        """Read one persisted pre-authorization draft without changing store state."""

        with self._read_connection() as conn:
            row = conn.execute(
                "SELECT * FROM planning_drafts WHERE request_id=?", (request_id,)
            ).fetchone()
            if row is None:
                raise ContinuityStoreError(f"PlanningDraft 不存在: {request_id}")
            return self._get_planning_draft(row)

    def get_planning_draft_decision_id(
        self, request_id: str, change_id: str, plan_hash: str
    ) -> str:
        """Return the Decision bound to this exact draft, CHG, and plan hash."""

        with self._read_connection() as conn:
            row = conn.execute(
                "SELECT * FROM planning_draft_decision_bindings WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if row is None:
                raise ContinuityStoreError("PlanningDraft 尚未绑定用户批准的 Decision")
            if str(row["change_id"]) != change_id or not hmac.compare_digest(
                str(row["plan_hash"]), plan_hash
            ):
                raise ContinuityStoreError("PlanningDraft 的 CHG 或 plan_hash 与批准事实不一致")
            return str(row["decision_id"])

    def resolve_planning_draft_mission_id(
        self,
        request_id: str,
        decision_id: str,
        change_id: str,
        plan_hash: str,
    ) -> str:
        """Resolve one deterministic Mission identity from an exact approved chain."""

        if re.fullmatch(r"[0-9a-f]{64}", plan_hash) is None:
            raise ContinuityStoreError("PlanningScopeCard plan_hash 必须是 64 位小写 SHA256")
        values = (decision_id, change_id, plan_hash)
        with self._read_connection() as conn:
            approved = conn.execute(
                "SELECT * FROM planning_draft_decision_bindings WHERE request_id=?",
                (request_id,),
            ).fetchone()
            if approved is None:
                raise ContinuityStoreError("PlanningDraft 尚未绑定用户批准的 Decision")
            persisted_approval = (
                str(approved["decision_id"]),
                str(approved["change_id"]),
                str(approved["plan_hash"]),
            )
            if persisted_approval != values:
                raise ContinuityStoreError("Mission 输入与 PlanningDraft 批准链不一致")
            identity = "\n".join((request_id, *values)).encode("utf-8")
            return f"MISSION-{hashlib.sha256(identity).hexdigest()[:16].upper()}"

    def create_mission(self, values: dict[str, Any], idempotency_key: str, now: str) -> Mission:
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
                if (
                    existing["aggregate_type"] != "mission"
                    or existing["aggregate_id"] != mission_id
                ):
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

    def list_work_relations(self) -> tuple[tuple[str, str, str], ...]:
        """Return the persisted directed Work Graph without opening a write transaction."""
        with self._read_connection() as conn:
            rows = conn.execute(
                """SELECT from_work_id, to_work_id, relation
                FROM work_relations ORDER BY rowid"""
            ).fetchall()
        return tuple((str(row[0]), str(row[1]), str(row[2])) for row in rows)

    def event_aggregate_for_key(self, idempotency_key: str) -> tuple[str, str] | None:
        """Read an idempotency binding before applying higher-level graph checks."""
        with self._read_connection() as conn:
            row = self._event_by_key(conn, idempotency_key)
            if row is None:
                return None
            return str(row["aggregate_type"]), str(row["aggregate_id"])

    @classmethod
    def _execution_intent_key(cls, operation_id: str) -> str:
        """Reserve a separate namespace in the existing unique event-key index."""
        operation_id = cls._validated_idempotency_key(operation_id)
        digest = hashlib.sha256(operation_id.encode("utf-8")).hexdigest()
        return f"execution-intent:{digest}"

    @classmethod
    def _execution_intent_from_event(
        cls, row: sqlite3.Row, operation_id: str
    ) -> ExecutionIntent:
        """Reject malformed or substituted reservations before returning a receipt."""
        try:
            intent = ExecutionIntent.model_validate_json(str(row["payload_json"]))
        except ValueError as error:
            raise ContinuityStoreError("ExecutionIntent payload 无法读取") from error
        if (
            row["aggregate_type"] != "execution_intent"
            or row["event_type"] != "EXECUTION_INTENT_PREPARED"
            or row["aggregate_id"] != operation_id
            or intent.operation_id != operation_id
            or row["idempotency_key"] != cls._execution_intent_key(operation_id)
        ):
            raise ContinuityStoreError("ExecutionIntent 事件身份不一致")
        return intent

    def get_execution_intent(self, operation_id: str) -> ExecutionIntent | None:
        """Read the durable intent without deriving state from a Run or worktree."""
        key = self._execution_intent_key(operation_id)
        with self._read_connection() as conn:
            row = self._event_by_key(conn, key)
            return None if row is None else self._execution_intent_from_event(row, operation_id)

    def reserve_execution_intent(
        self, intent: ExecutionIntent
    ) -> tuple[ExecutionIntent, bool]:
        """Atomically claim one operation; only the committed winner may dispatch.

        Existing append-only Continuity events are the single source of truth.
        Their UNIQUE idempotency key is the operation reservation, so no auxiliary
        file, in-memory registry, or schema migration is needed.
        """
        intent = ExecutionIntent.model_validate(intent.model_dump())
        key = self._execution_intent_key(intent.operation_id)
        try:
            with self._transaction() as conn:
                row = self._event_by_key(conn, key)
                if row is not None:
                    existing = self._execution_intent_from_event(row, intent.operation_id)
                    if (
                        existing.request_sha256 != intent.request_sha256
                        or existing.receipt != intent.receipt
                    ):
                        raise ContinuityStoreError("operation_id 已绑定不同载荷")
                    return existing, False
                receipt = intent.receipt
                work = self._get_work(conn, receipt.work_id)
                if work.state not in {WorkState.READY, WorkState.IN_PROGRESS}:
                    raise ContinuityStoreError("只有 READY/IN_PROGRESS Work 可以准备执行")
                if work.subject_project_id != receipt.subject_project_id or not all(
                    self._authority_path_covered(path, work.scope_paths)
                    for path in receipt.owned_paths
                ):
                    raise ContinuityStoreError("ExecutionIntent 超出 Work 授权")
                if conn.execute(
                    "SELECT 1 FROM run_items WHERE run_id=?", (receipt.run_id,)
                ).fetchone() is not None:
                    raise ContinuityStoreError("run_id 已存在，拒绝建立无原始 intent 的派发")
                rows = conn.execute(
                    "SELECT * FROM events WHERE aggregate_type='execution_intent'"
                ).fetchall()
                for other_row in rows:
                    other = self._execution_intent_from_event(
                        other_row, str(other_row["aggregate_id"])
                    )
                    if other.receipt.run_id == receipt.run_id:
                        raise ContinuityStoreError("run_id 已绑定其他 operation_id")
                self._append_event(
                    conn,
                    intent.operation_id,
                    "EXECUTION_INTENT_PREPARED",
                    intent.model_dump(mode="json"),
                    key,
                    intent.created_at.isoformat(),
                    aggregate_type="execution_intent",
                )
            return intent, True
        except sqlite3.Error as error:
            raise ContinuityStoreError("ExecutionIntent 持久化失败") from error

    def get_orchestration_outcome(
        self, mission_id: str, idempotency_key: str
    ) -> OrchestrationOutcome | None:
        """Read a prior idempotent outcome when a caller retries the same command."""
        with self._read_connection() as conn:
            row = self._event_by_key(conn, idempotency_key)
            if row is None:
                return None
            if row["aggregate_type"] != "mission" or row["aggregate_id"] != mission_id:
                raise ContinuityStoreError("idempotency_key 已用于其他聚合对象")
            if not str(row["event_type"]).startswith("ORCHESTRATION_"):
                raise ContinuityStoreError("idempotency_key 不属于编排事件")
            return self._decode_orchestration_outcome(row["payload_json"])

    def list_orchestration_outcomes(self, mission_id: str) -> tuple[OrchestrationOutcome, ...]:
        """Load append-only A3 outcomes in their original causal order."""
        with self._read_connection() as conn:
            self._get_mission(conn, mission_id)
            rows = conn.execute(
                """SELECT payload_json FROM events
                WHERE aggregate_type='mission' AND aggregate_id=?
                AND event_type LIKE 'ORCHESTRATION_%' ORDER BY rowid""",
                (mission_id,),
            ).fetchall()
        return tuple(self._decode_orchestration_outcome(row[0]) for row in rows)

    def record_orchestration_outcome(
        self,
        outcome: OrchestrationOutcome,
        idempotency_key: str,
        now: str,
    ) -> OrchestrationOutcome:
        """Append one replayable orchestration outcome on the owning Mission aggregate."""
        with self._transaction() as conn:
            existing = self._event_by_key(conn, idempotency_key)
            if existing is not None:
                if (
                    existing["aggregate_type"] != "mission"
                    or existing["aggregate_id"] != outcome.mission_id
                ):
                    raise ContinuityStoreError("idempotency_key 已用于其他聚合对象")
                if not str(existing["event_type"]).startswith("ORCHESTRATION_"):
                    raise ContinuityStoreError("idempotency_key 不属于编排事件")
                return self._decode_orchestration_outcome(existing["payload_json"])
            self._get_mission(conn, outcome.mission_id)
            self._append_event(
                conn,
                outcome.mission_id,
                f"ORCHESTRATION_{outcome.action.value}",
                outcome.model_dump(mode="json"),
                idempotency_key,
                now,
                aggregate_type="mission",
            )
            return outcome

    def get_work(self, work_id: str) -> WorkItem:
        with self._read_connection() as conn:
            return self._get_work(conn, work_id)

    def get_mission(self, mission_id: str) -> Mission:
        with self._read_connection() as conn:
            return self._get_mission(conn, mission_id)

    @staticmethod
    def _lexical_run_worktree(raw: object, *, base: Path | None = None) -> str:
        if not isinstance(raw, str) or raw != raw.strip() or not raw:
            raise ContinuityStoreError("Run worktree_path 必须是规范非空路径")
        raw_segments = raw.replace("\\", "/").split("/")
        if any(part in {".", ".."} for part in raw_segments):
            raise ContinuityStoreError("Run worktree_path 包含非 canonical 点路径段")
        candidate = Path(raw)
        if not candidate.is_absolute():
            if base is None:
                raise ContinuityStoreError("Run worktree_path 必须是绝对路径")
            candidate = base / candidate
        normalized = Path(os.path.abspath(os.path.normpath(str(candidate))))
        if any(part != part.rstrip(" .") for part in normalized.parts):
            raise ContinuityStoreError("Run worktree_path 包含非法路径段")
        return str(normalized)

    def _canonical_run_worktree(self, raw: object) -> str:
        lexical = self._lexical_run_worktree(raw, base=self.workspace_root)
        try:
            return str(Path(lexical).resolve(strict=True))
        except (OSError, RuntimeError) as error:
            raise ContinuityStoreError("Run worktree_path 无法解析") from error

    @staticmethod
    def _validated_idempotency_key(raw: object) -> str:
        if (
            not isinstance(raw, str)
            or raw != raw.strip()
            or not 1 <= len(raw) <= 255
            or any(not character.isprintable() for character in raw)
        ):
            raise ContinuityStoreError("idempotency_key 必须是 1 到 255 个 canonical 可打印字符")
        return raw

    @staticmethod
    def _validated_run_text(raw: object, *, label: str) -> str:
        if (
            not isinstance(raw, str)
            or raw != raw.strip()
            or not raw
            or any(not character.isprintable() for character in raw)
        ):
            raise ContinuityStoreError(f"Run {label} 必须是 canonical 非空可打印文本")
        return raw

    @classmethod
    def _validated_run_creation_inputs(
        cls,
        *,
        run_id: object,
        work_id: object,
        executor_id: object,
        adapter: object,
        owned_paths: object,
        declared_dirty_paths: object,
        git_head: object | None,
        lease_token: object,
        lease_seconds: object,
    ) -> tuple[str, str, str, str, tuple[str, ...], tuple[str, ...], str | None, str, int]:
        canonical_run_id = cls._validated_run_text(run_id, label="run_id")
        canonical_work_id = cls._validated_run_text(work_id, label="work_id")
        canonical_executor = cls._validated_run_text(executor_id, label="executor_id")
        canonical_adapter = cls._validated_run_text(adapter, label="adapter")
        canonical_owned = cls._run_paths(owned_paths, label="owned_paths", allow_empty=False)
        canonical_declared = cls._run_paths(
            declared_dirty_paths,
            label="declared_dirty_paths",
            allow_empty=True,
        )
        if not all(
            cls._authority_path_covered(path, canonical_owned) for path in canonical_declared
        ):
            raise ContinuityStoreError("declared_dirty_paths 超出 owned_paths")
        canonical_head: str | None = None
        if git_head is not None:
            canonical_head = cls._validated_run_text(git_head, label="git_head")
            if _FULL_GIT_COMMIT.fullmatch(canonical_head) is None:
                raise ContinuityStoreError("Run git_head 必须是完整小写 Git commit OID")
        canonical_token = cls._validated_run_text(lease_token, label="lease_token")
        if type(lease_seconds) is not int or not 60 <= lease_seconds <= 86_400:
            raise ContinuityStoreError("lease_seconds 必须在 60 到 86400 之间")
        return (
            canonical_run_id,
            canonical_work_id,
            canonical_executor,
            canonical_adapter,
            canonical_owned,
            canonical_declared,
            canonical_head,
            canonical_token,
            lease_seconds,
        )

    @staticmethod
    def _run_creation_request(
        *,
        run_id: str,
        work_id: str,
        executor_id: str,
        adapter: str,
        owned_paths: tuple[str, ...],
        declared_dirty_paths: tuple[str, ...],
        observed_dirty_paths: tuple[str, ...],
        git_head: str,
        worktree_path: str,
        lease_seconds: int,
    ) -> dict[str, object]:
        return {
            "run_id": run_id,
            "work_id": work_id,
            "executor_id": executor_id,
            "adapter": adapter,
            "owned_paths": list(owned_paths),
            "declared_dirty_paths": list(declared_dirty_paths),
            "observed_dirty_paths": list(observed_dirty_paths),
            "git_head": git_head,
            "worktree_path": worktree_path,
            "lease_seconds": lease_seconds,
        }

    @staticmethod
    def _run_creation_request_hash(request: dict[str, object]) -> str:
        return hashlib.sha256(
            json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _lease_token_fingerprint(lease_token: str) -> str:
        return hashlib.sha256(
            b"auto-pm/run-lease-token/v1\0" + lease_token.encode("utf-8")
        ).hexdigest()

    def run_creation_replay(
        self,
        *,
        run_id: str,
        work_id: str,
        executor_id: str,
        adapter: str,
        owned_paths: tuple[str, ...],
        declared_dirty_paths: tuple[str, ...],
        observed_dirty_paths: tuple[str, ...],
        git_head: str,
        worktree_path: str,
        lease_token: str,
        lease_seconds: int,
        idempotency_key: str,
    ) -> RunItem | None:
        """Replay an exact Run start without consulting mutable Git/lease time facts."""

        idempotency_key = self._validated_idempotency_key(idempotency_key)
        (
            run_id,
            work_id,
            executor_id,
            adapter,
            owned_paths,
            declared_dirty_paths,
            validated_head,
            lease_token,
            lease_seconds,
        ) = self._validated_run_creation_inputs(
            run_id=run_id,
            work_id=work_id,
            executor_id=executor_id,
            adapter=adapter,
            owned_paths=owned_paths,
            declared_dirty_paths=declared_dirty_paths,
            git_head=git_head,
            lease_token=lease_token,
            lease_seconds=lease_seconds,
        )
        assert validated_head is not None
        observed_dirty_paths = self._run_paths(
            observed_dirty_paths,
            label="observed_dirty_paths",
            allow_empty=True,
        )
        if not all(
            self._authority_path_covered(path, declared_dirty_paths)
            for path in observed_dirty_paths
        ):
            raise ContinuityStoreError("存在未声明的 dirty path")
        canonical_worktree = self._lexical_run_worktree(
            worktree_path,
            base=self.workspace_root,
        )
        request = self._run_creation_request(
            run_id=run_id,
            work_id=work_id,
            executor_id=executor_id,
            adapter=adapter,
            owned_paths=owned_paths,
            declared_dirty_paths=declared_dirty_paths,
            observed_dirty_paths=observed_dirty_paths,
            git_head=validated_head,
            worktree_path=canonical_worktree,
            lease_seconds=lease_seconds,
        )
        request_hash = self._run_creation_request_hash(request)
        with self._read_connection() as conn:
            return self._run_creation_replay(
                conn,
                run_id=run_id,
                executor_id=executor_id,
                lease_token=lease_token,
                request=request,
                request_hash=request_hash,
                idempotency_key=idempotency_key,
            )

    def run_creation_intent_replay(
        self,
        *,
        run_id: str,
        work_id: str,
        executor_id: str,
        adapter: str,
        owned_paths: tuple[str, ...],
        declared_dirty_paths: tuple[str, ...],
        worktree_path: str,
        lease_token: str,
        lease_seconds: int,
        idempotency_key: str,
    ) -> RunItem | None:
        """Replay CLI user intent while ignoring newly observed Git snapshot facts."""

        idempotency_key = self._validated_idempotency_key(idempotency_key)
        (
            run_id,
            work_id,
            executor_id,
            adapter,
            owned_paths,
            declared_dirty_paths,
            _validated_head,
            lease_token,
            lease_seconds,
        ) = self._validated_run_creation_inputs(
            run_id=run_id,
            work_id=work_id,
            executor_id=executor_id,
            adapter=adapter,
            owned_paths=owned_paths,
            declared_dirty_paths=declared_dirty_paths,
            git_head=None,
            lease_token=lease_token,
            lease_seconds=lease_seconds,
        )
        canonical_worktree = self._lexical_run_worktree(
            worktree_path,
            base=self.workspace_root,
        )
        expected_intent = {
            "run_id": run_id,
            "work_id": work_id,
            "executor_id": executor_id,
            "adapter": adapter,
            "owned_paths": list(owned_paths),
            "declared_dirty_paths": list(declared_dirty_paths),
            "worktree_path": canonical_worktree,
            "lease_seconds": lease_seconds,
        }
        with self._read_connection() as conn:
            row = self._event_by_key(conn, idempotency_key)
            if row is None:
                return None
            try:
                payload = json.loads(str(row["payload_json"]))
            except (TypeError, json.JSONDecodeError) as error:
                raise ContinuityStoreError("Run 创建事件 payload 无法读取") from error
            if not isinstance(payload, dict):
                raise ContinuityStoreError("Run 创建事件 payload 顶层必须是对象")
            recorded_request: dict[str, object]
            recorded_hash: str
            if set(payload) == _LEGACY_RUN_CREATION_FIELDS:
                recorded_request = self._legacy_run_creation_request_from_payload(
                    payload,
                    lease_seconds=lease_seconds,
                )
                recorded_hash = self._run_creation_request_hash(recorded_request)
            else:
                request_value = payload.get("request")
                hash_value = payload.get("request_hash")
                if not isinstance(request_value, dict) or not isinstance(hash_value, str):
                    raise ContinuityStoreError("Run 创建事件 request 无法读取")
                recorded_request = cast(dict[str, object], request_value)
                recorded_hash = hash_value
            replay = self._run_creation_replay(
                conn,
                run_id=run_id,
                executor_id=executor_id,
                lease_token=lease_token,
                request=recorded_request,
                request_hash=recorded_hash,
                idempotency_key=idempotency_key,
            )
            recorded_intent = {key: recorded_request.get(key) for key in expected_intent}
            if recorded_intent != expected_intent:
                raise ContinuityStoreError("idempotency_key 的 Run 创建用户意图不一致")
            return replay

    def create_run(
        self,
        values: dict[str, Any],
        lease: dict[str, Any],
        observed_dirty_paths: tuple[str, ...],
        lease_seconds: int,
        idempotency_key: str,
    ) -> RunItem:
        idempotency_key = self._validated_idempotency_key(idempotency_key)
        try:
            raw_owned_paths = json.loads(str(values.get("owned_paths_json")))
            raw_declared_dirty_paths = json.loads(str(values.get("declared_dirty_paths_json")))
        except (TypeError, json.JSONDecodeError) as error:
            raise ContinuityStoreError("Run path authority JSON 无法读取") from error
        (
            run_id,
            work_id,
            executor_id,
            adapter,
            owned_paths,
            declared_dirty_paths,
            git_head,
            lease_token,
            lease_seconds,
        ) = self._validated_run_creation_inputs(
            run_id=values.get("run_id"),
            work_id=values.get("work_id"),
            executor_id=values.get("executor_id"),
            adapter=values.get("adapter"),
            owned_paths=raw_owned_paths,
            declared_dirty_paths=raw_declared_dirty_paths,
            git_head=values.get("git_head"),
            lease_token=lease.get("lease_token"),
            lease_seconds=lease_seconds,
        )
        assert git_head is not None
        observed_paths = self._run_paths(
            observed_dirty_paths,
            label="observed_dirty_paths",
            allow_empty=True,
        )
        if not all(
            self._authority_path_covered(path, declared_dirty_paths) for path in observed_paths
        ):
            raise ContinuityStoreError("存在未声明的 dirty path")
        if lease.get("run_id") != run_id:
            raise ContinuityStoreError("Run 与 lease 身份不一致")
        if lease.get("owner_id") != executor_id:
            raise ContinuityStoreError("Run executor 与 lease owner 不一致")
        if lease.get("version") != 1:
            raise ContinuityStoreError("新 lease 初始版本必须是 1")
        canonical_worktree = self._canonical_run_worktree(values.get("worktree_path"))
        request = self._run_creation_request(
            run_id=run_id,
            work_id=work_id,
            executor_id=executor_id,
            adapter=adapter,
            owned_paths=owned_paths,
            declared_dirty_paths=declared_dirty_paths,
            observed_dirty_paths=observed_paths,
            git_head=git_head,
            worktree_path=canonical_worktree,
            lease_seconds=lease_seconds,
        )
        request_hash = self._run_creation_request_hash(request)
        with self._read_connection() as conn:
            replay = self._run_creation_replay(
                conn,
                run_id=run_id,
                executor_id=executor_id,
                lease_token=lease_token,
                request=request,
                request_hash=request_hash,
                idempotency_key=idempotency_key,
            )
        if replay is not None:
            return replay
        initial_worktree = self._validated_run_snapshot(
            canonical_worktree,
            values.get("git_head"),
            owned_paths,
            declared_dirty_paths,
            observed_paths,
        )
        stored_values = dict(values)
        stored_values.update(
            run_id=run_id,
            work_id=work_id,
            executor_id=executor_id,
            adapter=adapter,
            git_head=git_head,
        )
        stored_values["worktree_path"] = str(initial_worktree)
        stored_values["owned_paths_json"] = json.dumps(owned_paths, ensure_ascii=False)
        stored_values["declared_dirty_paths_json"] = json.dumps(
            declared_dirty_paths,
            ensure_ascii=False,
        )
        with self._transaction() as conn:
            replay = self._run_creation_replay(
                conn,
                run_id=stored_values["run_id"],
                executor_id=stored_values["executor_id"],
                lease_token=lease_token,
                request=request,
                request_hash=request_hash,
                idempotency_key=idempotency_key,
            )
            if replay is not None:
                return replay
            final_worktree = self._validated_run_snapshot(
                stored_values["worktree_path"],
                stored_values["git_head"],
                owned_paths,
                declared_dirty_paths,
                observed_paths,
            )
            if str(final_worktree) != stored_values["worktree_path"]:
                raise ContinuityStoreError("Run worktree canonical identity 发生漂移")
            if stored_values.get("state") != RunState.READY.value:
                raise ContinuityStoreError("新 Run 初始状态必须是 READY")
            if stored_values.get("version") != 1:
                raise ContinuityStoreError("新 Run 初始版本必须是 1")
            existing_run = conn.execute(
                "SELECT 1 FROM run_items WHERE run_id=?",
                (stored_values["run_id"],),
            ).fetchone()
            if existing_run is not None:
                raise ContinuityStoreError("Run 已存在；精确重放必须使用原 idempotency_key")
            observed_at = self._utc_now()
            now = observed_at.isoformat()
            stored_values["created_at"] = now
            stored_values["updated_at"] = now
            work = self._get_work(conn, stored_values["work_id"])
            if work.state not in {WorkState.READY, WorkState.IN_PROGRESS}:
                raise ContinuityStoreError("只有 READY/IN_PROGRESS Work 可以创建 Run")
            if not all(
                self._authority_path_covered(path, work.scope_paths) for path in owned_paths
            ):
                raise ContinuityStoreError("owned_paths 超出 Work scope")
            stored_lease = dict(lease)
            stored_lease["run_id"] = stored_values["run_id"]
            stored_lease["owner_id"] = stored_values["executor_id"]
            stored_lease["lease_token"] = lease_token
            stored_lease["expires_at"] = (
                observed_at + timedelta(seconds=lease_seconds)
            ).isoformat()
            stored_lease["version"] = 1
            stored_lease["updated_at"] = now
            active_sibling = conn.execute(
                """SELECT run_id FROM run_items
                WHERE work_id=? AND run_id<>?
                AND state NOT IN ('SUCCEEDED', 'FAILED', 'CANCELLED')
                LIMIT 1""",
                (stored_values["work_id"], stored_values["run_id"]),
            ).fetchone()
            if active_sibling is not None:
                raise ContinuityStoreError("Work 已有非终态 Run")
            self._insert_mapping(conn, "run_items", stored_values)
            self._insert_mapping(conn, "execution_leases", stored_lease)
            self._append_event(
                conn,
                stored_values["run_id"],
                "RUN_CREATED",
                {
                    "schema_version": "run-created.v2",
                    "request_hash": request_hash,
                    "request": request,
                    "lease_token_sha256": self._lease_token_fingerprint(lease_token),
                    "created_at": now,
                    "lease_expires_at": stored_lease["expires_at"],
                },
                idempotency_key,
                now,
                aggregate_type="run",
            )
            return self._get_run(conn, stored_values["run_id"])

    def transition_run(
        self,
        run_id: str,
        expected_version: int,
        new_state: str,
        idempotency_key: str,
        now: str,
    ) -> RunItem:
        del now
        idempotency_key = self._validated_idempotency_key(idempotency_key)
        run_id = self._validated_run_text(run_id, label="run_id")
        try:
            destination = RunState(new_state)
        except (TypeError, ValueError) as error:
            raise ContinuityStoreError("Run 目标状态非法") from error
        if type(expected_version) is not int or expected_version < 1:
            raise ContinuityStoreError("Run expected_version 必须是正整数")
        with self._transaction() as conn:
            existing = self._event_by_key(conn, idempotency_key)
            if existing is not None:
                try:
                    payload = json.loads(str(existing["payload_json"]))
                except (TypeError, json.JSONDecodeError) as error:
                    raise ContinuityStoreError("Run 迁移事件 payload 无法读取") from error
                if (
                    existing["aggregate_type"] != "run"
                    or existing["aggregate_id"] != run_id
                    or existing["event_type"] != "RUN_TRANSITIONED"
                    or payload
                    != {
                        "schema_version": "run-transition.v2",
                        "expected_version": expected_version,
                        "new_state": destination.value,
                        "result_version": expected_version + 1,
                    }
                ):
                    raise ContinuityStoreError("idempotency_key 的 Run 迁移语义不一致")
                return self._get_run(conn, run_id)
            current = self._get_run(conn, run_id)
            if current.version != expected_version:
                raise ContinuityStoreError("Run 不存在或版本冲突")
            if destination not in _STORE_RUN_TRANSITIONS[current.state]:
                raise ContinuityStoreError(f"非法 Run 状态迁移: {current.state} -> {destination}")
            if destination not in {RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED}:
                sibling = conn.execute(
                    """SELECT run_id FROM run_items
                    WHERE work_id=? AND run_id<>?
                    AND state NOT IN ('SUCCEEDED', 'FAILED', 'CANCELLED')
                    LIMIT 1""",
                    (current.work_id, run_id),
                ).fetchone()
                if sibling is not None:
                    raise ContinuityStoreError("Work 已有其他非终态 Run")
            event_time = self._utc_now().isoformat()
            cursor = conn.execute(
                """UPDATE run_items SET state=?, version=version+1, updated_at=?
                WHERE run_id=? AND version=?""",
                (destination.value, event_time, run_id, expected_version),
            )
            if cursor.rowcount != 1:
                raise ContinuityStoreError("Run 不存在或版本冲突")
            self._append_event(
                conn,
                run_id,
                "RUN_TRANSITIONED",
                {
                    "schema_version": "run-transition.v2",
                    "expected_version": expected_version,
                    "new_state": destination.value,
                    "result_version": expected_version + 1,
                },
                idempotency_key,
                event_time,
                aggregate_type="run",
            )
            return self._get_run(conn, run_id)

    def record_run_started(
        self,
        *,
        run_id: str,
        expected_version: int,
        owner_id: str,
        lease_token: str,
        evidence: ExecutionStartEvidence,
        idempotency_key: str,
    ) -> RunItem:
        """Append safe startup evidence and CAS-transition one READY Run to RUNNING."""

        idempotency_key = self._validated_idempotency_key(idempotency_key)
        run_id = self._validated_run_text(run_id, label="run_id")
        if type(expected_version) is not int or expected_version < 1:
            raise ContinuityStoreError("Run expected_version 必须是正整数")
        if not isinstance(owner_id, str) or not owner_id or owner_id != owner_id.strip():
            raise ContinuityStoreError("启动证据 owner 必须是 canonical 非空文本")
        if not isinstance(lease_token, str) or not lease_token or lease_token != lease_token.strip():
            raise ContinuityStoreError("启动证据 lease_token 必须是 canonical 非空文本")
        request = {
            "schema_version": "run-started.v1",
            "owner_id": owner_id,
            "evidence": evidence.model_dump(mode="json"),
        }
        with self._transaction() as conn:
            existing = self._event_by_key(conn, idempotency_key)
            if existing is not None:
                existing_payload = json.loads(str(existing["payload_json"]))
                if (
                    existing["aggregate_type"] != "run"
                    or existing["aggregate_id"] != run_id
                    or existing["event_type"] != "RUN_STARTED"
                    or {
                        "schema_version": existing_payload.get("schema_version"),
                        "owner_id": existing_payload.get("owner_id"),
                        "evidence": existing_payload.get("evidence"),
                    }
                    != request
                ):
                    raise ContinuityStoreError("idempotency_key 的启动证据语义不一致")
                return self._get_run(conn, run_id)
            payload = {
                **request,
                "expected_version": expected_version,
                "result_version": expected_version + 1,
            }
            current = self._get_run(conn, run_id)
            if current.version != expected_version or current.state is not RunState.READY:
                raise ContinuityStoreError("Run 不存在、非 READY 或版本冲突")
            if current.executor_id != owner_id:
                raise ContinuityStoreError("启动证据 owner 与 Run executor 不一致")
            lease = self._get_lease(conn, run_id)
            if lease.owner_id != owner_id or lease.lease_token != lease_token:
                raise ContinuityStoreError("启动证据 lease ownership 不匹配")
            try:
                expires_at = datetime.fromisoformat(lease.expires_at)
            except ValueError as error:
                raise ContinuityStoreError("启动证据 lease 到期时间非法") from error
            if expires_at.tzinfo is None or expires_at.astimezone(UTC) <= self._utc_now():
                raise ContinuityStoreError("启动证据 lease 已过期")
            event_time = self._utc_now().isoformat()
            cursor = conn.execute(
                """UPDATE run_items SET state=?, version=version+1, updated_at=?
                WHERE run_id=? AND version=? AND state=?""",
                (RunState.RUNNING.value, event_time, run_id, expected_version, RunState.READY.value),
            )
            if cursor.rowcount != 1:
                raise ContinuityStoreError("Run READY 到 RUNNING CAS 失败")
            self._append_event(
                conn,
                run_id,
                "RUN_STARTED",
                payload,
                idempotency_key,
                event_time,
                aggregate_type="run",
            )
            return self._get_run(conn, run_id)

    @staticmethod
    def _expired_run_settlement_request(
        *,
        target_run_id: str,
        recovery_run_id: str,
        recovery_owner_id: str,
        decision_id: str,
        outcome: str,
        reason: str,
    ) -> dict[str, object]:
        """Build the caller-owned settlement request; derived authority facts stay separate."""

        return {
            "schema_version": "expired-run-settlement-request.v2",
            "action": "settle_expired_run",
            "target_run_id": target_run_id,
            "recovery_run_id": recovery_run_id,
            "recovery_owner_id": recovery_owner_id,
            "decision_id": decision_id,
            "outcome": outcome,
            "reason": reason,
        }

    @staticmethod
    def _settlement_request_hash(request: dict[str, object]) -> str:
        canonical = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _validated_settlement_text(*, reason: object, idempotency_key: object) -> tuple[str, str]:
        if not isinstance(reason, str):
            raise ContinuityStoreError("结算原因类型非法")
        normalized_reason = reason.strip()
        if (
            reason != normalized_reason
            or not normalized_reason
            or len(normalized_reason) > 1000
            or any(not character.isprintable() for character in normalized_reason)
        ):
            raise ContinuityStoreError("结算原因必须是 1 到 1000 个字符的规范文本")
        if not isinstance(idempotency_key, str):
            raise ContinuityStoreError("idempotency_key 类型非法")
        normalized_key = idempotency_key.strip()
        if (
            idempotency_key != normalized_key
            or not normalized_key
            or len(normalized_key) > 255
            or any(not character.isprintable() for character in normalized_key)
        ):
            raise ContinuityStoreError("idempotency_key 必须是 1 到 255 个字符的规范文本")
        return normalized_reason, normalized_key

    @classmethod
    def _validated_settlement_caller_inputs(
        cls,
        *,
        target_run_id: object,
        recovery_run_id: object,
        recovery_owner_id: object,
        recovery_lease_token: object,
        decision_id: object,
        outcome: object,
        reason: object,
        idempotency_key: object,
    ) -> tuple[str, str, str, str, str, str, str, str]:
        reason, idempotency_key = cls._validated_settlement_text(
            reason=reason,
            idempotency_key=idempotency_key,
        )
        labels = (
            ("目标 Run", target_run_id),
            ("恢复 Run", recovery_run_id),
            ("恢复 owner", recovery_owner_id),
            ("Decision", decision_id),
        )
        for label, value in labels:
            if (
                not isinstance(value, str)
                or value != value.strip()
                or not 1 <= len(value) <= 255
                or any(not character.isprintable() for character in value)
            ):
                raise ContinuityStoreError(f"{label} 必须是 canonical 非空可打印文本")
        canonical_target_run_id = cast(str, target_run_id)
        canonical_recovery_run_id = cast(str, recovery_run_id)
        canonical_recovery_owner_id = cast(str, recovery_owner_id)
        canonical_decision_id = cast(str, decision_id)
        if (
            not isinstance(recovery_lease_token, str)
            or recovery_lease_token != recovery_lease_token.strip()
            or not 1 <= len(recovery_lease_token) <= 1000
            or any(not character.isprintable() for character in recovery_lease_token)
        ):
            raise ContinuityStoreError("恢复 lease token 必须是 canonical 非空可打印文本")
        if not isinstance(outcome, str) or outcome != RunState.CANCELLED.value:
            raise ContinuityStoreError("过期 Run 只能前向结算为 CANCELLED")
        if not is_canonical_decision_id(canonical_decision_id):
            raise ContinuityStoreError("运行态结算 Decision ID 必须是 canonical")
        if canonical_target_run_id == canonical_recovery_run_id:
            raise ContinuityStoreError("目标 Run 与恢复 Run 必须不同")
        if recovery_lease_token in reason:
            raise ContinuityStoreError("结算原因不得包含恢复 lease token")
        return (
            canonical_target_run_id,
            canonical_recovery_run_id,
            canonical_recovery_owner_id,
            recovery_lease_token,
            canonical_decision_id,
            outcome,
            reason,
            idempotency_key,
        )

    def expired_run_settlement_replay(
        self,
        *,
        target_run_id: str,
        recovery_run_id: str,
        recovery_owner_id: str,
        recovery_lease_token: str,
        decision_id: str,
        outcome: str,
        reason: str,
        idempotency_key: str,
    ) -> RunItem | None:
        """Replay a durable receipt before consulting any mutable authority facts."""

        (
            target_run_id,
            recovery_run_id,
            recovery_owner_id,
            recovery_lease_token,
            decision_id,
            outcome,
            reason,
            idempotency_key,
        ) = self._validated_settlement_caller_inputs(
            target_run_id=target_run_id,
            recovery_run_id=recovery_run_id,
            recovery_owner_id=recovery_owner_id,
            recovery_lease_token=recovery_lease_token,
            decision_id=decision_id,
            outcome=outcome,
            reason=reason,
            idempotency_key=idempotency_key,
        )
        request = self._expired_run_settlement_request(
            target_run_id=target_run_id,
            recovery_run_id=recovery_run_id,
            recovery_owner_id=recovery_owner_id,
            decision_id=decision_id,
            outcome=outcome,
            reason=reason,
        )
        request_hash = self._settlement_request_hash(request)
        with self._read_connection() as conn:
            return self._expired_run_settlement_replay(
                conn,
                recovery_lease_token=recovery_lease_token,
                request=request,
                request_hash=request_hash,
                idempotency_key=idempotency_key,
            )

    def settle_expired_run(
        self,
        *,
        target_run_id: str,
        expected_target_state: str,
        expected_target_version: int,
        expected_target_lease_version: int,
        expected_target_work_id: str,
        expected_target_work_version: int,
        expected_target_work_scope_hash: str,
        recovery_run_id: str,
        expected_recovery_run_version: int,
        recovery_work_id: str,
        expected_recovery_work_version: int,
        expected_recovery_work_scope_hash: str,
        expected_recovery_owned_paths_hash: str,
        expected_recovery_git_head: str,
        recovery_owner_id: str,
        recovery_lease_token: str,
        expected_recovery_lease_version: int,
        target_decision_id: str,
        target_decision_sha256: str,
        target_change_id: str,
        decision_id: str,
        decision_sha256: str,
        decision_change_id: str,
        decision_project_id: str,
        decision_approved_paths: tuple[str, ...],
        runtime_target_path: str,
        outcome: str,
        reason: str,
        idempotency_key: str,
    ) -> RunItem:
        """Atomically settle one abandoned Run without rewriting its forensic lease."""

        (
            target_run_id,
            recovery_run_id,
            recovery_owner_id,
            recovery_lease_token,
            decision_id,
            outcome,
            reason,
            idempotency_key,
        ) = self._validated_settlement_caller_inputs(
            target_run_id=target_run_id,
            recovery_run_id=recovery_run_id,
            recovery_owner_id=recovery_owner_id,
            recovery_lease_token=recovery_lease_token,
            decision_id=decision_id,
            outcome=outcome,
            reason=reason,
            idempotency_key=idempotency_key,
        )
        self._validate_recovery_git_head(expected_recovery_git_head)
        self._validate_settlement_authority_identity(
            target_decision_id=target_decision_id,
            target_decision_sha256=target_decision_sha256,
            target_change_id=target_change_id,
            decision_id=decision_id,
            decision_sha256=decision_sha256,
            decision_change_id=decision_change_id,
            decision_project_id=decision_project_id,
        )
        request = self._expired_run_settlement_request(
            target_run_id=target_run_id,
            recovery_run_id=recovery_run_id,
            recovery_owner_id=recovery_owner_id,
            decision_id=decision_id,
            outcome=outcome,
            reason=reason,
        )
        request_hash = self._settlement_request_hash(request)
        actual_runtime_target = self.runtime_target_path()
        if self._authority_path_key(runtime_target_path) != self._authority_path_key(
            actual_runtime_target
        ):
            raise ContinuityStoreError("结算运行态目标与实际 Continuity Store 不一致")
        with self._transaction() as conn:
            replay = self._expired_run_settlement_replay(
                conn,
                recovery_lease_token=recovery_lease_token,
                request=request,
                request_hash=request_hash,
                idempotency_key=idempotency_key,
            )
            if replay is not None:
                return replay
            observed_at = self._utc_now()
            event_time = observed_at.isoformat()
            if target_run_id == recovery_run_id:
                raise ContinuityStoreError("目标 Run 与恢复 Run 必须不同")
            if outcome != RunState.CANCELLED.value:
                raise ContinuityStoreError("过期 Run 只能前向结算为 CANCELLED")

            target = self._get_run(conn, target_run_id)
            target_lease = self._get_lease(conn, target_run_id)
            recovery = self._get_run(conn, recovery_run_id)
            recovery_lease = self._get_lease(conn, recovery_run_id)
            recovery_work = self._get_work(conn, recovery_work_id)
            target_work = self._get_work(conn, target.work_id)

            if target.work_id == recovery.work_id:
                raise ContinuityStoreError("目标 Run 与恢复 Run 必须属于独立 Work")
            if target.work_id != expected_target_work_id:
                raise ContinuityStoreError("目标 Run 的 Work lineage 发生漂移")
            if target_work.version != expected_target_work_version:
                raise ContinuityStoreError("目标 Work 版本冲突")
            actual_target_scope_hash = self.authority_paths_hash(target_work.scope_paths)
            if (
                target_work.scope_hash != actual_target_scope_hash
                or actual_target_scope_hash != expected_target_work_scope_hash
            ):
                raise ContinuityStoreError("目标 Work scope 事实或哈希冲突")
            terminal = {RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED}
            if target.state in terminal:
                raise ContinuityStoreError("目标 Run 已处于终态")
            if (
                target.state.value != expected_target_state
                or target.version != expected_target_version
            ):
                raise ContinuityStoreError("目标 Run 状态或版本冲突")
            if target_lease.version != expected_target_lease_version:
                raise ContinuityStoreError("目标 Run lease 版本冲突")
            if self._aware_timestamp(target_lease.expires_at, "目标 Run lease") > observed_at:
                raise ContinuityStoreError("目标 Run lease 尚未过期")

            if recovery.state is not RunState.RUNNING:
                raise ContinuityStoreError("恢复 Run 必须处于 RUNNING")
            if recovery.version != expected_recovery_run_version:
                raise ContinuityStoreError("恢复 Run 版本冲突")
            if recovery.git_head != expected_recovery_git_head:
                raise ContinuityStoreError("恢复 Run git_head 事实发生漂移")
            try:
                recovery_worktree = Path(recovery.worktree_path).resolve(strict=True)
            except OSError as error:
                raise ContinuityStoreError("恢复 Run worktree_path 无法规范化") from error
            if recovery_worktree != self.workspace_root:
                raise ContinuityStoreError("运行库行政结算的恢复 Run 必须位于控制根主工作树")
            if recovery.work_id != recovery_work_id:
                raise ContinuityStoreError("恢复 Run 与恢复 Work 不匹配")
            if recovery_work.version != expected_recovery_work_version:
                raise ContinuityStoreError("恢复 Work 版本冲突")
            actual_scope_hash = self.authority_paths_hash(recovery_work.scope_paths)
            if (
                recovery_work.scope_hash != actual_scope_hash
                or actual_scope_hash != expected_recovery_work_scope_hash
            ):
                raise ContinuityStoreError("恢复 Work scope 事实或哈希冲突")
            actual_owned_paths_hash = self.authority_paths_hash(recovery.owned_paths)
            if actual_owned_paths_hash != expected_recovery_owned_paths_hash:
                raise ContinuityStoreError("恢复 Run owned_paths 事实冲突")
            if recovery_work.read_only or recovery_work.state is not WorkState.IN_PROGRESS:
                raise ContinuityStoreError("恢复 Work 必须是 IN_PROGRESS 写入型 Work")
            if target_work.read_only or not is_canonical_decision_id(target_work.authorization_ref):
                raise ContinuityStoreError("目标 Work 必须绑定 canonical immutable Decision")
            if not is_canonical_decision_id(recovery_work.authorization_ref):
                raise ContinuityStoreError("恢复 Work 必须绑定 canonical immutable Decision")
            if recovery_work.authorization_ref != decision_id:
                raise ContinuityStoreError("恢复 Work 未绑定指定 Decision")
            if target_work.authorization_ref != target_decision_id:
                raise ContinuityStoreError("目标 Work 的 Decision 授权事实发生漂移")
            if target_decision_id == decision_id:
                raise ContinuityStoreError("恢复 Decision 不得复用目标 Work 的授权链")
            target_decision, recovery_decision = self._decision_git_snapshots(
                recovery_git_head=recovery.git_head,
                target_decision_id=target_decision_id,
                target_decision_sha256=target_decision_sha256,
                recovery_decision_id=decision_id,
                recovery_decision_sha256=decision_sha256,
                require_current_head=True,
            )
            if target_decision.change_id != target_change_id:
                raise ContinuityStoreError("目标 Decision immutable snapshot 发生漂移")
            if target_decision.decision_conclusion not in {
                "approved",
                "conditionally_approved",
            }:
                raise ContinuityStoreError("目标 Work 的原 Decision 未批准")
            if recovery_decision.change_id != decision_change_id:
                raise ContinuityStoreError("恢复 Decision immutable snapshot 发生漂移")
            capability = recovery_decision.runtime_capability
            if (
                recovery_decision.decision_conclusion != "approved"
                or recovery_decision.conditions
                or capability is None
                or RuntimeDecisionAction.SETTLE_EXPIRED_RUN
                not in capability.allowed_runtime_actions
                or target_run_id not in capability.target_run_ids
                or RuntimeDecisionOutcome.CANCELLED not in capability.allowed_outcomes
            ):
                raise ContinuityStoreError("恢复 Decision 未提供有效的无条件结算 capability")
            if target_decision.change_id == recovery_decision.change_id:
                raise ContinuityStoreError("恢复 CHG 必须独立于目标 Work 的原 CHG")
            if (
                recovery_work.subject_project_id != decision_project_id
                or target_work.subject_project_id != decision_project_id
                or recovery_decision.project_id != decision_project_id
                or target_decision.project_id != decision_project_id
            ):
                raise ContinuityStoreError("目标/恢复 Work 与 Decision 项目事实不一致")
            target_approved_paths = tuple(
                dict.fromkeys(
                    self._normalize_authority_path(path) for path in target_decision.approved_files
                )
            )
            actual_recovery_approved_paths = tuple(
                dict.fromkeys(
                    self._normalize_authority_path(path)
                    for path in recovery_decision.approved_files
                )
            )
            if actual_recovery_approved_paths != decision_approved_paths:
                raise ContinuityStoreError("恢复 Decision approved_files 事实发生漂移")
            if not all(
                self._authority_path_covered(path, target_approved_paths)
                for path in target_work.scope_paths
            ):
                raise ContinuityStoreError("目标 Work scope 超出原 Decision approved_files")
            if not all(
                self._authority_path_covered(path, actual_recovery_approved_paths)
                for path in recovery_work.scope_paths
            ):
                raise ContinuityStoreError("恢复 Work scope 超出 Decision approved_files")
            if not all(
                self._authority_path_covered(path, recovery_work.scope_paths)
                for path in recovery.owned_paths
            ):
                raise ContinuityStoreError("恢复 Run owned_paths 超出恢复 Work scope")
            if not self._authority_path_covered(actual_runtime_target, decision_approved_paths):
                raise ContinuityStoreError("Decision 未覆盖 canonical continuity.db")
            if not self._authority_path_covered(actual_runtime_target, recovery_work.scope_paths):
                raise ContinuityStoreError("恢复 Work scope 未覆盖 canonical continuity.db")
            if not self._authority_path_covered(actual_runtime_target, recovery.owned_paths):
                raise ContinuityStoreError("恢复 Run owned_paths 未覆盖 canonical continuity.db")
            if (
                recovery_lease.version != expected_recovery_lease_version
                or recovery_lease.owner_id != recovery_owner_id
                or recovery_lease.lease_token != recovery_lease_token
            ):
                raise ContinuityStoreError("恢复 lease owner、token 或版本冲突")
            if self._aware_timestamp(recovery_lease.expires_at, "恢复 Run lease") <= observed_at:
                raise ContinuityStoreError("恢复 Run lease 已过期")

            cursor = conn.execute(
                """UPDATE run_items SET state=?, version=version+1, updated_at=?
                WHERE run_id=? AND state=? AND version=?""",
                (
                    outcome,
                    event_time,
                    target_run_id,
                    expected_target_state,
                    expected_target_version,
                ),
            )
            if cursor.rowcount != 1:
                raise ContinuityStoreError("目标 Run CAS 冲突")
            payload = {
                "schema_version": "expired-run-settlement.v2",
                "request_hash": request_hash,
                "request": request,
                "recovery_token_sha256": self._lease_token_fingerprint(recovery_lease_token),
                "runtime_target_path": actual_runtime_target,
                "outcome": outcome,
                "reason": reason,
                "target": {
                    "run_id": target.run_id,
                    "work_id": target_work.work_id,
                    "work_version": target_work.version,
                    "work_scope_hash": actual_target_scope_hash,
                    "previous_state": target.state.value,
                    "previous_version": target.version,
                    "settled_state": outcome,
                    "settled_version": target.version + 1,
                    "lease_version": target_lease.version,
                    "lease_expires_at": target_lease.expires_at,
                },
                "recovery": {
                    "run_id": recovery.run_id,
                    "run_version": recovery.version,
                    "work_id": recovery_work.work_id,
                    "work_version": recovery_work.version,
                    "work_scope_hash": recovery_work.scope_hash,
                    "owned_paths_hash": actual_owned_paths_hash,
                    "lease_version": recovery_lease.version,
                    "owner_id": recovery_lease.owner_id,
                    "git_head": recovery.git_head,
                },
                "authority": {
                    "project_id": decision_project_id,
                    "target": {
                        "decision_id": target_decision_id,
                        "decision_sha256": target_decision_sha256,
                        "change_id": target_change_id,
                    },
                    "recovery": {
                        "decision_id": decision_id,
                        "decision_sha256": decision_sha256,
                        "change_id": decision_change_id,
                    },
                },
            }
            self._append_event(
                conn,
                target_run_id,
                "RUN_EXPIRED_SETTLED",
                payload,
                idempotency_key,
                event_time,
                aggregate_type="run",
            )
            return self._get_run(conn, target_run_id)

    def renew_lease(
        self,
        run_id: str,
        owner_id: str,
        lease_token: str,
        lease_seconds: int,
        idempotency_key: str,
    ) -> LeaseItem:
        run_id = self._validated_run_text(run_id, label="run_id")
        owner_id = self._validated_run_text(owner_id, label="lease owner")
        lease_token = self._validated_run_text(lease_token, label="lease token")
        idempotency_key = self._validated_idempotency_key(idempotency_key)
        if type(lease_seconds) is not int or not 60 <= lease_seconds <= 86_400:
            raise ContinuityStoreError("lease_seconds 必须在 60 到 86400 之间")
        request = {
            "schema_version": "lease-renew-request.v2",
            "run_id": run_id,
            "owner_id": owner_id,
            "lease_seconds": lease_seconds,
            "lease_token_sha256": self._lease_token_fingerprint(lease_token),
        }
        with self._transaction() as conn:
            existing = self._event_by_key(conn, idempotency_key)
            if existing is not None:
                payload = self._validated_event_payload(existing, label="lease 续租")
                if (
                    existing["aggregate_type"] != "run"
                    or existing["aggregate_id"] != run_id
                    or existing["event_type"] != "LEASE_RENEWED"
                    or not isinstance(payload, dict)
                    or set(payload) != {"schema_version", "request", "expires_at", "version"}
                    or payload.get("schema_version") != "lease-renewed.v2"
                    or payload.get("request") != request
                ):
                    raise ContinuityStoreError("idempotency_key 的 lease 续租语义不一致")
                return self._get_lease(conn, run_id)
            observed_at = self._utc_now()
            current = self._get_lease(conn, run_id)
            if current.owner_id != owner_id or current.lease_token != lease_token:
                raise ContinuityStoreError("lease ownership 不匹配")
            if self._aware_timestamp(current.expires_at, "lease") <= observed_at:
                raise ContinuityStoreError("lease 已过期")
            expires_at = (observed_at + timedelta(seconds=lease_seconds)).isoformat()
            event_time = observed_at.isoformat()
            cursor = conn.execute(
                """UPDATE execution_leases SET expires_at=?, version=version+1, updated_at=?
                WHERE run_id=? AND owner_id=? AND lease_token=? AND version=?""",
                (
                    expires_at,
                    event_time,
                    run_id,
                    owner_id,
                    lease_token,
                    current.version,
                ),
            )
            if cursor.rowcount != 1:
                raise ContinuityStoreError("lease owner、token 或版本冲突")
            self._append_event(
                conn,
                run_id,
                "LEASE_RENEWED",
                {
                    "schema_version": "lease-renewed.v2",
                    "request": request,
                    "expires_at": expires_at,
                    "version": current.version + 1,
                },
                idempotency_key,
                event_time,
                aggregate_type="run",
            )
            return self._get_lease(conn, run_id)

    def transfer_lease(
        self,
        handoff_id: str,
        receiver_id: str,
        new_token: str,
        lease_seconds: int,
        idempotency_key: str,
    ) -> LeaseItem:
        handoff_id = self._validated_run_text(handoff_id, label="handoff_id")
        receiver_id = self._validated_run_text(receiver_id, label="receiver_id")
        new_token = self._validated_run_text(new_token, label="new lease token")
        idempotency_key = self._validated_idempotency_key(idempotency_key)
        if type(lease_seconds) is not int or not 60 <= lease_seconds <= 86_400:
            raise ContinuityStoreError("lease_seconds 必须在 60 到 86400 之间")
        request = {
            "schema_version": "lease-transfer-request.v2",
            "handoff_id": handoff_id,
            "receiver_id": receiver_id,
            "lease_seconds": lease_seconds,
            "new_token_sha256": self._lease_token_fingerprint(new_token),
        }
        with self._transaction() as conn:
            existing = self._event_by_key(conn, idempotency_key)
            if existing is not None:
                payload = self._validated_event_payload(existing, label="lease 移交")
                if (
                    existing["aggregate_type"] != "run"
                    or existing["event_type"] != "LEASE_TRANSFERRED"
                    or not isinstance(payload, dict)
                    or set(payload)
                    != {
                        "schema_version",
                        "request",
                        "run_id",
                        "from_owner",
                        "expires_at",
                        "version",
                    }
                    or payload.get("schema_version") != "lease-transferred.v2"
                    or payload.get("request") != request
                    or existing["aggregate_id"] != payload.get("run_id")
                ):
                    raise ContinuityStoreError("idempotency_key 的 lease 移交语义不一致")
                return self._get_lease(conn, str(payload["run_id"]))
            handoff = self._validated_handoff_receipt(conn, handoff_id)
            if handoff.to_owner != receiver_id:
                raise ContinuityStoreError("接收方与 Handoff to_owner 不一致")
            current = self._get_lease(conn, handoff.run_id)
            observed_at = self._utc_now()
            if current.owner_id != handoff.from_owner:
                raise ContinuityStoreError("Handoff 源 owner 已失去 lease")
            if self._aware_timestamp(current.expires_at, "Handoff lease") <= observed_at:
                raise ContinuityStoreError("Handoff lease 已过期")
            expires_at = (observed_at + timedelta(seconds=lease_seconds)).isoformat()
            event_time = observed_at.isoformat()
            cursor = conn.execute(
                """UPDATE execution_leases
                SET owner_id=?, lease_token=?, expires_at=?, version=version+1, updated_at=?
                WHERE run_id=? AND owner_id=? AND version=?""",
                (
                    receiver_id,
                    new_token,
                    expires_at,
                    event_time,
                    handoff.run_id,
                    handoff.from_owner,
                    current.version,
                ),
            )
            if cursor.rowcount != 1:
                raise ContinuityStoreError("lease transfer owner 或版本冲突")
            self._append_event(
                conn,
                handoff.run_id,
                "LEASE_TRANSFERRED",
                {
                    "schema_version": "lease-transferred.v2",
                    "request": request,
                    "run_id": handoff.run_id,
                    "from_owner": handoff.from_owner,
                    "expires_at": expires_at,
                    "version": current.version + 1,
                },
                idempotency_key,
                event_time,
                aggregate_type="run",
            )
            return self._get_lease(conn, handoff.run_id)

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
        self,
        *,
        handoff_id: str,
        checkpoint_id: str,
        from_owner: str,
        to_owner: str,
        lease_token: str,
        idempotency_key: str,
    ) -> HandoffV2:
        handoff_id = self._validated_run_text(handoff_id, label="handoff_id")
        checkpoint_id = self._validated_run_text(checkpoint_id, label="checkpoint_id")
        from_owner = self._validated_run_text(from_owner, label="from_owner")
        to_owner = self._validated_run_text(to_owner, label="to_owner")
        lease_token = self._validated_run_text(lease_token, label="lease token")
        idempotency_key = self._validated_idempotency_key(idempotency_key)
        if from_owner == to_owner:
            raise ContinuityStoreError("Handoff 接收 owner 必须不同于源 owner")
        request = {
            "schema_version": "handoff-create-request.v2",
            "handoff_id": handoff_id,
            "checkpoint_id": checkpoint_id,
            "from_owner": from_owner,
            "to_owner": to_owner,
        }
        with self._transaction() as conn:
            existing = self._event_by_key(conn, idempotency_key)
            if existing is not None:
                payload = self._validated_event_payload(existing, label="Handoff 创建")
                if (
                    existing["aggregate_type"] != "run"
                    or existing["event_type"] != "HANDOFF_CREATED"
                    or not isinstance(payload, dict)
                    or set(payload)
                    != {
                        "schema_version",
                        "request",
                        "lease_token_sha256",
                        "handoff",
                    }
                    or payload.get("schema_version") != "handoff-created.v2"
                    or payload.get("request") != request
                    or not hmac.compare_digest(
                        str(payload.get("lease_token_sha256")),
                        self._lease_token_fingerprint(lease_token),
                    )
                ):
                    raise ContinuityStoreError("idempotency_key 的 Handoff 创建语义不一致")
                return self._validated_handoff_receipt(conn, handoff_id)
            checkpoint = self._get_checkpoint(conn, checkpoint_id)
            run = self._get_run(conn, checkpoint.run_id)
            lease = self._get_lease(conn, run.run_id)
            observed_at = self._utc_now()
            if lease.owner_id != from_owner or lease.lease_token != lease_token:
                raise ContinuityStoreError("Handoff lease ownership 不匹配")
            if self._aware_timestamp(lease.expires_at, "Handoff lease") <= observed_at:
                raise ContinuityStoreError("Handoff lease 已过期")
            if checkpoint.git_head != run.git_head:
                raise ContinuityStoreError("Handoff checkpoint 与 Run baseline 不一致")
            event_time = observed_at.isoformat()
            unsigned = {
                "handoff_id": handoff_id,
                "work_id": run.work_id,
                "run_id": run.run_id,
                "checkpoint_id": checkpoint.checkpoint_id,
                "from_owner": from_owner,
                "to_owner": to_owner,
                "owned_paths_json": json.dumps(run.owned_paths, ensure_ascii=False),
                "git_head": run.git_head,
                "worktree_path": run.worktree_path,
                "lease_expires_at": lease.expires_at,
                "created_at": event_time,
            }
            canonical = json.dumps(
                unsigned,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            values = {
                **unsigned,
                "snapshot_hash": hashlib.sha256(canonical.encode()).hexdigest(),
            }
            self._insert_mapping(conn, "handoffs_v2", values)
            handoff = self._get_handoff(conn, handoff_id)
            self._append_event(
                conn,
                run.run_id,
                "HANDOFF_CREATED",
                {
                    "schema_version": "handoff-created.v2",
                    "request": request,
                    "lease_token_sha256": self._lease_token_fingerprint(lease_token),
                    "handoff": handoff.model_dump(mode="json"),
                },
                idempotency_key,
                event_time,
                event_id=handoff_id,
                aggregate_type="run",
            )
            return handoff

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

    def list_works(
        self, subject_project_id: str, *, include_terminal: bool = False
    ) -> tuple[WorkItem, ...]:
        """List project Work without changing the default active-work behaviour."""
        with self._read_connection() as conn:
            query = (
                """SELECT work_id FROM work_items WHERE subject_project_id=?
                ORDER BY updated_at DESC, work_id"""
                if include_terminal
                else """SELECT work_id FROM work_items WHERE subject_project_id=?
                AND state NOT IN ('CLOSED', 'CANCELLED') ORDER BY updated_at DESC, work_id"""
            )
            rows = conn.execute(query, (subject_project_id,)).fetchall()
            return tuple(self._get_work(conn, str(row["work_id"])) for row in rows)

    def list_missions(
        self, subject_project_id: str, *, include_terminal: bool = False
    ) -> tuple[Mission, ...]:
        """List project Missions through the immutable reader, including history on request."""
        with self._read_connection() as conn:
            versions = self._schema_versions(conn)
            if not versions.issubset(_KNOWN_SCHEMA_VERSIONS):
                rendered = ", ".join(sorted(versions))
                raise ContinuityStoreError(f"未知或未来 Continuity Store schema: {rendered}")
            if versions == {_LEGACY_SCHEMA_VERSION}:
                # Strict reads must not upgrade a legacy store. It has no Mission table yet.
                return ()
            query = (
                """SELECT mission_id FROM mission_items WHERE subject_project_id=?
                ORDER BY updated_at DESC, mission_id"""
                if include_terminal
                else """SELECT mission_id FROM mission_items WHERE subject_project_id=?
                AND state NOT IN ('ACCEPTED', 'CLOSED', 'CANCELLED')
                ORDER BY updated_at DESC, mission_id"""
            )
            rows = conn.execute(query, (subject_project_id,)).fetchall()
            return tuple(self._get_mission(conn, str(row["mission_id"])) for row in rows)

    def list_active_missions(self, subject_project_id: str) -> tuple[Mission, ...]:
        """Compatibility view for callers that need only live Missions."""
        return self.list_missions(subject_project_id)

    def list_runs(self, work_id: str, *, include_terminal: bool = False) -> tuple[RunItem, ...]:
        """List Work Runs without changing the default active-run behaviour."""
        with self._read_connection() as conn:
            query = (
                """SELECT run_id FROM run_items WHERE work_id=?
                ORDER BY updated_at DESC, run_id"""
                if include_terminal
                else """SELECT run_id FROM run_items WHERE work_id=?
                AND state NOT IN ('SUCCEEDED', 'FAILED', 'CANCELLED')
                ORDER BY updated_at DESC, run_id"""
            )
            rows = conn.execute(query, (work_id,)).fetchall()
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
    def _validated_event_payload(row: sqlite3.Row, *, label: str) -> dict[str, object]:
        try:
            payload = json.loads(str(row["payload_json"]))
        except (TypeError, json.JSONDecodeError) as error:
            raise ContinuityStoreError(f"{label} 事件 payload 无法读取") from error
        if not isinstance(payload, dict):
            raise ContinuityStoreError(f"{label} 事件 payload 顶层必须是对象")
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        expected_hash = hashlib.sha256(
            (
                f"{row['previous_hash']}|{row['aggregate_id']}|{row['event_type']}|"
                f"{canonical}|{row['created_at']}"
            ).encode()
        ).hexdigest()
        if row["event_hash"] != expected_hash or (
            row["event_id"] != f"EVT-{expected_hash[:16].upper()}"
            and row["event_type"] not in {"CHECKPOINT_CREATED", "HANDOFF_CREATED"}
        ):
            raise ContinuityStoreError(f"{label} 事件 hash 或 identity 非法")
        return cast(dict[str, object], payload)

    @classmethod
    def _validated_handoff_receipt(
        cls,
        conn: sqlite3.Connection,
        handoff_id: str,
    ) -> HandoffV2:
        handoff = cls._get_handoff(conn, handoff_id)
        row = conn.execute("SELECT * FROM events WHERE event_id=?", (handoff_id,)).fetchone()
        if row is None:
            raise ContinuityStoreError("Handoff 缺少不可变创建回执")
        payload = cls._validated_event_payload(row, label="Handoff 创建")
        request = payload.get("request")
        token_fingerprint = payload.get("lease_token_sha256")
        if (
            row["aggregate_type"] != "run"
            or row["aggregate_id"] != handoff.run_id
            or row["event_type"] != "HANDOFF_CREATED"
            or set(payload) != {"schema_version", "request", "lease_token_sha256", "handoff"}
            or payload.get("schema_version") != "handoff-created.v2"
            or not isinstance(request, dict)
            or request
            != {
                "schema_version": "handoff-create-request.v2",
                "handoff_id": handoff.handoff_id,
                "checkpoint_id": handoff.checkpoint_id,
                "from_owner": handoff.from_owner,
                "to_owner": handoff.to_owner,
            }
            or payload.get("handoff") != handoff.model_dump(mode="json")
            or not isinstance(token_fingerprint, str)
            or re.fullmatch(r"[0-9a-f]{64}", token_fingerprint) is None
        ):
            raise ContinuityStoreError("Handoff 创建回执身份或 schema 非法")
        unsigned = {
            "handoff_id": handoff.handoff_id,
            "work_id": handoff.work_id,
            "run_id": handoff.run_id,
            "checkpoint_id": handoff.checkpoint_id,
            "from_owner": handoff.from_owner,
            "to_owner": handoff.to_owner,
            "owned_paths_json": json.dumps(handoff.owned_paths, ensure_ascii=False),
            "git_head": handoff.git_head,
            "worktree_path": handoff.worktree_path,
            "lease_expires_at": handoff.lease_expires_at,
            "created_at": handoff.created_at,
        }
        canonical = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if handoff.snapshot_hash != hashlib.sha256(canonical.encode()).hexdigest():
            raise ContinuityStoreError("Handoff snapshot_hash 非法")
        return handoff

    @classmethod
    def _legacy_run_creation_request_from_payload(
        cls,
        payload: dict[str, object],
        *,
        lease_seconds: int,
    ) -> dict[str, object]:
        if set(payload) != _LEGACY_RUN_CREATION_FIELDS:
            raise ContinuityStoreError("LEGACY_REPLAY_UNPROVABLE: Run 创建事件 schema 未知")
        try:
            owned_raw = json.loads(str(payload["owned_paths_json"]))
            declared_raw = json.loads(str(payload["declared_dirty_paths_json"]))
            (
                run_id,
                work_id,
                executor_id,
                adapter,
                owned_paths,
                declared_dirty_paths,
                git_head,
                _token,
                lease_seconds,
            ) = cls._validated_run_creation_inputs(
                run_id=payload["run_id"],
                work_id=payload["work_id"],
                executor_id=payload["executor_id"],
                adapter=payload["adapter"],
                owned_paths=owned_raw,
                declared_dirty_paths=declared_raw,
                git_head=payload["git_head"],
                lease_token="legacy-proof-placeholder",
                lease_seconds=lease_seconds,
            )
            worktree = cls._lexical_run_worktree(payload["worktree_path"])
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise ContinuityStoreError(
                "LEGACY_REPLAY_UNPROVABLE: Run 创建事件无法规范化"
            ) from error
        if (
            payload.get("state") != RunState.RUNNING.value
            or payload.get("version") != 1
            or payload.get("created_at") != payload.get("updated_at")
            or list(owned_paths) != owned_raw
            or list(declared_dirty_paths) != declared_raw
            or worktree != payload.get("worktree_path")
            or declared_dirty_paths
        ):
            raise ContinuityStoreError(
                "LEGACY_REPLAY_UNPROVABLE: 原 observed dirty paths 或创建语义无法证明"
            )
        assert git_head is not None
        return cls._run_creation_request(
            run_id=run_id,
            work_id=work_id,
            executor_id=executor_id,
            adapter=adapter,
            owned_paths=owned_paths,
            declared_dirty_paths=declared_dirty_paths,
            observed_dirty_paths=(),
            git_head=git_head,
            worktree_path=worktree,
            lease_seconds=lease_seconds,
        )

    @classmethod
    def _legacy_run_creation_replay(
        cls,
        conn: sqlite3.Connection,
        *,
        row: sqlite3.Row,
        payload: dict[str, object],
        executor_id: str,
        lease_token: str,
        request: dict[str, object],
    ) -> RunItem:
        lease_seconds_value = request["lease_seconds"]
        if type(lease_seconds_value) is not int:
            raise ContinuityStoreError("LEGACY_REPLAY_UNPROVABLE: lease 时长无法证明")
        lease_seconds = lease_seconds_value
        recorded_request = cls._legacy_run_creation_request_from_payload(
            payload,
            lease_seconds=lease_seconds,
        )
        if recorded_request != request:
            raise ContinuityStoreError("idempotency_key 的旧版 Run 创建请求语义不一致")
        cls._validated_event_payload(row, label="旧版 Run 创建")
        created_at = cls._aware_timestamp(str(payload["created_at"]), "旧版 Run created_at")
        if str(row["created_at"]) != payload["created_at"]:
            raise ContinuityStoreError("LEGACY_REPLAY_UNPROVABLE: 事件创建时间不一致")
        run = cls._get_run(conn, str(payload["run_id"]))
        lease = cls._get_lease(conn, run.run_id)
        try:
            lease_updated_at = cls._aware_timestamp(
                lease.updated_at,
                "旧版 Run lease updated_at",
            )
            lease_expires_at = cls._aware_timestamp(
                lease.expires_at,
                "旧版 Run lease expires_at",
            )
        except ContinuityStoreError as error:
            raise ContinuityStoreError(
                "LEGACY_REPLAY_UNPROVABLE: lease 创建身份无法证明"
            ) from error
        if (
            lease.version != 1
            or lease.owner_id != executor_id
            or lease.lease_token != lease_token
            or lease_updated_at != created_at
            or lease_expires_at - created_at != timedelta(seconds=lease_seconds)
        ):
            raise ContinuityStoreError(
                "LEGACY_REPLAY_UNPROVABLE: lease 已续租、移交或 token 无法证明"
            )
        if (
            run.work_id != payload["work_id"]
            or run.executor_id != payload["executor_id"]
            or run.adapter != payload["adapter"]
            or list(run.owned_paths) != request["owned_paths"]
            or list(run.declared_dirty_paths) != request["declared_dirty_paths"]
            or run.git_head != payload["git_head"]
            or run.worktree_path != payload["worktree_path"]
            or run.created_at != payload["created_at"]
        ):
            raise ContinuityStoreError("LEGACY_REPLAY_UNPROVABLE: 当前 Run 与创建事件身份不一致")
        return run

    @classmethod
    def _run_creation_replay(
        cls,
        conn: sqlite3.Connection,
        *,
        run_id: str,
        executor_id: str,
        lease_token: str,
        request: dict[str, object],
        request_hash: str,
        idempotency_key: str,
    ) -> RunItem | None:
        row = cls._event_by_key(conn, idempotency_key)
        if row is None:
            return None
        if (
            row["aggregate_type"] != "run"
            or row["aggregate_id"] != run_id
            or row["event_type"] != "RUN_CREATED"
        ):
            raise ContinuityStoreError("idempotency_key 已用于其他语义")
        try:
            payload = json.loads(str(row["payload_json"]))
        except (TypeError, json.JSONDecodeError) as error:
            raise ContinuityStoreError("Run 创建事件 payload 无法读取") from error
        if not isinstance(payload, dict):
            raise ContinuityStoreError("Run 创建事件 payload 顶层必须是对象")
        if set(payload) == _LEGACY_RUN_CREATION_FIELDS:
            return cls._legacy_run_creation_replay(
                conn,
                row=row,
                payload=payload,
                executor_id=executor_id,
                lease_token=lease_token,
                request=request,
            )
        recorded_request = payload.get("request")
        if (
            set(payload)
            != {
                "schema_version",
                "request_hash",
                "request",
                "lease_token_sha256",
                "created_at",
                "lease_expires_at",
            }
            or payload.get("schema_version") != "run-created.v2"
            or not isinstance(recorded_request, dict)
            or set(recorded_request) != _RUN_CREATION_REQUEST_FIELDS
        ):
            raise ContinuityStoreError("Run 创建事件 payload schema 无效")
        try:
            (
                recorded_run_id,
                recorded_work_id,
                recorded_executor,
                recorded_adapter,
                recorded_owned,
                recorded_declared,
                recorded_head,
                _validated_token,
                recorded_lease_seconds,
            ) = cls._validated_run_creation_inputs(
                run_id=recorded_request["run_id"],
                work_id=recorded_request["work_id"],
                executor_id=recorded_request["executor_id"],
                adapter=recorded_request["adapter"],
                owned_paths=recorded_request["owned_paths"],
                declared_dirty_paths=recorded_request["declared_dirty_paths"],
                git_head=recorded_request["git_head"],
                lease_token=lease_token,
                lease_seconds=recorded_request["lease_seconds"],
            )
            recorded_observed = cls._run_paths(
                recorded_request["observed_dirty_paths"],
                label="observed_dirty_paths",
                allow_empty=True,
            )
            recorded_worktree = cls._lexical_run_worktree(recorded_request["worktree_path"])
            created_at = cls._aware_timestamp(
                str(payload.get("created_at")),
                "Run 创建事件 created_at",
            )
            lease_expires_at = cls._aware_timestamp(
                str(payload.get("lease_expires_at")),
                "Run 创建事件 lease_expires_at",
            )
        except (KeyError, TypeError) as error:
            raise ContinuityStoreError("Run 创建事件 request 无法读取") from error
        if (
            list(recorded_owned) != recorded_request["owned_paths"]
            or list(recorded_declared) != recorded_request["declared_dirty_paths"]
            or list(recorded_observed) != recorded_request["observed_dirty_paths"]
            or not all(
                cls._authority_path_covered(path, recorded_declared) for path in recorded_observed
            )
            or recorded_worktree != recorded_request["worktree_path"]
            or lease_expires_at - created_at != timedelta(seconds=recorded_lease_seconds)
        ):
            raise ContinuityStoreError("Run 创建事件 request 非 canonical 或时间语义无效")
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        expected_event_hash = hashlib.sha256(
            (
                f"{row['previous_hash']}|{row['aggregate_id']}|{row['event_type']}|"
                f"{canonical}|{row['created_at']}"
            ).encode()
        ).hexdigest()
        if (
            row["event_hash"] != expected_event_hash
            or row["event_id"] != f"EVT-{expected_event_hash[:16].upper()}"
            or payload.get("request_hash") != request_hash
            or recorded_request != request
            or cls._run_creation_request_hash(recorded_request) != request_hash
            or payload.get("created_at") != row["created_at"]
        ):
            raise ContinuityStoreError("idempotency_key 的 Run 创建请求语义不一致")
        if not hmac.compare_digest(
            str(payload.get("lease_token_sha256")),
            cls._lease_token_fingerprint(lease_token),
        ):
            raise ContinuityStoreError("Run 创建 lease token identity 不匹配")
        run = cls._get_run(conn, run_id)
        if (
            recorded_run_id != run_id
            or recorded_executor != executor_id
            or run.work_id != recorded_work_id
            or run.executor_id != recorded_executor
            or run.adapter != recorded_adapter
            or list(run.owned_paths) != request["owned_paths"]
            or list(run.declared_dirty_paths) != request["declared_dirty_paths"]
            or run.git_head != recorded_head
            or run.worktree_path != recorded_worktree
            or run.created_at != payload["created_at"]
        ):
            raise ContinuityStoreError("Run 创建事件与当前 Run immutable identity 不一致")
        return run

    @classmethod
    def _expired_run_settlement_replay(
        cls,
        conn: sqlite3.Connection,
        *,
        recovery_lease_token: str,
        request: dict[str, object],
        request_hash: str,
        idempotency_key: str,
    ) -> RunItem | None:
        row = cls._event_by_key(conn, idempotency_key)
        if row is None:
            return None
        target_run_id = request.get("target_run_id")
        if (
            row["aggregate_type"] != "run"
            or row["aggregate_id"] != target_run_id
            or row["event_type"] != "RUN_EXPIRED_SETTLED"
        ):
            raise ContinuityStoreError("idempotency_key 已用于其他语义")
        try:
            payload = json.loads(str(row["payload_json"]))
        except (TypeError, json.JSONDecodeError) as error:
            raise ContinuityStoreError("结算事件 payload 无法读取") from error
        if not isinstance(payload, dict):
            raise ContinuityStoreError("结算事件 payload 顶层必须是对象")
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        expected_event_hash = hashlib.sha256(
            (
                f"{row['previous_hash']}|{row['aggregate_id']}|{row['event_type']}|"
                f"{canonical}|{row['created_at']}"
            ).encode()
        ).hexdigest()
        if (
            row["event_hash"] != expected_event_hash
            or row["event_id"] != f"EVT-{expected_event_hash[:16].upper()}"
        ):
            raise ContinuityStoreError("结算事件 hash 或 identity 非法")
        recorded_request = payload.get("request")
        target = payload.get("target")
        recovery = payload.get("recovery")
        authority = payload.get("authority")
        target_authority = authority.get("target") if isinstance(authority, dict) else None
        recovery_authority = authority.get("recovery") if isinstance(authority, dict) else None
        sha256_fields = (
            payload.get("request_hash"),
            payload.get("recovery_token_sha256"),
            target.get("work_scope_hash") if isinstance(target, dict) else None,
            recovery.get("work_scope_hash") if isinstance(recovery, dict) else None,
            recovery.get("owned_paths_hash") if isinstance(recovery, dict) else None,
            target_authority.get("decision_sha256") if isinstance(target_authority, dict) else None,
            recovery_authority.get("decision_sha256")
            if isinstance(recovery_authority, dict)
            else None,
        )
        if (
            set(payload)
            != {
                "schema_version",
                "request_hash",
                "request",
                "recovery_token_sha256",
                "runtime_target_path",
                "outcome",
                "reason",
                "target",
                "recovery",
                "authority",
            }
            or payload.get("schema_version") != "expired-run-settlement.v2"
            or not isinstance(recorded_request, dict)
            or set(recorded_request) != _SETTLEMENT_REQUEST_FIELDS
            or recorded_request.get("schema_version") != "expired-run-settlement-request.v2"
            or recorded_request.get("action") != "settle_expired_run"
            or cls._settlement_request_hash(recorded_request) != payload.get("request_hash")
            or payload.get("runtime_target_path") != _CANONICAL_RUNTIME_DB
            or payload.get("outcome") != RunState.CANCELLED.value
            or payload.get("outcome") != recorded_request.get("outcome")
            or not isinstance(payload.get("reason"), str)
            or not payload["reason"]
            or payload.get("reason") != recorded_request.get("reason")
            or not isinstance(target, dict)
            or set(target)
            != {
                "run_id",
                "work_id",
                "work_version",
                "work_scope_hash",
                "previous_state",
                "previous_version",
                "settled_state",
                "settled_version",
                "lease_version",
                "lease_expires_at",
            }
            or target.get("run_id") != recorded_request.get("target_run_id")
            or not isinstance(target.get("work_id"), str)
            or not target["work_id"]
            or type(target.get("work_version")) is not int
            or not isinstance(target.get("previous_state"), str)
            or type(target.get("previous_version")) is not int
            or target.get("settled_state") != RunState.CANCELLED.value
            or type(target.get("settled_version")) is not int
            or target["settled_version"] != target["previous_version"] + 1
            or type(target.get("lease_version")) is not int
            or not isinstance(target.get("lease_expires_at"), str)
            or not isinstance(recovery, dict)
            or set(recovery)
            != {
                "run_id",
                "run_version",
                "work_id",
                "work_version",
                "work_scope_hash",
                "owned_paths_hash",
                "lease_version",
                "owner_id",
                "git_head",
            }
            or not isinstance(recovery.get("run_id"), str)
            or not recovery["run_id"]
            or recovery.get("run_id") != recorded_request.get("recovery_run_id")
            or not isinstance(recovery.get("work_id"), str)
            or not recovery["work_id"]
            or type(recovery.get("run_version")) is not int
            or type(recovery.get("work_version")) is not int
            or type(recovery.get("lease_version")) is not int
            or not isinstance(recovery.get("owner_id"), str)
            or recovery.get("owner_id") != recorded_request.get("recovery_owner_id")
            or not isinstance(recovery.get("git_head"), str)
            or _FULL_GIT_COMMIT.fullmatch(recovery["git_head"]) is None
            or not isinstance(authority, dict)
            or set(authority) != {"project_id", "target", "recovery"}
            or not isinstance(authority.get("project_id"), str)
            or not authority["project_id"]
            or authority["project_id"] != authority["project_id"].strip()
            or not isinstance(target_authority, dict)
            or set(target_authority) != {"decision_id", "decision_sha256", "change_id"}
            or not is_canonical_decision_id(target_authority.get("decision_id"))
            or not is_canonical_runtime_change_id(target_authority.get("change_id"))
            or not isinstance(recovery_authority, dict)
            or set(recovery_authority) != {"decision_id", "decision_sha256", "change_id"}
            or not is_canonical_decision_id(recovery_authority.get("decision_id"))
            or not is_canonical_runtime_change_id(recovery_authority.get("change_id"))
            or recovery_authority.get("decision_id") != recorded_request.get("decision_id")
            or target_authority["decision_id"] == recovery_authority["decision_id"]
            or target_authority["change_id"] == recovery_authority["change_id"]
            or any(
                not isinstance(value, str)
                or len(value) != 64
                or any(character not in "0123456789abcdef" for character in value)
                for value in sha256_fields
            )
        ):
            raise ContinuityStoreError("结算事件 payload 身份或 schema 非法")
        if recorded_request != request or payload.get("request_hash") != request_hash:
            raise ContinuityStoreError("idempotency_key 的结算请求语义不一致")
        if not hmac.compare_digest(
            str(payload.get("recovery_token_sha256")),
            cls._lease_token_fingerprint(recovery_lease_token),
        ):
            raise ContinuityStoreError("结算恢复 lease token identity 不匹配")
        cls._aware_timestamp(target["lease_expires_at"], "结算事件目标 lease")
        run = cls._get_run(conn, str(target_run_id))
        if (
            run.work_id != target["work_id"]
            or run.state.value != target["settled_state"]
            or run.version != target["settled_version"]
        ):
            raise ContinuityStoreError("结算事件与 Run 当前状态不一致")
        return run

    @staticmethod
    def _aware_timestamp(raw: str, label: str) -> datetime:
        try:
            value = datetime.fromisoformat(raw)
        except ValueError as error:
            raise ContinuityStoreError(f"{label} 时间戳非法") from error
        if value.tzinfo is None:
            raise ContinuityStoreError(f"{label} 时间戳必须包含时区")
        return value.astimezone(UTC)

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
        row = conn.execute(
            "SELECT * FROM mission_items WHERE mission_id=?", (mission_id,)
        ).fetchone()
        if row is None:
            raise ContinuityStoreError(f"Mission 不存在: {mission_id}")
        data = dict(row)
        data["acceptance_criteria"] = tuple(json.loads(data.pop("acceptance_criteria_json")))
        data["authority"] = json.loads(data.pop("authority_json"))
        return Mission.model_validate(data)

    @staticmethod
    def _get_planning_draft(row: sqlite3.Row) -> PlanningDraft:
        data = dict(row)
        data["acceptance_criteria"] = tuple(json.loads(data.pop("acceptance_criteria_json")))
        data.pop("created_at")
        data.pop("updated_at")
        return PlanningDraft.model_validate(data)

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
    def _decode_orchestration_outcome(payload_json: str) -> OrchestrationOutcome:
        try:
            return OrchestrationOutcome.model_validate(json.loads(payload_json))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise ContinuityStoreError("编排事件无法读取") from error

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
        previous = conn.execute(
            "SELECT event_hash FROM events ORDER BY rowid DESC LIMIT 1"
        ).fetchone()
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
