"""QML 单元测试：DocBrowserView.qml 分类筛选与大纲导航联动 (CHG-SCPT-2026-130)"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtWidgets import QApplication

_QML_DIR = Path(__file__).resolve().parents[2] / "auto_pm" / "ui" / "qml"
_VIEWS_DIR = _QML_DIR / "views"

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

def test_doc_browser_view_generic_categories(qapp: QApplication, qml_engine: QQmlEngine) -> None:
    """测试 DocBrowserView 的项目文档分类筛选过滤逻辑"""
    view = _load_qml(qml_engine, _VIEWS_DIR / "DocBrowserView.qml")

    docs = [
        {"name": "00_项目管理/01_PM_Plan.md", "path": "/path/00_plan.md", "category": "pm"},
        {"name": "01_技术文档/01_Architecture.md", "path": "/path/01_arch.md", "category": "tech"},
        {"name": ".trae/specs/checklist.md", "path": "/path/specs.md", "category": "spec"},
        {"name": "PM_SESSION_SW-2026-008.md", "path": "/path/session.md", "category": "log"},
        {"name": "README.md", "path": "/path/readme.md", "category": "other"},
    ]
    view.setProperty("docList", docs)  # type: ignore[attr-defined]
    qapp.processEvents()

    # 默认全部文档
    view.setProperty("selectedCategory", "all")  # type: ignore[attr-defined]
    qapp.processEvents()
    filtered = _to_variant(view.property("filteredDocList"))  # type: ignore[attr-defined]
    assert len(filtered) == 5  # type: ignore[arg-type]

    # 筛选项目管理文档
    view.setProperty("selectedCategory", "pm")  # type: ignore[attr-defined]
    qapp.processEvents()
    filtered = _to_variant(view.property("filteredDocList"))  # type: ignore[attr-defined]
    assert len(filtered) == 1  # type: ignore[arg-type]
    assert filtered[0]["name"] == "00_项目管理/01_PM_Plan.md"  # type: ignore[index]

    # 筛选技术文档
    view.setProperty("selectedCategory", "tech")  # type: ignore[attr-defined]
    qapp.processEvents()
    filtered = _to_variant(view.property("filteredDocList"))  # type: ignore[attr-defined]
    assert len(filtered) == 1  # type: ignore[arg-type]
    assert filtered[0]["name"] == "01_技术文档/01_Architecture.md"  # type: ignore[index]

def test_doc_browser_view_outline_extraction(qapp: QApplication, qml_engine: QQmlEngine) -> None:
    """测试 DocBrowserView 自动从 blocks 中提取 h1, h2 级别的大纲模型"""
    view = _load_qml(qml_engine, _VIEWS_DIR / "DocBrowserView.qml")

    blocks = [
        {"type": "h1", "text": "Heading One"},
        {"type": "paragraph", "html": "<p>some text</p>"},
        {"type": "h2", "text": "Sub Heading Two"},
        {"type": "code", "code": "print(1)", "lang": "python"},
        {"type": "h3", "text": "Sub Sub Heading Three"}, # 不提取 h3 保持清爽
    ]
    view.setProperty("docBlocks", blocks)  # type: ignore[attr-defined]
    qapp.processEvents()

    outline = _to_variant(view.property("outlineModel"))  # type: ignore[attr-defined]
    assert len(outline) == 2  # type: ignore[arg-type]
    assert outline[0]["text"] == "Heading One"  # type: ignore[index]
    assert outline[0]["type"] == "h1"  # type: ignore[index]
    assert outline[0]["blockIndex"] == 0  # type: ignore[index]

    assert outline[1]["text"] == "Sub Heading Two"  # type: ignore[index]
    assert outline[1]["type"] == "h2"  # type: ignore[index]
    assert outline[1]["blockIndex"] == 2  # type: ignore[index]
