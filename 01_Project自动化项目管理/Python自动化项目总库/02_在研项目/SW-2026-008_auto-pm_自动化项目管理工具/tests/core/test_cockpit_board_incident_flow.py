"""总控屏“出事了”端到端：中途出两次事，照能走通的出口救回来，最后照样点总控屏的按钮收口、推到完成、对账干净。

接 ``tests/core/test_cockpit_board_full_flow.py`` 的主线（同一块总控屏、同一套沙盒和替身，夹具从那里拿），中间插两次 DJ-2026-005 试车
（2026-11-16）现场撞到过的事故，像 PLC 联调时故意拔一根线再插回去，看设备能不能自己回到正常节拍：

* 事故一“交卷被拒”：Run 开工后 agent 在工位里提交了，``pm verify`` 报“HEAD 不一致”拒收（试车第二轮 T4b）。
  出口是把提交撤回暂存区：``git reset --soft <Run 记的提交号>``，改动一个字不丢，同一个 Run 再 ``pm verify`` 就过
  （恢复路径方案 v1 第二节 X1 实测；不转 FAILED、不开新 Run、不碰红线 4 点名的单独推状态命令）。
* 事故二“收口做一半”：用户点了“确认验收”以后，收口只做了准备那一半就停了（同 D08 现场，CLOSE_HALF_DONE）。
  出口是再点一次“收口”（试车第三轮 E-9 实测走通）。

两次都走通以后，结果要和没出事的主线一模一样：验收过的字节按字节落回控制根，任务关掉，变更单推到完成，对账三项都是 0。

还没修好的写成严格 xfail，只认 ``KnownDefectError``（同主线文件）：收口做一半时进门定位指的下一步是“去交卷”（VERIFY_RUN），
可这时任务已经验收过了，照着做是错路（试车第三轮 E-1）；修好它的那张单摘掉标记。

规矩同主线文件：``scripts/cockpit_board/`` 一行不改；每条测试一个用完就丢的沙盒；agent 那一侧用和现场一样的真命令，各自一个子进程。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from auto_pm.infrastructure.continuity_store import ContinuityStore  # noqa: E402
from tests.core.test_cockpit_board_full_flow import (  # noqa: E402
    Board,
    KnownDefectError,
    board,  # noqa: F401 - fixture re-used by name
    failed,
    inbox_add,
    open_missions,
    plan,
    walk_change_to,
)
from tests.e2e.test_closure_drill import Drill, Step, change_status, comment_files  # noqa: E402
from tests.e2e.test_ide_lane_drill import EXECUTOR  # noqa: E402
from tests.e2e.test_pmf_plc import (  # noqa: E402
    PROJECT_ID,
    benchmark_tar,  # noqa: F401 - module fixture the board fixture needs, re-used by name
    git,
)

# 交卷被拒的原文里，现在的提示和“提示改成撤回提交”那张小修单改过以后的提示都有这一句（只认它，不认处理办法那半句）
HEAD_MOVED = "HEAD 不一致"


@dataclass
class Station:
    """agent 那一侧的一个工位和一个 Run：和进门细则第 6～8 步一样，全用命令行（同 ``tests/e2e/test_ide_lane_drill.Lane``）。"""

    drill: Drill
    mission_id: str
    request_id: str
    files: dict[str, str]
    work_id: str = ""
    git_head: str = ""
    log: list[Step] = field(default_factory=list)

    @property
    def worktree(self) -> Path:
        return self.drill.root / ".auto-pm" / "worktrees" / f"board-{self.request_id.lower()}"

    @property
    def run_id(self) -> str:
        return f"RUN-BOARD-{self.request_id}"

    def open(self) -> None:
        """开工位、登记 Run（带租约钱包）、转 RUNNING，在工位里写范围内的文件。“确认开工”已经由用户在总控屏上点过。"""

        drill = self.drill
        self.work_id = ContinuityStore(drill.root).get_mission(self.mission_id).root_work_id or ""
        assert self.work_id, "确认开工以后任务应当有作业票"
        git(drill.root, "worktree", "add", "-q", "--detach", str(self.worktree))
        self.git_head = git(self.worktree, "rev-parse", "HEAD")
        run = ["continuity", "run", "start", "--run-id", self.run_id, "--work-id", self.work_id, "--executor", EXECUTOR,
               "--adapter", "trae", "--worktree", str(self.worktree), "--lease-wallet", "--holder-pid", "none",
               "--idempotency-key", f"{self.run_id}:start"]
        for path in self.files:
            run += ["--owned", path, "--declared-dirty", path]
        self._ok(drill.cli(*run))
        self.transition("RUNNING")
        for relative, text in self.files.items():
            target = self.worktree / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")

    def transition(self, state: str) -> None:
        self._ok(self.drill.cli(
            "continuity", "run", "transition", "--run-id", self.run_id, "--to", state, "--owner", EXECUTOR,
            "--lease-wallet", "--idempotency-key", f"{self.run_id}:{state}",
        ))

    def verify(self) -> Step:
        return self.drill.cli("pm", "verify", "--mission-id", self.mission_id, "--lease-wallet")

    def states(self) -> tuple[str, str, str]:
        store = ContinuityStore(self.drill.root)
        mission = store.get_mission(self.mission_id)
        work = store.get_work(self.work_id)
        run = store.get_run(self.run_id)
        return mission.state.value, work.state.value, run.state.value

    def _ok(self, step: Step) -> None:
        assert step.returncode == 0, failed(step)


def start_on_the_board(screen: Board, request_id: str, label: str) -> tuple[dict[str, str], Station]:
    """主线第 1～5 步：收件箱一句话 → 点“确认入箱” → agent 出范围卡 → 点“批准范围” → 点“确认开工” → agent 开工位、写文件。"""

    drill = screen.drill
    files = comment_files(drill.root, label)
    item = inbox_add(drill, request_id)
    assert screen.click_decision("inbox_confirm", match=item["item_id"]).rc == 0
    card = plan(drill, request_id, item["item_id"], files)
    screen.reload()
    receipt = screen.click_decision("approve_card", match=card["request_id"])
    assert receipt.rc == 0, receipt.output
    (mission,) = open_missions(drill.root)
    receipt = screen.click_decision("begin_work", match=mission.mission_id)
    assert receipt.rc == 0, receipt.output
    station = Station(drill, mission.mission_id, request_id, files)
    station.open()
    return card, station


def half_close(screen: Board, card: dict[str, str]) -> None:
    """收口只做准备那一半就停（同 D08 现场：准备了，没做完）。用户已经在总控屏上点过“确认验收”。"""

    prepared = screen.drill.sdk("prepare", card)
    assert prepared.returncode == 0, failed(prepared)


# --------------------------------------------------------------------------- 出事了：两次事故，救回来，照样收口


def test_incident_a_refused_hand_in_and_a_half_done_close_both_recover_to_a_clean_ledger_by_clicking_the_board(board: Board) -> None:  # noqa: F811
    drill = board.drill
    card, station = start_on_the_board(board, "REQ-BOARD-INCIDENT", "总控屏出事了：交卷被拒、收口做一半")

    # 事故一：Run 开工后在工位里提交了，交卷被拒；任务、作业票、Run 都原地不动，不往下走也不出“受阻”
    git(station.worktree, "add", "-A")
    git(station.worktree, "commit", "-q", "-m", "Run 进行中在工位里提交（试车第二轮 T4b 现场）")
    assert git(station.worktree, "rev-parse", "HEAD") != station.git_head
    station.transition("VERIFYING")
    refused = station.verify()
    assert refused.returncode != 0, f"Run 开工后工位里提交过，交卷却过了\n{failed(refused)}"
    assert HEAD_MOVED in refused.stdout + refused.stderr, failed(refused)
    assert station.states() == ("ACTIVE", "IN_PROGRESS", "VERIFYING"), station.states()

    # 出口：把提交撤回暂存区（改动一个字不丢），同一个 Run 再交一次就过
    git(station.worktree, "reset", "--soft", station.git_head)
    assert git(station.worktree, "rev-parse", "HEAD") == station.git_head
    for relative, text in station.files.items():
        assert (station.worktree / relative).read_bytes() == text.encode("utf-8"), f"撤回提交以后工位里 {relative} 变了"
    verified = station.verify()
    assert verified.returncode == 0, failed(verified)
    assert verified.json()["verified"] is True and verified.json()["mission_state"] == "ACCEPTANCE_PENDING", verified.stdout
    assert station.states()[:2] == ("ACCEPTANCE_PENDING", "IN_PROGRESS"), station.states()

    # 用户点“确认验收”；事故二：收口只做了准备那一半就停了
    receipt = board.click_decision("accept", match=station.mission_id)
    assert receipt.rc == 0, receipt.output
    half_close(board, card)
    assert station.states() == ("ACCEPTED", "IN_PROGRESS", "VERIFYING"), station.states()

    # 出口：总控屏上“收口”按钮还在，再点一次就收完
    receipt = board.click_decision("close", match=station.mission_id)
    assert receipt.rc == 0, receipt.output
    assert open_missions(drill.root) == []
    assert station.states() == ("CLOSED", "CLOSED", "SUCCEEDED"), station.states()
    for relative, text in station.files.items():
        assert (drill.root / relative).read_bytes() == text.encode("utf-8"), f"收口后控制根里 {relative} 不是验收过的字节"

    # 和没出事的主线一样收尾：agent 把变更单推到“验收中”，点“推到完成”，对账干净，项目表回到没活
    assert change_status(drill.root, PROJECT_ID, card["change_id"]) == "approved"
    walk_change_to(drill, card["change_id"], "accepting")
    board.reload()
    receipt = board.click_decision("change_complete", match=card["change_id"])
    assert receipt.rc == 0, receipt.output
    assert change_status(drill.root, PROJECT_ID, card["change_id"]) == "completed"
    checked = drill.cli("ledger", "reconcile", PROJECT_ID)
    assert checked.returncode == 0, failed(checked)
    assert "台账缺失: 0 条, 台账多余(孤儿): 0 条, 状态不一致: 0 条" in checked.stdout, checked.stdout
    board.reload()
    assert board.project_row()["现在在干"] == "没有开着的活"


@pytest.mark.xfail(raises=KnownDefectError, strict=True, reason="试车第三轮 E-1：收口做一半时进门定位指向“去交卷”（VERIFY_RUN），任务其实已验收（恢复路径方案探测器那步修）")
def test_incident_a_half_done_close_is_pointed_at_close_not_at_hand_in_again(board: Board) -> None:  # noqa: F811
    """收口做一半的时候，进门定位（``pm orient``，看板和进门流程都靠它）给的下一步应当是“收口”，不是“去交卷”。"""

    drill = board.drill
    card, station = start_on_the_board(board, "REQ-BOARD-HALF", "总控屏出事了：收口做一半时的进门定位")
    station.transition("VERIFYING")
    verified = station.verify()
    assert verified.returncode == 0, failed(verified)
    assert board.click_decision("accept", match=station.mission_id).rc == 0
    half_close(board, card)
    assert station.states()[0] == "ACCEPTED", "前提：任务已验收，收口只做了一半"

    oriented = drill.cli("pm", "orient", PROJECT_ID, "--json")
    assert oriented.returncode == 0, failed(oriented)
    next_action = str(oriented.json().get("next_legal_action", ""))

    if next_action == "VERIFY_RUN":
        raise KnownDefectError(f"收口做一半（任务 {station.mission_id} 已验收），进门定位却叫人去交卷：{next_action}")
    assert "CLOSE" in next_action.upper(), f"收口做一半时下一步应当指向收口：{next_action}；{oriented.stdout[-800:]}"
