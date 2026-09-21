"""Read-only and privacy boundary tests for the default PM cockpit projection."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

from auto_pm.core.continuity_execution_service import ContinuityExecutionService
from auto_pm.core.mission_service import MissionService
from auto_pm.core.pm_cockpit_service import PmCockpitService
from auto_pm.core.work_registry_service import WorkRegistryService

from auto_pm.contracts.continuity import WorkKind, WorkState
from auto_pm.contracts.mission import AuthorityAudit, AuthorityEnvelope, MissionState
from auto_pm.contracts.pm_cockpit import CockpitUserAction


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _git_root(root: Path) -> None:
    _git(root, "init")
    (root / "README.md").write_text("baseline\n", encoding="utf-8", errors="replace")
    _git(root, "add", "README.md")
    _git(
        root,
        "-c",
        "user.name=Cockpit Test",
        "-c",
        "user.email=cockpit@example.invalid",
        "commit",
        "-m",
        "baseline",
    )


def _registry(root: Path) -> None:
    path = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [
                    {
                        "project_id": "SW-2026-008",
                        "project_root": "projects/SW-2026-008_自动化项目管理工具",
                        "development_root": "projects/SW-2026-008_自动化项目管理工具",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _authority(now: datetime) -> AuthorityEnvelope:
    return AuthorityEnvelope(
        envelope_id="AUTH-COCKPIT-001",
        subject_project_id="SW-2026-008",
        change_id="CHG-SCPT-2026-207",
        decision_id="DEC-20260910-1B4F38FD",
        scope_paths=("auto_pm/core/pm_cockpit_service.py",),
        valid_from=now - timedelta(minutes=1),
        expires_at=now + timedelta(days=1),
        audit=AuthorityAudit(
            created_by="Codex PM",
            created_at=now,
            approved_by="fubai",
            approved_at=now,
            source_fingerprint=f"sha256:{'d' * 64}",
        ),
    )


def _flush_continuity_wal(root: Path) -> None:
    db_path = root / ".auto-pm" / "continuity.db"
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")


def _seed_authorized_mission(root: Path) -> None:
    _git_root(root)
    now = datetime.now(UTC)
    works = WorkRegistryService(root)
    works.initialize("test")
    works.create_work(
        work_id="WORK-COCKPIT-001",
        subject_project_id="SW-2026-008",
        kind=WorkKind.WBS,
        title="老板驾驶舱",
        owner="Codex fullstack-engineer",
        scope_paths=["auto_pm/core/pm_cockpit_service.py"],
        source_fingerprint="sha256:test",
        idempotency_key="create-work",
        read_only=True,
    )
    missions = MissionService(root)
    missions.initialize("test")
    missions.create(
        mission_id="MISSION-COCKPIT-001",
        subject_project_id="SW-2026-008",
        title="面向用户的老板驾驶舱",
        objective="只向用户展示可决策的信息。",
        acceptance_criteria=["默认入口无写入副作用。"],
        authority=_authority(now),
        created_by="Codex PM",
        idempotency_key="create-mission",
        root_work_id="WORK-COCKPIT-001",
    )
    mission = missions.get("MISSION-COCKPIT-001")
    missions.transition(
        mission_id=mission.mission_id,
        expected_version=mission.version,
        new_state=MissionState.AWAITING_APPROVAL,
        root_work_id=None,
        idempotency_key="await-approval",
    )
    execution = ContinuityExecutionService(root)
    git_head = _git(root, "rev-parse", "HEAD").stdout.strip()
    run = execution.start_run(
        run_id="RUN-COCKPIT-001",
        work_id="WORK-COCKPIT-001",
        executor_id="Codex fullstack-engineer",
        adapter="codex",
        owned_paths=["auto_pm/core/pm_cockpit_service.py"],
        declared_dirty_paths=[],
        observed_dirty_paths=[],
        git_head=git_head,
        worktree_path=str(root),
        lease_token="must-not-leak",
        lease_seconds=900,
        idempotency_key="start-run",
    )
    execution.checkpoint(
        checkpoint_id="CP-COCKPIT-001",
        run_id=run.run_id,
        owner_id="Codex fullstack-engineer",
        lease_token="must-not-leak",
        summary="已建立只读证据投影。",
        git_head=git_head,
        dirty_paths=[],
        evidence=["pytest: focused pass"],
        idempotency_key="checkpoint",
    )
    _flush_continuity_wal(root)


def test_missing_continuity_store_is_friendly_and_creates_nothing(tmp_path: Path) -> None:
    _registry(tmp_path)

    snapshot = PmCockpitService(tmp_path).snapshot()

    assert len(snapshot.projects) == 1
    assert snapshot.projects[0].project_id == "SW-2026-008"
    assert "未建立连续性记录" in snapshot.notices[0]
    assert not (tmp_path / ".auto-pm").exists()


def test_cockpit_reads_evidence_without_lease_or_write_side_effects(tmp_path: Path) -> None:
    _registry(tmp_path)
    _seed_authorized_mission(tmp_path)
    db_path = tmp_path / ".auto-pm" / "continuity.db"
    baseline = db_path.read_bytes()

    service = PmCockpitService(tmp_path)
    snapshot = service.snapshot()
    evidence = service.evidence("SW-2026-008")

    card = snapshot.projects[0]
    assert card.user_action is CockpitUserAction.CONFIRM_START
    assert card.next_user_action == "确认开始执行"
    assert card.current_owner == "Codex fullstack-engineer"
    assert evidence.decision_id == "DEC-20260910-1B4F38FD"
    assert evidence.checkpoints[0].checkpoint_id == "CP-COCKPIT-001"
    rendered = evidence.model_dump_json().lower()
    assert "must-not-leak" not in rendered
    assert "lease" not in rendered
    assert db_path.read_bytes() == baseline


def test_cockpit_snapshot_reads_linked_worktree_without_side_effects(tmp_path: Path) -> None:
    _registry(tmp_path)
    _seed_authorized_mission(tmp_path)
    _git(tmp_path, "add", ".")
    _git(
        tmp_path,
        "-c",
        "user.name=Cockpit Test",
        "-c",
        "user.email=cockpit@example.invalid",
        "commit",
        "-m",
        "cockpit snapshot",
    )
    linked = tmp_path.parent / f"{tmp_path.name}-cockpit-linked"
    _git(tmp_path, "worktree", "add", "--detach", str(linked), "HEAD")
    before = {
        path.relative_to(linked).as_posix(): path.read_bytes()
        for path in linked.rglob("*")
        if path.is_file() and path.name != ".git"
    }

    snapshot = PmCockpitService(linked).snapshot()

    after = {
        path.relative_to(linked).as_posix(): path.read_bytes()
        for path in linked.rglob("*")
        if path.is_file() and path.name != ".git"
    }
    assert snapshot.projects[0].project_id == "SW-2026-008"
    assert after == before
    assert not _git(linked, "status", "--porcelain").stdout.strip()


def test_primary_work_ignores_accepted_history(tmp_path: Path) -> None:
    _git_root(tmp_path)
    work = WorkRegistryService(tmp_path, now=lambda: "2026-09-09T12:00:00+00:00")
    work.initialize("test")
    work.create_work(
        work_id="WORK-ACCEPTED",
        subject_project_id="SW-2026-008",
        kind=WorkKind.GOVERNANCE,
        title="Accepted history",
        owner="Codex",
        scope_paths=["auto_pm/example.py"],
        source_fingerprint="sha256:test",
        idempotency_key="create-accepted",
        read_only=True,
    )
    work.transition("WORK-ACCEPTED", WorkState.IN_PROGRESS, "start-accepted")
    work.transition("WORK-ACCEPTED", WorkState.VERIFYING, "verify-accepted")
    accepted = work.transition("WORK-ACCEPTED", WorkState.ACCEPTED, "accept-accepted")

    assert PmCockpitService._primary_work(None, (accepted,)) is None
