"""PLC-HMI 概念映射：SFB 库函数（WORK3 解析器（解析三菱 WORK3 变量表））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

Work3 格式解析器

V2.3 Week2 T10：解析 Work3（.wr3）PLC 变量表。
V2.3 Week3 T12：深化为真实字段提取 + 新增 detect_format 方法。

参考 SW-2026-001 src/parser/work3_parser.py 结构但重新实现：
- SW-2026-001 跳过前 2 行 + tab 分隔 + 8 字段（scope/name/type/.../address/description）
- 本实现同样跳过前 2 行 + tab 分隔，但返回 ParseResult 而非 List[Dict]

文件特征：
- 扩展名：.wr3
- 内容：前 2 行表头 + tab 分隔的变量行
- 字段顺序：scope / name / data_type / ... / address / description
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from auto_pm.vartable.models import ParseError, ParseResult, VarEntry, VarTable
from auto_pm.vartable.parsers.base_parser import BaseParser

SOURCE_FORMAT = "work3"

# Work3 tab 分隔字段最少列数（与 SW-2026-001 对齐）
_MIN_FIELDS = 8
# 字段索引（基于 SW-2026-001 实现：scope=0/name=1/type=2/address=6/desc=7）
_SCOPE_IDX = 0
_NAME_IDX = 1
_TYPE_IDX = 2
_ADDRESS_IDX = 6
_DESC_IDX = 7


class Work3Parser(BaseParser):
    """Work3 格式解析器

    用法：
        parser = Work3Parser()
        result = parser.parse("path/to/file.wr3")
        if result.success and result.var_table is not None:
            for entry in result.var_table.entries:
                print(entry.tag, entry.address)
    """

    def detect_format(self, file_path: str | Path) -> bool:
        """检测文件是否为 Work3 格式

        Args:
            file_path: 待检测文件路径

        Returns:
            True 表示是 Work3 格式（.wr3 扩展名或 tab 分隔特征）
        """
        from auto_pm.vartable.models import FormatType
        from auto_pm.vartable.parsers.format_detector import detect_format

        return bool(detect_format(file_path) == FormatType.WORK3)

    def parse(self, file_path: str | Path) -> ParseResult:
        """解析 Work3 格式变量表

        Args:
            file_path: .wr3 文件路径

        Returns:
            ParseResult：成功时 var_table 含 VarEntry 列表

        容错策略：
        - 文件不存在/读取失败 → success=False
        - 文件不足 2 行表头 → success=False
        - 单行字段不足 8 列 → success=True（部分成功），errors 含失败行
        """
        read_result = self._read_file(file_path)
        if isinstance(read_result, ParseResult):
            return read_result
        content, encoding = read_result

        lines = content.splitlines()
        if len(lines) < 2:
            return ParseResult(
                success=False,
                var_table=None,
                errors=(
                    ParseError(
                        line_number=1,
                        field="header",
                        message="Work3 文件至少需要 2 行表头",
                        raw_value=f"lines={len(lines)}",
                    ),
                ),
            )

        entries: list[VarEntry] = []
        errors: list[ParseError] = []
        warnings: list[str] = []

        # 跳过前 2 行表头，从第 3 行开始解析（行号从 3 开始）
        for line_num, line in enumerate(lines[2:], start=3):
            stripped = line.strip()
            if not stripped:
                continue

            fields = stripped.split("\t")
            if len(fields) < _MIN_FIELDS:
                errors.append(
                    ParseError(
                        line_number=line_num,
                        field="columns",
                        message=f"字段数不足 {len(fields)}/{_MIN_FIELDS}",
                        raw_value=stripped,
                    )
                )
                continue

            scope = fields[_SCOPE_IDX].strip().strip('"')
            name = fields[_NAME_IDX].strip().strip('"')
            data_type = fields[_TYPE_IDX].strip().strip('"')
            # W1-S03 修复：address 同样需要 strip('"')，真实样例空字段值为 ""（两个引号字符）
            address = fields[_ADDRESS_IDX].strip().strip('"')
            description = fields[_DESC_IDX].strip().strip('"')

            if not name:
                errors.append(
                    ParseError(
                        line_number=line_num,
                        field="name",
                        message="变量名为空",
                        raw_value=stripped,
                    )
                )
                continue

            entries.append(
                VarEntry(
                    station=scope or "work3",
                    signal_type=data_type or "VAR",
                    address=address,
                    tag=name,
                    signal_name=name,
                    device="",
                    comment=description,
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
