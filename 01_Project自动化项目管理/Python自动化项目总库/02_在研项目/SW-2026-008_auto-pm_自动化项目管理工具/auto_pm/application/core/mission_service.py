"""Mission lifecycle service backed only by the Continuity Store."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.contracts.mission import AuthorityEnvelope, Mission, MissionState
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
    ) -> None:
        self._store = ContinuityStore(workspace_root)
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
    ) -> Mission:
        instant = self._instant()
        now = instant.isoformat()
        self._assert_authority_is_current(authority, instant)
        if subject_project_id != authority.subject_project_id:
            raise MissionServiceError("Mission 与 AuthorityEnvelope subject project 不匹配")
        mission = Mission(
            mission_id=mission_id,
            subject_project_id=subject_project_id,
            title=title,
            objective=objective,
            acceptance_criteria=tuple(acceptance_criteria),
            authority=authority,
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
        if new_state in {
            MissionState.ACTIVE,
            MissionState.BLOCKED,
            MissionState.ACCEPTANCE_PENDING,
            MissionState.ACCEPTED,
            MissionState.CLOSED,
        }:
            if not root_work_id:
                raise MissionServiceError("目标 Mission 状态必须绑定 root_work_id")
            work = self._store.get_work(root_work_id)
            if work.subject_project_id != mission.subject_project_id:
                raise MissionServiceError("root Work 不属于当前 Mission 的 subject project")
        elif requested_root_work_id is not None:
            raise MissionServiceError("DRAFT、AWAITING_APPROVAL 或 CANCELLED 不允许新增 root_work_id")
        return root_work_id

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
