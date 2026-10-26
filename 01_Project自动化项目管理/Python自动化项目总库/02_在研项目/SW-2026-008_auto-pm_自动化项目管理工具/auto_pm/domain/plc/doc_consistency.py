"""PLC 文档与代码一致性核对与自动补全（需求说明 REQ-SW008-M2-DOCSYNC，任务 V01B）。

核对每个接口变量的名称、数据类型、方向与注释（不核对通信协议）：

- FB/FC 的接口变量（VAR_INPUT/VAR_OUTPUT/VAR_IN_OUT）对照该功能块自己的 ``PRD/接口文档_IFC-*.md``；
- DB、OB、结构体（TYPE … STRUCT）对照项目级 ``PLC变量定义文档_VAR.md`` 中以对象名为标题的变量表。

``analyze_project`` 与 ``confirm_project`` 之外的 ``sync_project`` 只会写文档，从不写 SCL。整份文档缺失只给警告，
变量逐项对不上给失败并指出位置；自动补全只补缺的行，补入的行在说明列前带 ``【待确认】``。
"""

from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

MARKER = "【待确认】"
ARCHIVE_HINT = "已不存在"
ARCHIVE_HEADING = f"## 附：代码中{ARCHIVE_HINT}的旧条目（待确认后删除）"
VAR_DOC_NAME = "PLC变量定义文档_VAR.md"
IFC_GLOB_PREFIX = "接口文档_IFC-"
FB_DIRECTIONS = ("VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT")
_KIND_BY_KEYWORD = {
    "FUNCTION_BLOCK": "FB",
    "FUNCTION": "FC",
    "ORGANIZATION_BLOCK": "OB",
    "DATA_BLOCK": "DB",
    "TYPE": "UDT",
}
_KIND_LABEL = {"FB": "功能块", "FC": "函数", "OB": "组织块", "DB": "数据块", "UDT": "结构体"}
_SECTIONS_BY_KIND = {
    "FB": ("VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT"),
    "FC": ("VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT"),
    "OB": ("VAR_TEMP", "VAR"),
    "DB": ("VAR",),
    "UDT": ("STRUCT",),
}
_SKIP_DIRS = {"node_modules", "__pycache__", "archive", "_archive", "Test", "99_基线", "工程资产"}

_HEADER = re.compile(
    r"^\s*(FUNCTION_BLOCK|FUNCTION|ORGANIZATION_BLOCK|DATA_BLOCK|TYPE)\s+\"?([A-Za-z_]\w*)\"?", re.I
)
_END_OBJECT = re.compile(r"^\s*END_(?:FUNCTION_BLOCK|FUNCTION|ORGANIZATION_BLOCK|DATA_BLOCK|TYPE)\b", re.I)
_SECTION = re.compile(r"^\s*(VAR_INPUT|VAR_OUTPUT|VAR_IN_OUT|VAR_TEMP|VAR_STAT|VAR\s+CONSTANT|VAR)\b", re.I)
_END_SECTION = re.compile(r"^\s*(END_VAR|END_STRUCT)\b", re.I)
_STRUCT_OPEN = re.compile(r"^\s*(?:([A-Za-z_]\w*)\s*:\s*)?STRUCT\s*(?://.*)?$", re.I)
_DECL = re.compile(r"^\s*([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*:\s*(.*?)\s*;\s*(.*)$")
_TRAILING_BLOCK_COMMENT = re.compile(r";\s*\(\*(.*?)\*\)\s*$")
_BLOCK_COMMENT = re.compile(r"\(\*.*?\*\)", re.S)
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
_DIRECTION_WORD = re.compile(r"VAR_IN_OUT|VAR_INPUT|VAR_OUTPUT")
_NAME_COLUMNS = {"名称", "参数名", "变量名", "字段名", "名称/变量", "变量", "信号名", "参数"}
_TYPE_COLUMNS = {"类型", "数据类型"}
_DESC_COLUMNS = {"说明", "描述", "功能描述", "含义", "注释"}
_DIR_COLUMNS = {"方向"}
_DIRECTION_ALIASES = {
    "VAR_INPUT": "VAR_INPUT", "INPUT": "VAR_INPUT", "IN": "VAR_INPUT", "输入": "VAR_INPUT",
    "VAR_OUTPUT": "VAR_OUTPUT", "OUTPUT": "VAR_OUTPUT", "OUT": "VAR_OUTPUT", "输出": "VAR_OUTPUT",
    "VAR_IN_OUT": "VAR_IN_OUT", "IN_OUT": "VAR_IN_OUT", "INOUT": "VAR_IN_OUT", "输入输出": "VAR_IN_OUT",
    "双向": "VAR_IN_OUT",
}


@dataclass(frozen=True)
class CodeVar:
    """One declared interface variable (or struct/DB field) of a code object."""

    name: str
    type: str
    comment: str
    direction: str
    line: int


@dataclass(frozen=True)
class CodeObject:
    """One FB/FC/OB/DB/UDT found in an SCL or DB source file."""

    kind: str
    name: str
    path: str
    variables: tuple[CodeVar, ...]
    unparsed: tuple[tuple[int, str], ...] = ()


@dataclass(frozen=True)
class DocRow:
    """One parsed row of a variable table in a document."""

    name: str
    type: str
    description: str
    direction: str
    line: int
    marked: bool


@dataclass(frozen=True)
class DocTable:
    """One variable table of a document, with the position data ``sync`` needs."""

    heading: str
    heading_line: int
    direction_hint: str
    archive: bool
    header_line: int
    last_line: int
    columns: tuple[str, ...]
    name_col: int
    type_col: int
    desc_col: int
    dir_col: int
    rows: tuple[DocRow, ...]


@dataclass(frozen=True)
class DocHeading:
    level: int
    text: str
    line: int


@dataclass(frozen=True)
class Finding:
    """One consistency finding with the exact place to look at."""

    obj: str
    kind: str
    severity: str
    variable: str
    message: str
    code_loc: str = ""
    doc_loc: str = ""

    def render(self) -> str:
        where = "；".join(part for part in (f"代码 {self.code_loc}" if self.code_loc else "",
                                             f"文档 {self.doc_loc}" if self.doc_loc else "") if part)
        who = f"{self.obj}.{self.variable}" if self.variable else self.obj
        return f"{who}：{self.message}" + (f"（{where}）" if where else "")


@dataclass
class ObjectReport:
    obj: CodeObject
    doc_path: str | None
    doc_state: str  # "ok" | "missing" | "unparsable"
    findings: list[Finding] = field(default_factory=list)
    marked: list[tuple[str, DocRow]] = field(default_factory=list)
    shared_doc: bool = False  # one document holds the headed sections of several function blocks

    @property
    def status(self) -> str:
        if any(item.severity == "fail" for item in self.findings):
            return "fail"
        return "warn" if self.findings else "pass"


@dataclass
class ProjectAnalysis:
    project_path: str
    reports: list[ObjectReport]
    var_doc_path: str
    var_doc_exists: bool

    @property
    def findings(self) -> list[Finding]:
        return [item for report in self.reports for item in report.findings]

    @property
    def marked_rows(self) -> list[tuple[str, DocRow]]:
        return [item for report in self.reports for item in report.marked]


# --------------------------------------------------------------------------------------
# normalisation
# --------------------------------------------------------------------------------------


def normalize_type(text: str) -> str:
    """Canonical form so ``BOOL[1..4]`` equals ``ARRAY[1..4] OF BOOL`` and quoting/case/spacing are ignored."""

    value = unicodedata.normalize("NFKC", text).replace('"', "").strip().upper()
    value = re.sub(r"\s+", "", value)
    array = re.fullmatch(r"([A-Z_][A-Z_0-9.]*)\[([^\]]+)\]", value)
    if array and array.group(1) not in {"STRING", "WSTRING"}:
        return f"ARRAY[{array.group(2)}]OF{array.group(1)}"
    return value


def normalize_description(text: str) -> str:
    value = unicodedata.normalize("NFKC", text.replace(MARKER, ""))
    return re.sub(r"\s+", " ", value).strip()


def _clean_cell(text: str) -> str:
    return text.replace("`", "").replace("**", "").strip()


def _direction_from(text: str) -> str:
    return _DIRECTION_ALIASES.get(unicodedata.normalize("NFKC", text).replace(" ", "").upper(), "")


# --------------------------------------------------------------------------------------
# SCL / DB source parsing
# --------------------------------------------------------------------------------------


def _prepare_lines(text: str) -> list[str]:
    lines = [_TRAILING_BLOCK_COMMENT.sub(lambda m: "; // " + m.group(1).strip(), x) for x in text.splitlines()]
    joined = _BLOCK_COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), "\n".join(lines))
    return joined.split("\n")


@dataclass
class _ObjectBuilder:
    kind: str
    name: str
    variables: list[CodeVar] = field(default_factory=list)
    unparsed: list[tuple[int, str]] = field(default_factory=list)


def parse_scl_text(text: str, path: str) -> list[CodeObject]:
    """Parse FB/FC/OB/DB/UDT declarations; only single-line declarations are understood."""

    objects: list[CodeObject] = []
    current: _ObjectBuilder | None = None
    section = ""
    prefix: list[str] = []
    for number, line in enumerate(_prepare_lines(text), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        if current is None:
            header = _HEADER.match(line)
            if header:
                current = _ObjectBuilder(_KIND_BY_KEYWORD[header.group(1).upper()], header.group(2))
                section = ""
                prefix = []
            continue
        kind = current.kind
        if _END_OBJECT.match(line):
            objects.append(CodeObject(kind, current.name, path, tuple(current.variables), tuple(current.unparsed)))
            current, section, prefix = None, "", []
            continue
        if _END_SECTION.match(line):
            if prefix:
                prefix.pop()
            else:
                section = ""
            continue
        opener = _STRUCT_OPEN.match(line)
        if opener:
            if section:
                prefix.append(opener.group(1) or "")
            elif kind == "UDT":
                section = "STRUCT"
            continue
        start = _SECTION.match(line)
        if start and not section:
            word = re.sub(r"\s+", " ", start.group(1).upper())
            section = word if word in _SECTIONS_BY_KIND[kind] else f"IGNORED:{word}"
            continue
        if not section or section.startswith("IGNORED:"):
            continue
        declaration = _DECL.match(line)
        if not declaration:
            current.unparsed.append((number, stripped[:80]))
            continue
        comment = declaration.group(3).strip()
        comment = comment[2:].strip() if comment.startswith("//") else ""
        type_text = declaration.group(2).split(":=")[0].strip()
        direction = section if section in FB_DIRECTIONS else ""
        for raw_name in declaration.group(1).split(","):
            name = ".".join([*prefix, raw_name.strip()])
            current.variables.append(CodeVar(name, type_text, comment, direction, number))
    return objects


def parse_scl_file(path: Path) -> list[CodeObject]:
    if path.suffix.lower() == ".db":
        try:
            with path.open("rb") as stream:
                head = stream.read(4096)
            if path.stat().st_size > 2_000_000 or b"\0" in head or b"DATA_BLOCK" not in head.upper():
                return []
        except OSError:
            return []
    try:
        return parse_scl_text(path.read_text(encoding="utf-8", errors="replace"), str(path))
    except OSError:
        return []


# --------------------------------------------------------------------------------------
# document parsing
# --------------------------------------------------------------------------------------


def _split_cells(line: str) -> list[str]:
    body = line.strip()
    body = body[1:] if body.startswith("|") else body
    body = body[:-1] if body.endswith("|") else body
    return [cell.strip() for cell in body.split("|")]


def _is_separator(line: str) -> bool:
    return line.lstrip().startswith("|") and re.fullmatch(r"[\s|:\-]+", line.strip()) is not None


def parse_doc_lines(lines: Sequence[str]) -> tuple[list[DocHeading], list[DocTable]]:
    """Parse headings and variable tables (tables with a name column and a type column)."""

    headings: list[DocHeading] = []
    tables: list[DocTable] = []
    stack: list[DocHeading] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        match = _HEADING.match(line)
        if match:
            heading = DocHeading(len(match.group(1)), match.group(2), index + 1)
            headings.append(heading)
            stack = [x for x in stack if x.level < heading.level] + [heading]
            index += 1
            continue
        if line.lstrip().startswith("|") and index + 1 < len(lines) and _is_separator(lines[index + 1]):
            header_cells = [_clean_cell(cell) for cell in _split_cells(line)]
            end = index + 2
            while end < len(lines) and lines[end].lstrip().startswith("|"):
                end += 1
            name_col = next((i for i, c in enumerate(header_cells) if c in _NAME_COLUMNS), -1)
            type_col = next((i for i, c in enumerate(header_cells) if c in _TYPE_COLUMNS), -1)
            if name_col >= 0 and type_col >= 0:
                desc_col = next((i for i, c in enumerate(header_cells) if c in _DESC_COLUMNS), -1)
                dir_col = next((i for i, c in enumerate(header_cells) if c in _DIR_COLUMNS), -1)
                hint = ""
                for item in reversed(stack):
                    found = _DIRECTION_WORD.search(item.text)
                    if found:
                        hint = found.group(0)
                        break
                archive = any(ARCHIVE_HINT in item.text for item in stack)
                rows: list[DocRow] = []
                for row_index in range(index + 2, end):
                    cells = _split_cells(lines[row_index])
                    if len(cells) <= max(name_col, type_col):
                        continue
                    name = re.split(r"[\s（(\[]", _clean_cell(cells[name_col]))[0]
                    if not name:
                        continue
                    description = cells[desc_col] if 0 <= desc_col < len(cells) else ""
                    direction = _direction_from(_clean_cell(cells[dir_col])) if 0 <= dir_col < len(cells) else ""
                    rows.append(DocRow(name, _clean_cell(cells[type_col]), description.strip(), direction,
                                       row_index + 1, description.strip().startswith(MARKER)))
                top = stack[-1] if stack else DocHeading(0, "", 0)
                tables.append(DocTable(top.text, top.line, hint, archive, index + 1, end, tuple(header_cells),
                                       name_col, type_col, desc_col, dir_col, tuple(rows)))
            index = end
            continue
        index += 1
    return headings, tables


def _read_lines(path: str) -> list[str]:
    return Path(path).read_text(encoding="utf-8", errors="replace").splitlines()


# --------------------------------------------------------------------------------------
# project discovery and comparison
# --------------------------------------------------------------------------------------


def _walk_sources(project_path: str) -> list[Path]:
    found: list[Path] = []
    for directory, names, files in os.walk(project_path):
        names[:] = sorted(n for n in names if not n.startswith(".") and n not in _SKIP_DIRS)
        for file_name in sorted(files):
            if file_name.lower().endswith((".scl", ".db")):
                found.append(Path(directory) / file_name)
    return found


def find_var_doc(project_path: str) -> str:
    for directory, names, files in os.walk(project_path):
        names[:] = sorted(n for n in names if not n.startswith(".") and n not in _SKIP_DIRS)
        if VAR_DOC_NAME in files:
            return str(Path(directory) / VAR_DOC_NAME)
    plc_root = Path(project_path) / "02_PLC程序"
    base = plc_root if plc_root.is_dir() else Path(project_path)
    return str(base / "程序文档" / VAR_DOC_NAME)


def _rel(path: str, project_path: str) -> str:
    try:
        return Path(path).resolve().relative_to(Path(project_path).resolve()).as_posix()
    except ValueError:
        return path


def _squash(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", unicodedata.normalize("NFKC", text).lower())


def _affinity(name: str, doc: Path) -> int:
    """How well an interface document's file name (``接口文档_IFC-FB1001-DualInfeed``) names a function block."""

    fb = _squash(name)
    stem = _squash(doc.stem.removeprefix(IFC_GLOB_PREFIX))
    for left, right, weight in ((fb, stem, 3), (re.sub(r"^f[bc]\d*", "", fb), re.sub(r"^f[bc]\d*", "", stem), 2)):
        if not left or not right:
            continue
        if left == right:
            return weight * 10_000 + len(left)
        if left.startswith(right) or right.startswith(left):
            return weight * 1_000 + min(len(left), len(right))
    return 0


def _doc_owner(doc: Path, sibling_names: Sequence[str]) -> str | None:
    """The one function block of a module that a document is named after (``None`` when unclear)."""

    scored = sorted(((_affinity(name, doc), name) for name in sibling_names), reverse=True)
    if not scored or scored[0][0] == 0 or (len(scored) > 1 and scored[1][0] == scored[0][0]):
        return None
    return scored[0][1]


def _resolve_interface_doc(
    item: CodeObject, sibling_names: Sequence[str], docs: Sequence[Path]
) -> tuple[Path, list[DocTable], bool] | None:
    """The interface document, its variable tables and whether it is shared, for one FB/FC of a module."""

    if len(sibling_names) == 1:
        chosen: Path | None = sorted(docs, key=lambda d: -_affinity(item.name, d))[0]
    else:
        chosen = next((d for d in docs if _doc_owner(d, sibling_names) == item.name), None)
    for doc in [chosen] if chosen is not None else docs:
        tables = parse_doc_lines(_read_lines(str(doc)))[1]
        shared = len(sibling_names) > 1 and any(n in t.heading for t in tables for n in sibling_names)
        if shared:
            tables = [t for t in tables if item.name in t.heading]
        if chosen is not None or (shared and tables):
            return doc, tables, shared
    return None


def _compare(
    obj: CodeObject, tables: Iterable[DocTable], doc_path: str, project_path: str
) -> tuple[list[Finding], list[tuple[str, DocRow]]]:
    findings: list[Finding] = []
    marked: list[tuple[str, DocRow]] = []
    is_fb = obj.kind in {"FB", "FC"}
    rows: list[tuple[DocRow, str]] = []
    for table in tables:
        if table.archive:
            continue
        for row in table.rows:
            rows.append((row, row.direction or table.direction_hint))
            if row.marked:
                marked.append((doc_path, row))
    seen: dict[str, DocRow] = {}
    for row, _direction in rows:
        if row.name in seen:
            findings.append(Finding(obj.name, "doc_duplicate", "fail", row.name, "文档里重复出现",
                                    doc_loc=f"{_rel(doc_path, project_path)}:{row.line}"))
        seen.setdefault(row.name, row)
    direction_of = {row.name: direction for row, direction in rows}
    code_names = set()
    for variable in obj.variables:
        code_names.add(variable.name)
        code_loc = f"{_rel(obj.path, project_path)}:{variable.line}"
        if not variable.comment:
            findings.append(Finding(obj.name, "no_comment", "fail", variable.name,
                                    "代码里没有写注释", code_loc=code_loc))
        doc_row = seen.get(variable.name)
        if doc_row is None:
            findings.append(Finding(obj.name, "code_not_in_doc", "fail", variable.name,
                                    "代码里有、文档里没写", code_loc=code_loc))
            continue
        doc_loc = f"{_rel(doc_path, project_path)}:{doc_row.line}"
        if normalize_type(variable.type) != normalize_type(doc_row.type):
            findings.append(Finding(obj.name, "type", "fail", variable.name,
                                    f"类型不同：代码 {variable.type}，文档 {doc_row.type}", code_loc, doc_loc))
        if is_fb:
            doc_direction = direction_of.get(variable.name, "")
            if not doc_direction:
                findings.append(Finding(obj.name, "direction", "fail", variable.name,
                                        "文档里无法确定方向（小节标题或“方向”列）", code_loc, doc_loc))
            elif doc_direction != variable.direction:
                findings.append(Finding(obj.name, "direction", "fail", variable.name,
                                        f"方向不同：代码 {variable.direction}，文档 {doc_direction}", code_loc, doc_loc))
        if variable.comment and normalize_description(variable.comment) != normalize_description(doc_row.description):
            findings.append(Finding(obj.name, "comment", "fail", variable.name,
                                    f"说明与代码注释不同：代码“{variable.comment}”，文档“{normalize_description(doc_row.description)}”",
                                    code_loc, doc_loc))
    for row, _direction in rows:
        if row.name not in code_names:
            findings.append(Finding(obj.name, "doc_not_in_code", "fail", row.name,
                                    "文档里有、代码里没有（已删除或改名）",
                                    doc_loc=f"{_rel(doc_path, project_path)}:{row.line}"))
    return findings, marked


def analyze_project(project_path: str) -> ProjectAnalysis:
    """Read-only: parse the sources and documents of one PLC project and compare them."""

    project_path = os.path.abspath(project_path)
    objects: list[CodeObject] = []
    for source in _walk_sources(project_path):
        objects.extend(parse_scl_file(source))
    objects = [item for item in objects if item.variables or item.unparsed]
    var_doc = find_var_doc(project_path)
    var_exists = os.path.isfile(var_doc)
    var_tables: list[DocTable] = []
    var_headings: list[DocHeading] = []
    if var_exists:
        var_headings, var_tables = parse_doc_lines(_read_lines(var_doc))
    modules: dict[str, list[CodeObject]] = {}
    for item in objects:
        if item.kind in {"FB", "FC"}:
            modules.setdefault(str(Path(item.path).parent), []).append(item)
    reports: list[ObjectReport] = []
    for item in objects:
        report = ObjectReport(item, None, "ok")
        for number, text in item.unparsed:
            report.findings.append(Finding(item.name, "unparsed", "warn", "", f"无法解析的声明：{text}",
                                           code_loc=f"{_rel(item.path, project_path)}:{number}"))
        if not item.variables:
            reports.append(report)
            continue
        if item.kind in {"FB", "FC"}:
            module = str(Path(item.path).parent)
            docs = sorted((Path(module) / "PRD").glob(f"{IFC_GLOB_PREFIX}*.md")) if (Path(module) / "PRD").is_dir() else []
            resolved = _resolve_interface_doc(item, [o.name for o in modules[module]], docs) if docs else None
            if resolved is None:
                report.doc_state = "missing"
                report.findings.append(Finding(item.name, "missing_doc", "warn", "",
                                               f"缺少接口文档（期望 {_rel(module, project_path)}/PRD/{IFC_GLOB_PREFIX}*.md）"))
            else:
                doc, tables, report.shared_doc = resolved
                doc_path = str(doc)
                report.doc_path = doc_path
                if not tables:
                    report.doc_state = "unparsable"
                    report.findings.append(Finding(item.name, "unparsable_doc", "warn", "",
                                                   "接口文档里没有可识别的变量表（需要含“名称”和“类型”列的表格）",
                                                   doc_loc=_rel(doc_path, project_path)))
                else:
                    found, marked = _compare(item, tables, doc_path, project_path)
                    report.findings.extend(found)
                    report.marked.extend(marked)
        else:
            if not var_exists:
                report.doc_state = "missing"
                report.findings.append(Finding(item.name, "missing_doc", "warn", "",
                                               f"缺少变量定义文档（期望 {_rel(var_doc, project_path)}）"))
            else:
                own = [h for h in var_headings if re.split(r"[\s（(]", h.text)[0] == item.name]
                tables = [t for t in var_tables if any(t.heading_line == h.line for h in own)]
                report.doc_path = var_doc
                if not tables:
                    report.doc_state = "missing"
                    report.findings.append(Finding(item.name, "missing_doc", "warn", "",
                                                   f"变量定义文档里没有“{item.name}”的变量表",
                                                   doc_loc=_rel(var_doc, project_path)))
                else:
                    found, marked = _compare(item, tables, var_doc, project_path)
                    report.findings.extend(found)
                    report.marked.extend(marked)
        reports.append(report)
    return ProjectAnalysis(project_path, reports, var_doc, var_exists)


REQUIRED_VAR_DOC_ITEM = "变量定义文档存在性"


def required_document_items(analysis: ProjectAnalysis) -> list[tuple[str, str, str]]:
    """The documents a project must have at all; their absence fails the check (TD-SW008-129, user ruling B7).

    ``consistency_items`` keeps a missing document per object as a warning, so a draft can be made with
    ``plc docs sync``. A project with data blocks, structures or organization blocks whose variable definition file
    is gone has nothing to compare them with at all: that is a failure, not a skipped check.
    """

    needing = [
        report.obj.name
        for report in analysis.reports
        if report.obj.kind not in {"FB", "FC"} and report.obj.variables
    ]
    if analysis.var_doc_exists or not needing:
        return []
    shown = "、".join(needing[:3]) + ("等" if len(needing) > 3 else "")
    return [
        (
            REQUIRED_VAR_DOC_ITEM,
            "fail",
            f"缺少变量定义文档（期望 {_rel(analysis.var_doc_path, analysis.project_path)}），"
            f"{len(needing)} 个数据块/结构体/组织块（{shown}）无处核对；运行 plc docs sync 生成草稿，审核后运行 plc docs confirm",
        )
    ]


def consistency_items(
    project_path: str, *, analysis: ProjectAnalysis | None = None
) -> list[tuple[str, str, str]]:
    """(item, status, message) triples for ``PlcChecker``; empty when the project has nothing to document."""

    analysis = analysis or analyze_project(project_path)
    items: list[tuple[str, str, str]] = []
    for report in analysis.reports:
        if not report.obj.variables and not report.findings:
            continue
        label = f"文档一致性 [{_KIND_LABEL[report.obj.kind]} {report.obj.name}]"
        if not report.findings:
            items.append((label, "pass", f"{len(report.obj.variables)} 个变量与文档一致"))
            continue
        counts: dict[str, int] = {}
        for finding in report.findings:
            counts[finding.kind] = counts.get(finding.kind, 0) + 1
        names = {"missing_doc": "缺文档", "unparsable_doc": "文档无法解析", "code_not_in_doc": "代码有文档无",
                 "doc_not_in_code": "文档有代码无", "type": "类型不同", "direction": "方向不同",
                 "comment": "注释不同", "no_comment": "代码无注释", "doc_duplicate": "文档重复",
                 "unparsed": "声明无法解析"}
        summary = "、".join(f"{names[k]} {v}" for k, v in sorted(counts.items()))
        examples = "；".join(x.render() for x in report.findings[:2])
        items.append((label, report.status,
                      f"{summary}（如：{examples}）；运行 plc docs check 查看全部，plc docs sync 自动补全"))
    marked = analysis.marked_rows
    if marked:
        items.append(("文档待确认标记", "warn", f"{len(marked)} 行带{MARKER}标记，审完后运行 plc docs confirm"))
    return items


# --------------------------------------------------------------------------------------
# sync (code -> document draft) and confirm
# --------------------------------------------------------------------------------------


def _row_text(columns: Sequence[str], values: dict[int, str]) -> str:
    cells = [values.get(i, "—") for i in range(len(columns))]
    return "| " + " | ".join(cells) + " |"


def _canonical_table(direction: str | None) -> list[str]:
    head = ["名称", "类型", "说明"]
    return ["| " + " | ".join(head) + " |", "|" + "|".join(["---"] * len(head)) + "|"]


@dataclass
class _Buffer:
    path: str
    lines: list[str]
    created: bool
    original: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return self.created or tuple(self.lines) != self.original


def _object_tables(obj: CodeObject, headings: Sequence[DocHeading], tables: Sequence[DocTable],
                   multi_in_module: bool) -> list[DocTable]:
    """The variable tables of one object: its own headed sections, or every table of a one-FB module doc."""

    if obj.kind in {"FB", "FC"}:
        return [t for t in tables if not multi_in_module or obj.name in t.heading]
    own = [h for h in headings if re.split(r"[\s（(]", h.text)[0] == obj.name]
    return [t for t in tables if any(t.heading_line == h.line for h in own)]


@dataclass
class SyncResult:
    written: list[str] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    added_rows: int = 0
    suggestions: list[str] = field(default_factory=list)
    applied: int = 0


def _target_table(tables: Sequence[DocTable], direction: str) -> DocTable | None:
    candidates = [t for t in tables if not t.archive and (not direction or t.direction_hint == direction
                                                           or any(r.direction == direction for r in t.rows))]
    return candidates[-1] if candidates else None


def _insert_row(buffer: _Buffer, tables: Sequence[DocTable], variable: CodeVar, direction: str,
                new_section_title: str, headings: Sequence[DocHeading]) -> None:
    description = MARKER + variable.comment
    table = _target_table(tables, direction)
    if table is not None:
        values = {table.name_col: variable.name, table.type_col: variable.type}
        if table.desc_col >= 0:
            values[table.desc_col] = description
        if table.dir_col >= 0:
            values[table.dir_col] = direction or "—"
        buffer.lines.insert(table.last_line, _row_text(table.columns, values))
        return
    owner = next((h for h in headings if h.text == new_section_title or re.split(r"[\s（(]", h.text)[0] == new_section_title), None)
    block = [*_canonical_table(direction), f"| {variable.name} | {variable.type} | {description} |"]
    if owner is not None:
        buffer.lines[owner.line:owner.line] = ["", *block, ""]
        return
    if buffer.lines and buffer.lines[-1].strip():
        buffer.lines.append("")
    buffer.lines.extend([new_section_title if new_section_title.startswith("#") else f"### {new_section_title}", "", *block])


def sync_project(project_path: str, *, write: bool = True, apply_suggestions: bool = False) -> SyncResult:
    """Complete the documents from the code. Never touches SCL; never overwrites human text unless asked."""

    analysis = analyze_project(project_path)
    result = SyncResult()
    buffers: dict[str, _Buffer] = {}

    def buffer_for(path: str, skeleton: Sequence[str]) -> _Buffer:
        if path not in buffers:
            exists = os.path.isfile(path)
            lines = _read_lines(path) if exists else list(skeleton)
            buffers[path] = _Buffer(path, lines, not exists, tuple(lines))
        return buffers[path]

    var_skeleton = ["# PLC变量定义文档", "",
                    f"> 本文件的变量表由 `plc docs sync` 按代码补全；标注“{MARKER}”的行需人工审核后运行 `plc docs confirm`。", "",
                    "## 变量表", ""]
    for report in analysis.reports:
        obj = report.obj
        if not obj.variables:
            continue
        if obj.kind in {"FB", "FC"}:
            module = Path(obj.path).parent
            doc_path = report.doc_path or str(module / "PRD" / f"{IFC_GLOB_PREFIX}{obj.name}.md")
            skeleton = [f"# 接口文档 {obj.name}", "",
                        f"> 本文件的变量表由 `plc docs sync` 按代码补全；标注“{MARKER}”的行需人工审核后运行 `plc docs confirm`。", ""]
        else:
            doc_path = analysis.var_doc_path
            skeleton = var_skeleton
        buffer = buffer_for(doc_path, skeleton)
        for variable in obj.variables:
            headings, tables = parse_doc_lines(buffer.lines)
            mine = _object_tables(obj, headings, tables, report.shared_doc)
            if variable.name in {row.name for table in mine if not table.archive for row in table.rows}:
                continue
            direction = variable.direction
            title = f"## {direction}" if obj.kind in {"FB", "FC"} else f"### {obj.name}（{_KIND_LABEL[obj.kind]}）"
            _insert_row(buffer, mine, variable, direction, title, headings)
            result.added_rows += 1
        if apply_suggestions and report.doc_state == "ok":
            _apply_suggestions(buffer, obj, report.shared_doc, result)
    for finding in analysis.findings:
        if finding.kind in {"type", "direction", "comment", "doc_not_in_code", "no_comment", "doc_duplicate"}:
            result.suggestions.append(finding.render())
    if write:
        for path, buffer in buffers.items():
            if not buffer.changed:
                continue
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as stream:
                stream.write("\n".join(buffer.lines).rstrip("\n") + "\n")
            (result.created if buffer.created else result.written).append(path)
    return result


def _apply_suggestions(buffer: _Buffer, obj: CodeObject, shared_doc: bool, result: SyncResult) -> None:
    """Explicit mode: rewrite differing rows from the code and move stale rows to the archive section."""

    headings, tables = parse_doc_lines(buffer.lines)
    mine = [t for t in _object_tables(obj, headings, tables, shared_doc) if not t.archive]
    code = {v.name: v for v in obj.variables}
    moves: list[tuple[DocRow, str]] = []
    edits: list[tuple[int, str]] = []
    reinsert: list[CodeVar] = []
    for table in mine:
        for row in table.rows:
            variable = code.get(row.name)
            if variable is None:
                moves.append((row, obj.name))
                continue
            direction = row.direction or table.direction_hint
            if obj.kind in {"FB", "FC"} and direction and direction != variable.direction:
                moves.append((row, obj.name))
                has_correct_row = any(
                    other is not row and other.name == row.name
                    and (other.direction or other_table.direction_hint) == variable.direction
                    for other_table in mine for other in other_table.rows
                )
                if not has_correct_row and variable not in reinsert:
                    reinsert.append(variable)
                continue
            if (normalize_type(row.type) != normalize_type(variable.type)
                    or (variable.comment and normalize_description(row.description) != normalize_description(variable.comment))):
                cells = _split_cells(buffer.lines[row.line - 1])
                cells[table.type_col] = variable.type
                if table.desc_col >= 0:
                    kept = variable.comment or normalize_description(row.description)
                    cells[table.desc_col] = MARKER + kept
                edits.append((row.line - 1, "| " + " | ".join(cells) + " |"))
    for index, text in edits:
        buffer.lines[index] = text
        result.applied += 1
    for row, _owner in sorted(moves, key=lambda item: -item[0].line):
        del buffer.lines[row.line - 1]
        result.applied += 1
    if moves:
        if ARCHIVE_HEADING not in buffer.lines:
            if buffer.lines and buffer.lines[-1].strip():
                buffer.lines.append("")
            buffer.lines.extend([ARCHIVE_HEADING, "", "| 名称 | 类型 | 说明 | 原对象 |", "|---|---|---|---|"])
        for row, owner in sorted(moves, key=lambda item: item[0].line):
            buffer.lines.append(f"| {row.name} | {row.type} | {MARKER}{normalize_description(row.description)} | {owner} |")
    for variable in reinsert:
        headings, tables = parse_doc_lines(buffer.lines)
        mine = [t for t in _object_tables(obj, headings, tables, shared_doc) if not t.archive]
        _insert_row(buffer, mine, variable, variable.direction, f"## {variable.direction}", headings)
        result.added_rows += 1


@dataclass
class ConfirmResult:
    confirmed: int = 0
    skipped: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)


def confirm_project(project_path: str, *, write: bool = True) -> ConfirmResult:
    """Strip the marker from rows that now equal the code; rows that still differ stay marked."""

    analysis = analyze_project(project_path)
    result = ConfirmResult()
    bad_keys = {(f.obj, f.variable) for f in analysis.findings if f.severity == "fail" and f.variable}
    edits: dict[str, list[int]] = {}
    for report in analysis.reports:
        for path, row in report.marked:
            if (report.obj.name, row.name) in bad_keys:
                result.skipped.append(f"{report.obj.name}.{row.name}：仍与代码不一致，未确认")
                continue
            edits.setdefault(path, []).append(row.line)
    for path, line_numbers in edits.items():
        lines = _read_lines(path)
        for number in line_numbers:
            lines[number - 1] = lines[number - 1].replace(MARKER, "", 1)
            result.confirmed += 1
        if write:
            with open(path, "w", encoding="utf-8", newline="\n") as stream:
                stream.write("\n".join(lines).rstrip("\n") + "\n")
        result.files.append(path)
    return result
