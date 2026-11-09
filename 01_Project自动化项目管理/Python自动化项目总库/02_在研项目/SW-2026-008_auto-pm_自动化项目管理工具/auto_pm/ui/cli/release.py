"""Release CLI (D-146, card 1): ``release status`` and ``release deploy <commit> --check-only``.  Read-only; the real deploy comes in a later card.

退出码：0 可以部署／状态已打印／部署完成；1 用法错误；2 预检没通过（有失败或没法核实的项）；
3 部署中途失败，指针已回退（账目保持打开，重试要新的用户确认引用）；4 部署失败且没能自动回退，或已切换但收口没完成（要人工，信息里有回退命令）。
真部署（``--no-check-only``）每次都要 ``--confirm-ref user-confirmation:<用户那条消息的时间或编号>``；没有它永远拒绝，没有默认同意。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import click

from auto_pm.app_context import AppContext
from auto_pm.application.core import release_deploy_check as check
from auto_pm.application.core import release_ops as ops
from auto_pm.application.core import release_wiring as wiring
from auto_pm.application.core.memory_gate_arming import arm_for_heavy_job
from auto_pm.application.core.release_deploy import DeployError
from auto_pm.application.core.release_ledger import LedgerError
from auto_pm.application.core.release_trial_service import ReleaseTrialError, ReleaseTrialService
from auto_pm.ui.cli.caller_path import CallerPath
from auto_pm.ui.cli.runtime_identity_guard import (
    require_runtime_identity_for_workspace,
    warn_runtime_identity,
)


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
@click.option("--check-only/--no-check-only", default=True, help="只做预检，什么都不写（默认）；真部署写 --no-check-only")
@click.option("--gate-verdict", type=CallerPath(path_type=Path, dir_okay=False), help="这个提交的全量门禁判决 JSON")
@click.option("--audit-signoff", type=CallerPath(path_type=Path, dir_okay=False), help="独立审计的放行记录")
@click.option("--confirm-ref", default="", help="真部署必填：user-confirmation:<用户那条消息的时间或编号>；没有它不批准、不部署")
@click.option("--approver", default="", help="真部署必填：写进变更单和 Decision 的批准人")
@click.option("--card-file", type=CallerPath(path_type=Path, dir_okay=False), help="真部署必填：切换后跑卡预检用的实施卡文件")
@click.option("--drill-script", type=CallerPath(path_type=Path, dir_okay=False), help="真部署必填：事件链演练脚本（本机文件）")
@click.option("--json", "as_json", is_flag=True, help="机器可读输出")
@click.pass_context
def release_deploy(
    ctx: click.Context, commit: str, check_only: bool, gate_verdict: Path | None, audit_signoff: Path | None,
    confirm_ref: str, approver: str, card_file: Path | None, drill_script: Path | None, as_json: bool,
) -> None:
    """部署前预检；加 --no-check-only 才真部署：预检全绿 → 建账 → 构建 → 切换 → 自检 → 失败自动回退，成功才收口并写回执。"""

    if not check_only:
        require_runtime_identity_for_workspace(ctx)  # a real deploy writes the ledger and the pointers: the runtime identity must be clean first
        missing = [flag for flag, value in (("--confirm-ref", confirm_ref), ("--approver", approver), ("--card-file", card_file), ("--drill-script", drill_script)) if not value]
        if missing:
            raise click.ClickException("真部署还缺：" + "、".join(missing))
        arm_for_heavy_job("deploy-gate")  # D-168: build, switch, self-checks and the pre-commit dry run are a heavy job the memory gate must not freeze; never raises
    report = check.preflight(_root(ctx), commit, gate_verdict=gate_verdict, audit_signoff=audit_signoff)
    if as_json and check_only:
        click.echo(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        for line in report.render():
            click.echo(line)
    if not report.ok:
        ctx.exit(2)
    if check_only:
        ctx.exit(0)
    assert card_file is not None and drill_script is not None  # narrowed by the missing-options check above
    try:
        result = wiring.real_deploy(_root(ctx), report, approver=approver, confirm_ref=confirm_ref, card_file=card_file, drill_script=drill_script)
    except LedgerError as error:  # a malformed confirmation reference stops before the books are touched
        raise click.ClickException(str(error)) from error
    except DeployError as error:
        click.echo(f"部署没有完成：{error}")
        ctx.exit(3 if error.rolled_back else 4)
    click.echo(f"已部署 {result.release_id}，变更单 {result.change_id} 已完成，回执 {result.receipt}")
    click.echo(f"回退命令：main.py release rollback {result.backup}")


@release_group.command(name="rollback")
@click.argument("backup_dir", type=CallerPath(path_type=Path, exists=True, file_okay=False))
@click.option("--json", "as_json", is_flag=True, help="机器可读输出")
@click.pass_context
def release_rollback(ctx: click.Context, backup_dir: Path, as_json: bool) -> None:
    """用切换前的指针备份把有效版本退回去：先核对备份校验和，只还原指针，不动数据库、不回滚已装发布。"""

    warn_runtime_identity(ctx, wiring.IDENTITY_PROJECT)  # the runtime may be exactly what is broken: warn, never refuse
    try:
        result = ops.rollback(_root(ctx), backup_dir, wiring.cockpit_identity)
    except ops.ReleaseOpsError as error:
        raise click.ClickException(str(error)) from error
    if as_json:
        click.echo(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        click.echo(f"已回退，有效版本 {result['active']}")


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
