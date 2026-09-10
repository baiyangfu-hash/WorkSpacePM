"""Resume v2 and PM_SESSION projection boundary tests."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from auto_pm.core.continuity_execution_service import ContinuityExecutionService
from auto_pm.core.continuity_resume_service import ContinuityResumeError, ContinuityResumeService
from auto_pm.core.mission_service import MissionService
from auto_pm.core.pm_session_projection_service import (
    PmSessionProjectionError,
    PmSessionProjectionService,
)
from auto_pm.core.work_registry_service import WorkRegistryService

from auto_pm.contracts.continuity import WorkKind
from auto_pm.contracts.mission import AuthorityAudit, AuthorityEnvelope, MissionState


def _workspace(root: Path) -> Path:
    project = root / "SW-2026-008"
    project.mkdir()
    (project / ".copier-answers.yml").write_text(
        "project_id: SW-2026-008\nproject_name: Resume Test\nstack: python\n",
        encoding="utf-8",
    )
    registry = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry.parent.mkdir()
    registry.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [
                    {
                        "project_id": "SW-2026-008",
                        "project_root": "SW-2026-008",
                        "development_root": "SW-2026-008",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return project


def _work(root: Path, work_id: str) -> None:
    service = WorkRegistryService(root, now=lambda: "2026-09-09T12:00:00+00:00")
    service.initialize("test")
    service.create_work(
        work_id=work_id,
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title=work_id,
        owner="architect",
        scope_paths=["auto_pm/a.py"],
        source_fingerprint="sha256:abc",
        idempotency_key=f"create-{work_id}",
        read_only=True,
    )


def _run(root: Path) -> None:
    execution = ContinuityExecutionService(
        root, now=lambda: datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    )
    execution.start_run(
        run_id="RUN-001",
        work_id="WORK-001",
        executor_id="agent-a",
        adapter="codex",
        owned_paths=["auto_pm/a.py"],
        declared_dirty_paths=[],
        observed_dirty_paths=[],
        git_head="a" * 40,
        worktree_path="C:/workspace",
        lease_token="lease-secret",
        lease_seconds=900,
        idempotency_key="create-run",
    )


def _mission(root: Path, mission_id: str = "MISSION-001") -> None:
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    service = MissionService(root, now=lambda: now)
    service.initialize("test")
    authority = AuthorityEnvelope(
        envelope_id=f"AUTH-{mission_id}",
        subject_project_id="SW-2026-008",
        change_id="CHG-SCPT-2026-200",
        decision_id="DEC-20260910-7421E80D",
        scope_paths=("auto_pm/a.py",),
        valid_from=now - timedelta(hours=1),
        expires_at=now + timedelta(days=1),
        audit=AuthorityAudit(
            created_by="Codex PM",
            created_at=now,
            approved_by="fubai",
            approved_at=now,
            source_fingerprint=f"sha256:{'a' * 64}",
        ),
    )
    service.create(
        mission_id=mission_id,
        subject_project_id="SW-2026-008",
        title="Resume mission",
        objective="Recover a user-approved mission.",
        acceptance_criteria=["Mission is visible on resume."],
        authority=authority,
        created_by="Codex PM",
        idempotency_key=f"create-{mission_id}",
    )
    service.transition(
        mission_id=mission_id,
        expected_version=1,
        new_state=MissionState.AWAITING_APPROVAL,
        root_work_id=None,
        idempotency_key=f"submit-{mission_id}",
    )


def test_empty_store_returns_explicitly_empty_execution_state(tmp_path: Path) -> None:
    _workspace(tmp_path)

    result = ContinuityResumeService(
        tmp_path, now=lambda: datetime(2026, 9, 9, 12, 1, tzinfo=UTC)
    ).collect(project_id="SW-2026-008")

    assert result.schema_version == "continuity-resume.v2"
    assert result.mission is None
    assert result.work is None
    assert result.run is None
    assert result.checkpoint is None
    assert result.lease is None
    assert result.next_legal_action == ""
    assert not (tmp_path / ".auto-pm" / "continuity.db").exists()


def test_resume_returns_one_unambiguous_work_and_run(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    _run(tmp_path)

    result = ContinuityResumeService(
        tmp_path, now=lambda: datetime(2026, 9, 9, 12, 1, tzinfo=UTC)
    ).collect(project_id="SW-2026-008")

    assert result.work and result.work.work_id == "WORK-001"
    assert result.run and result.run.run_id == "RUN-001"
    assert result.lease and result.lease.owner_id == "agent-a"
    assert result.lease.schema_version == "lease-view.v1"
    assert "lease_token" not in result.lease.model_dump(mode="json")
    assert result.checkpoint is None
    assert result.next_legal_action == "CONTINUE_RUN"


def test_resume_projects_mission_and_user_approval_boundary(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _mission(tmp_path)

    result = ContinuityResumeService(
        tmp_path, now=lambda: datetime(2026, 9, 9, 12, 1, tzinfo=UTC)
    ).collect(project_id="SW-2026-008")

    assert result.mission and result.mission.mission_id == "MISSION-001"
    assert result.work is None
    assert result.next_legal_action == "AWAIT_USER_APPROVAL"


def test_multiple_active_missions_fail_closed_without_guessing(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _mission(tmp_path, "MISSION-001")
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("DROP INDEX idx_one_open_mission_per_project")
        conn.execute(
            """INSERT INTO mission_items
            SELECT 'MISSION-002', subject_project_id, title, objective, state, root_work_id,
                   acceptance_criteria_json, authority_json, version, created_by, created_at, updated_at
            FROM mission_items WHERE mission_id='MISSION-001'"""
        )
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    result = ContinuityResumeService(tmp_path).collect(project_id="SW-2026-008")

    assert result.mission is None
    assert result.conflicts == ("MULTIPLE_ACTIVE_MISSIONS",)
    assert result.next_legal_action == ""


def test_expired_lease_is_a_conflict_and_suppresses_next_action(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    _run(tmp_path)

    result = ContinuityResumeService(
        tmp_path, now=lambda: datetime(2026, 9, 9, 12, 16, tzinfo=UTC)
    ).collect(project_id="SW-2026-008")

    assert "LEASE_EXPIRED" in result.conflicts
    assert result.next_legal_action == ""


def test_multiple_active_works_fail_closed_without_guessing(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    _work(tmp_path, "WORK-002")

    result = ContinuityResumeService(tmp_path).collect(project_id="SW-2026-008")

    assert result.work is None
    assert result.run is None
    assert result.conflicts == ("MULTIPLE_ACTIVE_WORKS",)
    assert result.next_legal_action == ""


def test_explicit_work_disambiguates_but_cross_project_fails(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    _work(tmp_path, "WORK-002")
    result = ContinuityResumeService(tmp_path).collect(
        project_id="SW-2026-008", work_id="WORK-002"
    )
    assert result.work and result.work.work_id == "WORK-002"

    service = WorkRegistryService(tmp_path, now=lambda: "2026-09-09T12:00:00+00:00")
    service.create_work(
        work_id="WORK-OTHER",
        subject_project_id="SYS-2026-001",
        kind=WorkKind.GOVERNANCE,
        title="Other",
        owner="architect",
        scope_paths=["x.py"],
        source_fingerprint="sha256:def",
        idempotency_key="create-other",
        read_only=True,
    )
    with pytest.raises(ContinuityResumeError, match="subject project"):
        ContinuityResumeService(tmp_path).collect(
            project_id="SW-2026-008", work_id="WORK-OTHER"
        )


def test_corrupt_continuity_store_fails_closed(tmp_path: Path) -> None:
    _workspace(tmp_path)
    path = tmp_path / ".auto-pm" / "continuity.db"
    path.parent.mkdir()
    path.write_text("not sqlite", encoding="utf-8")

    with pytest.raises(ContinuityResumeError, match="无法读取"):
        ContinuityResumeService(tmp_path).collect(project_id="SW-2026-008")


def test_future_continuity_schema_fails_closed_on_resume(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _mission(tmp_path)
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE schema_meta SET schema_version='continuity-store.v999'")
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    with pytest.raises(ContinuityResumeError, match="未知或未来"):
        ContinuityResumeService(tmp_path).collect(project_id="SW-2026-008")


def _store_snapshot(db_path: Path) -> tuple[tuple[str, ...], dict[str, tuple[int, int, str]]]:
    tracked = tuple(
        path
        for path in (db_path, Path(f"{db_path}-wal"), Path(f"{db_path}-shm"))
        if path.exists()
    )
    entries = tuple(sorted(path.name for path in db_path.parent.iterdir()))
    files = {
        path.name: (
            path.stat().st_size,
            path.stat().st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in tracked
    }
    return entries, files


def test_resume_succeeds_without_unmerged_wal_and_preserves_empty_sidecars(
    tmp_path: Path,
) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    _run(tmp_path)
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    keeper = sqlite3.connect(db_path)
    try:
        keeper.execute("SELECT COUNT(*) FROM work_items").fetchone()
        wal_path = Path(f"{db_path}-wal")
        shm_path = Path(f"{db_path}-shm")
        assert wal_path.is_file() and wal_path.stat().st_size == 0
        assert shm_path.is_file()
        before = _store_snapshot(db_path)

        result = ContinuityResumeService(
            tmp_path, now=lambda: datetime(2026, 9, 9, 12, 1, tzinfo=UTC)
        ).collect(project_id="SW-2026-008")

        assert result.run and result.run.run_id == "RUN-001"
        assert _store_snapshot(db_path) == before
    finally:
        keeper.close()


def test_resume_fails_closed_on_nonempty_wal_without_mutating_store(tmp_path: Path) -> None:
    _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    writer = sqlite3.connect(db_path)
    try:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute(
            "UPDATE work_items SET title=? WHERE work_id=?", ("WAL pending", "WORK-001")
        )
        writer.commit()
        wal_path = Path(f"{db_path}-wal")
        shm_path = Path(f"{db_path}-shm")
        assert wal_path.is_file() and wal_path.stat().st_size > 0
        assert shm_path.is_file()
        before = _store_snapshot(db_path)

        with pytest.raises(ContinuityResumeError, match="未合并 WAL"):
            ContinuityResumeService(tmp_path).collect(project_id="SW-2026-008")

        assert _store_snapshot(db_path) == before
    finally:
        writer.close()


def test_pm_session_projection_contains_no_execution_queue(tmp_path: Path) -> None:
    project = _workspace(tmp_path)
    _work(tmp_path, "WORK-001")
    result = ContinuityResumeService(tmp_path).collect(project_id="SW-2026-008")
    target = project / "PM_SESSION_SW-2026-008.md"

    PmSessionProjectionService().write(result, target)
    content = target.read_text(encoding="utf-8")

    assert "pm-session-projection.v1" in content
    assert "source_of_truth: .auto-pm/continuity.db" in content
    assert "WORK-001" not in content
    assert "current_focus" not in content
    with pytest.raises(PmSessionProjectionError, match="subject project"):
        PmSessionProjectionService().write(result, tmp_path / "outside.md")
