"""稳定控制面驱动的驾驶舱候选隔离与外部复核命令。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from auto_pm.app_context import AppContext
from auto_pm.core.dogfood_runner import DogfoodIsolationError, DogfoodRunner


def _workspace(ctx: click.Context) -> Path:
    app_ctx: AppContext = ctx.find_root().obj
    return Path(app_ctx.workspace_root).resolve()


def _print_result(payload: Any, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if "passed" in payload:
        state = "PASS" if payload["passed"] else "FAIL"
        click.echo(f"Dogfood 外部复核: {state}")
        for name, passed in payload.get("checks", {}).items():
            click.echo(f"  {'PASS' if passed else 'FAIL'} | {name}")
    elif "candidate_path" in payload:
        click.echo("Dogfood 候选 worktree 已创建")
        click.echo(f"  路径: {payload['candidate_path']}")
        click.echo(f"  基线: {payload['base_sha'] or '未检测到 Git'}")
        click.echo(f"  独立环境: {'已创建' if payload['environment_ready'] else '未创建'}")
    else:
        click.echo("Dogfood 隔离快照已生成")
        click.echo(f"  稳定版本: {payload['stable']['git_sha'] or '未检测到 Git'}")
        click.echo(f"  候选版本: {payload['candidate']['git_sha'] or '未检测到 Git'}")
        click.echo(f"  白名单违规: {len(payload['allowlist_violations'])}")


@click.group(name="dogfood")
def dogfood_group() -> None:
    """驾驶舱 Dogfooding 隔离、指纹和稳定版外部复核。"""


@dogfood_group.command(name="prepare")
@click.option(
    "--candidate-path",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="新候选 worktree 路径（必须位于 .auto-pm/worktrees/）",
)
@click.option(
    "--stable-path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="稳定控制面路径，默认是工作空间根目录",
)
@click.option("--base-ref", default="HEAD", show_default=True, help="候选起始 Git ref")
@click.option("--with-venv", "create_environment", is_flag=True, help="创建候选独立 Python 环境")
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def prepare_dogfood(
    ctx: click.Context,
    candidate_path: Path,
    stable_path: Path | None,
    base_ref: str,
    create_environment: bool,
    as_json: bool,
) -> None:
    """从干净稳定树创建候选 worktree，不覆盖已有目录。"""
    try:
        payload = DogfoodRunner(_workspace(ctx)).prepare_candidate(
            candidate_path,
            stable_path=stable_path,
            base_ref=base_ref,
            create_environment=create_environment,
        )
    except DogfoodIsolationError as error:
        raise click.ClickException(str(error)) from error
    _print_result(payload, as_json)


@dogfood_group.command(name="inspect")
@click.option(
    "--candidate-path",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="候选 worktree 路径（必须位于 .auto-pm/worktrees/）",
)
@click.option(
    "--stable-path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="稳定控制面路径，默认是工作空间根目录",
)
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def inspect_dogfood(
    ctx: click.Context,
    candidate_path: Path,
    stable_path: Path | None,
    as_json: bool,
) -> None:
    """读取稳定/候选状态和路径白名单，不执行候选代码。"""
    try:
        payload = DogfoodRunner(_workspace(ctx)).inspect(
            candidate_path,
            stable_path=stable_path,
        )
    except DogfoodIsolationError as error:
        raise click.ClickException(str(error)) from error
    _print_result(payload, as_json)


@dogfood_group.command(name="review")
@click.option(
    "--candidate-path",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="候选 worktree 路径（必须位于 .auto-pm/worktrees/）",
)
@click.option(
    "--stable-path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="稳定控制面路径，默认是工作空间根目录",
)
@click.option("--baseline-fingerprint", default="", help="预期稳定代码域指纹")
@click.option("--write-report/--no-report", default=True, help="是否保存外部复核证据")
@click.option("--json-output", "as_json", is_flag=True, help="以 JSON 输出")
@click.pass_context
def review_dogfood(
    ctx: click.Context,
    candidate_path: Path,
    stable_path: Path | None,
    baseline_fingerprint: str,
    write_report: bool,
    as_json: bool,
) -> None:
    """从稳定控制面外部复核候选，候选不能生成自己的放行结论。"""
    try:
        payload = DogfoodRunner(_workspace(ctx)).review(
            candidate_path,
            stable_path=stable_path,
            baseline_stable_fingerprint=baseline_fingerprint,
            write_report=write_report,
        )
    except DogfoodIsolationError as error:
        raise click.ClickException(str(error)) from error
    _print_result(payload, as_json)
    if not payload["passed"]:
        ctx.exit(2)
