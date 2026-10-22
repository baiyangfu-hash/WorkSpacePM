"""auto_pm.infrastructure.business_change_gate - commit-msg 认业务变更记录（BC）

断网、没有 AI 时，用户本人改 PLC 程序不必每次开 CHG 变更单：提交说明写上本项目
“已批”的业务变更编号（``02_业务变更记录.md`` 里的一行）即可。CHG 只留给大事：

* 发版：碰发版指针 / 发布目录 / ``.auto-pm`` / 规范库 / 任一项目的版本变更台账，
  或提交说明写了“发版”“发布”“交付”“release”；
* 安全区：碰了项目 ``safety_zone.yml`` 圈定的安全区（规则与 PR 安全区检查
  ``reviews/tools/safety_zone_check.py`` 一致：清单文件、``@安全区`` 区段、安全变量与安全点
  三层取并集，HEAD 与暂存两边的清单也取并集）；**项目还没有安全区清单时，改任何 PLC
  程序都按碰了安全区处理**。

编号两种都认：旧的 ``BC-DJ-2026-009-004``，新的 ``BC-DJ-2026-009-2026_10_001``。
每条都必须属于本次生产代码所在的项目、在业务变更记录表里恰有一行、状态为“已批”或
“已实施”、批准人不是空或“待补”。任何一项读不到或对不上都拒绝提交（fail-closed）。
"""

from __future__ import annotations

import csv
import fnmatch
import io
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import yaml

# 旧编号三位序号；2026-10-22 起新行按提出月份编号：BC-<项目号>-<年>_<月>_<三位序号>
BC_ID_PATTERN = re.compile(
    r"(?<![\w-])BC-([A-Z]+-\d{4}-\d{3})-(?:\d{4}_(?:0[1-9]|1[0-2])_\d{3}|\d{3})(?![\w-])"
)
APPROVED_BC_STATES = ("已批", "已实施")
BC_RECORD_PATHS = (
    "04_监控/01_变更管理/02_变更记录/02_业务变更记录.md",
    "11_监控/01_变更管理/02_变更记录/02_业务变更记录.md",
)

RELEASE_KEYWORDS = re.compile(r"发版|发布|交付|\brelease\b", re.IGNORECASE)
RELEASE_PREFIXES = (
    "00_Obsidian_Base",
    "00_Infrastructure/auto_pm/releases/",
    ".auto-pm/",
)
RELEASE_FILES = (
    "00_Infrastructure/auto_pm/active_release.json",
    "00_Infrastructure/auto_pm/previous_release.json",
    "00_Infrastructure/auto_pm/deployment_manifest.json",
)
RELEASE_SUFFIXES = ("/01_变更管理/02_变更记录/01_版本变更台账.md",)

PROGRAM_DIR = "02_PLC程序"
MANIFEST_NAMES = (f"{PROGRAM_DIR}/工程资产/safety_zone.yml", "safety_zone.yml")
IO_POINTS = f"{PROGRAM_DIR}/工程资产/io_points.csv"
PLC_CODE_SUFFIXES = frozenset({".scl", ".st", ".db", ".udt", ".awl"})
MANIFEST_KEYS = frozenset(
    {"project_id", "files", "variables", "points", "signed_by", "signed_at_commit", "note"}
)
SAFETY_COLUMNS = ("安全", "safety")
SAFETY_YES = frozenset({"是", "y", "yes", "true", "1"})
REGION_START = re.compile(r"@安全区\s*开始")
REGION_END = re.compile(r"@安全区\s*结束")
_TOKEN = re.compile(r"%?[A-Za-z_一-鿿][A-Za-z0-9_一-鿿]*(?:\.[A-Za-z0-9_一-鿿]+)*")
_RANGE = re.compile(r"^([A-Za-z%]+)(\d+)\.\.([A-Za-z%]+)?(\d+)$")
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class BusinessChangeError(RuntimeError):
    """业务变更依据不成立；提示文字直接给用户看。"""


def find_bc_ids(message: str) -> tuple[str, ...]:
    """提交说明里出现的全部 BC 编号（去重保序）。"""
    return tuple(dict.fromkeys(m.group(0) for m in BC_ID_PATTERN.finditer(message)))


def bc_project_id(bc_id: str) -> str:
    match = BC_ID_PATTERN.fullmatch(bc_id)
    if match is None:
        raise BusinessChangeError(f"业务变更编号格式不对: {bc_id}")
    return match.group(1)


# ---------------------------------------------------------------- 读文件（暂存区或控制根）


@dataclass(frozen=True)
class EvidenceSource:
    """单根时读暂存区（index），双根时读控制根工作区；与 CHG 的取证口径一致。"""

    candidate_root: Path
    governance_root: Path

    @property
    def single_root(self) -> bool:
        return self.candidate_root.resolve() == self.governance_root.resolve()

    def read(self, path: str) -> str | None:
        if self.single_root:
            return _git_text(self.candidate_root, "show", f":{path}")
        target = self.governance_root / path
        if not target.is_file():
            return None
        return target.read_text(encoding="utf-8", errors="replace")


def _git_text(cwd: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def _git_text_or_raise(cwd: Path, *args: str) -> str:
    text = _git_text(cwd, *args)
    if text is None:
        raise BusinessChangeError(f"git {' '.join(args)} 执行失败")
    return text


# ---------------------------------------------------------------- BC 记录表


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator(line: str) -> bool:
    return bool(re.fullmatch(r"\|[\s\-:|]+\|", line.strip()))


def find_bc_row(record: str, bc_id: str) -> dict[str, str]:
    """在业务变更记录表里找恰好一行编号等于 ``bc_id`` 的记录，按表头返回各栏。"""
    rows: list[dict[str, str]] = []
    header: list[str] | None = None
    for line in record.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            header = None
            continue
        if _is_separator(stripped):
            continue
        cells = _cells(stripped)
        if header is None:
            header = cells
            continue
        if "编号" not in header or "状态" not in header:
            continue
        row = dict(zip(header, cells, strict=False))
        if row.get("编号", "").strip("`* ") == bc_id:
            rows.append(row)
    if not rows:
        raise BusinessChangeError(f"业务变更记录表里没有这一条: {bc_id}")
    if len(rows) > 1:
        raise BusinessChangeError(f"业务变更记录表里 {bc_id} 出现了 {len(rows)} 行，编号重复")
    return rows[0]


def check_bc_approved(row: dict[str, str], bc_id: str) -> None:
    status = row.get("状态", "").strip("`* ")
    if not status.startswith(APPROVED_BC_STATES):
        raise BusinessChangeError(
            f"{bc_id} 的状态是“{status or '空'}”，要先改成“已批”（写上批准人和批准日期）才能提交"
        )
    if "批准人" in row:
        approver = row["批准人"].strip("`* ")
        if not approver or approver.startswith("待补"):
            raise BusinessChangeError(f"{bc_id} 没写批准人，不能当作已批")


def bc_record_text(source: EvidenceSource, project_root: str) -> str:
    texts = [
        text
        for rel in BC_RECORD_PATHS
        if (text := source.read(f"{project_root}/{rel}")) is not None
    ]
    if not texts:
        raise BusinessChangeError(
            f"项目没有业务变更记录表（{BC_RECORD_PATHS[1]}），不能用 BC 代替 CHG"
        )
    if len(texts) > 1:
        raise BusinessChangeError("项目有两份业务变更记录表（04_监控 与 11_监控），先合成一份")
    return texts[0]


# ---------------------------------------------------------------- 发版


def release_reasons(staged_paths: tuple[str, ...], message: str) -> list[str]:
    reasons = [
        f"碰了发版/治理文件 {path}"
        for path in staged_paths
        if path.startswith(RELEASE_PREFIXES)
        or path in RELEASE_FILES
        or path.endswith(RELEASE_SUFFIXES)
    ]
    keyword = RELEASE_KEYWORDS.search(message)
    if keyword:
        reasons.append(f"提交说明写了“{keyword.group(0)}”")
    return reasons


# ---------------------------------------------------------------- 安全区


@dataclass
class SafetyZone:
    marked: bool = False
    files: list[str] = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _expand(entry: str) -> list[str]:
    """``X140..X147`` 展开成单个点；三菱 X/Y 按八进制，其余按十进制。"""
    match = _RANGE.match(entry.strip())
    if not match:
        return [entry.strip()]
    prefix, start, prefix2, end = match.groups()
    if prefix2 and prefix2.upper() != prefix.upper():
        return [entry.strip()]
    base = 8 if prefix.upper().lstrip("%") in {"X", "Y"} else 10
    first, last = int(start, base), int(end, base)
    if last < first or last - first > 256:
        return [entry.strip()]
    fmt = (lambda n: format(n, "o")) if base == 8 else str
    return [f"{prefix}{fmt(n).zfill(len(start))}" for n in range(first, last + 1)]


def _str_list(raw: object, key: str, zone: SafetyZone) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(x, (str, int)) for x in raw):
        zone.errors.append(f"安全区清单 `{key}` 必须是字符串列表")
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def _load_zone(read: Callable[[str], str | None], project_root: str) -> SafetyZone:
    zone = SafetyZone()
    for name in MANIFEST_NAMES:
        text = read(f"{project_root}/{name}")
        if text is None:
            continue
        zone.marked = True
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            zone.errors.append(f"安全区清单不是合法 YAML: {exc}")
            data = None
        if data is not None and not isinstance(data, dict):
            zone.errors.append("安全区清单顶层必须是映射")
            data = None
        data = data or {}
        unknown = sorted(set(data) - MANIFEST_KEYS)
        if unknown:
            zone.errors.append(f"安全区清单有不认识的键: {', '.join(unknown)}")
        zone.files += _str_list(data.get("files"), "files", zone)
        zone.names += [v.lower() for v in _str_list(data.get("variables"), "variables", zone)]
        for entry in _str_list(data.get("points"), "points", zone):
            zone.names += [n.lower() for n in _expand(entry)]
        break
    csv_text = read(f"{project_root}/{IO_POINTS}")
    if csv_text:
        reader = csv.DictReader(io.StringIO(csv_text.lstrip("﻿")))
        column = next(
            (c for c in (reader.fieldnames or []) if c and c.strip().lower() in SAFETY_COLUMNS),
            None,
        )
        if column:
            for row in reader:
                if (row.get(column) or "").strip().lower() in SAFETY_YES:
                    for key in ("tag", "address"):
                        value = (row.get(key) or "").strip()
                        if value:
                            zone.names.append(value.lstrip("%").lower())
    return zone


def _tokens(line: str) -> set[str]:
    out: set[str] = set()
    for raw in _TOKEN.findall(line):
        word = raw.lstrip("%").lower()
        out.add(word)
        out.update(word.split("."))
    return out


def _regions(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start: int | None = None
    lines = text.splitlines()
    for number, line in enumerate(lines, start=1):
        if REGION_START.search(line):
            if start is not None:
                spans.append((start, number))
            start = number
        elif REGION_END.search(line):
            spans.append((start if start is not None else 1, number))
            start = None
    if start is not None:
        spans.append((start, len(lines)))
    return spans


def _inside(number: int, spans: list[tuple[int, int]]) -> bool:
    return any(a <= number <= b for a, b in spans)


def _changed_lines(cwd: Path, path: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """（删掉的行：HEAD 行号+内容，新增的行：暂存行号+内容）。"""
    diff = _git_text_or_raise(
        cwd, "diff", "--cached", "-U0", "--no-color", "--no-ext-diff", "--no-renames", "--", path
    )
    removed: list[tuple[int, str]] = []
    added: list[tuple[int, str]] = []
    old_no = new_no = 0
    for line in diff.splitlines():
        hunk = _HUNK.match(line)
        if hunk:
            old_no, new_no = int(hunk.group(1)), int(hunk.group(3))
            continue
        if line.startswith(("+++", "---")):
            continue
        if line.startswith("-"):
            removed.append((old_no, line[1:]))
            old_no += 1
        elif line.startswith("+"):
            added.append((new_no, line[1:]))
            new_no += 1
    return removed, added


def safety_reasons(
    candidate_root: Path,
    project_root: str,
    staged_paths: tuple[str, ...],
) -> list[str]:
    """本次暂存改动碰到安全区的理由；空列表表示没碰。"""

    def read_index(path: str) -> str | None:
        return _git_text(candidate_root, "show", f":{path}")

    def read_head(path: str) -> str | None:
        return _git_text(candidate_root, "show", f"HEAD:{path}")

    in_project = [p for p in staged_paths if p.startswith(f"{project_root}/")]
    reasons: list[str] = []
    for path in in_project:
        rel = path[len(project_root) + 1 :]
        if rel in MANIFEST_NAMES or rel == IO_POINTS:
            reasons.append(f"改了安全区清单或 IO 点表 {path}")

    index_zone, head_zone = _load_zone(read_index, project_root), _load_zone(read_head, project_root)
    errors = index_zone.errors + head_zone.errors
    if errors:
        reasons += [f"安全区清单有问题（{e}），按碰了安全区处理" for e in errors]
    code = [p for p in in_project if PurePosixPath(p).suffix.lower() in PLC_CODE_SUFFIXES]
    if not code:
        return reasons
    if not (index_zone.marked or head_zone.marked):
        reasons.append(
            "项目还没有安全区清单（02_PLC程序/工程资产/safety_zone.yml），"
            f"改 PLC 程序一律按安全区处理: {code[0]}"
        )
        return reasons

    files = index_zone.files + head_zone.files
    names = index_zone.names + head_zone.names
    for path in code:
        rel = path[len(project_root) + 1 :]
        if any(fnmatch.fnmatchcase(rel, pattern) for pattern in files):
            reasons.append(f"{path} 整个文件在安全区清单 files 里")
            continue
        removed, added = _changed_lines(candidate_root, path)
        new_spans = _regions(read_index(path) or "")
        old_spans = _regions(read_head(path) or "")
        hit = next(
            (
                f"第 {n} 行在 @安全区 区段里"
                for spans, lines in ((old_spans, removed), (new_spans, added))
                for n, text in lines
                if _inside(n, spans) or REGION_START.search(text) or REGION_END.search(text)
            ),
            None,
        )
        if hit is None:
            hit = next(
                (
                    f"第 {n} 行引用了安全变量 {name}"
                    for n, text in removed + added
                    for name in names
                    if any(fnmatch.fnmatchcase(w, name) for w in _tokens(text))
                ),
                None,
            )
        if hit is not None:
            reasons.append(f"{path} {hit}")
    return reasons


# ---------------------------------------------------------------- 总入口


def validate_business_change_basis(
    candidate_root: Path,
    governance_root: Path,
    project_id: str,
    project_root: str,
    staged_paths: tuple[str, ...],
    message: str,
    bc_ids: tuple[str, ...],
) -> None:
    """BC 代替 CHG 的全部条件；不成立时抛 ``BusinessChangeError``，说明要怎么改。"""
    release = release_reasons(staged_paths, message)
    if release:
        raise BusinessChangeError("这是发版类提交，必须带 CHG 变更单: " + "；".join(release))
    for bc_id in bc_ids:
        owner = bc_project_id(bc_id)
        if owner != project_id:
            raise BusinessChangeError(
                f"{bc_id} 属于项目 {owner}，本次改的是项目 {project_id} 的程序"
            )
    record = bc_record_text(EvidenceSource(candidate_root, governance_root), project_root)
    for bc_id in bc_ids:
        check_bc_approved(find_bc_row(record, bc_id), bc_id)
    safety = safety_reasons(candidate_root, project_root, staged_paths)
    if safety:
        raise BusinessChangeError(
            "改动碰了安全区，必须带 CHG 变更单（并按安全签字规矩走 PR）: " + "；".join(safety[:5])
        )
