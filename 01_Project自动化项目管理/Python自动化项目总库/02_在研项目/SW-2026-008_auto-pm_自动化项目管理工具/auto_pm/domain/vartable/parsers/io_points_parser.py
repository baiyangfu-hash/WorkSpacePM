"""PLC-HMI 概念映射：SFB 库函数（IO 点位解析器（解析 IO 点位表））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。

--- 原始注释 ---

io_points.csv 解析器

V2.3 Week1 T02：在 AssetSummaryService._read_io_points 基础上深化，
提取每行的具体字段值到 VarEntry，处理 address 多格式 + comment 多值。

DJ-2026-005 真实样例字段（7 列）：
    station,signal_type,address,tag,signal_name,device,comment

address 多格式示例：
- cpu 站点: Y0/X0/X76/Y50（直接 IO 地址）
- remote_io_1 站点: RIO1:Y10/RIO1:Y11（站点前缀:地址）

comment 字段含分号分隔的多值（按原样保留，调用方按需 split）：
- "P40/EFS1/24.7; 源程序用途: 变频器1异常检测"

设计原则：
- 不复用 SW-2026-001 src/variable/variable.py 死代码（PRD §7 明确不复用）
- 复用 AssetSummaryService._IO_REQUIRED_COLUMNS 列校验逻辑
- 使用 vartable.utils.encoding 检测编码
- 容错模式：单行错误不中断整体解析，记录到 ParseResult.errors
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.vartable.models import ParseError, ParseResult, VarEntry, VarTable
from auto_pm.vartable.utils.encoding import read_file_with_detection

# io_points.csv 必须 7 列（与 AssetSummaryService._IO_REQUIRED_COLUMNS 对齐）
REQUIRED_COLUMNS: tuple[str, ...] = (
    "station",
    "signal_type",
    "address",
    "tag",
    "signal_name",
    "device",
    "comment",
)

SOURCE_FORMAT = "io_points_csv"


class IoPointsParser:
    """io_points.csv 解析器

    用法：
        parser = IoPointsParser()
        result = parser.parse("path/to/io_points.csv")
        if result.success:
            for entry in result.var_table.entries:
                print(entry.tag, entry.address)
    """

    def parse(self, file_path: str | Path) -> ParseResult:
        """解析 io_points.csv 文件

        Args:
            file_path: io_points.csv 文件路径

        Returns:
            ParseResult：成功时 var_table 含 VarEntry 列表；失败时 errors 含原因

        容错策略：
        - 文件不存在/读取失败 → success=False, var_table=None
        - 列校验失败 → success=False, var_table=None
        - 单行数据错误 → success=True（部分成功），errors 含失败行
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

        # 解析 CSV
        entries: list[VarEntry] = []
        errors: list[ParseError] = []
        warnings: list[str] = []

        reader = csv.DictReader(io.StringIO(content))
        fieldnames = reader.fieldnames or []
        missing_columns = [col for col in REQUIRED_COLUMNS if col not in fieldnames]
        if missing_columns:
            return ParseResult(
                success=False,
                var_table=None,
                errors=(
                    ParseError(
                        line_number=1,
                        field="header",
                        message=f"缺少必需列: {', '.join(missing_columns)}",
                        raw_value=",".join(fieldnames),
                    ),
                ),
            )

        # 逐行解析（行号从 2 开始，第 1 行是表头）
        for line_num, row in enumerate(reader, start=2):
            if not self._row_has_data(row):
                continue

            entry = self._parse_row(row, line_num)
            if isinstance(entry, ParseError):
                errors.append(entry)
            elif isinstance(entry, VarEntry):
                entries.append(entry)

        # 构建元数据
        station_counts: dict[str, int] = {}
        signal_type_counts: dict[str, int] = {}
        for entry in entries:
            station_counts[entry.station] = station_counts.get(entry.station, 0) + 1
            signal_type_counts[entry.signal_type] = (
                signal_type_counts.get(entry.signal_type, 0) + 1
            )

        metadata = {
            "station_counts": station_counts,
            "signal_type_counts": signal_type_counts,
            "total_rows_read": len(entries) + len(errors),
        }

        var_table = VarTable(
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
            warnings.append(f"解析完成但有 {len(errors)} 个错误，已跳过对应行")

        return ParseResult(
            success=success,
            var_table=var_table,
            errors=tuple(errors),
            warnings=tuple(warnings),
        )

    @staticmethod
    def _row_has_data(row: dict[str, str]) -> bool:
        """检查行是否有数据（全空行跳过）"""
        return any(str(value).strip() for value in row.values() if value is not None)

    @staticmethod
    def _parse_row(row: dict[str, str], line_num: int) -> VarEntry | ParseError:
        """解析单行数据

        Returns:
            VarEntry: 解析成功
            ParseError: 解析失败（字段缺失或无效）
        """
        # 提取并清理字段
        station = (row.get("station") or "").strip()
        signal_type = (row.get("signal_type") or "").strip()
        address = (row.get("address") or "").strip()
        tag = (row.get("tag") or "").strip()
        signal_name = (row.get("signal_name") or "").strip()
        device = (row.get("device") or "").strip()
        comment = (row.get("comment") or "").strip()

        # 必需字段校验（station/address/tag 不能为空）
        if not station:
            return ParseError(
                line_number=line_num,
                field="station",
                message="station 字段为空",
                raw_value=station,
            )
        if not address:
            return ParseError(
                line_number=line_num,
                field="address",
                message="address 字段为空",
                raw_value=address,
            )
        if not tag:
            return ParseError(
                line_number=line_num,
                field="tag",
                message="tag 字段为空",
                raw_value=tag,
            )

        return VarEntry(
            station=station,
            signal_type=signal_type,
            address=address,
            tag=tag,
            signal_name=signal_name,
            device=device,
            comment=comment,
            source_format=SOURCE_FORMAT,
            line_number=line_num,
        )
