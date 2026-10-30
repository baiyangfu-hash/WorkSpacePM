"""Linux shell scripts keep their execute bit in Git (TD-SW008-154).

The install script reached the repository once through a tool that wrote bytes on Windows, which records no
execute bit, so ``./setup_env.sh`` failed on Linux. Git keeps the bit in the index mode, so it can be asserted
without running the script and the check works on any platform.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
MUST_BE_EXECUTABLE = ("00_Infrastructure/auto_pm/environment/setup_env.sh",)


def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-c", "core.quotepath=off", *args],
        cwd=HERE,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout


def _index_mode(workspace: Path, relative: str) -> str:
    out = _git("-C", str(workspace), "ls-files", "-s", "--", relative).strip()
    return out.split(maxsplit=1)[0] if out else ""


def _workspace() -> Path:
    try:
        return Path(_git("rev-parse", "--show-toplevel").strip())
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not inside a Git checkout")


@pytest.mark.parametrize("relative", MUST_BE_EXECUTABLE)
def test_listed_shell_scripts_are_tracked_as_executable(relative: str) -> None:
    mode = _index_mode(_workspace(), relative)
    assert mode, f"{relative} is not tracked by Git"
    assert mode == "100755", f"{relative} is tracked as {mode}; run: git update-index --chmod=+x {relative}"


def test_a_script_without_the_execute_bit_is_reported(tmp_path: Path) -> None:
    """Mutation evidence: a tracked file stored as 100644 yields a mode the assertion above would reject."""
    repo = tmp_path / "repo"
    repo.mkdir()
    for command in (["init", "-q"], ["config", "user.email", "t@example.invalid"], ["config", "user.name", "t"]):
        _git("-C", str(repo), *command)
    (repo / "plain.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo / "exec.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    _git("-C", str(repo), "add", "plain.sh", "exec.sh")
    _git("-C", str(repo), "update-index", "--chmod=+x", "exec.sh")
    assert _index_mode(repo, "plain.sh") == "100644"
    assert _index_mode(repo, "exec.sh") == "100755"
    assert _index_mode(repo, "missing.sh") == ""
