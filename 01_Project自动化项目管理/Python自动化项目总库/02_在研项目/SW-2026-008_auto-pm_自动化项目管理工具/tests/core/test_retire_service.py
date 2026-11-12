"""D-109 layer 2: ``RetireService`` cancels an old leftover Work and its root Mission; it never touches a live card."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from auto_pm.application.core.mission_service import MissionService
from auto_pm.application.core.retire_service import RetireError, RetireService
from auto_pm.contracts.continuity import WorkState
from auto_pm.contracts.mission import AuthorityAudit, AuthorityEnvelope, MissionState
from auto_pm.infrastructure.continuity_store import ContinuityStore
from tests.core.test_continuity_resume_service import _workspace
from tests.core.test_resume_residue import NOW, _leftover, _live

PROJECT = "SW-2026-008"
CREATED = NOW - timedelta(days=6)


def _mission(
    root: Path,
    work_id: str,
    *,
    expired: bool = True,
    final: MissionState = MissionState.ACTIVE,
    suffix: str = "",
    activate: bool = True,
) -> str:
    """A Mission rooted at ``work_id``, created 6 days ago; by NOW its authority has (by default) expired."""

    mission_id = f"MISSION-{work_id}{suffix}"
    authority = AuthorityEnvelope(
        envelope_id="AUTH-RETIRE-1",
        subject_project_id=PROJECT,
        change_id="CHG-SCPT-2026-200",
        decision_id="DEC-20260910-7421E80D",
        scope_paths=("auto_pm/a.py",),
        valid_from=CREATED - timedelta(hours=1),
        expires_at=(NOW - timedelta(days=2)) if expired else (NOW + timedelta(days=2)),
        audit=AuthorityAudit(
            created_by="Codex PM",
            created_at=CREATED,
            approved_by="fubai",
            approved_at=CREATED,
            source_fingerprint=f"sha256:{'a' * 64}",
        ),
    )
    service = MissionService(root, now=lambda: CREATED)
    service.initialize("test")
    mission = service.create(
        mission_id=mission_id,
        subject_project_id=PROJECT,
        title="old card",
        objective="o",
        acceptance_criteria=["c"],
        authority=authority,
        created_by="Codex PM",
        idempotency_key=f"create-{mission_id}",
        root_work_id=work_id,
    )
    for state in (MissionState.AWAITING_APPROVAL, MissionState.ACTIVE) if activate else (MissionState.AWAITING_APPROVAL,):
        mission = service.transition(
            mission_id=mission_id,
            expected_version=mission.version,
            new_state=state,
            root_work_id=None if state is MissionState.AWAITING_APPROVAL else work_id,
            idempotency_key=f"{state.value}-{mission_id}",
        )
    if final is MissionState.ACCEPTANCE_PENDING:
        mission = service.transition(
            mission_id=mission_id,
            expected_version=mission.version,
            new_state=final,
            root_work_id=work_id,
            idempotency_key=f"{final.value}-{mission_id}",
        )
    return mission_id


def _service(root: Path, at: datetime = NOW) -> RetireService:
    return RetireService(root, now=lambda: at)


def _states(root: Path, work_id: str, mission_id: str) -> tuple[WorkState, MissionState | None]:
    store = ContinuityStore(root)
    return store.get_work(work_id).state, (store.get_mission(mission_id).state if mission_id else None)


def test_dry_run_lists_the_leftover_and_its_mission_and_writes_nothing(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-OLD", timedelta(days=3))
    mission_id = _mission(tmp_path, "WORK-OLD")
    plan = _service(tmp_path).plan(PROJECT)
    assert [(i.work_id, i.mission_ids, i.blocked_reason) for i in plan.items] == [("WORK-OLD", (mission_id,), "")]
    assert _states(tmp_path, "WORK-OLD", mission_id) == (WorkState.BLOCKED, MissionState.ACTIVE)
    assert not (tmp_path / ".auto-pm" / "reports" / "retire").exists()


def test_apply_cancels_the_mission_with_expired_authority_then_the_work_and_writes_a_trace(tmp_path: Path) -> None:
    """The D-109 blocker: an old card whose authority expired could not be cancelled by any command."""

    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-OLD", timedelta(days=3))
    mission_id = _mission(tmp_path, "WORK-OLD", expired=True)
    results, trace = _service(tmp_path).apply(PROJECT, [], approval_evidence_ref="user-confirmation:2026-11-08T12:00Z")
    assert [(r.work_id, r.outcome) for r in results] == [("WORK-OLD", "retired")]
    assert _states(tmp_path, "WORK-OLD", mission_id) == (WorkState.CANCELLED, MissionState.CANCELLED)
    assert trace is not None and trace.parent == tmp_path / ".auto-pm" / "reports" / "retire"
    recorded = json.loads(trace.read_text(encoding="utf-8"))
    assert recorded["approval_evidence_ref"] == "user-confirmation:2026-11-08T12:00Z"
    assert recorded["results"][0]["outcome"] == "retired"
    # the leftover is gone from the listing, and a second apply has nothing left to do
    assert _service(tmp_path).plan(PROJECT).items == []
    assert _service(tmp_path).apply(PROJECT, [])[0] == []


def test_a_leftover_without_a_mission_is_retired_alone(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-OLD", timedelta(days=3))
    results, _ = _service(tmp_path).apply(PROJECT, ["WORK-OLD"])
    assert [(r.outcome, r.mission_ids) for r in results] == [("retired", ())]
    assert ContinuityStore(tmp_path).get_work("WORK-OLD").state is WorkState.CANCELLED


def test_a_live_card_is_never_touched_and_a_named_non_leftover_is_reported(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-OLD", timedelta(days=3))
    _live(tmp_path, "WORK-LIVE")
    live_mission = _mission(tmp_path, "WORK-LIVE", expired=False)
    results, _ = _service(tmp_path).apply(PROJECT, ["WORK-LIVE", "WORK-OLD"])
    by_id = {r.work_id: r for r in results}
    assert by_id["WORK-OLD"].outcome == "retired"
    assert by_id["WORK-LIVE"].outcome == "skipped"
    assert _states(tmp_path, "WORK-LIVE", live_mission) == (WorkState.IN_PROGRESS, MissionState.ACTIVE)


def test_only_the_named_work_is_retired(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-A", timedelta(days=3))
    _leftover(tmp_path, "WORK-B", timedelta(days=3))
    results, _ = _service(tmp_path).apply(PROJECT, ["WORK-A"])
    assert [r.work_id for r in results] == ["WORK-A"]
    assert ContinuityStore(tmp_path).get_work("WORK-B").state is WorkState.BLOCKED


def test_a_mission_waiting_for_the_users_verdict_is_left_alone_with_its_work(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-OLD", timedelta(days=3))
    mission_id = _mission(tmp_path, "WORK-OLD", expired=False, final=MissionState.ACCEPTANCE_PENDING)
    results, _ = _service(tmp_path).apply(PROJECT, [])
    assert [(r.outcome) for r in results] == ["skipped"] and "验收" in results[0].detail
    assert _states(tmp_path, "WORK-OLD", mission_id) == (WorkState.BLOCKED, MissionState.ACCEPTANCE_PENDING)


def test_a_work_that_got_a_fresh_run_since_the_scan_is_not_retired(tmp_path: Path) -> None:
    """apply re-reads the ledger: a card that is not an old leftover *now* is left alone even if it was named."""

    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-OLD", timedelta(hours=2))  # failed only 2 hours ago: not yet a leftover
    results, _ = _service(tmp_path).apply(PROJECT, ["WORK-OLD"])
    assert [r.outcome for r in results] == ["skipped"]
    assert ContinuityStore(tmp_path).get_work("WORK-OLD").state is WorkState.BLOCKED


def test_a_committed_pin_is_required_for_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.application.core.approval_proof_service import ApprovalProofService, make_key

    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-OLD", timedelta(days=3))
    key = make_key("baiyang", "Retire4815162342x", n=2**10)
    monkeypatch.setattr(ApprovalProofService, "committed_state", lambda self: ([key], ""))
    with pytest.raises(RetireError):
        _service(tmp_path).apply(PROJECT, [], approval_pin="Wrong0000000000x")
    assert ContinuityStore(tmp_path).get_work("WORK-OLD").state is WorkState.BLOCKED
    results, _ = _service(tmp_path).apply(PROJECT, [], approval_pin="Retire4815162342x")
    assert results[0].outcome == "retired"


def test_every_open_mission_under_the_work_is_listed_and_cancelled(tmp_path: Path) -> None:
    """D-135: the ledger lets one Work root several open Missions; none may be left behind as an orphan."""

    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-OLD", timedelta(days=3))
    active = _mission(tmp_path, "WORK-OLD")
    waiting = _mission(tmp_path, "WORK-OLD", suffix="-B", activate=False)
    plan = _service(tmp_path).plan(PROJECT)
    assert sorted(plan.items[0].mission_ids) == sorted([active, waiting])
    results, _ = _service(tmp_path).apply(PROJECT, [])
    assert [r.outcome for r in results] == ["retired"] and sorted(results[0].mission_ids) == sorted([active, waiting])
    store = ContinuityStore(tmp_path)
    assert store.get_mission(active).state is MissionState.CANCELLED
    assert store.get_mission(waiting).state is MissionState.CANCELLED
    assert store.get_work("WORK-OLD").state is WorkState.CANCELLED


def test_one_mission_waiting_for_the_users_verdict_keeps_the_whole_card_untouched(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-OLD", timedelta(days=3))
    pending = _mission(tmp_path, "WORK-OLD", expired=False, final=MissionState.ACCEPTANCE_PENDING)
    other = _mission(tmp_path, "WORK-OLD", suffix="-B", activate=False)
    results, _ = _service(tmp_path).apply(PROJECT, [])
    assert [r.outcome for r in results] == ["skipped"]
    store = ContinuityStore(tmp_path)
    assert store.get_mission(pending).state is MissionState.ACCEPTANCE_PENDING
    assert store.get_mission(other).state is MissionState.AWAITING_APPROVAL
    assert store.get_work("WORK-OLD").state is WorkState.BLOCKED


def test_two_applies_in_the_same_instant_keep_both_traces(tmp_path: Path) -> None:
    """D-134: the trace name used to be to-the-second, so the second apply overwrote the first."""

    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-A", timedelta(days=3))
    _leftover(tmp_path, "WORK-B", timedelta(days=3))
    _, first = _service(tmp_path).apply(PROJECT, ["WORK-A"])
    _, second = _service(tmp_path).apply(PROJECT, ["WORK-B"])
    assert first is not None and second is not None and first != second
    assert json.loads(first.read_text(encoding="utf-8"))["results"][0]["work_id"] == "WORK-A"
    assert json.loads(second.read_text(encoding="utf-8"))["results"][0]["work_id"] == "WORK-B"


# ---------------------------------------------------------------- CHG-SCPT-2026-647：D-338 草稿卡、D-339 孤卡

EVIDENCE = "user-confirmation:2026-11-12T19:40:27Z"


def _bare(root: Path, mission_id: str, *, awaiting: bool = False, project: str = PROJECT) -> str:
    """D-338: a card that never got a Work (DRAFT, or AWAITING_APPROVAL); its authority has expired by NOW."""

    authority = AuthorityEnvelope(
        envelope_id="AUTH-RETIRE-2",
        subject_project_id=project,
        change_id="CHG-SCPT-2026-200",
        decision_id="DEC-20260910-7421E80D",
        scope_paths=("auto_pm/a.py",),
        valid_from=CREATED - timedelta(hours=1),
        expires_at=NOW - timedelta(days=2),
        audit=AuthorityAudit(
            created_by="Codex PM",
            created_at=CREATED,
            approved_by="fubai",
            approved_at=CREATED,
            source_fingerprint=f"sha256:{'b' * 64}",
        ),
    )
    service = MissionService(root, now=lambda: CREATED)
    service.initialize("test")
    mission = service.create(
        mission_id=mission_id, subject_project_id=project, title="draft card", objective="o", acceptance_criteria=["c"],
        authority=authority, created_by="Codex PM", idempotency_key=f"create-{mission_id}",
    )
    if awaiting:
        service.transition(
            mission_id=mission_id, expected_version=mission.version, new_state=MissionState.AWAITING_APPROVAL,
            root_work_id=None, idempotency_key=f"await-{mission_id}",
        )
    return mission_id


def _orphan(root: Path, work_id: str = "WORK-GONE") -> str:
    """D-339: an ACTIVE card whose Work was cancelled; its only Run failed 3 days ago."""

    from auto_pm.application.core.work_registry_service import WorkRegistryService

    _leftover(root, work_id, timedelta(days=3))
    mission_id = _mission(root, work_id)
    WorkRegistryService(root, now=lambda: NOW.isoformat()).transition(work_id, WorkState.CANCELLED, f"cancel-{work_id}")
    return mission_id


def _mission_state(root: Path, mission_id: str) -> MissionState:
    return ContinuityStore(root).get_mission(mission_id).state


@pytest.mark.parametrize("awaiting", [False, True])
def test_d338_a_draft_without_work_is_listed_then_cancelled_with_a_trace(tmp_path: Path, awaiting: bool) -> None:
    _workspace(tmp_path)
    mission_id = _bare(tmp_path, "MISSION-DRAFT", awaiting=awaiting)
    before = "AWAITING_APPROVAL" if awaiting else "DRAFT"
    plan = _service(tmp_path).plan(PROJECT, mission_ids=[mission_id])
    assert [(c.mission_id, c.kind, c.state, c.root_work_id, c.blocked_reason) for c in plan.missions] == [
        (mission_id, "draft_without_work", before, "", "")
    ]
    assert plan.items == [] and _mission_state(tmp_path, mission_id).value == before  # 预演不写
    assert not (tmp_path / ".auto-pm" / "reports" / "retire").exists()
    results, trace = _service(tmp_path).apply(PROJECT, [], mission_ids=[mission_id], approval_evidence_ref=EVIDENCE)
    assert [(r.outcome, r.kind, r.cancelled_mission_ids) for r in results] == [("retired", "draft_without_work", (mission_id,))]
    assert _mission_state(tmp_path, mission_id) is MissionState.CANCELLED
    assert trace is not None
    recorded = json.loads(trace.read_text(encoding="utf-8"))
    assert recorded["approval_evidence_ref"] == EVIDENCE
    assert recorded["results"] == [{
        "kind": "draft_without_work", "work_id": "", "mission_ids": [mission_id], "mission_states_before": [before],
        "cancelled_mission_ids": [mission_id], "outcome": "retired", "detail": "已取消",
    }]


def test_d338_the_stale_scan_never_picks_up_a_draft_by_itself(tmp_path: Path) -> None:
    """A draft may still be waiting for a real approval: only a card the user names is retired."""

    _workspace(tmp_path)
    mission_id = _bare(tmp_path, "MISSION-DRAFT")
    assert _service(tmp_path).plan(PROJECT).missions == []
    assert _service(tmp_path).apply(PROJECT, [])[0] == []
    assert _mission_state(tmp_path, mission_id) is MissionState.DRAFT


def test_d338_a_card_with_a_live_work_or_waiting_for_acceptance_is_refused_with_a_reason(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-OLD", timedelta(days=3))
    pending = _mission(tmp_path, "WORK-OLD", expired=False, final=MissionState.ACCEPTANCE_PENDING)
    _live(tmp_path, "WORK-LIVE")  # 一个项目同一时刻只有一张在干：先把另一张送到等验收
    live = _mission(tmp_path, "WORK-LIVE", expired=False)
    plan = _service(tmp_path).plan(PROJECT, mission_ids=[live, pending])
    reasons = {c.mission_id: c.blocked_reason for c in plan.missions}
    assert "不是孤卡" in reasons[live] and "IN_PROGRESS" in reasons[live]
    assert "ACCEPTANCE_PENDING" in reasons[pending]
    results, _ = _service(tmp_path).apply(PROJECT, [], mission_ids=[live, pending], approval_evidence_ref=EVIDENCE)
    assert [r.outcome for r in results] == ["skipped", "skipped"]
    assert _mission_state(tmp_path, live) is MissionState.ACTIVE
    assert _mission_state(tmp_path, pending) is MissionState.ACCEPTANCE_PENDING


def test_d338_an_unknown_card_or_one_of_another_project_is_reported_and_untouched(tmp_path: Path) -> None:
    _workspace(tmp_path)
    other = _bare(tmp_path, "MISSION-OTHER", project="DJ-2026-009")
    plan = _service(tmp_path).plan(PROJECT, mission_ids=["MISSION-NOPE", other])
    assert plan.missions == [] and plan.unknown_mission_ids == ["MISSION-NOPE", other]
    results, _ = _service(tmp_path).apply(PROJECT, [], mission_ids=["MISSION-NOPE", other], approval_evidence_ref=EVIDENCE)
    assert [(r.outcome, r.mission_ids) for r in results] == [("skipped", ("MISSION-NOPE",)), ("skipped", (other,))]
    assert _mission_state(tmp_path, other) is MissionState.DRAFT


def test_d338_a_committed_pin_is_required(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.application.core.approval_proof_service import ApprovalProofService, make_key

    _workspace(tmp_path)
    mission_id = _bare(tmp_path, "MISSION-DRAFT")
    key = make_key("baiyang", "Retire4815162342x", n=2**10)
    monkeypatch.setattr(ApprovalProofService, "committed_state", lambda self: ([key], ""))
    with pytest.raises(RetireError):
        _service(tmp_path).apply(PROJECT, [], mission_ids=[mission_id], approval_pin="Wrong0000000000x")
    assert _mission_state(tmp_path, mission_id) is MissionState.DRAFT


def test_d339_an_orphan_card_is_listed_by_stale_and_only_the_mission_is_cancelled(tmp_path: Path) -> None:
    _workspace(tmp_path)
    mission_id = _orphan(tmp_path)
    store = ContinuityStore(tmp_path)
    run_before = store.get_run("RUN-WORK-GONE")
    plan = _service(tmp_path).plan(PROJECT)
    assert [(c.mission_id, c.kind, c.root_work_id) for c in plan.missions] == [(mission_id, "orphan_mission", "WORK-GONE")]
    assert plan.items == []  # 它的 Work 已是终态，不是陈年残留，不会重复列
    results, trace = _service(tmp_path).apply(PROJECT, [], approval_evidence_ref=EVIDENCE)
    assert [(r.outcome, r.kind, r.work_id, r.states_before) for r in results] == [
        ("retired", "orphan_mission", "WORK-GONE", ("ACTIVE",))
    ]
    store = ContinuityStore(tmp_path)
    assert store.get_mission(mission_id).state is MissionState.CANCELLED
    assert store.get_work("WORK-GONE").state is WorkState.CANCELLED
    run_after = store.get_run("RUN-WORK-GONE")
    assert (run_after.state, run_after.version) == (run_before.state, run_before.version)  # Run 不碰
    assert trace is not None and _service(tmp_path).plan(PROJECT).missions == []


def test_d339_an_orphan_card_can_also_be_named(tmp_path: Path) -> None:
    _workspace(tmp_path)
    mission_id = _orphan(tmp_path)
    results, _ = _service(tmp_path).apply(PROJECT, [], mission_ids=[mission_id], approval_evidence_ref=EVIDENCE)
    assert [(r.outcome, r.kind) for r in results] == [("retired", "orphan_mission")]


def test_d339_a_cancelled_work_with_a_run_still_going_is_not_an_orphan() -> None:
    """Pure judgement: one Run that has not ended keeps the card out (somebody may still be working)."""

    from types import SimpleNamespace

    from auto_pm.application.core.stale_residue import is_orphan_mission
    from auto_pm.contracts.continuity import RunState

    open_states = {MissionState.ACTIVE, MissionState.BLOCKED}
    mission: Any = SimpleNamespace(state=MissionState.ACTIVE, root_work_id="WORK-1")
    work: Any = SimpleNamespace(work_id="WORK-1", state=WorkState.CANCELLED)
    ended: Any = SimpleNamespace(state=RunState.FAILED)
    going: Any = SimpleNamespace(state=RunState.RUNNING)
    assert is_orphan_mission(mission, work, [ended], open_states)
    assert is_orphan_mission(mission, work, [], open_states)
    assert not is_orphan_mission(mission, work, [ended, going], open_states)
    live_work: Any = SimpleNamespace(work_id="WORK-1", state=WorkState.IN_PROGRESS)
    other_work: Any = SimpleNamespace(work_id="WORK-2", state=WorkState.CANCELLED)
    assert not is_orphan_mission(mission, live_work, [ended], open_states)
    assert not is_orphan_mission(mission, other_work, [ended], open_states)
    assert not is_orphan_mission(mission, None, [ended], open_states)
    closed: Any = SimpleNamespace(state=MissionState.ACCEPTANCE_PENDING, root_work_id="WORK-1")
    assert not is_orphan_mission(closed, work, [ended], open_states)


def test_d339_a_leftover_work_still_goes_the_old_way(tmp_path: Path) -> None:
    """A Work still IN_PROGRESS/BLOCKED is a leftover (D-109), not an orphan card: listed under items, not under missions."""

    _workspace(tmp_path)
    _leftover(tmp_path, "WORK-OLD", timedelta(days=3))
    mission_id = _mission(tmp_path, "WORK-OLD")
    plan = _service(tmp_path).plan(PROJECT)
    assert [i.work_id for i in plan.items] == ["WORK-OLD"] and plan.missions == []
    named = _service(tmp_path).plan(PROJECT, mission_ids=[mission_id])
    assert named.items == [] and "不是孤卡" in named.missions[0].blocked_reason
