"""Protocol 接口契约测试（M3-Iter3）

验证 ProjectService / ChangeService 实现了对应的 Protocol 接口。
Protocol 是结构性子类型，无需显式继承，只要方法签名匹配即可。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 将项目根目录加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from auto_pm.application.core.project_scanner import ProjectScanner  # noqa: E402
from auto_pm.application.core.project_service import ProjectService  # noqa: E402
from auto_pm.application.core.protocols import (  # noqa: E402
    ChangeServiceProtocol,
    ProjectScannerProtocol,
    ProjectServiceProtocol,
)
from auto_pm.domain.change.change_service import ChangeService  # noqa: E402


class TestProtocolConformance:
    """验证 Service 类实现对应 Protocol 接口"""

    def test_project_service_implements_protocol(self, tmp_path: Path) -> None:
        """ProjectService 实现 ProjectServiceProtocol"""
        svc = ProjectService(str(tmp_path))
        assert isinstance(svc, ProjectServiceProtocol)

    def test_project_service_has_service_protocol(self, tmp_path: Path) -> None:
        """ProjectService 实现 ServiceProtocol（基础接口）"""
        svc = ProjectService(str(tmp_path))
        # ServiceProtocol 要求 workspace_root 属性
        assert hasattr(svc, "workspace_root")
        assert isinstance(svc.workspace_root, str)

    def test_project_scanner_implements_protocol(self, tmp_path: Path) -> None:
        """ProjectScanner 实现 ProjectScannerProtocol"""
        scanner = ProjectScanner(str(tmp_path))
        assert isinstance(scanner, ProjectScannerProtocol)

    def test_change_service_implements_protocol(self, tmp_path: Path) -> None:
        """ChangeService 实现 ChangeServiceProtocol"""
        svc = ChangeService(str(tmp_path))
        assert isinstance(svc, ChangeServiceProtocol)


class TestProtocolMethodSignatures:
    """验证 Protocol 定义的方法在 Service 中存在"""

    def test_project_service_protocol_methods(self, tmp_path: Path) -> None:
        """ProjectService 包含 Protocol 定义的所有方法"""
        svc = ProjectService(str(tmp_path))
        required_methods = [
            "list_projects",
            "get_project",
            "find_project_path",
            "search_projects",
            "import_project",
            "update_project_meta",
            "list_projects_filtered",
            "list_projects_with_change_count",
            "sync_to_cache",
        ]
        for method_name in required_methods:
            assert callable(getattr(svc, method_name, None)), (
                f"ProjectService 缺少方法: {method_name}"
            )

    def test_change_service_protocol_methods(self, tmp_path: Path) -> None:
        """ChangeService 包含 Protocol 定义的所有方法"""
        svc = ChangeService(str(tmp_path))
        required_methods = [
            "create_change_request",
            "list_change_requests",
            "get_change_request",
            "transition_status",
            "list_all_changes",
            "update_change_request",
            "delete_change_request",
        ]
        for method_name in required_methods:
            assert callable(getattr(svc, method_name, None)), (
                f"ChangeService 缺少方法: {method_name}"
            )

    def test_project_scanner_protocol_methods(self, tmp_path: Path) -> None:
        """ProjectScanner 包含 Protocol 定义的所有方法"""
        scanner = ProjectScanner(str(tmp_path))
        required_methods = ["scan", "try_identify_project"]
        for method_name in required_methods:
            assert callable(getattr(scanner, method_name, None)), (
                f"ProjectScanner 缺少方法: {method_name}"
            )


class TestProtocolForDependencyInjection:
    """验证 Protocol 可用于依赖注入场景

    UI/CLI 层可以用 Protocol 类型注解，传入具体 Service 实例。
    """

    def test_project_service_as_protocol(self, tmp_path: Path) -> None:
        """ProjectService 可赋值给 ProjectServiceProtocol 类型变量"""
        svc: ProjectServiceProtocol = ProjectService(str(tmp_path))
        # 调用 Protocol 定义的方法
        result = svc.list_projects(scan_depth=1)
        assert isinstance(result, list)

    def test_change_service_as_protocol(self, tmp_path: Path) -> None:
        """ChangeService 可赋值给 ChangeServiceProtocol 类型变量"""
        svc: ChangeServiceProtocol = ChangeService(str(tmp_path))
        # 调用 Protocol 定义的方法
        result = svc.list_all_changes()
        assert isinstance(result, list)

    def test_scanner_as_protocol(self, tmp_path: Path) -> None:
        """ProjectScanner 可赋值给 ProjectScannerProtocol 类型变量"""
        scanner: ProjectScannerProtocol = ProjectScanner(str(tmp_path))
        result = scanner.scan(scan_depth=1)
        assert isinstance(result, list)
