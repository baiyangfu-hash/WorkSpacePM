"""Mission lifecycle service backed only by the Continuity Store."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from auto_pm.contracts.continuity import WorkKind
from auto_pm.contracts.decision_package import DecisionPackageDTO
from auto_pm.contracts.mission import AuthorityAudit, AuthorityEnvelope, Mission, MissionState
from auto_pm.contracts.pm_facade import PlanningDraft
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError


class MissionServiceError(RuntimeError):
    """Raised when a Mission request cannot be safely authorized or persisted."""


_TRANSITIONS: dict[MissionState, frozenset[MissionState]] = {
    MissionState.DRAFT: frozenset({MissionState.AWAITING_APPROVAL, MissionState.CANCELLED}),
    MissionState.AWAITING_APPROVAL: frozenset({MissionState.ACTIVE, MissionState.CANCELLED}),
    MissionState.ACTIVE: frozenset(
        {MissionState.BLOCKED, MissionState.ACCEPTANCE_PENDING, MissionState.CANCELLED}
    ),
    MissionState.BLOCKED: frozenset({MissionState.ACTIVE, MissionState.CANCELLED}),
    MissionState.ACCEPTANCE_PENDING: frozenset({MissionState.ACCEPTED, MissionState.BLOCKED}),
    MissionState.ACCEPTED: frozenset({MissionState.CLOSED}),
    MissionState.CLOSED: frozenset(),
    MissionState.CANCELLED: frozenset(),
}


class MissionService:
    """Create and advance one explicit, user-authorized Mission at a time."""

    def __init__(
        self,
        workspace_root: str | Path,
        now: Callable[[], datetime] | None = None,
        *,
        store: ContinuityStore | None = None,
    ) -> None:
        self._store = store or ContinuityStore(workspace_root)
        self._now = now or (lambda: datetime.now(UTC))

    def initialize(self, tool_version: str) -> None:
        try:
            self._store.initialize(self._timestamp(), tool_version)
        except ContinuityStoreError as error:
            raise MissionServiceError(str(error)) from error

    def create(
        self,
        *,
        mission_id: str,
        subject_project_id: str,
        title: str,
        objective: str,
        acceptance_criteria: list[str],
        authority: AuthorityEnvelope,
        created_by: str,
        idempotency_key: str,
        root_work_id: str | None = None,
    ) -> Mission:
        instant = self._instant()
        now = instant.isoformat()
        self._assert_authority_is_current(authority, instant)
        if subject_project_id != authority.subject_project_id:
            raise MissionServiceError("Mission 与 AuthorityEnvelope subject project 不匹配")
        resolved_root_work_id = root_work_id.strip() if root_work_id else None
        if resolved_root_work_id:
            self._assert_root_work_matches_project(subject_project_id, resolved_root_work_id)
        mission = Mission(
            mission_id=mission_id,
            subject_project_id=subject_project_id,
            title=title,
            objective=objective,
            acceptance_criteria=tuple(acceptance_criteria),
            authority=authority,
            root_work_id=resolved_root_work_id,
            created_by=created_by,
            created_at=instant,
            updated_at=instant,
        )
        values = mission.model_dump(mode="json")
        values.pop("schema_version")
        values["acceptance_criteria_json"] = json.dumps(
            values.pop("acceptance_criteria"), ensure_ascii=False, separators=(",", ":")
        )
        values["authority_json"] = json.dumps(
            values.pop("authority"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        try:
            return self._store.create_mission(values, idempotency_key, now)
        except ContinuityStoreError as error:
            raise MissionServiceError(str(error)) from error

    def create_from_planning_approval(
        self,
        *,
        mission_id: str,
        draft: PlanningDraft,
        decision: DecisionPackageDTO,
        plan_hash: str,
        created_by: str,
    ) -> Mission:
        """Create a strong-authority Mission from one exact planning approval."""

        approval = decision.metadata.get("planning_approval")
        if not isinstance(approval, dict) or approval.get("plan_hash") != plan_hash:
            raise MissionServiceError("Decision 未绑定指定 PlanningScopeCard plan_hash")
        if (
            decision.project_id != draft.subject_project_id
            or decision.decision_conclusion not in {"approved", "conditionally_approved"}
            or not decision.change_id
            or not decision.decision_id
            or not decision.approver
            or tuple(decision.approved_files) == ()
        ):
            raise MissionServiceError("Decision 不是可物化 Mission 的真实批准")
        try:
            parsed_approved_at = datetime.fromisoformat(decision.approved_at)
        except (TypeError, ValueError) as error:
            raise MissionServiceError("Decision approved_at 必须是带时区时间") from error
        if parsed_approved_at.tzinfo is None:
            raise MissionServiceError("Decision approved_at 必须是带时区时间")
        approved_at = parsed_approved_at.astimezone(UTC)
        instant = self._instant()
        if approved_at > instant:
            raise MissionServiceError("Decision approved_at 晚于当前时间，拒绝物化 Mission")
        source_payload = {
            "decision": decision.to_dict(),
            "plan_hash": plan_hash,
        }
        source_hash = hashlib.sha256(
            json.dumps(
                source_payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        envelope_hash = hashlib.sha256(
            f"{draft.request_id}\n{decision.decision_id}\n{plan_hash}".encode()
        ).hexdigest()
        authority = AuthorityEnvelope(
            envelope_id=f"AUTH-{envelope_hash[:16].upper()}",
            subject_project_id=draft.subject_project_id,
            change_id=decision.change_id,
            decision_id=decision.decision_id,
            authorization_source="CHG_DECISION",
            scope_paths=tuple(decision.approved_files),
            allowed_child_work_kinds=frozenset({WorkKind.WBS}),
            valid_from=approved_at,
            expires_at=instant + timedelta(days=30),
            audit=AuthorityAudit(
                created_by=created_by,
                created_at=instant,
                approved_by=decision.approver,
                approved_at=approved_at,
                source_fingerprint=f"sha256:{source_hash}",
            ),
        )
        return self.create(
            mission_id=mission_id,
            subject_project_id=draft.subject_project_id,
            title=draft.objective,
            objective=draft.objective,
            acceptance_criteria=list(draft.acceptance_criteria),
            authority=authority,
            created_by=created_by,
            idempotency_key=f"planning-mission-create:{draft.request_id}",
        )

    def get(self, mission_id: str) -> Mission:
        try:
            return self._store.get_mission(mission_id)
        except ContinuityStoreError as error:
            raise MissionServiceError(str(error)) from error

    def transition(
        self,
        *,
        mission_id: str,
        expected_version: int,
        new_state: MissionState,
        root_work_id: str | None,
        idempotency_key: str,
    ) -> Mission:
        try:
            current = self._store.get_mission(mission_id)
            instant = self._instant()
            if new_state not in _TRANSITIONS[current.state]:
                raise MissionServiceError(
                    f"Mission 不允许从 {current.state.value} 流转到 {new_state.value}"
                )
            self._assert_authority_is_current(
                current.authority,
                instant,
                allow_safe_block=new_state is MissionState.BLOCKED,
            )
            resolved_root_work_id = self._resolve_root_work(current, new_state, root_work_id)
            return self._store.transition_mission(
                mission_id,
                expected_version,
                new_state,
                resolved_root_work_id,
                idempotency_key,
                instant.isoformat(),
            )
        except ContinuityStoreError as error:
            raise MissionServiceError(str(error)) from error

    def _resolve_root_work(
        self,
        mission: Mission,
        new_state: MissionState,
        requested_root_work_id: str | None,
    ) -> str | None:
        root_work_id = requested_root_work_id or mission.root_work_id
        if (
            requested_root_work_id
            and mission.root_work_id
            and requested_root_work_id != mission.root_work_id
        ):
            raise MissionServiceError("Mission 已绑定 root_work_id，拒绝在生命周期中更换")
        if new_state in {
            MissionState.ACTIVE,
            MissionState.BLOCKED,
            MissionState.ACCEPTANCE_PENDING,
            MissionState.ACCEPTED,
            MissionState.CLOSED,
        }:
            if not root_work_id:
                raise MissionServiceError("目标 Mission 状态必须绑定 root_work_id")
            self._assert_root_work_matches_project(mission.subject_project_id, root_work_id)
        elif requested_root_work_id is not None:
            raise MissionServiceError("DRAFT、AWAITING_APPROVAL 或 CANCELLED 不允许新增 root_work_id")
        return root_work_id

    def _assert_root_work_matches_project(self, subject_project_id: str, root_work_id: str) -> None:
        try:
            work = self._store.get_work(root_work_id)
        except ContinuityStoreError as error:
            raise MissionServiceError(str(error)) from error
        if work.subject_project_id != subject_project_id:
            raise MissionServiceError("root Work 不属于当前 Mission 的 subject project")

    @staticmethod
    def _assert_authority_is_current(
        authority: AuthorityEnvelope,
        instant: datetime,
        *,
        allow_safe_block: bool = False,
    ) -> None:
        if (
            instant < authority.valid_from or instant > authority.expires_at
        ) and not allow_safe_block:
            raise MissionServiceError("AuthorityEnvelope 已过期或尚未生效，拒绝 Mission 写入")

    def _timestamp(self) -> str:
        return self._instant().isoformat()

    def _instant(self) -> datetime:
        value = self._now()
        if value.tzinfo is None:
            raise MissionServiceError("Mission now 必须是带时区时间")
        return value.astimezone(UTC)
