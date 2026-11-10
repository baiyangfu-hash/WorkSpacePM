"""auto_pm.application.core.station_presence - who is on this computer's control root right now (D-195).

One computer has one control root and, usually, several conversations (Claude Code windows, Trae, Cursor, ...).  Until now only a
conversation that opened an alias station left a record (``.auto-pm/station-holders``); one that works straight in the control root
left nothing, so nobody could say who else was there.  This module keeps a second, separate record per conversation under
``.auto-pm/presence/<key>.json`` (runtime data, never in Git) and answers three questions, all read-only except
``record_presence``:

* ``record_presence``  - a conversation says "I am here" (agents only; the user's own terminal is not a conversation);
* ``list_presence``    - everyone who is here, with an alive / quiet / suspected-orphan verdict;
* ``orient_lines``     - the one-line summary ``pm orient`` prints.

Nothing here deletes, blocks or refuses anything: it is information.  A record that cannot be written or read is skipped, never
an error for the command that called it.  This computer only: records carry the machine name so a copied ``.auto-pm`` is not
mistaken for live sessions, and nothing crosses computers (that is a separate, later design).
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from auto_pm.application.core.agent_worktree_service import (
    _hours_since,
    _process_alive,
    _stale_hours,
    caller_agent,
    caller_alias,
    session_id,
)

SCHEMA = "presence.v1"
PRESENCE_DIR = "presence"
# A conversation that ran any worktree command in the last five minutes does not rewrite its record again.
WRITE_INTERVAL_SECONDS = 300.0
# A record not seen for this long whose process is gone is only *marked* a suspected orphan; it is never deleted here.
QUIET_HOURS = 0.5
_UNKNOWN = "?"


@dataclass(frozen=True)
class Presence:
    """One conversation's record, plus the verdict computed now."""

    key: str
    alias: str
    source: str
    machine: str
    pid: int
    where: str  # "station" | "control-root" | "other"
    title: str
    opened_at: str
    seen_at: str
    silent_hours: float | None
    verdict: str  # "alive" | "quiet" | "orphan" | "elsewhere"
    reason: str


def _folder(control_root: str | Path) -> Path:
    return Path(control_root) / ".auto-pm" / PRESENCE_DIR


def _key(alias: str, pid: int) -> str:
    """A stable, file-name-safe id: the conversation's own id when it has one, else its declared process id."""

    sid = session_id()
    if sid:
        return hashlib.sha256(sid.encode("utf-8")).hexdigest()[:12]
    if pid > 0:
        return f"pid-{pid}"
    return alias or ""


def _declared_pid() -> int:
    try:
        return int(os.environ.get("CLAUDE_PID", "0") or 0)
    except ValueError:
        return 0


def _where(control_root: Path, cwd: Path) -> str:
    try:
        resolved = cwd.resolve()
        root = control_root.resolve()
        stations = (root / ".auto-pm" / "worktrees").resolve()
    except OSError:
        return "other"
    if resolved == stations or stations in resolved.parents:
        return "station"
    if resolved == root or root in resolved.parents:
        return "control-root"
    return "other"


def record_presence(control_root: str | Path, *, cwd: str | Path | None = None, min_interval_seconds: float = WRITE_INTERVAL_SECONDS) -> bool:
    """Say "this conversation is here" (agents only).  Returns True when a record exists and is fresh, False when nothing was written."""

    try:
        caller = caller_agent()
        if not caller or caller == _UNKNOWN:
            return False  # the user's terminal, or something unidentified: not a conversation
        pid = _declared_pid()
        alias = caller_alias()
        key = _key(alias, pid)
        if not key:
            return False
        root = Path(control_root)
        path = _folder(root) / f"{key}.json"
        previous = _read(path)
        now = datetime.now(UTC).isoformat()
        if previous and min_interval_seconds > 0:
            silent = _hours_since(previous.get("seen_at"))
            if silent is not None and silent * 3600 < min_interval_seconds:
                return True
        record = {
            "schema": SCHEMA,
            "key": key,
            "alias": alias,
            "source": caller,
            "machine": platform.node(),
            "pid": pid,
            "where": _where(root, Path(cwd) if cwd is not None else Path.cwd()),
            "title": os.environ.get("AUTO_PM_SESSION_TITLE", ""),
            "opened_at": str(previous.get("opened_at") or now) if previous else now,
            "seen_at": now,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except (OSError, ValueError):
        return False  # presence is information; failing to write it must never stop the real command


def _read(path: Path) -> dict[str, object]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def list_presence(control_root: str | Path, *, quiet_hours: float | None = None, orphan_hours: float | None = None) -> list[Presence]:
    """Every readable record with its verdict; read-only.

    alive     - the declared process is still there, or the record is fresh;
    quiet     - not seen for a while but nothing says the conversation is gone;
    orphan    - the declared process is gone (or none was declared) and the record is silent past the station limit;
    elsewhere - written on another computer (the machine name differs): shown, never judged.
    """

    quiet = QUIET_HOURS if quiet_hours is None else quiet_hours
    orphan_after = orphan_hours if orphan_hours is not None else _stale_hours()
    here = platform.node()
    found: list[Presence] = []
    folder = _folder(control_root)
    try:
        entries = sorted(folder.glob("*.json"))
    except OSError:
        return found
    for entry in entries:
        note = _read(entry)
        if note.get("schema") != SCHEMA:
            continue
        pid_value = note.get("pid")
        pid = pid_value if isinstance(pid_value, int) else 0
        silent = _hours_since(note.get("seen_at"))
        machine = str(note.get("machine", ""))
        if machine and machine != here:
            verdict, reason = "elsewhere", f"记录来自另一台电脑（{machine}），不判断"
        elif pid > 0 and _process_alive(pid):
            verdict, reason = "alive", f"进程 {pid} 还在"
        elif silent is None:
            verdict, reason = "quiet", "时间读不出来，不判断"
        elif silent >= orphan_after:
            gone = f"进程 {pid} 已不在" if pid > 0 else "没有记录进程号"
            verdict, reason = "orphan", f"疑似孤儿：{gone}，{silent:.1f} 小时没有动静（阈值 {orphan_after:g} 小时）"
        elif silent >= quiet:
            verdict, reason = "quiet", f"{silent:.1f} 小时没有动静"
        else:
            verdict, reason = "alive", "刚刚还在"
        found.append(
            Presence(
                key=str(note.get("key", entry.stem)),
                alias=str(note.get("alias", "")),
                source=str(note.get("source", "")),
                machine=machine,
                pid=pid,
                where=str(note.get("where", "other")),
                title=str(note.get("title", "")),
                opened_at=str(note.get("opened_at", "")),
                seen_at=str(note.get("seen_at", "")),
                silent_hours=silent,
                verdict=verdict,
                reason=reason,
            )
        )
    return found


def orient_lines(control_root: str | Path) -> tuple[str, ...]:
    """The line(s) ``pm orient`` prints: nothing when no other conversation is known; never raises, never writes."""

    try:
        mine = _key(caller_alias(), _declared_pid())
        others = [p for p in list_presence(control_root) if p.verdict in {"alive", "quiet"} and p.key != mine]
    except Exception:  # noqa: BLE001 - a hint must never stop the command it decorates
        return ()
    if not others:
        return ()
    at_root = sum(1 for p in others if p.where == "control-root")
    names = "、".join(p.alias or p.source or p.key for p in others[:4])
    more = f" 等 {len(others)} 个" if len(others) > 4 else ""
    root_note = f"，其中 {at_root} 个站在控制根上" if at_root else ""
    return (f"[在场] 本机另有 {len(others)} 个会话在场{root_note}：{names}{more}；详情 `main.py worktree who`",)
