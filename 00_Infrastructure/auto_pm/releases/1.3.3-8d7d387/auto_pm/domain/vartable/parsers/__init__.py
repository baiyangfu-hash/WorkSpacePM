"""变量表解析器子模块

V2.3 Week2 T08-T11：
- T08 program_blocks_parser: program_blocks.yml 解析器
- T09 communications_parser: communications.yml 解析器
- T10 BaseParser + 5 格式解析器（autoshop/work3/codesys/scl/intdoc）
- T11 format_detector: 格式自动识别 + 工厂
"""

from auto_pm.vartable.parsers.autoshop_parser import AutoshopParser
from auto_pm.vartable.parsers.base_parser import BaseParser
from auto_pm.vartable.parsers.codesys_parser import CodesysParser
from auto_pm.vartable.parsers.communications_parser import CommunicationsParser
from auto_pm.vartable.parsers.format_detector import (
    detect_format,
    get_parser_for_format,
    list_supported_formats,
)
from auto_pm.vartable.parsers.intdoc_parser import IntDocParser
from auto_pm.vartable.parsers.io_points_parser import IoPointsParser
from auto_pm.vartable.parsers.program_blocks_parser import ProgramBlocksParser
from auto_pm.vartable.parsers.scl_parser import SclParser
from auto_pm.vartable.parsers.work3_parser import Work3Parser

__all__ = [
    "AutoshopParser",
    "BaseParser",
    "CodesysParser",
    "CommunicationsParser",
    "IntDocParser",
    "IoPointsParser",
    "ProgramBlocksParser",
    "SclParser",
    "Work3Parser",
    "detect_format",
    "get_parser_for_format",
    "list_supported_formats",
]
