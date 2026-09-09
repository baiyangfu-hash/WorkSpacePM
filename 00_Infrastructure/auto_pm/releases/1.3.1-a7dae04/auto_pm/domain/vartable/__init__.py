"""变量表解析模块

V2.3 吸收 SW-2026-001 变量表解析能力，提供多格式解析、编码检测、转换导出能力。

模块结构：
- models.py: 数据模型（VarEntry/VarTable/ParseResult/ParseError + BlockEntry/BlockTable/ChannelEntry/ChannelTable/FormatType）
- parsers/: 各格式解析器（io_points_csv/program_blocks.yml/communications.yml + autoshop/work3/codesys/scl/intdoc）
- utils/: 工具（encoding 编码检测/...）
- converter.py: 格式转换器（统一中间模型导出 CSV/YAML/JSON，V2.3 Week3 T13）
- batch_parser.py: 批量解析器（目录扫描 + 多文件聚合，V2.3 Week3 T14）
"""

from auto_pm.vartable.batch_parser import BatchParser
from auto_pm.vartable.converter import VariableConverter
from auto_pm.vartable.models import (
    BlockEntry,
    BlockTable,
    ChannelEntry,
    ChannelTable,
    FormatType,
    ParseError,
    ParseResult,
    VarEntry,
    VarTable,
)

__all__ = [
    "BatchParser",
    "BlockEntry",
    "BlockTable",
    "ChannelEntry",
    "ChannelTable",
    "FormatType",
    "ParseError",
    "ParseResult",
    "VarEntry",
    "VarTable",
    "VariableConverter",
]
