"""The user's approval PIN on the command line (gap 9): ``pm approver-pin`` and the hidden prompt every approval uses.

The PIN is typed by the user into a terminal, hidden.  There is no option, environment variable or file for it, so an
agent has no way to pass a PIN along; a session without a terminal is refused at once instead of waiting.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click

from auto_pm.app_context import AppContext
from auto_pm.application.core.approval_proof_service import (
    REGISTRY_RELATIVE_PATH,
    ApprovalProof,
    ApprovalProofError,
    ApprovalProofService,
    make_key,
    pin_problem,
)
from auto_pm.application.core.lease_handover_service import agent_markers
from auto_pm.contracts.user_evidence import user_evidence_problem

NO_TERMINAL = (
    "已启用批准口令：这一步必须由用户本人在自己的终端运行这条命令并输入口令（当前不是交互终端）。"
    "agent 请把完整命令交给用户，不得索要或代填口令"
)


def _stdin_is_tty() -> bool:
    """A real terminal.  On Windows ``isatty`` is also true for the NUL device (a character device), so a session started
    with stdin closed would be taken for a user at a keyboard and wait for a PIN nobody can type; ask the console itself."""

    if not sys.stdin.isatty():
        return False
    if os.name != "nt":
        return True
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined,unused-ignore]
    # Without restype/argtypes ctypes treats the HANDLE as a 32-bit int, which truncates it on 64-bit Windows.
    kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
    kernel32.GetStdHandle.restype = wintypes.HANDLE
    kernel32.GetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.LPDWORD]
    kernel32.GetConsoleMode.restype = wintypes.BOOL
    mode = wintypes.DWORD()
    return bool(kernel32.GetConsoleMode(kernel32.GetStdHandle(wintypes.DWORD(-10)), ctypes.byref(mode)))


def _prompt_hidden(text: str) -> str:
    return str(click.prompt(text, hide_input=True, default="", show_default=False, err=True))


def refuse_agent_approval(action: str, evidence_ref: str = "") -> None:
    """Refuse (``ClickException``) when the session carries an agent marker and no user evidence backs the approval.

    The approval PIN only protects a root that has one committed; without it the old format check lets any caller write
    any approver name, so an agent could approve its own change order or decision package (Trae probe F16).  This
    refusal does not depend on the PIN.  The user ruled (A, 2026-10-31): same as ``pm approve``, an agent session may
    go ahead when it passes ``--approval-evidence-ref user-confirmation:<the user's message>`` in the form
    ``user_evidence_problem`` accepts (the standing pre-authorisation of 2026-10-18 depends on it); with none, or one
    that looks agent-written, it is refused.  With a committed PIN the user still types it in a terminal afterwards.
    Best effort, like the other agent-marker refusals: the markers are environment variables (single-user trust model).
    """

    markers = agent_markers(os.environ)
    if not markers:
        return
    if evidence_ref.strip():
        problem = user_evidence_problem(evidence_ref.strip())
        if not problem:
            return
        detail = f"给的凭据不被接受：{problem}"
    else:
        detail = "没有带用户原话凭据"
    raise click.ClickException(
        f"这是 agent 会话（{'、'.join(markers)}），不能{action}：{detail}。"
        "批准只听用户本人：请带上 --approval-evidence-ref user-confirmation:<用户那条消息的时间或编号>"
        "（只能引用用户真说过的话，不得自编），或把完整命令交给用户在自己的终端运行；"
        "已启用批准口令时还要用户本人输入口令，agent 不得索要口令、代填或绕过"
    )


def control_root(ctx: click.Context) -> Path:
    app_ctx: AppContext = ctx.find_root().obj
    return Path(getattr(app_ctx, "control_root", None) or app_ctx.workspace_root)


def approval_pin_enforced(root: str | Path) -> bool:
    """Whether an approver PIN is committed in ``root`` (read-only; never prompts)."""

    try:
        return ApprovalProofService(root).enforced()
    except ApprovalProofError as error:
        raise click.ClickException(str(error)) from error


def read_approval_pin(root: str | Path, *, summary: str) -> str:
    """'' when no approver PIN is committed in ``root`` (old format check); otherwise the PIN the user types, hidden.

    ``root`` must be the root the command then writes to (audit 72, high-2): a PIN looked up in one root and an
    approval written into another is no proof at all.
    """

    service = ApprovalProofService(root)
    try:
        if not service.enforced():
            return ""
    except ApprovalProofError as error:
        raise click.ClickException(str(error)) from error
    if not _stdin_is_tty():
        raise click.ClickException(NO_TERMINAL)
    click.echo(summary, err=True)
    return _prompt_hidden("请输入批准口令（输入时不显示）")


def require_approval_pin(
    root: str | Path, *, summary: str, purpose: str, subject: str, approver: str = ""
) -> ApprovalProof | None:
    """For a command whose own service has no PIN gate: verify here, in the root it writes to, before anything is written.

    None under the old format check; otherwise the proof, whose approver must be ``approver`` when one was given.
    """

    pin = read_approval_pin(root, summary=summary)
    try:
        proof = ApprovalProofService(root).require(pin=pin, purpose=purpose, subject=subject)
    except ApprovalProofError as error:
        raise click.ClickException(str(error)) from error
    if proof is not None and approver.strip() and approver.strip() != proof.approver:
        raise click.ClickException(f"批准口令属于 {proof.approver}，与填写的批准人 {approver.strip()} 不一致")
    if proof is not None:
        click.echo(f"已凭 {proof.approver} 的批准口令（编号 {proof.key_id}）批准", err=True)
    return proof


@click.group(name="approver-pin")
def approver_pin_group() -> None:
    """用户本人的批准口令：设置后，批准范围和最终验收都要在终端输入口令，agent 造不出来。"""


@approver_pin_group.command(name="status")
@click.pass_context
def approver_pin_status(ctx: click.Context) -> None:
    """只读：批准口令是否已生效（以 Git 已提交的登记文件为准）。"""

    service = ApprovalProofService(control_root(ctx))
    try:
        committed, problem = service.committed_state()
        working = service.working_keys()
    except ApprovalProofError as error:
        raise click.ClickException(str(error)) from error
    if problem:
        click.echo("批准口令：所有批准暂停。" + problem)
    elif committed is None:
        click.echo("批准口令：未生效（Git HEAD 里没有 " + REGISTRY_RELATIVE_PATH + "），批准只做格式检查")
    else:
        click.echo("批准口令：已生效；批准人 " + "、".join(f"{key.approver}（{key.key_id}）" for key in committed))
    committed_ids = {key.key_id for key in committed or []}
    if {key.key_id for key in working} != committed_ids:
        click.echo("注意：工作区里的登记文件与已提交的不一致；只有提交后的内容算数")


@approver_pin_group.command(name="init")
@click.option("--approver", required=True, help="你的名字（批准记录里显示的批准人）")
@click.pass_context
def approver_pin_init(ctx: click.Context, approver: str) -> None:
    """只限用户本人：设置或更换批准口令。写入登记文件后要提交（git commit）才生效。"""

    markers = agent_markers(os.environ)
    if markers:
        raise click.ClickException(
            "这是 agent 会话（" + "、".join(markers) + "），不能设置批准口令；请用户本人在自己的终端运行"
        )
    if not _stdin_is_tty():
        raise click.ClickException("批准口令只能由用户本人在交互式终端里设置")
    service = ApprovalProofService(control_root(ctx))
    try:
        # An uncommitted or vanished registry refuses approvals but must not stop the user from setting the PIN again.
        committed, _problem = service.committed_state()
        keys = service.working_keys()
    except ApprovalProofError as error:
        raise click.ClickException(str(error)) from error
    approver = approver.strip()
    if committed is not None and any(key.approver == approver for key in committed):
        old = _prompt_hidden(f"{approver} 已有批准口令；请先输入旧口令")
        try:
            proof = service.attest(old, purpose="pin-rotate", subject=approver)
        except ApprovalProofError as error:
            raise click.ClickException(str(error)) from error
        if proof.approver != approver:
            raise click.ClickException(f"旧口令属于 {proof.approver}，不是 {approver}")
    pin = _prompt_hidden("请设置批准口令（至少 10 位、不能全是数字，输入时不显示）")
    problem = pin_problem(pin)
    if problem:
        raise click.ClickException(problem)
    if _prompt_hidden("请再输入一次") != pin:
        raise click.ClickException("两次输入不一致，未设置")
    try:
        key = make_key(approver, pin)
    except ApprovalProofError as error:
        raise click.ClickException(str(error)) from error
    path = service.write_working_keys([item for item in keys if item.approver != approver] + [key])
    click.echo(f"已写入 {path}（只存口令的校验值，不存口令本身）。你的口令编号（key_id）：{key.key_id}，请记下。")
    click.echo("下一步：把这个文件提交（git add + git commit）。提交之后口令才生效；提交之前所有批准一律暂停。")
    click.echo("提交后运行 pm approver-pin status，核对显示的口令编号和上面这个一样（不一样说明文件被别人换过）。")
    click.echo("口令只在终端里输入，永远不要发给任何 AI 或写进聊天。")
