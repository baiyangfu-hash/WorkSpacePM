"""PLC-HMI 概念映射：主程序入口（启动流程）

像 PLC 的启动流程：上电 → 初始化 OB1 → 启动 HMI。
1. 创建 QGuiApplication（HMI 运行时）
2. 初始化所有 Service（DB 数据块）
3. 调用 OB1（FacadeRegistry.initialize）装配 FB
4. 创建 Bridge（HMI 变量表）注入 QML 上下文
5. 加载 main.qml（主画面）

--- 原始注释 ---
QML 主窗口入口（V0.9.0 QML 单入口）

用 QQmlApplicationEngine 加载 main.qml，通过 rootContext() 注入 5 个域 Bridge
（Workbench/Change/Spec/Delivery/System）+ ProjectListModel。

版本演进：
- V0.6.0 Week 1 PoC：QmlBridge + ProjectListModel 基础入口
- V0.8.0 Phase 1+2：扩展注入 6 个新 Service + SpecCenterAdapter
- V0.9.0：旧 QWidget main_window.py 完整移除，QML 成为唯一 GUI 入口；
  CLI 标志 --qml/--qwidget 退役，gui_command 简化为 (ctx, debug)；
  QmlBridge 拆分为 5 个域 Bridge（change/workbench/delivery/system/spec）

启动方式：
    auto-pm gui
    auto-pm gui --debug

设计参考：02_设计/GUI原型设计.md §15.4 QML 架构设计
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from auto_pm.change.change_service import ChangeService
from auto_pm.core.project_service import ProjectService
from auto_pm.modbus.modbus_bridge import ModbusBridge  # Modbus 联调工坊 Bridge
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
from auto_pm.ui.qml.bridges.ai_context_bridge import AiContextBridge
from auto_pm.ui.qml.bridges.change_bridge import ChangeBridge
from auto_pm.ui.qml.bridges.delivery_bridge import DeliveryBridge
from auto_pm.ui.qml.bridges.file_watcher_bridge import FileWatcherBridge
from auto_pm.ui.qml.bridges.spec_bridge import SpecBridge
from auto_pm.ui.qml.bridges.system_bridge import SystemBridge
from auto_pm.ui.qml.bridges.workbench_bridge import WorkbenchBridge
from auto_pm.ui.qml.models.project_list_model import ProjectListModel
from auto_pm.ui.qml.models.var_table_model import VarTableModel
from auto_pm.ui.registry import FacadeRegistry

log = logging.getLogger(__name__)


def run_qml_gui(workspace_root: str, debug: bool = False) -> int:
    """启动 QML GUI（V0.9.0 QML 单入口）

    初始化 10 个后端 Service + FacadeRegistry + 5 个域 Bridge，加载 main.qml。

    Args:
        workspace_root: 工作空间根路径
        debug: 是否开启调试日志

    Returns:
        应用退出码
    """
    # 1. 创建 QGuiApplication（QML 应用用 QGuiApplication 而非 QApplication）
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)

    # 1.5 设置 Basic 样式（支持控件 background 自定义，消除原生样式警告）
    QQuickStyle.setStyle("Basic")

    # 1.8 初始化 DatabaseManager 并注入
    from auto_pm.db.connection import DatabaseManager
    db = DatabaseManager(workspace_root)

    # 2. 初始化后端 Service（后端零改动约束：直接复用现有 Service）
    project_service = ProjectService(workspace_root=workspace_root, db=db)
    change_service = ChangeService(workspace_root=workspace_root, db=db)

    # 2.1 自动执行增量索引同步（自愈机制，解决文件变更后 GUI 缓存状态不符问题）
    try:
        project_service.sync_to_cache()
    except Exception as exc:
        sys.stderr.write(f"[WARNING] 启动时自动同步数据库索引失败: {exc}\n")

    # 2.2 启动时自动执行项目台账对账自愈（自愈机制）
    try:
        from auto_pm.change.ledger_reconciler import LedgerReconciler
        reconciler = LedgerReconciler()
        for proj in project_service.list_projects():
            try:
                reconciler.auto_fix(proj.path)
            except Exception as e:
                sys.stderr.write(f"[WARNING] 项目 {proj.project_id} 启动自动对账失败: {e}\n")
    except Exception as exc:
        sys.stderr.write(f"[WARNING] 启动时自动对账失败: {exc}\n")

    spec_check_service = make_spec_check_service(workspace_root)
    # V0.8.0 Phase 1 新增 6 个 Service（CHG-090）
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
        workspace_root=workspace_root,
    )
    asset_summary_service = make_asset_summary_service()
    doc_refresh_service = make_doc_refresh_service(workspace_root)
    # V0.8.0 Phase 2 新增 SpecCenterAdapter（CHG-091）
    spec_center_service = make_spec_center_service(workspace_root)
    # M5 CHG-119 新增 IndexService（规范索引生成）
    spec_index_service = make_spec_index_service(workspace_root)
    # M5 CHG-120 新增 Spec 域 ReportService（规范报告生成）
    spec_report_service = make_spec_report_service(workspace_root)
    # M5 CHG-121 新增 FrontmatterService（规范 Frontmatter 检查/修复）
    frontmatter_service = make_spec_frontmatter_service(workspace_root)

    # M1 阶段：初始化 FacadeRegistry
    registry = FacadeRegistry()
    registry.initialize({
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

    if debug:
        sys.stderr.write(
            f"[DEBUG] Service 初始化:\n"
            f"  project=✓ change=✓ spec="
            f"{'✓' if spec_check_service else '✗（无 spec_registry.json）'}\n"
            f"  report={'✓' if report_service else '✗'} "
            f"template={'✓' if template_service else '✗'} "
            f"pm_session={'✓' if pm_session_service else '✗'}\n"
            f"  dashboard={'✓' if dashboard_service else '✗'} "
            f"asset_summary={'✓' if asset_summary_service else '✗'} "
            f"doc_refresh={'✓' if doc_refresh_service else '✗'}\n"
            f"  spec_center={'✓' if spec_center_service else '✗（无 spec_registry.json）'} "
            f"spec_index={'✓' if spec_index_service else '✗（无 spec_registry.json）'} "
            f"spec_report={'✓' if spec_report_service else '✗（无 spec_registry.json）'} "
            f"frontmatter={'✓' if frontmatter_service else '✗（无 spec_registry.json）'}\n"
        )

    # 3. 创建 QML 桥接对象
    workbench_bridge = WorkbenchBridge(facade=registry.workbench_facade)
    change_bridge = ChangeBridge(facade=registry.change_facade)
    spec_bridge = SpecBridge(facade=registry.spec_facade)
    delivery_bridge = DeliveryBridge(facade=registry.delivery_facade)
    system_bridge = SystemBridge(facade=registry.system_facade)
    ai_context_bridge = AiContextBridge(workspace_root=workspace_root)
    project_model = ProjectListModel()
    var_table_model = VarTableModel()
    modbus_bridge = ModbusBridge()  # Modbus 联调工坊 Bridge（无依赖 Service，直接实例化）
    # FileWatcherBridge：监听业务文件变化 → 后台 sync_to_cache → syncFinished 驱动 QML 刷新
    # 消除 CLI 改文件后 GUI 缓存鸿沟（CHG-SCPT-2026-141）。自建 DB 连接，不依赖共享 db。
    file_watcher_bridge = FileWatcherBridge(workspace_root)

    # 3.5 注册运行时工作空间切换重载回调
    def reload_workspace(new_path: str) -> dict[str, object]:
        nonlocal db
        old_workspace_root = registry.workbench_facade._project_service.workspace_root if registry.workbench_facade else workspace_root
        new_db = None
        try:
            # 1. 先在旁路构建新运行态，成功后再切换，避免旧运行态半失效
            from auto_pm.db.connection import DatabaseManager
            new_db = DatabaseManager(new_path)
            new_db.init_schema()

            # 2. 重新创建所有 Services
            new_project_service = ProjectService(workspace_root=new_path, db=new_db)
            new_change_service = ChangeService(workspace_root=new_path, db=new_db)
            # 同步缓存
            try:
                new_project_service.sync_to_cache()
            except Exception as exc:
                sys.stderr.write(f"[WARNING] 切换工作空间自动同步数据库索引失败: {exc}\n")

            # 自动对账自愈
            try:
                from auto_pm.change.ledger_reconciler import LedgerReconciler
                reconciler = LedgerReconciler()
                for proj in new_project_service.list_projects():
                    try:
                        reconciler.auto_fix(proj.path)
                    except Exception as e:
                        sys.stderr.write(f"[WARNING] 项目 {proj.project_id} 切换自动对账失败: {e}\n")
            except Exception as exc:
                sys.stderr.write(f"[WARNING] 切换时自动对账失败: {exc}\n")

            new_spec_check_service = make_spec_check_service(new_path)
            new_report_service = make_report_service(
                project_service=new_project_service,
                change_service=new_change_service,
                workspace_root=new_path,
                db=new_db,
            )
            new_template_service = make_template_service(new_path)
            new_pm_session_service = make_pm_session_service(new_path)
            new_dashboard_service = make_dashboard_service(
                project_service=new_project_service,
                change_service=new_change_service,
                workspace_root=new_path,
            )
            new_asset_summary_service = make_asset_summary_service()
            new_doc_refresh_service = make_doc_refresh_service(new_path)
            new_spec_center_service = make_spec_center_service(new_path)
            new_spec_index_service = make_spec_index_service(new_path)
            new_spec_report_service = make_spec_report_service(new_path)
            new_frontmatter_service = make_spec_frontmatter_service(new_path)

            # 3. 新运行态准备完成后，再做切换
            file_watcher_bridge.prepareForReload()
            db.close()
            db = new_db

            # 4. 重建 Facades 并更新 registry
            registry.initialize({
                "project_service": new_project_service,
                "change_service": new_change_service,
                "spec_check_service": new_spec_check_service,
                "report_service": new_report_service,
                "template_service": new_template_service,
                "pm_session_service": new_pm_session_service,
                "dashboard_service": new_dashboard_service,
                "asset_summary_service": new_asset_summary_service,
                "doc_refresh_service": new_doc_refresh_service,
                "spec_center_service": new_spec_center_service,
                "index_service": new_spec_index_service,
                "spec_report_service": new_spec_report_service,
                "frontmatter_service": new_frontmatter_service,
            })

            # 5. 更新所有 Bridges 的 Facade 引用并通知刷新
            workbench_bridge.set_facade(registry.workbench_facade)
            change_bridge.set_facade(registry.change_facade)
            spec_bridge.set_facade(registry.spec_facade)
            delivery_bridge.set_facade(registry.delivery_facade)
            system_bridge.set_facade(registry.system_facade)
            ai_context_bridge.setWorkspaceRoot(new_path)

            # 6. 重建文件监听（更新工作空间路径，恢复监听）
            file_watcher_bridge.rebuild(new_path)
            log.info("工作空间已成功重载并同步：%s", new_path)
            return {
                "success": True,
                "message": f"运行态已重载: {new_path}",
                "workspace_root": new_path,
            }
        except Exception as e:
            sys.stderr.write(f"[ERROR] 重载工作空间失败: {e}\n")
            log.exception("重载工作空间失败")
            if new_db is not None and new_db is not db:
                try:
                    new_db.close()
                except Exception:
                    log.warning("关闭失败的新数据库连接时出错", exc_info=True)
            return {
                "success": False,
                "message": str(e),
                "workspace_root": old_workspace_root,
            }

    registry.reload_callback = reload_workspace
    if registry.workbench_facade:
        registry.workbench_facade._reload_callback = reload_workspace

    # 4. 加载 main.qml
    qml_dir = Path(__file__).parent / "qml"
    main_qml_path = qml_dir / "main.qml"

    if not main_qml_path.exists():
        sys.stderr.write(f"[ERROR] main.qml 不存在: {main_qml_path}\n")
        return 1

    engine = QQmlApplicationEngine()

    # 5. 注入 context property（QML 端通过 xxxBridge / projectModel 访问）
    engine.rootContext().setContextProperty("workbenchBridge", workbench_bridge)
    engine.rootContext().setContextProperty("changeBridge", change_bridge)
    engine.rootContext().setContextProperty("specBridge", spec_bridge)
    engine.rootContext().setContextProperty("deliveryBridge", delivery_bridge)
    engine.rootContext().setContextProperty("systemBridge", system_bridge)
    engine.rootContext().setContextProperty("projectModel", project_model)
    engine.rootContext().setContextProperty("varTableModel", var_table_model)
    engine.rootContext().setContextProperty("modbusBridge", modbus_bridge)  # Modbus 联调工坊
    engine.rootContext().setContextProperty("aiContextBridge", ai_context_bridge)  # AI 上下文桥接
    engine.rootContext().setContextProperty("fileWatcherBridge", file_watcher_bridge)  # 文件监听同步

    # 6. 加载 QML 文件
    qml_url = QUrl.fromLocalFile(str(main_qml_path))
    engine.load(qml_url)

    # 7. 检查加载结果
    if not engine.rootObjects():
        sys.stderr.write("[ERROR] QML 加载失败，rootObjects() 为空\n")
        return 1

    root_obj: QObject = engine.rootObjects()[0]
    if debug:
        sys.stderr.write(f"[DEBUG] QML root object: {type(root_obj).__name__}\n")
        sys.stderr.write(f"[DEBUG] workspace_root: {workspace_root}\n")

    # 7.5 启动文件监听（用户要求：每次启动 GUI 时开始监听业务文件变化）
    # 2.1 已完成首次阻塞式 sync_to_cache 保证缓存新鲜，此处仅启用监听处理运行时变更。
    file_watcher_bridge.toggleWatcher(True)
    if debug:
        sys.stderr.write(
            f"[DEBUG] 文件监听已启用，监听目录数: "
            f"{file_watcher_bridge.watchedDirectoryCount()}\n"
        )

    # 8. 启动事件循环
    return app.exec()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write("用法: python -m auto_pm.ui.qml_main_window <workspace_root>\n")
        sys.exit(1)
    workspace = os.path.abspath(sys.argv[1])
    sys.exit(run_qml_gui(workspace_root=workspace, debug="--debug" in sys.argv))
