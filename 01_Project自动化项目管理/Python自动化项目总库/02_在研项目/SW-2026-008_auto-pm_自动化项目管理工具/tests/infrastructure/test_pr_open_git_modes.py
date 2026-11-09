"""D-171: ``PrOpenService`` reads Git in two modes, so a succeeded push cannot fail afterwards on the remote's encoding.

``_git`` (strict) is only for ``diff --name-only -z``, whose names are compared with the claimed scope.  ``_git_text`` (lenient) serves
everything else: push / fetch / branch (exit code, echoed on failure), rev-parse / rev-list (ids), the task card and commit messages
(content, not paths).  The tests replace ``subprocess.run`` inside ``git_timeout`` with a fake that answers in bytes or in text like the OS.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from auto_pm.application.core.pr_open_service import PrOpenRefusedError, PrOpenService

GBK = b"\xd6\xd0\xce\xc4"


def _fake(monkeypatch: pytest.MonkeyPatch, *, stdout: bytes = b"", stderr: bytes = b"", code: int = 0) -> list[list[str]]:
    seen: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        seen.append(command)
        if kwargs.get("text"):
            errors = kwargs.get("errors", "strict")
            return subprocess.CompletedProcess(command, code, stdout.decode("utf-8", errors), stderr.decode("utf-8", errors))
        return subprocess.CompletedProcess(command, code, stdout, stderr)

    monkeypatch.setattr("auto_pm.infrastructure.git_timeout.subprocess.run", run)
    return seen


def _service() -> PrOpenService:
    service = object.__new__(PrOpenService)
    service._sleep = lambda _seconds: None
    service._root = Path("/tmp")
    return service


def test_a_push_that_succeeded_goes_on_when_the_remote_message_is_not_utf8(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen = _fake(monkeypatch, stderr=b"remote: " + GBK + b"\n")
    _service()._push(tmp_path, "claude/x", "a" * 40)
    assert [command[3] for command in seen] == ["push", "branch"], "the upstream is set after the push, the flow is not cut off"


def test_the_task_card_content_is_read_even_when_it_is_not_utf8(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake(monkeypatch, stdout=b"# card " + GBK + b"\n")
    assert "card" in _service()._card_at_base("card.md", "b" * 40)


def test_commit_messages_are_read_even_when_they_are_not_utf8(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake(monkeypatch, stdout=b"x " + GBK)
    commits = _service()._commits(tmp_path, "b" * 40)
    assert len(commits) == 2  # rev-list and show answer the same bytes: the point is that neither refuses


def test_the_changed_file_names_stay_strict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake(monkeypatch, stdout=b"src/" + GBK + b".scl\0")
    with pytest.raises(PrOpenRefusedError, match="UTF-8"):
        _service()._safety_declaration(tmp_path, "b" * 40, "否")
