"""Claim CLI: cross-machine card claims on GitHub (D-39).  Git and ``origin`` only -- no ledger, so a cloud session can run it.

退出码：0 成功；1 被拒绝（卡被领走、路径重叠、不是自己的占位）；2 Git 出错或离线。
"""

from __future__ import annotations

import json
import os

import click

from auto_pm.app_context import AppContext
from auto_pm.application.core.agent_worktree_service import caller_agent, caller_alias
from auto_pm.application.core.claim_service import ClaimError, ClaimService


def _service(ctx: click.Context) -> ClaimService:
    app_ctx: AppContext = ctx.obj
    return ClaimService(app_ctx.control_root or app_ctx.workspace_root or os.getcwd())


def _owner(explicit: str) -> str:
    """Default owner is this conversation's alias (``claude-a119dc``), so two conversations of one agent never share a claim (D-112).

    No session id (or the user's own terminal) falls back to the bare agent name, as before.  A claim made before D-112 carries the
    bare name; only an explicit ``--as claude`` can release or renew it.
    """

    return explicit.strip() or caller_alias() or caller_agent().strip("?") or "user"


def _fail(error: ClaimError) -> None:
    click.echo(f"拒绝 {error}", err=True)
    raise SystemExit(1)


@click.group(name="claim")
def claim_group() -> None:
    """跨电脑、跨云端会话的领卡占位（远程分支 claims/<卡号>，原子创建，两边抢同一张卡只有一个成功）。"""


@claim_group.command(name="open")
@click.argument("card")
@click.option("--paths", "paths", multiple=True, required=True, help="要改的路径，可重复；目录覆盖其下全部文件")
@click.option("--goal", default="", help="一句话目标")
@click.option("--as", "owner", default="", help="谁领的；缺省取调用方（agent 名或 user）")
@click.pass_context
def open_claim(ctx: click.Context, card: str, paths: tuple[str, ...], goal: str, owner: str) -> None:
    """领卡。CARD 写卡号，或写 auto 取下一个空号。"""
    try:
        claim = _service(ctx).open(card, paths=paths, goal=goal, owner=_owner(owner))
    except ClaimError as error:
        _fail(error)
        return
    click.echo(f"已领 {claim.label()}；路径：{'、'.join(claim.paths)}")


@claim_group.command(name="list")
@click.option("--json", "as_json", is_flag=True, help="stdout 只输出 JSON")
@click.option("--no-fetch", is_flag=True, help="不联网，只看本机已知的占位")
@click.pass_context
def list_claims(ctx: click.Context, as_json: bool, no_fetch: bool) -> None:
    """只读：列出远程所有占位（已放下或租约到期（默认 4 小时，持有者 `claim renew` 续）的视为空闲，不会自动删）。"""
    try:
        claims = _service(ctx).all_claims(fetch=not no_fetch)
    except ClaimError as error:
        click.echo(f"错误 {error}", err=True)
        raise SystemExit(2) from error
    if as_json:
        click.echo(json.dumps([claim.as_json() for claim in claims], ensure_ascii=False, indent=2))
        return
    if not claims:
        click.echo("没有占位。")
    for claim in claims:
        mark = "（已放下或租约到期，视为空闲）" if claim.free else ""
        click.echo(f"{claim.label()} {claim.claimed_at} 路径：{'、'.join(claim.paths)}{mark}")


@claim_group.command(name="release")
@click.argument("card")
@click.option("--as", "owner", default="", help="谁在放；必须与领卡时一致")
@click.pass_context
def release_claim(ctx: click.Context, card: str, owner: str) -> None:
    """放下自己的占位：推一个提交把它标成已放下，不删分支（云端也能用）；PR 合并后或用户说放弃时用。"""
    try:
        _service(ctx).release(card, owner=_owner(owner))
    except ClaimError as error:
        _fail(error)
        return
    click.echo(f"已放下卡 {card}")


@claim_group.command(name="renew")
@click.argument("card")
@click.option("--as", "owner", default="", help="谁在续；必须与领卡时一致")
@click.pass_context
def renew_claim(ctx: click.Context, card: str, owner: str) -> None:
    """续租自己的占位：还在干活就续，把到期时间推到现在 + 4 小时；停了不续，到期自动算空闲。"""
    try:
        renewed = _service(ctx).renew(card, owner=_owner(owner))
    except ClaimError as error:
        _fail(error)
        return
    click.echo(f"已续租 {renewed.label()}，到期 {renewed.expires_at}")


@claim_group.command(name="reclaim")
@click.argument("card")
@click.option("--reason", required=True, help="为什么收回（对方没动静、状态未知等）")
@click.option("--approval-evidence-ref", default="", help="用户原话所在的位置，写成 user-confirmation:<消息时间或编号>；收回别人的占位只听用户的")
@click.option("--as", "by", default="", help="谁在收；缺省取调用方")
@click.pass_context
def reclaim_claim(ctx: click.Context, card: str, reason: str, approval_evidence_ref: str, by: str) -> None:
    """收回别人没动静的占位：推一个“已收回”提交（写明谁、为什么、依据哪句用户的话），不删分支，卡随即空闲。"""
    try:
        claim = _service(ctx).reclaim(card, by=_owner(by), reason=reason, approval_ref=approval_evidence_ref)
    except ClaimError as error:
        _fail(error)
        return
    click.echo(f"卡 {card} 的占位已收回（现状态：{claim.status}）")
