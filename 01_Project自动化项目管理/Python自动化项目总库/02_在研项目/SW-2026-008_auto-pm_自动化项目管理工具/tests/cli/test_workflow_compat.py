"""Compatibility proofs for the old ``workflow`` entry: engine commands stay; the 7 old PM aliases are retired (退役批一) and refused."""

from __future__ import annotations

import ast
import hashlib
import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.domain.constraint.workflow import WorkflowEngine
from auto_pm.ui.cli import workflow as workflow_module
from auto_pm.ui.cli.__main__ import cli
from auto_pm.ui.cli.workflow import (
    list_workflows,
    run_workflow,
    workflow_group,
    workflow_history,
    workflow_status,
)

pytestmark = pytest.mark.usefixtures("identity_guard_off")

_ENGINE = {"list", "run", "history", "status"}
_RETIRED = ("plan", "approve", "confirm-start", "execute", "accept", "resume", "context")
_UNKNOWN_PREFIX = "旧 workflow 动作"


def _tree(root: Path) -> dict[str, str]:
    """Every file under ``root`` (relative path -> content hash)."""

    found: dict[str, str] = {}
    for current, _directories, files in os.walk(root):
        for name in files:
            path = Path(current) / name
            found[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def test_only_the_engine_commands_are_left() -> None:
    assert set(workflow_group.commands) == _ENGINE
    assert len(workflow_group.commands) == 4
    assert "workflow" not in workflow_group.commands
    for name in _RETIRED:
        assert name not in workflow_group.commands


def test_the_original_engine_commands_are_kept_unchanged() -> None:
    assert workflow_group.commands["list"].callback is list_workflows.callback
    assert workflow_group.commands["run"].callback is run_workflow.callback
    assert workflow_group.commands["history"].callback is workflow_history.callback
    assert workflow_group.commands["status"].callback is workflow_status.callback
    assert workflow_group.help == "工作流编排与执行管理"


@pytest.mark.parametrize(
    "action", ["handoff", "close", "start", "workflow", "rollback", "zz-garbage", *_RETIRED]
)
def test_an_unknown_old_action_is_refused_without_touching_anything(
    cli_runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, action: str
) -> None:
    built: list[Path] = []
    real_engine = WorkflowEngine

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
    assert "改用 pm 同名命令" in result.output
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


def test_help_lists_the_engine_commands_and_an_old_alias_help_is_refused(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    overview = cli_runner.invoke(cli, ["-w", str(tmp_path), "workflow", "--help"])

    assert overview.exit_code == 0
    for name in sorted(_ENGINE):
        assert name in overview.output
    for name in _RETIRED:
        refused = cli_runner.invoke(cli, ["-w", str(tmp_path), "workflow", name, "--help"])
        assert refused.exit_code == 2, name
        assert _UNKNOWN_PREFIX in refused.output, name


def test_the_module_does_not_revive_the_old_write_state_machine() -> None:
    source_path = Path(workflow_module.__file__)
    source = source_path.read_bytes()
    imported: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
            imported.extend(f"{node.module}.{alias.name}" for alias in node.names)

    forbidden = ("ai_handoff_service", "pm_saga_service", "handoff")
    assert not [name for name in imported if any(token in name for token in forbidden)]
    assert b"pm-workflow" not in source


def test_registration_and_the_pm_display_alias_are_unchanged(
    cli_runner: CliRunner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert cli.commands["workflow"] is workflow_group
    monkeypatch.setattr("auto_pm.ui.cli.workflow._resolve_workspace", lambda _ctx: tmp_path)

    listed = cli_runner.invoke(cli, ["-w", str(tmp_path), "workflow", "list"])
    alias = cli_runner.invoke(cli, ["-w", str(tmp_path), "pm", "workflow"])

    assert listed.exit_code == 0
    assert "file-modify" in listed.output
    assert alias.exit_code == 0
    assert "pm-workflow 已退役隔离" in alias.output
