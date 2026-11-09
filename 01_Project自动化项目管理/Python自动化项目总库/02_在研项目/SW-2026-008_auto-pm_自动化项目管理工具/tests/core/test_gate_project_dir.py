"""D-151: the gate finds the project folder from the worktree, not from where the gate code itself runs.

A deployed release sits under ``00_Infrastructure/auto_pm/releases/<id>/``; the nearest ``pyproject.toml`` above it
belongs to the infrastructure copy, which has its own ``tests/``. Real git repositories in a temp folder.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from auto_pm.application.core.gate_run_service import GateRunError, project_dir_in

PROJECT = "01_Project/SW-2026-008_tool"
INFRA = "00_Infrastructure/auto_pm"
RELEASE_MODULE = f"{INFRA}/releases/1.0.0-abc/auto_pm/application/core/gate_run_service.py"


def _git(root: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,  # noqa: S607
    )


def _write(root: Path, relative: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x = 1\n", encoding="utf-8")


def _repo(
    tmp_path: Path, *, project: bool = True, infra: bool = True, second: bool = False
) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    if project:
        for name in ("pyproject.toml", "main.py", "auto_pm/__init__.py", "tests/test_a.py"):
            _write(root, f"{PROJECT}/{name}")
    if infra:  # the deployed copy: pyproject, tests and a release package, but no main.py
        for name in ("pyproject.toml", "auto_pm/__init__.py", "tests/test_b.py"):
            _write(root, f"{INFRA}/{name}")
    _write(root, RELEASE_MODULE)
    if second:
        for name in ("pyproject.toml", "main.py", "auto_pm/__init__.py", "tests/test_c.py"):
            _write(root, f"01_Project/other/{name}")
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "init")
    return root


def test_a_deployed_release_module_still_finds_the_project_folder(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    assert project_dir_in(root, root / RELEASE_MODULE) == root / PROJECT


def test_the_answer_does_not_depend_on_where_the_code_lives(tmp_path: Path) -> None:
    root = _repo(tmp_path)

    assert project_dir_in(root, root / PROJECT / "auto_pm" / "x.py") == root / PROJECT
    assert project_dir_in(root) == root / PROJECT


def test_a_second_worktree_of_the_repo_gets_its_own_project_folder(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    other = tmp_path / "station"
    _git(root, "worktree", "add", "-q", "-b", "side", str(other))

    assert project_dir_in(other, root / RELEASE_MODULE) == other / PROJECT


def test_two_project_like_folders_are_refused_with_both_named(tmp_path: Path) -> None:
    root = _repo(tmp_path, second=True)

    with pytest.raises(GateRunError, match="多个") as caught:
        project_dir_in(root, root / RELEASE_MODULE)
    assert "other" in str(caught.value) and "SW-2026-008_tool" in str(caught.value)


def test_no_project_in_the_worktree_never_falls_back_to_the_deployed_copy(tmp_path: Path) -> None:
    root = _repo(tmp_path, project=False)

    with pytest.raises(GateRunError, match="发布版"):
        project_dir_in(root, root / RELEASE_MODULE)


def test_no_project_in_the_worktree_may_use_a_source_checkout_location(tmp_path: Path) -> None:
    # a worktree whose files are not tracked yet: the source-location fallback still answers, as before
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    for name in ("pyproject.toml", "main.py", "auto_pm/__init__.py", "tests/test_a.py"):
        _write(root, f"{PROJECT}/{name}")

    assert project_dir_in(root, root / PROJECT / "auto_pm" / "x.py") == root / PROJECT
