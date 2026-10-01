"""Compatibility proofs for the old ``workflow`` entry: engine commands stay, PM actions delegate."""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import os
from pathlib import Path

import pytest
from auto_pm.cli import workflow as workflow_module
from auto_pm.cli.__main__ import cli
from auto_pm.cli.pm import pm_group
from auto_pm.cli.workflow import (
    list_workflows,
    run_workflow,
    workflow_group,
    workflow_history,
    workflow_status,
)
from click.testing import CliRunner

# Reuse the existing PM CLI fixtures; imported dynamically so that this file is type-checked on its own.
_pm_facade_tests = importlib.import_module("tests.cli.test_pm_facade")
_git = _pm_facade_tests._git
_planning_args = _pm_facade_tests._planning_args
_setup = _pm_facade_tests._setup
_setup_planning = _pm_facade_tests._setup_planning

_ENGINE = {"list", "run", "history", "status"}
_DELEGATED = ("plan", "approve", "confirm-start", "execute", "accept", "resume", "context")
_UNKNOWN_PREFIX = "旧 workflow 动作"
_MISSION = "MISSION-PM-CLI-001"


def _tree(root: Path) -> dict[str, str]:
    """Every file under ``root`` (relative path -> content hash)."""

    found: dict[str, str] = {}
    for current, _directories, files in os.walk(root):
        for name in files:
            path = Path(current) / name
            found[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def test_the_seven_old_pm_actions_are_the_very_same_command_objects_as_pm() -> None:
    assert set(workflow_group.commands) == _ENGINE | set(_DELEGATED)
    assert len(workflow_group.commands) == 11
    assert "workflow" not in workflow_group.commands
    for name in _DELEGATED:
        assert workflow_group.commands[name] is pm_group.commands[name]


def test_the_original_engine_commands_are_kept_unchanged() -> None:
    assert workflow_group.commands["list"].callback is list_workflows.callback
    assert workflow_group.commands["run"].callback is run_workflow.callback
    assert workflow_group.commands["history"].callback is workflow_history.callback
    assert workflow_group.commands["status"].callback is workflow_status.callback
    assert workflow_group.help == "工作流编排与执行管理"


def test_a_delegated_action_behaves_exactly_like_the_pm_command(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    via_pm, via_workflow = tmp_path / "via-pm", tmp_path / "via-workflow"
    for root in (via_pm, via_workflow):
        root.mkdir()
        _setup(root)
    sequence = [
        ["plan", "--mission-id", _MISSION],
        ["confirm-start", "--mission-id", _MISSION],
        ["accept", "--mission-id", _MISSION],
    ]

    for arguments in sequence:
        expected = cli_runner.invoke(cli, ["-w", str(via_pm), "pm", *arguments])
        actual = cli_runner.invoke(cli, ["-w", str(via_workflow), "workflow", *arguments])
        assert actual.exit_code == expected.exit_code, arguments
        assert actual.output == expected.output, arguments

    assert expected.exit_code == 1
    assert json.loads(cli_runner.invoke(
        cli, ["-w", str(via_workflow), "workflow", "confirm-start", "--mission-id", _MISSION]
    ).output)["mission_state"] == "ACTIVE"


def test_delegated_actions_keep_every_pm_guard(
    cli_runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    _setup(root)
    linked = tmp_path / "linked"
    _git(root, "worktree", "add", "--detach", str(linked), "HEAD")

    refused = cli_runner.invoke(cli, ["-w", str(linked), "workflow", "plan", "--mission-id", _MISSION])

    assert refused.exit_code == 1
    assert "linked worktree" in refused.output
    assert not (linked / ".auto-pm").exists()

    planning = tmp_path / "planning"
    planning.mkdir()
    _setup_planning(planning)
    planned = cli_runner.invoke(cli, ["-w", str(planning), "workflow", "plan", *_planning_args()])
    assert planned.exit_code == 0
    card = json.loads(planned.output)
    reached = False

    def tripwire(_ctx: object) -> object:
        nonlocal reached
        reached = True
        raise AssertionError("dispatch must not be reached")

    monkeypatch.setattr("auto_pm.cli.pm._facade", tripwire)
    mismatch = cli_runner.invoke(
        cli,
        [
            "-w",
            str(planning),
            "workflow",
            "execute",
            "--request-id",
            "REQ-OTHER",
            "--card-json",
            json.dumps(card),
            "--plan-hash",
            card["plan_hash"],
            "--lease-token-env",
            "U08_TOKEN",
        ],
        env={"U08_TOKEN": "u08-super-secret"},
    )
    assert mismatch.exit_code == 1
    assert "不一致" in mismatch.output
    assert "u08-super-secret" not in mismatch.output
    assert reached is False


@pytest.mark.parametrize("action", ["handoff", "close", "start", "workflow", "rollback", "zz-garbage"])
def test_an_unknown_old_action_is_refused_without_touching_anything(
    cli_runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    built: list[Path] = []
    real_engine = workflow_module.WorkflowEngine

    def counting_engine(workspace_root: Path) -> object:
        built.append(workspace_root)
        return real_engine(workspace_root)

    monkeypatch.setattr(workflow_module, "WorkflowEngine", counting_engine)
    before = _tree(tmp_path)

    result = cli_runner.invoke(cli, ["-w", str(tmp_path), "workflow", action])

    assert result.exit_code == 2
    assert _UNKNOWN_PREFIX in result.output
    assert f"{action!r}" in result.output
    assert "list/run/history/status" in result.output
    assert "plan/approve/confirm-start/execute/accept/resume/context" in result.output
    assert "Traceback" not in result.output
    assert built == []
    assert _tree(tmp_path) == before


def test_a_very_long_unknown_action_name_is_truncated_in_the_message(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    result = cli_runner.invoke(cli, ["-w", str(tmp_path), "workflow", "x" * 100])

    assert result.exit_code == 2
    assert "x" * 39 in result.output
    assert "x" * 41 not in result.output


def test_help_lists_all_commands_and_delegated_help_matches_pm(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    overview = cli_runner.invoke(cli, ["-w", str(tmp_path), "workflow", "--help"])

    assert overview.exit_code == 0
    for name in sorted(_ENGINE | set(_DELEGATED)):
        assert name in overview.output
    for name in _DELEGATED:
        via_pm = cli_runner.invoke(cli, ["-w", str(tmp_path), "pm", name, "--help"])
        via_workflow = cli_runner.invoke(cli, ["-w", str(tmp_path), "workflow", name, "--help"])
        assert via_workflow.exit_code == via_pm.exit_code == 0
        assert via_workflow.output.split("\n\n", 1)[1] == via_pm.output.split("\n\n", 1)[1], name


def test_the_module_does_not_revive_the_old_write_state_machine() -> None:
    source_path = Path(workflow_module.__file__)
    source = source_path.read_text(encoding="utf-8", errors="replace")
    imported: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
            imported.extend(f"{node.module}.{alias.name}" for alias in node.names)

    forbidden = ("ai_handoff_service", "pm_saga_service", "handoff")
    assert not [name for name in imported if any(token in name for token in forbidden)]
    assert "pm-workflow" not in source


def test_registration_and_the_pm_display_alias_are_unchanged(
    cli_runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert cli.commands["workflow"] is workflow_group
    monkeypatch.setattr("auto_pm.cli.workflow._resolve_workspace", lambda _ctx: tmp_path)

    listed = cli_runner.invoke(cli, ["-w", str(tmp_path), "workflow", "list"])
    alias = cli_runner.invoke(cli, ["-w", str(tmp_path), "pm", "workflow"])

    assert listed.exit_code == 0
    assert "file-modify" in listed.output
    assert alias.exit_code == 0
    assert "pm-workflow 已退役隔离" in alias.output
