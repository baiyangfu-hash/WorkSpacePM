"""TD-SW008-113: change requests on disk must be visible as untracked or modified; the check never writes and never fails the caller."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from auto_pm.application.core.chg_tracking_service import check_project_chg_tracking

CHG = "CHG-SCPT-2026-001.md"


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(["git", "-C", str(root), *arguments], check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.name", "T")
    _git(tmp_path, "config", "user.email", "t@example.invalid")
    _git(tmp_path, "config", "core.autocrlf", "false")
    return tmp_path


def _write(project: Path, name: str, text: str = "v1\n", folder: str = "04_监控/01_变更管理/01_变更单/CHG-SCPT") -> str:
    path = project / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path.relative_to(project.parent).as_posix()


def _commit(root: Path) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "x")


def test_tracked_and_unchanged_change_requests_are_clean(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    project = root / "SW-1"
    _write(project, CHG)
    _commit(root)

    report = check_project_chg_tracking(project)

    assert report.clean and report.checked == 1


def test_a_change_request_that_is_in_no_commit_is_reported_as_untracked(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    project = root / "SW-1"
    _write(project, CHG)
    _commit(root)
    new = _write(project, "CHG-SCPT-2026-002.md")

    report = check_project_chg_tracking(project)

    assert report.untracked == (new,) and report.modified == () and not report.clean


def test_a_committed_change_request_edited_on_disk_is_reported_as_modified(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    project = root / "SW-1"
    name = _write(project, CHG)
    _commit(root)
    _write(project, CHG, "v2\n")

    report = check_project_chg_tracking(project)

    assert report.modified == (name,) and report.untracked == ()


def test_line_ending_differences_alone_are_not_a_modification(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    project = root / "SW-1"
    _write(project, CHG, "a\nb\n")
    _commit(root)
    _write(project, CHG, "a\r\nb\r\n")

    assert check_project_chg_tracking(project).clean


def test_other_projects_and_non_change_folders_are_not_this_projects_business(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    project = root / "SW-1"
    _write(project, CHG)
    _write(root / "SW-2", CHG)  # untracked, but another project
    _write(project, "CHG-SCPT-2026-009.md", folder="archive/old")  # outside a 01_变更单 folder
    _commit(root)
    _write(root / "SW-2", "CHG-SCPT-2026-003.md")

    assert check_project_chg_tracking(project).clean


def test_a_folder_that_is_not_a_repository_is_skipped_with_a_reason_not_an_error(tmp_path: Path) -> None:
    project = tmp_path / "plain"
    _write(project, CHG)

    report = check_project_chg_tracking(project)

    assert report.skipped_reason and not report.clean and report.checked == 0


def test_a_repository_without_commits_is_skipped_with_a_reason(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    project = root / "SW-1"
    _write(project, CHG)

    assert check_project_chg_tracking(project).skipped_reason


def test_the_check_is_read_only(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    project = root / "SW-1"
    _write(project, CHG)
    _commit(root)
    _write(project, "CHG-SCPT-2026-002.md")
    before = subprocess.run(["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True, check=True).stdout

    check_project_chg_tracking(project)

    after = subprocess.run(["git", "-C", str(root), "status", "--porcelain"], capture_output=True, text=True, check=True).stdout
    assert after == before and "??" in after


def test_reconcile_prints_the_warning_but_keeps_its_exit_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.domain.change.ledger_reconciler import ReconcileDiff
    from auto_pm.ui.cli import ledger

    root = _repo(tmp_path)
    project = root / "SW-1"
    _write(project, CHG)
    _commit(root)
    new = _write(project, "CHG-SCPT-2026-002.md")

    class FakeProjects:
        def __init__(self, _root: Path) -> None: ...

        def find_project_path(self, _pid: str) -> str:
            return str(project)

    class FakeReconciler:
        def reconcile(self, _path: str) -> ReconcileDiff:
            return ReconcileDiff()

    monkeypatch.setattr(ledger, "ProjectService", FakeProjects)
    monkeypatch.setattr(ledger, "LedgerReconciler", FakeReconciler)

    result = CliRunner().invoke(ledger.ledger_group, ["reconcile", "SW-1"], obj=SimpleNamespace(workspace_root=root))

    assert result.exit_code == 0, result.output
    assert "提交跟踪警告" in result.output and new in result.output
