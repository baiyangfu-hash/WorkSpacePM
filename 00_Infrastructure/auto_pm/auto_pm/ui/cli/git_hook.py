"""auto_pm.ui.cli.git_hook - Git 提交硬锁门禁命令行组"""

from __future__ import annotations

from pathlib import Path
import click
from rich.console import Console

from auto_pm.app_context import AppContext
from auto_pm.infrastructure.git_hook_enforcer import (
    enforce_commit_msg,
    enforce_pre_commit,
)

console = Console()


def _workspace(ctx: click.Context) -> Path:
    app_ctx: AppContext = ctx.obj
    return Path(app_ctx.workspace_root)


@click.group(name="git-hook")
def git_hook_group() -> None:
    """Git 提交硬锁物理门禁 (Git Hook Enforcer)"""


@git_hook_group.command(name="pre-commit")
@click.pass_context
def cmd_pre_commit(ctx: click.Context) -> None:
    """执行 pre-commit 台账一致性校验。"""
    ws = _workspace(ctx)
    code = enforce_pre_commit(ws)
    if code != 0:
        ctx.exit(code)


@git_hook_group.command(name="commit-msg")
@click.argument("msg_file", type=click.Path(exists=True))
@click.pass_context
def cmd_commit_msg(ctx: click.Context, msg_file: str) -> None:
    """执行 commit-msg 生产代码关联单据强校验。"""
    ws = _workspace(ctx)
    code = enforce_commit_msg(ws, Path(msg_file))
    if code != 0:
        ctx.exit(code)


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
# Resolve the PRIMARY worktree (main workspace) so linked worktrees reuse the
# main .venv, and inject the container path per invocation (no editable/.pth).
GIT_COMMON_DIR=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || GIT_COMMON_DIR=$(git rev-parse --git-common-dir)
case "$GIT_COMMON_DIR" in
    /*) ;;
    *) GIT_COMMON_DIR=$(cd "$GIT_COMMON_DIR" && pwd) ;;
esac
PROJECT_ROOT=$(dirname "$GIT_COMMON_DIR")
CONTAINER="$PROJECT_ROOT/00_Infrastructure/auto_pm"
PYTHON_EXE="python"
if [ -f "$PROJECT_ROOT/.venv/Scripts/python.exe" ]; then
    PYTHON_EXE="$PROJECT_ROOT/.venv/Scripts/python.exe"
elif [ -f "$PROJECT_ROOT/.venv/bin/python" ]; then
    PYTHON_EXE="$PROJECT_ROOT/.venv/bin/python"
fi

PYTHONPATH="$CONTAINER" "$PYTHON_EXE" -m auto_pm -w "$PROJECT_ROOT" git-hook pre-commit
exit $?
"""

    commit_msg_script = """#!/bin/sh
# Resolve the PRIMARY worktree (main workspace) so linked worktrees reuse the
# main .venv, and inject the container path per invocation (no editable/.pth).
GIT_COMMON_DIR=$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null) || GIT_COMMON_DIR=$(git rev-parse --git-common-dir)
case "$GIT_COMMON_DIR" in
    /*) ;;
    *) GIT_COMMON_DIR=$(cd "$GIT_COMMON_DIR" && pwd) ;;
esac
PROJECT_ROOT=$(dirname "$GIT_COMMON_DIR")
CONTAINER="$PROJECT_ROOT/00_Infrastructure/auto_pm"
PYTHON_EXE="python"
if [ -f "$PROJECT_ROOT/.venv/Scripts/python.exe" ]; then
    PYTHON_EXE="$PROJECT_ROOT/.venv/Scripts/python.exe"
elif [ -f "$PROJECT_ROOT/.venv/bin/python" ]; then
    PYTHON_EXE="$PROJECT_ROOT/.venv/bin/python"
fi

PYTHONPATH="$CONTAINER" "$PYTHON_EXE" -m auto_pm -w "$PROJECT_ROOT" git-hook commit-msg "$1"
exit $?
"""

    pre_commit_file = hooks_dir / "pre-commit"
    commit_msg_file = hooks_dir / "commit-msg"

    pre_commit_file.write_text(pre_commit_script, encoding="utf-8", newline="\n")
    commit_msg_file.write_text(commit_msg_script, encoding="utf-8", newline="\n")

    console.print("[green]✅ Git 物理门禁硬锁已成功激活！[/green]")
    console.print(f"  - pre-commit: {pre_commit_file}")
    console.print(f"  - commit-msg: {commit_msg_file}")
