"""PR CLI：agent 收工后自动开 PR（WS-001，WBS X05 卡 C）；ready 合并前只读放行检查

只开不合：命令里没有合并、自动合并、改已有 PR 的路径；合并按 AUD-001 独立审计后由主执行或用户做。

退出码：0 成功；1 被检查拒绝（说明里写了原因和下一步）；2 用法或 Git/gh 出错。
"""

from __future__ import annotations

import os
from pathlib import Path

import click
from rich.console import Console

from auto_pm.app_context import AppContext
from auto_pm.application.core.agent_worktree_service import AGENT_ROSTER, AgentWorktreeError
from auto_pm.application.core.pr_open_service import PrOpenRefusedError, PrOpenService
from auto_pm.application.core.pr_ready_service import PrReadyService, render
from auto_pm.ui.cli.caller_path import CallerPath

console = Console()
AGENTS = click.Choice(sorted(AGENT_ROSTER))


def _fail(error: AgentWorktreeError) -> None:
    label = "拒绝" if isinstance(error, PrOpenRefusedError) else "错误"
    console.print(f"[bold red]{label}[/bold red] {error}", markup=True, highlight=False)
    raise SystemExit(1 if isinstance(error, PrOpenRefusedError) else 2)


@click.group("pr")
def pr_group() -> None:
    """agent 的 PR：open（推送并开 PR，只开不合）、ready（合并前只读放行检查）；只在控制根执行"""


@pr_group.command("open")
@click.argument("agent", type=AGENTS)
@click.argument("card")
@click.option("--task-card", required=True, help="任务卡的仓库相对路径（取 origin/main 上的版本）")
@click.option(
    "--evidence", multiple=True, help="验收证据一行（命令 => 退出码，或测试/提交号）；可重复"
)
@click.option(
    "--safety-circuit",
    type=click.Choice(["是", "否"]),
    default=None,
    help="是否涉及安全回路；改到 0100_PLC自动化 下的文件时必填",
)
@click.option("--sweep", default=None, help="修缺陷的 PR 填：根因和全库同类排查结果（写进“同类排查”一节）")
@click.option("--title", default=None, help="覆盖 PR 标题；默认 [卡号] 任务卡标题")
@click.option("--dry-run", is_flag=True, help="只做检查并显示分支、标题、描述；不推送、不开 PR")
@click.option("--no-fetch", is_flag=True, help="断网时用本机现有的 origin/main")
@click.pass_context
def open_cmd(
    ctx: click.Context,
    agent: str,
    card: str,
    task_card: str,
    evidence: tuple[str, ...],
    safety_circuit: str | None,
    sweep: str | None,
    title: str | None,
    dry_run: bool,
    no_fetch: bool,
) -> None:
    """为 AGENT 的工位 <前缀><CARD> 推送分支并开 PR（只开不合）"""
    app_ctx: AppContext = ctx.obj
    root = app_ctx.control_root or app_ctx.workspace_root or os.getcwd()
    try:
        service = PrOpenService(root)
        plan = service.plan(
            agent,
            card,
            task_card,
            evidence=evidence,
            safety_circuit=safety_circuit,
            title=title,
            sweep=sweep,
            fetch=not no_fetch,
        )
    except AgentWorktreeError as error:
        _fail(error)
    console.print(f"分支  {plan.branch}", highlight=False)
    console.print(f"标题  {plan.title}", highlight=False)
    console.print(f"CHG   {'、'.join(plan.chg_numbers)}", highlight=False)
    console.print(
        f"提交  {len(plan.commits)} 个（{plan.base_sha[:8]}..{plan.head_sha[:8]}）", highlight=False
    )
    for note in plan.notes:
        console.print(f"[yellow]注意[/yellow] {note}", highlight=False)
    console.print("越界检查  通过（与 GitHub gate 同一套判据）")
    if dry_run:
        console.print("\n--- PR 描述 ---", highlight=False)
        console.print(plan.body, markup=False, highlight=False)
        console.print("[yellow]--dry-run：没有推送，也没有检查 gh 登录[/yellow]")
        return
    try:
        opened = service.open(plan)
    except AgentWorktreeError as error:
        _fail(error)
    console.print(f"[green]已开 PR #{opened.number}[/green] {opened.url}", highlight=False)
    console.print("只开不合：请独立审计（AUD-001），CI 全绿、评审对话解决后再合并")


@pr_group.command("ready")
@click.argument("number", type=int)
@click.option("--repo", default=None, help="owner/name；默认取 gh 当前仓库")
@click.option(
    "--reports-dir",
    "reports_dirs",
    multiple=True,
    type=CallerPath(file_okay=False, path_type=Path),
    help="再多找一个审计报告目录；可重复。默认只找控制根的 reviews/",
)
@click.pass_context
def ready_cmd(ctx: click.Context, number: int, repo: str | None, reports_dirs: tuple[Path, ...]) -> None:
    """合并前放行检查（只读）：审计报告、必过检查、safety-zone、安全签字；缺一条退出 1，不合并"""
    app_ctx: AppContext = ctx.obj
    root = Path(app_ctx.control_root or app_ctx.workspace_root or os.getcwd())
    dirs = (root / "reviews", *reports_dirs)
    try:
        report = PrReadyService(root, report_dirs=dirs, repo=repo).check(number)
    except AgentWorktreeError as error:
        console.print(f"[bold red]错误[/bold red] {error}", markup=True, highlight=False)
        raise SystemExit(2) from error
    for line in render(report):
        console.print(line, markup=False, highlight=False)
    if not report.ready:
        raise SystemExit(1)
