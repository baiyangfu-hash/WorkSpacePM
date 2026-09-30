"""Read-only implementation-card precheck run before any Work/Run is created (card 027 §5).

One precheck serves both entry points:

* Markdown cards (the hand-written cards actually used): machine-readable header lines
  ``隔离基线：`` (40-hex commit or ``WORKTREE``) and ``路径根：``, plus path tables whose header row
  contains ``路径`` and ``基线状态`` (values ``存在`` / ``计划新增`` / ``运行态``).
* Structured ``implementation_card.v1`` cards: ``base_commit``, ``owned_paths`` with
  ``planned_new_paths``, and gate ``argv``.

Every rule is fail-closed and nothing is written: no Git object, database row, Work, Run or
Decision is created. The command tree is injected by the CLI layer so this module never imports
the user interface.
"""

from __future__ import annotations

import difflib
import hashlib
import re
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from auto_pm.contracts.implementation_card import ImplementationCard
from auto_pm.infrastructure.control_root_guard import clean_git_environment

BASELINE_EXISTS = "存在"
BASELINE_PLANNED = "计划新增"
BASELINE_RUNTIME = "运行态"
BASELINE_STATES = (BASELINE_EXISTS, BASELINE_PLANNED, BASELINE_RUNTIME)
WORKTREE_BASELINE = "WORKTREE"

_FULL_SHA = re.compile(r"[0-9a-f]{40}")
_PLACEHOLDER = re.compile(r"<[^<>\n]*>|待回写|\bTBD\b")
_HEADER = re.compile(r"^>\s*(隔离基线|路径根)：(.*)$")
_BACKTICK = re.compile(r"`([^`]+)`")
_MAIN_PY = re.compile(r"main\.py[ \t]+([^`\n|]+)")
_COMMAND_NAME = re.compile(r"[a-z][a-z0-9-]*")
_APPROVAL_FIELDS = frozenset({"实施批准", "最终验收", "审批人"})
_TRAILING = "，。；、：:;,.)）]}】\"'"


@dataclass(frozen=True)
class CommandNode:
    """One click command: its options (name -> takes a value) and sub-commands."""

    options: Mapping[str, bool] = field(default_factory=dict)
    children: Mapping[str, CommandNode] = field(default_factory=dict)


@dataclass(frozen=True)
class PrecheckFinding:
    rule: str
    subject: str
    message: str


@dataclass(frozen=True)
class CardPath:
    path: str
    state: str


@dataclass(frozen=True)
class PrecheckReport:
    card: str
    card_sha256: str
    baseline: str
    path_root: str
    paths: tuple[CardPath, ...]
    commands: tuple[str, ...]
    findings: tuple[PrecheckFinding, ...]

    @property
    def passed(self) -> bool:
        return not self.findings

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "implementation-card-precheck.v1",
            "card": self.card,
            "card_sha256": self.card_sha256,
            "baseline": self.baseline,
            "path_root": self.path_root,
            "passed": self.passed,
            "paths": [{"path": item.path, "state": item.state} for item in self.paths],
            "commands": list(self.commands),
            "findings": [
                {"rule": item.rule, "subject": item.subject, "message": item.message}
                for item in self.findings
            ],
        }


def _git_ok(root: Path, *args: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=clean_git_environment(),
            stdin=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, ""
    return result.returncode == 0, result.stdout.strip()


def _normalized(path: str) -> str | None:
    """Canonical workspace-relative POSIX path, or None when traversing/absolute."""

    candidate = path.strip().replace("\\", "/")
    while candidate.startswith("./"):
        candidate = candidate[2:]
    parts = PurePosixPath(candidate).parts
    if not candidate or candidate.startswith("/") or ".." in parts or re.match(r"^[A-Za-z]:", candidate):
        return None
    return "/".join(parts)


def _join(root: str, relative: str) -> str | None:
    if root in {"", "."}:
        return _normalized(relative)
    return _normalized(f"{root}/{relative}")


def _baseline_findings(baseline: str, workspace_root: Path) -> list[PrecheckFinding]:
    if not baseline:
        return [PrecheckFinding("header", "隔离基线", "卡片缺少机器可读头部 `隔离基线：`（旧格式卡，不能作为 Work 依据）")]
    if _PLACEHOLDER.search(baseline):
        return [PrecheckFinding("placeholder", "隔离基线", f"隔离基线仍是占位符（基线未回写）: {baseline}")]
    if baseline == WORKTREE_BASELINE:
        return []
    if _FULL_SHA.fullmatch(baseline) is None:
        return [PrecheckFinding("baseline", "隔离基线", f"隔离基线必须是 40 位小写 commit SHA 或 WORKTREE: {baseline}")]
    ok, resolved = _git_ok(workspace_root, "rev-parse", "--verify", f"{baseline}^{{commit}}")
    if not ok or resolved != baseline:
        return [PrecheckFinding("baseline", "隔离基线", f"隔离基线无法解析为完整 commit: {baseline}")]
    return []


def _path_exists(workspace_root: Path, baseline: str, path: str) -> bool:
    if baseline == WORKTREE_BASELINE:
        return (workspace_root / path).exists()
    ok, _ = _git_ok(workspace_root, "cat-file", "-e", f"{baseline}:{path}")
    return ok


def _path_findings(
    paths: Iterable[CardPath], *, baseline: str, workspace_root: Path, baseline_valid: bool
) -> list[PrecheckFinding]:
    findings: list[PrecheckFinding] = []
    for item in paths:
        if item.state == BASELINE_RUNTIME:
            if not (workspace_root / item.path).exists():
                findings.append(PrecheckFinding("path", item.path, "运行态对象在控制根文件系统上不存在"))
            continue
        if not baseline_valid:
            continue
        exists = _path_exists(workspace_root, baseline, item.path)
        if item.state == BASELINE_EXISTS and not exists:
            findings.append(
                PrecheckFinding("path", item.path, f"标注“存在”，但在隔离基线 {baseline} 上不存在")
            )
        elif item.state == BASELINE_PLANNED and exists:
            findings.append(
                PrecheckFinding("path", item.path, f"标注“计划新增”，但在隔离基线 {baseline} 上已存在")
            )
    return findings


def _split_row(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [cell.strip().replace("**", "") for cell in body.split("|")]


def _tables(lines: Sequence[str]) -> list[tuple[int, list[str], list[list[str]]]]:
    tables: list[tuple[int, list[str], list[list[str]]]] = []
    index = 0
    while index < len(lines):
        if lines[index].lstrip().startswith("|"):
            start = index
            block: list[str] = []
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                block.append(lines[index])
                index += 1
            if len(block) >= 2 and re.fullmatch(r"[\s|:\-]+", block[1].strip()):
                tables.append((start + 1, _split_row(block[0]), [_split_row(row) for row in block[2:]]))
            continue
        index += 1
    return tables


def resolve_command(
    tokens: Sequence[str], tree: Mapping[str, CommandNode]
) -> tuple[str, list[PrecheckFinding]]:
    """Resolve ``main.py`` argument tokens against the real click command tree."""

    findings: list[PrecheckFinding] = []
    node = CommandNode(children=tree)
    path: list[str] = []
    position = 0
    while position < len(tokens):
        token = tokens[position]
        if _PLACEHOLDER.search(token):
            findings.append(PrecheckFinding("placeholder", " ".join(tokens), f"命令含占位符: {token}"))
            return " ".join(path), findings
        if token.startswith("-"):
            name = token.split("=", 1)[0]
            if name in {"--help", "-h"}:
                position += 1
                continue
            if name not in node.options:
                subject = " ".join(["main.py", *path]) or "main.py"
                findings.append(
                    PrecheckFinding("command", subject, f"{name} 不是 `{subject}` 声明过的选项")
                )
                position += 1
                continue
            takes_value = node.options[name] and "=" not in token
            if takes_value and position + 1 < len(tokens) and _PLACEHOLDER.search(tokens[position + 1]):
                findings.append(
                    PrecheckFinding("placeholder", " ".join(tokens), f"命令含占位符: {name} {tokens[position + 1]}")
                )
            position += 2 if takes_value else 1
            continue
        if not node.children:
            position += 1  # positional argument of a leaf command
            continue
        if token not in node.children:
            subject = " ".join(["main.py", *path, token])
            close = difflib.get_close_matches(token, list(node.children), n=3)
            hint = f"；最接近的合法命令: {', '.join(close)}" if close else ""
            findings.append(PrecheckFinding("command", subject, f"未知命令或子组: {token}{hint}"))
            return " ".join(path), findings
        path.append(token)
        node = node.children[token]
        position += 1
    if node.children:
        findings.append(
            PrecheckFinding("command", " ".join(["main.py", *path]), "命令不完整：停在命令组上")
        )
    return " ".join(path), findings


def _command_tokens(text: str) -> list[list[str]]:
    invocations: list[list[str]] = []
    for match in _MAIN_PY.finditer(text):
        tokens = [token.strip(_TRAILING) for token in match.group(1).split()]
        tokens = [token for token in tokens if token]
        if not tokens or _COMMAND_NAME.fullmatch(tokens[0]) is None and not tokens[0].startswith("-"):
            continue  # prose mentioning main.py, not an invocation
        invocations.append(tokens)
    return invocations


def precheck_markdown_card(
    card_file: Path, *, workspace_root: Path, command_tree: Mapping[str, CommandNode]
) -> PrecheckReport:
    """Precheck one hand-written Markdown card; pure read, fail-closed findings."""

    raw = card_file.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    findings: list[PrecheckFinding] = []
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return PrecheckReport(
            str(card_file), digest, "", "", (), (),
            (PrecheckFinding("header", str(card_file), "卡片不是合法 UTF-8"),),
        )
    lines = text.splitlines()
    header: dict[str, list[str]] = {"隔离基线": [], "路径根": []}
    for line in lines:
        match = _HEADER.match(line)
        if match:
            value = match.group(2).strip()
            quoted = _BACKTICK.search(value)
            header[match.group(1)].append(quoted.group(1).strip() if quoted else value)
    for key, values in header.items():
        if len(values) > 1:
            findings.append(PrecheckFinding("header", key, f"头部字段 `{key}：` 重复出现 {len(values)} 次"))
    baseline = header["隔离基线"][0] if header["隔离基线"] else ""
    path_root_raw = header["路径根"][0] if header["路径根"] else ""
    baseline_findings = _baseline_findings(baseline, workspace_root)
    findings.extend(baseline_findings)
    path_root = ""
    if not path_root_raw:
        findings.append(PrecheckFinding("header", "路径根", "卡片缺少机器可读头部 `路径根：`"))
    elif _PLACEHOLDER.search(path_root_raw):
        findings.append(PrecheckFinding("placeholder", "路径根", f"路径根仍是占位符: {path_root_raw}"))
    else:
        normalized_root = "." if path_root_raw.strip() in {".", "./"} else _normalized(path_root_raw)
        if normalized_root is None:
            findings.append(PrecheckFinding("header", "路径根", f"路径根必须是控制根内的相对路径: {path_root_raw}"))
        else:
            path_root = normalized_root

    paths: list[CardPath] = []
    path_tables = 0
    for line_number, head, rows in _tables(lines):
        if head and head[0] in _APPROVAL_FIELDS or any(row and row[0] in _APPROVAL_FIELDS for row in rows):
            for row in rows:
                if row and row[0] in _APPROVAL_FIELDS and _PLACEHOLDER.search(" ".join(row[1:])):
                    findings.append(PrecheckFinding("placeholder", row[0], "审批字段含占位符"))
        if "路径" not in head:
            continue
        if "基线状态" not in head:
            findings.append(
                PrecheckFinding("path_table", f"第 {line_number} 行表格", "表格含“路径”列但缺少“基线状态”列")
            )
            continue
        path_tables += 1
        path_column = head.index("路径")
        state_column = head.index("基线状态")
        for offset, row in enumerate(rows, start=2):
            where = f"第 {line_number + offset} 行"
            if len(row) <= max(path_column, state_column):
                findings.append(PrecheckFinding("path_table", where, "路径表行的列数不足"))
                continue
            quoted = _BACKTICK.search(row[path_column])
            if quoted is None:
                findings.append(PrecheckFinding("path_table", where, "路径单元格缺少反引号包裹的相对路径"))
                continue
            relative = quoted.group(1).strip()
            state = row[state_column].strip()
            if _PLACEHOLDER.search(relative):
                findings.append(PrecheckFinding("placeholder", relative, "路径仍是占位符"))
                continue
            if state not in BASELINE_STATES:
                findings.append(
                    PrecheckFinding("path_table", relative, f"基线状态只允许 存在/计划新增/运行态，实际为: {state or '空'}")
                )
                continue
            resolved = _normalized(relative) if state == BASELINE_RUNTIME else _join(path_root or ".", relative)
            if resolved is None:
                findings.append(PrecheckFinding("path_table", relative, "路径必须是不含 .. 的相对路径"))
                continue
            paths.append(CardPath(resolved, state))
    if path_tables == 0:
        findings.append(PrecheckFinding("path_table", str(card_file), "卡片没有含“路径”与“基线状态”两列的路径表"))
    findings.extend(
        _path_findings(
            paths, baseline=baseline, workspace_root=workspace_root, baseline_valid=not baseline_findings
        )
    )

    commands: list[str] = []
    for tokens in _command_tokens(text):
        resolved_command, command_findings = resolve_command(tokens, command_tree)
        commands.append(resolved_command)
        findings.extend(command_findings)
    return PrecheckReport(
        str(card_file), digest, baseline, path_root, tuple(paths), tuple(commands), tuple(findings)
    )


def precheck_structured_card(
    card: ImplementationCard,
    *,
    workspace_root: Path,
    command_tree: Mapping[str, CommandNode] | None,
) -> PrecheckReport:
    """Apply the same path/baseline/command rules to a structured implementation_card.v1."""

    findings = _baseline_findings(card.base_commit, workspace_root)
    planned = set(card.planned_new_paths)
    paths = tuple(
        CardPath(path, BASELINE_PLANNED if path in planned else BASELINE_EXISTS)
        for path in card.owned_paths
    )
    findings.extend(
        _path_findings(
            paths, baseline=card.base_commit, workspace_root=workspace_root, baseline_valid=not findings
        )
    )
    commands: list[str] = []
    if command_tree is not None:
        for gate in card.gates:
            for index, token in enumerate(gate.argv):
                if token == "main.py" or token.endswith(("/main.py", "\\main.py")):
                    resolved, command_findings = resolve_command(gate.argv[index + 1 :], command_tree)
                    commands.append(resolved)
                    findings.extend(command_findings)
                    break
    digest = hashlib.sha256(card.model_dump_json().encode("utf-8")).hexdigest()
    return PrecheckReport(
        card.card_id, digest, card.base_commit, ".", paths, tuple(commands), tuple(findings)
    )


def scopes_outside_card(scope_paths: Iterable[str], report: PrecheckReport) -> list[str]:
    """Return every Work scope that is not exactly a card path or below one."""

    allowed = [item.path for item in report.paths]
    outside: list[str] = []
    for scope in scope_paths:
        normalized = _normalized(scope)
        if normalized is None or not any(
            normalized == path or normalized.startswith(f"{path}/") for path in allowed
        ):
            outside.append(scope)
    return outside


def format_findings(report: PrecheckReport) -> str:
    return "; ".join(f"[{item.rule}] {item.subject}: {item.message}" for item in report.findings)
