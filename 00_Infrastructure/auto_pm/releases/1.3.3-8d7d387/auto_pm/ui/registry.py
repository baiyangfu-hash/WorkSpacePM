"""PLC-HMI 概念映射：OB1 组织块（初始化扫描）

像 PLC 上电的第一个扫描周期，负责：
1. 初始化所有 DB（数据块 / Service）
2. 装配所有 FB（功能块 / Facade）
3. 注入 HMI 上下文（让 QML 画面能访问 FB）

--- 原始注释 ---
Facade Registry 装配器"""

from typing import Any, TypedDict

from auto_pm.application.change_facade import ChangeFacade
from auto_pm.application.delivery_facade import DeliveryFacade
from auto_pm.application.spec_facade import SpecFacade
from auto_pm.application.system_facade import SystemFacade
from auto_pm.application.workbench_facade import WorkbenchFacade
from auto_pm.change.ledger_reconciler import LedgerReconciler
from auto_pm.core.protocols import (
    AssetSummaryServiceProtocol,
    ChangeServiceProtocol,
    DashboardServiceProtocol,
    DocRefreshServiceProtocol,
    PmSessionServiceProtocol,
    ProjectServiceProtocol,
    ReportServiceProtocol,
    SpecCenterServiceProtocol,
    SpecCheckServiceProtocol,
    TemplateServiceProtocol,
)


class ServiceContainer(TypedDict):
    """FacadeRegistry 装配所需的基础 Service 容器

    所有 key 均为必填（调用方必须提供完整字典）。除 project_service 外，其余
    Service 的工厂函数返回类型为 `Any | None`（如工作空间无 spec_registry.json
    时 spec_check_service 为 None），因此 TypedDict 字段统一标注为 `Protocol | None`；
    Facade 构造函数对 None 有降级处理。
    """

    # Service（工厂函数可能返回 None，Facade 内部降级处理）
    dashboard_service: DashboardServiceProtocol | None
    project_service: ProjectServiceProtocol
    asset_summary_service: AssetSummaryServiceProtocol | None
    pm_session_service: PmSessionServiceProtocol | None
    change_service: ChangeServiceProtocol | None
    spec_check_service: SpecCheckServiceProtocol | None
    spec_center_service: SpecCenterServiceProtocol | None
    index_service: Any | None  # M5 CHG-119: IndexService 无 Protocol，用 Any
    spec_report_service: Any | None  # M5 CHG-120: Spec 域 ReportService 无 Protocol，用 Any
    frontmatter_service: Any | None  # M5 CHG-121: FrontmatterService 无 Protocol，用 Any
    doc_refresh_service: DocRefreshServiceProtocol | None
    report_service: ReportServiceProtocol | None
    template_service: TemplateServiceProtocol | None


class FacadeRegistry:
    """手工依赖注入装配器，负责持有各基础 Service 并组装出 Application Facades"""

    def __init__(self) -> None:
        self.workbench_facade: WorkbenchFacade | None = None
        self.change_facade: ChangeFacade | None = None
        self.spec_facade: SpecFacade | None = None
        self.delivery_facade: DeliveryFacade | None = None
        self.system_facade: SystemFacade | None = None
        self.reload_callback: Any = None

    def initialize(self, services: ServiceContainer, reload_callback: Any = None) -> None:
        """根据传入的基础 Service 字典，装配 Facades"""
        if reload_callback is not None:
            self.reload_callback = reload_callback

        # 取出 services（TypedDict 提供类型安全，无需 cast）
        dashboard_service = services["dashboard_service"]
        project_service = services["project_service"]
        asset_summary_service = services["asset_summary_service"]
        change_service = services["change_service"]
        spec_check_service = services["spec_check_service"]
        spec_center_service = services["spec_center_service"]
        index_service = services["index_service"]
        spec_report_service = services["spec_report_service"]
        frontmatter_service = services["frontmatter_service"]
        doc_refresh_service = services["doc_refresh_service"]
        report_service = services["report_service"]
        pm_session_service = services["pm_session_service"]
        template_service = services["template_service"]

        # 装配 Facades
        self.workbench_facade = WorkbenchFacade(
            dashboard_service=dashboard_service,
            project_service=project_service,
            asset_summary_service=asset_summary_service,
            template_service=template_service,
            change_service=change_service,
            reload_callback=self.reload_callback,
        )

        self.change_facade = ChangeFacade(
            change_service=change_service,
            project_service=project_service,  # M5 CHG-118: 台账对账需要解析 project_id → project_path
            ledger_reconciler=LedgerReconciler(),  # M5 CHG-118: 复用 CHG-108 后端对账器
        )

        self.spec_facade = SpecFacade(
            spec_check_service=spec_check_service,
            spec_center_service=spec_center_service,
            index_service=index_service,  # M5 CHG-119: 复用后端 IndexService
            report_service=spec_report_service,  # M5 CHG-120: 复用后端 Spec 域 ReportService
            frontmatter_service=frontmatter_service,  # M5 CHG-121: 复用后端 FrontmatterService
            project_service=project_service,
        )

        self.delivery_facade = DeliveryFacade(
            doc_refresh_service=doc_refresh_service,
            report_service=report_service,
            asset_summary_service=asset_summary_service,
            project_service=project_service,  # 阶段 C: bug #1/#2/#3 修复需要
        )

        self.system_facade = SystemFacade(
            pm_session_service=pm_session_service,
            template_service=template_service,
            project_service=project_service,  # 阶段 C: bug #6 修复需要
        )
