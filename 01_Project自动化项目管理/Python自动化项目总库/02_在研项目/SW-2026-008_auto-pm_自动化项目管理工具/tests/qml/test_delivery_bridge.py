"""DeliveryBridge 单元测试（M4 第 2 批新增 + DTO 细化更新）

约束（与 tests/qml/conftest.py 一致）：
- qapp fixture 引用 tests/conftest.py 的 session 级 QApplication
- 不重新定义 qapp
- 全部用 Mock Facade，无文件系统/DB 依赖
- mock facade 用自定义 Mock 类（不使用 MagicMock），便于追踪调用参数

覆盖 DeliveryBridge 的 7 个 Slot：
- getProjectReport / getChangeReport / getSpecReport / getScanReport → dict（asdict 转换细化字段 DTO）
- refreshProjectDocs(project_id, dry_run) → dict（含参数透传验证）
- refreshAssetSummary → dict
- getAssetSummary → dict
"""

from __future__ import annotations

from typing import Any

from auto_pm.ui.contracts.dto.delivery_dto import (
    AssetSummaryDTO,
    ChangeReportDTO,
    ProjectReportDTO,
    RefreshAssetSummaryResultDTO,
    RefreshProjectDocsResultDTO,
    ScanReportDTO,
    SpecReportDTO,
)
from auto_pm.ui.contracts.result import CommandResult, QueryResult


class _MockDeliveryFacade:
    """Mock DeliveryFacade，记录方法调用并返回预设结果。"""

    def __init__(  # type: ignore[no-untyped-def]
        self,
        project_report_result=None,
        change_report_result=None,
        spec_report_result=None,
        scan_report_result=None,
        refresh_docs_result=None,
        refresh_asset_result=None,
        asset_summary_result=None,
    ) -> None:
        self._project_report_result = project_report_result
        self._change_report_result = change_report_result
        self._spec_report_result = spec_report_result
        self._scan_report_result = scan_report_result
        self._refresh_docs_result = refresh_docs_result
        self._refresh_asset_result = refresh_asset_result
        self._asset_summary_result = asset_summary_result
        self.refresh_docs_calls: list[tuple[str, bool]] = []
        self.refresh_asset_calls: list[str] = []
        self.asset_summary_calls: list[str] = []

    def get_project_report(self) -> Any:
        return self._project_report_result

    def get_change_report(self) -> Any:
        return self._change_report_result

    def get_spec_report(self) -> Any:
        return self._spec_report_result

    def get_scan_report(self) -> Any:
        return self._scan_report_result

    def refresh_project_docs(self, project_id: Any, dry_run: bool = False) -> Any:
        self.refresh_docs_calls.append((project_id, dry_run))
        return self._refresh_docs_result

    def refresh_asset_summary(self, project_id: Any) -> Any:
        self.refresh_asset_calls.append(project_id)
        return self._refresh_asset_result

    def get_asset_summary(self, project_id: Any) -> Any:
        self.asset_summary_calls.append(project_id)
        return self._asset_summary_result


def test_delivery_bridge_get_project_report(qapp) -> None:  # type: ignore[no-untyped-def]
    """getProjectReport() 返回 dict（asdict 转换细化字段 DTO）"""
    from auto_pm.ui.qml.bridges.delivery_bridge import DeliveryBridge

    dto = ProjectReportDTO(
        total=5,
        by_stack={"plc": 3, "python": 2},
        by_phase={"developing": 5},
        by_business_line={"SW": 5},
    )
    mock_facade = _MockDeliveryFacade(
        project_report_result=QueryResult(success=True, message="OK", payload=dto)
    )
    bridge = DeliveryBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.getProjectReport()

    assert isinstance(result, dict)
    assert result["total"] == 5
    assert result["by_stack"] == {"plc": 3, "python": 2}
    assert result["by_phase"] == {"developing": 5}
    assert result["by_business_line"] == {"SW": 5}


def test_delivery_bridge_get_change_report(qapp) -> None:  # type: ignore[no-untyped-def]
    """getChangeReport() 返回 dict（asdict 转换细化字段 DTO）"""
    from auto_pm.ui.qml.bridges.delivery_bridge import DeliveryBridge

    dto = ChangeReportDTO(
        total=10,
        by_status={"draft": 5, "closed": 5},
        by_domain={"ELEC": 10},
    )
    mock_facade = _MockDeliveryFacade(
        change_report_result=QueryResult(success=True, message="OK", payload=dto)
    )
    bridge = DeliveryBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.getChangeReport()

    assert isinstance(result, dict)
    assert result["total"] == 10
    assert result["by_status"] == {"draft": 5, "closed": 5}
    assert result["by_domain"] == {"ELEC": 10}


def test_delivery_bridge_get_spec_report(qapp) -> None:  # type: ignore[no-untyped-def]
    """getSpecReport() 返回 dict（asdict 转换细化字段 DTO）"""
    from auto_pm.ui.qml.bridges.delivery_bridge import DeliveryBridge

    dto = SpecReportDTO(
        total=2,
        found=1,
        missing=1,
        by_stack={"plc": {"total": 1, "found": 1, "missing": []}},
        missing_codes=["LSP-001"],
    )
    mock_facade = _MockDeliveryFacade(
        spec_report_result=QueryResult(success=True, message="OK", payload=dto)
    )
    bridge = DeliveryBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.getSpecReport()

    assert isinstance(result, dict)
    assert result["total"] == 2
    assert result["found"] == 1
    assert result["missing"] == 1
    assert result["missing_codes"] == ["LSP-001"]


def test_delivery_bridge_get_scan_report(qapp) -> None:  # type: ignore[no-untyped-def]
    """getScanReport() 返回 dict（asdict 转换细化字段 DTO）"""
    from auto_pm.ui.qml.bridges.delivery_bridge import DeliveryBridge

    dto = ScanReportDTO(
        latest={"timestamp": "2026-07-07T10:00"},
        last_sync_time="2026-07-07 10:00",
        is_cache_available=True,
    )
    mock_facade = _MockDeliveryFacade(
        scan_report_result=QueryResult(success=True, message="OK", payload=dto)
    )
    bridge = DeliveryBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.getScanReport()

    assert isinstance(result, dict)
    assert result["latest"] == {"timestamp": "2026-07-07T10:00"}
    assert result["last_sync_time"] == "2026-07-07 10:00"
    assert result["is_cache_available"] is True


def test_delivery_bridge_refresh_project_docs(qapp) -> None:  # type: ignore[no-untyped-def]
    """refreshProjectDocs() 返回 dict（asdict 转换细化字段 DTO）+ project_id/dry_run 透传验证"""
    from auto_pm.ui.qml.bridges.delivery_bridge import DeliveryBridge

    dto = RefreshProjectDocsResultDTO(
        project_id="PROJ-001",
        dry_run=True,
        updated=True,
        refreshed_files=[
            {"file_path": "/docs/readme.md", "block_keys": ["plc-io-overview"], "changed": True}
        ],
        issues=[],
    )
    mock_facade = _MockDeliveryFacade(
        refresh_docs_result=CommandResult(success=True, message="OK", payload=dto)
    )
    bridge = DeliveryBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.refreshProjectDocs("PROJ-001", True)

    assert isinstance(result, dict)
    assert result["project_id"] == "PROJ-001"
    assert result["dry_run"] is True
    assert result["updated"] is True
    assert len(result["refreshed_files"]) == 1
    assert result["refreshed_files"][0]["file_path"] == "/docs/readme.md"
    assert result["issues"] == []
    # 验证参数透传
    assert mock_facade.refresh_docs_calls == [("PROJ-001", True)]


def test_delivery_bridge_refresh_asset_summary(qapp) -> None:  # type: ignore[no-untyped-def]
    """refreshAssetSummary(project_id) 返回 dict（asdict 转换）+ project_id 透传验证"""
    from auto_pm.ui.qml.bridges.delivery_bridge import DeliveryBridge

    dto = RefreshAssetSummaryResultDTO(result={"refreshed": True, "count": 50})
    mock_facade = _MockDeliveryFacade(
        refresh_asset_result=CommandResult(success=True, message="OK", payload=dto)
    )
    bridge = DeliveryBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.refreshAssetSummary("PROJ-001")

    assert isinstance(result, dict)
    assert result["result"] == {"refreshed": True, "count": 50}
    # 验证 project_id 透传
    assert mock_facade.refresh_asset_calls == ["PROJ-001"]


def test_delivery_bridge_get_asset_summary(qapp) -> None:  # type: ignore[no-untyped-def]
    """getAssetSummary(project_id) 返回 dict（asdict 转换）+ project_id 透传验证"""
    from auto_pm.ui.qml.bridges.delivery_bridge import DeliveryBridge

    dto = AssetSummaryDTO(data={"assets": 100, "healthy": 95})
    mock_facade = _MockDeliveryFacade(
        asset_summary_result=QueryResult(success=True, message="OK", payload=dto)
    )
    bridge = DeliveryBridge(facade=mock_facade)  # type: ignore[arg-type]

    result = bridge.getAssetSummary("PROJ-001")

    assert isinstance(result, dict)
    assert result["data"] == {"assets": 100, "healthy": 95}
    # 验证 project_id 透传
    assert mock_facade.asset_summary_calls == ["PROJ-001"]


def test_delivery_bridge_no_facade(qapp) -> None:  # type: ignore[no-untyped-def]
    """facade=None 时 Slot 都返回降级值，不抛异常"""
    from auto_pm.ui.qml.bridges.delivery_bridge import DeliveryBridge

    bridge = DeliveryBridge(facade=None)
    # 4 个 report 降级为 {}
    assert bridge.getProjectReport() == {}
    assert bridge.getChangeReport() == {}
    assert bridge.getSpecReport() == {}
    assert bridge.getScanReport() == {}
    # refreshProjectDocs 降级为 {"success": False, "message": "未初始化"}
    result = bridge.refreshProjectDocs("PROJ-001")
    assert result == {"success": False, "message": "未初始化"}
    # refreshAssetSummary 降级（需传 project_id）
    assert bridge.refreshAssetSummary("PROJ-001") == {"success": False, "message": "未初始化"}
    # getAssetSummary 降级为 {}（需传 project_id）
    assert bridge.getAssetSummary("PROJ-001") == {}
    # listProjectDocs 降级为 []
    assert bridge.listProjectDocs("PROJ-001") == []
    # renderMarkdown 降级为错误 HTML
    assert "文件不存在" in bridge.renderMarkdown("nonexistent.md")


def test_delivery_bridge_parse_markdown_to_blocks(qapp, tmp_path: Path) -> None:  # type: ignore[name-defined, no-untyped-def]
    """测试 parseMarkdownToBlocks() 在读取 Markdown 文件时返回结构化块列表"""
    from auto_pm.ui.qml.bridges.delivery_bridge import DeliveryBridge

    # 1. 测试文件不存在
    bridge = DeliveryBridge(facade=None)
    res = bridge.parseMarkdownToBlocks(str(tmp_path / "nonexistent.md"))
    assert len(res) == 1
    assert res[0]["type"] == "paragraph"
    assert "文件不存在" in res[0]["html"]

    # 2. 测试正常解析
    md_file = tmp_path / "test.md"
    md_file.write_text("# Test Title\n\nSome text.", encoding="utf-8")
    res = bridge.parseMarkdownToBlocks(str(md_file))
    assert len(res) == 2
    assert res[0]["type"] == "h1"
    assert res[0]["text"] == "Test Title"
    assert res[1]["type"] == "paragraph"
    assert "Some text." in res[1]["html"]


def test_delivery_bridge_export_doc_to_pdf(qapp, tmp_path: Path) -> None:  # type: ignore[name-defined, no-untyped-def]
    """测试 exportDocToPdf() 能否通过 QTextDocument 离线输出 PDF"""
    from auto_pm.ui.qml.bridges.delivery_bridge import DeliveryBridge

    bridge = DeliveryBridge(facade=None)

    # 1. 源文件不存在
    res = bridge.exportDocToPdf(str(tmp_path / "nonexistent.md"), str(tmp_path / "out.pdf"))
    assert res["success"] is False
    assert "文件不存在" in res["message"]

    # 2. 正常导出
    md_file = tmp_path / "test.md"
    md_file.write_text("# Test Document\nThis is printed offline.", encoding="utf-8")
    pdf_file = tmp_path / "out.pdf"

    res = bridge.exportDocToPdf(str(md_file), str(pdf_file))
    assert res["success"] is True
    assert pdf_file.exists()
    assert pdf_file.stat().st_size > 0
