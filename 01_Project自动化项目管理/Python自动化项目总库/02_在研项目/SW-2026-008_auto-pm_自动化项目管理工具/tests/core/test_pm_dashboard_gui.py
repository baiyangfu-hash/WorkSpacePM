"""驾驶舱看板 v1 桌面界面 ``scripts/pm_dashboard_gui.py``：只读、窗口里只有“重新读取”一个按钮、
项目经理页签（灯、要你定最多 3 件、点开看变更）、开发页签五栏（含账本遗留）、双击 bat 不在 releases/ 里。
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (  # noqa: E402
    QAbstractButton,
    QAbstractSpinBox,
    QComboBox,
    QFrame,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QTabBar,
    QTextEdit,
)

from tests.core import test_pm_dashboard as base  # noqa: E402 - 复用原型测试的假工作空间

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "pm_dashboard_gui.py"
REPO_ROOT = Path(__file__).resolve().parents[6]
BAT = REPO_ROOT / "双击打开驾驶舱看板.bat"
NOW = base.NOW
FORBIDDEN_WORDS = ("codex", "执行", "开始", "开工", "合并", "删除", "切换", "批准", "同意", "退回")


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pm_dashboard_gui_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


gui = _load()


def _options(root: Path, db: Path, **extra: object) -> argparse.Namespace:
    options = gui.parse_options(
        ["--root", str(root), "--db", str(db), "--now", NOW.isoformat(), "--no-git"]
        + ["--no-legacy"] * (not extra.pop("legacy", False))
        + ["--utc-offset", "-7"]
    )
    for key, value in extra.items():
        setattr(options, key, value)
    return options


def _window(qapp, root: Path, db: Path, **extra: object):  # noqa: ANN001, ANN202
    options = _options(root, db, **extra)
    window = gui.DashboardWindow(options)
    window.show_board(gui.load_board(options, use_legacy=not options.no_legacy))
    qapp.processEvents()
    return window


def _texts(widget) -> list[str]:  # noqa: ANN001
    return [label.text() for label in widget.findChildren(QLabel)]


def _files(root: Path) -> dict[str, int]:
    return {str(path): path.stat().st_mtime_ns for path in root.rglob("*") if path.is_file()}


def test_window_has_only_the_refresh_button(qapp, tmp_path: Path) -> None:  # noqa: ANN001
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "AWAITING_APPROVAL", "待批准", 1)])
    window = _window(qapp, root, db, examples=True)
    buttons = [
        button
        for button in window.findChildren(QAbstractButton)
        if not isinstance(button.parent(), QTabBar)  # 页签条自带的左右翻页小箭头，没有文字
    ]
    assert {button.text() for button in buttons} == gui.ALLOWED_BUTTON_TEXTS
    for button in buttons:
        lowered = (button.text() + button.toolTip()).lower()
        assert not any(word in lowered for word in FORBIDDEN_WORDS), button.text()
    assert window.menuBar().actions() == []
    assert window.actions() == []
    for kind in (QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QAbstractSpinBox):
        assert window.findChildren(kind) == [], kind.__name__
    assert window.project_tree.editTriggers() == window.project_tree.EditTrigger.NoEditTriggers
    window.close()


def test_window_and_screenshot_never_write_the_workspace(qapp, tmp_path: Path) -> None:  # noqa: ANN001
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    before = _files(root)
    window = _window(qapp, root, db)
    window.close()
    shots = tmp_path / "shots"
    shots.mkdir()
    argv = ["--root", str(root), "--now", NOW.isoformat(), "--no-git", "--no-legacy"]
    assert gui.main([*argv, "--screenshot", str(shots / "看板.png")]) == 0
    assert _files(root) == before  # 账本哈希、修改时间都不变，旁边也不多出 -shm / -wal
    assert sorted(path.name for path in shots.iterdir()) == [
        "看板_开发人员.png",
        "看板_项目经理.png",
    ]


def test_pm_tab_lamps_and_at_most_three_decisions(qapp, tmp_path: Path) -> None:  # noqa: ANN001
    root, db = base._workspace(
        tmp_path,
        [
            ("DJ-2026-101", "BLOCKED", "卡住了", 0.5),
            ("DJ-2026-101", "AWAITING_APPROVAL", "等批一", 1),
            ("DJ-2026-101", "ACCEPTANCE_PENDING", "等验收", 2),
            ("SW-2026-008", "DRAFT", "工具卡", 4),
        ],
    )
    window = _window(qapp, root, db)
    asks = [frame for frame in window.pm_page.findChildren(QFrame) if frame.objectName() == "ask"]
    assert len(asks) == gui.pd.MAX_DECISIONS
    assert any("还有 2 件排在后面" in text for text in _texts(window.pm_page))
    tree = window.project_tree
    first = tree.topLevelItem(0)
    assert first.text(0).startswith("DJ-2026-101")
    assert first.data(0, gui.Qt.ItemDataRole.UserRole) == "red"
    last_project = tree.topLevelItem(tree.topLevelItemCount() - 2)
    # 没接入驾驶舱的 DJ-2026-102 是灰灯，排在业务项目最后
    assert last_project.data(0, gui.Qt.ItemDataRole.UserRole) == "idle"
    group = tree.topLevelItem(tree.topLevelItemCount() - 1)
    assert group.text(0).startswith("工具与验证项目（1 个")
    assert not group.isExpanded()
    assert group.child(0).text(0).startswith("SW-2026-008")
    # 点开一行：全部业务变更、实施卡、所在文件夹
    children = [first.child(index).text(0) for index in range(first.childCount())]
    assert children == ["BC-DJ-2026-101-001", "CARD-DJ-2026-101-001", "文件夹"]
    assert "BC-DJ-2026-101-001 节拍 30 s → 28 s" in first.text(3)
    window.close()


def test_dev_tab_has_five_columns_with_ledger_leftovers(qapp, tmp_path: Path) -> None:  # noqa: ANN001
    root, db = base._workspace(
        tmp_path,
        [("DJ-2026-101", "CLOSED", "早关了", 30), ("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)],
    )
    window = _window(qapp, root, db)
    projects = [f for f in window.dev_page.findChildren(QFrame) if f.objectName() == "project"]
    target = next(f for f in projects if f.property("project_id") == "DJ-2026-101")
    columns = {
        frame.property("column"): frame
        for frame in target.findChildren(QFrame)
        if frame.objectName() == "column"
    }
    assert list(columns) == list(gui.DEV_COLUMNS)
    assert list(gui.DEV_COLUMNS) == ["在干", "等你", "搁着", "已关", "账本遗留"]
    assert "在干 · 1" in _texts(columns["在干"])
    assert "写通讯层" in _texts(columns["在干"])
    leftovers = _texts(columns["账本遗留"])
    assert "账本遗留 · 1" in leftovers
    assert any(text.startswith("执行记录没结账") for text in leftovers)
    assert any("账本遗留共 1 条，交主执行清理" in text for text in _texts(window.dev_page))
    window.close()


def test_ledger_text_is_shown_as_plain_text(qapp, tmp_path: Path) -> None:  # noqa: ANN001
    sneaky = '<a href="file:///C:/">点我</a><b>粗</b>'
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", sneaky, 0.1)])
    window = _window(qapp, root, db)
    labels = window.findChildren(QLabel)
    assert any(sneaky in label.text() for label in labels)
    for label in labels:
        if label.text():
            assert label.textFormat() == gui.Qt.TextFormat.PlainText, label.text()
            assert not label.openExternalLinks()
    window.close()


def test_legacy_backend_only_snapshot_and_fast_read_first(qapp, tmp_path: Path) -> None:  # noqa: ANN001
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACCEPTANCE_PENDING", "握手断线", 1)])
    db_default = root / gui.pd.DB_RELATIVE
    assert db == db_default
    base._FakeLegacyService.calls = []
    options = _options(root, db, legacy=True, legacy_factory=base._FakeLegacyService)
    window = gui.DashboardWindow(options)
    started: list[bool] = []
    window._start = lambda use_legacy: started.append(use_legacy)  # 不真开线程，只看顺序
    window.reload()
    assert started == [False]  # 先快读，不带老后台
    window._on_loaded(gui.load_board(options, use_legacy=False), False)
    assert started == [False, True]  # 快读画好后，再接老后台
    assert not window.refresh_button.isEnabled()
    loader = gui.BoardLoader(options, True, None)
    results: list[object] = []
    loader.loaded.connect(lambda board, _legacy: results.append(board))
    loader.run()  # 在本线程里直接跑一遍后台读取
    assert base._FakeLegacyService.calls == ["snapshot"]
    window._on_loaded(results[0], True)
    assert window.refresh_button.isEnabled()
    assert any(
        "阶段 验收 · 风险 低" in window.project_tree.topLevelItem(i).text(1) for i in range(2)
    )
    window.close()


def test_read_failure_keeps_the_window_alive(qapp, tmp_path: Path) -> None:  # noqa: ANN001
    root, db = base._workspace(tmp_path, [])
    db.write_bytes(b"not a database")
    options = _options(root, db)
    loader = gui.BoardLoader(options, False, None)
    failures: list[str] = []
    loader.failed.connect(failures.append)
    loader.run()
    assert failures and "DatabaseError" in failures[0]
    window = gui.DashboardWindow(options)
    window._on_failed(failures[0])
    assert window.status.text().startswith("这次没读成")
    assert window.refresh_button.isEnabled()
    window.close()


def test_double_click_launcher_is_outside_releases() -> None:
    assert BAT.is_file()
    raw = BAT.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    text = raw.decode("utf-8")
    assert "releases" not in text.replace("不在 releases\\ 里", "")
    assert "main.py" not in text
    assert "codex" not in text.lower()
    assert "-B" in text and "pm_dashboard_gui.py" in text
    # bat 用纯英文通配符找脚本：01_Project* \ Python* \ 02_* \ SW-2026-008_* \ scripts
    matches = [
        path
        for a in REPO_ROOT.glob("01_Project*")
        for b in a.glob("Python*")
        for c in b.glob("02_*")
        for d in c.glob("SW-2026-008_*")
        if (path := d / "scripts" / "pm_dashboard_gui.py").is_file()
    ]
    assert matches == [SCRIPT]
    assert "releases" not in SCRIPT.relative_to(REPO_ROOT).parts


def test_gui_source_has_no_network_process_or_workspace_writes() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "subprocess",
        "urllib",
        "requests",
        "socket",
        "QNetwork",
        "QProcess",
        "os.system",
    ):
        assert forbidden not in source, forbidden
    for forbidden in ("start_execution", "confirm_start", "approve_scope", "close_accepted"):
        assert forbidden not in source, forbidden
    # 唯一的写文件是启动出错时把原因写到系统临时目录
    assert source.count("write_text(") == 1
    assert "tempfile.gettempdir()" in source.split("def _crash_report", 1)[1]
