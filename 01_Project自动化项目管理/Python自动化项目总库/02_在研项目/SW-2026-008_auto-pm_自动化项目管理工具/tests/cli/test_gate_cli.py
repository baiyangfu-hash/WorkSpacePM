"""D-107a: ``main.py gate`` command line."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from auto_pm.ui.cli.__main__ import cli


def _repo_top() -> Path:
    here = Path(__file__).resolve()
    return next(p for p in here.parents if (p / ".git").exists())


def test_plan_lists_all_eleven_groups_with_a_cwd_that_has_tests() -> None:
    result = CliRunner().invoke(cli, ["gate", "plan", "--worktree", str(_repo_top())])
    assert result.exit_code == 0, result.output
    plan = json.loads(result.output)
    assert len(plan) == 11 and all((Path(item["cwd"]) / "tests").is_dir() for item in plan)


def test_plan_rejects_an_unknown_group() -> None:
    result = CliRunner().invoke(
        cli, ["gate", "plan", "--worktree", str(_repo_top()), "--only", "nope"]
    )
    assert result.exit_code != 0 and "未知的组" in result.output


def test_judge_on_an_empty_folder_exits_two(tmp_path: Path) -> None:
    result = CliRunner().invoke(cli, ["gate", "judge", str(tmp_path)])
    assert result.exit_code == 2
