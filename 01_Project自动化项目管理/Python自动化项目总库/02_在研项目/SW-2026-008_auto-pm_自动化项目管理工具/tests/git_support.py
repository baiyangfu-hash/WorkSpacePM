"""Shared Git helpers for test fixtures.

``subprocess.run(..., check=True)`` raises a ``CalledProcessError`` whose text carries no stderr, so a Git failure inside
a fixture (for example an occasional ``git worktree add`` exit 128 on CI) shows nothing about what Git said. Every helper
here raises ``GitFixtureError`` with the command, the exit code, the directory and Git's own stderr.
"""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path


class GitFixtureError(RuntimeError):
    """A Git command used to build a test fixture failed."""


def run_git(
    root: Path,
    *args: str,
    config: Sequence[str] = (),
    env: Mapping[str, str] | None = None,
    check: bool = True,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``git -C root [-c k=v ...] args`` and return the completed process (text, UTF-8, stdout and stderr captured).

    ``check=False`` returns a non-zero exit as a result instead of raising, for tests that assert on a refusal.
    ``timeout`` bounds the call; a hung Git raises ``subprocess.TimeoutExpired``.
    """
    command = ["git", "-C", str(root)]
    for item in config:
        command += ["-c", item]
    command += list(args)
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=None if env is None else dict(env),
        timeout=timeout,
    )
    if check and result.returncode != 0:
        raise GitFixtureError(
            f"git {' '.join(args)} 失败（退出码 {result.returncode}，目录 {root}）:\n{result.stderr.strip()}"
        )
    return result


def git_out(
    root: Path, *args: str, config: Sequence[str] = (), env: Mapping[str, str] | None = None, timeout: float | None = None
) -> str:
    """Stdout of a Git command with surrounding whitespace stripped."""
    return run_git(root, *args, config=config, env=env, timeout=timeout).stdout.strip()


def git_do(root: Path, *args: str, config: Sequence[str] = (), env: Mapping[str, str] | None = None) -> None:
    """Run a Git command for its effect; the output is not needed."""
    run_git(root, *args, config=config, env=env)
