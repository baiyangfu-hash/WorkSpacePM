"""Safety tests for A5 controlled and isolated Git worktree policy."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from auto_pm.core.worktree_policy_service import WorktreePolicyError, WorktreePolicyService

import auto_pm.infrastructure.control_root_guard as control_root_guard
from auto_pm.contracts.execution_adapter import WorktreeMode
from auto_pm.infrastructure.control_root_guard import (
    ControlRootGuardError,
    authority_path_parts,
    require_governed_worktree,
    require_safe_workspace_path,
)


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


def _separate_repository(root: Path, git_dir: Path) -> None:
    subprocess.run(
        ["git", "init", "--separate-git-dir", str(git_dir), str(root)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
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


def _directory_link(link: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            pytest.skip(f"junction unavailable: {result.stderr or result.stdout}")
    else:
        link.symlink_to(target, target_is_directory=True)


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


def test_control_root_guard_accepts_primary_and_rejects_linked_worktree(tmp_path: Path) -> None:
    _repository(tmp_path)
    service = WorktreePolicyService(tmp_path)

    service.require_control_root()
    linked = service.materialize(
        service.select(
            run_id="RUN-SW008-ROOT-GUARD",
            allow_branch_creation=True,
            force_isolation=True,
        )
    ).worktree_path

    linked_plan = WorktreePolicyService(linked).select(
        run_id="RUN-SW008-LINKED-CURRENT", allow_branch_creation=False
    )
    assert linked_plan.worktree_path == linked.resolve()
    with pytest.raises(WorktreePolicyError, match="linked worktree"):
        WorktreePolicyService(linked).require_control_root()


def test_linked_worktree_materialize_fails_before_branch_or_directory_side_effect(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    primary = WorktreePolicyService(tmp_path)
    linked = primary.materialize(
        primary.select(
            run_id="RUN-SW008-LINKED-SEED",
            allow_branch_creation=True,
            force_isolation=True,
        )
    ).worktree_path
    service = WorktreePolicyService(linked)
    plan = service.select(
        run_id="RUN-SW008-LINKED-MUTATION",
        allow_branch_creation=True,
        force_isolation=True,
    )

    with pytest.raises(WorktreePolicyError, match="linked worktree"):
        service.materialize(plan)

    assert not plan.worktree_path.exists()
    assert not _git(tmp_path, "branch", "--list", plan.branch_name).stdout.strip()


def test_control_root_guard_ignores_git_environment_spoofing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repository(tmp_path)
    service = WorktreePolicyService(tmp_path)
    linked = service.materialize(
        service.select(
            run_id="RUN-SW008-ENV-SPOOF-SEED",
            allow_branch_creation=True,
            force_isolation=True,
        )
    ).worktree_path
    expected_head = _git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    linked_git_dir = _git(linked, "rev-parse", "--absolute-git-dir").stdout.strip()
    monkeypatch.setenv("GIT_COMMON_DIR", linked_git_dir)

    with pytest.raises(WorktreePolicyError, match="linked worktree"):
        WorktreePolicyService(linked).require_control_root()

    monkeypatch.setenv("GIT_DIR", str(linked_git_dir))
    monkeypatch.setenv("GIT_WORK_TREE", str(linked))
    plan = service.select(
        run_id="RUN-SW008-ENV-SPOOF-CONTROL",
        allow_branch_creation=True,
    )
    assert plan.git_head == expected_head
    assert plan.branch_name == "codex/run-sw008-env-spoof-control"


def test_control_root_guard_rejects_external_separate_git_directory_without_side_effect(
    tmp_path: Path,
) -> None:
    root = tmp_path / "separate-worktree"
    git_dir = tmp_path / "external-control"
    _separate_repository(root, git_dir)
    service = WorktreePolicyService(root)
    plan = service.select(
        run_id="RUN-SW008-SEPARATE-GIT-DIR",
        allow_branch_creation=True,
        force_isolation=True,
    )

    with pytest.raises(WorktreePolicyError, match="separate git-dir|真实 .git"):
        service.materialize(plan)

    assert not plan.worktree_path.exists()
    assert not (root / ".auto-pm").exists()
    assert not _git(root, "branch", "--list", plan.branch_name).stdout.strip()


def test_control_root_guard_rejects_git_control_junction_without_side_effect(
    tmp_path: Path,
) -> None:
    root = tmp_path / "junction-worktree"
    git_dir = tmp_path / "junction-control"
    _separate_repository(root, git_dir)
    (root / ".git").unlink()
    _directory_link(root / ".git", git_dir)
    service = WorktreePolicyService(root)
    plan = service.select(
        run_id="RUN-SW008-GIT-JUNCTION",
        allow_branch_creation=True,
        force_isolation=True,
    )

    with pytest.raises(WorktreePolicyError, match="junction|reparse"):
        service.materialize(plan)

    assert not plan.worktree_path.exists()
    assert not (root / ".auto-pm").exists()
    assert not _git(root, "branch", "--list", plan.branch_name).stdout.strip()


def test_materialize_revalidates_late_junction_before_mkdir_or_git_add(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    service = WorktreePolicyService(tmp_path)
    plan = service.select(
        run_id="RUN-SW008-LATE-JUNCTION",
        allow_branch_creation=True,
        force_isolation=True,
    )
    external = tmp_path.parent / f"{tmp_path.name}-external-worktrees"
    _directory_link(tmp_path / ".auto-pm", external)

    with pytest.raises(WorktreePolicyError, match="worktrees"):
        service.materialize(plan)

    assert list(external.iterdir()) == []
    assert not _git(tmp_path, "branch", "--list", plan.branch_name).stdout.strip()


def test_materialize_revalidates_junction_immediately_before_side_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _repository(tmp_path)
    service = WorktreePolicyService(tmp_path)
    plan = service.select(
        run_id="RUN-SW008-LATE-JUNCTION-TOCTOU",
        allow_branch_creation=True,
        force_isolation=True,
    )
    external = tmp_path.parent / f"{tmp_path.name}-external-worktrees-toctou"
    original = service._require_branch_absent

    def swap_then_validate(branch_name: str) -> None:
        _directory_link(tmp_path / ".auto-pm", external)
        original(branch_name)

    monkeypatch.setattr(service, "_require_branch_absent", swap_then_validate)

    with pytest.raises(WorktreePolicyError, match="worktrees"):
        service.materialize(plan)

    assert list(external.iterdir()) == []
    assert not _git(tmp_path, "branch", "--list", plan.branch_name).stdout.strip()


def test_governed_run_worktree_rejects_non_git_and_junction_alias(
    tmp_path: Path,
) -> None:
    _repository(tmp_path)
    plain = tmp_path / ".auto-pm" / "worktrees" / "plain"
    plain.mkdir(parents=True)

    with pytest.raises(ControlRootGuardError, match="linked worktree"):
        require_governed_worktree(tmp_path, plain.resolve())

    foreign = tmp_path.parent / f"{tmp_path.name}-foreign-run-worktree"
    foreign.mkdir()
    _repository(foreign)
    alias = tmp_path / ".auto-pm" / "worktrees" / "alias"
    _directory_link(alias, foreign)

    with pytest.raises(ControlRootGuardError, match="symlink/junction"):
        require_governed_worktree(tmp_path, alias)


def test_authority_path_identity_is_windows_insensitive_and_posix_sensitive() -> None:
    mixed = authority_path_parts("Src/Foo.py", windows=False)
    lower = authority_path_parts("src/foo.py", windows=False)
    assert mixed != lower
    assert authority_path_parts("Src/Foo.py", windows=True) == authority_path_parts(
        "src/foo.py",
        windows=True,
    )


@pytest.mark.parametrize("candidate", ["alias/../real", "real/./file.txt"])
def test_safe_workspace_path_rejects_raw_dot_segments(
    tmp_path: Path,
    candidate: str,
) -> None:
    (tmp_path / "real").mkdir()

    with pytest.raises(ControlRootGuardError, match="点路径段"):
        require_safe_workspace_path(tmp_path, candidate, label="test path")


def test_control_root_git_fact_rejects_success_with_permission_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _repository(tmp_path)

    def diagnostic_result(*_args, **_kwargs):
        return subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="",
            stderr="warning: Permission denied",
        )

    monkeypatch.setattr(control_root_guard.subprocess, "run", diagnostic_result)
    with pytest.raises(ControlRootGuardError, match="Permission denied"):
        control_root_guard._git_optional_output(tmp_path, "diff", "--name-only")
    assert not (tmp_path / ".auto-pm").exists()


def test_worktree_policy_git_fact_rejects_success_with_permission_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _repository(tmp_path)
    service = WorktreePolicyService(tmp_path)
    monkeypatch.setattr(
        service,
        "_run_git",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout="clean\n",
            stderr="warning: Permission denied",
        ),
    )

    with pytest.raises(WorktreePolicyError, match="Permission denied"):
        service._git_output("status", "--porcelain")
    assert not (tmp_path / ".auto-pm").exists()
