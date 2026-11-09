"""``pm triage``: the triage desk's read-only view (TD-SW008-066, full version).

One command answers "what is open, what waits for the user, and what should be taken next".  It reads the cards
(``pm missions``) and the inbox (``pm inbox list``) and writes nothing: no confirmation, no plan, no focus change.
"""

from __future__ import annotations

import click

from auto_pm.app_context import AppContext
from auto_pm.application.core.pm_triage_service import PmTriageError, PmTriageService
from auto_pm.contracts.triage import (
    CONFIRMED_STALE_DAYS,
    DISPOSITION_LABEL,
    KIND_LABEL,
    PROPOSED_STALE_DAYS,
    FocusCard,
    TriageEntry,
    TriageReport,
)

_COLUMN_LABEL = {"ACTIVE": "在干", "WAITING": "等你", "PARKED": "搁着"}


def _focus_line(card: FocusCard) -> str:
    extra = f"，已搁 {card.parked_days} 天{'（超期）' if card.stale else ''}" if card.column == "PARKED" else ""
    return f"  [{_COLUMN_LABEL[card.column]}] {card.mission_id} {card.title}（{card.state}{extra}）"


def _entry_lines(entry: TriageEntry, *, stale_days: int) -> list[str]:
    flag = f"  ⚠ 已等 {entry.waiting_days} 天（超过 {stale_days} 天）" if entry.stale else ""
    lines = [
        f"  {entry.rank}. {entry.item_id} [{KIND_LABEL[entry.kind]}] {entry.title}"
        f"（建议{DISPOSITION_LABEL[entry.disposition]}）{flag}",
        f"     理由: {entry.reason}",
        f"     下一步: {entry.next_step}{'【用户的决定】' if entry.needs_user else ''}",
    ]
    if entry.command:
        lines.append(f"     命令: {entry.command}")
    return lines


def render_text(report: TriageReport) -> str:
    """Render the report for a person; every line is plain words, commands are skeletons with <placeholders>."""

    lines = [f"分诊台 {report.project_id}（只读建议，不改变任何东西）"]
    lines.append("开着的卡:" if report.focus else "开着的卡: 无")
    lines.extend(_focus_line(card) for card in report.focus)
    if report.decide_now:
        lines.append(f"等你决定的条目（{len(report.decide_now)} 条）:")
        for entry in report.decide_now:
            lines.extend(_entry_lines(entry, stale_days=PROPOSED_STALE_DAYS))
    else:
        lines.append("等你决定的条目: 无")
    if report.ready_queue:
        lines.append(f"已确认、建议顺序（{len(report.ready_queue)} 条）:")
        for entry in report.ready_queue:
            lines.extend(_entry_lines(entry, stale_days=CONFIRMED_STALE_DAYS))
    else:
        lines.append("已确认待排的条目: 无")
    lines.extend(f"提示: {hint}" for hint in report.hints)
    lines.append(report.rule)
    return "\n".join(lines)


@click.command(name="triage")
@click.argument("project_id")
@click.option("--json", "as_json", is_flag=True, help="以 JSON 输出 pm-triage.v1")
@click.pass_context
def triage_pm(ctx: click.Context, project_id: str, as_json: bool) -> None:
    """只读：开着的卡 + 收件箱按建议顺序排好，每条写明下一步；不确认、不转计划、不切焦点。"""

    app_ctx: AppContext = ctx.find_root().obj
    try:
        report = PmTriageService(app_ctx.control_root).report(project_id)
    except PmTriageError as error:
        raise click.ClickException(str(error)) from error
    click.echo(report.model_dump_json(indent=2) if as_json else render_text(report))
