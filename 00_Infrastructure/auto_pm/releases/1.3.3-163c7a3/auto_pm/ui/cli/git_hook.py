"""auto_pm.ui.cli.git_hook - Git 提交硬锁门禁命令行组"""

from __future__ import annotations

import stat
import sys
from pathlib import Path

import click
from rich.console import Console

from auto_pm.app_context import AppContext
from auto_pm.infrastructure.git_hook_enforcer import (
    StagedSnapshotError,
    enforce_commit_msg,
    enforce_pre_commit,
    enforce_release_ledger_gate,
    get_staged_snapshot,
)
from auto_pm.ui.cli.caller_path import CallerPath

console = Console()


def _workspace(ctx: click.Context) -> Path:
    app_ctx: AppContext = ctx.obj
    return Path(app_ctx.workspace_root)


def _control_root(ctx: click.Context) -> Path:
    app_ctx: AppContext = ctx.obj
    return Path(app_ctx.control_root)


def make_stdio_encoding_safe() -> None:
    """让钩子输出里的 emoji 在 GBK 等窄编码终端上也不抛 UnicodeEncodeError（TD-SW008-015）。

    钩子（``git_hook_enforcer`` / ``plc_doc_hook``）直接 ``print`` 带 ❌⚠️🔍 的提示；终端编码编不出来时，
    默认的 ``errors="strict"`` 会让整个提交钩子崩掉，把“提示”变成“事故”。只改错误处理方式（编不出的字符
    换成 ``?``），不改编码本身，所以 UTF-8 终端输出一字不变。
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue  # pytest capture 等没有 reconfigure 的流
        try:
            reconfigure(errors="replace")
        except (ValueError, OSError):
            pass


@click.group(name="git-hook")
def git_hook_group() -> None:
    """Git 提交硬锁物理门禁 (Git Hook Enforcer)"""
    make_stdio_encoding_safe()


@git_hook_group.command(name="pre-commit")
@click.pass_context
def cmd_pre_commit(ctx: click.Context) -> None:
    """执行 pre-commit 台账一致性校验。"""
    ws = _workspace(ctx)
    ctrl = _control_root(ctx)
    code = enforce_pre_commit(ws, control_root=ctrl)
    if code != 0:
        ctx.exit(code)


@git_hook_group.command(name="release-gate")
@click.pass_context
def cmd_release_gate(ctx: click.Context) -> None:
    """执行发布前全局台账一致性校验。"""
    ctrl = _control_root(ctx)
    code = enforce_release_ledger_gate(ctrl)
    if code != 0:
        ctx.exit(code)


@git_hook_group.command(name="commit-msg")
@click.argument("msg_file", type=CallerPath(exists=True))
@click.pass_context
def cmd_commit_msg(ctx: click.Context, msg_file: str) -> None:
    """执行 commit-msg 生产代码关联单据强校验。"""
    ws = _workspace(ctx)
    ctrl = _control_root(ctx)
    code = enforce_commit_msg(ws, Path(msg_file), control_root=ctrl)
    if code != 0:
        ctx.exit(code)


@git_hook_group.command(name="preflight")
@click.argument("msg_file", type=CallerPath(exists=True, path_type=Path))
@click.pass_context
def cmd_preflight(ctx: click.Context, msg_file: Path) -> None:
    """以同一个不可变暂存快照执行提交前只读预检。"""
    ws = _workspace(ctx)
    ctrl = _control_root(ctx)
    try:
        staged_snapshot = get_staged_snapshot(ws)
    except StagedSnapshotError as error:
        console.print(f"[red]错误: 无法读取 Git 暂存区: {error}[/red]")
        ctx.exit(1)

    pre_commit_code = enforce_pre_commit(ws, staged_snapshot, control_root=ctrl)
    commit_msg_code = enforce_commit_msg(ws, msg_file, staged_snapshot, control_root=ctrl)
    if pre_commit_code != 0:
        ctx.exit(pre_commit_code)
    if commit_msg_code != 0:
        ctx.exit(commit_msg_code)


@git_hook_group.command(name="install")
@click.pass_context
def cmd_install(ctx: click.Context) -> None:
    """安装/激活工作区 Git 物理门禁钩子 (.git/hooks/pre-commit 与 commit-msg)。"""
    ws = _workspace(ctx)
    git_dir = ws / ".git"
    if not git_dir.is_dir():
        console.print(f"[red]错误: 未在工作区找到 .git 目录: {ws}[/red]")
        ctx.exit(1)

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    pre_commit_script = """#!/bin/sh
# Resolve the current worktree separately from the PRIMARY control root.  The
# stable launcher/runtime comes from the primary root, while Git evidence must
# be read from the worktree whose index triggered this hook.
WORKTREE_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 1
WORKTREE_ROOT=$(cd "$WORKTREE_ROOT" && pwd) || exit 1
GIT_COMMON_DIR=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || GIT_COMMON_DIR=$(git rev-parse --git-common-dir)
case "$GIT_COMMON_DIR" in
    /*) ;;
    *) GIT_COMMON_DIR=$(cd "$GIT_COMMON_DIR" && pwd) ;;
esac
PROJECT_ROOT=$(dirname "$GIT_COMMON_DIR")
# Linux images often ship only python3; keep the Windows default "python" first.
PYTHON_EXE="python"
if ! command -v python >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
    PYTHON_EXE="python3"
fi
if [ -f "$PROJECT_ROOT/.venv/Scripts/python.exe" ]; then
    PYTHON_EXE="$PROJECT_ROOT/.venv/Scripts/python.exe"
elif [ -f "$PROJECT_ROOT/.venv/bin/python" ]; then
    PYTHON_EXE="$PROJECT_ROOT/.venv/bin/python"
fi

"$PYTHON_EXE" "$PROJECT_ROOT/main.py" -w "$WORKTREE_ROOT" --control-root "$PROJECT_ROOT" git-hook pre-commit
exit $?
"""

    commit_msg_script = """#!/bin/sh
# Resolve the current worktree separately from the PRIMARY control root.  The
# stable launcher/runtime comes from the primary root, while Git evidence must
# be read from the worktree whose index triggered this hook.
WORKTREE_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || exit 1
WORKTREE_ROOT=$(cd "$WORKTREE_ROOT" && pwd) || exit 1
GIT_COMMON_DIR=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || GIT_COMMON_DIR=$(git rev-parse --git-common-dir)
case "$GIT_COMMON_DIR" in
    /*) ;;
    *) GIT_COMMON_DIR=$(cd "$GIT_COMMON_DIR" && pwd) ;;
esac
GIT_COMMON_DIR=$(cd "$GIT_COMMON_DIR" && pwd) || exit 1
PROJECT_ROOT=$(dirname "$GIT_COMMON_DIR")
# Linux images often ship only python3; keep the Windows default "python" first.
PYTHON_EXE="python"
if ! command -v python >/dev/null 2>&1 && command -v python3 >/dev/null 2>&1; then
    PYTHON_EXE="python3"
fi
if [ -f "$PROJECT_ROOT/.venv/Scripts/python.exe" ]; then
    PYTHON_EXE="$PROJECT_ROOT/.venv/Scripts/python.exe"
elif [ -f "$PROJECT_ROOT/.venv/bin/python" ]; then
    PYTHON_EXE="$PROJECT_ROOT/.venv/bin/python"
fi

# Git may pass .git/COMMIT_EDITMSG in the primary worktree and an absolute
# common-git-dir path in a linked worktree.  Resolve the path before the
# launcher can switch runtime context, and fail closed when it is unreadable.
MSG_FILE_DIR=$(dirname -- "$1") || exit 1
MSG_FILE_NAME=$(basename -- "$1") || exit 1
MSG_FILE_DIR_ABS=$(cd -- "$MSG_FILE_DIR" 2>/dev/null && pwd) || {
    echo "[auto-pm commit-msg] cannot resolve message directory: $MSG_FILE_DIR" >&2
    exit 1
}
MSG_FILE="$MSG_FILE_DIR_ABS/$MSG_FILE_NAME"
if [ ! -r "$MSG_FILE" ]; then
    echo "[auto-pm commit-msg] message file is not readable: $MSG_FILE" >&2
    exit 1
fi
case "$MSG_FILE" in
    "$GIT_COMMON_DIR/COMMIT_EDITMSG"|"$GIT_COMMON_DIR"/worktrees/*/COMMIT_EDITMSG) ;;
    *)
        echo "[auto-pm commit-msg] message file is outside Git metadata: $MSG_FILE" >&2
        exit 1
        ;;
esac

"$PYTHON_EXE" "$PROJECT_ROOT/main.py" -w "$WORKTREE_ROOT" --control-root "$PROJECT_ROOT" git-hook commit-msg "$MSG_FILE"
exit $?
"""

    pre_commit_file = hooks_dir / "pre-commit"
    commit_msg_file = hooks_dir / "commit-msg"

    pre_commit_file.write_text(pre_commit_script, encoding="utf-8", newline="\n")
    commit_msg_file.write_text(commit_msg_script, encoding="utf-8", newline="\n")
    # On POSIX Git silently skips a hook without the execute bit, which would turn the gate off.
    for hook_file in (pre_commit_file, commit_msg_file):
        hook_file.chmod(hook_file.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    console.print("[green]✅ Git 物理门禁硬锁已成功激活！[/green]")
    console.print(f"  - pre-commit: {pre_commit_file}")
    console.print(f"  - commit-msg: {commit_msg_file}")
