"""Gate CLI (D-107a): the official multi-group regression gate.

``gate plan``   show the commands of the groups (read-only);
``gate run``    run the groups from a clean test environment, judge each one, write ``gate_summary.json``;
``gate judge``  recompute the verdict from the logs of an earlier run (read-only);
``gate precheck`` the quick pre-push self check: ruff, mypy (win32) and the tests that belong to the change (read-only).

Exit codes: 0 PASS; 1 the gate ran and did not pass (a failed group, a missing group, a dirty worktree); 2 it could not start.
``gate start/status/stop/retry`` manage a durable full-gate task from the control root.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
from dataclasses import asdict
from pathlib import Path

import click

from auto_pm.application.core.gate_precheck_service import (
    DEFAULT_BASE,
    PrecheckReport,
    PrecheckService,
)
from auto_pm.application.core.gate_run_service import (
    SUMMARY_FILE,
    GateRunError,
    GateRunService,
    GateSummary,
    sha256_file,
)
from auto_pm.application.core.gate_task_service import (
    GateCandidate,
    GateTaskService,
    open_gate_task_service,
    preview_gate_candidate,
    task_record,
)
from auto_pm.application.core.memory_gate_arming import (
    MemoryPreflightRefusedError,
    require_for_heavy_job,
)
from auto_pm.ui.cli.caller_path import CallerPath
from auto_pm.ui.cli.runtime_identity_guard import require_runtime_identity_for_workspace


def _only(value: str) -> tuple[str, ...]:
    return tuple(name.strip() for name in value.split(",") if name.strip())


def _require_heavy(label: str) -> None:
    """Refuse to start a heavy local job when the memory gate says this machine has no headroom."""

    try:
        note = require_for_heavy_job(label)
    except MemoryPreflightRefusedError as error:
        click.echo(str(error), err=True)
        raise SystemExit(2) from error
    if note:
        click.echo(f"⚠ {note}", err=True)


def _fail(error: GateRunError) -> click.ClickException:
    return click.ClickException(str(error))


def _report(summary: GateSummary) -> None:
    for name, result in summary.results.items():
        line = f"{result.verdict:<5} {name:<20} exit={result.exit}"
        click.echo(line + (f"  {result.why}" if result.why else ""))
    for reason in summary.reasons:
        click.echo(f"  不是 PASS 的原因：{reason}")
    click.echo(
        f"总判定 {summary.verdict}（组齐全 {summary.complete}，工作树干净 {summary.git_dirty is False}，提交 {summary.commit[:12]}）"
    )


@click.group(name="gate")
def gate_group() -> None:
    """官方多组回归门禁：干净的测试环境、逐组判卷、汇总证据。"""


@gate_group.command(name="plan")
@click.option(
    "--worktree",
    required=True,
    type=CallerPath(file_okay=False, exists=True, path_type=Path),
    help="要判的工作树",
)
@click.option("--jobs", default=8, show_default=True, help="并行组的 xdist 进程数")
@click.option("--only", default="", help="只列这些组（逗号分隔）")
@click.option("--preview", is_flag=True, help="只读预览：工位、候选、基线、档次、理由、检查组、执行端和下一步")
@click.pass_context
def plan_command(ctx: click.Context, worktree: Path, jobs: int, only: str, preview: bool) -> None:
    """只读：列出每组的命令和工作目录；--preview 时给出候选门禁预览。"""
    if preview:
        try:
            root: Path | None
            try:
                root = Path(ctx.find_root().obj.control_root)
            except (AttributeError, TypeError):
                root = None
            click.echo(
                json.dumps(
                    preview_gate_candidate(worktree.resolve(), root=root).to_dict(),
                    ensure_ascii=False,
                    indent=2,
                )
            )
        except GateRunError as error:
            raise _fail(error) from error
        return
    try:
        click.echo(
            json.dumps(
                GateRunService().plan(worktree.resolve(), jobs=jobs, only=_only(only)),
                ensure_ascii=False,
                indent=2,
            )
        )
    except GateRunError as error:
        raise _fail(error) from error


@gate_group.command(name="run")
@click.option(
    "--worktree",
    required=True,
    type=CallerPath(file_okay=False, exists=True, path_type=Path),
    help="要判的工作树（必须已提交）",
)
@click.option(
    "--out",
    "out_dir",
    required=True,
    type=CallerPath(file_okay=False, path_type=Path),
    help="输出目录（日志与 gate_summary.json）",
)
@click.option("--jobs", default=8, show_default=True, help="并行组的 xdist 进程数")
@click.option("--only", default="", help="只跑这些组（逗号分隔）；少于全部组时总判定最多是 PARTIAL")
@click.option(
    "--timeout-minutes", default=180, show_default=True, help="每组的超时；并行组因可用内存不足被降低并发时，该组超时按降低的倍数放大并当场提示"
)
@click.option(
    "--require-full-jobs",
    is_flag=True,
    help="可用内存带不动 --jobs 时不降并发：该组不开跑、整轮停止，总判定不是 PASS，并写明需要多少、现在多少（要当切换依据的一轮用它）",
)
@click.option(
    "--candidate-release",
    default="",
    help="候选发布预检（D-157）：给待部署、已装好但还没切换的发布号，才允许用它自己的代码出门禁；"
    "发布必须在清单里、逐文件校验通过、实际加载的就是它、指针指的当前发布也完好，缺一就照常拒绝",
)
@click.pass_context
def run_command(
    ctx: click.Context, worktree: Path, out_dir: Path, jobs: int, only: str, timeout_minutes: int, require_full_jobs: bool,
    candidate_release: str,
) -> None:  # fmt: skip
    """依次跑各组；测试子进程只拿白名单环境变量，AUTO_PM_* 一律不传。"""
    require_runtime_identity_for_workspace(ctx, candidate_release)
    _require_heavy("long-gate")
    service = GateRunService()
    service.announce = lambda note: click.echo(f"⚠ {note}", err=True)  # D-235: said when it happens, not after the round (set after construction, so a stand-in service class needs no constructor arguments)
    try:
        summary = service.run(
            worktree, out_dir, jobs=jobs, only=_only(only), timeout_seconds=timeout_minutes * 60, require_full_jobs=require_full_jobs
        )
    except GateRunError as error:
        click.echo(f"无法开始: {error}", err=True)
        raise SystemExit(2) from error
    finally:
        for warning in service.preflight_warnings:
            click.echo(f"⚠ {warning}", err=True)
    _report(summary)
    click.echo(
        f"记录 SHA-256 {sha256_file(out_dir / SUMMARY_FILE)}（存进检查点，之后 gate judge --expect-sha256 核对）"
    )
    raise SystemExit(0 if summary.verdict == "PASS" else 1)


@gate_group.command(name="judge")
@click.argument("out_dir", type=CallerPath(file_okay=False, exists=True, path_type=Path))
@click.option("--json", "as_json", is_flag=True, help="输出机器可读 JSON")
@click.option(
    "--expect-sha256",
    default="",
    help="gate run 结束时打印的 gate_summary.json 的 SHA-256；不一致就不是 PASS",
)
@click.option(
    "--worktree",
    default=None,
    type=CallerPath(file_okay=False, exists=True, path_type=Path),
    help="再核对这个工作树现在是否仍是被判的那个提交且干净",
)
def judge_command(out_dir: Path, as_json: bool, expect_sha256: str, worktree: Path | None) -> None:
    """只读：按日志重新判一遍 OUT_DIR 里的那一轮（不重新生成任何文件）。"""
    try:
        summary = GateRunService().judge_dir(
            out_dir, expect_sha256=expect_sha256, worktree=worktree
        )
    except GateRunError as error:
        click.echo(f"无法判卷: {error}", err=True)
        raise SystemExit(2) from error
    if as_json:
        click.echo(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
    else:
        _report(summary)
    raise SystemExit(0 if summary.verdict == "PASS" else 1)


def _precheck_report(report: PrecheckReport) -> None:
    click.echo(f"对照 {report.base}：改动 {len(report.changed)} 个文件，相关测试 {len(report.related_tests)} 个")
    if report.scope_note:
        click.echo(f"  注意：{report.scope_note}")
    if report.outside_changes:
        shown = "、".join(report.outside_changes[:8]) + (" 等" if len(report.outside_changes) > 8 else "")
        click.echo(f"  工程目录之外的改动（预检没有对应的检查，结论最高只到 UNVERIFIED）：{shown}")
    for step in report.steps:
        click.echo(f"{step.verdict:<10} {step.name:<7}" + (f" exit={step.exit}" if step.exit is not None else "") + (f"  {step.why}" if step.why else ""))
        if step.verdict == "FAIL" and step.log:
            click.echo(f"           完整输出: {step.log}")
    click.echo(f"自检结论 {report.verdict}（这只是推送前的快检，部署前的全量门禁仍是 gate run）")


@gate_group.command(name="precheck")
@click.option(
    "--worktree",
    default=".",
    show_default=True,
    type=CallerPath(file_okay=False, exists=True, path_type=Path),
    help="要自检的工作树",
)
@click.option("--base", default=DEFAULT_BASE, show_default=True, help="对照哪个分支算“改了什么”")
@click.option("--jobs", default=4, show_default=True, help="相关测试多时的 xdist 进程数")
@click.option(
    "--out",
    "out_dir",
    default=None,
    type=CallerPath(file_okay=False, path_type=Path),
    help="各步输出放哪（默认放系统临时目录）",
)
@click.option("--json", "as_json", is_flag=True, help="输出机器可读 JSON")
@click.option("--defer-full", is_flag=True, help="遇到大范围选测时交给托管全量")
def precheck_command(worktree: Path, base: str, jobs: int, out_dir: Path | None, as_json: bool, defer_full: bool) -> None:
    """只读：推送前一条命令跑 ruff + mypy(win32) + 与改动相关的 pytest；不写账本、不写工作树。"""
    _require_heavy("full-tests")
    try:
        report = PrecheckService().run(worktree, base=base, out_dir=out_dir, jobs=jobs, defer_full=defer_full)
    except GateRunError as error:
        click.echo(f"无法自检: {error}", err=True)
        raise SystemExit(2) from error
    if as_json:
        click.echo(json.dumps({**asdict(report), "verdict": report.verdict}, ensure_ascii=False, indent=2))
    else:
        _precheck_report(report)
    raise SystemExit(0 if report.verdict == "PASS" else 1)


def _shared_gate(
    ctx: click.Context, worktree: Path | None = None, plugin: Path | None = None
) -> tuple[Path, GateTaskService]:
    root = Path(ctx.find_root().obj.control_root).resolve()
    return root, open_gate_task_service(root, worktree, plugin)


_TASK_ERRORS = (GateRunError, OSError, ValueError, sqlite3.Error, subprocess.SubprocessError)


def _task_json(record: dict[str, object]) -> None:
    click.echo(json.dumps(record, ensure_ascii=False, indent=2))


@gate_group.command(name="start")
@click.option("--worktree", required=True, type=CallerPath(exists=True, file_okay=False, path_type=Path))
@click.option("--full", is_flag=True, help="强制登记 L3 全量门禁（含全部 11 组与 Siemens LSP 插件）")
@click.pass_context
def start_command(ctx: click.Context, worktree: Path, full: bool) -> None:
    """登记托管门禁，优先由 GitHub Actions 执行（L2 按组提速，核心或 --full 走 L3 全量）。同一候选返回已有任务。"""
    require_runtime_identity_for_workspace(ctx)
    root, service = _shared_gate(ctx)
    try:
        _task_json(task_record(service.start(GateCandidate.from_worktree(root, worktree.resolve(), full=full))))
    except _TASK_ERRORS as error:
        raise click.ClickException(str(error)) from error


@gate_group.command(name="status")
@click.argument("task_id", required=False)
@click.option("--worktree", type=CallerPath(exists=True, file_okay=False, path_type=Path))
@click.option("--full", is_flag=True, help="按 L3 全量门禁候选查询")
@click.pass_context
def status_command(ctx: click.Context, task_id: str | None, worktree: Path | None, full: bool) -> None:
    """按任务号或当前候选查门禁，并与执行端对账。"""
    if (task_id is None) == (worktree is None):
        raise click.UsageError("请提供任务号或 --worktree")
    require_runtime_identity_for_workspace(ctx)
    root, service = _shared_gate(ctx)
    try:
        if worktree is not None:
            candidate = GateCandidate.from_worktree(root, worktree.resolve(), full=full)
            attempt = service.current(candidate)
            if attempt is None:
                raise GateRunError("当前候选尚未登记全量门禁" if candidate.tier == "L3" else "当前候选尚未登记托管门禁")
        else:
            assert task_id is not None
            attempt = service.status(task_id)
        _task_json(task_record(attempt))
    except _TASK_ERRORS as error:
        raise click.ClickException(str(error)) from error


@gate_group.command(name="stop")
@click.argument("task_id")
@click.pass_context
def stop_command(ctx: click.Context, task_id: str) -> None:
    """向已确认的执行端发送停止请求，最终状态以执行端对账为准。"""
    require_runtime_identity_for_workspace(ctx)
    _, service = _shared_gate(ctx)
    try:
        _task_json(task_record(service.stop(task_id)))
    except _TASK_ERRORS as error:
        raise click.ClickException(str(error)) from error


@gate_group.command(name="retry")
@click.argument("task_id")
@click.option("--worktree", required=True, type=CallerPath(exists=True, file_okay=False, path_type=Path))
@click.option("--full", is_flag=True, help="按 L3 全量门禁重试（切换本机执行时需带此项）")
@click.option("--local", is_flag=True, help="经用户确认，改用 Windows 计划任务")
@click.option("--approval-evidence-ref", default="", help="user-confirmation:<用户消息编号>")
@click.option("--siemens-lsp", type=CallerPath(exists=True, dir_okay=False, path_type=Path))
@click.pass_context
def retry_command(
    ctx: click.Context, task_id: str, worktree: Path, full: bool, local: bool, approval_evidence_ref: str,
    siemens_lsp: Path | None,
) -> None:
    """为已结束的同一候选登记新一次尝试。"""
    require_runtime_identity_for_workspace(ctx)
    worktree = worktree.resolve()
    root, service = _shared_gate(ctx, worktree, siemens_lsp.resolve() if siemens_lsp else None)
    try:
        candidate = GateCandidate.from_worktree(root, worktree, full=full)
        _task_json(task_record(service.retry(task_id, candidate, local=local, approval=approval_evidence_ref)))
    except _TASK_ERRORS as error:
        raise click.ClickException(str(error)) from error
