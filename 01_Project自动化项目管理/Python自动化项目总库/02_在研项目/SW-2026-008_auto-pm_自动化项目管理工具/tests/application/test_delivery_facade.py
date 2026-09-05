"""DeliveryFacade 单元测试

覆盖 DeliveryFacade 的 7 个方法：
- refresh_project_docs（含 dry_run 透传）
- get_project_report / get_change_report / get_spec_report / get_scan_report
- refresh_asset_summary
- get_asset_summary

M4 第 2 批重构后：方法返回带类型 DTO（不再是裸 dict）。
后续 DTO 细化：5 个 DTO 从 dict 包装升级为具体字段。
阶段 C bug 修复后：
- refresh_project_docs 注入 project_service 查 ProjectInfo
- refresh_asset_summary/get_asset_summary 改为接收 project_id，调 build_summary
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

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

# ── mock helpers ──────────────────────────────────────


def _raise(exc: Exception) -> Any:
    """返回一个调用即抛出指定异常的函数（兼容任意参数签名）"""

    def _fn(*args: Any, **kwargs: Any) -> Any:
        raise exc

    return _fn


def _make_project_info(
    project_id: str = "PROJ-001",
    name: str = "测试项目",
    stack: str = "plc",
    path: str = "/tmp/proj",
) -> SimpleNamespace:
    """构造 ProjectInfo mock（含 project_id/name/path/stack/project_type）"""
    return SimpleNamespace(
        project_id=project_id,
        name=name,
        path=path,
        stack=stack,
        project_type="single_machine",
    )


def _make_project_service(*projects: Any) -> SimpleNamespace:
    """构造 project_service mock

    - get_project_cached(pid) → 优先 DB 缓存返回，无则抛 RuntimeError（fallback list_projects）
    - list_projects() → 返回所有 projects
    """
    if not projects:
        projects = (_make_project_info(),)

    def _get_cached(pid: str) -> Any:
        for p in projects:
            if p.project_id == pid:
                return p
        return None  # DB 缓存未命中（不抛异常，让 Facade fallback 到 list_projects）

    def _list() -> Any:
        return list(projects)

    return SimpleNamespace(
        get_project_cached=_get_cached,
        get_project=_get_cached,
        list_projects=_list,
    )


def _make_doc_refresh_result(**overrides: Any) -> SimpleNamespace:
    """构造 DocRefreshResult-like 对象（有 to_dict() 方法）"""
    data = {
        "project_id": "PROJ-001",
        "dry_run": False,
        "updated": True,
        "refreshed_files": [
            {"file_path": "/docs/readme.md", "block_keys": ["plc-io-overview"], "changed": True}
        ],
        "issues": [],
    }
    data.update(overrides)

    def _to_dict() -> Any:
        return data

    obj = SimpleNamespace(**data)
    obj.to_dict = _to_dict
    return obj


def _make_doc_refresh_service(**overrides: Any) -> SimpleNamespace:
    """构造 doc_refresh_service mock

    refresh_project_documents(project_info, dry_run) — 接收 ProjectInfo 对象
    """
    captured: dict[str, Any] = {}

    def _refresh(project_info, dry_run=False) -> Any:  # type: ignore[no-untyped-def]
        captured["project_info"] = project_info
        captured["dry_run"] = dry_run
        project_id = getattr(project_info, "project_id", "PROJ-001")
        return overrides.get(
            "result",
            _make_doc_refresh_result(project_id=project_id, dry_run=dry_run),
        )

    svc = SimpleNamespace(refresh_project_documents=_refresh)
    svc.captured = captured
    return svc


def _make_report_service(**overrides: Any) -> SimpleNamespace:
    """构造 report_service mock"""
    return SimpleNamespace(
        get_project_overview=overrides.get(
            "get_project_overview",
            lambda: {
                "total": 5,
                "by_stack": {"plc": 3, "python": 2},
                "by_phase": {"developing": 5},
                "by_business_line": {"SW": 5},
            },
        ),
        get_change_overview=overrides.get(
            "get_change_overview",
            lambda: {
                "total": 10,
                "by_status": {"draft": 5, "closed": 5},
                "by_domain": {"ELEC": 10},
            },
        ),
        get_spec_report=overrides.get(
            "get_spec_report",
            lambda: {
                "total": 2,
                "found": 1,
                "missing": 1,
                "by_stack": {"plc": {"total": 1, "found": 1, "missing": []}},
                "missing_codes": ["LSP-001"],
            },
        ),
        get_scan_report=overrides.get(
            "get_scan_report",
            lambda: {
                "latest": {"timestamp": "2026-07-07T10:00"},
                "last_sync_time": "2026-07-07 10:00",
                "is_cache_available": True,
            },
        ),
    )


def _make_asset_service(**overrides: Any) -> SimpleNamespace:
    """构造 asset_summary_service mock

    build_summary(project_path, stack, project_type) — 阶段 C bug #2/#3 修复后的正确接口
    """
    captured: dict[str, Any] = {}

    def _build_summary(project_path, stack, project_type="") -> Any:  # type: ignore[no-untyped-def]
        captured["project_path"] = project_path
        captured["stack"] = stack
        captured["project_type"] = project_type
        return overrides.get("result", {"assets": 100})

    svc = SimpleNamespace(build_summary=_build_summary)
    svc.captured = captured
    return svc


# ── refresh_project_docs 测试 ──────────────────────────────


def test_refresh_project_docs_success() -> None:
    """正常调用返回 RefreshProjectDocsResultDTO 且字段正确"""
    svc = _make_doc_refresh_service()
    project_svc = _make_project_service()
    facade = DeliveryFacade(doc_refresh_service=svc, project_service=project_svc)

    res = facade.refresh_project_docs("PROJ-001")

    assert res.success is True
    assert isinstance(res.payload, RefreshProjectDocsResultDTO)
    assert res.payload.project_id == "PROJ-001"
    assert res.payload.dry_run is False
    assert res.payload.updated is True
    assert len(res.payload.refreshed_files) == 1
    assert res.payload.refreshed_files[0]["file_path"] == "/docs/readme.md"
    assert res.payload.issues == []
    # 验证 Service 收到的是 ProjectInfo 对象
    assert svc.captured["project_info"].project_id == "PROJ-001"
    assert svc.captured["dry_run"] is False


def test_refresh_project_docs_dry_run_pass_through() -> None:
    """dry_run=True 透传给 service.refresh_project_documents()"""
    svc = _make_doc_refresh_service()
    project_svc = _make_project_service()
    facade = DeliveryFacade(doc_refresh_service=svc, project_service=project_svc)

    res = facade.refresh_project_docs("PROJ-001", dry_run=True)

    assert res.success is True
    assert res.payload.dry_run is True  # type: ignore[union-attr]
    assert svc.captured["dry_run"] is True


def test_refresh_project_docs_no_service() -> None:
    """doc_refresh_service=None 时返回 success=False + payload=None"""
    facade = DeliveryFacade()

    res = facade.refresh_project_docs("PROJ-001")

    assert res.success is False
    assert res.payload is None
    assert "No doc_refresh_service" in res.message


def test_refresh_project_docs_no_project_service() -> None:
    """project_service=None 时返回 '项目不存在或未注入 project_service'"""
    svc = _make_doc_refresh_service()
    facade = DeliveryFacade(doc_refresh_service=svc, project_service=None)

    res = facade.refresh_project_docs("PROJ-001")

    assert res.success is False
    assert res.payload is None
    assert "未注入 project_service" in res.message


def test_refresh_project_docs_project_not_found() -> None:
    """project_service 未找到对应项目时返回 success=False"""
    svc = _make_doc_refresh_service()
    project_svc = _make_project_service()  # 默认含 PROJ-001
    facade = DeliveryFacade(doc_refresh_service=svc, project_service=project_svc)

    res = facade.refresh_project_docs("NOT-EXIST")

    assert res.success is False
    assert res.payload is None
    assert "项目不存在" in res.message


def test_refresh_project_docs_exception() -> None:
    """service.refresh_project_documents() 抛异常时返回 success=False + payload=None"""
    svc = SimpleNamespace(refresh_project_documents=_raise(Exception("doc boom")))
    project_svc = _make_project_service()
    facade = DeliveryFacade(doc_refresh_service=svc, project_service=project_svc)

    res = facade.refresh_project_docs("PROJ-001")

    assert res.success is False
    assert res.payload is None
    assert "doc boom" in res.message


# ── get_project_report 测试 ──────────────────────────────


def test_get_project_report_success() -> None:
    """正常调用返回 ProjectReportDTO 且字段正确（细化字段）"""
    svc = _make_report_service(
        get_project_overview=lambda: {
            "total": 5,
            "by_stack": {"plc": 3, "python": 2},
            "by_phase": {"developing": 5},
            "by_business_line": {"SW": 5},
        },
    )
    facade = DeliveryFacade(report_service=svc)

    res = facade.get_project_report()

    assert res.success is True
    assert isinstance(res.payload, ProjectReportDTO)
    assert res.payload.total == 5
    assert res.payload.by_stack == {"plc": 3, "python": 2}
    assert res.payload.by_phase == {"developing": 5}
    assert res.payload.by_business_line == {"SW": 5}


def test_get_project_report_no_service() -> None:
    """report_service=None 时返回 success=False + payload=None"""
    facade = DeliveryFacade()

    res = facade.get_project_report()

    assert res.success is False
    assert res.payload is None
    assert "No report_service" in res.message


# ── get_change_report / get_spec_report / get_scan_report 测试 ──


def test_get_change_report_success() -> None:
    """正常调用返回 ChangeReportDTO 且字段正确（细化字段）"""
    svc = _make_report_service(
        get_change_overview=lambda: {
            "total": 10,
            "by_status": {"draft": 5, "closed": 5},
            "by_domain": {"ELEC": 10},
        },
    )
    facade = DeliveryFacade(report_service=svc)

    res = facade.get_change_report()

    assert res.success is True
    assert isinstance(res.payload, ChangeReportDTO)
    assert res.payload.total == 10
    assert res.payload.by_status == {"draft": 5, "closed": 5}
    assert res.payload.by_domain == {"ELEC": 10}


def test_get_spec_report_success() -> None:
    """正常调用返回 SpecReportDTO 且字段正确（细化字段）"""
    svc = _make_report_service(
        get_spec_report=lambda: {
            "total": 2,
            "found": 1,
            "missing": 1,
            "by_stack": {"plc": {"total": 1, "found": 1, "missing": []}},
            "missing_codes": ["LSP-001"],
        },
    )
    facade = DeliveryFacade(report_service=svc)

    res = facade.get_spec_report()

    assert res.success is True
    assert isinstance(res.payload, SpecReportDTO)
    assert res.payload.total == 2
    assert res.payload.found == 1
    assert res.payload.missing == 1
    assert res.payload.missing_codes == ["LSP-001"]


def test_get_scan_report_success() -> None:
    """正常调用返回 ScanReportDTO 且字段正确（细化字段）"""
    svc = _make_report_service(
        get_scan_report=lambda: {
            "latest": {"timestamp": "2026-07-07T10:00"},
            "last_sync_time": "2026-07-07 10:00",
            "is_cache_available": True,
        },
    )
    facade = DeliveryFacade(report_service=svc)

    res = facade.get_scan_report()

    assert res.success is True
    assert isinstance(res.payload, ScanReportDTO)
    assert res.payload.latest == {"timestamp": "2026-07-07T10:00"}
    assert res.payload.last_sync_time == "2026-07-07 10:00"
    assert res.payload.is_cache_available is True


# ── refresh_asset_summary 测试 ──────────────────────────────


def test_refresh_asset_summary_success() -> None:
    """正常调用返回 RefreshAssetSummaryResultDTO 且 result 字段正确"""
    svc = _make_asset_service(result={"refreshed": True, "count": 50})
    project_svc = _make_project_service()
    facade = DeliveryFacade(asset_summary_service=svc, project_service=project_svc)

    res = facade.refresh_asset_summary("PROJ-001")

    assert res.success is True
    assert isinstance(res.payload, RefreshAssetSummaryResultDTO)
    assert res.payload.result == {"refreshed": True, "count": 50}
    # 验证 build_summary 收到正确的参数
    assert svc.captured["stack"] == "plc"
    assert svc.captured["project_type"] == "single_machine"


def test_refresh_asset_summary_no_service() -> None:
    """asset_summary_service=None 时返回 success=False + payload=None"""
    facade = DeliveryFacade()

    res = facade.refresh_asset_summary("PROJ-001")

    assert res.success is False
    assert res.payload is None
    assert "No asset_summary_service" in res.message


def test_refresh_asset_summary_missing_project_id() -> None:
    """缺 project_id 参数时返回 success=False"""
    svc = _make_asset_service()
    project_svc = _make_project_service()
    facade = DeliveryFacade(asset_summary_service=svc, project_service=project_svc)

    res = facade.refresh_asset_summary("")

    assert res.success is False
    assert res.payload is None
    assert "缺少 project_id 参数" in res.message


def test_refresh_asset_summary_no_project_service() -> None:
    """project_service=None 时返回 '未注入 project_service'"""
    svc = _make_asset_service()
    facade = DeliveryFacade(asset_summary_service=svc, project_service=None)

    res = facade.refresh_asset_summary("PROJ-001")

    assert res.success is False
    assert res.payload is None
    assert "未注入 project_service" in res.message


def test_refresh_asset_summary_exception() -> None:
    """service.build_summary() 抛异常时返回 success=False + payload=None"""
    svc = SimpleNamespace(build_summary=_raise(Exception("asset boom")))
    project_svc = _make_project_service()
    facade = DeliveryFacade(asset_summary_service=svc, project_service=project_svc)

    res = facade.refresh_asset_summary("PROJ-001")

    assert res.success is False
    assert res.payload is None
    assert "asset boom" in res.message


# ── get_asset_summary 测试 ──────────────────────────────


def test_get_asset_summary_success() -> None:
    """正常调用返回 AssetSummaryDTO 且 data 字段正确"""
    svc = _make_asset_service(result={"assets": 100, "healthy": 95})
    project_svc = _make_project_service()
    facade = DeliveryFacade(asset_summary_service=svc, project_service=project_svc)

    res = facade.get_asset_summary("PROJ-001")

    assert res.success is True
    assert isinstance(res.payload, AssetSummaryDTO)
    assert res.payload.data == {"assets": 100, "healthy": 95}


def test_get_asset_summary_no_service() -> None:
    """asset_summary_service=None 时返回 success=False + payload=None"""
    facade = DeliveryFacade()

    res = facade.get_asset_summary("PROJ-001")

    assert res.success is False
    assert res.payload is None
    assert "No asset_summary_service" in res.message


def test_get_asset_summary_missing_project_id() -> None:
    """缺 project_id 参数时返回 success=False"""
    svc = _make_asset_service()
    project_svc = _make_project_service()
    facade = DeliveryFacade(asset_summary_service=svc, project_service=project_svc)

    res = facade.get_asset_summary("")

    assert res.success is False
    assert res.payload is None
    assert "缺少 project_id 参数" in res.message
