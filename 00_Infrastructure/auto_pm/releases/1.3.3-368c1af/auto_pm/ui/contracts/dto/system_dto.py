"""PLC-HMI 概念映射：HMI 画面数据结构（系统设置 DTO（PM_SESSION/模板/设置数据））

像 HMI 触摸屏的画面变量结构，定义 QML 画面能显示的数据格式。

--- 原始注释 ---

System 相关 DTO 定义

M4 第 2 批新增：SystemFacade 6 方法返回带类型 DTO。
list_templates 返回 list[str]、get_template_path 返回 str，无需 DTO。
get_template_detail 从现有 Facade 代码提取 6 个具体字段。
pm_session 2 方法用 dict 字段包装（TODO: Service 结构明确后细化字段）。
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PmSessionViewDTO:
    """PM_SESSION 视图（对应 get_pm_session_view 返回，M4 第 2 批新增）"""
    data: dict[str, Any]  # pm_session_service.generate_view 返回


@dataclass(frozen=True)
class PmSessionCheckResultDTO:
    """PM_SESSION 检查结果（对应 run_pm_session_check 返回，M4 第 2 批新增）"""
    data: dict[str, Any]  # pm_session_service.check 返回


@dataclass(frozen=True)
class TemplateDetailDTO:
    """模板详情（对应 get_template_detail 返回，M4 第 2 批新增）"""
    name: str
    version: str
    description: str
    stack: str
    usage_count: int
    path: str


@dataclass(frozen=True)
class ApplyTemplateResultDTO:
    """模板应用结果（对应 apply_template 返回，M4 第 2 批新增）"""
    project_id: str
    template_name: str
    result: dict[str, Any]  # template_service.apply_template 返回


@dataclass(frozen=True)
class PmSessionArchiveResultDTO:
    """PM_SESSION 归档结果（对应 archive_pm_session 返回，M5 CHG-117 新增）"""
    archive_file: str
    archived_sections: list[str]
    archived_line_count: int
    main_file_lines_before: int
    main_file_lines_after: int
    is_dry_run: bool
    section_title: str
    section_total_lines: int
    keep_recent: int
