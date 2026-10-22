"""auto_pm.ui.cli.decision - 决策包（Decision Package）命令行工具"""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from auto_pm.app_context import AppContext
from auto_pm.contracts.decision_package import (
    RuntimeDecisionAction,
    RuntimeDecisionCapability,
    RuntimeDecisionOutcome,
)
from auto_pm.core.worktree_policy_service import WorktreePolicyError, WorktreePolicyService
from auto_pm.domain.change.decision_service import (
    DecisionError,
    DecisionService,
)
from auto_pm.ui.cli.approval_pin import require_approval_pin

console = Console()


def _workspace(ctx: click.Context) -> Path:
    app_ctx: AppContext = ctx.obj
    return Path(app_ctx.workspace_root)


# 独占动作：各自只能单独出现在一个 Decision 中（与 RuntimeDecisionCapability 合同一致）。
_EXCLUSIVE_ACTIONS = frozenset(
    {
        RuntimeDecisionAction.ADJUDICATE_BLOCKED_WORK,
        RuntimeDecisionAction.FENCE_LEGACY_TERMINAL_LEASE,
        RuntimeDecisionAction.RECONCILE_TERMINAL_LEASE,
    }
)


def _runtime_capability(
    runtime_actions: tuple[str, ...],
    target_run_ids: tuple[str, ...],
    target_work_ids: tuple[str, ...],
    runtime_outcomes: tuple[str, ...],
) -> RuntimeDecisionCapability:
    """Apply the per-action target/outcome matrix before building the typed capability.

    - settle_expired_run / revoke_unstarted_run / fence_terminal_lease (combinable):
      --target-run-id required, --target-work-id forbidden, outcome CANCELLED.
    - fence_legacy_terminal_lease (exclusive): Run targets required, outcome CANCELLED.
    - reconcile_terminal_lease (exclusive): Run targets required, outcome RELEASED.
    - adjudicate_blocked_work (exclusive): --target-work-id required, --target-run-id
      forbidden, outcome CANCELLED.

    Violations raise ValueError naming the broken rule; nothing is silently dropped.
    """

    actions = tuple(dict.fromkeys(RuntimeDecisionAction(item) for item in runtime_actions))
    outcomes = tuple(dict.fromkeys(RuntimeDecisionOutcome(item) for item in runtime_outcomes))
    if not actions or not outcomes:
        raise ValueError(
            "runtime capability 的 --allow-runtime-action、目标与 --allow-outcome 必须同时提供"
        )
    exclusive = [item for item in actions if item in _EXCLUSIVE_ACTIONS]
    if exclusive and len(actions) != 1:
        raise ValueError(f"{exclusive[0].value} 是独占 action，不得与其他 --allow-runtime-action 混用")
    if actions == (RuntimeDecisionAction.ADJUDICATE_BLOCKED_WORK,):
        if target_run_ids:
            raise ValueError("adjudicate_blocked_work 禁止 --target-run-id，只接受精确 --target-work-id")
        if not target_work_ids:
            raise ValueError("adjudicate_blocked_work 必须同时提供至少一个 --target-work-id")
    else:
        if target_work_ids:
            raise ValueError("--target-work-id 只适用于 adjudicate_blocked_work")
        if not target_run_ids:
            raise ValueError(
                f"{actions[0].value} 等 Run 级 action 必须同时提供至少一个 --target-run-id"
            )
    expected_outcome = (
        RuntimeDecisionOutcome.RELEASED
        if actions == (RuntimeDecisionAction.RECONCILE_TERMINAL_LEASE,)
        else RuntimeDecisionOutcome.CANCELLED
    )
    if outcomes != (expected_outcome,):
        raise ValueError(
            f"{actions[0].value} 的 --allow-outcome 必须且只能是 {expected_outcome.value}"
        )
    return RuntimeDecisionCapability(
        allowed_runtime_actions=actions,
        target_run_ids=target_run_ids,
        allowed_outcomes=outcomes,
        target_work_ids=target_work_ids,
    )


@click.group(name="decision")
def decision_group() -> None:
    """阶段 1 审批结构化决策包管理 (Decision Package)"""


@decision_group.command(name="create")
@click.option("--change-id", required=True, help="关联变更单编号（如 CHG-PLC-2026-012）")
@click.option("--approver", required=True, help="审批人（PM / 架构师）")
@click.option("--pid", "project_id", default="", help="可选的项目编号")
@click.option("--file", "approved_files", multiple=True, help="允许修改的文件相对路径，可重复指定")
@click.option(
    "--condition", "conditions", multiple=True, help="有条件批准的附加条件说明，可重复指定"
)
@click.option("--decision-id", default="", help="显式 Decision ID；runtime capability 必填")
@click.option(
    "--allow-runtime-action",
    "runtime_actions",
    multiple=True,
    type=click.Choice([item.value for item in RuntimeDecisionAction]),
)
@click.option(
    "--target-run-id",
    "target_run_ids",
    multiple=True,
    help="Run 级 runtime action 的精确目标 Run，可重复",
)
@click.option(
    "--target-work-id",
    "target_work_ids",
    multiple=True,
    help="adjudicate_blocked_work 的精确目标 Work，可重复；不得与 --target-run-id 混用",
)
@click.option(
    "--allow-outcome",
    "runtime_outcomes",
    multiple=True,
    type=click.Choice([item.value for item in RuntimeDecisionOutcome]),
)
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def create_decision(
    ctx: click.Context,
    change_id: str,
    approver: str,
    project_id: str,
    approved_files: tuple[str, ...],
    conditions: tuple[str, ...],
    decision_id: str,
    runtime_actions: tuple[str, ...],
    target_run_ids: tuple[str, ...],
    target_work_ids: tuple[str, ...],
    runtime_outcomes: tuple[str, ...],
    as_json: bool,
) -> None:
    """从已批准的变更单创建结构化决策包（已启用批准口令时须用户本人在终端输入口令）。"""
    proof = require_approval_pin(
        ctx, summary=f"签发决策包：变更单 {change_id}，批准人 {approver}", purpose="decision", subject=change_id,
        approver=approver,
    )
    if proof is not None:
        approver = proof.approver
    try:
        root = _workspace(ctx)
        WorktreePolicyService(root).require_control_root()
        supplied_capability = any(
            (runtime_actions, target_run_ids, target_work_ids, runtime_outcomes)
        )
        runtime_capability = None
        if supplied_capability:
            runtime_capability = _runtime_capability(
                runtime_actions, target_run_ids, target_work_ids, runtime_outcomes
            )
        service = DecisionService(root)
        dto = service.create_decision(
            change_id=change_id,
            approver=approver,
            project_id=project_id,
            approved_files=list(approved_files) if approved_files else None,
            conditions=list(conditions) if conditions else None,
            decision_id=decision_id,
            runtime_capability=runtime_capability,
        )
    except (DecisionError, WorktreePolicyError, ValueError) as e:
        console.print(f"[red]错误: {e}[/red]")
        ctx.exit(1)

    if as_json:
        click.echo(json.dumps(dto.to_dict(), ensure_ascii=False, indent=2))
    else:
        console.print(f"[green]✅ 决策包已成功创建并固化: {dto.decision_id}[/green]")
        console.print(f"  [cyan]关联变更单:[/cyan] {dto.change_id}")
        console.print(f"  [cyan]审批结论:[/cyan] {dto.decision_conclusion}")
        console.print(f"  [cyan]批准范围:[/cyan] {dto.approved_scope}")
        console.print(
            f"  [cyan]批准文件清单:[/cyan] {', '.join(dto.approved_files) or '无特异性限定'}"
        )


@decision_group.command(name="show")
@click.argument("decision_id")
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def show_decision(ctx: click.Context, decision_id: str, as_json: bool) -> None:
    """查看指定决策包详情。"""
    service = DecisionService(_workspace(ctx))
    try:
        dto = service.get_decision(decision_id)
    except DecisionError as e:
        console.print(f"[red]错误: {e}[/red]")
        ctx.exit(1)

    if as_json:
        click.echo(json.dumps(dto.to_dict(), ensure_ascii=False, indent=2))
    else:
        console.print(f"[bold cyan]═══ 决策包详情: {dto.decision_id} ═══[/bold cyan]")
        console.print(f"  [bold]项目编号:[/bold] {dto.project_id}")
        console.print(f"  [bold]变更单号:[/bold] {dto.change_id}")
        console.print(f"  [bold]审批人:[/bold] {dto.approver}")
        console.print(f"  [bold]审批时间:[/bold] {dto.approved_at}")
        console.print(f"  [bold]审批结论:[/bold] {dto.decision_conclusion}")
        console.print(f"  [bold]批准范围:[/bold] {dto.approved_scope}")
        console.print("  [bold]批准文件白名单:[/bold]")
        for f in dto.approved_files:
            console.print(f"    - {f}")
        if dto.conditions:
            console.print("  [bold]附加条件:[/bold]")
            for c in dto.conditions:
                console.print(f"    - {c}")


@decision_group.command(name="list")
@click.option("--pid", "project_id", default="", help="按项目编号过滤")
@click.option("--change-id", default="", help="按变更单编号过滤")
@click.pass_context
def list_decisions(
    ctx: click.Context,
    project_id: str,
    change_id: str,
) -> None:
    """列出工作空间内的所有决策包。"""
    service = DecisionService(_workspace(ctx))
    try:
        dtos = service.list_decisions(project_id=project_id, change_id=change_id)
    except DecisionError as e:
        console.print(f"[red]错误: {e}[/red]")
        ctx.exit(1)
    if not dtos:
        console.print("[dim]未找到匹配的决策包[/dim]")
        return

    table = Table(title="已固化决策包清单")
    table.add_column("决策编号", style="cyan")
    table.add_column("项目编号", style="green")
    table.add_column("变更单号", style="magenta")
    table.add_column("审批结论")
    table.add_column("审批人")
    table.add_column("批准文件数", justify="right")

    for d in dtos:
        table.add_row(
            d.decision_id,
            d.project_id,
            d.change_id,
            d.decision_conclusion,
            d.approver,
            str(len(d.approved_files)),
        )

    console.print(table)
