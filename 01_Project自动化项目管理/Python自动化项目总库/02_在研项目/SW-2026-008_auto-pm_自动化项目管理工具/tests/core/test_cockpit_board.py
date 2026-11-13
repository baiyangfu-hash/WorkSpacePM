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
    assert titles["受阻，要拿主意"] == "block"
    # CHG-SCPT-2026-653：依据句里的状态词从词表取；回复句认得出“受阻”，不退成“看过了”；项目健康叫“挡路”
    blocked = next(i for i in card.issues if i.title == "受阻，要拿主意")
    assert blocked.basis == "账本里这张卡的状态是“受阻”" and pd.STATE_LABEL["BLOCKED"] == "受阻"
    assert vm._reply(blocked).endswith(" 拿主意：…")
    assert card.health_label == "挡路" and vm.SEV_LABEL["block"] == "阻塞"
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


def _with_approval(decision: str, expires_days: float) -> tuple[str, ...]:
    """给造出来的卡补授权（批准编号 DEC-B1-OK、到期时间）和一条批准记录（批准编号 decision）。"""
    expires = (NOW + timedelta(days=expires_days)).isoformat()
    return (
        "ALTER TABLE mission_items ADD COLUMN authority_json TEXT",
        f"UPDATE mission_items SET authority_json = '{{\"decision_id\": \"DEC-B1-OK\", \"expires_at\": \"{expires}\"}}'",
        "CREATE TABLE planning_draft_decision_bindings (request_id TEXT PRIMARY KEY, decision_id TEXT, change_id TEXT, "
        "plan_hash TEXT, approver TEXT, approval_evidence_ref TEXT, created_at TEXT)",
        f"INSERT INTO planning_draft_decision_bindings VALUES ('REQ-B1', '{decision}', 'CHG-B1', 'h', 'fubai', 'e', 'x')",
    )


def test_b1_01b_an_approved_draft_without_work_still_waits_for_you(tmp_path: Path) -> None:
    """D-328 审计裁定②：有有效批准记录、还没有工作项的草稿＝已批准、等开工，照常进“要你出手”、照常报“等你超过 N 天”。"""
    board = _edited_board(tmp_path, [("DJ-2026-101", "DRAFT", "批了还没开工", 6)],
                          "UPDATE mission_items SET root_work_id = NULL", "DELETE FROM execution_leases", *_with_approval("DEC-B1-OK", 20))
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    card = _card(home)
    assert [i.title for i in card.issues if "批了还没开工" in i.detail] == [
        f"等你超过 {pd.WAITING_RED_DAYS} 天：已批准，还没开工"
    ]
    assert any("批了还没开工" in d.why for d in home.decisions)


@pytest.mark.parametrize(("decision", "expires_days"), [("DEC-OTHER", 20), ("DEC-B1-OK", -1)])
def test_b1_01c_a_missing_or_expired_approval_counts_as_none(tmp_path: Path, decision: str, expires_days: float) -> None:
    board = _edited_board(tmp_path, [("DJ-2026-101", "DRAFT", "批准查不到或过期", 6)],
                          "UPDATE mission_items SET root_work_id = NULL", "DELETE FROM execution_leases", *_with_approval(decision, expires_days))
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    assert [i.title for i in _card(home).issues if "批准查不到或过期" in i.detail] == ["草稿，没有工作项，也没有批准记录"]
    assert not any("批准查不到或过期" in d.why for d in home.decisions)


def test_b1_02_a_draft_with_work_still_waits_for_you(tmp_path: Path) -> None:
    board = _board(tmp_path, [("DJ-2026-101", "DRAFT", "真等你的草稿", 6)])
    card = _card(vm.home_vm(board, OFFSET, online=None, use_git=False))
    assert any(i.title.startswith(f"等你超过 {pd.WAITING_RED_DAYS} 天") and i.sev == "block" for i in card.issues)


def test_b1_03_an_active_card_whose_work_and_run_are_cancelled_is_not_a_lost_executor(tmp_path: Path) -> None:
    """D-327（TD-SW008-592，看板侧）：ACTIVE 卡下面 Work、Run 都已取消、没有租约，不报执行者失联。"""
    board = _edited_board(
        tmp_path, [("DJ-2026-101", "ACTIVE", "早就停了的活", 3)],
        "UPDATE work_items SET state = 'CANCELLED'", "UPDATE run_items SET state = 'CANCELLED'",
        "DELETE FROM execution_leases",
    )
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    card = _card(home)
    assert not any(i.title == "执行者失联" for i in card.issues)
    assert next(k for k in home.checks if k.key == "lost").value == 0
    idle = next(i for i in card.issues if i.title == "卡开着，但下面没有在跑的执行")
    assert idle.who.startswith("主执行") and "已取消" in idle.detail


def test_b1_03b_cancelled_run_with_an_old_expired_lease_is_not_lost_either(tmp_path: Path) -> None:
    board = _edited_board(tmp_path, [("DJ-2026-101", "ACTIVE", "停了但租约还在", 3)],
                          "UPDATE run_items SET state = 'CANCELLED'")
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    assert next(k for k in home.checks if k.key == "lost").value == 0


def test_b1_04_a_running_run_with_an_expired_lease_is_still_lost(tmp_path: Path) -> None:
    board = _board(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 2 / 24)])
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    assert any(i.title == "执行者失联" for i in _card(home).issues)
    assert next(k for k in home.checks if k.key == "lost").value == 1


def test_b1_05_a_closed_project_keeps_its_leftovers_as_old_records_not_risk(tmp_path: Path) -> None:
    """D-324（TD-SW008-589）：项目下的卡全关了，账本一致性留下的两条算旧账：降成提示、项目标“旧账”，首页分开计，不隐藏。"""
    board = _edited_board(
        tmp_path,
        [("DJ-2026-101", "CLOSED", "早关了的一张", 20), ("DJ-2026-101", "CANCELLED", "作废的一张", 20)],
        "UPDATE work_items SET state = 'BLOCKED'",
    )
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    card = _card(home)
    old = [i for i in card.issues if i.title == "工作项受阻"]
    assert len(old) == 2 and {(i.sev, i.basis) for i in old} == {("hint", vm.OLD_BASIS)}
    assert (card.health, card.health_label, card.closed) == ("old", "旧账", True)
    mismatch = next(k for k in home.checks if k.key == "mismatch")
    assert (mismatch.value, mismatch.text, mismatch.soft) == (0, "在干 0，旧账 2", True)


def test_b1_06_an_open_project_with_a_blocked_work_item_is_still_at_risk(tmp_path: Path) -> None:
    board = _edited_board(
        tmp_path,
        [("DJ-2026-101", "ACTIVE", "在干的一张", 0.01), ("DJ-2026-101", "CLOSED", "早关了的一张", 20)],
        "UPDATE work_items SET state = 'BLOCKED' WHERE title = '早关了的一张'",
    )
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    card = _card(home)
    stuck = [i for i in card.issues if i.title == "工作项受阻"]
    assert [(i.sev, i.basis) for i in stuck] == [("risk", "账本一致性检查")]
    assert (card.health, card.closed) == ("risk", False)
    mismatch = next(k for k in home.checks if k.key == "mismatch")
    assert (mismatch.value, mismatch.text) == (1, "1 条")


def _closure(mission: str, state: str, days_ago: float) -> str:
    return (f"INSERT INTO closure_items VALUES ('CLOSURE-{mission}', '{mission}', 'CHG-B1-{mission}', '{state}', "
            f"'{(NOW - timedelta(days=days_ago)).isoformat()}')")


@pytest.mark.parametrize("with_open_card", [False, True])
def test_b1_07_a_closed_card_with_an_unfinished_closure_counts_in_one_cell_only(tmp_path: Path, with_open_card: bool) -> None:
    """D-329（TD-SW008-594）：已关的卡收口停在半路，只在“说完成但机器没过”计 1，“账本对不上”不重复计；两格说明互相指到。"""
    missions: list[tuple[str, str, str, float]] = [("DJ-2026-101", "CLOSED", "关了但收口没走完", 5)]
    if with_open_card:
        missions.append(("DJ-2026-101", "ACTIVE", "在干的一张", 0.01))
    board = _edited_board(tmp_path, missions, _closure("MISSION-0", "PREPARED", 5))
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    checks = {k.key: k for k in home.checks}
    assert (checks["unverified"].value, checks["mismatch"].value) == (1, 0)
    assert "说完成但机器没过" in checks["mismatch"].note and "账本对不上" in checks["unverified"].note
    # CHG-SCPT-2026-653：收口单号挪进 ref，说明句里不带
    titles = [i.title for i in _card(home).issues if i.ref == "CLOSURE-MISSION-0"]
    assert titles == ["说完成但机器没过"]
    assert not any("CLOSURE-MISSION-0" in i.detail for i in _card(home).issues)


def test_b1_08_cards_closed_the_old_way_are_not_counted_but_are_named_in_the_note(tmp_path: Path) -> None:
    """D-330（TD-SW008-595）：没有收口记录的已关卡不计数，说明里写明另有几张和依据；收口 COMPLETED 的不计也不提。"""
    board = _edited_board(
        tmp_path,
        [("DJ-2026-101", "CLOSED", "旧办法关的", 30), ("DJ-2026-101", "CLOSED", "正常收口的", 30)],
        _closure("MISSION-1", "COMPLETED", 30),
    )
    check = next(k for k in vm.home_vm(board, OFFSET, online=None, use_git=False).checks if k.key == "unverified")
    assert check.value == 0
    assert "另有 1 张按旧办法关闭、没有收口记录的卡，未计入" in check.note and "依据" in check.note


def test_b1_08b_no_old_way_cards_means_no_extra_note(tmp_path: Path) -> None:
    board = _edited_board(tmp_path, [("DJ-2026-101", "CLOSED", "正常收口的", 30)], _closure("MISSION-0", "COMPLETED", 30))
    check = next(k for k in vm.home_vm(board, OFFSET, online=None, use_git=False).checks if k.key == "unverified")
    assert check.value == 0 and "另有" not in check.note


# ---------------------------------------------------------------- D-342“要你出手”分页和首页同一口径（CHG-SCPT-2026-648）


def d342_board(tmp_path: Path) -> Any:
    """DJ-2026-101：一张已批准、还没开工的草稿（等你）＋一张没有工作项、也没有批准记录的草稿（不算）；
    SW-2026-008：一张有工作项的等批准卡（首页算，分页读 DJ-2026-101 时没读到这个项目）。"""
    return _edited_board(
        tmp_path,
        [("DJ-2026-101", "DRAFT", "批了还没开工", 6), ("DJ-2026-101", "DRAFT", "没批的草稿", 6),
         ("SW-2026-008", "AWAITING_APPROVAL", "别的项目等批", 2)],
        "UPDATE mission_items SET root_work_id = NULL WHERE subject_project_id = 'DJ-2026-101'",
        "DELETE FROM execution_leases", *_with_approval("DEC-B1-OK", 20),
        "UPDATE mission_items SET authority_json = NULL WHERE title = '没批的草稿'",
    )


def _loose(project_id: str = "github") -> Any:
    return vm.Decision("block", project_id, "PR #9 等你安全签字", "x", "安全签字 abc", "y", None)


def test_d342_counted_items_are_the_home_cards_decisions_per_project(tmp_path: Path) -> None:
    home = vm.home_vm(d342_board(tmp_path), OFFSET, online=None, use_git=False)
    home.loose_decisions.append(_loose())  # 归不到项目的 PR 签字（首页算进总数）
    home.decisions_total += 1
    count = vm.attention_count(home, ["DJ-2026-101", "DJ-2026-101", "XX-0000-000"])
    by_card = {c.project_id: c for c in home.hot + home.rest}
    assert [pid for pid, _items in count.per_project] == ["DJ-2026-101", "XX-0000-000"]  # 去重、照读的顺序；读了但首页没有的项目记 0
    counted = dict(count.per_project)
    assert list(counted["DJ-2026-101"]) == by_card["DJ-2026-101"].decisions  # 逐条一样
    assert counted["XX-0000-000"] == ()
    assert any("批了还没开工" in d.why for d in counted["DJ-2026-101"])
    assert not any("没批的草稿" in d.why for d in counted["DJ-2026-101"])  # 草稿首页和分页都不算
    assert count.unread == (("SW-2026-008", len(by_card["SW-2026-008"].decisions)),) and count.unread[0][1] >= 1
    assert count.loose == 1 and count.total == home.decisions_total
    assert count.counted + sum(n for _p, n in count.unread) + count.loose == home.decisions_total  # 首页总数＝三样之和


def test_d342_home_vm_keeps_pr_signatures_without_a_project(tmp_path: Path) -> None:
    """不属于看板上任何项目的 PR 签字单独记在 loose_decisions，首页总数＝各项目卡的件数＋它们。"""
    import github_collector as gh

    board = _board(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    mine = _pull(480, ["DJ-2026-101"], [])
    shared = _pull(481, [], [])
    snapshot = _snapshot([
        gh.PullInfo(**{**mine.__dict__, "safety": gh.Safety("waiting", "是", "等签")}),
        gh.PullInfo(**{**shared.__dict__, "safety": gh.Safety("waiting", "是", "等签")}),
    ])
    home = vm.home_vm(board, OFFSET, online=True, use_git=False, github=snapshot)
    assert [d.ask for d in home.loose_decisions] == ["PR #481 等你安全签字"]
    assert any(d.ask == "PR #480 等你安全签字" for d in _card(home).decisions)
    assert home.decisions_total == sum(len(c.decisions) for c in home.hot + home.rest) + len(home.loose_decisions)
    count = vm.attention_count(home, ["DJ-2026-101"])
    assert count.loose == 1 and count.counted + sum(n for _p, n in count.unread) + count.loose == home.decisions_total


# ---------------------------------------------------------------- CHG-SCPT-2026-650：已归档折叠、性质状态上卡


def test_an_archived_project_is_folded_last_and_cards_carry_kind_and_status(tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "BLOCKED", "卡住了", 0.5)])
    registry = root / pd.REGISTRY_RELATIVE
    data = json.loads(registry.read_text(encoding="utf-8"))
    data["projects"][0].update({"kind": "equipment", "status": "archived"})
    registry.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    board = pd.build_board(root, db, NOW, use_git=False, use_legacy=False)
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)

    assert all(c.project_id != "DJ-2026-101" for c in home.hot)  # 受阻也不进“要留意的项目”
    assert home.rest[-1].project_id == "DJ-2026-101" and home.rest[-1].archived
    card = home.rest[-1]
    assert (card.kind_label, card.status_label) == ("设备", "已归档")
    tool = next(c for c in home.hot + home.rest if c.project_id == "SW-2026-008")
    assert (tool.kind_label, tool.status_label, tool.tool) == ("工具", "在研", True)
    other = next(c for c in home.hot + home.rest if c.project_id == "DJ-2026-102")
    assert (other.kind_label, other.status_label) == ("未登记", "未登记")
    assert len(home.hot) + len(home.rest) == len(board.projects)  # 件数口径不变


def test_the_station_default_prefers_equipment_then_unclassified(tmp_path: Path) -> None:
    from cockpit_board.app import default_station_project

    root, _db = base._workspace(tmp_path, [])
    assert default_station_project(root) == "DJ-2026-101"  # 未分类、在研，退回用它
    registry = root / pd.REGISTRY_RELATIVE
    data = json.loads(registry.read_text(encoding="utf-8"))
    data["projects"][0]["status"] = "archived"
    data["projects"].append({"project_id": "DJ-2026-103", "project_root": "x/DJ-2026-103_丙", "kind": "library"})
    registry.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert default_station_project(root) == ""  # 已归档、公共库、工具都不当默认
    data["projects"].append({"project_id": "DJ-2026-104", "project_root": "x/DJ-2026-104_丁", "kind": "equipment"})
    registry.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert default_station_project(root) == "DJ-2026-104"


# ---------------------------------------------------------------- CHG-SCPT-2026-653 词表与显示清理

STATE_CODE = re.compile(r"\b(RUNNING|CANCELLED|PREPARED|COMPLETED|BLOCKED|VERIFYING|SUCCEEDED|PENDING|FAILED)\b")
INTERNAL_ID = re.compile(r"\b(RUN|CLOSURE|WORK)-")


def _653_board(tmp_path: Path) -> Any:
    """一张卡开着但执行已取消（MISSION-0 / RUN-0）、一张已关但收口停在半路、一张开着且收口停在半路、一个受阻的工作项（WORK-3）。"""
    return _edited_board(
        tmp_path,
        [
            ("DJ-2026-101", "ACTIVE", "执行早取消了的活", 3),
            ("DJ-2026-101", "CLOSED", "关了但收口没走完", 5),
            ("DJ-2026-101", "ACTIVE", "开着且收口停在半路", 2),
            ("DJ-2026-101", "ACTIVE", "工作项受阻的活", 0.01),
        ],
        "UPDATE run_items SET state = 'CANCELLED' WHERE run_id = 'RUN-0'",
        "DELETE FROM execution_leases WHERE run_id = 'RUN-0'",
        "UPDATE work_items SET state = 'BLOCKED' WHERE work_id = 'WORK-3'",
        _closure("MISSION-1", "PREPARED", 5),
        _closure("MISSION-2", "PREPARED", 3),
    )


def test_653_issue_details_carry_no_state_codes_or_internal_ids(tmp_path: Path) -> None:
    """D-356：说明句里没有全大写状态码，也没有 RUN-、CLOSURE-、工作项号；编号在 ref 一栏。"""
    board = _653_board(tmp_path)
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    issues = {i.title: i for i in _card(home).issues}
    idle = issues["卡开着，但下面没有在跑的执行"]
    assert idle.detail.startswith("最近一次执行的状态是“已取消”：") and idle.ref == "RUN-0"
    assert issues["说完成但机器没过"].ref == "CLOSURE-MISSION-1" and "备好了，没走完" in issues["说完成但机器没过"].detail
    assert issues["账本对不上"].ref == "CLOSURE-MISSION-2" and "CHG-B1-MISSION-2" in issues["账本对不上"].detail
    assert (issues["工作项受阻"].ref, issues["工作项受阻"].detail) == ("WORK-3", "工作项受阻的活")
    for issue in _card(home).issues:
        assert not STATE_CODE.search(issue.detail) and not INTERNAL_ID.search(issue.detail), issue.detail
    # 账本遗留那一层（HTML 看板和问题页共用的数据）同样：编号在 ref
    for item in next(p for p in board.projects if p.project_id == "DJ-2026-101").attention:
        assert item.ref and item.ref not in item.detail and not STATE_CODE.search(item.detail), item.detail


def test_653_an_overdue_run_record_says_its_state_in_chinese_and_keeps_the_id_in_ref(tmp_path: Path) -> None:
    board = _board(tmp_path, [("DJ-2026-101", "ACTIVE", "租约过期两天的活", 2.5)])
    item = next(a for p in board.projects for a in p.attention if a.what == "执行记录没结账")
    assert item.ref == "RUN-0" and item.detail == "Trae，状态“运行中”：租约过期两天的活"


def test_653_html_board_shows_no_state_codes(tmp_path: Path) -> None:
    board = _653_board(tmp_path)
    page = pd.render_page(board, timezone.utc)
    text = re.sub(r"<(script|style)\b.*?</\1>", "", page, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    assert not STATE_CODE.search(text), STATE_CODE.search(text)
    assert "编号：CLOSURE-MISSION-2" in text and "编号：WORK-3" in text  # 编号另起一行，不靠鼠标悬停
    card = pd._dev_card(next(m for p in board.projects for m in p.missions if m.title == "开着且收口停在半路"), NOW, timezone.utc)
    assert "· 运行中 ·" in card and "收口 备好了，没走完" in card
    no_closure = next(m for p in board.projects for m in p.missions if m.title == "工作项受阻的活")
    no_closure.change_id = "CHG-X-1"
    assert "收口 未开始" in pd._dev_card(no_closure, NOW, timezone.utc)


def test_653_project_page_closure_rows_show_words_and_keep_the_raw_status(tmp_path: Path) -> None:
    board = _653_board(tmp_path)
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    project = vm.project_vm(board, _card(home), OFFSET, False)
    closures = [row for row in project.changes if row.kind == "收口"]
    assert {row.status for row in closures} == {"PREPARED"}  # 原值不动：排序、判定都按它
    assert {vm.change_status_text(row) for row in closures} == {"备好了，没走完"}
    assert vm.change_status_text(vm.ChangeRow("CHG-1", "", "收口", "x", "COMPLETED")) == "已走完"
    assert vm.change_status_text(vm.ChangeRow("CHG-1", "", "收口", "x", "")) == ""
    assert vm.change_status_text(vm.ChangeRow("BC-1", "", "参数", "x", "COMPLETED")) == "COMPLETED"  # 别的类型的状态栏不动
    evidence = {row.title: row.detail for row in project.evidence}
    assert evidence["质量回执"] == "已关的卡收口单是否已走完（账本路线）"
    unverified = next(k for k in home.checks if k.key == "unverified")
    assert "是否已走完" in unverified.note and not STATE_CODE.search(unverified.note)


def _luminance(color: str) -> float:
    parts = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    red, green, blue = (p / 12.92 if p <= 0.03928 else ((p + 0.055) / 1.055) ** 2.4 for p in parts)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _contrast(first: str, second: str) -> float:
    high, low = sorted((_luminance(first), _luminance(second)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize("tokens", [theme.LIGHT, theme.DARK], ids=["light", "dark"])
@pytest.mark.parametrize("ground", ["bg", "card", "card2", "side"])
def test_653_small_grey_text_is_readable_on_every_ground(tokens: theme.Tokens, ground: str) -> None:
    """D-358：灰字 fg3 在页面底、卡片、次级底、侧栏四种底上的对比度都不低于 4.5（WCAG AA）。"""
    assert _contrast(tokens.fg3, getattr(tokens, ground)) >= 4.5


def test_653_contrast_formula_is_the_wcag_one() -> None:
    assert round(_contrast("#000000", "#ffffff"), 1) == 21.0 and _contrast("#777777", "#777777") == 1.0
    assert _contrast("#8b93a0", theme.LIGHT.side) < 4.5  # 旧的浅色灰字在侧栏上不够，这条测试拦得住


# ---------------------------------------------------------------- 首页按方案丙重做（CHG-SCPT-2026-655）：owner、工位条、四个数、焦点事项


def _mission(state: str, mission_id: str = "M-1", closure: str = "", **extra: Any) -> Any:
    return pd.MissionInfo(mission_id, "DJ-2026-101", "一张卡", state, NOW - timedelta(days=1), closure_state=closure, **extra)


def _issue(owner: str, mission_id: str = "M-1", title: str = "批准范围") -> Any:
    return vm.Issue("hint", "DJ-2026-101", title, "一张卡", "谁", "依据", NOW - timedelta(days=2), owner=owner, mission_id=mission_id)


STRIP_TABLE = [  # 账本状态, 收口记录 → 当前格（1 起）, 当前格的字
    ("DRAFT", "", 1, "草稿"),
    ("AWAITING_APPROVAL", "", 2, "等批准"),
    ("ACTIVE", "", 3, "进行中"),
    ("BLOCKED", "", 3, "受阻"),
    ("PARKED", "", 3, "搁着"),
    ("ACCEPTANCE_PENDING", "", 4, "等验收"),
    ("ACCEPTED", "", 5, "已验收，等收口"),
    ("CLOSED", "PREPARED", 6, "收口没走完"),
]


@pytest.mark.parametrize(("state", "closure", "at", "text"), STRIP_TABLE)
def test_655_strip_position_and_word_follow_the_ledger_state_only(state: str, closure: str, at: int, text: str) -> None:
    """验收 2：位置表每一行各造一张卡，当前格的位置、字和“✓”的格数逐个对；格名取 STATE_LABEL。"""
    strip = vm.strip_of(_mission(state, closure=closure), [])
    assert strip is not None
    assert (strip.current, strip.text, strip.done) == (at, text, at - 1)
    assert strip.cells == ("草稿", "等批准", "进行中", "等验收", "已验收", "已关闭")
    assert strip.cells == tuple(pd.STATE_LABEL[s] for s in vm.STRIP_STATES)
    # 位置不看问题：名下有问题时位置和字不变
    for owner in (vm.OWNER_USER, vm.OWNER_LEAD):
        again = vm.strip_of(_mission(state, closure=closure), [_issue(owner)])
        assert again is not None and (again.current, again.text) == (at, text)


@pytest.mark.parametrize(("state", "closure"), [("CLOSED", "COMPLETED"), ("CLOSED", ""), ("CANCELLED", "")])
def test_655_closed_cards_without_an_unfinished_closure_stay_off_the_home_page(state: str, closure: str) -> None:
    """收口走完的、没有收口记录的（D-330 的老卡）、已取消的卡不进首页。"""
    assert vm.strip_of(_mission(state, closure=closure), [_issue(vm.OWNER_USER)]) is None
    assert vm.card_row(_mission(state, closure=closure), [], NOW) is None


def test_655_strip_colour_and_shape_follow_the_issues_of_this_card_only() -> None:
    """验收 2：颜色表三行各造一张；别的卡名下的问题不算数；user 和 lead 都有时按 user。"""
    mission = _mission("AWAITING_APPROVAL")
    red = vm.strip_of(mission, [_issue(vm.OWNER_USER)])
    yellow = vm.strip_of(mission, [_issue(vm.OWNER_LEAD)])
    plain = vm.strip_of(mission, [])
    assert red is not None and yellow is not None and plain is not None
    assert (red.sev, red.shape) == ("block", "■")
    assert (yellow.sev, yellow.shape) == ("risk", "●")
    assert (plain.sev, plain.shape) == ("", "")
    other = vm.strip_of(mission, [_issue(vm.OWNER_USER, mission_id="M-2"), _issue(vm.OWNER_USER, mission_id="")])
    assert other is not None and other.sev == ""
    both = vm.strip_of(mission, [_issue(vm.OWNER_LEAD), _issue(vm.OWNER_USER)])
    assert both is not None and both.sev == "block"
    nobody = vm.strip_of(mission, [_issue("")])
    assert nobody is not None and nobody.sev == ""
    # 两行例外：收口没走完固定黄底圆点（问题不带卡号）；已验收等收口不标色
    unfinished = vm.strip_of(_mission("CLOSED", closure="PREPARED"), [])
    accepted = vm.strip_of(_mission("ACCEPTED"), [])
    assert unfinished is not None and (unfinished.sev, unfinished.shape) == ("risk", "●")
    assert accepted is not None and (accepted.sev, accepted.shape) == ("", "")


def test_655_card_row_right_text() -> None:
    red = vm.card_row(_mission("AWAITING_APPROVAL"), [_issue(vm.OWNER_USER)], NOW)
    late = vm.card_row(_mission("AWAITING_APPROVAL"), [_issue(vm.OWNER_USER, title="等你超过 3 天：批准范围")], NOW)
    yellow = vm.card_row(_mission("ACTIVE"), [_issue(vm.OWNER_LEAD, title="执行者失联")], NOW)
    assert red is not None and red.right == "等你：批准范围 · 等了 2 天"
    assert late is not None and late.right == "等你超过 3 天：批准范围 · 等了 2 天"
    assert yellow is not None and yellow.right == "主执行：执行者失联"
    run = pd.RunInfo("RUN-1", "RUNNING", "Trae", NOW + timedelta(hours=1), "", "wt", NOW)
    running = vm.card_row(_mission("ACTIVE", run=run), [], NOW)
    stopped = vm.card_row(_mission("ACTIVE", run=pd.RunInfo("RUN-1", "CANCELLED", "Trae", None, "", "wt", NOW)), [], NOW)
    assert running is not None and running.right == "Trae"
    assert stopped is not None and stopped.right == ""
    accepted = vm.card_row(_mission("ACCEPTED"), [], NOW)
    unfinished = vm.card_row(_mission("CLOSED", closure="PREPARED"), [], NOW)
    assert accepted is not None and accepted.right == "「决定」页有“收口”按钮"
    assert unfinished is not None and unfinished.right == "主执行对账"


def test_655_closure_unfinished_is_the_same_condition_as_the_unverified_check(tmp_path: Path) -> None:
    """“收口没走完”那一行和“说完成但机器没过”那一格共用一个条件。"""
    board = _edited_board(
        tmp_path,
        [("DJ-2026-101", "CLOSED", "收口没走完的", 5), ("DJ-2026-101", "CLOSED", "正常收口的", 5),
         ("DJ-2026-101", "CLOSED", "旧办法关的", 5), ("DJ-2026-101", "ACTIVE", "在干的一张", 0.005)],
        _closure("MISSION-0", "PREPARED", 5), _closure("MISSION-1", "COMPLETED", 5),
    )
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    missions = [m for p in board.projects for m in p.missions]
    assert [m.title for m in missions if vm.closure_unfinished(m)] == ["收口没走完的"]
    assert next(k for k in home.checks if k.key == "unverified").value == 1
    group = next(g for g in home.groups if g.project_id == "DJ-2026-101")
    assert [(r.title, r.strip.text) for r in group.cards] == [("收口没走完的", "收口没走完"), ("在干的一张", "进行中")]
    assert group.open_count == 1  # “开着 N 张卡”只数开着的；跟着列出的已关卡不算


OWNER_TABLE = {  # 第 1.1 节那张表：(问题标题, owner, 带不带卡号)
    ("受阻，要拿主意", "user", True),
    ("草稿，没有工作项，也没有批准记录", "lead", True),
    ("等你超过 3 天：批准范围", "user", True),  # 等你一栏，超过 3 天
    ("等你超过 3 天：验收结果", "user", True),
    ("验收结果", "user", True),  # 等你一栏，没超过 3 天
    ("核对需求", "user", True),  # 有工作项的草稿
    ("卡开着，但下面没有在跑的执行", "lead", True),
    ("执行者失联", "lead", True),
    ("搁了超过 7 天", "user", True),
    ("开着的卡超过 8 张", "user", False),
    ("业务变更待批", "user", False),
    ("批准范围", "user", False),  # 范围卡
    ("核对需求", "user", False),  # 收件箱
    ("实施卡待批准派工", "user", False),
    ("14 天没动静", "user", False),
    ("账本遗留", "lead", False),
    ("账本对不上", "lead", False),
    ("说完成但机器没过", "lead", False),
    ("工作项受阻", "lead", False),
    ("PR #470 门禁红", "", False),
}


def _owner_board(tmp_path: Path) -> Any:
    """造数覆盖 owner 表每一行。账本能造的用账本造；范围卡、收件箱、实施卡、账本一致性那几条直接挂到读出来的项目上。"""
    board = _edited_board(
        tmp_path,
        [
            ("DJ-2026-101", "BLOCKED", "受阻的", 0.5),  # MISSION-0
            ("DJ-2026-101", "DRAFT", "没开起来的草稿", 6),  # MISSION-1：去掉工作项
            ("DJ-2026-101", "AWAITING_APPROVAL", "等批很久", 4),  # MISSION-2
            ("DJ-2026-101", "ACCEPTANCE_PENDING", "等验收的", 1),  # MISSION-3
            ("DJ-2026-101", "ACTIVE", "早就停了的活", 3),  # MISSION-4：执行取消
            ("DJ-2026-101", "ACTIVE", "失联的", 2 / 24),  # MISSION-5
            ("DJ-2026-101", "PARKED", "搁很久", 9),  # MISSION-6
            ("DJ-2026-101", "DRAFT", "草稿甲", 0.1),
            ("DJ-2026-101", "DRAFT", "草稿乙", 0.1),
            ("SW-2026-008", "ACCEPTANCE_PENDING", "很久没动的", 20),
        ],
        "UPDATE mission_items SET root_work_id = NULL WHERE mission_id = 'MISSION-1'",
        "UPDATE run_items SET state = 'CANCELLED' WHERE run_id = 'RUN-4'",
        "DELETE FROM execution_leases WHERE run_id = 'RUN-4'",
    )
    project = next(p for p in board.projects if p.project_id == "DJ-2026-101")
    project.asks += [
        pd.PendingAsk("DJ-2026-101", "scope", "REQ-1", "改节拍", NOW - timedelta(days=1), 1),
        pd.PendingAsk("DJ-2026-101", "inbox", "INBOX-1", "加一个传感器", NOW - timedelta(days=1)),
    ]
    project.cards.append(pd.CardInfo("CARD-DJ-2026-101-009", "换气缸", "待批准派工"))
    project.attention += [
        pd.Attention("DJ-2026-101", "执行记录没结账", NOW - timedelta(days=3), "一条执行没结账"),
        pd.Attention("DJ-2026-101", "收口停在半路", NOW - timedelta(days=3), "收口单停着", mission_state="ACTIVE"),
        pd.Attention("DJ-2026-101", "收口停在半路", NOW - timedelta(days=3), "卡关了收口没走完", mission_state="CLOSED"),
        pd.Attention("DJ-2026-101", "工作项受阻", NOW - timedelta(days=3), "一个工作项受阻"),
    ]
    return board


def _old_decisions_from(issues: list[Any]) -> list[Any]:
    """改之前的 decisions_from：按“谁来办”那句字是不是以“你”开头来挑（照抄 0f11b341 上的写法，对照用）。"""
    out = [(i.sev, i.project_id, i.title, i.detail, vm._reply(i), i.basis, i.since, i.example) for i in issues if i.who.startswith(vm.USER)]
    far = datetime.max.replace(tzinfo=UTC)
    return sorted(out, key=lambda d: (-vm.SEV_RANK[d[0]], d[6] or far))


def test_655_owner_table_row_by_row_and_decisions_are_the_same_as_before(tmp_path: Path) -> None:
    """验收 4：表里每一行造一条；owner == user 和“那句字以‘你’开头”逐条相同；decisions_from 的结果和改之前一样。"""
    board = _owner_board(tmp_path)
    snapshot = _snapshot([_pull(470, ["DJ-2026-101"], [("sw008-ci", "fail")])])
    home = vm.home_vm(board, OFFSET, online=True, use_git=False, github=snapshot)
    issues = vm.all_issues(home)
    seen = {(i.title, i.owner, bool(i.mission_id)) for i in issues}
    assert seen == OWNER_TABLE
    for issue in issues:
        assert (issue.owner == vm.OWNER_USER) == issue.who.startswith(vm.USER), issue.title
    for card in home.hot + home.rest:
        new = [(d.sev, d.project_id, d.ask, d.why, d.reply, d.basis, d.since, d.example) for d in vm.decisions_from(card.issues)]
        assert new == _old_decisions_from(card.issues)
    # 类别：对应卡的是 mission；范围卡、收件箱各归各；其余看板里没有能办的页
    kinds = {(d.ask, bool(d.mission_id)): d.kind for c in home.hot + home.rest for d in c.decisions}
    assert kinds[("受阻，要拿主意", True)] == kinds[("等你超过 3 天：批准范围", True)] == kinds[("搁了超过 7 天", True)] == "mission"
    assert kinds[("核对需求", True)] == "mission"
    assert (kinds[("批准范围", False)], kinds[("核对需求", False)]) == ("scope", "inbox")
    for ask in ("业务变更待批", "实施卡待批准派工", "开着的卡超过 8 张", "14 天没动静"):
        assert kinds[(ask, False)] == "other", ask
    assert {kind for (_ask, has_card), kind in kinds.items() if has_card} == {"mission"}


def test_655_red_cell_if_and_only_if_the_card_has_a_user_issue(tmp_path: Path) -> None:
    """验收 2 的不变式：一张卡是红格，当且仅当它名下有一条 owner == user 的问题；mission 类的焦点事项指的那张卡一定是红格。"""
    home = vm.home_vm(_owner_board(tmp_path), OFFSET, online=None, use_git=False)
    issues = vm.all_issues(home)
    user_cards = {i.mission_id for i in issues if i.owner == vm.OWNER_USER and i.mission_id}
    lead_cards = {i.mission_id for i in issues if i.owner == vm.OWNER_LEAD and i.mission_id}
    board = _owner_board(tmp_path / "again")
    rows = [row for p in board.projects for m in p.missions if (row := vm.card_row(m, issues, NOW)) is not None]
    assert len(rows) == 10 and user_cards and lead_cards
    shown = [row for group in home.groups for row in group.cards]
    assert shown and all(row in rows for row in shown)  # 首页列的就是这些行（每个项目最多 8 张）
    for row in rows:
        assert (row.strip.sev == "block") == (row.mission_id in user_cards), row.title
        assert (row.strip.sev == "risk") == (row.mission_id in lead_cards - user_cards), row.title
    assert {r.mission_id for r in rows if r.strip.sev == "block"} == user_cards
    by_title = {r.title: r.strip for r in rows}
    # 审计预核点的四处现状：有工作项的草稿红；没工作项没批准的草稿黄；失联黄；搁超过 7 天红
    assert (by_title["草稿甲"].sev, by_title["没开起来的草稿"].sev, by_title["失联的"].sev, by_title["搁很久"].sev) == (
        "block", "risk", "risk", "block")
    assert home.focus is not None and home.focus.decision.kind == "mission"
    assert home.focus.decision.mission_id in {r.mission_id for r in shown if r.strip.sev == "block"}
    # 排序：每个项目里红格在前，其次黄格
    for group in home.groups:
        ranks = [{"block": 0, "risk": 1}.get(r.strip.sev, 2) for r in group.cards]
        assert ranks == sorted(ranks)


def test_655_parked_within_seven_days_has_no_colour(tmp_path: Path) -> None:
    home = vm.home_vm(_board(tmp_path, [("DJ-2026-101", "PARKED", "刚搁下", 2)]), OFFSET, online=None, use_git=False)
    row = home.groups[0].cards[0]
    assert (row.strip.current, row.strip.text, row.strip.sev, row.right) == (3, "搁着", "", "")


def _numbers(home: Any) -> dict[str, Any]:
    return {n.key: n for n in home.numbers}


def _numbers_board(tmp_path: Path) -> Any:
    """四个数各不为 0：101 有一张等你的（要你办）、一张真在跑的（AI 在干）、一张失联的（AI 那边要收拾）；008 全关了留一条旧账。"""
    return _edited_board(
        tmp_path,
        [("DJ-2026-101", "AWAITING_APPROVAL", "等批的", 1), ("DJ-2026-101", "ACTIVE", "真在跑的", 0.005),
         ("DJ-2026-101", "ACTIVE", "失联的", 2 / 24), ("SW-2026-008", "CLOSED", "早关了的", 20)],
        "UPDATE work_items SET state = 'BLOCKED' WHERE title = '早关了的'",
    )


def test_655_four_numbers_and_how_each_is_counted(tmp_path: Path) -> None:
    """验收 3（数据层）：四个数各不为 0，各按写明的口径数。"""
    home = vm.home_vm(_numbers_board(tmp_path), OFFSET, online=None, use_git=False)
    numbers = _numbers(home)
    issues = vm.all_issues(home)
    assert [n.key for n in home.numbers] == ["user", "running", "lead", "old"]
    assert [n.label for n in home.numbers] == ["要你办", "AI 在干", "AI 那边要收拾", "旧账"]
    assert numbers["user"].value == home.decisions_total == 2  # 等批的 + 那条待批的业务变更
    assert (numbers["running"].value, numbers["running"].cards) == (1, ("真在跑的",))  # 失联的那张名下有问题，不算在干
    assert numbers["lead"].value == sum(1 for i in issues if i.owner == vm.OWNER_LEAD and i.basis != vm.OLD_BASIS) == 1
    assert numbers["old"].value == sum(1 for i in issues if i.basis == vm.OLD_BASIS) == 2  # 工作项受阻、账本遗留各一条
    assert all(n.read and n.text == str(n.value) for n in home.numbers)
    assert home.decisions_without_issue == 0
    # 其余项目：008 没有开着的卡、留有旧账 1 条；102 没登记也没卡
    assert [(pid, old) for pid, _name, old in home.quiet] == [("DJ-2026-102", 0), ("SW-2026-008", 2)]


def test_655_running_card_of_an_archived_project_is_not_counted(tmp_path: Path) -> None:
    board = _numbers_board(tmp_path)
    next(p for p in board.projects if p.project_id == "DJ-2026-101").status = "archived"
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    assert _numbers(home)["running"].value == 0


def test_655_numbers_say_unchecked_when_the_ledger_was_not_read(tmp_path: Path) -> None:
    """验收 3、5：账本读不到时四个数写“没检查”，不写 0；焦点事项那一块也不能说“没有要你办的”。"""
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "AWAITING_APPROVAL", "等批的", 1)])
    db.unlink()
    for suffix in ("-wal", "-shm"):
        Path(str(db) + suffix).unlink(missing_ok=True)
    home = vm.home_vm(pd.build_board(root, db, NOW, use_git=False, use_legacy=False), OFFSET, online=None, use_git=False)
    assert home.ledger_ok is False
    assert [n.text for n in home.numbers] == ["没检查"] * 4
    assert all(not n.read for n in home.numbers)
    ok = vm.home_vm(_board(tmp_path / "ok", []), OFFSET, online=None, use_git=False)
    assert ok.ledger_ok is True and all(n.read for n in ok.numbers)


def test_655_pr_signature_counts_in_the_total_but_has_no_issue_row(tmp_path: Path) -> None:
    """验收 3：要你办 N ＝ 问题页归你办的 M 条 ＋ 问题页没有行的 K 件（PR 上等你签的）。"""
    import github_collector as gh

    pull = _pull(471, ["DJ-2026-101"], [("plc-ci", "pass")])
    pull.safety = gh.Safety("waiting", "是", "等签")
    home = vm.home_vm(_numbers_board(tmp_path), OFFSET, online=True, use_git=False, github=_snapshot([pull]))
    listed = sum(1 for i in vm.all_issues(home) if i.owner == vm.OWNER_USER)
    assert home.decisions_without_issue == 1
    assert listed + home.decisions_without_issue == home.decisions_total == _numbers(home)["user"].value == 3
    assert home.focus is not None and (home.focus.decision.kind, home.focus.page) == ("pr", "prs")


def test_655_focus_item_kinds_pages_and_plain_words(tmp_path: Path) -> None:
    """验收 5：焦点事项＝decisions[0]，接下来最多 2 条；mission 去决定页，范围卡、收件箱去要你出手页，other 没有能去的页。"""
    empty = vm.home_vm(_board(tmp_path / "empty", [("SW-2026-008", "ACTIVE", "真在跑的", 0.005)]), OFFSET, online=None, use_git=False)
    # 假工作空间里 101 自带一条待批的业务变更：只有它时焦点是 other 类
    assert empty.focus is not None and (empty.focus.decision.kind, empty.focus.page) == ("other", "")
    assert empty.focus.matter == "业务变更待批" and empty.focus.ask.startswith("回一句：")
    home = vm.home_vm(_owner_board(tmp_path / "full"), OFFSET, online=None, use_git=False)
    assert home.focus is not None and home.focus.decision == home.decisions[0]
    assert [f.decision for f in home.focus_next] == home.decisions[1:] and len(home.focus_next) == pd.MAX_DECISIONS - 1
    names = {c.project_id: c.name for c in home.hot + home.rest}
    assert home.focus.project_name == names[home.focus.decision.project_id] and names["DJ-2026-101"] == "甲"
    pages = {}
    for card in home.hot + home.rest:
        for decision in card.decisions:
            focus = vm.focus_of(decision, names)
            pages[(decision.ask, bool(decision.mission_id))] = focus.page
            assert focus.matter and focus.ask
    assert pages[("受阻，要拿主意", True)] == pages[("搁了超过 7 天", True)] == pages[("核对需求", True)] == "decisions"
    assert pages[("批准范围", False)] == pages[("核对需求", False)] == "attention"
    for ask in ("业务变更待批", "实施卡待批准派工", "开着的卡超过 8 张", "14 天没动静"):
        assert pages[(ask, False)] == "", ask
    blocked = vm.focus_of(next(d for c in home.hot for d in c.decisions if d.ask == "受阻，要拿主意"), names)
    assert (blocked.matter, blocked.ask) == ("一张卡受阻了", "怎么往下走")
    late = vm.focus_of(next(d for c in home.hot for d in c.decisions if d.ask == "等你超过 3 天：批准范围"), names)
    assert (late.matter, late.ask) == ("一张卡的范围等你点头", "范围认不认")


def test_655_no_decisions_means_no_focus(tmp_path: Path) -> None:
    board = _board(tmp_path, [])
    next(p for p in board.projects if p.project_id == "DJ-2026-101").changes.clear()
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    assert home.decisions_total == 0 and home.focus is None and home.focus_next == [] and home.ledger_ok


def test_655_approved_draft_without_work_shows_the_retire_command_and_change_id(tmp_path: Path) -> None:
    """“收掉”只能在终端办：折叠项里给完整命令（只显示）。有工作项的卡、别的状态不给。"""
    board = _edited_board(tmp_path, [("DJ-2026-101", "DRAFT", "批了还没开工", 6), ("DJ-2026-101", "ACCEPTANCE_PENDING", "等验收的", 5)],
                          "UPDATE mission_items SET root_work_id = NULL WHERE mission_id = 'MISSION-0'",
                          "DELETE FROM execution_leases", *_with_approval("DEC-B1-OK", 20))
    next(m for p in board.projects for m in p.missions if m.mission_id == "MISSION-0").change_id = "CHG-DOCU-2026-055"
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    by_card = {d.mission_id: d for c in home.hot + home.rest for d in c.decisions if d.mission_id}
    draft = by_card["MISSION-0"]
    assert draft.command == "main.py pm retire --pid DJ-2026-101 --mission-id MISSION-0"
    assert draft.change_id == "CHG-DOCU-2026-055"
    assert by_card["MISSION-1"].command == ""
    focus = vm.focus_of(draft, {})
    assert (focus.matter, focus.ask, focus.page) == ("一张卡批准了，还没开工", "开工，还是收掉这张卡", "decisions")
    assert "647" in vm.RETIRE_NOTE and "No such command" in vm.RETIRE_NOTE
    # 两个条件各自单独管用：草稿卡下面有工作项不给；没有工作项但不是草稿、等批准的也不给
    cards = {"M-1": _mission("DRAFT", "M-1"), "M-2": _mission("DRAFT", "M-2", work_id="WORK-9"),
             "M-3": _mission("ACTIVE", "M-3"), "M-4": _mission("AWAITING_APPROVAL", "M-4")}
    made = vm.decisions_from([_issue(vm.OWNER_USER, mission_id) for mission_id in cards], cards)
    assert {d.mission_id: bool(d.command) for d in made} == {"M-1": True, "M-2": False, "M-3": False, "M-4": True}


def test_655_archived_projects_stay_out_of_projects_and_cards(tmp_path: Path) -> None:
    """验收 7：已归档的项目不进“项目和卡”，也不进“其余 N 个项目”，只点数。"""
    board = _board(tmp_path, [("DJ-2026-101", "AWAITING_APPROVAL", "等批的", 1), ("SW-2026-008", "ACTIVE", "真在跑的", 0.005)])
    before = vm.home_vm(board, OFFSET, online=None, use_git=False)
    assert [g.project_id for g in before.groups] == ["DJ-2026-101", "SW-2026-008"] and before.archived_count == 0
    next(p for p in board.projects if p.project_id == "DJ-2026-101").status = "archived"
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    assert [g.project_id for g in home.groups] == ["SW-2026-008"]
    assert home.archived_count == 1 and "DJ-2026-101" not in [pid for pid, _name, _old in home.quiet]


def test_655_a_project_lists_at_most_eight_cards_and_counts_the_rest(tmp_path: Path) -> None:
    board = _board(tmp_path, [("DJ-2026-101", "DRAFT", f"草稿{i}", 0.1 + i / 100) for i in range(11)])
    group = vm.home_vm(board, OFFSET, online=None, use_git=False).groups[0]
    assert (len(group.cards), group.more, group.open_count) == (pd.OPEN_SOFT_LIMIT, 3, 11)


def test_655_accepted_card_is_listed_only_next_to_an_open_card(tmp_path: Path) -> None:
    alone = vm.home_vm(_board(tmp_path / "a", [("DJ-2026-101", "ACCEPTED", "验收过的", 1)]), OFFSET, online=None, use_git=False)
    assert alone.groups == []
    both = vm.home_vm(_board(tmp_path / "b", [("DJ-2026-101", "ACCEPTED", "验收过的", 1), ("DJ-2026-101", "ACTIVE", "在跑的", 0.005)]),
                      OFFSET, online=None, use_git=False)
    assert sorted((r.title, r.strip.current, r.strip.sev) for r in both.groups[0].cards) == [("在跑的", 3, ""), ("验收过的", 5, "")]
    assert both.groups[0].open_count == 1


def test_655_groups_put_red_projects_first_then_yellow(tmp_path: Path) -> None:
    board = _board(tmp_path, [("SW-2026-008", "AWAITING_APPROVAL", "等批的", 1), ("DJ-2026-101", "ACTIVE", "失联的", 2 / 24)])
    home = vm.home_vm(board, OFFSET, online=None, use_git=False)
    assert [(g.project_id, g.cards[0].strip.sev) for g in home.groups] == [("SW-2026-008", "block"), ("DJ-2026-101", "risk")]


def test_655_mismatch_note_uses_the_word_from_the_table(tmp_path: Path) -> None:
    home = vm.home_vm(_board(tmp_path, []), OFFSET, online=None, use_git=False)
    note = next(k for k in home.checks if k.key == "mismatch").note
    assert "工作项受阻" in note and "BLOCKED" not in note
