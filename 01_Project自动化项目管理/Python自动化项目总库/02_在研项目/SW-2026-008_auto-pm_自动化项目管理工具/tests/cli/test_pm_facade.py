"""CLI coverage for the user-facing PM Facade commands."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from auto_pm.cli.__main__ import cli
from auto_pm.core.mission_service import MissionService
from auto_pm.core.work_registry_service import WorkRegistryService
from click.testing import CliRunner

from auto_pm.contracts.continuity import WorkKind
from auto_pm.contracts.mission import AuthorityAudit, AuthorityEnvelope
from auto_pm.infrastructure.continuity_store import ContinuityStore


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


def _setup_planning(root: Path) -> None:
    _repository(root)
    project_root = root / "SW-TEST-001"
    project_root.mkdir()
    registry = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [
                    {
                        "project_id": "SW-TEST-001",
                        "project_root": "SW-TEST-001",
                        "development_root": "SW-TEST-001",
                    }
                ],
            }
        ),
        encoding="utf-8",
        errors="replace",
    )
    specs = root / "00_Obsidian_Base全局规范文件仓库"
    (specs / "python.md").parent.mkdir(parents=True)
    (specs / "python.md").write_text("python spec\n", encoding="utf-8", errors="replace")
    (specs / "plc.md").write_text("plc spec\n", encoding="utf-8", errors="replace")
    (specs / "spec_registry.json").write_text(
        json.dumps(
            {
                "specs": {
                    "DEV-TEST": {
                        "domain": "python",
                        "lifecycle": "stable",
                        "canonical_path": "00_Obsidian_Base全局规范文件仓库/python.md",
                        "version": "V1",
                    },
                    "LSP-TEST": {
                        "domain": "plc",
                        "lifecycle": "active",
                        "canonical_path": "00_Obsidian_Base全局规范文件仓库/plc.md",
                        "version": "V1",
                    },
                }
            }
        ),
        encoding="utf-8",
        errors="replace",
    )
    ContinuityStore(root).initialize("2026-09-14T00:00:00+00:00", "test")


def _planning_args() -> list[str]:
    return [
        "--project-id",
        "SW-TEST-001",
        "--request-id",
        "REQ-P11-001",
        "--objective",
        "Expose a user-facing planning entry.",
        "--acceptance",
        "A deterministic scope card is returned.",
        "--scope",
        "auto_pm/example.py",
        "--risk",
        "scope drift",
        "--non-goal",
        "no execution before approval",
        "--adapter",
        "codex",
        "--approved-model",
        "gpt-approved",
        "--declared-dirty",
        "auto_pm/example.py",
    ]


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


def test_pm_plan_creates_and_replays_scope_card_without_internal_ids(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _setup_planning(tmp_path)

    planned = cli_runner.invoke(cli, ["-w", str(tmp_path), "pm", "plan", *_planning_args()])
    replayed = cli_runner.invoke(cli, ["-w", str(tmp_path), "pm", "plan", *_planning_args()])

    assert planned.exit_code == 0
    assert replayed.exit_code == 0, replayed.output
    payload = json.loads(planned.output)
    assert json.loads(replayed.output) == payload
    assert payload["schema_version"] == "planning-scope-card.v1"
    assert payload["request_id"] == "REQ-P11-001"
    assert payload["executable"] is False
    assert not {"mission_id", "decision_id", "work_id"}.intersection(payload)
    store = ContinuityStore(tmp_path)
    assert store.list_missions("SW-TEST-001", include_terminal=True) == ()
    assert store.list_works("SW-TEST-001", include_terminal=True) == ()


def test_pm_approve_materializes_one_authorized_chain_without_internal_ids(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _setup_planning(tmp_path)
    planned = cli_runner.invoke(cli, ["-w", str(tmp_path), "pm", "plan", *_planning_args()])
    plan_hash = json.loads(planned.output)["plan_hash"]
    approve_args = [
        "-w",
        str(tmp_path),
        "pm",
        "approve",
        *_planning_args(),
        "--plan-hash",
        plan_hash,
        "--approver",
        "fubai",
        "--approval-evidence-ref",
        "user-confirmation:P11-TEST-001",
    ]

    approved = cli_runner.invoke(cli, approve_args)
    replayed = cli_runner.invoke(cli, approve_args)

    assert approved.exit_code == 0
    assert replayed.exit_code == 0, replayed.output
    payload = json.loads(approved.output)
    assert json.loads(replayed.output) == payload
    assert payload["authorization_status"] == "AUTHORIZED"
    assert payload["work_state"] == "READY"
    assert not {"mission_id", "decision_id", "work_id"}.intersection(payload)
    store = ContinuityStore(tmp_path)
    assert len(store.list_missions("SW-TEST-001", include_terminal=True)) == 1
    assert len(store.list_works("SW-TEST-001", include_terminal=True)) == 1


def test_pm_execute_consumes_env_secret_and_emits_foreground_receipt(
    cli_runner: CliRunner,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _setup_planning(tmp_path)
    planned = cli_runner.invoke(cli, ["-w", str(tmp_path), "pm", "plan", *_planning_args()])
    card_payload = json.loads(planned.output)
    captured: dict[str, object] = {}

    class _Receipt:
        status = "VERIFYING"

        @staticmethod
        def model_dump(*, mode: str) -> dict[str, object]:
            assert mode == "json"
            return {"status": "VERIFYING", "run_id": "RUN-PLAN-TEST"}

    class _Facade:
        @staticmethod
        def execute_planning_foreground(
            card,
            *,
            expected_plan_hash: str,
            lease_token: str,
            lease_token_environment: str,
        ):
            captured.update(
                card=card,
                expected_plan_hash=expected_plan_hash,
                lease_token=lease_token,
                lease_token_environment=lease_token_environment,
                env_present="E08A_TOKEN" in os.environ,
            )
            return _Receipt()

    monkeypatch.setattr("auto_pm.cli.pm._facade", lambda _ctx: _Facade())
    result = cli_runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "pm",
            "execute",
            "--request-id",
            card_payload["request_id"],
            "--card-json",
            json.dumps(card_payload),
            "--plan-hash",
            card_payload["plan_hash"],
            "--lease-token-env",
            "E08A_TOKEN",
        ],
        env={"E08A_TOKEN": "cli-super-secret"},
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == "pm-foreground-execution.v1"
    assert payload["status"] == "VERIFYING"
    assert payload["run_state"] == "VERIFYING"
    assert captured["lease_token"] == "cli-super-secret"
    assert captured["lease_token_environment"] == "E08A_TOKEN"
    assert captured["env_present"] is False
    assert "cli-super-secret" not in result.output
    assert "cli-super-secret" not in repr(result.exception)


def test_pm_execute_rejects_mismatched_request_before_dispatch(
    cli_runner: CliRunner,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _setup_planning(tmp_path)
    planned = cli_runner.invoke(cli, ["-w", str(tmp_path), "pm", "plan", *_planning_args()])
    card_payload = json.loads(planned.output)
    called = False

    def fail_if_called(_ctx):
        nonlocal called
        called = True
        raise AssertionError("dispatch must not be reached")

    monkeypatch.setattr("auto_pm.cli.pm._facade", fail_if_called)
    result = cli_runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "pm",
            "execute",
            "--request-id",
            "REQ-OTHER",
            "--card-json",
            json.dumps(card_payload),
            "--plan-hash",
            card_payload["plan_hash"],
            "--lease-token-env",
            "E08A_TOKEN",
        ],
        env={"E08A_TOKEN": "cli-super-secret"},
    )
    assert result.exit_code == 1
    assert "不一致" in result.output
    assert "cli-super-secret" not in result.output
    assert called is False


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
