"""IO 点表 CSV 读取与查重"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

REQUIRED_COLUMNS: tuple[str, ...] = ("变量名", "地址", "注释")
_ENCODINGS: tuple[str, ...] = ("utf-8-sig", "gb18030")


class IoTableError(ValueError):
    """IO 点表读取失败，消息为中文。"""


@dataclass(frozen=True)
class IoPoint:
    """IO 点表中的一行；line_number 为文件内物理行号（从 1 起）。"""

    variable_name: str
    address: str
    comment: str
    line_number: int


def read_io_table(path: str | Path) -> list[IoPoint]:
    """读取 IO 点表 CSV，按文件原始顺序返回全部数据行（不去重）。

    表头取首个非空行，必须包含 变量名、地址、注释 三列（顺序无关，多余列忽略）；
    空行跳过，单元格去首尾空白。任何读取或格式问题抛 IoTableError。
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise IoTableError(f"IO 点表文件不存在: {file_path}")

    text = _decode(file_path)
    points: list[IoPoint] = []
    columns: dict[str, int] | None = None
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        if not any(cell.strip() for cell in row):
            continue
        if columns is None:
            columns = _column_indexes([cell.strip() for cell in row], file_path)
            continue
        points.append(
            IoPoint(
                variable_name=_cell(row, columns["变量名"]),
                address=_cell(row, columns["地址"]),
                comment=_cell(row, columns["注释"]),
                line_number=reader.line_num,
            )
        )
    if columns is None:
        raise IoTableError(f"IO 点表为空: {file_path}")
    return points


def _decode(file_path: Path) -> str:
    raw = file_path.read_bytes()
    for encoding in _ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise IoTableError(f"IO 点表编码无法识别（已尝试 UTF-8 与 GB18030）: {file_path}")


def _column_indexes(header: list[str], file_path: Path) -> dict[str, int]:
    indexes = {name: header.index(name) for name in REQUIRED_COLUMNS if name in header}
    missing = [name for name in REQUIRED_COLUMNS if name not in indexes]
    if missing:
        shown = ", ".join(header) if header else "空"
        raise IoTableError(
            f"IO 点表缺少必需列: {', '.join(missing)}（实际表头: {shown}）: {file_path}"
        )
    return indexes


def _cell(row: list[str], index: int) -> str:
    return row[index].strip() if index < len(row) else ""


@dataclass(frozen=True)
class Duplicate:
    """一组重复：归一化后的键与出现的物理行号（升序）。"""

    key: str
    line_numbers: tuple[int, ...]


@dataclass(frozen=True)
class DuplicateReport:
    """IO 点表查重结果；两项都为空表示没有重复。"""

    addresses: tuple[Duplicate, ...]
    variable_names: tuple[Duplicate, ...]

    @property
    def has_duplicates(self) -> bool:
        return bool(self.addresses or self.variable_names)


def find_duplicates(points: list[IoPoint]) -> DuplicateReport:
    """找出重复的地址与重复的变量名。

    地址去掉空白后按大写比较（%i0.0 与 %I0.0 视为同一地址）；变量名按西门子变量表的习惯
    不区分大小写比较，报告里写首次出现时的原样。空地址、空变量名不参与查重。
    结果按首次出现的行号排序。
    """
    return DuplicateReport(
        addresses=_group(
            points,
            lambda point: "".join(point.address.split()).upper(),
            lambda point: "".join(point.address.split()).upper(),
        ),
        variable_names=_group(
            points, lambda point: point.variable_name.casefold(), lambda point: point.variable_name
        ),
    )


def format_duplicate_report(report: DuplicateReport) -> str:
    """把查重结果写成给人看的中文报告。"""
    if not report.has_duplicates:
        return "未发现重复的地址或变量名。"
    lines: list[str] = []
    for title, groups in (("重复地址", report.addresses), ("重复变量名", report.variable_names)):
        if not groups:
            continue
        lines.append(f"{title}（{len(groups)} 组）:")
        lines.extend(
            f"  {group.key}: 第 {', '.join(str(n) for n in group.line_numbers)} 行"
            for group in groups
        )
    return "\n".join(lines)


def _group(
    points: list[IoPoint],
    key_of: Callable[[IoPoint], str],
    shown_as: Callable[[IoPoint], str],
) -> tuple[Duplicate, ...]:
    seen: dict[str, list[int]] = {}
    shown: dict[str, str] = {}
    for point in points:
        key = key_of(point)
        if key:
            seen.setdefault(key, []).append(point.line_number)
            shown.setdefault(key, shown_as(point))
    return tuple(
        Duplicate(shown[key], tuple(sorted(lines)))
        for key, lines in sorted(seen.items(), key=lambda item: min(item[1]))
        if len(lines) > 1
    )
