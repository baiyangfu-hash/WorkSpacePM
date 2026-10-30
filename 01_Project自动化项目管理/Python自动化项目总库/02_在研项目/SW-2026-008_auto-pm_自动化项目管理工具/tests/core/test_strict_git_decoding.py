"""Git output that decides something is decoded as strict UTF-8 (audit 368 item 4, batch 1).

Before, ``errors="replace"`` repaired invalid bytes into look-alike text, so a path or registry with bad bytes was
compared or parsed as if it were fine.  Now each site refuses or reports instead.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from auto_pm.application.core import candidate_merge_back_service as merge_back_module
from auto_pm.application.core import chg_tracking_service
from auto_pm.application.core.approval_proof_service import (
    REGISTRY_RELATIVE_PATH,
    ApprovalProofService,
    make_key,
)
from auto_pm.application.core.candidate_merge_back_service import (
    CandidateMergeBackError,
    CandidateMergeBackService,
)
from auto_pm.infrastructure.continuity_store import ContinuityStoreError, _decode_git_path
from tests.git_support import git_do

BAD = b"proj/\xff\xfe.scl"


def _completed(stdout: bytes) -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr=b"")


def test_continuity_store_path_with_invalid_bytes_is_refused() -> None:
    assert _decode_git_path(b".auto-pm/decisions/D-1.json\n") == ".auto-pm/decisions/D-1.json"
    with pytest.raises(ContinuityStoreError, match="不是合法 UTF-8"):
        _decode_git_path(BAD)


def test_merge_back_path_listing_with_invalid_bytes_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = CandidateMergeBackService(tmp_path)
    monkeypatch.setattr(merge_back_module, "run_git_bounded", lambda *a, **k: _completed(b"ok.scl\0" + BAD + b"\0"))
    with pytest.raises(CandidateMergeBackError, match="不是合法 UTF-8"):
        service._git_z(["diff", "-z"])
    monkeypatch.setattr(merge_back_module, "run_git_bounded", lambda *a, **k: _completed(b"ok.scl\0"))
    assert service._git_z(["diff", "-z"]) == ("ok.scl",)


def test_merge_back_hash_output_with_invalid_bytes_counts_as_unknown(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = CandidateMergeBackService(tmp_path)
    monkeypatch.setattr(merge_back_module, "run_git_bounded", lambda *a, **k: _completed(b"\xff\xfe\n"))
    assert service._git(["hash-object", "--stdin"], stdin=b"x") is None


def test_chg_tracking_listing_with_invalid_bytes_is_reported_not_repaired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake_git(cwd: Path, *arguments: str) -> bytes:
        calls["n"] += 1
        if arguments[0] == "rev-parse" and "--show-toplevel" in arguments:
            return str(tmp_path).encode() + b"\n"
        if arguments[0] == "ls-tree":
            return BAD + b"\0"
        return b""

    monkeypatch.setattr(chg_tracking_service, "_git", fake_git)
    report = chg_tracking_service.check_project_chg_tracking(tmp_path, "HEAD")
    assert "无法用 Git 检查" in report.skipped_reason and not report.clean


def test_chg_tracking_toplevel_with_invalid_bytes_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(chg_tracking_service, "_git", lambda cwd, *a: str(tmp_path).encode() + b"\xff\n")
    report = chg_tracking_service.check_project_chg_tracking(tmp_path, "HEAD")
    assert "无法用 Git 检查" in report.skipped_reason


@pytest.fixture
def pinned_root(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    root.mkdir()
    git_do(root, "init", "-q")
    git_do(root, "config", "user.name", "t")
    git_do(root, "config", "user.email", "t@example.invalid")
    (root / "README.md").write_text("x", encoding="utf-8")
    git_do(root, "add", "README.md")
    git_do(root, "commit", "-q", "-m", "base")
    service = ApprovalProofService(root)
    service.write_working_keys([make_key("baiyang", "relay-K1-on", n=2**10)])
    git_do(root, "add", REGISTRY_RELATIVE_PATH)
    git_do(root, "commit", "-q", "-m", "pin")
    return root


def test_approval_registry_with_invalid_bytes_refuses_every_approval(pinned_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    service = ApprovalProofService(pinned_root)
    keys, problem = service.committed_state()
    assert keys is not None and not problem  # baseline: a clean registry is read

    real = ApprovalProofService._git

    def broken_show(self: ApprovalProofService, *arguments: str) -> subprocess.CompletedProcess[bytes]:
        done = real(self, *arguments)
        if arguments[0] == "show":
            return subprocess.CompletedProcess(done.args, 0, done.stdout + b"\xff\xfe", b"")
        return done

    monkeypatch.setattr(ApprovalProofService, "_git", broken_show)
    keys, problem = ApprovalProofService(pinned_root).committed_state()
    assert keys is None and "一律拒绝" in problem and "不是合法 UTF-8" in problem


def test_approval_toplevel_with_invalid_bytes_refuses(pinned_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = ApprovalProofService._git

    def broken_top(self: ApprovalProofService, *arguments: str) -> subprocess.CompletedProcess[bytes]:
        done = real(self, *arguments)
        if arguments[:2] == ("rev-parse", "--show-toplevel"):
            return subprocess.CompletedProcess(done.args, 0, done.stdout.strip() + b"\xff\n", b"")
        return done

    monkeypatch.setattr(ApprovalProofService, "_git", broken_top)
    keys, problem = ApprovalProofService(pinned_root).committed_state()
    assert keys is None and "一律拒绝" in problem
