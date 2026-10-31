"""PLC-HMI 概念映射：SFB 库函数（解析器基类（所有变量表解析器的父类））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

多格式解析器抽象基类

V2.3 Week2 T10：定义所有 PLC 变量表解析器的统一接口。

设计原则：
- 重新实现，不复用 SW-2026-001 src/parser/base_parser.py 死代码（PRD §7 明确不复用）
- 抽象基类强制子类实现 parse() 方法
- parse() 返回 ParseResult（统一成功/失败返回，避免异常控制流）
- 复用 vartable.utils.encoding 检测编码
- 容错模式：单行错误不中断整体解析，记录到 ParseResult.errors

与 SW-2026-001 BaseParser 的差异（参考结构但重新实现）：
- SW-2026-001 用 List[Dict] 返回 + 异常控制流；本基类用 ParseResult 返回
- SW-2026-001 在 __init__ 接收 file_path 并存 self.variables；本基类无状态，parse() 接收路径
- SW-2026-001 用 EncodingDetector 工具类；本基类复用 vartable.utils.encoding.read_file_with_detection
"""

from __future__ import annotations

import abc
from pathlib import Path

from auto_pm.vartable.models import ParseError, ParseResult
from auto_pm.vartable.utils.encoding import read_file_with_detection


class BaseParser(abc.ABC):
    """多格式解析器抽象基类

    子类必须实现 parse() 方法，返回 ParseResult。
    不同格式解析器只填充对应 table（var_table/block_table/channel_table）。

    用法：
        class MyFormatParser(BaseParser):
            def parse(self, file_path: str | Path) -> ParseResult:
                ...
    """

    @abc.abstractmethod
    def parse(self, file_path: str | Path) -> ParseResult:
        """解析文件，返回 ParseResult

        Args:
            file_path: 待解析文件路径

        Returns:
            ParseResult：成功时对应 table 非 None；失败时 errors 含原因
        """
        raise NotImplementedError

    @staticmethod
    def _read_file(file_path: str | Path) -> tuple[str, str] | ParseResult:
        """通用文件读取辅助

        Returns:
            (content, encoding): 读取成功
            ParseResult: 读取失败（文件不存在/读取异常）
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

        return content, encoding

    @staticmethod
    def _empty_content_error(file_path: str | Path, fmt: str) -> ParseResult:
        """构造空内容错误（解析器骨架未实现完整字段提取时使用）"""
        return ParseResult(
            success=False,
            var_table=None,
            errors=(
                ParseError(
                    line_number=0,
                    field="content",
                    message=f"文件内容为空或 {fmt} 格式不匹配",
                    raw_value=str(file_path),
                ),
            ),
        )
