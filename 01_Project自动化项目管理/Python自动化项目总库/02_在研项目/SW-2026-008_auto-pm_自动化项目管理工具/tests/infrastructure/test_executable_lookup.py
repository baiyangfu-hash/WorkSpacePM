"""``find_on_path``: PATH lookup that never lets the current directory (or anything relative) stand in for a program.

The Windows rules are exercised on every platform by injecting ``windows=True``; the callers that used ``shutil.which``
(``gh`` in the PR opener, ``codex`` in the local executor) are checked against a program planted in the current directory.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from auto_pm.application.core import pr_open_service
from auto_pm.infrastructure.executable_lookup import find_on_path, windows_path_extensions

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _touch(path: Path, executable: bool = True) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a real program")
    path.chmod(0o755 if executable else 0o644)
    return str(path)


def test_windows_skips_the_current_directory_relative_entries_and_empty_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    cwd, real = tmp_path / "repo", tmp_path / "tools"
    _touch(cwd / "gh.exe")
    _touch(tmp_path / "rel" / "gh.exe")
    entries = ["", ".", "rel", str(cwd), f'"{cwd}"', str(tmp_path / "empty")]
    assert find_on_path("gh", path=";".join(entries), windows=True, cwd=str(cwd)) is None
    chosen = _touch(real / "gh.exe")
    found = find_on_path("gh", path=";".join([*entries, str(real)]), windows=True, cwd=str(cwd))
    assert found == chosen and os.path.isabs(found)


def test_windows_accepts_only_exe_unless_the_caller_asks_for_more(tmp_path: Path) -> None:
    for suffix in (".bat", ".cmd", ".com", ".ps1", ""):
        _touch(tmp_path / "bin" / f"gh{suffix}")
    where = {"path": str(tmp_path / "bin"), "windows": True, "cwd": str(tmp_path / "elsewhere")}
    assert find_on_path("gh", **where) is None
    assert find_on_path("gh", extensions=(".exe", ".cmd"), **where) == str(tmp_path / "bin" / "gh.cmd")
    _touch(tmp_path / "bin" / "gh.exe")
    assert find_on_path("gh", **where) == str(tmp_path / "bin" / "gh.exe")


def test_windows_takes_a_name_that_already_carries_an_allowed_extension_as_it_is(tmp_path: Path) -> None:
    _touch(tmp_path / "bin" / "git.exe")
    where = {"path": str(tmp_path / "bin"), "windows": True, "cwd": str(tmp_path / "elsewhere")}
    assert find_on_path("git.exe", **where) == str(tmp_path / "bin" / "git.exe")
    assert find_on_path("git.cmd", **where) is None


def test_the_path_extension_list_follows_pathext(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATHEXT", ".COM;;.Exe;.CMD")
    assert windows_path_extensions() == (".com", ".exe", ".cmd")


@pytest.mark.skipif(os.name == "nt", reason="POSIX semantics: colon separator, execute bit")
def test_posix_skips_an_empty_entry_and_needs_the_execute_bit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil

    cwd = tmp_path / "repo"
    _touch(cwd / "gh")
    monkeypatch.chdir(cwd)
    assert shutil.which("gh", path=":/nonexistent") == "gh"  # baseline: the standard library takes an empty entry as "here"
    assert find_on_path("gh", path=":/nonexistent:.", cwd=str(cwd)) is None
    _touch(tmp_path / "plain" / "gh", executable=False)
    assert find_on_path("gh", path=str(tmp_path / "plain"), cwd=str(cwd)) is None
    good = _touch(tmp_path / "tools" / "gh")
    assert find_on_path("gh", path=f"{tmp_path / 'plain'}:{tmp_path / 'tools'}", cwd=str(cwd)) == good


def test_the_copy_the_scripts_keep_answers_the_same_as_this_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``scripts/cockpit_board/actions.py`` cannot import ``auto_pm``; the two copies must not drift apart."""
    monkeypatch.syspath_prepend(str(SCRIPTS))
    from cockpit_board import actions

    cwd = tmp_path / "repo"
    _touch(cwd / "gh.exe")
    _touch(cwd / "gh")
    good = tmp_path / "tools"
    _touch(good / "gh.exe")
    _touch(good / "gh")
    for windows, separator in ((True, ";"), (False, ":")):
        for entries in (
            ["", ".", "rel", str(cwd)],
            [str(cwd), str(good)],
            [str(tmp_path / "nothing"), str(good)],
        ):
            joined = separator.join(entries)
            ours = find_on_path("gh", path=joined, windows=windows, cwd=str(cwd))
            theirs = actions.find_on_path("gh", path=joined, windows=windows, cwd=str(cwd))
            assert ours == theirs, (windows, entries)


@pytest.mark.skipif(os.name == "nt", reason="plants an executable named gh and relies on POSIX PATH rules")
def test_the_pr_opener_never_runs_a_gh_planted_in_the_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = tmp_path / "ran.txt"
    planted = tmp_path / "gh"
    planted.write_text(f"#!/bin/sh\necho ran > {marker}\n", encoding="utf-8")
    planted.chmod(0o755)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", ":" + str(tmp_path / "nowhere"))  # the empty entry means "here" to shutil.which

    with pytest.raises(pr_open_service.PrOpenRefusedError, match="gh"):
        pr_open_service.default_gh(["--version"], None)
    assert pr_open_service.gh_status() == (False, False)
    assert not marker.exists()
    assert sys.platform != "win32"
