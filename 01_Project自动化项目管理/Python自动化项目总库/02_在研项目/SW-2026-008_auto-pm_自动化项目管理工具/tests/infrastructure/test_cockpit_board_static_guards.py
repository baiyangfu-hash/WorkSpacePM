"""Static source guards split out from heavy GUI tests (no PySide6 dependency)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
SCRIPTS = PROJECT / "scripts"
SCRIPT = SCRIPTS / "pm_dashboard_gui.py"
PACKAGE = SCRIPTS / "cockpit_board"
WRITES = r"(?<![\w.])open\(|write_bytes\(|write_text\("


def test_cockpit_board_sources_have_no_hardcoded_hex_colors() -> None:
    """画面代码里不许写颜色，改颜色只改 theme.py（从 test_cockpit_board 拆出的纯静态守卫）。"""

    for path in PACKAGE.rglob("*.py"):
        if path.name != "theme.py":
            assert not re.search(r"#[0-9a-fA-F]{6}\b", path.read_text(encoding="utf-8")), path.name


def test_process_and_file_writes_live_only_in_actions() -> None:
    """视图层不得引入网络/进程/写文件调用（从 test_pm_dashboard_gui 拆出的纯静态守卫）。"""

    sources = {path: path.read_text(encoding="utf-8") for path in [SCRIPT, *PACKAGE.rglob("*.py")]}
    for path, source in sources.items():
        for forbidden in ("urllib", "requests", "socket", "QNetwork", "QProcess", "os.system"):
            assert forbidden not in source, (path.name, forbidden)
        for forbidden in ("start_execution", "confirm_start", "approve_scope", "close_accepted"):
            assert forbidden not in source, (path.name, forbidden)
        if path.name != "policy.py":  # 规矩文件列的是禁用词本身
            assert "no-verify" not in source, path.name
        # 起子进程的只有 actions.py（决定类按钮）和 tool_actions.py（工程工具）；后者另有 test_cockpit_board_tools 逐文件数
        if path.name not in ("actions.py", "tool_actions.py"):
            assert "subprocess" not in source, path.name
        if path.name not in ("actions.py", "app.py"):
            assert not re.search(WRITES, source), path.name
    # 写文件只有三处：actions.py 追加一行 BC（带预览）、actions.write_snapshot 存“上次读取”快照（只写
    # .auto-pm/cache/cockpit_board/，CHG-SCPT-2026-628 骨架 B）；app.py 只在启动出错时写系统临时目录
    app_source = sources[PACKAGE / "app.py"]
    assert app_source.count("write_text(") == 1
    assert "tempfile.gettempdir()" in app_source.split("def _crash_report", 1)[1]
    actions_source = sources[PACKAGE / "actions.py"]
    assert len(re.findall(WRITES, actions_source)) == 2
    assert (
        len(re.findall(WRITES, actions_source.split("def write_snapshot", 1)[1])) == 1
    )  # 快照那一处在 write_snapshot 里
    assert len(re.findall(WRITES, app_source)) == 1


def test_static_guards_module_has_no_qt_dependency() -> None:
    """确认本静态守卫文件零 Qt 依赖，可在无 PySide6 环境独立运行。"""

    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"), filename=__file__)
    qt_roots = {"PySide6", "PyQt5", "PyQt6", "qtpy"}
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(qt_roots), imported & qt_roots
