"""Worktree CLI：agent 工位开、看、收、清（WS-001，WBS X05）

像产线换型：开工位＝领料上线，收工位＝清线退料；清线前先核对在制品（未提交改动、没推送的提交），
有在制品就停线并说明，不强拆。

退出码：0 成功；1 被安全检查拒绝（说明里写了原因和下一步）；2 用法或 Git 出错。
"""

from __future__ import annotations

import json
import os
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from auto_pm.app_context import AppContext
from auto_pm.application.core.agent_worktree_service import (
    AGENT_ROSTER,
    AgentWorktreeError,
    AgentWorktreeService,
    Station,
    StationRefusedError,
)

console = Console()
AGENTS = click.Choice(sorted(AGENT_ROSTER))


def _service(ctx: click.Context, *, measure_size: bool = True) -> AgentWorktreeService:
    app_ctx: AppContext = ctx.obj
    root = app_ctx.control_root or app_ctx.workspace_root or os.getcwd()
    try:
        return AgentWorktreeService(root, measure_size=measure_size)
    except AgentWorktreeError as error:
        _fail(error)
        raise AssertionError("unreachable") from error  # pragma: no cover


def _fail(error: AgentWorktreeError) -> None:
    label = "拒绝" if isinstance(error, StationRefusedError) else "错误"
    console.print(f"[bold red]{label}[/bold red] {error}")
    raise SystemExit(1 if isinstance(error, StationRefusedError) else 2)


def _progress(name: str) -> None:
    click.echo(f"检查工位 {name} ……", err=True)


def _interrupted() -> None:
    click.echo("已中断", err=True)
    raise SystemExit(130)


def _size(value: int | None) -> str:
    return "-" if value is None else f"{value / 1024 / 1024:.0f} MB"


def _station_json(station: Station) -> dict[str, Any]:
    return {
        "name": station.name,
        "path": str(station.path),
        "kind": station.kind,
        "registered": station.registered,
        "branch": station.branch,
        "checked": station.checked,  # False: dirty/unpushed/merged/untouched were not looked at (null)
        "dirty": len(station.dirty_paths) if station.checked else None,
        "unpushed": station.unpushed if station.checked else None,
        "merged": station.merged if station.checked else None,
        "untouched": station.untouched if station.checked else None,
        "locked": station.locked,
        "size_bytes": station.size_bytes,
    }


@click.group("worktree")
def worktree_group() -> None:
    """agent 工位：开（open）、看（list）、收（close）、清（sweep）；只在控制根执行"""


@worktree_group.command("open")
@click.argument("agent", type=AGENTS)
@click.argument("card")
@click.option("--no-fetch", is_flag=True, help="断网时用本机现有的 origin/main，不先拉取")
@click.pass_context
def open_cmd(ctx: click.Context, agent: str, card: str, no_fetch: bool) -> None:
    """为 AGENT 开工位，分支 <前缀><CARD>，从最新 origin/main 起"""
    service = _service(ctx, measure_size=False)
    try:
        station = service.open(agent, card, fetch=not no_fetch)
    except AgentWorktreeError as error:
        _fail(error)
    console.print(f"[green]已开工位[/green] {station.path}")
    console.print(
        f"分支 {station.branch}（从 origin/main {station.head[:8]} 起，未设上游；第一次推送用 git push -u origin {station.branch}）"
    )
    console.print(
        "Python 环境默认共用控制根的 .venv；只有这张卡改依赖锁定文件时才在工位里另建 .venv，收工时一起删"
    )


@worktree_group.command("list")
@click.option("--json", "as_json", is_flag=True, help="机器可读输出")
@click.option("--no-size", is_flag=True, help="不统计占用大小（大目录时更快；--deep 时才统计占用）")
@click.option(
    "--deep",
    is_flag=True,
    help="逐个工位查未提交改动、未推送提交、是否并进 main（整仓库大时要几分钟）",
)
@click.pass_context
def list_cmd(ctx: click.Context, as_json: bool, no_size: bool, deep: bool) -> None:
    """列出 .auto-pm/worktrees 下每个工位；默认只列名字、分支、路径，加 --deep 才逐个检查"""
    service = _service(ctx, measure_size=deep and not no_size)
    try:
        stations = service.stations(deep=deep, progress=_progress if deep else None)
    except AgentWorktreeError as error:
        _fail(error)
    except KeyboardInterrupt:
        _interrupted()
    if as_json:
        click.echo(json.dumps([_station_json(s) for s in stations], ensure_ascii=False, indent=2))
        return
    if not stations:
        console.print(f"没有工位（{service.stations_dir}）")
        return
    table = Table(title="工位", show_header=True, header_style="bold cyan")
    if not deep:
        for column in ("工位", "类型", "分支", "路径"):
            table.add_column(column)
        for s in stations:
            table.add_row(
                s.name, s.kind if s.registered else "未登记目录", s.branch or "-", str(s.path)
            )
        console.print(table)
        console.print(
            "只列了名字、分支、路径；要看未提交、未推送、是否并进 main，加 --deep（会慢）"
        )
        return
    for column in ("工位", "类型", "分支", "未提交", "未推送", "并进 main", "占用（含 .venv）"):
        table.add_column(column)
    for s in stations:
        kind = s.kind if s.registered else "未登记目录"
        merged = "空工位" if s.untouched else ("是" if s.merged else "否")
        table.add_row(
            s.name,
            kind,
            s.branch or "-",
            str(len(s.dirty_paths)),
            str(s.unpushed),
            merged,
            _size(s.size_bytes),
        )
    console.print(table)


@worktree_group.command("close")
@click.argument("agent", type=AGENTS)
@click.option("--no-fetch", is_flag=True, help="断网时按本机已知的远程分支判断")
@click.pass_context
def close_cmd(ctx: click.Context, agent: str, no_fetch: bool) -> None:
    """收 AGENT 的工位：无未提交改动、提交都已推送才删；已并进 main 的再删本地分支"""
    service = _service(ctx, measure_size=False)
    try:
        result = service.close(agent, fetch=not no_fetch)
    except AgentWorktreeError as error:
        _fail(error)
    console.print(f"[green]已收工位[/green] {result.path}（分支 {result.branch}）：{result.note}")


@worktree_group.command("sweep")
@click.option("--apply", "apply", is_flag=True, help="真的删除；不加时只列出（等于 --dry-run）")
@click.option("--dry-run", "dry_run", is_flag=True, help="只列出，不删（默认）")
@click.option("--agent", type=AGENTS, default=None, help="只清这个 agent 的工位")
@click.option("--no-fetch", is_flag=True, help="断网时按本机已知的远程分支判断")
@click.option("--json", "as_json", is_flag=True, help="机器可读输出")
@click.pass_context
def sweep_cmd(
    ctx: click.Context, apply: bool, dry_run: bool, agent: str | None, no_fetch: bool, as_json: bool
) -> None:
    """清理已并进 main 的工位、远程已删的本地分支、已结束 Run 的 run-plan-* 残留；默认只列"""
    if apply and dry_run:
        _fail(AgentWorktreeError("--apply 和 --dry-run 只能选一个"))
    service = _service(ctx, measure_size=False)
    try:
        report = service.sweep(apply=apply, agent=agent, fetch=not no_fetch, progress=_progress)
    except AgentWorktreeError as error:
        _fail(error)
    except KeyboardInterrupt:
        _interrupted()
    if as_json:
        payload = {
            "applied": report.applied,
            "fetch_warning": report.fetch_warning,
            "items": [vars(item) for item in report.items],
            "done": report.done,
            "failed": report.failed,
        }
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if report.fetch_warning:
            console.print(f"[yellow]{report.fetch_warning}[/yellow]")
        table = Table(
            title="清理（已执行）"
            if report.applied
            else "清理预览（没删任何东西；加 --apply 才删）"
        )
        for column in ("对象", "类别", "处理", "原因"):
            table.add_column(column)
        for item in report.items:
            table.add_row(
                item.target, item.category, "[red]删[/red]" if item.remove else "保留", item.reason
            )
        console.print(table)
        for line in report.failed:
            console.print(f"[bold red]没删成[/bold red] {line}")
        console.print("远程分支一律不删（合并后由 GitHub 自动删）")
    if report.failed:
        raise SystemExit(1)
