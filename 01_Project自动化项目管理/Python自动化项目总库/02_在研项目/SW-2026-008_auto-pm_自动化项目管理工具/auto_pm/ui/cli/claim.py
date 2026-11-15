"""Claim CLI: cross-machine card claims on GitHub (D-39).  Git and ``origin`` only -- no ledger, so a cloud session can run it.

退出码：0 成功；1 被拒绝（卡被领走、路径重叠、不是自己的占位、交接记录不合规则）；2 Git 出错或离线。
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path

import click

from auto_pm.app_context import AppContext
from auto_pm.application.core.agent_worktree_service import caller_agent, caller_alias
from auto_pm.application.core.claim_note_service import (
    KINDS,
    VERDICTS,
    VERIFICATIONS,
    ClaimNoteRefusedError,
    ClaimNoteService,
    Note,
)
from auto_pm.application.core.claim_service import ClaimError, ClaimService


def _root(ctx: click.Context) -> str:
    app_ctx: AppContext = ctx.obj
    return app_ctx.control_root or app_ctx.workspace_root or os.getcwd()


def _service(ctx: click.Context) -> ClaimService:
    return ClaimService(_root(ctx))


def normalise_paths(root: Path, cwd: Path, paths: Sequence[str]) -> tuple[list[str], list[str]]:
    """Claim paths are repository-root paths (D-115); a path written relative to the folder the agent stands in is lifted to one.

    ``pr_overlap_check`` compares a PR's changed files, which are repository-root paths, against the claim: ``auto_pm/x.py`` typed
    from inside the project folder would never cover ``<project folder>/auto_pm/x.py``.  Returns (paths, notes about what was
    rewritten); an absolute path inside the repository becomes relative to it, one outside it is refused by the caller.
    """

    root = root.resolve()
    cwd = cwd.resolve()
    result: list[str] = []
    notes: list[str] = []
    for raw in paths:
        text = raw.strip().replace("\\", "/")
        path = Path(text)
        if path.is_absolute():
            try:
                fixed = path.resolve().relative_to(root).as_posix()
            except ValueError:
                raise click.UsageError(f"路径 {raw} 在仓库 {root} 之外；领卡只认仓库内的路径") from None
            notes.append(f"{raw} → {fixed}")
            result.append(fixed)
            continue
        text = text.removeprefix("./")
        first = text.split("/", 1)[0]
        lifted = ""
        if first and not (root / first).exists() and cwd != root and (cwd / first).exists():
            try:
                lifted = (cwd / text).relative_to(root).as_posix()
            except ValueError:
                lifted = ""
        if lifted:
            notes.append(f"{raw} → {lifted}")
        result.append(lifted or text)
    return result, notes


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
    fixed, notes = normalise_paths(Path(_root(ctx)), Path.cwd(), paths)
    for note in notes:
        click.echo(f"路径已按仓库根补全：{note}", err=True)
    try:
        claim = _service(ctx).open(card, paths=fixed, goal=goal, owner=_owner(owner))
    except ClaimError as error:
        _fail(error)
        return
    click.echo(f"已领 {claim.label()}；路径：{'、'.join(claim.paths)}")


@claim_group.command(name="number")
@click.option("--goal", required=True, help="一句话说明这个号用来做什么卡（必填：别人看占位表靠它认出这个号是谁拿去做什么的）")
@click.option("--as", "owner", default="", help="谁领的；缺省取调用方（agent 名或 user）")
@click.pass_context
def number_claim(ctx: click.Context, goal: str, owner: str) -> None:
    """只领号：取下一个不会撞的卡号，不占任何路径（落卡文件时用；开工时再 `claim add-paths` 补路径）。"""
    try:
        claim = _service(ctx).reserve_number(goal=goal, owner=_owner(owner))
    except ClaimError as error:
        _fail(error)
        return
    click.echo(f"已领号 {claim.card}（{claim.label()}）")
    click.echo(f"卡文件名：…/02_规划/{claim.card}_<名称>_PM.md")
    click.echo(f"开工时补路径：main.py claim add-paths {claim.card} --paths <要改的文件> --as {claim.owner}")


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
        if not no_fetch:
            click.echo("离线或连不上 GitHub 时，可加 --no-fetch 看本机上次抓到的占位（可能不是最新，不能当作没人占着）", err=True)
        raise SystemExit(2) from error
    if no_fetch:
        click.echo("（离线视图：只含本机上次抓取时的占位，可能不是最新；开卡、开 PR 前以联网结果为准）", err=True)
    if as_json:
        click.echo(json.dumps([claim.as_json() for claim in claims], ensure_ascii=False, indent=2))
        return
    if not claims:
        click.echo("没有占位。")
    for claim in claims:
        mark = "（已放下或租约到期，视为空闲）" if claim.free else ""
        paths = "、".join(claim.paths) if claim.paths else "（只占号，未补路径）"
        click.echo(f"{claim.label()} {claim.claimed_at} 路径：{paths}{mark}")


@claim_group.command(name="release")
@click.argument("card")
@click.option("--as", "owner", default="", help="谁在放；必须与领卡时一致")
@click.pass_context
def release_claim(ctx: click.Context, card: str, owner: str) -> None:
    """放下自己的占位：推一个提交把它标成已放下，不删分支（云端也能用）；PR 合并后或用户说放弃时用。"""
    try:
        written = _service(ctx).release(card, owner=_owner(owner))
    except ClaimError as error:
        _fail(error)
        return
    if written:
        click.echo(f"已放下卡 {card}（远程已记为 released）")
    else:
        click.echo(f"卡 {card} 早就放下或被收回了，这次什么都没写")


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


@claim_group.command(name="add-paths")
@click.argument("card")
@click.option("--paths", "paths", multiple=True, required=True, help="要追加的路径，可重复；目录覆盖其下全部文件")
@click.option("--as", "owner", default="", help="谁在追加；必须与领卡时一致")
@click.pass_context
def add_paths_claim(ctx: click.Context, card: str, paths: tuple[str, ...], owner: str) -> None:
    """给自己的占位追加路径：领卡后发现还要改别的文件时用，不必放下重领（重领会重置领卡时间，已有提交就排到领卡之前）。"""
    fixed, notes = normalise_paths(Path(_root(ctx)), Path.cwd(), paths)
    for note in notes:
        click.echo(f"路径已按仓库根补全：{note}", err=True)
    try:
        claim = _service(ctx).add_paths(card, owner=_owner(owner), paths=fixed)
    except ClaimError as error:
        _fail(error)
        return
    if not claim.written:  # TD-SW008-611（D-346）：要加的路径都已在占位里，服务什么都没推，不能说“已追加”
        click.echo(f"要加的路径都已在 {claim.label()} 的占位里，这次什么都没写；现在的路径：{'、'.join(claim.paths)}")
        return
    click.echo(f"已追加路径 {claim.label()}；现在的路径：{'、'.join(claim.paths)}（领卡时间和到期时间不变）")


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
    if claim.written:
        click.echo(f"卡 {card} 的占位已收回（远程已记为 {claim.status}）")
    else:
        click.echo(f"卡 {card} 的占位早就是 {claim.status}，这次什么都没写")


# ── hand-over record (claim note / claim log) ─────────────────────────────

_VERDICT_NAMES = {"pass": "通过", "fail": "不通过", "fix": "要改"}
_VERIFY_NAMES = {"lint": "检查通过", "test": "测试通过", "other": "其他", "none": "没跑"}
_KIND_HELP = "、".join(f"{key}={name}" for key, name in KINDS.items())


def _note_service(ctx: click.Context) -> ClaimNoteService:
    return ClaimNoteService(_root(ctx))


def _note_line(note: Note) -> str:
    parts = [f"{note.sequence}. {note.text('at')} {KINDS.get(note.kind, note.kind)}：{note.text('from')} → {note.text('to')}"]
    if note.text("verdict"):
        parts.append(f"结论 {_VERDICT_NAMES.get(note.text('verdict'), note.text('verdict'))}")
    if note.text("verify"):
        parts.append(f"验证 {_VERIFY_NAMES.get(note.text('verify'), note.text('verify'))}")
    if note.text("chg"):
        parts.append(f"变更单 {note.text('chg')}")
    if note.text("pr"):
        parts.append(f"PR #{note.text('pr')}")
    parts.append(f"提交 {note.text('git_head')[:12]}")
    lines = ["；".join(parts) + f"（记录 {note.commit[:12]}）"]
    refs = note.data.get("refs", [])
    for ref in refs if isinstance(refs, list) else []:
        if isinstance(ref, dict):
            lines.append(f"   引用 {ref.get('path')} sha256 {str(ref.get('sha256'))[:16]}…")
    outside = note.data.get("refs_outside", [])
    for ref in outside if isinstance(outside, list) else []:
        if isinstance(ref, dict):
            lines.append(f"   仓库外引用 {ref.get('path')} sha256 {str(ref.get('sha256'))[:16]}…（没核）")
    if note.items("changed"):
        lines.append(f"   改了：{'、'.join(note.items('changed'))}")
    for key, label in (("risk", "风险"), ("caution", "注意"), ("ask_user", "请用户说（只是提示，不是批准）")):
        if note.text(key):
            lines.append(f"   {label}：{note.text(key)}")
    lines.append(f"   下一步：{note.text('next')}")
    return "\n".join(lines)


@claim_group.command(name="note")
@click.argument("card")
@click.option("--kind", required=True, help=f"这一棒是什么：{_KIND_HELP}")
@click.option("--to", "to", required=True, help="交给谁")
@click.option("--next", "next_step", required=True, help="下一棒做什么；真的没有就写“无”")
@click.option("--git-head", default="", help="交的时候的提交号；缺省取当前 HEAD。必须是 origin 上有的提交")
@click.option("--ref", "refs", multiple=True, help="仓库里的文件路径（仓库根起），可重复；哈希由命令按 --git-head 那个提交算")
@click.option("--ref-outside", "refs_outside", multiple=True, help="仓库外的引用，写成 路径#sha256，可重复；不核，读出来时标“没核”")
@click.option("--chg", default="", help="变更单号")
@click.option("--pr", type=int, default=None, help="PR 号；会去 origin 核对有没有")
@click.option("--verdict", default="", help=f"预核、比对、审计必填：{'|'.join(VERDICTS)}")
@click.option("--verify", default="", help=f"交卷必填，怎么验证的：{'|'.join(VERIFICATIONS)}")
@click.option("--changed", multiple=True, help="交卷必填：改了哪些文件，可重复；必须落在占位登记的路径里")
@click.option("--risk", default="", help="风险")
@click.option("--caution", default="", help="注意事项")
@click.option("--ask-user", default="", help="请用户这一笔必填：要请用户说的那句完整的话。只是提示，不是批准")
@click.option("--read-first", multiple=True, help="接手的人先读哪些文件（仓库根起），可重复")
@click.option("--as", "sender", default="", help="谁记的；缺省取调用方")
@click.option("--json", "as_json", is_flag=True, help="stdout 只输出 JSON")
@click.pass_context
def note_claim(
    ctx: click.Context,
    card: str,
    kind: str,
    to: str,
    next_step: str,
    git_head: str,
    refs: tuple[str, ...],
    refs_outside: tuple[str, ...],
    chg: str,
    pr: int | None,
    verdict: str,
    verify: str,
    changed: tuple[str, ...],
    risk: str,
    caution: str,
    ask_user: str,
    read_first: tuple[str, ...],
    sender: str,
    as_json: bool,
) -> None:
    """在这张卡的交接记录上记一笔（只追加；只记引用和下一步，不记状态）。记之前先要有占位：没订卡的先 `claim number` 领号。"""
    arguments = {
        "kind": kind, "sender": _owner(sender), "to": to, "next_step": next_step, "git_head": git_head, "refs": refs,
        "refs_outside": refs_outside, "chg": chg, "pr": pr, "verdict": verdict, "verify": verify, "changed": changed,
        "risk": risk, "caution": caution, "ask_user": ask_user, "read_first": read_first,
    }
    try:
        note = _note_service(ctx).add(card, **arguments)  # type: ignore[arg-type]
    except ClaimNoteRefusedError as error:
        _fail(error)
        return
    except ClaimError as error:
        click.echo(f"错误 {error}", err=True)
        click.echo("这一笔没有记上，也没有存在本机。联网后原样重记：", err=True)
        click.echo(json.dumps({"card": card, **{key: value for key, value in arguments.items() if value not in ("", None, ())}}, ensure_ascii=False), err=True)
        raise SystemExit(2) from error
    if as_json:
        click.echo(json.dumps(note.as_json(), ensure_ascii=False, indent=2))
        return
    click.echo(f"已记第 {note.sequence} 笔（{KINDS[note.kind]}，记录 {note.commit[:12]}）；下一棒：{note.text('to')}，{note.text('next')}")


@claim_group.command(name="log")
@click.argument("card")
@click.option("--json", "as_json", is_flag=True, help="stdout 只输出 JSON")
@click.option("--no-fetch", is_flag=True, help="不联网，只看本机已知的记录")
@click.pass_context
def log_claim(ctx: click.Context, card: str, as_json: bool, no_fetch: bool) -> None:
    """只读：按顺序读出这张卡的交接记录，最后说明现在轮到谁、做什么、先读什么。这里不显示状态，状态看项目体检。"""
    try:
        notes = _note_service(ctx).log(card, fetch=not no_fetch)
    except ClaimNoteRefusedError as error:
        _fail(error)
        return
    except ClaimError as error:
        click.echo(f"错误 {error}", err=True)
        if not no_fetch:
            click.echo("离线或连不上 GitHub 时，可加 --no-fetch 看本机上次抓到的记录（可能不是最新）", err=True)
        raise SystemExit(2) from error
    if no_fetch:
        click.echo("（离线视图：只含本机上次抓取时的记录，可能不是最新）", err=True)
    if as_json:
        click.echo(json.dumps([note.as_json() for note in notes], ensure_ascii=False, indent=2))
        return
    if not notes:
        click.echo("这张卡还没有交接记录。")
        return
    for note in notes:
        click.echo(_note_line(note))
    last = notes[-1]
    click.echo(f"最后一笔：{KINDS.get(last.kind, last.kind)}，{last.text('from')} → {last.text('to')}，{last.text('at')}")
    click.echo(f"下一棒：{last.text('to')}，{last.text('next')}")
    click.echo(f"先读：{'、'.join(last.items('read_first')) or '无'}")
