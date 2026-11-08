"""TD-SW008-237 batch B: the application-layer decodes that take part in a decision stop (or compare exactly) instead of turning bytes into '?'.

Each test feeds undecodable bytes through the *real* decode path (a stand-in child process prints the bytes, so the keyword arguments
the production code passes to ``subprocess.run`` decide the outcome) and fails if the lenient decode comes back.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from auto_pm.application.core import execution_microtask_service as microtask
from auto_pm.application.core.ai_handoff_service import AiHandoffService
from auto_pm.application.core.dogfood_runner import DogfoodRunner
from auto_pm.application.core.execution_microtask_service import (
    ExecutionMicrotaskError,
    ExecutionMicrotaskService,
)
from auto_pm.application.core.gates.stage_gate_engine import StageGateEngine
from auto_pm.application.core.pm_facade_service import PmFacadeService
from auto_pm.application.core.project_fact_service import ProjectFactError, ProjectFactService
from auto_pm.application.core.role_pack_service import FAIL
from tests.core.test_role_pack_service import _codes, _workspace

BAD = b"src/\xff\xfe.scl"
REAL_RUN = subprocess.run


def _printing(payload: bytes) -> Any:
    """A ``subprocess.run`` that ignores the command and runs a child printing ``payload`` with the caller's own decoding options."""

    code = f"import sys; sys.stdout.buffer.write({payload!r})"

    def run(command: Any, **kwargs: Any) -> Any:
        kwargs.pop("cwd", None)
        kwargs.pop("env", None)
        return REAL_RUN([sys.executable, "-c", code], **kwargs)

    return run


def test_protected_change_scan_says_unknown_when_a_path_does_not_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    """A path that became '?' could slip past the protected-path comparison; "Git cannot say" (None) is the fail-closed answer."""

    monkeypatch.setattr(subprocess, "run", _printing(BAD + b"\0"))
    run = SimpleNamespace(worktree_path="/w", git_head="abc", owned_paths=())
    assert PmFacadeService._protected_file_changes(run) is None


def test_microtask_git_text_refuses_undecodable_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ExecutionMicrotaskService, "_git_bytes", classmethod(lambda cls, root, *args, env=None: BAD))
    with pytest.raises(ExecutionMicrotaskError, match="UTF-8"):
        ExecutionMicrotaskService._git_text(Path("."), "rev-parse", "--show-toplevel")
    monkeypatch.setattr(ExecutionMicrotaskService, "_git_bytes", classmethod(lambda cls, root, *args, env=None: b"abc\n"))
    assert ExecutionMicrotaskService._git_text(Path("."), "rev-parse", "HEAD") == "abc"
    assert microtask.ExecutionMicrotaskError is ExecutionMicrotaskError


def test_project_fact_git_query_refuses_undecodable_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(subprocess, "run", _printing(BAD))
    service = ProjectFactService(str(tmp_path))
    with pytest.raises(ProjectFactError, match="UTF-8"):
        service._run_git("status", "--porcelain=v1")
    monkeypatch.setattr(subprocess, "run", _printing(b"abc"))
    assert service._run_git("rev-parse", "HEAD").stdout == "abc"


def test_unreadable_change_order_counts_as_not_closed(tmp_path: Path) -> None:
    """The closing gate used to drop the bad bytes and judge the rest of the file; a file it cannot read cannot be shown closed."""

    project = tmp_path / "SW-TEST-001_demo"
    (project / "04_监控").mkdir(parents=True)
    # Closed on its face, with one undecodable byte in the body: dropping the byte would have let it count as closed.
    (project / "04_监控" / "CHG-TEST-2026-001.md").write_bytes("| 变更状态 | closed |\n".encode() + b"\xff\n")
    (project / "04_监控" / "CHG-TEST-2026-002.md").write_bytes("| 变更状态 | closed |\n".encode())
    result = StageGateEngine(str(tmp_path)).evaluate_stage_transition(str(project), "monitoring", "closing")
    found = next(i for i in result.items if i.id == "G4-CHG-ALL-CLOSED")
    assert found.passed is False and "CHG-TEST-2026-001.md" in found.message and "002" not in found.message


def test_refs_that_differ_only_in_undecodable_bytes_are_not_equal(tmp_path: Path) -> None:
    roles, workspace = _workspace(tmp_path)
    (roles / "engineer-demo" / "refs" / "note.md").write_bytes(b"a\xff\n")
    (workspace / ".trae" / "skills" / "demo-skill" / "refs" / "note.md").write_bytes(b"a\xfe\n")
    assert ("RP-008", FAIL) in _codes(roles, workspace)


def test_fingerprint_keeps_lone_surrogates_apart() -> None:
    first = AiHandoffService._fingerprint(None, {"text": "a\ud800"})  # type: ignore[arg-type]
    second = AiHandoffService._fingerprint(None, {"text": "a\udc00"})  # type: ignore[arg-type]
    plain = AiHandoffService._fingerprint(None, {"text": "abc"})  # type: ignore[arg-type]
    assert first != second
    assert plain == hashlib.sha256(b'{"text":"abc"}').hexdigest()


def test_scope_fingerprint_hashes_the_exact_path_bytes(tmp_path: Path) -> None:
    runner = DogfoodRunner.__new__(DogfoodRunner)
    (tmp_path / "main.py").write_bytes(b"x")
    expected = hashlib.sha256()
    expected.update(b"main.py\0x\0")
    assert runner._scope_fingerprint(tmp_path) == expected.hexdigest()


@pytest.mark.skipif(os.name == "nt", reason="a file name with undecodable bytes cannot be created on Windows")
def test_scope_fingerprint_tells_apart_names_that_differ_only_in_undecodable_bytes(tmp_path: Path) -> None:
    """Both names decode to 'a?' with errors='replace'; the exact file-system bytes keep them apart."""

    runner = DogfoodRunner.__new__(DogfoodRunner)
    first, second = tmp_path / "one", tmp_path / "two"
    for root, name in ((first, b"a\xff"), (second, b"a\xfe")):
        folder = root / "00_Infrastructure" / "auto_pm"
        folder.mkdir(parents=True)
        Path(os.fsdecode(os.path.join(os.fsencode(folder), name))).write_bytes(b"same")
    assert runner._scope_fingerprint(first) != runner._scope_fingerprint(second)
