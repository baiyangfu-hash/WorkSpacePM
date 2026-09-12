"""Behaviour tests for the state-free PM Facade."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from auto_pm.core.mission_service import MissionService
from auto_pm.core.pm_facade_service import PmFacadeError, PmFacadeService
from auto_pm.core.work_registry_service import WorkRegistryService

from auto_pm.contracts.continuity import WorkKind, WorkState
from auto_pm.contracts.mission import AuthorityAudit, AuthorityEnvelope, MissionState
from auto_pm.contracts.pm_facade import PmConfirmationKind


def _git_root(root: Path) -> None:
    subprocess.run(
        ["git", "-C", str(root), "init"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _authority(now: datetime) -> AuthorityEnvelope:
    return AuthorityEnvelope(
        envelope_id="AUTH-PM-FACADE-001",
        subject_project_id="SW-TEST-001",
        change_id="CHG-SCPT-2026-201",
        decision_id="DEC-20260910-C518CA55",
        scope_paths=("pm.py",),
        valid_from=now - timedelta(minutes=1),
        expires_at=now + timedelta(days=1),
        audit=AuthorityAudit(
            created_by="Codex PM",
            created_at=now,
            approved_by="fubai",
            approved_at=now,
            source_fingerprint=f"sha256:{'b' * 64}",
        ),
    )


def _setup(root: Path) -> tuple[MissionService, PmFacadeService]:
    _git_root(root)
    now = datetime.now(UTC)
    works = WorkRegistryService(root)
    works.initialize("test")
    works.create_work(
        work_id="WORK-PM-001",
        subject_project_id="SW-TEST-001",
        kind=WorkKind.WBS,
        title="Facade root work",
        owner="Codex",
        scope_paths=["pm.py"],
        source_fingerprint="sha256:test",
        idempotency_key="work-create",
        read_only=True,
    )
    missions = MissionService(root)
    missions.initialize("test")
    missions.create(
        mission_id="MISSION-PM-001",
        subject_project_id="SW-TEST-001",
        title="Friendly PM",
        objective="Hide internal task routing from the user.",
        acceptance_criteria=["User sees only confirmation cards."],
        authority=_authority(now),
        created_by="Codex PM",
        idempotency_key="mission-create",
        root_work_id="WORK-PM-001",
    )
    return missions, PmFacadeService(root)


def test_plan_approve_and_execute_are_bounded_and_idempotent(tmp_path: Path) -> None:
    _, facade = _setup(tmp_path)

    plan = facade.plan("MISSION-PM-001")
    assert plan.kind is PmConfirmationKind.APPROVAL
    assert plan.mission_state is MissionState.AWAITING_APPROVAL
    assert facade.plan("MISSION-PM-001").mission_state is MissionState.AWAITING_APPROVAL

    approved = facade.approve("MISSION-PM-001", "WORK-PM-001")
    assert approved.kind is PmConfirmationKind.EXECUTION
    assert approved.mission_state is MissionState.ACTIVE

    executing = facade.execute("MISSION-PM-001")
    assert executing.kind is PmConfirmationKind.EXECUTION
    assert facade._work("WORK-PM-001").state is WorkState.IN_PROGRESS


def test_accept_requires_the_verification_gate(tmp_path: Path) -> None:
    missions, facade = _setup(tmp_path)

    facade.plan("MISSION-PM-001")
    facade.approve("MISSION-PM-001", "WORK-PM-001")
    active = missions.get("MISSION-PM-001")
    missions.transition(
        mission_id=active.mission_id,
        expected_version=active.version,
        new_state=MissionState.ACCEPTANCE_PENDING,
        root_work_id=active.root_work_id,
        idempotency_key="verification-complete",
    )

    card = facade.accept("MISSION-PM-001")
    assert card.kind is PmConfirmationKind.ACCEPTANCE
    assert card.mission_state is MissionState.ACCEPTED


def test_confirm_start_uses_the_mission_bound_work_without_an_internal_id(tmp_path: Path) -> None:
    _, facade = _setup(tmp_path)

    facade.plan("MISSION-PM-001")
    card = facade.confirm_start("MISSION-PM-001")

    assert card.kind is PmConfirmationKind.EXECUTION
    assert facade._work("WORK-PM-001").state is WorkState.IN_PROGRESS


def test_facade_rejects_out_of_order_actions_and_keeps_legacy_isolated(tmp_path: Path) -> None:
    _, facade = _setup(tmp_path)

    with pytest.raises(PmFacadeError, match="可执行状态"):
        facade.execute("MISSION-PM-001")
    assert "pm-workflow 已退役隔离" in facade.compatibility_notice()
