"""只读命令输出的纯解析（CHG-SCPT-2026-628 骨架 B）。

像 PLC 里读回来的一包数据先过一遍“校验和”：认得的格式拆成字段，认不得的老实标“读不懂”，
绝不猜、不补 0。这里不起子进程、不读写文件、不 import auto_pm；命令怎么跑、跑出错怎么归类在 actions.py。

每个解析函数收命令的 stdout 文本，返回 Parsed：state 是 "ok" 或 "unreadable"，data 是界面要用的字段。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

OK = "ok"
UNREADABLE = "unreadable"


@dataclass(frozen=True)
class Parsed:
    state: str  # OK / UNREADABLE
    data: dict[str, Any] = field(default_factory=dict)
    note: str = ""  # 读不懂时写明哪里不对

    @property
    def ok(self) -> bool:
        return self.state == OK


def unreadable(note: str) -> Parsed:
    return Parsed(UNREADABLE, {}, note)


def lenient_json(text: str) -> Any | None:
    """容错 JSON：跳过前面的提示行、后面的尾巴，从第一个以 { 或 [ 开头的行取一个完整 JSON 值；取不出返回 None。"""
    decoder = json.JSONDecoder()
    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped[:1] in ("{", "["):
            start = offset + (len(line) - len(stripped))
            try:
                value, _end = decoder.raw_decode(text, start)
            except ValueError:
                return None
            return value
        offset += len(line)
    return None


def _dict_with(value: Any, schema_prefix: str) -> dict[str, Any] | None:
    if isinstance(value, dict) and str(value.get("schema_version", "")).startswith(schema_prefix):
        return value
    return None


def _rows(value: Any, key: str) -> list[dict[str, Any]] | None:
    """value[key] 必须是由字典组成的列表，否则 None（读不懂）。"""
    rows = value.get(key) if isinstance(value, dict) else None
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        return None
    return rows


def parse_orient(text: str) -> Parsed:
    """`pm orient <PID> --json`（continuity-resume.v2）：焦点卡、冲突、出口提示、下一步合法动作。"""
    value = _dict_with(lenient_json(text), "continuity-resume.")
    if value is None or not isinstance(value.get("context"), dict):
        return unreadable("不是 continuity-resume 格式（缺 schema_version 或 context）")
    context = value["context"]
    conflicts = value.get("conflicts")
    hints = value.get("exit_hints")
    if not isinstance(conflicts, list) or not isinstance(hints, list):
        return unreadable("conflicts / exit_hints 不是列表")
    mission = value.get("mission") if isinstance(value.get("mission"), dict) else None
    return Parsed(OK, {
        "project_id": context.get("subject_project_id", ""),
        "release_id": context.get("release_id", ""),
        "mission_id": (mission or {}).get("mission_id", ""),
        "mission_title": (mission or {}).get("title", ""),
        "has_run": isinstance(value.get("run"), dict),
        "conflicts": [str(item) for item in conflicts],
        "exit_hints": [str(item) for item in hints],
        "next_legal_action": str(value.get("next_legal_action") or ""),
    })


def parse_missions(text: str) -> Parsed:
    """`pm missions --pid <PID>`（pm-missions.v1）：在干 / 等你 / 搁着 / 已关 四栏。"""
    value = _dict_with(lenient_json(text), "pm-missions.")
    if value is None:
        return unreadable("不是 pm-missions 格式")
    columns: dict[str, list[dict[str, Any]]] = {}
    for key in ("active", "waiting", "parked", "closed"):
        rows = _rows(value, key)
        if rows is None:
            return unreadable(f"缺“{key}”栏或格式不对")
        columns[key] = rows
    return Parsed(OK, {"project_id": value.get("subject_project_id", ""), "open_count": value.get("open_count"), **columns})


def parse_pending(text: str) -> Parsed:
    """`pm pending --project-id <PID>`（pm-pending-scope-cards.v1）：待批准的范围卡。"""
    value = _dict_with(lenient_json(text), "pm-pending-scope-cards.")
    rows = _rows(value, "cards") if value is not None else None
    if rows is None:
        return unreadable("不是 pm-pending-scope-cards 格式")
    return Parsed(OK, {"project_id": value.get("project_id", "") if value else "", "cards": rows})


def parse_inbox(text: str) -> Parsed:
    """`pm inbox list --project-id <PID>`（pm-inbox.v1）：收件箱条目。"""
    value = _dict_with(lenient_json(text), "pm-inbox.")
    rows = _rows(value, "items") if value is not None else None
    if rows is None:
        return unreadable("不是 pm-inbox 格式")
    return Parsed(OK, {"project_id": value.get("project_id", "") if value else "", "items": rows})


def parse_worktree_list(text: str) -> Parsed:
    """`worktree list --json`：每个工位一行（名字、分支、是否查过、未提交数……）；空列表是“没有工位”，不是读不懂。"""
    value = lenient_json(text)
    if not isinstance(value, list) or not all(isinstance(row, dict) and "name" in row and "branch" in row for row in value):
        return unreadable("不是工位列表（每行要有 name、branch）")
    return Parsed(OK, {"stations": value})


def parse_worktree_sweep(text: str) -> Parsed:
    """`worktree sweep --json`：只列可清理项（applied 为 False）；每项有 target、category、reason。"""
    value = lenient_json(text)
    rows = _rows(value, "items")
    if not isinstance(value, dict) or rows is None or not all("target" in row and "category" in row for row in rows):
        return unreadable("不是清理清单（要有 items，每项 target、category）")
    return Parsed(OK, {"applied": bool(value.get("applied")), "fetch_warning": str(value.get("fetch_warning") or ""), "items": rows})


def parse_project_list(text: str) -> Parsed:
    """`project list --json`：受管项目，每个要有 project_id。"""
    value = lenient_json(text)
    if not isinstance(value, list) or not all(isinstance(row, dict) and "project_id" in row for row in value):
        return unreadable("不是项目列表（每行要有 project_id）")
    return Parsed(OK, {"projects": value})


def parse_plc_check(text: str) -> Parsed:
    """`plc check <PID> --json`：逐项 pass / warn / fail；计数以 items 现数为准，和命令自报的计数对不上算读不懂。"""
    value = lenient_json(text)
    rows = _rows(value, "items")
    if not isinstance(value, dict) or rows is None:
        return unreadable("不是 plc check 结果（缺 items）")
    counts = {status: sum(1 for row in rows if row.get("status") == status) for status in ("pass", "warn", "fail")}
    for status, number in counts.items():
        reported = value.get(f"{status}_count")
        if reported is not None and reported != number:
            return unreadable(f"{status}_count 写的是 {reported}，逐项数出来是 {number}")
    return Parsed(OK, {"project_path": value.get("project_path", ""), "items": rows, **counts,
                       "not_applicable": bool(value.get("not_applicable"))})


def parse_long_run(text: str) -> Parsed:
    """`long-run status`：不带 --name 是 {"tasks": [...]}，每行 name、state；读不出的任务命令自己标 UNREADABLE，照原样留着。"""
    value = lenient_json(text)
    rows = _rows(value, "tasks")
    if rows is None or not all("name" in row and "state" in row for row in rows):
        return unreadable("不是长任务清单（要有 tasks，每行 name、state）")
    return Parsed(OK, {"tasks": rows})


# 解析器登记表：键是读法名（C 的 pages.json 引用这些名字），值是解析函数。
READERS: dict[str, Callable[[str], Parsed]] = {
    "orient": parse_orient,
    "missions": parse_missions,
    "pending": parse_pending,
    "inbox": parse_inbox,
    "worktree_list": parse_worktree_list,
    "worktree_sweep": parse_worktree_sweep,
    "project_list": parse_project_list,
    "plc_check": parse_plc_check,
    "long_run": parse_long_run,
}


def parse(reader: str, text: str) -> Parsed:
    """按读法名解析；没登记的读法直接报错（是代码写错了，不是数据读不懂）。"""
    return READERS[reader](text)
