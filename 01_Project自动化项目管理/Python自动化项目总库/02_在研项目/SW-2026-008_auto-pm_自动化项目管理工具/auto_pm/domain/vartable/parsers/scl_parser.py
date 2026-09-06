"""PLC-HMI 概念映射：SFB 库函数（SCL 解析器（解析 SCL 源文件中的变量声明））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

SCL 格式解析器

V2.3 Week2 T10：解析 Siemens SCL（.scl/.awl）源文件中的变量声明。
V2.3 Week3 T12：深化为真实字段提取 + 新增 detect_format 方法。

参考 SW-2026-001 src/parser/scl_parser.py 结构但重新实现：
- SW-2026-001 用正则提取 FUNCTION_BLOCK + VAR_INPUT/VAR_OUTPUT/VAR 块
- 本实现同样用正则提取 VAR 块变量声明，但返回 ParseResult 而非 List[Dict]

文件特征：
- 扩展名：.scl / .awl
- 内容：SCL 源码，含 FUNCTION_BLOCK / VAR_INPUT / VAR_OUTPUT / VAR / END_VAR 等块

实现说明：识别 VAR 块 + 提取顶层变量名/类型/注释；复杂类型（FB_/ST_ 字段展开）
留待 V2.3 Week4+（当前提取顶层声明已满足变量表导出需求）。
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.vartable.models import ParseResult, VarEntry, VarTable
from auto_pm.vartable.parsers.base_parser import BaseParser

SOURCE_FORMAT = "scl"

# VAR 块类型 → scope 标签
_SCOPE_MAP = {
    "VAR_INPUT": "VAR_INPUT",
    "VAR_OUTPUT": "VAR_OUTPUT",
    "VAR_IN_OUT": "VAR_IN_OUT",
    "VAR": "VAR",
    "VAR_TEMP": "VAR_TEMP",
    "VAR_CONSTANT": "VAR_CONSTANT",
}

# VAR 块开始/结束标记
_VAR_BLOCK_RE = re.compile(
    r"^\s*(VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT|VAR_TEMP|VAR_CONSTANT|VAR)\b",
    re.IGNORECASE,
)
_END_VAR_RE = re.compile(r"^\s*END_VAR\b", re.IGNORECASE)

# 单行变量声明：name[:type] : type := default ; (* comment *) // comment
# 简化匹配：name : type
_VAR_DECL_RE = re.compile(
    r"^\s*"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)"
    r"\s*:\s*"
    r"(?P<type>[A-Za-z_][A-Za-z0-9_]*)"
    r"\b"
)

# FB 名称（用于 station 元数据）
_FB_NAME_RE = re.compile(
    r"^\s*(?:FUNCTION_BLOCK|PROGRAM|ORGANIZATION_BLOCK)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)


class SclParser(BaseParser):  # type: ignore[misc]  # CHG-SCPT-2026-021: 稳定版 verbatim 回收，基类经命名空间 shim 解析为 Any
    """SCL 格式解析器

    用法：
        parser = SclParser()
        result = parser.parse("path/to/file.scl")
        if result.success and result.var_table is not None:
            for entry in result.var_table.entries:
                print(entry.tag, entry.signal_type, entry.station)
    """

    def detect_format(self, file_path: str | Path) -> bool:
        """检测文件是否为 SCL 格式

        Args:
            file_path: 待检测文件路径

        Returns:
            True 表示是 SCL 格式（.scl/.awl 扩展名或内容含 FUNCTION_BLOCK/VAR 关键字）
        """
        from auto_pm.vartable.models import FormatType
        from auto_pm.vartable.parsers.format_detector import detect_format

        return bool(detect_format(file_path) == FormatType.SCL)

    def parse(self, file_path: str | Path) -> ParseResult:
        """解析 SCL 源文件变量声明

        Args:
            file_path: .scl/.awl 文件路径

        Returns:
            ParseResult：成功时 var_table 含 VarEntry 列表

        容错策略：
        - 文件不存在/读取失败 → success=False
        - 文件无 VAR 块 → success=True（var_table.entries 为空，warnings 提示）
        - 单行声明无法识别 → 跳过（不计入 errors，仅记录 warnings）
        """
        read_result = self._read_file(file_path)
        if isinstance(read_result, ParseResult):
            return read_result
        content, encoding = read_result

        if not content.strip():
            return self._empty_content_error(file_path, SOURCE_FORMAT)

        # 提取 FB 名称（用于 station 元数据）
        fb_name = ""
        for line in content.splitlines():
            match = _FB_NAME_RE.match(line)
            if match:
                fb_name = match.group("name")
                break

        entries: list[VarEntry] = []
        warnings: list[str] = []
        var_block_count = 0

        # 状态机：扫描 VAR 块
        current_scope = ""
        in_var_block = False

        for line_num, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue

            if not in_var_block:
                match = _VAR_BLOCK_RE.match(line)
                if match:
                    scope_key = match.group(1).upper()
                    current_scope = _SCOPE_MAP.get(scope_key, scope_key)
                    in_var_block = True
                    var_block_count += 1
                continue

            # 在 VAR 块内
            if _END_VAR_RE.match(line):
                in_var_block = False
                continue

            # 尝试匹配变量声明
            decl_match = _VAR_DECL_RE.match(line)
            if decl_match:
                name = decl_match.group("name")
                var_type = decl_match.group("type")
                # 提取行尾注释（// 或 (* *)）
                comment = self._extract_comment(line)

                entries.append(
                    VarEntry(
                        station=current_scope or fb_name or "scl",
                        signal_type=var_type,
                        address="",
                        tag=name,
                        signal_name=name,
                        device=fb_name,
                        comment=comment,
                        source_format=SOURCE_FORMAT,
                        line_number=line_num,
                    )
                )

        if var_block_count == 0:
            warnings.append("未识别到 VAR 块（VAR_INPUT/VAR_OUTPUT/VAR）")

        var_table = VarTable(
            entries=tuple(entries),
            source_path=str(Path(file_path).resolve()),
            source_format=SOURCE_FORMAT,
            parsed_at=datetime.now(UTC).isoformat(),
            encoding=encoding,
            metadata={
                "total_rows_read": len(entries),
                "fb_name": fb_name,
                "var_block_count": var_block_count,
            },
        )

        # SCL 解析默认 success=True（即使无 VAR 块也视为格式识别成功）
        return ParseResult(
            success=True,
            var_table=var_table,
            errors=(),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _extract_comment(line: str) -> str:
        """提取行尾注释

        支持：
        - // 行注释
        - (* 块注释 *) 行尾同款
        """
        # 优先匹配 // 行注释
        if "//" in line:
            idx = line.index("//")
            return line[idx + 2 :].strip()
        # 匹配 (* ... *) 行尾块注释
        match = re.search(r"\(\*(?P<comment>[^*]*)\*\)\s*$", line)
        if match:
            return match.group("comment").strip()
        return ""
