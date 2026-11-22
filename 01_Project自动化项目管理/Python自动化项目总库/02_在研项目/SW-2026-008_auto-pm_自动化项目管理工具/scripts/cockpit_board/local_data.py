"""单机本地优先数据的只读适配器（GH-001 / PM-056 V2.0.0 / FLOW-002）。

纯 Python，不 import Qt、不起子进程、不写任何文件、不打开写句柄（严格 Path.read_text 只读），
所有读不到的、或格式损坏的文件都按“没建立 / 读不懂”退回，绝不抛未捕获异常、不伪装正常或 0。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_GITHUB_MODES = ("关", "备份", "多机")
_DEFAULT_GITHUB_MODE = "备份"
_STATE_DIR = Path(".auto-pm") / "reports" / "local_merge"
_MODE_FILE = "github_mode.json"
_LOG_FILE = "merge_log.jsonl"
_HANDOFF_DIR = "交接交换区"
_FOCUS_FILE = "focus.json"
_JOURNAL_FILE = "journal.jsonl"
_STALE_DAYS = 7
_PROJECT_RE = re.compile(r"(?:^|[/_\\-])([A-Z]{2,4}-\d{4}-\d{3})(?=[_/\-]|$)")
_PLC_PREFIX = "0100_PLC自动化/"


@dataclass(frozen=True)
class GithubModeInfo:
    """本机 GitHub 联动三档（关 / 备份 / 多机）。"""

    mode: str  # 关 / 备份 / 多机 / 读不懂
    set_at: str = ""
    configured: bool = False
    note: str = ""


@dataclass(frozen=True)
class MergeRecord:
    """本机 pm_merge.py merge_log.jsonl 的单条合并记录。"""

    time: str
    branch: str
    merge_sha: str
    card: str = ""
    mode: str = ""
    pushed: bool = False
    chgs: tuple[str, ...] = ()
    push_error: str = ""

    @property
    def revert_command(self) -> str:
        return f"git revert -m 1 {self.merge_sha[:8]}" if self.merge_sha else ""


@dataclass(frozen=True)
class HandoffPriority:
    rank: int
    item: str
    ref: str = ""


@dataclass(frozen=True)
class HandoffEvent:
    ts: str
    agent: str
    kind: str
    summary: str
    card: str = ""
    commit: str = ""
    chg: str = ""
    read_first: tuple[str, ...] = ()
    next_hint: str = ""


@dataclass(frozen=True)
class ProjectHandoff:
    """单个项目的轻轨交接区状态（focus.json + journal.jsonl）。"""

    project_id: str
    handoff_rel: str
    exists: bool = False
    unreadable: str = ""
    updated_at: str = ""
    updated_by: str = ""
    stage_goal: str = ""
    priorities: tuple[HandoffPriority, ...] = ()
    active_card: str = ""
    active_branch: str = ""
    active_chg: str = ""
    active_breakpoint: str = ""
    waiting_for_user: tuple[str, ...] = ()
    next_action: str = ""
    stale_days: int | None = None
    events: tuple[HandoffEvent, ...] = ()

    @property
    def is_stale(self) -> bool:
        return self.stale_days is not None and self.stale_days >= _STALE_DAYS


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _parse_iso(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def read_github_mode(root: Path | None) -> GithubModeInfo:
    """读 .auto-pm/reports/local_merge/github_mode.json；不存在按默认“备份（未单独设置）”，损坏写“读不懂”。"""
    if root is None:
        return GithubModeInfo(_DEFAULT_GITHUB_MODE, "", False, "未给控制根，按默认「备份」档展示")
    path = root / _STATE_DIR / _MODE_FILE
    if not path.is_file():
        return GithubModeInfo(_DEFAULT_GITHUB_MODE, "", False, "未切换过档位文件，当前按默认「备份」档工作")
    text = _read_text(path)
    if text is None:
        return GithubModeInfo("读不懂", "", True, "github_mode.json 读取失败")
    try:
        data = json.loads(text)
    except ValueError:
        return GithubModeInfo("读不懂", "", True, "github_mode.json 不是合法 JSON")
    if not isinstance(data, dict):
        return GithubModeInfo("读不懂", "", True, "github_mode.json 结构不对")
    mode = str(data.get("mode") or "")
    set_at = str(data.get("set_at") or "")
    if mode not in _GITHUB_MODES:
        return GithubModeInfo("读不懂", set_at, True, f"github_mode.json 档位不认识：{mode}")
    return GithubModeInfo(mode, set_at, True, f"本机 GitHub 联动：{mode}")


def read_merge_log(root: Path | None, limit: int = 8) -> tuple[list[MergeRecord], str]:
    """倒序读最近 limit 条 pm_merge 合并记录；文件不存在返回 ([], '')，损坏时写明“读不懂”。"""
    if root is None:
        return [], ""
    path = root / _STATE_DIR / _LOG_FILE
    if not path.is_file():
        return [], ""
    text = _read_text(path)
    if text is None:
        return [], "合并日志 merge_log.jsonl 读不到"
    records: list[MergeRecord] = []
    bad = 0
    for line in text.splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except ValueError:
            bad += 1
            continue
        if not isinstance(item, dict):
            bad += 1
            continue
        chgs = tuple(str(x) for x in (item.get("chgs") or []) if x)
        records.append(
            MergeRecord(
                time=str(item.get("time") or ""),
                branch=str(item.get("branch") or ""),
                merge_sha=str(item.get("merge_sha") or ""),
                card=str(item.get("card") or ""),
                mode=str(item.get("mode") or ""),
                pushed=bool(item.get("pushed")),
                chgs=chgs,
                push_error=str(item.get("push_error") or ""),
            )
        )
    records.reverse()
    note = f"合并日志有 {bad} 行读不懂" if bad else ""
    return records[:limit], note


def handoff_dir_for(project_root: str) -> str:
    """按 PM-056 V2.0.0 规矩算各项目交接交换区相对路径。"""
    norm = project_root.replace("\\", "/").lstrip("/")
    if not norm:
        return ""
    sub = "11_监控" if norm.startswith(_PLC_PREFIX) else "04_监控"
    return f"{norm.rstrip('/')}/{sub}/{_HANDOFF_DIR}"


def read_project_handoff(
    root: Path | None,
    project_id: str,
    project_root: str,
    *,
    now: datetime | None = None,
    tail: int = 10,
) -> ProjectHandoff:
    """只读一个项目的 focus.json 与最近 tail 条 journal.jsonl。"""
    rel = handoff_dir_for(project_root)
    if root is None or not rel:
        return ProjectHandoff(project_id=project_id, handoff_rel=rel)
    folder = root / rel
    if not folder.is_dir():
        return ProjectHandoff(project_id=project_id, handoff_rel=rel)
    focus_path = folder / _FOCUS_FILE
    journal_path = folder / _JOURNAL_FILE
    exists = focus_path.is_file() or journal_path.is_file()
    if not exists:
        return ProjectHandoff(project_id=project_id, handoff_rel=rel)

    errors: list[str] = []
    updated_at = updated_by = stage_goal = next_action = ""
    active_card = active_branch = active_chg = active_bp = ""
    priorities: list[HandoffPriority] = []
    waiting: list[str] = []
    stale_days: int | None = None

    if focus_path.is_file():
        ftext = _read_text(focus_path)
        if ftext is None:
            errors.append("focus.json 读不到")
        else:
            try:
                fdata = json.loads(ftext)
            except ValueError:
                errors.append("focus.json 不是合法 JSON")
                fdata = None
            if isinstance(fdata, dict):
                if fdata.get("schema") != "local-handoff-focus.v1":
                    errors.append(f"focus.json schema 不认识：{fdata.get('schema')}")
                updated_at = str(fdata.get("updated_at") or "")
                updated_by = str(fdata.get("updated_by") or "")
                stage_goal = str(fdata.get("stage_goal") or "")
                next_action = str(fdata.get("next_action") or "")
                aw = fdata.get("active_work")
                if isinstance(aw, dict):
                    active_card = str(aw.get("card") or "")
                    active_branch = str(aw.get("branch") or "")
                    active_chg = str(aw.get("chg") or "")
                    active_bp = str(aw.get("breakpoint") or "")
                for entry in fdata.get("priorities") or []:
                    if isinstance(entry, dict) and entry.get("item"):
                        try:
                            rank = int(entry.get("rank") or len(priorities) + 1)
                        except (TypeError, ValueError):
                            rank = len(priorities) + 1
                        priorities.append(HandoffPriority(rank, str(entry.get("item") or ""), str(entry.get("ref") or "")))
                waiting = [str(w) for w in (fdata.get("waiting_for_user") or []) if str(w).strip()]
                dt = _parse_iso(updated_at)
                if dt is not None:
                    ref_now = now or datetime.now(UTC)
                    if ref_now.tzinfo is None:
                        ref_now = ref_now.replace(tzinfo=UTC)
                    stale_days = max(0, int((ref_now - dt).total_seconds() // 86400))
            elif fdata is not None:
                errors.append("focus.json 顶层必须是对象")

    events: list[HandoffEvent] = []
    if journal_path.is_file():
        jtext = _read_text(journal_path)
        if jtext is None:
            errors.append("journal.jsonl 读不到")
        else:
            bad_lines = 0
            for raw_line in jtext.splitlines():
                stripped = raw_line.strip()
                if not stripped:
                    continue
                try:
                    ev = json.loads(stripped)
                except ValueError:
                    bad_lines += 1
                    continue
                if not isinstance(ev, dict):
                    bad_lines += 1
                    continue
                events.append(
                    HandoffEvent(
                        ts=str(ev.get("ts") or ""),
                        agent=str(ev.get("agent") or ""),
                        kind=str(ev.get("kind") or ""),
                        summary=str(ev.get("summary") or ""),
                        card=str(ev.get("card") or ""),
                        commit=str(ev.get("commit") or ""),
                        chg=str(ev.get("chg") or ""),
                        read_first=tuple(str(r) for r in (ev.get("read_first") or []) if r),
                        next_hint=str(ev.get("next") or ""),
                    )
                )
            if bad_lines:
                errors.append(f"journal.jsonl 有 {bad_lines} 行读不懂")
            events.reverse()

    return ProjectHandoff(
        project_id=project_id,
        handoff_rel=rel,
        exists=True,
        unreadable="；".join(errors),
        updated_at=updated_at,
        updated_by=updated_by,
        stage_goal=stage_goal,
        priorities=tuple(priorities),
        active_card=active_card,
        active_branch=active_branch,
        active_chg=active_chg,
        active_breakpoint=active_bp,
        waiting_for_user=tuple(waiting),
        next_action=next_action,
        stale_days=stale_days,
        events=tuple(events[:tail]),
    )


def read_all_handoffs(
    root: Path | None,
    projects: Sequence[tuple[str, str]],
    *,
    now: datetime | None = None,
) -> dict[str, ProjectHandoff]:
    """按项目编号批量只读交接交换区。"""
    found: dict[str, ProjectHandoff] = {}
    for pid, proj_root in projects:
        if pid and proj_root:
            found[pid] = read_project_handoff(root, pid, proj_root, now=now)
    return found


def resolve_station_project(
    branch: str,
    card: str,
    claim_paths: Sequence[str] | None,
    handoffs: Mapping[str, ProjectHandoff] | None = None,
    known_pids: Sequence[str] = (),
) -> str:
    """四级优先级解析单机工位所属项目：

    1. 占位表 paths 里的项目编号（如 0100_PLC自动化/DJ-2026-005/...）；
    2. 各项目 focus.json 的 active_work.branch / active_work.card 匹配；
    3. branch 或 card 字符串中显式包含的项目编号（如 SW-2026-008）；
    4. 都匹配不到返回空串（界面按 UNKNOWN 显示，不猜）。
    """
    from_paths: list[str] = []
    for raw_path in claim_paths or ():
        match = _PROJECT_RE.search(str(raw_path).replace("\\", "/"))
        if match and match.group(1) not in from_paths:
            from_paths.append(match.group(1))
    if from_paths:
        return "、".join(from_paths)

    clean_branch = (branch or "").strip()
    clean_card = (card or "").strip()
    if handoffs:
        for pid, info in handoffs.items():
            if info.active_branch and info.active_branch == clean_branch:
                return pid
            if clean_card and info.active_card and info.active_card == clean_card:
                return pid

    known_set = set(known_pids)
    for source in (clean_branch, clean_card):
        for found in _PROJECT_RE.findall(source):
            if not known_set or found in known_set:
                return str(found)
    return ""
