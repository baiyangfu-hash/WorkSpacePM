"""Release CLI (D-146, card 1): ``release status`` and ``release deploy <commit> --check-only``.  Read-only; the real deploy comes in a later card.

退出码：0 可以部署／状态已打印；1 用法错误或真部署尚未实现；2 预检没通过（有失败或没法核实的项）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import click

from auto_pm.app_context import AppContext
from auto_pm.application.core import release_deploy_check as check
from auto_pm.application.core.release_trial_service import ReleaseTrialError, ReleaseTrialService
from auto_pm.ui.cli.caller_path import CallerPath


def _root(ctx: click.Context) -> Path:
    app_ctx: AppContext = ctx.obj
    return Path(app_ctx.control_root or app_ctx.workspace_root or os.getcwd())


@click.group(name="release")
def release_group() -> None:
    """发版：状态与部署前预检（只读）。"""


@release_group.command(name="status")
@click.option("--json", "as_json", is_flag=True, help="机器可读输出")
@click.pass_context
def release_status(ctx: click.Context, as_json: bool) -> None:
    """配置的有效版本与上一版、已装发布、发布记录是否互相一致、最近一次部署回执。"""

    info = check.status(_root(ctx))
    if as_json:
        click.echo(json.dumps(info, ensure_ascii=False, indent=2))
        return
    for slot, pointer in info["pointers"].items():
        click.echo(f"{slot}: {pointer['release_id'] or '读不出'}（{pointer['updated_at'] or '无时间'}）")
    click.echo(f"已装发布 {len(info['installed_releases'])} 个；发布记录一致性：{info['consistency']['status']}")
    for failure in info["consistency"]["failures"][:5]:
        click.echo(f"  ✗ {failure}")
    click.echo(f"最近部署回执：{info['last_receipt'] or '没有'}")


@release_group.command(name="deploy")
@click.argument("commit")
@click.option("--check-only/--no-check-only", default=True, help="只做预检，什么都不写（现在只支持这个）")
@click.option("--gate-verdict", type=CallerPath(path_type=Path, dir_okay=False), help="这个提交的全量门禁判决 JSON")
@click.option("--audit-signoff", type=CallerPath(path_type=Path, dir_okay=False), help="独立审计的放行记录")
@click.option("--json", "as_json", is_flag=True, help="机器可读输出")
@click.pass_context
def release_deploy(
    ctx: click.Context, commit: str, check_only: bool, gate_verdict: Path | None, audit_signoff: Path | None, as_json: bool
) -> None:
    """部署前预检：这个提交现在能不能发布。真部署还没做（D-146 卡4），不带 --check-only 会被拒。"""

    if not check_only:
        raise click.ClickException("真部署还没实现（D-146 卡4）；现在只有 --check-only 预检")
    report = check.preflight(_root(ctx), commit, gate_verdict=gate_verdict, audit_signoff=audit_signoff)
    if as_json:
        click.echo(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        for line in report.render():
            click.echo(line)
    ctx.exit(0 if report.ok else 2)


@release_group.command(name="trial")
@click.option("--dest-parent", type=CallerPath(path_type=Path, file_okay=False), help="副本放在哪个目录下（默认系统临时目录；不能在工作区里面）")
@click.option("--json", "as_json", is_flag=True, help="机器可读输出")
@click.pass_context
def release_trial(ctx: click.Context, dest_parent: Path | None, as_json: bool) -> None:
    """把生效发布拷一份到工作区外的临时目录，用来复现问题；不动 releases/、不写账本，副本用完请自行删除（D-05）。"""

    try:
        copy = ReleaseTrialService(_root(ctx)).make_copy(dest_parent)
    except ReleaseTrialError as error:
        raise click.ClickException(str(error)) from error
    if as_json:
        click.echo(json.dumps(copy.to_dict(), ensure_ascii=False, indent=2))
        return
    click.echo(f"已拷出发布 {copy.release_id}（{copy.files} 个文件）到 {copy.destination}")
    click.echo(f"试用：{copy.run_hint}")
    click.echo("用完请自己删除这个目录；它不在工作区里，不会被提交。")
