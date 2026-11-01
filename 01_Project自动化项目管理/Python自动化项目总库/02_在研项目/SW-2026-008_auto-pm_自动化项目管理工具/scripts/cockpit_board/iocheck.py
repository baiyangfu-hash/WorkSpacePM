"""IO / 变量表查重（不依赖 Qt，只读）：对 `vartable parse <文件> --output-format json` 的输出找重复。

规矩（电气上的常识）：
- 同一个地址出现两次，是两个信号占了一个点（接线或点表抄错）；
- 同一个变量名出现两次，程序里引用会串；
- 地址比较时去掉前面的 % 和空格、不分大小写（%I0.0、I0.0、i0.0 算同一个）；变量名只去掉两头空格，不分大小写；
- 不同站（station）里的同名同址不算重复——两台 PLC 各有各的 I0.0；
- 地址或变量名是空的，单独数出来，不算重复。

这里只对解析结果做统计，不读文件、不写文件、不碰账本；解析本身由命令行 vartable parse 做。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


class IoCheckError(ValueError):
    """解析输出认不出；文字直接给人看。"""


@dataclass(frozen=True)
class Duplicate:
    key: str  # 重复的地址（规范化后）或变量名（原样）
    station: str
    lines: tuple[int, ...]  # 在源文件里的行号（解析器没给就是 0）
    names: tuple[str, ...]  # 这几行各自的另一栏（查地址重复时是变量名，反之是地址）


@dataclass(frozen=True)
class IoReport:
    total: int
    duplicate_addresses: tuple[Duplicate, ...]
    duplicate_names: tuple[Duplicate, ...]
    missing_address: int
    missing_name: int

    @property
    def clean(self) -> bool:
        return not self.duplicate_addresses and not self.duplicate_names

    def summary(self) -> str:
        parts = [f"共 {self.total} 条", f"重复地址 {len(self.duplicate_addresses)} 组", f"重复变量名 {len(self.duplicate_names)} 组"]
        if self.missing_address:
            parts.append(f"{self.missing_address} 条没写地址")
        if self.missing_name:
            parts.append(f"{self.missing_name} 条没写变量名")
        return "，".join(parts)


def normalize_address(address: str) -> str:
    return "".join(str(address).split()).lstrip("%").upper()


def _name_of(entry: dict[str, Any]) -> str:
    return str(entry.get("tag") or entry.get("signal_name") or "").strip()


def extract_entries(output: str) -> list[dict[str, Any]]:
    """从命令输出里取 var_table.entries。输出前面若混了日志行，从第一个 { 开始读。"""
    start = output.find("{")
    if start < 0:
        raise IoCheckError("命令没有输出 JSON，没法查重（看上面的命令输出）")
    try:
        document, _end = json.JSONDecoder().raw_decode(output[start:])
    except ValueError as error:
        raise IoCheckError(f"命令输出不是合法 JSON：{error}") from error
    if not isinstance(document, dict):
        raise IoCheckError("命令输出不是预期的 JSON 对象，没法查重")
    if document.get("success") is False:
        reasons = [str(e.get("message", "")) for e in document.get("errors") or [] if isinstance(e, dict)][:3]
        raise IoCheckError("vartable parse 报告解析没成功，没法查重" + ("：" + "；".join(r for r in reasons if r) if reasons else ""))
    table = document.get("var_table")
    if not isinstance(table, dict) or not isinstance(table.get("entries"), list):
        raise IoCheckError("这个文件解析出来不是变量 / IO 表（没有 var_table.entries），不查重")
    return [e for e in table["entries"] if isinstance(e, dict)]


def find_duplicates(entries: list[dict[str, Any]]) -> IoReport:
    by_address: dict[tuple[str, str], list[dict[str, Any]]] = {}
    by_name: dict[tuple[str, str], list[dict[str, Any]]] = {}
    missing_address = missing_name = 0
    for entry in entries:
        station = str(entry.get("station") or "")
        address, name = normalize_address(entry.get("address") or ""), _name_of(entry)
        if address:
            by_address.setdefault((station, address), []).append(entry)
        else:
            missing_address += 1
        if name:
            by_name.setdefault((station, name.casefold()), []).append(entry)
        else:
            missing_name += 1
    return IoReport(
        len(entries),
        _groups(by_address, lambda e: _name_of(e) or "（没写变量名）", lambda e: normalize_address(e.get("address") or "")),
        _groups(by_name, lambda e: str(e.get("address") or "（没写地址）"), _name_of),
        missing_address,
        missing_name,
    )


def _groups(
    groups: dict[tuple[str, str], list[dict[str, Any]]],
    other: Callable[[dict[str, Any]], str],
    shown_key: Callable[[dict[str, Any]], str],
) -> tuple[Duplicate, ...]:
    found = []
    for (station, _key), items in groups.items():
        if len(items) > 1:
            found.append(Duplicate(
                shown_key(items[0]), station,
                tuple(int(i.get("line_number") or 0) for i in items), tuple(str(other(i)) for i in items),
            ))
    return tuple(sorted(found, key=lambda d: (d.station, d.key)))


def render_report(report: IoReport) -> str:
    """给人看的纯文本报告；没有重复也明说，不留空白。"""
    lines = [report.summary()]
    for title, items, unit in (("重复地址", report.duplicate_addresses, "变量名"), ("重复变量名", report.duplicate_names, "地址")):
        if not items:
            lines.append(f"{title}：无")
            continue
        lines.append(f"{title}：")
        for dup in items:
            where = "、".join(f"第 {n} 行" if n else "行号未知" for n in dup.lines)
            station = f"[{dup.station}] " if dup.station else ""
            lines.append(f"  {station}{dup.key}  出现在 {where}（{unit}：{'、'.join(dup.names)}）")
    return "\n".join(lines)
