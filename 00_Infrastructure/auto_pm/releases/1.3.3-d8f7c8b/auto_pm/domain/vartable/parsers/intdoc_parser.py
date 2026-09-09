"""PLC-HMI 概念映射：SFB 库函数（IntDoc 解析器（解析 TIA Portal 内部文档格式））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

INT doc 接口文档解析器

V2.3 Week2 T10：解析 Markdown 格式的 PLC 接口文档（接口文档_INT.md）。
V2.3 Week3 T12：深化为真实字段提取 + 新增 detect_format 方法。

参考 SW-2026-001 src/parser/intdoc_parser.py 结构但重新实现：
- SW-2026-001 用正则识别 ### 2.1 VAR_INPUT / ### 2.2 VAR_OUTPUT / ### 2.3 VAR 区段
- 本实现同样用正则识别 VAR 区段，但返回 ParseResult 而非 List[Dict]
- 提取顶层变量（VAR_INPUT/VAR_OUTPUT/VAR 区段）

文件特征：
- 扩展名：.doc / .docx / .txt（部分项目以 .md 命名）
- 内容：Markdown 表格格式，含 ### N.N VAR_INPUT / VAR_OUTPUT / VAR 区段标题
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.vartable.models import ParseResult, VarEntry, VarTable
from auto_pm.vartable.parsers.base_parser import BaseParser

SOURCE_FORMAT = "intdoc"

# VAR 区段标题正则：### 2.1 VAR_INPUT / ### 2.2 VAR_OUTPUT / ### 2.3 VAR
_SECTION_RE = re.compile(
    r"^#{2,4}\s*[\d.]*\s*(VAR_INPUT|VAR_OUTPUT|VAR(?:\s+CONSTANT)?)\b",
    re.IGNORECASE,
)

# Markdown 表格行：| name | type | ... | comment |
# 至少 2 列，第一列是变量名
_TABLE_ROW_RE = re.compile(r"^\s*\|(?P<cols>[^|]+(?:\|[^|]+)+)\|\s*$")

# 表格分隔行：|---|---|...|
_TABLE_SEP_RE = re.compile(r"^\s*\|[\s\-:|]+\|\s*$")


class IntDocParser(BaseParser):
    """INT doc 接口文档解析器

    用法：
        parser = IntDocParser()
        result = parser.parse("path/to/接口文档_INT.md")
        if result.success and result.var_table is not None:
            for entry in result.var_table.entries:
                print(entry.tag, entry.signal_type, entry.station)
    """

    def detect_format(self, file_path: str | Path) -> bool:
        """检测文件是否为 INT doc 接口文档格式

        Args:
            file_path: 待检测文件路径

        Returns:
            True 表示是 INT doc 格式（内容含 ### VAR_INPUT/VAR_OUTPUT 区段标题）
        """
        from auto_pm.vartable.models import FormatType
        from auto_pm.vartable.parsers.format_detector import detect_format

        return detect_format(file_path) == FormatType.INTDOC

    def parse(self, file_path: str | Path) -> ParseResult:
        """解析 Markdown 接口文档

        Args:
            file_path: .md/.doc/.docx/.txt 文件路径

        Returns:
            ParseResult：成功时 var_table 含 VarEntry 列表

        容错策略：
        - 文件不存在/读取失败 → success=False
        - 无 VAR 区段 → success=True（entries 为空，warnings 提示）
        - 单行表格无法识别 → 跳过
        """
        read_result = self._read_file(file_path)
        if isinstance(read_result, ParseResult):
            return read_result
        content, encoding = read_result

        if not content.strip():
            return self._empty_content_error(file_path, SOURCE_FORMAT)

        lines = content.splitlines()
        entries: list[VarEntry] = []
        warnings: list[str] = []
        section_count = 0

        # 状态机：扫描 VAR 区段
        current_scope = ""
        in_section = False
        in_table = False
        table_columns: list[str] = []

        for line_num, line in enumerate(lines, start=1):
            # 检测 VAR 区段标题
            section_match = _SECTION_RE.match(line)
            if section_match:
                current_scope = section_match.group(1).upper().replace(
                    " CONSTANT", ""
                )
                in_section = True
                in_table = False
                table_columns = []
                section_count += 1
                continue

            if not in_section:
                continue

            # 在 VAR 区段内
            # 检测下个同级或更高级标题（结束当前区段）
            if line.startswith("#") and not line.startswith("####"):
                in_section = False
                in_table = False
                current_scope = ""
                table_columns = []
                continue

            # 检测表格行
            row_match = _TABLE_ROW_RE.match(line)
            if not row_match:
                continue

            cols = [c.strip() for c in row_match.group("cols").split("|")]

            # 表格分隔行（---）
            if _TABLE_SEP_RE.match(line):
                in_table = True
                continue

            # 表头行（首个非分隔行）
            if not in_table:
                if not _TABLE_SEP_RE.match(line) and cols:
                    table_columns = cols
                continue

            # 表格数据行
            if not table_columns:
                continue

            entry = self._parse_table_row(cols, table_columns, current_scope, line_num)
            if isinstance(entry, VarEntry):
                entries.append(entry)

        if section_count == 0:
            warnings.append("未识别到 VAR 区段（VAR_INPUT/VAR_OUTPUT/VAR）")

        var_table = VarTable(
            entries=tuple(entries),
            source_path=str(Path(file_path).resolve()),
            source_format=SOURCE_FORMAT,
            parsed_at=datetime.now(UTC).isoformat(),
            encoding=encoding,
            metadata={
                "total_rows_read": len(entries),
                "section_count": section_count,
                "table_columns": list(table_columns),
            },
        )

        return ParseResult(
            success=True,
            var_table=var_table,
            errors=(),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _parse_table_row(
        cols: list[str],
        columns: list[str],
        scope: str,
        line_num: int,
    ) -> VarEntry | None:
        """解析 Markdown 表格行

        表头列名候选：变量名/名称/Name → name；类型/Type → type；注释/说明/Comment → comment
        """
        if len(cols) < 2:
            return None

        # 按表头列名定位字段
        name = ""
        var_type = ""
        comment = ""

        for idx, col_name in enumerate(columns):
            if idx >= len(cols):
                break
            col_lower = col_name.lower()
            value = cols[idx].strip()
            if not name and any(k in col_lower for k in ("变量名", "名称", "name")):
                name = value
            elif not var_type and any(
                k in col_lower for k in ("类型", "type", "数据类型")
            ):
                var_type = value
            elif not comment and any(
                k in col_lower for k in ("注释", "说明", "comment", "备注")
            ):
                comment = value

        # 兜底：若列名未识别，按位置取前 2 列
        if not name and cols:
            name = cols[0].strip()
        if not var_type and len(cols) >= 2:
            var_type = cols[1].strip()

        if not name:
            return None

        return VarEntry(
            station=scope,
            signal_type=var_type or "VAR",
            address="",
            tag=name,
            signal_name=name,
            device="",
            comment=comment,
            source_format=SOURCE_FORMAT,
            line_number=line_num,
        )
