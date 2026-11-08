"""``pm retire``: formally close an old leftover Work and the Mission rooted at it (D-109 layer 2).

Dry run by default: it lists what ``orient`` already warns about and what closing each would touch, and writes nothing.
``--apply`` cancels them and needs the user in person: an agent session must carry the user's own words
(``--approval-evidence-ref user-confirmation:<…>``), and once an approval PIN is committed the user types it.
"""

from __future__ import annotations

import json
from typing import Any

import click

from auto_pm import __version__
from auto_pm.app_context import AppContext
from auto_pm.application.core.retire_service import (
    RetireError,
    RetirePlan,
    RetireResult,
    RetireService,
)
from auto_pm.application.core.worktree_policy_service import (
    WorktreePolicyError,
    WorktreePolicyService,
)
from auto_pm.ui.cli.approval_pin import read_approval_pin, refuse_agent_approval
from auto_pm.ui.cli.runtime_identity_guard import require_runtime_identity


def _plan_payload(plan: RetirePlan) -> dict[str, Any]:
    return {
        "project_id": plan.project_id,
        "leftovers": [
            {
                "work_id": item.work_id,
                "title": item.title,
                "work_state": item.residue.work_state,
                "last_run_id": item.residue.last_run_id,
                "last_run_state": item.residue.last_run_state,
                "last_run_ended_at": item.residue.last_run_ended_at,
                "mission_id": item.mission_id,
                "mission_state": item.mission_state,
                "can_retire": not item.blocked_reason,
                "blocked_reason": item.blocked_reason,
            }
            for item in plan.items
        ],
        "not_leftover": plan.unknown_work_ids,
    }


def _result_payload(result: RetireResult) -> dict[str, str]:
    return {
        "work_id": result.work_id,
        "mission_id": result.mission_id,
        "outcome": result.outcome,
        "detail": result.detail,
    }


@click.command(name="retire")
@click.option("--pid", "project_id", required=True, help="项目编号")
@click.option("--work-id", "work_ids", multiple=True, help="只收这几张（可重复）；与 --stale 二选一")
@click.option("--stale", is_flag=True, help="该项目里所有陈年残留（最后一个 Run 结束超过 24 小时、无活跃 Run、租约已过期）")
@click.option("--apply", "apply_", is_flag=True, help="真的取消；不带则只列出，什么都不写")
@click.option("--approval-evidence-ref", default="", help="用户原话所在的位置（--apply 只听用户的；已启用批准口令时由口令代替）")
@click.pass_context
def retire_pm(
    ctx: click.Context,
    project_id: str,
    work_ids: tuple[str, ...],
    stale: bool,
    apply_: bool,
    approval_evidence_ref: str,
) -> None:
    """把陈年残留的 Work（及其根 Mission）正式取消，让 orient 不再报警；默认只预演。"""

    if bool(work_ids) == stale:
        raise click.ClickException("要么用 --work-id 点名，要么用 --stale 收该项目全部陈年残留，二者选一")
    app_ctx: AppContext = ctx.find_root().obj
    service = RetireService(app_ctx.control_root)
    if not apply_:
        plan = service.plan(project_id, work_ids)
        click.echo(
            json.dumps(
                {"schema_version": "pm-retire.v1", "mode": "dry-run", **_plan_payload(plan)},
                ensure_ascii=False,
                indent=2,
            )
        )
        if plan.items:
            click.echo("以上只是预演，没有写任何东西；确认后加 --apply（需要用户本人批准）。", err=True)
        return
    refuse_agent_approval("收口陈年残留（pm retire --apply）", approval_evidence_ref)
    require_runtime_identity(ctx, project_id)
    try:
        WorktreePolicyService(app_ctx.control_root).require_control_root()
    except WorktreePolicyError as error:
        raise click.ClickException(str(error)) from error
    approval_pin = read_approval_pin(str(app_ctx.control_root), summary=f"收口 {project_id} 的陈年残留 Work")
    try:
        results, trace = service.apply(
            project_id,
            work_ids,
            approval_pin=approval_pin,
            approval_evidence_ref=approval_evidence_ref,
            tool_version=__version__,
        )
    except RetireError as error:
        raise click.ClickException(str(error)) from error
    click.echo(
        json.dumps(
            {
                "schema_version": "pm-retire.v1",
                "mode": "apply",
                "project_id": project_id,
                "results": [_result_payload(r) for r in results],
                "trace": str(trace) if trace else "",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
