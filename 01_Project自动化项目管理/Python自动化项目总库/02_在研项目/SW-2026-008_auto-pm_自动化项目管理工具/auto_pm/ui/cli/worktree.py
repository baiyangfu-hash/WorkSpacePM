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
    MAX_STATIONS,
    STALE_DAYS,
    AgentWorktreeError,
    AgentWorktreeService,
    Station,
    StationRefusedError,
    base_agent,
    caller_alias,
    ensure_session_id,
)
from auto_pm.ui.cli.runtime_identity_guard import require_runtime_identity_for_workspace

console = Console()


class _AgentName(click.ParamType):  # type: ignore[type-arg]
    """名册里的基名，或 <基名>-<6位十六进制> 的会话别名（每个对话一个工位）。"""

    name = "agent"

    def convert(self, value: Any, param: click.Parameter | None, ctx: click.Context | None) -> str:
        text = str(value)
        if text == "self":  # 本对话自己的别名工位：不用手写别名，任何 agent 都能用
            alias = caller_alias()
            if not alias:
                self.fail("`self` 只能由 agent 在有会话 ID 的对话里使用；用户终端请写明 agent 名或别名", param, ctx)
            return alias
        if base_agent(text):
            return text
        self.fail(f"`{text}` 不是名册里的 agent（{'、'.join(sorted(AGENT_ROSTER))}）或会话别名（如 claude-b89bc8）", param, ctx)

    def get_metavar(self, param: click.Parameter, ctx: click.Context | None = None) -> str:
        return "[" + "|".join(sorted(AGENT_ROSTER)) + "|<基名>-<6位十六进制>]"


AGENTS = _AgentName()


def resolve_station_name(service: AgentWorktreeService, agent: str, *, opening: bool = False) -> str:
    """D-112: a bare roster name from an agent that has its own conversation alias means *this conversation's* station.

    Every Claude conversation used to pass ``claude`` and land on the one shared ``claude`` station, so whoever opened it first
    held it for days and nobody else could open a PR from a different card.  With a session id the caller has its own station
    ``claude-<6 hex>``; ``opening`` always uses it, other commands use it when it exists and otherwise keep the name they were
    given (an older station opened under the bare name keeps working).  Without a session id (the user's terminal, other AIs)
    nothing changes.  Only the caller's own alias can come out of here, so one conversation cannot reach another's station.
    """

    alias = caller_alias()
    if not alias or agent == alias or agent != base_agent(alias):
        return agent
    if opening or (service.stations_dir / alias).exists():
        console.print(f"[cyan]按本对话别名 {alias} 处理（{agent} 是所有同名对话共用的名字）[/cyan]")
        return alias
    return agent


def _service(ctx: click.Context, *, measure_size: bool = True) -> AgentWorktreeService:
    app_ctx: AppContext = ctx.obj
    root = app_ctx.control_root or app_ctx.workspace_root or os.getcwd()
    ensure_session_id(root)
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
        "broken": station.broken,  # non-empty: the directory is no longer a work tree (never run git in it)
        "branch": station.branch,
        "checked": station.checked,  # False: dirty/unpushed/merged/untouched were not looked at (null)
        "dirty": len(station.dirty_paths) if station.checked else None,
        "unpushed": station.unpushed if station.checked else None,
        "merged": station.merged if station.checked else None,
        "untouched": station.untouched if station.checked else None,
        "locked": station.locked,
        "size_bytes": station.size_bytes,
        "idle_days": station.idle_days,  # whole days since the last commit / branch switch / opening; null: unknown
        "stale": station.stale,  # untouched for more than 3 days (WS-001 rule 5)
    }


def _kind_label(station: Any) -> str:
    if station.broken:
        return "残缺目录"
    return station.kind if station.registered else "未登记目录"


def _idle_cell(station: Any) -> str:
    if station.idle_days is None:
        return "-"
    return f"[yellow]{station.idle_days}[/yellow]" if station.stale else str(station.idle_days)


def _print_count(stations: list[Any]) -> None:
    """One line under the table: how many directories, against the limit that ``open`` enforces."""

    if len(stations) >= MAX_STATIONS:
        console.print(
            f"[red]共 {len(stations)} 个目录，已到上限 {MAX_STATIONS}：再 open 会被拒；先 close 做完的，或 sweep 看哪些可清[/red]"
        )
    else:
        console.print(f"共 {len(stations)} 个目录（上限 {MAX_STATIONS}）")
    stale = [s for s in stations if s.stale]
    if stale:
        names = "、".join(s.name for s in stale)
        console.print(
            f"[yellow]超过 {STALE_DAYS} 天没动的 {len(stale)} 个：{names}；做完了就 close / sweep，没做完就在日报里写明[/yellow]",
            highlight=False,
        )


def _print_broken_hint(stations: list[Any]) -> None:
    broken = [s for s in stations if s.broken]
    if not broken:
        return
    console.print("[red]有已经不是工作树的残缺目录，不要在里面跑 git（命令会落到控制根）：[/red]")
    for s in broken:
        console.print(f"  {s.path}：{s.broken}", markup=False, highlight=False)


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
    require_runtime_identity_for_workspace(ctx)
    service = _service(ctx, measure_size=False)
    agent = resolve_station_name(service, agent, opening=True)
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
        for column in ("工位", "类型", "分支", "闲置（天）", "路径"):
            table.add_column(column)
        for s in stations:
            table.add_row(s.name, _kind_label(s), s.branch or "-", _idle_cell(s), str(s.path))
        console.print(table)
        _print_count(stations)
        _print_broken_hint(stations)
        console.print(
            "只列了名字、分支、路径；要看未提交、未推送、是否并进 main，加 --deep（会慢）"
        )
        return
    for column in ("工位", "类型", "分支", "闲置（天）", "未提交", "未推送", "并进 main", "占用（含 .venv）"):
        table.add_column(column)
    for s in stations:
        kind = _kind_label(s)
        merged = "空工位" if s.untouched else ("是" if s.merged else "否")
        table.add_row(
            s.name,
            kind,
            s.branch or "-",
            _idle_cell(s),
            str(len(s.dirty_paths)),
            str(s.unpushed),
            merged,
            _size(s.size_bytes),
        )
    console.print(table)
    _print_count(stations)
    _print_broken_hint(stations)


@worktree_group.command("close")
@click.argument("agent", type=AGENTS)
@click.option("--no-fetch", is_flag=True, help="断网时按本机已知的远程分支判断")
@click.pass_context
def close_cmd(ctx: click.Context, agent: str, no_fetch: bool) -> None:
    """收 AGENT 的工位：无未提交改动、提交都已推送才删；已并进 main 的再删本地分支"""
    require_runtime_identity_for_workspace(ctx)
    service = _service(ctx, measure_size=False)
    agent = resolve_station_name(service, agent)
    try:
        result = service.close(agent, fetch=not no_fetch)
    except AgentWorktreeError as error:
        _fail(error)
    console.print(f"[green]已收工位[/green] {result.path}（分支 {result.branch}）：{result.note}")


@worktree_group.command("release")
@click.argument("agent", type=AGENTS, required=False)
@click.option("--self", "mine", is_flag=True, help="回收本对话自己的别名工位（给包装脚本、SessionEnd 钩子在对话结束时调用）")
@click.pass_context
def release_cmd(ctx: click.Context, agent: str | None, mine: bool) -> None:
    """回收一个会话别名工位（对话结束时用）：先把未提交和未跟踪的内容存成救援引用，再收目录；分支保留"""
    if mine == (agent is not None):
        _fail(AgentWorktreeError("要么给出别名，要么用 --self，二选一"))
    require_runtime_identity_for_workspace(ctx)
    service = _service(ctx, measure_size=False)
    if mine:
        agent = caller_alias()
        if not agent:
            console.print("本对话没有会话别名（不是 agent 调用，或没有会话 ID），没有可回收的工位")
            return
        if not (service.stations_dir / agent).exists():
            console.print(f"本对话（{agent}）没有开过工位，没有可回收的")
            return
    assert agent is not None
    try:
        result = service.release(agent)
    except AgentWorktreeError as error:
        _fail(error)
    console.print(f"[green]已回收工位[/green] {result.path}（分支 {result.branch} 保留）")
    if result.rescue_ref:
        console.print(f"工位里有没提交的内容，已存为救援引用 {result.rescue_ref}；找回：git checkout {result.rescue_ref} -- .")
    else:
        console.print("工位是干净的，没有需要救援的内容")


@worktree_group.command("heartbeat")
@click.pass_context
def heartbeat_cmd(ctx: click.Context) -> None:
    """刷新本对话工位的心跳（给 Claude Code 的 Stop / PreToolUse 钩子调用；没有本对话的工位就什么都不做）"""
    service = _service(ctx, measure_size=False)
    alias = caller_alias()
    if alias and service.touch_heartbeat(alias):
        console.print(f"已刷新 {alias} 的心跳")


@worktree_group.command("reclaim")
@click.option("--stale", "stale", is_flag=True, required=True, help="回收持有对话已经不在的会话别名工位")
@click.option("--apply", "apply", is_flag=True, help="真的回收；不加时只列出")
@click.pass_context
def reclaim_cmd(ctx: click.Context, stale: bool, apply: bool) -> None:
    """快捷回收：列出（加 --apply 则回收）持有对话已不在的会话别名工位；回收前一样先存救援引用，分支保留"""
    del stale
    if apply:
        require_runtime_identity_for_workspace(ctx)
    service = _service(ctx, measure_size=False)
    try:
        found = service.reclaim_stale(apply=apply)
    except AgentWorktreeError as error:
        _fail(error)
    if not found:
        console.print("没有持有对话已不在的会话别名工位")
        return
    for name, reason in found:
        console.print(f"{'[green]已回收[/green]' if apply else '可回收'} {name}：{reason}")
    if not apply:
        console.print("加 --apply 才会真的回收（先存救援引用，分支保留）")


@worktree_group.command("sweep")
@click.option("--apply", "apply", is_flag=True, help="真的删除；不加时只列出（等于 --dry-run）")
@click.option("--dry-run", "dry_run", is_flag=True, help="只列出，不删（默认）")
@click.option("--agent", type=AGENTS, default=None, help="只清这个 agent 的工位")
@click.option("--only", "only", metavar="NAME", default=None, help="只处理这一个目录（目录名，见 worktree list）；远程已删的分支不看")
@click.option("--no-fetch", is_flag=True, help="断网时按本机已知的远程分支判断")
@click.option("--json", "as_json", is_flag=True, help="机器可读输出")
@click.pass_context
def sweep_cmd(
    ctx: click.Context,
    apply: bool,
    dry_run: bool,
    agent: str | None,
    only: str | None,
    no_fetch: bool,
    as_json: bool,
) -> None:
    """清理已并进 main 的工位、名册外已并进 main 且干净的目录、远程已删的本地分支、已结束 Run 的 run-plan-* 残留；默认只列"""
    if apply and dry_run:
        _fail(AgentWorktreeError("--apply 和 --dry-run 只能选一个"))
    if apply:  # the default is a listing: it deletes nothing, so it asks the guard nothing
        require_runtime_identity_for_workspace(ctx)
    service = _service(ctx, measure_size=False)
    try:
        report = service.sweep(
            apply=apply, agent=agent, only=only, fetch=not no_fetch, progress=_progress
        )
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
