"""驾驶舱总控屏的纯 Python 层：视图模型、主题令牌、按钮规矩、本机动作。不需要 Qt。"""

from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.core import test_pm_dashboard as base

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cockpit_board import actions, policy, theme  # noqa: E402
from cockpit_board import viewmodel as vm

pd = base.pd
NOW = base.NOW
OFFSET = timezone(timedelta(hours=-7))


def _board(tmp_path: Path, missions: list[tuple[str, str, str, float]]) -> pd.Board:
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
    for text in policy.GATED_UNTIL_GAP9:
        assert buttons[text][0] is False and "缺口⑨" in buttons[text][1]
    assert buttons["提交"][0] is False
    assert buttons["重新跑 plc check"][0] is True
    # 在线 + ⑨已合：推送和批准开放，开工仍不启动 agent（只是按钮可用）
    station = vm.station_vm(board, home.hot + home.rest, True, {"source": "a", "effective": "a"}, "manual/x", [], True)
    buttons = {text: (enabled, reason) for step in station.steps for text, _k, enabled, reason in step.buttons}
    assert buttons["批准范围"][0] and buttons["开工"][0]
    # 推送 / 开 PR 本版没实现：在线也灰着，提示去命令提示符和网页做（Codex 评审 #52）
    for text in ("推送 manual/ 分支", "打开 GitHub 开 PR"):
        assert buttons[text][0] is False and "本版不做" in buttons[text][1]
    assert not station.warn
    # 只有登记的客户项目进“接着干”
    assert [p[0].project_id for p in station.projects] == ["DJ-2026-101"]


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


def _fields(**override: str) -> dict[str, str]:
    values = {"类型": "参数", "改了什么": "急停复位 → 加 2 s 延时", "为什么": "现场误动作", "影响": "OB1、FB_1001"}
    values.update({{"what": "改了什么", "why": "为什么", "impact": "影响", "kind": "类型"}[k]: v for k, v in override.items()})
    return values


# DJ-2026-009 真实的业务变更记录表头（0100_PLC自动化/DJ-2026-009_汇川换型改造/11_监控/01_变更管理/02_变更记录/）
DJ009_HEADER = (
    "| 编号 | 提出日期 | 提出人 | 类型 | 改了什么（原来 → 改成） | 为什么 | 影响 | 批准人 | 批准日期 | 状态 | 关联 CHG / 提交 |\n"
    "|---|---|---|---|---|---|---|---|---|---|---|\n"
)
DJ009_RECORD = (
    Path(__file__).resolve().parents[6] / "0100_PLC自动化" / "DJ-2026-009_汇川换型改造" / "11_监控" / "01_变更管理"
    / "02_变更记录" / "02_业务变更记录.md"
)


def _bc_row_matches_header(record: Path, line: str) -> dict[str, str]:
    header = actions.bc_header(record)
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    assert len(cells) == len(header) == 11  # 审计 95：表头 11 列，新行也必须 11 格
    return dict(zip(header, cells, strict=True))


@pytest.mark.parametrize("source", ["literal", "repo"])
def test_bc_row_fills_every_column_of_the_real_dj009_table(tmp_path: Path, source: str) -> None:
    """审计 95 的高：写进 11 列表的行只有 6 格、“改了什么”落进“类型”栏、内容是占位字、提出人写死、时间只到日期。"""
    record = tmp_path / "02_业务变更记录.md"
    if source == "repo":
        if not DJ009_RECORD.is_file():
            pytest.skip("仓库里没有 DJ-2026-009 的业务变更记录")
        record.write_bytes(DJ009_RECORD.read_bytes())
    else:
        record.write_text("# 业务变更记录\n\n" + DJ009_HEADER + "| BC-DJ-2026-009-001 | 待补 | 待补 | 硬件 | 甲 → 乙 | 国产化 | 全部程序 | 待补 | 待补 | 待补 | 待补 |\n",
                          encoding="utf-8")
    when = datetime(2026, 10, 23, 14, 5, tzinfo=OFFSET)
    line = actions.bc_preview(record, "DJ-2026-009", when, "张工", _fields())
    row = _bc_row_matches_header(record, line)
    assert row["编号"] == "BC-DJ-2026-009-2026_10_001"
    assert row["提出日期"] == "2026-10-23 14:05"  # 到分钟
    assert row["提出人"] == "张工"  # 从配置来，不是写死的 baiyang
    assert row["类型"] == "参数" and row["改了什么（原来 → 改成）"] == "急停复位 → 加 2 s 延时"
    assert row["为什么"] == "现场误动作" and row["影响"] == "OB1、FB_1001"
    assert row["状态"] == "待批 2026-10-23 14:05" and row["批准人"] == row["批准日期"] == "待补"
    before = record.read_bytes()
    assert actions.bc_append(record, line, actions.bc_digest(record)).rc == 0
    assert record.read_bytes() == before + (line + "\n").encode("utf-8")


@pytest.mark.parametrize(
    "override",
    [{"what": ""}, {"what": "（填改了什么）"}, {"impact": "（填影响）"}, {"why": "待补"}, {"kind": "  "}, {"impact": "TODO"}],
)
def test_bc_refuses_empty_or_placeholder_fields(tmp_path: Path, override: dict[str, str]) -> None:
    record = tmp_path / "02_业务变更记录.md"
    record.write_text(DJ009_HEADER, encoding="utf-8")
    with pytest.raises(actions.BcError, match="先填"):
        actions.bc_preview(record, "DJ-2026-009", datetime(2026, 10, 23, tzinfo=OFFSET), "张工", _fields(**override))


def test_bc_append_rechecks_columns_and_placeholders(tmp_path: Path) -> None:
    """就算绕过预览直接写，bc_append 也按表头再核一遍：格数不对、必填栏是占位字都拒写，文件不动。"""
    record = tmp_path / "02_业务变更记录.md"
    record.write_text(DJ009_HEADER, encoding="utf-8")
    before = record.read_bytes()
    six = "| BC-DJ-2026-009-2026_10_001 | 2026-10-23 现场 | baiyang | （填改了什么） | （填影响） | 待批 2026-10-23 |"
    receipt = actions.bc_append(record, six)  # 审计 95 复现的那一行
    assert receipt.rc == 1 and "6 格" in receipt.command and "11 格" in receipt.command
    placeholder = "| " + " | ".join(["BC-x", "t", "p", "需求", "（填改了什么）", "w", "i", "-", "-", "待批", "-"]) + " |"
    receipt = actions.bc_append(record, placeholder)
    assert receipt.rc == 1 and "改了什么" in receipt.command
    assert record.read_bytes() == before


def test_bc_refuses_without_operator_or_when_table_is_not_last(tmp_path: Path) -> None:
    record = tmp_path / "02_业务变更记录.md"
    record.write_text(DJ009_HEADER, encoding="utf-8")
    when = datetime(2026, 10, 23, tzinfo=OFFSET)
    with pytest.raises(actions.BcError, match="提出人没配置"):
        actions.bc_preview(record, "DJ-2026-009", when, "", _fields())
    record.write_text(DJ009_HEADER + "\n## 说明\n\n表后面还有字。\n", encoding="utf-8")
    with pytest.raises(actions.BcError, match="表外"):
        actions.bc_preview(record, "DJ-2026-009", when, "张工", _fields())
    record.write_text("没有表\n", encoding="utf-8")
    with pytest.raises(actions.BcError, match="表头"):
        actions.bc_preview(record, "DJ-2026-009", when, "张工", _fields())


def test_operator_name_comes_from_config(tmp_path: Path) -> None:
    def git(command, **_kw):  # noqa: ANN001, ANN202
        return subprocess.CompletedProcess(command, 0, "李工\n", "")

    assert actions.operator_name("王工", {actions.OPERATOR_ENV: "赵工"}, tmp_path, runner=git) == "王工"
    assert actions.operator_name("", {actions.OPERATOR_ENV: "赵工"}, tmp_path, runner=git) == "赵工"
    assert actions.operator_name("", {}, tmp_path, runner=git) == "李工"
    assert actions.operator_name("", {}, tmp_path / "没有", runner=git) == ""

    def broken(command, **_kw):  # noqa: ANN001, ANN202
        return subprocess.CompletedProcess(command, 1, "", "")

    assert actions.operator_name("", {}, tmp_path, runner=broken) == ""


def test_bc_next_id_and_append_only(tmp_path: Path) -> None:
    record = tmp_path / "02_业务变更记录.md"
    record.write_text(
        "| 编号 | 提出日期 | 类型 | 改了什么 | 状态 |\n|---|---|---|---|---|\n"
        "| BC-DJ-2026-009-2026_10_005 | 2026-10-21 | 需求 | 三格 | 待批 |\n",
        encoding="utf-8",
    )
    october = datetime(2026, 10, 22, tzinfo=OFFSET)
    assert actions.bc_next_id(record, "DJ-2026-009", october) == "BC-DJ-2026-009-2026_10_006"
    november = datetime(2026, 11, 3, tzinfo=OFFSET)
    assert actions.bc_next_id(record, "DJ-2026-009", november) == "BC-DJ-2026-009-2026_11_001"  # 跨月归零
    line = actions.bc_preview(record, "DJ-2026-009", october, "baiyang", _fields(what="改 | 了", impact="安全区，待签字"))
    assert line.startswith("| BC-DJ-2026-009-2026_10_006 |") and "｜" in line and "待批 2026-10-22 00:00" in line
    assert len(line.strip("|").split(" | ")) == 5  # 和这张 5 列表的表头一样多
    before = record.read_bytes()
    receipt = actions.bc_append(record, line)
    after = record.read_bytes()
    assert after.startswith(before) and after[len(before):] == (line + "\n").encode("utf-8")
    assert receipt.rc == 0 and receipt.action == "写入 BC 行"
    assert actions.bc_next_id(record, "DJ-2026-009", october) == "BC-DJ-2026-009-2026_10_007"


def test_bc_append_refuses_when_the_file_changed_after_preview(tmp_path: Path) -> None:
    """预览后文件被别人改了（外部编辑器、连点两下）就拒写，不拿旧快照覆盖新内容（Codex 评审 #52）。"""
    record = tmp_path / "02_业务变更记录.md"
    record.write_text("| 编号 | 改了什么 | 状态 |\n|---|---|---|\n", encoding="utf-8")
    when = datetime(2026, 10, 23, tzinfo=OFFSET)
    digest = actions.bc_digest(record)
    line = actions.bc_preview(record, "DJ-2026-009", when, "baiyang", _fields())
    with record.open("a", encoding="utf-8") as stream:  # 预览后，别人在编辑器里加了一行
        stream.write("| BC-DJ-2026-009-2026_10_001 | 别人写的 | 待批 |\n")
    edited = record.read_bytes()
    receipt = actions.bc_append(record, line, digest)
    assert receipt.rc == 1 and "重新预览" in receipt.command
    assert record.read_bytes() == edited  # 别人那行还在，也没多写
    # 重新预览：编号顺延，写进去后原有内容一字不差
    digest = actions.bc_digest(record)
    line = actions.bc_preview(record, "DJ-2026-009", when, "baiyang", _fields())
    assert line.startswith("| BC-DJ-2026-009-2026_10_002 |")
    assert actions.bc_append(record, line, digest).rc == 0
    assert record.read_bytes() == edited + (line + "\n").encode("utf-8")
    # 同一份预览再写一次（连点）也拒写
    assert actions.bc_append(record, line, digest).rc == 1
    assert record.read_bytes().count(line.encode("utf-8")) == 1


def test_probe_offline_on_timeout_and_run_check_receipt(tmp_path: Path) -> None:
    def timeout(*_args, **_kwargs):  # noqa: ANN002, ANN003, ANN202
        raise subprocess.TimeoutExpired("git", actions.PROBE_TIMEOUT)

    assert actions.probe_online(tmp_path, runner=timeout) is False
    calls: list[list[str]] = []

    def fake(command, **_kwargs):  # noqa: ANN001, ANN003, ANN202
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
    assert policy.GATED_UNTIL_GAP9 <= policy.STATION_BUTTONS
    assert policy.PM_BUTTONS <= policy.STATION_BUTTONS
