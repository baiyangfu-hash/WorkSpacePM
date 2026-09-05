"""PLC-HMI 概念映射：CLI 命令行入口（变更命令组（create/list/show/edit/delete））

像 PLC 的调试终端/工程师站，通过命令行直接操作功能块。
不经过 HMI 画面，直接调用 FB 或 SFB。

--- 原始注释 ---

change 子命令组 - 变更单 CRUD + 状态流转

Commands:
    list <PID>                          列出项目变更单
    show <CHG-NUM>                      查看变更单详情
    create --pid --domain ...           创建变更单
    transition <CHG-NUM> --to <STATUS>  状态流转
    edit <CHG-NUM> --background ...     编辑变更单字段
"""

from __future__ import annotations

import re
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from auto_pm.app_context import AppContext
from auto_pm.change.change_service import ChangeService
from auto_pm.change.constants import (
    ALL_STATUSES,
    BUSINESS_NATURES,
    DOMAINS,
    IMPACT_SCOPES,
    STATUS_LABELS,
    URGENCY_LEVELS,
)
from auto_pm.change.track_classifier import ChangeTrack, ChangeTrackClassifier
from auto_pm.models import ChangeRequest

console = Console()

# click.Choice 选项（从规范常量动态生成）
_DOMAIN_CHOICES = list(DOMAINS.keys())
_NATURE_CHOICES = list(BUSINESS_NATURES.keys())
_SCOPE_CHOICES = list(IMPACT_SCOPES.keys())
_URGENCY_CHOICES = list(URGENCY_LEVELS.keys())
_STATUS_CHOICES = sorted(ALL_STATUSES)


# ════════════════════════════════════════════════════════════
#  M3.5-6: Markdown 表格解析辅助函数（供 cmd_show 渲染 §6/§8/§9/§10）
# ════════════════════════════════════════════════════════════


def _parse_md_table(text: str) -> tuple[list[str], list[list[str]]]:
    """解析 Markdown 表格为表头+数据行

    Args:
        text: 包含 Markdown 表格的文本（可含非表格行）

    Returns:
        (header_cells, data_rows) — 表头单元格列表 + 数据行列表
        无表格时返回 ([], [])
    """
    header: list[str] = []
    rows: list[list[str]] = []
    seen_header = False

    for line in text.split("\n"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        # 跳过分隔行（|---|---|）
        if re.match(r"^\|[\s\-:|]+\|$", line):
            continue
        # 按 | 分割，去除首尾空单元格
        cells = [c.strip() for c in line.split("|")]
        if cells and cells[0] == "":
            cells = cells[1:]
        if cells and cells[-1] == "":
            cells = cells[:-1]
        if not cells:
            continue
        if not seen_header:
            header = cells
            seen_header = True
        else:
            rows.append(cells)

    return header, rows


def _extract_subsection(section_text: str, sub_num: str) -> str:
    """从章节文本中提取子章节（如 §8.1、§10.3）

    Args:
        section_text: 章节正文（如 cr.sections["8"]）
        sub_num: 子章节号（如 "8.1"）

    Returns:
        子章节文本（含标题行），未找到返回空字符串
    """
    pattern = re.compile(
        rf"###\s*{re.escape(sub_num)}\s*[.、：:]*(.*?)(?=\n###|\n##|\Z)",
        re.DOTALL,
    )
    match = pattern.search(section_text)
    return match.group(0) if match else ""


def _truncate(text: str, max_len: int = 60) -> str:
    """截断长文本，保留可读性"""
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


# ════════════════════════════════════════════════════════════
#  §6/§8/§9/§10 显示函数
# ════════════════════════════════════════════════════════════


def _display_section_6(cr: ChangeRequest) -> None:
    """显示 §6 变更影响分析"""
    section = cr.sections.get("6", "")
    if not section:
        return

    # 判断是否有实质内容
    has_constraint = bool(cr.constraint_impacts)
    has_domain = any(info.get("affected") for info in cr.domain_impacts.values())
    has_propagation = bool(cr.propagation_chain) or bool(cr.related_changes)
    has_risk = bool(cr.risk_level) or bool(cr.mitigation)
    if not (has_constraint or has_domain or has_propagation or has_risk):
        return

    console.print()
    console.print("[bold cyan]═══ §6 变更影响分析 ═══[/bold cyan]")

    # §6.1 项目约束影响
    if has_constraint:
        s61 = _extract_subsection(section, "6.1")
        if s61:
            header, rows = _parse_md_table(s61)
            if header and rows:
                table = Table(title="§6.1 项目约束影响（PMBOK五大约束）", show_lines=False)
                for h in header:
                    table.add_column(_truncate(h, 20), style="white", no_wrap=False)
                for row in rows:
                    # 补齐列数
                    while len(row) < len(header):
                        row.append("")
                    table.add_row(*[_truncate(c, 50) for c in row[: len(header)]])
                console.print(table)

    # §6.1 风险评估（独立于约束表，CLI edit 可单独设置）
    if has_risk:
        if cr.risk_level:
            risk_labels = {"none": "无", "low": "低", "medium": "中", "high": "高"}
            console.print(
                f"  [cyan]风险等级:[/cyan] {risk_labels.get(cr.risk_level, cr.risk_level)}"
            )
        if cr.mitigation:
            console.print(f"  [cyan]缓解措施:[/cyan] {_truncate(cr.mitigation, 100)}")

    # §6.2 技术领域影响
    if has_domain:
        s62 = _extract_subsection(section, "6.2")
        if s62:
            header, rows = _parse_md_table(s62)
            if header and rows:
                table = Table(title="§6.2 技术领域影响", show_lines=False)
                for h in header:
                    table.add_column(_truncate(h, 20), style="white", no_wrap=False)
                for row in rows:
                    while len(row) < len(header):
                        row.append("")
                    table.add_row(*[_truncate(c, 50) for c in row[: len(header)]])
                console.print(table)

    # §6.3 变更传播链
    if has_propagation:
        console.print()
        console.print("[bold]§6.3 变更传播链:[/bold]")
        if cr.propagation_chain:
            console.print(f"  [dim]{cr.propagation_chain}[/dim]")
        if cr.related_changes:
            console.print(f"  [cyan]关联变更单:[/cyan] {', '.join(cr.related_changes)}")


def _display_section_8(cr: ChangeRequest) -> None:
    """显示 §8 变更审批"""
    section = cr.sections.get("8", "")
    if not section:
        return

    # §8.1 审批流程
    s81 = _extract_subsection(section, "8.1")
    if s81:
        header, rows = _parse_md_table(s81)
        if header and rows:
            console.print()
            console.print("[bold cyan]═══ §8 变更审批 ═══[/bold cyan]")
            table = Table(title="§8.1 审批流程", show_lines=False)
            for h in header:
                table.add_column(_truncate(h, 15), style="white", no_wrap=False)
            for row in rows:
                while len(row) < len(header):
                    row.append("")
                table.add_row(*[_truncate(c, 50) for c in row[: len(header)]])
            console.print(table)

    # §8.2 审批结论
    s82 = _extract_subsection(section, "8.2")
    if s82:
        header, rows = _parse_md_table(s82)
        if rows:
            for row in rows:
                cells = [c for c in row if c]
                if cells:
                    console.print(f"  [cyan]审批结论:[/cyan] {_truncate(' | '.join(cells), 120)}")


def _display_section_9(cr: ChangeRequest) -> None:
    """显示 §9 变更实施记录"""
    section = cr.sections.get("9", "")
    if not section:
        return

    header, rows = _parse_md_table(section)
    if not header or not rows:
        return

    console.print()
    console.print("[bold cyan]═══ §9 变更实施记录 ═══[/bold cyan]")
    table = Table(title="实施记录", show_lines=False)
    for h in header:
        table.add_column(_truncate(h, 15), style="white", no_wrap=False)
    for row in rows:
        while len(row) < len(header):
            row.append("")
        table.add_row(*[_truncate(c, 50) for c in row[: len(header)]])
    console.print(table)


def _display_section_10(cr: ChangeRequest) -> None:
    """显示 §10 变更验证"""
    section = cr.sections.get("10", "")
    if not section:
        return

    has_verify = cr.has_section_10_verify
    has_conclusion = bool(cr.section_10_conclusion)
    if not (has_verify or has_conclusion):
        return

    console.print()
    console.print("[bold cyan]═══ §10 变更验证 ═══[/bold cyan]")

    # §10.1 验证项清单
    if has_verify:
        s101 = _extract_subsection(section, "10.1")
        if s101:
            header, rows = _parse_md_table(s101)
            if header and rows:
                table = Table(title="§10.1 验证项清单", show_lines=False)
                for h in header:
                    table.add_column(_truncate(h, 15), style="white", no_wrap=False)
                for row in rows:
                    while len(row) < len(header):
                        row.append("")
                    table.add_row(*[_truncate(c, 50) for c in row[: len(header)]])
                console.print(table)

    # §10.2 跨领域联动验证
    s102 = _extract_subsection(section, "10.2")
    if s102:
        header, rows = _parse_md_table(s102)
        if header and rows:
            table = Table(title="§10.2 跨领域联动验证", show_lines=False)
            for h in header:
                table.add_column(_truncate(h, 20), style="white", no_wrap=False)
            for row in rows:
                while len(row) < len(header):
                    row.append("")
                table.add_row(*[_truncate(c, 50) for c in row[: len(header)]])
            console.print(table)

    # §10.3 验证结论
    if has_conclusion:
        s103 = _extract_subsection(section, "10.3")
        if s103:
            header, rows = _parse_md_table(s103)
            if rows:
                for row in rows:
                    cells = [c for c in row if c]
                    if cells:
                        console.print(
                            f"  [cyan]验证结论:[/cyan] {_truncate(' | '.join(cells), 120)}"
                        )
            else:
                console.print(f"  [cyan]验证结论:[/cyan] {cr.section_10_conclusion}")


@click.group(name="change")
@click.pass_context
def change_group(ctx: click.Context) -> None:
    """变更管理 - 变更单创建/查询/状态流转"""


@change_group.command(name="list")
@click.argument("project_id")
@click.option("--status", type=click.Choice(_STATUS_CHOICES), default=None, help="按状态筛选")
@click.option("--domain", type=click.Choice(_DOMAIN_CHOICES), default=None, help="按领域筛选")
@click.option(
    "--full",
    "full_mode",
    is_flag=True,
    default=False,
    help="完整模式：标题列自动换行不截断（适合详细查看）",
)
@click.pass_context
def cmd_list(
    ctx: click.Context,
    project_id: str,
    status: str | None,
    domain: str | None,
    full_mode: bool,
) -> None:
    """列出项目变更单

    默认紧凑模式：关键短列（编号/领域/性质/范围/状态/申请人/日期）不换行，
    标题列单行省略号截断。--full 模式下标题列自动换行完整显示。
    """
    app_ctx: AppContext = ctx.obj
    svc = ChangeService(app_ctx.workspace_root)
    summaries = svc.list_change_requests(project_id, status=status, domain=domain)

    if not summaries:
        console.print("[yellow]未发现变更单[/yellow]")
        return

    table = Table(title=f"变更单列表 ({len(summaries)} 条) - 项目 {project_id}", expand=False)
    # 关键短列：min_width 保证不被压缩，no_wrap 保证不换行
    table.add_column("变更编号", style="cyan", no_wrap=True, min_width=19)
    table.add_column("领域", style="green", no_wrap=True, min_width=6)
    table.add_column("性质", style="blue", no_wrap=True, min_width=6)
    table.add_column("影响范围", style="magenta", no_wrap=True, min_width=13)
    table.add_column("状态", style="yellow", no_wrap=True, min_width=6)
    table.add_column("申请人", style="white", no_wrap=True, min_width=6)
    table.add_column("申请日期", style="dim", no_wrap=True, min_width=10)
    # 标题列：ratio=1 吸收剩余空间；默认单行省略号截断，--full 自动换行
    table.add_column(
        "标题",
        style="white",
        no_wrap=not full_mode,
        overflow="fold" if full_mode else "ellipsis",
        ratio=1,
    )

    for s in summaries:
        table.add_row(
            s.change_number,
            s.domain,
            s.business_nature,
            ",".join(s.impact_scope),
            STATUS_LABELS.get(s.status, s.status),
            s.applicant,
            s.apply_date,
            s.title,
        )

    console.print(table)


@change_group.command(name="show")
@click.argument("change_number")
@click.option("--pid", default=None, help="项目编号（跨项目单号冲突时必填，TD-A04 修复）")
@click.pass_context
def cmd_show(ctx: click.Context, change_number: str, pid: str | None) -> None:
    """查看变更单详情"""
    app_ctx: AppContext = ctx.obj
    svc = ChangeService(app_ctx.workspace_root)
    cr = svc.get_change_request(change_number, project_id=pid)

    if cr is None:
        console.print(f"[red]错误: 变更单不存在: {change_number}[/red]")
        ctx.exit(1)

    console.print(f"[cyan]变更编号:[/cyan] {cr.change_number}")
    console.print(f"[cyan]项目编号:[/cyan] {cr.project_id}")
    console.print(f"[cyan]项目名称:[/cyan] {cr.project_name}")
    console.print(f"[cyan]技术领域:[/cyan] {cr.domain} ({DOMAINS.get(cr.domain, '?')})")
    console.print(
        f"[cyan]业务性质:[/cyan] {cr.business_nature} ({BUSINESS_NATURES.get(cr.business_nature, '?')})"
    )
    console.print(f"[cyan]影响范围:[/cyan] {','.join(cr.impact_scope)}")
    console.print(f"[cyan]紧急程度:[/cyan] {cr.urgency} ({URGENCY_LEVELS.get(cr.urgency, '?')})")
    console.print(f"[cyan]当前状态:[/cyan] {STATUS_LABELS.get(cr.status, cr.status)}")
    console.print(f"[cyan]申请人:[/cyan]   {cr.applicant}")
    console.print(f"[cyan]申请日期:[/cyan] {cr.apply_date}")
    console.print(f"[cyan]预计实施:[/cyan] {cr.planned_date}")
    console.print()
    console.print("[cyan]变更背景:[/cyan]")
    console.print(cr.background)
    console.print()
    console.print("[cyan]变更必要性:[/cyan]")
    console.print(cr.necessity)
    if cr.references and cr.references != "待补充":
        console.print()
        console.print("[cyan]参考依据:[/cyan]")
        console.print(cr.references)

    # M3.5-6: 渲染 §6/§8/§9/§10 章节内容（仅当存在实质内容时显示）
    _display_section_6(cr)
    _display_section_8(cr)
    _display_section_9(cr)
    _display_section_10(cr)

    if cr.file_path:
        console.print()
        console.print(f"[dim]文件路径: {cr.file_path}[/dim]")


@change_group.command(name="create")
@click.option("--pid", "project_id", required=True, help="项目编号")
@click.option("--domain", type=click.Choice(_DOMAIN_CHOICES), required=True, help="技术领域")
@click.option(
    "--nature",
    "business_nature",
    type=click.Choice(_NATURE_CHOICES),
    required=True,
    help="业务性质",
)
@click.option(
    "--scope",
    "impact_scope",
    multiple=True,
    type=click.Choice(_SCOPE_CHOICES),
    required=True,
    help="影响范围（可多次指定）",
)
@click.option("--applicant", required=True, help="变更申请人")
@click.option("--background", required=True, help="变更背景")
@click.option("--necessity", required=True, help="变更必要性")
@click.option("--references", "references", default="", help="参考依据")
@click.option("--planned-date", default=None, help="预计实施日期（YYYY-MM-DD，默认今天）")
@click.option("--urgency", type=click.Choice(_URGENCY_CHOICES), default="normal", help="紧急程度")
@click.option(
    "--retrofit",
    "retrofit",
    is_flag=True,
    default=False,
    help="CHG-108 缺陷3: 先实施后补模式——直接创建 closed 状态变更单（跳过状态流转）",
)
@click.pass_context
def cmd_create(
    ctx: click.Context,
    project_id: str,
    domain: str,
    business_nature: str,
    impact_scope: tuple[str, ...],
    applicant: str,
    background: str,
    necessity: str,
    references: str,
    planned_date: str | None,
    urgency: str,
    retrofit: bool,
) -> None:
    """创建变更单（生成 CHG-*.md 文件并更新台帐）"""
    app_ctx: AppContext = ctx.obj
    svc = ChangeService(app_ctx.workspace_root)

    try:
        cr = svc.create_change_request(
            project_id=project_id,
            domain=domain,
            business_nature=business_nature,
            impact_scope=list(impact_scope),
            applicant=applicant,
            background=background,
            necessity=necessity,
            references=references,
            planned_date=planned_date,
            urgency=urgency,
            retrofit=retrofit,
        )
        track = ChangeTrackClassifier.classify(
            domain=domain,
            nature=business_nature,
            scope=impact_scope,
        )
        console.print(f"[green]变更单创建成功: {cr.change_number}[/green]")
        if track == ChangeTrack.QUICK:
            console.print(
                "  [cyan]通道: Quick Track (轻量通道) ⚡ - 局部改动，推荐简化审批/先实施后补[/cyan]"
            )
        else:
            console.print(
                "  [blue]通道: Full Track (完整通道) 🛡️ - 架构/全局改动，需走完整 12 态门禁流转[/blue]"
            )
        if retrofit:
            console.print("  [yellow]模式: retrofit（先实施后补，直接 closed）[/yellow]")
        console.print(f"  领域: {domain} ({DOMAINS[domain]})")
        console.print(f"  性质: {business_nature} ({BUSINESS_NATURES[business_nature]})")
        console.print(f"  范围: {','.join(impact_scope)}")
        console.print(f"  状态: {STATUS_LABELS.get(cr.status, cr.status)}")
        if cr.file_path:
            console.print(f"  文件: {cr.file_path}")
    except ValueError as e:
        console.print(f"[red]创建失败: {e}[/red]")
        ctx.exit(1)
    except Exception as e:
        console.print(f"[red]创建异常: {e}[/red]")
        ctx.exit(1)


@change_group.command(name="verify")
@click.argument("project_id")
@click.option(
    "--ledger-check",
    "ledger_check",
    is_flag=True,
    default=False,
    help="CHG-108 缺陷3: 对账门禁——校验变更单文件 vs 台账记录一致性，差异时报错退出",
)
@click.pass_context
def cmd_verify(
    ctx: click.Context,
    project_id: str,
    ledger_check: bool,
) -> None:
    """变更单验证（CHG-108 缺陷 3：对账门禁）

    \b
    --ledger-check: 对账门禁，检测台账与 CHG 文件的一致性
      退出码 0 = 对账无差异（门禁通过）
      退出码 1 = 项目不存在
      退出码 2 = 有差异（门禁失败，需用 ledger reconcile --fix 修复）
    """
    if not ledger_check:
        console.print("[yellow]请指定验证项，目前支持: --ledger-check[/yellow]")
        ctx.exit(1)

    from auto_pm.change.ledger_reconciler import LedgerReconciler
    from auto_pm.core.project_service import ProjectService

    app_ctx: AppContext = ctx.obj
    svc = ProjectService(app_ctx.workspace_root)
    project_path = svc.find_project_path(project_id)
    if project_path is None:
        console.print(f"[red]错误: 项目不存在: {project_id}[/red]")
        ctx.exit(1)

    reconciler = LedgerReconciler()
    diff = reconciler.reconcile(project_path)

    console.print()
    console.print(f"[bold cyan]═══ 变更单对账门禁: {project_id} ═══[/bold cyan]")
    console.print(f"  [cyan]结果:[/cyan] {diff.summary()}")

    if diff.is_clean:
        console.print("[green]✅ 门禁通过: 台账与变更单文件一致[/green]")
        ctx.exit(0)
    else:
        console.print("[red]❌ 门禁失败: 检测到差异[/red]")
        if diff.missing_in_ledger:
            console.print(
                f"  [red]台账缺失 {len(diff.missing_in_ledger)} 条: {', '.join(diff.missing_in_ledger)}[/red]"
            )
        if diff.orphan_in_ledger:
            console.print(
                f"  [yellow]台账孤儿 {len(diff.orphan_in_ledger)} 条: {', '.join(diff.orphan_in_ledger)}[/yellow]"
            )
        if diff.status_mismatches:
            console.print(f"  [red]状态不一致 {len(diff.status_mismatches)} 条[/red]")
        console.print(
            "[dim]提示: 运行 `auto-pm ledger reconcile <PID> --fix` 自动修复缺失行和状态不一致[/dim]"
        )
        ctx.exit(2)


@change_group.command(name="transition")
@click.argument("change_number")
@click.option(
    "--to", "new_status", type=click.Choice(_STATUS_CHOICES), required=True, help="目标状态"
)
@click.option("--approver", default="", help="审批人/实施人")
@click.option("--comment", default="", help="审批意见/返工原因")
@click.option(
    "--verification-conclusion", default="全部通过", help="验证结论（completed 状态必填）"
)
@click.option(
    "--allow-partial-verification",
    is_flag=True,
    default=False,
    help="允许部分验证闭环（CHG-085：§10.1 存在未通过项时，标注待验证项后允许流转到 completed）",
)
@click.option("--pid", default=None, help="项目编号（跨项目单号冲突时必填，TD-A04 修复）")
@click.pass_context
def cmd_transition(
    ctx: click.Context,
    change_number: str,
    new_status: str,
    approver: str,
    comment: str,
    verification_conclusion: str,
    allow_partial_verification: bool,
    pid: str | None,
) -> None:
    """状态流转（更新变更单章节并持久化状态）"""
    app_ctx: AppContext = ctx.obj
    svc = ChangeService(app_ctx.workspace_root)

    try:
        cr = svc.transition_status(
            change_number=change_number,
            new_status=new_status,
            approver=approver,
            comment=comment,
            verification_conclusion=verification_conclusion,
            allow_partial_verification=allow_partial_verification,
            project_id=pid,
        )
        if cr is None:
            console.print(f"[red]错误: 变更单不存在: {change_number}[/red]")
            ctx.exit(1)
        # 审计日志：记录变更单状态流转（关键流程操作追溯）
        from auto_pm.logging.audit import audit_log

        audit_log(
            "change_transition",
            change_number=change_number,
            new_status=new_status,
            approver=approver or "",
        )
        console.print(f"[green]状态流转成功: {change_number}[/green]")
        console.print(f"  新状态: {STATUS_LABELS.get(cr.status, cr.status)}")
        if cr.file_path:
            console.print(f"  文件: {cr.file_path}")
    except ValueError as e:
        console.print(f"[red]流转失败: {e}[/red]")
        ctx.exit(1)
    except Exception as e:
        console.print(f"[red]流转异常: {e}[/red]")
        ctx.exit(1)


# M3.5-8: change edit 命令支持的风险等级选项
_RISK_LEVEL_CHOICES = ["none", "low", "medium", "high"]


@change_group.command(name="edit")
@click.argument("change_number")
@click.option("--background", default=None, help="§4 变更背景")
@click.option("--necessity", default=None, help="§4 变更必要性")
@click.option("--references", default=None, help="§4 参考依据")
@click.option("--planned-date", default=None, help="§3.4 预计实施日期（YYYY-MM-DD）")
@click.option("--urgency", type=click.Choice(_URGENCY_CHOICES), default=None, help="§3.4 紧急程度")
@click.option(
    "--risk-level", type=click.Choice(_RISK_LEVEL_CHOICES), default=None, help="§6.1 风险等级"
)
@click.option("--mitigation", default=None, help="§6.1 缓解措施")
@click.option("--propagation-chain", default=None, help="§6.3 变更传播链")
@click.option("--pid", default=None, help="项目编号（跨项目单号冲突时必填，TD-A04 修复）")
@click.pass_context
def cmd_edit(
    ctx: click.Context,
    change_number: str,
    background: str | None,
    necessity: str | None,
    references: str | None,
    planned_date: str | None,
    urgency: str | None,
    risk_level: str | None,
    mitigation: str | None,
    propagation_chain: str | None,
    pid: str | None,
) -> None:
    """编辑变更单字段（支持 §4 基本字段 + §6 影响分析字符串字段）

    constraint_impacts/domain_impacts 两个 dict 字段因 CLI 输入繁琐，
    留给 GUI EditChangeDialog 编辑（见 spec.md M3.5-8 说明）。
    """
    app_ctx: AppContext = ctx.obj
    svc = ChangeService(app_ctx.workspace_root)

    # 收集实际要更新的字段（跳过 None）
    updates: dict[str, Any] = {}
    if background is not None:
        updates["background"] = background
    if necessity is not None:
        updates["necessity"] = necessity
    if references is not None:
        updates["references"] = references
    if planned_date is not None:
        updates["planned_date"] = planned_date
    if urgency is not None:
        updates["urgency"] = urgency
    if risk_level is not None:
        updates["risk_level"] = risk_level
    if mitigation is not None:
        updates["mitigation"] = mitigation
    if propagation_chain is not None:
        updates["propagation_chain"] = propagation_chain

    if not updates:
        console.print("[yellow]未指定要更新的字段，请使用 --background/--necessity 等选项[/yellow]")
        ctx.exit(1)

    try:
        cr = svc.update_change_request(change_number, lookup_project_id=pid, **updates)
        if cr is None:
            console.print(f"[red]错误: 变更单不存在: {change_number}[/red]")
            ctx.exit(1)
        console.print(f"[green]变更单已更新: {change_number}[/green]")
        console.print(f"  更新字段: {', '.join(updates.keys())}")
        if cr.file_path:
            console.print(f"  文件: {cr.file_path}")
    except click.exceptions.Exit:
        raise
    except ValueError as e:
        console.print(f"[red]更新失败: {e}[/red]")
        ctx.exit(1)
    except Exception as e:
        console.print(f"[red]更新异常: {e}[/red]")
        ctx.exit(1)
