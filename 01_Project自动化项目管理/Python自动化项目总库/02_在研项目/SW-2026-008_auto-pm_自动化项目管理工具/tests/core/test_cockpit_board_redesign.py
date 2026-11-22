"""驾驶舱总控屏 GUI 重设计专项测试（local_data 只读适配、主题切换、遥测、项目总线工位、全局回执控制台）。

全部在离屏 / tmp_path 下运行，不碰真控制根、不起真实网络或外部进程、不改动受保护治理文件。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QPushButton  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cockpit_board import actions, local_data, readers, theme  # noqa: E402
from cockpit_board import viewmodel as vm  # noqa: E402
from cockpit_board.widgets import common as c  # noqa: E402
from cockpit_board.widgets.commands import CommandsPage  # noqa: E402
from cockpit_board.widgets.console import GlobalConsoleDrawer, GlobalFailureBar  # noqa: E402
from cockpit_board.widgets.decisions import DecisionsPage  # noqa: E402
from cockpit_board.widgets.flow import FlowPage  # noqa: E402
from cockpit_board.widgets.project_page import ProjectPage  # noqa: E402
from cockpit_board.widgets.projects import ProjectsPage  # noqa: E402
from cockpit_board.widgets.tools import ToolsPage  # noqa: E402
from cockpit_board.widgets.worktrees import WorktreesPage  # noqa: E402

from tests.core import test_pm_dashboard as base  # noqa: E402
from tests.core import test_pm_dashboard_gui as gui_tests  # noqa: E402

NOW = datetime(2026, 11, 21, 18, 0, tzinfo=UTC)


def _labels(widget: Any) -> list[str]:
    return [item.text() for item in widget.findChildren(QLabel)]


# ---------------------------------------------------------------- local_data 只读适配


def test_read_github_mode_default_valid_and_corrupt(tmp_path: Path) -> None:
    no_root = local_data.read_github_mode(None)
    assert no_root.mode == "备份" and not no_root.configured

    missing = local_data.read_github_mode(tmp_path)
    assert missing.mode == "备份" and not missing.configured

    mode_path = tmp_path / ".auto-pm" / "reports" / "local_merge" / "github_mode.json"
    mode_path.parent.mkdir(parents=True, exist_ok=True)
    for target_mode in ("关", "备份", "多机"):
        mode_path.write_text(json.dumps({"mode": target_mode, "set_at": "2026-11-21T12:00:00Z"}), encoding="utf-8")
        info = local_data.read_github_mode(tmp_path)
        assert info.mode == target_mode and info.configured and info.set_at == "2026-11-21T12:00:00Z"

    mode_path.write_text("{坏掉", encoding="utf-8")
    assert local_data.read_github_mode(tmp_path).mode == "读不懂"

    mode_path.write_text(json.dumps(["关"]), encoding="utf-8")
    assert local_data.read_github_mode(tmp_path).mode == "读不懂"

    mode_path.write_text(json.dumps({"mode": "未知档位"}), encoding="utf-8")
    assert local_data.read_github_mode(tmp_path).mode == "读不懂"


def test_read_merge_log_order_limit_corrupt_and_revert(tmp_path: Path) -> None:
    empty, note = local_data.read_merge_log(tmp_path)
    assert empty == [] and note == ""

    log_path = tmp_path / ".auto-pm" / "reports" / "local_merge" / "merge_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps({"time": "10:00", "branch": "trae/1", "merge_sha": "111122223333", "card": "C-1", "mode": "备份", "pushed": True}),
        "{bad json",
        json.dumps([1, 2, 3]),
        json.dumps({"time": "11:00", "branch": "claude/2", "merge_sha": "abcdef123456", "card": "C-2", "mode": "关", "pushed": False}),
        json.dumps({"time": "12:00", "branch": "antigravity/3", "merge_sha": "998877665544", "card": "C-3", "mode": "备份", "pushed": False}),
    ]
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    records, warn = local_data.read_merge_log(tmp_path, limit=2)
    assert warn == "合并日志有 2 行读不懂"
    assert [rec.card for rec in records] == ["C-3", "C-2"]
    assert records[0].revert_command == "git revert -m 1 99887766"
    assert records[1].mode == "关" and not records[1].pushed


def test_read_project_handoff_plc_sw_stale_and_corrupt(tmp_path: Path) -> None:
    assert local_data.handoff_dir_for("0100_PLC自动化/DJ-2026-005_产线") == "0100_PLC自动化/DJ-2026-005_产线/11_监控/交接交换区"
    assert local_data.handoff_dir_for("01_Project自动化项目管理/SW-2026-008") == "01_Project自动化项目管理/SW-2026-008/04_监控/交接交换区"

    sw_rel = "01_Project自动化项目管理/SW-2026-008"
    missing = local_data.read_project_handoff(tmp_path, "SW-2026-008", sw_rel, now=NOW)
    assert not missing.exists and missing.handoff_rel.endswith("/04_监控/交接交换区")

    exchange = tmp_path / sw_rel / "04_监控" / "交接交换区"
    exchange.mkdir(parents=True, exist_ok=True)
    focus_data = {
        "schema": "local-handoff-focus.v1",
        "updated_at": (NOW - timedelta(days=8)).isoformat(),
        "updated_by": "antigravity",
        "stage_goal": "完成总控屏重设计",
        "next_action": "等用户审批",
        "active_work": {"card": "GUI-01", "branch": "antigravity/SW-2026-008-gui", "chg": "CHG-SCPT-2026-999", "breakpoint": "待提交"},
        "priorities": [{"rank": 1, "item": "跑通测试", "ref": "pytest"}],
        "waiting_for_user": ["批准变更单"],
    }
    (exchange / "focus.json").write_text(json.dumps(focus_data, ensure_ascii=False), encoding="utf-8")
    (exchange / "journal.jsonl").write_text(
        "\n".join([
            json.dumps({"ts": "2026-11-12T08:00:00Z", "agent": "claude", "kind": "note", "summary": "旧记录", "card": "C-OLD"}),
            "{坏行",
            json.dumps({"ts": "2026-11-13T09:00:00Z", "agent": "antigravity", "kind": "handoff", "summary": "最新记录", "card": "GUI-01", "commit": "abc123", "next": "复核"}),
        ]) + "\n",
        encoding="utf-8",
    )

    handoff = local_data.read_project_handoff(tmp_path, "SW-2026-008", sw_rel, now=NOW, tail=5)
    assert handoff.exists and handoff.is_stale and handoff.stale_days == 8
    assert handoff.stage_goal == "完成总控屏重设计"
    assert handoff.active_card == "GUI-01" and handoff.active_chg == "CHG-SCPT-2026-999"
    assert handoff.waiting_for_user == ("批准变更单",)
    assert [ev.summary for ev in handoff.events] == ["最新记录", "旧记录"]
    assert "journal.jsonl 有 1 行读不懂" in handoff.unreadable

    # schema 不认识与 JSON 坏掉都要如实报出 unreadable
    (exchange / "focus.json").write_text(json.dumps({"schema": "other.v0"}), encoding="utf-8")
    bad_schema = local_data.read_project_handoff(tmp_path, "SW-2026-008", sw_rel, now=NOW)
    assert bad_schema.exists and "schema 不认识" in bad_schema.unreadable


def test_resolve_station_project_four_tiers() -> None:
    handoffs = {
        "DJ-2026-101": local_data.ProjectHandoff(
            project_id="DJ-2026-101",
            handoff_rel="x",
            exists=True,
            active_branch="trae/feature-alpha",
            active_card="CARD-ALPHA",
        ),
    }
    # 1. claim_paths 最高优先级
    assert local_data.resolve_station_project(
        "trae/SW-2026-008-something",
        "CARD-ALPHA",
        ["0100_PLC自动化/DJ-2026-005/OB1.scl"],
        handoffs,
        ("SW-2026-008", "DJ-2026-101", "DJ-2026-005"),
    ) == "DJ-2026-005"
    # 2. focus.json 的 active_branch / active_card 次之
    assert local_data.resolve_station_project("trae/feature-alpha", "", None, handoffs, ("SW-2026-008", "DJ-2026-101")) == "DJ-2026-101"
    assert local_data.resolve_station_project("trae/other", "CARD-ALPHA", None, handoffs, ("SW-2026-008", "DJ-2026-101")) == "DJ-2026-101"
    # 3. branch / card 中的显式项目编号正则
    assert local_data.resolve_station_project("antigravity/SW-2026-008-ui", "C-1", None, handoffs, ("SW-2026-008", "DJ-2026-101")) == "SW-2026-008"
    assert local_data.resolve_station_project("antigravity/wip", "fix-DJ-2026-101-io", None, handoffs, ("SW-2026-008", "DJ-2026-101")) == "DJ-2026-101"
    # 4. 都找不到返回空串
    assert local_data.resolve_station_project("antigravity/misc", "no-id", None, handoffs, ("SW-2026-008",)) == ""


# ---------------------------------------------------------------- 主窗口顶栏、主题、遥测与全局回执控制台


def test_window_theme_toggle_updates_button_and_flow_tokens(qapp: QApplication, tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    old_qss = qapp.styleSheet()
    window = gui_tests._window(qapp, root, db)
    try:
        window.set_theme("dark")
        assert window.theme_mode == "dark"
        assert window.theme_button.text() == "浅色"
        assert window.flow.widget.tokens_override == theme.DARK

        window.theme_button.click()
        qapp.processEvents()
        assert window.theme_mode == "light"
        assert window.theme_button.text() == "深色"
        assert window.flow.widget.tokens_override == theme.LIGHT
    finally:
        window.close()
        qapp.setStyleSheet(old_qss)


def test_version_pill_and_github_mode_pill_and_telemetry(qapp: QApplication, tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    mode_path = root / ".auto-pm" / "reports" / "local_merge" / "github_mode.json"
    mode_path.parent.mkdir(parents=True, exist_ok=True)
    mode_path.write_text(json.dumps({"mode": "关"}), encoding="utf-8")

    window = gui_tests._window(qapp, root, db, source_version="9703dfb", effective_version="1.3.3-9703dfb")
    try:
        assert window.version_pill.property("warn") == "false"
        assert not any("版本不一致" in txt for txt in _labels(window.version_pill))

        window.options.effective_version = "1.3.2-0000000"
        window._render()
        assert window.version_pill.property("warn") == "true"
        assert any("版本不一致" in txt for txt in _labels(window.version_pill))

        segs = [lbl for lbl in window.gh_mode_pill.findChildren(QLabel) if lbl.objectName() == "gh_seg"]
        assert [(s.text(), s.property("active")) for s in segs] == [("关", "true"), ("备份", "false"), ("多机", "false")]
        window.gh_mode_pill.activated.emit()
        assert window.current == "prs"

        telemetry_panel = window.sidebar.findChild(QFrame, "telemetry_panel")
        assert telemetry_panel is not None
        telemetry_texts = _labels(telemetry_panel)
        assert {"账本", "正常", "版本锁", "不一致", "GitHub", "已关闭", "AI 标记"}.issubset(set(telemetry_texts))
    finally:
        window.close()


def test_global_console_drawer_and_failure_bar_wire_to_receipts(qapp: QApplication, tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    window = gui_tests._window(qapp, root, db)
    try:
        assert window.failure_bar.isHidden()
        fail_receipt = actions.Receipt("12:00", "验证命令", "main.py bad", 2, False, "Error: boom")
        window.decisions.page.add_receipt(fail_receipt)
        assert not window.failure_bar.isHidden()
        assert len(window.console_drawer.receipts) == 1
        assert "没成功：验证命令" in " ".join(_labels(window.failure_bar))

        dismiss_btn = next(b for b in window.failure_bar.findChildren(QPushButton) if b.text() == "知道了")
        dismiss_btn.click()
        assert window.failure_bar.isHidden()

        window.worktrees.add_receipt(actions.Receipt("12:01", "再错一次", "main.py bad2", 1, False, "fail"))
        assert not window.failure_bar.isHidden()

        # 成功回执自动关掉全局常驻失败条
        window.tools.add_receipt(actions.Receipt("12:02", "正常通过", "main.py ok", 0, False, "ok"))
        assert window.failure_bar.isHidden()
        assert len(window.console_drawer.receipts) == 3

        window.console_drawer.toggle()
        assert window.console_drawer.opened and not window.console_drawer.body.isHidden()
    finally:
        window.close()


def test_console_bar_and_drawer_standalone_copy_and_dedup(qapp: QApplication) -> None:
    copied: list[str] = []
    drawer = GlobalConsoleDrawer(copied.append)
    bar = GlobalFailureBar()

    drawer.add_receipt(actions.Receipt("10:00", "收工位", "worktree close a", None, False, ""))
    drawer.add_receipt(actions.Receipt("10:01", "收工位", "worktree close a", 0, False, "done"))
    assert len(drawer.receipts) == 1 and drawer.receipts[0].rc == 0

    drawer.set_open(True)
    copy_btn = drawer.body.findChild(c.ClickBox, "copy_cmd")
    assert copy_btn is not None
    copy_btn.activated.emit()
    assert copied == ["worktree close a"]

    bar.show_failure(actions.Receipt("10:02", "失败测试", "cmd x", 3, False, "bad line"))
    assert not bar.isHidden() and bar.receipt is not None
    bar.dismiss()
    assert bar.isHidden() and bar.receipt is None


# ---------------------------------------------------------------- 升级页面与交互控件


def test_worktrees_project_bay_leds_merge_history_and_receipt_signal(qapp: QApplication, tmp_path: Path) -> None:
    log_path = tmp_path / ".auto-pm" / "reports" / "local_merge" / "merge_log.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        json.dumps({"time": "14:00", "branch": "antigravity/DJ-2026-101-fix", "merge_sha": "deadbeef1234", "card": "C-1", "mode": "关", "pushed": False}) + "\n",
        encoding="utf-8",
    )

    copied: list[str] = []
    emitted: list[actions.Receipt] = []
    page = WorktreesPage(tmp_path, lambda: (), copied.append, lambda: NOW)
    page.receipt_added.connect(emitted.append)
    page.set_context({}, ("DJ-2026-101",))

    listed = json.dumps([
        {"name": "claude-111111", "kind": "agent", "branch": "claude/DJ-2026-101-io", "checked": True, "dirty": 0, "unpushed": 2, "merged": False, "locked": False},
        {"name": "gate-formal", "kind": "other", "branch": "gate/formal", "checked": False, "dirty": None, "unpushed": None, "merged": None, "locked": False},
    ])
    results = [
        c.ReadResult("worktree_list", "main.py worktree list --json", actions.ReadOutcome("ok", "main.py worktree list --json", 0, listed), readers.parse("worktree_list", listed)),
    ]
    page.show_results("控制根", results)

    bays = page.findChildren(QFrame, "project_bay")
    rails = page.findChildren(QFrame, "bus_rail")
    pods = page.findChildren(QFrame, "station_pod")
    assert len(bays) == 1 and len(rails) == 1 and len(pods) == 1
    assert "DJ-2026-101" in _labels(bays[0])
    pod_texts = set(_labels(pods[0]))
    assert {"✓ 工作树干净", "● 未推送 2", "● 未进 main"}.issubset(pod_texts)
    assert "○ 工作树 没检查" in set(_labels(page))

    copy_btn = next(b for b in page.findChildren(QPushButton) if b.text() == "复制命令")
    copy_btn.click()
    assert copied == ["git revert -m 1 deadbeef"]

    page.add_receipt(actions.Receipt("14:05", "测试", "cmd", 0, False, ""))
    assert len(emitted) == 1


def test_decisions_counted_attention_fold_and_receipt_signal(qapp: QApplication) -> None:
    emitted: list[actions.Receipt] = []
    page = DecisionsPage(lambda _t: None, lambda *_a: "main.py ok")
    page.receipt_added.connect(emitted.append)

    dec = vm.Decision("risk", "DJ-2026-101", "批准范围", "等批", "在看板点批准", "账本", NOW)
    page.show_counted(vm.AttentionCount((("DJ-2026-101", (dec,)),), (), 1, 0))
    pending_json = json.dumps({"schema_version": "pm-pending-scope-cards.v1", "cards": [{"objective": "审批范围", "card": {"request_id": "REQ-1"}}]})
    res = c.ReadResult("pending", "main.py pm pending --project-id DJ-2026-101", actions.ReadOutcome("ok", "main.py pm pending --project-id DJ-2026-101", 0, pending_json), readers.parse("pending", pending_json))
    page.show_attention_results("项目：DJ-2026-101", [res], NOW)

    texts = _labels(page)
    assert any("待办同源计入与只读核对（D-342）" in t for t in texts)
    assert any("明细读于 18:00" in t for t in texts)
    assert any(f.property("fold") == "att_detail" for f in page.findChildren(c.Fold))

    page.add_receipt(actions.Receipt("18:00", "批准变更单", "main.py change transition CHG-1", 0, False, "ok"))
    assert len(emitted) == 1


def test_projects_filters_and_card_view_toggle(qapp: QApplication) -> None:
    opened: list[str] = []
    page = ProjectsPage(opened.append, lambda: None)
    cov = vm.Coverage(True, False, False)
    cards = [
        vm.ProjectCard("DJ-1", "装备一", False, True, "block", cov, "M1", "今日", "C1", "claude", "", "今天", kind_label="设备", status_label="在研"),
        vm.ProjectCard("LIB-1", "共享库", False, True, "ok", cov, "M2", "下周", "C2", "trae", "", "昨天", kind_label="公共库", status_label="在研"),
        vm.ProjectCard("TL-1", "旧工具", True, True, "old", cov, "M0", "—", "—", "—", "", "上月", kind_label="工具", status_label="已归档", archived=True),
    ]
    page.show_view(cards)
    assert [c_.project_id for c_ in page.cards] == ["DJ-1", "LIB-1"]

    page.kind_pills["equipment"].activated.emit()
    assert [c_.project_id for c_ in page.cards] == ["DJ-1"]

    page.kind_pills["all"].activated.emit()
    page.health_pills["block"].activated.emit()
    assert [c_.project_id for c_ in page.cards] == ["DJ-1"]

    page.health_pills["all"].activated.emit()
    page.mode_pills["cards"].activated.emit()
    assert page.table.isHidden() and not page.cards_scroll.isHidden()

    tiles = page.cards_scroll.findChildren(c.ClickBox, "project_bay")
    assert len(tiles) == 2
    tiles[0].activated.emit()
    assert opened == ["DJ-1"]


def test_project_page_phase_strip_handoff_tab_and_tasks_results(qapp: QApplication) -> None:
    page = ProjectPage(lambda: None, lambda _t: None)
    cov = vm.Coverage(True, False, False)
    card = vm.ProjectCard("DJ-2026-101", "甲设备", False, True, "ok", cov, "M1", "明日", "C-1", "claude", "断点1", "刚刚", kind_label="设备", status_label="在研")
    handoff = local_data.ProjectHandoff(
        project_id="DJ-2026-101",
        handoff_rel="0100_PLC自动化/DJ-2026-101/11_监控/交接交换区",
        exists=True,
        stage_goal="联调气缸时序",
        next_action="运行 plc check",
        stale_days=9,
        events=(local_data.HandoffEvent("2026-11-20", "plc-eng", "handoff", "完成 FB_Main", card="C-1", commit="112233", next_hint="跑检查"),),
    )
    pvm = vm.ProjectVM(card, [vm.BoardColumn("在干", "", [])], [], [], [], [], handoff=handoff)
    page.show_view(pvm, NOW, False)

    phase_pills = [lbl for lbl in page.findChildren(QLabel) if lbl.objectName() == "phase_pill"]
    assert len(phase_pills) == len(vm.PHASES) == 8
    assert all(lbl.textFormat() == Qt.TextFormat.PlainText for lbl in phase_pills)

    page.set_tab("handoff")
    handoff_texts = _labels(page)
    assert "联调气缸时序" in handoff_texts
    assert "完成 FB_Main" in handoff_texts

    missions_json = json.dumps({"schema_version": "pm-missions.v1", "active": [{"mission_id": "M-9", "title": "实时读取项"}], "waiting": [], "parked": [], "closed": []})
    page.set_tasks_results("DJ-2026-101", [c.ReadResult("missions", "main.py pm missions --pid DJ-2026-101", actions.ReadOutcome("ok", "main.py pm missions --pid DJ-2026-101", 0, missions_json), readers.parse("missions", missions_json))])
    page.set_tab("board")
    assert any("进门定位与实时任务只读核对" in t for t in _labels(page))


def test_tools_handoff_tab_flow_spine_subtab_and_commands_filter(qapp: QApplication, tmp_path: Path) -> None:
    copied: list[str] = []
    proj_rel = "01_Project自动化项目管理/DJ-2026-101"
    exchange = tmp_path / proj_rel / "04_监控" / "交接交换区"
    exchange.mkdir(parents=True, exist_ok=True)
    (exchange / "focus.json").write_text(json.dumps({"schema": "local-handoff-focus.v1", "stage_goal": "工具页交接目标"}), encoding="utf-8")

    tools = ToolsPage(tmp_path, threaded=False, on_copy=copied.append)
    tools.set_projects([("DJ-2026-101", proj_rel)])
    tools.select_tab("handoff")
    tools_texts = _labels(tools.pages["handoff"])
    assert "已建立" in tools_texts and "工具页交接目标" in tools_texts
    copy_box = tools.pages["handoff"].findChild(c.ClickBox, "copy_cmd")
    assert copy_box is not None
    copy_box.activated.emit()
    assert copied and "pm_handoff.py" in copied[0]

    flow = FlowPage()
    assert not flow.graphs_host.isHidden() and flow.spine_page.isHidden()
    flow.select_subview("spine")
    assert flow.graphs_host.isHidden() and not flow.spine_page.isHidden()

    commands = CommandsPage()
    commands.set_filter("user_only")
    commands.search_input.setText("release")
    shown = _labels(commands.cards_holder)
    assert any("release" in t for t in shown)
    assert not any(t.startswith("只读（") for t in shown)

    commands.search_input.setText("__no_such_command_xyz__")
    assert "没有匹配过滤条件的命令。" in _labels(commands.cards_holder)


def test_smoke_busy_tracks_controller_jobs_and_release_checking(qapp: QApplication, tmp_path: Path) -> None:
    from cockpit_board import smoke

    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    window = gui_tests._window(qapp, root, db)
    try:
        assert not smoke._busy(window)
        window.release_actions._checking = True
        assert smoke._busy(window)
        window.release_actions._checking = False
        assert not smoke._busy(window)
    finally:
        window.close()
