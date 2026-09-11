"""Application service for authorized Work lifecycle operations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from auto_pm.contracts.continuity import WorkItem, WorkKind, WorkState
from auto_pm.contracts.decision_package import DecisionPackageDTO
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError


class WorkRegistryError(RuntimeError):
    """Raised when a Work command violates authorization or state rules."""


_TRANSITIONS = {
    WorkState.PLANNED: {WorkState.READY, WorkState.CANCELLED},
    WorkState.READY: {WorkState.IN_PROGRESS, WorkState.BLOCKED, WorkState.CANCELLED},
    WorkState.IN_PROGRESS: {WorkState.BLOCKED, WorkState.VERIFYING, WorkState.CANCELLED},
    WorkState.BLOCKED: {WorkState.READY, WorkState.CANCELLED},
    WorkState.VERIFYING: {WorkState.IN_PROGRESS, WorkState.ACCEPTED},
    WorkState.ACCEPTED: {WorkState.CLOSED},
    WorkState.CLOSED: set(),
    WorkState.CANCELLED: set(),
}
_RELATIONS = {"blocks", "blocked_by", "parent", "child", "discovered_from", "duplicates"}


class WorkRegistryService:
    """Create and advance Work while keeping CHG/Decision authorization separate."""

    def __init__(
        self,
        workspace_root: str | Path,
        store: ContinuityStore | None = None,
        now: Callable[[], str] | None = None,
    ) -> None:
        self._root = Path(workspace_root).resolve()
        self._store = store or ContinuityStore(self._root)
        self._now = now or (lambda: datetime.now(UTC).isoformat())

    def initialize(self, tool_version: str = "dev") -> None:
        self._store.initialize(self._now(), tool_version)

    def create_work(
        self,
        *,
        work_id: str,
        subject_project_id: str,
        kind: WorkKind,
        title: str,
        owner: str,
        scope_paths: list[str],
        source_fingerprint: str,
        idempotency_key: str,
        read_only: bool = False,
    ) -> WorkItem:
        paths = self._normalize_paths(scope_paths)
        if not all((work_id.strip(), subject_project_id.strip(), title.strip(), owner.strip())):
            raise WorkRegistryError("Work 身份、项目、标题和 owner 均不能为空")
        if not idempotency_key.strip() or not source_fingerprint.strip():
            raise WorkRegistryError("idempotency_key 与 source_fingerprint 均不能为空")
        now = self._now()
        values = {
            "work_id": work_id,
            "subject_project_id": subject_project_id,
            "kind": kind.value,
            "title": title,
            "state": (WorkState.READY if read_only else WorkState.PLANNED).value,
            "owner": owner,
            "read_only": int(read_only),
            "authorization_ref": "READ_ONLY" if read_only else "",
            "scope_json": json.dumps(paths, ensure_ascii=False),
            "scope_hash": self._scope_hash(paths),
            "source_fingerprint": source_fingerprint,
            "version": 1,
            "created_at": now,
            "updated_at": now,
        }
        try:
            return self._store.create_work(values, idempotency_key, now)
        except ContinuityStoreError as error:
            raise WorkRegistryError(str(error)) from error

    def authorize(self, work_id: str, decision_id: str, idempotency_key: str) -> WorkItem:
        work = self._store.get_work(work_id)
        if work.read_only or work.state != WorkState.PLANNED:
            raise WorkRegistryError("只有 PLANNED 写入型 Work 可以授权")
        decision = self._load_decision(decision_id)
        if decision.project_id != work.subject_project_id:
            raise WorkRegistryError("Decision 项目与 Work subject 不一致")
        if decision.decision_conclusion not in {"approved", "conditionally_approved"}:
            raise WorkRegistryError("Decision 未批准")
        approved = set(self._normalize_paths(decision.approved_files))
        if not set(work.scope_paths).issubset(approved):
            raise WorkRegistryError("Work scope 超出 Decision approved_files")
        return self._transition(work, WorkState.READY, decision_id, idempotency_key)

    def transition(
        self,
        work_id: str,
        new_state: WorkState,
        idempotency_key: str,
    ) -> WorkItem:
        work = self._store.get_work(work_id)
        if new_state not in _TRANSITIONS[work.state]:
            raise WorkRegistryError(f"非法 Work 状态迁移: {work.state} -> {new_state}")
        return self._transition(work, new_state, work.authorization_ref, idempotency_key)

    def add_relation(
        self,
        from_work_id: str,
        to_work_id: str,
        relation: str,
        idempotency_key: str,
    ) -> None:
        if from_work_id == to_work_id:
            raise WorkRegistryError("Work 不得与自身建立关系")
        if relation not in _RELATIONS:
            raise WorkRegistryError(f"未知 Work relation: {relation}")
        digest = hashlib.sha256(idempotency_key.encode()).hexdigest()[:16].upper()
        try:
            self._store.add_relation(
                from_work_id,
                to_work_id,
                relation,
                f"EVT-{digest}",
                idempotency_key,
                self._now(),
            )
        except ContinuityStoreError as error:
            raise WorkRegistryError(str(error)) from error

    def _transition(
        self,
        work: WorkItem,
        new_state: WorkState,
        authorization_ref: str,
        idempotency_key: str,
    ) -> WorkItem:
        try:
            return self._store.transition(
                work.work_id,
                work.version,
                new_state.value,
                authorization_ref,
                idempotency_key,
                self._now(),
            )
        except ContinuityStoreError as error:
            raise WorkRegistryError(str(error)) from error

    def _load_decision(self, decision_id: str) -> DecisionPackageDTO:
        path = self._root / ".auto-pm" / "decisions" / f"{decision_id}.json"
        if not path.is_file():
            raise WorkRegistryError(f"Decision 不存在: {decision_id}")
        try:
            return DecisionPackageDTO.from_dict(
                json.loads(path.read_text(encoding="utf-8", errors="replace"))
            )
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise WorkRegistryError(f"Decision 无法读取: {decision_id}") from error

    @staticmethod
    def _normalize_paths(paths: list[str]) -> tuple[str, ...]:
        result: list[str] = []
        for raw in paths:
            path = PurePosixPath(str(raw).replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts or str(path) in {"", "."}:
                raise WorkRegistryError(f"非法 scope path: {raw}")
            normalized = path.as_posix()
            if normalized not in result:
                result.append(normalized)
        if not result:
            raise WorkRegistryError("Work scope_paths 不能为空")
        return tuple(result)

    @staticmethod
    def _scope_hash(paths: tuple[str, ...]) -> str:
        return hashlib.sha256(
            json.dumps(paths, ensure_ascii=False, separators=(",", ":")).encode()
        ).hexdigest()
