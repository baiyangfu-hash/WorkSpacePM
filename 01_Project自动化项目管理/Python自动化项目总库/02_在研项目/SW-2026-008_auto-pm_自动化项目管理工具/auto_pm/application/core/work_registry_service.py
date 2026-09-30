"""Application service for authorized Work lifecycle operations."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from auto_pm.contracts.continuity import (
    EXECUTION_ACTIVE_WORK_STATES,
    WorkItem,
    WorkKind,
    WorkState,
)
from auto_pm.contracts.decision_package import (
    DecisionPackageDTO,
    RuntimeDecisionAction,
    RuntimeDecisionOutcome,
    is_canonical_decision_id,
)
from auto_pm.contracts.mission import Mission
from auto_pm.domain.change.decision_service import DecisionError, DecisionService
from auto_pm.infrastructure.continuity_store import (
    ContinuityStore,
    ContinuityStoreError,
    WorkAdjudicationEvidence,
)


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
        self._assert_no_active_scope_conflict(mission.subject_project_id, owner, work_id, paths)
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

    def _assert_no_active_scope_conflict(
        self, subject_project_id: str, owner: str, work_id: str, paths: tuple[str, ...]
    ) -> None:
        try:
            existing_works = self._store.list_works(subject_project_id)
        except ContinuityStoreError as error:
            raise WorkRegistryError(str(error)) from error
        for existing in existing_works:
            if existing.state not in EXECUTION_ACTIVE_WORK_STATES:
                raise WorkRegistryError("Store 返回了非执行活动态 Work")
            overlap = sorted(set(existing.scope_paths).intersection(paths))
            if overlap and existing.owner != owner and existing.work_id != work_id:
                raise WorkRegistryError(
                    "其他 owner 的 active Work 路径冲突: "
                    f"owner={existing.owner}; paths={','.join(overlap)}"
                )

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

    def adjudication_evidence(self, work_id: str) -> tuple[WorkAdjudicationEvidence, str]:
        """Read-only facts and the original Decision digest an adjudication must bind."""

        try:
            evidence = self._store.work_adjudication_evidence(work_id)
            if not is_canonical_decision_id(evidence.authorization_ref):
                return evidence, ""
            _decision, sha256 = DecisionService(self._root).get_decision_with_sha256(
                evidence.authorization_ref
            )
            issues = self._store.decision_git_binding_issues(evidence.authorization_ref)
        except (ContinuityStoreError, DecisionError) as error:
            raise WorkRegistryError(str(error)) from error
        if issues:
            evidence = dataclasses.replace(evidence, blockers=evidence.blockers + issues)
        return evidence, sha256

    def adjudicate_blocked_work(
        self,
        *,
        target_work_id: str,
        expected_work_version: int,
        expected_original_decision_sha256: str,
        expected_run_set_sha256: str,
        expected_lease_set_sha256: str,
        recovery_run_id: str,
        recovery_owner_id: str,
        recovery_lease_token: str,
        decision_id: str,
        outcome: WorkState,
        reason: str,
        idempotency_key: str,
    ) -> WorkItem:
        """Forward-cancel one historical BLOCKED Work under an exact, independent Decision.

        History is preserved: Runs, leases, Checkpoints and earlier events are untouched.
        """

        normalized_reason = reason.strip()
        if not all(
            value.strip()
            for value in (
                target_work_id,
                expected_original_decision_sha256,
                expected_run_set_sha256,
                expected_lease_set_sha256,
                recovery_run_id,
                recovery_owner_id,
                recovery_lease_token,
                decision_id,
                idempotency_key,
            )
        ):
            raise WorkRegistryError("裁决目标、绑定摘要、恢复 lease、Decision 与幂等键均不能为空")
        if (
            reason != normalized_reason
            or not normalized_reason
            or len(normalized_reason) > 1000
            or any(not character.isprintable() for character in normalized_reason)
        ):
            raise WorkRegistryError("裁决原因必须为 1 到 1000 个字符")
        if recovery_lease_token in normalized_reason:
            raise WorkRegistryError("裁决原因不得包含恢复 lease token")
        if outcome is not WorkState.CANCELLED:
            raise WorkRegistryError("行政裁决只能前向结算为 CANCELLED")
        try:
            target = self._store.get_work(target_work_id)
            recovery = self._store.get_run(recovery_run_id)
            recovery_work = self._store.get_work(recovery.work_id)
            recovery_lease = self._store.get_lease(recovery_run_id)
            runtime_target_path = self._store.runtime_target_path()
            decisions = DecisionService(self._root)
            decision, decision_sha256 = decisions.get_decision_with_sha256(decision_id)
            capability = decision.runtime_capability
            if decision.decision_conclusion != "approved" or decision.conditions:
                raise WorkRegistryError("运行态 Decision 必须是无条件 approved")
            if capability is None:
                raise WorkRegistryError("Decision 未声明 runtime_capability")
            if RuntimeDecisionAction.ADJUDICATE_BLOCKED_WORK not in capability.allowed_runtime_actions:
                raise WorkRegistryError("Decision 未授权 adjudicate_blocked_work")
            if target_work_id not in capability.target_work_ids:
                raise WorkRegistryError("Decision 未授权目标 Work")
            if RuntimeDecisionOutcome(outcome.value) not in capability.allowed_outcomes:
                raise WorkRegistryError("Decision 未授权目标裁决状态")
            replay_original_id = self._store.adjudication_replay_original_id(
                target_work_id=target_work_id, idempotency_key=idempotency_key
            )
            if replay_original_id is not None:
                # 精确重放：Work 已被裁决，授权引用已是裁决 Decision；语义一致性由 Store 事件核验。
                original_id = replay_original_id
                original_sha256 = expected_original_decision_sha256
            else:
                if target.read_only or not is_canonical_decision_id(target.authorization_ref):
                    raise WorkRegistryError("目标 Work 必须绑定 canonical immutable Decision")
                original_id = target.authorization_ref
                original, original_sha256 = decisions.get_decision_with_sha256(original_id)
                if original_sha256 != expected_original_decision_sha256:
                    raise WorkRegistryError("原 Decision SHA-256 与裁决绑定不一致")
                if original_id == decision_id:
                    raise WorkRegistryError("裁决 Decision 不得复用目标 Work 的原授权链")
                if original.change_id == decision.change_id:
                    raise WorkRegistryError("裁决 CHG 必须独立于目标 Work 的原 CHG")
                if original.project_id != target.subject_project_id:
                    raise WorkRegistryError("原 Decision 项目与目标 Work 不一致")
            if target.subject_project_id != recovery_work.subject_project_id:
                raise WorkRegistryError("裁决目标与恢复 Work 不属于同一项目")
            if decision.project_id != recovery_work.subject_project_id:
                raise WorkRegistryError("Decision 项目与恢复 Work 不一致")
            if recovery_work.authorization_ref != decision_id:
                raise WorkRegistryError("恢复 Work 未绑定指定 Decision")
            if recovery_work.work_id == target.work_id:
                raise WorkRegistryError("裁决目标与恢复 Work 必须不同")
            approved = self._normalize_paths(decision.approved_files)
            if not self._covers(runtime_target_path, approved):
                raise WorkRegistryError("Decision 未覆盖 canonical continuity.db")
            return self._store.adjudicate_blocked_work(
                target_work_id=target_work_id,
                expected_work_version=expected_work_version,
                expected_original_decision_id=original_id,
                original_decision_sha256=original_sha256,
                expected_run_set_sha256=expected_run_set_sha256,
                expected_lease_set_sha256=expected_lease_set_sha256,
                recovery_run_id=recovery_run_id,
                expected_recovery_run_version=recovery.version,
                expected_recovery_lease_version=recovery_lease.version,
                recovery_work_id=recovery_work.work_id,
                expected_recovery_work_version=recovery_work.version,
                expected_recovery_work_scope_hash=self._store.authority_paths_hash(
                    recovery_work.scope_paths
                ),
                expected_recovery_owned_paths_hash=self._store.authority_paths_hash(
                    recovery.owned_paths
                ),
                recovery_owner_id=recovery_owner_id,
                recovery_lease_token=recovery_lease_token,
                decision_id=decision_id,
                decision_sha256=decision_sha256,
                decision_change_id=decision.change_id,
                decision_project_id=decision.project_id,
                decision_approved_paths=approved,
                runtime_target_path=runtime_target_path,
                outcome=outcome.value,
                reason=normalized_reason,
                idempotency_key=idempotency_key,
            )
        except (ContinuityStoreError, DecisionError) as error:
            raise WorkRegistryError(str(error)) from error

    @staticmethod
    def _covers(path: str, roots: tuple[str, ...]) -> bool:
        target = PurePosixPath(path).parts
        return any(target[: len(PurePosixPath(root).parts)] == PurePosixPath(root).parts for root in roots)

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
