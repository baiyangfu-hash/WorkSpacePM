"""``main.py long-run``: run a long command outside the agent's terminal, under a memory guard, and leave a status file as evidence.

Why: a regression of 40-60 minutes run directly in an agent terminal made the commit charge climb until the laptop was nearly dead
(11-03 memory P1); the same command detached stays flat.  ``start`` refuses on a machine that is already close to its commit limit,
launches the command detached from this terminal, and starts a guard that pauses it if the machine fills up.  ``status`` is read-only
and says how the job is doing; ``stop`` ends it.  The status file (``.auto-pm/long-run/<name>/status.json``) is what ``pm verify`` accepts
as the result of a long regression.

Exit codes: 0 done; 1 refused or failed (the message says why and what to type next).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import click

from auto_pm.app_context import AppContext
from auto_pm.application.core import acceptance_runner
from auto_pm.contracts.acceptance_command import WORKTREE_PLACEHOLDER
from auto_pm.infrastructure import long_run_core
from auto_pm.ui.cli.caller_path import CallerPath, caller_cwd_default
from auto_pm.ui.cli.runtime_identity_guard import require_runtime_identity_for_workspace


def _root(ctx: click.Context) -> Path:
    app_ctx: AppContext = ctx.find_root().obj
    return Path(app_ctx.control_root or app_ctx.workspace_root or os.getcwd())


def _echo(payload: dict[str, Any]) -> None:
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))


def _added_environment(extra: dict[str, str]) -> dict[str, str]:
    """What the acceptance runner would add to the environment (UTF-8, Git quoting, the worktree switches) -- only those variables, never a dump of ours."""

    base = os.environ
    wanted = acceptance_runner.execution_environment(base)
    wanted.update(extra)
    return {key: value for key, value in wanted.items() if base.get(key) != value}


def _fail(error: long_run_core.LongRunError) -> click.ClickException:
    return click.ClickException(str(error))


@click.group(name="long-run")
def long_run_group() -> None:
    """长任务：脱离终端、带内存保护地跑，状态文件就是证据（超过 10 分钟或 100 个用例的回归都走这里）。"""


@long_run_group.command(name="start", context_settings={"ignore_unknown_options": True, "allow_interspersed_args": False})
@click.option("--name", required=True, help="任务名（字母、数字、点、下划线、连字符）；用过的名字不能再用，旧记录是证据")
@click.option(
    "--cwd",
    type=CallerPath(file_okay=False, exists=True, path_type=Path),
    default=caller_cwd_default,
    help="命令的工作目录（默认当前目录；写你工位或受治理工作树的绝对路径）",
)
@click.option(
    "--worktree",
    type=CallerPath(file_okay=False, exists=True, path_type=Path),
    default=None,
    help="这次回归要判的受治理工作树（Run 的工作树）：状态文件记它的 git_head/git_dirty，命令按验收命令的同样环境运行"
    "（AUTO_PM_WORKSPACE、AUTO_PM_CONTROL_ROOT、AUTO_PM_RUN_WORKTREE，命令里的 {worktree} 换成它的路径）；pm verify 凭这个认长回归",
)
@click.option("--timeout-min", type=click.IntRange(1, 480), default=long_run_core.DEFAULT_TIMEOUT_MINUTES, show_default=True, help="超时分钟数，到点杀掉整棵进程树")
@click.argument("command", nargs=-1, type=click.UNPROCESSED, required=True)
@click.pass_context
def start_command(
    ctx: click.Context, name: str, cwd: Path | None, worktree: Path | None, timeout_min: int, command: tuple[str, ...]
) -> None:
    """先内存预检，再脱离终端启动命令和内存守卫。命令写在 -- 后面。"""

    require_runtime_identity_for_workspace(ctx)
    root = _root(ctx)
    argv = list(command)
    env: dict[str, str] = {}
    if worktree is not None:
        argv = [item.replace(WORKTREE_PLACEHOLDER, str(worktree.resolve())) for item in argv]
        env = _added_environment(acceptance_runner.worktree_environment(worktree.resolve(), root))
    try:
        status = long_run_core.start(
            root, name, argv, cwd=cwd or Path.cwd(), timeout_minutes=timeout_min, worktree=worktree, env=env
        )
    except long_run_core.LongRunError as error:
        raise _fail(error) from error
    status["next"] = f"python main.py long-run status --name {name}"
    _echo(status)


@long_run_group.command(name="status")
@click.option("--name", default=None, help="任务名；不写就列出全部任务")
@click.pass_context
def status_command(ctx: click.Context, name: str | None) -> None:
    """只读：看任务进行到哪、退出码、守卫采样数和峰值已提交内存。"""

    require_runtime_identity_for_workspace(ctx)
    root = _root(ctx)
    try:
        if name is not None:
            _echo(long_run_core.read_status(long_run_core.run_directory(root, name)))
            return
        base = root / long_run_core.RUN_ROOT
        names = sorted(path.name for path in base.iterdir() if path.is_dir()) if base.is_dir() else []
        rows = []
        for task in names:
            try:
                state = long_run_core.read_status(base / task)
                rows.append({"name": task, "state": state.get("state"), "exit_code": state.get("exit_code"), "started_at": state.get("started_at")})
            except long_run_core.LongRunError as error:
                rows.append({"name": task, "state": "UNREADABLE", "error": str(error)})
        _echo({"tasks": rows})
    except long_run_core.LongRunError as error:
        raise _fail(error) from error


@long_run_group.command(name="stop")
@click.option("--name", required=True, help="要停的任务名")
@click.pass_context
def stop_command(ctx: click.Context, name: str) -> None:
    """结束一个在跑的任务：恢复暂停、杀掉整棵进程树，状态记为 STOPPED。"""

    require_runtime_identity_for_workspace(ctx)
    try:
        _echo(long_run_core.stop(long_run_core.run_directory(_root(ctx), name)))
    except long_run_core.LongRunError as error:
        raise _fail(error) from error
