"""总控屏全流程：从收件箱一句话走到对账干净，决定类的每一步都点总控屏自己的按钮（设计：自动化流程梳理 v2.1 第七节）。

像 PLC 的仿真联调：仿真台架早就有（``tests/e2e/test_pmf_gui.py`` 接的是旧的 QML 窗口），这里把它接到用户双击 bat 打开的
这块屏 ``scripts/cockpit_board/``，再把 DJ-2026-005 试车（2026-11-16）现场撞到的故障编成测试工况：

* 主线：收件箱加一条 → 点“确认入箱” → agent 出范围卡 → 点“批准范围” → 点“确认开工” → 替身干活、质量验证 →
  点“确认验收” → 点“收口” → agent 把变更单推到“验收中” → 点“推到完成” → 对账干净；
* R1 登记表两栏：在项目页点“确认归档”“确认重新激活”，让沙盒登记表像用户本机一样带上 status，再批准；
* R2 批准半写：登记表里有一个模型里没有的字段，批准被拒以后什么都不许留下（新债二，严格 xfail）；
* R3 项目表只认任务：范围卡在等批准时，“全部项目”页的“现在在干”看得见它（新债三，严格 xfail）；
* R4 孤卡：卡还开着、作业票被取消，看板和进门定位要给“再开一张作业票”的出口，不是只能退役（第三节三层联动，严格 xfail）。
* R5 批准人为空：“决定”页顶上的“批准人”框是空的，点要批准人的按钮，确认框要让人找得到去哪填（用户 2026-11-16 第一次用看板就卡在这里，
  把名字填进了“批准意见”；看板工位管理单的 U-1 修好：确认框自己有“批准人”一栏，摘掉了严格 xfail）。

规矩（照设计第七节 7.3 的改动边界）：

* ``scripts/cockpit_board/`` 一行都不改：只用窗口上本来就有的控件、按钮字和构造参数。按钮用 ``QPushButton.click()`` 点，
  确认框里点的是框里那个“确认并运行”，不替换 ``exec``、不直接发 ``run_requested``；
* 每条测试一个用完就丢的仓库和账本（``make_drill``，钉死版本的 DJ-2026-005 基准件），不碰真账本（``tests/ledger_isolation.py``
  的绊线在 pytest 里一碰就报错）、不连 PLC、不调真 AI（执行 agent 是现成的替身子进程）；
* agent 那一侧（``pm inbox add``、``pm plan``、跑 Run、推变更单）用和现场一样的真命令，各自一个子进程；
* 还没修好的写成严格 xfail，只认 ``KnownDefectError``：只有那个缺陷自己的症状才算“已知”，别的错照样红；修好了它会自己变红
  （XPASS strict），逼修的那张单把标记摘掉。

批准人怎么过：夹具把环境变量 ``AUTO_PM_COCKPIT_APPROVER`` 设成 ``baiyang``，“决定”页顶上的“批准人”框打开时就取这个值
（``widgets/decisions.py`` 的 ``QLineEdit(os.environ.get(APPROVER_ENV, ""))``），和用户本机设了这个变量一样；测试不往框里打字，
也不改框的值（R5 除外：它把框清空，看框是空的时候确认框怎么说）。所以主线和 R1～R4 测不到“用户没设变量、框是空的”这一路，那一路归 R5。

看板进程里的 AI 标记：``tests/conftest.py`` 的自动夹具在每条测试开始前删掉全部标记，所以这里的看板是“你本人打开的”。
“带 AI 标记时用户专属按钮拦得住”另写一条测试（等补拦截单合并后起草），不在本文件。
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QLabel, QPushButton, QWidget  # noqa: E402

from auto_pm.infrastructure.continuity_store import ContinuityStore  # noqa: E402
from tests.e2e.test_closure_drill import (  # noqa: E402
    LAUNCHER,
    MAIN_DOMAIN,
    ORIGINAL_WORDS,
    PLAN_CHECKLIST,
    Drill,
    Step,
    change_status,
    comment_files,
    make_drill,
)
from tests.e2e.test_pmf_plc import (  # noqa: E402
    PROJECT,
    PROJECT_ID,
    benchmark_tar,  # noqa: F401 - module fixture re-used by name
    git,
)

PROJECT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS = PROJECT_DIR / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from cockpit_board import actions as board_actions  # noqa: E402
from cockpit_board import app as board_app  # noqa: E402
from cockpit_board import decisions as board_decisions  # noqa: E402
from cockpit_board.widgets.decisions import ConfirmDialog  # noqa: E402

APPROVER = "baiyang"
REGISTRY = "SYS-2026-001_WorkspaceGovernance/workspace_registry.json"
WAIT_MS = 180_000  # 一条命令（含启动器）在 Windows 上最慢一两分钟；超时就红，不当成“没有”
# 沙盒控制根的 main.py：看板的按钮在控制根跑 ``python -B main.py …``（actions.run_cli）；沙盒没有发布版启动器，
# 用演练自己的启动器（固定内存读数，见 test_closure_drill.LAUNCHER），并且把沙盒根当工作空间。只放在沙盒里，git 不跟踪。
SANDBOX_MAIN = (
    "import sys\n"
    "from pathlib import Path\n"
    "sys.argv[1:1] = ['-w', str(Path(__file__).resolve().parent)]\n"
) + LAUNCHER

# 今晚现场原文（新债一）：批准被拒时命令输出里的这一句。修好以前 R1 在这里停下。
REGISTRY_REFUSAL = "Workspace Registry project 字段不完整或未知"


class KnownDefectError(AssertionError):
    """严格 xfail 唯一能吸收的症状；别的失败照样是失败（同 tests/e2e/test_trial_run_drill.py）。"""


# --------------------------------------------------------------------------- 沙盒和窗口


@dataclass
class Board:
    """一块总控屏（真窗口、真控制器、真子进程），开在一个沙盒控制根上。"""

    drill: Drill
    window: Any
    qtbot: Any

    @property
    def root(self) -> Path:
        return self.drill.root

    @property
    def page(self) -> Any:
        return self.window.decisions.page

    # ---- 等

    def idle(self) -> None:
        """等窗口自己的后台线程（读账本、读老后台）和“决定”控制器的命令都跑完。"""

        def quiet() -> bool:
            controller = self.window.decisions
            return not self.window._threads and not controller._jobs and not controller._reading

        self.qtbot.waitUntil(quiet, timeout=WAIT_MS)

    def reload(self) -> None:
        """点顶栏的“重新读取”。"""
        self.idle()
        self.window.refresh_button.click()
        self.idle()

    # ---- “决定”页

    def open_decisions(self) -> None:
        """点侧栏的“决定”：页面在后台读口令状态、待批准范围卡、收件箱。"""
        self.idle()
        self.window.page_buttons["decisions"].click()
        self.idle()

    def buttons(self, decision_key: str) -> list[QPushButton]:
        return [b for b in self.page.findChildren(QPushButton) if b.property("decision") == decision_key and b.isVisible()]

    def card_texts(self) -> list[str]:
        return [f"{card.column}|{card.heading}|{card.detail}" for card in self.page.vm.cards]

    def click_decision(self, decision_key: str, *, match: str = "", fill: dict[str, str] | None = None) -> board_actions.Receipt:
        """在“决定”页点一个按钮，再在弹出的确认框里点“确认并运行”；等命令跑完、窗口重读完。返回这条命令的回执。"""

        self.reload()  # 你本人的做法：agent 那边动过账本，先点“重新读取”
        self.open_decisions()

        def candidates() -> list[QPushButton]:
            return [b for b in self.buttons(decision_key) if not match or match in self._card_heading_of(b)]

        # 页面每次重画都换一批新按钮，新按钮要等事件循环转一圈才显示（机器忙时更慢，2026-11-16 全量 -n 4 撞到过）：先等一会儿再数
        try:
            self.qtbot.waitUntil(lambda: len(candidates()) == 1, timeout=10_000)
        except Exception:  # noqa: BLE001 - 等不到就照实写出页上有什么
            raise AssertionError(
                f"“决定”页上应正好有 1 个 {decision_key}（{match}）按钮，实际 {len(candidates())}：{self.card_texts()}") from None
        button = candidates()[0]
        assert button.isEnabled(), f"{button.text()} 灰着：{self.page.vm.blocked}"
        before = len(self.page.receipts)
        problems = self._confirm_when_shown(lambda: self.page.last_dialog, fill or {})
        button.click()
        if problems:
            raise problems[0]
        self.qtbot.waitUntil(lambda: len(self.page.receipts) > before, timeout=WAIT_MS)
        self.idle()
        receipt: board_actions.Receipt = self.page.receipts[-1]
        return receipt

    def _card_heading_of(self, button: QPushButton) -> str:
        widget: QWidget | None = button
        while widget is not None and widget.property("column") is None:
            widget = widget.parentWidget()
        return " ".join(label.text() for label in widget.findChildren(QLabel)) if widget is not None else ""

    def _confirm_when_shown(self, dialog_of: Callable[[], ConfirmDialog | None], fill: dict[str, str]) -> list[AssertionError]:
        """确认框是模态的（exec 起一个嵌套事件循环）：先排一个定时器，框一出来就填栏、点框里的“确认并运行”。

        框里有不对的（确认键灰着、改走了终端窗口），点“取消”关掉框，原因记进返回的列表，由调用的人在 click() 返回后抛出：
        在定时器里直接抛错，框不会关，测试就卡在 exec 里。
        """

        from PySide6.QtCore import QTimer

        problems: list[AssertionError] = []
        tries = [0]

        def press() -> None:
            dialog = dialog_of()
            if dialog is None or not dialog.isVisible():
                tries[0] += 1
                if tries[0] < 500:  # 最多等 10 秒；框一直没出来，click() 早就返回了，调用的人会因为没有回执而超时
                    QTimer.singleShot(20, press)
                return
            for key, text in fill.items():
                box = dialog.inputs[key]
                box.setPlainText(text) if hasattr(box, "setPlainText") else box.setText(text)
            if dialog.run_button.text() != "确认并运行" or not dialog.run_button.isEnabled():
                problems.append(AssertionError(
                    f"确认框的确认键是“{dialog.run_button.text()}”、能不能点 {dialog.run_button.isEnabled()}：{dialog.problem.text()} {dialog.blocked}"))
                dialog.cancel_button.click()
                return
            dialog.run_button.click()

        QTimer.singleShot(0, press)
        return problems

    # ---- 项目页（项目生命周期）

    def lifecycle(self, key: str) -> Any:
        """项目页“项目状态”一块：点“归档…”/“重新激活…”跑预演，预演过了再点“确认归档”/“确认重新激活”，框里点“确认并运行”。"""

        entry = board_decisions.LIFECYCLES[key]
        self.idle()
        self.window.open_project(PROJECT_ID)
        self.qtbot.waitUntil(lambda: self.window.decisions.lifecycle_probe is not None, timeout=WAIT_MS)
        self.idle()
        dry = self._project_button(entry.dry_label)
        assert dry is not None
        dry.click()
        confirm_label = board_decisions.BY_KEY[entry.decision].label
        self.qtbot.waitUntil(lambda: self._project_button(confirm_label, required=False) is not None, timeout=WAIT_MS)
        before = self.window.project.lifecycle_receipt
        problems = self._confirm_when_shown(lambda: self.window.decisions.last_dialog, {})
        button = self._project_button(confirm_label)
        assert button is not None
        button.click()
        if problems:
            raise problems[0]
        self.qtbot.waitUntil(lambda: self.window.project.lifecycle_receipt not in (None, before), timeout=WAIT_MS)
        self.idle()
        return self.window.project.lifecycle_receipt[1]

    def _project_button(self, text: str, *, required: bool = True) -> QPushButton | None:
        """项目页上一个能点的按钮。页面每次重画都换一批新控件，新控件要等事件循环转一圈才显示，所以先等一会儿再找。"""

        def found() -> list[QPushButton]:
            return [b for b in self.window.project.findChildren(QPushButton) if b.text() == text and b.isVisible() and b.isEnabled()]

        if required:
            try:
                self.qtbot.waitUntil(lambda: len(found()) == 1, timeout=10_000)
            except Exception:  # noqa: BLE001 - 等不到就照实写出页上有什么
                shown = [label.text() for label in self.window.project.findChildren(QLabel) if label.isVisible()]
                raise AssertionError(f"项目页上应正好有 1 个能点的“{text}”，实际 {len(found())}；页上的字：{shown[:40]}") from None
        hits = found()
        return hits[0] if hits else None

    # ---- “全部项目”页

    def project_row(self) -> dict[str, str]:
        self.idle()
        self.window.page_buttons["projects"].click()
        table = self.window.projects.table
        headers = [table.horizontalHeaderItem(i).text() for i in range(table.columnCount())]
        for row in range(table.rowCount()):
            if table.item(row, 0).text().startswith(PROJECT_ID):
                return {headers[i]: table.item(row, i).text() for i in range(table.columnCount())}
        raise AssertionError(f"“全部项目”页没有 {PROJECT_ID} 这一行")


@pytest.fixture
def board(tmp_path: Path, benchmark_tar: bytes, qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> Iterator[Board]:  # noqa: F811
    drill = make_drill(tmp_path, benchmark_tar)
    (drill.root / "main.py").write_text(SANDBOX_MAIN, encoding="utf-8")
    with (drill.root / ".git" / "info" / "exclude").open("a", encoding="utf-8") as exclude:
        exclude.write("/main.py\n")
    # 看板起的子进程继承这个进程的环境（actions.run_cli）：找得到驾驶舱包；批准人一栏打开就有名字（窗口自己读这个变量）。
    monkeypatch.setenv("PYTHONPATH", str(PROJECT_DIR))
    monkeypatch.setenv("AUTO_PM_COCKPIT_APPROVER", APPROVER)
    options = board_app.parse_options([
        "--root", str(drill.root), "--no-git", "--no-net", "--no-github", "--no-legacy",
        "--station-project", PROJECT_ID, "--github-cache", str(tmp_path / "github_cache.json"),
    ])
    window = board_app.CockpitWindow(options)
    qtbot.addWidget(window)
    window.show()
    current = Board(drill, window, qtbot)
    current.reload()
    assert current.window.board is not None, current.window.status.text()
    yield current
    current.idle()


# --------------------------------------------------------------------------- agent 那一侧（真命令，各自一个子进程）


def inbox_add(drill: Drill, request_id: str) -> dict[str, Any]:
    added = drill.cli(
        "pm", "inbox", "add", "--project-id", PROJECT_ID, "--request-id", request_id, "--title", f"总控屏全流程 {request_id}",
        "--kind", "iteration", "--domain", MAIN_DOMAIN, "--original-words", ORIGINAL_WORDS, "--affects", "公共报警块",
        "--duplicate-check", "查过收件箱与台账，没有同类条目", "--evidence", f"file:{PROJECT}/.plc.json",
        "--disposition", "after_current", "--rationale", "演练", "--alternative", "不做", "--cost-risk", "低",
    )
    assert added.returncode == 0, drill.transcript()
    item: dict[str, Any] = added.json()["item"]
    return item


def plan(drill: Drill, request_id: str, item_id: str, files: dict[str, str]) -> dict[str, Any]:
    arguments = [
        "pm", "plan", "--project-id", PROJECT_ID, "--request-id", request_id, "--objective", f"公共报警块加注释 {request_id}",
        "--acceptance", "门禁全绿并一步收口", "--risk", "只动公共报警块，改错会影响报警指示", "--non-goal", "不下载到控制器",
        "--adapter", "codex", "--approved-model", "agent-a", "--inbox-id", item_id, *PLAN_CHECKLIST,
    ]
    for path in files:
        arguments += ["--scope", path, "--declared-dirty", path]
    planned = drill.cli(*arguments)
    assert planned.returncode == 0, drill.transcript()
    card: dict[str, Any] = planned.json()
    return card


def open_missions(root: Path) -> list[Any]:
    return list(ContinuityStore(root).list_missions(PROJECT_ID))


def ledger_events(root: Path, event_type: str) -> int:
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(f"file:{root / '.auto-pm' / 'continuity.db'}?mode=ro", uri=True)) as db:
        return int(db.execute("SELECT COUNT(*) FROM events WHERE event_type = ?", (event_type,)).fetchone()[0])


def decision_files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("DEC-*") if ".git" not in p.parts)


def walk_change_to(drill: Drill, change_id: str, target: str) -> None:
    """agent 的活：变更单从现在的状态一步一步推到 ``target``（和现场一样用 change transition，每次一步、都带 --pid）。"""

    order = ("approved", "implementing", "pending_acceptance", "accepting")
    status = change_status(drill.root, PROJECT_ID, change_id)
    assert status in order, status
    for step in order[order.index(status) + 1 : order.index(target) + 1]:
        moved = drill.cli("change", "transition", change_id, "--to", step, "--approver", APPROVER, "--comment", "总控屏全流程", "--pid", PROJECT_ID)
        assert moved.returncode == 0, drill.transcript()


def failed(step: Step) -> str:
    return (step.stdout + step.stderr)[-2000:]


# --------------------------------------------------------------------------- 主线


def test_main_line_from_one_inbox_sentence_to_a_clean_ledger_by_clicking_the_board(board: Board) -> None:
    drill = board.drill
    files = comment_files(drill.root, "总控屏全流程：主线")

    # 1 agent 收件箱加一条；“决定”页“收件箱”一栏出现它
    item = inbox_add(drill, "REQ-BOARD-MAIN")
    board.reload()
    board.open_decisions()
    assert any(t.startswith("收件箱|") and item["item_id"] in t for t in board.card_texts()), board.card_texts()

    # 2 点“确认入箱”：收件箱条目变成 CONFIRMED，“收件箱”一栏里它消失
    receipt = board.click_decision("inbox_confirm", match=item["item_id"])
    assert receipt.rc == 0, receipt.output
    assert "--approver" in receipt.command and APPROVER in receipt.command
    board.open_decisions()
    assert not any(item["item_id"] in t for t in board.card_texts()), board.card_texts()

    # 3 agent 出范围卡；“决定”页“范围卡”一栏出现它，带这一版的哈希
    card = plan(drill, "REQ-BOARD-MAIN", item["item_id"], files)
    board.reload()
    board.open_decisions()
    assert any(t.startswith("范围卡|") and card["plan_hash"][:12] in t for t in board.card_texts()), board.card_texts()

    # 4 点“批准范围”：pm approve 自己把变更单推到已批准、签 Decision、建任务
    decisions_before = decision_files(drill.root)
    receipt = board.click_decision("approve_card", match=card["request_id"])
    assert receipt.rc == 0, receipt.output
    assert change_status(drill.root, PROJECT_ID, card["change_id"]) == "approved"
    assert len(decision_files(drill.root)) > len(decisions_before), "批准成功却没有新的 Decision 文件"
    missions = open_missions(drill.root)
    assert [m.state.value for m in missions] == ["DRAFT"], missions
    mission_id = missions[0].mission_id

    # 5 点“确认开工”：任务进行中，作业票建好；替身执行 agent 干活、质量验证（和现场一样是 agent 那一侧的进程）
    receipt = board.click_decision("begin_work", match=mission_id)
    assert receipt.rc == 0, receipt.output
    (mission,) = open_missions(drill.root)
    assert mission.state.value == "ACTIVE" and mission.root_work_id, mission
    ran = drill.sdk("run", card, files)
    assert ran.returncode == 0 and ran.json()["verified"], failed(ran)
    board.reload()
    assert board.project_row()["现在在干"] != "没有开着的活"

    # 6 点“确认验收”，再点“收口”：文件按字节并回控制根，任务关掉
    receipt = board.click_decision("accept", match=mission_id)
    assert receipt.rc == 0, receipt.output
    receipt = board.click_decision("close", match=mission_id)
    assert receipt.rc == 0, receipt.output
    assert open_missions(drill.root) == []
    for relative, text in files.items():
        assert (drill.root / relative).read_bytes() == text.encode("utf-8"), f"收口后控制根里 {relative} 不是验收过的字节"
    # 收口后变更单停在“已批准”（2026-11-16 云端实测）：离“推到完成”按钮还差三步，由 agent 推
    assert change_status(drill.root, PROJECT_ID, card["change_id"]) == "approved"

    # 7 agent 把变更单推到“验收中”；点“推到完成”；对账干净，项目表回到没活
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
    board.open_decisions()
    assert not any(card["change_id"] in t or mission_id in t for t in board.card_texts()), board.card_texts()


# --------------------------------------------------------------------------- 回归用例（DJ-2026-005 试车，2026-11-16）


def test_r1_approval_still_works_after_the_board_archived_and_reactivated_the_project(board: Board) -> None:
    """新债一：用户本人点“确认归档”“确认重新激活”，登记表就带上 status（和用户本机同一来路），之后批准不能被拒。

    登记表两栏修复单（CHG-SCPT 待编号）合并之前这条是红的，红在批准那一步、原文就是 REGISTRY_REFUSAL；
    本文件按约定排在那张单之后合并，所以这里不标 xfail。
    """

    drill = board.drill
    receipt = board.lifecycle("archive")
    assert receipt.rc == 0, receipt.output
    receipt = board.lifecycle("reactivate")
    assert receipt.rc == 0, receipt.output
    entry = next(p for p in json.loads((drill.root / REGISTRY).read_text(encoding="utf-8"))["projects"] if p["project_id"] == PROJECT_ID)
    # 归档、重新激活只写 status（2026-11-16 云端实测）；kind 只有 project register --kind 才写。多一栏就够撞上新债一。
    assert entry.get("status") == "active", f"归档、重新激活以后登记表应带上 status：{entry}"

    files = comment_files(drill.root, "总控屏全流程：R1")
    item = inbox_add(drill, "REQ-BOARD-R1")
    assert board.click_decision("inbox_confirm", match=item["item_id"]).rc == 0
    card = plan(drill, "REQ-BOARD-R1", item["item_id"], files)
    board.reload()
    receipt = board.click_decision("approve_card", match=card["request_id"])
    assert REGISTRY_REFUSAL not in receipt.output, f"新债一：登记表带上 status 后批准被拒\n{receipt.output}"
    assert receipt.rc == 0, receipt.output
    assert [m.state.value for m in open_missions(drill.root)] == ["DRAFT"]


@pytest.mark.xfail(raises=KnownDefectError, strict=True, reason="新债二：批准中途被拒，变更单已写成“已批准”（后续单修）")
def test_r2_a_refused_approval_leaves_nothing_half_written(board: Board) -> None:
    drill = board.drill
    files = comment_files(drill.root, "总控屏全流程：R2")
    item = inbox_add(drill, "REQ-BOARD-R2")
    assert board.click_decision("inbox_confirm", match=item["item_id"]).rc == 0
    card = plan(drill, "REQ-BOARD-R2", item["item_id"], files)
    # 登记表里有一个模型里没有的字段：签 Decision 时必须拒（登记表两栏修复单保留这道严格性）
    registry = drill.root / REGISTRY
    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["projects"][0]["hand_edited_extra"] = "x"
    registry.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    git(drill.root, "commit", "-q", "-am", "登记表多一个字段")
    status_before = change_status(drill.root, PROJECT_ID, card["change_id"])
    board.reload()

    receipt = board.click_decision("approve_card", match=card["request_id"])

    assert receipt.rc != 0, f"登记表有未知字段，批准却过了\n{receipt.output}"
    assert board.page.failure is receipt, "批准被拒，“决定”页顶上应有红条"
    status_after = change_status(drill.root, PROJECT_ID, card["change_id"])
    reserved = ledger_events(drill.root, "PLANNING_DECISION_RESERVED")
    if status_after == "approved" and status_before != "approved":
        raise KnownDefectError(f"批准被拒，变更单却已是“已批准”（之前 {status_before}），账本预留 {reserved} 次")
    assert status_after == status_before, f"批准被拒，变更单从 {status_before} 变成了 {status_after}"
    assert reserved == 0, "批准被拒，账本里却留下了 Decision 预留"
    assert open_missions(drill.root) == []


@pytest.mark.xfail(raises=KnownDefectError, strict=True, reason="新债三：项目表“现在在干”只认任务，看不见等批准的范围卡（看板单修）")
def test_r3_the_projects_page_shows_a_scope_card_that_waits_for_approval(board: Board) -> None:
    drill = board.drill
    files = comment_files(drill.root, "总控屏全流程：R3")
    item = inbox_add(drill, "REQ-BOARD-R3")
    assert board.click_decision("inbox_confirm", match=item["item_id"]).rc == 0
    card = plan(drill, "REQ-BOARD-R3", item["item_id"], files)
    board.reload()
    board.open_decisions()
    assert any(t.startswith("范围卡|") for t in board.card_texts()), "前提：“决定”页看得见这张范围卡"
    assert open_missions(drill.root) == [], "前提：范围卡批准前还不是任务"

    doing = board.project_row()["现在在干"]

    if doing == "没有开着的活":
        raise KnownDefectError(f"范围卡 {card['request_id']} 在等批准，“全部项目”页却写“没有开着的活”")
    assert card["request_id"] in doing or "范围卡" in doing, f"“现在在干”应指出这张等批准的范围卡：{doing}"


@pytest.mark.xfail(raises=KnownDefectError, strict=True, reason="孤卡：作业票取消后任务只能退役，没有“再开一张作业票”的出口（三层联动单修）")
def test_r4_an_open_card_whose_work_was_cancelled_offers_a_new_work_not_only_retirement(board: Board) -> None:
    """卡确认开工以后，作业票被取消（现场是租约过期清算之后；这里用同一条 Work 状态命令直接取消，来路是推断，见草稿第 5 节）。"""

    drill = board.drill
    files = comment_files(drill.root, "总控屏全流程：R4")
    item = inbox_add(drill, "REQ-BOARD-R4")
    assert board.click_decision("inbox_confirm", match=item["item_id"]).rc == 0
    card = plan(drill, "REQ-BOARD-R4", item["item_id"], files)
    board.reload()
    assert board.click_decision("approve_card", match=card["request_id"]).rc == 0
    (mission,) = open_missions(drill.root)
    assert board.click_decision("begin_work", match=mission.mission_id).rc == 0
    (mission,) = open_missions(drill.root)
    cancelled = drill.cli("continuity", "work", "transition", "--work-id", mission.root_work_id, "--to", "CANCELLED",
                          "--idempotency-key", "board-r4-cancel")
    assert cancelled.returncode == 0, failed(cancelled)
    assert [m.mission_id for m in open_missions(drill.root)] == [mission.mission_id], "前提：作业票取消，任务不动（用户的逻辑）"

    oriented = drill.cli("pm", "orient", PROJECT_ID, "--json")
    assert oriented.returncode == 0, failed(oriented)
    said = oriented.stdout

    if f"pm retire --pid {PROJECT_ID} --mission-id {mission.mission_id}" in said and "新开" not in said:
        raise KnownDefectError(f"孤卡 {mission.mission_id}：进门定位只给“pm retire 收掉”，没有再开作业票的出口")
    assert "pm retire" not in said, f"作业票取消后任务还在，不该叫用户退役它：{said[-800:]}"


def test_r5_an_empty_approver_box_tells_you_where_to_fill_it_in(board: Board) -> None:
    """用户本机没设批准人变量时，“决定”页顶上的“批准人”框是空的。点“确认入箱”（要批准人的按钮都走同一处 ``_need``），
    确认框不能放行，而且要让人一眼找到去哪填：框里自己有“批准人”一栏，或者提示写明在“决定”页顶上的“批准人”框。"""

    from PySide6.QtCore import QTimer

    drill = board.drill
    item = inbox_add(drill, "REQ-BOARD-R5")
    board.reload()
    board.open_decisions()
    board.page.approver_input.setText("")  # 用户本机没设变量时框就是空的；这里照那个样子清空
    board.qtbot.waitUntil(lambda: len([b for b in board.buttons("inbox_confirm") if item["item_id"] in board._card_heading_of(b)]) == 1,
                          timeout=10_000)
    (button,) = [b for b in board.buttons("inbox_confirm") if item["item_id"] in board._card_heading_of(b)]
    before = len(board.page.receipts)
    seen: dict[str, Any] = {}

    def look_then_cancel() -> None:
        dialog = board.page.last_dialog
        if dialog is None or not dialog.isVisible():
            QTimer.singleShot(20, look_then_cancel)
            return
        seen.update(problem=dialog.problem.text(), runnable=dialog.run_button.isEnabled(),
                    fields=sorted(dialog.inputs), labels=" ".join(label.text() for label in dialog.findChildren(QLabel)))
        dialog.cancel_button.click()

    QTimer.singleShot(0, look_then_cancel)
    button.click()
    board.qtbot.waitUntil(lambda: bool(seen), timeout=10_000)
    assert seen["runnable"] is False, f"批准人是空的，确认框却能点“确认并运行”：{seen}"
    assert "批准人" in seen["problem"], f"确认框应说缺的是批准人：{seen}"
    board.idle()
    assert len(board.page.receipts) == before, f"点了取消，却跑了命令：{board.page.receipts[before:]}"

    has_own_box = any("approver" in key for key in seen["fields"])
    says_where = "决定" in seen["problem"] and any(word in seen["problem"] for word in ("顶上", "上方", "上面", "页首"))
    if not (has_own_box or says_where):
        raise KnownDefectError(f"批准人为空时确认框只说“{seen['problem']}”，框里没有批准人一栏，也没说去“决定”页顶上的“批准人”框填")

