"""doctor: before a release at most MAX_STATIONS - 1 directories may be left under .auto-pm/worktrees (H-04b).

The limit is 8 for ``worktree open``; a release needs one place of its own, so the pre-release check allows 7.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.application.core.agent_worktree_service import MAX_STATIONS, RELEASE_FREE_PLACES
from auto_pm.ui.cli.doctor import check_worktree_floor, doctor_command, run_doctor_check

LIMIT = MAX_STATIONS - RELEASE_FREE_PLACES


def _dirs(root: Path, count: int, *, files: int = 0) -> None:
    folder = root / ".auto-pm" / "worktrees"
    folder.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        (folder / f"m3-left-{index}").mkdir(exist_ok=True)
    for index in range(files):
        (folder / f"note-{index}.txt").write_text("not a work tree\n", encoding="utf-8")


def test_the_limit_is_seven() -> None:
    assert LIMIT == 7


def test_a_root_without_the_folder_is_info_not_a_failure(tmp_path: Path) -> None:
    result = check_worktree_floor(str(tmp_path))
    assert result["status"] == "info" and result["count"] == 0 and result["reasons"] == []


def test_seven_directories_pass_and_eight_fail(tmp_path: Path) -> None:
    _dirs(tmp_path, LIMIT)
    assert check_worktree_floor(str(tmp_path))["status"] == "ok"

    _dirs(tmp_path, LIMIT + 1)  # one more directory (m3-left-7)
    failed = check_worktree_floor(str(tmp_path))
    assert failed["status"] == "fail" and failed["count"] == LIMIT + 1
    assert "最多 7 个" in "".join(failed["reasons"])
    assert "m3-left-7" in failed["names"]


def test_plain_files_do_not_count(tmp_path: Path) -> None:
    _dirs(tmp_path, LIMIT, files=5)
    assert check_worktree_floor(str(tmp_path))["status"] == "ok"


def test_the_laptop_state_of_11_01_fails_and_the_planned_cleanup_passes(tmp_path: Path) -> None:
    _dirs(tmp_path, 25)
    assert check_worktree_floor(str(tmp_path))["status"] == "fail"
    folder = tmp_path / ".auto-pm" / "worktrees"
    for index in range(25 - 6):  # 19 removed, 6 stay
        (folder / f"m3-left-{index}").rmdir()
    assert check_worktree_floor(str(tmp_path))["status"] == "ok"


def test_doctor_reports_the_floor_and_fails_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "auto_pm.ui.cli.doctor.check_release_consistency",
        lambda root: {"status": "info", "failures": [], "warnings": []},
    )
    monkeypatch.setattr(
        "auto_pm.ui.cli.doctor.check_release_pointers",
        lambda root: {"status": "info", "reasons": [], "ref": ""},
    )
    _dirs(tmp_path, LIMIT + 1)

    assert run_doctor_check(str(tmp_path))["all_passed"] is False

    result = CliRunner().invoke(doctor_command, ["-w", str(tmp_path)])
    assert result.exit_code == 1, result.output
    assert "工位目录数" in result.output and "FAIL" in result.output
