"""驾驶舱总控屏的纯 Python 层：视图模型、主题令牌、按钮规矩、本机动作。不需要 Qt。"""

from __future__ import annotations

import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from tests.core import test_pm_dashboard as base

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


def _changes_of(board: Any) -> list[vm.ChangeRow]:
    home = vm.home_vm(board, OFFSET, online=False, use_git=False)
    card = next(c for c in home.hot + home.rest if c.project_id == "DJ-2026-101")
    return vm.project_vm(board, card, OFFSET, False).changes


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
