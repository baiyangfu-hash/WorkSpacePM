"""Unit cases for bringing an isolated Run's accepted bytes back into the control root (gap 8)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from auto_pm.application.core import candidate_merge_back_service as module
from auto_pm.application.core.candidate_merge_back_service import (
    CandidateMergeBackError,
    CandidateMergeBackService,
)
from auto_pm.application.core.evidence_collection_service import EvidenceCollection
from auto_pm.contracts.continuity import CheckpointItem, RunItem, RunState

TARGET = "proj/src/block.scl"
OTHER = "proj/src/other.scl"


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *arguments], check=True, capture_output=True, text=True
    ).stdout.strip()


def _repository(tmp_path: Path, *, attributes: str = "") -> tuple[Path, Path, str]:
    control = tmp_path / "control"
    (control / "proj" / "src").mkdir(parents=True)
    _git(tmp_path, "init", "-q", str(control))
    _git(control, "config", "user.email", "drill@example.invalid")
    _git(control, "config", "user.name", "drill")
    if attributes:
        (control / ".gitattributes").write_text(attributes, encoding="utf-8")
    (control / TARGET).write_bytes(b"base\n")
    (control / OTHER).write_bytes(b"other\n")
    _git(control, "add", ".")
    _git(control, "commit", "-q", "-m", "base")
    head = _git(control, "rev-parse", "HEAD")
    if attributes:  # check out again so the working file carries the attribute's line endings, as on the user's PC
        (control / TARGET).unlink()
        _git(control, "checkout", "--", TARGET)
    worktree = control / ".auto-pm" / "worktrees" / "run"
    _git(control, "worktree", "add", "-q", "--detach", str(worktree))
    return control, worktree, head


def _lineage(
    monkeypatch: pytest.MonkeyPatch, worktree: Path, head: str, changed: tuple[str, ...]
) -> tuple[RunItem, CheckpointItem]:
    collection = EvidenceCollection(
        run_id="RUN-1", git_head=head, worktree_path=str(worktree), staged_paths=(), unstaged_paths=changed,
        untracked_paths=(), untracked_content_hashes=(), staged_diff="", unstaged_diff="diff",
    )
    monkeypatch.setattr(module.EvidenceCollectionService, "collect", lambda self, run: collection)
    run = RunItem(
        run_id="RUN-1", work_id="WORK-1", state=RunState.VERIFYING, executor_id="trae:cn", adapter="trae",
        owned_paths=changed, declared_dirty_paths=changed, git_head=head, worktree_path=str(worktree),
        version=3, created_at="2026-10-21T00:00:00+00:00", updated_at="2026-10-21T00:00:00+00:00",
    )
    checkpoint = CheckpointItem(
        checkpoint_id="CP-RUN-1-VERIFY", run_id="RUN-1", sequence=1, summary="verified", git_head=head,
        dirty_paths=changed, evidence=(json.dumps({"collection_hash": collection.content_hash}),),
        created_at="2026-10-21T00:00:00+00:00",
    )
    return run, checkpoint


def test_a_run_in_the_control_root_itself_has_nothing_to_merge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    control, _worktree, head = _repository(tmp_path)
    run, checkpoint = _lineage(monkeypatch, control, head, (TARGET,))

    receipt = CandidateMergeBackService(control).merge_back(run, checkpoint)

    assert receipt.written == () and receipt.already_present == ()


def test_a_deletion_is_never_carried_out_and_nothing_else_is_written(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control, worktree, head = _repository(tmp_path)
    (worktree / TARGET).write_bytes(b"accepted\n")
    (worktree / OTHER).unlink()
    run, checkpoint = _lineage(monkeypatch, worktree, head, (OTHER, TARGET))

    with pytest.raises(CandidateMergeBackError, match="收口不替你删除"):
        CandidateMergeBackService(control).merge_back(run, checkpoint)

    assert (control / TARGET).read_bytes() == b"base\n"
    assert (control / OTHER).read_bytes() == b"other\n"


def test_a_crlf_checkout_of_the_baseline_is_not_mistaken_for_a_foreign_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control, worktree, head = _repository(tmp_path, attributes="*.scl text eol=crlf\n")
    assert (control / TARGET).read_bytes() == b"base\r\n"
    (worktree / TARGET).write_bytes(b"accepted\r\n")
    run, checkpoint = _lineage(monkeypatch, worktree, head, (TARGET,))

    receipt = CandidateMergeBackService(control).merge_back(run, checkpoint)

    assert receipt.written == (TARGET,)
    assert (control / TARGET).read_bytes() == b"accepted\r\n"


def test_a_new_file_is_created_and_a_replay_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    control, worktree, head = _repository(tmp_path)
    created = "proj/src/新文件.md"
    (worktree / created).write_bytes("说明\n".encode())
    run, checkpoint = _lineage(monkeypatch, worktree, head, (created,))
    service = CandidateMergeBackService(control)

    first = service.merge_back(run, checkpoint)
    second = service.merge_back(run, checkpoint)

    assert first.written == (created,)
    assert second.written == () and second.already_present == (created,)
    assert (control / created).read_bytes() == "说明\n".encode()


def test_a_checkpoint_without_system_evidence_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    control, worktree, head = _repository(tmp_path)
    run, checkpoint = _lineage(monkeypatch, worktree, head, (TARGET,))
    hand_made = checkpoint.model_copy(update={"evidence": ("verified quality evidence",)})

    with pytest.raises(CandidateMergeBackError, match="证据无法解析"):
        CandidateMergeBackService(control).merge_back(run, hand_made)


def test_control_root_drift_lists_modified_and_untracked_owned_files_only(tmp_path: Path) -> None:
    control, _worktree, head = _repository(tmp_path)
    (control / TARGET).write_bytes(b"merged back, not committed\n")
    (control / "proj" / "src" / "loose.scl").write_bytes(b"x\n")
    (control / "unowned.txt").write_bytes(b"y\n")

    drift = CandidateMergeBackService(control).control_root_drift(("proj/src",), head)

    assert drift == ("proj/src/block.scl", "proj/src/loose.scl")
