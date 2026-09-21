"""Application service for authorized Work lifecycle operations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from auto_pm.contracts.continuity import WorkItem, WorkKind, WorkState
from auto_pm.contracts.decision_package import DecisionPackageDTO
from auto_pm.contracts.mission import Mission
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
        self.assert_authorized_scope(
            subject_project_id=work.subject_project_id,
            decision_id=decision_id,
            scope_paths=work.scope_paths,
        )
        return self._transition(work, WorkState.READY, decision_id, idempotency_key)

    def create_from_mission(
        self, *, mission_id: str, owner: str, scope_paths: list[str]
    ) -> WorkItem:
        """Derive one replay-safe WBS Work from an existing strong-authority Mission."""
        try:
            mission = self._store.get_mission(mission_id)
        except ContinuityStoreError as error:
            raise WorkRegistryError(f"Mission 不存在: {mission_id}") from error
        self._assert_mission_authority(mission, scope_paths)
        paths = self._normalize_paths(scope_paths)
        digest = hashlib.sha256(
            f"{mission.mission_id}\n{mission.authority.decision_id}\n{self._scope_hash(paths)}".encode()
        ).hexdigest()[:16].upper()
        work_id = f"WORK-MSN-{digest}"
        for existing in self._store.list_works(mission.subject_project_id):
            overlap = sorted(set(existing.scope_paths).intersection(paths))
            if overlap and existing.owner != owner and existing.work_id != work_id:
                raise WorkRegistryError(
                    "其他 owner 的 active Work 路径冲突: "
                    f"owner={existing.owner}; paths={','.join(overlap)}"
                )
        work = self.create_work(
            work_id=work_id,
            subject_project_id=mission.subject_project_id,
            kind=WorkKind.WBS,
            title=mission.title,
            owner=owner,
            scope_paths=list(paths),
            source_fingerprint=mission.authority.audit.source_fingerprint,
            idempotency_key=f"mission-work-create:{mission.mission_id}:{digest}",
        )
        if work.state is WorkState.PLANNED:
            return self.authorize(
                work.work_id,
                mission.authority.decision_id,
                f"mission-work-authorize:{mission.mission_id}:{digest}",
            )
        return work

    def _assert_mission_authority(self, mission: Mission, scope_paths: list[str]) -> None:
        authority = mission.authority
        if authority.authorization_source != "CHG_DECISION":
            raise WorkRegistryError("Mission 不具备 CHG_DECISION 强授权")
        if WorkKind.WBS not in authority.allowed_child_work_kinds:
            raise WorkRegistryError("Mission 未授权 WBS 子 Work")
        paths = self._normalize_paths(scope_paths)
        if not set(paths).issubset(set(authority.scope_paths)):
            raise WorkRegistryError("Work scope 超出 Mission authority")
        decision = self._load_decision(authority.decision_id)
        if decision.change_id != authority.change_id:
            raise WorkRegistryError("Mission CHG 与 Decision 不一致")
        self.assert_authorized_scope(
            subject_project_id=mission.subject_project_id,
            decision_id=authority.decision_id,
            scope_paths=paths,
        )

    def assert_authorized_scope(
        self,
        *,
        subject_project_id: str,
        decision_id: str,
        scope_paths: tuple[str, ...] | list[str],
    ) -> None:
        """Preflight a child Work before creating any mutable partial state."""
        decision = self._load_decision(decision_id)
        if decision.project_id != subject_project_id:
            raise WorkRegistryError("Decision 项目与 Work subject 不一致")
        if decision.decision_conclusion not in {"approved", "conditionally_approved"}:
            raise WorkRegistryError("Decision 未批准")
        approved = set(self._normalize_paths(decision.approved_files))
        paths = self._normalize_paths(list(scope_paths))
        if not set(paths).issubset(approved):
            raise WorkRegistryError("Work scope 超出 Decision approved_files")

    def get_work(self, work_id: str) -> WorkItem:
        """Read one Work without exposing the persistence implementation."""
        try:
            return self._store.get_work(work_id)
        except ContinuityStoreError as error:
            raise WorkRegistryError(str(error)) from error

    def list_relations(self) -> tuple[tuple[str, str, str], ...]:
        """Read the directed Work Graph in insertion order."""
        try:
            return self._store.list_work_relations()
        except ContinuityStoreError as error:
            raise WorkRegistryError(str(error)) from error

    def is_reachable(self, from_work_id: str, to_work_id: str) -> bool:
        """Return whether a directed relation path already connects two same-project Works."""
        source = self.get_work(from_work_id)
        target = self.get_work(to_work_id)
        if source.subject_project_id != target.subject_project_id:
            raise WorkRegistryError("Work Graph 不允许跨项目关系")
        adjacency: dict[str, set[str]] = {}
        for source_id, target_id, _relation in self.list_relations():
            adjacency.setdefault(source_id, set()).add(target_id)
        pending = [from_work_id]
        visited: set[str] = set()
        while pending:
            current = pending.pop()
            if current == to_work_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            pending.extend(adjacency.get(current, ()))
        return False

    def transition(
        self,
        work_id: str,
        new_state: WorkState,
        idempotency_key: str,
    ) -> WorkItem:
        try:
            existing = self._store.work_transition_for_key(idempotency_key)
            work = self._store.get_work(work_id)
        except ContinuityStoreError as error:
            raise WorkRegistryError(str(error)) from error
        if existing is not None:
            aggregate_id, recorded_state, recorded_authorization_ref = existing
            if aggregate_id != work_id:
                raise WorkRegistryError("idempotency_key 已用于其他 Work")
            if (
                recorded_state is not new_state
                or recorded_authorization_ref != work.authorization_ref
                or work.state is not new_state
            ):
                raise WorkRegistryError("idempotency_key 已绑定不同 Work 状态迁移")
            return work
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
        try:
            existing = self._store.event_aggregate_for_key(idempotency_key)
        except ContinuityStoreError as error:
            raise WorkRegistryError(str(error)) from error
        if existing is not None:
            _aggregate_type, aggregate_id = existing
            if aggregate_id != from_work_id:
                raise WorkRegistryError("idempotency_key 已用于其他 Work")
            return
        source = self.get_work(from_work_id)
        target = self.get_work(to_work_id)
        if source.subject_project_id != target.subject_project_id:
            raise WorkRegistryError("Work Graph 不允许跨项目关系")
        if self.is_reachable(to_work_id, from_work_id):
            raise WorkRegistryError("Work Graph 不允许循环关系")
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
            transitioned = self._store.transition(
                work.work_id,
                work.version,
                new_state.value,
                authorization_ref,
                idempotency_key,
                self._now(),
            )
        except ContinuityStoreError as error:
            raise WorkRegistryError(str(error)) from error
        if transitioned.state is not new_state:
            raise WorkRegistryError("idempotency_key 已绑定不同 Work 状态迁移")
        return transitioned

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
