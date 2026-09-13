"""Compile Resume v2 from Workspace Context and the Continuity Store."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.contracts.continuity import LeaseItem, RunState, WorkItem, WorkState
from auto_pm.contracts.continuity_resume import (
    ContinuityResume,
    LeaseView,
    ResumeRunCandidate,
)
from auto_pm.contracts.mission import Mission, MissionState
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError

from .workspace_context_service import WorkspaceContextError, WorkspaceContextService


class ContinuityResumeError(RuntimeError):
    """Raised when Resume cannot establish a single trustworthy chain."""


_SELECTABLE_WORK_STATES = frozenset(
    {
        WorkState.READY,
        WorkState.IN_PROGRESS,
        WorkState.BLOCKED,
        WorkState.VERIFYING,
    }
)


class ContinuityResumeService:
    """Read bounded identity and transactional execution state without inference."""

    def __init__(
        self,
        workspace_root: str | Path,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._root = Path(workspace_root).resolve()
        self._contexts = WorkspaceContextService(str(self._root))
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
        mission: Mission | None = None
        work = None
        run = None
        checkpoint = None
        lease_view: LeaseView | None = None
        work_candidates: tuple[WorkItem, ...] = ()
        run_candidates: tuple[ResumeRunCandidate, ...] = ()
        db_exists = self._store.db_path.is_file()
        if db_exists:
            try:
                missions = self._store.list_active_missions(context.subject_project_id)
                if len(missions) == 1:
                    mission = missions[0]
                elif len(missions) > 1:
                    conflicts.append("MULTIPLE_ACTIVE_MISSIONS")

                works = tuple(
                    sorted(
                        (
                            candidate
                            for candidate in self._store.list_works(
                                context.subject_project_id
                            )
                            if candidate.state in _SELECTABLE_WORK_STATES
                        ),
                        key=lambda candidate: candidate.work_id,
                    )
                )
                work_candidates = works
                if mission and mission.root_work_id:
                    if work_id and work_id != mission.root_work_id:
                        raise ContinuityResumeError("指定 Work 与活动 Mission 的 root Work 不一致")
                    work = self._store.get_work(mission.root_work_id)
                elif work_id:
                    work = self._store.get_work(work_id)
                    if work.subject_project_id != context.subject_project_id:
                        raise ContinuityResumeError("Work 不属于当前 subject project")
                elif len(works) == 1:
                    work = works[0]
                elif len(works) > 1:
                    conflicts.append("MULTIPLE_ACTIVE_WORKS")

                if run_id and work is None:
                    raise ContinuityResumeError("指定 run_id 时必须能确定 Work")
                if work is not None:
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
                    else:
                        if len(runs) == 1:
                            run = runs[0]
                        elif len(runs) > 1:
                            conflicts.append("MULTIPLE_ACTIVE_RUNS")
                if run is not None:
                    checkpoint = self._store.latest_checkpoint(run.run_id)
                    candidate_leases = {
                        candidate.run.run_id: candidate.lease for candidate in run_candidates
                    }
                    lease_view = candidate_leases.get(run.run_id)
                    if lease_view is None:
                        lease_view = self._lease_view(self._store.get_lease(run.run_id))
                    if (
                        run.run_id in candidate_leases
                        and datetime.fromisoformat(lease_view.expires_at)
                        <= self._now().astimezone(UTC)
                    ):
                        conflicts.append("LEASE_EXPIRED")
            except (ContinuityStoreError, sqlite3.Error) as error:
                raise ContinuityResumeError(f"Continuity Store 无法读取: {error}") from error

        next_action = self._next_action(
            mission.state if mission else None,
            work.state if work else None,
            run.state if run else None,
            checkpoint is not None,
        )
        if conflicts:
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
        digest = hashlib.sha256(
            json.dumps(seed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return ContinuityResume(
            context=context,
            mission=mission,
            work=work,
            work_candidates=work_candidates,
            run=run,
            run_candidates=run_candidates,
            checkpoint=checkpoint,
            lease=lease_view,
            conflicts=tuple(conflicts),
            next_legal_action=next_action,
            read_set=read_set,
            evidence_id=f"RESUME-{digest[:16].upper()}",
        )

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
        if mission_state is not None:
            mission_actions = {
                MissionState.DRAFT: "SUBMIT_MISSION_FOR_APPROVAL",
                MissionState.AWAITING_APPROVAL: "AWAIT_USER_APPROVAL",
                MissionState.BLOCKED: "RESOLVE_MISSION_BLOCKER",
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
