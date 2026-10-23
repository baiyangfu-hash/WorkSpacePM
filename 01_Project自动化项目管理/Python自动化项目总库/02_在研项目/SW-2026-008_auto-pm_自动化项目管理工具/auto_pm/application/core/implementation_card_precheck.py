"""Read-only implementation-card precheck run before any Work/Run is created (card 027 §5).

One precheck serves both entry points:

* Markdown cards (the hand-written cards actually used): machine-readable header lines
  ``隔离基线：`` (40-hex commit or ``WORKTREE``) and ``路径根：``, plus path tables whose header row
  contains ``路径`` and ``基线状态`` (values ``存在`` / ``计划新增`` / ``运行态``).
* New-format Markdown cards (``CARD-<PID>-NNN`` in ``<project>/<监控>/01_变更管理/03_实施卡/``)
  additionally carry ``依据：`` and ``变更单：``; see ``implementation_card_basis``. Their ``路径根``
  defaults to the project directory and several cards may share one change order.
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

from auto_pm.application.core import implementation_card_basis as basis
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
    card_format: str = "legacy"
    basis: tuple[str, ...] = ()
    change: str = ""

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
            "card_format": self.card_format,
            "basis": list(self.basis),
            "change": self.change,
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


def _baseline_findings(
    baseline: str, workspace_root: Path, *, new_format: bool = False
) -> list[PrecheckFinding]:
    if not baseline and new_format:
        return [
            PrecheckFinding("header", "隔离基线", "派工前要在卡片头部填 `隔离基线：`（起始 main 的 40 位提交号）")
        ]
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


def _path_column(head: Sequence[str]) -> int | None:
    """The path column: ``路径`` or an annotated ``路径（相对项目根）``."""
    for index, cell in enumerate(head):
        if cell == "路径" or cell.startswith(("路径（", "路径(")):
            return index
    return None


def _state_of(cell: str) -> str:
    """``存在（只加调用）`` reads as ``存在``; any other annotation stays and is rejected."""
    state = cell.strip()
    for known in BASELINE_STATES:
        if state.startswith((f"{known}（", f"{known}(")) and state.endswith(("）", ")")):
            return known
    return state


def _parse_path_tables(
    lines: Sequence[str], path_root: str, card: str
) -> tuple[tuple[CardPath, ...], list[PrecheckFinding]]:
    findings: list[PrecheckFinding] = []
    paths: list[CardPath] = []
    path_tables = 0
    for line_number, head, rows in _tables(lines):
        if head and head[0] in _APPROVAL_FIELDS or any(row and row[0] in _APPROVAL_FIELDS for row in rows):
            for row in rows:
                if row and row[0] in _APPROVAL_FIELDS and _PLACEHOLDER.search(" ".join(row[1:])):
                    findings.append(PrecheckFinding("placeholder", row[0], "审批字段含占位符"))
        path_column = _path_column(head)
        if path_column is None:
            continue
        if "基线状态" not in head:
            findings.append(
                PrecheckFinding("path_table", f"第 {line_number} 行表格", "表格含“路径”列但缺少“基线状态”列")
            )
            continue
        path_tables += 1
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
            state = _state_of(row[state_column])
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
        findings.append(PrecheckFinding("path_table", card, "卡片没有含“路径”与“基线状态”两列的路径表"))
    return tuple(paths), findings


def precheck_markdown_card(
    card_file: Path,
    *,
    workspace_root: Path,
    command_tree: Mapping[str, CommandNode],
    project_id: str | None = None,
) -> PrecheckReport:
    """Precheck one hand-written Markdown card; pure read, fail-closed findings.

    ``project_id`` (the Work's ``--pid``) is compared with the project a new-format card lives in.
    """

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
    header = _machine_header(lines)
    basis_header = basis.parse_header(lines)
    new_format = basis.is_new_format(card_file, basis_header)
    project_root = _project_root(card_file, workspace_root) if new_format else None
    for key, values in header.items():
        if len(values) > 1:
            findings.append(PrecheckFinding("header", key, f"头部字段 `{key}：` 重复出现 {len(values)} 次"))
    baseline = header["隔离基线"][0] if header["隔离基线"] else ""
    path_root_raw = header["路径根"][0] if header["路径根"] else ""
    baseline_findings = _baseline_findings(baseline, workspace_root, new_format=new_format)
    findings.extend(baseline_findings)
    path_root = ""
    if not path_root_raw and project_root is not None:
        path_root = project_root  # new-format path tables are relative to the project directory
    elif not path_root_raw:
        findings.append(PrecheckFinding("header", "路径根", "卡片缺少机器可读头部 `路径根：`"))
    elif _PLACEHOLDER.search(path_root_raw):
        findings.append(PrecheckFinding("placeholder", "路径根", f"路径根仍是占位符: {path_root_raw}"))
    else:
        normalized_root = "." if path_root_raw.strip() in {".", "./"} else _normalized(path_root_raw)
        if normalized_root is None:
            findings.append(PrecheckFinding("header", "路径根", f"路径根必须是控制根内的相对路径: {path_root_raw}"))
        else:
            path_root = normalized_root

    table_paths, table_findings = _parse_path_tables(lines, path_root, str(card_file))
    paths = list(table_paths)
    findings.extend(table_findings)
    findings.extend(
        _path_findings(
            paths, baseline=baseline, workspace_root=workspace_root, baseline_valid=not baseline_findings
        )
    )
    if new_format:
        card_paths = [item.path for item in paths]
        findings.extend(
            PrecheckFinding(item.rule, item.subject, item.message)
            for item in basis.basis_findings(
                card_file,
                basis_header,
                workspace_root=workspace_root,
                paths=card_paths,
                project_id=project_id,
            )
        )
        findings.extend(
            _sibling_findings(card_file, basis_header, card_paths, project_root or "")
        )

    commands: list[str] = []
    for tokens in _command_tokens(text):
        resolved_command, command_findings = resolve_command(tokens, command_tree)
        commands.append(resolved_command)
        findings.extend(command_findings)
    return PrecheckReport(
        str(card_file), digest, baseline, path_root, tuple(paths), tuple(commands), tuple(findings),
        card_format="new" if new_format else "legacy",
        basis=basis_header.basis,
        change=basis_header.change_id,
    )


def _machine_header(lines: Sequence[str]) -> dict[str, list[str]]:
    header: dict[str, list[str]] = {"隔离基线": [], "路径根": []}
    for line in lines:
        match = _HEADER.match(line)
        if match:
            value = match.group(2).strip()
            quoted = _BACKTICK.search(value)
            header[match.group(1)].append(quoted.group(1).strip() if quoted else value)
    return header


def _project_root(card_file: Path, workspace_root: Path) -> str | None:
    """The card's project directory relative to the control root, when it sits in its drawer."""
    project_dir = basis.project_dir_of(card_file)
    root = workspace_root.resolve()
    if project_dir is None or not project_dir.is_relative_to(root):
        return None
    return project_dir.relative_to(root).as_posix() or "."


def _sibling_findings(
    card_file: Path, header: basis.CardHeader, paths: Sequence[str], project_root: str
) -> list[PrecheckFinding]:
    """One change order, several cards: open cards under it must not touch the same paths
    unless one names the other in ``前置卡：`` (their order is then fixed)."""

    change_id = header.change_id
    if not change_id or not project_root:
        return []
    own_id = basis.card_id_of(card_file)
    findings: list[PrecheckFinding] = []
    drawer = card_file.resolve().parent
    for unreadable in basis.unreadable_cards(drawer):
        if unreadable.resolve() != card_file.resolve():
            findings.append(
                PrecheckFinding(
                    "change",
                    unreadable.name,
                    "同一抽屉里的这张卡不是 UTF-8 文本，读不出它挂哪张变更单、改哪些文件；先转成 UTF-8",
                )
            )
    for sibling in basis.cards_for_change(drawer, change_id):
        if sibling.card_file.resolve() == card_file.resolve() or not sibling.open:
            continue
        names_me = own_id in sibling.header.predecessors
        named_by_me = sibling.card_id in header.predecessors
        if names_me and named_by_me:
            findings.append(
                PrecheckFinding(
                    "change",
                    sibling.card_id,
                    f"本卡和 {sibling.card_id} 互为前置卡，先后没有排定；只在后做的那张卡写 `前置卡：`",
                )
            )
            continue
        if names_me:
            continue  # this card goes first; the sibling waits for it
        lines = sibling.card_file.read_text(encoding="utf-8").splitlines()
        declared = _machine_header(lines)["路径根"]
        root = _normalized(declared[0]) if declared and declared[0] not in {".", "./"} else None
        sibling_root = root or ("." if declared else project_root)
        sibling_paths, sibling_problems = _parse_path_tables(lines, sibling_root, str(sibling.card_file))
        if any(item.rule in {"path_table", "placeholder"} for item in sibling_problems):
            # A row that cannot be read may be the one that overlaps: refuse rather than guess.
            findings.append(
                PrecheckFinding(
                    "change",
                    sibling.card_id,
                    f"同一变更单 {change_id} 下未关闭的卡路径表读不全，无法核对是否改同一批文件；"
                    "先把那张卡的路径表补齐",
                )
            )
            continue
        shared = basis.paths_overlap(paths, [item.path for item in sibling_paths])
        if shared and sibling.card_id in header.predecessors:
            findings.append(
                PrecheckFinding(
                    "change",
                    sibling.card_id,
                    f"前置卡 {sibling.card_id} 还没关闭，它和本卡改同一批文件（{', '.join(shared)}）；"
                    "等前置卡验收关闭后再开工",
                )
            )
        elif shared:
            findings.append(
                PrecheckFinding(
                    "change",
                    sibling.card_id,
                    f"与同一变更单 {change_id} 下未关闭的卡改同一批文件（{', '.join(shared)}）；"
                    "在其中一张卡头部写 `前置卡：` 排定先后",
                )
            )
    return findings


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
