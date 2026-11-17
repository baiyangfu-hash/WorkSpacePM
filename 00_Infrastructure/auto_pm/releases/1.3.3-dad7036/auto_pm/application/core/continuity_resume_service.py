"""Compile Resume v2 from Workspace Context and the Continuity Store."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.contracts.continuity import (
    EXECUTION_ACTIVE_WORK_STATES,
    POST_ACCEPTANCE_WORK_STATES,
    TERMINAL_WORK_STATES,
    LeaseItem,
    RunState,
    WorkItem,
    WorkState,
)
from auto_pm.contracts.continuity_resume import (
    ContinuityResume,
    LeaseView,
    ResumeResidue,
    ResumeRunCandidate,
)
from auto_pm.contracts.intake import IntakeNoteSummary, IntakeSummary
from auto_pm.contracts.interlock_matrix import exit_hint
from auto_pm.contracts.mission import Mission, MissionState
from auto_pm.infrastructure.continuity_store import (
    LEASE_RENEWAL_RED_COUNT,
    ContinuityStore,
    ContinuityStoreError,
)
from auto_pm.infrastructure.intake_store import IntakeStore

from .stale_residue import classify_residue
from .workspace_context_service import WorkspaceContextError, WorkspaceContextService


class ContinuityResumeError(RuntimeError):
    """Raised when Resume cannot establish a single trustworthy chain."""


class ContinuityResumeService:
    """Read bounded identity and transactional execution state without inference."""

    def __init__(
        self,
        workspace_root: str | Path,
        now: Callable[[], datetime] | None = None,
        *,
        execution_root: str | Path | None = None,
    ) -> None:
        self._root = Path(workspace_root).resolve()
        self._contexts = WorkspaceContextService(
            str(self._root), execution_root=execution_root
        )
        self._store = ContinuityStore(self._root)
        self._now = now or (lambda: datetime.now(UTC))

    def collect(
        self,
        *,
        project_id: str = "",
        invocation_path: str | Path | None = None,
        work_id: str = "",
        run_id: str = "",
    ) -> ContinuityResume:
        try:
            context = self._contexts.resolve(
                project_id=project_id, start_path=invocation_path or self._root
            )
        except WorkspaceContextError as error:
            raise ContinuityResumeError(str(error)) from error

        conflicts = list(context.conflicts)
        hold_warnings: list[str] = []
        residue: list[ResumeResidue] = []
        orphan_run_ids: tuple[str, ...] = ()
        mission: Mission | None = None
        work = None
        run = None
        checkpoint = None
        lease_view: LeaseView | None = None
        work_candidates: tuple[WorkItem, ...] = ()
        run_candidates: tuple[ResumeRunCandidate, ...] = ()
        mission_candidates: tuple[Mission, ...] = ()
        db_exists = self._store.db_path.is_file()
        if db_exists:
            try:
                missions = self._store.list_active_missions(context.subject_project_id)
                hold_warnings.extend(self._orphan_card_warnings(missions, context.subject_project_id))
                mission, mission_candidates = self._select_mission(missions, work_id)
                if mission is None and any(
                    candidate.state is MissionState.ACTIVE for candidate in mission_candidates
                ):
                    # Two ACTIVE Missions cannot exist in a v8 store: the data is damaged, never guess.
                    conflicts.append("MULTIPLE_ACTIVE_MISSIONS")

                works = tuple(
                    sorted(
                        self._store.list_works(context.subject_project_id),
                        key=lambda candidate: candidate.work_id,
                    )
                )
                if any(candidate.state not in EXECUTION_ACTIVE_WORK_STATES for candidate in works):
                    raise ContinuityResumeError("Store 返回了非执行活动态 Work")
                work_candidates = works
                residue = self._stale_residue(works)
                residue_ids = {item.work_id for item in residue}
                # A leftover is listed as a warning, not counted: otherwise one old card makes "several active Works".
                live_works = tuple(item for item in works if item.work_id not in residue_ids)
                if mission is not None and mission.root_work_id:
                    if work_id and work_id != mission.root_work_id:
                        raise ContinuityResumeError("指定 Work 与活动 Mission 的 root Work 不一致")
                    work = self._store.get_work(mission.root_work_id)
                    if work.subject_project_id != context.subject_project_id:
                        raise ContinuityResumeError("Mission root Work 不属于当前 subject project")
                    if work.state not in EXECUTION_ACTIVE_WORK_STATES and works:
                        conflicts.append("MISSION_ROOT_NOT_EXECUTION_ACTIVE")
                elif mission_candidates and not work_id:
                    # Several open cards and none in hand: only the user picks the next one.
                    pass
                elif work_id:
                    work = self._store.get_work(work_id)
                    if work.subject_project_id != context.subject_project_id:
                        raise ContinuityResumeError("Work 不属于当前 subject project")
                elif len(live_works) == 1:
                    work = live_works[0]
                elif len(live_works) > 1:
                    conflicts.append("MULTIPLE_ACTIVE_WORKS")

                if run_id and work is None:
                    raise ContinuityResumeError("指定 run_id 时必须能确定 Work")
                if work is not None:
                    if work.state in POST_ACCEPTANCE_WORK_STATES | TERMINAL_WORK_STATES:
                        # Historical selection never exposes a live Run or lease.
                        if run_id:
                            historical_run = self._store.get_run(run_id)
                            if historical_run.work_id != work.work_id:
                                raise ContinuityResumeError("Run 不属于选定 Work")
                            if historical_run.state in {
                                RunState.SUCCEEDED,
                                RunState.FAILED,
                                RunState.CANCELLED,
                            }:
                                run = historical_run
                                checkpoint = self._store.latest_checkpoint(run.run_id)
                            else:
                                raise ContinuityResumeError("验收后 Work 不可恢复非终态 Run")
                    elif work.state in EXECUTION_ACTIVE_WORK_STATES:
                        runs = tuple(
                            sorted(
                                self._store.list_runs(work.work_id),
                                key=lambda candidate: candidate.run_id,
                            )
                        )
                        run_candidates = tuple(
                            ResumeRunCandidate(
                                run=candidate,
                                lease=self._lease_view(self._store.get_lease(candidate.run_id)),
                            )
                            for candidate in runs
                        )
                        if run_id:
                            run = self._store.get_run(run_id)
                            if run.work_id != work.work_id:
                                raise ContinuityResumeError("Run 不属于选定 Work")
                        elif len(runs) == 1:
                            run = runs[0]
                        elif len(runs) > 1:
                            conflicts.append("MULTIPLE_ACTIVE_RUNS")
                    else:
                        raise ContinuityResumeError("未知 Work 生命周期状态")
                if run is not None and work is not None and work.state in EXECUTION_ACTIVE_WORK_STATES:
                    checkpoint = self._store.latest_checkpoint(run.run_id)
                    candidate_leases = {
                        candidate.run.run_id: candidate.lease for candidate in run_candidates
                    }
                    lease_view = candidate_leases.get(run.run_id)
                    if lease_view is None:
                        lease_view = self._lease_view(self._store.get_lease(run.run_id))
                    if (
                        run.run_id in candidate_leases
                        and not (mission is not None and mission.state is MissionState.PARKED)
                        and datetime.fromisoformat(lease_view.expires_at)
                        <= self._now().astimezone(UTC)
                    ):
                        conflicts.append("LEASE_EXPIRED")
                    hold = self._store.lease_hold_status(run.run_id)
                    renewals = int(str(hold["renewals"]))
                    if renewals >= LEASE_RENEWAL_RED_COUNT:
                        hold_warnings.append(
                            f"续租 {renewals} 次（≥{LEASE_RENEWAL_RED_COUNT}）：这个 Run 卡住了或开得太久，"
                            f"持有上限 {hold['hold_end']}；请先查原因，别无限续"
                        )
                # Interlock matrix state LIVE_RUN_UNDER_FINISHED_WORK: the walk above never reaches a live Run whose Work is
                # already accepted, closed or cancelled, so look at the whole ledger once, not through the Mission tree.
                orphans = self._store.list_live_runs_under_finished_work(context.subject_project_id)
                if orphans:
                    conflicts.append("LIVE_RUN_UNDER_FINISHED_WORK")
                    orphan_run_ids = tuple(item.run_id for item in orphans)
            except (ContinuityStoreError, sqlite3.Error) as error:
                raise ContinuityResumeError(f"Continuity Store 无法读取: {error}") from error

        intake = IntakeSummary()
        notes = IntakeNoteSummary()
        if db_exists:
            try:
                intake_store = IntakeStore(self._root)
                intake = intake_store.summary(context.subject_project_id)
                # D-357: raw notes waiting for triage.  Read-only like the summary above: no ledger, no table is created.
                notes = intake_store.note_summary(context.subject_project_id)
            except ContinuityStoreError as error:
                raise ContinuityResumeError(f"收件箱无法读取: {error}") from error

        next_action = self._next_action(
            mission.state if mission else None,
            work.state if work else None,
            run.state if run else None,
            checkpoint is not None,
        )
        if mission is None and work is None and mission_candidates:
            next_action = "AWAIT_USER_SWITCH"
        if (
            mission is None
            and work is None
            and run is None
            and not work_candidates
            and not mission_candidates
            and not conflicts
        ):
            # TD-SW008-569: a registered project with nothing on the ledger yet starts by recording the user's request
            # (``pm inbox add``).  Only this exact state gets it; every fail-closed state above keeps an empty action, and
            # nothing here opens or creates the store.
            # D-357: raw notes take over this one state only (somebody already said what they want; triage it first).
            # Every other state keeps its own next action; the ``notes`` block is reported in all of them.
            next_action = "USE_INBOX" if notes.is_empty else "TRIAGE_NOTES"
        if conflicts == ["LEASE_EXPIRED"]:
            # 只有租约过期这一个冲突时的出口是回收（continuity run reclaim）：申请人必须换一个名字（原持有者续租被拒、
            # 自己回收自己也被拒），原持有者进程判不出时还须用户本人 pm sign-risk 签字。settle-expired 要另开恢复
            # Work/Run 和运行态 Decision，不是执行端的常规出口。留空会让人卡在续租/回收互相踢皮球里。
            next_action = "RECLAIM_EXPIRED_RUN"
        elif conflicts:
            next_action = ""
        read_set = tuple(item.path for item in context.read_set) + (
            (str(self._store.db_path),) if db_exists else ()
        )
        seed = {
            "context": context.evidence_id,
            "mission": mission.model_dump(mode="json") if mission else None,
            "work": work.model_dump(mode="json") if work else None,
            "work_candidates": [
                candidate.model_dump(mode="json") for candidate in work_candidates
            ],
            "run": run.model_dump(mode="json") if run else None,
            "run_candidates": [
                candidate.model_dump(mode="json") for candidate in run_candidates
            ],
            "checkpoint": checkpoint.model_dump(mode="json") if checkpoint else None,
            "lease": lease_view.model_dump(mode="json") if lease_view else None,
            "conflicts": conflicts,
        }
        if not intake.is_empty:
            seed["intake"] = intake.model_dump(mode="json")
        if not notes.is_empty:  # a project without raw notes keeps the evidence_id it had before D-357
            seed["notes"] = notes.model_dump(mode="json")
        if residue:
            seed["residue"] = [item.model_dump(mode="json") for item in residue]
        if mission_candidates:
            seed["mission_candidates"] = [
                candidate.model_dump(mode="json") for candidate in mission_candidates
            ]
        digest = hashlib.sha256(
            json.dumps(seed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return ContinuityResume(
            context=context,
            mission=mission,
            work=work,
            work_candidates=work_candidates,
            mission_candidates=mission_candidates,
            run=run,
            run_candidates=run_candidates,
            checkpoint=checkpoint,
            lease=lease_view,
            conflicts=tuple(conflicts),
            hold_warnings=tuple(hold_warnings),
            residue=tuple(residue),
            exit_hints=tuple(
                exit_hint(code, detail=", ".join(orphan_run_ids) if code == "LIVE_RUN_UNDER_FINISHED_WORK" else "")
                for code in conflicts
            ),
            next_legal_action=next_action,
            read_set=read_set,
            intake=intake,
            notes=notes,
            evidence_id=f"RESUME-{digest[:16].upper()}",
        )

    def _orphan_card_warnings(
        self, missions: tuple[Mission, ...], project_id: str
    ) -> list[str]:
        """D-348: an open card whose root Work already ended is said out loud; nothing else changes.

        Only the warning list grows: conflicts, the next legal action and the evidence id stay as they were.  A root
        Work that cannot be read is reported, never raised: before this the Work of a card that is not in hand was not
        read at all, and looking at it must not turn a working ``pm orient`` into an error.
        """

        warnings: list[str] = []
        for card in missions:
            if not card.root_work_id:
                continue
            try:
                root_work = self._store.get_work(card.root_work_id)
            except (ContinuityStoreError, ValueError):  # 缺行、坏行都算读不出
                warnings.append(
                    f"读不出卡 {card.mission_id} 的工作项 {card.root_work_id}，没法判断它是不是孤卡"
                )
                continue
            if root_work.state not in TERMINAL_WORK_STATES:
                continue
            head = f"孤卡：{card.mission_id} 还开着（{card.state.value}），但它的工作项 {root_work.work_id} "
            if root_work.state is WorkState.CANCELLED:
                warnings.append(
                    f"{head}已取消；请用户本人用 pm retire --pid {project_id} --mission-id {card.mission_id} "
                    "收掉（不加 --apply 只列出，什么都不写）"
                )
            else:
                warnings.append(
                    f"{head}已经结束（{root_work.state.value}）；请交主执行查，不要自己改状态"
                )
        return warnings

    def _stale_residue(self, works: tuple[WorkItem, ...]) -> list[ResumeResidue]:
        now = self._now().astimezone(UTC)
        found: list[ResumeResidue] = []
        for candidate in works:
            runs = self._store.list_runs(candidate.work_id, include_terminal=True)
            expiries: dict[str, datetime | None] = {}
            for run in runs:
                try:
                    expiries[run.run_id] = datetime.fromisoformat(
                        self._store.get_lease(run.run_id).expires_at
                    )
                except ContinuityStoreError:  # no lease row for this Run
                    expiries[run.run_id] = None
                except ValueError:  # lease time is not a time: cannot prove it expired, so it counts as "not expired"
                    expiries[run.run_id] = datetime.max.replace(tzinfo=UTC)
            item = classify_residue(candidate, runs, expiries, now)
            if item is not None:
                found.append(item)
        return found

    @staticmethod
    def _select_mission(
        missions: tuple[Mission, ...], work_id: str
    ) -> tuple[Mission | None, tuple[Mission, ...]]:
        """Pick the card to resume (TD-071): the one asked for by its root Work, else the ACTIVE one,
        else the only open one.  Every other open card is returned as a candidate, never guessed."""

        if len(missions) <= 1:
            return (missions[0] if missions else None), ()
        if work_id:
            by_work = [candidate for candidate in missions if candidate.root_work_id == work_id]
            if len(by_work) == 1:
                chosen = by_work[0]
                return chosen, tuple(m for m in missions if m.mission_id != chosen.mission_id)
        active = [candidate for candidate in missions if candidate.state is MissionState.ACTIVE]
        if len(active) == 1:
            chosen = active[0]
            return chosen, tuple(m for m in missions if m.mission_id != chosen.mission_id)
        return None, tuple(sorted(missions, key=lambda candidate: candidate.mission_id))

    @staticmethod
    def _lease_view(lease: LeaseItem) -> LeaseView:
        return LeaseView(
            run_id=lease.run_id,
            owner_id=lease.owner_id,
            expires_at=lease.expires_at,
            version=lease.version,
            updated_at=lease.updated_at,
        )

    @staticmethod
    def _next_action(
        mission_state: MissionState | None,
        work_state: WorkState | None,
        run_state: RunState | None,
        has_checkpoint: bool,
    ) -> str:
        if work_state in TERMINAL_WORK_STATES:
            return ""
        if work_state in POST_ACCEPTANCE_WORK_STATES:
            return "ADMIN_REVIEW_OR_CLOSE"
        if mission_state is not None:
            mission_actions = {
                MissionState.DRAFT: "SUBMIT_MISSION_FOR_APPROVAL",
                MissionState.AWAITING_APPROVAL: "AWAIT_USER_APPROVAL",
                MissionState.BLOCKED: "RESOLVE_MISSION_BLOCKER",
                # TD-071: only the user decides which parked card is picked back up.
                MissionState.PARKED: "AWAIT_USER_UNPARK",
                MissionState.ACCEPTANCE_PENDING: "AWAIT_USER_ACCEPTANCE",
            }
            if mission_state in mission_actions:
                return mission_actions[mission_state]
        if work_state is None:
            return ""
        if run_state is None:
            return "CREATE_RUN" if work_state in {WorkState.READY, WorkState.IN_PROGRESS} else ""
        mapping = {
            RunState.RUNNING: "CONTINUE_FROM_CHECKPOINT" if has_checkpoint else "CONTINUE_RUN",
            RunState.BLOCKED: "RESOLVE_BLOCKER",
            RunState.VERIFYING: "VERIFY_RUN",
            RunState.READY: "START_RUN",
        }
        return mapping.get(run_state, "")
