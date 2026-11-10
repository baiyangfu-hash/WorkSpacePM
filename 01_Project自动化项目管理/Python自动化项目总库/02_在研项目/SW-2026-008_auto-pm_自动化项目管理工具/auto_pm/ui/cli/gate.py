"""Gate CLI (D-107a): the official multi-group regression gate.

``gate plan``   show the commands of the groups (read-only);
``gate run``    run the groups from a clean test environment, judge each one, write ``gate_summary.json``;
``gate judge``  recompute the verdict from the logs of an earlier run (read-only);
``gate precheck`` the quick pre-push self check: ruff, mypy (win32) and the tests that belong to the change (read-only).

Exit codes: 0 PASS; 1 the gate ran and did not pass (a failed group, a missing group, a dirty worktree); 2 it could not start.
Run it detached with ``main.py long-run start --name <n> --cwd <control root> --worktree <W> -- python -B main.py gate run ...``.
"""

from __future__ import annotations

import json
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
from auto_pm.application.core.memory_gate_arming import arm_for_heavy_job
from auto_pm.ui.cli.caller_path import CallerPath
from auto_pm.ui.cli.runtime_identity_guard import require_runtime_identity_for_workspace


def _only(value: str) -> tuple[str, ...]:
    return tuple(name.strip() for name in value.split(",") if name.strip())


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
def plan_command(worktree: Path, jobs: int, only: str) -> None:
    """只读：列出每组的命令和工作目录。"""
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
    arm_for_heavy_job("long-gate")  # D-168: the full regression (eleven pytest groups, hours) is the heavy job the memory gate protects; never raises
    service = GateRunService(announce=lambda note: click.echo(f"⚠ {note}", err=True))  # D-235: said when it happens, not after the round
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
def precheck_command(worktree: Path, base: str, jobs: int, out_dir: Path | None, as_json: bool) -> None:
    """只读：推送前一条命令跑 ruff + mypy(win32) + 与改动相关的 pytest；不写账本、不写工作树。"""
    arm_for_heavy_job("full-tests")  # D-168: mypy plus the related pytest is a heavy job; never raises
    try:
        report = PrecheckService().run(worktree, base=base, out_dir=out_dir, jobs=jobs)
    except GateRunError as error:
        click.echo(f"无法自检: {error}", err=True)
        raise SystemExit(2) from error
    if as_json:
        click.echo(json.dumps({**asdict(report), "verdict": report.verdict}, ensure_ascii=False, indent=2))
    else:
        _precheck_report(report)
    raise SystemExit(0 if report.verdict == "PASS" else 1)
