"""PM 与执行技能之间的 handoff.v1 交接命令。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from auto_pm.app_context import AppContext
from auto_pm.core.ai_handoff_service import (
    AiHandoffService,
    HandoffError,
)


def _workspace(ctx: click.Context) -> Path:
    app_ctx: AppContext = ctx.find_root().obj
    return Path(app_ctx.workspace_root).resolve()


def _json_output(payload: Any) -> None:
    click.echo(json.dumps(payload, ensure_ascii=False, indent=2))


def _parse_specs(values: tuple[str, ...]) -> list[str]:
    result: list[str] = []
    for value in values:
        result.extend(item.strip() for item in value.split(",") if item.strip())
    return result


def _inside_workspace(root: Path, candidate: str | Path) -> Path:
    path = Path(candidate)
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise click.ClickException("文件路径必须位于工作空间内") from exc
    return resolved


def _load_result_file(root: Path, result_file: str) -> dict[str, Any]:
    path = _inside_workspace(root, result_file)
    if not path.is_file():
        raise click.ClickException(f"结果文件不存在: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        raise click.ClickException(f"结果文件不是有效 JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise click.ClickException("结果文件根节点必须是 JSON 对象")
    return payload


def _handle_error(error: HandoffError) -> None:
    raise click.ClickException(str(error)) from error


@click.group(name="handoff")
def handoff_group() -> None:
    """管理 PM 与 PLC/全栈执行技能之间的 handoff.v1 交接包。"""


@handoff_group.command(name="create")
@click.option("--pid", "project_id", required=True, help="项目编号")
@click.option(
    "--to",
    "executor_skill",
    required=True,
    type=click.Choice(sorted(AiHandoffService.ALLOWED_EXECUTOR_SKILLS)),
    help="目标执行技能",
)
@click.option("--summary", required=True, help="任务摘要")
@click.option("--goal", default="", help="任务目标")
@click.option(
    "--mode",
    type=click.Choice(["grooming", "execution"]),
    default="execution",
    show_default=True,
    help="grooming 只读预研，execution 执行交付",
)
@click.option("--specs", multiple=True, help="注入的规范编号，可重复或逗号分隔")
@click.option("--read-first", multiple=True, help="执行前必读文件，可重复")
@click.option("--request-id", default="", help="可选的幂等请求编号")
@click.option("--change-id", default="", help="绑定的变更单编号（如 CHG-PLC-2026-012）")
@click.option("--decision-id", default="", help="绑定的阶段 1 审批决策包编号（如 DEC-20260903-XXXX）")
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def create_handoff(
    ctx: click.Context,
    project_id: str,
    executor_skill: str,
    summary: str,
    goal: str,
    mode: str,
    specs: tuple[str, ...],
    read_first: tuple[str, ...],
    request_id: str,
    change_id: str,
    decision_id: str,
    as_json: bool,
) -> None:
    """创建交接请求，默认状态为 pending。"""
    service = AiHandoffService(_workspace(ctx))
    try:
        payload = service.create_request(
            project_id,
            executor_skill,
            summary,
            goal=goal,
            mode=mode,
            specs=_parse_specs(specs),
            read_first=list(read_first),
            request_id=request_id,
            change_id=change_id,
            decision_id=decision_id,
        )
    except HandoffError as error:
        _handle_error(error)
    if as_json:
        _json_output(payload)
    else:
        click.echo(f"已创建 handoff: {payload['request_id']}")
        click.echo(f"目标技能: {payload['executor_skill']} | 模式: {payload['mode']}")


@handoff_group.command(name="list")
@click.option("--pid", "project_id", default="", help="按项目编号过滤")
@click.option(
    "--status",
    type=click.Choice(["", *sorted(AiHandoffService.ALLOWED_STATUSES)]),
    default="",
    help="按生命周期状态过滤",
)
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def list_handoffs(
    ctx: click.Context,
    project_id: str,
    status: str,
    as_json: bool,
) -> None:
    """列出交接请求；不指定状态时显示全部有效记录。"""
    service = AiHandoffService(_workspace(ctx))
    try:
        payload = service.list_requests(project_id=project_id, status=status)
    except HandoffError as error:
        _handle_error(error)
    if as_json:
        _json_output(payload)
        return
    if not payload:
        click.echo("没有找到符合条件的 handoff")
        return
    for item in payload:
        click.echo(
            f"{item['request_id']} | {item['status']} | {item['project_id']} | "
            f"{item['executor_skill']} | {item['summary']}"
        )


@handoff_group.command(name="queue")
@click.option("--pid", "project_id", default="", help="按项目编号过滤")
@click.option(
    "--limit",
    type=click.IntRange(1, 50),
    default=10,
    show_default=True,
    help="最多显示最近请求数",
)
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def queue_handoffs(ctx: click.Context, project_id: str, limit: int, as_json: bool) -> None:
    """查看 handoff 工作队列快照；此命令只读，不改变交接状态。"""
    service = AiHandoffService(_workspace(ctx))
    try:
        payload = service.queue_snapshot(project_id=project_id, limit=limit)
    except HandoffError as error:
        _handle_error(error)
    if as_json:
        _json_output(payload)
        return

    scope = project_id or "全部项目"
    click.echo(f"handoff 工作队列快照（只读） | 项目: {scope}")
    click.echo(f"总请求数: {payload['total']}")
    counts = payload["status_counts"]
    click.echo("状态统计: " + " | ".join(f"{status}={counts[status]}" for status in AiHandoffService.STATUS_ORDER))
    lifecycle_counts = payload["lifecycle_state_counts"]
    click.echo(
        "执行态: " + " | ".join(f"{state}={count}" for state, count in lifecycle_counts.items())
    )
    failures = payload["failure_events"]
    click.echo(f"失败事件: {failures['total']}")
    latest = payload["latest"]
    if not latest:
        click.echo("最近请求: 无")
        return
    click.echo("最近请求:")
    for item in latest:
        click.echo(
            f"{item['request_id']} | {item['status']} | {item['project_id']} | "
            f"{item['executor_skill']} | {item['summary']}"
        )


@handoff_group.command(name="show")
@click.argument("request_id")
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def show_handoff(ctx: click.Context, request_id: str, as_json: bool) -> None:
    """查看一个 handoff 请求或已消费回执。"""
    service = AiHandoffService(_workspace(ctx))
    try:
        payload = service.get_request(request_id)
    except HandoffError as error:
        _handle_error(error)
    if payload is None:
        raise click.ClickException(f"找不到 handoff: {request_id}")
    if as_json:
        _json_output(payload)
    else:
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))


@handoff_group.command(name="claim")
@click.argument("request_id")
@click.option("--executor-id", required=True, help="领取任务的执行者唯一标识")
@click.option("--adapter", default="manual", show_default=True, help="执行器适配器名称")
@click.option(
    "--lease-seconds",
    type=click.IntRange(60, 86_400),
    default=AiHandoffService.DEFAULT_LEASE_SECONDS,
    show_default=True,
    help="执行租约有效期；到期后必须由 PM 重新派发",
)
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def claim_handoff(
    ctx: click.Context,
    request_id: str,
    executor_id: str,
    adapter: str,
    lease_seconds: int,
    as_json: bool,
) -> None:
    """领取一个待执行 handoff；manual 只表示可领取，不代表启动 IDE。"""
    service = AiHandoffService(_workspace(ctx))
    try:
        payload = service.claim_request(
            request_id,
            executor_id=executor_id,
            adapter=adapter,
            lease_seconds=lease_seconds,
        )
    except HandoffError as error:
        _handle_error(error)
    if as_json:
        _json_output(payload)
    else:
        click.echo(f"已领取 handoff: {request_id} | 租约持有者: {executor_id}")


@handoff_group.command(name="start")
@click.argument("request_id")
@click.option("--executor-id", required=True, help="租约持有者标识")
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def start_handoff(ctx: click.Context, request_id: str, executor_id: str, as_json: bool) -> None:
    """将已领取 handoff 标记为执行中。"""
    service = AiHandoffService(_workspace(ctx))
    try:
        payload = service.start_request(request_id, executor_id=executor_id)
    except HandoffError as error:
        _handle_error(error)
    if as_json:
        _json_output(payload)
    else:
        click.echo(f"已启动 handoff: {request_id}")


@handoff_group.command(name="heartbeat")
@click.argument("request_id")
@click.option("--executor-id", required=True, help="租约持有者标识")
@click.option(
    "--lease-seconds",
    type=click.IntRange(60, 86_400),
    default=AiHandoffService.DEFAULT_LEASE_SECONDS,
    show_default=True,
    help="续租时长",
)
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def heartbeat_handoff(
    ctx: click.Context,
    request_id: str,
    executor_id: str,
    lease_seconds: int,
    as_json: bool,
) -> None:
    """续租执行 handoff，防止工作队列将其判定为失联。"""
    service = AiHandoffService(_workspace(ctx))
    try:
        payload = service.heartbeat_request(
            request_id,
            executor_id=executor_id,
            lease_seconds=lease_seconds,
        )
    except HandoffError as error:
        _handle_error(error)
    if as_json:
        _json_output(payload)
    else:
        click.echo(f"心跳已更新: {request_id}")


@handoff_group.command(name="result-submit")
@click.argument("request_id")
@click.option("--executor-id", required=True, help="租约持有者标识")
@click.option("--result-file", required=True, help="执行技能写入的 handoff_result JSON 文件")
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def submit_handoff_result(
    ctx: click.Context,
    request_id: str,
    executor_id: str,
    result_file: str,
    as_json: bool,
) -> None:
    """提交执行回执；成功后仅 PM 可调用 close 消费结果。"""
    root = _workspace(ctx)
    service = AiHandoffService(root)
    try:
        payload = service.submit_result(
            request_id,
            executor_id=executor_id,
            result=_load_result_file(root, result_file),
        )
    except HandoffError as error:
        _handle_error(error)
    if as_json:
        _json_output(payload)
    else:
        click.echo(f"执行回执已提交: {request_id}")


@handoff_group.command(name="fail")
@click.argument("request_id")
@click.option("--executor-id", required=True, help="租约持有者标识")
@click.option("--reason", required=True, help="失败原因")
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def fail_handoff(
    ctx: click.Context,
    request_id: str,
    executor_id: str,
    reason: str,
    as_json: bool,
) -> None:
    """由租约持有者报告执行失败，保留请求供 PM 处理。"""
    service = AiHandoffService(_workspace(ctx))
    try:
        payload = service.fail_request(request_id, executor_id=executor_id, reason=reason)
    except HandoffError as error:
        _handle_error(error)
    if as_json:
        _json_output(payload)
    else:
        click.echo(f"执行失败已记录: {request_id}")


@handoff_group.command(name="timeout")
@click.option("--pid", "project_id", default="", help="按项目编号过滤")
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def timeout_handoffs(ctx: click.Context, project_id: str, as_json: bool) -> None:
    """将租约到期的 claimed/in_progress 请求显式标记为 expired。"""
    service = AiHandoffService(_workspace(ctx))
    try:
        payload = service.expire_stale_requests(project_id)
    except HandoffError as error:
        _handle_error(error)
    if as_json:
        _json_output(payload)
    else:
        click.echo(f"已标记超时请求: {len(payload)}")


@handoff_group.command(name="requeue")
@click.argument("request_id")
@click.option("--pm-id", required=True, help="执行重新派发的 PM 标识")
@click.option("--reason", required=True, help="重新派发原因")
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def requeue_handoff(
    ctx: click.Context,
    request_id: str,
    pm_id: str,
    reason: str,
    as_json: bool,
) -> None:
    """由 PM 显式将失联或失败请求重新置为待领取。"""
    service = AiHandoffService(_workspace(ctx))
    try:
        payload = service.requeue_request(request_id, pm_id=pm_id, reason=reason)
    except HandoffError as error:
        _handle_error(error)
    if as_json:
        _json_output(payload)
    else:
        click.echo(f"已由 PM 重新派发 handoff: {request_id}")


@handoff_group.command(name="preflight")
@click.argument("request_id")
@click.option("--result-file", default="", help="待消费的 handoff_result JSON 文件")
@click.option("--pid", "expected_project_id", default="", help="预期项目编号")
@click.option("--to", "expected_executor_skill", default="", help="预期执行技能")
@click.option("--idempotency-key", default="", help="关闭幂等键")
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def preflight_handoff(
    ctx: click.Context,
    request_id: str,
    result_file: str,
    expected_project_id: str,
    expected_executor_skill: str,
    idempotency_key: str,
    as_json: bool,
) -> None:
    """只做 PM 收口预检，不改变 handoff 或项目台账。"""
    root = _workspace(ctx)
    service = AiHandoffService(root)
    try:
        result = _load_result_file(root, result_file) if result_file else {}
        payload = service.preflight_close(
            request_id,
            result=result,
            idempotency_key=idempotency_key,
            expected_project_id=expected_project_id,
            expected_executor_skill=expected_executor_skill,
        )
    except HandoffError as error:
        _handle_error(error)
    if as_json:
        _json_output(payload)
    else:
        state = "已消费且可幂等重试" if payload["already_consumed"] else "可安全消费"
        click.echo(f"预检通过: {request_id} | {state}")


@handoff_group.command(name="failures")
@click.argument("request_id")
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def list_handoff_failures(ctx: click.Context, request_id: str, as_json: bool) -> None:
    """查看 handoff Saga 的失败与重试证据。"""
    service = AiHandoffService(_workspace(ctx))
    try:
        payload = service.list_failure_events(request_id)
    except HandoffError as error:
        _handle_error(error)
    if as_json:
        _json_output(payload)
    elif not payload:
        click.echo("没有失败事件")
    else:
        for event in payload:
            click.echo(
                f"{event.get('occurred_at', '')} | {event.get('phase', '')} | "
                f"{event.get('error_type', '')} | {event.get('error', '')}"
            )


@handoff_group.command(name="close")
@click.argument("request_id", required=False)
@click.option("--pid", "project_id", default="", help="兼容模式：按项目解析唯一 pending 请求")
@click.option("--result-file", default="", help="执行技能写入的 handoff_result JSON 文件")
@click.option("--summary", default="", help="回执摘要")
@click.option("--changed-file", multiple=True, help="变更文件，可重复")
@click.option("--risk", multiple=True, help="风险，可重复")
@click.option("--next-action", multiple=True, help="后续动作，可重复")
@click.option("--watchout", multiple=True, help="注意事项，可重复")
@click.option("--artifact", multiple=True, help="验证或交付物证据，可重复")
@click.option("--chg-update", multiple=True, help="变更单更新记录，可重复")
@click.option("--read-first", multiple=True, help="执行实际读取过的基线文件，可重复")
@click.option("--lint-result", default="", help="Lint/静态检查结果")
@click.option("--test-result", default="", help="测试结果")
@click.option("--other-check", multiple=True, help="其他门禁结果，可重复")
@click.option("--not-run", multiple=True, help="未运行项目，可重复")
@click.option("--idempotency-key", default="", help="关闭幂等键")
@click.option("--actor", default="pm-workflow", show_default=True, help="收口方")
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def close_handoff(
    ctx: click.Context,
    request_id: str | None,
    project_id: str,
    result_file: str,
    summary: str,
    changed_file: tuple[str, ...],
    risk: tuple[str, ...],
    next_action: tuple[str, ...],
    watchout: tuple[str, ...],
    artifact: tuple[str, ...],
    chg_update: tuple[str, ...],
    read_first: tuple[str, ...],
    lint_result: str,
    test_result: str,
    other_check: tuple[str, ...],
    not_run: tuple[str, ...],
    idempotency_key: str,
    actor: str,
    as_json: bool,
) -> None:
    """由 PM 消费一个交接包并原子写入 consumed 状态。"""
    root = _workspace(ctx)
    service = AiHandoffService(root)
    try:
        if not request_id:
            if not project_id:
                raise click.ClickException("必须提供 REQUEST_ID，或使用 --pid 兼容解析")
            pending = service.list_pending(project_id)
            if len(pending) != 1:
                raise click.ClickException(
                    f"--pid 只能解析唯一 pending handoff，当前找到 {len(pending)} 个"
                )
            request_id = str(pending[0]["request_id"])

        result: dict[str, Any] = {}
        if result_file:
            result.update(_load_result_file(root, result_file))
        if summary:
            result["summary"] = summary
        if changed_file:
            result["changed_files"] = list(changed_file)
        if risk:
            result["risks"] = list(risk)
        if next_action:
            result["next_actions"] = list(next_action)
        if watchout:
            result["watchouts"] = list(watchout)
        if artifact:
            result["artifacts"] = list(artifact)
        if chg_update:
            result["chg_updates"] = list(chg_update)
        if read_first:
            result["read_first"] = list(read_first)
        verification = dict(result.get("verification") or {})
        if lint_result:
            verification["lint_result"] = lint_result
        if test_result:
            verification["test_result"] = test_result
        if other_check:
            verification["other_checks"] = list(other_check)
        if not_run:
            verification["not_run"] = list(not_run)
        if verification:
            result["verification"] = verification

        payload = service.close_request(
            request_id,
            result=result,
            idempotency_key=idempotency_key,
            actor=actor,
        )
    except HandoffError as error:
        _handle_error(error)
    if as_json:
        _json_output(payload)
    else:
        click.echo(f"已消费 handoff: {payload['request_id']}")
        click.echo("PM 收口状态: consumed")


@handoff_group.group(name="saga")
def saga_group() -> None:
    """管理 PM 收口跨资产 Saga 事务与检查点日志。"""


@saga_group.command(name="status")
@click.argument("request_id")
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def saga_status(ctx: click.Context, request_id: str, as_json: bool) -> None:
    """查看 handoff PM 收口 Saga 事务状态与检查点。"""
    service = AiHandoffService(_workspace(ctx))
    payload = service.get_saga_status(request_id)
    if payload is None:
        raise click.ClickException(f"找不到 Saga 事务日志: {request_id}")
    if as_json:
        _json_output(payload)
    else:
        click.echo(f"Saga 编号: {payload.get('saga_id', '')}")
        click.echo(
            f"请求编号: {payload.get('request_id', '')} | 项目: {payload.get('project_id', '')}"
        )
        click.echo(
            f"当前状态: {payload.get('status', '')} | 当前步骤: {payload.get('current_step', '')}"
        )
        click.echo(
            f"已完成步骤: {', '.join(payload.get('completed_steps') or []) or '无'}"
        )
        if payload.get("error"):
            click.echo(f"错误信息: {payload['error']}")


@saga_group.command(name="resume")
@click.argument("request_id")
@click.option("--actor", default="pm-workflow", show_default=True, help="收口方")
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def saga_resume(ctx: click.Context, request_id: str, actor: str, as_json: bool) -> None:
    """从断点恢复并继续执行未完成的 Saga 步骤。"""
    service = AiHandoffService(_workspace(ctx))
    try:
        payload = service.resume_saga(request_id, actor=actor)
    except HandoffError as error:
        _handle_error(error)
    if as_json:
        _json_output(payload)
    else:
        click.echo(
            f"Saga 恢复完成: {payload.get('saga_id', '')} | 状态: {payload.get('status', '')}"
        )


@saga_group.command(name="compensate")
@click.argument("request_id")
@click.option("--actor", default="pm-workflow", show_default=True, help="补偿执行方")
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def saga_compensate(ctx: click.Context, request_id: str, actor: str, as_json: bool) -> None:
    """补偿回滚已失败或需撤销的 Saga 事务，恢复所有修改文件。"""
    service = AiHandoffService(_workspace(ctx))
    try:
        payload = service.compensate_saga(request_id, actor=actor)
    except HandoffError as error:
        _handle_error(error)
    if as_json:
        _json_output(payload)
    else:
        click.echo(
            f"Saga 补偿回滚完成: {payload.get('saga_id', '')} | 状态: {payload.get('status', '')}"
        )
