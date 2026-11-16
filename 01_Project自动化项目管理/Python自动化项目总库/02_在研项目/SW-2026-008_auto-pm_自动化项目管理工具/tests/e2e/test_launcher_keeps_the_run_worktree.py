"""A2 false green (DJ-2026-005 trial, 2026-11-16): an approved ``main.py`` command must judge the Run's worktree.

``pm verify`` runs every approved command from the control root and hands it ``AUTO_PM_WORKSPACE`` = the Run's worktree
(project data) and ``AUTO_PM_CONTROL_ROOT`` = the control root (ledger), see ``acceptance_runner.worktree_environment``.
The stable launcher used to overwrite ``AUTO_PM_WORKSPACE`` with the control root, so ``main.py plc check <PID>`` checked
the untouched control root and passed while the worktree was broken.  This drill builds a real container from the current
source and the real stable launcher (the one in this repository), breaks the project only in a worktree, and runs
``plc check`` through the launcher exactly the way ``pm verify`` does.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from auto_pm.application.core.acceptance_runner import worktree_environment
from tests.e2e.test_release_pycache_drill import PROJECT, PROJECT_ID, _container
from tests.git_support import run_git

pytestmark = pytest.mark.external_reads  # D-200: copies the real stable launcher from 00_Infrastructure

BROKEN = "Bad.scl"
BROKEN_SOURCE = 'FUNCTION_BLOCK "FB_Bad"\nBEGIN\n  GOTO lbl;\nEND_FUNCTION_BLOCK\n'
_COCKPIT_ENV = ("AUTO_PM_WORKSPACE", "AUTO_PM_CONTROL_ROOT", "AUTO_PM_RUN_WORKTREE")


def _setup(tmp_path: Path) -> tuple[Path, Path, Path]:
    workspace, container = _container(tmp_path)
    worktree = workspace / ".auto-pm" / "worktrees" / "claude-a2drill"
    run_git(workspace, "worktree", "add", "-q", "--detach", str(worktree), "HEAD")
    (worktree / PROJECT / BROKEN).write_text(BROKEN_SOURCE, encoding="utf-8")
    return workspace, container, worktree


def _plc_check(container: Path, cwd: Path, extra: dict[str, str]) -> subprocess.CompletedProcess[str]:
    environment = {key: value for key, value in os.environ.items() if key not in {"PYTHONPATH", "PYTHONHOME", *_COCKPIT_ENV}}
    environment.update(extra)
    environment["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-B", str(container / "launcher" / "launch.py"), "plc", "check", PROJECT_ID],
        capture_output=True, text=True, encoding="utf-8", errors="replace", env=environment, cwd=str(cwd), timeout=300,
        check=False,
    )


def test_a2_an_acceptance_command_through_the_launcher_judges_the_run_worktree(tmp_path: Path) -> None:
    workspace, container, worktree = _setup(tmp_path)

    on_root = _plc_check(container, workspace, {})
    on_worktree = _plc_check(container, workspace, worktree_environment(worktree, workspace))

    assert "launcher: release verified via active_release.json" in on_root.stderr, on_root.stderr
    assert BROKEN not in on_root.stdout  # the control root is untouched
    assert on_worktree.returncode == 1, on_worktree.stdout + on_worktree.stderr
    assert f"{BROKEN}:3" in on_worktree.stdout and "GOTO" in on_worktree.stdout, on_worktree.stdout  # the worktree's file


@pytest.mark.parametrize(
    "extra",
    [
        pytest.param({"AUTO_PM_WORKSPACE": "elsewhere"}, id="another-folder-without-the-ledger"),
        pytest.param({"AUTO_PM_WORKSPACE": "elsewhere", "AUTO_PM_CONTROL_ROOT": "ws"}, id="another-folder-with-the-ledger"),
        pytest.param({"AUTO_PM_WORKSPACE": "worktree", "AUTO_PM_CONTROL_ROOT": "elsewhere"}, id="worktree-with-another-ledger"),
    ],
)
def test_a2_any_other_workspace_stops_the_launcher_instead_of_being_replaced(tmp_path: Path, extra: dict[str, str]) -> None:
    workspace, container, worktree = _setup(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    where = {"elsewhere": str(elsewhere), "ws": str(workspace), "worktree": str(worktree)}

    result = _plc_check(container, workspace, {key: where[value] for key, value in extra.items()})

    assert result.returncode == 5, result.stdout + result.stderr
    assert "launcher: 没有启动" in result.stderr and "AUTO_PM_WORKSPACE" in result.stderr
    assert "SCL 代码规范" not in result.stdout  # the release never ran


def test_a2_the_control_root_itself_named_as_the_workspace_still_runs(tmp_path: Path) -> None:
    workspace, container, _worktree = _setup(tmp_path)

    result = _plc_check(container, workspace, {"AUTO_PM_WORKSPACE": str(workspace)})

    assert result.returncode in (0, 1) and "SCL 代码规范" in result.stdout, result.stdout + result.stderr
    assert BROKEN not in result.stdout
