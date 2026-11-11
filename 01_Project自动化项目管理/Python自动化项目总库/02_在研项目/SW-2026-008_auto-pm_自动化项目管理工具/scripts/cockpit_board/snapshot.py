"""“上次读取”快照：读取和新鲜度判断（CHG-SCPT-2026-628 骨架 B）。

断网或命令跑不动时，页面先亮上次读到的那份，并写明是几点读的、过没过期——像 HMI 通讯断了
画面变灰但保留最后值、标“通讯中断”。快照放 `<控制根>/.auto-pm/cache/cockpit_board/`（已被 .gitignore 忽略）。

这里只读不写：写入在 actions.write_snapshot（整个包只有 actions.py 写文件）。encode() 给它要写的文本。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

CACHE_RELATIVE = Path(".auto-pm") / "cache" / "cockpit_board"
SCHEMA = "cockpit-board-snapshot.v1"
STALE_AFTER = timedelta(minutes=30)  # 超过这么久的快照标“过期”
_KEY = re.compile(r"^[a-z0-9_-]{1,64}$")


@dataclass(frozen=True)
class Snapshot:
    key: str  # 读法名 + 项目，如 orient-SW-2026-008 → orient-sw-2026-008
    saved_at: datetime  # 带时区
    kind: str  # 读那次 actions 的归类（ok、exit_nonzero……）
    stdout: str
    stderr: str


def key_for(reader: str, project_id: str = "") -> str:
    """快照文件名的键：只用小写字母、数字、- 和 _，别的字一律报错，不让路径穿出缓存目录。"""
    key = (reader + ("-" + project_id if project_id else "")).lower()
    if not _KEY.match(key):
        raise ValueError(f"快照键不合规：{key!r}")
    return key


def path_for(root: Path, key: str) -> Path:
    if not _KEY.match(key):
        raise ValueError(f"快照键不合规：{key!r}")
    return root / CACHE_RELATIVE / f"{key}.json"


def encode(key: str, saved_at: datetime, kind: str, stdout: str, stderr: str) -> str:
    if saved_at.tzinfo is None:
        raise ValueError("saved_at 必须带时区")
    return json.dumps({"schema_version": SCHEMA, "key": key, "saved_at": saved_at.isoformat(), "kind": kind,
                       "stdout": stdout, "stderr": stderr}, ensure_ascii=False, indent=2) + "\n"


def decode(text: str) -> Snapshot | None:
    """读不懂的快照当作没有（返回 None），不让坏缓存把页面带崩。"""
    try:
        value = json.loads(text)
        if not isinstance(value, dict) or value.get("schema_version") != SCHEMA:
            return None
        saved_at = datetime.fromisoformat(str(value["saved_at"]))
        if saved_at.tzinfo is None:
            return None
        return Snapshot(str(value["key"]), saved_at, str(value["kind"]), str(value["stdout"]), str(value["stderr"]))
    except (ValueError, KeyError, TypeError):
        return None


def load(root: Path, key: str) -> Snapshot | None:
    path = path_for(root, key)
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    snapshot = decode(text)
    return snapshot if snapshot is not None and snapshot.key == key else None


def is_stale(snapshot: Snapshot, now: datetime | None = None, limit: timedelta = STALE_AFTER) -> bool:
    """快照比 now 早 limit 以上算过期；时间在将来（本机钟被调过）也算过期，不当成新鲜。"""
    current = now or datetime.now(UTC)
    age = current - snapshot.saved_at
    return age > limit or age < timedelta(0)


def age_text(snapshot: Snapshot, now: datetime | None = None) -> str:
    """给人看的“上次读取”说明：几分钟前，过期的写明过期。"""
    current = now or datetime.now(UTC)
    minutes = int((current - snapshot.saved_at).total_seconds() // 60)
    if minutes < 0:
        return "上次读取时间在将来（本机时间可能被改过），按过期处理"
    shown = "刚刚" if minutes == 0 else f"{minutes} 分钟前" if minutes < 120 else f"{minutes // 60} 小时前"
    return f"上次读取：{shown}" + ("（已过期）" if is_stale(snapshot, current) else "")
