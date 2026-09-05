"""PLC-HMI 概念映射：FB_Delivery 功能块

对应 PLC 的 FB，封装"交付管理"域的完整业务逻辑（文档刷新/报告生成/资产汇总）。
- 输入引脚：doc_refresh_service, report_service, asset_summary_service, project_service
- 输出引脚：返回 QueryResult/CommandResult → Bridge Signal 通知画面刷新

--- 原始注释 ---
Delivery Facade 接口层

M4 第 2 批重构：从"转发层"升级为"用例编排层"，7 方法返回带类型 DTO。
后续 DTO 细化：5 个 DTO 从 dict 包装升级为具体字段（ProjectReport/ChangeReport/SpecReport/ScanReport/RefreshProjectDocsResult）。
Service bug 修复（阶段 C）：
- Bug #1: refresh_project_docs 注入 project_service 查 ProjectInfo 后调 Service
- Bug #2/#3: refresh_asset_summary/get_asset_summary 改为接收 project_id，调 build_summary
"""

from auto_pm.core.protocols import (
    AssetSummaryServiceProtocol,
    DocRefreshServiceProtocol,
    ProjectServiceProtocol,
    ReportServiceProtocol,
)
from auto_pm.models import ProjectInfo

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


class DeliveryFacade:
    """提供给 UI 层的 Delivery (文档/报告/发布) 用例聚合入口"""

    def __init__(
        self,
        doc_refresh_service: DocRefreshServiceProtocol | None = None,
        report_service: ReportServiceProtocol | None = None,
        asset_summary_service: AssetSummaryServiceProtocol | None = None,
        project_service: ProjectServiceProtocol | None = None,
    ):
        self._doc_refresh_service = doc_refresh_service
        self._report_service = report_service
        self._asset_summary_service = asset_summary_service
        self._project_service = project_service

    @property
    def has_report_service(self) -> bool:
        return self._report_service is not None

    @property
    def has_asset_summary_service(self) -> bool:
        return self._asset_summary_service is not None

    @property
    def has_doc_refresh_service(self) -> bool:
        return self._doc_refresh_service is not None

    @property
    def has_project_service(self) -> bool:
        return self._project_service is not None

    def _get_project_info(self, project_id: str) -> ProjectInfo | None:
        """通过 project_service 获取项目信息（DB 缓存优先 + 文件系统降级）。"""
        if not self._project_service:
            return None
        return self._project_service.get_project(project_id)

    def refresh_project_docs(
        self, project_id: str, dry_run: bool = False
    ) -> CommandResult[RefreshProjectDocsResultDTO | None]:
        try:
            if not self._doc_refresh_service:
                return CommandResult(success=False, message="No doc_refresh_service", payload=None)
            # Bug #1 修复：查 ProjectInfo 后调 Service（Service 期望 ProjectInfo 非 project_id）
            project_info = self._get_project_info(project_id)
            if project_info is None:
                return CommandResult(
                    success=False,
                    message=f"项目不存在或未注入 project_service: {project_id}",
                    payload=None,
                )
            result = self._doc_refresh_service.refresh_project_documents(
                project_info, dry_run=dry_run
            )
            # DocRefreshResult dataclass 有 to_dict() 方法
            result_dict = (
                result.to_dict()
                if hasattr(result, "to_dict")
                else (result if isinstance(result, dict) else {"raw": result})
            )
            dto = RefreshProjectDocsResultDTO(
                project_id=result_dict.get("project_id", project_id),
                dry_run=result_dict.get("dry_run", dry_run),
                updated=result_dict.get("updated", False),
                refreshed_files=result_dict.get("refreshed_files", []),
                issues=result_dict.get("issues", []),
            )
            return CommandResult(success=True, message="Success", payload=dto)
        except Exception as e:
            return CommandResult(success=False, message=str(e), payload=None)

    def get_project_report(self) -> QueryResult[ProjectReportDTO | None]:
        try:
            if not self._report_service:
                return QueryResult(success=False, message="No report_service", payload=None)
            data = self._report_service.get_project_overview()
            dto = ProjectReportDTO(
                total=data.get("total", 0),
                by_stack=data.get("by_stack", {}),
                by_phase=data.get("by_phase", {}),
                by_business_line=data.get("by_business_line", {}),
            )
            return QueryResult(success=True, message="Success", payload=dto)
        except Exception as e:
            return QueryResult(success=False, message=str(e), payload=None)

    def get_change_report(self) -> QueryResult[ChangeReportDTO | None]:
        try:
            if not self._report_service:
                return QueryResult(success=False, message="No report_service", payload=None)
            data = self._report_service.get_change_overview()
            dto = ChangeReportDTO(
                total=data.get("total", 0),
                by_status=data.get("by_status", {}),
                by_domain=data.get("by_domain", {}),
            )
            return QueryResult(success=True, message="Success", payload=dto)
        except Exception as e:
            return QueryResult(success=False, message=str(e), payload=None)

    def get_spec_report(self) -> QueryResult[SpecReportDTO | None]:
        try:
            if not self._report_service:
                return QueryResult(success=False, message="No report_service", payload=None)
            data = self._report_service.get_spec_report()
            dto = SpecReportDTO(
                total=data.get("total", 0),
                found=data.get("found", 0),
                missing=data.get("missing", 0),
                by_stack=data.get("by_stack", {}),
                missing_codes=data.get("missing_codes", []),
            )
            return QueryResult(success=True, message="Success", payload=dto)
        except Exception as e:
            return QueryResult(success=False, message=str(e), payload=None)

    def get_scan_report(self) -> QueryResult[ScanReportDTO | None]:
        try:
            if not self._report_service:
                return QueryResult(success=False, message="No report_service", payload=None)
            data = self._report_service.get_scan_report()
            dto = ScanReportDTO(
                latest=data.get("latest"),
                last_sync_time=data.get("last_sync_time", "—"),
                is_cache_available=data.get("is_cache_available", False),
            )
            return QueryResult(success=True, message="Success", payload=dto)
        except Exception as e:
            return QueryResult(success=False, message=str(e), payload=None)

    def refresh_asset_summary(
        self, project_id: str = ""
    ) -> CommandResult[RefreshAssetSummaryResultDTO | None]:
        try:
            if not self._asset_summary_service:
                return CommandResult(
                    success=False, message="No asset_summary_service", payload=None
                )
            # Bug #2 修复：调 build_summary(project_path, stack, project_type) 而非 refresh_all()
            if not project_id:
                return CommandResult(
                    success=False,
                    message="缺少 project_id 参数",
                    payload=None,
                )
            project_info = self._get_project_info(project_id)
            if project_info is None:
                return CommandResult(
                    success=False,
                    message=f"项目不存在或未注入 project_service: {project_id}",
                    payload=None,
                )
            result = self._asset_summary_service.build_summary(
                project_path=project_info.path,
                stack=project_info.stack,
                project_type=getattr(project_info, "project_type", "") or "",
            )
            dto = RefreshAssetSummaryResultDTO(
                result=result if isinstance(result, dict) else {"raw": result},
            )
            return CommandResult(success=True, message="Success", payload=dto)
        except Exception as e:
            return CommandResult(success=False, message=str(e), payload=None)

    def get_asset_summary(self, project_id: str = "") -> QueryResult[AssetSummaryDTO | None]:
        try:
            if not self._asset_summary_service:
                return QueryResult(success=False, message="No asset_summary_service", payload=None)
            # Bug #3 修复：调 build_summary(project_path, stack, project_type) 而非 get_summary()
            if not project_id:
                return QueryResult(
                    success=False,
                    message="缺少 project_id 参数",
                    payload=None,
                )
            project_info = self._get_project_info(project_id)
            if project_info is None:
                return QueryResult(
                    success=False,
                    message=f"项目不存在或未注入 project_service: {project_id}",
                    payload=None,
                )
            data = self._asset_summary_service.build_summary(
                project_path=project_info.path,
                stack=project_info.stack,
                project_type=getattr(project_info, "project_type", "") or "",
            )
            dto = AssetSummaryDTO(data=data if isinstance(data, dict) else {"raw": data})
            return QueryResult(success=True, message="Success", payload=dto)
        except Exception as e:
            return QueryResult(success=False, message=str(e), payload=None)
