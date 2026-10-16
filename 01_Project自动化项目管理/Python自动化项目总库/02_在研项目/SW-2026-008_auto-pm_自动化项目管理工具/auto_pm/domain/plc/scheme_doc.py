"""方案级接口文档与代码的一一对应检查（M3-PRDLAYOUT 第 2 张，TD-SW008-138）。

方案级 ``接口文档_INT.md`` 只写三件事（用户 2026-10-14 裁决）：FB 实例表（FB 类型名 + 实例名）、FC 调用表、跨系统交换区契约。
本模块把这三部分与代码做**存在性对照**，只给警告、从不失败，也不写任何文件：

- FB 实例表：文档里的 (FB 类型名, 实例名) 与数据块里声明的 FB 实例一一对应；
- FC 调用表：表里的 FC 在项目里有定义，代码里被调用的 FC 在表里有登记（定义了但没被调用的 FC 不算差异）；
- 交换区契约：``负责的块`` 在代码里存在；``本机侧承载的变量`` 的数据块与第一级变量在代码里存在（项目未填的占位格不检查）。

块的参数明细不在方案级，由块自己的接口文档承担（见 ``doc_consistency``）。
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from pathlib import Path

from auto_pm.core.paths import find_prd_dir
from auto_pm.plc.doc_consistency import _is_separator, _split_cells, _walk_sources, parse_scl_file

INT_DOC_NAME = "接口文档_INT.md"
SCHEME_DIR = "00_程序方案"
_IDENT = re.compile(r"^[A-Za-z_]\w*$")
_PATH = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*$")
_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"\(\*.*?\*\)", re.S)
_LIMIT = 5

ITEM_FB = "接口文档 INT ↔ 代码 [FB 实例]"
ITEM_FC = "接口文档 INT ↔ 代码 [FC 调用]"
ITEM_CONTRACT = "接口文档 INT ↔ 代码 [交换区契约]"


def find_scheme_int_doc(project_path: str) -> str | None:
    """Return the program-scheme interface document: ``00_程序方案`` first, then the PRD directory ``find_prd_dir`` finds."""

    candidates = [os.path.join(project_path, "02_PLC程序", "PLC_ST", SCHEME_DIR, INT_DOC_NAME)]
    found = find_prd_dir(project_path)
    if found is not None:
        candidates.append(os.path.join(found[0], INT_DOC_NAME))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return None


def _tables(lines: Sequence[str]) -> list[tuple[list[str], list[list[str]]]]:
    tables: list[tuple[list[str], list[list[str]]]] = []
    index = 0
    while index < len(lines) - 1:
        if lines[index].lstrip().startswith("|") and _is_separator(lines[index + 1]):
            header = _split_cells(lines[index])
            rows: list[list[str]] = []
            cursor = index + 2
            while cursor < len(lines) and lines[cursor].lstrip().startswith("|"):
                rows.append(_split_cells(lines[cursor]))
                cursor += 1
            tables.append((header, rows))
            index = cursor
        else:
            index += 1
    return tables


def _clean(cell: str) -> str:
    return cell.strip().strip("`").strip('"').strip("'").strip("`").strip()


def _column(header: Sequence[str], *needles: str) -> int:
    for position, text in enumerate(header):
        if all(needle in text for needle in needles):
            return position
    return -1


def _names(values: Sequence[str]) -> str:
    shown = sorted(values)
    text = "、".join(shown[:_LIMIT])
    return text + (f" 等 {len(shown)} 个" if len(shown) > _LIMIT else "")


def _strip_comments(text: str) -> str:
    return _LINE_COMMENT.sub("", _BLOCK_COMMENT.sub("", text))


def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def scheme_items(project_path: str) -> list[tuple[str, str, str]]:
    """``(item, status, message)`` triples for ``PlcChecker``; ``status`` is only ever ``pass`` or ``warn``; empty without the document."""

    project_path = os.path.abspath(project_path)
    doc = find_scheme_int_doc(project_path)
    if doc is None:
        return []
    tables = _tables(_read(doc).splitlines())
    objects = []
    sources: list[tuple[str, str]] = []
    for source in _walk_sources(project_path):
        objects.extend(parse_scl_file(source))
        sources.append((str(source), _strip_comments(_read(str(source)))))
    fb_names = {o.name.casefold(): o.name for o in objects if o.kind == "FB"}
    fc_names = {o.name.casefold(): o.name for o in objects if o.kind == "FC"}
    known_blocks = {o.name.casefold() for o in objects if o.kind in {"FB", "FC", "OB"}}
    db_vars: dict[str, set[str]] = {}
    for obj in objects:
        if obj.kind == "DB":
            db_vars.setdefault(obj.name.casefold(), set()).update(v.name.split(".")[0].casefold() for v in obj.variables)
    code_instances = {
        (fb_names[var.type.strip('"').casefold()], f"{obj.name}.{var.name}")
        for obj in objects
        if obj.kind == "DB"
        for var in obj.variables
        if var.type.strip('"').casefold() in fb_names
    }
    items: list[tuple[str, str, str]] = []

    # ---- FB instance table ------------------------------------------------------------------------------------------------------
    doc_instances: set[tuple[str, str]] | None = None
    doc_duplicates: list[str] = []
    doc_rows_seen: set[tuple[str, str]] = set()
    short_names: dict[str, list[str]] = {}
    for _type, full_name in code_instances:
        short_names.setdefault(full_name.rsplit(".", 1)[-1].casefold(), []).append(full_name)
    for header, rows in tables:
        type_col, inst_col = _column(header, "类型"), _column(header, "实例名")
        if type_col >= 0 and inst_col >= 0:
            doc_instances = doc_instances or set()
            for row in rows:
                if len(row) <= max(type_col, inst_col):
                    continue
                type_name, inst_name = _clean(row[type_col]), _clean(row[inst_col])
                if _IDENT.match(type_name) and _PATH.match(inst_name):
                    if "." not in inst_name and len(short_names.get(inst_name.casefold(), [])) == 1:
                        inst_name = short_names[inst_name.casefold()][0]
                    key = (type_name.casefold(), inst_name.casefold())
                    if key in doc_rows_seen:
                        doc_duplicates.append(f"{type_name} {inst_name}")
                    doc_rows_seen.add(key)
                    doc_instances.add((type_name, inst_name))
    if doc_instances is None:
        if code_instances:
            items.append((ITEM_FB, "warn", f"方案级接口文档里没有 FB 实例表（需要含“FB 类型名”和“实例名”列的表格），无法对照代码里的 {len(code_instances)} 个 FB 实例"))
    else:
        code_keys = {(t.casefold(), i.casefold()): f"{t} {i}" for t, i in code_instances}
        doc_keys = {(t.casefold(), i.casefold()): f"{t} {i}" for t, i in doc_instances}
        only_code = [code_keys[k] for k in code_keys if k not in doc_keys]
        only_doc = [doc_keys[k] for k in doc_keys if k not in code_keys]
        if only_code or only_doc or doc_duplicates:
            parts = []
            if doc_duplicates:
                parts.append(f"文档里重复：{_names(doc_duplicates)}")
            if only_code:
                parts.append(f"代码有、文档无：{_names(only_code)}")
            if only_doc:
                parts.append(f"文档有、代码无：{_names(only_doc)}")
            items.append((ITEM_FB, "warn", "；".join(parts) + "（FB 实例表需要与数据块里的 FB 实例一一对应）"))
        else:
            items.append((ITEM_FB, "pass", f"{len(doc_instances)} 个 FB 实例与代码一致"))

    # ---- FC call table ----------------------------------------------------------------------------------------------------------
    doc_fcs: set[str] | None = None
    for header, rows in tables:
        fc_col = next((p for p, text in enumerate(header) if text.strip().upper().startswith("FC") and "名" in text), -1)
        if fc_col >= 0:
            doc_fcs = doc_fcs or set()
            for row in rows:
                if len(row) > fc_col and _IDENT.match(_clean(row[fc_col])):
                    doc_fcs.add(_clean(row[fc_col]))
    called: set[str] = set()
    for _path, text in sources:
        for line in text.splitlines():
            if re.match(r"\s*FUNCTION\b", line, re.I):
                continue
            for key, name in fc_names.items():
                if key not in called and re.search(r'(?<![\w.])"?' + re.escape(name) + r'"?\s*\(', line, re.I):
                    called.add(key)
    called_names = {fc_names[k] for k in called}
    if doc_fcs is None:
        if called_names:
            items.append((ITEM_FC, "warn", f"方案级接口文档里没有 FC 调用表（需要含“FC 名”列的表格），无法对照代码里调用的 FC：{_names(sorted(called_names))}"))
    else:
        doc_fc_keys = {name.casefold(): name for name in doc_fcs}
        unknown = [doc_fc_keys[k] for k in doc_fc_keys if k not in fc_names]
        unlisted = [fc_names[k] for k in called if k not in doc_fc_keys]
        if unknown or unlisted:
            parts = []
            if unlisted:
                parts.append(f"代码调用、表里未登记：{_names(unlisted)}")
            if unknown:
                parts.append(f"表里有、项目里没有定义：{_names(unknown)}")
            items.append((ITEM_FC, "warn", "；".join(parts)))
        elif doc_fcs:
            items.append((ITEM_FC, "pass", f"{len(doc_fcs)} 个 FC 与代码一致（定义了但没被调用的 FC 不算差异）"))

    # ---- exchange-area contract -------------------------------------------------------------------------------------------------
    checked = 0
    problems: list[str] = []
    for header, rows in tables:
        block_col, var_col = _column(header, "负责的块"), _column(header, "承载的变量")
        if block_col < 0 and var_col < 0:
            continue
        for row in rows:
            if block_col >= 0 and len(row) > block_col:
                block = _clean(row[block_col])
                if _IDENT.match(block):
                    checked += 1
                    if block.casefold() not in known_blocks:
                        problems.append(f"负责的块 {block} 在代码里不存在")
            if var_col >= 0 and len(row) > var_col:
                variable = _clean(row[var_col])
                if _PATH.match(variable) and "." in variable:
                    checked += 1
                    parts_ = variable.split(".")
                    if parts_[0].casefold() not in db_vars:
                        problems.append(f"承载变量 {variable} 的数据块 {parts_[0]} 在代码里不存在")
                    elif parts_[1].casefold() not in db_vars[parts_[0].casefold()]:
                        problems.append(f"承载变量 {variable}：数据块 {parts_[0]} 里没有 {parts_[1]}")
    if problems:
        items.append((ITEM_CONTRACT, "warn", "；".join(problems[:_LIMIT]) + (f" 等 {len(problems)} 处" if len(problems) > _LIMIT else "")))
    elif checked:
        items.append((ITEM_CONTRACT, "pass", f"交换区契约里 {checked} 个已填的块与变量在代码里存在"))
    return items
