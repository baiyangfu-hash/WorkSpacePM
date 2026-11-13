"""“要你出手”页（CHG-SCPT-2026-628 骨架 D；计数口径 CHG-SCPT-2026-648 修 D-342）。

顶上一块“计入”：件数和首页“要你出手”同一口径，直接取首页那份 HomeVM 里各项目卡的 card.decisions
（viewmodel.attention_count），不另读账本、不另写一套判断。首页每重算一次，app 立刻重画这一块（不等下一轮读取）。
首页还没算好时写“首页还没算好，暂不计数”，不写“没有”。分页读的项目和首页不一样时写明另有几件、在哪些项目。

下面两块是明细：读 `pm pending --project-id <项目>` 和 `pm inbox list --project-id <项目>`，已算进上面的件数，不另计；
读哪些项目见 app.ask_project_ids（工程工位默认项目、账本里有等批准范围卡或等确认收件箱条目的项目、有开着的卡的项目，
最多 12 个）。明细可以比“计入”晚一轮，项目那一行写明明细是几点读的。
只读：批准、确认在“决定”页做（要口令的由你本人在终端做），这里只告诉你“有几件、是什么”。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from cockpit_board import shell
from cockpit_board.viewmodel import AttentionCount
from cockpit_board.widgets import common as c

LISTED = 5  # 每类最多列几条
NOT_READY = "首页还没算好，暂不计数"
DETAIL_NOTE = "下面是明细，已算进上面的件数，不另计"


def summarize(reader: str, data: dict[str, Any]) -> list[tuple[str, str]]:
    """明细块的要点。只列“是什么”，件数以顶上“计入”为准。"""
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


def is_empty(count: AttentionCount | None) -> bool | None:
    """判空只看计入的条目：首页还没算好（None）不判；首页口径一共 0 件才算空。"""
    if count is None:
        return None
    return count.total == 0


def counted_lines(count: AttentionCount | None) -> list[tuple[str, str]]:
    """“计入”块的几行（名字 → 值）。纯函数，测试直接调。"""
    if count is None:
        return [("计入", NOT_READY)]
    rows = [("计入（和首页同一口径）", f"{count.total} 件" if count.total else "没有")]
    for pid, items in count.per_project:
        rows.append((pid, f"{len(items)} 件" if items else "没有"))
        for item in items[:LISTED]:
            rows.append(("　· " + item.ask, item.why))
    if count.unread:
        pids = "、".join(pid for pid, _n in count.unread)
        rows.append(("本页没读的项目", f"另有 {sum(n for _p, n in count.unread)} 件在本页没读的 {len(count.unread)} 个项目里：{pids}"))
    if count.loose:
        rows.append(("不属于任何项目的 PR 签字", f"{count.loose} 件"))
    return rows


class AttentionPage(c.ReadPage):
    def __init__(self) -> None:
        empty_text, error_text = shell.page_texts()["attention"]
        super().__init__("attention", "要你出手", "现在有没有等你本人拍板的事", (), empty_text, error_text)
        self.count: AttentionCount | None = None
        self.read_at = ""  # 明细是几点读的（show_results 时记）
        self._draw_top()

    def summary(self, reader: str, data: dict[str, Any]) -> list[tuple[str, str]]:
        return summarize(reader, data)

    def is_empty(self, reader: str, data: dict[str, Any]) -> bool | None:
        """明细不参与判空：空不空只看顶上“计入”（D-342）。"""
        return None

    def show_counted(self, count: AttentionCount | None) -> None:
        """首页重算后由 app 立刻调：只重画“计入”一块，明细不动。"""
        self.count = count
        self._draw_top()

    def show_results(self, scope: str, results: Sequence[c.ReadResult], when: datetime | None = None) -> None:
        """明细读完时由 app 调：只重画明细，“计入”照旧用首页那份。"""
        self.read_at = when.strftime("%H:%M") if when is not None else ""
        super().show_results(scope + (f" · 明细读于 {self.read_at}" if self.read_at else ""), results)
        self._draw_top()

    def _draw_top(self) -> None:
        c.clear(self.top)
        kind, state = self.status
        if kind == "error" and self.error_text:
            self.top.addWidget(c.page_line(state, self.error_text))
        elif is_empty(self.count) and self.empty_text:
            self.top.addWidget(c.page_line("", self.empty_text))
        frame, layout = c.card()
        frame.setProperty("counted", "true")  # 测试按它找这一块；objectName 留给 card 的样式
        layout.addWidget(c.kv(counted_lines(self.count)))
        if self.results:
            layout.addWidget(c.label(DETAIL_NOTE, "small"))
        self.top.addWidget(frame)
