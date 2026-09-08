"""QML 单元测试：DocBrowserView.qml 及其委托组件渲染 (CHG-SCPT-2026-129)"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtWidgets import QApplication

_QML_DIR = Path(__file__).resolve().parents[2] / "auto_pm" / "ui" / "qml"
_VIEWS_DIR = _QML_DIR / "views"
_COMPONENTS_DOC_DIR = _QML_DIR / "components" / "doc"

def _load_qml(engine: QQmlEngine, path: Path) -> object:
    url = QUrl.fromLocalFile(str(path))
    component = QQmlComponent(engine, url)
    if component.isError():
        errors = "\n".join(e.toString() for e in component.errors())
        raise AssertionError(f"加载 QML 失败 {path.name}:\n{errors}")
    obj = component.create()
    assert obj is not None, f"实例化 QML 失败: {path.name}"
    obj._component_ref = component
    return obj

def _to_variant(value: object) -> object:
    if hasattr(value, "toVariant"):
        return value.toVariant()
    return value

def test_doc_browser_view_instantiation(qapp: QApplication, qml_engine: QQmlEngine) -> None:
    """测试 DocBrowserView 默认属性与初始化成功"""
    view = _load_qml(qml_engine, _VIEWS_DIR / "DocBrowserView.qml")
    assert view.property("projectId") == ""  # type: ignore[attr-defined]
    assert view.property("selectedIndex") == -1  # type: ignore[attr-defined]
    assert view.property("statusMessage") == ""  # type: ignore[attr-defined]

def test_doc_browser_view_filter_logic(qapp: QApplication, qml_engine: QQmlEngine) -> None:
    """测试 DocBrowserView 的目录搜索过滤逻辑"""
    view = _load_qml(qml_engine, _VIEWS_DIR / "DocBrowserView.qml")

    docs = [
        {"name": "01_PRD.md", "path": "/path/01_PRD.md"},
        {"name": "02_DES.md", "path": "/path/02_DES.md"},
        {"name": "PM_SESSION.md", "path": "/path/PM_SESSION.md"},
    ]
    view.setProperty("docList", docs)  # type: ignore[attr-defined]
    qapp.processEvents()

    # 默认不过滤
    filtered = _to_variant(view.property("filteredDocList"))  # type: ignore[attr-defined]
    assert len(filtered) == 3  # type: ignore[arg-type]

    # 输入过滤关键字
    view.setProperty("filterText", "session")  # type: ignore[attr-defined]
    qapp.processEvents()
    filtered = _to_variant(view.property("filteredDocList"))  # type: ignore[attr-defined]
    assert len(filtered) == 1  # type: ignore[arg-type]
    assert filtered[0]["name"] == "PM_SESSION.md"  # type: ignore[index]


def test_load_doc_delegates(qapp: QApplication, qml_engine: QQmlEngine) -> None:
    """测试 Markdown 渲染委托组件集均能正常加载"""
    header = _load_qml(qml_engine, _COMPONENTS_DOC_DIR / "DocHeader.qml")
    assert header.property("textData") == ""  # type: ignore[attr-defined]

    para = _load_qml(qml_engine, _COMPONENTS_DOC_DIR / "DocParagraph.qml")
    assert para.property("htmlData") == ""  # type: ignore[attr-defined]

    code = _load_qml(qml_engine, _COMPONENTS_DOC_DIR / "DocCodeBlock.qml")
    assert code.property("codeData") == ""  # type: ignore[attr-defined]
    assert code.property("language") == "text"  # type: ignore[attr-defined]

    alert = _load_qml(qml_engine, _COMPONENTS_DOC_DIR / "DocAlert.qml")
    assert alert.property("htmlData") == ""  # type: ignore[attr-defined]
    assert alert.property("alertType") == "note"  # type: ignore[attr-defined]

    table = _load_qml(qml_engine, _COMPONENTS_DOC_DIR / "DocTable.qml")
    assert table.property("htmlData") == ""  # type: ignore[attr-defined]
