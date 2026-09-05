"""PLC-HMI 概念映射：SFB 库函数（变量表模型（变量/VarGroup/VarTable 数据结构））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

变量表数据模型

V2.3 Week1 T01：定义变量表解析的统一数据模型。
V2.3 Week2 T08-T11：扩展支持 BlockEntry/ChannelEntry/FormatType。

设计原则：
- frozen dataclass 保证不可变，可哈希
- 字段对齐 io_points.csv 7 字段 + 解析元数据
- ParseResult 统一成功/失败返回，避免异常控制流
- VarTable.entries 用 tuple 而非 list（frozen 兼容）
- V2.3 Week2：BlockTable/ChannelTable 独立容器，避免 VarTable 泛型化破坏现有 API
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass(frozen=True, slots=True)
class VarEntry:
    """单个变量条目（io_points.csv 一行对应一个 VarEntry）

    字段对齐 DJ-2026-005 io_points.csv 的 7 列：
    station,signal_type,address,tag,signal_name,device,comment

    多地址格式示例：
    - cpu 站点: Y0/X0（直接 IO 地址）
    - remote_io 站点: RIO1:Y10（站点前缀:地址）

    comment 字段可能含分号分隔的多值，按原样保留：
    - "P40/EFS1/24.7; 源程序用途: 变频器1异常检测"
    """

    station: str
    signal_type: str
    address: str
    tag: str
    signal_name: str
    device: str
    comment: str
    source_format: str = "io_points_csv"
    line_number: int = 0

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化字典（供 JSON 输出）"""
        return {
            "station": self.station,
            "signal_type": self.signal_type,
            "address": self.address,
            "tag": self.tag,
            "signal_name": self.signal_name,
            "device": self.device,
            "comment": self.comment,
            "source_format": self.source_format,
            "line_number": self.line_number,
        }


@dataclass(frozen=True, slots=True)
class ParseError:
    """解析错误条目（某行某字段校验失败）"""

    line_number: int
    field: str
    message: str
    raw_value: str = ""


@dataclass(frozen=True, slots=True)
class VarTable:
    """变量表容器（一次解析的结果集）

    entries 用 tuple 而非 list，保证 frozen dataclass 可哈希。
    metadata 存放解析过程中收集的额外信息（如站点统计、地址段统计）。
    """

    entries: tuple[VarEntry, ...]
    source_path: str
    source_format: str
    parsed_at: str
    encoding: str = "utf-8"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def total_count(self) -> int:
        """变量条目总数"""
        return len(self.entries)

    @property
    def stations(self) -> tuple[str, ...]:
        """去重后的站点列表"""
        return tuple(sorted({entry.station for entry in self.entries}))

    @property
    def signal_types(self) -> tuple[str, ...]:
        """去重后的信号类型列表"""
        return tuple(sorted({entry.signal_type for entry in self.entries}))

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化字典（供 JSON 输出）"""
        return {
            "entries": [entry.to_dict() for entry in self.entries],
            "source_path": self.source_path,
            "source_format": self.source_format,
            "parsed_at": self.parsed_at,
            "encoding": self.encoding,
            "metadata": dict(self.metadata),
            "total_count": self.total_count,
            "stations": list(self.stations),
            "signal_types": list(self.signal_types),
        }


class FormatType(Enum):
    """支持的解析格式类型（V2.3 Week2 T11）

    用于 format_detector 自动识别 + CLI --format 显式指定。
    """

    AUTOSHOP = "autoshop"
    WORK3 = "work3"
    CODESYS = "codesys"
    SCL = "scl"
    INTDOC = "intdoc"
    IO_POINTS_CSV = "io_points_csv"
    PROGRAM_BLOCKS_YML = "program_blocks_yml"
    COMMUNICATIONS_YML = "communications_yml"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class BlockEntry:
    """单个程序块条目（program_blocks.yml 一项对应一个 BlockEntry）

    V2.3 Week2 T08：字段对齐 DJ-2026-005 program_blocks.yml 真实样例：
        name / type / path / responsibility

    AssetSummaryService._BLOCK_REQUIRED_KEYS = ("name", "type", "path", "responsibility")
    """

    block_name: str
    block_type: str
    path: str
    responsibility: str
    source_format: str = "program_blocks_yml"
    index: int = 0

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化字典（供 JSON 输出）"""
        return {
            "block_name": self.block_name,
            "block_type": self.block_type,
            "path": self.path,
            "responsibility": self.responsibility,
            "source_format": self.source_format,
            "index": self.index,
        }


@dataclass(frozen=True, slots=True)
class ChannelEntry:
    """单个通信通道条目（communications.yml 一项对应一个 ChannelEntry）

    V2.3 Week2 T09：字段对齐 DJ-2026-005 communications.yml 真实样例：
        name / protocol / role / endpoint / notes

    AssetSummaryService._CHANNEL_REQUIRED_KEYS = ("name", "protocol", "role", "endpoint", "notes")
    """

    channel_name: str
    protocol: str
    role: str
    endpoint: str
    notes: str
    source_format: str = "communications_yml"
    index: int = 0

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化字典（供 JSON 输出）"""
        return {
            "channel_name": self.channel_name,
            "protocol": self.protocol,
            "role": self.role,
            "endpoint": self.endpoint,
            "notes": self.notes,
            "source_format": self.source_format,
            "index": self.index,
        }


@dataclass(frozen=True, slots=True)
class BlockTable:
    """程序块表容器（一次解析 program_blocks.yml 的结果集）

    V2.3 Week2 T08：独立容器，不复用 VarTable（VarTable.entries 强类型 VarEntry）。
    """

    entries: tuple[BlockEntry, ...]
    source_path: str
    source_format: str
    parsed_at: str
    encoding: str = "utf-8"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def total_count(self) -> int:
        """程序块条目总数"""
        return len(self.entries)

    @property
    def block_types(self) -> tuple[str, ...]:
        """去重后的块类型列表"""
        return tuple(sorted({entry.block_type for entry in self.entries}))

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化字典（供 JSON 输出）"""
        return {
            "entries": [entry.to_dict() for entry in self.entries],
            "source_path": self.source_path,
            "source_format": self.source_format,
            "parsed_at": self.parsed_at,
            "encoding": self.encoding,
            "metadata": dict(self.metadata),
            "total_count": self.total_count,
            "block_types": list(self.block_types),
        }


@dataclass(frozen=True, slots=True)
class ChannelTable:
    """通信通道表容器（一次解析 communications.yml 的结果集）

    V2.3 Week2 T09：独立容器，不复用 VarTable。
    """

    entries: tuple[ChannelEntry, ...]
    source_path: str
    source_format: str
    parsed_at: str
    encoding: str = "utf-8"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def total_count(self) -> int:
        """通道条目总数"""
        return len(self.entries)

    @property
    def protocols(self) -> tuple[str, ...]:
        """去重后的协议列表"""
        return tuple(sorted({entry.protocol for entry in self.entries}))

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化字典（供 JSON 输出）"""
        return {
            "entries": [entry.to_dict() for entry in self.entries],
            "source_path": self.source_path,
            "source_format": self.source_format,
            "parsed_at": self.parsed_at,
            "encoding": self.encoding,
            "metadata": dict(self.metadata),
            "total_count": self.total_count,
            "protocols": list(self.protocols),
        }


@dataclass(frozen=True, slots=True)
class ParseResult:
    """解析结果（统一成功/失败返回）

    成功时 var_table/block_table/channel_table 之一非 None，errors 为空；
    失败时所有 table 为 None，errors 含失败原因；
    部分成功时 table 含已解析条目，errors 含失败行（容错模式）。

    V2.3 Week2：新增 block_table/channel_table 字段，向后兼容（默认 None）。
    不同格式解析器只填充对应 table，调用方按 source_format 判断。
    """

    success: bool
    var_table: VarTable | None
    errors: tuple[ParseError, ...] = ()
    warnings: tuple[str, ...] = ()
    block_table: BlockTable | None = None
    channel_table: ChannelTable | None = None

    @property
    def error_count(self) -> int:
        """错误数"""
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        """警告数"""
        return len(self.warnings)

    @property
    def entry_count(self) -> int:
        """已解析条目数（部分成功时也有值）

        优先级：var_table > block_table > channel_table。
        """
        if self.var_table is not None:
            return self.var_table.total_count
        if self.block_table is not None:
            return self.block_table.total_count
        if self.channel_table is not None:
            return self.channel_table.total_count
        return 0

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化字典（供 JSON 输出）"""
        return {
            "success": self.success,
            "var_table": self.var_table.to_dict() if self.var_table else None,
            "block_table": self.block_table.to_dict() if self.block_table else None,
            "channel_table": (self.channel_table.to_dict() if self.channel_table else None),
            "errors": [
                {
                    "line_number": err.line_number,
                    "field": err.field,
                    "message": err.message,
                    "raw_value": err.raw_value,
                }
                for err in self.errors
            ],
            "warnings": list(self.warnings),
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "entry_count": self.entry_count,
        }
