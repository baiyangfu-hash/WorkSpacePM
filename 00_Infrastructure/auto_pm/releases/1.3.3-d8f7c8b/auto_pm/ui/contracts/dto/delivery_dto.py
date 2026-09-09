"""PLC-HMI 概念映射：HMI 画面数据结构（交付管理 DTO（文档刷新/报告/资产汇总数据））

像 HMI 触摸屏的画面变量结构，定义 QML 画面能显示的数据格式。

--- 原始注释 ---

Delivery 相关 DTO 定义

M4 第 2 批新增：DeliveryFacade 7 方法返回带类型 DTO。
对于 Service 层返回动态 dict 的方法，DTO 用 dict 字段包装（TODO: Service 结构明确后细化字段）。
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RefreshProjectDocsResultDTO:
    """文档刷新结果（对应 refresh_project_docs 返回，M4 第 2 批细化字段）

    对应 DocRefreshResult dataclass 的 to_dict() 输出。
    TODO: Service 调用参数待修复（DocRefreshService.refresh_project_documents 需要 ProjectInfo 非 project_id）。
    """
    project_id: str
    dry_run: bool
    updated: bool
    refreshed_files: list[dict[str, Any]]  # RefreshedDocument 的 dict 表示
    issues: list[str]


@dataclass(frozen=True)
class ProjectReportDTO:
    """项目报告（对应 get_project_report 返回，M4 第 2 批细化字段）

    对应 ReportService.get_project_overview() 返回。
    """
    total: int
    by_stack: dict[str, int]  # {"plc": int, "python": int, "unknown": int}
    by_phase: dict[str, int]  # {"developing": int, "commissioning": int, ...}
    by_business_line: dict[str, int]  # {"SW": int, "DJ": int, ...}


@dataclass(frozen=True)
class ChangeReportDTO:
    """变更报告（对应 get_change_report 返回，M4 第 2 批细化字段）

    对应 ReportService.get_change_overview() 返回。
    """
    total: int
    by_status: dict[str, int]  # 动态键（status 值）
    by_domain: dict[str, int]  # 动态键（domain 值）


@dataclass(frozen=True)
class SpecReportDTO:
    """规范报告（对应 get_spec_report 返回，M4 第 2 批细化字段）

    对应 ReportService.get_spec_report() 返回。
    """
    total: int
    found: int
    missing: int
    by_stack: dict[str, dict[str, Any]]  # 动态键（domain），值是 {"total": int, "found": int, "missing": list[str]}
    missing_codes: list[str]


@dataclass(frozen=True)
class ScanReportDTO:
    """扫描报告（对应 get_scan_report 返回，M4 第 2 批细化字段）

    对应 ReportService.get_scan_report() 返回。
    """
    latest: dict[str, Any] | None  # 最近一次扫描日志
    last_sync_time: str  # "YYYY-MM-DD HH:MM" 或 "—"
    is_cache_available: bool


@dataclass(frozen=True)
class RefreshAssetSummaryResultDTO:
    """资产汇总刷新结果（对应 refresh_asset_summary 返回，M4 第 2 批新增）"""
    result: dict[str, Any]  # asset_summary_service.refresh_all 返回


@dataclass(frozen=True)
class AssetSummaryDTO:
    """资产汇总（对应 get_asset_summary 返回，M4 第 2 批新增）"""
    data: dict[str, Any]  # asset_summary_service.get_summary 返回
