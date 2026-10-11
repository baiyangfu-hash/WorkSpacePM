"""The change-request tracking check (M2-GOV-TRK, TD-SW008-113): proofs that a change request which exists only on disk is found, that a tracked one is accepted, and that the
check never changes the repository.

`ledger reconcile` compares "the file is on disk" with "the ledger has a row" and says nothing about Git. ``tests/tools/chg_tracking_check.py`` asks the missing question. Every test builds a
real throw-away repository with real commits, runs the tool as a command, and asserts the exit code and the named files.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tests.tools import chg_tracking_check as tool

TOOL = Path(tool.__file__).resolve()
FOLDER = "proj/04_监控/01_变更管理/01_变更单/CHG-SCPT"
BODY = "# change request\n\n| 变更状态 | implementing |\n"


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    return done.stdout


def _write(repo: Path, rel: str, text: str = BODY, newline: str = "\n") -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))


def _run(repo: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-B", str(TOOL), "--repo", str(repo), *extra], capture_output=True, text=True, encoding="utf-8")


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.invalid")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "core.autocrlf", "false")
    _write(root, f"{FOLDER}/CHG-SCPT-2026-001.md")
    _write(root, f"{FOLDER}/CHG-SCPT-2026-002.md")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "baseline")
    return root


def test_a_repository_whose_change_requests_are_all_committed_is_clean(repo: Path) -> None:
    done = _run(repo, "--json")
    assert done.returncode == 0, done.stdout + done.stderr
    report = json.loads(done.stdout)
    assert report["checked"] == 2 and report["untracked"] == [] and report["modified"] == [] and report["clean"] is True


def test_a_change_request_that_is_only_on_disk_is_reported_as_untracked(repo: Path) -> None:
    rel = f"{FOLDER}/CHG-SCPT-2026-003.md"
    _write(repo, rel)
    before = _git(repo, "status", "--porcelain", "--untracked-files=all")
    done = _run(repo, "--json")
    assert done.returncode == 2
    report = json.loads(done.stdout)
    assert report["untracked"] == [rel] and report["modified"] == [] and report["checked"] == 3
    assert _git(repo, "status", "--porcelain", "--untracked-files=all") == before, "the check must not change the repository"


def test_a_committed_change_request_whose_content_changed_is_reported_as_modified(repo: Path) -> None:
    rel = f"{FOLDER}/CHG-SCPT-2026-001.md"
    _write(repo, rel, BODY.replace("implementing", "completed"))
    done = _run(repo, "--json")
    assert done.returncode == 2
    report = json.loads(done.stdout)
    assert report["modified"] == [rel] and report["untracked"] == []


def test_a_difference_in_line_endings_alone_is_not_a_modification(repo: Path) -> None:
    rel = f"{FOLDER}/CHG-SCPT-2026-001.md"
    _write(repo, rel, newline="\r\n")
    done = _run(repo, "--json")
    assert done.returncode == 0, done.stdout
    assert json.loads(done.stdout)["modified"] == []


def test_a_file_that_is_not_a_change_request_is_not_checked(repo: Path) -> None:
    _write(repo, f"{FOLDER}/notes.md")
    _write(repo, f"{FOLDER}/CHG-SCPT-2026-9.md")
    _write(repo, f"{FOLDER}/CHG-SCPT-2026-004.md.disabled")
    done = _run(repo, "--json")
    assert done.returncode == 0, done.stdout
    assert json.loads(done.stdout)["checked"] == 2


def test_the_reference_commit_decides_what_counts_as_tracked(repo: Path) -> None:
    first = _git(repo, "rev-parse", "HEAD").strip()
    rel = f"{FOLDER}/CHG-SCPT-2026-003.md"
    _write(repo, rel)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "add 003")
    assert _run(repo).returncode == 0
    done = _run(repo, "--ref", first, "--json")
    assert done.returncode == 2
    assert json.loads(done.stdout)["untracked"] == [rel]


def test_only_the_named_folders_are_checked_when_dir_is_given(repo: Path) -> None:
    other = "other/04_监控/01_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-001.md"
    _write(repo, other)
    both = _run(repo, "--json")
    assert both.returncode == 2 and json.loads(both.stdout)["untracked"] == [other]
    only = _run(repo, "--dir", FOLDER, "--json")
    assert only.returncode == 0 and json.loads(only.stdout)["checked"] == 2


def test_a_folder_that_is_not_a_repository_or_a_ref_that_does_not_exist_is_refused(tmp_path: Path, repo: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    done = _run(plain)
    assert done.returncode == 3 and "ERROR" in done.stderr
    missing_ref = _run(repo, "--ref", "no-such-ref")
    assert missing_ref.returncode == 3 and "ERROR" in missing_ref.stderr
    (repo.parent / "outside").mkdir()
    escaped = _run(repo, "--dir", "../outside")
    assert escaped.returncode == 3 and "ERROR" in escaped.stderr


def test_the_default_search_looks_only_in_change_request_folders_and_skips_runtime_folders(repo: Path) -> None:
    nested = "deep/er/04_监控/01_变更管理/01_变更单/CHG-HMI/CHG-HMI-2026-001.md"
    runtime = ".auto-pm/worktrees/x/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-777.md"
    elsewhere = "docs/archive/CHG-SCPT-2026-555.md"
    _write(repo, nested)
    _write(repo, runtime)
    _write(repo, elsewhere)
    done = _run(repo, "--json")
    report = json.loads(done.stdout)
    assert report["untracked"] == [nested], report
