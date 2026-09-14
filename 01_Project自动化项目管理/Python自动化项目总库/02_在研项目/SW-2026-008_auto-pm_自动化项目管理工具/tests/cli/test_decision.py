"""CLI safety coverage for immutable, typed Decision capabilities."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from auto_pm.cli.__main__ import cli
from click.testing import CliRunner

from auto_pm.domain.change.decision_service import DecisionService, DecisionValidationError


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _approved_repository(root: Path) -> None:
    project = root / "SW-2026-008_auto-pm"
    chg_dir = project / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-SCPT"
    chg_dir.mkdir(parents=True)
    (chg_dir / "CHG-SCPT-2026-214.md").write_text(
        """# CHG-SCPT-2026-214
## 3. 变更基本信息
### 3.0 编号与项目
| 变更编号 | CHG-SCPT-2026-214 |
| 项目编号 | SW-2026-008 |
### 3.3 影响范围
| 影响范围 | MODULE |
### 3.4 申请信息
| 变更状态 | approved |
""",
        encoding="utf-8",
        errors="replace",
    )
    registry = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [
                    {
                        "project_id": "SW-2026-008",
                        "project_root": "SW-2026-008_auto-pm",
                        "development_root": "SW-2026-008_auto-pm",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    _git(root, "init")
    _git(root, "add", ".")
    _git(
        root,
        "-c",
        "user.name=Decision Test",
        "-c",
        "user.email=decision@example.invalid",
        "commit",
        "-m",
        "baseline",
    )


def _create_args() -> list[str]:
    return [
        "decision",
        "create",
        "--change-id",
        "CHG-SCPT-2026-214",
        "--approver",
        "fubai",
        "--pid",
        "SW-2026-008",
        "--file",
        "auto_pm/core/a.py",
        "--decision-id",
        "DEC-20260911-5C37A985",
        "--allow-runtime-action",
        "settle_expired_run",
        "--target-run-id",
        "RUN-SW008-A2-OLD",
        "--allow-outcome",
        "CANCELLED",
        "--json-output",
    ]


def test_decision_cli_creates_typed_capability_and_rejects_overwrite(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _approved_repository(tmp_path)

    created = cli_runner.invoke(cli, ["-w", str(tmp_path), *_create_args()])

    assert created.exit_code == 0
    payload = json.loads(created.output)
    assert payload["decision_id"] == "DEC-20260911-5C37A985"
    assert payload["metadata"]["runtime_capability"] == {
        "allowed_runtime_actions": ["settle_expired_run"],
        "target_run_ids": ["RUN-SW008-A2-OLD"],
        "allowed_outcomes": ["CANCELLED"],
    }
    decision_path = tmp_path / ".auto-pm" / "decisions" / "DEC-20260911-5C37A985.json"
    original = decision_path.read_bytes()

    duplicate = cli_runner.invoke(cli, ["-w", str(tmp_path), *_create_args()])

    assert duplicate.exit_code == 1
    assert "拒绝覆盖" in duplicate.output
    assert decision_path.read_bytes() == original


def test_decision_cli_capability_is_all_or_none(cli_runner: CliRunner, tmp_path: Path) -> None:
    _approved_repository(tmp_path)

    result = cli_runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "decision",
            "create",
            "--change-id",
            "CHG-SCPT-2026-214",
            "--approver",
            "fubai",
            "--pid",
            "SW-2026-008",
            "--decision-id",
            "DEC-20260911-5C37A985",
            "--allow-runtime-action",
            "settle_expired_run",
        ],
    )

    assert result.exit_code == 1
    assert "必须同时提供" in result.output


def test_planning_decision_requires_external_human_evidence(tmp_path: Path) -> None:
    _approved_repository(tmp_path)
    service = DecisionService(tmp_path)

    with pytest.raises(DecisionValidationError, match="user-confirmation"):
        service.create_decision(
            "CHG-SCPT-2026-214",
            "fubai",
            project_id="SW-2026-008",
            approved_files=["auto_pm/core/a.py"],
            decision_id="DEC-20260914-A1B2C3D4",
            planning_plan_hash="a" * 64,
            approval_evidence_ref="model-confirmation:P07-TEST-001",
        )
    with pytest.raises(DecisionValidationError, match="模型或 Agent 自签"):
        service.create_decision(
            "CHG-SCPT-2026-214",
            "codex-gpt-5",
            project_id="SW-2026-008",
            approved_files=["auto_pm/core/a.py"],
            decision_id="DEC-20260914-A1B2C3D4",
            planning_plan_hash="a" * 64,
            approval_evidence_ref="user-confirmation:P07-TEST-001",
        )

    decision = service.create_decision(
        "CHG-SCPT-2026-214",
        "fubai",
        project_id="SW-2026-008",
        approved_files=["auto_pm/core/a.py"],
        decision_id="DEC-20260914-A1B2C3D4",
        planning_plan_hash="a" * 64,
        approval_evidence_ref="user-confirmation:P07-TEST-001",
    )

    assert decision.metadata["planning_approval"] == {
        "schema_version": "planning-approval.v1",
        "plan_hash": "a" * 64,
        "approval_evidence_ref": "user-confirmation:P07-TEST-001",
    }


def test_decision_cli_rejects_linked_worktree_before_runtime_directory_creation(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    _approved_repository(tmp_path)
    linked = tmp_path.parent / f"{tmp_path.name}-linked"
    _git(tmp_path, "worktree", "add", "--detach", str(linked), "HEAD")

    result = cli_runner.invoke(cli, ["-w", str(linked), *_create_args()])

    assert result.exit_code == 1
    assert "linked worktree" in result.output
    assert not (linked / ".auto-pm").exists()


def test_decision_show_and_list_are_zero_write(cli_runner: CliRunner, tmp_path: Path) -> None:
    listed = cli_runner.invoke(cli, ["-w", str(tmp_path), "decision", "list"])
    shown = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "decision", "show", "DEC-20260911-5C37A985"],
    )

    assert listed.exit_code == 0
    assert shown.exit_code == 1
    assert not (tmp_path / ".auto-pm").exists()


def test_decision_list_reports_corrupt_canonical_file_as_controlled_error(
    cli_runner: CliRunner,
    tmp_path: Path,
) -> None:
    decision_dir = tmp_path / ".auto-pm" / "decisions"
    decision_dir.mkdir(parents=True)
    corrupt = decision_dir / "DEC-20260911-5C37A985.json"
    corrupt.write_text("{not-json", encoding="utf-8", errors="replace")
    original = corrupt.read_bytes()

    listed = cli_runner.invoke(cli, ["-w", str(tmp_path), "decision", "list"])

    assert listed.exit_code == 1
    assert "无效文件" in listed.output
    assert corrupt.read_bytes() == original
