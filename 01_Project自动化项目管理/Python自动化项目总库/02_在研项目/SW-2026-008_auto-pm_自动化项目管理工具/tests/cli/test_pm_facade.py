"""CLI coverage for the user-facing PM Facade commands."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from auto_pm.cli.__main__ import cli
from auto_pm.core.mission_service import MissionService
from auto_pm.core.work_registry_service import WorkRegistryService
from click.testing import CliRunner

from auto_pm.contracts.continuity import WorkKind
from auto_pm.contracts.mission import AuthorityAudit, AuthorityEnvelope


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _repository(root: Path) -> None:
    _git(root, "init")
    (root / "README.md").write_text("baseline\n", encoding="utf-8", errors="replace")
    _git(root, "add", "README.md")
    _git(
        root,
        "-c",
        "user.name=PM Test",
        "-c",
        "user.email=pm@example.invalid",
        "commit",
        "-m",
        "baseline",
    )


def _setup(root: Path) -> None:
    _repository(root)
    now = datetime.now(UTC)
    authority = AuthorityEnvelope(
        envelope_id="AUTH-PM-CLI-001",
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
            source_fingerprint=f"sha256:{'c' * 64}",
        ),
    )
    works = WorkRegistryService(root)
    works.initialize("test")
    works.create_work(
        work_id="WORK-PM-CLI-001",
        subject_project_id="SW-TEST-001",
        kind=WorkKind.WBS,
        title="PM CLI work",
        owner="Codex",
        scope_paths=["pm.py"],
        source_fingerprint="sha256:test",
        idempotency_key="work-create",
        read_only=True,
    )
    missions = MissionService(root)
    missions.initialize("test")
    missions.create(
        mission_id="MISSION-PM-CLI-001",
        subject_project_id="SW-TEST-001",
        title="PM CLI",
        objective="Expose a friendly confirmation card.",
        acceptance_criteria=["A card is emitted."],
        authority=authority,
        created_by="Codex PM",
        idempotency_key="mission-create",
        root_work_id="WORK-PM-CLI-001",
    )


def test_pm_plan_and_approve_emit_confirmation_cards(cli_runner: CliRunner, tmp_path: Path) -> None:
    _setup(tmp_path)

    planned = cli_runner.invoke(
        cli, ["-w", str(tmp_path), "pm", "plan", "--mission-id", "MISSION-PM-CLI-001"]
    )
    assert planned.exit_code == 0
    assert json.loads(planned.output)["kind"] == "APPROVAL"

    approved = cli_runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "pm",
            "approve",
            "--mission-id",
            "MISSION-PM-CLI-001",
            "--root-work-id",
            "WORK-PM-CLI-001",
        ],
    )
    assert approved.exit_code == 0
    assert json.loads(approved.output)["mission_state"] == "ACTIVE"


def test_pm_confirm_start_hides_the_root_work_id(cli_runner: CliRunner, tmp_path: Path) -> None:
    _setup(tmp_path)
    planned = cli_runner.invoke(
        cli, ["-w", str(tmp_path), "pm", "plan", "--mission-id", "MISSION-PM-CLI-001"]
    )
    assert planned.exit_code == 0

    started = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "pm", "confirm-start", "--mission-id", "MISSION-PM-CLI-001"],
    )

    assert started.exit_code == 0
    assert json.loads(started.output)["mission_state"] == "ACTIVE"


def test_pm_workflow_is_a_display_only_compatibility_alias(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    result = cli_runner.invoke(cli, ["-w", str(tmp_path), "pm", "workflow"])

    assert result.exit_code == 0
    assert "pm-workflow 已退役隔离" in result.output


def test_pm_mutation_rejects_linked_worktree_before_runtime_initialization(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _setup(tmp_path)
    linked = tmp_path.parent / f"{tmp_path.name}-linked"
    _git(tmp_path, "worktree", "add", "--detach", str(linked), "HEAD")

    result = cli_runner.invoke(
        cli,
        ["-w", str(linked), "pm", "plan", "--mission-id", "MISSION-PM-CLI-001"],
    )

    assert result.exit_code == 1
    assert "linked worktree" in result.output
    assert not (linked / ".auto-pm").exists()

    display_only = cli_runner.invoke(cli, ["-w", str(linked), "pm", "workflow"])
    assert display_only.exit_code == 0
    assert not (linked / ".auto-pm").exists()
