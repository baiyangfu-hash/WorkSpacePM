"""PLC 项目里程碑表的读取与检查（模板 ``0100_PLC自动化/00_通用规范/项目文档模板/11_里程碑表模板.md``）。

驾驶舱总控屏的“到期倒数”只读这张表的计划日期，所以计划日期没填要报出来：

- 表头写 ``项目来源: 新项目``（或没写、写错）：每条问题都是 ``fail``，``plc docs check`` 退出码 1；
- ``项目来源: 老项目迁入``：同样的问题只给 ``warn``（先只提示）；
- 项目里找不到里程碑表：只给 ``warn``（分不清新老项目；现有老项目都还没有这张表）；
- 共享库（``.plc.json`` 里 ``project_type`` 为 ``library``/``shared_library``，或 ``.copier-answers.yml`` 里
  ``mode: shared-library``）不是交付项目，不查。

只读，不写文件。
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from auto_pm.plc.doc_consistency import Finding

STAGES = ("需求", "设计", "编程", "仿真", "现场", "收尾")
STATUSES = ("未开始", "进行中", "已完成", "不适用")
ORIGIN_NEW = "新项目"
ORIGIN_MIGRATED = "老项目迁入"
FILE_SUFFIX = "_里程碑表.md"
TEMPLATE_HINT = "模板见 0100_PLC自动化/00_通用规范/项目文档模板/11_里程碑表模板.md"
OBJ = "里程碑表"
_EMPTY = {"", "-", "—", "待填", "待补", "tbd", "TBD"}
_SKIP_DIRS = {"node_modules", "__pycache__", "archive", "_archive", "Test", "99_基线", "工程资产"}
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ORIGIN = re.compile(r"^\s*项目来源\s*[:：]\s*[\"']?(.*?)[\"']?\s*(?:#.*)?$")
_COLUMNS = ("阶段", "计划日期", "实际日期", "状态")
_LIBRARY_TYPES = {"library", "shared_library", "shared-library"}
_MODE = re.compile(r"^\s*mode\s*:\s*[\"']?([\w-]+)[\"']?\s*$")


@dataclass(frozen=True)
class Milestone:
    stage: str
    planned: str  # "YYYY-MM-DD" or "" when not filled
    actual: str
    status: str
    note: str
    line: int


@dataclass
class MilestoneTable:
    path: str | None
    origin: str  # ORIGIN_NEW / ORIGIN_MIGRATED / raw text as written / "" when absent
    rows: list[Milestone] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    applicable: bool = True

    @property
    def strict(self) -> bool:
        return self.origin != ORIGIN_MIGRATED


def find_milestone_files(project_path: str) -> list[str]:
    found: list[str] = []
    for directory, names, files in os.walk(project_path):
        names[:] = sorted(n for n in names if not n.startswith(".") and n not in _SKIP_DIRS)
        found.extend(str(Path(directory) / f) for f in sorted(files) if f.endswith(FILE_SUFFIX))
    return found


def _cells(line: str) -> list[str]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [cell.strip().strip("`").strip() for cell in text.split("|")]


def _is_separator(line: str) -> bool:
    cells = _cells(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c) for c in cells)


def _front_matter_origin(lines: list[str]) -> str:
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = _ORIGIN.match(line)
        if match:
            return match.group(1).strip()
    return ""


def _valid_date(text: str) -> bool:
    if not _DATE.match(text):
        return False
    try:
        _dt.date.fromisoformat(text)
    except ValueError:
        return False
    return True


def read_milestones(path: str) -> MilestoneTable:
    """Parse one milestone file; findings carry the severity its 项目来源 calls for."""

    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    table = MilestoneTable(path=path, origin=_front_matter_origin(lines))
    severity = "fail" if table.strict else "warn"

    def report(kind: str, stage: str, message: str, line: int) -> None:
        table.findings.append(Finding(OBJ, kind, severity, stage, message, doc_loc=f"{path}:{line}"))

    if table.origin not in (ORIGIN_NEW, ORIGIN_MIGRATED):
        written = f"写的是“{table.origin}”" if table.origin else "没写"
        report("origin", "", f"表头“项目来源”{written}，只认“{ORIGIN_NEW}”或“{ORIGIN_MIGRATED}”，按新项目处理", 1)

    header_at = None
    for index, line in enumerate(lines):
        if line.lstrip().startswith("|") and index + 1 < len(lines) and _is_separator(lines[index + 1]):
            if all(col in _cells(line) for col in _COLUMNS):
                header_at = index
                break
    if header_at is None:
        report("table", "", f"找不到里程碑表格（表头要有 {'、'.join(_COLUMNS)} 四列）；{TEMPLATE_HINT}", 1)
        return table

    header = _cells(lines[header_at])
    col = {name: header.index(name) for name in _COLUMNS}
    note_col = header.index("备注") if "备注" in header else None
    index = header_at + 2
    while index < len(lines) and lines[index].lstrip().startswith("|"):
        cells = _cells(lines[index])

        def cell(i: int | None, cells: list[str] = cells) -> str:
            return cells[i] if i is not None and i < len(cells) else ""

        table.rows.append(Milestone(cell(col["阶段"]), cell(col["计划日期"]), cell(col["实际日期"]),
                                    cell(col["状态"]), cell(note_col), index + 1))
        index += 1

    seen: dict[str, Milestone] = {}
    for row in table.rows:
        if row.stage not in STAGES:
            report("stage", row.stage, f"阶段名不认识，只认 {' → '.join(STAGES)}", row.line)
            continue
        if row.stage in seen:
            report("stage", row.stage, f"阶段重复（第 {seen[row.stage].line} 行已有）", row.line)
            continue
        seen[row.stage] = row
    for stage in STAGES:
        if stage not in seen:
            report("stage", stage, "缺这一阶段的行", header_at + 1)

    order = [row.stage for row in table.rows if row.stage in STAGES]
    if len(order) == len(set(order)) and order != sorted(order, key=STAGES.index):
        report("stage", "", f"阶段顺序不对，应为 {' → '.join(STAGES)}", header_at + 1)

    for stage, row in seen.items():
        status = row.status
        if status not in STATUSES:
            report("status", stage, f"状态“{status}”不认识，只认 {'、'.join(STATUSES)}", row.line)
        planned_empty = row.planned in _EMPTY
        if planned_empty and status != "不适用":
            report("planned", stage, "计划日期没填（总控屏到期倒数靠它；确实没有这一阶段就把状态写“不适用”）", row.line)
        elif not planned_empty and not _valid_date(row.planned):
            report("planned", stage, f"计划日期“{row.planned}”格式不对，要写 YYYY-MM-DD", row.line)
        actual_empty = row.actual in _EMPTY
        if not actual_empty and not _valid_date(row.actual):
            report("actual", stage, f"实际日期“{row.actual}”格式不对，要写 YYYY-MM-DD", row.line)
        if status == "已完成" and actual_empty:
            report("actual", stage, "状态是“已完成”但实际日期没填", row.line)
    return table


def _is_library(project_path: str) -> bool:
    """SysLib writes ``project_type: library``; ``project create --mode shared-library`` only records the mode in
    ``.copier-answers.yml`` (its ``.plc.json`` carries no project_type)."""

    try:
        config = json.loads(Path(project_path, ".plc.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        config = None
    if isinstance(config, dict) and config.get("project_type") in _LIBRARY_TYPES:
        return True
    try:
        answers = Path(project_path, ".copier-answers.yml").read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    modes = (_MODE.match(line) for line in answers)
    return any(match is not None and match.group(1) in _LIBRARY_TYPES for match in modes)


def check_project(project_path: str) -> MilestoneTable:
    """Find and check the milestone table of one PLC project (read-only)."""

    project_path = os.path.abspath(project_path)
    if _is_library(project_path):
        return MilestoneTable(path=None, origin="", applicable=False)
    files = find_milestone_files(project_path)
    if not files:
        missing = MilestoneTable(path=None, origin="")
        missing.findings.append(Finding(
            OBJ, "missing", "warn", "",
            f"项目里没有里程碑表（文件名以“{FILE_SUFFIX}”结尾），总控屏到期倒数会显示“到期未填”；{TEMPLATE_HINT}"))
        return missing
    table = read_milestones(files[0])
    if len(files) > 1:
        others = "、".join(os.path.relpath(f, project_path) for f in files[1:])
        table.findings.insert(0, Finding(OBJ, "duplicate", "fail" if table.strict else "warn", "",
                                         f"有 {len(files)} 份里程碑表，只读了第一份；多出的：{others}",
                                         doc_loc=files[0]))
    return table
