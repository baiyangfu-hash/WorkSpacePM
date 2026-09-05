"""PLC-HMI 概念映射：SFB 库函数（Frontmatter 服务（Markdown 文件元数据管理））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from auto_pm.spec.core.config import WorkspaceConfig
from auto_pm.spec.core.registry import SpecRegistry

log = logging.getLogger(__name__)


@dataclass
class FrontmatterItem:
    spec_id: str
    file_path: Path
    has_frontmatter: bool
    is_deprecated: bool
    file_exists: bool
    new_frontmatter: str
    status: str


@dataclass
class FrontmatterOutput:
    items: list[FrontmatterItem]
    modified_count: int = 0
    skipped_count: int = 0
    error_count: int = 0


class FrontmatterService:
    def __init__(self, workspace: Path, config: WorkspaceConfig | None = None) -> None:
        self.workspace = workspace
        self.config = config or WorkspaceConfig(workspace=workspace)
        self.registry = SpecRegistry(workspace, registry_path=self.config.registry_path)
        if not self.registry.load():
            raise FileNotFoundError(f"注册表文件不存在或格式错误: {self.registry.path}")

    def preview(self, spec_id: str | None = None) -> list[FrontmatterItem]:
        raw_specs = self.registry.raw.get("specs", {})
        if not isinstance(raw_specs, dict) or not raw_specs:
            return []

        if spec_id:
            spec = raw_specs.get(spec_id)
            if not isinstance(spec, dict):
                return []
            specs_to_process = {spec_id: spec}
        else:
            specs_to_process = {
                sid: spec
                for sid, spec in raw_specs.items()
                if isinstance(sid, str) and isinstance(spec, dict)
            }

        items: list[FrontmatterItem] = []

        for sid, spec in specs_to_process.items():
            lifecycle = spec.get("lifecycle", "")
            is_deprecated = lifecycle in ("deprecated", "archived")

            canonical_path = spec.get("canonical_path", "")
            file_path = self.workspace / canonical_path
            file_exists = file_path.exists()

            if is_deprecated:
                items.append(
                    FrontmatterItem(
                        spec_id=sid,
                        file_path=file_path,
                        has_frontmatter=False,
                        is_deprecated=True,
                        file_exists=file_exists,
                        new_frontmatter="",
                        status="skipped",
                    )
                )
                continue

            if not file_exists:
                items.append(
                    FrontmatterItem(
                        spec_id=sid,
                        file_path=file_path,
                        has_frontmatter=False,
                        is_deprecated=False,
                        file_exists=False,
                        new_frontmatter="",
                        status="error",
                    )
                )
                continue

            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception as e:
                log.warning(
                    "读取规范文件 frontmatter 失败: %s, 错误: %s", file_path, e, exc_info=True
                )
                items.append(
                    FrontmatterItem(
                        spec_id=sid,
                        file_path=file_path,
                        has_frontmatter=False,
                        is_deprecated=False,
                        file_exists=True,
                        new_frontmatter="",
                        status="error",
                    )
                )
                continue

            has_frontmatter = content.startswith("---")
            if has_frontmatter:
                items.append(
                    FrontmatterItem(
                        spec_id=sid,
                        file_path=file_path,
                        has_frontmatter=True,
                        is_deprecated=False,
                        file_exists=True,
                        new_frontmatter="",
                        status="skipped",
                    )
                )
                continue

            fm = self._generate_frontmatter(sid, spec)
            items.append(
                FrontmatterItem(
                    spec_id=sid,
                    file_path=file_path,
                    has_frontmatter=False,
                    is_deprecated=False,
                    file_exists=True,
                    new_frontmatter=fm,
                    status="pending",
                )
            )

        return items

    def apply(self, items: list[FrontmatterItem]) -> FrontmatterOutput:
        modified_count = 0
        skipped_count = 0
        error_count = 0

        for item in items:
            if item.status != "pending":
                skipped_count += 1
                continue

            try:
                content = item.file_path.read_text(encoding="utf-8")
                new_content = item.new_frontmatter + "\n\n" + content
                item.file_path.write_text(new_content, encoding="utf-8")
                item.status = "applied"
                modified_count += 1
            except Exception as e:
                log.warning("应用 frontmatter 失败: %s, 错误: %s", item.file_path, e, exc_info=True)
                item.status = "error"
                error_count += 1

        return FrontmatterOutput(
            items=items,
            modified_count=modified_count,
            skipped_count=skipped_count,
            error_count=error_count,
        )

    def _generate_frontmatter(self, spec_id: str, spec: dict[str, Any]) -> str:
        fm_data: dict[str, object] = {
            "spec_id": spec_id,
            "title": spec.get("title", ""),
            "version": spec.get("version", ""),
            "domain": spec.get("domain", ""),
            "lifecycle": spec.get("lifecycle", ""),
            "canonical_path": spec.get("canonical_path", ""),
        }
        for key in ("number", "sub_domain", "type_prefix"):
            if spec.get(key):
                fm_data[key] = spec[key]
        for key in ("replaces", "replaced_by", "tags"):
            if spec.get(key):
                fm_data[key] = spec[key]
        fm_text = yaml.dump(fm_data, allow_unicode=True, default_flow_style=False)
        return f"---\n{fm_text}---"
