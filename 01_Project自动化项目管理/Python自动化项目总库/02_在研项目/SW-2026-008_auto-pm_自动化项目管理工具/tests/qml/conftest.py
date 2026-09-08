"""tests/qml 共享 fixture

约束（与 tests/ui/conftest.py 一致）：
- qapp fixture 单一定位 tests/conftest.py（session 级 QApplication）
- 不重新定义 qapp，直接通过 `def test_xxx(qapp):` 引用
- QApplication 是 QGuiApplication 子类，QML 模块在 QApplication 下正常工作

提供 fixture：
- sample_projects：内存构造的 ProjectInfo 列表（不依赖文件系统扫描）
- mock_project_service：Mock ProjectService，list_projects 返回 sample_projects
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from auto_pm.models import ProjectInfo
from PySide6.QtQml import QQmlEngine
from PySide6.QtWidgets import QApplication

if TYPE_CHECKING:
    pass


@pytest.fixture
def qml_engine(qapp: QApplication) -> QQmlEngine:
    """提供当前 Python 环境的 QML 引擎与项目 QML import path。"""
    import PySide6

    engine = QQmlEngine()
    pyside6_qml = Path(PySide6.__file__).resolve().parent / "qml"
    if pyside6_qml.is_dir():
        engine.addImportPath(str(pyside6_qml))
    project_qml = Path(__file__).resolve().parents[2] / "auto_pm" / "ui" / "qml"
    engine.addImportPath(str(project_qml))
    return engine


@pytest.fixture
def sample_projects() -> list[ProjectInfo]:
    """内存构造的项目列表（不依赖文件系统扫描）

    覆盖 stack/phase/business_line 三种枚举值的代表性场景：
    - SW-2026-008：python + developing + SW（典型在研软件项目）
    - DJ-2026-005：plc + commissioning + DJ（典型调试中 PLC 项目）
    - DJ-2026-010：plc + production + DJ（典型生产中 PLC 项目）
    """
    return [
        ProjectInfo(
            project_id="SW-2026-008",
            name="auto-pm",
            path="c:/tmp/SW-2026-008_auto-pm",
            stack="python",
            version="0.6.0",
            phase="developing",
            business_line="SW",
        ),
        ProjectInfo(
            project_id="DJ-2026-005",
            name="输送线自动化项目",
            path="c:/tmp/DJ-2026-005_输送线",
            stack="plc",
            version="1.0.0",
            phase="commissioning",
            business_line="DJ",
        ),
        ProjectInfo(
            project_id="DJ-2026-010",
            name="包装机项目",
            path="c:/tmp/DJ-2026-010_包装机",
            stack="plc",
            version="2.1.0",
            phase="production",
            business_line="DJ",
        ),
    ]


@pytest.fixture
def mock_project_service(sample_projects: list[ProjectInfo]) -> MagicMock:
    """Mock ProjectService，list_projects 返回 sample_projects

    用于 QmlBridge 测试，避免依赖真实文件系统扫描。
    """
    from auto_pm.application.common import FacadeResult
    service = MagicMock()
    # 兼容老的 list_projects 接口，为了某些测试不报错
    service.list_projects.return_value = sample_projects
    # 新的 Facade 接口
    service.list_project_cards.return_value = FacadeResult.success(sample_projects)
    service.has_project_service = True
    service.has_dashboard_service = True
    return service
