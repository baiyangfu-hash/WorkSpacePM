"""PLC-HMI 概念映射：HMI 画面数据结构（规范检查 DTO（检查结果/索引/报告/Frontmatter））

像 HMI 触摸屏的画面变量结构，定义 QML 画面能显示的数据格式。

--- 原始注释 ---

Spec 相关 DTO 定义"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SpecCenterDTO:
    overview: dict[str, Any]
    index_items: list[dict[str, Any]]
    check_items: list[dict[str, Any]]
    drift_items: list[dict[str, Any]]


@dataclass(frozen=True)
class SpecCheckResultDTO:
    """规范检查结果（对应 run_spec_check 返回，M4 第 1 批新增）"""

    error_count: int
    warning_count: int
    info_count: int
    exit_code: int
    results: list[dict[str, Any]]  # 检查项明细（保留 dict，因为字段动态）


@dataclass(frozen=True)
class SpecCenterOverviewDTO:
    """规范中心概览（对应 get_spec_center_overview 返回，M4 第 1 批新增）"""

    spec_count: int
    domain_counts: dict[str, int]
    lifecycle_counts: dict[str, int]
    health_summary: dict[str, Any]  # 含 error_count/warning_count/info_count/exit_code


@dataclass(frozen=True)
class SpecCenterEntryDTO:
    """规范中心条目（对应 list_spec_center_entries 返回的每个条目，M4 第 1 批新增）"""

    spec_id: str
    title: str
    number: str
    domain: str
    lifecycle: str
    canonical_path: str
    version: str
    file_exists: bool


@dataclass(frozen=True)
class SpecIndexResultDTO:
    """规范索引生成结果（对应 generate_spec_index 返回，M5 CHG-119 新增）

    封装 IndexService.run() 的 IndexOutput 为 QML 友好的 DTO：
    - generated_files 从 list[Path] 转为 list[str]（QML 不支持 Path 对象）
    - domain 标识生成的域（"all"/"pm"/"plc"/"python"）
    - errors 为生成过程中的错误信息列表（为空表示全部成功）
    """

    domain: str
    generated_files: list[str]
    errors: list[str]


@dataclass(frozen=True)
class SpecReportResultDTO:
    """规范报告生成结果（对应 generate_spec_report 返回，M5 CHG-120 新增）

    封装 ReportService.generate() 的 ReportOutput 为 QML 友好的 DTO：
    - output_path 从 Path 转为 str（QML 不支持 Path 对象）
    - fmt 标识格式（"markdown"/"json"）
    - content 为报告完整内容字符串（QML 可预览）
    - file_size 为 content 字节数，便于 UI 展示文件大小
    """

    fmt: str
    output_path: str
    content: str
    file_size: int


@dataclass(frozen=True)
class SpecFrontmatterResultDTO:
    """规范 Frontmatter 检查/修复结果（对应 check_spec_frontmatter 返回，M5 CHG-121 新增）

    封装 FrontmatterService.preview()/apply() 的结果为 QML 友好的 DTO：
    - items 为检查项明细列表（每个 dict 含 spec_id/file_path/has_frontmatter/is_deprecated/file_exists/status/new_frontmatter）
    - file_path 从 Path 转为 str（QML 不支持 Path 对象）
    - total_count 总规范数
    - pending_count 需要添加 frontmatter 的数量
    - skipped_count 已有 frontmatter 或已弃用的数量
    - error_count 错误数量
    - modified_count 实际修改的数量（auto_fix=True 时才有值）
    - auto_fixed 是否执行了自动修复
    """

    items: list[dict[str, Any]]
    total_count: int
    pending_count: int
    skipped_count: int
    error_count: int
    modified_count: int
    auto_fixed: bool
