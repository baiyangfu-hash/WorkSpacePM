"""User-facing PM workflow built solely on Continuity Store truth."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from auto_pm.change.change_service import ChangeService
from auto_pm.core.continuity_resume_service import ContinuityResumeError, ContinuityResumeService
from auto_pm.core.mission_service import MissionService, MissionServiceError
from auto_pm.core.work_registry_service import WorkRegistryError, WorkRegistryService

from auto_pm.contracts.continuity import WorkItem, WorkState
from auto_pm.contracts.continuity_resume import ContinuityResume
from auto_pm.contracts.mission import Mission, MissionState
from auto_pm.contracts.pm_facade import (
    PlanningDraft,
    PmConfirmationCard,
    PmConfirmationKind,
    PmIntent,
)
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError


class PmFacadeError(RuntimeError):
    """Raised when a user-facing PM action is not legally available."""


class PmFacadeService:
    """Stateless orchestrating facade for a single approved Mission."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        store: ContinuityStore | None = None,
        change_service: ChangeService | None = None,
    ) -> None:
        self._workspace_root = Path(workspace_root)
        self._missions = MissionService(self._workspace_root)
        self._works = WorkRegistryService(self._workspace_root)
        self._store = store or ContinuityStore(self._workspace_root)
        self._changes = change_service or ChangeService(str(self._workspace_root))

    def create_planning_draft(self, intent: PmIntent) -> PlanningDraft:
        """Persist a pre-authorization draft without creating executable state."""

        try:
            return self._store.create_planning_draft(PlanningDraft.from_intent(intent))
        except ContinuityStoreError as error:
            raise PmFacadeError(str(error)) from error

    def create_planning_draft_change(self, intent: PmIntent) -> str:
        """Create or replay the one pre-authorization CHG for a PlanningDraft."""

        draft = self.create_planning_draft(intent)
        try:
            candidate_change_id = self._changes.next_change_number(
                draft.subject_project_id, "SCPT"
            )
            change_id = self._store.reserve_planning_draft_change(
                draft.request_id, candidate_change_id
            )
            change = self._changes.create_change_request(
                project_id=draft.subject_project_id,
                domain="SCPT",
                business_nature="DEF",
                impact_scope=["MODULE"],
                applicant="PM Facade",
                background=draft.objective,
                necessity="PlanningDraft 需生成可审查的真实 CHG 草稿。",
                references=f"PlanningDraft request_id={draft.request_id}; "
                f"input_fingerprint={draft.input_fingerprint}",
                change_number=change_id,
            )
        except (ContinuityStoreError, ValueError) as error:
            raise PmFacadeError(str(error)) from error
        if change.change_number != change_id or change.status != "draft":
            raise PmFacadeError("PlanningDraft 绑定的 CHG 必须保持 DRAFT，不能进入执行")
        return change_id

    def bind_planning_draft_specs(self, intent: PmIntent) -> tuple[tuple[str, str, str], ...]:
        """Bind a PlanningDraft to the effective Python and PLC spec sources."""

        draft = self.create_planning_draft(intent)
        try:
            return self._store.bind_planning_draft_specs(
                draft.request_id, self._effective_spec_sources()
            )
        except ContinuityStoreError as error:
            raise PmFacadeError(str(error)) from error

    def _effective_spec_sources(self) -> tuple[tuple[str, str, str], ...]:
        registry_path = self._workspace_root / "00_Obsidian_Base全局规范文件仓库" / "spec_registry.json"
        try:
            payload = json.loads(registry_path.read_text(encoding="utf-8", errors="replace"))
        except FileNotFoundError as error:
            raise PmFacadeError(f"规范注册表不存在: {registry_path}") from error
        except json.JSONDecodeError as error:
            raise PmFacadeError(f"规范注册表 JSON 无效: {error.msg}") from error
        specs = payload.get("specs") if isinstance(payload, dict) else None
        if not isinstance(specs, dict):
            raise PmFacadeError("规范注册表缺少 specs 对象")
        sources: list[tuple[str, str, str]] = []
        covered_domains: set[str] = set()
        for spec_id, raw in specs.items():
            if not isinstance(spec_id, str) or not isinstance(raw, dict):
                raise PmFacadeError("规范注册表含无效条目")
            entry = cast(dict[str, Any], raw)
            domain = entry.get("domain")
            lifecycle = entry.get("lifecycle")
            if domain not in {"python", "plc"} or lifecycle not in {"stable", "active"}:
                continue
            canonical_path = entry.get("canonical_path")
            version = entry.get("version")
            if not isinstance(canonical_path, str) or not canonical_path.strip():
                raise PmFacadeError(f"规范 {spec_id} 缺少 canonical_path")
            if not isinstance(version, str) or not version.strip():
                raise PmFacadeError(f"规范 {spec_id} 缺少 version")
            resolved = (self._workspace_root / canonical_path).resolve()
            try:
                resolved.relative_to(self._workspace_root.resolve())
            except ValueError as error:
                raise PmFacadeError(f"规范 {spec_id} 路径越出工作区: {canonical_path}") from error
            if not resolved.is_file():
                raise PmFacadeError(f"规范文件不存在: {spec_id} -> {canonical_path}")
            covered_domains.add(domain)
            sources.append((spec_id, canonical_path, version))
        missing = {"python", "plc"} - covered_domains
        if missing:
            raise PmFacadeError(f"规范注册表缺少有效领域: {', '.join(sorted(missing))}")
        return tuple(sorted(sources))

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
