"""User-facing PM workflow built solely on Continuity Store truth."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from auto_pm.core.continuity_resume_service import ContinuityResumeError, ContinuityResumeService
from auto_pm.core.mission_service import MissionService, MissionServiceError
from auto_pm.core.work_registry_service import WorkRegistryError, WorkRegistryService

from auto_pm.contracts.continuity import WorkItem, WorkState
from auto_pm.contracts.continuity_resume import ContinuityResume
from auto_pm.contracts.mission import Mission, MissionState
from auto_pm.contracts.pm_facade import PmConfirmationCard, PmConfirmationKind
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError


class PmFacadeError(RuntimeError):
    """Raised when a user-facing PM action is not legally available."""


class PmFacadeService:
    """Stateless orchestrating facade for a single approved Mission."""

    def __init__(self, workspace_root: str | Path) -> None:
        self._workspace_root = Path(workspace_root)
        self._missions = MissionService(self._workspace_root)
        self._works = WorkRegistryService(self._workspace_root)
        self._store = ContinuityStore(self._workspace_root)

    def plan(self, mission_id: str) -> PmConfirmationCard:
        """Present the first confirmation card and persist only its legal state change."""
        mission = self._mission(mission_id)
        if mission.state is MissionState.DRAFT:
            mission = self._transition(
                mission,
                MissionState.AWAITING_APPROVAL,
                root_work_id=None,
                action="plan",
            )
        if mission.state is not MissionState.AWAITING_APPROVAL:
            raise PmFacadeError("当前 Mission 不能生成开工确认卡")
        return self._card(
            mission,
            PmConfirmationKind.APPROVAL,
            "请确认需求、验收条件和授权边界；确认后驾驶舱才会安排执行。",
            ("approve", "cancel"),
        )

    def approve(self, mission_id: str, root_work_id: str = "") -> PmConfirmationCard:
        """Apply the first approval using the Mission-bound Work when available."""
        mission = self._mission(mission_id)
        requested_root_work_id = root_work_id.strip()
        bound_root_work_id = mission.root_work_id
        if (
            requested_root_work_id
            and bound_root_work_id
            and requested_root_work_id != bound_root_work_id
        ):
            raise PmFacadeError("该需求已绑定其他内部授权，拒绝切换执行范围")
        effective_root_work_id = bound_root_work_id or requested_root_work_id
        if not effective_root_work_id:
            raise PmFacadeError("该需求尚未完成内部授权，暂时不能开始执行")
        if mission.state is MissionState.AWAITING_APPROVAL:
            work = self._work(effective_root_work_id)
            if work.state not in {WorkState.READY, WorkState.IN_PROGRESS}:
                raise PmFacadeError("需求尚未获得对应授权，不能开始执行")
            mission = self._transition(
                mission,
                MissionState.ACTIVE,
                root_work_id=effective_root_work_id,
                action="approve",
            )
        if mission.state is not MissionState.ACTIVE:
            raise PmFacadeError("当前 Mission 不能进入执行态")
        return self._card(
            mission,
            PmConfirmationKind.EXECUTION,
            "已获批准；驾驶舱将在授权边界内安排执行、恢复与分流。",
            ("execute", "resume"),
        )

    def confirm_start(self, mission_id: str) -> PmConfirmationCard:
        """Perform the user's one start confirmation without requesting internal IDs."""
        self.approve(mission_id)
        return self.execute(mission_id)

    def execute(self, mission_id: str) -> PmConfirmationCard:
        """Start the Mission's authorized root Work, without creating hidden state."""
        mission = self._mission(mission_id)
        if mission.state is not MissionState.ACTIVE or not mission.root_work_id:
            raise PmFacadeError("当前 Mission 不在可执行状态")
        work = self._work(mission.root_work_id)
        if work.state is WorkState.READY:
            try:
                self._works.transition(
                    work.work_id,
                    WorkState.IN_PROGRESS,
                    f"pm-execute:{mission.mission_id}:work-v{work.version}",
                )
            except WorkRegistryError as error:
                raise PmFacadeError(str(error)) from error
        elif work.state is not WorkState.IN_PROGRESS:
            raise PmFacadeError("root Work 不在可执行状态")
        return self._card(
            mission,
            PmConfirmationKind.EXECUTION,
            "执行已由驾驶舱接管；只有越出授权边界或需要最终验收时才会打扰你。",
            ("resume",),
        )

    def resume(
        self,
        *,
        project_id: str = "",
        invocation_path: str | None = None,
        work_id: str = "",
        run_id: str = "",
    ) -> ContinuityResume:
        """Return a strictly read-only recovery view for a new PM conversation."""
        try:
            return cast(
                ContinuityResume,
                ContinuityResumeService(self._workspace_root).collect(
                    project_id=project_id,
                    invocation_path=invocation_path,
                    work_id=work_id,
                    run_id=run_id,
                ),
            )
        except ContinuityResumeError as error:
            raise PmFacadeError(str(error)) from error

    def accept(self, mission_id: str) -> PmConfirmationCard:
        """Record only the final user acceptance after verification has reached its gate."""
        mission = self._mission(mission_id)
        if mission.state is MissionState.ACCEPTANCE_PENDING:
            mission = self._transition(
                mission,
                MissionState.ACCEPTED,
                root_work_id=mission.root_work_id,
                action="accept",
            )
        if mission.state is not MissionState.ACCEPTED:
            raise PmFacadeError("当前 Mission 尚未到达用户验收门")
        return self._card(
            mission,
            PmConfirmationKind.ACCEPTANCE,
            "请确认最终验收；确认后驾驶舱才会执行关闭和台账闭环。",
            ("close",),
        )

    @staticmethod
    def compatibility_notice() -> str:
        """Keep the historic name discoverable without loading its quarantined implementation."""
        return "兼容提示：pm-workflow 已退役隔离；请使用 pm plan / approve / execute / resume / accept。"

    def _mission(self, mission_id: str) -> Mission:
        try:
            return cast(Mission, self._missions.get(mission_id))
        except MissionServiceError as error:
            raise PmFacadeError(str(error)) from error

    def _work(self, work_id: str) -> WorkItem:
        try:
            return self._store.get_work(work_id)
        except ContinuityStoreError as error:
            raise PmFacadeError(str(error)) from error

    def _transition(
        self,
        mission: Mission,
        new_state: MissionState,
        *,
        root_work_id: str | None,
        action: str,
    ) -> Mission:
        try:
            return cast(
                Mission,
                self._missions.transition(
                    mission_id=mission.mission_id,
                    expected_version=mission.version,
                    new_state=new_state,
                    root_work_id=root_work_id,
                    idempotency_key=f"pm-{action}:{mission.mission_id}:v{mission.version}",
                ),
            )
        except MissionServiceError as error:
            raise PmFacadeError(str(error)) from error

    @staticmethod
    def _card(
        mission: Mission,
        kind: PmConfirmationKind,
        summary: str,
        next_actions: tuple[str, ...],
    ) -> PmConfirmationCard:
        return PmConfirmationCard(
            kind=kind,
            mission_id=mission.mission_id,
            title=mission.title,
            mission_state=mission.state,
            summary=summary,
            acceptance_criteria=mission.acceptance_criteria,
            next_actions=next_actions,
        )
