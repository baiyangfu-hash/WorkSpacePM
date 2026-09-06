"""PLC-HMI 概念映射：HMI 画面数据结构（规范中心页面 DTO（跨页面规范数据））

像 HMI 触摸屏的画面变量结构，定义 QML 画面能显示的数据格式。

--- 原始注释 ---

规范中心 DTO 层

将 Spec 子系统的 4 个 Service（IndexService / CheckService / FrontmatterService /
ReportService）输出整形为 QWidget 可直接渲染的不可变 DTO。

设计原则：
- Service 输出 → DTO 转换（本文件）→ QWidget 渲染
- 禁止 QWidget 直接调用 Service，必须经过 DTO 层
- 所有 DTO 为 frozen dataclass，确保不可变
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from auto_pm.spec.core.checker_base import CheckResult, Severity
from auto_pm.spec.core.registry import SpecInfo
from auto_pm.spec.services.fix_svc import FixResult
from auto_pm.spec.services.frontmatter_svc import FrontmatterItem

if TYPE_CHECKING:
    from auto_pm.spec.core.config import WorkspaceConfig
    from auto_pm.spec.core.registry import SpecRegistry


# ── Tab1 概览 DTO ────────────────────────────────────────


@dataclass(frozen=True)
class HealthSummaryDTO:
    """健康检查摘要 DTO"""

    error_count: int
    warning_count: int
    info_count: int
    exit_code: int


@dataclass(frozen=True)
class SpecOverviewDTO:
    """规范概览 DTO（Tab1 Overview）

    由 IndexService 的 registry.raw + CheckService 输出聚合而来。
    """

    spec_count: int
    domain_counts: dict[str, int]
    lifecycle_counts: dict[str, int]
    health_summary: HealthSummaryDTO


# ── Tab2 索引 DTO ────────────────────────────────────────


@dataclass(frozen=True)
class SpecEntryDTO:
    """规范索引条目 DTO（Tab2 Index）

    由 SpecRegistry.list_specs() → SpecInfo 转换而来。
    """

    spec_id: str
    title: str
    number: str
    domain: str
    lifecycle: str
    canonical_path: str
    version: str
    file_exists: bool


# ── Tab3 健康检查 DTO ────────────────────────────────────


@dataclass(frozen=True)
class HealthCheckResultDTO:
    """健康检查结果条目 DTO（Tab3 Check）

    由 CheckService.run() → CheckResult 转换而来。
    """

    check_id: str
    severity: Severity
    message: str
    details: str
    fix_suggestion: str
    auto_fixable: bool


@dataclass(frozen=True)
class HealthCheckOutputDTO:
    """健康检查输出聚合 DTO（Tab3 Check）"""

    results: list[HealthCheckResultDTO]
    error_count: int
    warning_count: int
    info_count: int
    exit_code: int
    fix_results: list[FixResult] = field(default_factory=list)


# ── Tab4 Frontmatter DTO ────────────────────────────────


@dataclass(frozen=True)
class FrontmatterPreviewDTO:
    """Frontmatter 预览条目 DTO（Tab4 Frontmatter）

    由 FrontmatterService.preview() → FrontmatterItem 转换而来。
    """

    spec_id: str
    file_path: Path
    has_frontmatter: bool
    is_deprecated: bool
    file_exists: bool
    new_frontmatter: str
    status: str


# ── Tab5 报告 DTO ────────────────────────────────────────


@dataclass(frozen=True)
class ReportOutputDTO:
    """报告输出 DTO（Tab5 Report）

    由 ReportService.generate() → ReportOutput 转换而来。
    """

    fmt: str
    content: str
    saved_path: Path


# ── Tab6 对比 DTO ────────────────────────────────────────


@dataclass(frozen=True)
class CompareResultDTO:
    """规范对比结果 DTO（Tab6 Compare）

    由 SpecCenterAdapter.compare_specs() 基于注册表 + 文件读取生成。
    """

    left_spec_id: str
    right_spec_id: str
    left_path: str
    right_path: str
    left_lines: list[str] = field(default_factory=list)
    right_lines: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    same: bool = False


# ── 转换函数 ─────────────────────────────────────────────


def to_spec_entry_dto(spec_info: SpecInfo, workspace: Path) -> SpecEntryDTO:
    """SpecInfo → SpecEntryDTO

    Args:
        spec_info: 注册表中的规范元数据
        workspace: 工作空间根目录，用于校验文件存在性

    Returns:
        SpecEntryDTO 不可变条目
    """
    canonical = spec_info.canonical_path or ""
    file_exists = bool(canonical) and (workspace / canonical).exists()
    return SpecEntryDTO(
        spec_id=spec_info.spec_id,
        title=spec_info.title,
        number=spec_info.number,
        domain=spec_info.domain,
        lifecycle=spec_info.lifecycle,
        canonical_path=canonical,
        version=spec_info.version,
        file_exists=file_exists,
    )


def to_health_check_result_dto(
    result: CheckResult,
    auto_fixable: bool,
) -> HealthCheckResultDTO:
    """CheckResult → HealthCheckResultDTO"""
    return HealthCheckResultDTO(
        check_id=result.check_id,
        severity=result.severity,
        message=result.message,
        details=result.details,
        fix_suggestion=result.fix_suggestion,
        auto_fixable=auto_fixable,
    )


def to_frontmatter_preview_dto(item: FrontmatterItem) -> FrontmatterPreviewDTO:
    """FrontmatterItem → FrontmatterPreviewDTO"""
    return FrontmatterPreviewDTO(
        spec_id=item.spec_id,
        file_path=item.file_path,
        has_frontmatter=item.has_frontmatter,
        is_deprecated=item.is_deprecated,
        file_exists=item.file_exists,
        new_frontmatter=item.new_frontmatter,
        status=item.status,
    )


def build_overview_dto(
    specs: list[SpecInfo],
    health: HealthCheckOutputDTO | None,
) -> SpecOverviewDTO:
    """聚合规范列表与健康检查输出 → SpecOverviewDTO

    Args:
        specs: SpecRegistry.list_specs() 返回的规范列表
        health: CheckService 输出转换的 HealthCheckOutputDTO（可为空）

    Returns:
        SpecOverviewDTO
    """
    domain_counts: dict[str, int] = {}
    lifecycle_counts: dict[str, int] = {}
    for s in specs:
        d = s.domain or "unknown"
        domain_counts[d] = domain_counts.get(d, 0) + 1
        lc = s.lifecycle or "unknown"
        lifecycle_counts[lc] = lifecycle_counts.get(lc, 0) + 1

    if health is not None:
        hs = HealthSummaryDTO(
            error_count=health.error_count,
            warning_count=health.warning_count,
            info_count=health.info_count,
            exit_code=health.exit_code,
        )
    else:
        hs = HealthSummaryDTO(
            error_count=0, warning_count=0, info_count=0, exit_code=0
        )

    return SpecOverviewDTO(
        spec_count=len(specs),
        domain_counts=domain_counts,
        lifecycle_counts=lifecycle_counts,
        health_summary=hs,
    )


def build_health_output_dto(
    results: list[CheckResult],
    error_count: int,
    warning_count: int,
    info_count: int,
    exit_code: int,
    fix_results: list[FixResult] | None = None,
) -> HealthCheckOutputDTO:
    """聚合 CheckService 输出 → HealthCheckOutputDTO

    Args:
        results: CheckService.run() 返回的 CheckResult 列表
        error_count/warning_count/info_count/exit_code: CheckOutput 字段
        fix_results: 自动修复结果（None 表示未执行修复）

    Returns:
        HealthCheckOutputDTO
    """
    # 延迟导入避免循环依赖
    from auto_pm.spec.services.fix_svc import can_auto_fix

    dto_results = [to_health_check_result_dto(r, can_auto_fix(r)) for r in results]
    return HealthCheckOutputDTO(
        results=dto_results,
        error_count=error_count,
        warning_count=warning_count,
        info_count=info_count,
        exit_code=exit_code,
        fix_results=fix_results or [],
    )


def build_report_output_dto(
    fmt: str,
    content: str,
    saved_path: Path,
) -> ReportOutputDTO:
    """ReportService.ReportOutput → ReportOutputDTO"""
    return ReportOutputDTO(
        fmt=fmt,
        content=content,
        saved_path=saved_path,
    )


def build_compare_dto(
    left_spec_id: str,
    right_spec_id: str,
    left_path: str,
    right_path: str,
    left_content: str,
    right_content: str,
) -> CompareResultDTO:
    """基于两份规范文本内容构建 CompareResultDTO

    使用行级对比（与旧 SpecIndexService.compare 行为一致）。
    """
    left_lines = left_content.splitlines()
    right_lines = right_content.splitlines()
    set_l = set(left_lines)
    set_r = set(right_lines)
    added = [line for line in right_lines if line not in set_l]
    removed = [line for line in left_lines if line not in set_r]
    return CompareResultDTO(
        left_spec_id=left_spec_id,
        right_spec_id=right_spec_id,
        left_path=left_path,
        right_path=right_path,
        left_lines=left_lines,
        right_lines=right_lines,
        added=added,
        removed=removed,
        same=left_content == right_content,
    )


__all__ = [
    "HealthSummaryDTO",
    "SpecOverviewDTO",
    "SpecEntryDTO",
    "HealthCheckResultDTO",
    "HealthCheckOutputDTO",
    "FrontmatterPreviewDTO",
    "ReportOutputDTO",
    "CompareResultDTO",
    "SpecCenterAdapter",
    "to_spec_entry_dto",
    "to_health_check_result_dto",
    "to_frontmatter_preview_dto",
    "build_overview_dto",
    "build_health_output_dto",
    "build_report_output_dto",
    "build_compare_dto",
]


class SpecCenterAdapter:
    """规范中心适配器

    聚合 4 个 Spec 子系统 Service（IndexService / CheckService /
    FrontmatterService / ReportService），向 QWidget 层暴露返回 DTO 的方法。

    QWidget 禁止直接调用 Service，必须通过本 Adapter 获取 DTO。

    用法：
        adapter = SpecCenterAdapter(workspace=Path(...))
        overview = adapter.get_overview()
        entries = adapter.list_entries(domain="plc")
        health = adapter.run_checks()
    """

    def __init__(
        self,
        workspace: Path,
        config: WorkspaceConfig | None = None,
    ) -> None:
        from auto_pm.spec.core.config import WorkspaceConfig
        from auto_pm.spec.services.check_svc import CheckService
        from auto_pm.spec.services.frontmatter_svc import FrontmatterService
        from auto_pm.spec.services.index_svc import IndexService
        from auto_pm.spec.services.report_svc import ReportService

        self.workspace = workspace
        self.config = config or WorkspaceConfig(workspace=workspace)
        self.index_service = IndexService(workspace, config=self.config)
        self.check_service = CheckService(workspace, config=self.config)
        self.frontmatter_service = FrontmatterService(workspace, config=self.config)
        self.report_service = ReportService(workspace, config=self.config)

    @property
    def registry(self) -> SpecRegistry:
        """暴露 SpecRegistry（供需要原始数据的场景使用）"""
        return self.index_service.registry

    # ── Tab1 概览 ────────────────────────────────────────

    def get_overview(self) -> SpecOverviewDTO:
        """获取规范概览 DTO（统计 + 健康摘要）

        健康摘要为空（不触发完整检查），仅用于概览页快速展示。
        详细检查结果在 Tab3 中按需触发。
        """
        specs = self.registry.list_specs()
        return build_overview_dto(specs, health=None)

    # ── Tab2 索引 ────────────────────────────────────────

    def list_entries(self, domain: str | None = None) -> list[SpecEntryDTO]:
        """列出规范索引条目

        Args:
            domain: 按域过滤（pm/plc/python/cross-domain），None 返回全部

        Returns:
            SpecEntryDTO 列表（按 spec_id 排序）
        """
        specs = self.registry.list_specs(domain=domain) if domain else self.registry.list_specs()
        return [to_spec_entry_dto(s, self.workspace) for s in specs]

    def read_spec_content(self, spec_id: str) -> str:
        """读取规范文件内容

        Raises:
            FileNotFoundError: 规范不在注册表或文件不存在
        """
        info = self.registry.get_spec(spec_id)
        if info is None:
            raise FileNotFoundError(f"未找到规范: {spec_id}")
        if not info.canonical_path:
            raise FileNotFoundError(f"规范 {spec_id} 缺少 canonical_path")
        path = self.workspace / info.canonical_path
        if not path.exists():
            raise FileNotFoundError(f"规范文件不存在: {path}")
        return str(path.read_text(encoding="utf-8"))

    # ── Tab3 健康检查 ────────────────────────────────────

    def run_checks(
        self,
        check_ids: list[str] | None = None,
        auto_fix: bool = False,
        dry_run: bool = False,
    ) -> HealthCheckOutputDTO:
        """运行健康检查，返回 DTO"""
        from auto_pm.spec.core.checker_base import Severity

        out = self.check_service.run(
            check_ids=check_ids,
            min_severity=Severity.INFO,
            auto_fix=auto_fix,
            dry_run=dry_run,
        )
        return build_health_output_dto(
            results=out.results,
            error_count=out.error_count,
            warning_count=out.warning_count,
            info_count=out.info_count,
            exit_code=out.exit_code,
            fix_results=out.fix_results,
        )

    # ── Tab4 Frontmatter ────────────────────────────────

    def preview_frontmatter(self, spec_id: str | None = None) -> list[FrontmatterPreviewDTO]:
        """预览 Frontmatter"""
        items = self.frontmatter_service.preview(spec_id=spec_id)
        return [to_frontmatter_preview_dto(i) for i in items]

    def apply_frontmatter(
        self, items: list[FrontmatterPreviewDTO]
    ) -> tuple[int, int, int]:
        """应用 Frontmatter（实际写入）

        Args:
            items: 预览得到的 DTO 列表

        Returns:
            (modified_count, skipped_count, error_count)
        """
        from auto_pm.spec.services.frontmatter_svc import FrontmatterItem

        # DTO → FrontmatterItem（apply 需要 FrontmatterItem）
        raw_items: list[FrontmatterItem] = []
        for dto in items:
            if dto.status != "pending":
                continue
            raw_items.append(FrontmatterItem(
                spec_id=dto.spec_id,
                file_path=dto.file_path,
                has_frontmatter=dto.has_frontmatter,
                is_deprecated=dto.is_deprecated,
                file_exists=dto.file_exists,
                new_frontmatter=dto.new_frontmatter,
                status=dto.status,
            ))
        if not raw_items:
            return (0, 0, 0)
        result = self.frontmatter_service.apply(raw_items)
        return (result.modified_count, result.skipped_count, result.error_count)

    # ── Tab5 报告 ────────────────────────────────────────

    def generate_report(
        self,
        fmt: str = "markdown",
        output_path: Path | None = None,
    ) -> ReportOutputDTO:
        """生成规范元数据汇总报告"""
        out = self.report_service.generate(fmt=fmt, output_path=output_path)
        return build_report_output_dto(
            fmt=out.fmt,
            content=out.content,
            saved_path=out.output_path,
        )

    # ── Tab6 对比 ────────────────────────────────────────

    def compare_specs(self, left_spec_id: str, right_spec_id: str) -> CompareResultDTO:
        """对比两个规范文件内容

        Raises:
            FileNotFoundError: 规范不存在或文件缺失
        """
        left_info = self.registry.get_spec(left_spec_id)
        right_info = self.registry.get_spec(right_spec_id)
        if left_info is None:
            raise FileNotFoundError(f"未找到规范: {left_spec_id}")
        if right_info is None:
            raise FileNotFoundError(f"未找到规范: {right_spec_id}")
        if not left_info.canonical_path:
            raise FileNotFoundError(f"规范 {left_spec_id} 缺少 canonical_path")
        if not right_info.canonical_path:
            raise FileNotFoundError(f"规范 {right_spec_id} 缺少 canonical_path")

        left_path = self.workspace / left_info.canonical_path
        right_path = self.workspace / right_info.canonical_path
        if not left_path.exists():
            raise FileNotFoundError(f"规范文件不存在: {left_path}")
        if not right_path.exists():
            raise FileNotFoundError(f"规范文件不存在: {right_path}")

        left_content = left_path.read_text(encoding="utf-8")
        right_content = right_path.read_text(encoding="utf-8")
        return build_compare_dto(
            left_spec_id=left_spec_id,
            right_spec_id=right_spec_id,
            left_path=str(left_path),
            right_path=str(right_path),
            left_content=left_content,
            right_content=right_content,
        )

    # ── 工作空间切换 ────────────────────────────────────

    def set_workspace(self, workspace: Path) -> None:
        """切换工作空间（重建所有 Service）"""
        self.workspace = workspace
        from auto_pm.spec.core.config import WorkspaceConfig
        from auto_pm.spec.services.check_svc import CheckService
        from auto_pm.spec.services.frontmatter_svc import FrontmatterService
        from auto_pm.spec.services.index_svc import IndexService
        from auto_pm.spec.services.report_svc import ReportService

        self.config = WorkspaceConfig(workspace=workspace)
        self.index_service = IndexService(workspace, config=self.config)
        self.check_service = CheckService(workspace, config=self.config)
        self.frontmatter_service = FrontmatterService(workspace, config=self.config)
        self.report_service = ReportService(workspace, config=self.config)
