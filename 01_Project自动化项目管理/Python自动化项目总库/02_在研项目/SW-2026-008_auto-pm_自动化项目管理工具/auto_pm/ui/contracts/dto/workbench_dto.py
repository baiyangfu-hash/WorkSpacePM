"""PLC-HMI 概念映射：HMI 画面数据结构（工作台 DTO（项目列表/项目详情/驾驶舱数据））

像 HMI 触摸屏的画面变量结构，定义 QML 画面能显示的数据格式。

--- 原始注释 ---

Workbench 相关 DTO 定义"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DashboardSnapshotDTO:
    total_projects: int
    phase_counts: dict[str, int]
    open_change_count: int
    failed_check_project_count: int
    not_applicable_project_count: int
    recent_activities: list[dict[str, Any]]
    risk_hints: list[dict[str, Any]]
    failed_check_project_ids: list[str]
    not_applicable_project_ids: list[str]
    # CHG-106 新增：技术债计数 + 测试通过率（KPI 网格数据源）
    tech_debt_count: int = 0
    tech_debt_total: int = 0
    test_pass_rate: float = 0.0
    test_total: int = 0

@dataclass(frozen=True)
class ProjectCardDTO:
    project_id: str
    name: str
    stack: str
    phase: str
    version: str
    health_status: str
    open_change_count: int
    last_activity_at: str | None
    path: str
    business_line: str

@dataclass(frozen=True)
class ProjectWorkspaceDTO:
    project_id: str
    summary: dict[str, Any]
    asset_summary: dict[str, Any] | None
    document_status: dict[str, Any] | None
    vartable_status: dict[str, Any] | None
    pending_actions: list[dict[str, Any]]


@dataclass(frozen=True)
class SettingsSummaryDTO:
    """设置页摘要信息"""

    workspace_root: str
    db_path: str
    project_count: int
    last_sync: str
    db_available: bool


@dataclass(frozen=True)
class RebuildIndexResultDTO:
    """重建索引结果"""

    projects_found: int
    changes_found: int
    message: str


@dataclass(frozen=True)
class ClearCacheResultDTO:
    """清除缓存结果"""

    success: bool
    message: str
