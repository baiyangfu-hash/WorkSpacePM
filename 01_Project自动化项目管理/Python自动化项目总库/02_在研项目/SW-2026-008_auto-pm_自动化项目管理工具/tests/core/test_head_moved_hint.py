"""The "HEAD moved" refusal of pm verify and of the automatic checkpoint gives the one command that works, never "turn the Run FAILED" (DJ-2026-005 trial B4).

Turning the Run FAILED blocks its Work (D-109) and a BLOCKED Work cannot get a new Run, so that advice ended in cancelling the
card.  ``git reset --soft <the Run's git_head>`` takes the commit back into the index with every change kept; the drill
``tests/e2e/test_verify_hint_after_commit_drill.py`` follows it through to a passing ``pm verify``.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from auto_pm.application.core.continuity_execution_service import ContinuityExecutionError
from auto_pm.application.core.evidence_collection_service import (
    EvidenceCollectionError,
    EvidenceCollectionService,
)
from tests.core.test_docs_checkpoint_chain import _append_docs, _docs_service
from tests.core.test_evidence_collection_service import _two_project_quality_run

_RESET = re.compile(r'git -C "(?P<worktree>[^"]+)" reset --soft (?P<head>[0-9a-f]{40})')


def _assert_the_way_out(message: str, worktree: Path, head: str) -> None:
    found = _RESET.search(message)
    assert found is not None, message
    assert Path(found["worktree"]).resolve() == worktree.resolve() and found["head"] == head
    assert "把该 Run 转 FAILED，在当前 HEAD" not in message
    assert "不要把 Run 转 FAILED" in message


def test_the_checkpoint_refusal_after_a_commit_in_the_worktree_names_the_reset(tmp_path: Path) -> None:
    candidate, service = _docs_service(tmp_path)
    head = subprocess.run(["git", "-C", str(candidate), "rev-parse", "HEAD"], check=True, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()
    subprocess.run(["git", "-C", str(candidate), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(candidate), "-c", "user.name=t", "-c", "user.email=t@e.invalid", "commit", "-qm", "work commit"],
        check=True,
    )

    with pytest.raises(ContinuityExecutionError) as refusal:
        _append_docs(service, candidate)

    _assert_the_way_out(str(refusal.value), candidate, head)


def test_the_verify_refusal_after_the_head_moved_names_the_reset(tmp_path: Path) -> None:
    workspace, candidate, run = _two_project_quality_run(tmp_path)
    drifted = run.model_copy(update={"git_head": "0" * 40})

    with pytest.raises(EvidenceCollectionError) as refusal:
        EvidenceCollectionService(workspace).run_generic_checkpoint_quality_gates(drifted, candidate)

    _assert_the_way_out(str(refusal.value), candidate, "0" * 40)


def test_the_verify_refusal_says_the_same_sentence_as_the_commit_hook(tmp_path: Path) -> None:
    """G 工位止血第 3 条（卡 280）：提交钩子拒提交和 pm verify 发现 HEAD 挪了，说同一句话。"""
    from auto_pm.contracts.run_open_commit import run_open_commit_hint

    workspace, candidate, run = _two_project_quality_run(tmp_path)
    drifted = run.model_copy(update={"git_head": "0" * 40})
    with pytest.raises(EvidenceCollectionError) as refusal:
        EvidenceCollectionService(workspace).run_generic_checkpoint_quality_gates(drifted, candidate)
    assert str(refusal.value).startswith(run_open_commit_hint("0" * 40)), str(refusal.value)
