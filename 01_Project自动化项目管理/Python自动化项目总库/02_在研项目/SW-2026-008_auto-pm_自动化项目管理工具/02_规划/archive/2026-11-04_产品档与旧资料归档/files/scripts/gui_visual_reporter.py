"""GUI 视觉测试报告生成器 V1

桥梁角色：自动测试输出 → 多模态 AI 可消费的结构化 JSON → 修复建议模板。

功能：
1. 从 gui_plc_full_test.py 的 bugs/visual_issues/op_log 生成结构化报告
2. 控件路径 → 源代码位置映射（启发式推断）
3. 按问题类型自动生成 fix_hint
4. 输出 ai_analysis_input.json（可直接喂给多模态 LLM）
5. 输出 ai_fix_suggestions_template.json（AI 应返回的修复指令格式）

用法：
    from scripts.gui_visual_reporter import VisualReporter

    reporter = VisualReporter(project_root=PROJECT_ROOT, screenshot_dir=SCREENSHOT_DIR)
    reporter.add_bugs(bugs)
    reporter.add_visual_issues(visual_issues)
    reporter.add_op_log(op_log)
    reporter.add_screenshots(screenshot_dir)
    reporter.generate(REPORT_DIR)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# ── 控件类名 → 源代码文件映射（启发式） ──────────────────

_WIDGET_SOURCE_MAP: dict[str, str] = {
    "MainWindow": "auto_pm/ui/main_window.py",
    "ProjectWorkspaceView": "auto_pm/ui/workspace/workspace_view.py",
    "OverviewTab": "auto_pm/ui/workspace/overview_tab.py",
    "ChangeTab": "auto_pm/ui/workspace/change_tab.py",
    "CheckTab": "auto_pm/ui/workspace/check_tab.py",
    "DocTab": "auto_pm/ui/workspace/doc_tab.py",
    "VartableTab": "auto_pm/ui/vartable/vartable_tab.py",
    "VariableTableEditor": "auto_pm/ui/vartable/variable_table_editor.py",
    "ProjectListView": "auto_pm/ui/project_list/list_view.py",
    "ChangeCenterView": "auto_pm/ui/change_center/center_view.py",
    "ChangeListPanel": "auto_pm/ui/change_center/change_list_panel.py",
    "SpecCenterView": "auto_pm/ui/global_pages/spec_center.py",
    "ReportPage": "auto_pm/ui/global_pages/report_page.py",
    "SettingsPage": "auto_pm/ui/global_pages/settings_page.py",
    "TemplatePage": "auto_pm/ui/global_pages/template_page.py",
    "NavigationTree": "auto_pm/ui/navigation/nav_tree.py",
    "NewProjectDialog": "auto_pm/ui/dialogs/new_project_dialog.py",
    "EditProjectDialog": "auto_pm/ui/dialogs/edit_project_dialog.py",
    "CreateChangeDialog": "auto_pm/ui/dialogs/create_change_dialog.py",
    "TransitionDialog": "auto_pm/ui/dialogs/transition_dialog.py",
    "StatusMachineView": "auto_pm/ui/dialogs/status_machine_view.py",
    "PropagationView": "auto_pm/ui/change_center/propagation_view.py",
    "ApprovalTimeline": "auto_pm/ui/change_center/approval_timeline.py",
    "ProjectCard": "auto_pm/ui/project_list/project_card.py",
    "ViewControls": "auto_pm/ui/project_list/view_controls.py",
    "StatsBar": "auto_pm/ui/widgets/stats_bar.py",
    "FilterBar": "auto_pm/ui/widgets/filter_bar.py",
}

# ── 问题类型 → fix_hint 模板 ───────────────────────────────

_FIX_HINT_TEMPLATES: dict[str, str] = {
    "out_of_bounds": (
        "控件几何超出父控件边界。修复方向："
        "① 为父控件设置 QScrollArea + setWidgetResizable(True)；"
        "② 在父控件的 layout 中正确设置 sizePolicy(Expanding)；"
        "③ 检查是否有固定最小尺寸导致内容撑破。"
    ),
    "zero_size": (
        "可见控件尺寸为零（宽或高为0）。修复方向："
        "① 为控件设置 setMinimumWidth() / setMinimumHeight()；"
        "② 检查 QSplitter 的 setStretchFactor 是否正确分配空间；"
        "③ 在 showEvent 中调用 adjustSize() 或 refresh() 延迟布局。"
    ),
    "text_truncated": (
        "文本被截断（所需宽度大于实际宽度）。修复方向："
        "① 为 QLabel 设置 setWordWrap(True)；"
        "② 增加控件最小宽度；"
        "③ 使用 elide 模式或 tooltip 显示完整文本。"
    ),
    "low_contrast": (
        "前景色与背景色对比度不足（< 4.5:1）。修复方向："
        "① 调整 foreground/background 样式使对比度 ≥ 4.5；"
        "② 参见 auto_pm/ui/styles.py 检查 BASE_WIDGET_STYLE。"
    ),
    "z_overlap": (
        "可见控件被其他控件遮挡。修复方向："
        "① 调整 layout 中 widget 顺序或 z-order；"
        "② 检查是否有绝对定位的 widget 覆盖在 layout widget 之上。"
    ),
    "scrollbar_missing": (
        "内容溢出但父控件缺少滚动条。修复方向："
        "① 将内容包裹在 QScrollArea 中并 setWidgetResizable(True)；"
        "② 检查父控件的 sizePolicy 是否为 Expanding。"
    ),
    "empty_space": (
        "大面积空白区域（可能布局失败）。修复方向："
        "① 检查 layout 中是否有 stretch 项未正确分配；"
        "② 检查 hide/show 切换后是否调用了 adjustSize()。"
    ),
    "default": (
        "通用视觉问题。修复方向："
        "① 检查对应控件的 stylesheet 和布局设置；"
        "② 参见代码位置注释。"
    ),
}


# ── AI 应返回的修复指令 JSON Schema ───────────────────────

_AI_FIX_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "AIFixSuggestion",
    "description": (
        "多模态 AI 对 GUI 截图和程序化检查的分析结果。"
        "每条 fix 应精确到源代码文件和行号范围。"
    ),
    "type": "object",
    "required": ["analysis_summary", "fixes", "confidence_scores"],
    "properties": {
        "analysis_summary": {
            "type": "string",
            "description": "对本次测试截图的整体分析摘要（2-5句中文）。"
        },
        "fixes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["file", "line_range", "current_behavior", "suggested_change", "priority"],
                "properties": {
                    "file": {
                        "type": "string",
                        "description": "需要修改的源代码文件路径（如 auto_pm/ui/main_window.py）。"
                    },
                    "line_range": {
                        "type": "string",
                        "description": "行号范围（如 L236-L240）。"
                    },
                    "current_behavior": {
                        "type": "string",
                        "description": "当前代码的行为描述（从截图分析得出）。"
                    },
                    "suggested_change": {
                        "type": "string",
                        "description": "具体的代码修改建议。"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["P0", "P1", "P2"],
                        "description": "修复优先级。"
                    },
                    "screenshot_reference": {
                        "type": "string",
                        "description": "关联的截图文件名。"
                    },
                },
            },
        },
        "confidence_scores": {
            "type": "object",
            "description": "各 fix 的置信度（0-1），低于0.6的建议可能不准确。",
        },
    },
}


# ── 数据结构 ───────────────────────────────────────────────

@dataclass
class StructuredIssue:
    """结构化的视觉问题记录"""
    issue_type: str
    severity: str
    widget_path: str
    detail: str
    viewport: str
    screenshot: str = ""
    timestamp: str = ""

    # 流水线增强字段
    source_file: str = ""          # 推断的源代码文件
    fix_hint: str = ""             # 修复提示
    widget_class: str = ""         # 最具体的控件类名


@dataclass
class AIAnalysisInput:
    """多模态 AI 分析输入"""
    test_session: str
    screenshot_dir: str
    screenshot_count: int
    total_bugs: int
    total_visual_issues: int
    bugs: list[dict[str, Any]] = field(default_factory=list)
    visual_issues: list[dict[str, Any]] = field(default_factory=list)
    widget_snapshot: list[dict[str, Any]] = field(default_factory=list)
    source_file_hints: dict[str, str] = field(default_factory=dict)  # widget_path → source_file
    op_log: list[str] = field(default_factory=list)


# ── 核心类 ────────────────────────────────────────────────

class VisualReporter:
    """GUI 视觉测试报告生成器

    桥接自动测试输出与多模态 AI 消费。
    """

    def __init__(
        self,
        project_root: Path,
        screenshot_dir: Path | None = None,
    ) -> None:
        self.project_root = project_root
        self.screenshot_dir = screenshot_dir
        self._bugs: list[dict[str, Any]] = []
        self._visual_issues: list[dict[str, Any]] = []
        self._op_log: list[str] = []
        self._screenshots: list[str] = []
        self._widget_snapshot: list[dict[str, Any]] = []
        self._timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── 数据注入 ──────────────────────────────────────────

    def add_bugs(self, bugs: list[dict[str, Any]]) -> None:
        self._bugs = bugs

    def add_visual_issues(self, visual_issues: list[dict[str, Any]]) -> None:
        self._visual_issues = visual_issues

    def add_op_log(self, op_log: list[str]) -> None:
        self._op_log = op_log

    def add_screenshots(self, screenshot_dir: Path) -> None:
        """扫描截图目录，记录所有截图文件"""
        self.screenshot_dir = screenshot_dir
        if screenshot_dir and screenshot_dir.is_dir():
            self._screenshots = sorted(
                str(p.relative_to(self.project_root))
                for p in screenshot_dir.glob("*.png")
            )

    def add_widget_snapshot(self, widget_snapshot: list[dict[str, Any]]) -> None:
        """注入来自 gui_plc_full_test.py 的 widget_snapshot"""
        self._widget_snapshot = widget_snapshot

    # ── 控件路径 → 源代码映射 ──────────────────────────────

    @staticmethod
    def _infer_source_file(widget_path: str) -> str:
        """从控件路径推断源代码文件

        策略：从路径中提取最具体的已知控件类名，查映射表。
        映射表覆盖 auto-pm 所有主要 UI 组件。
        """
        # 从 widget_path (如 "MainWindow > QSplitter > ProjectWorkspaceView > QTabWidget")
        # 提取每个类名，从右向左匹配已知类名
        parts = [p.strip() for p in widget_path.split(">")]
        for part in reversed(parts):
            if part in _WIDGET_SOURCE_MAP:
                return _WIDGET_SOURCE_MAP[part]
            # 尝试匹配部分名称（如 QTabWidget → 无匹配，跳过）
        return "auto_pm/ui/（无法推断具体文件）"

    @staticmethod
    def _infer_widget_class(widget_path: str) -> str:
        """从控件路径提取最具体的已知控件类名"""
        parts = [p.strip() for p in widget_path.split(">")]
        for part in reversed(parts):
            if part in _WIDGET_SOURCE_MAP:
                return part
        return parts[-1] if parts else "Unknown"

    # ── fix_hint 生成 ──────────────────────────────────────

    @staticmethod
    def _generate_fix_hint(issue_type: str, widget_path: str, detail: str) -> str:
        """生成修复提示，结合问题类型和控件信息"""
        base_hint = _FIX_HINT_TEMPLATES.get(issue_type, _FIX_HINT_TEMPLATES["default"])
        source_file = VisualReporter._infer_source_file(widget_path)
        return f"[{source_file}] {base_hint} 具体情况: {detail}"

    # ── 报告生成 ───────────────────────────────────────────

    def generate(self, report_dir: Path) -> dict[str, Path]:
        """生成所有报告文件，返回路径映射

        Returns:
            {
                "ai_input": Path to ai_analysis_input.json,
                "fix_template": Path to ai_fix_suggestions_template.json,
            }
        """
        report_dir.mkdir(parents=True, exist_ok=True)

        # 1. 结构化视觉问题
        structured = self._build_structured_issues()

        # 2. AI 分析输入 JSON
        ai_input_path = report_dir / f"ai_analysis_input_{self._timestamp}.json"
        ai_input = self._build_ai_input(structured)
        ai_input_path.write_text(
            json.dumps(ai_input, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 3. AI 修复建议模板 JSON
        fix_template_path = report_dir / "ai_fix_suggestions_template.json"
        fix_template_path.write_text(
            json.dumps(_AI_FIX_SCHEMA, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return {
            "ai_input": ai_input_path,
            "fix_template": fix_template_path,
        }

    def _build_structured_issues(self) -> list[StructuredIssue]:
        """将原始 visual_issues 转换为结构化记录"""
        structured: list[StructuredIssue] = []
        for vi in self._visual_issues:
            widget_path = vi.get("widget", vi.get("widget_path", ""))
            issue_type = vi.get("type", "unknown")
            detail = vi.get("detail", "")
            structured.append(
                StructuredIssue(
                    issue_type=issue_type,
                    severity=vi.get("severity", "minor"),
                    widget_path=widget_path,
                    detail=detail,
                    viewport=vi.get("viewport", "desktop"),
                    screenshot=vi.get("screenshot", ""),
                    timestamp=vi.get("timestamp", ""),
                    source_file=self._infer_source_file(widget_path),
                    fix_hint=self._generate_fix_hint(issue_type, widget_path, detail),
                    widget_class=self._infer_widget_class(widget_path),
                )
            )
        return structured

    def _build_ai_input(self, structured: list[StructuredIssue]) -> dict[str, Any]:
        """构建给多模态 AI 的完整分析输入"""
        # 构建 source_file_hints: widget_path → source_file
        source_hints: dict[str, str] = {}
        for si in structured:
            source_hints[si.widget_path] = si.source_file

        return {
            "test_session": datetime.now().isoformat(),
            "project": "auto-pm (SW-2026-008)",
            "code_base": "V0.5.4",
            "screenshot_dir": str(self.screenshot_dir) if self.screenshot_dir else "",
            "screenshots": self._screenshots,
            "screenshot_count": len(self._screenshots),
            "summary": {
                "total_bugs": len(self._bugs),
                "total_visual_issues": len(self._visual_issues),
                "by_severity": {
                    sev: sum(
                        1 for b in self._bugs
                        if b.get("severity") == sev
                    ) + sum(
                        1 for v in self._visual_issues
                        if v.get("severity") == sev
                    )
                    for sev in ("critical", "major", "minor")
                },
                "views_tested": ["desktop 1920x1080", "tablet 768x1024", "mobile 375x812"],
            },
            "bugs": [
                {
                    "id": f"BUG-{i+1:03d}",
                    "step": b.get("step", ""),
                    "error": b.get("error", ""),
                    "severity": b.get("severity", "major"),
                    "screenshot": b.get("screenshot", ""),
                    "timestamp": b.get("timestamp", ""),
                }
                for i, b in enumerate(self._bugs)
            ],
            "visual_issues": [
                {
                    "id": f"VIS-{i+1:03d}",
                    "type": si.issue_type,
                    "severity": si.severity,
                    "widget_path": si.widget_path,
                    "source_file": si.source_file,
                    "widget_class": si.widget_class,
                    "detail": si.detail,
                    "viewport": si.viewport,
                    "screenshot": si.screenshot,
                    "fix_hint": si.fix_hint,
                }
                for i, si in enumerate(structured)
            ],
            "source_file_hints": source_hints,
            "widget_snapshot": self._widget_snapshot,
            "op_log_tail": self._op_log[-20:] if self._op_log else [],
            "_instructions": (
                "请基于此 JSON 中的 screenshots、visual_issues 和 widget_snapshot "
                "分析 GUI 的视觉问题，并输出修复建议。修复建议应精确到文件名和行号。"
                "输出格式见 ai_fix_suggestions_template.json。"
            ),
        }
