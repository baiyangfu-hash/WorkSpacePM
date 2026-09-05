"""PLC-HMI 概念映射：SFB 库函数（通信解析器（解析通信配置变量表））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

communications.yml 解析器

V2.3 Week2 T09：在 AssetSummaryService._read_communications 基础上深化，
提取每个 channel 的具体字段值到 ChannelEntry。

DJ-2026-005 真实样例字段：
    project_id / project_type    顶层元数据
    channels:                    列表
      - name / protocol / role / endpoint / notes   每通道 5 字段

AssetSummaryService._CHANNEL_REQUIRED_KEYS = ("name", "protocol", "role", "endpoint", "notes")

设计原则：
- 不复用 SW-2026-001 死代码（PRD §7 明确不复用）
- 复用 AssetSummaryService._CHANNEL_REQUIRED_KEYS 字段校验语义
- 使用 vartable.utils.encoding 检测编码
- 容错模式：单项错误不中断整体解析，记录到 ParseResult.errors
- 返回 ParseResult.channel_table（var_table 保持 None）
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from auto_pm.vartable.models import (
    ChannelEntry,
    ChannelTable,
    ParseError,
    ParseResult,
)
from auto_pm.vartable.utils.encoding import read_file_with_detection

# communications.yml 必需字段（与 AssetSummaryService._CHANNEL_REQUIRED_KEYS 对齐）
REQUIRED_KEYS: tuple[str, ...] = ("name", "protocol", "role", "endpoint", "notes")

SOURCE_FORMAT = "communications_yml"


class CommunicationsParser:
    """communications.yml 解析器

    用法：
        parser = CommunicationsParser()
        result = parser.parse("path/to/communications.yml")
        if result.success and result.channel_table is not None:
            for entry in result.channel_table.entries:
                print(entry.channel_name, entry.protocol, entry.endpoint)
    """

    def parse(self, file_path: str | Path) -> ParseResult:
        """解析 communications.yml 文件

        Args:
            file_path: communications.yml 文件路径

        Returns:
            ParseResult：成功时 channel_table 含 ChannelEntry 列表；失败时 errors 含原因

        容错策略：
        - 文件不存在/读取失败 → success=False, channel_table=None
        - 缺少 channels 列表 → success=False, channel_table=None
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

        channels = data.get("channels")
        if not isinstance(channels, list):
            return ParseResult(
                success=False,
                var_table=None,
                errors=(
                    ParseError(
                        line_number=1,
                        field="channels",
                        message="缺少 channels 列表或类型不正确",
                        raw_value=str(type(channels).__name__),
                    ),
                ),
            )

        # 逐项解析（index 从 1 开始，与 AssetSummaryService 对齐）
        entries: list[ChannelEntry] = []
        errors: list[ParseError] = []
        warnings: list[str] = []

        for index, channel in enumerate(channels, start=1):
            if not isinstance(channel, dict):
                errors.append(
                    ParseError(
                        line_number=index,
                        field="channel",
                        message=f"第 {index} 项必须为对象",
                        raw_value=str(type(channel).__name__),
                    )
                )
                continue

            entry = self._parse_channel(channel, index)
            if isinstance(entry, ParseError):
                errors.append(entry)
            elif isinstance(entry, ChannelEntry):
                entries.append(entry)

        # 构建元数据
        protocol_counts: dict[str, int] = {}
        for entry in entries:
            protocol_counts[entry.protocol] = protocol_counts.get(entry.protocol, 0) + 1

        # 提取顶层元数据（可选字段，不强制）
        metadata: dict[str, Any] = {
            "protocol_counts": protocol_counts,
            "total_items_read": len(entries) + len(errors),
            "project_id": str(data.get("project_id", "")),
            "project_type": str(data.get("project_type", "")),
        }

        channel_table = ChannelTable(
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
            channel_table=channel_table,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _parse_channel(channel: dict[str, Any], index: int) -> ChannelEntry | ParseError:
        """解析单个 channel 项

        Returns:
            ChannelEntry: 解析成功
            ParseError: 解析失败（必需字段缺失或为空）
        """
        # 提取并清理字段
        name = str(channel.get("name", "")).strip()
        protocol = str(channel.get("protocol", "")).strip()
        role = str(channel.get("role", "")).strip()
        endpoint = str(channel.get("endpoint", "")).strip()
        notes = str(channel.get("notes", "")).strip()

        # 必需字段校验
        missing: list[str] = []
        if not name:
            missing.append("name")
        if not protocol:
            missing.append("protocol")
        if not role:
            missing.append("role")
        if not endpoint:
            missing.append("endpoint")
        if not notes:
            missing.append("notes")

        if missing:
            return ParseError(
                line_number=index,
                field=",".join(missing),
                message=f"第 {index} 项缺少必需字段: {', '.join(missing)}",
                raw_value=str(channel),
            )

        return ChannelEntry(
            channel_name=name,
            protocol=protocol,
            role=role,
            endpoint=endpoint,
            notes=notes,
            source_format=SOURCE_FORMAT,
            index=index,
        )
