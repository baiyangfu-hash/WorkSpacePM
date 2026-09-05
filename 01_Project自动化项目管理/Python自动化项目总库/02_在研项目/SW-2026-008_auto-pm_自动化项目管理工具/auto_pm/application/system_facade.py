"""PLC-HMI 概念映射：FB_System 功能块

对应 PLC 的 FB，封装"系统设置"域的完整业务逻辑（PM_SESSION 管理/模板管理/全局设置）。
- 输入引脚：pm_session_service, template_service, project_service
- 输出引脚：返回 QueryResult/CommandResult → Bridge Signal 通知画面刷新

--- 原始注释 ---
System Facade 接口层

M4 第 2 批重构：从"转发层"升级为"用例编排层"，6 方法返回带类型 DTO。
list_templates 返回 list[str]、get_template_path 返回 str，保持基础类型。
Service bug 修复（阶段 C）：
- Bug #6: apply_template 注入 project_service 查 ProjectInfo 后调 copy_template
M5 CHG-117 新增：archive_pm_session 方法供 GUI 调用归档。
"""

import logging
from pathlib import Path

import yaml
from auto_pm.core.protocols import (
    PmSessionServiceProtocol,
    ProjectServiceProtocol,
    TemplateServiceProtocol,
)
from auto_pm.models import ProjectInfo

from auto_pm.ui.contracts.dto.system_dto import (
    ApplyTemplateResultDTO,
    PmSessionArchiveResultDTO,
    PmSessionCheckResultDTO,
    PmSessionViewDTO,
    TemplateDetailDTO,
)
from auto_pm.ui.contracts.result import CommandResult, QueryResult

log = logging.getLogger(__name__)


class SystemFacade:
    """提供给 UI 层的 System (配置/状态/索引) 用例聚合入口"""

    def __init__(
        self,
        pm_session_service: PmSessionServiceProtocol | None = None,
        template_service: TemplateServiceProtocol | None = None,
        project_service: ProjectServiceProtocol | None = None,
    ):
        self._pm_session_service = pm_session_service
        self._template_service = template_service
        self._project_service = project_service

    @property
    def has_template_service(self) -> bool:
        return self._template_service is not None

    @property
    def has_pm_session_service(self) -> bool:
        return self._pm_session_service is not None

    @property
    def has_project_service(self) -> bool:
        return self._project_service is not None

    def _get_project_info(self, project_id: str) -> ProjectInfo | None:
        """通过 project_service 获取项目信息（DB 缓存优先 + 文件系统降级）。"""
        if not self._project_service:
            return None
        return self._project_service.get_project(project_id)

    def get_pm_session_view(self) -> QueryResult[PmSessionViewDTO | None]:
        try:
            if not self._pm_session_service:
                return QueryResult(success=False, message="No pm_session_service", payload=None)
            view = self._pm_session_service.generate_view()
            data = view if isinstance(view, dict) else {"raw": view}
            dto = PmSessionViewDTO(data=data)
            return QueryResult(success=True, message="Success", payload=dto)
        except Exception as e:
            return QueryResult(success=False, message=str(e), payload=None)

    def run_pm_session_check(self) -> CommandResult[PmSessionCheckResultDTO | None]:
        try:
            if not self._pm_session_service:
                return CommandResult(success=False, message="No pm_session_service", payload=None)
            result = self._pm_session_service.check()
            data = result if isinstance(result, dict) else {"raw": result}
            dto = PmSessionCheckResultDTO(data=data)
            return CommandResult(success=True, message="Success", payload=dto)
        except Exception as e:
            return CommandResult(success=False, message=str(e), payload=None)

    def list_templates(self) -> QueryResult[list[str]]:
        try:
            if not self._template_service:
                return QueryResult(success=False, message="No template_service", payload=[])
            templates = self._template_service.list_templates()
            return QueryResult(success=True, message="Success", payload=templates)
        except Exception as e:
            return QueryResult(success=False, message=str(e), payload=[])

    def get_template_path(self, template_name: str) -> QueryResult[str]:
        try:
            if not self._template_service:
                return QueryResult(success=False, message="No template_service", payload="")
            path = self._template_service.get_template_path(template_name)
            return QueryResult(success=True, message="Success", payload=path)
        except Exception as e:
            return QueryResult(success=False, message=str(e), payload="")

    def get_template_detail(self, template_name: str) -> QueryResult[TemplateDetailDTO | None]:
        try:
            if not self._template_service:
                return QueryResult(success=False, message="No template_service", payload=None)

            path = self._template_service.get_template_path(template_name)
            if not path:
                return QueryResult(
                    success=False, message=f"模板路径不存在: {template_name}", payload=None
                )

            # Read version and description
            copier_yml = Path(path) / "copier.yml"
            version = "unknown"
            description = "暂无描述"
            if copier_yml.exists():
                try:
                    with open(copier_yml, encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                        if data and isinstance(data, dict):
                            version = str(
                                data.get("_commit", data.get("_min_copier_version", "unknown"))
                            )
                            description = str(data.get("_description", description))
                except Exception as e:
                    log.warning("读取 copier.yml 失败: %s", e, exc_info=True)

            # Infer stack
            stack = "pm"
            if "python" in template_name.lower():
                stack = "python"
            elif "plc" in template_name.lower() or "portal" in template_name.lower():
                stack = "plc"

            # Count usage
            usage_count = 0
            if self._project_service:
                projects = self._project_service.list_projects()
                for p in projects:
                    try:
                        stack_val = str(p.stack).lower()
                        if stack_val == stack:
                            usage_count += 1
                    except Exception as e:
                        log.warning("模板使用计数 stack 比较失败: %s", e, exc_info=True)

            dto = TemplateDetailDTO(
                name=template_name,
                version=version,
                description=description,
                stack=stack,
                usage_count=usage_count,
                path=str(path),
            )
            return QueryResult(success=True, message="Success", payload=dto)
        except Exception as e:
            return QueryResult(success=False, message=str(e), payload=None)

    def apply_template(
        self, project_id: str, template_name: str
    ) -> CommandResult[ApplyTemplateResultDTO | None]:
        try:
            if not self._template_service:
                return CommandResult(success=False, message="No template_service", payload=None)
            # Bug #6 修复：查 ProjectInfo 后调 copy_template(dest_path, data)
            project_info = self._get_project_info(project_id)
            if project_info is None:
                return CommandResult(
                    success=False,
                    message=f"项目不存在或未注入 project_service: {project_id}",
                    payload=None,
                )
            # 构造模板变量 data（从 ProjectInfo 提取关键字段）
            data = {
                "project_id": project_id,
                "project_name": getattr(project_info, "name", "") or "",
                "stack": getattr(project_info, "stack", "") or "",
            }
            # 调 copy_template(template_name, dest_path, data, overwrite=True)
            # 注：apply_template 语义为"应用模板到已有项目"，使用 overwrite=True 覆盖冲突文件
            result = self._template_service.copy_template(
                template_name=template_name,
                dest_path=str(project_info.path),
                data=data,
                overwrite=True,
            )
            dto = ApplyTemplateResultDTO(
                project_id=project_id,
                template_name=template_name,
                result=result if isinstance(result, dict) else {"raw": result},
            )
            return CommandResult(success=True, message="Success", payload=dto)
        except Exception as e:
            return CommandResult(success=False, message=str(e), payload=None)

    def archive_pm_session(
        self,
        section: str,
        keep_recent: int = 0,
        dry_run: bool = False,
    ) -> CommandResult[PmSessionArchiveResultDTO | None]:
        """归档 PM_SESSION 指定章节的早期内容（M5 CHG-117 新增）

        Args:
            section: 章节号（如 "6"/"8"）
            keep_recent: 保留最近 N 行（§8 表示保留最新 N 条 skill_handoff）
            dry_run: 仅预览，不实际修改文件
        """
        try:
            if not self._pm_session_service:
                return CommandResult(success=False, message="No pm_session_service", payload=None)
            result = self._pm_session_service.archive(section, keep_recent, dry_run)
            if "error" in result:
                return CommandResult(success=False, message=result["error"], payload=None)
            dto = PmSessionArchiveResultDTO(
                archive_file=result.get("archive_file", ""),
                archived_sections=result.get("archived_sections", []),
                archived_line_count=result.get("archived_line_count", 0),
                main_file_lines_before=result.get("main_file_lines_before", 0),
                main_file_lines_after=result.get("main_file_lines_after", 0),
                is_dry_run=result.get("is_dry_run", False),
                section_title=result.get("section_title", ""),
                section_total_lines=result.get("section_total_lines", 0),
                keep_recent=result.get("keep_recent", 0),
            )
            return CommandResult(success=True, message="Success", payload=dto)
        except Exception as e:
            return CommandResult(success=False, message=str(e), payload=None)
