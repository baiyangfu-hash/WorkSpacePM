"""“发版”页的接线（CHG-SCPT-2026-707）：列候选版本、在后台逐个跑 ``release ship <提交> --json``（只看），
用户在确认框里点了“确认并运行”以后，生成凭据、写批准记录、再跑真发版那条命令，回执和结果交回页面。

app.py 接这一页只需要：
    controller = ReleaseController(page, root)   # 打开这一页时调 controller.refresh()

只看那条也是 user_only 命令：看板带 AI 标记或认不出时不跑，只写原因。
运行真发版前再拦几道（页上的按钮和确认框已经拦过，这里防别的入口调进来），拦下就只留一张“未运行”回执，写明原因：
看板进程带 AI 标记或认不出；release_ship.blocked_reason 不为空（没判决、没放行、预检没过、命令说不能切、已经生效、上一次还在跑）；
批准人没填或有不能用的字符；参数不是 policy.RELEASE_COMMANDS 登记的形状；批准记录没写成。

本文件不直接起子进程、不直接写文件：起命令只调 actions.run_cli，写批准记录只调 actions.record_board_approval。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject

from cockpit_board import actions, decisions, release_ship
from cockpit_board.decision_controller import _Job
from cockpit_board.release_ship import Candidate, Check
from cockpit_board.widgets.release import RUNNING, ReleasePage

NOT_ALLOWED = "这条命令不是发版页登记过的两种（policy.RELEASE_COMMANDS），不运行"
NO_APPROVER = "没填批准人（你的名字），不运行"
RECORD_FAILED = "批准记录没写成，不运行：{error}"


class ReleaseController(QObject):
    def __init__(self, page: ReleasePage, root: Path, runner: Callable[..., Any] | None = None,
                 now: Callable[[], datetime] = lambda: datetime.now(UTC),
                 markers: Callable[[], Sequence[str] | None] = actions.board_agent_markers, session: str = "") -> None:
        super().__init__()
        self.page, self.root, self.now, self.markers = page, root, now, markers
        self.runner = runner  # 测试注入；None 用真的子进程
        self.session = session or uuid.uuid4().hex[:12]  # 看板会话号：每开一次看板换一个，写进凭据和批准记录
        self._jobs: list[_Job] = []
        self._checking = False
        self._recheck = False  # 检查的过程中又要求重查（比如刚切完）：这一轮查完马上再查一次，不能丢
        self._switching = False
        page.check_requested.connect(self.refresh)
        page.switch_requested.connect(self.switch)

    # ------------------------------------------------ 只看

    def refresh(self) -> None:
        """列候选版本，对每个在后台跑一遍只看的 ``release ship <提交> --json``；上一轮没查完就记下，查完再查。

        ``release ship`` 在命令表里是 user_only（同 release deploy）：看板带 AI 标记或认不出时，连只看的那条也不跑，只写原因。
        """
        if self._checking:
            self._recheck = True
            return
        candidates = release_ship.list_candidates(self.root)
        why = decisions.human_only_block(self.markers())
        self.page.set_candidates(candidates, checking=bool(candidates) and not why, check_block=why)
        if not candidates or why:
            return
        self._checking = True
        extra: dict[str, Any] = {"runner": self.runner} if self.runner else {}

        def job() -> list[Check]:
            checks = []
            for candidate in candidates:
                receipt = actions.run_cli(self.root, f"检查 {candidate.release_id}", release_ship.check_args(candidate.commit),
                                          timeout=release_ship.CHECK_TIMEOUT, **extra)
                checks.append(release_ship.parse_check(candidate, receipt.rc, receipt.stdout, receipt.output))
            return checks

        self._spawn(job, self._checked)

    def _checked(self, result: list[Check] | Exception) -> None:
        self._checking = False
        if isinstance(result, Exception):
            problem = f"检查没跑完：{type(result).__name__}: {result}"
            self.page.set_checks([Check(candidate, None, problem) for candidate in self.page.candidates])
        else:
            self.page.set_checks(result)
        if self._recheck:
            self._recheck = False
            self.refresh()

    # ------------------------------------------------ 真发版

    def _refuse(self, release_id: str, args: Sequence[str], why: str) -> None:
        shown = release_ship.shown_command(args) if args else f"release ship（{release_id}）"
        self.page.add_receipt(actions.Receipt(self._clock(), release_ship.SWITCH_PREFIX + release_id, shown + "（未运行）", 1,
                                              False, why))

    def _clock(self) -> str:
        return self.now().astimezone().strftime("%H:%M")

    def switch(self, release_id: str, approver: str) -> None:
        """确认框里点了“确认并运行”：再判一遍，生成凭据、先写批准记录，写成了才在后台跑真发版，跑完把结果放到页上。"""
        check = self.page.checks.get(release_id)
        why = decisions.human_only_block(self.markers()) or release_ship.blocked_reason(check, busy=self._switching)
        name = approver.strip()
        if not why and not name:
            why = NO_APPROVER
        if not why:
            try:
                name = decisions._free(name, decisions.APPROVER_LABEL)
            except decisions.DecisionError as error:
                why = str(error)
        if why or check is None:
            self._refuse(release_id, (), why or "还没读到这个版本的检查结论")
            return
        moment = self.now()
        ref = release_ship.confirm_ref(moment, self.session)
        args = release_ship.switch_args(check.commit, ref, name)
        if not release_ship.allowed_command(args):
            self._refuse(release_id, args, NOT_ALLOWED)
            return
        try:  # 先留下“谁、何时点的”，写不成就不动版本
            actions.record_board_approval(self.root, release_ship.APPROVAL_RECORD,
                                          release_ship.approval_record(check, ref, name, moment, self.session))
        except OSError as error:
            self._refuse(release_id, args, RECORD_FAILED.format(error=f"{type(error).__name__}: {error}"))
            return
        label = release_ship.SWITCH_PREFIX + release_id
        # 点下去马上给个回音：这条命令要跑好几分钟，页面上什么都不变，看起来就像“点了没反应”（#851 同样的修法）
        self.page.add_receipt(actions.Receipt(self._clock(), label, release_ship.shown_command(args), None, False, RUNNING))
        self._switching = True
        self.page.set_busy(True)
        extra: dict[str, Any] = {"runner": self.runner} if self.runner else {}
        self._spawn(lambda: actions.run_cli(self.root, label, args, timeout=release_ship.SWITCH_TIMEOUT, **extra),
                    lambda result: self._switched(check.candidate, args, result))

    def _switched(self, candidate: Candidate, args: Sequence[str], result: actions.Receipt | Exception) -> None:
        self._switching = False
        self.page.set_busy(False)
        if isinstance(result, Exception):
            self._refuse(candidate.release_id, args, f"{type(result).__name__}: {result}")
            self.page.set_result(candidate.release_id, "没读到发版结果（命令没跑起来），看下面的回执", "block")
        else:
            self.page.add_receipt(result)
            parsed = release_ship.parse_check(candidate, result.rc, result.stdout, result.output)
            text, sev = release_ship.result_text(None if parsed.problem else parsed.result, result.rc, parsed.deployed)
            self.page.set_result(candidate.release_id, text, sev)
        self.refresh()  # 切没切成都按命令现在说的重查一遍：生效版本变了，按钮该灰

    def busy(self) -> bool:
        return bool(self._jobs)

    def _spawn(self, job: Callable[[], Any], done: Callable[[Any], None]) -> None:
        thread = _Job(job, self)
        thread.done.connect(done)
        thread.finished.connect(lambda t=thread: self._jobs.remove(t) if t in self._jobs else None)
        self._jobs.append(thread)
        thread.start()
