"""PLC-HMI 概念映射：SFB 库函数（文档注入（向项目注入规范文件/模板））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

文档自动区注入服务（V0.4.1 Step 2）

为历史 PLC 项目 retrofit AUTO_PM 标记。与 DocRefreshService 职责分离：
- DocRefreshService: 仅替换已有 AUTO_PM 标记内容
- DocInjectService:   仅插入新 AUTO_PM 标记（不替换已有）

通过组合 DocRefreshService 复用其 builder 方法与 _locate_target_docs / _load_asset_data。

锚点映射（marker key → 锚点正则，宽松前缀匹配）：
- plc-program-components → `4.1/5.1 组件清单(与职责)`
- plc-asset-index        → `8/13 关联文档索引`
- plc-io-overview        → `2 IO总览/2 系统硬件配置总览`
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from auto_pm.core.doc_refresh_service import DocRefreshService
from auto_pm.models import ProjectInfo
from auto_pm.utils.file_utils import StaleFileError, read_file_snapshot, write_file

log = logging.getLogger(__name__)


# 锚点正则映射：兼容模板文档与历史真实项目的章节编号差异。
_ANCHOR_PATTERNS: dict[str, str] = {
    "plc-program-components": r"^###\s+(?:4|5)\.1\s+组件清单(?:与职责)?",
    "plc-asset-index": r"^##\s+(?:8|13)\.\s+关联文档索引",
    "plc-io-overview": r"^##\s+2\.\s*(?:IO(?:\s*总览)?|系统硬件配置总览)",
}


@dataclass
class InjectedDocument:
    """单个文档注入结果"""

    file_path: str
    injected_keys: list[str] = field(default_factory=list)  # 新插入的 marker key
    skipped_keys: list[str] = field(default_factory=list)  # 已存在 marker，跳过
    missing_anchors: list[str] = field(default_factory=list)  # 锚点未找到的 marker key
    changed: bool = False


@dataclass
class DocInjectResult:
    """文档注入结果"""

    project_id: str
    dry_run: bool
    updated: bool
    injected_files: list[InjectedDocument] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "dry_run": self.dry_run,
            "updated": self.updated,
            "injected_files": [asdict(item) for item in self.injected_files],
            "issues": self.issues,
        }


class DocInjectService:
    """为历史 PLC 项目注入 AUTO_PM 标记

    与 DocRefreshService 职责分离：
    - 仅在文档缺少 marker 时插入新 marker block
    - 已有 marker 时跳过（不替换内容）
    - 锚点缺失时报告 issue（不强制注入）
    - 原手工内容保留在 END 标记之后，不丢失
    """

    def __init__(self, workspace_root: str) -> None:
        self.workspace_root = os.path.abspath(workspace_root)
        # 组合 DocRefreshService 复用其 builder 方法
        self._refresh_service = DocRefreshService(workspace_root)

    def inject_markers(
        self,
        project: ProjectInfo,
        dry_run: bool = False,
    ) -> DocInjectResult:
        """为项目文档注入 AUTO_PM 标记"""
        result = DocInjectResult(
            project_id=project.project_id,
            dry_run=dry_run,
            updated=False,
        )
        if project.stack != "plc":
            result.issues.append("仅 PLC 项目支持 doc inject")
            return result

        asset_data = self._refresh_service.load_asset_data(project.path)
        target_docs = self._refresh_service.locate_target_docs(project.path)
        if not target_docs:
            result.issues.append("未找到可注入标记的 PLC 文档")
            return result

        for doc_path, block_builders in target_docs:
            content, original_mtime = read_file_snapshot(doc_path)
            if not content:
                result.issues.append(f"读取文档失败: {doc_path}")
                continue

            original = content
            injected_doc = InjectedDocument(file_path=doc_path)

            for block_key, builder_name in block_builders:
                # 1. 检查 marker 是否已存在 → 跳过
                if self._has_marker(content, block_key):
                    injected_doc.skipped_keys.append(block_key)
                    continue

                # 2. 查找锚点正则
                anchor_pattern = _ANCHOR_PATTERNS.get(block_key)
                if not anchor_pattern:
                    result.issues.append(f"未配置锚点正则: {block_key}")
                    continue

                # 3. 查找锚点位置
                anchor_pos = self._find_anchor(content, anchor_pattern)
                if anchor_pos < 0:
                    injected_doc.missing_anchors.append(block_key)
                    result.issues.append(
                        f"文档缺少锚点: {os.path.basename(doc_path)} [{block_key}] "
                        f"期望匹配: {anchor_pattern}"
                    )
                    continue

                # 4. 生成 marker block 内容（复用 DocRefreshService 的 builder）
                builder = getattr(self._refresh_service, builder_name)
                generated_body = builder(project, asset_data)

                # 5. 构造完整 marker block 并插入
                marker_block = self._build_marker_block(block_key, generated_body)
                content = self._insert_after_anchor(content, anchor_pos, marker_block)
                injected_doc.injected_keys.append(block_key)

            if not (
                injected_doc.injected_keys
                or injected_doc.skipped_keys
                or injected_doc.missing_anchors
            ):
                continue

            injected_doc.changed = bool(injected_doc.injected_keys) and content != original
            result.injected_files.append(injected_doc)

            if injected_doc.changed and not dry_run:
                try:
                    write_file(doc_path, content, expected_mtime=original_mtime)
                except StaleFileError as exc:
                    result.issues.append(f"文档已被外部修改，跳过写入: {doc_path} ({exc})")
                    continue
                result.updated = True

        return result

    @staticmethod
    def _has_marker(content: str, block_key: str) -> bool:
        """检查内容中是否已存在指定 marker 的 BEGIN 标记"""
        pattern = re.compile(
            r"<!--\s*AUTO_PM:BEGIN\s+" + re.escape(block_key) + r"\s*-->",
            re.MULTILINE,
        )
        return bool(pattern.search(content))

    @staticmethod
    def _find_anchor(content: str, anchor_pattern: str) -> int:
        """查找锚点标题位置

        返回锚点行末尾换行符之后的位置（即下一行开头）。
        返回 -1 表示未找到。
        """
        pattern = re.compile(anchor_pattern, re.MULTILINE)
        match = pattern.search(content)
        if not match:
            return -1
        line_end = content.find("\n", match.end())
        return line_end + 1 if line_end >= 0 else len(content)

    @staticmethod
    def _build_marker_block(block_key: str, generated_body: str) -> str:
        """构造完整 marker block

        格式与 DocRefreshService._replace_auto_block 替换后的格式一致：
        <!-- AUTO_PM:BEGIN {key} -->{generated_body}<!-- AUTO_PM:END {key} -->\\n
        """
        return (
            f"<!-- AUTO_PM:BEGIN {block_key} -->"
            f"{generated_body}"
            f"<!-- AUTO_PM:END {block_key} -->\n"
        )

    @staticmethod
    def _insert_after_anchor(content: str, anchor_pos: int, marker_block: str) -> str:
        """在锚点位置后插入 marker block

        anchor_pos 指向锚点行末尾换行符之后的位置（下一行开头）。
        插入策略：在锚点后插入空行 + marker block + 空行，原内容保留在 marker block 之后。
        """
        return content[:anchor_pos] + "\n" + marker_block + "\n" + content[anchor_pos:]
