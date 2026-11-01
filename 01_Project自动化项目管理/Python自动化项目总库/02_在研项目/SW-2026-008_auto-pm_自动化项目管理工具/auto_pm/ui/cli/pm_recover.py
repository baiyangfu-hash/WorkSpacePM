"""``pm recover-status`` / ``pm recover``: read-only check of a started Run's executor process after the controller restarted (TD-SW008-074, step 1).

只读，不写账本、不拉起、不结束任何进程；进程已死后的结算是单独一步。进程号被别的进程复用时，以进程创建时刻识别，不当作仍在运行。
``recover-status`` 给机器读（JSON）；``recover`` 给人和 agent 读：先说现在是什么情况，再说下一步敲什么。
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from auto_pm.app_context import AppContext
from auto_pm.application.core.continuity_execution_service import (
    ContinuityExecutionError,
    ContinuityExecutionService,
)
from auto_pm.application.core.execution_recovery_status import (
    RecoveryStatus,
    RecoveryVerdict,
    inspect_started_process,
)


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


def plain_report(
    *,
    run_id: str,
    run_state: str,
    process_id: int,
    status: RecoveryStatus,
    recorded_started_at: str,
    observed_created_at: str | None,
) -> str:
    """The text a person (or another agent) reads: what is happening now, then exactly what to type next.

    Wording is fixed per verdict so a reader never has to guess; no branch here writes anything or touches a process.
    """

    verdict = status.verdict
    header = [
        f"Run: {run_id}（账上状态 {run_state}）",
        f"账本记的执行进程: 进程号 {process_id}，启动时刻 {recorded_started_at}",
        f"这台电脑现在看到的: {'进程创建时刻 ' + observed_created_at if observed_created_at else '没有读到这个进程的创建时刻'}",
        f"结论: {verdict.value}（{status.reason}）",
        "",
    ]
    if verdict is RecoveryVerdict.ALIVE:
        body = [
            "现在的情况: 执行进程还在运行，没有丢。账上 RUNNING 是对的。",
            "下一步: 什么都不用敲。等它自己结束；想中途停掉它，要问用户，驾驶舱不替你结束进程。",
        ]
    elif verdict is RecoveryVerdict.UNKNOWN:
        body = [
            "现在的情况: 这台电脑读不出进程的状态，不能说它死了，也不能说它活着。",
            "下一步: 什么都不要改。确认你就在跑执行代理的那台电脑上、用同一个用户重新敲一次；仍然 UNKNOWN 就把上面这几行原样报告用户。",
        ]
    else:
        body = [
            "现在的情况: 记录里的执行进程已经不在了（多半是主控或电脑重启时被带走），但账上这个 Run 还写着在运行，没有人在干活。",
            f"工位里可能留着它没做完的半成品，先别清理。{'进程号已被别的无关进程占用，驾驶舱不会去碰它。' if verdict is RecoveryVerdict.PID_REUSED else ''}",
            "下一步: 先停下，把上面这几行报告用户，不要自己开新 Run。把这个 Run 记为失败的命令（pm recover --apply）随下一个版本提供；在那之前不要用底层 continuity 命令硬改。",
        ]
    return "\n".join(header + body)


@click.command(name="recover")
@click.option("--operation-id", default="", help="派发时的操作编号（ExecutionIntent 的 operation_id）")
@click.option("--run-id", default="", help="不知道操作编号时，用 Run 编号（RUN-…，pm orient 会显示）")
@click.option("--json", "as_json", is_flag=True, help="输出 JSON，给脚本读")
@click.pass_context
def recover_pm(ctx: click.Context, operation_id: str, run_id: str, as_json: bool) -> None:
    """只读：主控重启后，核对执行进程还在不在，并用大白话写出现在的情况和下一步。

    操作编号和 Run 编号二选一。本命令不写账本、不结束任何进程。
    """

    if bool(operation_id) == bool(run_id):
        raise click.UsageError("--operation-id 和 --run-id 必须给一个，且只给一个")
    app_ctx: AppContext = ctx.find_root().obj
    service = ContinuityExecutionService(Path(app_ctx.workspace_root).resolve())
    try:
        if operation_id:
            receipt, run, evidence = service.resolve_started_run(operation_id)
            run_id = receipt.run_id
        else:
            run, evidence = service.resolve_started_run_by_run_id(run_id)
    except ContinuityExecutionError as error:
        raise click.ClickException(f"运行身份不可恢复，必须 BLOCKED/待恢复：{error}") from error
    status, created_at = inspect_started_process(evidence)
    recorded = evidence.started_at.isoformat()
    observed = created_at.isoformat() if created_at is not None else None
    if as_json:
        click.echo(
            json.dumps(
                {
                    "run_id": run_id,
                    "run_state": run.state.value,
                    "process_id": evidence.process_id,
                    "recorded_started_at": recorded,
                    "observed_created_at": observed,
                    "verdict": status.verdict.value,
                    "reason": status.reason,
                    "wrote_ledger": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    click.echo(
        plain_report(
            run_id=run_id,
            run_state=run.state.value,
            process_id=evidence.process_id,
            status=status,
            recorded_started_at=recorded,
            observed_created_at=observed,
        )
    )
