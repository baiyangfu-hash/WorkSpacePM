"""脊柱图页（CHG-SCPT-2026-628 骨架 D）：一张卡从进门到收口的十步，谁做、跑哪条命令、做完的判据。

只读 `flow/spine.json`（契约测试已对过：十步齐、命令都登记过、页面都存在）。像设备的工艺流程卡：
先把标准步骤贴在墙上；“哪张卡走到第几步”这一页不画，页尾一行字指到首页的格子条和流程图页。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cockpit_board import shell
from cockpit_board.widgets import common as c
from PySide6.QtWidgets import QVBoxLayout, QWidget

SPINE = Path(__file__).resolve().parents[1] / "flow" / "spine.json"


def load(path: Path = SPINE) -> dict[str, Any] | None:
    """读不出、不是 cockpit-spine 格式都返回 None，页面写“读不懂”，不画空图。"""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(value, dict) or not str(value.get("schema_version", "")).startswith("cockpit-spine.") or not isinstance(value.get("steps"), list):
        return None
    return value


def _page_names(keys: list[str]) -> str:
    names = []
    for key in keys:
        try:
            names.append(shell.spec(key).text)
        except KeyError:
            names.append(key)
    return "、".join(names)


def step_rows(data: dict[str, Any]) -> list[tuple[str, list[tuple[str, str]]]]:
    """每一步一块：（“第 n 步 · 名字”, 几行“名字 → 值”）；脊柱外的情形接在后面。纯函数，测试直接调。"""
    lanes = {lane["id"]: lane["name"] for lane in data.get("lanes", [])}
    touches = {item["id"]: item for item in data.get("touchpoints", [])}
    blocks: list[tuple[str, list[tuple[str, str]]]] = []
    for step in data["steps"]:
        rows = [("谁做", "、".join(lanes.get(lane, lane) for lane in step.get("lanes", [])) or "（没写）"),
                ("命令", "、".join(step.get("commands", [])) or "（没有命令）"),
                ("做完的判据", str(step.get("done_when") or "（没写）")),
                ("在哪页看", _page_names(step.get("pages", [])))]
        if step.get("touch") in touches:
            rows.insert(1, ("要你出手", str(touches[step["touch"]]["name"])))
        blocks.append((f"第 {step['n']} 步 · {step['name']}", rows))
    for item in data.get("off_spine", []):
        blocks.append((f"不在主线上 · {item['name']}", [("命令", "、".join(item.get("commands", []))),
                                                   ("在哪页看", _page_names(item.get("pages", [])))]))
    return blocks


class SpinePage(QWidget):
    def __init__(self, path: Path = SPINE) -> None:
        super().__init__()
        self.setObjectName("page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll, body = c.page()
        outer.addWidget(scroll)
        body.addWidget(c.section("脊柱图", "一张卡从进门到收口的十步，每步谁做、做完看什么"))
        data = load(path)
        self.data = data
        if data is None:
            body.addWidget(c.state_line("unreadable", shell.page_texts()["spine"][1]))
        else:
            for title, rows in step_rows(data):
                frame, layout = c.card()
                layout.addWidget(c.label(title, "heading", wrap=False))
                layout.addWidget(c.kv(rows))
                body.addWidget(frame)
        body.addWidget(c.label(c.WHERE_IS_EACH_CARD, "small"))
