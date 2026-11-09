"""TD-SW008-237 / D-162 card 2: the eight callers whose Git output carries PATHS refuse output that is not UTF-8.

Each caller used to decode with ``errors="replace"``, so two different undecodable names both became '?' and a scope, protected-path or
identity comparison could not tell them from a harmless one.  The tests replace ``subprocess.run`` inside ``git_timeout`` with a fake
that answers like the OS would (bytes, or text when the caller asks for ``text=True``), so they run the same on Windows, where a file
name that is not UTF-8 cannot be created.  A caller moved back to the lenient function gets '?' and does not raise: the test fails.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from auto_pm.application.core import project_delete_guard
from auto_pm.application.core.dogfood_runner import DogfoodIsolationError, DogfoodRunner
from auto_pm.application.core.implementation_card_service import (
    ImplementationCardError,
    ImplementationCardService,
)
from auto_pm.application.core.pr_open_service import PrOpenRefusedError, PrOpenService
from auto_pm.infrastructure import (
    ignored_file_scan,
    plc_doc_hook,
    plc_git_marker_guard,
)
from auto_pm.infrastructure.git_timeout import run_git_bounded_strict_text
from auto_pm.infrastructure.local_executor import LocalCodexExecutor, LocalExecutionError

BAD = b"src/\xff\xfe.scl"
GOOD = "路径/é.scl".encode()


def _answer(monkeypatch: pytest.MonkeyPatch, stdout: bytes, stderr: bytes = b"") -> None:
    """Make every bounded Git run answer ``stdout``/``stderr`` as the OS would for the mode the caller asked for."""

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        if kwargs.get("text"):
            errors = kwargs.get("errors", "strict")
            return subprocess.CompletedProcess(command, 0, stdout.decode("utf-8", errors), stderr.decode("utf-8", errors))
        return subprocess.CompletedProcess(command, 0, stdout, stderr)

    monkeypatch.setattr("auto_pm.infrastructure.git_timeout.subprocess.run", fake_run)


def _dogfood(tmp: Path) -> object:
    return DogfoodRunner._run_git(object.__new__(DogfoodRunner), tmp, "status", "--porcelain")


def _card(tmp: Path) -> object:
    return ImplementationCardService._git(tmp, "diff", "--name-only", "-z")


def _pr_open(tmp: Path) -> object:
    return PrOpenService._git(tmp, "diff", "--name-only", "-z")


def _delete_guard(tmp: Path) -> object:
    return project_delete_guard.uncommitted_blockers(tmp, tmp / "p")


def _ignored(tmp: Path) -> object:
    return ignored_file_scan.ignored_among(tmp, ["a.txt"])


def _executor(tmp: Path) -> object:
    return LocalCodexExecutor._git_output(object.__new__(LocalCodexExecutor), tmp, "ls-files", "-z")


def _doc_hook(tmp: Path) -> object:
    return plc_doc_hook._git(tmp, ["ls-files", "-z"])


def _marker_guard(tmp: Path) -> object:
    return plc_git_marker_guard._git(tmp, "ls-files", "-z")


# (caller, what it does with a refused decode).  ``refuses`` callers raise their own error class; the delete guard turns it into a blocker.
RAISING: list[tuple[str, Callable[[Path], object], type[Exception]]] = [
    ("dogfood_runner", _dogfood, DogfoodIsolationError),
    ("implementation_card_service", _card, ImplementationCardError),
    ("pr_open_service", _pr_open, PrOpenRefusedError),
    ("ignored_file_scan", _ignored, ignored_file_scan.IgnoreScanError),
    ("local_executor", _executor, LocalExecutionError),
    ("plc_doc_hook", _doc_hook, RuntimeError),
    ("plc_git_marker_guard", _marker_guard, plc_git_marker_guard.GitMarkerGuardError),
]


@pytest.mark.parametrize(("name", "call", "error"), RAISING, ids=[row[0] for row in RAISING])
def test_a_name_that_is_not_utf8_is_refused_with_the_callers_own_error(
    name: str, call: Callable[[Path], object], error: type[Exception], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answer(monkeypatch, BAD)
    with pytest.raises(error, match="UTF-8"):
        call(tmp_path)


@pytest.mark.parametrize(("name", "call", "error"), RAISING, ids=[row[0] for row in RAISING])
def test_stderr_that_is_not_utf8_is_refused_too(
    name: str, call: Callable[[Path], object], error: type[Exception], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answer(monkeypatch, b"", BAD)
    with pytest.raises(error, match="UTF-8"):
        call(tmp_path)


def test_the_delete_guard_blocks_instead_of_reading_a_question_mark(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _answer(monkeypatch, b"?? " + BAD + b"\n")
    blockers = project_delete_guard.uncommitted_blockers(tmp_path, tmp_path / "p")
    assert len(blockers) == 1 and "UTF-8" in blockers[0] and "项目目录里有没提交的改动" not in blockers[0]


@pytest.mark.parametrize(("name", "call", "error"), RAISING, ids=[row[0] for row in RAISING])
def test_valid_non_ascii_text_still_passes(
    name: str, call: Callable[[Path], object], error: type[Exception], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _answer(monkeypatch, GOOD)
    try:
        call(tmp_path)
    except error as caught:  # a later check of the caller may refuse the made-up answer, but not for its encoding
        assert "UTF-8" not in str(caught)


# --- the strict function on a REAL child process: runs on Windows too (no file name involved) ---------------------------------------


class _RefusedError(RuntimeError):
    pass


def _emit(stream: str, payload: bytes) -> list[str]:
    return [sys.executable, "-c", f"import sys; sys.{stream}.buffer.write({payload!r})"]


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_a_real_process_that_writes_bad_bytes_is_refused_on_either_stream(stream: str, tmp_path: Path) -> None:
    with pytest.raises(_RefusedError, match="UTF-8"):
        run_git_bounded_strict_text(_emit(stream, BAD), default_timeout=60.0, error_cls=_RefusedError, where=tmp_path, capture_output=True)


def test_a_real_process_that_writes_valid_text_on_both_streams_is_read_back(tmp_path: Path) -> None:
    command = [sys.executable, "-c", f"import sys; sys.stdout.buffer.write({GOOD!r}); sys.stderr.buffer.write({GOOD!r})"]
    done = run_git_bounded_strict_text(command, default_timeout=60.0, error_cls=_RefusedError, where=tmp_path, capture_output=True)
    assert done.stdout == GOOD.decode() and done.stderr == GOOD.decode()
