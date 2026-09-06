"""稳定版 Dogfood 隔离 runner 的外部复核测试。"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from auto_pm.core.dogfood_runner import DogfoodIsolationError, DogfoodRunner


def _git(cwd: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stderr


def _git_repo(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / ".gitignore").write_text(
        ".auto-pm/worktrees/\n",
        encoding="utf-8",
    )
    source = workspace / "00_Infrastructure" / "auto_pm"
    source.mkdir(parents=True)
    (source / "version.txt").write_text("stable\n", encoding="utf-8")
    (workspace / "main.py").write_text("print('stable')\n", encoding="utf-8")

    _git(workspace, "init")
    _git(workspace, "config", "user.email", "test@example.com")
    _git(workspace, "config", "user.name", "Dogfood Test")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-m", "baseline")

    candidate_parent = workspace / ".auto-pm" / "worktrees"
    candidate_parent.mkdir(parents=True)
    candidate = candidate_parent / "candidate"
    _git(workspace, "clone", str(workspace), str(candidate))
    return workspace, candidate


def test_review_uses_stable_side_fingerprint_and_allowlist(tmp_path: Path) -> None:
    workspace, candidate = _git_repo(tmp_path)
    (candidate / "00_Infrastructure" / "auto_pm" / "version.txt").write_text(
        "candidate\n",
        encoding="utf-8",
    )
    runner = DogfoodRunner(workspace)
    baseline = runner.inspect(candidate)["stable"]["scope_fingerprint"]

    report = runner.review(
        candidate,
        baseline_stable_fingerprint=baseline,
        write_report=True,
    )

    assert report["passed"] is True
    assert report["reviewer"] == "stable-control-plane"
    assert report["checks"]["stable_baseline_match"] is True
    evidence_file = Path(report["evidence_file"])
    assert evidence_file.is_file()
    assert not list(evidence_file.parent.glob("*.tmp"))


def test_review_rejects_candidate_scope_and_runtime_changes(tmp_path: Path) -> None:
    workspace, candidate = _git_repo(tmp_path)
    (candidate / "forbidden.txt").write_text("outside\n", encoding="utf-8")
    (candidate / ".auto-pm").mkdir(exist_ok=True)
    (candidate / ".auto-pm" / "runtime.db").write_text("runtime\n", encoding="utf-8")

    report = DogfoodRunner(workspace).review(candidate, write_report=False)

    assert report["passed"] is False
    assert "forbidden.txt" in report["allowlist_violations"]
    assert ".auto-pm/runtime.db" in report["candidate_runtime_changes"]


def test_candidate_must_be_under_isolated_worktree_directory(tmp_path: Path) -> None:
    workspace, _ = _git_repo(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()

    with pytest.raises(DogfoodIsolationError, match="隔离目录"):
        DogfoodRunner(workspace).inspect(outside)


def test_prepare_candidate_requires_clean_stable_tree(tmp_path: Path) -> None:
    workspace, _ = _git_repo(tmp_path)
    candidate = workspace / ".auto-pm" / "worktrees" / "prepared"

    prepared = DogfoodRunner(workspace).prepare_candidate(candidate)

    assert prepared["candidate_path"] == str(candidate.resolve())
    assert prepared["base_sha"]
    assert (candidate / "main.py").is_file()

    dirty_candidate = workspace / ".auto-pm" / "worktrees" / "dirty"
    (workspace / "main.py").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(DogfoodIsolationError, match="不是干净树"):
        DogfoodRunner(workspace).prepare_candidate(dirty_candidate)
