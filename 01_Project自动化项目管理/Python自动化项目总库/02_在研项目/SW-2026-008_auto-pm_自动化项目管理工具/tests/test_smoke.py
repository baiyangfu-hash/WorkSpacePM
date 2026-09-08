"""冒烟测试（Smoke Tests）

核心功能快速验证，用于：
- CI/CD 流水线快速门禁
- 发布前快速回归
- GUI 全功能测试前的预检查

冒烟测试要求：
- 运行时间 < 30s
- 覆盖核心功能（项目扫描/变更管理/状态流转/规范索引/报告生成）
- 不依赖外部环境（不访问真实工作空间）
- 不运行 GUI 测试

运行方式：
    python scripts/run_tests.py smoke
    或
    python -m pytest -m smoke --tb=short -q --no-cov
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# 必须在导入 PySide6 前设置离屏渲染
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ── 核心模块导入测试 ─────────────────────────────────────


@pytest.mark.smoke
class TestCoreImports:
    """核心模块导入测试"""

    def test_import_project_service(self) -> None:
        """ProjectService 可导入"""
        from auto_pm.core.project_service import ProjectService
        assert ProjectService is not None

    def test_import_change_service(self) -> None:
        """ChangeService 可导入"""
        from auto_pm.change.change_service import ChangeService
        assert ChangeService is not None

    def test_import_report_service(self) -> None:
        """ReportService 可导入"""
        from auto_pm.core.report_service import ReportService
        assert ReportService is not None

    def test_import_plc_service(self) -> None:
        """PlcService 可导入"""
        from auto_pm.plc.service import PlcService
        assert PlcService is not None

    def test_import_protocols(self) -> None:
        """Protocol 接口可导入"""
        from auto_pm.core.protocols import (
            ChangeServiceProtocol,
            PlcServiceProtocol,
            ProjectServiceProtocol,
        )
        assert ProjectServiceProtocol is not None
        assert ChangeServiceProtocol is not None
        assert PlcServiceProtocol is not None

    def test_import_paths_constants(self) -> None:
        """路径常量可导入"""
        from auto_pm.core.paths import (
            WORKSPACE_PROJECTS_SUBDIR,
            get_projects_subdir,
        )
        assert WORKSPACE_PROJECTS_SUBDIR == "02_在研项目"
        assert get_projects_subdir("/tmp") is not None

    def test_import_constants(self) -> None:
        """业务常量可导入"""
        from auto_pm.core.constants import (
            BUSINESS_LINE_OPTIONS,
            STACK_TEMPLATE_MAP,
            get_template_name,
        )
        assert STACK_TEMPLATE_MAP is not None
        assert BUSINESS_LINE_OPTIONS is not None
        assert get_template_name("plc") == "plc-standard-project"


# ── 状态流转合法性测试 ─────────────────────────────────


@pytest.mark.smoke
class TestStatusFlow:
    """状态流转合法性测试"""

    def test_status_flow_defined(self) -> None:
        """STATUS_FLOW 已定义"""
        from auto_pm.change.constants import STATUS_FLOW
        assert "draft" in STATUS_FLOW
        assert "completed" in STATUS_FLOW
        assert "archived" in STATUS_FLOW

    def test_acceptance_flow_valid(self) -> None:
        """验收流程状态流转合法"""
        from auto_pm.change.constants import validate_status_transition
        validate_status_transition("implementing", "pending_acceptance")
        validate_status_transition("pending_acceptance", "accepting")
        validate_status_transition("accepting", "completed")

    def test_archive_flow_valid(self) -> None:
        """归档流程状态流转合法"""
        from auto_pm.change.constants import validate_status_transition
        validate_status_transition("completed", "archived")

    def test_rework_flow_valid(self) -> None:
        """返工路径状态流转合法"""
        from auto_pm.change.constants import validate_status_transition
        validate_status_transition("accepting", "implementing")

    def test_archived_is_terminal(self) -> None:
        """archived 是终态"""
        from auto_pm.change.constants import STATUS_FLOW
        assert STATUS_FLOW["archived"] == set()

    def test_status_labels_exist(self) -> None:
        """状态标签存在"""
        from auto_pm.change.constants import STATUS_LABELS
        assert STATUS_LABELS["draft"] == "草稿"
        assert STATUS_LABELS["completed"] == "已完成"
        assert STATUS_LABELS["archived"] == "已归档"


# ── ProjectService 基础功能测试 ────────────────────────


@pytest.mark.smoke
class TestProjectServiceBasic:
    """ProjectService 基础功能测试"""

    def test_instantiation(self, tmp_path: Path) -> None:
        """ProjectService 可实例化"""
        from auto_pm.core.project_service import ProjectService
        svc = ProjectService(str(tmp_path))
        assert svc is not None
        assert svc.workspace_root == str(tmp_path)

    def test_scanner_instantiation(self, tmp_path: Path) -> None:
        """ProjectScanner 可实例化"""
        from auto_pm.core.project_scanner import ProjectScanner
        scanner = ProjectScanner(str(tmp_path))
        assert scanner is not None
        assert scanner.workspace_root == str(tmp_path)

    def test_list_projects_empty(self, tmp_path: Path) -> None:
        """空工作空间返回空列表"""
        from auto_pm.core.project_service import ProjectService
        svc = ProjectService(str(tmp_path))
        projects = svc.list_projects()
        assert projects == []


# ── ChangeService 基础功能测试 ─────────────────────────


@pytest.mark.smoke
class TestChangeServiceBasic:
    """ChangeService 基础功能测试"""

    def test_instantiation(self, tmp_path: Path) -> None:
        """ChangeService 可实例化"""
        from auto_pm.change.change_service import ChangeService
        svc = ChangeService(str(tmp_path))
        assert svc is not None

    def test_list_all_changes_empty(self, tmp_path: Path) -> None:
        """空工作空间返回空变更列表"""
        from auto_pm.change.change_service import ChangeService
        svc = ChangeService(str(tmp_path))
        changes = svc.list_all_changes()
        assert changes == []


# ── ReportService 基础功能测试 ─────────────────────────


@pytest.mark.smoke
class TestReportServiceBasic:
    """ReportService 基础功能测试"""

    def test_report_types(self) -> None:
        """支持 4 种报告类型"""
        from auto_pm.change.change_service import ChangeService
        from auto_pm.core.project_service import ProjectService
        from auto_pm.core.report_service import ReportService

        ps = ProjectService.__new__(ProjectService)
        cs = ChangeService.__new__(ChangeService)
        svc = ReportService(ps, cs)
        types = svc.list_report_types()
        assert "project" in types
        assert "change" in types
        assert "spec" in types
        assert "scan" in types
        assert len(types) == 4


# ── 数据库连接测试 ─────────────────────────────────────


@pytest.mark.smoke
class TestDatabaseBasic:
    """数据库基础功能测试"""

    def test_database_manager_instantiation(self, tmp_path: Path) -> None:
        """DatabaseManager 可实例化"""
        from auto_pm.db.connection import DatabaseManager
        db = DatabaseManager(str(tmp_path))
        assert db is not None
        db.init_schema()

    def test_repositories_instantiation(self, tmp_path: Path) -> None:
        """Repository 可实例化"""
        from auto_pm.db.connection import DatabaseManager
        from auto_pm.db.repository import (
            ChangeRequestRepository,
            ProjectRepository,
            ScanLogRepository,
        )

        db = DatabaseManager(str(tmp_path))
        db.init_schema()

        proj_repo = ProjectRepository(db)
        change_repo = ChangeRequestRepository(db)
        scan_repo = ScanLogRepository(db)

        assert proj_repo is not None
        assert change_repo is not None
        assert scan_repo is not None


# ── CLI 入口测试 ───────────────────────────────────────


@pytest.mark.smoke
class TestCLIEntry:
    """CLI 入口测试"""

    def test_cli_module_importable(self) -> None:
        """CLI 模块可导入"""
        from auto_pm.cli.__main__ import cli
        assert callable(cli)

    def test_cli_help(self, capsys: pytest.CaptureFixture[str]) -> None:
        """CLI --help 正常工作"""
        from auto_pm.cli.__main__ import cli
        from click.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0


# ── QML 静态语法与完整性测试 ────────────────────────────


@pytest.mark.smoke
class TestQmlIntegrity:
    """QML 组件语法与加载完整性测试 (DEV-216/DEV-300)"""

    def test_all_qml_components_loadable(self) -> None:
        """所有 QML 文件必须能被 QQmlComponent 成功解析无语法错误"""
        from PySide6.QtCore import QCoreApplication, QUrl
        from PySide6.QtQml import QQmlComponent, QQmlEngine

        app = QCoreApplication.instance()
        if app is None:
            app = QCoreApplication([])

        engine = QQmlEngine()
        qml_dir = Path(__file__).parent.parent / "auto_pm" / "ui" / "qml"
        engine.addImportPath(str(qml_dir))
        engine.addImportPath(str(qml_dir / "components"))
        engine.addImportPath(str(qml_dir / "views"))
        engine.addImportPath(str(qml_dir / "views" / "workspace"))
        engine.addImportPath(str(qml_dir / "dialogs"))
        engine.addImportPath(str(qml_dir / "theme"))

        all_qml = list(qml_dir.rglob("*.qml"))
        assert len(all_qml) > 0, "未找到任何 QML 文件"

        errors: list[str] = []
        for qml_file in all_qml:
            component = QQmlComponent(engine, QUrl.fromLocalFile(str(qml_file)))
            if component.isError():
                err_msgs = "; ".join(e.toString() for e in component.errors())
                errors.append(f"{qml_file.name}: {err_msgs}")

        assert not errors, f"发现 {len(errors)} 个 QML 语法/加载错误:\n" + "\n".join(errors)

