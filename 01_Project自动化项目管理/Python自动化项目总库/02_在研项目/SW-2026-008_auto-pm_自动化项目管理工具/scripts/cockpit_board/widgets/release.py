"""发版页（CHG-SCPT-2026-628 骨架 D）：长任务（全量门禁等）现在的状态。

读 `long-run status`（只读）。生效发布版、候选包、切换都不在这里做；切换永远不放进界面。
"""

from __future__ import annotations

from typing import Any

from cockpit_board import shell
from cockpit_board.widgets import common as c

STATE_ZH = {"STARTING": "正在起", "RUNNING": "在跑", "DONE": "跑完", "FAILED": "跑完没过或没跑起来", "STOPPED": "被停了", "UNREADABLE": "读不懂"}


def _task(row: dict[str, Any]) -> str:
    state = str(row.get("state") or "")
    parts = [STATE_ZH.get(state, state or "（没写状态）")]
    if row.get("exit_code") is not None:
        parts.append(f"退出码 {row['exit_code']}")
    if row.get("started_at"):
        parts.append("开始于 " + str(row["started_at"]))
    if row.get("error"):
        parts.append(str(row["error"]))
    return " · ".join(parts)


def summarize(reader: str, data: dict[str, Any]) -> list[tuple[str, str]]:
    if reader == "long_run":
        tasks = data.get("tasks") or []
        return [("长任务", c.count_text(tasks, "个")), *((str(row.get("name")), _task(row)) for row in tasks)]
    return []


def is_empty(reader: str, data: dict[str, Any]) -> bool | None:
    """没有 STARTING 或 RUNNING 的长任务就算空（跑完的照样列在下面）。"""
    if reader == "long_run":
        return not [row for row in data.get("tasks") or [] if str(row.get("state") or "") in ("STARTING", "RUNNING")]
    return None


class ReleasePage(c.ReadPage):
    def __init__(self) -> None:
        empty_text, error_text = shell.page_texts()["release"]
        super().__init__("release", "发版", "门禁跑到哪了、能不能准备发版", (), empty_text, error_text)

    def summary(self, reader: str, data: dict[str, Any]) -> list[tuple[str, str]]:
        return summarize(reader, data)

    def is_empty(self, reader: str, data: dict[str, Any]) -> bool | None:
        return is_empty(reader, data)
