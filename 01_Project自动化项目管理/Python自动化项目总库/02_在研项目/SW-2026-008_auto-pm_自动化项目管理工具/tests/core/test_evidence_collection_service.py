"""Real-Git safety tests for Run-scoped evidence collection."""

from __future__ import annotations

import subprocess
import sys
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


def _workspace_with_candidate(
    tmp_path: Path,
    *,
    baseline_text: str = "baseline\n",
    ruff_failure: bool = False,
    unrelated_failure: bool = False,
) -> tuple[Path, Path, str]:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    _git(workspace, "init")
    (workspace / "owned.txt").write_text(
        baseline_text, encoding="utf-8", errors="replace"
    )
    (workspace / "foreign.txt").write_text("baseline\n", encoding="utf-8", errors="replace")
    (workspace / "auto_pm").mkdir()
    (workspace / "auto_pm" / "__init__.py").write_text("", encoding="utf-8", errors="replace")
    (workspace / "test_quality_gate.py").write_text(
        "def test_quality_gate_child_process() -> None:\n    assert True\n",
        encoding="utf-8",
        errors="replace",
    )
    if ruff_failure:
        (workspace / "auto_pm" / "ruff_failure.py").write_text(
            "import os\n", encoding="utf-8", errors="replace"
        )
    if unrelated_failure:
        (workspace / "test_unrelated_failure.py").write_text(
            "def test_unrelated_failure() -> None:\n    assert False\n",
            encoding="utf-8",
            errors="replace",
        )
    _git(workspace, "add", ".")
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


def _quality_run(candidate: Path, baseline: str, *, ruff_failure: bool = False) -> RunItem:
    owned_paths = ["auto_pm/__init__.py", "test_quality_gate.py"]
    if ruff_failure:
        owned_paths.append("auto_pm/ruff_failure.py")
    return _run(candidate, baseline, tuple(owned_paths))


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


def test_evidence_content_hash_changes_for_baseline_staged_and_unstaged_content(
    tmp_path: Path,
) -> None:
    first_workspace, first_candidate, first_baseline = _workspace_with_candidate(tmp_path / "first")
    second_workspace, second_candidate, second_baseline = _workspace_with_candidate(
        tmp_path / "second", baseline_text="different baseline\n"
    )
    first_service = EvidenceCollectionService(first_workspace)
    second_service = EvidenceCollectionService(second_workspace)

    baseline_hash = first_service.collect(_run(first_candidate, first_baseline)).content_hash
    changed_baseline_hash = second_service.collect(_run(second_candidate, second_baseline)).content_hash
    owned = first_candidate / "owned.txt"
    owned.write_text("baseline\nstaged\n", encoding="utf-8", errors="replace")
    _git(first_candidate, "add", "owned.txt")
    staged_hash = first_service.collect(_run(first_candidate, first_baseline)).content_hash
    owned.write_text("baseline\nstaged\nunstaged\n", encoding="utf-8", errors="replace")
    unstaged_hash = first_service.collect(_run(first_candidate, first_baseline)).content_hash

    assert baseline_hash != changed_baseline_hash
    assert baseline_hash != staged_hash
    assert staged_hash != unstaged_hash


def test_real_python_quality_gates_run_in_run_candidate_project_root(tmp_path: Path) -> None:
    workspace, candidate, baseline = _workspace_with_candidate(tmp_path, unrelated_failure=True)
    service = EvidenceCollectionService(workspace)

    receipt = service.run_python_quality_gates(_quality_run(candidate, baseline), candidate)

    assert receipt.status == "PASS"
    assert receipt.evidence_current
    assert receipt.project_root == str(candidate.resolve())
    assert tuple(gate.name for gate in receipt.gates) == ("pytest", "ruff", "mypy")
    assert all(gate.cwd == str(candidate.resolve()) for gate in receipt.gates)
    assert all(gate.exit_code == 0 for gate in receipt.gates)
    assert all(gate.output_digest for gate in receipt.gates)
    pytest_gate, ruff_gate, mypy_gate = receipt.gates
    assert pytest_gate.command[-1] == "test_quality_gate.py"
    assert ruff_gate.command[-2:] == ("auto_pm/__init__.py", "test_quality_gate.py")
    assert mypy_gate.command[-1] == "auto_pm/__init__.py"
    assert service.quality_receipt_is_current(_quality_run(candidate, baseline), candidate, receipt)


def test_nonzero_real_quality_gate_cannot_report_pass(tmp_path: Path) -> None:
    workspace, candidate, baseline = _workspace_with_candidate(tmp_path, ruff_failure=True)

    receipt = EvidenceCollectionService(workspace).run_python_quality_gates(
        _quality_run(candidate, baseline, ruff_failure=True), candidate
    )

    ruff = next(gate for gate in receipt.gates if gate.name == "ruff")
    assert ruff.exit_code not in (None, 0)
    assert receipt.status == "FAIL"


def test_quality_receipt_becomes_invalid_when_evidence_changes(tmp_path: Path) -> None:
    workspace, candidate, baseline = _workspace_with_candidate(tmp_path)
    service = EvidenceCollectionService(workspace)
    run = _quality_run(candidate, baseline)
    receipt = service.run_python_quality_gates(run, candidate)
    assert receipt.status == "PASS"

    (candidate / "owned.txt").write_text("baseline\nchanged\n", encoding="utf-8", errors="replace")

    assert not service.quality_receipt_is_current(run, candidate, receipt)


def test_missing_owned_quality_category_returns_failure_receipt(tmp_path: Path) -> None:
    workspace, candidate, baseline = _workspace_with_candidate(tmp_path)

    receipt = EvidenceCollectionService(workspace).run_python_quality_gates(
        _run(candidate, baseline, ("test_quality_gate.py",)), candidate
    )

    mypy = next(gate for gate in receipt.gates if gate.name == "mypy")
    assert receipt.status == "FAIL"
    assert mypy.exit_code is None
    assert "缺少已批准" in mypy.output_summary


def test_quality_gate_launch_failure_returns_failure_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, candidate, baseline = _workspace_with_candidate(tmp_path)
    original_run = subprocess.run

    def fail_python_commands(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        command = args[0]
        if isinstance(command, tuple) and command and command[0] == sys.executable:
            raise FileNotFoundError("simulated quality tool launch failure")
        return original_run(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "auto_pm.application.core.evidence_collection_service.subprocess.run", fail_python_commands
    )
    receipt = EvidenceCollectionService(workspace).run_python_quality_gates(
        _quality_run(candidate, baseline), candidate
    )

    assert receipt.status == "FAIL"
    assert all(gate.exit_code is None for gate in receipt.gates)
    assert all("launch error" in gate.output_summary for gate in receipt.gates)
