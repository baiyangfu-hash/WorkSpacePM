"""D-109 layer 2: formally close an old leftover Work (and the Mission it roots) so ``orient`` stops warning about it.

Layer 1 (``stale_residue``) only *lists* a leftover.  This is the way out the listing points to: cancel the Mission rooted
at the leftover Work, then the Work itself, both through their ordinary services (same legal transitions, same ledger rows,
idempotent keys).  Nothing is deleted; the Run history stays.  A dry run (the default) reads and prints only.  ``apply``
re-checks every item against the ledger *at that moment* (a Work that got a live Run or a fresh lease since the scan is
left alone) and writes a JSON trace under ``.auto-pm/reports/retire/``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.application.core.approval_proof_service import ApprovalProofError, ApprovalProofService
from auto_pm.application.core.continuity_resume_service import ContinuityResumeService
from auto_pm.application.core.mission_service import MissionService, MissionServiceError
from auto_pm.application.core.work_registry_service import WorkRegistryError, WorkRegistryService
from auto_pm.contracts.continuity import WorkState
from auto_pm.contracts.continuity_resume import ResumeResidue
from auto_pm.contracts.mission import Mission, MissionState
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError

REPORT_RELATIVE_DIR = Path(".auto-pm") / "reports" / "retire"
# A Mission in one of these states can be cancelled by the Mission state machine (ACCEPTANCE_PENDING cannot: it is waiting
# for the user's verdict, and retiring it behind that verdict would be exactly the wrong shortcut).
_CANCELLABLE_MISSION_STATES = frozenset(
    {
        MissionState.DRAFT,
        MissionState.AWAITING_APPROVAL,
        MissionState.ACTIVE,
        MissionState.BLOCKED,
        MissionState.PARKED,
    }
)


class RetireError(Exception):
    """The retire request cannot be carried out (bad input or approval); nothing was written."""


@dataclass(frozen=True)
class RetireItem:
    """One leftover Work and what retiring it would touch."""

    residue: ResumeResidue
    title: str
    mission_id: str = ""
    mission_state: str = ""
    # "" when the item can be retired, otherwise why it is left alone
    blocked_reason: str = ""

    @property
    def work_id(self) -> str:
        return self.residue.work_id


@dataclass(frozen=True)
class RetireResult:
    work_id: str
    outcome: str  # "retired" | "skipped"
    detail: str = ""
    mission_id: str = ""


@dataclass
class RetirePlan:
    project_id: str
    items: list[RetireItem] = field(default_factory=list)
    unknown_work_ids: list[str] = field(default_factory=list)


class RetireService:
    def __init__(self, workspace_root: str | Path, now: Callable[[], datetime] | None = None) -> None:
        self._root = Path(workspace_root).resolve()
        self._now = now or (lambda: datetime.now(UTC))

    # ------------------------------------------------------------------ read-only
    def plan(self, project_id: str, work_ids: Sequence[str] = ()) -> RetirePlan:
        """Every leftover of the project (or only ``work_ids``); a requested id that is not a leftover is listed apart."""

        found = ContinuityResumeService(self._root, now=self._now).collect(project_id=project_id).residue
        wanted = {item.strip() for item in work_ids if item.strip()}
        plan = RetirePlan(project_id=project_id)
        by_id = {item.work_id: item for item in found}
        plan.unknown_work_ids = sorted(wanted - set(by_id))
        store = ContinuityStore(self._root)
        for work_id in sorted(by_id):
            if wanted and work_id not in wanted:
                continue
            residue = by_id[work_id]
            title = store.get_work(work_id).title
            mission = self._mission_of(store, project_id, work_id)
            blocked = ""
            if mission is not None and mission.state not in _CANCELLABLE_MISSION_STATES:
                blocked = f"Mission {mission.mission_id} 处于 {mission.state.value}，要由用户的验收流程处理，不在这里收口"
            plan.items.append(
                RetireItem(
                    residue=residue,
                    title=title,
                    mission_id=mission.mission_id if mission is not None else "",
                    mission_state=mission.state.value if mission is not None else "",
                    blocked_reason=blocked,
                )
            )
        return plan

    @staticmethod
    def _mission_of(store: ContinuityStore, project_id: str, work_id: str) -> Mission | None:
        for mission in store.list_missions(project_id):
            if mission.root_work_id == work_id:
                return mission
        return None

    # ------------------------------------------------------------------ write
    def apply(
        self,
        project_id: str,
        work_ids: Sequence[str],
        *,
        approval_pin: str = "",
        approval_evidence_ref: str = "",
        tool_version: str = "",
    ) -> tuple[list[RetireResult], Path | None]:
        """Retire the leftovers; returns each outcome and the trace file (None when there was nothing to do)."""

        try:
            _approver, evidence = ApprovalProofService(self._root).resolve(
                pin=approval_pin,
                approver="",
                evidence_ref=approval_evidence_ref,
                purpose="retire",
                subject=project_id,
            )
        except ApprovalProofError as error:
            raise RetireError(str(error)) from error
        plan = self.plan(project_id, work_ids)  # fresh read: what is a leftover *now*
        results = [
            RetireResult(work_id=work_id, outcome="skipped", detail="不是陈年残留（已有进展、已收口或不存在），没有动它")
            for work_id in plan.unknown_work_ids
        ]
        missions = MissionService(self._root, now=self._now)
        works = WorkRegistryService(self._root, now=lambda: self._now().isoformat())
        if tool_version:
            works.initialize(tool_version)
            missions.initialize(tool_version)
        for item in plan.items:
            if item.blocked_reason:
                results.append(RetireResult(item.work_id, "skipped", item.blocked_reason, item.mission_id))
                continue
            results.append(self._retire_one(item, missions, works))
        trace = self._write_trace(project_id, evidence, results) if results else None
        return results, trace

    def _retire_one(self, item: RetireItem, missions: MissionService, works: WorkRegistryService) -> RetireResult:
        key_tail = f"{item.work_id}-{item.residue.last_run_id}"
        try:
            if item.mission_id:
                mission = ContinuityStore(self._root).get_mission(item.mission_id)
                missions.transition(
                    mission_id=mission.mission_id,
                    expected_version=mission.version,
                    new_state=MissionState.CANCELLED,
                    root_work_id=None,  # CANCELLED takes no root Work (it is already bound)
                    idempotency_key=f"retire-mission-{key_tail}",
                )
            works.transition(item.work_id, WorkState.CANCELLED, f"retire-work-{key_tail}")
        except (MissionServiceError, WorkRegistryError, ContinuityStoreError) as error:
            return RetireResult(item.work_id, "skipped", f"没有收口：{error}", item.mission_id)
        return RetireResult(item.work_id, "retired", "已取消", item.mission_id)

    def _write_trace(self, project_id: str, evidence: str, results: list[RetireResult]) -> Path:
        stamp = self._now().astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = self._root / REPORT_RELATIVE_DIR / f"retire-{project_id}-{stamp}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "pm-retire-trace.v1",
            "project_id": project_id,
            "at": self._now().astimezone(UTC).isoformat(),
            "approval_evidence_ref": evidence,
            "results": [
                {"work_id": r.work_id, "mission_id": r.mission_id, "outcome": r.outcome, "detail": r.detail}
                for r in results
            ],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        return path
