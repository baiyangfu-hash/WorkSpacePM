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

from collections.abc import Iterator
from contextlib import AbstractContextManager, ExitStack, contextmanager
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest
from auto_pm.models import ProjectInfo
from PySide6.QtCore import QCoreApplication, QEvent, QObject, Qt, QThread
from PySide6.QtQml import QQmlEngine
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

if TYPE_CHECKING:
    pass


class _QmlRoots(QObject):
    """Retain only explicitly registered roots, window lifetimes and their bridges."""

    def __init__(self, engine: QQmlEngine) -> None:
        super().__init__(engine)
        self.windows = ExitStack()
        self.bridges: list[QObject] = []


def _assert_gui_thread(*objects: QObject) -> None:
    """Reject lifecycle operations before touching Qt from a non-GUI thread."""
    app = QCoreApplication.instance()
    assert app is not None, "QML lifecycle requires an application"
    assert QThread.currentThread() == app.thread(), "QML lifecycle requires the GUI thread"
    for value in objects:
        assert isValid(value), "QML lifecycle received a deleted QObject"
        assert value.thread() == app.thread(), "QML lifecycle object is not on the GUI thread"


def _qml_roots(engine: QQmlEngine) -> _QmlRoots:
    """Find this engine's registration without introducing a global ownership table."""
    _assert_gui_thread(engine)
    owner = engine.findChild(_QmlRoots, options=Qt.FindChildOption.FindDirectChildrenOnly)
    if owner is None:
        owner = _QmlRoots(engine)
    return owner


def _own_qml_root(engine: QQmlEngine, root: QObject) -> None:
    """Register a C++-owned root without changing the loader's return contract."""
    _assert_gui_thread(engine, root)
    owner = _qml_roots(engine)
    # QQuickWindow overrides setParent with a QWindow-only overload.
    QObject.setParent(root, owner)


def _register_qml_window(
    engine: QQmlEngine, bridge: QObject, lifetime: AbstractContextManager[QObject]
) -> QObject:
    """Keep public-loader windows and their context bridges until fixture teardown."""
    _assert_gui_thread(engine, bridge)
    owner = _qml_roots(engine)
    if not any(held is bridge for held in owner.bridges):
        owner.bridges.append(bridge)
    return owner.windows.enter_context(lifetime)


def _close_registered_qml(engine: QQmlEngine) -> None:
    """Destroy registered consumers before bridges; leave every legacy object alone."""
    _assert_gui_thread(engine)
    owner = engine.findChild(_QmlRoots, options=Qt.FindChildOption.FindDirectChildrenOnly)
    if owner is None:
        return
    owner.windows.close()
    bridges = tuple(owner.bridges)
    owner.bridges.clear()
    _delete_qobject(owner)
    for bridge in bridges:
        _delete_qobject(bridge)


def _delete_qobject(value: QObject) -> None:
    """Finish this GUI object's deferred deletion without dispatching general events."""
    if isValid(value):
        _assert_gui_thread(value)
        value.deleteLater()
        QCoreApplication.sendPostedEvents(value, QEvent.Type.DeferredDelete.value)
        assert not isValid(value), "QObject deferred deletion did not complete"


def _new_qml_engine() -> QQmlEngine:
    """Configure the import paths without imposing a root-lifetime policy."""
    import PySide6

    _assert_gui_thread()
    engine = QQmlEngine()
    pyside6_qml = Path(PySide6.__file__).resolve().parent / "qml"
    if pyside6_qml.is_dir():
        engine.addImportPath(str(pyside6_qml))
    project_qml = Path(__file__).resolve().parents[2] / "auto_pm" / "ui" / "qml"
    engine.addImportPath(str(project_qml))
    return engine


@contextmanager
def _managed_qml_engine() -> Iterator[QQmlEngine]:
    """Opt in only when every caller manages or registers its QML roots."""
    engine = _new_qml_engine()
    try:
        yield engine
    finally:
        _close_registered_qml(engine)
        _delete_qobject(engine)


@pytest.fixture
def qml_engine(qapp: QApplication) -> Iterator[QQmlEngine]:
    """Close registered resources only; preserve legacy engine/root lifetime semantics."""
    engine = _new_qml_engine()
    try:
        yield engine
    finally:
        _close_registered_qml(engine)


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
