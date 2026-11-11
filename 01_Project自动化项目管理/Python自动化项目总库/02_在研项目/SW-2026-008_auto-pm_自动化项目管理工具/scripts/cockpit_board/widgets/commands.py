"""命令与契约页（CHG-SCPT-2026-628 骨架 D）：驾驶舱每一条命令归哪一类，界面能不能碰它。

只读 `flow/commands_map.json`（契约测试已对过真实命令树：一条不漏、一条不多）。
四类：只读（页面可以自己读）、写（要按钮和确认）、只听用户本人（要口令或你的原话）、永不放进界面。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cockpit_board.widgets import common as c
from PySide6.QtWidgets import QVBoxLayout, QWidget

COMMANDS_MAP = Path(__file__).resolve().parents[1] / "flow" / "commands_map.json"
CLASS_ZH = {"read": "只读", "write": "写", "user_only": "只听用户本人", "never": "永不放进界面"}
CLASS_TIP = {
    "read": "页面可以自己在后台读，不改任何东西",
    "write": "会改账本或文件；界面要放就得有按钮、预览和确认",
    "user_only": "要口令或你本人的原话；AI 不代做",
    "never": "界面里永远没有按钮，只在终端里由你本人做",
}


def load(path: Path = COMMANDS_MAP) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(value, dict) or not str(value.get("schema_version", "")).startswith("cockpit-commands.") or not isinstance(value.get("commands"), dict):
        return None
    return value


def grouped(data: dict[str, Any]) -> dict[str, list[tuple[str, str]]]:
    """类 → [(命令, 理由或写开关)]，按命令名排；类按 CLASS_ZH 的顺序。纯函数，测试直接调。"""
    groups: dict[str, list[tuple[str, str]]] = {key: [] for key in CLASS_ZH}
    for name, entry in sorted(data["commands"].items()):
        note = str(entry.get("note") or "")
        if entry.get("write_flags"):
            note = "带 " + "、".join(entry["write_flags"]) + " 时会写，页面不许带"
        groups.setdefault(str(entry.get("class")), []).append((name, note))
    return groups


class CommandsPage(QWidget):
    def __init__(self, path: Path = COMMANDS_MAP) -> None:
        super().__init__()
        self.setObjectName("page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll, body = c.page()
        outer.addWidget(scroll)
        body.addWidget(c.section("命令与契约", "每条命令界面能不能碰、谁能按"))
        data = load(path)
        self.data = data
        if data is None:
            body.addWidget(c.state_line("unreadable", "flow/commands_map.json 读不出或不是认得的格式"))
            return
        groups = grouped(data)
        body.addWidget(c.kv([(CLASS_ZH[key], f"{len(groups[key])} 条 · {CLASS_TIP[key]}") for key in CLASS_ZH]))
        for key, label in CLASS_ZH.items():
            frame, layout = c.card()
            layout.addWidget(c.label(f"{label}（{len(groups[key])} 条）", "heading", wrap=False))
            noted = [(name, note) for name, note in groups[key] if note]
            plain = [name for name, note in groups[key] if not note]
            if plain:
                layout.addWidget(c.label("、".join(plain), "mono"))
            if noted:
                layout.addWidget(c.kv(noted))
            body.addWidget(frame)
