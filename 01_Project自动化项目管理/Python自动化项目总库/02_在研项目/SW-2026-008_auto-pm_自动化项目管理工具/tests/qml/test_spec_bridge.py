"""SpecBridge 单元测试（M4 第 1 批新增）

约束（与 tests/qml/conftest.py 一致）：
- qapp fixture 引用 tests/conftest.py 的 session 级 QApplication
- 不重新定义 qapp
- 全部用 Mock Facade，无文件系统/DB 依赖
- mock facade 用自定义 Mock 类（不使用 MagicMock），便于追踪调用参数

覆盖 SpecBridge 的 4 个 Slot：
- runSpecCheck() → dict + emit specCheckCompleted 信号
- getSpecOverview() → dict
- listSpecEntries(filter_domain) → list[dict]
- generateSpecIndex(domain) → dict (M5 CHG-119 新增)
"""

from __future__ import annotations

from typing import Any

from auto_pm.ui.contracts.dto.spec_dto import (
    SpecCenterEntryDTO,
    SpecCenterOverviewDTO,
    SpecCheckResultDTO,
    SpecFrontmatterResultDTO,
    SpecIndexResultDTO,
    SpecReportResultDTO,
)
from auto_pm.ui.contracts.result import CommandResult, QueryResult


class _MockSpecFacade:
    """Mock SpecFacade，记录方法调用并返回预设结果。

    用自定义类替代 MagicMock，便于显式追踪 list_spec_center_entries
    的调用参数（filter_domain 透传验证）和 generate_spec_index 的调用参数（domain 透传验证）。
    """

    def __init__(  # type: ignore[no-untyped-def]
        self,
        run_check_result=None,
        overview_result=None,
        list_entries_result=None,
        generate_index_result=None,
        generate_report_result=None,
        check_frontmatter_result=None,
        repair_result=None,
    ) -> None:
        self._run_check_result = run_check_result
        self._overview_result = overview_result
        self._list_entries_result = list_entries_result
        self._generate_index_result = generate_index_result
        self._generate_report_result = generate_report_result
        self._check_frontmatter_result = check_frontmatter_result
        self._repair_result = repair_result
        self.list_entries_calls: list[str | None] = []
        self.generate_index_calls: list[str] = []
        self.generate_report_calls: list[str] = []
        self.check_frontmatter_calls: list[bool] = []
        self.check_calls: list[str] = []
        self.repair_calls: list[str] = []

    def run_spec_check(self, project_id: str = "") -> Any:
        self.check_calls.append(project_id)
        return self._run_check_result

    def get_spec_center_overview(self) -> Any:
        return self._overview_result

    def list_spec_center_entries(self, filter_domain: Any = None) -> Any:
        self.list_entries_calls.append(filter_domain)
        return self._list_entries_result

    def generate_spec_index(self, domain: str = "all") -> Any:
        self.generate_index_calls.append(domain)
        return self._generate_index_result

    def generate_spec_report(self, fmt: str = "markdown") -> Any:
        self.generate_report_calls.append(fmt)
        return self._generate_report_result

    def check_spec_frontmatter(self, auto_fix: bool = False) -> Any:
        self.check_frontmatter_calls.append(auto_fix)
        return self._check_frontmatter_result

    def run_spec_repair(self, project_id) -> None:  # type: ignore[no-untyped-def]
        self.repair_calls.append(project_id)
        return self._repair_result  # type: ignore[no-any-return]


def _make_check_result_dto(**overrides) -> Any:  # type: ignore[no-untyped-def]
    return SpecCheckResultDTO(
        error_count=overrides.get("error_count", 2),
        warning_count=overrides.get("warning_count", 3),
        info_count=overrides.get("info_count", 1),
        exit_code=overrides.get("exit_code", 0),
        results=overrides.get("results", []),
    )


def _make_overview_dto(**overrides) -> Any:  # type: ignore[no-untyped-def]
    return SpecCenterOverviewDTO(
        spec_count=overrides.get("spec_count", 10),
        domain_counts=overrides.get("domain_counts", {"plc": 6, "python": 4}),
        lifecycle_counts=overrides.get("lifecycle_counts", {"draft": 2, "active": 8}),
        health_summary=overrides.get(
            "health_summary",
            {
                "error_count": 2,
                "warning_count": 3,
                "info_count": 1,
                "exit_code": 0,
            },
        ),
    )


def _make_entry_dto(**overrides) -> Any:  # type: ignore[no-untyped-def]
    return SpecCenterEntryDTO(
        spec_id=overrides.get("spec_id", "SW-2026-006"),
        title=overrides.get("title", "SpecMgr 规范管理"),
        number=overrides.get("number", "006"),
        domain=overrides.get("domain", "python"),
        lifecycle=overrides.get("lifecycle", "active"),
        canonical_path=overrides.get("canonical_path", "/specs/SW-2026-006.md"),
        version=overrides.get("version", "1.0.0"),
        file_exists=overrides.get("file_exists", True),
    )


def test_spec_bridge_run_check(qapp) -> None:  # type: ignore[no-untyped-def]
    """runSpecCheck() 返回 dict + emit specCheckCompleted 信号"""
    from PySide6.QtTest import QSignalSpy

    from auto_pm.ui.qml.bridges.spec_bridge import SpecBridge

    dto = _make_check_result_dto(error_count=2, warning_count=3, info_count=1)
    mock_facade = _MockSpecFacade(
        run_check_result=CommandResult(success=True, message="OK", payload=dto)
    )
    bridge = SpecBridge(facade=mock_facade)  # type: ignore[arg-type]

    spy = QSignalSpy(bridge.specCheckCompleted)
    result = bridge.runSpecCheck()

    # 返回 dict（asdict 转换），字段与 DTO 一致
    assert isinstance(result, dict)
    assert result["error_count"] == 2
    assert result["warning_count"] == 3
    assert result["info_count"] == 1
    assert result["exit_code"] == 0
    assert result["results"] == []
    # 信号 emit 一次，参数为 (error_count, warning_count, info_count)
    assert spy.count() == 1
    args = spy.at(0)
    assert int(args[0]) == 2
    assert int(args[1]) == 3
    assert int(args[2]) == 1


def test_spec_bridge_get_overview(qapp) -> None:  # type: ignore[no-untyped-def]
    """getSpecOverview() 返回 dict"""
    from auto_pm.ui.qml.bridges.spec_bridge import SpecBridge

    dto = _make_overview_dto(spec_count=10)
    mock_facade = _MockSpecFacade(
        overview_result=QueryResult(success=True, message="OK", payload=dto)
    )
    bridge = SpecBridge(facade=mock_facade)  # type: ignore[arg-type]
    result = bridge.getSpecOverview()

    assert isinstance(result, dict)
    assert result["spec_count"] == 10
    assert result["domain_counts"] == {"plc": 6, "python": 4}
    assert result["lifecycle_counts"] == {"draft": 2, "active": 8}
    assert result["health_summary"]["error_count"] == 2
    assert result["health_summary"]["exit_code"] == 0


def test_spec_bridge_list_entries(qapp) -> None:  # type: ignore[no-untyped-def]
    """listSpecEntries() 返回 list[dict]"""
    from auto_pm.ui.qml.bridges.spec_bridge import SpecBridge

    entries = [
        _make_entry_dto(spec_id="SW-2026-006", domain="python"),
        _make_entry_dto(spec_id="SW-2026-008", domain="python", title="auto-pm 项目管理"),
    ]
    mock_facade = _MockSpecFacade(
        list_entries_result=QueryResult(success=True, message="OK", payload=entries)
    )
    bridge = SpecBridge(facade=mock_facade)  # type: ignore[arg-type]
    result = bridge.listSpecEntries("python")

    assert isinstance(result, list)
    assert len(result) == 2
    assert isinstance(result[0], dict)
    assert result[0]["spec_id"] == "SW-2026-006"
    assert result[0]["domain"] == "python"
    assert result[0]["file_exists"] is True
    assert result[1]["spec_id"] == "SW-2026-008"
    assert result[1]["title"] == "auto-pm 项目管理"
    # 验证 filter_domain 透传给 Facade
    assert mock_facade.list_entries_calls == ["python"]


def test_spec_bridge_no_facade(qapp) -> None:  # type: ignore[no-untyped-def]
    """facade=None 时 4 个 Slot 都返回降级值，不抛异常"""
    from auto_pm.ui.qml.bridges.spec_bridge import SpecBridge

    bridge = SpecBridge(facade=None)
    # runSpecCheck 降级
    assert bridge.runSpecCheck() == {"error_count": -1, "message": "未初始化"}
    # getSpecOverview 降级
    assert bridge.getSpecOverview() == {}
    # listSpecEntries 降级
    assert bridge.listSpecEntries("") == []
    # generateSpecIndex 降级（M5 CHG-119）
    assert bridge.generateSpecIndex("all") == {"success": False, "message": "未初始化"}
    # generateSpecReport 降级（M5 CHG-120）
    assert bridge.generateSpecReport("markdown") == {"success": False, "message": "未初始化"}
    # checkSpecFrontmatter 降级（M5 CHG-121）
    assert bridge.checkSpecFrontmatter(False) == {"success": False, "message": "未初始化"}


def test_spec_bridge_run_check_failure(qapp) -> None:  # type: ignore[no-untyped-def]
    """Facade 返回失败时，runSpecCheck 返回 {"error_count": -1, "message": ...}"""
    from PySide6.QtTest import QSignalSpy

    from auto_pm.ui.qml.bridges.spec_bridge import SpecBridge

    mock_facade = _MockSpecFacade(
        run_check_result=CommandResult(success=False, message="Spec check failed", payload=None)
    )
    bridge = SpecBridge(facade=mock_facade)  # type: ignore[arg-type]

    spy = QSignalSpy(bridge.specCheckCompleted)
    result = bridge.runSpecCheck()

    assert result == {"error_count": -1, "message": "Spec check failed"}
    # 失败时不 emit 信号
    assert spy.count() == 0


# ── generateSpecIndex 测试（M5 CHG-119 新增）──────────────


def _make_index_result_dto(**overrides) -> Any:  # type: ignore[no-untyped-def]
    return SpecIndexResultDTO(
        domain=overrides.get("domain", "all"),
        generated_files=overrides.get("generated_files", ["/tmp/index_pm.md", "/tmp/index_plc.md"]),
        errors=overrides.get("errors", []),
    )


def test_spec_bridge_generate_spec_index(qapp) -> None:  # type: ignore[no-untyped-def]
    """generateSpecIndex() 返回 dict（asdict 转换）+ domain 透传验证（M5 CHG-119）"""
    from auto_pm.ui.qml.bridges.spec_bridge import SpecBridge

    dto = _make_index_result_dto(
        domain="plc",
        generated_files=["/tmp/index_plc.md"],
        errors=[],
    )
    mock_facade = _MockSpecFacade(
        generate_index_result=CommandResult(success=True, message="OK", payload=dto)
    )
    bridge = SpecBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.generateSpecIndex("plc")

    assert isinstance(result, dict)
    assert result["domain"] == "plc"
    assert result["generated_files"] == ["/tmp/index_plc.md"]
    assert result["errors"] == []
    # domain 透传验证
    assert mock_facade.generate_index_calls == ["plc"]


def test_spec_bridge_generate_spec_index_error(qapp) -> None:  # type: ignore[no-untyped-def]
    """generateSpecIndex() service 返回失败时透传 success=False + message（M5 CHG-119）"""
    from auto_pm.ui.qml.bridges.spec_bridge import SpecBridge

    mock_facade = _MockSpecFacade(
        generate_index_result=CommandResult(success=False, message="No index_service", payload=None)
    )
    bridge = SpecBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.generateSpecIndex("all")

    assert isinstance(result, dict)
    assert result["success"] is False
    assert result["message"] == "No index_service"
    assert mock_facade.generate_index_calls == ["all"]


# ── generateSpecReport 测试（M5 CHG-120 新增）──────────────


def _make_report_result_dto(**overrides) -> Any:  # type: ignore[no-untyped-def]
    return SpecReportResultDTO(
        fmt=overrides.get("fmt", "markdown"),
        output_path=overrides.get("output_path", "/tmp/规范元数据汇总报告.md"),
        content=overrides.get("content", "# 规范元数据汇总报告\n\n总览..."),
        file_size=overrides.get("file_size", 30),
    )


def test_spec_bridge_generate_spec_report(qapp) -> None:  # type: ignore[no-untyped-def]
    """generateSpecReport() 返回 dict（asdict 转换）+ fmt 透传验证（M5 CHG-120）"""
    from auto_pm.ui.qml.bridges.spec_bridge import SpecBridge

    dto = _make_report_result_dto(
        fmt="json",
        output_path="/tmp/report.json",
        content='{"specs": {}}',
        file_size=13,
    )
    mock_facade = _MockSpecFacade(
        generate_report_result=CommandResult(success=True, message="OK", payload=dto)
    )
    bridge = SpecBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.generateSpecReport("json")

    assert isinstance(result, dict)
    assert result["fmt"] == "json"
    assert result["output_path"] == "/tmp/report.json"
    assert result["content"] == '{"specs": {}}'
    assert result["file_size"] == 13
    # fmt 透传验证
    assert mock_facade.generate_report_calls == ["json"]


def test_spec_bridge_generate_spec_report_error(qapp) -> None:  # type: ignore[no-untyped-def]
    """generateSpecReport() service 返回失败时透传 success=False + message（M5 CHG-120）"""
    from auto_pm.ui.qml.bridges.spec_bridge import SpecBridge

    mock_facade = _MockSpecFacade(
        generate_report_result=CommandResult(
            success=False, message="No report_service", payload=None
        )
    )
    bridge = SpecBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.generateSpecReport("markdown")

    assert isinstance(result, dict)
    assert result["success"] is False
    assert result["message"] == "No report_service"
    assert mock_facade.generate_report_calls == ["markdown"]


# ── checkSpecFrontmatter 测试（M5 CHG-121 新增）──────────────


def _make_frontmatter_result_dto(**overrides) -> Any:  # type: ignore[no-untyped-def]
    return SpecFrontmatterResultDTO(
        items=overrides.get("items", []),
        total_count=overrides.get("total_count", 1),
        pending_count=overrides.get("pending_count", 1),
        skipped_count=overrides.get("skipped_count", 0),
        error_count=overrides.get("error_count", 0),
        modified_count=overrides.get("modified_count", 0),
        auto_fixed=overrides.get("auto_fixed", False),
    )


def test_spec_bridge_check_spec_frontmatter(qapp) -> None:  # type: ignore[no-untyped-def]
    """checkSpecFrontmatter() 返回 dict（asdict 转换）+ autoFix 透传验证（M5 CHG-121）"""
    from auto_pm.ui.qml.bridges.spec_bridge import SpecBridge

    dto = _make_frontmatter_result_dto(
        items=[{"spec_id": "SW-006", "status": "pending", "file_path": "/tmp/spec.md"}],
        total_count=1,
        pending_count=1,
        auto_fixed=True,
        modified_count=1,
    )
    mock_facade = _MockSpecFacade(
        check_frontmatter_result=CommandResult(success=True, message="OK", payload=dto)
    )
    bridge = SpecBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.checkSpecFrontmatter(True)

    assert isinstance(result, dict)
    assert result["total_count"] == 1
    assert result["pending_count"] == 1
    assert result["auto_fixed"] is True
    assert result["modified_count"] == 1
    assert result["items"][0]["spec_id"] == "SW-006"
    # autoFix 透传验证
    assert mock_facade.check_frontmatter_calls == [True]


def test_spec_bridge_check_spec_frontmatter_error(qapp) -> None:  # type: ignore[no-untyped-def]
    """checkSpecFrontmatter() service 返回失败时透传 success=False + message（M5 CHG-121）"""
    from auto_pm.ui.qml.bridges.spec_bridge import SpecBridge

    mock_facade = _MockSpecFacade(
        check_frontmatter_result=CommandResult(
            success=False, message="No frontmatter_service", payload=None
        )
    )
    bridge = SpecBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.checkSpecFrontmatter(False)

    assert isinstance(result, dict)
    assert result["success"] is False
    assert result["message"] == "No frontmatter_service"
    assert mock_facade.check_frontmatter_calls == [False]


def test_spec_bridge_run_spec_check_with_project_id(qapp) -> None:  # type: ignore[no-untyped-def]
    """测试 runSpecCheck(project_id) 透传 project_id 到 facade"""
    from auto_pm.ui.qml.bridges.spec_bridge import SpecBridge

    dto = _make_check_result_dto(error_count=0)
    mock_facade = _MockSpecFacade(
        run_check_result=CommandResult(success=True, message="OK", payload=dto)
    )
    bridge = SpecBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.runSpecCheck("SW-2026-PYT")
    assert isinstance(result, dict)
    assert mock_facade.check_calls == ["SW-2026-PYT"]


def test_spec_bridge_repair_spec(qapp) -> None:  # type: ignore[no-untyped-def]
    """测试 repairSpec(project_id) 槽函数调用"""
    from auto_pm.ui.qml.bridges.spec_bridge import SpecBridge

    mock_facade = _MockSpecFacade(
        repair_result=CommandResult(
            success=True, message="修复成功", payload={"repaired_items": []}
        )
    )
    bridge = SpecBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.repairSpec("SW-2026-PYT")
    assert isinstance(result, dict)
    assert result["success"] is True
    assert result["message"] == "修复成功"
    assert mock_facade.repair_calls == ["SW-2026-PYT"]
