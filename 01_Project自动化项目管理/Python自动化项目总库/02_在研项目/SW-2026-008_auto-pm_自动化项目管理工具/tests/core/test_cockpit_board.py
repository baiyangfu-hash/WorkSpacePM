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
        assert keys["gate_red"] == "unchecked" and keys["scope"] == "unchecked"
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
    buttons = {text: enabled for step in station.steps for text, _k, enabled, _r in step.buttons}
    assert buttons["推送 manual/ 分支"] and buttons["批准范围"] and buttons["开工"]
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
    line = actions.bc_preview(record, "DJ-2026-009", october, "baiyang", "改 | 了", "安全区，待签字")
    assert line.startswith("| BC-DJ-2026-009-2026_10_006 |") and "｜" in line and "待批 2026-10-22" in line
    before = record.read_bytes()
    receipt = actions.bc_append(record, line)
    after = record.read_bytes()
    assert after.startswith(before) and after[len(before):] == (line + "\n").encode("utf-8")
    assert receipt.rc == 0 and receipt.action == "写入 BC 行"
    assert actions.bc_next_id(record, "DJ-2026-009", october) == "BC-DJ-2026-009-2026_10_007"


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
