"""“工作树与分支”页的接线：确认框点了“确认并运行”以后，在后台跑那条 ``main.py worktree …``，回执交回页面。

app.py 接这一页只需要：
    controller = WorktreeController(page, root, on_changed)   # on_changed：命令成功后让这一页重新读一遍

运行前再拦两道（页上的按钮和确认框已经拦过，这里防别的入口调进来）：看板进程带 AI 标记或认不出时不运行；
参数不是 policy.WORKTREE_COMMANDS 登记的形状时不运行。两种都只留一张“未运行”回执，写明原因。

本文件不直接起子进程：只调 actions.run_cli（整个包里唯一允许起子进程的地方）。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject

from cockpit_board import actions, decisions, stations
from cockpit_board.decision_controller import _Job
from cockpit_board.widgets.worktrees import WorktreesPage

NOT_ALLOWED = "这条命令不是工位页登记过的几种（policy.WORKTREE_COMMANDS），不运行"
RUNNING = "正在运行……跑完这里会出结果，这一页会自己重读"
NOTHING_TO_RECLAIM = "没有可回收的残留持有记录（worktree reclaim --stale 没列出任何一条），什么都没动"


class WorktreeController(QObject):
    def __init__(self, page: WorktreesPage, root: Path, on_changed: Callable[[], None],
                 runner: Callable[..., Any] | None = None, now: Callable[[], datetime] = datetime.now,
                 markers: Callable[[], Sequence[str] | None] = actions.board_agent_markers) -> None:
        super().__init__()
        self.page, self.root, self.on_changed, self.now = page, root, on_changed, now
        self.runner = runner  # 测试注入；None 用真的子进程
        self.markers = markers
        self._jobs: list[_Job] = []
        self.dialog_on_preview = True  # 测试置 False：只列完不弹确认框（弹框要人点）
        page.run_requested.connect(self.run)
        page.reclaim_requested.connect(self.preview_reclaim)
        page.registry_requested.connect(self.preview_registry)

    def _refuse(self, label: str, args: Sequence[str], why: str) -> None:
        self.page.add_receipt(actions.Receipt(self.now().strftime("%H:%M"), label, stations.shown_command(args) + "（未运行）", 1,
                                              False, why))

    def _blocked(self, label: str, args: Sequence[str]) -> bool:
        why = decisions.human_only_block(self.markers())
        if not why and not stations.allowed_command(args):
            why = NOT_ALLOWED
        if why:
            self._refuse(label, args, why)
            return True
        return False

    def run(self, action: stations.Action) -> None:
        """确认框里点了“确认并运行”：后台跑这条命令，跑完把回执放到页上；退出码 0 就让页面重读。"""
        if self._blocked(action.label, action.args):
            return
        extra: dict[str, Any] = {"runner": self.runner} if self.runner else {}
        # 点下去马上给个回音：命令要跑几秒，页面上什么都不变，看起来就像“点了没反应”（用户 2026-11-16 14:04 实际遇到）
        self.page.add_receipt(actions.Receipt(self.now().strftime("%H:%M"), action.label, stations.shown_command(action.args),
                                              None, False, RUNNING))

        def done(result: Any) -> None:
            self._done(action, result)

        self._spawn(lambda: actions.run_cli(self.root, action.label, action.args, timeout=actions.WRITE_TIMEOUT, **extra), done)

    def _done(self, action: stations.Action, result: actions.Receipt | Exception) -> None:
        if isinstance(result, Exception):
            self._refuse(action.label, action.args, f"{type(result).__name__}: {result}")
            return
        if result.rc == 0 and action.key in ("register", "unregister"):
            self.page.pending_registry = None
        self.page.add_receipt(result)
        if result.rc == 0:
            self.on_changed()

    def preview_reclaim(self) -> None:
        """“清残留持有记录”：先只列（不带 --apply），列出来的放进确认框；一条都没有就只留回执，不弹框。"""
        args = stations.reclaim_preview_args()
        if self._blocked("清残留持有记录（只列）", args):
            return
        extra: dict[str, Any] = {"runner": self.runner} if self.runner else {}
        self._spawn(lambda: actions.run_cli(self.root, "清残留持有记录（只列）", args, timeout=actions.READ_TIMEOUT, **extra),
                    self._previewed)

    def _previewed(self, result: actions.Receipt | Exception) -> None:
        if isinstance(result, Exception):
            self._refuse("清残留持有记录（只列）", stations.reclaim_preview_args(), f"{type(result).__name__}: {result}")
            return
        self.page.add_receipt(result)
        if result.rc != 0:  # 只列都没成：原文已在回执里，不弹框
            return
        found = stations.parse_reclaim_preview(result.stdout)
        if not found:
            self.page.add_receipt(actions.Receipt(self.now().strftime("%H:%M"), "清残留持有记录", result.command, 0, False,
                                                  NOTHING_TO_RECLAIM))
            return
        self.page.pending_reclaim = stations.reclaim_action(found)
        if self.dialog_on_preview:
            self.page.open_dialog(self.page.pending_reclaim)

    def preview_registry(self) -> None:
        """“登记新 AI”：先只读列名册（agent list --json），读到的放进登记框；没读成只留回执，不弹框。"""
        args = stations.registry_preview_args()
        if self._blocked("登记新 AI（只列名册）", args):
            return
        extra: dict[str, Any] = {"runner": self.runner} if self.runner else {}
        self._spawn(lambda: actions.run_cli(self.root, "登记新 AI（只列名册）", args, timeout=actions.READ_TIMEOUT, **extra),
                    self._registry_listed)

    def _registry_listed(self, result: actions.Receipt | Exception) -> None:
        if isinstance(result, Exception):
            self._refuse("登记新 AI（只列名册）", stations.registry_preview_args(), f"{type(result).__name__}: {result}")
            return
        if result.rc != 0:
            self.page.add_receipt(result)
            return
        self.page.pending_registry = stations.parse_registry(result.stdout)
        if self.dialog_on_preview:
            self.page.open_registry(self.page.pending_registry)

    def busy(self) -> bool:
        return bool(self._jobs)

    def _spawn(self, job: Callable[[], Any], done: Callable[[Any], None]) -> None:
        thread = _Job(job, self)
        thread.done.connect(done)
        thread.finished.connect(lambda t=thread: self._jobs.remove(t) if t in self._jobs else None)
        self._jobs.append(thread)
        thread.start()
