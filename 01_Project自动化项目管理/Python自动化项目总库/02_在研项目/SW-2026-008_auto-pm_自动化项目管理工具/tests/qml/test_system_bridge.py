"""SystemBridge 单元测试（M4 第 2 批新增）

约束（与 tests/qml/conftest.py 一致）：
- qapp fixture 引用 tests/conftest.py 的 session 级 QApplication
- 不重新定义 qapp
- 全部用 Mock Facade，无文件系统/DB 依赖
- mock facade 用自定义 Mock 类（不使用 MagicMock），便于追踪调用参数

覆盖 SystemBridge 的 7 个 Slot：
- listTemplates() → list[str]
- getTemplatePath(template_name) → str
- getTemplateDetail(template_name) → dict（asdict 转换）
- getPmSessionView() → dict（asdict 转换）
- runPmSessionCheck() → dict（asdict 转换）
- applyTemplate(project_id, template_name) → dict（asdict 转换）
- archivePmSession(section, keepRecent, dryRun) → dict（asdict 转换，M5 CHG-117 新增）
"""

from __future__ import annotations

from typing import Any

from auto_pm.ui.contracts.dto.system_dto import (
    ApplyTemplateResultDTO,
    PmSessionArchiveResultDTO,
    PmSessionCheckResultDTO,
    PmSessionViewDTO,
    TemplateDetailDTO,
)
from auto_pm.ui.contracts.result import CommandResult, QueryResult


class _MockSystemFacade:
    """Mock SystemFacade，记录方法调用并返回预设结果。"""

    def __init__(  # type: ignore[no-untyped-def]
        self,
        list_templates_result=None,
        get_template_path_result=None,
        get_template_detail_result=None,
        pm_session_view_result=None,
        run_pm_session_check_result=None,
        apply_template_result=None,
        archive_pm_session_result=None,
    ) -> None:
        self._list_templates_result = list_templates_result
        self._get_template_path_result = get_template_path_result
        self._get_template_detail_result = get_template_detail_result
        self._pm_session_view_result = pm_session_view_result
        self._run_pm_session_check_result = run_pm_session_check_result
        self._apply_template_result = apply_template_result
        self._archive_pm_session_result = archive_pm_session_result
        self.get_template_path_calls: list[str] = []
        self.get_template_detail_calls: list[str] = []
        self.apply_template_calls: list[tuple[str, str]] = []
        self.archive_pm_session_calls: list[tuple[str, int, bool]] = []

    def list_templates(self) -> Any:
        return self._list_templates_result

    def get_template_path(self, template_name: Any) -> Any:
        self.get_template_path_calls.append(template_name)
        return self._get_template_path_result

    def get_template_detail(self, template_name: Any) -> Any:
        self.get_template_detail_calls.append(template_name)
        return self._get_template_detail_result

    def get_pm_session_view(self) -> Any:
        return self._pm_session_view_result

    def run_pm_session_check(self) -> Any:
        return self._run_pm_session_check_result

    def apply_template(self, project_id: Any, template_name: Any) -> Any:
        self.apply_template_calls.append((project_id, template_name))
        return self._apply_template_result

    def archive_pm_session(self, section: Any, keep_recent: Any, dry_run: Any) -> Any:
        self.archive_pm_session_calls.append((section, keep_recent, dry_run))
        return self._archive_pm_session_result


def test_system_bridge_list_templates(qapp) -> None:  # type: ignore[no-untyped-def]
    """listTemplates() 返回 list[str]"""
    from auto_pm.ui.qml.bridges.system_bridge import SystemBridge

    mock_facade = _MockSystemFacade(
        list_templates_result=QueryResult(
            success=True, message="OK", payload=["python-tpl", "plc-tpl"]
        )
    )
    bridge = SystemBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.listTemplates()

    assert isinstance(result, list)
    assert result == ["python-tpl", "plc-tpl"]


def test_system_bridge_get_template_path(qapp) -> None:  # type: ignore[no-untyped-def]
    """getTemplatePath() 返回 str + template_name 透传验证"""
    from auto_pm.ui.qml.bridges.system_bridge import SystemBridge

    mock_facade = _MockSystemFacade(
        get_template_path_result=QueryResult(
            success=True, message="OK", payload="/templates/python-tpl"
        )
    )
    bridge = SystemBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.getTemplatePath("python-tpl")

    assert isinstance(result, str)
    assert result == "/templates/python-tpl"
    assert mock_facade.get_template_path_calls == ["python-tpl"]


def test_system_bridge_get_template_detail(qapp) -> None:  # type: ignore[no-untyped-def]
    """getTemplateDetail() 返回 dict（asdict 转换）+ template_name 透传验证"""
    from auto_pm.ui.qml.bridges.system_bridge import SystemBridge

    dto = TemplateDetailDTO(
        name="python-tpl",
        version="v1.2.3",
        description="Python project template",
        stack="python",
        usage_count=3,
        path="/templates/python-tpl",
    )
    mock_facade = _MockSystemFacade(
        get_template_detail_result=QueryResult(success=True, message="OK", payload=dto)
    )
    bridge = SystemBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.getTemplateDetail("python-tpl")

    assert isinstance(result, dict)
    assert result["name"] == "python-tpl"
    assert result["version"] == "v1.2.3"
    assert result["description"] == "Python project template"
    assert result["stack"] == "python"
    assert result["usage_count"] == 3
    assert result["path"] == "/templates/python-tpl"
    assert mock_facade.get_template_detail_calls == ["python-tpl"]


def test_system_bridge_get_pm_session_view(qapp) -> None:  # type: ignore[no-untyped-def]
    """getPmSessionView() 返回 dict（asdict 转换）"""
    from auto_pm.ui.qml.bridges.system_bridge import SystemBridge

    dto = PmSessionViewDTO(data={"status": "ok", "version": "1.0"})
    mock_facade = _MockSystemFacade(
        pm_session_view_result=QueryResult(success=True, message="OK", payload=dto)
    )
    bridge = SystemBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.getPmSessionView()

    assert isinstance(result, dict)
    assert result["data"] == {"status": "ok", "version": "1.0"}


def test_system_bridge_run_pm_session_check(qapp) -> None:  # type: ignore[no-untyped-def]
    """runPmSessionCheck() 返回 dict（asdict 转换）"""
    from auto_pm.ui.qml.bridges.system_bridge import SystemBridge

    dto = PmSessionCheckResultDTO(data={"errors": 0, "warnings": 2})
    mock_facade = _MockSystemFacade(
        run_pm_session_check_result=CommandResult(success=True, message="OK", payload=dto)
    )
    bridge = SystemBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.runPmSessionCheck()

    assert isinstance(result, dict)
    assert result["data"] == {"errors": 0, "warnings": 2}


def test_system_bridge_apply_template(qapp) -> None:  # type: ignore[no-untyped-def]
    """applyTemplate() 返回 dict（asdict 转换）+ project_id/template_name 透传验证"""
    from auto_pm.ui.qml.bridges.system_bridge import SystemBridge

    dto = ApplyTemplateResultDTO(
        project_id="PROJ-001",
        template_name="python-tpl",
        result={"applied": True},
    )
    mock_facade = _MockSystemFacade(
        apply_template_result=CommandResult(success=True, message="OK", payload=dto)
    )
    bridge = SystemBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.applyTemplate("PROJ-001", "python-tpl")

    assert isinstance(result, dict)
    assert result["project_id"] == "PROJ-001"
    assert result["template_name"] == "python-tpl"
    assert result["result"] == {"applied": True}
    assert mock_facade.apply_template_calls == [("PROJ-001", "python-tpl")]


def test_system_bridge_archive_pm_session(qapp) -> None:  # type: ignore[no-untyped-def]
    """archivePmSession() 返回 dict（asdict 转换）+ section/keepRecent/dryRun 透传验证（M5 CHG-117）"""
    from auto_pm.ui.qml.bridges.system_bridge import SystemBridge

    dto = PmSessionArchiveResultDTO(
        archive_file="/tmp/archive.md",
        archived_sections=["6"],
        archived_line_count=30,
        main_file_lines_before=300,
        main_file_lines_after=270,
        is_dry_run=True,
        section_title="Implementation Log",
        section_total_lines=51,
        keep_recent=20,
    )
    mock_facade = _MockSystemFacade(
        archive_pm_session_result=CommandResult(success=True, message="OK", payload=dto)
    )
    bridge = SystemBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.archivePmSession("6", 20, True)

    assert isinstance(result, dict)
    assert result["archive_file"] == "/tmp/archive.md"
    assert result["archived_sections"] == ["6"]
    assert result["archived_line_count"] == 30
    assert result["main_file_lines_before"] == 300
    assert result["main_file_lines_after"] == 270
    assert result["is_dry_run"] is True
    assert result["section_title"] == "Implementation Log"
    assert result["section_total_lines"] == 51
    assert result["keep_recent"] == 20
    # 透传验证
    assert mock_facade.archive_pm_session_calls == [("6", 20, True)]


def test_system_bridge_archive_pm_session_error(qapp) -> None:  # type: ignore[no-untyped-def]
    """archivePmSession() service 返回 error 时透传 success=False + message（M5 CHG-117）"""
    from auto_pm.ui.qml.bridges.system_bridge import SystemBridge

    mock_facade = _MockSystemFacade(
        archive_pm_session_result=CommandResult(
            success=False, message="章节 §99 不存在", payload=None
        )
    )
    bridge = SystemBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.archivePmSession("99", 0, False)

    assert isinstance(result, dict)
    assert result["success"] is False
    assert result["message"] == "章节 §99 不存在"
    assert mock_facade.archive_pm_session_calls == [("99", 0, False)]


def test_system_bridge_no_facade(qapp) -> None:  # type: ignore[no-untyped-def]
    """facade=None 时 7 个 Slot 都返回降级值，不抛异常"""
    from auto_pm.ui.qml.bridges.system_bridge import SystemBridge

    bridge = SystemBridge(facade=None)
    # listTemplates 降级为 []
    assert bridge.listTemplates() == []
    # getTemplatePath 降级为 ""
    assert bridge.getTemplatePath("python-tpl") == ""
    # getTemplateDetail 降级为 {}
    assert bridge.getTemplateDetail("python-tpl") == {}
    # getPmSessionView 降级为 {}
    assert bridge.getPmSessionView() == {}
    # runPmSessionCheck 降级为 {"success": False, "message": "未初始化"}
    assert bridge.runPmSessionCheck() == {"success": False, "message": "未初始化"}
    # applyTemplate 降级为 {"success": False, "message": "未初始化"}
    assert bridge.applyTemplate("PROJ-001", "python-tpl") == {
        "success": False,
        "message": "未初始化",
    }
    # archivePmSession 降级为 {"success": False, "message": "未初始化"}（M5 CHG-117）
    assert bridge.archivePmSession("6", 20, True) == {"success": False, "message": "未初始化"}
