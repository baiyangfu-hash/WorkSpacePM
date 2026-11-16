"""工作树与分支页（CHG-SCPT-2026-628 骨架 D；看板工位管理单加按钮）：每个工位谁开的、在干哪张卡、干不干净，能收的就地收。

读 `worktree list --json --deep --no-size`、`worktree sweep --json --no-fetch`（只列，不带 --apply）、`claim list --json --no-fetch`、
`long-run status`，再读本机的会话持有记录（`.auto-pm/station-holders/*.json`，只读）。命令里写 null 的字段（没查过）显示“没检查”，不当成“没有”。

按钮和命令见 stations.py；这里只画、只发信号，不起子进程（命令由 worktree_controller.py 交给 actions.run_cli 在后台跑）。
每个按钮先弹确认框：对象、检查结果、等价命令；看板带 AI 标记时全部灰着，确认键也灰着。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cockpit_board import decisions, shell, stations, theme
from cockpit_board.actions import Receipt
from cockpit_board.widgets import common as c
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QVBoxLayout, QWidget

LISTED = 12
RECEIPT_LIMIT = 6
OUTPUT_TAIL_LINES = 12
RECLAIM_TIP = "先只列（worktree reclaim --stale），列出来的确认后再清（加 --apply）"


def _station(row: dict[str, Any]) -> str:
    parts = [str(row.get("branch") or "（没有分支）")]
    if row.get("broken"):
        parts.append("坏了：" + str(row["broken"]))
    if not row.get("checked"):
        parts.append("改动和推送" + c.STATES["unchecked"])
    else:
        parts.append(c.flag_text(row.get("dirty"), "有未提交", "无未提交"))
        parts.append(c.flag_text(row.get("unpushed"), "有未推送", "都已推送"))
        parts.append(c.flag_text(row.get("merged"), "已并进 main", "没并进 main"))
    if row.get("stale"):
        parts.append(f"闲了 {row.get('idle_days')} 天")
    return " · ".join(parts)


def summarize(reader: str, data: dict[str, Any]) -> list[tuple[str, str]]:
    if reader == "worktree_list":
        rows_in = data.get("stations") or []
        rows = [("工位", c.count_text(rows_in, "个"))]
        rows += [(str(row.get("name")), _station(row)) for row in rows_in[:LISTED]]
        return rows
    if reader == "worktree_sweep":
        items = data.get("items") or []
        rows = [("可清理", c.count_text(items, "项") + "（只列出，没清）")]
        if data.get("fetch_warning"):
            rows.append(("注意", str(data["fetch_warning"])))
        rows += [(str(row.get("target")), f"{row.get('category')} · {row.get('reason') or ''}".rstrip(" ·")) for row in items[:LISTED]]
        return rows
    if reader == "claim_list":
        claims = [row for row in data.get("claims") or [] if row.get("status", "active") == "active"]
        return [("在用的占位", c.count_text(claims, "张"))]
    if reader == "long_run":
        tasks = data.get("tasks") or []
        running = [str(t.get("name")) for t in tasks if str(t.get("state") or "") in ("STARTING", "RUNNING")]
        return [("在跑的长任务", "、".join(running) if running else "没有")]
    return []


def is_empty(reader: str, data: dict[str, Any]) -> bool | None:
    """工位列表是空的才算空；清理清单、占位表、长任务不参与判空（“没有可清理的”不代表“没有工位”）。"""
    if reader == "worktree_list":
        return not data.get("stations")
    return None


def _data(results: Sequence[c.ReadResult], reader: str) -> dict[str, Any] | None:
    """这条命令这次真读到、读懂了的数据；没读到（含只剩快照）返回 None：按钮不能凭旧数据点。"""
    for result in results:
        if result.reader != reader:
            continue
        outcome, parsed = result.outcome, result.parsed
        if outcome is None or outcome.kind != "ok" or parsed is None or not parsed.ok:
            return None
        data: dict[str, Any] = parsed.data
        return data
    return None


class ActionDialog(QDialog):
    """会动东西的按钮点开的确认框：对象、会发生什么、检查结果、等价命令。``blocked`` 非空时确认键一直灰着。"""

    def __init__(self, action: stations.Action, blocked: str, warning: str, on_copy: Callable[[str], None],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.action, self.blocked = action, blocked
        self.setObjectName("worktree_dialog")
        self.setWindowTitle(action.label)
        self.setMinimumWidth(560)
        outer = QVBoxLayout(self)
        outer.setSpacing(theme.SPACE)
        outer.addWidget(c.label(action.label, "title", wrap=False))
        outer.addWidget(c.label(action.target, "section"))
        outer.addWidget(c.label(action.summary))
        if action.facts:
            outer.addWidget(c.kv([(key, value) for key, value in action.facts]))
        if warning:
            frame = QFrame()
            frame.setObjectName("bar")
            frame.setProperty("sev", "risk")
            QVBoxLayout(frame).addWidget(c.label(warning))
            outer.addWidget(frame)
        outer.addWidget(c.label("等价的命令行", "q"))
        self.command_text = stations.shown_command(action.args)
        outer.addWidget(c.label(self.command_text, "mono"))
        if blocked:
            outer.addWidget(c.label(blocked, "small"))
        row = QHBoxLayout()
        self.copy_button = c.button("复制命令")
        self.copy_button.clicked.connect(lambda: on_copy(self.command_text))
        self.cancel_button = c.button("取消")
        self.cancel_button.clicked.connect(self.reject)
        self.run_button = c.button("确认并运行")
        self.run_button.setObjectName("run")
        self.run_button.setEnabled(not blocked)
        self.run_button.clicked.connect(self.accept)
        row.addWidget(self.copy_button)
        row.addStretch(1)
        row.addWidget(self.cancel_button)
        row.addWidget(self.run_button)
        outer.addLayout(row)


class WorktreesPage(c.ReadPage):
    run_requested = Signal(object)  # stations.Action：用户在确认框里点了“确认并运行”
    reclaim_requested = Signal()  # 点了“清残留持有记录”：控制器先跑只列命令，再回来弹确认框

    def __init__(self, root: Path | None = None, markers: Callable[[], Sequence[str] | None] | None = None,
                 on_copy: Callable[[str], None] | None = None, now: Callable[[], datetime] | None = None) -> None:
        empty_text, error_text = shell.page_texts()["worktrees"]
        super().__init__("worktrees", "工作树与分支", "每个 AI 的工位谁开的、在干什么、干不干净，能收的就在这里收", (), empty_text, error_text)
        self.root = root
        self.markers = markers or (lambda: None)
        self.on_copy = on_copy or (lambda _text: None)
        self.now = now or (lambda: datetime.now(UTC))
        self.view = stations.StationsView()
        self.receipts: list[Receipt] = []
        self.last_dialog: ActionDialog | None = None
        self.human_block = ""
        self.pending_reclaim: stations.Action | None = None  # “清残留持有记录”只列出来的那几条，确认框用的就是它

    def summary(self, reader: str, data: dict[str, Any]) -> list[tuple[str, str]]:
        return summarize(reader, data)

    def is_empty(self, reader: str, data: dict[str, Any]) -> bool | None:
        return is_empty(reader, data)

    # ------------------------------------------------ 画

    def show_results(self, scope: str, results: Sequence[c.ReadResult]) -> None:
        super().show_results(scope, results)
        self.human_block = decisions.human_only_block(self.markers())
        listed = _data(results, "worktree_list")
        sweep = _data(results, "worktree_sweep")
        claims = _data(results, "claim_list")
        runs = _data(results, "long_run")
        self.view = stations.build_view(
            None if listed is None else listed.get("stations") or [],
            None if sweep is None else sweep.get("items") or [],
            None if claims is None else claims.get("claims") or [],
            stations.read_holders(self.root),
            human_block=self.human_block, now=self.now(),
            long_runs=None if runs is None else runs.get("tasks") or [],
        )
        if listed is None:
            self.view.notes.insert(0, "工位列表这次没读到：收工位的按钮先不放，原因见下面那条命令的原文")
        self.reads.insertWidget(0, self._actions_block())

    def _actions_block(self) -> QWidget:
        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(theme.SPACE)
        lay.addWidget(c.section("工位", "每行一个工位；按钮灰着时旁边写着差哪一条"))
        if self.human_block:
            lay.addWidget(c.label(self.human_block, "small"))
        for note in self.view.notes:
            lay.addWidget(c.label(note, "small"))
        for row in self.view.rows:
            lay.addWidget(self._row(row))
        if self.view.sweep or self.view.sweep_all is not None:
            lay.addWidget(c.section("可清理的其他项", "远程已删的本地分支等；已并进 main 的才放进整批清理"))
            for item in self.view.sweep:
                verdict = "可清" if item.removable else "保留"
                lay.addWidget(c.label(f"{item.target} · {item.category} · {verdict} · {item.reason}", "small"))
            if self.view.sweep_all is not None:
                lay.addWidget(self._action_button(self.view.sweep_all, self.view.sweep_all_blocked, ""))
        reclaim = c.button("清残留持有记录", "", RECLAIM_TIP)
        reclaim.setProperty("worktree_action", "reclaim")
        reclaim.setEnabled(not self.human_block)
        reclaim.clicked.connect(self.reclaim_requested.emit)
        lay.addWidget(c.hrow(reclaim, 1))
        lay.addWidget(c.section("刚才运行过的命令", f"最近 {RECEIPT_LIMIT} 条，命令、退出码和原文输出"))
        if not self.receipts:
            lay.addWidget(c.label("还没有运行过。", "muted"))
        for receipt in reversed(self.receipts[-RECEIPT_LIMIT:]):
            lay.addWidget(self._receipt(receipt))
        return holder

    def _row(self, row: stations.StationRow) -> QFrame:
        frame, inner = c.card("block" if row.blocked and not self.human_block else "")
        frame.setProperty("station", row.name)
        inner.addWidget(c.label(f"{row.name} · {row.branch}", "section"))
        inner.addWidget(c.kv([("谁开的", row.who), ("在干哪张卡", row.card), ("属于哪个项目", row.project),
                              ("最后动静", row.last_seen), ("检查结果", row.checks)]))
        if row.warning:
            inner.addWidget(c.label(row.warning, "small"))
        if row.action is not None:
            inner.addWidget(self._action_button(row.action, row.blocked, row.warning))
        return frame

    def _action_button(self, action: stations.Action, blocked: str, warning: str) -> QWidget:
        item = c.button(action.label, "", action.summary)
        item.setProperty("worktree_action", action.key)
        item.setProperty("target", action.target)
        item.setEnabled(not blocked)
        item.clicked.connect(lambda _checked=False, a=action, b=blocked, w=warning: self.open_dialog(a, b, w))
        widgets: list[QWidget | int] = [item]
        if blocked:
            reason = c.label(blocked, "small")
            reason.setProperty("blocked_reason", action.target)
            widgets.append(reason)
        return c.hrow(*widgets, 1)

    def _receipt(self, receipt: Receipt) -> QFrame:
        frame, inner = c.card("ok" if receipt.rc == 0 else ("block" if receipt.rc else "hint"))
        frame.setProperty("receipt", receipt.action)
        inner.addWidget(c.hrow(c.label(receipt.when, "mono", wrap=False), c.label(receipt.action, "section"),
                               c.chip(receipt.rc_text, "ok" if receipt.rc == 0 else ("block" if receipt.rc else "hint")), 1))
        inner.addWidget(c.label(receipt.command, "mono"))
        if receipt.output.strip():
            lines = [line for line in receipt.output.strip().splitlines() if line.strip()]
            inner.addWidget(c.label("\n".join(lines[-OUTPUT_TAIL_LINES:]), "small"))
        return frame

    # ------------------------------------------------ 动作

    def open_dialog(self, action: stations.Action, blocked: str = "", warning: str = "", *, run: bool = True) -> ActionDialog:
        blocked = decisions.human_only_block(self.markers()) or blocked  # 点开那一刻再看一次标记
        dialog = ActionDialog(action, blocked, warning, self.on_copy, self)
        self.last_dialog = dialog
        if run and dialog.exec() == QDialog.DialogCode.Accepted and not dialog.blocked:
            self.run_requested.emit(action)
        return dialog

    def add_receipt(self, receipt: Receipt) -> None:
        self.receipts.append(receipt)
        self.receipts = self.receipts[-RECEIPT_LIMIT * 2:]
        if self.results:
            self.show_results(self.project_line.text(), self.results)
