"""任务页（CHG-SCPT-2026-628 骨架 D）：一个项目的四栏卡和进门定位。

读 `pm missions --pid <项目>`（在干 / 等你 / 搁着 / 已关）和 `pm orient <项目> --json`（焦点卡、冲突、下一步）。
只读；切卡、搁着、拿回都在“决定”页或终端里做，这里不放按钮。
"""

from __future__ import annotations

from typing import Any

from cockpit_board import shell
from cockpit_board.widgets import common as c

COLUMNS = (("active", "在干"), ("waiting", "等你"), ("parked", "搁着"), ("closed", "已关"))
TITLES_SHOWN = 3  # 每栏最多列几张卡的标题


def _titles(rows: list[dict[str, Any]]) -> str:
    names = [str(row.get("title") or row.get("mission_id") or "（没写标题）") for row in rows[:TITLES_SHOWN]]
    more = f" 等 {len(rows)} 张" if len(rows) > TITLES_SHOWN else ""
    return "、".join(names) + more


def summarize(reader: str, data: dict[str, Any]) -> list[tuple[str, str]]:
    if reader == "missions":
        rows = []
        for key, name in COLUMNS:
            items = data.get(key) or []
            text = c.count_text(items, "张")
            if items and key != "closed":
                text += "：" + _titles(items)
            rows.append((name, text))
        return rows
    if reader == "orient":
        focus = data.get("mission_id") or ""
        conflicts = data.get("conflicts") or []
        return [
            ("项目", str(data.get("project_id") or "（命令没写）")),
            ("焦点卡", f"{focus} {data.get('mission_title') or ''}".strip() if focus else "没有焦点卡"),
            ("冲突", c.count_text(conflicts, "条") + ("：" + str(conflicts[0]) if conflicts else "")),
            ("下一步", str(data.get("next_legal_action") or "（命令没给）")),
        ]
    return []


def is_empty(reader: str, data: dict[str, Any]) -> bool | None:
    """在干、等你、搁着三栏都空才算空（已关的不算）；进门定位不参与判空。"""
    if reader == "missions":
        return not any(data.get(key) for key, _ in COLUMNS if key != "closed")
    return None


class TasksPage(c.ReadPage):
    def __init__(self) -> None:
        empty_text, error_text = shell.page_texts()["tasks"]
        super().__init__("tasks", "任务", "这个项目手上有几张卡、哪张在干、卡在哪", (
            ("每张卡走到脊柱第几步", "要按卡对照 flow/spine.json 的十步，还没做", "main.py pm orient <项目> --json"),
            ("换项目看", "现在只读工程工位的默认项目（--station-project）", ""),
        ), empty_text, error_text)

    def summary(self, reader: str, data: dict[str, Any]) -> list[tuple[str, str]]:
        return summarize(reader, data)

    def is_empty(self, reader: str, data: dict[str, Any]) -> bool | None:
        return is_empty(reader, data)
