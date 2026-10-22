"""PR 安全区检查：PR 碰没碰 PLC 安全区；碰了，有没有用户本人对当前头提交的签字（GitHub Actions 的 safety-gate 调用）。

设计依据：项目文件夹 ``plans/现场回传与安全签字规则_设计稿_20261021.md`` 第 2 节；本仓库说明见 ``reviews/安全区签字检查_说明.md``。

安全区怎么认（三层取并集，任一层命中就算碰了安全区；基线与 PR 头两边的标记也取并集，PR 不能靠删标记缩小安全区）：

1. **清单 · 按文件**：项目的 ``02_PLC程序/工程资产/safety_zone.yml`` 里 ``files`` 列出的文件 / 通配；
2. **区段注释**：程序里成对的 ``@安全区 开始`` … ``@安全区 结束`` 注释圈出的行（含两行标记本身）；
3. **清单 · 按变量**：清单 ``variables``（可通配）、``points`` 和 ``io_points.csv`` 里“安全”列为“是”的点；
   改动的任何一行（新增或删掉的）引用了它们，就算碰了安全区。

另外三种情况整体算碰安全区：项目在 PR 基线上**没有安全区清单**（未标定：改任何 PLC 程序都要签字）、PR 改了清单本身、
PR 改了 ``io_points.csv`` 里涉及安全点的行。

两项硬检查（签字也放不行，检查 PR 头上改到的 PLC 程序文件）：

* **禁止式**：``OR TRUE`` / ``AND FALSE`` 这类恒真恒假旁路（任何变量）；安全点被赋常量；引用安全变量的代码被整行注释掉；
  区段标记不成对；清单格式不对。
* **完整性**：清单 ``points`` 和 ``io_points.csv`` 标“安全=是”的每个点，在该项目程序逻辑里（去掉注释和 VAR 声明段）
  至少出现一次（标签名或地址任一即可）。

计划栏④“是否涉及安全回路”（审计 69 要求的两条联锁）：

* PR 描述里单独一行 ``安全回路: 是`` / ``安全回路: 否``（GitHub 上的检查只看得到 PR 描述）。填“是”：不论改到哪些文件都要签字；
  填“否”但上面任一层认定碰了安全区：同样要签字，并在结论里点明“计划与改动不一致”。写了这一行但值不是 是/否、
  或写了多行且不一致，直接判不通过（改 PR 描述后自动重跑）。没写这一行时只按改动判定。
* 批准记录（Decision 元数据 ``execution_grant.plan_checklist.safety_circuit``）只在本机控制根的账本里，CI 读不到；
  合并前由主执行在本机加 ``--decision DEC-…`` 跑一次：批准记录为“是”而 PR 描述没写“是”，判不通过（先改 PR 描述，
  让 GitHub 上的硬锁也接上）；批准记录的值同样按上面两条判定。

签字：PR 页面上一条评论，某一行写 ``安全签字 <PR 头提交号，至少 7 位>``。只认 ``SIGNERS`` 里的账号（登录名和数字 ID
都要对上），经由 GitHub App 发出的评论不算，提交号不是当前头提交的不算（签完再推新提交，签字自动作废）。
已知漏洞：本机 agent 用用户已登录的 ``gh`` 命令行代发评论，机器分不出来——见说明文档。

本脚本不写仓库：CI 里 PR 评论和描述由工作流用 ``gh api`` 取好，以文件经 ``--comments`` / ``--pr-body-file`` 传入，
脚本本身不访问网络。只有本机的 ``--pr`` 用法会调用已登录的 ``gh`` 读 PR、并把 PR 头取到 ``refs/safety/pr-<编号>``。

用法（在仓库根执行）::

    python reviews/tools/safety_zone_check.py --base <base sha> --head <head sha> [--repo <被检查的检出>]
        [--comments <comments.json>] [--pr-body-file <body.txt>] [--status-out <status.json>]

    # 本机合并前（主执行，控制根上）：读批准记录，与 PR 描述、改动、签字一起判
    python -B reviews/tools/safety_zone_check.py --pr <PR 编号> --decision <DEC-…> [--control-root <控制根>]

退出码：0 通过（没碰安全区，或碰了且签字有效）；1 不通过；2 用法或 Git 出错。
"""

from __future__ import annotations

import argparse
import csv
import fnmatch
import io
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

TOOL_ROOT = Path(__file__).resolve().parents[2]

PLC_TOP = "0100_PLC自动化"
PROGRAM_DIR = "02_PLC程序"
MANIFEST_NAMES = (f"{PROGRAM_DIR}/工程资产/safety_zone.yml", "safety_zone.yml")
IO_POINTS = f"{PROGRAM_DIR}/工程资产/io_points.csv"
CODE_SUFFIXES = frozenset({".scl", ".st", ".db", ".udt", ".awl"})
MANIFEST_KEYS = frozenset({"project_id", "files", "variables", "points", "signed_by", "signed_at_commit", "note"})
SAFETY_COLUMNS = ("安全", "safety")
SAFETY_YES = frozenset({"是", "y", "yes", "true", "1"})
# 能签字的人：GitHub 登录名 → 数字用户 ID（ID 不随改名变化，两个都要对上）
SIGNERS = {"baiyangfu-hash": 246858089}

# 计划栏④：PR 描述里单独一行“安全回路: 是/否”（“是否涉及安全回路”也认）
PLAN_LINE = re.compile(r"^\s*(?:\*\*)?(?:④\s*)?(?:是否涉及)?安全回路(?:\*\*)?\s*[:：]\s*(.*?)\s*$")
PLAN_CHOICES = ("是", "否")
PLAN_KEY = "计划栏④（是否涉及安全回路）"
DEFAULT_REPO = "baiyangfu-hash/WorkSpacePM"
SW008_ROOT = TOOL_ROOT / "01_Project自动化项目管理" / "Python自动化项目总库" / "02_在研项目" / "SW-2026-008_auto-pm_自动化项目管理工具"
SIGN_LINE = re.compile(r"^\s*安全签字\s*[:：]?\s*`?([0-9a-fA-F]{7,40})`?(?:\s.*)?$")
REGION_START = re.compile(r"@安全区\s*开始")
REGION_END = re.compile(r"@安全区\s*结束")
TOKEN = re.compile(r"%?[A-Za-z_一-鿿][A-Za-z0-9_一-鿿]*(?:\.[A-Za-z0-9_一-鿿]+)*")
_TRUE, _FALSE = r"(?<![\w#.])(?:TRUE|1)(?![\w#.])", r"(?<![\w#.])(?:FALSE|0)(?![\w#.])"
TAUTOLOGY = re.compile(rf"\bOR\s+{_TRUE}|{_TRUE}\s+OR\b|\bAND\s+{_FALSE}|{_FALSE}\s+AND\b", re.IGNORECASE)
CONST_ASSIGN = re.compile(r"(%?[A-Za-z_][\w.]*)\s*:=\s*(?:TRUE|FALSE|0|1)\s*;", re.IGNORECASE)
DECL_BLOCK = re.compile(r"\b(VAR(?:_\w+)?|TYPE)\b.*?\bEND_(?:VAR|TYPE)\b", re.IGNORECASE | re.DOTALL)
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
RANGE = re.compile(r"^([A-Za-z%]+)(\d+)\.\.([A-Za-z%]+)?(\d+)$")


class GitError(RuntimeError):
    pass


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def show(repo: Path, rev: str, path: str) -> str | None:
    try:
        return git(repo, "show", f"{rev}:{path}")
    except GitError:
        return None


def changed_files(repo: Path, base: str, head: str) -> list[str]:
    raw = git(repo, "diff", "--name-only", "--no-renames", "-z", f"{base}...{head}")
    return sorted({item for item in raw.split("\0") if item})


# ---------------------------------------------------------------- 文件归属


def zone_root(path: str) -> str | None:
    """PLC 文件所属的“项目根”：``02_PLC程序`` 之前的部分；不在项目结构里的（如共享库）取 ``0100_PLC自动化/<第二级>``。"""

    parts = PurePosixPath(path).parts
    if len(parts) < 3 or parts[0] != PLC_TOP:
        return None
    if PROGRAM_DIR in parts:
        return "/".join(parts[: parts.index(PROGRAM_DIR)])
    return "/".join(parts[:2])


def is_code(path: str) -> bool:
    return PurePosixPath(path).suffix.lower() in CODE_SUFFIXES


def is_manifest(path: str, root: str) -> bool:
    return any(path == f"{root}/{name}" for name in MANIFEST_NAMES)


# ---------------------------------------------------------------- 安全区定义


@dataclass
class Point:
    """一个安全点：标签名、地址任一出现在程序逻辑里就算被读到。"""

    aliases: tuple[str, ...]
    source: str


@dataclass
class Zone:
    root: str
    marked: bool = False
    manifest: str | None = None
    files: list[str] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)
    points: list[Point] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def names(self) -> list[str]:
        """所有“引用即算碰安全区”的名字模式（小写）。"""

        out = [v.lower() for v in self.variables]
        out += [a.lower() for p in self.points for a in p.aliases]
        return out

    def union(self, other: Zone) -> Zone:
        merged = Zone(self.root, self.marked or other.marked, self.manifest or other.manifest)
        merged.files = sorted(set(self.files) | set(other.files))
        merged.variables = sorted(set(self.variables) | set(other.variables))
        merged.points = self.points + [p for p in other.points if p.aliases not in {q.aliases for q in self.points}]
        return merged


def expand(entry: str) -> list[str]:
    """``X140..X147`` 展开成单个点；三菱 X/Y 按八进制，其余按十进制。"""

    match = RANGE.match(entry.strip())
    if not match:
        return [entry.strip()]
    prefix, start, prefix2, end = match.groups()
    if prefix2 and prefix2.upper() != prefix.upper():
        return [entry.strip()]
    base = 8 if prefix.upper().lstrip("%") in {"X", "Y"} else 10
    first, last = int(start, base), int(end, base)
    if last < first or last - first > 256:
        return [entry.strip()]
    width = len(start)
    fmt = (lambda n: format(n, "o")) if base == 8 else str
    return [f"{prefix}{fmt(n).zfill(width)}" for n in range(first, last + 1)]


def str_list(raw: Any, key: str, errors: list[str], where: str) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(x, (str, int)) for x in raw):
        errors.append(f"{where}：`{key}` 必须是字符串列表")
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def load_zone(repo: Path, rev: str, root: str) -> Zone:
    zone = Zone(root)
    for name in MANIFEST_NAMES:
        text = show(repo, rev, f"{root}/{name}")
        if text is not None:
            zone.manifest = f"{root}/{name}"
            break
    else:
        text = None
    if text is not None:
        zone.marked = True
        where = f"安全区清单 `{zone.manifest}`（{rev[:8]}）"
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as error:
            zone.errors.append(f"{where} 不是合法 YAML：{error}")
            data = None
        if data is not None and not isinstance(data, dict):
            zone.errors.append(f"{where} 顶层必须是映射")
            data = None
        data = data or {}
        unknown = sorted(set(data) - MANIFEST_KEYS)
        if unknown:
            zone.errors.append(f"{where} 有不认识的键：{', '.join(unknown)}（拼错的键会让安全区悄悄变小，所以直接拒绝）")
        zone.files = str_list(data.get("files"), "files", zone.errors, where)
        zone.variables = str_list(data.get("variables"), "variables", zone.errors, where)
        for entry in str_list(data.get("points"), "points", zone.errors, where):
            zone.points += [Point((name,), "清单 points") for name in expand(entry)]
    csv_text = show(repo, rev, f"{root}/{IO_POINTS}")
    if csv_text:
        reader = csv.DictReader(io.StringIO(csv_text.lstrip("﻿")))
        column = next((c for c in (reader.fieldnames or []) if c and c.strip().lower() in SAFETY_COLUMNS), None)
        if column:
            for row in reader:
                if (row.get(column) or "").strip().lower() in SAFETY_YES:
                    aliases = tuple(a for a in ((row.get("tag") or "").strip(), (row.get("address") or "").strip()) if a)
                    if aliases:
                        zone.points.append(Point(aliases, "io_points.csv 安全=是"))
    return zone


# ---------------------------------------------------------------- 文本处理


def strip_comments(text: str) -> tuple[str, list[str]]:
    """去掉 ST 注释和字符串；返回（代码文本，按行的注释文本），行号保持不变。"""

    code: list[str] = []
    comments: list[str] = [""]
    i, n = 0, len(text)
    mode = ""
    while i < n:
        ch, pair = text[i], text[i : i + 2]
        if ch == "\n":
            code.append("\n")
            comments.append("")
            if mode == "//":
                mode = ""
            i += 1
            continue
        if mode == "":
            if pair == "//":
                mode = "//"
                i += 2
                continue
            if pair in ("(*", "/*"):
                mode = pair
                i += 2
                continue
            if ch in ("'", '"'):
                end = text.find(ch, i + 1)
                if end > 0 and "\n" not in text[i:end]:
                    # 双引号在西门子里是符号名，保留内容；单引号是字符串，置空
                    code.append(text[i : end + 1] if ch == '"' else ch * 2)
                    i = end + 1
                    continue
            code.append(ch)
        elif mode == "//":
            comments[-1] += ch
        else:
            closing = "*)" if mode == "(*" else "*/"
            if pair == closing:
                mode = ""
                i += 2
                continue
            comments[-1] += ch
        i += 1
    return "".join(code), comments


def tokens(line: str) -> set[str]:
    """一行里的标识符（小写）：整体和按点拆开的各段都算，``%I0.0`` 与 ``I0.0`` 等价。"""

    out: set[str] = set()
    for raw in TOKEN.findall(line):
        word = raw.lstrip("%").lower()
        out.add(word)
        out.update(word.split("."))
    return out


def hits(line: str, names: list[str]) -> list[str]:
    words = tokens(line)
    return sorted({n for n in names if any(fnmatch.fnmatchcase(w, n) for w in words)})


def regions(text: str) -> tuple[list[tuple[int, int]], list[str]]:
    """成对的 ``@安全区 开始/结束`` 圈出的行号区间（含标记行，从 1 起）。"""

    spans: list[tuple[int, int]] = []
    problems: list[str] = []
    start: int | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        if REGION_START.search(line):
            if start is not None:
                problems.append(f"第 {number} 行：上一个 @安全区 开始（第 {start} 行）还没结束")
            start = number
        elif REGION_END.search(line):
            if start is None:
                problems.append(f"第 {number} 行：@安全区 结束 前面没有 开始")
            else:
                spans.append((start, number))
                start = None
    if start is not None:
        problems.append(f"第 {start} 行：@安全区 开始 一直没有 结束")
        spans.append((start, len(text.splitlines())))
    return spans, problems


def inside(number: int, spans: list[tuple[int, int]]) -> bool:
    return any(a <= number <= b for a, b in spans)


def diff_lines(repo: Path, base: str, head: str, path: str) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """（删掉的行：基线行号+内容，新增的行：PR 头行号+内容）。"""

    raw = git(repo, "diff", "-U0", "--no-renames", "--no-color", "--text", f"{base}...{head}", "--", path)
    removed: list[tuple[int, str]] = []
    added: list[tuple[int, str]] = []
    old = new = 0
    in_hunk = False
    for line in raw.splitlines():
        match = HUNK.match(line)
        if match:
            old, new = int(match.group(1)), int(match.group(3))
            in_hunk = True
            continue
        if not in_hunk or line.startswith("\\"):
            continue
        if line.startswith("-"):
            removed.append((old, line[1:]))
            old += 1
        elif line.startswith("+"):
            added.append((new, line[1:]))
            new += 1
    return removed, added


# ---------------------------------------------------------------- 判定


@dataclass
class Result:
    touched: dict[str, list[str]] = field(default_factory=dict)
    violations: list[str] = field(default_factory=list)
    signature: str | None = None
    notes: list[str] = field(default_factory=list)
    plan: str | None = None
    plan_mismatch: bool = False

    def touch(self, root: str, reason: str) -> None:
        reasons = self.touched.setdefault(root, [])
        if reason not in reasons:
            reasons.append(reason)

    @property
    def needs_signature(self) -> bool:
        return bool(self.touched)

    @property
    def passed(self) -> bool:
        return not self.violations and (not self.needs_signature or self.signature is not None)


def forbidden(path: str, text: str, zone: Zone, result: Result) -> None:
    code, comments = strip_comments(text)
    points = [a.lower() for p in zone.points for a in p.aliases]
    names = zone.names()
    for number, line in enumerate(code.splitlines(), start=1):
        if TAUTOLOGY.search(line):
            result.violations.append(f"禁止式：`{path}` 第 {number} 行有恒真/恒假旁路：`{line.strip()[:120]}`")
        for match in CONST_ASSIGN.finditer(line):
            if hits(match.group(1), points):
                result.violations.append(f"禁止式：`{path}` 第 {number} 行把安全点赋成常量：`{match.group(0)}`")
    for number, comment in enumerate(comments, start=1):
        body = comment.strip()
        if (":=" in body or body.endswith(";")) and hits(body, names):
            result.violations.append(f"禁止式：`{path}` 第 {number} 行把引用安全变量的代码注释掉了：`{body[:120]}`")


def logic_tokens(text: str) -> set[str]:
    code, _ = strip_comments(text)
    return tokens(DECL_BLOCK.sub(" ", code))


def completeness(repo: Path, head: str, zone: Zone, result: Result) -> None:
    if not zone.points:
        return
    prefix = f"{zone.root}/"
    files = [f for f in git(repo, "ls-tree", "-r", "--name-only", "-z", head, "--", zone.root).split("\0") if f]
    seen: set[str] = set()
    for path in files:
        if path.startswith(prefix) and is_code(path) and zone_root(path) == zone.root:
            seen |= logic_tokens(show(repo, head, path) or "")
    for point in zone.points:
        if not any(alias.lstrip("%").lower() in seen for alias in point.aliases):
            result.violations.append(
                f"安全点漏引用：`{zone.root}` 的 {' / '.join(point.aliases)}（{point.source}）在程序逻辑里一次都没读到"
            )


def touched_lines(repo: Path, base: str, head: str, path: str, zone: Zone, result: Result) -> None:
    base_text, head_text = show(repo, base, path) or "", show(repo, head, path) or ""
    base_spans, base_problems = regions(base_text)
    head_spans, head_problems = regions(head_text)
    if base_problems:
        base_spans = [(1, max(1, len(base_text.splitlines())))]
        result.notes.append(f"`{path}` 在基线上的 @安全区 标记不成对，整个文件按安全区算")
    for problem in head_problems:
        result.violations.append(f"区段标记不成对：`{path}` {problem}")
    removed, added = diff_lines(repo, base, head, path)
    names = zone.names()
    for side, lines, spans in (("删掉", removed, base_spans), ("新增", added, head_spans)):
        for number, line in lines:
            if inside(number, spans):
                result.touch(zone.root, f"`{path}` {side}的第 {number} 行在 @安全区 区段里")
            found = hits(line, names)
            if found:
                result.touch(zone.root, f"`{path}` {side}的第 {number} 行引用安全变量 {', '.join(found)}")


def plan_declaration(body: str | None) -> tuple[str | None, list[str]]:
    """PR 描述里的计划栏④：返回（“是”/“否”/None，问题清单）。写了多行且不一致、或值不是 是/否，都是问题。"""

    values = [m.group(1).strip("`*_ ") for m in (PLAN_LINE.match(line) for line in (body or "").splitlines()) if m]
    if not values:
        return None, []
    bad = sorted({v for v in values if v not in PLAN_CHOICES})
    if bad:
        return None, [f"PR 描述里“安全回路”只能写 是 或 否，现在写的是：{'、'.join(bad)}"]
    if len(set(values)) > 1:
        return None, ["PR 描述里“安全回路”写了多行且不一致（既有“是”又有“否”），只留一行"]
    return values[0], []


def apply_plan(result: Result, plan: str | None, source: str) -> None:
    """两条联锁：填“是”一律要签字；填“否”却碰了安全区，同样要签字并点明不一致。须在改动判定之后调用。"""

    result.plan = plan
    if plan == "是":
        result.touch(PLAN_KEY, f"{source}填了“是”（涉及安全回路）：不论改到哪些文件都要安全签字")
    elif plan == "否" and result.touched:
        result.plan_mismatch = True
        result.touch(PLAN_KEY, f"{source}填了“否”，但本 PR 改到了安全区（见上）：计划与改动不一致，按安全区处理")


def check(
    repo: Path,
    base: str,
    head: str,
    comments: list[dict[str, Any]] | None = None,
    plan: str | None = None,
    plan_source: str = "PR 描述",
) -> Result:
    result = Result()
    head_sha = git(repo, "rev-parse", f"{head}^{{commit}}").strip()
    files = changed_files(repo, base, head)
    roots: dict[str, list[str]] = {}
    for path in files:
        root = zone_root(path)
        if root is None:
            continue
        if is_code(path) or is_manifest(path, root) or path == f"{root}/{IO_POINTS}":
            roots.setdefault(root, []).append(path)

    for root, paths in sorted(roots.items()):
        base_zone, head_zone = load_zone(repo, base, root), load_zone(repo, head, root)
        result.violations += head_zone.errors
        zone = base_zone.union(head_zone)
        for path in paths:
            if is_manifest(path, root):
                result.touch(root, f"改了安全区清单 `{path}`")
                continue
            if not base_zone.marked and is_code(path):
                result.touch(root, "项目在基线上还没有安全区清单（未标定）：改任何 PLC 程序都按安全区处理")
            if any(fnmatch.fnmatchcase(path.removeprefix(f"{root}/"), p) or fnmatch.fnmatchcase(path, p) for p in zone.files):
                result.touch(root, f"`{path}` 整个文件在安全区清单里")
            touched_lines(repo, base, head, path, zone, result)
            if is_code(path):
                text = show(repo, head, path)
                if text is not None:
                    forbidden(path, text, zone, result)
        completeness(repo, head, head_zone, result)

    apply_plan(result, plan, plan_source)
    if result.needs_signature:
        result.signature = find_signature(comments or [], head_sha, result)
    return result


def flatten(raw: Any) -> list[dict[str, Any]]:
    """``gh api --paginate --slurp`` 给的是“数组的数组”，单页给的是数组；两种都收。"""

    if isinstance(raw, dict):
        return [raw]
    out: list[dict[str, Any]] = []
    for item in raw or []:
        out += flatten(item) if isinstance(item, list) else [item] if isinstance(item, dict) else []
    return out


def find_signature(comments: list[dict[str, Any]], head_sha: str, result: Result) -> str | None:
    for comment in comments:
        body = str(comment.get("body") or "")
        shas = [m.group(1).lower() for m in (SIGN_LINE.match(line) for line in body.splitlines()) if m]
        if not shas:
            continue
        user = comment.get("user") or {}
        login, uid = user.get("login"), user.get("id")
        where = f"评论 {comment.get('html_url') or comment.get('id')}（{login}）"
        if login not in SIGNERS or SIGNERS[login] != uid:
            result.notes.append(f"{where}：不是指定签字人，不算")
            continue
        if comment.get("performed_via_github_app"):
            app = (comment["performed_via_github_app"] or {}).get("slug", "某个 App")
            result.notes.append(f"{where}：经由 GitHub App `{app}` 发出，不是本人手写，不算")
            continue
        if not any(head_sha.startswith(sha) for sha in shas):
            result.notes.append(f"{where}：签的是 {', '.join(shas)}，不是当前头提交 {head_sha[:8]}（签完又推过提交），要重签")
            continue
        return f"{where}，签 {head_sha[:8]}"
    return None


# ---------------------------------------------------------------- 本机：批准记录


class DecisionReadError(RuntimeError):
    pass


def decision_safety(control_root: Path, decision_id: str) -> str | None:
    """读批准记录（Decision）里的计划栏④：“是”/“否”；#36 之前批的、没有计划栏的返回 None。

    经 SW-2026-008 的 ``DecisionService`` 读，与 pm 同一套校验（规范编号、唯一链接、不漂移、合法 UTF-8）。
    """

    for entry in (SW008_ROOT / "auto_pm", SW008_ROOT):
        if str(entry) not in sys.path:
            sys.path.insert(0, str(entry))
    try:
        from auto_pm.domain.change.decision_service import DecisionService
    except ImportError as error:
        raise DecisionReadError(f"导入不了 auto_pm（本机用法要在装好依赖的控制根上跑）：{error}") from error
    try:
        decision = DecisionService(control_root).get_decision(decision_id)
    except Exception as error:  # DecisionService 的几种错误都按“读不了”处理，不放行
        raise DecisionReadError(f"读不了批准记录 {decision_id}：{error}") from error
    approval = decision.metadata.get("planning_approval")
    grant = approval.get("execution_grant") if isinstance(approval, dict) else None
    checklist = grant.get("plan_checklist") if isinstance(grant, dict) else None
    if checklist is None:
        return None
    value = checklist.get("safety_circuit") if isinstance(checklist, dict) else None
    if value not in PLAN_CHOICES:
        raise DecisionReadError(f"批准记录 {decision_id} 的计划栏④值不对：{value!r}（只认 是/否）")
    return value


def reconcile(recorded: str | None, declared: str | None, decision_id: str) -> tuple[str | None, list[str], list[str]]:
    """批准记录 vs PR 描述：返回（按哪个值判，硬问题，提示）。以严的一方为准。"""

    if recorded is None:
        return declared, [], [f"批准记录 {decision_id} 没有计划栏（计划防呆生效前批的），只按 PR 描述和改动判"]
    if recorded == "是" and declared != "是":
        said = "写了“否”" if declared == "否" else "没写"
        problem = f"批准记录 {decision_id} 计划栏④是“是”，PR 描述却{said}：先把 PR 描述改成单独一行“安全回路: 是”，GitHub 上的硬锁才接得上"
        return "是", [problem], []
    if recorded == "否" and declared == "是":
        return "是", [], [f"PR 描述写“是”，比批准记录 {decision_id} 的“否”严，按“是”处理"]
    if recorded == "否" and declared is None:
        return "否", [], ["PR 描述没写“安全回路: 否”，建议补上，让 GitHub 上的检查也做“填否却碰安全区”的核对"]
    return recorded, [], []


def gh_json(*args: str) -> Any:
    result = subprocess.run(["gh", "api", *args], capture_output=True, text=True, encoding="utf-8", check=False,
                            stdin=subprocess.DEVNULL)
    if result.returncode != 0:
        raise GitError(f"gh api {' '.join(args)}: {result.stderr.strip()}")
    return json.loads(result.stdout)


def fetch_pr(repo: Path, number: int, gh_repo: str) -> tuple[str, str, str, list[dict[str, Any]]]:
    """本机用法：经已登录的 gh 读 PR（基线、头、描述、评论），把头取到 refs/safety/pr-N。返回（base, head, body, 评论）。"""

    pr = gh_json(f"repos/{gh_repo}/pulls/{number}")
    comments = flatten(gh_json("--paginate", "--slurp", f"repos/{gh_repo}/issues/{number}/comments?per_page=100"))
    base, head = pr["base"]["sha"], pr["head"]["sha"]
    git(repo, "fetch", "--no-tags", "origin", f"+refs/pull/{number}/head:refs/safety/pr-{number}")
    if git(repo, "rev-parse", f"refs/safety/pr-{number}").strip() != head:
        raise GitError(f"取到的 PR 头和 GitHub 上的 {head[:8]} 不一致，重跑一次")
    try:
        git(repo, "cat-file", "-e", f"{base}^{{commit}}")
    except GitError:
        git(repo, "fetch", "--no-tags", "origin", pr["base"]["ref"])
    return base, head, pr.get("body") or "", comments


# ---------------------------------------------------------------- 输出


def status(result: Result) -> tuple[str, str]:
    if result.violations:
        return "failure", f"硬检查不通过 {len(result.violations)} 项（签字也放不行）"
    if not result.needs_signature:
        return "success", "没碰安全区"
    if result.signature:
        return "success", "碰了安全区，已有本人对当前提交的有效签字"
    if result.plan_mismatch:
        return "failure", "计划填“否”却碰了安全区：等用户在 PR 上评论“安全签字 <头提交号>”"
    if result.plan == "是" and list(result.touched) == [PLAN_KEY]:
        return "failure", "计划填了涉及安全回路：等用户在 PR 上评论“安全签字 <头提交号>”"
    return "failure", "碰了安全区：等用户在 PR 上评论“安全签字 <头提交号>”"


def render(result: Result, head: str) -> str:
    state, description = status(result)
    lines = ["## PR 安全区检查", "", f"- 头提交：`{head}`", f"- 计划栏④ 是否涉及安全回路：{result.plan or '没写'}"]
    if result.touched:
        lines.append(f"- 要签字的原因（按项目和计划栏分组）：{len(result.touched)} 组")
        for root, reasons in result.touched.items():
            lines.append(f"  - `{root}`")
            lines += [f"    - {r}" for r in reasons[:30]]
            if len(reasons) > 30:
                lines.append(f"    - …（另有 {len(reasons) - 30} 处）")
    else:
        lines.append("- 没碰到安全区")
    if result.needs_signature:
        lines.append(f"- 签字：{result.signature or '没有有效签字'}")
    lines.append("")
    lines.append(f"**结论：{'通过' if state == 'success' else '不通过'}**（{description}）")
    lines += [f"- ❌ {v}" for v in result.violations]
    lines += [f"- ℹ️ {n}" for n in result.notes]
    if result.needs_signature and not result.signature and not result.violations:
        lines += ["", f"用户本人在 PR 页面（网页或手机 App 手写）评论一行：`安全签字 {head[:7]}`，本检查会自动重跑。"]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PR 安全区检查（只读）")
    parser.add_argument("--base", help="PR 基线提交（base.sha）；用 --pr 时不填")
    parser.add_argument("--head", help="PR 头部提交（head.sha）；用 --pr 时不填")
    parser.add_argument("--pr", type=int, help="本机用法：经已登录的 gh 读这个 PR 的基线、头、描述和评论")
    parser.add_argument("--gh-repo", default=DEFAULT_REPO, help="owner/name（配合 --pr）")
    parser.add_argument("--pr-body-file", type=Path, help="PR 描述文本（读其中“安全回路: 是/否”一行）")
    parser.add_argument("--decision", help="本机用法：批准记录编号 DEC-…，读其计划栏④与 PR 描述核对")
    parser.add_argument("--control-root", type=Path, default=TOOL_ROOT, help="批准记录所在的控制根（默认：脚本所在仓库）")
    parser.add_argument("--repo", type=Path, default=TOOL_ROOT, help="被检查的仓库检出（默认：脚本所在仓库）")
    parser.add_argument("--comments", type=Path, help="PR 评论 JSON（GitHub issue comments API 的输出）")
    parser.add_argument("--status-out", type=Path, help="把提交状态（state/description）写成 JSON，供工作流回报")
    parser.add_argument("--ci", action="store_true", help="CI 模式：裁判与被检查对象必须是两份不同的检出")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    if args.ci and (args.decision or args.pr is not None):
        print("拒绝运行：CI 里读不到本机账本，--decision / --pr 只在本机用", file=sys.stderr)
        return 2
    if args.pr is None and not (args.base and args.head):
        print("要么给 --pr，要么同时给 --base 和 --head", file=sys.stderr)
        return 2
    if args.ci and (repo == TOOL_ROOT or TOOL_ROOT.is_relative_to(repo) or repo.is_relative_to(TOOL_ROOT)):
        print(f"拒绝运行：裁判 {TOOL_ROOT} 与被检查的检出 {repo} 必须分开（裁判取自 PR 基线）", file=sys.stderr)
        return 2
    comments: list[dict[str, Any]] = []
    if args.comments:
        try:
            comments = flatten(json.loads(args.comments.read_text(encoding="utf-8")))
        except (OSError, ValueError) as error:
            print(f"读不了评论文件：{error}", file=sys.stderr)
            return 2
    body = ""
    if args.pr_body_file:
        try:
            body = args.pr_body_file.read_text(encoding="utf-8")
        except OSError as error:
            print(f"读不了 PR 描述文件：{error}", file=sys.stderr)
            return 2
    base, head = args.base, args.head
    try:
        if args.pr is not None:
            base, head, body, fetched = fetch_pr(repo, args.pr, args.gh_repo)
            comments = comments or fetched
        declared, plan_problems = plan_declaration(body)
        plan, source, decision_problems, decision_notes = declared, "PR 描述", [], []
        if args.decision:
            recorded = decision_safety(args.control_root.resolve(), args.decision)
            plan, decision_problems, decision_notes = reconcile(recorded, declared, args.decision)
            if recorded is not None:
                source = f"批准记录 {args.decision}" if plan == recorded else "PR 描述"
        result = check(repo, base, head, comments, plan=plan, plan_source=source)
        result.violations += plan_problems + decision_problems
        result.notes += decision_notes
        head_sha = git(repo, "rev-parse", f"{head}^{{commit}}").strip()
    except (GitError, DecisionReadError, ValueError, KeyError) as error:
        print(f"出错：{error}", file=sys.stderr)
        return 2
    report = render(result, head_sha)
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8", errors="replace") as handle:
            handle.write(report)
    if args.status_out:
        state, description = status(result)
        args.status_out.write_text(json.dumps({"state": state, "description": description}, ensure_ascii=False), encoding="utf-8")
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
