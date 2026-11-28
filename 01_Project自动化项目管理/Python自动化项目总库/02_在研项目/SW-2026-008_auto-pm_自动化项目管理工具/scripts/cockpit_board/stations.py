"""“工作树与分支”页的判断（纯 Python，不 import Qt，不起子进程）：每个工位一行写什么、能不能收、点了跑哪条命令。

读这个文件就知道页上每个按钮背后是哪条 ``main.py worktree …`` 命令：

* 名册里的工位（``claude``、``claude-1b7302`` 这类，``worktree list`` 里 kind 是 agent）：“收工位”→ ``worktree close <名字>``；
* 名册里、但 Git 里已经没登记的残留目录（``worktree list`` 里 registered=false，收工位删到一半的空壳）：
  “清理残留”→ 同样跑 ``worktree close <名字>``，命令只清空目录，有内容就拒绝并给出人工清理命令（CHG-SCPT-2026-747）；
* 名册外的目录（``gate-formal`` 这类，kind 是 other）和 run-plan 残留：``worktree close`` 不认这种名字（rc 2），
  只能“清理”→ ``worktree sweep --apply --only <目录名> --no-fetch``，而且要清理清单里这一项判了“可清”；
* “清残留持有记录”→ 先跑 ``worktree reclaim --stale``（只列），列出来的再跑 ``worktree reclaim --stale --apply``；
* “清理全部可清项”→ ``worktree sweep --apply --no-fetch``（远程已删的本地分支没有单项参数，只能整批）。
* “登记新 AI”（CHG-SCPT-2026-712）→ 先只读跑 ``agent list --json`` 列名册，在框里填名字后跑 ``agent register <名字> --via board``；
  名册里登记的每个 AI 带“注销”→ 再弹一次确认框，跑 ``agent unregister <名字>``（还有工位或有效占位命令自己会拒）。

为什么这一页现在有会收目录的按钮（policy.WORKTREE_BUTTONS 写了来由）：以前骨架不放按钮，让用户去终端敲；
用户 2026-11-16 说“我没办法用”，项目经理定这一页加按钮，保护是下面几条，每条都有测试：

1. 只在你本人打开的看板能点：看板进程带 AI 标记、或认不出带没带时，所有按钮灰着并写原因，运行入口再拦一道；
2. 点之前看得见检查结果：确认框里写工位名、分支、未提交、未推送、并进 main 没有，和等价命令；
3. 没查过、有未提交、有未推送、分支不是这个名字的前缀、被锁、目录坏了：按钮灰着，旁边写差哪一条（命令自己也照样拒）；
4. 每次点击留回执：命令、退出码、原文输出留在页上。

命令自己的护栏（不删有改动或没推送的、不动别人的、认不出调用方就拒）一条不少；页上的判断只是让人先看明白，不是安全边界。
"""

from __future__ import annotations

import contextlib
import json
import re
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cockpit_board import local_data, policy

# 内置名册和会话别名的写法：和 auto_pm.application.core.agent_worktree_service 的 BUILTIN_ROSTER、_ALIAS 逐字一致（测试对照）；
# 本包不 import auto_pm，所以照抄。用户登记的 AI（CHG-SCPT-2026-712）不在这里：`worktree list --json` 每个 agent 工位行
# 自带 kind="agent" 和 branch_prefix（命令按本机登记表判的），页上按行里的这两项走，不另抄一份登记表。
ROSTER_PREFIX = {"claude": "claude/", "trae": "trae/", "cursor": "cursor/", "vscode": "vscode/", "codex": "codex/"}
ALIAS = re.compile(r"^(claude|codex|cursor|trae|vscode)-[0-9a-f]{6}$")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")  # 进命令行的目录名：只认这些字符
_PROJECT = re.compile(r"(?:^|/)([A-Z]{2,4}-\d{4}-\d{3})(?=[_/]|$)")  # 路径里的项目编号，如 SW-2026-008
UNKNOWN = "未知"

CLOSE_SUMMARY = ("收这个工位：命令先查有没有未提交、未推送，都没有才收掉工位目录；分支已并进 main 的，本地分支一起收掉，"
                 "远程分支不动。有改动或没推送的命令会拒绝，什么都不动。")
RESIDUE_SUMMARY = ("清理这个残留：Git 里已经没有这个工位的登记，目录还在（多半是收工位没删干净）。"
                   "命令只清空目录；里面还有文件时拒绝，并给出人工清理命令。")
SWEEP_ONE_SUMMARY = "清理这一个目录：命令再按清理清单的规矩判一遍（已并进 main、干净、不在保留名单），判可清才收掉，否则什么都不动。"
SWEEP_ALL_SUMMARY = "清理清单里判了“可清”的全部项（工位目录和远程已删、已并进 main 的本地分支）；判了“保留”的不动，远程分支不动。"
RECLAIM_SUMMARY = ("清残留持有记录：持有对话已经不在的会话工位先存一份救援引用再收目录（分支保留），"
                   "工位目录早就没了的孤儿持有记录直接清掉。只清下面列出来的这些。")


@dataclass(frozen=True)
class Action:
    """页上一个会动东西的按钮背后的那条命令。``args`` 是 ``main.py`` 后面的参数。"""

    key: str  # close / sweep_one / sweep_all / reclaim
    label: str
    summary: str
    args: tuple[str, ...]
    target: str  # 确认框第二行写的对象（工位名、目录名）
    facts: tuple[tuple[str, str], ...] = ()  # 确认框里列的检查结果


@dataclass(frozen=True)
class StationRow:
    """“工作树与分支”页的一行工位。``blocked`` 非空时按钮灰着，旁边写这句。"""

    name: str
    kind: str
    branch: str
    who: str
    card: str
    project: str
    last_seen: str
    checks: str
    action: Action | None
    blocked: str = ""
    warning: str = ""  # 按钮能点也要先看的一句（名册外目录：是不是正被门禁用着）
    checked: bool = False
    dirty: int | None = None
    unpushed: int | None = None
    merged: bool | None = None
    locked: bool = False


@dataclass(frozen=True)
class SweepRow:
    target: str
    category: str
    reason: str
    removable: bool
    action: Action | None
    blocked: str = ""


@dataclass
class StationsView:
    rows: list[StationRow] = field(default_factory=list)
    sweep: list[SweepRow] = field(default_factory=list)
    sweep_all: Action | None = None
    sweep_all_blocked: str = ""  # 整批清理会连名册外目录一起清：有长任务在跑时灰着，写这句
    notes: list[str] = field(default_factory=list)
    collected_at: str = ""


def base_agent(name: str) -> str:
    """名册里的基名：``claude`` → ``claude``，``claude-1b7302`` → ``claude``，名册外 → 空串。"""
    if name in ROSTER_PREFIX:
        return name
    match = ALIAS.match(name)
    return match.group(1) if match else ""


def card_of(branch: str) -> str:
    """分支名里的卡号：``claude/695-launcher-worktree`` → ``695-launcher-worktree``；没有斜杠的不算。"""
    head, _sep, tail = (branch or "").partition("/")
    return tail if head and tail else ""


def project_of(paths: Sequence[str]) -> str:
    """占位路径落在哪个项目目录：取路径里的项目编号；几条路径落在不同项目时都列出来。"""
    found: list[str] = []
    for path in paths:
        match = _PROJECT.search(str(path).replace("\\", "/"))
        if match and match.group(1) not in found:
            found.append(match.group(1))
    return "、".join(found)


def _hours_since(stamp: Any, now: datetime) -> float | None:
    try:
        then = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=UTC)
    return max(0.0, (now - then).total_seconds() / 3600)


def _last_seen(row: Mapping[str, Any], note: Mapping[str, Any], now: datetime) -> str:
    parts: list[str] = []
    hours = _hours_since(note.get("heartbeat_at") or note.get("opened_at"), now) if note else None
    if hours is not None:
        parts.append(f"心跳 {hours:.1f} 小时前")
    idle = row.get("idle_days")
    if isinstance(idle, int):
        parts.append("今天动过" if idle == 0 else f"{idle} 天没动")
    return "，".join(parts) or UNKNOWN


def _who(name: str, claim: Mapping[str, Any] | None, note: Mapping[str, Any], prefix: str = "") -> str:
    title = str(note.get("title") or "").strip() if note else ""
    owner = str(claim.get("owner") or "").strip() if claim else ""
    base = base_agent(name) or prefix.rstrip("/")  # 登记的 AI：基名就是它分支前缀去掉斜杠
    parts = [p for p in (title and f"对话“{title}”", owner and f"占位人 {owner}") if p]
    if not parts and base:
        parts.append(f"{base}（{'会话别名' if name != base else '共用名'}）")
    return "，".join(parts) or UNKNOWN


def _checks(row: Mapping[str, Any]) -> str:
    if row.get("broken"):
        return "目录坏了：" + str(row["broken"])
    if not row.get("checked"):
        return "未提交、未推送没检查"
    merged = row.get("merged")
    return " · ".join((
        f"未提交 {row.get('dirty')}",
        f"未推送 {row.get('unpushed')}",
        "已并进 main" if merged else ("没并进 main" if merged is False else "并进 main 没检查"),
    ))


def close_block(row: Mapping[str, Any], sweep_reason: str = "") -> str:
    """名册里的工位能不能点“收工位”；能点返回空串，不能点返回差的那一条（和 worktree close 自己拒的口径一致）。

    有未提交、有未推送时，清理清单里这一项的原因就是 ``worktree close`` 拒绝时的原话（同一个 ``_refusal``），有就照抄；
    清理清单没读到时退回按数字写。
    """
    name, branch = str(row.get("name") or ""), str(row.get("branch") or "")
    if row.get("broken"):
        return "目录坏了，命令不收：" + str(row["broken"])
    if not row.get("checked"):
        return "还没查过有没有未提交、未推送（工位列表没读到检查结果），先点“重新读取”"
    if row.get("locked"):
        return "工位被 git worktree lock 锁着，命令不收"
    if not branch:
        return "工位不在分支上（detached HEAD），命令不收"
    prefix = str(row.get("branch_prefix") or "") or ROSTER_PREFIX.get(base_agent(name), "")
    if prefix and not branch.startswith(prefix):
        return f"分支 {branch} 不是 {prefix} 开头，命令不收；这个工位归谁要你先确认"
    dirty, unpushed = row.get("dirty"), row.get("unpushed")
    if dirty or (unpushed and not row.get("merged")):
        said = sweep_reason if sweep_reason.startswith("有") else ""
        if said:
            return said
        return f"有未提交的改动 {dirty} 个文件" if dirty else f"有 {unpushed} 个提交还没推到 GitHub"
    if not _NAME.fullmatch(name):
        return f"工位名“{name[:40]}”里有命令行不认的字符，不运行"
    return ""


def _facts(row: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    return (
        ("工位", str(row.get("name") or "")),
        ("目录", str(row.get("path") or UNKNOWN)),
        ("分支", str(row.get("branch") or "（没有分支）")),
        ("检查结果", _checks(row)),
    )


def _station_op_warning(
    name: str,
    note: Mapping[str, Any],
    ops: Mapping[str, Mapping[str, Any]] | None,
) -> str:
    """最近一次工位提交操作不是工位主人（或被跨工位互锁拒绝）时返回告警文案。"""
    last_op = (ops or {}).get(name)
    if last_op is None and isinstance(note.get("_last_op"), Mapping):
        last_op = note["_last_op"]
    if not isinstance(last_op, Mapping):
        return ""
    actor = str(last_op.get("actor") or "").strip()
    owner = str(last_op.get("owner") or name).strip()
    outcome = str(last_op.get("outcome") or "").strip()
    reason = str(last_op.get("reason") or "").strip()
    if outcome == "blocked":
        return f"工位跨会话操作告警：最近被拦截操作者 {actor or UNKNOWN} ≠ 工位主人 {owner}"
    if outcome == "allowed" and reason in {"owner", "user-terminal", "borrower"}:
        return ""
    if actor and owner and actor != owner and actor != "no-agent-marker":
        return f"工位跨会话操作告警：最近操作者 {actor} ≠ 工位主人 {owner}"
    return ""


def build_view(
    stations: Sequence[Mapping[str, Any]] | None,
    sweep_items: Sequence[Mapping[str, Any]] | None,
    claims: Sequence[Mapping[str, Any]] | None,
    holders: Mapping[str, Mapping[str, Any]],
    *,
    human_block: str,
    now: datetime,
    long_runs: Sequence[Mapping[str, Any]] | None = None,
    handoffs: Mapping[str, local_data.ProjectHandoff] | None = None,
    known_pids: Sequence[str] = (),
    station_ops: Mapping[str, Mapping[str, Any]] | None = None,
) -> StationsView:
    """拼一页：每个工位一行、清理清单每项一行。``None``＝那条命令没读到：对应的按钮全灰，写明原因，不当成“没有”。

    ``human_block`` 非空＝看板进程带 AI 标记（或认不出），所有按钮灰着，写这句。
    """

    view = StationsView(collected_at=now.isoformat(timespec="seconds"))
    by_card = {str(c.get("card")): c for c in (claims or ()) if c.get("status", "active") == "active" and c.get("card")}
    by_path: dict[str, Mapping[str, Any]] = {}
    for entry in sweep_items or ():
        by_path[str(entry.get("target") or "")] = entry
    if claims is None:
        view.notes.append("占位表没读到：卡号只按分支名猜，谁领的、属于哪个项目写“未知”")
    if sweep_items is None:
        view.notes.append("清理清单没读到：名册外目录的“清理”按钮先灰着")
    running = [str(t.get("name")) for t in long_runs or () if str(t.get("state") or "") in ("STARTING", "RUNNING")]
    if long_runs is None:
        in_use = "是不是正被门禁或长任务用着：未知（长任务状态没读到）"
    elif running:
        in_use = (f"有长任务在跑（{'、'.join(running)}）：这个目录可能正被它用着；长任务状态不写它用的是哪个目录，"
                  "判不了是不是这一个，所以长任务跑完以前名册外的目录一律不清")
    else:
        in_use = "是不是正被门禁用着：未知（命令不给这一项；现在没有在跑的长任务）"
    for row in stations or ():
        name, kind, branch = str(row.get("name") or ""), str(row.get("kind") or ""), str(row.get("branch") or "")
        card = card_of(branch)
        claim = by_card.get(card)
        note = holders.get(name, {})
        action: Action | None
        item: Mapping[str, Any] | None = by_path.get(str(row.get("path") or ""))
        warning = ""
        if row.get("registered") is False and (kind == "agent" or base_agent(name)):
            warning = "Git 里没有登记这个工位：目录是收工位没删干净的残留；点了只清空目录，有内容时命令会拒绝并给出人工清理命令"
            action = Action("clean_residue", "清理残留", RESIDUE_SUMMARY, ("worktree", "close", name), name, _facts(row))
            blocked = human_block or (
                f"目录名“{name[:40]}”里有命令行不认的字符，不运行" if not _NAME.fullmatch(name) else ""
            )
        elif kind == "agent" or base_agent(name):
            blocked = human_block or close_block(row, str(item.get("reason") or "") if item else "")
            action = Action("close", "收工位", CLOSE_SUMMARY, ("worktree", "close", name), name, _facts(row))
        else:
            warning = in_use
            # 确认框照抄清理清单这一项的判词：门禁目录还是手工 detached 目录、HEAD 是哪个提交、有没有长任务在用（G 工位止血，卡 280）
            verdict = (("清理清单判词", str(item.get("reason") or "（没写原因）")),) if item else ()
            action = Action("sweep_one", "清理", SWEEP_ONE_SUMMARY, ("worktree", "sweep", "--apply", "--only", name, "--no-fetch"),
                            name, _facts(row) + verdict)
            if human_block:
                blocked = human_block
            elif running:  # 门禁正跑着时它的目录也是名册外的：分不出是哪一个，就都不放（项目经理 14:15Z：gate-f90fef3 谁都不动）
                blocked = in_use
            elif sweep_items is None:
                blocked = "清理清单没读到，判不了能不能清"
            elif item is None:
                blocked = "清理清单里没有这一项，判不了能不能清"
            elif not item.get("remove"):
                blocked = "清理清单判了保留：" + str(item.get("reason") or "（没写原因）")
            elif not _NAME.fullmatch(name):
                blocked = f"目录名“{name[:40]}”里有命令行不认的字符，不运行"
            else:
                blocked = ""
        op_warning = _station_op_warning(name, note, station_ops)
        if op_warning:
            warning = f"{warning}；{op_warning}" if warning else op_warning
        resolved_proj = project_of(claim.get("paths") or ()) if claim else ""
        if not resolved_proj:
            resolved_proj = local_data.resolve_station_project(branch, card, None, handoffs, known_pids)
        view.rows.append(StationRow(
            name=name, kind=kind, branch=branch or "（没有分支）",
            who=_who(name, claim, note, str(row.get("branch_prefix") or "") if kind == "agent" else ""),
            card=(card or UNKNOWN) + ("" if claim or not card else "（占位表里没有这张）"),
            project=resolved_proj or UNKNOWN,
            last_seen=_last_seen(row, note, now),
            checks=_checks(row),
            action=action, blocked=blocked, warning=warning,
            checked=bool(row.get("checked")),
            dirty=row.get("dirty") if isinstance(row.get("dirty"), int) and not isinstance(row.get("dirty"), bool) else None,
            unpushed=row.get("unpushed") if isinstance(row.get("unpushed"), int) and not isinstance(row.get("unpushed"), bool) else None,
            merged=row.get("merged") if isinstance(row.get("merged"), bool) else None,
            locked=bool(row.get("locked")),
        ))
    station_paths = {str(r.get("path") or "") for r in stations or ()}
    removable: list[str] = []
    for item in sweep_items or ():
        target = str(item.get("target") or "")
        remove = bool(item.get("remove"))
        if remove:
            removable.append(target)
        if target in station_paths:  # 工位目录那一项在上面那一行里已经有按钮
            continue
        view.sweep.append(SweepRow(target, str(item.get("category") or ""), str(item.get("reason") or ""), remove, None,
                                   "" if remove else "判了保留"))
    if removable:
        facts = tuple(("会清", target) for target in removable)
        view.sweep_all = Action("sweep_all", "清理全部可清项", SWEEP_ALL_SUMMARY, ("worktree", "sweep", "--apply", "--no-fetch"),
                                f"{len(removable)} 项", facts)
        view.sweep_all_blocked = human_block or (in_use if running else "")
    return view


def read_station_ops(root: Path | None) -> dict[str, dict[str, Any]]:
    """读取 ``.auto-pm/logs/station-ops.jsonl`` 中每个工位的最后一条操作记录（只读，坏行跳过）。"""
    found: dict[str, dict[str, Any]] = {}
    log_path = (root / ".auto-pm" / "logs" / "station-ops.jsonl") if root is not None else None
    if log_path is None or not log_path.is_file():
        return found
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return found
    for raw in lines:
        if not raw.strip():
            continue
        try:
            item = json.loads(raw)
        except ValueError:
            continue
        if isinstance(item, dict):
            station = str(item.get("station") or "").strip()
            if station:
                found[station] = item
    return found


def read_holders(root: Path | None) -> dict[str, dict[str, Any]]:
    """``.auto-pm/station-holders/<名字>.json``：谁开的会话工位、对话标题、最后心跳（只读；读不了的跳过，页上写“未知”）。"""
    found: dict[str, dict[str, Any]] = {}
    folder = (root / ".auto-pm" / "station-holders") if root is not None else None
    if folder is not None and folder.is_dir():
        for entry in sorted(folder.glob("*.json")):
            try:
                loaded = json.loads(entry.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(loaded, dict):
                found[entry.stem] = loaded
    for station, last_op in read_station_ops(root).items():
        found.setdefault(station, {})["_last_op"] = last_op
    return found


def read_registered(root: Path | None) -> list[dict[str, Any]]:
    """从控制根账本只读读取已登记的表外 AI 花名册（只返回 active）。"""
    if root is None:
        return []
    db = root / ".auto-pm" / "continuity.db"
    if not db.is_file():
        return []
    try:
        uri = f"{db.resolve().as_uri()}?mode=ro"
        with contextlib.closing(sqlite3.connect(uri, uri=True, timeout=1.0)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT name, branch_prefix, status, registered_by, registered_at, source_ref "
                "FROM agent_registry WHERE status = 'active' ORDER BY name"
            ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []


def reclaim_preview_args() -> tuple[str, ...]:
    """“清残留持有记录”点开时先跑的只列命令（不带 --apply，什么都不动）。"""
    return ("worktree", "reclaim", "--stale")


def parse_reclaim_preview(text: str) -> list[str]:
    """``worktree reclaim --stale`` 的输出 → 会清的那几条（每条“可回收 <名字>：<依据>”）。

    命令的输出窄时会折行：一条从“可回收 ”开头，下面接着的行（不是下一条、不是末尾那句“加 --apply …”）接回这一条，原话不丢。
    """
    found: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if line.startswith("可回收 "):
            found.append(line[len("可回收 "):])
        elif found and line and not line.startswith("加 --apply"):
            found[-1] += line
        elif line.startswith("加 --apply"):
            break
    return found


def reclaim_action(found: Sequence[str]) -> Action:
    return Action("reclaim", "清残留持有记录", RECLAIM_SUMMARY, ("worktree", "reclaim", "--stale", "--apply"),
                  f"{len(found)} 条", tuple(("会清", line) for line in found))


# ---- AI 登记表（CHG-SCPT-2026-712）：“登记新 AI”先只读列出名册（agent list --json），确认框里填名字再跑 agent register

AGENT_NAME = re.compile(r"[a-z][a-z0-9]{1,19}")  # 和 auto_pm.application.core.agent_registry.NAME 逐字一致（测试对照）
REGISTER_SUMMARY = ("登记一个内置五个以外的 AI：分支前缀自动是 <名字>/。登记后它用 AUTO_PM_AGENT=<名字>（pm-as-agent.ps1 <名字>）"
                    "运行驾驶舱命令、开工位。只在你本人打开的看板能点，命令自己也拒任何 AI 来登记。")
UNREGISTER_SUMMARY = "注销这个 AI：以后带这个名字的 AI 会被拒。它还有工位或有效占位时命令会拒绝，什么都不动；登记记录留着。"


def registry_preview_args() -> tuple[str, ...]:
    return ("agent", "list", "--json")


def parse_registry(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    """``agent list --json`` → (内置, 登记的)；读不懂返回 None（按钮照样能点，但名单写“读不懂”）。"""
    try:
        data = json.loads(text)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    builtin, registered = data.get("builtin"), data.get("registered")
    if not isinstance(builtin, list) or not isinstance(registered, list):
        return None
    return [b for b in builtin if isinstance(b, dict)], [r for r in registered if isinstance(r, dict)]


def register_problem(name: str, taken: Sequence[str]) -> str:
    """确认框里填的名字能不能登记；能返回空串（命令自己还会再判一遍）。"""
    if not name:
        return "先填名字"
    if not AGENT_NAME.fullmatch(name):
        return "名字要小写字母开头，2～20 位小写字母和数字（不带横线、空格、大写）"
    if name in taken:
        return f"{name} 已经在名册里了"
    return ""


def register_action(name: str) -> Action:
    return Action("register", "登记新 AI", REGISTER_SUMMARY, ("agent", "register", name, "--via", "board"), name,
                  (("名字", name), ("分支前缀", f"{name}/")))


def unregister_action(item: Mapping[str, Any]) -> Action:
    name = str(item.get("name") or "")
    facts = (("名字", name), ("分支前缀", str(item.get("branch_prefix") or "")),
             ("登记", f"{item.get('registered_by') or UNKNOWN}，{item.get('registered_at') or UNKNOWN}"))
    return Action("unregister", "注销", UNREGISTER_SUMMARY, ("agent", "unregister", name), name, facts)


def allowed_command(args: Sequence[str]) -> bool:
    """这条参数是不是 policy.WORKTREE_COMMANDS 里登记的形状之一；“<名字>”那一格只认 _NAME 的字符（不以 - 开头，不带空格）。"""
    for shape in policy.WORKTREE_COMMANDS:
        if len(shape) == len(args) and all(
            (_NAME.fullmatch(str(got)) is not None) if want == "<名字>" else got == want for want, got in zip(shape, args, strict=True)
        ):
            return True
    return False


def shown_command(args: Sequence[str]) -> str:
    return "main.py " + " ".join(args)
