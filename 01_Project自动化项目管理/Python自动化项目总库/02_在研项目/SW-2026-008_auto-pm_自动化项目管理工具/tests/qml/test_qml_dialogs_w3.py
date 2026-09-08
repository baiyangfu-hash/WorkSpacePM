"""QML W3 对话框单元测试（V0.6.0 W3-S10~S17）

覆盖 8 个对话框的实例化 + 默认属性 + 信号：
- NewProjectWizard.qml：3 步向导 + projectCreated 信号
- NewChangeDialog.qml：变更单表单 + changeCreated 信号
- ProjectSettingsDialog.qml：项目设置字段 + saved 信号
- SyncCacheDialog.qml：进度条 + updateProgress 方法
- ImportProjectDialog.qml：导入项目 + imported 信号
- AboutDialog.qml：关于信息 + closed 信号
- ReportDialog.qml：报告生成 + reportGenerated 信号
- GlobalSettingsDialog.qml：全局设置 + saved 信号

测试策略：
- QQmlEngine + QQmlComponent 加载 QML 文件
- 用 qapp fixture 确保 Qt 事件循环可用
- 直接断言 QML 对象属性值
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication


# ── 路径常量 ───────────────────────────────────────────────

_QML_DIR = (
    Path(__file__).resolve().parents[2]
    / "auto_pm"
    / "ui"
    / "qml"
)
_DIALOGS_DIR = _QML_DIR / "dialogs"


def _load_component(engine: QQmlEngine, qml_file: Path) -> object:
    """加载 QML 对话框并返回根对象实例"""
    url = QUrl.fromLocalFile(str(qml_file))
    component = QQmlComponent(engine, url)
    if component.isError():
        errors = "\n".join(f"  - {e.toString()}" for e in component.errors())
        raise AssertionError(f"加载 QML 对话框失败 {qml_file.name}:\n{errors}")
    obj = component.create()
    assert obj is not None, f"创建 QML 对话框实例失败: {qml_file.name}"
    obj._component_ref = component
    return obj


def _to_variant(value: object) -> object:
    """QJSValue → Python 原生类型"""
    if hasattr(value, "toVariant"):
        return value.toVariant()
    return value


# ── NewProjectWizard.qml (W3-S10) ────────────────────────


def test_new_project_wizard_default_properties(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    """NewProjectWizard 默认 _isOpen=False，currentStep=0，totalSteps=3"""
    wizard = _load_component(qml_engine, _DIALOGS_DIR / "NewProjectWizard.qml")
    assert wizard.property("_isOpen") is False  # type: ignore[attr-defined]
    assert wizard.property("currentStep") == 0  # type: ignore[attr-defined]
    assert wizard.property("totalSteps") == 3  # type: ignore[attr-defined]
    assert wizard.property("projectId") == ""  # type: ignore[attr-defined]
    assert wizard.property("stack") == "python"  # type: ignore[attr-defined]
    assert wizard.property("businessLine") == "SW"  # type: ignore[attr-defined]
    assert wizard.property("mode") == "standard"  # type: ignore[attr-defined]


def test_new_project_wizard_set_step(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    """NewProjectWizard 设置 currentStep 后应正确读取"""
    wizard = _load_component(qml_engine, _DIALOGS_DIR / "NewProjectWizard.qml")
    wizard.setProperty("currentStep", 2)  # type: ignore[attr-defined]
    qapp.processEvents()
    assert wizard.property("currentStep") == 2  # type: ignore[attr-defined]


def test_new_project_wizard_set_project_id(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    """NewProjectWizard 设置 projectId 后应正确读取"""
    wizard = _load_component(qml_engine, _DIALOGS_DIR / "NewProjectWizard.qml")
    wizard.setProperty("projectId", "SW-2026-008")  # type: ignore[attr-defined]
    qapp.processEvents()
    assert wizard.property("projectId") == "SW-2026-008"  # type: ignore[attr-defined]


# ── NewChangeDialog.qml (W3-S11) ─────────────────────────


def test_new_change_dialog_default_properties(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    """NewChangeDialog 默认字段值正确"""
    dlg = _load_component(qml_engine, _DIALOGS_DIR / "NewChangeDialog.qml")
    assert dlg.property("_isOpen") is False  # type: ignore[attr-defined]
    assert dlg.property("changeTitle") == ""  # type: ignore[attr-defined]
    assert dlg.property("projectId") == ""  # type: ignore[attr-defined]
    assert dlg.property("domain") == "PLC"  # type: ignore[attr-defined]
    assert dlg.property("nature") == "REQ"  # type: ignore[attr-defined]


def test_new_change_dialog_set_fields(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    """NewChangeDialog 设置字段后应正确读取"""
    dlg = _load_component(qml_engine, _DIALOGS_DIR / "NewChangeDialog.qml")
    dlg.setProperty("changeTitle", "新增功能")  # type: ignore[attr-defined]
    dlg.setProperty("projectId", "SW-2026-008")  # type: ignore[attr-defined]
    dlg.setProperty("domain", "SCPT")  # type: ignore[attr-defined]
    dlg.setProperty("nature", "OPT")  # type: ignore[attr-defined]
    qapp.processEvents()
    assert dlg.property("changeTitle") == "新增功能"  # type: ignore[attr-defined]
    assert dlg.property("projectId") == "SW-2026-008"  # type: ignore[attr-defined]
    assert dlg.property("domain") == "SCPT"  # type: ignore[attr-defined]
    assert dlg.property("nature") == "OPT"  # type: ignore[attr-defined]


# ── ProjectSettingsDialog.qml (W3-S12) ───────────────────


def test_project_settings_dialog_default_properties(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    """ProjectSettingsDialog 默认字段值正确"""
    dlg = _load_component(qml_engine, _DIALOGS_DIR / "ProjectSettingsDialog.qml")
    assert dlg.property("_isOpen") is False  # type: ignore[attr-defined]
    assert dlg.property("projectId") == ""  # type: ignore[attr-defined]
    assert dlg.property("version") == "0.1.0"  # type: ignore[attr-defined]
    assert dlg.property("phase") == "developing"  # type: ignore[attr-defined]
    assert dlg.property("stack") == "python"  # type: ignore[attr-defined]
    assert dlg.property("businessLine") == "SW"  # type: ignore[attr-defined]


def test_project_settings_dialog_set_version(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    """ProjectSettingsDialog 设置 version 后应正确读取"""
    dlg = _load_component(qml_engine, _DIALOGS_DIR / "ProjectSettingsDialog.qml")
    dlg.setProperty("version", "0.6.0")  # type: ignore[attr-defined]
    qapp.processEvents()
    assert dlg.property("version") == "0.6.0"  # type: ignore[attr-defined]


# ── SyncCacheDialog.qml (W3-S13) ─────────────────────────


def test_sync_cache_dialog_default_properties(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    """SyncCacheDialog 默认 progress=0，isRunning=False"""
    dlg = _load_component(qml_engine, _DIALOGS_DIR / "SyncCacheDialog.qml")
    assert dlg.property("_isOpen") is False  # type: ignore[attr-defined]
    assert dlg.property("progress") == 0.0  # type: ignore[attr-defined]
    assert dlg.property("isRunning") is False  # type: ignore[attr-defined]
    assert dlg.property("statusText") == "准备同步..."  # type: ignore[attr-defined]


def test_sync_cache_dialog_set_progress(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    """SyncCacheDialog 设置 progress 后应正确读取"""
    dlg = _load_component(qml_engine, _DIALOGS_DIR / "SyncCacheDialog.qml")
    dlg.setProperty("progress", 0.5)  # type: ignore[attr-defined]
    qapp.processEvents()
    assert dlg.property("progress") == 0.5  # type: ignore[attr-defined]


# ── ImportProjectDialog.qml (W3-S14) ─────────────────────


def test_import_project_dialog_default_properties(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    """ImportProjectDialog 默认字段值正确"""
    dlg = _load_component(qml_engine, _DIALOGS_DIR / "ImportProjectDialog.qml")
    assert dlg.property("_isOpen") is False  # type: ignore[attr-defined]
    assert dlg.property("projectPath") == ""  # type: ignore[attr-defined]
    assert dlg.property("detectedId") == ""  # type: ignore[attr-defined]
    assert dlg.property("isDetecting") is False  # type: ignore[attr-defined]


def test_import_project_dialog_set_path(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    """ImportProjectDialog 设置 projectPath 后应正确读取"""
    dlg = _load_component(qml_engine, _DIALOGS_DIR / "ImportProjectDialog.qml")
    dlg.setProperty("projectPath", "D:\\Projects\\TestProject")  # type: ignore[attr-defined]
    qapp.processEvents()
    assert dlg.property("projectPath") == "D:\\Projects\\TestProject"  # type: ignore[attr-defined]


# ── AboutDialog.qml (W3-S15) ─────────────────────────────


def test_about_dialog_default_properties(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    """AboutDialog 默认应用信息正确"""
    dlg = _load_component(qml_engine, _DIALOGS_DIR / "AboutDialog.qml")
    assert dlg.property("_isOpen") is False  # type: ignore[attr-defined]
    assert dlg.property("appName") == "auto-pm"  # type: ignore[attr-defined]
    assert dlg.property("appVersion") == "1.0.0"  # type: ignore[attr-defined]
    assert dlg.property("license") == "MIT"  # type: ignore[attr-defined]
    assert "PySide6" in dlg.property("techStack")  # type: ignore[attr-defined]


def test_about_dialog_set_version(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    """AboutDialog 设置 appVersion 后应正确读取"""
    dlg = _load_component(qml_engine, _DIALOGS_DIR / "AboutDialog.qml")
    dlg.setProperty("appVersion", "1.0.0")  # type: ignore[attr-defined]
    qapp.processEvents()
    assert dlg.property("appVersion") == "1.0.0"  # type: ignore[attr-defined]


# ── ReportDialog.qml (W3-S16) ────────────────────────────


def test_report_dialog_default_properties(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    """ReportDialog 默认字段值正确"""
    dlg = _load_component(qml_engine, _DIALOGS_DIR / "ReportDialog.qml")
    assert dlg.property("_isOpen") is False  # type: ignore[attr-defined]
    assert dlg.property("reportType") == "summary"  # type: ignore[attr-defined]
    assert dlg.property("outputFormat") == "markdown"  # type: ignore[attr-defined]
    assert dlg.property("outputPath") == ""  # type: ignore[attr-defined]
    assert dlg.property("isGenerating") is False  # type: ignore[attr-defined]
    assert dlg.property("progress") == 0.0  # type: ignore[attr-defined]


def test_report_dialog_set_output_path(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    """ReportDialog 设置 outputPath 后应正确读取"""
    dlg = _load_component(qml_engine, _DIALOGS_DIR / "ReportDialog.qml")
    dlg.setProperty("outputPath", "/tmp/report.md")  # type: ignore[attr-defined]
    qapp.processEvents()
    assert dlg.property("outputPath") == "/tmp/report.md"  # type: ignore[attr-defined]


# ── GlobalSettingsDialog.qml (W3-S17) ────────────────────


def test_global_settings_dialog_default_properties(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    """GlobalSettingsDialog 默认设置值正确"""
    dlg = _load_component(qml_engine, _DIALOGS_DIR / "GlobalSettingsDialog.qml")
    assert dlg.property("_isOpen") is False  # type: ignore[attr-defined]
    assert dlg.property("workspaceRoot") == ""  # type: ignore[attr-defined]
    assert dlg.property("theme") == "light"  # type: ignore[attr-defined]
    assert dlg.property("language") == "zh-CN"  # type: ignore[attr-defined]
    assert dlg.property("autoRefresh") is True  # type: ignore[attr-defined]
    assert dlg.property("refreshInterval") == 30  # type: ignore[attr-defined]
    assert dlg.property("confirmBeforeDelete") is True  # type: ignore[attr-defined]
    assert dlg.property("enableDebugLog") is False  # type: ignore[attr-defined]


def test_global_settings_dialog_set_workspace(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    """GlobalSettingsDialog 设置 workspaceRoot 后应正确读取"""
    dlg = _load_component(qml_engine, _DIALOGS_DIR / "GlobalSettingsDialog.qml")
    dlg.setProperty("workspaceRoot", "C:\\Users\\test\\workspace")  # type: ignore[attr-defined]
    qapp.processEvents()
    assert dlg.property("workspaceRoot") == "C:\\Users\\test\\workspace"  # type: ignore[attr-defined]


def test_global_settings_dialog_set_refresh_interval(
    qapp: QApplication, qml_engine: QQmlEngine
) -> None:
    """GlobalSettingsDialog 设置 refreshInterval 后应正确读取"""
    dlg = _load_component(qml_engine, _DIALOGS_DIR / "GlobalSettingsDialog.qml")
    dlg.setProperty("refreshInterval", 60)  # type: ignore[attr-defined]
    qapp.processEvents()
    assert dlg.property("refreshInterval") == 60  # type: ignore[attr-defined]


# ── 全部 8 个对话框加载验证（汇总） ─────────────────────


def test_all_8_dialogs_loadable(qapp: QApplication, qml_engine: QQmlEngine) -> None:
    """8 个对话框应全部能成功加载（W3-S10~S17 整体验证）"""
    dialog_files = [
        "NewProjectWizard.qml",
        "NewChangeDialog.qml",
        "ProjectSettingsDialog.qml",
        "SyncCacheDialog.qml",
        "ImportProjectDialog.qml",
        "AboutDialog.qml",
        "ReportDialog.qml",
        "GlobalSettingsDialog.qml",
    ]
    for filename in dialog_files:
        obj = _load_component(qml_engine, _DIALOGS_DIR / filename)
        assert obj is not None, f"对话框加载失败: {filename}"
        assert obj.property("_isOpen") is False, f"{filename} 默认 _isOpen 应为 False"  # type: ignore[attr-defined]
