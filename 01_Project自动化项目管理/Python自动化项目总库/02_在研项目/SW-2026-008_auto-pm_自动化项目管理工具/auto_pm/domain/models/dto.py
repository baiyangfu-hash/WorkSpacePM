"""PLC-HMI 概念映射：UDT 自定义数据类型（通用数据传输对象（DTO 基类/通用数据结构））

像 PLC 的 UDT（User Defined Type），定义数据结构。

--- 原始注释 ---

GUI / API 层 DTO

供 PySide6 视图层和 CLI 使用，与核心模型分离，避免内部字段暴露给前端。
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from auto_pm.models.change import ChangeSummary
from auto_pm.models.enums import Stack
from auto_pm.models.project import BusinessLine, Project

T = TypeVar("T")


class ProjectListItem(BaseModel):
    """项目列表项（轻量，左侧列表用）"""

    project_id: str = Field(..., description="项目编号")
    name: str = Field(..., description="项目名称")
    path: str = Field("", description="项目绝对路径")
    stack: Stack = Field(..., description="技术栈")
    version: str = Field("", description="版本号")
    phase: str = Field("", description="阶段")
    business_line: str = Field("", description="业务线")
    change_count: int = Field(0, description="关联变更单数（JOIN 查询）")

    model_config = ConfigDict(from_attributes=True)


class ProjectDetailDTO(BaseModel):
    """项目详情 DTO（PySide6 项目工作区详情页用）

    包含完整 Project 字段 + 关联变更单列表，供详情视图渲染。
    """

    project_id: str = Field(..., description="项目编号")
    name: str = Field(..., description="项目名称")
    path: str = Field(..., description="项目绝对路径")
    stack: Stack = Field(..., description="技术栈")
    version: str = Field("", description="版本号")
    description: str = Field("", description="描述")
    source: str = Field("", description="元数据来源")
    phase: str = Field("", description="项目阶段")
    business_line: BusinessLine = Field("", description="业务线")
    extra: dict[str, object] = Field(default_factory=dict, description="额外字段")
    changes: list[ChangeSummary] = Field(default_factory=list, description="关联变更单列表")
    change_count: int = Field(0, description="关联变更单数")

    model_config = ConfigDict(from_attributes=True)


class ProjectDetail(BaseModel):
    """项目详情（右侧面板用）"""

    project: Project = Field(..., description="项目完整信息")
    changes: list[ChangeSummary] = Field(default_factory=list, description="关联变更单列表")
    doc_count: int = Field(0, description="文档数")
    last_check: str = Field("", description="最后规范检查结果")

    model_config = ConfigDict(from_attributes=True)


class ProjectCreateRequest(BaseModel):
    """创建项目请求（新建项目弹窗）"""

    project_id: str = Field(..., pattern=r"^[A-Z]+-\d{4}-\d{3}$", description="项目编号")
    project_name: str = Field(..., min_length=1, description="项目名称")
    stack: Stack = Field(..., description="技术栈: plc/python")
    template: str = Field("plc-standard", description="模板名")
    description: str = Field("", description="描述")
    author: str = Field("", description="作者")


class ProjectUpdateRequest(BaseModel):
    """更新项目元数据请求"""

    phase: str | None = Field(None, description="阶段")
    description: str | None = Field(None, description="描述")
    version: str | None = Field(None, description="版本号")


class DashboardSummaryDTO(BaseModel):
    """项目驾驶舱摘要 DTO（首页/报告页聚合数据）"""

    total_projects: int = Field(0, description="项目总数")
    phase_counts: dict[str, int] = Field(
        default_factory=dict,
        description="阶段分布: developing/commissioning/production/archived",
    )
    open_change_count: int = Field(0, description="未关闭变更数")
    failed_check_project_count: int = Field(0, description="PLC 检查失败项目数")
    failed_check_project_ids: list[str] = Field(
        default_factory=list,
        description="PLC 检查失败项目编号列表",
    )
    # V0.4.1 Step 3: PLC 检查不适用项目数（Python 项目）
    # 与 failed_check 区分：not_applicable 是「不适用 PLC 检查」的正常口径，
    # 不计入 failed_check，避免驾驶舱误报
    not_applicable_project_count: int = Field(0, description="PLC 检查不适用项目数（Python 项目）")
    not_applicable_project_ids: list[str] = Field(
        default_factory=list,
        description="PLC 检查不适用项目编号列表",
    )
    recent_activities: list[dict[str, Any]] = Field(
        default_factory=list,
        description="最近活动摘要列表（CHG-106: 格式 {type, title, desc, time}）",
    )
    risk_hints: list[str] = Field(
        default_factory=list,
        description="交付风险/健康提示列表",
    )
    # CHG-106 新增：技术债计数（解析 006 报告 §0.1 总览表）
    tech_debt_count: int = Field(0, description="遗留技术债数（剩余未治理）")
    tech_debt_total: int = Field(0, description="技术债总数（历史累计）")
    # CHG-106 新增：测试通过率（读取 .pytest_cache）
    test_pass_rate: float = Field(0.0, description="自动化测试通过率（0-100）")
    test_total: int = Field(0, description="自动化测试总数")


class AssetSummaryViewDTO(BaseModel):
    """工程资产摘要视图 DTO（OverviewTab 展示用）"""

    status: str = Field("unknown", description="资产健康状态")
    badge_label: str = Field("未知", description="状态徽标文本")
    badge_bg: str = Field("#95a5a6", description="徽标背景色")
    badge_fg: str = Field("#ffffff", description="徽标前景色")
    status_text: str = Field("未知", description="状态说明文案")
    reason: str = Field("", description="不适用或降级原因")
    io_count: int = Field(0, description="IO 点数")
    program_block_count: int = Field(0, description="程序块数量")
    communication_count: int = Field(0, description="通讯对象数量")
    issue_messages: list[str] = Field(default_factory=list, description="问题摘要列表")

    @classmethod
    def from_asset_summary(
        cls,
        asset_summary: dict[str, Any] | None,
        *,
        status_badges: dict[str, tuple[str, str, str]],
        status_texts: dict[str, str],
    ) -> AssetSummaryViewDTO:
        """从 ProjectScanner 注入的原始 asset_summary 生成视图 DTO"""
        if not isinstance(asset_summary, dict):
            return cls(
                status="unknown",
                badge_label="未知",
                badge_bg="#95a5a6",
                badge_fg="#ffffff",
                status_text="未知",
                reason="暂无资产摘要",
                io_count=0,
                program_block_count=0,
                communication_count=0,
            )

        status = str(asset_summary.get("status", "unknown"))
        badge_label, badge_bg, badge_fg = status_badges.get(
            status, ("未知", "#95a5a6", "#ffffff")
        )
        issue_messages = cls._normalize_issue_messages(asset_summary.get("issue_messages"))

        return cls(
            status=status,
            badge_label=badge_label,
            badge_bg=badge_bg,
            badge_fg=badge_fg,
            status_text=status_texts.get(status, status),
            reason=issue_messages[0] if status == "not_applicable" and issue_messages else "",
            io_count=cls._extract_count(asset_summary, "io_points"),
            program_block_count=cls._extract_count(asset_summary, "program_blocks"),
            communication_count=cls._extract_count(asset_summary, "communications"),
            issue_messages=issue_messages,
        )

    @staticmethod
    def _extract_count(asset_summary: dict[str, Any], key: str) -> int:
        """从原始资产摘要中提取数量字段"""
        sub = asset_summary.get(key)
        if isinstance(sub, dict):
            try:
                return int(sub.get("count", 0))
            except (TypeError, ValueError):
                return 0
        return 0

    @staticmethod
    def _normalize_issue_messages(value: object) -> list[str]:
        """标准化问题列表，过滤空值和非字符串项"""
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]


class ScanResult(BaseModel):
    """扫描结果"""

    scan_type: str = Field(..., description="扫描类型: full/incremental")
    projects_found: int = Field(0, description="发现项目数")
    changes_found: int = Field(0, description="发现变更单数")
    duration_ms: int = Field(0, description="耗时(毫秒)")
    status: str = Field("success", description="状态: success/failed")
    message: str = Field("", description="附加消息")


class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应（pywebview JS bridge 返回格式）"""

    success: bool = Field(True, description="是否成功")
    data: T | None = Field(None, description="响应数据")
    error: str | None = Field(None, description="错误信息")
    message: str = Field("", description="附加消息")
    timestamp: str = Field("", description="时间戳 ISO8601")
