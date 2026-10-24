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


def _child_environment(cache_root: Path, workspace_root: Path) -> dict[str, str]:
    """Return an isolated child environment pinned to the owning workspace."""
    env = dict(os.environ)
    for name in _UNSAFE_PYTHON_ENV:
        env.pop(name, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONNOUSERSITE"] = "1"
    env["RUFF_CACHE_DIR"] = str(cache_root)
    env["AUTO_PM_WORKSPACE"] = str(workspace_root)
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
    print(f"launcher: release verified via {slot}: {release_dir}")
    if os.environ.get("AUTO_PM_ENTRY_RESOLVE_ONLY") == "1" or release_args == [
        _RESOLVE_ONLY_ARGUMENT
    ]:
        return 0
    command = [sys.executable, "-B", "-I", "-c", _RELEASE_CHILD, str(release_dir)]
    command.extend(release_args)
    cache_root = resolved_container / ".auto-pm" / "runtime-cache" / "ruff"
    workspace_root = resolved_container.parent.parent
    return subprocess.run(
        command,
        cwd=release_dir,
        env=_child_environment(cache_root, workspace_root),
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
