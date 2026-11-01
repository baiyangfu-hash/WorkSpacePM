"""``pm recover-status`` / ``pm recover``: check a started Run's executor process after the controller restarted (TD-SW008-074).

``recover-status`` 只读，给机器读（JSON）。``recover`` 给人和 agent 读：先说现在是什么情况，再说下一步敲什么。
``recover`` 不带 ``--apply`` 只读；带 ``--apply`` 且结论是 DEAD / PID_REUSED 时才把 Run 记为失败（EXECUTOR_LOST），
进程活着或判不出一律拒绝，永远不结束任何进程。进程号被别的进程复用时，以进程创建时刻识别，不当作仍在运行。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click

from auto_pm.app_context import AppContext
from auto_pm.application.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
    StartedRunLookupError,
)
from auto_pm.application.core.execution_recovery_status import (
    RecoveryStatus,
    RecoveryVerdict,
    inspect_started_process,
)
from auto_pm.contracts.continuity import RunState
from auto_pm.contracts.execution_adapter import (
    ExecutionActivityStage,
    ExecutionFailure,
    ExecutionFailureCode,
)
from auto_pm.infrastructure import lease_wallet
from auto_pm.ui.cli.continuity import _secret_from_environment
from auto_pm.ui.cli.runtime_identity_guard import project_of_run, require_runtime_identity


@click.command(name="recover-status")
@click.option("--operation-id", required=True, help="派发时的操作编号（ExecutionIntent 的 operation_id）")
@click.pass_context
def recover_status_pm(ctx: click.Context, operation_id: str) -> None:
    """只读：对账已启动的执行进程，输出 ALIVE / DEAD / PID_REUSED / UNKNOWN。"""

    app_ctx: AppContext = ctx.find_root().obj
    service = ContinuityExecutionService(Path(app_ctx.workspace_root).resolve())
    try:
        receipt, run, evidence = service.resolve_started_run(operation_id)
    except ContinuityExecutionError as error:
        raise click.ClickException(f"运行身份不可恢复，必须 BLOCKED/待恢复：{error}") from error
    status, created_at = inspect_started_process(evidence)
    click.echo(
        json.dumps(
            {
                "operation_id": operation_id,
                "run_id": receipt.run_id,
                "run_state": run.state.value,
                "process_id": evidence.process_id,
                "session_id": evidence.session_id,
                "recorded_started_at": evidence.started_at.isoformat(),
                "observed_created_at": created_at.isoformat() if created_at is not None else None,
                "verdict": status.verdict.value,
                "reason": status.reason,
                "note": "只读结论，未写账本；证据不含主机标识，默认执行进程与本命令在同一台电脑",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


MST = timezone(timedelta(hours=-7), "MST")


def mst_text(moment: datetime) -> str:
    """A moment as the user reads it (MST, UTC-7); the judgement itself still compares timezone-aware UTC values."""

    return moment.astimezone(MST).strftime("%Y-%m-%d %H:%M:%S MST")


def plain_refusal(error: ContinuityExecutionError, *, run_id: str, operation_id: str) -> str:
    """Say in plain words why there is nothing to check, and what to type next; the technical text stays at the end for the record.

    The branch comes from the error's own ``kind`` (never from its message text), so rewording a message in the service cannot
    silently send a case to the last branch.
    """

    lookup = error if isinstance(error, StartedRunLookupError) else None
    kind = lookup.kind if lookup is not None else ""
    if kind == StartedRunLookupError.NO_SUCH_OPERATION:
        head = f"账本里没有操作编号 {operation_id} 的派发记录。确认编号抄对了；不知道编号就改用 --run-id，Run 编号用 python main.py pm orient 看。"
    elif lookup is not None and kind == StartedRunLookupError.NOT_ACTIVE:
        shown = lookup.run_id or run_id or "这个 Run"
        which = f"操作编号 {operation_id} 对应的 {shown}" if operation_id else shown
        head = (
            f"{which} 现在是 {lookup.run_state}，已经不在运行（可能早就结束了），没有正在跑的执行进程可核对，不用对账。"
            "想看当前是哪个 Run、该做什么，敲 python main.py pm orient。"
        )
    elif kind == StartedRunLookupError.NO_SUCH_RUN:
        head = f"账本里没有 {run_id or '这个'} Run。Run 编号用 python main.py pm orient 看。"
    else:
        head = (
            "账本里这个 Run 的启动记录对不上（缺失、重复或属于别的执行者），无法判断执行进程是谁的。"
            "这是账本层面的问题：不要自己改，把这句原样报告用户。"
        )
    return f"{head}\n（技术原因：{error}）"


def plain_report(
    *,
    run_id: str,
    run_state: str,
    process_id: int,
    status: RecoveryStatus,
    recorded_started_at: datetime,
    observed_created_at: datetime | None,
) -> str:
    """The text a person (or another agent) reads: what is happening now, then exactly what to type next.

    Wording is fixed per verdict so a reader never has to guess; no branch here writes anything or touches a process.
    """

    verdict = status.verdict
    header = [
        f"Run: {run_id}（账上状态 {run_state}）",
        f"账本记的执行进程: 进程号 {process_id}，启动时刻 {mst_text(recorded_started_at)}",
        f"这台电脑现在看到的: {'进程创建时刻 ' + mst_text(observed_created_at) if observed_created_at else '没有读到这个进程的创建时刻'}",
        f"结论: {verdict.value}（{status.reason}）",
        "",
    ]
    if verdict is RecoveryVerdict.ALIVE:
        body = [
            f"现在的情况: 执行进程还在运行，没有丢。账上写 {run_state} 是对的。",
            "下一步: 什么都不用敲。等它自己结束；想中途停掉它，要问用户，驾驶舱不替你结束进程。",
        ]
    elif verdict is RecoveryVerdict.UNKNOWN:
        body = [
            "现在的情况: 这台电脑读不出进程的状态，不能说它死了，也不能说它活着。",
            "下一步: 什么都不要改。确认你就在跑执行代理的那台电脑上、用同一个用户重新敲一次；仍然 UNKNOWN 就把上面这几行原样报告用户。",
        ]
    else:
        body = [
            f"现在的情况: 记录里的执行进程已经不在了（多半是主控或电脑重启时被带走），但账上这个 Run 还写着 {run_state}，没有人在干活。",
            "先确认你就在跑执行代理的那台电脑上：在别的电脑上敲，进程号不存在，也会得到这个结论，那是误判，不要照着办。",
            f"工位里可能留着它没做完的半成品，先别清理。{'进程号已被别的无关进程占用，驾驶舱不会去碰它。' if verdict is RecoveryVerdict.PID_REUSED else ''}",
            "下一步: 先别自己开新 Run。把这个 Run 在账上记为失败（只改账本，不动工位）要持有它的租约口令，敲："
            f"python main.py pm recover --run-id {run_id} --apply --lease-wallet",
            "记为失败之后，要开新 Run 接着干，需要用户批准。",
        ]
    return "\n".join(header + body)


@click.command(name="recover")
@click.option("--operation-id", default="", help="派发时的操作编号（ExecutionIntent 的 operation_id）")
@click.option("--run-id", default="", help="不知道操作编号时，用 Run 编号（RUN-…，pm orient 会显示）")
@click.option("--json", "as_json", is_flag=True, help="输出 JSON，给脚本读")
@click.option(
    "--apply",
    "apply_",
    is_flag=True,
    help="执行进程确认已不在（DEAD/PID_REUSED）时，把这个 Run 记为失败（EXECUTOR_LOST）；活着或判不出一律拒绝。要持有该 Run 的租约口令",
)
@click.option("--lease-wallet", "use_wallet", is_flag=True, help="--apply 用：从本机钱包读取本 Run 持有者的口令（推荐）")
@click.option("--lease-token-env", default=None, metavar="ENV_NAME", help="--apply 用：口令所在环境变量；读取后立即删除")
@click.pass_context
def recover_pm(
    ctx: click.Context,
    operation_id: str,
    run_id: str,
    as_json: bool,
    apply_: bool,
    use_wallet: bool,
    lease_token_env: str | None,
) -> None:
    """主控重启后，核对执行进程还在不在，并用大白话写出现在的情况和下一步。

    操作编号和 Run 编号二选一。不带 --apply 只读：不写账本、不结束任何进程。
    带 --apply：只有进程确认已不在才把 Run 记为失败，不清理工位、不开新 Run。
    """

    if bool(operation_id) == bool(run_id):
        raise click.UsageError("--operation-id 和 --run-id 必须给一个，且只给一个")
    if apply_ and use_wallet == (lease_token_env is not None):
        raise click.UsageError("--apply 必须且只能给出一个口令来源：--lease-wallet 或 --lease-token-env")
    if not apply_ and (use_wallet or lease_token_env is not None):
        raise click.UsageError("--lease-wallet / --lease-token-env 只用于 --apply；不带 --apply 本命令只读，不需要口令")
    app_ctx: AppContext = ctx.find_root().obj
    if apply_ and run_id:
        # a write: the runtime identity is checked before the ledger is touched at all
        require_runtime_identity(ctx, project_of_run(ctx, run_id))
    service = ContinuityExecutionService(Path(app_ctx.control_root).resolve())  # the ledger lives in the control root
    try:
        if operation_id:
            receipt, run, evidence = service.resolve_started_run(operation_id)
            run_id = receipt.run_id
        else:
            run, evidence = service.resolve_started_run_by_run_id(run_id)
    except ContinuityExecutionError as error:
        raise click.ClickException(plain_refusal(error, run_id=run_id, operation_id=operation_id)) from error
    if apply_ and operation_id:
        # the operation id had to be turned into a Run first (a read); the guard still runs before anything is written
        require_runtime_identity(ctx, project_of_run(ctx, run_id))
    status, created_at = inspect_started_process(evidence)
    wrote = False
    if apply_:
        _apply_executor_lost(
            ctx,
            service,
            run_id=run_id,
            run_state=run.state,
            process_id=evidence.process_id,
            recorded_started_at=evidence.started_at,
            status=status,
            use_wallet=use_wallet,
            lease_token_env=lease_token_env,
        )
        wrote = True
    if as_json:
        click.echo(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_state": RunState.FAILED.value if wrote else run.state.value,
                    "process_id": evidence.process_id,
                    "recorded_started_at": evidence.started_at.isoformat(),
                    "observed_created_at": created_at.isoformat() if created_at is not None else None,
                    "verdict": status.verdict.value,
                    "reason": status.reason,
                    "wrote_ledger": wrote,
                    "failure_code": ExecutionFailureCode.EXECUTOR_LOST.value if wrote else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    if wrote:
        seen = f"进程创建时刻 {mst_text(created_at)}" if created_at is not None else "已没有这个进程"
        click.echo(
            f"已把 {run_id} 在账上记为失败（失败原因 {ExecutionFailureCode.EXECUTOR_LOST.value}：执行进程已不在）。\n"
            f"依据: 账本记的进程号 {evidence.process_id}、启动时刻 {mst_text(evidence.started_at)}；这台电脑现在看到的: {seen}；结论 {status.verdict.value}。\n"
            "没有动工位里的任何文件，也没有开新 Run。\n"
            "下一步: 向用户报告并请用户批准开新 Run 接着干；新 Run 开工时把工位里留下的未提交改动用 --declared-dirty 声明。"
        )
        return
    click.echo(
        plain_report(
            run_id=run_id,
            run_state=run.state.value,
            process_id=evidence.process_id,
            status=status,
            recorded_started_at=evidence.started_at,
            observed_created_at=created_at,
        )
    )


def _apply_executor_lost(
    ctx: click.Context,
    service: ContinuityExecutionService,
    *,
    run_id: str,
    run_state: RunState,
    process_id: int,
    recorded_started_at: datetime,
    status: RecoveryStatus,
    use_wallet: bool,
    lease_token_env: str | None,
) -> None:
    """Settle one Run as EXECUTOR_LOST.  Every refusal below happens before anything is written."""

    if run_state is not RunState.RUNNING:
        raise click.ClickException(f"已拒绝落账：{run_id} 现在是 {run_state.value}，只有 RUNNING 的 Run 才能这样记为失败")
    if status.verdict not in {RecoveryVerdict.DEAD, RecoveryVerdict.PID_REUSED}:
        raise click.ClickException(
            f"已拒绝落账：结论是 {status.verdict.value}（{status.reason}）。执行进程没有确认已不在，账本一个字都没改。\n"
            f"先不带 --apply 敲 python main.py pm recover --run-id {run_id}，按它写的下一步办。"
        )
    try:
        lease = service.current_lease(run_id)
        if lease_token_env is not None:
            token = _secret_from_environment(lease_token_env)
        else:
            token = lease_wallet.load(Path(ctx.find_root().obj.control_root), run_id=run_id, owner_id=lease.owner_id)
    except lease_wallet.LeaseWalletError as error:
        raise click.ClickException(f"已拒绝落账：{error}；只有持有这个 Run 租约的人才能记它失败") from error
    except ContinuityExecutionError as error:
        raise click.ClickException(f"已拒绝落账：读不到这个 Run 的租约：{error}") from error
    # Same key for the same executor process, so a retry after a crash cannot write a second failure.
    key = f"executor-lost:{run_id}:{process_id}:{recorded_started_at.isoformat()}"
    try:
        service.transition_run(
            run_id,
            RunState.FAILED,
            lease.owner_id,
            token,
            key,
            failure=ExecutionFailure(stage=ExecutionActivityStage.FAILED, code=ExecutionFailureCode.EXECUTOR_LOST),
        )
    except ContinuityExecutionError as error:
        raise click.ClickException(
            f"已拒绝落账：{error}\n租约过期或口令对不上时，不要硬改：按 pm orient 给出的 RECLAIM_EXPIRED_RUN 走回收，或交给持有者/用户。"
        ) from error
