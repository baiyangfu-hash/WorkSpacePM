"""PLC-HMI 概念映射：SFB 库函数（程序块解析器（解析程序块变量表））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

program_blocks.yml 解析器

V2.3 Week2 T08：在 AssetSummaryService._read_program_blocks 基础上深化，
提取每个 block 的具体字段值到 BlockEntry。

DJ-2026-005 真实样例字段：
    project_id / project_name / plc_program_root  顶层元数据
    blocks:                                        列表
      - name / type / path / responsibility        每块 4 字段

AssetSummaryService._BLOCK_REQUIRED_KEYS = ("name", "type", "path", "responsibility")

设计原则：
- 不复用 SW-2026-001 死代码（PRD §7 明确不复用）
- 复用 AssetSummaryService._BLOCK_REQUIRED_KEYS 字段校验语义
- 使用 vartable.utils.encoding 检测编码
- 容错模式：单项错误不中断整体解析，记录到 ParseResult.errors
- 返回 ParseResult.block_table（var_table 保持 None）
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from auto_pm.vartable.models import (
    BlockEntry,
    BlockTable,
    ParseError,
    ParseResult,
)
from auto_pm.vartable.utils.encoding import read_file_with_detection

# program_blocks.yml 必需字段（与 AssetSummaryService._BLOCK_REQUIRED_KEYS 对齐）
REQUIRED_KEYS: tuple[str, ...] = ("name", "type", "path", "responsibility")

SOURCE_FORMAT = "program_blocks_yml"


class ProgramBlocksParser:
    """program_blocks.yml 解析器

    用法：
        parser = ProgramBlocksParser()
        result = parser.parse("path/to/program_blocks.yml")
        if result.success and result.block_table is not None:
            for entry in result.block_table.entries:
                print(entry.block_name, entry.block_type, entry.path)
    """

    def parse(self, file_path: str | Path) -> ParseResult:
        """解析 program_blocks.yml 文件

        Args:
            file_path: program_blocks.yml 文件路径

        Returns:
            ParseResult：成功时 block_table 含 BlockEntry 列表；失败时 errors 含原因

        容错策略：
        - 文件不存在/读取失败 → success=False, block_table=None
        - 缺少 blocks 列表 → success=False, block_table=None
        - 单项字段缺失 → success=True（部分成功），errors 含失败项
        """
        path = Path(file_path)
        if not path.exists():
            return ParseResult(
                success=False,
                var_table=None,
                errors=(
                    ParseError(
                        line_number=0,
                        field="file",
                        message=f"文件不存在: {file_path}",
                        raw_value=str(file_path),
                    ),
                ),
            )

        # 检测编码并读取
        try:
            content, encoding = read_file_with_detection(path)
        except OSError as exc:
            return ParseResult(
                success=False,
                var_table=None,
                errors=(
                    ParseError(
                        line_number=0,
                        field="file",
                        message=f"文件读取失败: {exc}",
                        raw_value=str(path),
                    ),
                ),
            )

        # 解析 YAML
        try:
            data = yaml.safe_load(content) or {}
        except yaml.YAMLError as exc:
            return ParseResult(
                success=False,
                var_table=None,
                errors=(
                    ParseError(
                        line_number=0,
                        field="yaml",
                        message=f"YAML 解析失败: {exc}",
                        raw_value=str(path),
                    ),
                ),
            )

        if not isinstance(data, dict):
            return ParseResult(
                success=False,
                var_table=None,
                errors=(
                    ParseError(
                        line_number=1,
                        field="root",
                        message="YAML 根节点必须为对象",
                        raw_value=type(data).__name__,
                    ),
                ),
            )

        blocks = data.get("blocks")
        if not isinstance(blocks, list):
            return ParseResult(
                success=False,
                var_table=None,
                errors=(
                    ParseError(
                        line_number=1,
                        field="blocks",
                        message="缺少 blocks 列表或类型不正确",
                        raw_value=str(type(blocks).__name__),
                    ),
                ),
            )

        # 逐项解析（index 从 1 开始，与 AssetSummaryService 对齐）
        entries: list[BlockEntry] = []
        errors: list[ParseError] = []
        warnings: list[str] = []

        for index, block in enumerate(blocks, start=1):
            if not isinstance(block, dict):
                errors.append(
                    ParseError(
                        line_number=index,
                        field="block",
                        message=f"第 {index} 项必须为对象",
                        raw_value=str(type(block).__name__),
                    )
                )
                continue

            entry = self._parse_block(block, index)
            if isinstance(entry, ParseError):
                errors.append(entry)
            elif isinstance(entry, BlockEntry):
                entries.append(entry)

        # 构建元数据
        block_type_counts: dict[str, int] = {}
        for entry in entries:
            block_type_counts[entry.block_type] = block_type_counts.get(entry.block_type, 0) + 1

        # 提取顶层元数据（可选字段，不强制）
        metadata: dict[str, Any] = {
            "block_type_counts": block_type_counts,
            "total_items_read": len(entries) + len(errors),
            "project_id": str(data.get("project_id", "")),
            "project_name": str(data.get("project_name", "")),
            "plc_program_root": str(data.get("plc_program_root", "")),
        }

        block_table = BlockTable(
            entries=tuple(entries),
            source_path=str(path.resolve()),
            source_format=SOURCE_FORMAT,
            parsed_at=datetime.now(UTC).isoformat(),
            encoding=encoding,
            metadata=metadata,
        )

        # 容错模式：有错误但有有效条目也算部分成功
        success = len(entries) > 0 or len(errors) == 0
        if errors and entries:
            warnings.append(f"解析完成但有 {len(errors)} 个错误，已跳过对应项")

        return ParseResult(
            success=success,
            var_table=None,
            block_table=block_table,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _parse_block(block: dict[str, Any], index: int) -> BlockEntry | ParseError:
        """解析单个 block 项

        Returns:
            BlockEntry: 解析成功
            ParseError: 解析失败（必需字段缺失或为空）
        """
        # 提取并清理字段
        name = str(block.get("name", "")).strip()
        block_type = str(block.get("type", "")).strip()
        block_path = str(block.get("path", "")).strip()
        responsibility = str(block.get("responsibility", "")).strip()

        # 必需字段校验
        missing: list[str] = []
        if not name:
            missing.append("name")
        if not block_type:
            missing.append("type")
        if not block_path:
            missing.append("path")
        if not responsibility:
            missing.append("responsibility")

        if missing:
            return ParseError(
                line_number=index,
                field=",".join(missing),
                message=f"第 {index} 项缺少必需字段: {', '.join(missing)}",
                raw_value=str(block),
            )

        return BlockEntry(
            block_name=name,
            block_type=block_type,
            path=block_path,
            responsibility=responsibility,
            source_format=SOURCE_FORMAT,
            index=index,
        )
