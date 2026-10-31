"""Basis and change-order rules for new-format implementation cards (CARD-<PID>-NNN).

The project's change cabinet has three drawers (plan "实施卡与变更单定位与存放方案" §4)::

    <project>/<04_监控|11_监控>/01_变更管理/
        01_变更单/   CHG change orders (ECN), only for releases, safety, core ledger, spec library
        02_变更记录/ business change records (BC table ``02_业务变更记录.md``)
        03_实施卡/   implementation cards, one file each

A card points one way at its basis through two machine-readable header lines::

    > 依据：`BC-DJ-2026-009-004`        (one or more BC ids, or REQ items such as `A3`)
    > 变更单：`无`                      (or exactly one `CHG-<domain>-<year>-<seq>`)

Every lookup stays inside the card's own project (change orders are numbered per project and may
repeat across projects). Nothing here writes; every rule fails closed. Several cards may hang
under one change order; their path tables must not overlap unless one names the other in
``> 前置卡：`` (the order is then fixed).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

CHANGE_CABINET = "01_变更管理"
CARD_DRAWER = "03_实施卡"
CHANGE_DRAWER = "01_变更单"
BC_RECORD = ("02_变更记录", "02_业务变更记录.md")
MONITOR_DIRS = ("04_监控", "11_监控")
NO_CHANGE = "无"
APPROVED_BC_STATES = ("已批", "已实施")
CLOSED_CARD_STATES = ("已验收", "关闭", "驳回", "取消")

# Paths that only move under a change order: spec library, release pointers and releases, the
# runtime ledger store, and every project's version ledger.
GUARDED_PREFIXES = (
    "00_Obsidian_Base全局规范文件仓库/",
    "00_Infrastructure/auto_pm/releases/",
    ".auto-pm/",
)
GUARDED_FILES = (
    "00_Infrastructure/auto_pm/active_release.json",
    "00_Infrastructure/auto_pm/previous_release.json",
    "00_Infrastructure/auto_pm/deployment_manifest.json",
)
GUARDED_SUFFIXES = (f"/{CHANGE_CABINET}/02_变更记录/01_版本变更台账.md",)

NEW_CARD_NAME = re.compile(r"^(CARD-[A-Z]+-\d{4}-\d{3})-(\d{3})(?=_|$)")
# Old ids keep a three-digit serial; from 2026-10-22 a new row is numbered by the month it was raised: BC-<pid>-<year>_<month>_<serial>.
BC_ID = re.compile(r"^BC-[A-Z]+-\d{4}-\d{3}-(?:\d{3}|\d{4}_(?:0[1-9]|1[0-2])_\d{3})$")
# A confirmed requirement checklist cited with its version: REQ-<pid>-<year>_<month>_<serial> V<n>.
REQ_ID = re.compile(r"^(REQ-[A-Z]+-\d{4}-\d{3}-\d{4}_(?:0[1-9]|1[0-2])_\d{3}) V([1-9]\d*)$")
REQ_DRAWER = "00_需求核对单"
_REQ_CONFIRMED_VERSION = re.compile(r"^\|\s*确认的版本\s*\|\s*(V[1-9]\d*)\s*\|", re.MULTILINE)
_BC_MONTH = re.compile(r"-(\d{4})_(\d{2})_\d{3}$")
# The template column is 提出时间; older project tables still say 提出日期.
_BC_RAISED = ("提出时间", "提出日期")
CHG_ID = re.compile(r"^CHG-[A-Z]+-\d{4}-\d{3,}$")
CARD_ID = re.compile(r"CARD-[A-Za-z0-9-]+")
_BASIS_HEADER = re.compile(r"^>\s*(依据|变更单|前置卡|状态)：(.*)$")
_BACKTICK = re.compile(r"`([^`]+)`")
_PLACEHOLDER = re.compile(r"<[^<>\n]*>|待回写|待补|\bTBD\b")


@dataclass(frozen=True)
class BasisFinding:
    rule: str
    subject: str
    message: str


@dataclass(frozen=True)
class CardHeader:
    """The basis header lines of one card, values as written (backticks removed)."""

    basis: tuple[str, ...]
    basis_raw: tuple[str, ...]
    change: tuple[str, ...]
    predecessors: tuple[str, ...]
    state: str

    @property
    def declared(self) -> bool:
        return bool(self.basis_raw or self.change)

    @property
    def change_id(self) -> str:
        """The single change order this card hangs under, or "" for 无 / undeclared."""
        if len(self.change) != 1:
            return ""
        value = _first_value(self.change[0])
        return "" if value == NO_CHANGE else value


def _first_value(raw: str) -> str:
    quoted = _BACKTICK.search(raw)
    return (quoted.group(1) if quoted else raw).strip()


def _state_word(raw: str) -> str:
    return re.split(r"[（(/\s]", raw.strip(), maxsplit=1)[0] if raw.strip() else ""


def parse_header(lines: Sequence[str]) -> CardHeader:
    values: dict[str, list[str]] = {"依据": [], "变更单": [], "前置卡": [], "状态": []}
    for line in lines:
        match = _BASIS_HEADER.match(line)
        if match:
            values[match.group(1)].append(match.group(2).strip())
    basis: list[str] = []
    for raw in values["依据"]:
        quoted = _BACKTICK.findall(raw)
        items = quoted if quoted else re.split(r"[,，、]", raw)
        basis.extend(item.strip() for item in items if item.strip())
    predecessors = [
        found for raw in values["前置卡"] for found in CARD_ID.findall(raw)
    ]
    return CardHeader(
        basis=tuple(basis),
        basis_raw=tuple(values["依据"]),
        change=tuple(values["变更单"]),
        predecessors=tuple(predecessors),
        state=_state_word(values["状态"][0]) if values["状态"] else "",
    )


def card_id_of(card_file: Path) -> str:
    match = NEW_CARD_NAME.match(card_file.name)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return card_file.stem.split("_", 1)[0]


def project_dir_of(card_file: Path) -> Path | None:
    """``<project>`` when the card sits directly in ``<project>/<监控>/01_变更管理/03_实施卡/``."""
    parent = card_file.resolve().parent
    if parent.name != CARD_DRAWER or parent.parent.name != CHANGE_CABINET:
        return None
    if parent.parent.parent.name not in MONITOR_DIRS:
        return None
    return parent.parent.parent.parent


def is_new_format(card_file: Path, header: CardHeader) -> bool:
    """New-format rules apply in the card drawer, to CARD-<PID>-NNN names, or once declared."""
    return (
        header.declared
        or project_dir_of(card_file) is not None
        or NEW_CARD_NAME.match(card_file.name) is not None
    )


def _project_id(project_dir: Path) -> str:
    return project_dir.name.split("_", 1)[0]


def _skip(path: Path, base: Path) -> bool:
    return any(part.casefold() == "archive" for part in path.relative_to(base).parts)


def _bc_rows(record: Path) -> dict[str, tuple[str, str]]:
    """``{BC id: (状态, 提出时间)}``; the raise time is "" when the table has neither 提出时间 nor 提出日期."""
    rows: dict[str, tuple[str, str]] = {}
    head: list[str] = []
    for line in record.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.lstrip().startswith("|"):
            head = []
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not head:
            head = cells
            continue
        if re.fullmatch(r"[\s|:\-]+", line.strip()) or "编号" not in head or "状态" not in head:
            continue
        if len(cells) == len(head):
            raised = next((cells[head.index(name)] for name in _BC_RAISED if name in head), "")
            rows[cells[head.index("编号")].strip("`")] = (cells[head.index("状态")], raised)
    return rows


def _req_files(project_dir: Path) -> list[Path]:
    return sorted(
        path for path in project_dir.rglob("*REQ*.md")
        if path.is_file() and not _skip(path, project_dir) and REQ_DRAWER not in path.parts
    )


def _req_checklist_finding(item: str, project_dir: Path, pid: str) -> BasisFinding | None:
    """A cited checklist must be this project's, sit in its drawer, and carry the cockpit's confirmation of that version."""

    match = REQ_ID.fullmatch(item)
    if match is None:
        return BasisFinding("basis", item, "需求核对单的写法应为 REQ-<项目号>-<年>_<月>_<三位序号> V<版本>")
    req_id, version = match.group(1), f"V{match.group(2)}"
    if not req_id.startswith(f"REQ-{pid}-"):
        return BasisFinding("basis", item, f"依据的需求核对单不属于本项目 {pid}")
    files = sorted(
        path for path in project_dir.rglob(f"{req_id}_*.md")
        if path.is_file() and path.parent.name == REQ_DRAWER and not _skip(path, project_dir)
    )
    if len(files) != 1:
        return BasisFinding("basis", item, f"本项目 {REQ_DRAWER}/ 里应恰有一份 {req_id}，实际 {len(files)} 份")
    text = files[0].read_text(encoding="utf-8", errors="replace")
    confirmed = _REQ_CONFIRMED_VERSION.search(text)
    if not re.search(r"^> 状态：已确认\s*$", text, re.MULTILINE) or confirmed is None:
        return BasisFinding("basis", item, "需求核对单还没有经用户确认（第 8 节未由驾驶舱写入）")
    if confirmed.group(1) != version:
        return BasisFinding("basis", item, f"用户确认的是 {confirmed.group(1)}，实施卡依据写的是 {version}")
    return None


def _resolve_doc(token: str, project_dir: Path, workspace_root: Path) -> Path | None:
    for base in (project_dir, workspace_root):
        candidate = (base / token).resolve()
        if candidate.is_file() and candidate.is_relative_to(workspace_root.resolve()):
            return candidate
    return None


def change_files(monitor_dir: Path, change_id: str) -> list[Path]:
    drawer = monitor_dir / CHANGE_CABINET / CHANGE_DRAWER
    if not drawer.is_dir():
        return []
    return sorted(
        path for path in drawer.rglob(f"{change_id}.md")
        if path.is_file() and not _skip(path, drawer)
    )


def is_guarded(path: str, workspace_root: Path | None = None) -> bool:
    """A guarded file or directory, or a directory that contains one (an ancestor such as
    ``00_Infrastructure/auto_pm`` covers ``active_release.json``).  With ``workspace_root`` a
    directory is also searched for project version ledgers."""

    if (
        path in GUARDED_FILES
        or any(path.startswith(prefix) or f"{path}/" == prefix for prefix in GUARDED_PREFIXES)
        or any(path.endswith(suffix) for suffix in GUARDED_SUFFIXES)
    ):
        return True
    directory = path.rstrip("/")
    if directory in {"", "."}:
        return True
    if any(item.startswith(f"{directory}/") for item in (*GUARDED_FILES, *GUARDED_PREFIXES)):
        return True
    if workspace_root is None or not (workspace_root / directory).is_dir():
        return False
    ledger_name = GUARDED_SUFFIXES[0].rsplit("/", 1)[-1]
    return any(
        f"/{ledger.relative_to(workspace_root).as_posix()}".endswith(suffix)
        for ledger in (workspace_root / directory).rglob(ledger_name)
        for suffix in GUARDED_SUFFIXES
    )


def basis_findings(
    card_file: Path,
    header: CardHeader,
    *,
    workspace_root: Path,
    paths: Iterable[str],
    project_id: str | None = None,
) -> list[BasisFinding]:
    """Rules §4.4: card in its project's drawer, basis exists and is approved, CHG when guarded."""

    findings: list[BasisFinding] = []
    project_dir = project_dir_of(card_file)
    if project_dir is None or not project_dir.is_relative_to(workspace_root.resolve()):
        findings.append(
            BasisFinding(
                "location",
                str(card_file),
                "新式实施卡必须放在本项目的 `<04_监控|11_监控>/01_变更管理/03_实施卡/` 下",
            )
        )
        return findings
    if _skip(card_file.resolve(), workspace_root.resolve()):
        findings.append(BasisFinding("location", str(card_file), "实施卡不能放在 archive 目录里"))
    pid = _project_id(project_dir)
    if project_id is not None and project_id != pid:
        findings.append(
            BasisFinding("location", str(card_file), f"实施卡属于项目 {pid}，与 Work 的项目 {project_id} 不一致")
        )
    name = NEW_CARD_NAME.match(card_file.name)
    if name and name.group(1) != f"CARD-{pid}":
        findings.append(
            BasisFinding("location", card_file.name, f"卡号前缀应为 CARD-{pid}-，实际为 {name.group(1)}-")
        )

    monitor_dir = card_file.resolve().parent.parent.parent
    findings.extend(_basis_rule(header, project_dir, monitor_dir, workspace_root, pid))
    findings.extend(_change_rule(header, monitor_dir, paths, workspace_root.resolve()))
    return findings


def _basis_rule(
    header: CardHeader, project_dir: Path, monitor_dir: Path, workspace_root: Path, pid: str
) -> list[BasisFinding]:
    if not header.basis_raw:
        return [BasisFinding("basis", "依据", "新式实施卡缺少机器可读头部 `依据：`")]
    if len(header.basis_raw) > 1:
        return [BasisFinding("basis", "依据", f"头部字段 `依据：` 重复出现 {len(header.basis_raw)} 次")]
    if not header.basis or _PLACEHOLDER.search(header.basis_raw[0]):
        return [BasisFinding("placeholder", "依据", f"依据仍是空的或占位符: {header.basis_raw[0]}")]

    findings: list[BasisFinding] = []
    bcs = [item for item in header.basis if item.startswith("BC-")]
    reqs = [item for item in header.basis if item.startswith("REQ-")]
    docs = [item for item in header.basis if "/" in item or item.endswith(".md")]
    items = [item for item in header.basis if item not in bcs and item not in reqs and item not in docs]
    for item in reqs:
        finding = _req_checklist_finding(item, project_dir, pid)
        if finding is not None:
            findings.append(finding)
    for item in header.basis:
        if item.startswith("CHG-"):
            findings.append(BasisFinding("basis", item, "CHG 变更单写在 `变更单：` 一栏，不能当作依据"))
    items = [item for item in items if not item.startswith("CHG-")]

    if bcs:
        bc_ids = [item for item in bcs if BC_ID.fullmatch(item)]
        for item in bcs:
            if item not in bc_ids:
                findings.append(BasisFinding("basis", item, "业务变更编号格式应为 BC-<项目号>-<年>_<月>_<三位序号>（旧编号 BC-<项目号>-<三位序号>）"))
            elif not item.startswith(f"BC-{pid}-"):
                findings.append(BasisFinding("basis", item, f"依据的业务变更不属于本项目 {pid}"))
        record = monitor_dir.joinpath(CHANGE_CABINET, *BC_RECORD)
        if not record.is_file():
            findings.append(
                BasisFinding("basis", "02_业务变更记录.md", "本项目变更管理柜里没有业务变更记录表")
            )
        else:
            rows = _bc_rows(record)
            for item in bc_ids:
                if not item.startswith(f"BC-{pid}-"):
                    continue
                row = rows.get(item)
                if row is None:
                    findings.append(BasisFinding("basis", item, "业务变更记录表里没有这一条"))
                    continue
                state, raised = row
                month = _BC_MONTH.search(item)
                if month and not raised.startswith(f"{month.group(1)}-{month.group(2)}"):
                    findings.append(
                        BasisFinding(
                            "basis",
                            item,
                            f"编号里的年月 {month.group(1)}_{month.group(2)} 与提出时间不符: {raised or '空'}",
                        )
                    )
                if not state.startswith(APPROVED_BC_STATES):
                    findings.append(
                        BasisFinding("basis", item, f"依据的业务变更必须是“已批”，实际为: {state or '空'}")
                    )

    doc_files: list[Path] = []
    for token in docs:
        resolved = _resolve_doc(token, project_dir, workspace_root)
        if resolved is None:
            findings.append(BasisFinding("basis", token, "依据里引用的需求文件不存在"))
        else:
            doc_files.append(resolved)
    if items:
        search = doc_files or _req_files(project_dir)
        texts = [path.read_text(encoding="utf-8", errors="replace") for path in search]
        for item in items:
            pattern = re.compile(rf"(?<![A-Za-z0-9_-]){re.escape(item)}(?![A-Za-z0-9_-])")
            if not any(pattern.search(text) for text in texts):
                findings.append(BasisFinding("basis", item, "需求条目在本项目的需求说明（*REQ*.md）里找不到"))
    if not bcs and not reqs and not items:
        findings.append(BasisFinding("basis", "依据", "依据至少要引用一条业务变更（BC）或需求条目"))
    return findings


def _change_rule(
    header: CardHeader, monitor_dir: Path, paths: Iterable[str], workspace_root: Path
) -> list[BasisFinding]:
    if not header.change:
        return [BasisFinding("change", "变更单", "新式实施卡缺少机器可读头部 `变更单：`（没有就写 `无`）")]
    if len(header.change) > 1:
        return [BasisFinding("change", "变更单", f"头部字段 `变更单：` 重复出现 {len(header.change)} 次")]
    raw = header.change[0]
    values = _BACKTICK.findall(raw) or [raw.strip()]
    if len(values) != 1:
        return [BasisFinding("change", "变更单", "一张实施卡最多挂一张变更单")]
    value = values[0].strip()
    if _PLACEHOLDER.search(value) or not value:
        return [BasisFinding("placeholder", "变更单", f"变更单仍是空的或占位符: {raw}")]
    guarded = sorted(path for path in paths if is_guarded(path, workspace_root))
    if value == NO_CHANGE:
        if guarded:
            return [
                BasisFinding(
                    "change",
                    "变更单",
                    "路径表碰到核心账本、发版指针或规范库，变更单不能写“无”: " + ", ".join(guarded),
                )
            ]
        return []
    if CHG_ID.fullmatch(value) is None:
        return [BasisFinding("change", value, "变更单编号格式应为 CHG-<领域>-<年>-<序号>，没有就写 `无`")]
    found = change_files(monitor_dir, value)
    if not found:
        return [BasisFinding("change", value, "本项目变更管理柜的 01_变更单/ 里找不到这张变更单")]
    if len(found) > 1:
        return [BasisFinding("change", value, f"本项目 01_变更单/ 里这张变更单有 {len(found)} 份，无法确定")]
    return []


@dataclass(frozen=True)
class SiblingCard:
    card_file: Path
    card_id: str
    header: CardHeader

    @property
    def open(self) -> bool:
        return self.header.state not in CLOSED_CARD_STATES


def cards_for_change(drawer: Path, change_id: str) -> list[SiblingCard]:
    """Every card in one project's card drawer that hangs under ``change_id`` (read-only)."""
    cards: list[SiblingCard] = []
    if not drawer.is_dir() or not change_id:
        return cards
    for path in sorted(drawer.glob("*.md")):
        if path.name.casefold() == "readme.md" or not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        header = parse_header(lines)
        if header.change_id == change_id:
            cards.append(SiblingCard(path, card_id_of(path), header))
    return cards


def unreadable_cards(drawer: Path) -> list[Path]:
    """Cards in the drawer that are not UTF-8 text: their change order cannot be read, so they may be siblings."""
    unreadable: list[Path] = []
    if not drawer.is_dir():
        return unreadable
    for path in sorted(drawer.glob("*.md")):
        if path.name.casefold() == "readme.md" or not path.is_file():
            continue
        try:
            path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            unreadable.append(path)
    return unreadable


def paths_overlap(left: Iterable[str], right: Iterable[str]) -> list[str]:
    right_paths = list(right)
    shared: set[str] = set()
    for one in left:
        for other in right_paths:
            if one == other or one.startswith(f"{other}/"):
                shared.add(one)
            elif other.startswith(f"{one}/"):
                shared.add(other)
    return sorted(shared)
