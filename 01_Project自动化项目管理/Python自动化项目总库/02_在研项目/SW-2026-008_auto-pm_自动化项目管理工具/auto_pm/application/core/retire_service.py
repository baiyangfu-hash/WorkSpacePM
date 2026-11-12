"""D-109 layer 2: formally close an old leftover Work (and the Mission it roots) so ``orient`` stops warning about it.

Layer 1 (``stale_residue``) only *lists* a leftover.  This is the way out the listing points to: cancel the Mission rooted
at the leftover Work, then the Work itself, both through their ordinary services (same legal transitions, same ledger rows,
idempotent keys).  Nothing is deleted; the Run history stays.  A dry run (the default) reads and prints only.  ``apply``
re-checks every item against the ledger *at that moment* (a Work that got a live Run or a fresh lease since the scan is
left alone) and writes a JSON trace under ``.auto-pm/reports/retire/``.

CHG-SCPT-2026-647 adds two kinds of card that had no formal way out (``continuity mission transition`` alone is forbidden):

- D-338 *draft without Work*: a DRAFT or AWAITING_APPROVAL Mission with no root Work.  Only when named (``mission_ids``).
- D-339 *orphan card*: an open Mission whose root Work is already CANCELLED and every Run has ended
  (``stale_residue.is_orphan_mission``).  Listed by the stale scan and when named.

Both are only cancelled (Mission → CANCELLED through ``MissionService``); a Work or Run is never touched for them.
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
from auto_pm.application.core.stale_residue import is_orphan_mission
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


# D-338: a card that never got a Work can only be in one of these (the Mission state machine binds a Work on ACTIVE).
_DRAFT_STATES = frozenset({MissionState.DRAFT, MissionState.AWAITING_APPROVAL})
KIND_LEFTOVER_WORK = "leftover_work"
KIND_DRAFT_WITHOUT_WORK = "draft_without_work"
KIND_ORPHAN_MISSION = "orphan_mission"


class RetireError(Exception):
    """The retire request cannot be carried out (bad input or approval); nothing was written."""


@dataclass(frozen=True)
class RetireItem:
    """One leftover Work and what retiring it would touch."""

    residue: ResumeResidue
    title: str
    # D-135: the ledger allows several open Missions under one Work; every one of them is listed and cancelled
    mission_ids: tuple[str, ...] = ()
    mission_states: tuple[str, ...] = ()
    # "" when the item can be retired, otherwise why it is left alone
    blocked_reason: str = ""

    @property
    def work_id(self) -> str:
        return self.residue.work_id


@dataclass(frozen=True)
class MissionRetireItem:
    """D-338 / D-339: one card retired by itself (no leftover Work under it)."""

    mission_id: str
    title: str
    state: str  # the Mission state when listed
    root_work_id: str  # "" for a draft without Work
    kind: str  # KIND_DRAFT_WITHOUT_WORK | KIND_ORPHAN_MISSION | "" when it cannot be retired
    blocked_reason: str = ""


@dataclass(frozen=True)
class RetireResult:
    work_id: str
    outcome: str  # "retired" | "skipped"
    detail: str = ""
    # planned: every Mission under the Work that this retire meant to cancel
    mission_ids: tuple[str, ...] = ()
    # D-149: the subset confirmed CANCELLED by this apply (a half-done retire lists fewer than planned)
    cancelled_mission_ids: tuple[str, ...] = ()
    # CHG-SCPT-2026-647: what kind of card this was, and the state of each planned Mission before the apply
    kind: str = KIND_LEFTOVER_WORK
    states_before: tuple[str, ...] = ()


@dataclass
class RetirePlan:
    project_id: str
    items: list[RetireItem] = field(default_factory=list)
    unknown_work_ids: list[str] = field(default_factory=list)
    # CHG-SCPT-2026-647: cards retired by themselves, and named cards that do not exist in this project
    missions: list[MissionRetireItem] = field(default_factory=list)
    unknown_mission_ids: list[str] = field(default_factory=list)


class RetireService:
    def __init__(self, workspace_root: str | Path, now: Callable[[], datetime] | None = None) -> None:
        self._root = Path(workspace_root).resolve()
        self._now = now or (lambda: datetime.now(UTC))

    # ------------------------------------------------------------------ read-only
    def plan(self, project_id: str, work_ids: Sequence[str] = (), mission_ids: Sequence[str] = ()) -> RetirePlan:
        """Every leftover and orphan card of the project when nothing is named (``--stale``); otherwise only the named
        ``work_ids`` (leftover Works) or ``mission_ids`` (cards).  A named id that cannot be retired is listed apart."""

        named_missions = list(dict.fromkeys(item.strip() for item in mission_ids if item.strip()))
        wanted = {item.strip() for item in work_ids if item.strip()}
        plan = RetirePlan(project_id=project_id)
        if named_missions:
            self._plan_missions(plan, named_missions)
            if not wanted:
                return plan
        elif not wanted:
            self._plan_orphans(plan)
        found = ContinuityResumeService(self._root, now=self._now).collect(project_id=project_id).residue
        by_id = {item.work_id: item for item in found}
        plan.unknown_work_ids = sorted(wanted - set(by_id))
        store = ContinuityStore(self._root)
        for work_id in sorted(by_id):
            if wanted and work_id not in wanted:
                continue
            residue = by_id[work_id]
            title = store.get_work(work_id).title
            missions = self._missions_of(store, project_id, work_id)
            blocked = ""
            for mission in missions:
                if mission.state not in _CANCELLABLE_MISSION_STATES:
                    blocked = f"Mission {mission.mission_id} 处于 {mission.state.value}，要由用户的验收流程处理，不在这里收口"
                    break
            plan.items.append(
                RetireItem(
                    residue=residue,
                    title=title,
                    mission_ids=tuple(m.mission_id for m in missions),
                    mission_states=tuple(m.state.value for m in missions),
                    blocked_reason=blocked,
                )
            )
        return plan

    @staticmethod
    def _missions_of(store: ContinuityStore, project_id: str, work_id: str) -> list[Mission]:
        return [mission for mission in store.list_missions(project_id) if mission.root_work_id == work_id]

    def _plan_orphans(self, plan: RetirePlan) -> None:
        """D-339: every open card of the project whose Work was cancelled and whose Runs have all ended."""

        store = ContinuityStore(self._root)
        for mission in sorted(store.list_missions(plan.project_id), key=lambda item: item.mission_id):
            if mission.root_work_id and self._is_orphan(store, mission):
                plan.missions.append(self._mission_item(mission, KIND_ORPHAN_MISSION))

    def _plan_missions(self, plan: RetirePlan, mission_ids: Sequence[str]) -> None:
        """D-338 / D-339: judge each named card; a card that cannot be retired says why."""

        store = ContinuityStore(self._root)
        for mission_id in mission_ids:
            try:
                mission = store.get_mission(mission_id)
            except ContinuityStoreError:
                plan.unknown_mission_ids.append(mission_id)
                continue
            if mission.subject_project_id != plan.project_id:
                plan.unknown_mission_ids.append(mission_id)
                continue
            plan.missions.append(self._judge_mission(store, mission))

    def _judge_mission(self, store: ContinuityStore, mission: Mission) -> MissionRetireItem:
        if mission.state not in _CANCELLABLE_MISSION_STATES:
            return self._mission_item(
                mission, "", f"卡处于 {mission.state.value}：已结束或在等你验收，不在这里收"
            )
        if not mission.root_work_id:
            if mission.state in _DRAFT_STATES:
                return self._mission_item(mission, KIND_DRAFT_WITHOUT_WORK)
            return self._mission_item(mission, "", f"卡处于 {mission.state.value} 却没有 Work，账本异常，不在这里收")
        if self._is_orphan(store, mission):
            return self._mission_item(mission, KIND_ORPHAN_MISSION)
        try:
            work_state = store.get_work(mission.root_work_id).state.value
        except ContinuityStoreError:
            work_state = "读不到"
        return self._mission_item(
            mission,
            "",
            f"卡下面的 Work {mission.root_work_id} 是 {work_state}，或者还有没结束的 Run：不是孤卡；"
            "陈年残留用 --work-id 收，正在干的不收",
        )

    @staticmethod
    def _is_orphan(store: ContinuityStore, mission: Mission) -> bool:
        if not mission.root_work_id:
            return False
        try:
            work = store.get_work(mission.root_work_id)
            runs = store.list_runs(work.work_id, include_terminal=True)
        except ContinuityStoreError:
            return False
        return is_orphan_mission(mission, work, runs, _CANCELLABLE_MISSION_STATES)

    @staticmethod
    def _mission_item(mission: Mission, kind: str, blocked_reason: str = "") -> MissionRetireItem:
        return MissionRetireItem(
            mission_id=mission.mission_id,
            title=mission.title,
            state=mission.state.value,
            root_work_id=mission.root_work_id or "",
            kind=kind,
            blocked_reason=blocked_reason,
        )

    # ------------------------------------------------------------------ write
    def apply(
        self,
        project_id: str,
        work_ids: Sequence[str],
        *,
        mission_ids: Sequence[str] = (),
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
        plan = self.plan(project_id, work_ids, mission_ids)  # fresh read: what is a leftover *now*
        results = [
            RetireResult(work_id=work_id, outcome="skipped", detail="不是陈年残留（已有进展、已收口或不存在），没有动它")
            for work_id in plan.unknown_work_ids
        ]
        results += [
            RetireResult("", "skipped", "这个项目里没有这张卡，没有动它", (mission_id,), kind="")
            for mission_id in plan.unknown_mission_ids
        ]
        missions = MissionService(self._root, now=self._now)
        works = WorkRegistryService(self._root, now=lambda: self._now().isoformat())
        if tool_version:
            works.initialize(tool_version)
            missions.initialize(tool_version)
        for item in plan.items:
            if item.blocked_reason:
                results.append(
                    RetireResult(item.work_id, "skipped", item.blocked_reason, item.mission_ids, states_before=item.mission_states)
                )
                continue
            results.append(self._retire_one(item, missions, works))
        for card in plan.missions:
            if card.blocked_reason:
                results.append(
                    RetireResult(card.root_work_id, "skipped", card.blocked_reason, (card.mission_id,),
                                 kind=card.kind, states_before=(card.state,))
                )
                continue
            results.append(self._retire_card(card, missions))
        trace = self._write_trace(project_id, evidence, results) if results else None
        return results, trace

    def _retire_one(self, item: RetireItem, missions: MissionService, works: WorkRegistryService) -> RetireResult:
        key_tail = f"{item.work_id}-{item.residue.last_run_id}"
        cancelled: list[str] = []
        try:
            for mission_id in item.mission_ids:
                mission = ContinuityStore(self._root).get_mission(mission_id)
                missions.transition(
                    mission_id=mission.mission_id,
                    expected_version=mission.version,
                    new_state=MissionState.CANCELLED,
                    root_work_id=None,  # CANCELLED takes no root Work (it is already bound)
                    idempotency_key=f"retire-mission-{mission_id}-{key_tail}",
                )
                cancelled.append(mission_id)
            works.transition(item.work_id, WorkState.CANCELLED, f"retire-work-{key_tail}")
        except (MissionServiceError, WorkRegistryError, ContinuityStoreError) as error:
            return RetireResult(
                item.work_id, "skipped", f"没有收口：{error}", item.mission_ids, tuple(cancelled), states_before=item.mission_states
            )
        return RetireResult(
            item.work_id, "retired", "已取消", item.mission_ids, tuple(cancelled), states_before=item.mission_states
        )

    def _retire_card(self, card: MissionRetireItem, missions: MissionService) -> RetireResult:
        """D-338 / D-339: cancel only the Mission; its Work and Runs (if any) are already terminal and stay as they are."""

        planned = (card.mission_id,)
        try:
            mission = ContinuityStore(self._root).get_mission(card.mission_id)
            missions.transition(
                mission_id=mission.mission_id,
                expected_version=mission.version,
                new_state=MissionState.CANCELLED,
                root_work_id=None,
                idempotency_key=f"retire-{card.kind}-{card.mission_id}-v{mission.version}",
            )
        except (MissionServiceError, ContinuityStoreError) as error:
            return RetireResult(card.root_work_id, "skipped", f"没有收：{error}", planned,
                                kind=card.kind, states_before=(card.state,))
        return RetireResult(card.root_work_id, "retired", "已取消", planned, planned,
                            kind=card.kind, states_before=(card.state,))

    def _write_trace(self, project_id: str, evidence: str, results: list[RetireResult]) -> Path:
        """Write the trace; never overwrite an earlier one (D-134: two applies in the same second used to share a file)."""

        stamp = self._now().astimezone(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        folder = self._root / REPORT_RELATIVE_DIR
        folder.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": "pm-retire-trace.v1",
            "project_id": project_id,
            "at": self._now().astimezone(UTC).isoformat(),
            "approval_evidence_ref": evidence,
            "results": [
                {
                    "kind": r.kind,
                    "work_id": r.work_id,
                    "mission_ids": list(r.mission_ids),
                    "mission_states_before": list(r.states_before),
                    "cancelled_mission_ids": list(r.cancelled_mission_ids),
                    "outcome": r.outcome,
                    "detail": r.detail,
                }
                for r in results
            ],
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        for attempt in range(1000):
            path = folder / f"retire-{project_id}-{stamp}{'' if attempt == 0 else f'-{attempt}'}.json"
            try:
                with path.open("x", encoding="utf-8", newline="\n") as handle:  # exclusive: fails if the name is taken
                    handle.write(text)
            except FileExistsError:
                continue
            return path
        raise RetireError("留痕文件名连续冲突，没有写入")
