"""Fail-closed, read-only projection for the default boss cockpit."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from auto_pm.core.pm_facade_service import PmFacadeError, PmFacadeService

from auto_pm.contracts.continuity import CheckpointItem, RunItem, WorkItem, WorkState
from auto_pm.contracts.mission import Mission, MissionState
from auto_pm.contracts.pm_cockpit import (
    CockpitUserAction,
    PmCockpitCheckpointEvidence,
    PmCockpitEvidence,
    PmCockpitProjectCard,
    PmCockpitSnapshot,
    PmCockpitWorkNode,
)
from auto_pm.contracts.pm_facade import PmConfirmationCard
from auto_pm.contracts.workspace_context import WorkspaceProjectMapping, WorkspaceRegistry
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError


class PmCockpitError(RuntimeError):
    """Raised only for a user-confirmed cockpit action that cannot proceed safely."""


@dataclass(frozen=True)
class _ProjectFacts:
    """Internal, immutable-reader facts used to build one presentation card."""

    missions: tuple[Mission, ...]
    works: tuple[WorkItem, ...]
    runs_by_work: dict[str, tuple[RunItem, ...]]
    checkpoints: tuple[CheckpointItem, ...]


class PmCockpitService:
    """Project the registered workspace without creating indexes, caches, or databases."""

    _REGISTRY_RELATIVE_PATH = Path(
        "SYS-2026-001_WorkspaceGovernance", "workspace_registry.json"
    )

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        registry_path: str | Path | None = None,
        store: ContinuityStore | None = None,
    ) -> None:
        self._workspace_root = Path(workspace_root).resolve()
        selected = Path(registry_path) if registry_path is not None else self._REGISTRY_RELATIVE_PATH
        self._registry_path = (
            selected.resolve()
            if selected.is_absolute()
            else (self._workspace_root / selected).resolve()
        )
        self._store = store or ContinuityStore(self._workspace_root)

    def snapshot(self) -> PmCockpitSnapshot:
        """Return the default screen's complete status without initializing any persistence."""
        try:
            mappings = self._mappings()
        except PmCockpitError as error:
            return PmCockpitSnapshot(projects=(), notices=(str(error),))

        store_note = self._store_note()
        cards: list[PmCockpitProjectCard] = []
        notices: list[str] = [store_note] if store_note else []
        for mapping in mappings:
            if store_note:
                cards.append(self._unavailable_card(mapping, store_note))
                continue
            try:
                cards.append(self._card(mapping, self._facts(mapping.project_id)))
            except (ContinuityStoreError, sqlite3.Error, OSError, ValueError) as error:
                note = "连续性记录无法安全读取；驾驶舱没有尝试修复或重建它。"
                notices.append(f"{mapping.project_id}: {note}")
                cards.append(self._unavailable_card(mapping, note, error))
        return PmCockpitSnapshot(projects=tuple(cards), notices=tuple(dict.fromkeys(notices)))

    def evidence(self, project_id: str) -> PmCockpitEvidence:
        """Return bounded provenance for the evidence drawer, never execution credentials."""
        mapping = self._mapping(project_id)
        store_note = self._store_note()
        if store_note:
            return self._empty_evidence(mapping.project_id, store_note)
        try:
            facts = self._facts(mapping.project_id)
        except (ContinuityStoreError, sqlite3.Error, OSError, ValueError):
            return self._empty_evidence(
                mapping.project_id,
                "连续性记录无法安全读取；未执行修复、迁移或重建。",
            )

        mission = self._primary_mission(facts.missions)
        graph = tuple(
            PmCockpitWorkNode(
                work_id=work.work_id,
                title=work.title,
                state=self._state_label(work.state.value),
                owner=work.owner,
                runs=tuple(
                    f"{run.run_id} · {self._state_label(run.state.value)}"
                    for run in facts.runs_by_work.get(work.work_id, ())
                ),
            )
            for work in facts.works
        )
        checkpoints = tuple(
            PmCockpitCheckpointEvidence(
                checkpoint_id=item.checkpoint_id,
                summary=item.summary,
                evidence=item.evidence,
                created_at=item.created_at,
            )
            for item in facts.checkpoints
        )
        verification = tuple(
            evidence
            for checkpoint in checkpoints
            for evidence in checkpoint.evidence
        )
        return PmCockpitEvidence(
            project_id=mapping.project_id,
            decision_id=mission.authority.decision_id if mission else "",
            change_id=mission.authority.change_id if mission else "",
            read_set=self._read_set(),
            work_graph=graph,
            checkpoints=checkpoints,
            verification_evidence=verification,
            status_note="证据来自不可变只读连续性记录；未读取或展示执行租约。",
        )

    def confirm_start(self, mission_id: str) -> PmConfirmationCard:
        """Apply the first human confirmation without exposing root Work identifiers."""
        try:
            return cast(
                PmConfirmationCard,
                PmFacadeService(self._workspace_root).confirm_start(mission_id),
            )
        except PmFacadeError as error:
            raise PmCockpitError(str(error)) from error

    def confirm_acceptance(self, mission_id: str) -> PmConfirmationCard:
        """Apply final user acceptance after the existing verification gate has opened."""
        try:
            return cast(
                PmConfirmationCard,
                PmFacadeService(self._workspace_root).accept(mission_id),
            )
        except PmFacadeError as error:
            raise PmCockpitError(str(error)) from error

    def _mappings(self) -> tuple[WorkspaceProjectMapping, ...]:
        self._require_workspace_path(self._registry_path)
        if not self._registry_path.is_file():
            raise PmCockpitError("工作空间项目清单不存在，驾驶舱已保持只读并停止加载。")
        try:
            registry = WorkspaceRegistry.model_validate_json(
                self._registry_path.read_text(encoding="utf-8", errors="replace")
            )
        except (OSError, ValueError) as error:
            raise PmCockpitError("工作空间项目清单格式无效，驾驶舱没有猜测项目归属。") from error
        return registry.projects

    def _mapping(self, project_id: str) -> WorkspaceProjectMapping:
        for mapping in self._mappings():
            if mapping.project_id == project_id:
                return mapping
        raise PmCockpitError("该项目不在工作空间项目清单中，无法显示未经登记的状态。")

    def _store_note(self) -> str:
        if not self._store.db_path.is_file():
            return "尚未建立连续性记录；驾驶舱仅显示项目清单，未创建任何数据。"
        return ""

    def _facts(self, project_id: str) -> _ProjectFacts:
        missions = self._store.list_missions(project_id, include_terminal=True)
        works = self._store.list_works(project_id, include_terminal=True)
        runs_by_work = {
            work.work_id: self._store.list_runs(work.work_id, include_terminal=True)
            for work in works
        }
        checkpoints = tuple(
            checkpoint
            for runs in runs_by_work.values()
            for run in runs
            if (checkpoint := self._store.latest_checkpoint(run.run_id)) is not None
        )
        return _ProjectFacts(
            missions=missions,
            works=works,
            runs_by_work=runs_by_work,
            checkpoints=checkpoints,
        )

    def _card(
        self, mapping: WorkspaceProjectMapping, facts: _ProjectFacts
    ) -> PmCockpitProjectCard:
        mission = self._primary_mission(facts.missions)
        work = self._primary_work(mission, facts.works)
        blocked = self._is_blocked(mission, work, facts.runs_by_work)
        action, next_action = self._next_action(mission, blocked)
        return PmCockpitProjectCard(
            project_id=mapping.project_id,
            project_name=self._project_name(mapping),
            mission=mission.title if mission else "暂无进行中的需求",
            mission_id=mission.mission_id if mission else "",
            milestone=self._milestone(mission),
            progress=self._progress(mission, work),
            blocked=blocked,
            verification=self._verification(mission, work, facts.runs_by_work),
            risk=self._risk(mission, blocked),
            current_owner=work.owner if work else "驾驶舱待命",
            next_user_action=next_action,
            user_action=action,
        )

    def _unavailable_card(
        self,
        mapping: WorkspaceProjectMapping,
        note: str,
        error: Exception | None = None,
    ) -> PmCockpitProjectCard:
        detail = "无法读取" if error is not None else "尚未建立"
        return PmCockpitProjectCard(
            project_id=mapping.project_id,
            project_name=self._project_name(mapping),
            mission="暂无可核验的需求记录",
            milestone="等待连续性记录",
            progress="未启动",
            blocked=False,
            verification=f"{detail}验证记录",
            risk="中：需要先恢复可验证的治理记录",
            current_owner="驾驶舱待命",
            next_user_action="向 PM 描述需求；系统不会自动修复记录",
            user_action=CockpitUserAction.NONE,
        )

    def _empty_evidence(self, project_id: str, note: str) -> PmCockpitEvidence:
        return PmCockpitEvidence(
            project_id=project_id,
            read_set=self._read_set(),
            work_graph=(),
            checkpoints=(),
            verification_evidence=(),
            status_note=note,
        )

    @staticmethod
    def _primary_mission(missions: tuple[Mission, ...]) -> Mission | None:
        terminal = {MissionState.ACCEPTED, MissionState.CLOSED, MissionState.CANCELLED}
        return next((mission for mission in missions if mission.state not in terminal), None) or (
            missions[0] if missions else None
        )

    @staticmethod
    def _primary_work(mission: Mission | None, works: tuple[WorkItem, ...]) -> WorkItem | None:
        if mission and mission.root_work_id:
            for work in works:
                if work.work_id == mission.root_work_id:
                    return work
        return next(
            (work for work in works if work.state not in {WorkState.CLOSED, WorkState.CANCELLED}),
            works[0] if works else None,
        )

    @staticmethod
    def _is_blocked(
        mission: Mission | None,
        work: WorkItem | None,
        runs_by_work: dict[str, tuple[RunItem, ...]],
    ) -> bool:
        return bool(
            mission and mission.state is MissionState.BLOCKED
        ) or bool(work and work.state is WorkState.BLOCKED) or any(
            run.state.value == "BLOCKED" for runs in runs_by_work.values() for run in runs
        )

    @staticmethod
    def _milestone(mission: Mission | None) -> str:
        if mission is None:
            return "需求准备"
        labels = {
            MissionState.DRAFT: "需求准备",
            MissionState.AWAITING_APPROVAL: "等待开工确认",
            MissionState.ACTIVE: "系统执行",
            MissionState.BLOCKED: "等待决策",
            MissionState.ACCEPTANCE_PENDING: "等待验收确认",
            MissionState.ACCEPTED: "验收完成",
            MissionState.CLOSED: "已关闭",
            MissionState.CANCELLED: "已取消",
        }
        return labels[mission.state]

    @staticmethod
    def _progress(mission: Mission | None, work: WorkItem | None) -> str:
        if mission is None:
            return "未启动"
        if mission.state is MissionState.ACTIVE and work and work.state is WorkState.IN_PROGRESS:
            return "执行中"
        if mission.state is MissionState.ACCEPTANCE_PENDING:
            return "等待验收"
        return PmCockpitService._milestone(mission)

    @staticmethod
    def _verification(
        mission: Mission | None,
        work: WorkItem | None,
        runs_by_work: dict[str, tuple[RunItem, ...]],
    ) -> str:
        if mission and mission.state is MissionState.ACCEPTANCE_PENDING:
            return "验证已完成，等待您的验收确认"
        if mission and mission.state in {MissionState.ACCEPTED, MissionState.CLOSED}:
            return "已保存验证证据"
        if work and work.state is WorkState.VERIFYING:
            return "正在验证"
        if any(run.state.value == "VERIFYING" for runs in runs_by_work.values() for run in runs):
            return "正在验证"
        return "尚无验证结论" if mission is None else "等待执行验证"

    @staticmethod
    def _risk(mission: Mission | None, blocked: bool) -> str:
        if blocked:
            return "高：存在需要您决策的阻塞事项"
        if mission is None:
            return "低：尚未开始"
        if mission.state is MissionState.ACCEPTANCE_PENDING:
            return "低：仅等待最终验收"
        return "低：在既定授权范围内"

    @staticmethod
    def _next_action(mission: Mission | None, blocked: bool) -> tuple[CockpitUserAction, str]:
        if blocked:
            return CockpitUserAction.REVIEW_ESCALATION, "查看需要您决策的事项"
        if mission is None:
            return CockpitUserAction.NONE, "向 PM 描述您的需求"
        if mission.state is MissionState.AWAITING_APPROVAL:
            return CockpitUserAction.CONFIRM_START, "确认开始执行"
        if mission.state is MissionState.ACCEPTANCE_PENDING:
            return CockpitUserAction.CONFIRM_ACCEPTANCE, "确认最终验收"
        if mission.state is MissionState.ACTIVE:
            return CockpitUserAction.NONE, "无需操作，驾驶舱正在处理"
        return CockpitUserAction.NONE, "向 PM 描述下一项需求"

    def _read_set(self) -> tuple[str, ...]:
        paths = [self._relative(self._registry_path)]
        if self._store.db_path.is_file():
            paths.append(self._relative(self._store.db_path))
        return tuple(paths)

    @staticmethod
    def _state_label(value: str) -> str:
        return {
            "PLANNED": "待安排",
            "READY": "已授权",
            "IN_PROGRESS": "执行中",
            "BLOCKED": "已阻塞",
            "VERIFYING": "验证中",
            "ACCEPTED": "已验收",
            "CLOSED": "已关闭",
            "CANCELLED": "已取消",
            "RUNNING": "执行中",
            "SUCCEEDED": "已完成",
            "FAILED": "失败",
        }.get(value, value)

    @staticmethod
    def _project_name(mapping: WorkspaceProjectMapping) -> str:
        leaf = Path(mapping.project_root).name
        prefix = f"{mapping.project_id}_"
        return leaf.removeprefix(prefix).replace("_", " ") or mapping.project_id

    def _relative(self, path: Path) -> str:
        self._require_workspace_path(path)
        return path.relative_to(self._workspace_root).as_posix()

    def _require_workspace_path(self, path: Path) -> None:
        try:
            path.relative_to(self._workspace_root)
        except ValueError as error:
            raise PmCockpitError("驾驶舱拒绝读取工作空间外的路径。") from error
