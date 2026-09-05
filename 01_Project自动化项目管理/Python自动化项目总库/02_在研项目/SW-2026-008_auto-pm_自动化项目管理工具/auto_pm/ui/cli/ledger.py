"""PLC-HMI 概念映射：CLI 命令行入口（台账命令组（对账/同步/修复））

像 PLC 的调试终端/工程师站，通过命令行直接操作功能块。
不经过 HMI 画面，直接调用 FB 或 SFB。

--- 原始注释 ---

ledger 子命令组 - 版本变更台账对账（CHG-108 缺陷 1 修复）

Commands:
    reconcile <PID> [--fix]   台账对账（扫描 CHG 文件 vs 台账记录）
                              --fix: 自动补建缺失行 + 修复状态不一致
"""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from auto_pm.app_context import AppContext
from auto_pm.change.ledger_reconciler import LedgerReconciler, ReconcileDiff
from auto_pm.core.project_service import ProjectService

console = Console()


@click.group(name="ledger")
@click.pass_context
def ledger_group(ctx: click.Context) -> None:
    """版本变更台账对账与修复"""


@ledger_group.command(name="reconcile")
@click.argument("project_id")
@click.option("--fix", "auto_fix", is_flag=True, help="自动补建缺失行 + 修复状态不一致")
@click.pass_context
def cmd_reconcile(
    ctx: click.Context,
    project_id: str,
    auto_fix: bool,
) -> None:
    """对账：扫描项目 CHG 文件 vs 版本变更台账记录

    \b
    三类差异检测：
      - 台账缺失: CHG 文件存在但台账无记录（--fix 时自动补建）
      - 台账多余: 台账有记录但 CHG 文件不存在（孤儿记录，需人工审核）
      - 状态不一致: CHG 状态 vs 台账状态不匹配（--fix 时自动修正）

    \b
    退出码：
      0 = 对账无差异 或 --fix 修复后无差异
      1 = 项目不存在
      2 = 有差异且未修复（未传 --fix，或存在孤儿记录需人工处理）
    """
    app_ctx: AppContext = ctx.obj
    svc = ProjectService(app_ctx.workspace_root)
    project_path = svc.find_project_path(project_id)
    if project_path is None:
        console.print(f"[red]错误: 项目不存在: {project_id}[/red]")
        ctx.exit(1)

    reconciler = LedgerReconciler()
    diff: ReconcileDiff = reconciler.reconcile(project_path)

    # 输出对账报告
    console.print()
    console.print(f"[bold cyan]═══ 台账对账报告: {project_id} ═══[/bold cyan]")
    console.print(f"  [cyan]摘要:[/cyan] {diff.summary()}")

    if diff.missing_in_ledger:
        table = Table(title="台账缺失记录（CHG 文件存在但台账无）", show_lines=False)
        table.add_column("变更编号", style="red")
        for cn in diff.missing_in_ledger:
            table.add_row(cn)
        console.print(table)

    if diff.orphan_in_ledger:
        table = Table(title="台账孤儿记录（台账有但 CHG 文件不存在，需人工审核）", show_lines=False)
        table.add_column("变更编号", style="yellow")
        for cn in diff.orphan_in_ledger:
            table.add_row(cn)
        console.print(table)

    if diff.status_mismatches:
        table = Table(title="状态不一致（CHG 期望 vs 台账实际）", show_lines=False)
        table.add_column("变更编号", style="magenta")
        table.add_column("CHG期望", style="green")
        table.add_column("台账实际", style="red")
        for cn, expected, actual in diff.status_mismatches:
            table.add_row(cn, expected, actual)
        console.print(table)

    # 自动修复
    if auto_fix and not diff.is_clean:
        console.print()
        console.print("[bold yellow]启动自动修复...[/bold yellow]")
        reconciler.auto_fix(project_path, diff)
        # 修复后重新对账（孤儿记录无法自动修复，会保留）
        new_diff = reconciler.reconcile(project_path)
        console.print()
        console.print(f"[cyan]修复后对账:[/cyan] {new_diff.summary()}")
        if new_diff.is_clean:
            console.print("[green]✅ 对账完成，无差异[/green]")
            ctx.exit(0)
        else:
            # 孤儿记录需人工处理
            if (
                new_diff.orphan_in_ledger
                and not new_diff.missing_in_ledger
                and not new_diff.status_mismatches
            ):
                console.print(
                    "[yellow]⚠ 仅有孤儿记录（台账多余但无对应 CHG 文件），需人工审核后用 ledger remove 清理[/yellow]"
                )
            else:
                console.print("[red]❌ 修复后仍有差异，请检查[/red]")
            ctx.exit(2)
    elif diff.is_clean:
        console.print()
        console.print("[green]✅ 对账无差异[/green]")
        ctx.exit(0)
    else:
        console.print()
        console.print(
            f"[yellow]⚠ 检测到差异（缺失 {len(diff.missing_in_ledger)} / "
            f"孤儿 {len(diff.orphan_in_ledger)} / "
            f"状态不一致 {len(diff.status_mismatches)}）[/yellow]"
        )
        console.print(
            "[dim]提示: 使用 --fix 自动补建缺失行和修复状态不一致（孤儿记录需人工处理）[/dim]"
        )
        ctx.exit(2)
