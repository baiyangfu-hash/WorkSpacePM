"""PR 与审计页（CHG-SCPT-2026-628 骨架 D）：开着的 PR 和 reviews/ 里的审计结论。

不另起命令：用窗口已经在读的 GitHub 采集（scripts/github_collector.py，只 GET，后台线程）。
读不到（--no-github、断网、限流、认证失败）就按三态标签写明，不画成“没有 PR”；
本机缓存里的旧数据只写“缓存截至几点”，不拿来列 PR（flow/pages.json：不用旧数据冒充）。
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from cockpit_board import shell
from cockpit_board.widgets import common as c
from PySide6.QtWidgets import QVBoxLayout, QWidget

VERDICT_ZH = {"pass": "通过", "fail": "不通过", "conditional": "有条件", "unknown": "看不出"}
LISTED = 15


def github_state(snapshot: Any, disabled: bool) -> tuple[str, str]:
    """（三态标签的键或空串, 一句状态）。只有这次真从 GitHub 读到了（fresh）才是空串。"""
    if snapshot is None:
        return "unchecked", "按 --no-github 启动，没读 GitHub" if disabled else "还没读完 GitHub"
    if snapshot.fresh:
        return "", "读到了" + ("（部分）" if snapshot.state == "partial" else "")
    state = "offline" if snapshot.state == "offline" else "unchecked"
    reason = {"offline": "断网，读不到 GitHub", "rate_limited": "GitHub 限流了", "auth": "GitHub 认证失败",
              "error": "GitHub 读取出错", "disabled": "没读 GitHub"}.get(snapshot.state, "没读到 GitHub")
    if snapshot.from_cache and snapshot.fetched_at is not None:
        reason += f"；本机缓存截至 {snapshot.fetched_at:%m-%d %H:%M} UTC，不拿来冒充现在"
    return state, reason


def pull_rows(snapshot: Any) -> list[tuple[str, str]]:
    pulls = list(snapshot.pulls)
    rows = [("开着的 PR", c.count_text(pulls, "个"))]
    for pull in pulls[:LISTED]:
        rows.append((f"#{pull.number}", f"{'草稿' if pull.draft else '正式'} · {pull.title} · {pull.head_ref}"))
    return rows


def audit_rows(snapshot: Any, dirs: Sequence[Path] = ()) -> list[tuple[str, str]]:
    """审计报告几份、读的是哪些目录、最新一份是哪份（D-317：写明读了哪里，别让人以为“没有新审计”）。"""
    audits = list(snapshot.audits)
    rows = [("审计报告", c.count_text(audits, "份"))]
    if dirs:
        rows.append(("读的目录", "、".join(str(d) for d in dirs)
                     + "；只认这些目录里“编号_*.md”的报告，写在别处的（如共享库）这里看不到，可启动时加 --reviews-dir"))
    if audits:
        newest = max(audits, key=lambda a: (a.number, a.file))
        rows.append(("编号最大的一份", newest.file))
    for audit in audits[:LISTED]:
        target = f"PR #{audit.pr}" if audit.pr else audit.file
        rows.append((target, f"{VERDICT_ZH.get(audit.verdict, audit.verdict)} · {audit.summary}"))
    return rows


class PrsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll, body = c.page()
        outer.addWidget(scroll)
        body.addWidget(c.section("PR 与审计", "哪些 PR 开着、审计怎么说"))
        holder = QWidget()
        self.box = QVBoxLayout(holder)
        self.box.setContentsMargins(0, 0, 0, 0)
        body.addWidget(holder)
        self.empty_text, self.error_text = shell.page_texts()["prs"]
        self.status: tuple[str, str] = ("", "")
        self.reviews_dirs: list[Path] = []  # 窗口启动时填 options.reviews_dirs（<root>/reviews 加 --reviews-dir 给的）
        body.addWidget(c.placeholder("每个 PR 的检查、审计逐条对照", "采集里已有这些字段，还没排版", ""))
        self.show_github(None, disabled=False)

    def show_github(self, snapshot: Any, disabled: bool) -> None:
        c.clear(self.box)
        state, status = github_state(snapshot, disabled)
        self.state = state
        # 顶上一行总状态（CHG-SCPT-2026-637）：读到且 0 个 PR → 空态；断网 → 错态；其他读不到的照旧只写下面那句说明
        if snapshot is not None and snapshot.fresh and not list(snapshot.pulls):
            self.status = ("empty", "")
            self.box.addWidget(c.page_line("", self.empty_text))
        elif state == "offline":
            self.status = ("error", "offline")
            self.box.addWidget(c.page_line("offline", self.error_text))
        else:
            self.status = ("", "")
        frame, layout = c.card()
        layout.addWidget(c.state_line(state, status))
        # 只有这次真读到了才列；缓存和从没读到过都不列，免得旧数据冒充现在、或画成“没有 PR”
        if snapshot is not None and snapshot.fresh:
            layout.addWidget(c.kv(pull_rows(snapshot)))
            layout.addWidget(c.kv(audit_rows(snapshot, self.reviews_dirs)))
        self.box.addWidget(frame)
