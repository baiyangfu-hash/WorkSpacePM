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

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from auto_pm.app_context import AppContext
from auto_pm.application.core.chg_tracking_service import check_project_chg_tracking
from auto_pm.change.ledger_reconciler import LedgerReconciler, ReconcileDiff
from auto_pm.core.project_service import ProjectService
from auto_pm.ui.cli.runtime_identity_guard import require_runtime_identity

console = Console()


_TRACKING_LIST_LIMIT = 10


def print_chg_tracking_warning(project_path: Path, *, verbose: bool = False, block: bool = False) -> bool:
    """Show change requests that exist on disk but are not in the HEAD commit (TD-SW008-113); return True when that must fail the gate.

    Shows the first ten per kind with a relative path; ``verbose`` shows them all.  With ``block`` (the ``change verify --ledger-check`` gate) a change
    request that is *in no commit* fails the gate (the caller turns a passing exit into 2); without it (``ledger reconcile``, run right after closure,
    which never commits) it is a loud warning only.  Change requests that merely *differ* from the commit stay a warning either way, because an edit in
    progress is legitimate.  When Git cannot answer the check is reported as skipped and never blocks.
    """

    report = check_project_chg_tracking(project_path)
    if report.skipped_reason:
        console.print(f"[dim]提交跟踪检查未执行：{report.skipped_reason}[/dim]")
        return False
    if report.clean:
        return False
    blocked = block and bool(report.untracked)
    console.print()
    verdict = "拦截，退出码 2" if blocked else "只提示，不影响退出码"
    color = "red" if (blocked or report.untracked) else "yellow"
    console.print(
        f"[{color}]{'❌' if blocked else '⚠'} 提交跟踪（{verdict}）：{len(report.untracked)} 个变更单未提交（不在 {report.ref} 提交里），"
        f"{len(report.modified)} 个与提交内容不同[/{color}]"
    )
    if report.untracked:
        console.print("[red]未提交，请先提交变更单；提交前 `change verify --ledger-check` 会拦截。[/red]")
    for label, names in (("未入库", report.untracked), ("有改动", report.modified)):
        shown = names if verbose else names[:_TRACKING_LIST_LIMIT]
        for name in shown:
            console.print(f"  [yellow]{label}:[/yellow] {report.relative(name)}", markup=True, highlight=False)
        if len(names) > len(shown):
            console.print(f"  [yellow]…另有 {len(names) - len(shown)} 个{label}（加 --verbose 看完整清单）[/yellow]")
    console.print("[dim]提示: 变更单只存在于本机磁盘时，换电脑或误删就找不回；请和代码一起提交。[/dim]")
    return blocked


def exit_with_tracking(ctx: click.Context, code: int, project_path: Path, *, verbose: bool = False, block: bool = False) -> None:
    """Print the tracking report last, then exit with ``code`` — or, with ``block``, 2 when the gate would have passed but change requests are in no commit."""

    if print_chg_tracking_warning(project_path, verbose=verbose, block=block) and code == 0:
        code = 2
    ctx.exit(code)


@click.group(name="ledger")
@click.pass_context
def ledger_group(ctx: click.Context) -> None:
    """版本变更台账对账与修复"""


@ledger_group.command(name="reconcile")
@click.argument("project_id")
@click.option("--fix", "auto_fix", is_flag=True, help="自动补建缺失行 + 修复状态不一致")
@click.option("--verbose", is_flag=True, help="提交跟踪警告列出全部文件（默认每类只列前 10 个）")
@click.pass_context
def cmd_reconcile(
    ctx: click.Context,
    project_id: str,
    auto_fix: bool,
    verbose: bool,
) -> None:
    """对账：扫描项目 CHG 文件 vs 版本变更台账记录

    \b
    三类差异检测：
      - 台账缺失: CHG 文件存在但台账无记录（--fix 时自动补建）
      - 台账多余: 台账有记录但 CHG 文件不存在（孤儿记录，需人工审核）
      - 状态不一致: CHG 状态 vs 台账状态不匹配（--fix 时自动修正）

    \b
    退出码：
      0 = 对账无差异 或 --fix 修复后无差异（变更单未提交只醒目警告，不改退出码；拦截见 change verify --ledger-check）
      1 = 项目不存在
      2 = 有差异且未修复（未传 --fix，或存在孤儿记录需人工处理）
    """
    app_ctx: AppContext = ctx.obj
    svc = ProjectService(app_ctx.workspace_root)
    project_path = svc.find_project_path(project_id)
    if project_path is None:
        console.print(f"[red]错误: 项目不存在: {project_id}[/red]")
        ctx.exit(1)

    if auto_fix:
        # Only --fix writes the ledger; the plain report stays a read.
        require_runtime_identity(ctx, project_id)

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

    # 提交跟踪结果放在结论之后：不管从哪个出口退出，最后一屏都是它。reconcile 只警告：收口只并回文件、从不提交，收口后立刻对账必然有未提交的变更单，
    # 若此刻就红，人会习惯忽略红灯；拦截放在 `change verify --ledger-check`（TD-SW008-113）
    exit_code = 2
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
            exit_code = 0
        # 孤儿记录需人工处理
        elif new_diff.orphan_in_ledger and not new_diff.missing_in_ledger and not new_diff.status_mismatches:
            console.print("[yellow]⚠ 仅有孤儿记录（台账多余但无对应 CHG 文件），需人工审核后用 ledger remove 清理[/yellow]")
        else:
            console.print("[red]❌ 修复后仍有差异，请检查[/red]")
    elif diff.is_clean:
        console.print()
        console.print("[green]✅ 对账无差异[/green]")
        exit_code = 0
    else:
        console.print()
        console.print(
            f"[yellow]⚠ 检测到差异（缺失 {len(diff.missing_in_ledger)} / "
            f"孤儿 {len(diff.orphan_in_ledger)} / "
            f"状态不一致 {len(diff.status_mismatches)}）[/yellow]"
        )
        console.print("[dim]提示: 使用 --fix 自动补建缺失行和修复状态不一致（孤儿记录需人工处理）[/dim]")
    exit_with_tracking(ctx, exit_code, project_path, verbose=verbose)
