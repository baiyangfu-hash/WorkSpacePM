"""多项目安灯板（只读原型）- 从账本和项目文件夹读数据，生成一张 HTML 看板

用途：给项目经理看“哪个项目要我定什么”，给开发人员看“四栏里每张卡干到哪了、账本里有什么遗留”。
     设计稿：/mnt/project-files/plans/驾驶舱看板设计_20261022.md（共享文件夹）。

只读保证：
    - 账本 continuity.db 先拷到系统临时目录，再用 SQLite 只读模式打开（mode=ro + PRAGMA query_only）；
    - 利旧老驾驶舱后台时只调 PmCockpitService.snapshot()（它先把账本拷到工作空间外再只读打开），
      不调任何批准、开工、验收、收口方法；
    - 项目文件夹只读 .md / .json；git 只跑 `git log`；
    - 看板上没有任何会执行动作的按钮，更没有启动 Codex 或任何 agent 的入口。

运行方式（控制根下）：
    python -B <本脚本> --root . --out %TEMP%\\安灯板.html

输出：
    一个自包含的 HTML 文件（默认写到系统临时目录，不写进工作空间）。
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

REGISTRY_RELATIVE = Path("SYS-2026-001_WorkspaceGovernance") / "workspace_registry.json"
DB_RELATIVE = Path(".auto-pm") / "continuity.db"
SCAN_DIRS = (
    Path("0100_PLC自动化"),
    Path("01_Project自动化项目管理") / "Python自动化项目总库" / "02_在研项目",
)
PROJECT_DIR_PATTERN = re.compile(r"^((?:DJ|SW|SYS)-\d{4}-\d{3})(?:_(.+))?$")

# 驾驶舱自身和验证套件，项目经理视图里收进“工具与验证”一组。以后应搬进 workspace_registry.json。
DEFAULT_TOOL_PROJECTS = (
    "SYS-2026-001",
    "SW-2026-008",
    "SW-2026-009",
    "SW-2026-010",
    "DJ-2026-000",
    "DJ-2026-011",
)

# Mission 状态 -> 看板四栏（Mission挂起状态设计稿 §3.1）。PARKED 是设计稿新增的状态，代码里还没有。
COLUMN_OF_STATE = {
    "ACTIVE": "在干",
    "DRAFT": "等你",
    "AWAITING_APPROVAL": "等你",
    "BLOCKED": "等你",
    "ACCEPTANCE_PENDING": "等你",
    "PARKED": "搁着",
    "ACCEPTED": "已关",
    "CLOSED": "已关",
    "CANCELLED": "已关",
}
COLUMNS = ("在干", "等你", "搁着", "已关")
WAITING_ASK = {
    "DRAFT": "核对需求",
    "AWAITING_APPROVAL": "批准范围",
    "ACCEPTANCE_PENDING": "验收结果",
    "BLOCKED": "卡住了，要你拿主意",
}
STATE_LABEL = {
    "DRAFT": "草稿",
    "AWAITING_APPROVAL": "待批准",
    "ACTIVE": "在干",
    "BLOCKED": "卡住",
    "ACCEPTANCE_PENDING": "待验收",
    "PARKED": "搁着",
    "ACCEPTED": "已验收",
    "CLOSED": "已收口",
    "CANCELLED": "已作废",
}
OPEN_RUN_STATES = ("RUNNING", "VERIFYING", "BLOCKED", "PENDING", "CLAIMED")

WAITING_RED_DAYS = 3
PARKED_YELLOW_DAYS = 7
QUIET_YELLOW_DAYS = 14
RECENT_CLOSED_DAYS = 14
OPEN_SOFT_LIMIT = 8
MAX_DECISIONS = 3


@dataclass
class RunInfo:
    run_id: str
    state: str
    executor: str
    lease_expires: datetime | None
    checkpoint: str
    worktree: str
    updated_at: datetime | None


@dataclass
class MissionInfo:
    mission_id: str
    project_id: str
    title: str
    state: str
    updated_at: datetime | None
    change_id: str = ""
    closure_state: str = ""
    run: RunInfo | None = None
    example: bool = False

    @property
    def column(self) -> str:
        return COLUMN_OF_STATE.get(self.state, "等你")


@dataclass
class BusinessChange:
    change_id: str
    kind: str
    what: str
    status: str
    raised: str


@dataclass
class CardInfo:
    card_id: str
    title: str
    status: str


@dataclass
class Attention:
    project_id: str
    what: str
    since: datetime | None
    detail: str


@dataclass
class LegacyCard:
    """老驾驶舱后台 PmCockpitService.snapshot() 给这个项目的状态卡（利旧，只读）。"""

    mission_id: str
    milestone: str
    progress: str
    risk: str
    verification: str
    owner: str
    next_action: str
    user_action: str
    readable: bool


@dataclass
class Project:
    project_id: str
    name: str
    root: str
    registered: bool
    tool: bool
    missions: list[MissionInfo] = field(default_factory=list)
    changes: list[BusinessChange] = field(default_factory=list)
    cards: list[CardInfo] = field(default_factory=list)
    last_commit: datetime | None = None
    attention: list[Attention] = field(default_factory=list)
    legacy: LegacyCard | None = None


@dataclass
class Decision:
    project_id: str
    ask: str
    subject: str
    since: datetime | None
    example: bool = False


@dataclass
class Board:
    generated_at: datetime
    ledger_note: str
    projects: list[Project]
    decisions: list[Decision]
    decision_overflow: int
    example: bool = False
    legacy_note: str = ""
    legacy_notices: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- 读数据


def parse_time(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def open_ledger_read_only(db_path: Path) -> sqlite3.Connection:
    """只读打开账本；文件不存在时报错，绝不新建。"""
    if not db_path.is_file():
        raise FileNotFoundError(str(db_path))
    uri = db_path.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _tables(connection: sqlite3.Connection) -> set:
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {row[0] for row in rows}


def _short(text: str, limit: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------------------------------------------------------------- 账本读法（可切换）
#
# 两种读法，接口一样：给 (root, db_path)，吐一个只读 sqlite3 连接。
#   copy  ：本脚本自己的读法——账本连 -wal 拷到工作空间外的临时目录再 mode=ro 打开（老路线）。
#   store ：复用 auto_pm ContinuityStore._read_connection（TD-105 修过：严格只读快照，拷贝时不把
#           写账本的进程锁在外面，拷到一半账本变了会重拷）。
#   auto  ：TD-105 合进 main 后（ContinuityStore 有 close_read_snapshot）走 store，否则走 copy。
LEDGER_READERS = ("auto", "copy", "store")
TD105_MARKER = "close_read_snapshot"  # TD-105 分支（claude/td105-ui-concurrency）给 ContinuityStore 加的方法
LEDGER_READER_LABEL = {"copy": "本地拷贝", "store": "TD-105 严格只读快照"}


def continuity_store_class() -> type | None:
    """找 auto_pm 的 ContinuityStore；找不到（脚本单独拷走了）返回 None。"""
    try:
        source_root = str(Path(__file__).resolve().parent.parent)
        if source_root not in sys.path:
            sys.path.insert(0, source_root)
        from auto_pm.infrastructure.continuity_store import ContinuityStore
    except Exception:  # noqa: BLE001 - 没有 auto_pm 就只能走 copy
        return None
    return ContinuityStore


def td105_merged(store_class: type | None) -> bool:
    """这个 Store 类带不带 TD-105 的读法（None＝没有 auto_pm，按没合处理）。"""
    return store_class is not None and callable(getattr(store_class, TD105_MARKER, None))


@contextmanager
def copy_ledger_connection(root: Path, db_path: Path) -> Iterator[sqlite3.Connection]:
    """先把账本（连同 -wal）拷到工作空间外的临时目录再只读打开，账本旁边连 -shm 都不会多出来。"""
    del root
    with tempfile.TemporaryDirectory(prefix="andon-") as temporary:
        copy = Path(temporary) / db_path.name
        shutil.copyfile(db_path, copy)
        wal = db_path.with_name(db_path.name + "-wal")
        if wal.is_file():
            shutil.copyfile(wal, copy.with_name(copy.name + "-wal"))
        connection = open_ledger_read_only(copy)
        try:
            yield connection
        finally:
            connection.close()


@contextmanager
def store_ledger_connection(
    root: Path, db_path: Path, store_factory: Callable[..., object] | None = None
) -> Iterator[sqlite3.Connection]:
    """复用 ContinuityStore 的严格只读快照读法；只调 _read_connection，不 initialize、不建表。"""
    if store_factory is None:
        store_factory = continuity_store_class()
        if store_factory is None:
            raise RuntimeError("找不到 auto_pm.infrastructure.continuity_store，无法用 store 读法")
    store = store_factory(root, db_path)
    try:
        with store._read_connection() as connection:  # noqa: SLF001 - 账本读法以 Store 为准
            yield connection
    finally:
        close = getattr(store, TD105_MARKER, None)
        if callable(close):
            close()


def _within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def choose_ledger_reader(
    name: str = "auto", root: Path | None = None, db_path: Path | None = None
) -> tuple[str, Callable[[Path, Path], object]]:
    """把 auto 定成 copy 或 store，返回 (读法名, 连接工厂)。

    auto 走 store 的条件：TD-105 已合入，且账本在工作空间自己的目录下（Store 只认自己的账本，
    看别处拷来的账本仍用 copy）。
    """
    if name not in LEDGER_READERS:
        raise ValueError(f"账本读法只能是 {LEDGER_READERS}，不是 {name!r}")
    if name == "auto":
        own_ledger = root is None or db_path is None or _within(db_path, root)
        name = "store" if own_ledger and td105_merged(continuity_store_class()) else "copy"
    return name, (store_ledger_connection if name == "store" else copy_ledger_connection)


def read_ledger_copy(
    db_path: Path, now: datetime, root: Path | None = None, reader: str = "copy"
) -> tuple[list[MissionInfo], list[Attention]]:
    """按选定读法打开账本并读出卡和遗留；默认老路线 copy，原有调用不变。"""
    _name, connect = choose_ledger_reader(reader)
    with connect(root or db_path.parent.parent, db_path) as connection:  # type: ignore[attr-defined]
        return read_ledger(connection, now)


def read_ledger(
    connection: sqlite3.Connection, now: datetime
) -> tuple[list[MissionInfo], list[Attention]]:
    tables = _tables(connection)
    missions: list[MissionInfo] = []
    attention: list[Attention] = []
    if "mission_items" not in tables:
        return missions, attention

    closures: dict[str, tuple[str, str]] = {}
    if "closure_items" in tables:
        for row in connection.execute(
            "SELECT mission_id, change_id, state, updated_at, closure_id FROM closure_items"
        ):
            closures[row["mission_id"]] = (row["change_id"], row["state"])

    for row in connection.execute(
        "SELECT mission_id, subject_project_id, title, state, root_work_id, updated_at "
        "FROM mission_items"
    ):
        change_id, closure_state = closures.get(row["mission_id"], ("", ""))
        mission = MissionInfo(
            mission_id=row["mission_id"],
            project_id=row["subject_project_id"],
            title=row["title"],
            state=row["state"],
            updated_at=parse_time(row["updated_at"]),
            change_id=change_id,
            closure_state=closure_state,
        )
        if row["root_work_id"] and "run_items" in tables:
            mission.run = _latest_run(connection, row["root_work_id"], tables)
        missions.append(mission)

    if "run_items" in tables and "execution_leases" in tables:
        for row in connection.execute(
            "SELECT r.run_id, r.state, r.executor_id, w.subject_project_id, w.title, "
            "l.expires_at FROM run_items r JOIN work_items w ON w.work_id = r.work_id "
            "LEFT JOIN execution_leases l ON l.run_id = r.run_id "
            "WHERE r.state IN ({})".format(",".join("?" * len(OPEN_RUN_STATES))),
            OPEN_RUN_STATES,
        ):
            expires = parse_time(row["expires_at"])
            if expires is not None and now - expires > timedelta(days=1):
                attention.append(
                    Attention(
                        project_id=row["subject_project_id"],
                        what="执行记录没结账",
                        since=expires,
                        detail="{}（{}，状态 {}）：{}".format(
                            row["run_id"],
                            row["executor_id"],
                            row["state"],
                            _short(row["title"], 40),
                        ),
                    )
                )
    if "closure_items" in tables:
        for row in connection.execute(
            "SELECT c.closure_id, c.change_id, c.state, c.updated_at, m.subject_project_id "
            "FROM closure_items c JOIN mission_items m ON m.mission_id = c.mission_id "
            "WHERE c.state != 'COMPLETED'"
        ):
            since = parse_time(row["updated_at"])
            if since is not None and now - since > timedelta(days=1):
                attention.append(
                    Attention(
                        project_id=row["subject_project_id"],
                        what="收口停在半路",
                        since=since,
                        detail="{}（{}，状态 {}）".format(
                            row["closure_id"], row["change_id"], row["state"]
                        ),
                    )
                )
    if "work_items" in tables:
        for row in connection.execute(
            "SELECT work_id, subject_project_id, title, updated_at FROM work_items "
            "WHERE state = 'BLOCKED'"
        ):
            attention.append(
                Attention(
                    project_id=row["subject_project_id"],
                    what="工作项卡住",
                    since=parse_time(row["updated_at"]),
                    detail="{}：{}".format(row["work_id"], _short(row["title"], 40)),
                )
            )
    return missions, attention


def _latest_run(connection: sqlite3.Connection, work_id: str, tables: set) -> RunInfo | None:
    row = connection.execute(
        "SELECT run_id, state, executor_id, worktree_path, updated_at FROM run_items "
        "WHERE work_id = ? ORDER BY updated_at DESC LIMIT 1",
        (work_id,),
    ).fetchone()
    if row is None:
        return None
    expires = None
    if "execution_leases" in tables:
        lease = connection.execute(
            "SELECT expires_at FROM execution_leases WHERE run_id = ?", (row["run_id"],)
        ).fetchone()
        expires = parse_time(lease["expires_at"]) if lease else None
    checkpoint = ""
    if "checkpoints" in tables:
        point = connection.execute(
            "SELECT summary FROM checkpoints WHERE run_id = ? ORDER BY sequence DESC LIMIT 1",
            (row["run_id"],),
        ).fetchone()
        checkpoint = point["summary"] if point else ""
    return RunInfo(
        run_id=row["run_id"],
        state=row["state"],
        executor=row["executor_id"],
        lease_expires=expires,
        checkpoint=checkpoint,
        worktree=row["worktree_path"],
        updated_at=parse_time(row["updated_at"]),
    )


def discover_projects(root: Path, tool_projects: Iterable[str]) -> list[Project]:
    tool_set = set(tool_projects)
    found: dict[str, Project] = {}
    registry_path = root / REGISTRY_RELATIVE
    if registry_path.is_file():
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        for entry in registry.get("projects", []):
            project_root = entry.get("project_root", "")
            match = PROJECT_DIR_PATTERN.match(Path(project_root).name)
            found[entry["project_id"]] = Project(
                project_id=entry["project_id"],
                name=(match.group(2) or "") if match else "",
                root=project_root,
                registered=True,
                tool=entry["project_id"] in tool_set,
            )
    for scan in SCAN_DIRS:
        base = root / scan
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            match = PROJECT_DIR_PATTERN.match(child.name)
            if not child.is_dir() or not match or match.group(1) in found:
                continue
            found[match.group(1)] = Project(
                project_id=match.group(1),
                name=match.group(2) or "",
                root=(scan / child.name).as_posix(),
                registered=False,
                tool=match.group(1) in tool_set,
            )
    return list(found.values())


def _change_dirs(project_root: Path) -> list[Path]:
    return [path for path in sorted(project_root.glob("*/01_变更管理")) if path.is_dir()]


def read_business_changes(project_root: Path) -> list[BusinessChange]:
    changes: list[BusinessChange] = []
    for folder in _change_dirs(project_root):
        record = folder / "02_变更记录" / "02_业务变更记录.md"
        if not record.is_file():
            continue
        header: list[str] = []
        for line in record.read_text(encoding="utf-8").splitlines():
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if "编号" in cells and "状态" in cells:
                header = cells
                continue
            if header and cells and cells[0].startswith("BC-"):
                row = dict(zip(header, cells, strict=False))
                changes.append(
                    BusinessChange(
                        change_id=cells[0],
                        kind=row.get("类型", ""),
                        what=row.get("改了什么（原来 → 改成）", row.get("改了什么", "")),
                        status=row.get("状态", ""),
                        raised=row.get("提出日期", ""),
                    )
                )
    return changes


def read_cards(project_root: Path) -> list[CardInfo]:
    cards: list[CardInfo] = []
    for folder in _change_dirs(project_root):
        for path in sorted((folder / "03_实施卡").glob("CARD-*.md")):
            title, status = path.stem, ""
            for line in path.read_text(encoding="utf-8").splitlines()[:15]:
                if line.startswith("# ") and title == path.stem:
                    title = line[2:].strip()
                if line.startswith("> 状态"):
                    status = line.split("：", 1)[-1].strip()
            card_id = path.stem.split("_", 1)[0]
            cards.append(CardInfo(card_id=card_id, title=title, status=status))
    return cards


def git_last_commit(root: Path, project_root: str) -> datetime | None:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", project_root],
            cwd=str(root),
            capture_output=True,
            encoding="utf-8",
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_time(result.stdout.strip()) if result.returncode == 0 else None


# ---------------------------------------------------------------- 判灯与“要你定”


def lamp(project: Project, now: datetime) -> tuple[str, str]:
    """返回（灯色, 一句话原因）。灯色：red / amber / green / idle。"""
    if not project.registered:
        return "idle", "还没接入驾驶舱，只看得到文件夹里的记录"
    open_missions = [m for m in project.missions if m.column != "已关"]
    for mission in open_missions:
        if mission.state == "BLOCKED":
            return "red", "有卡住的活，要你拿主意"
        if mission.column == "等你" and _days(now, mission.updated_at) > WAITING_RED_DAYS:
            return "red", f"有一件等你超过 {WAITING_RED_DAYS} 天"
    for mission in open_missions:
        if mission.column == "搁着" and _days(now, mission.updated_at) > PARKED_YELLOW_DAYS:
            return "amber", f"有一张搁了超过 {PARKED_YELLOW_DAYS} 天"
    if len(open_missions) > OPEN_SOFT_LIMIT:
        return "amber", f"开着的卡超过 {OPEN_SOFT_LIMIT} 张"
    if project.attention:
        return "amber", f"账本里有 {len(project.attention)} 条遗留要清"
    if open_missions:
        latest = max((m.updated_at for m in open_missions if m.updated_at), default=None)
        if _days(now, latest) > QUIET_YELLOW_DAYS:
            return "amber", f"有活开着，但 {QUIET_YELLOW_DAYS} 天没动静"
        return "green", "正常推进"
    return "green", "没有开着的活"


def _days(now: datetime, moment: datetime | None) -> float:
    if moment is None:
        return 0.0
    return (now - moment).total_seconds() / 86400


# 老驾驶舱的 user_action -> “要你定”里的说法。看板只列出来，不提供老界面那种按钮。
LEGACY_ASK = {
    "CONFIRM_START": "确认开工",
    "CONFIRM_ACCEPTANCE": "验收结果",
    "REVIEW_ESCALATION": "看升级的事",
    "RETRY_SYNC": "收口同步没完成（交主执行重试）",
}


def read_legacy(
    root: Path, service_factory: Callable[[Path], object] | None = None
) -> tuple[dict[str, LegacyCard], list[Decision], list[str], str]:
    """利旧老驾驶舱后台：只调只读的 snapshot()，绝不调 approve/confirm/start/close。"""
    try:
        if service_factory is None:
            source_root = str(Path(__file__).resolve().parent.parent)
            if source_root not in sys.path:
                sys.path.insert(0, source_root)
            from auto_pm.application.core.pm_cockpit_service import PmCockpitService

            service_factory = PmCockpitService
        snapshot = service_factory(root).snapshot()  # type: ignore[attr-defined]
    except Exception as error:  # noqa: BLE001 - 老后台出任何问题都退回只读 SQL，不让看板挂掉
        return {}, [], [], f"没接上老驾驶舱后台（{type(error).__name__}），只用账本只读数据"
    cards: dict[str, LegacyCard] = {}
    for card in snapshot.projects:
        action = getattr(card.user_action, "value", str(card.user_action))
        cards[card.project_id] = LegacyCard(
            mission_id=card.mission_id,
            milestone=card.milestone,
            progress=card.progress,
            risk=card.risk,
            verification=card.verification,
            owner=card.current_owner,
            next_action=card.next_user_action,
            user_action=action,
            readable="无法读取" not in card.verification and card.milestone != "等待连续性记录",
        )
    pending = [
        Decision(
            project_id=item.project_id,
            ask="批准范围",
            subject=_short(item.objective, 46),
            since=parse_time(item.submitted_at),
        )
        for item in snapshot.pending_cards
    ]
    return cards, pending, list(snapshot.notices), "状态卡措辞来自老驾驶舱后台（只读）"


def collect_decisions(
    projects: list[Project], extra: Iterable[Decision] = ()
) -> tuple[list[Decision], int]:
    decisions: list[Decision] = list(extra)
    ordered = sorted(projects, key=lambda p: (p.tool, p.project_id))
    for project in ordered:
        legacy = project.legacy
        legacy_ask = LEGACY_ASK.get(legacy.user_action, "") if legacy and legacy.readable else ""
        covered = False
        for mission in project.missions:
            if mission.column == "等你":
                ask = WAITING_ASK.get(mission.state, "看一眼")
                if legacy_ask and legacy is not None and legacy.mission_id == mission.mission_id:
                    ask, covered = legacy_ask, True
                decisions.append(
                    Decision(
                        project_id=project.project_id,
                        ask=ask,
                        subject=_short(mission.title, 46),
                        since=mission.updated_at,
                        example=mission.example,
                    )
                )
        if legacy_ask and not covered and legacy is not None:
            decisions.append(
                Decision(
                    project_id=project.project_id,
                    ask=legacy_ask,
                    subject=_short(legacy.next_action, 46),
                    since=None,
                )
            )
        for change in project.changes:
            if change.status.startswith("待批"):
                decisions.append(
                    Decision(
                        project_id=project.project_id,
                        ask="批准业务变更 " + change.change_id,
                        subject=_short(change.what, 46),
                        since=parse_time(change.raised),
                    )
                )
        for card in project.cards:
            if card.status.startswith("待批"):
                decisions.append(
                    Decision(
                        project_id=project.project_id,
                        ask="批准派工 " + card.card_id,
                        subject=_short(card.title, 46),
                        since=None,
                    )
                )
    oldest_first = sorted(
        decisions,
        key=lambda d: d.since or datetime.max.replace(tzinfo=UTC),
    )
    return oldest_first[:MAX_DECISIONS], max(0, len(oldest_first) - MAX_DECISIONS)


def build_board(
    root: Path,
    db_path: Path | None,
    now: datetime,
    tool_projects: Iterable[str] = DEFAULT_TOOL_PROJECTS,
    use_git: bool = True,
    use_legacy: bool = True,
    legacy_factory: Callable[[Path], object] | None = None,
    ledger_reader: str = "auto",
) -> Board:
    projects = discover_projects(root, tool_projects)
    by_id = {project.project_id: project for project in projects}
    ledger_note = "没找到账本，只显示文件夹里的记录"
    if db_path is not None and db_path.is_file():
        reader_name, _connect = choose_ledger_reader(ledger_reader, root, db_path)
        missions, attention = read_ledger_copy(db_path, now, root, reader_name)
        ledger_note = f"账本只读：{db_path.name}（{LEDGER_READER_LABEL[reader_name]}）"
        for mission in missions:
            project = by_id.get(mission.project_id)
            if project is None:
                project = Project(mission.project_id, "", "", True, False)
                by_id[mission.project_id] = project
                projects.append(project)
            project.missions.append(mission)
        for item in attention:
            if item.project_id in by_id:
                by_id[item.project_id].attention.append(item)
    for project in projects:
        if project.root:
            project_root = root / project.root
            project.changes = read_business_changes(project_root)
            project.cards = read_cards(project_root)
            if use_git:
                project.last_commit = git_last_commit(root, project.root)
    pending: list[Decision] = []
    legacy_note, legacy_notices = "", []
    # 老后台只认 <root>/.auto-pm/continuity.db；--db 指到别处时不混用两份账本。
    default_db = (root / DB_RELATIVE).resolve()
    if use_legacy and db_path is not None and db_path.is_file() and db_path.resolve() == default_db:
        cards, pending, legacy_notices, legacy_note = read_legacy(root, legacy_factory)
        for project_id, card in cards.items():
            if project_id in by_id:
                by_id[project_id].legacy = card
    decisions, overflow = collect_decisions(projects, pending)
    return Board(
        now, ledger_note, projects, decisions, overflow, False, legacy_note, legacy_notices
    )


def add_examples(board: Board, now: datetime) -> Board:
    """在内存里叠加几张“示例”卡，演示四栏都有活时的样子。不碰账本。"""
    target = next((p for p in board.projects if p.project_id.startswith("DJ-2026-009")), None)
    if target is None:
        return board
    samples = [
        (
            "ACTIVE",
            "CARD-DJ-2026-009-001 Modbus TCP 客户端通讯层",
            0.2,
            "Trae",
            "已写完读寄存器，差写回和断线测试",
        ),
        (
            "ACCEPTANCE_PENDING",
            "CARD-DJ-2026-009-002 握手中途断线撤销允许信号",
            1.5,
            "Claude",
            "仿真 6 条用例全过，等你验收",
        ),
        (
            "AWAITING_APPROVAL",
            "CARD-DJ-2026-009-003 安全区 7 点（急停、安全门复位后不自启）",
            0.6,
            "",
            "",
        ),
        (
            "PARKED",
            "HMI 报警页改版（客户插急活，先搁着）",
            9.0,
            "Trae",
            "报警表做完一半，断点：ALM_021 之后",
        ),
    ]
    for index, (state, title, age, executor, checkpoint) in enumerate(samples, start=1):
        moment = now - timedelta(days=age)
        run = None
        if executor:
            run = RunInfo(
                run_id=f"RUN-示例-{index}",
                state="RUNNING" if state == "ACTIVE" else "BLOCKED",
                executor=executor,
                lease_expires=now + timedelta(minutes=40) if state == "ACTIVE" else None,
                checkpoint=checkpoint,
                worktree=f".auto-pm/worktrees/{executor.lower()}",
                updated_at=moment,
            )
        target.missions.append(
            MissionInfo(
                mission_id=f"MISSION-示例-{index}",
                project_id=target.project_id,
                title=title,
                state=state,
                updated_at=moment,
                run=run,
                example=True,
            )
        )
    target.registered = True
    decisions, overflow = collect_decisions(board.projects)
    return Board(
        board.generated_at,
        board.ledger_note,
        board.projects,
        decisions,
        overflow,
        True,
        board.legacy_note,
        board.legacy_notices,
    )


# ---------------------------------------------------------------- 画页面

CSS = """
/* 布局：上面一条“要你定”，下面一行一个项目，像产线安灯板；开发视图按四栏排卡。 */
:root {
  --bg: #eef1f4; --panel: #ffffff; --ink: #1b2430; --muted: #5d6b7a; --rule: #d3dae2;
  --accent: #1f5fa8; --chip: #e3e9f0;
  --ok: #1f8a4c; --warn: #c27a00; --bad: #c63b2f; --idle: #8a96a3;
  --font-body: "Noto Sans SC", "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
  --font-mono: "JetBrains Mono", "Cascadia Mono", Consolas, ui-monospace, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #11161c; --panel: #19212a; --ink: #e4e9ef; --muted: #93a1b0; --rule: #2b3642;
  --accent: #6fa8ec; --chip: #24303c;
  --ok: #4cc27f; --warn: #e3a336; --bad: #ef6b5e; --idle: #6d7a87; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #11161c; --panel: #19212a; --ink: #e4e9ef; --muted: #93a1b0; --rule: #2b3642;
  --accent: #6fa8ec; --chip: #24303c;
  --ok: #4cc27f; --warn: #e3a336; --bad: #ef6b5e; --idle: #6d7a87; color-scheme: dark }
body { background: var(--bg); color: var(--ink); font-family: var(--font-body);
  font-size: 15px; line-height: 1.55; margin: 0; }
.wrap { max-width: 1180px; margin: 0 auto; padding-block: 20px 48px;
  padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px));
  display: grid; gap: 22px; }
header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 18px; }
h1 { font-size: 1.6rem; margin: 0; letter-spacing: .02em; text-wrap: balance; }
h2 { font-size: 1.05rem; margin: 0 0 10px; letter-spacing: .04em; }
.meta { color: var(--muted); font-size: .85rem; }
.mono { font-family: var(--font-mono); font-size: .82em; }
.tabs { display: flex; gap: 4px; border-bottom: 2px solid var(--rule); }
.sr { position: absolute; opacity: 0; pointer-events: none; }
.tabs label { padding: 8px 16px; cursor: pointer; color: var(--muted); font-weight: 600;
  border-bottom: 3px solid transparent; margin-bottom: -2px; }
#v-pm:focus-visible ~ .wrap label[for=v-pm], #v-dev:focus-visible ~ .wrap label[for=v-dev] {
  outline: 2px solid var(--accent); outline-offset: 2px; }
#v-pm:checked ~ .wrap label[for=v-pm], #v-dev:checked ~ .wrap label[for=v-dev] {
  color: var(--ink); border-color: var(--accent); }
.view { display: none; gap: 22px; }
#v-pm:checked ~ .wrap #pm, #v-dev:checked ~ .wrap #dev { display: grid; }
.decide { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
.ask { background: var(--panel); border: 1px solid var(--rule); border-left: 5px solid var(--warn);
  padding: 12px 14px; display: grid; gap: 4px; min-width: 0; }
.ask b { font-size: 1rem; }
.none { color: var(--muted); background: var(--panel); border: 1px dashed var(--rule);
  padding: 12px 14px; }
.board { display: grid; gap: 0; background: var(--panel); border: 1px solid var(--rule); }
.row { display: grid; grid-template-columns: 30px minmax(0, 2.2fr) minmax(0, 2fr) minmax(0, 2.6fr);
  gap: 6px 16px; padding: 12px 14px; border-top: 1px solid var(--rule); align-items: start; }
.row:first-child { border-top: 0; }
.row.head { color: var(--muted); font-size: .8rem; letter-spacing: .06em; padding-block: 8px; }
.lampdot { width: 18px; height: 18px; border-radius: 50%; margin-top: 3px;
  box-shadow: inset 0 0 0 3px rgba(255,255,255,.25); }
.red { background: var(--bad); } .amber { background: var(--warn); }
.green { background: var(--ok); } .idle { background: var(--idle); }
.pid { font-family: var(--font-mono); font-weight: 600; }
.counts { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { background: var(--chip); padding: 1px 8px; font-size: .82rem; white-space: nowrap;
  font-variant-numeric: tabular-nums; }
.chip.hot { background: var(--warn); color: var(--panel); }
.small { font-size: .85rem; color: var(--muted); }
.ex { font-size: .72rem; border: 1px solid var(--warn); color: var(--warn); padding: 0 5px;
  margin-left: 6px; white-space: nowrap; }
details { background: var(--panel); border: 1px solid var(--rule); }
details > summary { cursor: pointer; padding: 10px 14px; font-weight: 600; }
details > .board { border: 0; border-top: 1px solid var(--rule); }
details.prow { border: 0; border-top: 1px solid var(--rule); background: transparent; }
details.prow > summary.row { border-top: 0; font-weight: 400; list-style: none; }
details.prow > summary.row::-webkit-details-marker { display: none; }
details.prow > summary:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
.open { color: var(--accent); }
details.prow[open] .open { display: none; }
.more { padding: 0 14px 14px 60px; display: grid; gap: 8px; min-width: 0; }
.scroll { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: .85rem; }
th, td { text-align: left; vertical-align: top; padding: 6px 8px; border-bottom: 1px solid var(--rule); }
th { color: var(--muted); font-weight: 600; white-space: nowrap; }
.timeline { display: grid; gap: 6px; background: var(--panel); border: 1px solid var(--rule);
  padding: 12px 14px 12px 2em; }
.legend { display: flex; flex-wrap: wrap; gap: 8px 22px; font-size: .85rem; color: var(--muted); }
.legend span { display: inline-flex; align-items: center; gap: 6px; }
.legend i { width: 11px; height: 11px; border-radius: 50%; display: inline-block; }
.proj { background: var(--panel); border: 1px solid var(--rule); padding: 14px; display: grid;
  gap: 12px; min-width: 0; }
.cols { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.col { display: grid; gap: 8px; align-content: start; min-width: 0; }
.col h3 { font-size: .85rem; margin: 0; color: var(--muted); letter-spacing: .06em; }
.card { border: 1px solid var(--rule); padding: 8px 10px; display: grid; gap: 3px; min-width: 0;
  overflow-wrap: anywhere; font-size: .88rem; }
.card .t { font-weight: 600; }
.health { display: grid; gap: 6px; }
.health li { overflow-wrap: anywhere; }
ul { margin: 0; padding-left: 1.2em; }
footer { color: var(--muted); font-size: .8rem; }
@media (max-width: 760px) {
  .more { padding-left: 14px; }
  .row { grid-template-columns: 24px minmax(0, 1fr); }
  .row > :nth-child(n+3) { grid-column: 2; }
  .row.head { display: none; }
  .cols { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
}
@media (max-width: 440px) { .cols { grid-template-columns: minmax(0, 1fr); } }
"""

# 只负责“带 #dev 打开时直接显示开发人员视图”；切换本身是纯 CSS。
SCRIPT = """
if (location.hash === '#dev') { document.getElementById('v-dev').checked = true; }
"""


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _when(moment: datetime | None, offset: timezone) -> str:
    return moment.astimezone(offset).strftime("%m-%d %H:%M") if moment else "—"


def _ago(now: datetime, moment: datetime | None) -> str:
    if moment is None:
        return ""
    days = _days(now, moment)
    if days < 1:
        return "不到 1 天"
    return f"{int(days)} 天"


def _example_tag(flag: bool) -> str:
    return '<span class="ex">示例</span>' if flag else ""


def _recent_closed(project: Project, now: datetime) -> list[MissionInfo]:
    return [
        m
        for m in project.missions
        if m.column == "已关" and _days(now, m.updated_at) <= RECENT_CLOSED_DAYS
    ]


def render_pm(board: Board, offset: timezone) -> str:
    now = board.generated_at
    parts = ['<section id="pm" class="view">']
    parts.append(f"<div><h2>要你定（最多 {MAX_DECISIONS} 件，最久的排前面）</h2>")
    if board.decisions:
        parts.append('<div class="decide">')
        for item in board.decisions:
            parts.append(
                '<div class="ask"><span class="pid">{}</span><b>{}{}</b><span>{}</span>'
                '<span class="small">{} · 定法在线程里回一句话，不在这里点</span></div>'.format(
                    _e(item.project_id),
                    _e(item.ask),
                    _example_tag(item.example),
                    _e(item.subject),
                    _e("等了 " + _ago(now, item.since) if item.since else "日期未记"),
                )
            )
        parts.append("</div>")
        if board.decision_overflow:
            parts.append(
                f'<p class="small">还有 {board.decision_overflow} 件排在后面，前面定完再给你。</p>'
            )
    else:
        parts.append('<div class="none">目前没有要你定的事。</div>')
    parts.append("</div>")

    business = [p for p in board.projects if not p.tool]
    tools = [p for p in board.projects if p.tool]
    parts.append(f"<div><h2>在研项目</h2>{_pm_table(business, now, offset)}</div>")
    events = recent_events(board)
    parts.append("<div><h2>最近 7 天动态</h2>")
    if events:
        parts.append('<ul class="timeline">')
        for moment, project_id, text, example, date_only in events:
            stamp = moment.strftime("%m-%d") if date_only else _when(moment, offset)
            parts.append(
                f'<li><span class="small mono">{_e(stamp)}</span> '
                f'<span class="pid">{_e(project_id)}</span> {_e(text)}{_example_tag(example)}</li>'
            )
        parts.append("</ul>")
    else:
        parts.append('<div class="none">这 7 天账本和变更记录里都没有新动静。</div>')
    parts.append("</div>")
    parts.append(
        f"<details><summary>工具与验证项目（{len(tools)} 个，驾驶舱自己和测试台）</summary>"
        f"{_pm_table(tools, now, offset)}</details>"
    )
    parts.append(
        '<div class="legend">'
        f'<span><i class="red"></i>红：有卡住的，或等你超过 {WAITING_RED_DAYS} 天</span>'
        f'<span><i class="amber"></i>黄：搁着超过 {PARKED_YELLOW_DAYS} 天、'
        f"开着超过 {OPEN_SOFT_LIMIT} 张、账本有遗留，或 {QUIET_YELLOW_DAYS} 天没动静</span>"
        '<span><i class="green"></i>绿：正常</span>'
        '<span><i class="idle"></i>灰：还没接入驾驶舱</span></div>'
    )
    parts.append("</section>")
    return "".join(parts)


def _pm_table(projects: list[Project], now: datetime, offset: timezone) -> str:
    if not projects:
        return '<div class="none">没有。</div>'
    rows = [
        '<div class="board"><div class="row head"><span></span><span>项目</span>'
        "<span>四栏</span><span>最近一条业务变更</span></div>"
    ]
    # 红灯排最前，灰灯（未接入）排最后；30 个项目时要先看到出事的。
    rank = {"red": 0, "amber": 1, "green": 2, "idle": 3}
    for project in sorted(projects, key=lambda p: (rank[lamp(p, now)[0]], p.project_id)):
        color, reason = lamp(project, now)
        counts = dict.fromkeys(COLUMNS, 0)
        for mission in project.missions:
            if mission.column != "已关":
                counts[mission.column] += 1
        counts["已关"] = len(_recent_closed(project, now))
        chips = "".join(
            '<span class="chip{}">{} {}</span>'.format(
                " hot" if column == "等你" and counts[column] else "", column, counts[column]
            )
            for column in COLUMNS
        )
        doing = [m for m in project.missions if m.column == "在干"]
        doing_text = (
            "在干：" + _e(_short(doing[0].title, 34)) + _example_tag(doing[0].example)
            if doing
            else ""
        )
        latest_change = project.changes[-1] if project.changes else None
        change_text = (
            f'<span class="mono">{_e(latest_change.change_id)}</span> {_e(_short(latest_change.what, 60))}<br><span class="small">{_e(_short(latest_change.status, 40))}</span>'
            if latest_change
            else '<span class="small">还没有业务变更记录</span>'
        )
        legacy = project.legacy
        stage_text = (
            f'<br><span class="small">阶段 {_e(legacy.milestone)} · 风险 {_e(legacy.risk)}</span>'
            if legacy and legacy.readable
            else ""
        )
        moved = max(
            [m.updated_at for m in project.missions if m.updated_at]
            + ([project.last_commit] if project.last_commit else []),
            default=None,
        )
        open_text = f"点开看全部 {len(project.changes)} 条变更" if project.changes else "点开看详情"
        # 点开一行看这个项目的全部业务变更和实施卡（参考旧原型 V13 的“工程变更控制矩阵”）。
        rows.append(
            f'<details class="prow"><summary class="row">'
            f'<span class="lampdot {color}" title="{_e(reason)}"></span>'
            f'<div><span class="pid">{_e(project.project_id)}</span> {_e(project.name)}<br><span class="small">{_e(reason)} · 最后动静 {_e(_when(moved, offset))}</span>{stage_text}</div>'
            f'<div class="counts">{chips}<span class="small" style="flex-basis:100%">{doing_text}</span></div>'
            f'<div>{change_text}<br><span class="open small">{open_text}</span></div>'
            f"</summary>{_project_detail(project)}</details>"
        )
    rows.append("</div>")
    return "".join(rows)


def _project_detail(project: Project) -> str:
    parts = ['<div class="more">']
    if project.changes:
        parts.append(
            '<div class="scroll"><table><thead><tr><th>编号</th><th>提出</th><th>类型</th>'
            "<th>改了什么（原来 → 改成）</th><th>状态</th></tr></thead><tbody>"
        )
        for change in reversed(project.changes):
            parts.append(
                f'<tr><td class="mono">{_e(change.change_id)}</td><td>{_e(_short(change.raised, 12))}</td>'
                f"<td>{_e(change.kind)}</td><td>{_e(_short(change.what, 160))}</td>"
                f"<td>{_e(_short(change.status, 60))}</td></tr>"
            )
        parts.append("</tbody></table></div>")
    else:
        parts.append('<p class="small">这个项目还没有业务变更记录。</p>')
    if project.cards:
        parts.append(
            '<p class="small">实施卡：'
            + "；".join(
                f"{_e(card.card_id)} {_e(_short(card.status, 30) or '状态未写')}"
                for card in project.cards
            )
            + "</p>"
        )
    parts.append(f'<p class="small mono">{_e(project.root)}</p></div>')
    return "".join(parts)


def recent_events(
    board: Board, days: int = 7, limit: int = 8
) -> list[tuple[datetime, str, str, bool, bool]]:
    """最近几天的动静（参考旧原型 V13 的“近期动态时间线”），只用账本和变更记录里已有的日期。

    每条是（时刻, 项目号, 说明, 是否示例, 是否只有日期）。
    """
    now = board.generated_at
    events: list[tuple[datetime, str, str, bool, bool]] = []
    for project in board.projects:
        for mission in project.missions:
            if mission.updated_at and _days(now, mission.updated_at) <= days:
                label = STATE_LABEL.get(mission.state, mission.state)
                text = f"{label}：{_short(mission.title, 48)}"
                events.append(
                    (mission.updated_at, project.project_id, text, mission.example, False)
                )
        for change in project.changes:
            raised = parse_time(change.raised[:10]) if change.raised[:4].isdigit() else None
            if raised and _days(now, raised) <= days:
                text = f"提出业务变更 {change.change_id}：{_short(change.what, 40)}"
                events.append((raised, project.project_id, text, False, True))
    events.sort(key=lambda item: item[0], reverse=True)
    return events[:limit]


def render_dev(board: Board, offset: timezone) -> str:
    now = board.generated_at
    parts = ['<section id="dev" class="view">']
    shown = [
        p
        for p in sorted(board.projects, key=lambda p: (p.tool, p.project_id))
        if any(m.column != "已关" for m in p.missions) or _recent_closed(p, now) or p.cards
    ]
    if not shown:
        parts.append(
            f'<div class="none">账本里没有开着的卡，近 {RECENT_CLOSED_DAYS} 天也没有收口。</div>'
        )
    for project in shown:
        parts.append(
            f'<div class="proj"><div><span class="pid">{_e(project.project_id)}</span> {_e(project.name)} <span class="small">{_e(project.root)}</span></div>'
        )
        if project.legacy is not None:
            legacy = project.legacy
            parts.append(
                '<div class="small">老驾驶舱后台：'
                + (
                    f"{_e(legacy.progress)} · 验证 {_e(legacy.verification)} · 负责 {_e(legacy.owner)}"
                    if legacy.readable
                    else "这个项目的记录它读不了，下面四栏来自账本只读数据"
                )
                + "</div>"
            )
        parts.append('<div class="cols">')
        for column in COLUMNS:
            missions = (
                _recent_closed(project, now)
                if column == "已关"
                else [m for m in project.missions if m.column == column]
            )
            missions.sort(key=lambda m: m.updated_at or now, reverse=True)
            parts.append(f'<div class="col"><h3>{column} · {len(missions)}</h3>')
            for mission in missions[:6]:
                parts.append(_dev_card(mission, now, offset))
            if len(missions) > 6:
                parts.append(f'<span class="small">另有 {len(missions) - 6} 张</span>')
            parts.append("</div>")
        parts.append("</div>")
        if project.cards:
            parts.append(
                '<div class="small">实施卡（文件夹）：{}</div>'.format(
                    "；".join(
                        "{} {}".format(_e(card.card_id), _e(_short(card.status, 24) or "状态未写"))
                        for card in project.cards
                    )
                )
            )
        parts.append("</div>")

    if board.legacy_note:
        parts.append(f'<div class="small">{_e(board.legacy_note)}</div>')
    if board.legacy_notices:
        parts.append(
            '<div><h2>老驾驶舱后台的提示</h2><ul class="health">'
            + "".join(f"<li>{_e(note)}</li>" for note in board.legacy_notices)
            + "</ul></div>"
        )
    issues = [item for p in board.projects for item in p.attention]
    parts.append(f"<div><h2>账本遗留（{len(issues)} 条，交主执行清理，不在看板上动）</h2>")
    if issues:
        parts.append('<ul class="health">')
        for item in sorted(issues, key=lambda i: (i.project_id, i.since or now)):
            parts.append(
                f'<li><span class="pid">{_e(item.project_id)}</span> {_e(item.what)} · {_e(_when(item.since, offset))}<br><span class="small mono">{_e(item.detail)}</span></li>'
            )
        parts.append("</ul>")
    else:
        parts.append('<div class="none">没有遗留。</div>')
    parts.append("</div></section>")
    return "".join(parts)


def _dev_card(mission: MissionInfo, now: datetime, offset: timezone) -> str:
    lines = [
        f'<div class="card"><span class="t">{_e(_short(mission.title, 70))}{_example_tag(mission.example)}</span>',
        f'<span class="small mono">{_e(mission.mission_id)} · {_e(STATE_LABEL.get(mission.state, mission.state))}</span>',
    ]
    run = mission.run
    if run is not None and mission.column != "已关":
        lease = (
            "租约到 " + _when(run.lease_expires, offset)
            if run.lease_expires and run.lease_expires > now
            else "未持租约"
        )
        lines.append(
            f'<span class="small">{_e(run.executor)} · {_e(run.state)} · {_e(lease)}</span>'
        )
        if run.checkpoint:
            lines.append(f'<span class="small">断点：{_e(_short(run.checkpoint, 60))}</span>')
    if mission.change_id:
        lines.append(
            '<span class="small mono">{} · 收口 {}</span>'.format(
                _e(mission.change_id), _e(mission.closure_state or "未开始")
            )
        )
    lines.append(f'<span class="small">更新 {_e(_when(mission.updated_at, offset))}</span></div>')
    return "".join(lines)


def render_page(board: Board, offset: timezone, fragment: bool = False) -> str:
    title = "多项目安灯板"
    note = "含示例卡（标“示例”的不是真数据）" if board.example else ""
    body = (
        '<input type="radio" name="v" id="v-pm" class="sr" checked>'
        '<input type="radio" name="v" id="v-dev" class="sr">'
        f'<div class="wrap"><header><h1>{_e(title)}</h1><span class="meta">数据截至 {_e(_when(board.generated_at, offset))} · {_e(board.ledger_note)} {_e(note)}</span></header>'
        '<nav class="tabs"><label for="v-pm">项目经理</label><label for="v-dev">开发人员</label></nav>'
        f"{render_pm(board, offset)}{render_dev(board, offset)}"
        "<footer>只读看板：读账本和项目文件夹，不写任何东西；页面上没有执行按钮。"
        "要定的事在线程里回一句话，由主执行去办。</footer></div>"
    )
    head = (
        f'<title>{_e(title)}</title><meta name="claude:viewport-fit-sides" content="cover">'
        '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:'
        'wght@400;600&family=Noto+Sans+SC:wght@400;600;700&display=swap">'
        f"<style>{CSS}</style>"
    )
    script = f"<script>{SCRIPT}</script>"
    if fragment:
        return head + body + script
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
        f"{head}</head><body>{body}{script}</body></html>"
    )


# ---------------------------------------------------------------- 命令行


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="多项目安灯板（只读）")
    parser.add_argument("--root", default=".", help="工作空间根（控制根）")
    parser.add_argument("--db", default="", help="账本路径，默认 <root>/.auto-pm/continuity.db")
    parser.add_argument("--out", default="", help="输出 HTML，默认写到系统临时目录")
    parser.add_argument("--now", default="", help="按这个时刻判灯（ISO 时间），默认现在")
    parser.add_argument("--utc-offset", type=float, default=None, help="显示用时区，如 -7")
    parser.add_argument("--examples", action="store_true", help="叠加几张示例卡（只在内存里）")
    parser.add_argument("--fragment", action="store_true", help="只输出页面片段（发布用）")
    parser.add_argument("--no-git", action="store_true", help="不读 git 最后提交时间")
    parser.add_argument(
        "--no-legacy", action="store_true", help="不调老驾驶舱后台（快，约省 20 秒）"
    )
    parser.add_argument(
        "--ledger-reader", choices=LEDGER_READERS, default="auto",
        help="账本读法：copy 本地拷贝；store 复用 ContinuityStore 严格只读快照（TD-105）；auto 按 TD-105 是否合入自动选",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    db_path = Path(args.db) if args.db else root / DB_RELATIVE
    now = parse_time(args.now) if args.now else datetime.now(UTC)
    if now is None:
        parser.error("--now 不是合法的 ISO 时间")
    offset = (
        timezone(timedelta(hours=args.utc_offset))
        if args.utc_offset is not None
        else datetime.now().astimezone().tzinfo
    )
    board = build_board(root, db_path, now, use_git=not args.no_git, use_legacy=not args.no_legacy,
                        ledger_reader=args.ledger_reader)
    if args.examples:
        board = add_examples(board, now)
    out = Path(args.out) if args.out else Path(tempfile.gettempdir()) / "安灯板.html"
    if out.resolve() == db_path.resolve():
        parser.error("输出不能指向账本")
    out.write_text(render_page(board, offset, fragment=args.fragment), encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
