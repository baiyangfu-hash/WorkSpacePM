"""Fail-closed, read-only projection for the default boss cockpit."""

from __future__ import annotations

import hashlib
import logging
import secrets
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from auto_pm.core.continuity_query_service import ContinuityQueryService
from auto_pm.core.mission_admission import admission_verdict
from auto_pm.core.pm_closure_service import (
    ClosureCompletionState,
    PmClosureError,
    PmClosureService,
)
from auto_pm.core.pm_facade_service import PmFacadeError, PmFacadeService

from auto_pm.contracts.continuity import (
    CheckpointItem,
    RunItem,
    RunState,
    WorkItem,
    WorkState,
)
from auto_pm.contracts.continuity_query import validate_runtime_capabilities
from auto_pm.contracts.execution_adapter import (
    ExecutionActivity,
    ExecutionActivityStage,
    ExecutionFailureCode,
    WorktreeMode,
)
from auto_pm.contracts.mission import (
    OPEN_MISSION_SOFT_LIMIT,
    PARKED_STALE_DAYS,
    Mission,
    MissionBoard,
    MissionState,
)
from auto_pm.contracts.pm_cockpit import (
    CockpitUserAction,
    PmCockpitActivity,
    PmCockpitBoardCard,
    PmCockpitCheckpointEvidence,
    PmCockpitCompletion,
    PmCockpitCompletionState,
    PmCockpitEvidence,
    PmCockpitEvidenceCurrency,
    PmCockpitFocus,
    PmCockpitMissionBoard,
    PmCockpitPendingScopeCard,
    PmCockpitProjectCard,
    PmCockpitResume,
    PmCockpitResumeState,
    PmCockpitSnapshot,
    PmCockpitWorkNode,
)
from auto_pm.contracts.pm_facade import PlanningApprovalResult, PmConfirmationCard, PmRunOutcome
from auto_pm.contracts.workspace_context import WorkspaceProjectMapping, WorkspaceRegistry
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError

log = logging.getLogger(__name__)

_TERMINAL_MISSION_STATES = frozenset({MissionState.CLOSED, MissionState.CANCELLED})
_CLOSE_PREPARE_KEY = "cockpit-close-prepare:"
_CLOSE_COMPLETE_KEY = "cockpit-close-complete:"
_COMPLETED_MESSAGE = "已完成：变更单与台账已同步。"
_PENDING_SYNC_MESSAGE = "台账同步未完成，已保留现场；可稍后重试。"
_NOT_READY_MESSAGE = "无法完成收尾：必要证据或状态未就绪，已保留现场；请向 PM 说明。"
_SYNC_PENDING_NOTE = "验收已记录，变更单与台账尚未同步完成；完成前不会显示为已完成。"
_SYNC_COMPLETED_NOTE = "已验收并完成变更单与台账同步。"
_UNVERIFIABLE_REASON = "无法核验验收证据：读取失败，未做任何修复。"
_REASON_LIMIT = 200
_LEASE_ENVIRONMENT = "AUTO_PM_EXECUTION_LEASE_TOKEN"
_START_READY_REASON = "等待您确认开工；确认前不会创建或启动任何执行。"
_ALREADY_VERIFIED_MESSAGE = "该需求已执行并验证，等待验收；请直接确认验收，不要重复执行。"
_APPROVER_MISSING_REASON = "未配置批准人，不能批准；请先设置环境变量 AUTO_PM_COCKPIT_APPROVER。"
_ADMISSION_RELEASE_HINT = "。放行请在命令行用 pm approve --admission-release-ref。"


def _clip(text: str) -> str:
    """Bound a user-facing reason to the contract limit without altering short text."""
    return text if len(text) <= _REASON_LIMIT else text[: _REASON_LIMIT - 1] + "…"


class PmCockpitError(RuntimeError):
    """Raised only for a user-confirmed cockpit action that cannot proceed safely."""


@dataclass(frozen=True)
class _ProjectFacts:
    """Internal, immutable-reader facts used to build one presentation card."""

    missions: tuple[Mission, ...]
    works: tuple[WorkItem, ...]
    runs_by_work: dict[str, tuple[RunItem, ...]]
    checkpoints: tuple[CheckpointItem, ...]
    started_run_ids: frozenset[str]


_EXPECTED_CAPABILITIES = {"PARK": "SUPPORTED", "RESUME_PARKED": "SUPPORTED", "PREEMPT": "UNSUPPORTED"}
_CAPABILITY_DECLARED = (
    "挂起与拿回：支持，只在命令行做（pm park / pm unpark / pm switch），拿回哪张只听用户的；"
    "运行中插队：不支持（能力查询 runtime-capabilities.v2）。驾驶舱只显示四栏，不提供切换按钮。"
)
_BOARD_CLOSED_SHOWN = 5
_CAPABILITY_UNVERIFIED = "挂起与插队的能力查询未能确认；为安全起见这些操作保持停用，驾驶舱不会假装挂起。"


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
        closure_service: PmClosureService | None = None,
        facade: PmFacadeService | None = None,
        approver: str = "",
        control_root: str | Path | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        # ``workspace_root`` is where the GUI was started (the execution root, possibly a linked candidate);
        # ``control_root`` is the governed main root that owns the registry, the store and every write.
        self._workspace_root = Path(workspace_root).resolve()
        self._control_root = Path(control_root).resolve() if control_root is not None else self._workspace_root
        selected = Path(registry_path) if registry_path is not None else self._REGISTRY_RELATIVE_PATH
        self._registry_path = (
            selected.resolve()
            if selected.is_absolute()
            else (self._control_root / selected).resolve()
        )
        self._store = store or ContinuityStore(self._control_root)
        self._closure_service = closure_service
        self._facade_override = facade
        self._approver = approver.strip()
        self._now = now or (lambda: datetime.now(UTC))

    def _real_facade(self) -> PmFacadeService:
        """The facade of the governed control root; execution runs against the GUI's own root."""
        return PmFacadeService(self._control_root, execution_root=self._workspace_root)

    def snapshot(self) -> PmCockpitSnapshot:
        """Return the default screen's complete status without initializing any persistence."""
        try:
            mappings = self._mappings()
        except PmCockpitError as error:
            return PmCockpitSnapshot(projects=(), notices=(str(error),))

        store_note = self._store_note()
        cards: list[PmCockpitProjectCard] = []
        activities: list[PmCockpitActivity] = []
        pending: list[PmCockpitPendingScopeCard] = []
        boards: list[PmCockpitMissionBoard] = []
        notices: list[str] = [store_note] if store_note else []
        for mapping in mappings:
            if store_note:
                cards.append(self._unavailable_card(mapping, store_note))
                continue
            try:
                facts = self._facts(mapping.project_id)
                cards.append(self._card(mapping, facts))
                activities.extend(self._activities(mapping.project_id, facts))
                pending.extend(self._pending_cards(mapping, facts, notices))
                boards.append(self._board(mapping, self._store.list_missions_by_board(mapping.project_id)))
            except (ContinuityStoreError, sqlite3.Error, OSError, ValueError) as error:
                note = "连续性记录无法安全读取；驾驶舱没有尝试修复或重建它。"
                notices.append(f"{mapping.project_id}: {note}")
                cards.append(self._unavailable_card(mapping, note, error))
        notices.append(self._capability_notice())
        return PmCockpitSnapshot(
            projects=tuple(cards),
            activities=tuple(activities),
            pending_cards=tuple(pending),
            boards=tuple(boards),
            notices=tuple(dict.fromkeys(notices)),
        )

    def _board(self, mapping: WorkspaceProjectMapping, board: MissionBoard) -> PmCockpitMissionBoard:
        """The four columns, read-only (TD-071 card 4): who is in hand, who waits for you, who is put down and why."""

        now = self._now()

        def plain(mission: Mission) -> PmCockpitBoardCard:
            return PmCockpitBoardCard(
                mission_id=mission.mission_id, title=mission.title, state_label=self._milestone(mission)
            )

        parked = []
        for item in board.parked:
            days = (now - item.park.parked_at).total_seconds() / 86_400
            stale = days > PARKED_STALE_DAYS
            note = (
                f"为什么放下：{item.park.reason}；断点：{item.checkpoint_summary}；"
                f"放下于 {ContinuityStore.local_time_text(item.park.parked_at.isoformat())}"
            )
            if stale:
                note += f"；已搁着超过 {PARKED_STALE_DAYS} 天，请决定拿回还是作废"
            parked.append(
                PmCockpitBoardCard(
                    mission_id=item.mission.mission_id,
                    title=item.mission.title,
                    state_label=self._milestone(item.mission),
                    note=note,
                    stale=stale,
                )
            )
        shown_closed = board.closed[:_BOARD_CLOSED_SHOWN]
        return PmCockpitMissionBoard(
            project_id=mapping.project_id,
            project_name=self._project_name(mapping),
            open_count=board.open_count,
            open_limit=OPEN_MISSION_SOFT_LIMIT,
            active=tuple(plain(mission) for mission in board.active),
            waiting=tuple(plain(mission) for mission in board.waiting),
            parked=tuple(parked),
            closed=tuple(plain(mission) for mission in shown_closed),
            closed_hidden=len(board.closed) - len(shown_closed),
        )

    @staticmethod
    def _capability_notice() -> str:
        """Say what the shared query declares about parking and pre-emption; anything unexpected keeps them off."""
        try:
            capabilities = validate_runtime_capabilities(ContinuityQueryService.capabilities())
        except (TypeError, ValueError):
            return _CAPABILITY_UNVERIFIED
        declared = {item.action.value: item.status for item in capabilities.actions}
        if (
            capabilities.parking_supported is not True
            or capabilities.preemption_supported
            or declared != _EXPECTED_CAPABILITIES
        ):
            return _CAPABILITY_UNVERIFIED
        return _CAPABILITY_DECLARED

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
        work = self._primary_work(mission, facts.works)
        run = (
            self._primary_run(facts.runs_by_work.get(work.work_id, ()))
            if mission and work
            else None
        )
        focus = PmCockpitFocus(
            mission_id=mission.mission_id if mission else "",
            work_id=work.work_id if mission and work else "",
            run_id=run.run_id if run else "",
            run_state=self._state_label(run.state.value) if run else "",
        )
        currency, currency_reason = self._evidence_currency(mission)
        resume = self._resume(mission, work, run, facts, currency, currency_reason)
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
                run_id=item.run_id,
                is_current_run=bool(focus.run_id) and item.run_id == focus.run_id,
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
            focus=focus,
            evidence_currency=currency,
            evidence_currency_reason=currency_reason,
            resume=resume,
        )

    def confirm_start(self, mission_id: str) -> PmConfirmationCard:
        """Apply the first human confirmation without exposing root Work identifiers."""
        try:
            return cast(
                PmConfirmationCard,
                self._real_facade().confirm_start(mission_id),
            )
        except PmFacadeError as error:
            raise PmCockpitError(str(error)) from error

    def start_execution(self, mission_id: str) -> PmRunOutcome:
        """Run one approved Mission in isolation and verify it; keep this off the UI thread."""

        mission_id = mission_id.strip()
        if not mission_id:
            raise PmCockpitError("未找到可启动的需求。")
        try:
            mission = self._store.get_mission(mission_id)
        except (ContinuityStoreError, sqlite3.Error, OSError, ValueError) as error:
            raise PmCockpitError("无法读取该需求，已保留现场。") from error
        if mission.state is MissionState.ACCEPTANCE_PENDING:
            raise PmCockpitError(_ALREADY_VERIFIED_MESSAGE)
        if mission.state not in {
            MissionState.DRAFT,
            MissionState.AWAITING_APPROVAL,
            MissionState.ACTIVE,
        }:
            raise PmCockpitError("该需求当前不能开始执行。")
        facade = self._facade_override or self._real_facade()
        try:
            card = facade.recover_planning_scope_card(mission_id)
            return cast(
                PmRunOutcome,
                facade.run_approved_planning(
                    card,
                    expected_plan_hash=card.plan_hash,
                    lease_token=secrets.token_urlsafe(32),
                    lease_token_environment=_LEASE_ENVIRONMENT,
                ),
            )
        except PmFacadeError as error:
            raise PmCockpitError(str(error)) from error

    def approve_scope(self, request_id: str, plan_hash: str) -> PlanningApprovalResult:
        """Apply the user's one scope approval; the approver comes from configuration only."""

        request_id, plan_hash = request_id.strip(), plan_hash.strip()
        if not request_id or not plan_hash:
            raise PmCockpitError("未找到要批准的范围卡。")
        if not self._approver:
            raise PmCockpitError(_APPROVER_MISSING_REASON)
        facade = self._facade_override or self._real_facade()
        try:
            return cast(
                PlanningApprovalResult,
                facade.approve_pending_planning_scope_card(
                    request_id,
                    expected_plan_hash=plan_hash,
                    approver=self._approver,
                    approval_evidence_ref=self._approval_evidence(plan_hash),
                ),
            )
        except PmFacadeError as error:
            raise PmCockpitError(str(error)) from error

    def _approval_evidence(self, plan_hash: str) -> str:
        """Deterministic, secret-free reference to this cockpit click, so a retry is idempotent."""

        who = hashlib.sha256(self._approver.encode("utf-8")).hexdigest()[:8]
        return f"user-confirmation:cockpit-{plan_hash[:16]}-{who}"

    def confirm_acceptance(self, mission_id: str) -> PmConfirmationCard:
        """Apply final user acceptance after the existing verification gate has opened."""
        try:
            return cast(
                PmConfirmationCard,
                self._real_facade().accept(mission_id),
            )
        except PmFacadeError as error:
            raise PmCockpitError(str(error)) from error

    def close_accepted(self, mission_id: str) -> PmCockpitCompletion:
        """Close one accepted Mission through the closure service; callers must keep this
        off the UI thread.  Only a COMPLETED closure receipt yields COMPLETED."""
        mission_id = mission_id.strip()
        if not mission_id:
            raise PmCockpitError("未找到可收尾的需求。")
        try:
            mission = self._store.get_mission(mission_id)
        except (ContinuityStoreError, sqlite3.Error, OSError, ValueError) as error:
            raise PmCockpitError("无法读取该需求，已保留现场。") from error
        if mission.state is MissionState.CLOSED:
            return PmCockpitCompletion(
                mission_id=mission_id,
                state=PmCockpitCompletionState.COMPLETED,
                message=_COMPLETED_MESSAGE,
            )
        if mission.state is not MissionState.ACCEPTED:
            raise PmCockpitError("该需求尚未验收，不能收尾。")
        closure = self._closure_service or PmClosureService(
            self._control_root, store=self._store
        )
        try:
            preparation = closure.prepare_closure(
                mission_id, idempotency_key=_CLOSE_PREPARE_KEY + mission_id
            )
            receipt = closure.complete_closure(
                preparation.closure.closure_id,
                idempotency_key=_CLOSE_COMPLETE_KEY + mission_id,
            )
        except PmClosureError:
            log.exception("Cockpit closure refused: %s", mission_id)
            return PmCockpitCompletion(
                mission_id=mission_id,
                state=PmCockpitCompletionState.PENDING_SYNC,
                message=_NOT_READY_MESSAGE,
            )
        if receipt.state is ClosureCompletionState.COMPLETED:
            return PmCockpitCompletion(
                mission_id=mission_id,
                state=PmCockpitCompletionState.COMPLETED,
                message=_COMPLETED_MESSAGE,
            )
        log.warning("Cockpit closure pending sync: %s", mission_id)
        return PmCockpitCompletion(
            mission_id=mission_id,
            state=PmCockpitCompletionState.PENDING_SYNC,
            message=_PENDING_SYNC_MESSAGE,
        )

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
        started_run_ids: set[str] = set()
        for runs in runs_by_work.values():
            for run in runs:
                try:
                    self._store.get_run_started_evidence(run.run_id)
                except ContinuityStoreError:
                    continue
                started_run_ids.add(run.run_id)
        return _ProjectFacts(
            missions=missions,
            works=works,
            runs_by_work=runs_by_work,
            checkpoints=checkpoints,
            started_run_ids=frozenset(started_run_ids),
        )

    def _card(
        self, mapping: WorkspaceProjectMapping, facts: _ProjectFacts
    ) -> PmCockpitProjectCard:
        mission = self._primary_mission(facts.missions)
        work = self._primary_work(mission, facts.works)
        blocked = self._is_blocked(mission, work, facts.runs_by_work)
        action, next_action = self._next_action(mission, blocked)
        completion_state, completion_note = self._completion(mission)
        return PmCockpitProjectCard(
            project_id=mapping.project_id,
            project_name=self._project_name(mapping),
            mission=mission.title if mission else "暂无进行中的需求",
            mission_id=mission.mission_id if mission else "",
            milestone=self._milestone(mission),
            progress=self._progress(
                mission, work, facts.runs_by_work, facts.started_run_ids
            ),
            blocked=blocked,
            verification=self._verification(mission, work, facts.runs_by_work),
            risk=self._risk(mission, blocked),
            current_owner=work.owner if work else "驾驶舱待命",
            next_user_action=next_action,
            user_action=action,
            completion_state=completion_state,
            completion_note=completion_note,
        )

    @staticmethod
    def _completion(mission: Mission | None) -> tuple[PmCockpitCompletionState, str]:
        """Completion is a pure function of the Mission state: only CLOSED is complete."""
        if mission is not None and mission.state is MissionState.CLOSED:
            return PmCockpitCompletionState.COMPLETED, _SYNC_COMPLETED_NOTE
        if mission is not None and mission.state is MissionState.ACCEPTED:
            return PmCockpitCompletionState.PENDING_SYNC, _SYNC_PENDING_NOTE
        return PmCockpitCompletionState.NOT_STARTED, ""

    def _pending_cards(
        self,
        mapping: WorkspaceProjectMapping,
        facts: _ProjectFacts,
        notices: list[str],
    ) -> tuple[PmCockpitPendingScopeCard, ...]:
        """Pending scope cards of one project; an unreadable record never hides the project card."""

        try:
            submitted = self._store.list_pending_planning_scope_cards(mapping.project_id)
        except (ContinuityStoreError, sqlite3.Error, OSError, ValueError):
            notices.append(
                f"{mapping.project_id}: 待批准范围卡无法安全读取；驾驶舱没有尝试修复或重建它。"
            )
            return ()
        def blocked_reason(scope_paths: tuple[str, ...]) -> str:
            if not self._approver:
                return _APPROVER_MISSING_REASON
            # TD-071 card 3: past the soft limit or over an open card's paths, the button stays off and
            # the reason says why; the user's word is given on the command line (pm approve --admission-release-ref).
            verdict = admission_verdict(facts.missions, scope_paths)
            return _clip(verdict.reason() + _ADMISSION_RELEASE_HINT) if verdict.needs_user_release else ""

        return tuple(
            PmCockpitPendingScopeCard(
                project_id=mapping.project_id,
                project_name=self._project_name(mapping),
                request_id=item.card.request_id,
                plan_hash=item.card.plan_hash,
                revision=item.revision,
                objective=item.objective,
                acceptance_criteria=item.card.acceptance_criteria,
                scope_paths=item.card.scope_paths,
                risks=item.card.risks,
                non_goals=item.card.non_goals,
                executor=(
                    f"{item.card.execution_grant.adapter.value} · "
                    f"{item.card.execution_grant.approved_model}"
                ),
                submitted_by=item.submitted_by,
                submitted_at=item.submitted_at,
                approver=self._approver,
                can_approve=not blocked_reason(item.card.scope_paths),
                approve_blocked_reason=blocked_reason(item.card.scope_paths),
            )
            for item in submitted
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

    def _activities(
        self,
        project_id: str,
        facts: _ProjectFacts,
    ) -> tuple[PmCockpitActivity, ...]:
        mission = self._primary_mission(facts.missions)
        if mission is None or not mission.root_work_id:
            return ()
        runs = facts.runs_by_work.get(mission.root_work_id, ())
        run = self._primary_run(runs)
        if run is None:
            return ()
        return tuple(
            self._activity(project_id, mission, mission.root_work_id, activity)
            for activity in self._store.list_run_activities(run.run_id)
        )

    @staticmethod
    def _primary_run(runs: tuple[RunItem, ...]) -> RunItem | None:
        terminal = {RunState.SUCCEEDED, RunState.FAILED, RunState.CANCELLED}
        return next((run for run in runs if run.state not in terminal), None) or (
            runs[0] if runs else None
        )

    @staticmethod
    def _activity(
        project_id: str,
        mission: Mission,
        work_id: str,
        activity: ExecutionActivity,
    ) -> PmCockpitActivity:
        titles = {
            ExecutionActivityStage.READY: "执行已授权",
            ExecutionActivityStage.STARTING: "正在启动",
            ExecutionActivityStage.RUNNING: "执行进程已启动",
            ExecutionActivityStage.PROJECTED: "执行结果已投影",
            ExecutionActivityStage.VERIFYING: "正在验证",
            ExecutionActivityStage.CHECKPOINTED: "验证证据已保存",
            ExecutionActivityStage.BLOCKED: "执行被阻塞",
            ExecutionActivityStage.PENDING: "执行状态待核验",
            ExecutionActivityStage.SUCCEEDED: "执行已完成",
            ExecutionActivityStage.FAILED: "执行失败",
            ExecutionActivityStage.CANCELLED: "执行已取消",
        }
        failure_labels = {
            ExecutionFailureCode.LOCAL_START_FAILED: "本地执行器启动失败",
            ExecutionFailureCode.HANDSHAKE_FAILED: "执行握手失败",
            ExecutionFailureCode.START_EVIDENCE_REJECTED: "启动证据未获接受",
            ExecutionFailureCode.CHILD_REAP_FAILED: "子进程回收未能确认",
            ExecutionFailureCode.COLLECTION_PENDING: "执行结果仍待收集",
            ExecutionFailureCode.TERMINATED: "执行进程被终止",
            ExecutionFailureCode.NONZERO_EXIT: "执行命令返回非零状态",
            ExecutionFailureCode.EXECUTOR_FAILED: "执行器报告失败",
            ExecutionFailureCode.PROJECTION_FAILED: "结果投影失败",
            ExecutionFailureCode.LEGACY_UNKNOWN: "历史原因未记录",
        }
        success = {
            ExecutionActivityStage.PROJECTED,
            ExecutionActivityStage.CHECKPOINTED,
            ExecutionActivityStage.SUCCEEDED,
        }
        warning = {
            ExecutionActivityStage.BLOCKED,
            ExecutionActivityStage.PENDING,
            ExecutionActivityStage.CANCELLED,
        }
        failure_code = activity.failure.code if activity.failure else None
        description = (
            failure_labels[failure_code]
            if failure_code is not None
            else f"canonical 事件：{activity.event_type}"
        )
        tone = (
            "error"
            if activity.stage is ExecutionActivityStage.FAILED
            else "warning"
            if activity.stage in warning
            else "success"
            if activity.stage in success
            else "default"
        )
        return PmCockpitActivity(
            project_id=project_id,
            mission_id=mission.mission_id,
            work_id=work_id,
            run_id=activity.run_id,
            operation_id=activity.operation_id,
            stage=activity.stage,
            title=titles[activity.stage],
            description=description,
            occurred_at=activity.occurred_at.isoformat(),
            tone=tone,
            failure_code=failure_code,
        )

    def _evidence_currency(
        self, mission: Mission | None
    ) -> tuple[PmCockpitEvidenceCurrency, str]:
        """Judge evidence currency only at the acceptance gate, by the facade's own checks."""
        not_applicable = PmCockpitEvidenceCurrency.NOT_APPLICABLE
        if mission is None:
            return not_applicable, "暂无进行中的需求。"
        if mission.state is MissionState.ACCEPTED:
            return not_applicable, "验收已记录，验证证据已封存。"
        if mission.state in _TERMINAL_MISSION_STATES:
            return not_applicable, "该需求已结束，证据仅供追溯。"
        if mission.state is not MissionState.ACCEPTANCE_PENDING:
            return not_applicable, "尚未进入验收阶段，暂无需核验。"
        try:
            reason = self._real_facade().acceptance_gate_reason(
                mission.mission_id
            )
        except PmFacadeError as error:
            return PmCockpitEvidenceCurrency.NOT_CURRENT, _clip(str(error))
        except (ContinuityStoreError, sqlite3.Error, OSError, ValueError):
            return PmCockpitEvidenceCurrency.NOT_CURRENT, _UNVERIFIABLE_REASON
        if reason:
            return PmCockpitEvidenceCurrency.NOT_CURRENT, _clip(reason)
        return PmCockpitEvidenceCurrency.CURRENT, ""

    def _resume(
        self,
        mission: Mission | None,
        work: WorkItem | None,
        run: RunItem | None,
        facts: _ProjectFacts,
        currency: PmCockpitEvidenceCurrency,
        currency_reason: str,
    ) -> PmCockpitResume:
        """Return the single legal next step; never a way to start or restart anything."""
        state = PmCockpitResumeState
        action = CockpitUserAction

        def resume(
            value: PmCockpitResumeState, user_action: CockpitUserAction, reason: str
        ) -> PmCockpitResume:
            return PmCockpitResume(state=value, user_action=user_action, reason=_clip(reason))

        if mission is not None and mission.state is MissionState.ACCEPTED:
            return resume(
                state.WAITING_FOR_USER,
                action.RETRY_SYNC,
                "验收已记录，变更单与台账尚未同步完成；可重试同步，完成前不会显示为已完成。",
            )
        if mission is None or mission.state in _TERMINAL_MISSION_STATES:
            return resume(state.NO_ACTIVE_WORK, action.NONE, "暂无进行中的需求。")
        if self._is_blocked(mission, work, facts.runs_by_work):
            return resume(
                state.NEEDS_REVIEW,
                action.REVIEW_ESCALATION,
                "存在需要您决策的阻塞事项；不会自动重复启动。",
            )
        if mission.state is MissionState.AWAITING_APPROVAL:
            return resume(
                state.WAITING_FOR_USER,
                action.CONFIRM_START,
                "等待您确认开工；确认前不会创建或启动任何执行。",
            )
        if self._is_start_ready(mission):
            return resume(state.WAITING_FOR_USER, action.CONFIRM_START, _START_READY_REASON)
        if mission.state is MissionState.DRAFT:
            return resume(state.NO_ACTIVE_WORK, action.NONE, "需求仍在准备阶段，尚无可执行内容。")
        if mission.state is MissionState.ACCEPTANCE_PENDING:
            if currency is PmCockpitEvidenceCurrency.CURRENT:
                return resume(
                    state.WAITING_FOR_USER,
                    action.CONFIRM_ACCEPTANCE,
                    "验证证据与当前内容一致，可确认最终验收。",
                )
            return resume(
                state.NEEDS_REVIEW,
                action.REVIEW_ESCALATION,
                f"验收证据不能确认：{currency_reason}",
            )
        if mission.state is MissionState.ACTIVE:
            return self._resume_active(run, facts)
        return resume(
            state.NEEDS_REVIEW,
            action.REVIEW_ESCALATION,
            "当前状态无法确认，已保留现场；请向 PM 说明。",
        )

    @staticmethod
    def _resume_active(run: RunItem | None, facts: _ProjectFacts) -> PmCockpitResume:
        monitoring = (PmCockpitResumeState.MONITORING, CockpitUserAction.NONE)
        review = (PmCockpitResumeState.NEEDS_REVIEW, CockpitUserAction.REVIEW_ESCALATION)
        if run is None or run.state is RunState.SUCCEEDED:
            state, action = monitoring
            reason = "已授权，等待执行或验证流转，无需操作。"
        elif run.state is RunState.READY:
            state, action = monitoring
            reason = "执行正在启动，无需操作。"
        elif run.state is RunState.PENDING:
            state, action = review
            reason = "执行结果仍待核验；为避免重复执行，不会自动重试。"
        elif run.state in {RunState.FAILED, RunState.CANCELLED}:
            state, action = review
            reason = "最近一次执行未完成；需要您决定是否重新授权，不会自动重试。"
        elif run.run_id in facts.started_run_ids:
            state, action = monitoring
            reason = "执行已启动，驾驶舱正在处理，无需操作。"
        else:
            state, action = review
            reason = "已有执行记录，但无法证明进程已启动；为避免重复执行，不会自动重启。"
        return PmCockpitResume(state=state, user_action=action, reason=_clip(reason))

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
        """The card in hand first, then one waiting for the user, then a parked one (TD-071), then the latest closed."""

        for wanted in (
            {MissionState.ACTIVE},
            {
                MissionState.ACCEPTANCE_PENDING,
                MissionState.BLOCKED,
                MissionState.AWAITING_APPROVAL,
                MissionState.DRAFT,
            },
            {MissionState.PARKED},
        ):
            found = next((mission for mission in missions if mission.state in wanted), None)
            if found is not None:
                return found
        return missions[0] if missions else None

    @staticmethod
    def _primary_work(mission: Mission | None, works: tuple[WorkItem, ...]) -> WorkItem | None:
        if mission and mission.root_work_id:
            for work in works:
                if work.work_id == mission.root_work_id:
                    return work
        return next(
            (
                work
                for work in works
                if work.state
                not in {WorkState.ACCEPTED, WorkState.CLOSED, WorkState.CANCELLED}
            ),
            None,
        )

    @staticmethod
    def _is_blocked(
        mission: Mission | None,
        work: WorkItem | None,
        runs_by_work: dict[str, tuple[RunItem, ...]],
    ) -> bool:
        return bool(
            mission and mission.state is MissionState.BLOCKED
        ) or bool(work and work.state is WorkState.BLOCKED) or bool(
            work
            and any(
                run.state.value == "BLOCKED"
                for run in runs_by_work.get(work.work_id, ())
            )
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
            MissionState.PARKED: "搁着（断点已记）",
            MissionState.ACCEPTANCE_PENDING: "等待验收确认",
            MissionState.ACCEPTED: "验收已记录，待同步",
            MissionState.CLOSED: "已关闭",
            MissionState.CANCELLED: "已取消",
        }
        return labels[mission.state]

    @staticmethod
    def _progress(
        mission: Mission | None,
        work: WorkItem | None,
        runs_by_work: dict[str, tuple[RunItem, ...]],
        started_run_ids: frozenset[str],
    ) -> str:
        if mission is None:
            return "未启动"
        if (
            mission.state is MissionState.ACTIVE
            and work
            and work.state is WorkState.IN_PROGRESS
            and any(
                run.run_id in started_run_ids
                for run in runs_by_work.get(work.work_id, ())
            )
        ):
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
        if work and any(
            run.state.value == "VERIFYING"
            for run in runs_by_work.get(work.work_id, ())
        ):
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
        if mission.state is MissionState.ACCEPTED:
            return "中：验收已记录，变更单与台账尚未同步"
        return "低：在既定授权范围内"

    @staticmethod
    def _is_start_ready(mission: Mission) -> bool:
        """A DRAFT Mission created by an approved planning card may be started by the user."""

        routing = mission.authority.routing
        return (
            mission.state is MissionState.DRAFT
            and routing.required_worktree_mode is WorktreeMode.ISOLATED
            and bool(routing.approved_model)
            and bool(routing.allowed_execution_adapters)
        )

    @staticmethod
    def _next_action(mission: Mission | None, blocked: bool) -> tuple[CockpitUserAction, str]:
        if blocked:
            return CockpitUserAction.REVIEW_ESCALATION, "查看需要您决策的事项"
        if mission is None:
            return CockpitUserAction.NONE, "向 PM 描述您的需求"
        if mission.state is MissionState.AWAITING_APPROVAL or PmCockpitService._is_start_ready(mission):
            return CockpitUserAction.CONFIRM_START, "确认开始执行"
        if mission.state is MissionState.ACCEPTANCE_PENDING:
            return CockpitUserAction.CONFIRM_ACCEPTANCE, "确认最终验收"
        if mission.state is MissionState.ACTIVE:
            return CockpitUserAction.NONE, "无需操作，驾驶舱正在处理"
        if mission.state is MissionState.ACCEPTED:
            return CockpitUserAction.RETRY_SYNC, "重试台账同步"
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
        return path.relative_to(self._control_root).as_posix()

    def _require_workspace_path(self, path: Path) -> None:
        try:
            path.relative_to(self._control_root)
        except ValueError as error:
            raise PmCockpitError("驾驶舱拒绝读取工作空间外的路径。") from error
