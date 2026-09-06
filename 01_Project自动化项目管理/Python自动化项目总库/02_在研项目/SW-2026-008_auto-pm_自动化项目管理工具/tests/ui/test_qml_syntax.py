"""QML 静态语法与组件加载回归测试门禁 (DEV-216 / DEV-300)

自动扫描 auto_pm/ui/qml 目录下的所有 .qml 文件，
在 offscreen 模式下通过 QQmlComponent 校验语法、类型绑定和信号定义的正确性，
确保 QML 解析错误 100% 在 CI/pytest 阶段被拦截。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qml_engine(qapp) -> QQmlEngine:
    """复用根 conftest 的 session 级 qapp（QApplication）。

    CHG-SCPT-2026-019：原先在此创建裸 QCoreApplication 单例，会使其后执行的
    tests/qml 全部在根 qapp 断言处假失败（Qt 全局单例不可替换，且目录枚举序
    导致本模块与 tests/qml 的先后顺序非确定）。QApplication 兼容 QML 加载。
    """
    engine = QQmlEngine()
    qml_dir = Path(__file__).parent.parent.parent / "auto_pm" / "ui" / "qml"
    engine.addImportPath(str(qml_dir))
    engine.addImportPath(str(qml_dir / "components"))
    engine.addImportPath(str(qml_dir / "views"))
    engine.addImportPath(str(qml_dir / "views" / "workspace"))
    engine.addImportPath(str(qml_dir / "dialogs"))
    engine.addImportPath(str(qml_dir / "theme"))
    return engine


def _get_all_qml_files() -> list[Path]:
    qml_dir = Path(__file__).parent.parent.parent / "auto_pm" / "ui" / "qml"
    return sorted(qml_dir.rglob("*.qml"))


@pytest.mark.parametrize("qml_path", _get_all_qml_files(), ids=lambda p: p.name)
def test_qml_file_syntax_and_component_loading(qml_engine: QQmlEngine, qml_path: Path) -> None:
    """每个 QML 文件必须能被 QQmlComponent 成功解析无语法错误"""
    component = QQmlComponent(qml_engine, QUrl.fromLocalFile(str(qml_path)))
    if component.isError():
        errors = [e.toString() for e in component.errors()]
        pytest.fail(f"QML 语法解析错误 [{qml_path.name}]:\n" + "\n".join(errors))
