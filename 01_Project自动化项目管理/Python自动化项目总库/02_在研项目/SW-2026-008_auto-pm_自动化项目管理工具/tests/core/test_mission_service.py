"""Mission persistence, migration, and lifecycle boundary tests."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from auto_pm.core.mission_service import MissionService, MissionServiceError
from auto_pm.core.work_registry_service import WorkRegistryService

from auto_pm.contracts.continuity import WorkKind
from auto_pm.contracts.mission import AuthorityAudit, AuthorityEnvelope, MissionState
from auto_pm.infrastructure.continuity_store import ContinuityStore

NOW = datetime(2026, 9, 10, 3, 0, tzinfo=UTC)


def _authority(*, expires_at: datetime = NOW + timedelta(days=1)) -> AuthorityEnvelope:
    return AuthorityEnvelope(
        envelope_id="AUTH-SW008-A1",
        subject_project_id="SW-2026-008",
        change_id="CHG-SCPT-2026-200",
        decision_id="DEC-20260910-7421E80D",
        scope_paths=("auto_pm/infrastructure/continuity_store.py",),
        valid_from=NOW - timedelta(hours=1),
        expires_at=expires_at,
        audit=AuthorityAudit(
            created_by="Codex PM",
            created_at=NOW,
            approved_by="fubai",
            approved_at=NOW,
            source_fingerprint=f"sha256:{'a' * 64}",
        ),
    )


def _service(root: Path, *, now: datetime = NOW) -> MissionService:
    service = MissionService(root, now=lambda: now)
    service.initialize("test")
    return service


def _create(service: MissionService, mission_id: str = "MISSION-SW008-A1") -> None:
    service.create(
        mission_id=mission_id,
        subject_project_id="SW-2026-008",
        title="Mission truth",
        objective="Persist one approved business objective.",
        acceptance_criteria=["Resume can recover the active Mission."],
        authority=_authority(),
        created_by="Codex PM",
        idempotency_key=f"create-{mission_id}",
    )


def _work(root: Path) -> None:
    service = WorkRegistryService(root, now=lambda: NOW.isoformat())
    service.initialize("test")
    service.create_work(
        work_id="WORK-SW008-A1",
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title="Root work",
        owner="Codex",
        scope_paths=["auto_pm/infrastructure/continuity_store.py"],
        source_fingerprint="sha256:test",
        idempotency_key="create-root-work",
    )


def test_create_is_idempotent_and_rejects_another_open_mission(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _create(service)

    duplicate = service.create(
        mission_id="MISSION-SW008-A1",
        subject_project_id="SW-2026-008",
        title="Mission truth",
        objective="Persist one approved business objective.",
        acceptance_criteria=["Resume can recover the active Mission."],
        authority=_authority(),
        created_by="Codex PM",
        idempotency_key="create-MISSION-SW008-A1",
    )

    assert duplicate.mission_id == "MISSION-SW008-A1"
    with pytest.raises(MissionServiceError, match="未终结 Mission"):
        _create(service, "MISSION-SW008-SECOND")


def test_transition_requires_current_authority_root_work_and_expected_version(tmp_path: Path) -> None:
    service = _service(tmp_path)
    _create(service)
    awaiting = service.transition(
        mission_id="MISSION-SW008-A1",
        expected_version=1,
        new_state=MissionState.AWAITING_APPROVAL,
        root_work_id=None,
        idempotency_key="submit-a1",
    )
    _work(tmp_path)

    active = service.transition(
        mission_id="MISSION-SW008-A1",
        expected_version=awaiting.version,
        new_state=MissionState.ACTIVE,
        root_work_id="WORK-SW008-A1",
        idempotency_key="activate-a1",
    )

    assert active.state is MissionState.ACTIVE
    assert active.root_work_id == "WORK-SW008-A1"
    with pytest.raises(MissionServiceError, match="版本冲突"):
        service.transition(
            mission_id="MISSION-SW008-A1",
            expected_version=awaiting.version,
            new_state=MissionState.BLOCKED,
            root_work_id=None,
            idempotency_key="stale-transition",
        )


def test_expired_authority_fails_closed_before_any_mission_write(tmp_path: Path) -> None:
    service = _service(tmp_path)
    with pytest.raises(MissionServiceError, match="已过期"):
        service.create(
            mission_id="MISSION-SW008-EXPIRED",
            subject_project_id="SW-2026-008",
            title="Expired",
            objective="Must fail.",
            acceptance_criteria=["No write."],
            authority=_authority(expires_at=NOW - timedelta(seconds=1)),
            created_by="Codex PM",
            idempotency_key="expired",
        )
    assert ContinuityStore(tmp_path).list_active_missions("SW-2026-008") == ()


def test_v2_store_migrates_additively_and_preserves_existing_work(tmp_path: Path) -> None:
    registry = WorkRegistryService(tmp_path, now=lambda: NOW.isoformat())
    registry.initialize("legacy")
    registry.create_work(
        work_id="WORK-LEGACY-001",
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title="Legacy work",
        owner="Codex",
        scope_paths=["legacy.py"],
        source_fingerprint="sha256:legacy",
        idempotency_key="legacy-work",
    )
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP TABLE mission_items")
        conn.execute("DELETE FROM schema_migrations")
        conn.execute(
            "UPDATE schema_meta SET schema_version='continuity-store.v2'"
        )
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    service = _service(tmp_path)

    assert ContinuityStore(tmp_path).get_work("WORK-LEGACY-001").title == "Legacy work"
    with sqlite3.connect(db_path) as conn:
        version = conn.execute("SELECT schema_version FROM schema_meta").fetchone()[0]
        migration = conn.execute(
            "SELECT from_version, to_version FROM schema_migrations"
        ).fetchone()
    assert version == "continuity-store.v3"
    assert migration == ("continuity-store.v2", "continuity-store.v3")
    _create(service)


def test_unknown_schema_fails_closed(tmp_path: Path) -> None:
    _service(tmp_path)
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE schema_meta SET schema_version='continuity-store.v999'")

    with pytest.raises(MissionServiceError, match="未知或未来"):
        _service(tmp_path)
