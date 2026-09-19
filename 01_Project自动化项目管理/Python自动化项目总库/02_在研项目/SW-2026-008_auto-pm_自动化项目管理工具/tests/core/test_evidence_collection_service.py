"""Real-Git safety tests for Run-scoped evidence collection."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from auto_pm.application.core.evidence_collection_service import (
    EvidenceCollectionError,
    EvidenceCollectionService,
)
from auto_pm.contracts.continuity import RunItem, RunState
from auto_pm.infrastructure.control_root_guard import clean_git_environment

_TIMESTAMP = "2026-09-19T00:00:00+00:00"


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=clean_git_environment(),
    )
    return result.stdout.strip()


def _workspace_with_candidate(tmp_path: Path) -> tuple[Path, Path, str]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    _git(workspace, "init")
    (workspace / "owned.txt").write_text("baseline\n", encoding="utf-8", errors="replace")
    (workspace / "foreign.txt").write_text("baseline\n", encoding="utf-8", errors="replace")
    _git(workspace, "add", "owned.txt", "foreign.txt")
    _git(
        workspace,
        "-c",
        "user.name=Evidence Test",
        "-c",
        "user.email=evidence@example.invalid",
        "commit",
        "-m",
        "baseline",
    )
    baseline = _git(workspace, "rev-parse", "HEAD")
    candidate = workspace / ".auto-pm" / "worktrees" / "evidence-run"
    candidate.parent.mkdir(parents=True)
    _git(workspace, "worktree", "add", "-b", "codex/evidence-run", str(candidate), baseline)
    return workspace, candidate, baseline


def _run(candidate: Path, baseline: str, owned_paths: tuple[str, ...] = ("owned.txt",)) -> RunItem:
    return RunItem(
        run_id="RUN-SW008-PMF-C01-001",
        work_id="WORK-SW008-PMF-C01-001",
        state=RunState.RUNNING,
        executor_id="codex",
        adapter="codex",
        owned_paths=owned_paths,
        declared_dirty_paths=(),
        git_head=baseline,
        worktree_path=str(candidate.resolve()),
        version=1,
        created_at=_TIMESTAMP,
        updated_at=_TIMESTAMP,
    )


def test_collect_keeps_staged_and_later_unstaged_content_separate(tmp_path: Path) -> None:
    workspace, candidate, baseline = _workspace_with_candidate(tmp_path)
    owned = candidate / "owned.txt"
    owned.write_text("baseline\nstaged\n", encoding="utf-8", errors="replace")
    _git(candidate, "add", "owned.txt")
    owned.write_text("baseline\nstaged\nunstaged\n", encoding="utf-8", errors="replace")

    evidence = EvidenceCollectionService(workspace).collect(_run(candidate, baseline))

    assert evidence.baseline_git_head == baseline
    assert evidence.worktree_path == str(candidate.resolve())
    assert evidence.staged_paths == ("owned.txt",)
    assert evidence.unstaged_paths == ("owned.txt",)
    assert evidence.untracked_paths == ()
    assert "+staged" in evidence.staged_diff
    assert "+unstaged" not in evidence.staged_diff
    assert "+unstaged" in evidence.unstaged_diff


def test_collect_uses_only_the_run_candidate_worktree(tmp_path: Path) -> None:
    workspace, candidate, baseline = _workspace_with_candidate(tmp_path)
    (workspace / "foreign.txt").write_text(
        "baseline\ncontrol worktree only\n", encoding="utf-8", errors="replace"
    )
    (candidate / "owned.txt").write_text(
        "baseline\ncandidate only\n", encoding="utf-8", errors="replace"
    )
    _git(candidate, "add", "owned.txt")

    evidence = EvidenceCollectionService(workspace).collect(_run(candidate, baseline))

    assert evidence.staged_paths == ("owned.txt",)
    assert "candidate only" in evidence.staged_diff
    assert "control worktree only" not in evidence.staged_diff


def test_collect_rejects_foreign_staged_path(tmp_path: Path) -> None:
    workspace, candidate, baseline = _workspace_with_candidate(tmp_path)
    foreign = candidate / "foreign.txt"
    foreign.write_text("baseline\nforeign staged\n", encoding="utf-8", errors="replace")
    _git(candidate, "add", "foreign.txt")

    with pytest.raises(EvidenceCollectionError, match="staged.*foreign.txt"):
        EvidenceCollectionService(workspace).collect(_run(candidate, baseline))


def test_collect_rejects_foreign_unstaged_path(tmp_path: Path) -> None:
    workspace, candidate, baseline = _workspace_with_candidate(tmp_path)
    (candidate / "foreign.txt").write_text(
        "baseline\nforeign unstaged\n", encoding="utf-8", errors="replace"
    )

    with pytest.raises(EvidenceCollectionError, match="unstaged.*foreign.txt"):
        EvidenceCollectionService(workspace).collect(_run(candidate, baseline))


def test_collect_rejects_foreign_untracked_path(tmp_path: Path) -> None:
    workspace, candidate, baseline = _workspace_with_candidate(tmp_path)
    (candidate / "foreign-untracked.txt").write_text(
        "foreign untracked\n", encoding="utf-8", errors="replace"
    )

    with pytest.raises(EvidenceCollectionError, match="untracked.*foreign-untracked.txt"):
        EvidenceCollectionService(workspace).collect(_run(candidate, baseline))


def test_collect_rejects_candidate_head_drift_from_run_baseline(tmp_path: Path) -> None:
    workspace, candidate, baseline = _workspace_with_candidate(tmp_path)
    (candidate / "owned.txt").write_text("candidate commit\n", encoding="utf-8", errors="replace")
    _git(candidate, "add", "owned.txt")
    _git(
        candidate,
        "-c",
        "user.name=Evidence Test",
        "-c",
        "user.email=evidence@example.invalid",
        "commit",
        "-m",
        "candidate drift",
    )

    with pytest.raises(EvidenceCollectionError, match="git_head"):
        EvidenceCollectionService(workspace).collect(_run(candidate, baseline))
