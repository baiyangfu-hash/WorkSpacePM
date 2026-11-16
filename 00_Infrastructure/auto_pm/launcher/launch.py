#!/usr/bin/env python3
"""Fail-closed stable launcher: verify first, then isolate release execution."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bootstrap import BootstrapError, purge_bytecode, resolve_release

_RELEASE_CHILD = (
    "import runpy, sys; release_dir = sys.argv[1]; "
    "sys.argv = ['main.py', *sys.argv[2:]]; "  # under -c argv[0] is '-c', which click prints in its usage line
    "sys.path.insert(0, release_dir); runpy.run_module('auto_pm', run_name='__main__')"
)
_UNSAFE_PYTHON_ENV = ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONUSERBASE")
_RESOLVE_ONLY_ARGUMENT = "--resolve-only"
_PURGE_BYTECODE_ARGUMENT = "--purge-bytecode"
_CALLER_CWD_ENV = "AUTO_PM_CALLER_CWD"
_WORKSPACE_ENV = "AUTO_PM_WORKSPACE"
_CONTROL_ROOT_ENV = "AUTO_PM_CONTROL_ROOT"
_WORKTREES = Path(".auto-pm") / "worktrees"
EXIT_WORKSPACE_INVALID = 5


class WorkspaceEnvironmentError(Exception):
    """The caller's AUTO_PM_WORKSPACE names neither this control root nor one of its own worktrees."""


def _same_path(left: Path, right: Path) -> bool:
    return os.path.normcase(str(left.resolve())) == os.path.normcase(str(right.resolve()))


def _inside(path: Path, parent: Path) -> bool:
    child = os.path.normcase(str(path.resolve()))
    folder = os.path.normcase(str(parent.resolve()))
    return child.startswith(folder.rstrip(os.sep) + os.sep)


def _child_workspace(workspace_root: Path, environ: dict[str, str]) -> str:
    """The project data the release reads: this control root, or a worktree the caller named on purpose.

    ``pm verify`` and ``long-run --worktree`` run the approved commands from the control root and hand them the Run's
    worktree as ``AUTO_PM_WORKSPACE`` (data) and this control root as ``AUTO_PM_CONTROL_ROOT`` (ledger); overwriting
    the first made every ``main.py`` acceptance command judge the control root instead of the worktree (a false green,
    found in the DJ-2026-005 trial run of 2026-11-16).  The worktree is kept only when it is one of this control root's own worktrees and
    the ledger is this control root, so a stale variable can never point the cockpit at another clone or a second ledger;
    any other value stops the launcher instead of being silently replaced (fail closed: a silent replacement is what hid
    the false green).
    """
    requested = environ.get(_WORKSPACE_ENV, "").strip()
    if not requested or _same_path(Path(requested), workspace_root):
        return str(workspace_root)
    control = environ.get(_CONTROL_ROOT_ENV, "").strip()
    worktree = Path(requested)
    if not (control and _same_path(Path(control), workspace_root)):
        raise WorkspaceEnvironmentError(
            f"{_WORKSPACE_ENV}={requested} 不是本控制根 {workspace_root}，又没有同时设 {_CONTROL_ROOT_ENV}={workspace_root}；"
            f"清掉 {_WORKSPACE_ENV} 再运行，或者改用 --workspace / --control-root 写明"
        )
    if not (worktree.is_dir() and _inside(worktree, workspace_root / _WORKTREES)):
        raise WorkspaceEnvironmentError(
            f"{_WORKSPACE_ENV}={requested} 不是本控制根的工位（{workspace_root / _WORKTREES} 下的目录）；"
            f"清掉 {_WORKSPACE_ENV} 再运行，或者改用 --workspace / --control-root 写明"
        )
    return requested


def _child_environment(cache_root: Path, workspace_root: Path) -> dict[str, str]:
    """Return an isolated child environment pinned to the owning workspace (or one of its own worktrees, see above)."""
    env = dict(os.environ)
    for name in _UNSAFE_PYTHON_ENV:
        env.pop(name, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env["RUFF_CACHE_DIR"] = str(cache_root)
    env[_WORKSPACE_ENV] = _child_workspace(workspace_root, env)
    return env


def main(argv: list[str] | None = None, *, container: Path | None = None) -> int:
    """Resolve and execute a release, or only resolve for isolation testing."""
    resolved_container = container or Path(__file__).resolve().parent.parent
    release_args = list(sys.argv[1:] if argv is None else argv)
    if release_args == [_PURGE_BYTECODE_ARGUMENT]:
        try:
            removed = purge_bytecode(resolved_container)
        except BootstrapError as exc:
            print(f"launcher: 未清除任何缓存: {exc}", file=sys.stderr)
            return exc.exit_code
        print(f"launcher: 已清除 {len(removed)} 处发布目录里的 Python 缓存")
        for entry in removed:
            print(f"  - {entry}")
        release_args = [_RESOLVE_ONLY_ARGUMENT]
    try:
        release_dir, slot, fallback_reason = resolve_release(resolved_container)
    except BootstrapError as exc:
        print(f"launcher: {exc}", file=sys.stderr)
        return exc.exit_code
    if fallback_reason:
        # Never fall back quietly: an older release cannot write the ledger and fails in confusing ways.
        print(
            "launcher: 警告：当前版本（active）没通过校验，已改用上一版本（previous）启动。"
            f"原因：{fallback_reason}。上一版本缺少之后修的功能，经驾驶舱接口的写入会被运行身份检查拒绝；"
            "请把这段提示原样发给维护驾驶舱的 AI 处理。",
            file=sys.stderr,
        )
    resolve_only = os.environ.get("AUTO_PM_ENTRY_RESOLVE_ONLY") == "1" or release_args == [_RESOLVE_ONLY_ARGUMENT]
    # Only the resolve/purge modes answer on stdout; a real run keeps stdout for the release, so `--json` output stays parseable (TD-SW008-031).
    print(f"launcher: release verified via {slot}: {release_dir}", file=sys.stdout if resolve_only else sys.stderr)
    if resolve_only:
        return 0
    command = [sys.executable, "-B", "-I", "-c", _RELEASE_CHILD, str(release_dir)]
    command.extend(release_args)
    cache_root = resolved_container / ".auto-pm" / "runtime-cache" / "ruff"
    workspace_root = resolved_container.parent.parent
    try:
        environment = _child_environment(cache_root, workspace_root)
    except WorkspaceEnvironmentError as exc:
        print(f"launcher: 没有启动：{exc}", file=sys.stderr)
        return EXIT_WORKSPACE_INVALID
    # The release runs with its own folder as the working directory; relative path arguments must still mean the caller's folder (TD-SW008-232).
    environment[_CALLER_CWD_ENV] = os.getcwd()
    return subprocess.run(
        command,
        cwd=release_dir,
        env=environment,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
