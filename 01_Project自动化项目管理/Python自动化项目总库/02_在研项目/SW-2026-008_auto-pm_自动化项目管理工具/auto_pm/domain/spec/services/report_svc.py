"""PLC-HMI 概念映射：SFB 库函数（规范报告（生成规范检查报告））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from auto_pm.spec.core.config import (
    DOMAIN_LABELS,
    DOMAIN_ORDER,
    LIFECYCLE_ICONS,
    SUB_DOMAIN_ORDER,
    WorkspaceConfig,
)
from auto_pm.spec.core.registry import SpecRegistry


@dataclass
class ReportOutput:
    content: str
    output_path: Path
    fmt: str


class ReportService:
    def __init__(self, workspace: Path, config: WorkspaceConfig | None = None) -> None:
        self.workspace = workspace
        self.config = config or WorkspaceConfig(workspace=workspace)
        self.registry = SpecRegistry(workspace, registry_path=self.config.registry_path)
        if not self.registry.load():
            raise FileNotFoundError(f"注册表文件不存在或格式错误: {self.registry.path}")

    def generate(
        self,
        fmt: str = "markdown",
        output_path: Path | None = None,
    ) -> ReportOutput:
        raw = self.registry.raw

        if fmt == "json":
            content = json.dumps(raw, ensure_ascii=False, indent=2)
        else:
            content = self._generate_markdown_report(raw)

        if output_path:
            final_path = output_path
        else:
            default_name = (
                "规范元数据汇总报告.md" if fmt == "markdown" else "规范元数据汇总报告.json"
            )
            final_path = self.workspace / "00_Obsidian_Base全局规范文件仓库" / default_name

        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_text(content, encoding="utf-8")

        return ReportOutput(
            content=content,
            output_path=final_path,
            fmt=fmt,
        )

    def _generate_markdown_report(self, raw: dict[str, Any]) -> str:
        now = datetime.now().strftime("%Y-%m-%d")
        raw_specs = raw.get("specs", {})
        if isinstance(raw_specs, dict):
            specs = {
                sid: sinfo
                for sid, sinfo in raw_specs.items()
                if isinstance(sid, str) and isinstance(sinfo, dict)
            }
        else:
            specs = {}
        domains = raw.get("domains", {})
        lines: list[str] = []

        lines.append("# 规范元数据汇总报告")
        lines.append("")
        lines.append(f"> 生成日期: {now}")
        lines.append(f"> 数据来源: spec_registry.json v{raw.get('version', 'unknown')}")
        lines.append(f"> 工作空间: {self.workspace.name}")
        lines.append("")
        lines.append("---")
        lines.append("")

        total = len(specs)
        stable = sum(1 for s in specs.values() if s.get("lifecycle") == "stable")
        deprecated = sum(1 for s in specs.values() if s.get("lifecycle") == "deprecated")
        archived = sum(1 for s in specs.values() if s.get("lifecycle") == "archived")

        lines.append("## 总览")
        lines.append("")
        lines.append("| 指标 | 数值 |")
        lines.append("|------|------|")
        lines.append(f"| 规范总数 | **{total}** |")
        lines.append(f"| 🟢 活跃(stable) | **{stable}** |")
        lines.append(f"| 🟡 已废弃(deprecated) | **{deprecated}** |")
        lines.append(f"| ⚪ 已归档(archived) | **{archived}** |")
        lines.append("")

        domain_counts: dict[str, int] = {}
        for s in specs.values():
            d = s.get("domain", "unknown")
            domain_counts[d] = domain_counts.get(d, 0) + 1

        lines.append("### 按域分布")
        lines.append("")
        lines.append("| 域 | 说明 | 数量 |")
        lines.append("|----|------|------|")
        for domain_key, domain_desc in domains.items():
            cnt = domain_counts.get(domain_key, 0)
            lines.append(f"| `{domain_key}` | {domain_desc} | {cnt} |")
        lines.append("")
        lines.append("---")
        lines.append("")

        type_counts: dict[str, int] = {}
        for s in specs.values():
            tp = s.get("type_prefix") or "无"
            type_counts[tp] = type_counts.get(tp, 0) + 1

        lines.append("### 按类型前缀分布")
        lines.append("")
        lines.append("| 类型前缀 | 数量 |")
        lines.append("|----------|------|")
        for tp, cnt in sorted(type_counts.items(), key=lambda x: -x[1]):
            lines.append(f"| `{tp}` | {cnt} |")
        lines.append("")
        lines.append("---")
        lines.append("")

        lines.append("## 替代关系图")
        lines.append("")
        lines.append("```mermaid")
        lines.append("graph LR")
        for spec_id, spec_info in specs.items():
            replaced_by = spec_info.get("replaced_by", [])
            replaces = spec_info.get("replaces", [])
            if isinstance(replaced_by, list):
                for replaced in replaced_by:
                    lines.append(f"    {spec_id} --> {replaced}")
            elif replaced_by:
                lines.append(f"    {spec_id} --> {replaced_by}")
            if isinstance(replaces, list):
                for r in replaces:
                    lines.append(f"    {r} --> {spec_id}")
            elif replaces:
                lines.append(f"    {replaces} --> {spec_id}")
        lines.append("```")
        lines.append("")

        replaced_pairs: list[tuple[str, str]] = []
        for spec_id, spec_info in specs.items():
            replaced_by = spec_info.get("replaced_by", [])
            if isinstance(replaced_by, list):
                for replaced in replaced_by:
                    replaced_pairs.append((spec_id, replaced))
            elif replaced_by:
                replaced_pairs.append((spec_id, str(replaced_by)))

        if replaced_pairs:
            lines.append("| 废弃规范 | 替代规范 |")
            lines.append("|----------|----------|")
            for old, new in replaced_pairs:
                old_info = specs.get(old, {})
                new_info = specs.get(new, {})
                old_title = old_info.get("title", "?")
                new_title = new_info.get("title", "?")
                lines.append(f"| {old} ({old_title}) | **{new}** ({new_title}) |")
            lines.append("")

        lines.append("---")
        lines.append("")

        for domain_key in DOMAIN_ORDER:
            domain_specs = {
                sid: sinfo for sid, sinfo in specs.items() if sinfo.get("domain") == domain_key
            }
            if not domain_specs:
                continue

            label = DOMAIN_LABELS.get(domain_key, domain_key)
            lines.append(f"## {label}")
            lines.append("")

            sub_groups: dict[str, list[tuple[str, dict[str, Any]]]] = {}
            for sid, sinfo in domain_specs.items():
                sd = sinfo.get("sub_domain") or "其他"
                sub_groups.setdefault(sd, []).append((sid, sinfo))

            for sd in sorted(sub_groups.keys(), key=lambda x: SUB_DOMAIN_ORDER.get(x, 50)):
                group = sub_groups[sd]
                lines.append(f"### {sd} ({len(group)}个)")
                lines.append("")
                lines.append("| spec_id | 编号 | 标题 | 版本 | 生命周期 | 类型 | 文件名 |")
                lines.append("|---------|------|------|------|----------|------|--------|")
                for sid, sinfo in sorted(group, key=lambda x: x[1].get("number", "999")):
                    lifecycle = sinfo.get("lifecycle", "")
                    icon = LIFECYCLE_ICONS.get(lifecycle, "⚪")
                    fname = Path(sinfo.get("canonical_path", "")).name
                    lines.append(
                        f"| `{sid}` | {sinfo.get('number', '-')} | {sinfo.get('title', '')} | "
                        f"{sinfo.get('version', '')} | {icon}{lifecycle} | "
                        f"{sinfo.get('type_prefix', '-')} | `{fname}` |"
                    )
                lines.append("")

            lines.append("---")
            lines.append("")

        lines.append("## 完整YAML元数据清单")
        lines.append("")
        lines.append("以下为每个活跃规范的frontmatter原始数据：")
        lines.append("")

        for sid, sinfo in sorted(
            specs.items(), key=lambda x: (x[1].get("domain", "z"), x[1].get("number", "999"))
        ):
            lifecycle = sinfo.get("lifecycle", "")
            if lifecycle in ("deprecated", "archived"):
                continue
            lines.append(f"### `{sid}` — {sinfo.get('title', '')}")
            lines.append("")
            lines.append("```yaml")
            lines.append(f"spec_id: {sid}")
            lines.append(f'title: "{sinfo.get("title", "")}"')
            lines.append(f'version: "{sinfo.get("version", "")}"')
            lines.append(f"domain: {sinfo.get('domain', '')}")
            lines.append(f"lifecycle: {lifecycle}")
            lines.append(f'canonical_path: "{sinfo.get("canonical_path", "")}"')
            if sinfo.get("type_prefix"):
                lines.append(f"type_prefix: {sinfo['type_prefix']}")
            if sinfo.get("number"):
                lines.append(f'number: "{sinfo["number"]}"')
            if sinfo.get("sub_domain"):
                lines.append(f"sub_domain: {sinfo['sub_domain']}")
            replaces = sinfo.get("replaces", [])
            if replaces:
                if isinstance(replaces, list):
                    lines.append(f"replaces: [{', '.join(replaces)}]")
                else:
                    lines.append(f"replaces: [{replaces}]")
            replaced_by = sinfo.get("replaced_by", [])
            if replaced_by:
                if isinstance(replaced_by, list):
                    lines.append(f"replaced_by: [{', '.join(replaced_by)}]")
                else:
                    lines.append(f"replaced_by: [{replaced_by}]")
            tags = sinfo.get("tags", [])
            if tags:
                tags_str = ", ".join(f'"{t}"' for t in tags)
                lines.append(f"tags: [{tags_str}]")
            lines.append("```")
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append(f"*报告自动生成于 {now} | 注册表版本: v{raw.get('version', 'unknown')}*")

        return "\n".join(lines)
