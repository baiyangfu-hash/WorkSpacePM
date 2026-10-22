"""按《项目周期规范》推里程碑计划日期（规范：``0100_PLC自动化/00_通用规范/项目周期规范.md``）。

工期数字只从规范文档里的表格读，不写死在代码里：用户改了规范里的数，推出来的日期跟着变。
计划日期是阶段完成日：需求 = 需求确认日；设计 = 需求 + 设计工期；编程 = 设计 + 衔接间隔 + 编程工期；
其后各阶段首尾相接。工期 =（主类型周数 + 附加项周数）× 规模系数，换成天数向上取整；衔接间隔不乘系数。

``fill_milestone_file`` 只填计划日期为空的行（状态“不适用”的行不填），已有日期一律不改。
"""

from __future__ import annotations

import datetime as _dt
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path

from auto_pm.plc import milestones as ms

SPEC_RELATIVE = Path("0100_PLC自动化") / "00_通用规范" / "项目周期规范.md"
MAIN_TYPES = ("纯电气", "机电协作")
ADDONS = ("上位机", "机器人")
_GAP_ROW = "设计确认 → 开始编程"
_VERSION = re.compile(r"^\s*version\s*:\s*[\"']?([^\"'\s]+)", re.M)


class CycleSpecError(ValueError):
    """The cycle spec document is missing or its tables cannot be read."""


@dataclass(frozen=True)
class CycleSpec:
    path: str
    version: str
    weeks: dict[str, dict[str, float]]  # stage -> column ("纯电气", "加机器人", ...) -> weeks
    scales: dict[str, float]
    gap_weeks: float


def _tables(lines: list[str]) -> list[tuple[list[str], list[list[str]]]]:
    tables = []
    index = 0
    while index < len(lines):
        if lines[index].lstrip().startswith("|") and index + 1 < len(lines) and ms._is_separator(lines[index + 1]):
            header = ms._cells(lines[index])
            rows = []
            index += 2
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                rows.append(ms._cells(lines[index]))
                index += 1
            tables.append((header, rows))
            continue
        index += 1
    return tables


def _number(text: str, where: str) -> float:
    try:
        return float(text)
    except ValueError:
        raise CycleSpecError(f"{where}：“{text}”不是数字") from None


def find_spec(start: str) -> str | None:
    """Walk up from ``start`` (a project or workspace directory) to the spec document."""

    current = Path(os.path.abspath(start))
    for folder in (current, *current.parents):
        candidate = folder / SPEC_RELATIVE
        if candidate.is_file():
            return str(candidate)
    return None


def read_spec(path: str) -> CycleSpec:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    match = _VERSION.search(text)
    weeks: dict[str, dict[str, float]] = {}
    scales: dict[str, float] = {}
    gap: float | None = None
    for header, rows in _tables(lines):
        if header[:1] == ["阶段"] and all(c in header for c in MAIN_TYPES):
            columns = [*MAIN_TYPES, *(f"加{a}" for a in ADDONS)]
            missing = [c for c in columns if c not in header]
            if missing:
                raise CycleSpecError(f"工期表缺列：{'、'.join(missing)}")
            for row in rows:
                stage = row[0]
                if stage in ms.STAGES:
                    weeks[stage] = {c: _number(row[header.index(c)], f"工期表 {stage}·{c}") for c in columns}
        elif header[:1] == ["规模"] and "系数" in header:
            for row in rows:
                scales[row[0]] = _number(row[header.index("系数")], f"规模表 {row[0]}")
        elif header[:1] == ["衔接"]:
            for row in rows:
                if row[0] == _GAP_ROW:
                    gap = _number(row[1], f"衔接表 {_GAP_ROW}")
    missing_stages = [s for s in ms.STAGES if s not in weeks]
    if missing_stages:
        raise CycleSpecError(f"{path}：工期表缺阶段 {'、'.join(missing_stages)}")
    if not scales:
        raise CycleSpecError(f"{path}：找不到规模表（表头“规模 | 判据 | 系数”）")
    if gap is None:
        raise CycleSpecError(f"{path}：衔接表里找不到“{_GAP_ROW}”")
    return CycleSpec(path, match.group(1) if match else "", weeks, scales, gap)


def _days(weeks: float) -> _dt.timedelta:
    return _dt.timedelta(days=math.ceil(round(weeks * 7, 6)))


def plan(spec: CycleSpec, start: _dt.date, main_type: str, addons: tuple[str, ...], scale: str) -> dict[str, _dt.date]:
    if main_type not in MAIN_TYPES:
        raise CycleSpecError(f"主类型只认 {'、'.join(MAIN_TYPES)}")
    unknown = [a for a in addons if a not in ADDONS]
    if unknown:
        raise CycleSpecError(f"附加项只认 {'、'.join(ADDONS)}，不认识：{'、'.join(unknown)}")
    if scale not in spec.scales:
        raise CycleSpecError(f"规模只认 {'、'.join(spec.scales)}")
    factor = spec.scales[scale]

    def duration(stage: str) -> _dt.timedelta:
        row = spec.weeks[stage]
        return _days((row[main_type] + sum(row[f"加{a}"] for a in addons)) * factor)

    dates: dict[str, _dt.date] = {}
    current = start + duration("需求")
    dates["需求"] = current
    for stage in ms.STAGES[1:]:
        if stage == "编程":
            current += _days(spec.gap_weeks)
        current += duration(stage)
        dates[stage] = current
    return dates


def describe(spec: CycleSpec, main_type: str, addons: tuple[str, ...], scale: str) -> str:
    kinds = "+".join([main_type, *addons])
    version = f" {spec.version} " if spec.version else ""
    return f"按项目周期规范{version}推算：{kinds}、{scale}"


@dataclass
class FillResult:
    filled: list[str]
    kept: list[str]


def fill_milestone_file(path: str, dates: dict[str, _dt.date], note: str, *, write: bool) -> FillResult:
    """Fill empty planned dates only; never touches a row that already has a date or is 不适用."""

    table = ms.read_milestones(path)
    lines = Path(path).read_text(encoding="utf-8").splitlines(keepends=True)
    result = FillResult([], [])
    header_line = next((r.line for r in table.rows), None)
    if header_line is None:
        raise CycleSpecError(f"{path}：读不出里程碑表格")
    header = ms._cells(lines[header_line - 3])  # rows start two lines below the header
    plan_col = header.index("计划日期")
    note_col = header.index("备注") if "备注" in header else None
    for row in table.rows:
        if row.stage not in dates:
            continue
        if row.planned not in ms._EMPTY or row.status == "不适用":
            result.kept.append(row.stage)
            continue
        raw = lines[row.line - 1]
        ending = raw[len(raw.rstrip("\r\n")):]
        cells = ms._cells(raw)
        while len(cells) < len(header):
            cells.append("")
        cells[plan_col] = dates[row.stage].isoformat()
        if note_col is not None:
            cells[note_col] = f"{cells[note_col]}（{note}）" if cells[note_col] else note
        lines[row.line - 1] = "| " + " | ".join(cells) + " |" + (ending or "\n")
        result.filled.append(row.stage)
    if write and result.filled:
        Path(path).write_text("".join(lines), encoding="utf-8")
    return result
