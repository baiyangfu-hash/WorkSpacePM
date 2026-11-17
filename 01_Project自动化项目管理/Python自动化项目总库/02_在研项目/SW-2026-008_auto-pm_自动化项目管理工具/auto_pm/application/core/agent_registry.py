"""AI 登记表（CHG-SCPT-2026-712）：内置五个以外的 AI，由用户本人在本机登记，登记后马上能开工位、声明身份、开分支。

以前驾驶舱认得的 AI 写死在代码里（``agent_worktree_service.AGENT_ROSTER``），来一个新工具就要改代码、改规则、发版；
没登记的 AI 不带身份标记时又会被当成用户本人。现在：

* 登记表放在本机账本 ``R/.auto-pm/continuity.db`` 的 ``agent_registry`` 表（第一次登记时才建表）：账本在发布载荷之外，
  登记后立刻生效；只在本机控制根，不进 git，不用 PR，也不碰规则文件。代价是每台电脑各登记一次（一台电脑一本账，WS-001）。
* 只有用户本人能登记、注销：带任何 agent 标记都拒（``agent_markers``，和 ``pm sign-risk`` 同一口径），agent 不能自己登记自己。
  每次登记、注销都记下谁（``recorder()``，用户终端记作 ``no-agent-marker``，不冒充“用户”）、何时、从哪里（终端或看板），
  并写一条 ``events``。注销只把这一行标成 ``retired``，原来的登记记录留着。
* 名字规则：小写字母开头，2～20 位小写字母和数字；不能和内置名字、保留名重名；分支前缀固定为 ``<名字>/``。
* 读表：``use_ledger_roster(<控制根>)`` 让 ``AGENT_ROSTER`` 从这本账读登记的名字（懒读，用户终端和内置 agent 不读），
  同时让批准证据检查（``contracts.user_evidence``）把登记的名字也当成 agent 名字。读不了账本就只认内置五个（失败关闭）。
"""

from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.application.core import agent_worktree_service as stations
from auto_pm.application.core.lease_handover_service import agent_markers
from auto_pm.contracts import user_evidence
from auto_pm.infrastructure.continuity_store import (
    AGENT_REGISTRY_DDL,
    ContinuityStore,
    ContinuityStoreError,
)

# 小写字母开头，2～20 位小写字母和数字（不带横线：别名 ``<名字>-<6位十六进制>`` 才分得清基名）。
NAME = re.compile(r"[a-z][a-z0-9]{1,19}")
# 驾驶舱自己用的名字，和会被误读的名字：control-root、run-plan 是 codex/ 前缀下驾驶舱自己的分支，claims/ 是占位分支，
# main 是主干，project 是项目 Claude 的前缀；user 是用户本人（AI 不能叫这个名字），manual/ 是看板“推送 manual/ 分支”用的前缀。
# 再加上用户本人凭据格式里的固定词（board-click、gui-click、pin-<用途>、cmsg_… 等，由 user_evidence 统一给出，审计 865 §3.1）：
# 登记了这些名字，用户自己点的批准就会被当成 AI 写的。
RESERVED_NAMES = frozenset({"control-root", "run-plan", "claims", "main", "project", "user", "manual"}) | user_evidence.EVIDENCE_FORMAT_WORDS
# 只由十六进制字符组成的名字（如 deadbeef）会和凭据里的摘要、看板会话号撞上，同样不收。
_HEX_ONLY = re.compile(r"[0-9a-f]+")
VIA = ("terminal", "board")  # 从哪里登记的：用户自己的终端，或用户本人打开的看板
ACTIVE = "active"
RETIRED = "retired"
TABLE = "agent_registry"


class AgentRegistryError(RuntimeError):
    """登记表读写失败（账本没有、不是控制根、名字不合规则）。"""


class AgentRegistryRefusedError(AgentRegistryError):
    """安全检查拒绝了（agent 自己来登记、注销一个还在用的名字）；说明写清为什么、下一步怎么做。"""


@dataclass(frozen=True)
class AgentRegistration:
    name: str
    branch_prefix: str
    status: str
    registered_by: str
    registered_at: str
    source_ref: str
    retired_by: str = ""
    retired_at: str = ""

    @property
    def active(self) -> bool:
        return self.status == ACTIVE

    def as_json(self) -> dict[str, object]:
        return {
            "name": self.name,
            "branch_prefix": self.branch_prefix,
            "status": self.status,
            "registered_by": self.registered_by,
            "registered_at": self.registered_at,
            "source_ref": self.source_ref,
            "retired_by": self.retired_by,
            "retired_at": self.retired_at,
        }


def name_problem(name: str) -> str:
    """``name`` 为什么不能登记；能登记返回空串。"""

    if not NAME.fullmatch(name):
        return f"名字“{name[:40]}”不合规则：小写字母开头，2～20 位小写字母和数字（不带横线、空格、大写）"
    if name in stations.BUILTIN_ROSTER:
        return f"{name} 是内置的名字，本来就认得，不用登记"
    if name in user_evidence.EVIDENCE_FORMAT_WORDS:
        return f"{name} 是用户本人批准凭据格式里的固定词（如 user-confirmation:board-click:…），登记了会让你自己的批准被当成 AI 写的，换一个"
    if name in RESERVED_NAMES:
        return f"{name} 是驾驶舱保留的名字（{'、'.join(sorted(RESERVED_NAMES - user_evidence.EVIDENCE_FORMAT_WORDS))}），换一个"
    if _HEX_ONLY.fullmatch(name):
        return f"{name} 只由十六进制字符组成，会和批准凭据里的摘要撞上，换一个（里面加一个 g～z 的字母就行）"
    return ""


def user_only_refusal(action: str) -> str:
    """带任何 agent 标记时为什么不能 ``action``；用户本人（没有标记）返回空串。"""

    markers = agent_markers(os.environ)
    if not markers:
        return ""
    return (
        f"这是 agent 会话（{'、'.join(markers)}），不能{action}：登记表只限用户本人改，agent 不能登记或注销自己。"
        "请用户本人在看板“工作树与分支”页点“登记新 AI”，或在自己的终端（不带 AUTO_PM_AGENT）运行这条命令"
    )


class AgentRegistryStore(ContinuityStore):
    """``agent_registry`` 表的读写；每次改动都在同一个事务里写一条 ``events``。"""

    @contextmanager
    def _registry_transaction(self) -> Iterator[sqlite3.Connection]:
        if not self.db_path.is_file():
            raise AgentRegistryError("本机账本还没有初始化（.auto-pm/continuity.db 不存在），没法登记；先在控制根初始化账本")
        with self._transaction() as conn:
            if not self._schema_versions(conn):
                raise AgentRegistryError("本机账本还没有初始化，拒绝建登记表")
            conn.execute(AGENT_REGISTRY_DDL)
            yield conn

    @staticmethod
    def _row(row: sqlite3.Row) -> AgentRegistration:
        return AgentRegistration(
            name=str(row["name"]),
            branch_prefix=str(row["branch_prefix"]),
            status=str(row["status"]),
            registered_by=str(row["registered_by"]),
            registered_at=str(row["registered_at"]),
            source_ref=str(row["source_ref"]),
            retired_by=str(row["retired_by"]),
            retired_at=str(row["retired_at"]),
        )

    def list_registrations(self, *, include_retired: bool = False) -> tuple[AgentRegistration, ...]:
        """登记过的 AI，按名字排。只读：不建账本也不建表；没有账本、没有表都是“一个也没登记”。"""

        if not self.db_path.is_file():
            return ()
        with self._read_connection() as conn:
            if not self._table_exists(conn, TABLE):
                return ()
            rows = conn.execute(f"SELECT * FROM {TABLE} ORDER BY name").fetchall()
        found = tuple(self._row(row) for row in rows)
        return found if include_retired else tuple(item for item in found if item.active)

    def register(self, name: str, *, by: str, source_ref: str, now: str) -> AgentRegistration:
        with self._registry_transaction() as conn:
            existing = conn.execute(f"SELECT * FROM {TABLE} WHERE name=?", (name,)).fetchone()
            if existing is not None and str(existing["status"]) == ACTIVE:
                raise AgentRegistryRefusedError(f"{name} 已经登记过了（{existing['registered_by']}，{existing['registered_at']}），不用再登记")
            values = (f"{name}/", ACTIVE, by, now, source_ref)
            if existing is None:
                conn.execute(
                    f"INSERT INTO {TABLE} (name, branch_prefix, status, registered_by, registered_at, source_ref)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (name, *values),
                )
            else:  # 注销过又登记回来：这一行改回有效，上一次的注销记在 events 里
                conn.execute(
                    f"UPDATE {TABLE} SET branch_prefix=?, status=?, registered_by=?, registered_at=?, source_ref=?,"
                    " retired_by='', retired_at='' WHERE name=?",
                    (*values, name),
                )
            self._append_event(
                conn,
                name,
                "AGENT_REGISTERED",
                {"name": name, "branch_prefix": f"{name}/", "registered_by": by, "source_ref": source_ref},
                f"agent-registry:register:{name}:{now}",
                now,
                aggregate_type="agent_registry",
            )
            row = conn.execute(f"SELECT * FROM {TABLE} WHERE name=?", (name,)).fetchone()
        return self._row(row)

    def unregister(self, name: str, *, by: str, now: str) -> AgentRegistration:
        with self._registry_transaction() as conn:
            existing = conn.execute(f"SELECT * FROM {TABLE} WHERE name=?", (name,)).fetchone()
            if existing is None or str(existing["status"]) != ACTIVE:
                raise AgentRegistryRefusedError(f"{name} 没有登记（或早已注销），没什么可注销的；`main.py agent list` 看登记表")
            conn.execute(
                f"UPDATE {TABLE} SET status=?, retired_by=?, retired_at=? WHERE name=?",
                (RETIRED, by, now, name),
            )
            self._append_event(
                conn,
                name,
                "AGENT_UNREGISTERED",
                {"name": name, "retired_by": by},
                f"agent-registry:unregister:{name}:{now}",
                now,
                aggregate_type="agent_registry",
            )
            row = conn.execute(f"SELECT * FROM {TABLE} WHERE name=?", (name,)).fetchone()
        return self._row(row)


def registered_roster(control_root: str | Path) -> dict[str, str]:
    """这本账里登记着、还有效的 AI：名字 → 分支前缀。

    本机还没有账本（新克隆、云端会话、目录已不在）就是还没人登记，回空；账本在却读不了才抛错
    （``AGENT_ROSTER`` 接住后只认内置五个，用户证据也跟着从严）。
    """

    if not (Path(control_root) / ".auto-pm" / "continuity.db").is_file():
        return {}
    store = AgentRegistryStore(control_root)
    try:
        return {item.name: item.branch_prefix for item in store.list_registrations() if not name_problem(item.name)}
    finally:
        store.close_read_snapshot()


_ROSTER_ROOT: list[str] = []  # 现在 AGENT_ROSTER 读的是哪个控制根（同一个根不重读）


def use_ledger_roster(control_root: str | Path | None) -> None:
    """从现在起，名册（工位、身份标记、分支前缀）和批准证据检查都认 ``control_root`` 这本账里登记的 AI。``None``：只认内置五个。"""

    key = "" if control_root is None else os.path.normcase(str(Path(control_root).resolve()))
    if _ROSTER_ROOT == [key]:
        return
    _ROSTER_ROOT[:] = [key]
    if control_root is None:
        stations.AGENT_ROSTER.use(None)
    else:
        root = Path(control_root)
        stations.AGENT_ROSTER.use(lambda: registered_roster(root))
    user_evidence.use_extra_agent_names(_evidence_names)


def _evidence_names() -> tuple[str, ...]:
    """批准证据检查要认的 AI 名字（内置加登记的）；登记表读不出来就抛错，证据检查据此失败关闭（审计 865 §3.2）。"""

    names = tuple(stations.AGENT_ROSTER)
    if stations.AGENT_ROSTER.read_failed:
        raise AgentRegistryError("本机 AI 登记表读不出来")
    return names


class AgentRegistryService:
    """``agent register / unregister / list`` 的业务：只限用户本人改，注销前查这个名字还有没有在用的工位和占位。"""

    def __init__(self, control_root: str | Path, *, now: datetime | None = None) -> None:
        self._root = Path(control_root).resolve()
        self._store = AgentRegistryStore(self._root)
        self._now = now

    def _stamp(self) -> str:
        return (self._now or datetime.now(UTC)).isoformat()

    def list(self, *, include_retired: bool = False) -> tuple[AgentRegistration, ...]:
        try:
            return self._store.list_registrations(include_retired=include_retired)
        except ContinuityStoreError as error:
            raise AgentRegistryError(f"登记表读不出来：{error}") from error

    def register(self, name: str, *, via: str = "terminal") -> AgentRegistration:
        refusal = user_only_refusal("登记新 AI")
        if refusal:
            raise AgentRegistryRefusedError(refusal)
        name = name.strip()
        problem = name_problem(name)
        if problem:
            raise AgentRegistryError(problem)
        if via not in VIA:
            raise AgentRegistryError(f"--via 只能是 {'、'.join(VIA)}")
        now = self._stamp()
        try:
            done = self._store.register(name, by=stations.recorder(), source_ref=f"{via}:{now}", now=now)
        except ContinuityStoreError as error:
            raise AgentRegistryError(f"没登记上：{error}") from error
        self._refresh()
        return done

    def unregister(self, name: str) -> AgentRegistration:
        refusal = user_only_refusal("注销 AI")
        if refusal:
            raise AgentRegistryRefusedError(refusal)
        name = name.strip()
        if name in stations.BUILTIN_ROSTER:
            raise AgentRegistryRefusedError(f"{name} 是内置的名字，不能注销")
        in_use = self.in_use(name)
        if in_use:
            raise AgentRegistryRefusedError(f"{name} 还在用，不能注销：{in_use}。先收工位、放下占位，再注销")
        try:
            done = self._store.unregister(name, by=stations.recorder(), now=self._stamp())
        except ContinuityStoreError as error:
            raise AgentRegistryError(f"没注销成：{error}") from error
        self._refresh()
        return done

    def in_use(self, name: str) -> str:
        """``name`` 还在哪里用着（工位目录、有效占位）；没在用返回空串。占位表读不出来也算在用（失败关闭）。"""

        found: list[str] = []
        folder = self._root / ".auto-pm" / "worktrees"
        if folder.is_dir():
            shape = re.compile(rf"{re.escape(name)}(?:-[0-9a-f]{{6}})?")
            found += [f"工位 {child.name}" for child in sorted(folder.iterdir()) if child.is_dir() and shape.fullmatch(child.name)]
        from auto_pm.application.core.claim_service import ClaimError, ClaimService

        try:
            claims = ClaimService(self._root).all_claims(fetch=False)
        except (ClaimError, OSError) as error:
            return "、".join([*found, f"占位表读不出来（{error}），判不了有没有在用的占位"])
        owner = re.compile(rf"{re.escape(name)}(?:-[0-9a-f]{{6}})?")
        found += [f"占位 {claim.card}（{claim.owner}）" for claim in claims if not claim.free and owner.fullmatch(claim.owner)]
        return "、".join(found)

    def _refresh(self) -> None:
        """登记表改了：这个进程里的名册重读一遍。"""

        _ROSTER_ROOT.clear()
        use_ledger_roster(self._root)
