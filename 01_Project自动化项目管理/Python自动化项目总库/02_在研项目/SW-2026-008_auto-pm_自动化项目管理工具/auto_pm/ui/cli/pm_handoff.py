"""PM-level agent swap commands: ``pm handoff``, ``pm takeover`` and the user's ``pm sign-risk`` (M3-HANDOFF card, TD-SW008-063).

An agent never handles a lease token: ``pm handoff`` reads the holder's token from the local wallet (or an environment variable),
``pm takeover`` generates the receiver's token and writes it to the wallet.  ``pm sign-risk`` is for the user only.
"""

from __future__ import annotations

import getpass
import json
import os
import sys
from typing import Any

import click

from auto_pm import __version__
from auto_pm.app_context import AppContext
from auto_pm.application.core.lease_handover_service import LeaseHandoverError, LeaseHandoverService
from auto_pm.application.core.pm_facade_service import PmFacadeError, PmFacadeService
from auto_pm.application.core.work_registry_service import WorkRegistryService
from auto_pm.application.core.worktree_policy_service import (
    WorktreePolicyError,
    WorktreePolicyService,
)
from auto_pm.infrastructure import process_probe
from auto_pm.infrastructure.continuity_store import ContinuityStore, ContinuityStoreError
from auto_pm.ui.cli.approval_pin import require_approval_pin
from auto_pm.ui.cli.runtime_identity_guard import project_of_run, require_runtime_identity

RISK_PHRASE = "接受风险"


def _stdin_is_tty() -> bool:
    return sys.stdin.isatty()


def _stdout_is_tty() -> bool:
    return sys.stdout.isatty()


def _service(ctx: click.Context) -> LeaseHandoverService:
    app_ctx: AppContext = ctx.find_root().obj
    try:
        WorktreePolicyService(app_ctx.control_root).require_control_root()
    except WorktreePolicyError as error:
        raise click.ClickException(str(error)) from error
    WorkRegistryService(app_ctx.control_root).initialize(__version__)
    return LeaseHandoverService(app_ctx.control_root)


def _store(ctx: click.Context) -> ContinuityStore:
    app_ctx: AppContext = ctx.find_root().obj
    return ContinuityStore(app_ctx.control_root)


def _echo(payload: dict[str, Any]) -> None:
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))


def _holder_pid(value: str) -> int | None:
    if value == "none":
        return None
    if value == "auto":
        return process_probe.holder_process_pid()
    if value.isdigit() and int(value) > 0:
        return int(value)
    raise click.BadParameter("--holder-pid 必须是 auto、none 或正整数")


@click.command(name="handoff")
@click.option("--run-id", required=True, help="要交出去的 Run")
@click.option("--to", "to_owner", required=True, help="接手的 agent 身份，例如 claude:local 或 trae:cn")
@click.option("--summary", default="换 agent 交接", show_default=True, help="写进检查点的交接摘要")
@click.option(
    "--lease-token-env", default=None, metavar="ENV_NAME", help="口令所在环境变量；省略时从本机钱包读取当前持有者的口令"
)
@click.pass_context
def handoff_pm(ctx: click.Context, run_id: str, to_owner: str, summary: str, lease_token_env: str | None) -> None:
    """当前持有者一条命令交接：记检查点并生成发给接手方的 handoff；交接后请停止写入。"""

    service = _service(ctx)
    require_runtime_identity(ctx, project_of_run(ctx, run_id))
    try:
        owner = _store(ctx).get_lease(run_id).owner_id
    except ContinuityStoreError as error:
        raise click.ClickException(str(error)) from error
    if lease_token_env is not None:
        from auto_pm.ui.cli.continuity import _secret_from_environment

        token = _secret_from_environment(lease_token_env)
    else:
        try:
            token = service.token_for(run_id, owner)
        except LeaseHandoverError as error:
            raise click.ClickException(str(error)) from error
    try:
        outcome = service.handoff(run_id=run_id, to_owner=to_owner, lease_token=token, summary=summary)
    except LeaseHandoverError as error:
        raise click.ClickException(str(error)) from error
    _echo(
        {
            "schema_version": "pm-handoff.v1",
            "handoff_id": outcome.handoff.handoff_id,
            "run_id": outcome.handoff.run_id,
            "work_id": outcome.handoff.work_id,
            "from_owner": outcome.handoff.from_owner,
            "to_owner": outcome.handoff.to_owner,
            "checkpoint_id": outcome.checkpoint.checkpoint_id,
            "next_command": f"main.py pm takeover --handoff-id {outcome.handoff.handoff_id} --as {outcome.handoff.to_owner}",
            "note": "交接已生成；接手方运行 next_command 之前你的口令仍有效，但请停止写入。",
        }
    )


@click.command(name="takeover")
@click.option("--handoff-id", required=True)
@click.option("--as", "receiver_id", required=True, help="你自己的 agent 身份，必须与交接指定的接收方一致")
@click.option("--lease-seconds", type=click.IntRange(60, 3_600), default=900, show_default=True)
@click.option("--holder-pid", default="auto", show_default=True, help="记录你的长驻进程：auto（调用本命令的 shell 或 IDE）、none 或 pid")
@click.pass_context
def takeover_pm(ctx: click.Context, handoff_id: str, receiver_id: str, lease_seconds: int, holder_pid: str) -> None:
    """接手方先只读定位，再接手：自己生成口令存入本机钱包，旧持有者的口令随即失效。"""

    app_ctx: AppContext = ctx.find_root().obj
    service = _service(ctx)
    try:
        handoff = service.get_handoff(handoff_id)
        project_id = _store(ctx).get_work(handoff.work_id).subject_project_id
    except (LeaseHandoverError, ContinuityStoreError) as error:
        raise click.ClickException(str(error)) from error
    require_runtime_identity(ctx, project_id)
    try:
        orient = PmFacadeService(app_ctx.control_root, execution_root=app_ctx.workspace_root).orient(
            project_id=project_id, invocation_path=None, work_id=handoff.work_id, run_id=handoff.run_id, requested_action=""
        )
    except PmFacadeError as error:
        raise click.ClickException(f"接手前的只读定位失败，未接手: {error}") from error
    try:
        lease = service.takeover(
            handoff_id=handoff_id, receiver_id=receiver_id, lease_seconds=lease_seconds, holder_pid=_holder_pid(holder_pid)
        )
    except LeaseHandoverError as error:
        raise click.ClickException(str(error)) from error
    _echo(
        {
            "schema_version": "pm-takeover.v1",
            "orient": {
                "evidence_id": orient.evidence_id,
                "subject_project_id": orient.context.subject_project_id,
                "work_id": orient.work.work_id if orient.work else "",
                "run_id": orient.run.run_id if orient.run else "",
                "next_legal_action": orient.next_legal_action,
                "conflicts": list(orient.conflicts),
            },
            "run_id": lease.run_id,
            "owner_id": lease.owner_id,
            "epoch": lease.epoch,
            "expires_at": lease.expires_at,
            "expires_local": ContinuityStore.local_time_text(lease.expires_at),
            "wallet_path": lease.wallet_path,
            "holder_process_recorded": lease.holder_process_recorded,
            "next": "后续写命令加 --lease-wallet（例如 continuity lease renew、checkpoint create、run transition），不要手抄口令。",
        }
    )


def _shown(typed: str, limit: int = 40) -> str:
    """The user's wrong input echoed back in a bounded, single-line form (the phrase and the Run id are not secrets)."""

    flat = " ".join(typed.split())
    return flat if len(flat) <= limit else flat[:limit] + "…"


@click.command(name="sign-risk")
@click.option("--run-id", required=True)
@click.option("--claimant", "claimant_id", required=True, help="将要接手的 agent 身份")
@click.pass_context
def sign_risk_pm(ctx: click.Context, run_id: str, claimant_id: str) -> None:
    """只限用户本人：在自己的交互式终端里签署“接受风险”，允许在无法判断原持有者进程时回收 Run。agent 会话一律拒绝。"""

    refusal = LeaseHandoverService.signature_refusal(
        os.environ, stdin_is_tty=_stdin_is_tty(), stdout_is_tty=_stdout_is_tty()
    )
    if refusal:
        raise click.ClickException(refusal)
    service = _service(ctx)
    require_runtime_identity(ctx, project_of_run(ctx, run_id))
    store = _store(ctx)
    try:
        lease = store.get_lease(run_id)
        verdict, recorded = service.judge_holder(run_id)
    except (ContinuityStoreError, LeaseHandoverError) as error:
        raise click.ClickException(str(error)) from error
    click.echo(f"Run {run_id} 现在由 {lease.owner_id} 持有，租约到 {ContinuityStore.local_time_text(lease.expires_at)}（本机时间）。")
    click.echo(f"原持有者进程判定：{verdict.value}" + ("（没有记录进程）" if recorded is None else f"（记录的 pid {recorded.pid}）"))
    click.echo(f"签署后，{claimant_id} 可以在租约失效后接手；如果原持有者其实还在干活，它之后的写入会全部被拒绝。")
    if claimant_id == lease.owner_id:
        click.echo(
            f"提醒：申请人 {claimant_id} 与当前持有者同名，回收会被拒（“你已是当前持有者”），这份签字用不上。"
            "请按 Ctrl+C 退出，换一个新名字作为 --claimant 再签署。"
        )
    click.echo("接下来有两次输入（口令开启时另有第三次）：")
    click.echo(f"  第 1 次：把上面“Run”后面那一整串编号原样输入，即 {run_id}（不要只输一部分，也不要输申请人名字）")
    click.echo(f"  第 2 次：输入这四个字：{RISK_PHRASE}")
    click.echo("  输错不会签署任何东西，直接重新运行同一条命令即可。")
    typed_run = click.prompt(f"第 1 次（共 2 次）请输入 Run 编号 {run_id}", default="", show_default=False)
    if typed_run.strip() != run_id:
        raise click.ClickException(
            f"Run 编号不一致，未签署。你输入的是“{_shown(typed_run)}”，应当是“{run_id}”（命令里 --run-id 后面的整串）。"
            "请重新运行同一条命令。"
        )
    typed_phrase = click.prompt(f"第 2 次（共 2 次）请输入“{RISK_PHRASE}”四个字", default="", show_default=False)
    if typed_phrase.strip() != RISK_PHRASE:
        raise click.ClickException(
            f"未输入“{RISK_PHRASE}”，未签署。你输入的是“{_shown(typed_phrase)}”，应当是这四个字：{RISK_PHRASE}。"
            "请重新运行同一条命令。"
        )
    # A pseudo terminal and a cleared environment pass the checks above; the user's PIN (gap 9) does not.
    proof = require_approval_pin(
        ctx.find_root().obj.control_root, summary=f"签署接受风险：Run {run_id} → {claimant_id}", purpose="sign-risk", subject=f"{run_id}:{claimant_id}"
    )
    try:
        signature = service.sign_risk(
            run_id=run_id,
            claimant_id=claimant_id,
            signer=proof.approver if proof is not None else getpass.getuser(),
            environ=os.environ,
            stdin_is_tty=_stdin_is_tty(),
            stdout_is_tty=_stdout_is_tty(),
        )
    except LeaseHandoverError as error:
        raise click.ClickException(str(error)) from error
    _echo({"schema_version": "reclaim-risk-signature.v1", "run_id": run_id, "claimant_id": claimant_id, "signature_id": signature})
