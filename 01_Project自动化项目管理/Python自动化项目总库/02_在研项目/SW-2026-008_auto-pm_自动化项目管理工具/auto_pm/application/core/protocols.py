"""PLC-HMI 概念映射：SFB 库函数（接口协议（类型定义/抽象基类/协议类））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

Service 层 Protocol 接口定义（M3-Iter3）

定义 Service 层对外契约的 Protocol 接口，实现依赖倒置：
- UI/CLI 层依赖 Protocol，不依赖具体 Service 实现
- 便于单元测试时用 Fake/Mock 替换真实 Service
- 为未来扩展（如 RemoteProjectService）预留接口

Protocol 是结构性子类型（duck typing 的静态化），Service 无需显式继承。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from auto_pm.models import (
    ChangeRequest,
    ChangeSummary,
    ProjectInfo,
    ProjectListItem,
)

# ── Project 域 ────────────────────────────────────────────


@runtime_checkable
class ProjectServiceProtocol(Protocol):
    """项目服务接口契约

    定义项目 CRUD + 查询 + 缓存同步的对外方法。
    ProjectService 实现此接口（无需显式继承）。
    """

    def list_projects(self, scan_depth: int = 4) -> list[ProjectInfo]:
        """扫描工作空间，返回所有项目"""
        ...

    def get_project(self, project_id: str) -> ProjectInfo | None:
        """按 project_id 查询项目"""
        ...

    def get_project_cached(self, project_id: str) -> ProjectInfo | None:
        """从 DB 缓存按 project_id 查询项目"""
        ...

    workspace_root: str

    def clear_cache(self) -> dict[str, Any]:
        """清除 DB 缓存并重新初始化 schema"""
        ...

    def find_project_path(self, project_id: str) -> str | None:
        """按 project_id 查询项目路径"""
        ...

    def search_projects(self, keyword: str) -> list[ProjectInfo]:
        """关键字搜索项目"""
        ...

    def import_project(
        self,
        src_path: str,
        business_line: str | None = None,
        move: bool = False,
        force: bool = False,
    ) -> str:
        """导入外部项目目录到工作空间"""
        ...

    def update_project_meta(self, project_id: str, **kwargs: str) -> ProjectInfo:
        """更新项目元数据"""
        ...

    def list_projects_filtered(
        self,
        stack: str | None = None,
        phase: str | None = None,
        business_line: str | None = None,
    ) -> list[ProjectInfo]:
        """按条件筛选项目"""
        ...

    def list_projects_with_change_count(self) -> list[ProjectListItem]:
        """返回带变更数统计的项目列表"""
        ...

    def generate_project_code(self, business_line: str) -> str:
        """自动生成项目编号：{业务线}-{年份}-{序号:03d}"""
        ...

    def sync_to_cache(self, force_full: bool = False) -> dict[str, Any]:
        """同步文件系统项目到 DB 缓存"""
        ...

    def get_last_sync_time(self) -> str:
        """获取上次同步时间（格式 YYYY-MM-DD HH:MM，无记录返回 '—'）"""
        ...

    def init_project_pm_framework(
        self,
        project_path: str,
        project_id: str,
        project_name: str,
        stack_type: str,
        author: str | None = None,
    ) -> None:
        """为指定路径的项目执行非侵入式 PM 基础文档与目录的初始化补全"""
        ...

    def is_cache_available(self) -> bool:
        """DB 缓存是否可用"""
        ...

    def get_project_count(self) -> int:
        """获取项目总数（优先查缓存）"""
        ...

    def get_db_path(self) -> str:
        """获取 DB 文件路径（若未初始化则返回空字符串）"""
        ...

    def is_git_hooks_installed(self, project_path: str) -> bool:
        """检查指定项目是否已安装 auto-pm Git 提交门禁钩子"""
        ...

    def install_git_hooks(self, project_path: str) -> dict[str, Any]:
        """为指定项目安装离线 Git Pre-commit 提交门禁与自愈钩子"""
        ...

    def uninstall_git_hooks(self, project_path: str) -> dict[str, Any]:
        """为指定项目卸载 Git Pre-commit 提交门禁钩子"""
        ...


@runtime_checkable
class ProjectScannerProtocol(Protocol):
    """项目扫描器接口契约"""

    def scan(self, scan_depth: int = 4) -> list[ProjectInfo]:
        """扫描工作空间，返回所有项目"""
        ...

    def try_identify_project(self, project_path: str) -> ProjectInfo | None:
        """尝试识别目录是否为项目"""
        ...


# ── Change 域 ─────────────────────────────────────────────


@runtime_checkable
class ChangeServiceProtocol(Protocol):
    """变更管理服务接口契约

    定义变更单 CRUD + 状态流转的对外方法。
    ChangeService 实现此接口（无需显式继承）。
    """

    def create_change_request(
        self,
        project_id: str,
        domain: str,
        business_nature: str,
        impact_scope: list[str],
        applicant: str,
        background: str,
        necessity: str,
        references: str = "",
        planned_date: str | None = None,
        urgency: str = "normal",
    ) -> ChangeRequest:
        """创建变更单"""
        ...

    def list_change_requests(
        self,
        project_id: str,
        status: str | None = None,
        domain: str | None = None,
    ) -> list[ChangeSummary]:
        """列出变更单，支持筛选"""
        ...

    def get_change_request(
        self, change_number: str, project_id: str | None = None
    ) -> ChangeRequest | None:
        """获取变更单完整内容"""
        ...

    def transition_status(
        self,
        change_number: str,
        new_status: str,
        approver: str = "",
        comment: str = "",
        verification_conclusion: str = "全部通过",
        allow_partial_verification: bool = False,
        project_id: str | None = None,
    ) -> ChangeRequest | None:
        """状态流转"""
        ...

    def list_all_changes(
        self,
        status: str | None = None,
        domain: str | None = None,
        urgency: str | None = None,
        project_id: str | None = None,
    ) -> list[ChangeSummary]:
        """跨项目查询所有变更单"""
        ...

    def update_change_request(
        self,
        change_number: str,
        lookup_project_id: str | None = None,
        **kwargs: Any,
    ) -> ChangeRequest | None:
        """修改变更单字段"""
        ...

    def delete_change_request(self, change_number: str, project_id: str | None = None) -> bool:
        """删除变更单"""
        ...

    def list_approval_history(self, change_number: str, project_id: str | None = None) -> list[Any]:
        """查询变更单审批流转历史（供 GUI 审批时间线使用）"""
        ...

    def get_impact_analysis(self, change_number: str, project_id: str | None = None) -> Any | None:
        """查询变更单的影响分析记录（供 GUI 验证摘要使用，M3 新增）"""
        ...


# ── PLC 域 ────────────────────────────────────────────────


@runtime_checkable
class PlcServiceProtocol(Protocol):
    """PLC 服务接口契约（M3-Iter4 将提供实现）

    封装 PlcChecker/PlcRepairer，提供统一的 PLC 项目检查/修复/标准化入口。
    """

    def check(self, project_path: str, fix: bool = False) -> Any:
        """检查 PLC 项目规范性"""
        ...

    def repair(self, project_path: str) -> Any:
        """修复 PLC 项目规范问题"""
        ...

    def standardize(self, project_path: str, dry_run: bool = False) -> Any:
        """标准化 PLC 项目命名"""
        ...


# ── Dashboard / Asset 域 ─────────────────────────────────


@runtime_checkable
class DashboardServiceProtocol(Protocol):
    """驾驶舱服务接口契约（M4-2 T8 新增）

    提供 DashboardSummary 聚合数据供 WorkbenchFacade.get_dashboard_snapshot() 调用。
    CHG-106 扩展：新增 get_active_change_for_project 供平台驾驶舱状态机视图调用。
    CHG-123 扩展：新增 get_change_summary_for_project 供项目工作区变更Tab驾驶舱模式调用。
    """

    def get_summary(self) -> Any:
        """返回 DashboardSummary（total_projects/phase_counts/open_change_count 等）"""
        ...

    def get_active_change_for_project(self, project_id: str) -> Any:
        """返回项目最近一条活跃变更单（CHG-106），无活跃变更时返回 None"""
        ...

    def get_change_summary_for_project(self, project_id: str) -> dict[str, Any]:
        """返回项目级变更聚合摘要（CHG-123），含 KPI/状态机/活动时间线"""
        ...


@runtime_checkable
class AssetSummaryServiceProtocol(Protocol):
    """工程资产摘要服务接口契约（M4-2 T8 新增）

    提供 build_summary() 供 WorkbenchFacade/DeliveryFacade 调用。
    """

    def build_summary(
        self,
        project_path: str,
        stack: str,
        project_type: str,
    ) -> dict[str, Any]:
        """构建工程资产摘要（IO 点/程序块/通信变量等）"""
        ...


# ── PmSession / Template 域 ──────────────────────────────


@runtime_checkable
class PmSessionServiceProtocol(Protocol):
    """PM_SESSION 服务接口契约（M4-2 T8 新增）

    提供 generate_view()/check() 供 SystemFacade 调用。
    M5 CHG-117 新增 archive() 供 SystemFacade 调用。
    """

    def generate_view(self) -> dict[str, Any]:
        """生成 PM_SESSION 视图数据"""
        ...

    def check(self) -> dict[str, Any]:
        """执行 PM_SESSION 健康检查"""
        ...

    def archive(self, section: str, keep_recent: int, dry_run: bool) -> dict[str, Any]:
        """归档指定章节的早期内容

        Args:
            section: 章节号（如 "6"/"8"）
            keep_recent: 保留最近 N 行（§8 表示保留最新 N 条 skill_handoff）
            dry_run: 仅预览，不实际修改文件
        """
        ...


@runtime_checkable
class TemplateServiceProtocol(Protocol):
    """模板服务接口契约（M4-2 T8 新增）

    提供 list_templates()/get_template_path()/copy_template() 供 SystemFacade 调用。
    """

    def list_templates(self) -> list[str]:
        """列出所有可用模板名"""
        ...

    def get_template_path(self, template_name: str) -> str:
        """获取模板路径（不存在返回空字符串）"""
        ...

    def copy_template(
        self,
        template_name: str,
        dest_path: str,
        data: dict[str, Any],
        overwrite: bool = False,
    ) -> dict[str, Any]:
        """复制模板到目标路径并注入变量"""
        ...


# ── Spec 域（Check/Center）──────────────────────────────


@runtime_checkable
class SpecCheckServiceProtocol(Protocol):
    """规范检查服务接口契约（M4-1 T8 新增）

    提供 run() 供 SpecFacade.run_spec_check() 调用。
    """

    def run(
        self,
        check_ids: list[str] | None = None,
        auto_fix: bool = False,
        dry_run: bool = False,
        scope: str = "workspace",
        project_root: Any = None,
    ) -> Any:
        """执行规范检查，返回 CheckOutput（含 results/error_count 等）"""
        ...


@runtime_checkable
class SpecCenterServiceProtocol(Protocol):
    """规范中心服务接口契约（M4-1 T8 新增）

    提供 get_overview()/list_entries() 供 SpecFacade 调用。
    """

    def get_overview(self) -> Any:
        """返回 SpecCenterOverview（spec_count/domain_counts/health_summary 等）"""
        ...

    def list_entries(self, filter_domain: str | None = None) -> list[Any]:
        """列出规范条目（支持按 domain 过滤）"""
        ...


# ── Delivery 域（DocRefresh/Report）─────────────────────


@runtime_checkable
class DocRefreshServiceProtocol(Protocol):
    """文档刷新服务接口契约（M4-2 T8 新增）

    提供 refresh_project_documents() 供 DeliveryFacade 调用。
    """

    def refresh_project_documents(
        self,
        project_info: Any,
        dry_run: bool = False,
    ) -> Any:
        """刷新项目文档自动区（返回 DocRefreshResult）"""
        ...


@runtime_checkable
class ReportServiceProtocol(Protocol):
    """报告服务接口契约（M4-2 T8 新增）

    提供 get_project_overview()/get_change_overview()/get_spec_report()/get_scan_report()
    供 DeliveryFacade 调用。
    """

    def get_project_overview(self) -> dict[str, Any]:
        """返回项目概览报告（total/by_stack/by_phase/by_business_line）"""
        ...

    def get_change_overview(self) -> dict[str, Any]:
        """返回变更概览报告（total/by_status/by_domain）"""
        ...

    def get_spec_report(self) -> dict[str, Any]:
        """返回规范报告（total/found/missing/by_stack/missing_codes）"""
        ...

    def get_scan_report(self) -> dict[str, Any]:
        """返回扫描报告（latest/last_sync_time/is_cache_available）"""
        ...


# ── 通用 ──────────────────────────────────────────────────


@runtime_checkable
class ServiceProtocol(Protocol):
    """所有 Service 的基础接口

    标记一个类是 Service 层组件，便于运行时检查。
    """

    @property
    def workspace_root(self) -> str:
        """工作空间根目录"""
        ...
