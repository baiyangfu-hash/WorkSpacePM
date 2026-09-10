"""CLI coverage for the user-facing PM Facade commands."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from auto_pm.cli.__main__ import cli
from auto_pm.core.mission_service import MissionService
from auto_pm.core.work_registry_service import WorkRegistryService
from click.testing import CliRunner

from auto_pm.contracts.continuity import WorkKind
from auto_pm.contracts.mission import AuthorityAudit, AuthorityEnvelope


def _setup(root: Path) -> None:
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
            "-w", str(tmp_path), "pm", "approve", "--mission-id", "MISSION-PM-CLI-001",
            "--root-work-id", "WORK-PM-CLI-001",
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


def test_pm_workflow_is_a_display_only_compatibility_alias(cli_runner: CliRunner, tmp_path: Path) -> None:
    result = cli_runner.invoke(cli, ["-w", str(tmp_path), "pm", "workflow"])

    assert result.exit_code == 0
    assert "pm-workflow 已退役隔离" in result.output
