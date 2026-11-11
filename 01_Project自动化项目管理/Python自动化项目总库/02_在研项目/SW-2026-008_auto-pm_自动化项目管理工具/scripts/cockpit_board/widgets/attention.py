"""“要你出手”页（CHG-SCPT-2026-628 骨架 D）：等你批准的范围卡、等你确认的收件箱条目。

读 `pm pending --project-id <项目>` 和 `pm inbox list --project-id <项目>`。只读：批准、确认在“决定”页做
（要口令的由你本人在终端做），这里只告诉你“有几件、是什么”。
"""

from __future__ import annotations

from typing import Any

from cockpit_board.widgets import common as c

LISTED = 5  # 每类最多列几条


def summarize(reader: str, data: dict[str, Any]) -> list[tuple[str, str]]:
    if reader == "pending":
        cards = [row for row in data.get("cards") or [] if not row.get("superseded")]
        rows = [("等你批准的范围卡", c.count_text(cards, "张"))]
        for row in cards[:LISTED]:
            card = row.get("card") if isinstance(row.get("card"), dict) else {}
            rows.append((str(card.get("request_id") or "（没写请求号）"), str(row.get("objective") or "（没写目标）")))
        return rows
    if reader == "inbox":
        items = data.get("items") or []
        proposed = [row for row in items if str(row.get("status", "")).upper() == "PROPOSED"]
        rows = [("等你确认的收件箱条目", c.count_text(proposed, "条")), ("收件箱一共", c.count_text(items, "条"))]
        for row in proposed[:LISTED]:
            rows.append((str(row.get("item_id") or "（没写编号）"), str(row.get("title") or "（没写标题）")))
        return rows
    return []


class AttentionPage(c.ReadPage):
    def __init__(self) -> None:
        super().__init__("attention", "要你出手", "现在有没有等你本人拍板的事", (
            ("所有项目合在一起看", "现在只读工程工位的默认项目；“决定”页已按项目读全", ""),
            ("规则、门禁、安全类的 PR 等你点", "要读 GitHub 的检查结果，还没接", ""),
        ))

    def summary(self, reader: str, data: dict[str, Any]) -> list[tuple[str, str]]:
        return summarize(reader, data)
