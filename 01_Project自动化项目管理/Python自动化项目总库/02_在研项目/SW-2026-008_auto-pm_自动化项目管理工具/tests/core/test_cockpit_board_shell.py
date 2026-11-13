"""驾驶舱总控屏的壳（CHG-SCPT-2026-628 骨架 A）：侧栏三组、页面注册表、路由、范围标记、占位卡、三态标签。

每页都能从侧栏进；侧栏按钮文字都在白名单里、不带禁用词；颜色只在 theme.py；
三态标签只有“没检查 / 断网未知 / 读不懂”三种字样，占位卡没有按钮。
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (  # noqa: E402
    QAbstractButton,
    QApplication,
    QLabel,
    QStackedWidget,
    QWidget,
)

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cockpit_board import policy, shell, theme, tool_policy  # noqa: E402
from cockpit_board.widgets import common as c  # noqa: E402

from tests.core import test_pm_dashboard as base  # noqa: E402 - 复用假工作空间
from tests.core import test_pm_dashboard_gui as gui_tests  # noqa: E402 - 复用窗口工厂


def test_pages_are_registered_once_in_known_groups() -> None:
    keys = [p.key for p in shell.PAGES]
    assert len(keys) == len(set(keys))
    assert shell.GROUPS == policy.SIDEBAR_GROUPS
    for page in shell.PAGES:
        assert page.group in shell.GROUPS, page
    # 每组至少一个侧栏按钮，组按 GROUPS 的顺序排
    for group in shell.GROUPS:
        assert any(p.group == group and p.nav for p in shell.PAGES), group
    with pytest.raises(KeyError):
        shell.spec("没有这页")


def test_sidebar_texts_are_whitelisted_and_clean() -> None:
    allowed = policy.PM_BUTTONS | tool_policy.NAV_BUTTONS
    for page in shell.PAGES:
        if not page.nav:
            continue
        assert page.text in allowed, page.text
        lowered = (page.text + page.tip).lower()
        assert not any(word in lowered for word in policy.NEVER), page.text


def test_sidebar_groups_buttons_in_order_and_lights_one(qapp: QApplication) -> None:
    bar = shell.Sidebar()
    labels = [w.text() for w in bar.findChildren(QLabel) if w.objectName() == "navgroup"]
    assert tuple(labels) == shell.GROUPS
    expected = [p.key for g in shell.GROUPS for p in shell.PAGES if p.group == g and p.nav]
    assert list(bar.buttons) == expected
    assert all(b.objectName() == "nav" and b.isCheckable() for b in bar.buttons.values())
    seen: list[str] = []
    bar.navigate.connect(seen.append)
    bar.buttons["flow"].click()
    assert seen == ["flow"]
    bar.select("issues")
    assert [k for k, b in bar.buttons.items() if b.isChecked()] == ["issues"]
    bar.select("project")  # 项目详情不在侧栏：全部熄灭
    assert not any(b.isChecked() for b in bar.buttons.values())


def test_router_refuses_unknown_and_duplicate_pages(qapp: QApplication) -> None:
    router = shell.Router(QStackedWidget())
    page = QWidget()
    router.register("home", page)
    with pytest.raises(KeyError):
        router.register("没有这页", QWidget())
    with pytest.raises(ValueError):
        router.register("home", QWidget())
    assert router.show("home") is page


def test_every_page_is_reachable_from_the_sidebar_with_its_scope(qapp: QApplication, tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    window = gui_tests._window(qapp, root, db)
    window._refresh_decisions = lambda: None  # 决定页读命令的接线在 test_pm_dashboard_gui 里测
    window._refresh_reads = lambda _key: None  # 骨架页读命令的接线在 test_cockpit_board_pages 里测
    assert window.page_buttons is window.sidebar.buttons
    for key, button in window.sidebar.buttons.items():
        button.click()
        qapp.processEvents()
        assert window.stack.currentWidget() is window.router.pages[key], key
        assert button.isChecked()
        assert window.scope.text() == shell.scope_text(key)
    # 工程工位模式下“今天”是工位页，范围标记写明
    window.set_mode("ws")
    assert window.stack.currentWidget() is window.station
    assert window.scope.text().endswith("工程工位")
    # 项目详情从别的页点进去：侧栏全灭，范围标记写“受管项目 · 项目详情”
    window.set_mode("pm")
    window.open_project("DJ-2026-101")
    assert window.stack.currentWidget() is window.project
    assert not any(b.isChecked() for b in window.sidebar.buttons.values())
    assert window.scope.text() == "受管项目 · 项目详情"
    # 顶栏不再放页面按钮
    topbar = next(w for w in window.findChildren(QWidget) if w.objectName() == "topbar")
    assert not [b for b in topbar.findChildren(QAbstractButton) if b.objectName() in ("tab", "nav")]
    window.close()


def test_state_tags_only_say_the_three_words(qapp: QApplication) -> None:
    assert set(c.STATES.values()) == set(policy.UNCHECKED_TEXTS)
    for state, text in c.STATES.items():
        tag = c.state_tag(state)
        assert tag.text() == text and tag.property("state") == state and tag.objectName() == "state"
        assert tag.text() != "0"
    with pytest.raises(ValueError):
        c.state_tag("ok")  # 读到了的数不用三态标签，写错直接报错


def test_placeholder_card_has_no_buttons_and_says_what_it_will_read(qapp: QApplication) -> None:
    card = c.placeholder("任务", "四栏看板下一批做", "main.py pm missions --pid <项目>")
    texts = [w.text() for w in card.findChildren(QLabel)]
    assert card.findChildren(QAbstractButton) == []
    assert card.property("dashed") == "true" and card.property("placeholder") == "true"
    assert "这一块还没做：四栏看板下一批做" in texts
    assert "以后读：main.py pm missions --pid <项目>" in texts


def test_read_block_shows_status_and_raw_text_truncated(qapp: QApplication) -> None:
    block = c.read_block("命令不存在：本机发布版太旧", "No such command 'orient'", state="unreadable")
    texts = [w.text() for w in block.findChildren(QLabel)]
    assert "读不懂" in texts and "No such command 'orient'" in texts
    long = c.read_block("读到了", "x" * (c.RAW_LIMIT + 10))
    raw = [w.text() for w in long.findChildren(QLabel) if w.objectName() == "mono"][0]
    assert raw.endswith("（截断，后面还有 10 字）")
    empty = c.read_block("读到了", "")
    assert "（没有输出）" in [w.text() for w in empty.findChildren(QLabel)]
    # 原文是纯文本：富文本不被解释
    rich = c.read_block("读到了", "<b>粗</b>")
    assert all(w.textFormat().name == "PlainText" for w in rich.findChildren(QLabel))


def test_tokens_v2_cover_sidebar_and_states_with_token_colors_only() -> None:
    for tokens in (theme.LIGHT, theme.DARK):
        qss = theme.build_qss(tokens)
        for selector in ("QFrame#sidebar", "QPushButton#nav", "QLabel#navgroup", "QLabel#scope", "QLabel#state"):
            assert selector in qss, selector
        for state in c.STATES:
            assert f'QLabel#state[state="{state}"]' in qss, state
        allowed = {getattr(tokens, name).lower() for name in theme.token_names()}
        assert {m.lower() for m in re.findall(r"#[0-9a-fA-F]{6}\b", qss)} <= allowed
    assert set(theme.STATE_SEV) == set(c.STATES)
    assert sorted(theme.FONT_LADDER_PT.values()) == sorted(set(theme.FONT_LADDER_PT.values()))  # 四级字号互不相同
    for path in (SCRIPTS / "cockpit_board").rglob("*.py"):
        if path.name != "theme.py":
            assert not re.search(r"#[0-9a-fA-F]{6}\b", path.read_text(encoding="utf-8")), path.name


def test_655_decisions_sits_right_below_today_in_the_sidebar(qapp: QApplication) -> None:
    """侧栏“决定”排到“今天”下面第一位；“今天”的说明讲的是新首页。"""
    daily = [p.text for p in shell.PAGES if p.group == "日常" and p.nav]
    assert daily == ["今天", "决定", "问题", "要你出手"]
    bar = shell.Sidebar()
    shown = [b.text() for b in bar.findChildren(QAbstractButton) if b.objectName() == "nav"]
    assert shown[:4] == daily
    tip = shell.spec("home").tip
    assert "最该你办的一件" in tip and "灯" in tip
    assert not any(word in tip.lower() for word in policy.PM_FORBIDDEN_WORDS)
