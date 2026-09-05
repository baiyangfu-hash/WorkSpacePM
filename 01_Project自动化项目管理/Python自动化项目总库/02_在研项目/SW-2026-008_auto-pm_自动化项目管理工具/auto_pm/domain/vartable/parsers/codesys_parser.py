"""PLC-HMI 概念映射：SFB 库函数（CODESYS 解析器（解析 CODESYS 变量表））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

Codesys 格式解析器

V2.3 Week2 T10：解析 Codesys（.csv/.txt）PLC 变量表。
V2.3 Week3 T12：深化为真实字段提取 + 新增 detect_format 方法。

参考 SW-2026-001 src/parser/codesys_parser.py 结构但重新实现：
- SW-2026-001 用 csv.DictReader + 列名 'Name'/'Type'/'Address'/'Comment'/'Scope'
- 本实现同样用 csv.DictReader，但返回 ParseResult 而非 List[Dict]

文件特征：
- 扩展名：.csv / .txt
- 内容：CSV 格式，含英文列名 'Name' 'Type' 'Address' 'Comment' 'Scope'
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

from auto_pm.vartable.models import ParseError, ParseResult, VarEntry, VarTable

if TYPE_CHECKING:
    from auto_pm.domain.vartable.parsers.base_parser import BaseParser
else:
    from auto_pm.vartable.parsers.base_parser import BaseParser

SOURCE_FORMAT = "codesys"

# Codesys CSV 列名变体
_NAME_KEYS = ("Name", "name", "变量名")
_TYPE_KEYS = ("Type", "type", "数据类型")
_ADDRESS_KEYS = ("Address", "address", "地址")
_COMMENT_KEYS = ("Comment", "comment", "注释")
_SCOPE_KEYS = ("Scope", "scope", "作用域")


def _pick(row: dict[str, str], keys: tuple[str, ...]) -> str:
    """从 row 中按候选 key 顺序取首个非空值"""
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


class CodesysParser(BaseParser):
    """Codesys 格式解析器

    用法：
        parser = CodesysParser()
        result = parser.parse("path/to/file.csv")
        if result.success and result.var_table is not None:
            for entry in result.var_table.entries:
                print(entry.tag, entry.address)
    """

    def detect_format(self, file_path: str | Path) -> bool:
        """检测文件是否为 Codesys 格式

        Args:
            file_path: 待检测文件路径

        Returns:
            True 表示是 Codesys 格式（内容含英文列名 Name+Type）
        """
        from auto_pm.vartable.models import FormatType
        from auto_pm.vartable.parsers.format_detector import detect_format

        return bool(detect_format(file_path) == FormatType.CODESYS)

    def parse(self, file_path: str | Path) -> ParseResult:
        """解析 Codesys 格式变量表

        Args:
            file_path: .csv/.txt 文件路径

        Returns:
            ParseResult：成功时 var_table 含 VarEntry 列表

        容错策略：
        - 文件不存在/读取失败 → success=False
        - CSV 表头为空 → success=False
        - 单行数据错误 → success=True（部分成功），errors 含失败行
        """
        read_result = self._read_file(file_path)
        if isinstance(read_result, ParseResult):
            return read_result
        content, encoding = read_result

        if not content.strip():
            return cast(ParseResult, self._empty_content_error(file_path, SOURCE_FORMAT))

        entries: list[VarEntry] = []
        errors: list[ParseError] = []
        warnings: list[str] = []

        reader = csv.DictReader(io.StringIO(content))
        fieldnames = reader.fieldnames or []
        if not fieldnames:
            return ParseResult(
                success=False,
                var_table=None,
                errors=(
                    ParseError(
                        line_number=1,
                        field="header",
                        message="CSV 表头为空",
                        raw_value="",
                    ),
                ),
            )

        for line_num, row in enumerate(reader, start=2):
            if not any(str(v).strip() for v in row.values() if v is not None):
                continue

            name = _pick(row, _NAME_KEYS)
            data_type = _pick(row, _TYPE_KEYS)
            address = _pick(row, _ADDRESS_KEYS)
            comment = _pick(row, _COMMENT_KEYS)
            scope = _pick(row, _SCOPE_KEYS)

            if not name:
                errors.append(
                    ParseError(
                        line_number=line_num,
                        field="name",
                        message="Name 字段为空",
                        raw_value=str(row),
                    )
                )
                continue

            entries.append(
                VarEntry(
                    station=scope or "codesys",
                    signal_type=data_type or "VAR",
                    address=address,
                    tag=name,
                    signal_name=name,
                    device="",
                    comment=comment,
                    source_format=SOURCE_FORMAT,
                    line_number=line_num,
                )
            )

        var_table = VarTable(
            entries=tuple(entries),
            source_path=str(Path(file_path).resolve()),
            source_format=SOURCE_FORMAT,
            parsed_at=datetime.now(UTC).isoformat(),
            encoding=encoding,
            metadata={"total_rows_read": len(entries) + len(errors)},
        )

        success = len(entries) > 0 or len(errors) == 0
        if errors and entries:
            warnings.append(f"解析完成但有 {len(errors)} 个错误，已跳过对应行")

        return ParseResult(
            success=success,
            var_table=var_table,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )
