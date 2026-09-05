"""DeliveryFacade 集成测试（M4 后续待办 B3 + C7 补齐）

验证 DeliveryFacade → ReportService → Repository → DB / SpecRegistry 端到端链路。
验证 DeliveryFacade → DocRefreshService / AssetSummaryService → ProjectService 端到端链路。

覆盖 4 个 report 方法（无 Service bug 的方法）：
- get_project_report: ProjectRepository → DB
- get_change_report: ChangeRequestRepository → DB
- get_spec_report: SpecRegistry → spec_registry.json
- get_scan_report: ScanLogRepository → DB

阶段 C bug 修复后补齐 3 个方法：
- refresh_project_docs: DocRefreshService.refresh_project_documents(project_info, dry_run)
- refresh_asset_summary: AssetSummaryService.build_summary(project_path, stack, project_type)
- get_asset_summary: 同上

参考 M3 的 test_change_facade_int.py 模式。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.change.change_service import ChangeService
from auto_pm.core.asset_summary_service import AssetSummaryService
from auto_pm.core.doc_refresh_service import DocRefreshService
from auto_pm.core.project_service import ProjectService
from auto_pm.core.report_service import ReportService

from auto_pm.application.delivery_facade import DeliveryFacade
from auto_pm.ui.contracts.dto.delivery_dto import (
    AssetSummaryDTO,
    ChangeReportDTO,
    ProjectReportDTO,
    RefreshAssetSummaryResultDTO,
    RefreshProjectDocsResultDTO,
    ScanReportDTO,
    SpecReportDTO,
)


@pytest.fixture
def delivery_facade_with_db(  # type: ignore[no-untyped-def]
    temp_workspace: str,
    db_manager,
    project_repo_with_data,
    change_repo_with_data,
) -> DeliveryFacade:
    """构造含真实 Service 的 DeliveryFacade

    - ProjectService(workspace_root, db) → list_projects_cached 从 DB 读取
    - ChangeService(workspace_root, db) → list_all_changes 从 DB 读取
    - ReportService 注入上述 Service + workspace_root + db
    """
    project_service = ProjectService(workspace_root=temp_workspace, db=db_manager)
    change_service = ChangeService(workspace_root=temp_workspace, db=db_manager)
    report_service = ReportService(
        project_service=project_service,
        change_service=change_service,
        workspace_root=temp_workspace,
        db=db_manager,
    )
    return DeliveryFacade(
        doc_refresh_service=None,
        report_service=report_service,
        asset_summary_service=None,
    )


@pytest.fixture
def delivery_facade_with_spec(
    spec_registry_workspace: Path,
) -> DeliveryFacade:
    """构造专门用于 get_spec_report 的 DeliveryFacade

    使用 spec_registry_workspace（含 2 条规范，1 个文件存在 1 个 missing）。
    ProjectService / ChangeService 用临时空 workspace，避免影响 spec_report 断言。
    """
    # 用 spec_registry_workspace 作为 workspace_root，ReportService.get_spec_report
    # 会从 <workspace>/00_Obsidian_Base全局规范文件仓库/spec_registry.json 读取
    project_service = ProjectService(workspace_root=str(spec_registry_workspace), db=None)
    change_service = ChangeService(workspace_root=str(spec_registry_workspace), db=None)
    report_service = ReportService(
        project_service=project_service,
        change_service=change_service,
        workspace_root=str(spec_registry_workspace),
        db=None,  # get_spec_report 不需要 db
    )
    return DeliveryFacade(
        doc_refresh_service=None,
        report_service=report_service,
        asset_summary_service=None,
    )


def test_delivery_facade_int_get_project_report(delivery_facade_with_db: DeliveryFacade) -> None:
    """集成测试：get_project_report 从 DB 读取项目统计

    fixture 预置 2 个项目：DJ-2026-001(plc/developing/SW) + SW-2026-001(python/production/DJ)
    """
    result = delivery_facade_with_db.get_project_report()
    assert result.success is True
    assert result.payload is not None

    dto: ProjectReportDTO = result.payload
    assert dto.total == 2
    # by_stack 含 plc/python/unknown 3 个固定 key（_STACK_KEYS）
    assert dto.by_stack["plc"] == 1
    assert dto.by_stack["python"] == 1
    assert dto.by_stack["unknown"] == 0
    # by_phase 含 4 个固定 key（_PHASE_KEYS）
    assert dto.by_phase["developing"] == 1
    assert dto.by_phase["production"] == 1
    # by_business_line 含 5 个固定 key（_BL_KEYS）
    assert dto.by_business_line["SW"] == 1
    assert dto.by_business_line["DJ"] == 1


def test_delivery_facade_int_get_change_report(delivery_facade_with_db: DeliveryFacade) -> None:
    """集成测试：get_change_report 从 DB 读取变更统计

    fixture 预置 1 个变更：CHG-2026-001(DOCU/approved)
    """
    result = delivery_facade_with_db.get_change_report()
    assert result.success is True
    assert result.payload is not None

    dto: ChangeReportDTO = result.payload
    assert dto.total == 1
    assert dto.by_status == {"approved": 1}
    assert dto.by_domain == {"DOCU": 1}


def test_delivery_facade_int_get_spec_report(delivery_facade_with_spec: DeliveryFacade) -> None:
    """集成测试：get_spec_report 从 spec_registry.json 读取规范覆盖统计

    spec_registry_workspace 预置 2 条规范：
    - LSP-905: plc 文件存在 → found
    - CODE-210: python 文件 missing → missing
    """
    result = delivery_facade_with_spec.get_spec_report()
    assert result.success is True
    assert result.payload is not None

    dto: SpecReportDTO = result.payload
    assert dto.total == 2
    assert dto.found == 1
    assert dto.missing == 1
    assert "CODE-210" in dto.missing_codes
    assert "LSP-905" not in dto.missing_codes
    # by_stack 按 domain 分组
    assert "plc" in dto.by_stack
    assert dto.by_stack["plc"]["total"] == 1
    assert dto.by_stack["plc"]["found"] == 1
    assert "python" in dto.by_stack
    assert dto.by_stack["python"]["total"] == 1
    assert dto.by_stack["python"]["found"] == 0
    assert "CODE-210" in dto.by_stack["python"]["missing"]


def test_delivery_facade_int_get_scan_report(delivery_facade_with_db: DeliveryFacade) -> None:
    """集成测试：get_scan_report 从 DB 读取扫描日志

    fixture 未预置扫描日志记录，latest 应为 None，last_sync_time 为 '—'。
    is_cache_available=True（db 已注入）。
    """
    result = delivery_facade_with_db.get_scan_report()
    assert result.success is True
    assert result.payload is not None

    dto: ScanReportDTO = result.payload
    assert dto.latest is None
    assert dto.last_sync_time == "—"
    assert dto.is_cache_available is True


def test_delivery_facade_int_full_flow(delivery_facade_with_db: DeliveryFacade) -> None:
    """集成测试：端到端 4 个 report 流程"""
    # 1. project report
    project_result = delivery_facade_with_db.get_project_report()
    assert project_result.success
    assert project_result.payload.total == 2  # type: ignore[union-attr]

    # 2. change report
    change_result = delivery_facade_with_db.get_change_report()
    assert change_result.success
    assert change_result.payload.total == 1  # type: ignore[union-attr]

    # 3. scan report
    scan_result = delivery_facade_with_db.get_scan_report()
    assert scan_result.success
    assert scan_result.payload.is_cache_available is True  # type: ignore[union-attr]


def test_delivery_facade_int_no_report_service() -> None:
    """集成测试：未注入 ReportService 时 4 个 report 方法返回 success=False"""
    facade = DeliveryFacade(
        doc_refresh_service=None,
        report_service=None,
        asset_summary_service=None,
    )

    assert facade.get_project_report().success is False
    assert facade.get_change_report().success is False
    assert facade.get_spec_report().success is False
    assert facade.get_scan_report().success is False


def test_delivery_facade_int_spec_report_no_workspace() -> None:
    """集成测试：ReportService 未注入 workspace_root 时 get_spec_report 返回 success=False

    RuntimeError("未注入 workspace_root") 被 Facade except 捕获转 success=False。
    """
    # 构造无 workspace_root 的 ReportService（workspace_root=""）
    project_service = ProjectService(workspace_root="", db=None)
    change_service = ChangeService(workspace_root="", db=None)
    report_service = ReportService(
        project_service=project_service,
        change_service=change_service,
        workspace_root="",
        db=None,
    )
    facade = DeliveryFacade(
        doc_refresh_service=None,
        report_service=report_service,
        asset_summary_service=None,
    )

    result = facade.get_spec_report()
    assert result.success is False
    assert "workspace_root" in result.message or "未注入" in result.message


def test_delivery_facade_int_scan_report_no_db() -> None:
    """集成测试：ReportService 未注入 db 时 get_scan_report 返回 success=False

    RuntimeError("未注入 DatabaseManager") 被 Facade except 捕获转 success=False。
    """
    project_service = ProjectService(workspace_root=".", db=None)
    change_service = ChangeService(workspace_root=".", db=None)
    report_service = ReportService(
        project_service=project_service,
        change_service=change_service,
        workspace_root=".",
        db=None,
    )
    facade = DeliveryFacade(
        doc_refresh_service=None,
        report_service=report_service,
        asset_summary_service=None,
    )

    result = facade.get_scan_report()
    assert result.success is False
    assert "DatabaseManager" in result.message or "未注入" in result.message


# ── 阶段 C bug 修复后的集成测试（refresh_project_docs / refresh_asset_summary / get_asset_summary）──


@pytest.fixture
def delivery_facade_with_doc_refresh(  # type: ignore[no-untyped-def]
    temp_workspace: str,
    db_manager,
    project_repo_with_data,
) -> DeliveryFacade:
    """构造含真实 DocRefreshService + ProjectService（DB 缓存）的 DeliveryFacade

    bug #1 修复后：refresh_project_docs 通过 project_service 查 ProjectInfo 后调 Service。
    fixture 预置 DJ-2026-001(plc) 项目记录，path 为绝对路径。
    """
    project_service = ProjectService(workspace_root=temp_workspace, db=db_manager)
    doc_refresh_service = DocRefreshService(workspace_root=temp_workspace)
    return DeliveryFacade(
        doc_refresh_service=doc_refresh_service,
        report_service=None,
        asset_summary_service=None,
        project_service=project_service,
    )


@pytest.fixture
def delivery_facade_with_asset_summary(  # type: ignore[no-untyped-def]
    temp_workspace: str,
    db_manager,
    project_repo_with_data,
) -> DeliveryFacade:
    """构造含真实 AssetSummaryService + ProjectService（DB 缓存）的 DeliveryFacade

    bug #2/#3 修复后：refresh_asset_summary/get_asset_summary 通过 project_service 查
    ProjectInfo 后调 build_summary(project_path, stack, project_type)。
    """
    project_service = ProjectService(workspace_root=temp_workspace, db=db_manager)
    asset_summary_service = AssetSummaryService()
    return DeliveryFacade(
        doc_refresh_service=None,
        report_service=None,
        asset_summary_service=asset_summary_service,
        project_service=project_service,
    )


def test_delivery_facade_int_refresh_project_docs_plc_dry_run(
    delivery_facade_with_doc_refresh: DeliveryFacade,
) -> None:
    """集成测试：refresh_project_docs 对 PLC 项目 dry_run=True

    bug #1 修复后链路：Facade → project_service.get_project_cached → DocRefreshService.refresh_project_documents(project_info, dry_run)
    PLC 项目目录无完整文档结构，refresh 返回 issues 但 success=True。
    """
    result = delivery_facade_with_doc_refresh.refresh_project_docs("DJ-2026-001", dry_run=True)
    assert result.success is True
    assert isinstance(result.payload, RefreshProjectDocsResultDTO)
    assert result.payload.project_id == "DJ-2026-001"
    assert result.payload.dry_run is True
    # issues 是 list（可能含"未找到可刷新的 PLC 文档"等）
    assert isinstance(result.payload.issues, list)


def test_delivery_facade_int_refresh_project_docs_python_project(
    delivery_facade_with_doc_refresh: DeliveryFacade,
) -> None:
    """集成测试：refresh_project_docs 对 Python 项目返回 success=True + issues 含"仅 PLC"

    Python 项目 stack != plc，DocRefreshService 直接返回 issues=["仅 PLC 项目支持 doc refresh"]。
    """
    result = delivery_facade_with_doc_refresh.refresh_project_docs("SW-2026-001", dry_run=False)
    assert result.success is True
    assert result.payload.project_id == "SW-2026-001"  # type: ignore[union-attr]
    assert result.payload.dry_run is False  # type: ignore[union-attr]
    assert result.payload.updated is False  # type: ignore[union-attr]
    # issues 应含"仅 PLC 项目支持 doc refresh"
    assert any("仅 PLC" in issue for issue in result.payload.issues)  # type: ignore[union-attr]


def test_delivery_facade_int_refresh_project_docs_project_not_found(
    delivery_facade_with_doc_refresh: DeliveryFacade,
) -> None:
    """集成测试：refresh_project_docs 项目不存在时返回 success=False

    project_service.get_project_cached 未命中 + list_projects 未命中 → "项目不存在"
    """
    result = delivery_facade_with_doc_refresh.refresh_project_docs("NOT-EXIST-999")
    assert result.success is False
    assert result.payload is None
    assert "项目不存在" in result.message


def test_delivery_facade_int_refresh_project_docs_no_project_service(
    temp_workspace: str,
) -> None:
    """集成测试：project_service=None 时 refresh_project_docs 返回 '未注入 project_service'"""
    doc_refresh_service = DocRefreshService(workspace_root=temp_workspace)
    facade = DeliveryFacade(
        doc_refresh_service=doc_refresh_service,
        report_service=None,
        asset_summary_service=None,
        project_service=None,
    )

    result = facade.refresh_project_docs("DJ-2026-001")
    assert result.success is False
    assert "未注入 project_service" in result.message


def test_delivery_facade_int_refresh_asset_summary_plc(
    delivery_facade_with_asset_summary: DeliveryFacade,
) -> None:
    """集成测试：refresh_asset_summary 对 PLC 项目返回 build_summary 结果

    bug #2 修复后链路：Facade → project_service 查 ProjectInfo → AssetSummaryService.build_summary(path, stack, project_type)
    PLC 项目目录无 02_PLC程序/工程资产/，build_summary 返回 status="missing"。
    """
    result = delivery_facade_with_asset_summary.refresh_asset_summary("DJ-2026-001")
    assert result.success is True
    assert isinstance(result.payload, RefreshAssetSummaryResultDTO)
    # result 是 build_summary 返回的 dict
    assert isinstance(result.payload.result, dict)
    assert result.payload.result["status"] in ("missing", "healthy", "not_applicable")
    # PLC 项目 + 无工程资产目录，预期 status="missing"
    assert result.payload.result["status"] == "missing"
    assert result.payload.result["asset_dir_exists"] is False


def test_delivery_facade_int_refresh_asset_summary_python_not_applicable(
    delivery_facade_with_asset_summary: DeliveryFacade,
) -> None:
    """集成测试：refresh_asset_summary 对 Python 项目返回 not_applicable

    Python 项目 stack != plc，build_summary 直接返回 status="not_applicable"。
    """
    result = delivery_facade_with_asset_summary.refresh_asset_summary("SW-2026-001")
    assert result.success is True
    assert isinstance(result.payload, RefreshAssetSummaryResultDTO)
    assert result.payload.result["status"] == "not_applicable"
    assert "仅 PLC" in result.payload.result["issue_messages"][0]


def test_delivery_facade_int_refresh_asset_summary_missing_project_id(
    delivery_facade_with_asset_summary: DeliveryFacade,
) -> None:
    """集成测试：refresh_asset_summary 缺 project_id 时返回 success=False"""
    result = delivery_facade_with_asset_summary.refresh_asset_summary("")
    assert result.success is False
    assert result.payload is None
    assert "缺少 project_id 参数" in result.message


def test_delivery_facade_int_refresh_asset_summary_no_project_service(
    temp_workspace: str,
) -> None:
    """集成测试：project_service=None 时 refresh_asset_summary 返回 '未注入 project_service'"""
    asset_summary_service = AssetSummaryService()
    facade = DeliveryFacade(
        doc_refresh_service=None,
        report_service=None,
        asset_summary_service=asset_summary_service,
        project_service=None,
    )

    result = facade.refresh_asset_summary("DJ-2026-001")
    assert result.success is False
    assert "未注入 project_service" in result.message


def test_delivery_facade_int_get_asset_summary_plc(
    delivery_facade_with_asset_summary: DeliveryFacade,
) -> None:
    """集成测试：get_asset_summary 对 PLC 项目返回 build_summary 结果

    bug #3 修复后链路：同 refresh_asset_summary，但返回 AssetSummaryDTO（data 字段）。
    """
    result = delivery_facade_with_asset_summary.get_asset_summary("DJ-2026-001")
    assert result.success is True
    assert isinstance(result.payload, AssetSummaryDTO)
    assert isinstance(result.payload.data, dict)
    assert result.payload.data["status"] == "missing"
    assert result.payload.data["asset_dir_exists"] is False


def test_delivery_facade_int_get_asset_summary_python_not_applicable(
    delivery_facade_with_asset_summary: DeliveryFacade,
) -> None:
    """集成测试：get_asset_summary 对 Python 项目返回 not_applicable"""
    result = delivery_facade_with_asset_summary.get_asset_summary("SW-2026-001")
    assert result.success is True
    assert isinstance(result.payload, AssetSummaryDTO)
    assert result.payload.data["status"] == "not_applicable"
