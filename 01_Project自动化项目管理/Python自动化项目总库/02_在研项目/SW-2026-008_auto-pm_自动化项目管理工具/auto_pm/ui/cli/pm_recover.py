"""``pm recover-status``: read-only check of a started Run's executor process after the controller restarted (TD-SW008-074, step 1).

只读，不写账本、不拉起、不结束任何进程；进程已死后的结算是单独一步。进程号被别的进程复用时，以进程创建时刻识别，不当作仍在运行。
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
from auto_pm.application.core.execution_recovery_status import judge_started_process
from auto_pm.infrastructure import process_probe


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
    observation = process_probe.observe(evidence.process_id)
    created_at = process_probe.start_time_to_datetime(observation.start_time) if observation is not None else None
    status = judge_started_process(evidence, observation, created_at)
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
