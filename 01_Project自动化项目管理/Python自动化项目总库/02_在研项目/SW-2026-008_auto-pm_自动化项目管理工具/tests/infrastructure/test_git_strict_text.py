"""TD-SW008-237 / D-162: Git output that carries PATHS is decoded strictly, so a name that is not UTF-8 is refused instead of read as '?'.

``run_git_bounded_text`` decodes with ``errors="replace"``; two different undecodable names then both become '?' and a scope or
protected-path comparison cannot tell them from a harmless one.  ``run_git_bounded_strict_text`` decodes the captured bytes itself (a
``text=True`` decode runs in a reader thread, and on Windows a decode error there is swallowed and the caller gets ``stdout=None``).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from auto_pm.infrastructure import git_hook_enforcer as hook
from auto_pm.infrastructure.git_timeout import run_git_bounded_strict_text, run_git_bounded_text

needs_raw_names = pytest.mark.skipif(sys.platform == "win32", reason="Windows file names are UTF-16: no undecodable name can exist")
BAD_NAME = os.fsdecode(b"bad\xff.txt")


class _RefusedError(RuntimeError):
    pass


def _child(payload: bytes, *, code: int = 0) -> list[str]:
    return [sys.executable, "-c", f"import sys; sys.stdout.buffer.write({payload!r}); sys.exit({code})"]


def _strict(command: list[str], tmp_path: Path, **kwargs: object) -> subprocess.CompletedProcess[str]:
    return run_git_bounded_strict_text(command, default_timeout=60.0, error_cls=_RefusedError, where=tmp_path, capture_output=True, **kwargs)


# --- the function itself --------------------------------------------------------------------------------------------------


def test_undecodable_output_raises_the_callers_error(tmp_path: Path) -> None:
    with pytest.raises(_RefusedError, match="UTF-8"):
        _strict(_child(b"src/\xff\xfe.scl"), tmp_path)


def test_valid_text_comes_back_unchanged_even_when_it_is_not_ascii(tmp_path: Path) -> None:
    done = _strict(_child("路径/é.scl".encode()), tmp_path)
    assert done.returncode == 0 and done.stdout == "路径/é.scl" and done.stderr == ""


def test_check_true_keeps_its_meaning_and_carries_the_decoded_output(tmp_path: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError) as caught:
        _strict(_child(b"out", code=3), tmp_path, check=True)
    assert caught.value.returncode == 3 and caught.value.output == "out"


def test_a_text_input_is_sent_as_utf8(tmp_path: Path) -> None:
    command = [sys.executable, "-c", "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())"]
    assert _strict(command, tmp_path, input="路径\0").stdout == "路径\0"


@pytest.mark.parametrize("option", ["text", "encoding", "errors", "universal_newlines"])
def test_the_caller_cannot_ask_for_a_decode_of_its_own(tmp_path: Path, option: str) -> None:
    with pytest.raises(TypeError):
        _strict(_child(b"x"), tmp_path, **{option: "utf-8" if option != "text" else True})


def test_the_lenient_function_is_still_lenient_for_the_callers_that_only_need_an_exit_code(tmp_path: Path) -> None:
    done = run_git_bounded_text(_child(b"a\xffb"), default_timeout=60.0, error_cls=_RefusedError, where=tmp_path, capture_output=True)
    assert done.stdout == "a\ufffdb"


# --- the commit hook: every place that reads paths --------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _repo_with(tmp_path: Path, name: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / name).write_text("x", encoding="utf-8")
    _git(repo, "add", "--", name)
    return repo


@needs_raw_names
def test_hook_staged_names_that_are_not_utf8_are_refused(tmp_path: Path) -> None:
    repo = _repo_with(tmp_path, BAD_NAME)
    with pytest.raises(RuntimeError, match="UTF-8"):
        hook.get_staged_files(repo)
    with pytest.raises(hook.StagedSnapshotError, match="UTF-8"):
        hook.get_staged_snapshot(repo)
    with pytest.raises(hook.StagedSnapshotError, match="UTF-8"):
        hook._git_z_lines(repo, ["ls-files", "-z"])


@needs_raw_names
def test_hook_ignored_additions_scan_refuses_a_name_that_is_not_utf8(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _repo_with(tmp_path, BAD_NAME)
    assert hook._enforce_ignored_additions(repo) == 1
    assert "拒绝提交" in capsys.readouterr().out


@needs_raw_names
def test_hook_roots_and_common_dir_under_a_path_that_is_not_utf8_are_refused(tmp_path: Path) -> None:
    parent = tmp_path / BAD_NAME
    parent.mkdir()
    repo = parent / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    with pytest.raises(hook.StagedSnapshotError):
        hook._resolve_git_common_dir(repo)
    with pytest.raises(hook.StagedSnapshotError):
        hook.validate_repository_roots(repo, None)


def test_hook_reads_ordinary_and_chinese_names_as_before(tmp_path: Path) -> None:
    repo = _repo_with(tmp_path, "中文 文件.txt")
    assert hook.get_staged_files(repo) == ["中文 文件.txt"]
    assert [entry.path for entry in hook.get_staged_snapshot(repo).entries] == ["中文 文件.txt"]
    assert hook._git_z_lines(repo, ["ls-files", "-z"]) == ["中文 文件.txt"]
    assert hook._resolve_git_common_dir(repo) == (repo / ".git").resolve()
    assert hook._enforce_ignored_additions(repo) == 0
