"""Compile Resume v2 from Workspace Context and the Continuity Store."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.contracts.continuity import LeaseItem, RunState, WorkState
from auto_pm.contracts.continuity_resume import ContinuityResume, LeaseView
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError

from .workspace_context_service import WorkspaceContextError, WorkspaceContextService


class ContinuityResumeError(RuntimeError):
    """Raised when Resume cannot establish a single trustworthy chain."""


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
        work = None
        run = None
        checkpoint = None
        lease: LeaseItem | None = None
        lease_view: LeaseView | None = None
        db_exists = self._store.db_path.is_file()
        if db_exists:
            try:
                works = self._store.list_works(context.subject_project_id)
                if work_id:
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
                    runs = self._store.list_runs(work.work_id)
                    if run_id:
                        run = self._store.get_run(run_id)
                        if run.work_id != work.work_id:
                            raise ContinuityResumeError("Run 不属于选定 Work")
                    elif len(runs) == 1:
                        run = runs[0]
                    elif len(runs) > 1:
                        conflicts.append("MULTIPLE_ACTIVE_RUNS")
                if run is not None:
                    checkpoint = self._store.latest_checkpoint(run.run_id)
                    lease = self._store.get_lease(run.run_id)
                    lease_view = LeaseView(
                        run_id=lease.run_id,
                        owner_id=lease.owner_id,
                        expires_at=lease.expires_at,
                        version=lease.version,
                        updated_at=lease.updated_at,
                    )
                    if datetime.fromisoformat(lease.expires_at) <= self._now().astimezone(UTC):
                        conflicts.append("LEASE_EXPIRED")
            except (ContinuityStoreError, sqlite3.Error) as error:
                raise ContinuityResumeError(f"Continuity Store 无法读取: {error}") from error

        next_action = self._next_action(
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
            "work": work.model_dump(mode="json") if work else None,
            "run": run.model_dump(mode="json") if run else None,
            "checkpoint": checkpoint.model_dump(mode="json") if checkpoint else None,
            "lease": lease_view.model_dump(mode="json") if lease_view else None,
            "conflicts": conflicts,
        }
        digest = hashlib.sha256(
            json.dumps(seed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return ContinuityResume(
            context=context,
            work=work,
            run=run,
            checkpoint=checkpoint,
            lease=lease_view,
            conflicts=tuple(conflicts),
            next_legal_action=next_action,
            read_set=read_set,
            evidence_id=f"RESUME-{digest[:16].upper()}",
        )

    @staticmethod
    def _next_action(
        work_state: WorkState | None,
        run_state: RunState | None,
        has_checkpoint: bool,
    ) -> str:
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
