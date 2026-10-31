"""PLC-HMI 概念映射：SFB 库函数（规范索引（生成规范文档索引））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from auto_pm.spec.core.config import (
    AUTO_GENERATED_HEADER,
    CORE_IDS,
    DOMAIN_CONFIG,
    WorkspaceConfig,
)
from auto_pm.spec.core.registry import SpecRegistry


@dataclass
class IndexOutput:
    generated_files: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class IndexService:
    def __init__(self, workspace: Path, config: WorkspaceConfig | None = None) -> None:
        self.workspace = workspace
        self.config = config or WorkspaceConfig(workspace=workspace)
        self.registry = SpecRegistry(workspace, registry_path=self.config.registry_path)
        if not self.registry.load():
            raise FileNotFoundError(f"注册表文件不存在或格式错误: {self.registry.path}")

    def run(self, domains: list[str] | None = None) -> IndexOutput:
        output = IndexOutput()
        raw = self.registry.raw
        if not raw:
            output.errors.append("注册表为空或不存在")
            return output

        domains_to_generate = domains or ["pm", "plc", "python"]

        for d in domains_to_generate:
            try:
                if d == "pm":
                    content = self._generate_pm_index(raw)
                else:
                    content = self._generate_tech_stack_index(raw, d)

                cfg = DOMAIN_CONFIG[d]
                output_path = self.workspace / cfg["output_path"]
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(content, encoding="utf-8")
                output.generated_files.append(output_path)
            except Exception as e:
                output.errors.append(f"{d}: {e}")

        return output

    @staticmethod
    def _iter_registry_specs(raw: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        specs = raw.get("specs", {})
        if not isinstance(specs, dict):
            return []
        return [
            (spec_id, info)
            for spec_id, info in specs.items()
            if isinstance(spec_id, str) and isinstance(info, dict)
        ]

    def _get_specs_by_domain(
        self,
        raw: dict[str, Any],
        domain: str,
        lifecycle_filter: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if lifecycle_filter is None:
            lifecycle_filter = ["stable", "draft"]
        specs = []
        for spec_id, info in self._iter_registry_specs(raw):
            if info.get("domain") == domain and info.get("lifecycle") in lifecycle_filter:
                entry = dict(info)
                entry["spec_id"] = spec_id
                specs.append(entry)
        specs.sort(key=lambda s: s.get("number", "999"))
        return specs

    def _get_deprecated_specs(self, raw: dict[str, Any], domain: str, lifecycles: list[str] | None = None) -> list[dict[str, Any]]:
        if lifecycles is None:
            lifecycles = ["deprecated", "archived"]
        specs = []
        for spec_id, info in self._iter_registry_specs(raw):
            if info.get("domain") == domain and info.get("lifecycle") in lifecycles:
                entry = dict(info)
                entry["spec_id"] = spec_id
                specs.append(entry)
        specs.sort(key=lambda s: s.get("number", "999"))
        return specs

    def _generate_pm_index(self, raw: dict[str, Any]) -> str:
        cfg = DOMAIN_CONFIG["pm"]
        specs = self._get_specs_by_domain(raw, "pm")
        deprecated = self._get_deprecated_specs(raw, "pm", ["deprecated"])
        archived = self._get_deprecated_specs(raw, "pm", ["archived"])
        now = datetime.now().strftime("%Y-%m-%d")
        lines: list[str] = []

        registry_version = raw.get("version", "unknown")
        lines.append(f"# {cfg['title']} {registry_version}")
        lines.append("")
        lines.append(f"> {AUTO_GENERATED_HEADER}")
        lines.append(f"> **版本**: {registry_version} (自动生成)")
        lines.append(f"> **生成日期**: {now}")
        lines.append("> **权威来源**: `spec_registry.json` + Obsidian 规范真源文件")
        lines.append("> **注册表**: spec_registry.json")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 📋 项目管理域规范")

        grouped: dict[str, list[dict[str, Any]]] = {}
        for spec in specs:
            sd = spec.get("sub_domain", "其他")
            grouped.setdefault(sd, []).append(spec)

        for sub_domain, label in cfg["sub_domains"].items():
            group_specs = grouped.get(sub_domain, [])
            if not group_specs:
                continue
            lines.append(f"### {label} ({len(group_specs)}个)")
            lines.append("")
            lines.append("| 编号 | 文件 | 版本 | 说明 |")
            lines.append("|------|------|------|------|")
            for spec in group_specs:
                fname = Path(spec["canonical_path"]).name
                rel = spec["canonical_path"].replace("00_Obsidian_Base全局规范文件仓库/", "")
                lines.append(f"| {spec['spec_id']} | [{fname}]({rel}) | {spec['version']} | {spec['title']} |")
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("## ⚠️ 技术栈规范位置（当前真源）")
        lines.append("")
        lines.append("| 技术栈 | 规范位置 | 包含内容 |")
        lines.append("|--------|----------|----------|")
        lines.append("| **PLC** | `00_Obsidian_Base全局规范文件仓库/03_PLC自动化域/` | LSP-903~907、STD-820/830/840/850/860 等 PLC 真源规范 |")
        lines.append("| **Python** | `00_Obsidian_Base全局规范文件仓库/02_Python开发域/` | DEV-210/211/216/217/218/220 等 Python 真源规范 |")
        lines.append("")
        lines.append("**冲突处理**: 当全局PM规范与技术栈编码/架构规范冲突时，以本索引列出的技术栈真源目录为准")
        lines.append("")
        lines.append("---")
        lines.append("")

        lines.append("## 已废弃规范（Deprecated）")
        lines.append("")
        lines.append("> 以下规范已被替代，仅供历史参考")
        lines.append("")
        if deprecated:
            lines.append("| spec_id | 标题 | 替代规范 | 废弃日期 |")
            lines.append("|---------|------|---------|---------|")
            for spec in deprecated:
                replaced_by = spec.get("replaced_by", [])
                replaced_str = ", ".join(replaced_by) if isinstance(replaced_by, list) else str(replaced_by)
                deprecated_date = spec.get("deprecated_date", "未知")
                lines.append(f"| {spec['spec_id']} | {spec['title']} | {replaced_str or '无'} | {deprecated_date} |")
        else:
            lines.append("暂无")
        lines.append("")

        lines.append("## 已归档规范（Archived）")
        lines.append("")
        lines.append("> 以下规范已从活跃目录移除")
        lines.append("")
        if archived:
            lines.append("| spec_id | 标题 | 归档路径 | 归档日期 |")
            lines.append("|---------|------|---------|---------|")
            for spec in archived:
                canonical_path = spec.get("canonical_path", "")
                archived_date = spec.get("archived_date", "未知")
                lines.append(f"| {spec['spec_id']} | {spec['title']} | {canonical_path} | {archived_date} |")
        else:
            lines.append("暂无")
        lines.append("")
        lines.append("---")
        lines.append("")

        lines.append("## 📊 统计")
        lines.append("")
        lines.append("| 指标 | 数值 |")
        lines.append("|------|------|")
        lines.append(f"| 活跃PM规范 | **{len(specs)}个** |")
        lines.append(f"| 已废弃规范 | **{len(deprecated)}个** |")
        lines.append(f"| 已归档规范 | **{len(archived)}个** |")
        lines.append(f"| 最后更新 | {now} |")
        lines.append("")
        lines.append(f"*索引自动生成: {now} | 注册表版本: {raw.get('version', 'unknown')}*")

        return "\n".join(lines)

    def _generate_tech_stack_index(self, raw: dict[str, Any], domain: str) -> str:
        cfg = DOMAIN_CONFIG[domain]
        specs = self._get_specs_by_domain(raw, domain)
        cross_domain_specs = self._get_specs_by_domain(raw, "cross-domain") if domain == "plc" else []
        deprecated = self._get_deprecated_specs(raw, domain, ["deprecated"])
        archived = self._get_deprecated_specs(raw, domain, ["archived"])
        now = datetime.now().strftime("%Y-%m-%d")
        lines: list[str] = []

        lines.append(f"# {cfg['title']}")
        lines.append("")
        lines.append(f"> {AUTO_GENERATED_HEADER}")
        lines.append("> **版本**: 自动生成版")
        lines.append(f"> **生成日期**: {now}")
        lines.append("")
        lines.append("---")
        lines.append("")

        for sub_domain, label in cfg["sub_domains"].items():
            sub_specs = [s for s in specs if s.get("sub_domain") == sub_domain]
            if not sub_specs:
                continue
            lines.append(f"## {label} (`{sub_domain}/`)")
            lines.append("")
            lines.append("| 规范ID | 文件名 | 版本 | 说明 | 优先级 |")
            lines.append("|--------|--------|------|------|--------|")
            core_ids = CORE_IDS.get(domain, [])
            for spec in sub_specs:
                fname = Path(spec["canonical_path"]).name
                priority = "🔴必读" if spec["spec_id"] in core_ids else "🟡配套"
                lines.append(f"| {spec['spec_id']} | {fname} | {spec['version']} | {spec['title']} | {priority} |")
            lines.append("")

        if cross_domain_specs and domain == "plc":
            lines.append("## 跨域工具规范 (`项目管理/`)")
            lines.append("")
            lines.append("| 规范ID | 文件名 | 版本 | 说明 |")
            lines.append("|--------|--------|------|------|")
            for spec in cross_domain_specs:
                fname = Path(spec["canonical_path"]).name
                lines.append(f"| {spec['spec_id']} | {fname} | {spec['version']} | {spec['title']} |")
            lines.append("")

        lines.append("## 已废弃规范（Deprecated）")
        lines.append("")
        lines.append("> 以下规范已被替代，仅供历史参考")
        lines.append("")
        if deprecated:
            lines.append("| spec_id | 标题 | 替代规范 | 废弃日期 |")
            lines.append("|---------|------|---------|---------|")
            for spec in deprecated:
                replaced_by = spec.get("replaced_by", [])
                replaced_str = ", ".join(replaced_by) if isinstance(replaced_by, list) else str(replaced_by)
                deprecated_date = spec.get("deprecated_date", "未知")
                lines.append(f"| {spec['spec_id']} | {spec['title']} | {replaced_str or '无'} | {deprecated_date} |")
        else:
            lines.append("暂无")
        lines.append("")

        lines.append("## 已归档规范（Archived）")
        lines.append("")
        lines.append("> 以下规范已从活跃目录移除")
        lines.append("")
        if archived:
            lines.append("| spec_id | 标题 | 归档路径 | 归档日期 |")
            lines.append("|---------|------|---------|---------|")
            for spec in archived:
                canonical_path = spec.get("canonical_path", "")
                archived_date = spec.get("archived_date", "未知")
                lines.append(f"| {spec['spec_id']} | {spec['title']} | {canonical_path} | {archived_date} |")
        else:
            lines.append("暂无")
        lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("## 溯源信息")
        lines.append("")
        lines.append("- **注册表**: `00_Obsidian_Base全局规范文件仓库/spec_registry.json`")
        lines.append(f"- **生成时间**: {now}")
        lines.append("")
        lines.append(f"*{AUTO_GENERATED_HEADER}*")

        return "\n".join(lines)
