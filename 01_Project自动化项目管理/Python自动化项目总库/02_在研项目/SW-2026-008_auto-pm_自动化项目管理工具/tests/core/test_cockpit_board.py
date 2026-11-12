"""驾驶舱总控屏的纯 Python 层：视图模型、主题令牌、按钮规矩、本机动作。不需要 Qt。"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from tests.core import test_pm_dashboard as base
from tests.core.test_pm_run_e2e import PROJECT_ID

pytestmark = pytest.mark.external_reads  # D-200: reads real files outside the project

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cockpit_board import actions, policy, theme  # noqa: E402
from cockpit_board import viewmodel as vm

pd = base.pd
NOW = base.NOW
OFFSET = timezone(timedelta(hours=-7))


def _board(tmp_path: Path, missions: list[tuple[str, str, str, float]]) -> Any:
    root, db = base._workspace(tmp_path, missions)
    return pd.build_board(root, db, NOW, use_git=False, use_legacy=False)


# ---------------------------------------------------------------- 问题三档与要你出手


def test_issue_tiers_and_decisions(tmp_path: Path) -> None:
    board = _board(
        tmp_path,
        [
            ("DJ-2026-101", "BLOCKED", "卡住了", 0.5),
            ("DJ-2026-101", "AWAITING_APPROVAL", "等批一", 4),
            ("DJ-2026-101", "ACCEPTANCE_PENDING", "等验收", 1),
        ],
    )
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    card = next(c for c in home.hot if c.project_id == "DJ-2026-101")
    titles = {i.title: i.sev for i in card.issues}
    assert titles["卡住要拿主意"] == "block"
    assert titles["等你超过 3 天：批准范围"] == "block"  # 等批一 等了 4 天
    assert titles["验收结果"] == "hint"  # 等验收 才 1 天
    assert titles["业务变更待批"] == "hint"
    assert card.health == "block"
    # 要你出手：严重的在前、等得久的在前，每件一句回复
    asks = [(d.sev, d.ask, d.reply) for d in home.decisions]
    assert asks[0][0] == "block" and "范围认" in asks[0][2]
    assert all(d.reply for d in home.decisions)
    assert home.decisions_total >= 4 and len(home.decisions) == pd.MAX_DECISIONS
    # 每条问题都写明谁动手和依据
    assert all(i.who and i.basis for i in card.issues)


def test_lost_executor_versus_leftover(tmp_path: Path) -> None:
    # 卡开着 + 租约过期 + 最近断点超过 1 小时 → 失联（阻塞）
    board = _board(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.2)])
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    card = home.hot[0]
    assert any(i.title == "执行者失联" and i.sev == "block" for i in card.issues)
    lost = next(k for k in home.checks if k.key == "lost")
    assert lost.state == "number" and lost.value == 1
    # 卡已关的旧 Run 只算遗留（提醒），不算失联
    board = _board(tmp_path / "b", [("DJ-2026-101", "CLOSED", "早关了", 30)])
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    card = next(c for c in home.hot + home.rest if c.project_id == "DJ-2026-101")
    assert not any(i.title == "执行者失联" for i in card.issues)
    assert any(i.title == "账本遗留" and i.sev == "hint" for i in card.issues)


def test_checks_never_render_zero_without_a_source(tmp_path: Path) -> None:
    board = _board(tmp_path, [])
    for online in (None, False, True):
        checks = vm.checks_of(board, [], online)
        assert len(checks) == 6
        for check in checks:
            if check.state != "number":
                assert check.text in policy.UNCHECKED_TEXTS
                assert check.sev == "na"
        keys = {c.key: c.state for c in checks}
        assert keys["gate_red"] == ("offline" if online is False else "unchecked") and keys["scope"] == "unchecked"
        assert keys["safety_unsigned"] == ("offline" if online is False else "unchecked")
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    assert home.checks_ran == 3  # 只有账本路线的三项真跑了


def test_health_nodata_when_ledger_or_git_missing(tmp_path: Path) -> None:
    board = _board(tmp_path, [])
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    by_id = {c.project_id: c for c in home.hot + home.rest}
    assert by_id["DJ-2026-102"].health == "off"  # 没登记
    assert by_id["SW-2026-008"].health in ("nodata", "hint", "risk")  # 没开卡 → 看不出好坏，不许绿
    assert by_id["SW-2026-008"].health != "ok"
    assert by_id["DJ-2026-101"].coverage.git is False  # use_git=False → 覆盖里 Git ✗
    assert "Git ✗" in by_id["DJ-2026-101"].coverage.text()


def test_station_gating(tmp_path: Path) -> None:
    board = _board(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    home = vm.home_vm(board, OFFSET, online=False, use_git=False)
    station = vm.station_vm(board, home.hot + home.rest, False, {"source": "a", "effective": "a"}, "manual/x", [], False)
    assert station.warn and station.banner.startswith("当前离线")
    buttons = {text: (enabled, reason) for step in station.steps for text, _key, enabled, reason in step.buttons}
    for text in ("推送 manual/ 分支", "打开 GitHub 开 PR"):
        assert buttons[text][0] is False and "离线" in buttons[text][1]
    for text in policy.GATED_UNTIL_WIRED:
        # 灰着时必须说清现在去终端用哪条命令，不许再写“缺口⑨合并后”这种早已过期的理由
        assert buttons[text][0] is False and "main.py pm " in buttons[text][1] and "缺口" not in buttons[text][1]
    assert buttons["提交"][0] is False
    assert buttons["重新跑 plc check"][0] is True
    # 在线 + 界面已接好批准口令：批准和开工开放（开工仍不启动 agent，只是按钮可用）
    station = vm.station_vm(board, home.hot + home.rest, True, {"source": "a", "effective": "a"}, "manual/x", [], True)
    buttons = {text: (enabled, reason) for step in station.steps for text, _k, enabled, reason in step.buttons}
    assert buttons["批准范围"][0] and buttons["开工"][0]
    # 推送 / 开 PR 本版没实现：在线也灰着，提示去命令提示符和网页做（Codex 评审 #52）
    for text in ("推送 manual/ 分支", "打开 GitHub 开 PR"):
        assert buttons[text][0] is False and "本版不做" in buttons[text][1]
    assert not station.warn
    # 只有登记的客户项目进“接着干”
    assert [p[0].project_id for p in station.projects] == ["DJ-2026-101"]


def test_station_does_not_pretend_to_know_steps_it_never_checked_or_send_the_user_to_pm_session(tmp_path: Path) -> None:
    """试用 11-01：工程工位把“开分支”标成已完成、“改程序”标成进行中（界面根本没核对），
    还叫用户“先在 PM_SESSION 写明要做什么”——PM_SESSION 已于 2026-10-10 退役。"""
    board = _board(tmp_path, [])
    for project in board.projects:
        project.cards = []  # 没有实施卡：走“先在 PM_SESSION 写明要做什么”那一支
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    station = vm.station_vm(board, home.hot + home.rest, None, {"source": "a", "effective": "a"}, "manual/x", [], False)
    assert [s.state for s in station.steps[:2]] == ["unk", "unk"]  # 没核对，不冒充 done / cur
    assert station.projects, "测试数据里应有一个已登记的客户项目"
    for _card, _left, nxt, files, _branch, _safety in station.projects:
        assert "PM_SESSION" not in nxt and not any("PM_SESSION" in f for f in files)
        assert "业务变更" in nxt  # 改指向现行的第 4 步


# ---------------------------------------------------------------- 搁着栏读账本里的断点（TD-071）

PARKS_DDL = (
    "CREATE TABLE run_parks (park_id TEXT PRIMARY KEY, run_id TEXT, mission_id TEXT, checkpoint_id TEXT, "
    "parked_by TEXT, reason TEXT, parked_at TEXT, unparked_at TEXT, unparked_by TEXT)"
)


def _columns(board: Any) -> dict[str, Any]:
    home = vm.home_vm(board, OFFSET, online=False, use_git=False)
    card = next(c for c in home.hot + home.rest if c.project_id == "DJ-2026-101")
    return {col.name: col for col in vm.project_vm(board, card, OFFSET, False).columns}


def test_parked_column_shows_reason_and_breakpoint_from_the_ledger(tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "PARKED", "HMI 报警页改版", 2)])
    connection = sqlite3.connect(db)
    connection.execute(PARKS_DDL)
    # 一条已拿回的旧记录（不该显示）和一条还开着的当前记录
    connection.execute(
        "INSERT INTO run_parks VALUES ('P-old','RUN-0','MISSION-0','CK-0','Trae','旧原因','2026-10-01T00:00:00+00:00',"
        "'2026-10-02T00:00:00+00:00','user')"
    )
    connection.execute(
        "INSERT INTO run_parks VALUES ('P-now','RUN-0','MISSION-0','CK-0','Trae','客户急改 IO 表','2026-10-20T00:00:00+00:00',NULL,NULL)"
    )
    connection.commit()
    connection.close()
    board = pd.build_board(root, db, NOW, use_git=False, use_legacy=False)
    parked = _columns(board)["搁着"]
    assert [row[0] for row in parked.cards] == ["MISSION-0"]
    meta = parked.cards[0][2]
    assert "原因：客户急改 IO 表" in meta and "断点：干到一半" in meta and "旧原因" not in meta
    assert "TD-071" not in parked.note and "还没有" not in parked.note  # 过期的“账本里还没有 PARKED”提示已去掉


def test_parked_column_with_only_an_unparked_old_record_has_no_breakpoint(tmp_path: Path) -> None:
    """搁着的卡只有一条已拿回的旧挂起记录（没有开着的）：不把旧原因和旧断点当成现在的显示出来。"""
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "PARKED", "HMI 报警页改版", 2)])
    connection = sqlite3.connect(db)
    connection.execute(PARKS_DDL)
    connection.execute(
        "INSERT INTO run_parks VALUES ('P-old','RUN-0','MISSION-0','CK-0','Trae','旧原因','2026-10-01T00:00:00+00:00',"
        "'2026-10-02T00:00:00+00:00','user')"
    )
    connection.commit()
    connection.close()
    parked = _columns(pd.build_board(root, db, NOW, use_git=False, use_legacy=False))["搁着"]
    assert [row[0] for row in parked.cards] == ["MISSION-0"]
    assert "旧原因" not in parked.cards[0][2] and "断点" not in parked.cards[0][2] and "原因" not in parked.cards[0][2]


def test_parked_column_without_a_park_record_or_table_still_renders(tmp_path: Path) -> None:
    # 老账本没有 run_parks 表、也可能没有记录：卡照样出现在搁着栏，只是没有断点；空栏写“没有搁着的卡”
    board = _board(tmp_path, [("DJ-2026-101", "PARKED", "HMI 报警页改版", 2), ("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    columns = _columns(board)
    assert [row[0] for row in columns["搁着"].cards] == ["MISSION-0"]
    assert "断点" not in columns["搁着"].cards[0][2] and columns["搁着"].note == ""
    empty = _columns(_board(tmp_path / "x", [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)]))
    assert empty["搁着"].cards == [] and empty["搁着"].note == "没有搁着的卡"


# ---------------------------------------------------------------- 变更记录要列正式变更单

CHG_ORDER = """# 变更单

### 3.0 编号与项目
| 字段 | 内容 |
|------|------|
| 变更编号 | CHG-PLC-2026-015 |
| 项目编号 | DJ-2026-101 |

### 3.4 其他
| 字段 | 内容 |
|------|------|
| 申请日期 | 2026-10-23 |
| 变更状态 | approved |

## 4. 变更原因

**变更背景**：
修复公共报警结构体两个字段的数组声明
"""


def _order_dir(root: Path) -> Path:
    folder = root / "0100_PLC自动化" / "DJ-2026-101_甲" / "11_监控" / "01_变更管理" / "01_变更单" / "CHG-PLC"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _changes_of(board: Any) -> list[Any]:
    home = vm.home_vm(board, OFFSET, online=False, use_git=False)
    card = next(c for c in home.hot + home.rest if c.project_id == "DJ-2026-101")
    return list(vm.project_vm(board, card, OFFSET, False).changes)


def test_change_orders_are_read_from_the_project_folder(tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [])
    (_order_dir(root) / "CHG-PLC-2026-015.md").write_text(CHG_ORDER, encoding="utf-8")
    orders = pd.read_change_orders(root / "0100_PLC自动化" / "DJ-2026-101_甲")
    assert [(o.change_id, o.domain, o.status, o.raised) for o in orders] == [
        ("CHG-PLC-2026-015", "PLC", "approved", "2026-10-23")
    ]
    assert orders[0].what == "修复公共报警结构体两个字段的数组声明"
    # 进了变更记录页签：变更单一行，来源写明是变更单而不是业务变更
    board = pd.build_board(root, db, NOW, use_git=False, use_legacy=False)
    rows = [c for c in _changes_of(board) if c.change_id == "CHG-PLC-2026-015"]
    assert [(r.kind, r.status, r.date) for r in rows] == [("变更单 PLC", "approved", "2026-10-23")]


def test_change_order_with_unknown_format_is_listed_not_dropped(tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [])
    (_order_dir(root) / "CHG-PLC-2026-099.md").write_text("# 变更单\n\n正文没有表格\n", encoding="utf-8")
    board = pd.build_board(root, db, NOW, use_git=False, use_legacy=False)
    rows = [c for c in _changes_of(board) if c.change_id == "CHG-PLC-2026-099"]
    # 读不出状态也要列出来，状态写“未读到状态”，日期写“日期待补”——不许从列表里消失让人以为没改过
    assert [(r.status, r.date) for r in rows] == [("未读到状态", "日期待补")]


def test_project_without_change_order_folder_has_no_order_rows(tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [])
    board = pd.build_board(root, db, NOW, use_git=False, use_legacy=False)
    assert not any(c.kind.startswith("变更单") for c in _changes_of(board))


# 审计 536 的三个存活变异：状态口径、“变更背景”同行写法、表格行要整格相等


def _order_text(**fields: str) -> str:
    return (
        "# 变更单\n\n| 字段 | 内容 |\n|------|------|\n"
        + "".join(f"| {name} | {value} |\n" for name, value in fields.items())
        + "\n**变更背景**：" + "同行写的背景正文\n"
    )


def _read_one(tmp_path: Path, text: str) -> Any:
    root, _db = base._workspace(tmp_path, [])
    (_order_dir(root) / "CHG-PLC-2026-050.md").write_text(text, encoding="utf-8")
    orders = pd.read_change_orders(root / "0100_PLC自动化" / "DJ-2026-101_甲")
    assert len(orders) == 1
    return orders[0]


def test_when_a_sheet_has_two_status_rows_the_later_one_counts(tmp_path: Path) -> None:
    """状态口径：一张单里“变更状态”出现两处（例如头部是草稿、后面流转到已批准），以后出现的为准。"""
    text = "| 变更状态 | draft |\n| 申请日期 | 2026-10-01 |\n\n正文\n\n| 变更状态 | approved |\n"
    order = _read_one(tmp_path, "| 字段 | 内容 |\n|---|---|\n" + text)
    assert order.status == "approved" and order.raised == "2026-10-01"
    # 后面一处是空格子时不覆盖前面读到的状态
    order = _read_one(tmp_path / "b", "| 字段 | 内容 |\n|---|---|\n| 变更状态 | approved |\n| 变更状态 |  |\n")
    assert order.status == "approved"


def test_background_on_the_same_line_as_the_label_is_read(tmp_path: Path) -> None:
    order = _read_one(tmp_path, _order_text(变更编号="CHG-PLC-2026-050", 变更状态="approved", 申请日期="2026-10-23"))
    assert order.what == "同行写的背景正文"


def test_background_on_the_next_line_still_works_and_same_line_wins(tmp_path: Path) -> None:
    next_line = "| 变更状态 | approved |\n\n**变更背景**：\n\n下一行的正文\n"
    assert _read_one(tmp_path, "| 字段 | 内容 |\n|---|---|\n" + next_line).what == "下一行的正文"
    both = "| 变更状态 | approved |\n\n**变更背景**：同行\n下一行\n"
    assert _read_one(tmp_path / "b", "| 字段 | 内容 |\n|---|---|\n" + both).what == "同行"


def test_table_cells_must_equal_the_field_name_not_just_contain_it(tmp_path: Path) -> None:
    """“旧变更状态”“备注：变更状态说明”这类格子不能被当成“变更状态”。"""
    text = (
        "| 字段 | 内容 |\n|---|---|\n| 旧变更状态 | rejected |\n| 备注变更状态 | on_hold |\n"
        "| 变更状态说明 | 没有用 |\n| 原申请日期 | 2020-01-01 |\n"
    )
    order = _read_one(tmp_path, text)
    assert order.status == "未读到状态" and order.raised == ""
    ok = _read_one(tmp_path / "b", text + "| 变更状态 | approved |\n| 申请日期 | 2026-10-23 |\n")
    assert (ok.status, ok.raised) == ("approved", "2026-10-23")


# ---------------------------------------------------------------- 变更记录：从新到旧，只列最近 30 条


def _many_orders(root: Path, dates: list[str], status: str = "completed", start: int = 1) -> None:
    """按日期各放一张变更单；默认都是已收口（completed），要测没收口的另给 status。编号从 start 起。"""
    folder = _order_dir(root)
    for index, day in enumerate(dates, start=start):
        number = f"CHG-PLC-2026-{index:03d}"
        text = CHG_ORDER.replace("CHG-PLC-2026-015", number).replace("2026-10-23", day).replace("| 变更状态 | approved |", f"| 变更状态 | {status} |")
        (folder / f"{number}.md").write_text(text, encoding="utf-8")


def _order_rows(board: Any) -> list[Any]:
    return [c for c in _changes_of(board) if c.kind.startswith("变更单")]


def test_change_records_are_newest_first(tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [])
    _many_orders(root, ["2026-09-01", "2026-10-20", "2026-08-15", "2026-10-02"])
    board = pd.build_board(root, db, NOW, use_git=False, use_legacy=False)
    assert [r.date for r in _order_rows(board)] == ["2026-10-20", "2026-10-02", "2026-09-01", "2026-08-15"]


def test_same_day_orders_put_the_larger_number_first(tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [])
    _many_orders(root, ["2026-10-20"] * 3)
    board = pd.build_board(root, db, NOW, use_git=False, use_legacy=False)
    assert [r.change_id for r in _order_rows(board)] == ["CHG-PLC-2026-003", "CHG-PLC-2026-002", "CHG-PLC-2026-001"]


def _project_of(board: Any) -> Any:
    home = vm.home_vm(board, OFFSET, online=False, use_git=False)
    card = next(c for c in home.hot + home.rest if c.project_id == "DJ-2026-101")
    return vm.project_vm(board, card, OFFSET, False)


# 假工作空间里已有 1 条业务变更（BC，2026-10-01，状态“待批”＝没收口）和 1 张实施卡；下面的数量都把它们算进去


def test_only_the_latest_30_closed_are_listed_and_the_rest_are_counted(tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [])
    days = [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(45)]  # 45 张已收口的变更单，日期各不相同
    _many_orders(root, days)
    project = _project_of(pd.build_board(root, db, NOW, use_git=False, use_legacy=False))
    rows = [c for c in project.changes if c.kind != "实施卡"]
    assert [r.change_id for r in rows[:1]] == ["BC-DJ-2026-101-001"]  # 没收口的在最上面，不占名额
    closed = rows[1:]
    assert len(closed) == vm.CHANGES_SHOWN == 30
    assert [r.date for r in closed] == sorted(days, reverse=True)[:30]  # 已收口的留下最新的 30 条
    assert "还有 15 条" in project.changes_more and "最近 30 条" in project.changes_more and "01_变更管理" in project.changes_more


def test_exactly_30_closed_or_fewer_shows_no_more_line(tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [])
    _many_orders(root, [f"2026-09-{1 + i:02d}" for i in range(30)])
    project = _project_of(pd.build_board(root, db, NOW, use_git=False, use_legacy=False))
    assert len([c for c in project.changes if c.kind.startswith("变更单")]) == 30 and project.changes_more == ""
    root2, db2 = base._workspace(tmp_path / "b", [])
    _many_orders(root2, [f"2026-09-{1 + i:02d}" for i in range(31)])  # 再多一张已收口的才有“还有 1 条”
    assert "还有 1 条" in _project_of(pd.build_board(root2, db2, NOW, use_git=False, use_legacy=False)).changes_more


@pytest.mark.parametrize("status", ["draft", "approved", "implementing", "pending_acceptance", "Approved", " draft "])
def test_an_old_unclosed_change_is_listed_next_to_30_newer_closed_ones(tmp_path: Path, status: str) -> None:
    """协调者裁决：没收口的变更再旧也不能被“最近 30 条”藏起来，也不占那 30 个名额。"""
    root, db = base._workspace(tmp_path, [])
    _many_orders(root, ["2020-01-01"], status=status, start=1)  # 最老的一张，还没收口
    _many_orders(root, [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(35)], start=2)  # 35 张更新的，已收口
    project = _project_of(pd.build_board(root, db, NOW, use_git=False, use_legacy=False))
    orders = [c for c in project.changes if c.kind.startswith("变更单")]
    assert "CHG-PLC-2026-001" in [c.change_id for c in orders]  # 老的没收口的在
    assert len(orders) == 31  # 1 张没收口的 + 30 张已收口的最新
    assert orders[0].change_id == "CHG-PLC-2026-001"  # 没收口的排在已收口的上面
    assert "还有 5 条" in project.changes_more  # 只数没列出的已收口的，那张老单不算


@pytest.mark.parametrize("status", ["completed", "closed", "rejected", "cancelled"])
def test_closed_statuses_are_subject_to_the_limit(tmp_path: Path, status: str) -> None:
    root, db = base._workspace(tmp_path, [])
    _many_orders(root, ["2020-01-01"], status=status, start=1)
    _many_orders(root, [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(30)], start=2)
    project = _project_of(pd.build_board(root, db, NOW, use_git=False, use_legacy=False))
    assert "CHG-PLC-2026-001" not in [c.change_id for c in project.changes] and "还有 1 条" in project.changes_more


def test_unclosed_rows_are_sorted_newest_first_among_themselves_and_unknown_status_counts_as_unclosed(tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [])
    _many_orders(root, ["2021-05-01"], status="draft", start=1)
    _many_orders(root, ["2023-05-01"], status="implementing", start=2)
    (_order_dir(root) / "CHG-PLC-2026-099.md").write_text("# 变更单\n\n正文没有表格\n", encoding="utf-8")  # 读不出状态
    _many_orders(root, [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(31)], start=10)
    project = _project_of(pd.build_board(root, db, NOW, use_git=False, use_legacy=False))
    top = [c.change_id for c in project.changes if c.kind != "实施卡"][:4]
    assert top == ["BC-DJ-2026-101-001", "CHG-PLC-2026-002", "CHG-PLC-2026-001", "CHG-PLC-2026-099"]  # 新→旧，没日期的最后


def test_closure_rows_are_sorted_by_the_mission_update_time(tmp_path: Path) -> None:
    """收口记录按任务更新时间参与排序，不是被丢到最后（审计 544 的存活变异）。"""
    import sqlite3 as sql  # noqa: PLC0415

    root, db = base._workspace(tmp_path, [("DJ-2026-101", "CLOSED", "旧任务", 400), ("DJ-2026-101", "CLOSED", "新任务", 1)])
    with sql.connect(db) as connection:
        connection.execute("INSERT INTO closure_items VALUES ('CL-0', 'MISSION-0', 'CHG-OLD-1', 'COMPLETED', ?)", (base._iso(400),))
        connection.execute("INSERT INTO closure_items VALUES ('CL-1', 'MISSION-1', 'CHG-NEW-1', 'COMPLETED', ?)", (base._iso(1),))
    _many_orders(root, [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(40)])
    project = _project_of(pd.build_board(root, db, NOW, use_git=False, use_legacy=False))
    closures = [c for c in project.changes if c.kind == "收口"]
    assert [c.change_id for c in closures] == ["CHG-NEW-1"]  # 新的在前列里；400 天前的那条被挤出 30 条之外
    assert "还有" in project.changes_more


def test_what_counts_as_unclosed() -> None:
    """变更单看状态；业务变更看“待批”；收口记录和实施卡的状态不是变更的收口状态，不算。"""
    def row(kind: str, status: str) -> Any:
        return vm.ChangeRow("X", "2026-01-01", kind, "x", status)

    assert all(vm.is_unclosed(row("变更单 PLC", s)) for s in ("draft", "approved", "implementing", "pending_acceptance", "未读到状态"))
    assert not any(vm.is_unclosed(row("变更单 PLC", s)) for s in ("completed", "closed", "rejected", "cancelled", ""))
    assert vm.is_unclosed(row("参数", "待批")) and vm.is_unclosed(row("参数", "待批准"))
    assert not vm.is_unclosed(row("参数", "已批"))
    assert not vm.is_unclosed(row("收口", "draft")) and not vm.is_unclosed(row("实施卡", "approved"))


def test_dates_must_start_with_yyyy_mm_dd_otherwise_the_row_counts_as_undated() -> None:
    """把当前行为钉住：只认 2026-10-21 这种开头；2026-1-5、2026/10/21、日期待补都按“没写日期”，排在有日期的后面。"""
    for text in ("2026-1-5", "2026/10/21", "日期待补", "", "10-21"):
        assert vm._day(text) is None, text
    assert vm._day("2026-10-21") == datetime(2026, 10, 21, tzinfo=UTC)
    assert vm._day("2026-10-21 14:30") == datetime(2026, 10, 21, tzinfo=UTC)


def test_undated_rows_go_last_and_do_not_pose_as_newest() -> None:
    dated = [vm.ChangeRow(f"X-{i}", "2026-10-01", "BC", "x", "ok", datetime(2026, 10, 1 + i, tzinfo=UTC)) for i in range(3)]
    undated = [vm.ChangeRow("U-1", "日期待补", "BC", "x", "ok"), vm.ChangeRow("U-2", "日期待补", "BC", "x", "ok")]
    shown, more = vm.recent_changes(undated + dated, "proj", limit=3)
    assert [r.change_id for r in shown] == ["X-2", "X-1", "X-0"]  # 有日期的先占满名额
    assert "还有 2 条" in more and "2 条没写日期" in more
    shown, more = vm.recent_changes(undated + dated, "proj", limit=4)
    assert [r.change_id for r in shown] == ["X-2", "X-1", "X-0", "U-1"] and "还有 1 条" in more


def test_cards_are_always_listed_after_the_changes_and_do_not_use_up_the_30(tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [])
    _many_orders(root, [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(40)])
    cards = root / "0100_PLC自动化" / "DJ-2026-101_甲" / "11_监控" / "01_变更管理" / "03_实施卡"
    cards.mkdir(parents=True, exist_ok=True)
    for number in ("CARD-001", "CARD-002"):
        (cards / f"{number}_做点事.md").write_text(f"# {number} 做点事\n\n> 状态：进行中\n", encoding="utf-8")
    board = pd.build_board(root, db, NOW, use_git=False, use_legacy=False)
    kinds = [c.kind for c in _changes_of(board)]
    assert kinds.count("实施卡") == 3 and kinds[-3:] == ["实施卡"] * 3  # 原有 1 张 + 新放的 2 张
    assert sum(1 for k in kinds if k != "实施卡") == 31  # 1 条没收口的业务变更 + 最近 30 条已收口


# ---------------------------------------------------------------- 主题令牌


def test_theme_tokens_are_the_only_colors() -> None:
    names = theme.token_names()
    for tokens in (theme.LIGHT, theme.DARK):
        qss = theme.build_qss(tokens)
        allowed = {getattr(tokens, name).lower() for name in names}
        used = {m.lower() for m in re.findall(r"#[0-9a-fA-F]{6}\b", qss)}
        assert used <= allowed, used - allowed  # 样式表里每个颜色都来自令牌
        for name in names:
            assert getattr(tokens, name).startswith("#")
    assert "fonts.googleapis" not in theme.build_qss(theme.LIGHT)
    # 画面代码里不许写颜色，改颜色只改 theme.py
    for path in (SCRIPTS / "cockpit_board").rglob("*.py"):
        if path.name != "theme.py":
            assert not re.search(r"#[0-9a-fA-F]{6}\b", path.read_text(encoding="utf-8")), path.name


# ---------------------------------------------------------------- 本机动作


REPO_ROOT = Path(__file__).resolve().parents[6]
BC_TEMPLATE = REPO_ROOT / "0100_PLC自动化" / "00_通用规范" / "项目文档模板" / "02_业务变更记录模板.md"
BC_REAL = REPO_ROOT / "0100_PLC自动化" / "DJ-2026-009_汇川换型改造" / "11_监控" / "01_变更管理" / "02_变更记录" / "02_业务变更记录.md"


def _form(**changes: str) -> actions.BcForm:
    values = {
        "raised": "2026-10-23 14:05", "channel": "电话", "who": "张工（客户设备科）", "kind": "参数",
        "what": "上料节拍 30 s → 28 s", "why": "客户要提产", "impact": "FB_2001 节拍计时；无图纸改动",
    }
    values.update(changes)
    return actions.BcForm(**values)


def _row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _template_record(tmp_path: Path, source: Path = BC_TEMPLATE) -> Path:
    record = tmp_path / "02_业务变更记录.md"
    record.write_bytes(source.read_bytes())
    return record


def test_bc_row_matches_the_11_column_template(tmp_path: Path) -> None:
    """审计 95（高）：BC 行按模板 11 栏生成，内容全来自用户填的表单，提出时间写到分钟，提出人不写死。"""
    record = _template_record(tmp_path)
    header = actions.bc_header(record)
    assert len(header) == 11 and header[0] == "编号" and header[-1] == "关联 CHG / 提交"
    preview = actions.bc_preview(record, "DJ-2026-009", _form(what="A | B"))
    cells = _row(preview.line)
    assert len(cells) == len(header) == len(preview.columns) == 11
    assert dict(preview.columns) == dict(zip(header, cells, strict=True))
    by_name = dict(preview.columns)
    assert by_name["编号"] == "BC-DJ-2026-009-2026_10_000"  # 模板占位行 BC-<项目号>-… 不算，这个月从 000 起
    assert by_name["提出时间"] == "2026-10-23 14:05（电话）"
    assert by_name["提出人"] == "张工（客户设备科）" and by_name["类型"] == "参数"
    assert by_name["改了什么（原来 → 改成）"] == "A ｜ B"  # 竖线换成全角，不会多出一栏
    assert by_name["为什么"] == "客户要提产" and by_name["影响"].startswith("FB_2001")
    assert by_name["批准人"] == by_name["批准日期"] == by_name["关联 CHG / 提交"] == ""
    assert by_name["状态"] == "待批"
    assert "baiyang" not in preview.line and "（填" not in preview.line


def test_bc_row_against_the_real_009_record(tmp_path: Path) -> None:
    """拿 DJ-2026-009 真实的变更记录试：仍是 11 栏，编号按月从 000 起。
    第 2 栏名跟着仓库现状走（老表“提出日期”，main 上 eab587dc 起改成“提出时间”），两种都要能过。"""
    record = _template_record(tmp_path, BC_REAL)
    preview = actions.bc_preview(record, "DJ-2026-009", _form())
    header = actions.bc_header(record)
    assert len(_row(preview.line)) == len(header) == 11
    assert _row(preview.line)[0] == "BC-DJ-2026-009-2026_10_000"
    assert header[1] in ("提出日期", "提出时间")
    assert dict(preview.columns)[header[1]] == "2026-10-23 14:05（电话）"


def test_bc_refuses_when_text_follows_the_table(tmp_path: Path) -> None:
    """表后还有正文时拒写：追加到文件末尾的行会落在表外。表后只有空行或表格行照常。"""
    record = _template_record(tmp_path)
    record.write_text(record.read_text(encoding="utf-8") + "\n\n| BC-DJ-2026-101-2026_10_000 | x |\n", encoding="utf-8")
    assert len(actions.bc_preview(record, "DJ-2026-101", _form()).columns) == 11
    record.write_text(record.read_text(encoding="utf-8") + "\n## 备注\n别的内容\n", encoding="utf-8")
    with pytest.raises(actions.BcError, match="落在表外"):
        actions.bc_preview(record, "DJ-2026-101", _form())


def test_bc_form_must_be_filled_for_real(tmp_path: Path) -> None:
    record = _template_record(tmp_path)
    bad = {
        "raised": ("2026-10-23", "写到分钟"), "channel": ("飞鸽", "渠道"), "kind": ("其他", "类型"),
        "who": ("", "提出人"), "what": ("（填改了什么）", "占位字"), "why": ("  ", "为什么"),
        "impact": ("", "影响"),
    }
    for field_name, (value, message) in bad.items():
        with pytest.raises(actions.BcError, match=message):
            actions.bc_preview(record, "DJ-2026-009", _form(**{field_name: value}))
    with pytest.raises(actions.BcError, match="真实日期"):
        actions.bc_preview(record, "DJ-2026-009", _form(raised="2026-02-30 10:00"))
    assert actions.bc_preview(record, "DJ-2026-009", _form(impact="无")).line  # 影响“无”是合法的
    short = tmp_path / "short.md"
    short.write_text("| 编号 | 提出日期 | 类型 | 改了什么 | 状态 |\n|---|---|---|---|---|\n", encoding="utf-8")
    with pytest.raises(actions.BcError, match="表头认不出"):  # 旧的 5 栏表：拒绝，不猜
        actions.bc_preview(short, "DJ-2026-009", _form())


def test_bc_next_id_and_append_only(tmp_path: Path) -> None:
    record = _template_record(tmp_path)
    with record.open("a", encoding="utf-8") as stream:
        stream.write("| BC-DJ-2026-009-2026_10_005 | 2026-10-21 09:00（当面） | 李工 | 需求 | 三格 | 甲 | 无 | | | 待批 | |\n")
        stream.write("| BC-DJ-2026-009-2026_10_002 | 2026-10-21 10:00（当面） | 李工 | 需求 | 补登 | 乙 | 无 | | | 待批 | |\n")
        stream.write("| BC-DJ-2026-011-2026_10_009 | 2026-10-21 10:00（当面） | 别的项目 | 需求 | x | y | 无 | | | 待批 | |\n")
    october = datetime(2026, 10, 22, tzinfo=OFFSET)
    assert actions.bc_next_id(record, "DJ-2026-009", october) == "BC-DJ-2026-009-2026_10_006"  # 取本项目本月最大号 +1
    november = datetime(2026, 11, 3, tzinfo=OFFSET)
    assert actions.bc_next_id(record, "DJ-2026-009", november) == "BC-DJ-2026-009-2026_11_000"  # 跨月从 000 起
    preview = actions.bc_preview(record, "DJ-2026-009", _form(raised="2026-11-03 08:30"))
    assert preview.line.startswith("| BC-DJ-2026-009-2026_11_000 |")  # 年月跟“提出时间”走
    preview = actions.bc_preview(record, "DJ-2026-009", _form())
    line = preview.line
    assert line.startswith("| BC-DJ-2026-009-2026_10_006 |")
    before = record.read_bytes()
    receipt = actions.bc_append(record, line)
    after = record.read_bytes()
    assert after.startswith(before) and after[len(before):] == (line + "\n").encode("utf-8")
    assert receipt.rc == 0 and receipt.action == "写入 BC 行"
    assert actions.bc_next_id(record, "DJ-2026-009", october) == "BC-DJ-2026-009-2026_10_007"


def test_bc_append_refuses_when_the_file_changed_after_preview(tmp_path: Path) -> None:
    """预览后文件被别人改了（外部编辑器、连点两下）就拒写，不拿旧快照覆盖新内容（Codex 评审 #52）。"""
    record = _template_record(tmp_path)
    digest = actions.bc_digest(record)
    line = actions.bc_preview(record, "DJ-2026-009", _form()).line
    with record.open("a", encoding="utf-8") as stream:  # 预览后，别人在编辑器里加了一行
        stream.write("| BC-DJ-2026-009-2026_10_000 | 别人写的 | | | | | | | | | |\n")
    edited = record.read_bytes()
    receipt = actions.bc_append(record, line, digest)
    assert receipt.rc == 1 and "重新预览" in receipt.command
    assert record.read_bytes() == edited  # 别人那行还在，也没多写
    # 重新预览：编号顺延，写进去后原有内容一字不差
    digest = actions.bc_digest(record)
    line = actions.bc_preview(record, "DJ-2026-009", _form()).line
    assert line.startswith("| BC-DJ-2026-009-2026_10_001 |")
    assert actions.bc_append(record, line, digest).rc == 0
    assert record.read_bytes() == edited + (line + "\n").encode("utf-8")
    # 同一份预览再写一次（连点）也拒写
    assert actions.bc_append(record, line, digest).rc == 1
    assert record.read_bytes().count(line.encode("utf-8")) == 1


def test_probe_offline_on_timeout_and_run_check_receipt(tmp_path: Path) -> None:
    def timeout(*_args: Any, **_kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired("git", actions.PROBE_TIMEOUT)

    assert actions.probe_online(tmp_path, runner=timeout) is False
    calls: list[list[str]] = []

    def fake(command: Any, **_kwargs: Any) -> Any:
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, "Fail=1", "")

    receipt = actions.run_check(tmp_path, tmp_path / "manual", "DJ-2026-009", "docs_check", runner=fake)
    assert receipt.rc == 1 and receipt.rc_text == "rc 1" and "plc docs check" in receipt.command
    assert calls[0][-1] == "DJ-2026-009" and "-w" in calls[0]
    with pytest.raises(KeyError):
        actions.run_check(tmp_path, tmp_path, "X", "merge", runner=fake)  # 没有这种动作


def test_policy_never_list_is_not_in_station_buttons() -> None:
    lowered = {text.lower() for text in policy.STATION_BUTTONS}
    for word in ("合并", "删除", "切换发布", "no-verify", "codex", "全量门禁"):
        assert not any(word in text for text in lowered), word
    assert policy.GATED_UNTIL_WIRED <= policy.STATION_BUTTONS
    assert policy.PM_BUTTONS <= policy.STATION_BUTTONS


# ---------------------------------------------------------------- GitHub 门禁红进问题页“风险”档（试用 11-01：问题页全 0）


def _pull(number: int, projects: list[str], states: list[tuple[str, str]], *, draft: bool = False) -> Any:
    import github_collector as gh

    return gh.PullInfo(number, f"改 {number}", f"https://example.invalid/pull/{number}", "baiyangfu-hash", "a" * 40, "claude/x", draft,
                       "2026-10-31T09:00:00Z", projects=projects, ci=[gh.CiState(name, state, "") for name, state in states])


def _snapshot(pulls: list[Any], state: str = "ok", *, from_cache: bool = False) -> Any:
    import github_collector as gh

    return gh.Snapshot("o/r", state, NOW, NOW, from_cache=from_cache, pulls=pulls)


def _issue_board(tmp_path: Path) -> Any:
    return _board(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])


def test_a_red_pr_becomes_a_risk_issue_on_its_project_and_on_the_issues_page(tmp_path: Path) -> None:
    board = _issue_board(tmp_path)
    snapshot = _snapshot([
        _pull(470, ["DJ-2026-101"], [("sw008-ci", "fail"), ("plc-ci", "pass"), ("windows-cli", "fail")]),
        _pull(471, ["DJ-2026-101"], [("sw008-ci", "pass")]),
        _pull(472, ["DJ-2026-101"], [("sw008-ci", "running")]),
    ])
    home = vm.home_vm(board, OFFSET, online=True, use_git=False, github=snapshot)
    card = next(c for c in home.hot + home.rest if c.project_id == "DJ-2026-101")
    red = [i for i in card.issues if "门禁红" in i.title]
    assert [(i.sev, i.title) for i in red] == [("risk", "PR #470 门禁红")]  # 绿的、跑着的不报
    assert "sw008-ci" in red[0].detail and "windows-cli" in red[0].detail and "plc-ci" not in red[0].detail
    assert red[0].who and red[0].basis and red[0].since is not None
    assert red[0] in vm.all_issues(home)
    assert home.issue_notes == []  # 全读到了，没有“没检查”要说


def test_a_red_pr_that_touches_no_registered_project_still_reaches_the_issues_page(tmp_path: Path) -> None:
    board = _issue_board(tmp_path)
    snapshot = _snapshot([_pull(473, [], [("sw008-ci", "fail")], draft=True)])
    home = vm.home_vm(board, OFFSET, online=True, use_git=False, github=snapshot)
    assert [i.title for i in home.extra_issues] == ["PR #473 门禁红（草稿）"]
    assert home.extra_issues[0] in vm.all_issues(home)


def test_unread_github_never_looks_like_zero_red_prs(tmp_path: Path) -> None:
    """没读到（断网、限流、只有缓存、没开采集）不凭旧数据报警，但问题页必须说“没检查，条数不含它”。"""
    board = _issue_board(tmp_path)
    red = _pull(474, ["DJ-2026-101"], [("sw008-ci", "fail")])
    for snapshot in (_snapshot([red], "offline", from_cache=True), _snapshot([red], "rate_limited"), None):
        home = vm.home_vm(board, OFFSET, online=None, use_git=False, github=snapshot)
        assert not any("门禁红" in i.title for i in vm.all_issues(home))
        assert len(home.issue_notes) == 1 and "没检查" in home.issue_notes[0] and "不含" in home.issue_notes[0]


def test_a_pr_whose_checks_could_not_be_read_is_named_not_counted_as_green(tmp_path: Path) -> None:
    board = _issue_board(tmp_path)
    snapshot = _snapshot([_pull(475, ["DJ-2026-101"], [("sw008-ci", "unknown")]), _pull(476, ["DJ-2026-101"], [("sw008-ci", "pass")])], "partial")
    home = vm.home_vm(board, OFFSET, online=True, use_git=False, github=snapshot)
    assert not any("门禁红" in i.title for i in vm.all_issues(home))
    assert len(home.issue_notes) == 1 and "#475" in home.issue_notes[0] and "#476" not in home.issue_notes[0]


# ---------------------------------------------------------------- 等批准的范围卡、等确认的收件箱条目（CHG-SCPT-2026-639）


def _intake(store: Any, request_id: str, project: str, title: str) -> Any:
    from auto_pm.contracts.intake import Disposition, IntakeClassification, IntakeKind, TriageTicket

    ticket = TriageTicket(
        original_words=title, affects="x", duplicate_check="x", evidence=("file:README.md",),
        disposition=Disposition.INBOX_WAIT, rationale="x", alternatives=("x",), cost_risk="x",
    )
    item, _created = store.add_item(
        request_id=request_id, project_id=project, title=title,
        classification=IntakeClassification(kind=IntakeKind.BUG, domain="SCPT"), ticket=ticket, proposed_by="p",
    )
    return item


def _asks_env(tmp_path: Path) -> Any:
    """真账本：一张等批准的卡、一张改过两版的卡、一张已批准的卡、一条等确认和一条已确认的收件箱条目。"""
    from auto_pm.contracts.intake import IntakeStatus
    from auto_pm.infrastructure.intake_store import IntakeStore
    from tests.core import test_pm_pending_scope_card as cards

    env = cards._env(tmp_path)
    env.draft("REQ-ASK-001", objective="等批准的一张")
    env.submit("REQ-ASK-001")
    env.draft("REQ-ASK-002", objective="改过两版的一张")
    env.submit("REQ-ASK-002")
    env.submit("REQ-ASK-002", risks=("r2",))
    env.draft("REQ-ASK-003", objective="已批准的一张")
    env.approve("REQ-ASK-003", env.submit("REQ-ASK-003").card.plan_hash)
    intake = IntakeStore(env.root)
    _intake(intake, "REQ-IN-001", PROJECT_ID, "需求一")
    done = _intake(intake, "REQ-IN-002", PROJECT_ID, "需求二")
    intake.decide_item(
        done.item_id, status=IntakeStatus.CONFIRMED, ticket_hash=done.ticket_hash,
        decided_by="fubai", decision_ref="user-confirmation:test-639-01",
    )
    return env


def test_pending_asks_match_pm_pending_and_inbox_proposed(tmp_path: Path) -> None:
    """契约：看板读到的和 `pm pending`、`pm inbox list` 里 PROPOSED 的逐项一致；读完账本字节不变。"""
    from auto_pm.contracts.intake import IntakeStatus
    from auto_pm.infrastructure.intake_store import IntakeStore

    env = _asks_env(tmp_path)
    before = env.settled_sha()
    asks = pd.read_pending_asks_copy(env.db, env.root)
    assert env.settled_sha() == before

    pending = env.store.list_pending_planning_scope_cards(PROJECT_ID)
    scope = [a for a in asks if a.kind == "scope"]
    assert [(a.ref, a.revision) for a in scope] == [(p.card.request_id, p.revision) for p in pending]
    assert [a.ref for a in scope] == ["REQ-ASK-001", "REQ-ASK-002"] and scope[1].revision == 2
    proposed = IntakeStore(env.root).list_items(PROJECT_ID, (IntakeStatus.PROPOSED,))
    inbox = [a for a in asks if a.kind == "inbox"]
    assert [a.ref for a in inbox] == [i.item_id for i in proposed] and [a.subject for a in inbox] == ["需求一"]
    assert {a.project_id for a in asks} == {PROJECT_ID}
    assert all(a.since is not None for a in asks)


def test_pending_asks_reach_the_home_page_decisions(tmp_path: Path) -> None:

    env = _asks_env(tmp_path)
    board = pd.build_board(env.root, env.db, NOW, use_git=False, use_legacy=False)
    project = next(p for p in board.projects if p.project_id == PROJECT_ID)
    assert sorted(a.ref for a in project.asks if a.kind == "scope") == ["REQ-ASK-001", "REQ-ASK-002"]
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    card = next(c for c in [*home.hot, *home.rest] if c.project_id == PROJECT_ID)
    whys = {d.why: d for d in card.decisions}
    asked = [whys[w] for w in whys if w.startswith(("REQ-ASK-", "INBOX-"))]
    assert sorted(d.ask for d in asked) == ["批准范围", "批准范围", "核对需求"], list(whys)
    assert sum(d.why.endswith("需求一") for d in asked) == 1
    assert not any("REQ-ASK-003" in w or "需求二" in w for w in whys)
    assert all(d.reply and d.basis and d.since is not None for d in asked)
    # 首页“要你出手”的总数算上它们（首页只摆前 pd.MAX_DECISIONS 件）
    assert home.decisions_total >= len(asked) + 1


def test_pending_asks_of_an_unregistered_project_are_not_dropped(tmp_path: Path) -> None:
    from tests.core import test_pm_pending_scope_card as cards

    env = _asks_env(tmp_path)
    cards._add_project(env.root, "SW-OTHER-639")
    env.draft("REQ-ASK-OTHER", project="SW-OTHER-639", objective="别的项目的一张")
    env.submit("REQ-ASK-OTHER")
    registry = env.root / pd.REGISTRY_RELATIVE
    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["projects"] = [p for p in payload["projects"] if p["project_id"] != "SW-OTHER-639"]
    registry.write_text(json.dumps(payload), encoding="utf-8")
    board = pd.build_board(env.root, env.db, NOW, use_git=False, use_legacy=False)
    other = next(p for p in board.projects if p.project_id == "SW-OTHER-639")
    assert [a.ref for a in other.asks] == ["REQ-ASK-OTHER"]


def test_pending_asks_without_the_tables_are_empty_and_create_nothing(tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [])
    before = {r[0] for r in sqlite3.connect(db).execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert pd.read_pending_asks_copy(db, root) == []
    after = {r[0] for r in sqlite3.connect(db).execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert before == after and "intake_items" not in after


# ---------------------------------------------------------------- 批 1 看板说真话（CHG-SCPT-2026-644）


def _edited_board(tmp_path: Path, missions: list[tuple[str, str, str, float]], *sql: str) -> Any:
    """照 _board 造账本，再按给的 SQL 改几处（去掉工作项、取消 Run、加收口记录等），然后读成看板。"""
    root, db = base._workspace(tmp_path, missions)
    connection = sqlite3.connect(db)
    for statement in sql:
        connection.execute(statement)
    connection.commit()
    connection.close()
    return pd.build_board(root, db, NOW, use_git=False, use_legacy=False)


def _card(home: Any, project_id: str = "DJ-2026-101") -> Any:
    return next(c for c in home.hot + home.rest if c.project_id == project_id)


FIELD_NAMES = ("mission.state", "execution_leases", "checkpoints", "mission_items", "planning_scope_cards",
               "intake_items", "updated_at", "snapshot()")


def test_b1_09_issue_basis_is_plain_language_without_ledger_field_names(tmp_path: Path) -> None:
    """D-326（TD-SW008-591）：依据一栏写白话，不出现账本字段名。"""
    board = _board(
        tmp_path,
        [
            ("DJ-2026-101", "BLOCKED", "卡住了", 0.5),
            ("DJ-2026-101", "AWAITING_APPROVAL", "等批一", 4),
            ("DJ-2026-101", "ACCEPTANCE_PENDING", "等验收", 1),
            ("DJ-2026-101", "ACTIVE", "写通讯层", 0.2),
            ("DJ-2026-101", "PARKED", "搁很久", 9),
            *[("DJ-2026-101", "DRAFT", f"草稿{i}", 0.1) for i in range(5)],
        ],
    )
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    texts = [i.basis for c in home.hot + home.rest for i in c.issues] + [d.basis for d in home.decisions]
    assert len(texts) >= 6
    assert [t for t in texts if any(name in t for name in FIELD_NAMES)] == []


def test_b1_01_a_draft_without_work_is_not_waiting_for_you(tmp_path: Path) -> None:
    """D-328（TD-SW008-593）：没有工作项的草稿卡不进“等你超过 N 天”，也不算进“要你出手”。"""
    board = _edited_board(tmp_path, [("DJ-2026-101", "DRAFT", "没开起来的草稿", 6)],
                          "UPDATE mission_items SET root_work_id = NULL")
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    card = _card(home)
    assert not any(i.title.startswith("等你超过") for i in card.issues)
    draft = next(i for i in card.issues if "没有工作项" in i.title)
    assert draft.sev == "hint" and "草稿，没有工作项" in draft.title and not draft.who.startswith(vm.USER)
    assert not any("没开起来的草稿" in d.why for d in home.decisions)


def test_b1_02_a_draft_with_work_still_waits_for_you(tmp_path: Path) -> None:
    board = _board(tmp_path, [("DJ-2026-101", "DRAFT", "真等你的草稿", 6)])
    card = _card(vm.home_vm(board, OFFSET, online=None, use_git=False))
    assert any(i.title.startswith(f"等你超过 {pd.WAITING_RED_DAYS} 天") and i.sev == "block" for i in card.issues)
