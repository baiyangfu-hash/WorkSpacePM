"""D-109 layer 2: ``RetireService`` cancels an old leftover Work and its root Mission; it never touches a live card."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

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


def _mission(root: Path, work_id: str, *, expired: bool = True, final: MissionState = MissionState.ACTIVE) -> str:
    """A Mission rooted at ``work_id``, created 6 days ago; by NOW its authority has (by default) expired."""

    mission_id = f"MISSION-{work_id}"
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
    for state in (MissionState.AWAITING_APPROVAL, MissionState.ACTIVE):
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
    assert [(i.work_id, i.mission_id, i.blocked_reason) for i in plan.items] == [("WORK-OLD", mission_id, "")]
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
    assert [(r.outcome, r.mission_id) for r in results] == [("retired", "")]
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
