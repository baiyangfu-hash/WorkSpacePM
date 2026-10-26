"""TD-SW008-040: ``plc check`` is judged by its exit code - 0 only when nothing failed, 1 whenever something did."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from auto_pm.cli.__main__ import cli
from click.testing import CliRunner, Result

from tests.plc.test_checker import full_project  # noqa: F401  (pytest fixture: every check passes)

PROJECT_ID = "DJ-2026-FULL"


def _check(runner: CliRunner, workspace: Path, *args: str) -> Result:
    return runner.invoke(cli, ["-w", str(workspace), "plc", "check", *args], catch_exceptions=False)


def _break(workspace: Path) -> None:
    """One missing mandatory document: the project now has exactly one failing item."""
    (workspace / "DJ-2026-FULL_完整项目" / "PRD" / "接口文档_INT.md").unlink()


def test_a_project_with_nothing_failing_exits_zero(cli_runner: CliRunner, full_project: Path) -> None:  # noqa: F811
    result = _check(cli_runner, full_project, PROJECT_ID)

    assert result.exit_code == 0, result.output
    assert "缺少 接口文档_INT.md" not in result.output


def test_a_project_with_a_failing_item_exits_one(cli_runner: CliRunner, full_project: Path) -> None:  # noqa: F811
    _break(full_project)

    result = _check(cli_runner, full_project, PROJECT_ID)

    assert result.exit_code == 1, result.output
    assert "缺少 接口文档_INT.md" in result.output


def test_json_output_does_not_hide_the_failure_from_the_exit_code(
    cli_runner: CliRunner, full_project: Path  # noqa: F811
) -> None:
    clean = _check(cli_runner, full_project, PROJECT_ID, "--json")
    assert clean.exit_code == 0 and json.loads(clean.output)["fail_count"] == 0

    _break(full_project)
    broken = _check(cli_runner, full_project, PROJECT_ID, "--json")

    assert broken.exit_code == 1
    assert json.loads(broken.output)["fail_count"] >= 1


def test_the_whole_workspace_exits_one_when_any_project_fails(
    cli_runner: CliRunner, full_project: Path  # noqa: F811
) -> None:
    clean = _check(cli_runner, full_project, "--all")
    assert clean.exit_code == 0, clean.output

    _break(full_project)

    assert _check(cli_runner, full_project, "--all").exit_code == 1


@pytest.mark.parametrize(
    ("flag", "reason"),
    [("--no-language-service", "缺少 接口文档_INT.md"), ("--substance", "文件不存在: 接口文档_INT.md")],
)
def test_the_other_check_modes_keep_the_same_exit_code_rule(
    cli_runner: CliRunner, full_project: Path, flag: str, reason: str  # noqa: F811
) -> None:
    _break(full_project)

    result = _check(cli_runner, full_project, PROJECT_ID, flag)

    assert result.exit_code == 1, result.output
    assert reason in result.output
