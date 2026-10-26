"""The shared Git fixture helpers report what Git said when a command fails."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.git_support import GitFixtureError, git_do, git_out, run_git


def test_a_failing_command_carries_the_exit_code_directory_and_git_stderr(tmp_path: Path) -> None:
    git_do(tmp_path, "init")

    with pytest.raises(GitFixtureError, match=r"worktree add .*退出码 128[\s\S]*fatal"):
        git_do(tmp_path, "worktree", "add", str(tmp_path / "wt"), "no-such-ref")


def test_git_out_returns_stripped_stdout_and_run_git_the_full_result(tmp_path: Path) -> None:
    git_do(tmp_path, "init", "-q")

    assert git_out(tmp_path, "rev-parse", "--is-inside-work-tree") == "true"
    assert run_git(tmp_path, "rev-parse", "--is-inside-work-tree").stdout == "true\n"


def test_config_options_precede_the_subcommand(tmp_path: Path) -> None:
    git_do(tmp_path, "init", "-q")

    assert git_out(tmp_path, "config", "user.name", config=["user.name=Fixture"]) == "Fixture"
