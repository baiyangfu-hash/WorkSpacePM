"""``find_on_path``: PATH lookup that never lets the current directory (or anything relative) stand in for a program.

The Windows rules are exercised on every platform by injecting ``windows=True``; the callers that used ``shutil.which``
(``gh`` in the PR opener, ``codex`` in the local executor) are checked against a program planted in the current directory.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from typing import Any

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


def test_windows_takes_a_quoted_path_directory_that_holds_spaces(tmp_path: Path) -> None:
    """Windows writes ``PATH`` entries with spaces in double quotes (``"C:\\Program Files\\Git\\cmd"``); the quotes are not part of the name."""
    folder = tmp_path / "Program Files" / "Git cmd"
    chosen = _touch(folder / "git.exe")
    cwd = str(tmp_path / "elsewhere")
    assert find_on_path("git", path=f'"{folder}"', windows=True, cwd=cwd) == chosen
    assert find_on_path("git", path=f'{tmp_path / "nothing"};  "{folder}"  ', windows=True, cwd=cwd) == chosen
    # A quoted entry that is the working directory is still the working directory.
    assert find_on_path("git", path=f'"{folder}"', windows=True, cwd=str(folder)) is None
    # A quoted relative entry is still relative.
    assert find_on_path("git", path='"Program Files"', windows=True, cwd=str(tmp_path)) is None


def test_windows_accepts_only_exe_unless_the_caller_asks_for_more(tmp_path: Path) -> None:
    for suffix in (".bat", ".cmd", ".com", ".ps1", ""):
        _touch(tmp_path / "bin" / f"gh{suffix}")
    where: dict[str, Any] = {"path": str(tmp_path / "bin"), "windows": True, "cwd": str(tmp_path / "elsewhere")}
    assert find_on_path("gh", **where) is None
    assert find_on_path("gh", extensions=(".exe", ".cmd"), **where) == str(tmp_path / "bin" / "gh.cmd")
    _touch(tmp_path / "bin" / "gh.exe")
    assert find_on_path("gh", **where) == str(tmp_path / "bin" / "gh.exe")


def test_windows_takes_a_name_that_already_carries_an_allowed_extension_as_it_is(tmp_path: Path) -> None:
    _touch(tmp_path / "bin" / "git.exe")
    where: dict[str, Any] = {"path": str(tmp_path / "bin"), "windows": True, "cwd": str(tmp_path / "elsewhere")}
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
    spaced = tmp_path / "Program Files" / "Git"
    for folder in (good, spaced):
        _touch(folder / "gh.exe")
        _touch(folder / "gh")
        _touch(folder / "git.cmd")
    # Plain, ``.exe``-suffixed (any case), a ``.cmd`` shim name, and a name without a match.
    for name in ("gh", "gh.exe", "GH.EXE", "git.cmd", "git", "nothing"):
        for windows, separator in ((True, ";"), (False, ":")):
            for entries in (
                ["", ".", "rel", str(cwd)],
                [str(cwd), str(good)],
                [str(tmp_path / "nothing"), str(good)],
                [f'"{spaced}"', str(good)],
                [f'  "{cwd}"  ', f'"{spaced}"'],
            ):
                joined = separator.join(entries)
                ours = find_on_path(name, path=joined, windows=windows, cwd=str(cwd))
                theirs = actions.find_on_path(name, path=joined, windows=windows, cwd=str(cwd))
                assert ours == theirs, (name, windows, entries)


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


def which_call_lines(source: str | bytes) -> list[int]:
    """Lines that use ``shutil.which`` in any spelling: ``shutil.which``, ``import shutil as s`` + ``s.which`` and ``from shutil import which [as w]``."""
    tree = ast.parse(source)
    shutil_names: set[str] = set()
    which_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            shutil_names.update(alias.asname or alias.name for alias in node.names if alias.name == "shutil")
        elif isinstance(node, ast.ImportFrom) and node.module == "shutil":
            which_names.update(alias.asname or alias.name for alias in node.names if alias.name == "which")
    lines: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "which":
            if isinstance(node.value, ast.Name) and node.value.id in shutil_names:
                lines.append(node.lineno)
        elif isinstance(node, ast.Name) and node.id in which_names and isinstance(node.ctx, ast.Load):
            lines.append(node.lineno)
    return sorted(lines)


def test_the_guard_recognises_every_spelling_and_ignores_other_which_names() -> None:
    assert which_call_lines("import shutil\nshutil.which('x')\n") == [2]
    assert which_call_lines("import shutil as s\ns.which('x')\n") == [2]
    assert which_call_lines("from shutil import which as w\nw('x')\n") == [2]
    assert which_call_lines("import shutil\nshutil.copy('a', 'b')\n") == []
    assert which_call_lines("class A:\n    def which(self): ...\nA().which()\n") == []


def test_the_cockpit_package_never_looks_a_program_up_with_shutil_which() -> None:
    """``shutil.which`` searches the working directory first on Windows and trusts an empty entry on POSIX: a new call site turns this red."""
    package = Path(__file__).resolve().parents[2] / "auto_pm"
    offenders = [
        f"{source.relative_to(package)}:{line}" for source in sorted(package.rglob("*.py")) for line in which_call_lines(source.read_bytes())
    ]
    assert offenders == [], f"use auto_pm.infrastructure.executable_lookup.find_on_path instead: {offenders}"
