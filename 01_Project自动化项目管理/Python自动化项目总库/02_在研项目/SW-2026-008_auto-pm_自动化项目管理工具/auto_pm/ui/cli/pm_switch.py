"""PM-level card switching: ``pm missions``, ``pm park``, ``pm unpark``, ``pm switch`` (TD-071 card 2).

一个项目可以开着多张卡，但车间钥匙只有一把：同一时刻只有一张“在干”。插急活就是把手上这张记好断点
“搁着”，钥匙交给急活那张；干完再凭断点拿回来。拿回哪张、切到哪张只听用户的：``unpark`` / ``switch`` 必须带
``--approval-evidence-ref``（用户原话所在的位置）。agent 不带凭据只能用 ``pm park`` 把自己手上的卡放进“等你”。
Tokens never reach the screen: they come from and go to the local wallet, as with ``pm handoff`` / ``pm takeover``.
"""

from __future__ import annotations

import json
from typing import Any

import click

from auto_pm import __version__
from auto_pm.app_context import AppContext
from auto_pm.contracts.mission import PARKED_STALE_DAYS, Mission, MissionBoard
from auto_pm.core.mission_switch_service import (
    MissionSwitchError,
    MissionSwitchService,
    ParkOutcome,
    UnparkOutcome,
)
from auto_pm.core.work_registry_service import WorkRegistryService
from auto_pm.core.worktree_policy_service import WorktreePolicyError, WorktreePolicyService
from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.ui.cli.approval_pin import read_approval_pin
from auto_pm.ui.cli.continuity import _secret_from_environment
from auto_pm.ui.cli.pm_handoff import _holder_pid


def _root(ctx: click.Context) -> str:
    """The root MissionSwitchService writes to; the approval PIN is looked up in the same root."""

    app_ctx: AppContext = ctx.find_root().obj
    return str(app_ctx.control_root)


def _service(ctx: click.Context, *, mutating: bool) -> MissionSwitchService:
    app_ctx: AppContext = ctx.find_root().obj
    if mutating:
        try:
            WorktreePolicyService(app_ctx.control_root).require_control_root()
        except WorktreePolicyError as error:
            raise click.ClickException(str(error)) from error
        WorkRegistryService(app_ctx.control_root).initialize(__version__)
    return MissionSwitchService(app_ctx.control_root)


def _echo(payload: dict[str, Any]) -> None:
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))


def _card(mission: Mission) -> dict[str, Any]:
    return {
        "mission_id": mission.mission_id,
        "title": mission.title,
        "state": mission.state.value,
        "root_work_id": mission.root_work_id or "",
        "updated_at": mission.updated_at.isoformat(),
    }


def _board_payload(board: MissionBoard, service: MissionSwitchService) -> dict[str, Any]:
    now = service._now()
    parked = []
    for item in board.parked:
        days = (now - item.park.parked_at).total_seconds() / 86_400
        parked.append(
            {
                **_card(item.mission),
                "park_id": item.park.park_id,
                "reason": item.park.reason,
                "checkpoint_summary": item.checkpoint_summary,
                "parked_by": item.park.parked_by,
                "parked_at": item.park.parked_at.isoformat(),
                "parked_local": ContinuityStore.local_time_text(item.park.parked_at.isoformat()),
                # Design decision 2: a card parked for more than seven days is flagged yellow on the board.
                "stale": days > PARKED_STALE_DAYS,
            }
        )
    return {
        "schema_version": "pm-missions.v1",
        "subject_project_id": board.subject_project_id,
        "open_count": board.open_count,
        "active": [_card(mission) for mission in board.active],
        "waiting": [_card(mission) for mission in board.waiting],
        "parked": parked,
        "closed": [_card(mission) for mission in board.closed],
    }


def _park_payload(outcome: ParkOutcome) -> dict[str, Any]:
    return {
        "mission_id": outcome.mission.mission_id,
        "state": outcome.mission.state.value,
        "park_id": outcome.park.park_id,
        "checkpoint_id": outcome.checkpoint_id,
        "run_id": outcome.park.run_id,
    }


def _unpark_payload(outcome: UnparkOutcome) -> dict[str, Any]:
    behind = outcome.behind_main
    return {
        "mission_id": outcome.mission.mission_id,
        "state": outcome.mission.state.value,
        "run_id": outcome.park.run_id,
        "owner_id": outcome.owner_id,
        "epoch": outcome.epoch,
        "expires_at": outcome.expires_at,
        "expires_local": ContinuityStore.local_time_text(outcome.expires_at),
        "wallet_path": outcome.wallet_path,
        "holder_process_recorded": outcome.holder_process_recorded,
        "checkpoint_summary": outcome.checkpoint_summary,
        "behind_main": behind,
        "sync_note": (
            "本卡分支落后 main 未知（找不到 main）"
            if behind is None
            else f"本卡分支落后 main {behind} 个提交；请在本卡工作树里同步 main 并跑测试，有冲突停下交给用户，不自动变基"
            if behind
            else "本卡分支没有落后 main"
        ),
        "overlap_note": [
            f"和 {other} 改同一批文件（{'、'.join(paths)}），开干前先同步对方已合并的改动"
            for other, paths in outcome.overlaps
        ],
    }


@click.command(name="missions")
@click.option("--pid", "project_id", required=True, help="项目编号，例如 DJ-2026-009")
@click.pass_context
def missions_pm(ctx: click.Context, project_id: str) -> None:
    """只读：这个项目开着哪些卡，按“在干 / 等你 / 搁着 / 已关”四栏列出。"""

    service = _service(ctx, mutating=False)
    try:
        board = service.board(project_id)
    except MissionSwitchError as error:
        raise click.ClickException(str(error)) from error
    _echo(_board_payload(board, service))


@click.command(name="park")
@click.option("--mission-id", required=True)
@click.option("--reason", required=True, help="为什么先放下，例如“客户急改 IO 表”")
@click.option("--summary", required=True, help="断点：干到哪了、下一步做什么")
@click.option(
    "--approval-evidence-ref",
    default="",
    help="用户原话所在的位置；有它才放进“搁着”，没有就放进“等你”（agent 自己只能这样）",
)
@click.option("--lease-token-env", default=None, metavar="ENV_NAME", help="口令所在环境变量；省略时从本机钱包读取")
@click.pass_context
def park_pm(
    ctx: click.Context,
    mission_id: str,
    reason: str,
    summary: str,
    approval_evidence_ref: str,
    lease_token_env: str | None,
) -> None:
    """把手上这张卡记好断点放下：交出钥匙，之后谁也不能写，直到用户让人用 pm unpark 拿回来。"""

    service = _service(ctx, mutating=True)
    token = _secret_from_environment(lease_token_env) if lease_token_env is not None else None
    # Into "搁着" is the user's call: with a committed approver PIN the user types it here (gap 9).
    approval_pin = (
        read_approval_pin(_root(ctx), summary=f"把 {mission_id} 放进“搁着”（{reason}）") if approval_evidence_ref.strip() else ""
    )
    try:
        outcome = service.park(
            mission_id=mission_id,
            reason=reason,
            summary=summary,
            approval_evidence_ref=approval_evidence_ref,
            lease_token=token,
            approval_pin=approval_pin,
        )
    except MissionSwitchError as error:
        raise click.ClickException(str(error)) from error
    _echo(
        {
            "schema_version": "pm-park.v1",
            **_park_payload(outcome),
            "note": "已记断点、交出钥匙；请停止写入。"
            + ("放进了“搁着”。" if outcome.mission.state.value == "PARKED" else "放进了“等你”，由用户决定什么时候拿回。"),
        }
    )


@click.command(name="unpark")
@click.option("--mission-id", required=True)
@click.option("--as", "as_owner", required=True, help="拿回来接着干的 agent 身份，可以不是放下它的那个")
@click.option("--approval-evidence-ref", default="", help="用户原话所在的位置（拿回哪张只听用户的；已启用批准口令时由口令代替）")
@click.option("--lease-seconds", type=click.IntRange(60, 3_600), default=900, show_default=True)
@click.option("--holder-pid", default="auto", show_default=True, help="记录你的长驻进程：auto、none 或 pid")
@click.pass_context
def unpark_pm(
    ctx: click.Context, mission_id: str, as_owner: str, approval_evidence_ref: str, lease_seconds: int, holder_pid: str
) -> None:
    """凭断点把搁着的卡拿回来：先核对工作树没被动过，再发新钥匙（存本机钱包，不显示）。"""

    service = _service(ctx, mutating=True)
    approval_pin = read_approval_pin(_root(ctx), summary=f"拿回 {mission_id}，交给 {as_owner} 接着干")
    try:
        outcome = service.unpark(
            mission_id=mission_id,
            as_owner=as_owner,
            approval_evidence_ref=approval_evidence_ref,
            lease_seconds=lease_seconds,
            holder_pid=_holder_pid(holder_pid),
            approval_pin=approval_pin,
        )
    except MissionSwitchError as error:
        raise click.ClickException(str(error)) from error
    _echo({"schema_version": "pm-unpark.v1", **_unpark_payload(outcome)})


@click.command(name="switch")
@click.option("--pid", "project_id", required=True)
@click.option("--to", "to_mission_id", default="", help="切到哪张；省略时只给建议，不执行")
@click.option("--reason", default="", help="手上这张为什么先放下")
@click.option("--summary", default="", help="手上这张的断点：干到哪了、下一步做什么")
@click.option("--as", "as_owner", default="", help="拿起目标卡的 agent 身份")
@click.option("--approval-evidence-ref", default="", help="用户原话所在的位置（切换只听用户的）")
@click.option("--lease-seconds", type=click.IntRange(60, 3_600), default=900, show_default=True)
@click.option("--holder-pid", default="auto", show_default=True)
@click.pass_context
def switch_pm(
    ctx: click.Context,
    project_id: str,
    to_mission_id: str,
    reason: str,
    summary: str,
    as_owner: str,
    approval_evidence_ref: str,
    lease_seconds: int,
    holder_pid: str,
) -> None:
    """插急活一步完成：把在干的卡搁着，再把目标卡拿起来；第二步失败时第一张稳稳停在“搁着”。"""

    service = _service(ctx, mutating=bool(to_mission_id))
    approval_pin = (
        read_approval_pin(_root(ctx), summary=f"插急活：把手上的卡搁着，改干 {to_mission_id}") if to_mission_id else ""
    )
    try:
        outcome = service.switch(
            project_id=project_id,
            to_mission_id=to_mission_id or None,
            reason=reason,
            summary=summary,
            as_owner=as_owner,
            approval_evidence_ref=approval_evidence_ref,
            lease_seconds=lease_seconds,
            holder_pid=_holder_pid(holder_pid) if to_mission_id else None,
            approval_pin=approval_pin,
        )
    except MissionSwitchError as error:
        raise click.ClickException(str(error)) from error
    _echo(
        {
            "schema_version": "pm-switch.v1",
            "parked": _park_payload(outcome.parked) if outcome.parked else None,
            "started": _unpark_payload(outcome.started) if outcome.started else None,
            "recommended_mission_id": outcome.recommended_mission_id,
            "next_command": outcome.next_command,
            "note": outcome.note,
        }
    )
