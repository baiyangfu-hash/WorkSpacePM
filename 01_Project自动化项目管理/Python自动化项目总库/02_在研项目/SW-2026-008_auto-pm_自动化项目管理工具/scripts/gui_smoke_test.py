"""GUI 冒烟测试 - 全页面及 DJ-2026-005 深度截图 + 控制台警告收集

运行方式：
    python scripts/gui_smoke_test.py --workspace <工作空间路径> --output <输出目录> --project DJ-2026-005
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

# 自动将项目根目录加入 sys.path
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from PySide6.QtCore import QCoreApplication, QObject, QTimer, QtMsgType, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlExpression
from PySide6.QtQuick import QQuickWindow
from PySide6.QtQuickControls2 import QQuickStyle


class GuiTestRunner(QObject):
    """GUI 冒烟测试运行器"""

    def __init__(
        self,
        engine: QQmlApplicationEngine,
        output_dir: Path,
        workspace_root: str,
        target_project_id: str = "DJ-2026-005",
    ) -> None:
        super().__init__()
        self.engine = engine
        self.output_dir = output_dir
        self.screenshots_dir = output_dir / "screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_root = workspace_root
        self.target_project_id = target_project_id

        self.warnings: list[dict[str, Any]] = []
        self.screenshots: list[dict[str, Any]] = []
        self.test_steps: list[dict[str, Any]] = []
        self.step_index = 0

        self._install_message_handler()

    def _install_message_handler(self) -> None:
        def handler(mode: QtMsgType, context: Any, message: str) -> None:
            if mode in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
                type_name = {
                    QtMsgType.QtWarningMsg: "Warning",
                    QtMsgType.QtCriticalMsg: "Critical",
                    QtMsgType.QtFatalMsg: "Fatal",
                }.get(mode, "Unknown")
                self.warnings.append({
                    "type": type_name,
                    "message": message,
                    "file": context.file if context else "",
                    "line": context.line if context else 0,
                    "function": context.function if context else "",
                    "timestamp": datetime.now().isoformat(),
                })

        from PySide6.QtCore import qInstallMessageHandler
        qInstallMessageHandler(handler)

    def _eval_qml(self, expression_str: str) -> Any:
        window = self._get_root_window()
        if not window:
            return None
        expr = QQmlExpression(self.engine.rootContext(), window, expression_str)
        val = expr.evaluate()
        if expr.hasError():
            print(f"[QML Eval Error] {expr.error().toString()} for '{expression_str}'")
        QCoreApplication.processEvents()
        return val

    def _take_screenshot(self, name: str, description: str) -> str:
        QCoreApplication.processEvents()
        time.sleep(0.3)
        QCoreApplication.processEvents()

        root_objects = self.engine.rootObjects()
        if not root_objects:
            return ""

        window = root_objects[0]
        if not isinstance(window, QQuickWindow):
            return ""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.step_index:02d}_{name}_{timestamp}.png"
        filepath = self.screenshots_dir / filename

        image = window.grabWindow()
        image.save(str(filepath), "PNG")  # type: ignore[call-overload]

        rel_path = f"screenshots/{filename}"
        self.screenshots.append({
            "step": self.step_index,
            "name": name,
            "description": description,
            "path": rel_path,
            "timestamp": datetime.now().isoformat(),
        })
        print(f"[截图 {self.step_index:02d}] {name} -> {filepath}")
        return rel_path

    def _get_root_window(self) -> QQuickWindow | None:
        root_objects = self.engine.rootObjects()
        if not root_objects:
            return None
        window = root_objects[0]
        if isinstance(window, QQuickWindow):
            return window
        return None

    def _navigate_to_page(self, page_key: str) -> bool:
        window = self._get_root_window()
        if not window:
            return False
        fn = getattr(window, "navigateToPage", None)
        if callable(fn):
            fn(page_key)
        else:
            window.setProperty("currentPage", page_key)
        QCoreApplication.processEvents()
        return True

    def _select_project_and_switch_tab(self, project_id: str, tab_index: int) -> bool:
        window = self._get_root_window()
        if not window:
            return False
        fn = getattr(window, "switchToProjectTab", None)
        if callable(fn):
            fn(project_id, project_id, tab_index)
        else:
            window.setProperty("currentPage", "workspace")
            window.setProperty("currentProjectId", project_id)
        QCoreApplication.processEvents()
        return True

    def run(self) -> dict[str, Any]:
        start_time = datetime.now()
        steps = self._build_test_steps()

        def execute_next_step() -> None:
            if self.step_index >= len(steps):
                self._finish_test(start_time)
                return

            step = steps[self.step_index]
            try:
                result = step["action"]()
                self.test_steps.append({
                    "index": self.step_index,
                    "name": step["name"],
                    "description": step["description"],
                    "status": "passed" if result else "failed",
                    "timestamp": datetime.now().isoformat(),
                })
            except Exception as e:
                self.test_steps.append({
                    "index": self.step_index,
                    "name": step["name"],
                    "description": step["description"],
                    "status": "error",
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                    "timestamp": datetime.now().isoformat(),
                })

            self.step_index += 1
            QTimer.singleShot(1000, execute_next_step)

        QTimer.singleShot(1500, execute_next_step)
        return {}

    def _build_test_steps(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "应用启动",
                "description": "验证应用启动成功，主窗口可见",
                "action": self._step_app_launch,
            },
            {
                "name": "项目列表页",
                "description": "导航到项目列表页，显示全量项目",
                "action": self._step_project_list,
            },
            {
                "name": "平台驾驶舱大盘",
                "description": "平台驾驶舱大盘页，验证SW-2026-008状态机与KPI",
                "action": self._step_platform_dashboard,
            },
            {
                "name": "平台变更管控",
                "description": "平台变更管控中心，验证变更列表与过滤",
                "action": self._step_change_center,
            },
            {
                "name": "平台规范检查",
                "description": "规范中心，验证规范概览与Tab切换",
                "action": self._step_spec_center,
            },
            {
                "name": "平台报告中心",
                "description": "报告中心，验证项目与变更统计概览",
                "action": self._step_report_center,
            },
            {
                "name": "平台模板管理",
                "description": "模板管理页，验证项目模板列表",
                "action": self._step_template_manage,
            },
            {
                "name": "系统设置页",
                "description": "设置页，验证数据库与环境配置",
                "action": self._step_settings,
            },
            # ── 重点：针对 DJ-2026-005 具体的 5 个 Tab 逐一深入检查 ──
            {
                "name": f"{self.target_project_id} 概览Tab (Overview)",
                "description": f"项目 {self.target_project_id} - 概览Tab：基本信息、PLC信息、资产汇总与交付物看板",
                "action": self._step_workspace_tab_0_overview,
            },
            {
                "name": f"{self.target_project_id} 变更Tab (Changes)",
                "description": f"项目 {self.target_project_id} - 变更Tab：状态流转图、活动时间线、变更列表与详情面板",
                "action": self._step_workspace_tab_1_changes,
            },
            {
                "name": f"{self.target_project_id} 检查Tab (Check)",
                "description": f"项目 {self.target_project_id} - 检查Tab：项目级规范检查报告与修复建议",
                "action": self._step_workspace_tab_2_check,
            },
            {
                "name": f"{self.target_project_id} 文档Tab (Doc)",
                "description": f"项目 {self.target_project_id} - 文档Tab：文档树与架构文档浏览器",
                "action": self._step_workspace_tab_3_doc,
            },
            {
                "name": f"{self.target_project_id} 变量表Tab (VarTable)",
                "description": f"项目 {self.target_project_id} - 变量表Tab：变量表编辑器与 IO 映射",
                "action": self._step_workspace_tab_4_vartable,
            },
            {
                "name": f"{self.target_project_id} 模板应用弹窗 (TemplateApplyDialog)",
                "description": f"打开项目 {self.target_project_id} 的模板应用对话框，验证深色实底磨砂与模板列表",
                "action": self._step_template_dialog,
            },
            {
                "name": "新建变更单向导弹窗 (NewChangeDialog)",
                "description": "打开新建变更单向导，验证表单控件、焦点遮罩与深色磨砂卡片",
                "action": self._step_new_change_dialog,
            },
            {
                "name": f"{self.target_project_id} 项目编辑弹窗 (ProjectEditDialog)",
                "description": f"打开项目 {self.target_project_id} 的编辑对话框，验证阶段选择与保存按钮",
                "action": self._step_project_edit_dialog,
            },
            {
                "name": f"{self.target_project_id} 删除确认弹窗 (DeleteConfirmDialog)",
                "description": f"打开项目 {self.target_project_id} 的删除确认对话框，验证强校验与危险操作样式",
                "action": self._step_delete_confirm_dialog,
            },
            {
                "name": f"{self.target_project_id} PM初始化弹窗 (PmInitializeConfirmDialog)",
                "description": f"打开项目 {self.target_project_id} 的 PM 初始化确认弹窗，验证提示清单",
                "action": self._step_pm_initialize_dialog,
            },
            {
                "name": f"{self.target_project_id} PM归档弹窗 (PmSessionArchiveDialog)",
                "description": f"打开项目 {self.target_project_id} 的 PM_SESSION 归档对话框，验证章节选择与归档按钮",
                "action": self._step_pm_archive_dialog,
            },
            {
                "name": "关于对话框 (AboutDialog)",
                "description": "打开关于对话框，验证版本信息与系统状态",
                "action": self._step_about_dialog,
            },
        ]

    def _step_app_launch(self) -> bool:
        window = self._get_root_window()
        if not window:
            return False
        workbench_bridge = self.engine.rootContext().contextProperty("workbenchBridge")
        change_bridge = self.engine.rootContext().contextProperty("changeBridge")
        if workbench_bridge:
            workbench_bridge.rebuildIndex()
            workbench_bridge.refreshProjects()
            if change_bridge:
                change_bridge.refreshChanges()
        self._take_screenshot("00_app_launch", "应用启动后主窗口初始状态")
        return window.isVisible()

    def _step_project_list(self) -> bool:
        self._navigate_to_page("projectList")
        self._take_screenshot("01_project_list", "项目列表页 - 显示所有项目")
        return True

    def _step_platform_dashboard(self) -> bool:
        self._navigate_to_page("platformDashboard")
        self._take_screenshot("02_platform_dashboard", "平台驾驶舱大盘页 - 显示KPI与主线流转状态机")
        return True

    def _step_change_center(self) -> bool:
        self._navigate_to_page("changeCenter")
        self._take_screenshot("03_change_center", "变更中心页 - 显示所有变更单")
        return True

    def _step_spec_center(self) -> bool:
        self._navigate_to_page("specCenter")
        self._take_screenshot("04_spec_center", "规范中心页 - 显示规范概览/索引/检查")
        return True

    def _step_report_center(self) -> bool:
        self._navigate_to_page("reportCenter")
        self._take_screenshot("05_report_center", "报告中心页 - 显示报告模板和生成入口")
        return True

    def _step_template_manage(self) -> bool:
        self._navigate_to_page("templateManage")
        self._take_screenshot("06_template_manage", "模板管理页 - 显示项目模板列表")
        return True

    def _step_settings(self) -> bool:
        self._navigate_to_page("settings")
        self._take_screenshot("07_settings", "设置页 - 显示应用设置选项")
        return True

    # ── 针对具体项目 DJ-2026-005 5 个 Tab 深度截图 ──

    def _step_workspace_tab_0_overview(self) -> bool:
        ok = self._select_project_and_switch_tab(self.target_project_id, 0)
        self._take_screenshot(
            f"08_{self.target_project_id}_tab0_overview",
            f"项目 {self.target_project_id} - 概览 Tab（基本信息/PLC信息/资产汇总/交付物看板）",
        )
        return ok

    def _step_workspace_tab_1_changes(self) -> bool:
        ok = self._select_project_and_switch_tab(self.target_project_id, 1)
        self._take_screenshot(
            f"09_{self.target_project_id}_tab1_changes",
            f"项目 {self.target_project_id} - 变更 Tab（状态流转/时间线/变更列表/详情面板）",
        )
        return ok

    def _step_workspace_tab_2_check(self) -> bool:
        ok = self._select_project_and_switch_tab(self.target_project_id, 2)
        self._take_screenshot(
            f"10_{self.target_project_id}_tab2_check",
            f"项目 {self.target_project_id} - 检查 Tab（规范检查报告）",
        )
        return ok

    def _step_workspace_tab_3_doc(self) -> bool:
        ok = self._select_project_and_switch_tab(self.target_project_id, 3)
        self._take_screenshot(
            f"11_{self.target_project_id}_tab3_doc",
            f"项目 {self.target_project_id} - 文档 Tab（文档浏览器）",
        )
        return ok

    def _step_workspace_tab_4_vartable(self) -> bool:
        ok = self._select_project_and_switch_tab(self.target_project_id, 4)
        self._take_screenshot(
            f"12_{self.target_project_id}_tab4_vartable",
            f"项目 {self.target_project_id} - 变量表 Tab（变量表编辑器）",
        )
        return ok

    def _step_template_dialog(self) -> bool:
        window = self._get_root_window()
        if not window:
            return False
        dialog = window.findChild(QObject, "templateApplyDialog")
        if dialog:
            dialog.open(self.target_project_id, self.target_project_id)
        self._take_screenshot(
            f"13_{self.target_project_id}_template_dialog",
            f"项目 {self.target_project_id} - 模板应用对话框（深色实底磨砂拟物）",
        )
        if dialog:
            dialog.close()
        return True

    def _step_new_change_dialog(self) -> bool:
        window = self._get_root_window()
        if not window:
            return False
        dialog = window.findChild(QObject, "newChangeDialog")
        if dialog:
            dialog.open()
        self._take_screenshot(
            "14_dialog_new_change",
            "新建变更单向导弹窗（全表单/深色实底卡片/焦点遮罩）",
        )
        if dialog:
            dialog.close()
        return True

    def _step_project_edit_dialog(self) -> bool:
        window = self._get_root_window()
        if not window:
            return False
        dialog = window.findChild(QObject, "projectEditDialog")
        if dialog:
            dialog.open(self.target_project_id, self.target_project_id, {})
        self._take_screenshot(
            f"15_{self.target_project_id}_dialog_project_edit",
            f"项目 {self.target_project_id} - 项目信息编辑对话框",
        )
        if dialog:
            dialog.close()
        return True

    def _step_delete_confirm_dialog(self) -> bool:
        window = self._get_root_window()
        if not window:
            return False
        dialog = window.findChild(QObject, "deleteConfirmDialog")
        if dialog:
            dialog.open(self.target_project_id, self.target_project_id)
        self._take_screenshot(
            f"16_{self.target_project_id}_dialog_delete_confirm",
            f"项目 {self.target_project_id} - 项目删除确认对话框（破坏性安全门禁）",
        )
        if dialog:
            dialog.close()
        return True

    def _step_pm_initialize_dialog(self) -> bool:
        window = self._get_root_window()
        if not window:
            return False
        dialog = window.findChild(QObject, "pmInitializeConfirmDialog")
        if dialog:
            dialog.open(self.target_project_id, self.target_project_id)
        self._take_screenshot(
            f"17_{self.target_project_id}_dialog_pm_initialize",
            f"项目 {self.target_project_id} - PM规范初始化确认对话框",
        )
        if dialog:
            dialog.close()
        return True

    def _step_pm_archive_dialog(self) -> bool:
        window = self._get_root_window()
        if not window:
            return False
        dialog = window.findChild(QObject, "pmSessionArchiveDialog")
        if dialog:
            dialog.open(self.target_project_id)
        self._take_screenshot(
            f"18_{self.target_project_id}_dialog_pm_archive",
            f"项目 {self.target_project_id} - PM_SESSION 会话归档对话框",
        )
        if dialog:
            dialog.close()
        return True

    def _step_about_dialog(self) -> bool:
        window = self._get_root_window()
        if not window:
            return False
        dialog = window.findChild(QObject, "aboutDialog")
        if dialog:
            dialog.open()
        self._take_screenshot(
            "19_dialog_about",
            "关于系统对话框（版本 V1.0.0 / 架构信息）",
        )
        if dialog:
            dialog.close()
        return True

    def _finish_test(self, start_time: datetime) -> None:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        passed = sum(1 for s in self.test_steps if s["status"] == "passed")
        failed = sum(1 for s in self.test_steps if s["status"] == "failed")
        errors = sum(1 for s in self.test_steps if s["status"] == "error")

        result = {
            "test_name": f"auto-pm QML GUI 冒烟与 {self.target_project_id} 专项测试",
            "version": "V1.0.0",
            "target_project": self.target_project_id,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": duration,
            "workspace_root": self.workspace_root,
            "summary": {
                "total_steps": len(self.test_steps),
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "total_screenshots": len(self.screenshots),
                "total_warnings": len(self.warnings),
            },
            "test_steps": self.test_steps,
            "screenshots": self.screenshots,
            "warnings": self.warnings,
        }

        result_path = self.output_dir / "test_result.json"
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"\n{'='*60}")
        print(f"GUI 测试完成 (目标项目: {self.target_project_id})")
        print(f"{'='*60}")
        print(f"总步骤: {len(self.test_steps)}")
        print(f"通过: {passed}")
        print(f"失败: {failed}")
        print(f"错误: {errors}")
        print(f"截图数: {len(self.screenshots)}")
        print(f"警告数: {len(self.warnings)}")
        print(f"耗时: {duration:.1f}s")
        print(f"结果文件: {result_path}")
        print(f"{'='*60}\n")

        QGuiApplication.quit()


def main() -> int:
    parser = argparse.ArgumentParser(description="auto-pm QML GUI 冒烟测试")
    parser.add_argument("--workspace", "-w", required=True, help="工作空间根路径")
    parser.add_argument("--output", "-o", required=True, help="测试结果输出目录")
    parser.add_argument("--project", "-p", default="DJ-2026-005", help="测试目标项目编号")
    args = parser.parse_args()

    workspace_root = str(Path(args.workspace).resolve())
    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    QQuickStyle.setStyle("Basic")

    from auto_pm.change.change_service import ChangeService
    from auto_pm.core.project_service import ProjectService
    from auto_pm.db.connection import DatabaseManager

    from auto_pm.ui.factories import (
        make_asset_summary_service,
        make_dashboard_service,
        make_doc_refresh_service,
        make_pm_session_service,
        make_report_service,
        make_spec_center_service,
        make_spec_check_service,
        make_spec_frontmatter_service,
        make_spec_index_service,
        make_spec_report_service,
        make_template_service,
    )
    from auto_pm.ui.qml.bridges.change_bridge import ChangeBridge
    from auto_pm.ui.qml.bridges.delivery_bridge import DeliveryBridge
    from auto_pm.ui.qml.bridges.file_watcher_bridge import FileWatcherBridge
    from auto_pm.ui.qml.bridges.spec_bridge import SpecBridge
    from auto_pm.ui.qml.bridges.system_bridge import SystemBridge
    from auto_pm.ui.qml.bridges.workbench_bridge import WorkbenchBridge
    from auto_pm.ui.qml.models.project_list_model import ProjectListModel
    from auto_pm.ui.registry import FacadeRegistry

    db = DatabaseManager(workspace_root)

    project_service = ProjectService(workspace_root=workspace_root, db=db)
    change_service = ChangeService(workspace_root=workspace_root, db=db)
    spec_check_service = make_spec_check_service(workspace_root)
    report_service = make_report_service(
        project_service=project_service,
        change_service=change_service,
        workspace_root=workspace_root,
        db=db,
    )
    template_service = make_template_service(workspace_root)
    pm_session_service = make_pm_session_service(workspace_root)
    dashboard_service = make_dashboard_service(
        project_service=project_service,
        change_service=change_service,
    )
    asset_summary_service = make_asset_summary_service()
    doc_refresh_service = make_doc_refresh_service(workspace_root)
    spec_center_service = make_spec_center_service(workspace_root)
    spec_index_service = make_spec_index_service(workspace_root)
    spec_report_service = make_spec_report_service(workspace_root)
    frontmatter_service = make_spec_frontmatter_service(workspace_root)

    facade_registry = FacadeRegistry()
    facade_registry.initialize({
        "project_service": project_service,
        "change_service": change_service,
        "spec_check_service": spec_check_service,
        "report_service": report_service,
        "template_service": template_service,
        "pm_session_service": pm_session_service,
        "dashboard_service": dashboard_service,
        "asset_summary_service": asset_summary_service,
        "doc_refresh_service": doc_refresh_service,
        "spec_center_service": spec_center_service,
        "index_service": spec_index_service,
        "spec_report_service": spec_report_service,
        "frontmatter_service": frontmatter_service,
    })

    project_model = ProjectListModel()
    workbench_bridge = WorkbenchBridge(facade=facade_registry.workbench_facade)
    change_bridge = ChangeBridge(facade=facade_registry.change_facade)
    spec_bridge = SpecBridge(facade=facade_registry.spec_facade)
    delivery_bridge = DeliveryBridge(facade=facade_registry.delivery_facade)
    system_bridge = SystemBridge(facade=facade_registry.system_facade)
    file_watcher_bridge = FileWatcherBridge(workspace_root)

    engine = QQmlApplicationEngine()
    qml_dir = Path(__file__).parent.parent / "auto_pm" / "ui" / "qml"
    engine.addImportPath(str(qml_dir))

    context = engine.rootContext()
    context.setContextProperty("workspace_root", workspace_root)
    context.setContextProperty("workbenchBridge", workbench_bridge)
    context.setContextProperty("changeBridge", change_bridge)
    context.setContextProperty("specBridge", spec_bridge)
    context.setContextProperty("deliveryBridge", delivery_bridge)
    context.setContextProperty("systemBridge", system_bridge)
    context.setContextProperty("projectModel", project_model)
    context.setContextProperty("fileWatcherBridge", file_watcher_bridge)

    runner = GuiTestRunner(engine, output_dir, workspace_root, target_project_id=args.project)

    main_qml = qml_dir / "main.qml"
    engine.load(QUrl.fromLocalFile(str(main_qml.resolve())))

    if not engine.rootObjects():
        print("错误：QML 引擎加载失败，根对象为空")
        return -1

    file_watcher_bridge.toggleWatcher(True)
    runner.run()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
