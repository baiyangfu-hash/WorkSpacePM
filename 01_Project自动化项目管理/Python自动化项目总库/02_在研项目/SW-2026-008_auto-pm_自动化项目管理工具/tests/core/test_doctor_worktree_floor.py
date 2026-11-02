"""doctor: before a release at most MAX_STATIONS - 1 directories may be left under .auto-pm/worktrees (H-04b).

The limit is 8 for ``worktree open``; a release needs one place of its own, so the pre-release check allows 7.
Everyday ``doctor`` only warns; ``doctor --pre-release`` fails.  The count is the one ``worktree open`` uses.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from auto_pm.application.core.agent_worktree_service import (
    MAX_STATIONS,
    RELEASE_FREE_PLACES,
    AgentWorktreeService,
)
from auto_pm.ui.cli.doctor import check_worktree_floor, doctor_command, run_doctor_check

LIMIT = MAX_STATIONS - RELEASE_FREE_PLACES


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=ci",
            "-c",
            "user.email=ci@example.invalid",
            *args,
        ],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """A control root: a real Git repository with one commit."""

    _git(tmp_path, "init", "-q")
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def _dirs(root: Path, count: int, *, files: int = 0) -> None:
    """Plain directories nobody registered: the m3-* leftovers."""

    folder = root / ".auto-pm" / "worktrees"
    folder.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        (folder / f"m3-left-{index}").mkdir(exist_ok=True)
    for index in range(files):
        (folder / f"note-{index}.txt").write_text("not a work tree\n", encoding="utf-8")


def _healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Everything else doctor looks at passes, so ``all_passed`` can only be moved by the worktree floor.

    In a bare sandbox ``all_passed`` is False for unrelated reasons (missing packages, stray files), which would make
    "the floor does not fail the run" and "the floor fails the run" look the same.
    """

    monkeypatch.setattr("auto_pm.ui.cli.doctor.importlib.util.find_spec", lambda name: object())
    monkeypatch.setattr(
        "auto_pm.ui.cli.doctor.GovernanceService",
        lambda **kwargs: SimpleNamespace(
            inspect_sanitation=lambda: SimpleNamespace(is_pure=True, total_issues=0)
        ),
    )
    monkeypatch.setattr(
        "auto_pm.ui.cli.doctor.check_release_pointers",
        lambda root: {"status": "info", "reasons": [], "ref": ""},
    )
    monkeypatch.setattr(
        "auto_pm.ui.cli.doctor.check_release_consistency",
        lambda root: {"status": "info", "failures": [], "warnings": []},
    )


def test_the_limit_is_seven() -> None:
    assert LIMIT == 7


def test_a_root_without_the_folder_passes_with_zero(root: Path) -> None:
    result = check_worktree_floor(str(root), pre_release=True)
    assert result["status"] == "ok" and result["count"] == 0


def test_a_directory_that_is_not_a_control_root_is_info_never_a_failure(tmp_path: Path) -> None:
    _dirs(tmp_path, LIMIT + 3)  # not a Git repository at all

    result = check_worktree_floor(str(tmp_path), pre_release=True)

    assert result["status"] == "info" and result["reasons"]


def test_seven_directories_pass_and_eight_warn_by_default_but_fail_before_a_release(
    root: Path,
) -> None:
    _dirs(root, LIMIT)
    assert check_worktree_floor(str(root), pre_release=True)["status"] == "ok"

    _dirs(root, LIMIT + 1)
    warned = check_worktree_floor(str(root))
    failed = check_worktree_floor(str(root), pre_release=True)
    assert warned["status"] == "warn" and failed["status"] == "fail"
    assert failed["count"] == LIMIT + 1 and "最多 7 个" in "".join(failed["reasons"])


def test_plain_files_do_not_count(root: Path) -> None:
    _dirs(root, LIMIT, files=5)
    assert check_worktree_floor(str(root), pre_release=True)["status"] == "ok"


def test_the_count_is_the_one_worktree_open_refuses_on(root: Path) -> None:
    """A registered station and the unregistered leftovers are all counted, a station only once."""

    _git(
        root,
        "worktree",
        "add",
        "-q",
        "-b",
        "claude/CARD-1",
        str(root / ".auto-pm" / "worktrees" / "claude"),
    )
    _dirs(root, LIMIT - 1)  # 1 registered + 6 leftovers = 7
    service = AgentWorktreeService(root, measure_size=False)

    assert check_worktree_floor(str(root))["count"] == service.count() == LIMIT
    assert check_worktree_floor(str(root), pre_release=True)["status"] == "ok"

    _dirs(root, LIMIT)  # one more leftover -> 8
    assert check_worktree_floor(str(root))["count"] == service.count() == MAX_STATIONS
    assert check_worktree_floor(str(root), pre_release=True)["status"] == "fail"


def test_the_laptop_state_of_11_01_fails_and_the_planned_cleanup_passes(root: Path) -> None:
    _dirs(root, 25)
    assert check_worktree_floor(str(root), pre_release=True)["status"] == "fail"
    folder = root / ".auto-pm" / "worktrees"
    for index in range(25 - 6):  # 19 removed, 6 stay
        (folder / f"m3-left-{index}").rmdir()
    assert check_worktree_floor(str(root), pre_release=True)["status"] == "ok"


def test_only_the_pre_release_run_moves_all_passed(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _healthy(monkeypatch)
    assert run_doctor_check(str(root))["all_passed"] is True, (
        "对照：其余都健康时 all_passed 必须是 True"
    )

    _dirs(root, LIMIT + 1)

    assert run_doctor_check(str(root))["all_passed"] is True, "日常体检只提示，不能因为工位多而变红"
    assert run_doctor_check(str(root), pre_release=True)["all_passed"] is False


def test_the_doctor_command_warns_everyday_and_exits_1_before_a_release(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _healthy(monkeypatch)
    _dirs(root, LIMIT + 1)

    everyday = CliRunner().invoke(doctor_command, ["-w", str(root)])
    assert everyday.exit_code == 0, everyday.output
    assert (
        "工位目录数" in everyday.output
        and "FAIL" not in everyday.output
        and "--pre-release" in everyday.output
    )

    before_release = CliRunner().invoke(doctor_command, ["-w", str(root), "--pre-release"])
    assert before_release.exit_code == 1, before_release.output
    assert "工位目录数" in before_release.output and "FAIL" in before_release.output
