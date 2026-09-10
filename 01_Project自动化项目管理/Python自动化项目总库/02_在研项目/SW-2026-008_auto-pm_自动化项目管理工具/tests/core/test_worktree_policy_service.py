"""Safety tests for A5 controlled and isolated Git worktree policy."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from auto_pm.core.worktree_policy_service import WorktreePolicyError, WorktreePolicyService

from auto_pm.contracts.execution_adapter import WorktreeMode


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _repository(root: Path) -> None:
    _git(root, "init")
    (root / "README.md").write_text("baseline\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(
        root,
        "-c",
        "user.name=Worktree Test",
        "-c",
        "user.email=worktree@example.invalid",
        "commit",
        "-m",
        "baseline",
    )


def test_clean_controlled_worktree_is_reused_without_branch_authority(tmp_path: Path) -> None:
    _repository(tmp_path)

    plan = WorktreePolicyService(tmp_path).select(
        run_id="RUN-SW008-A5-001", allow_branch_creation=False
    )

    assert plan.worktree_mode is WorktreeMode.CURRENT
    assert plan.worktree_path == tmp_path.resolve()
    assert plan.branch_name == ""
    assert plan.origin_dirty_paths == ()


def test_dirty_controlled_worktree_creates_an_isolated_branch_without_touching_parent(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    (tmp_path / "unrelated.txt").write_text("preserve me\n", encoding="utf-8")
    service = WorktreePolicyService(tmp_path)

    plan = service.select(run_id="RUN-SW008-A5-002", allow_branch_creation=True)
    materialized = service.materialize(plan)

    assert materialized.worktree_mode is WorktreeMode.ISOLATED
    assert materialized.branch_name == "codex/run-sw008-a5-002"
    assert (materialized.worktree_path / "README.md").read_text(encoding="utf-8") == "baseline\n"
    assert not (materialized.worktree_path / "unrelated.txt").exists()
    assert (tmp_path / "unrelated.txt").read_text(encoding="utf-8") == "preserve me\n"
    assert service.branch_name_for(materialized.worktree_path) == materialized.branch_name


def test_dirty_controlled_worktree_refuses_to_branch_without_authority(tmp_path: Path) -> None:
    _repository(tmp_path)
    (tmp_path / "unrelated.txt").write_text("preserve me\n", encoding="utf-8")

    with pytest.raises(WorktreePolicyError, match="未授权"):
        WorktreePolicyService(tmp_path).select(
            run_id="RUN-SW008-A5-003", allow_branch_creation=False
        )


def test_existing_isolated_target_is_never_reused_or_overwritten(tmp_path: Path) -> None:
    _repository(tmp_path)
    service = WorktreePolicyService(tmp_path)
    plan = service.select(
        run_id="RUN-SW008-A5-004", allow_branch_creation=True, force_isolation=True
    )
    service.materialize(plan)

    with pytest.raises(WorktreePolicyError, match="已存在"):
        service.select(run_id="RUN-SW008-A5-004", allow_branch_creation=True, force_isolation=True)
