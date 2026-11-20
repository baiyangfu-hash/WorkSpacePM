"""本机轻轨交接交换区读写与核验工具（PM-056 V2.0.0，local-handoff.v1，卡 318）。

用法（在控制根或工位，用控制根 .venv 里的 Python；Windows 是 .venv\\Scripts\\python.exe）：
  python <本项目>/scripts/pm_handoff.py show <项目号> [--root <路径>] [--tail 5] [--json]
  python <本项目>/scripts/pm_handoff.py validate <项目号> [--root <路径>] [--require-exists]
  python <本项目>/scripts/pm_handoff.py set-focus <项目号> --root <工位路径> --by <署名> --goal <阶段目标> --next <下一步> [...]
  python <本项目>/scripts/pm_handoff.py log <项目号> --root <工位路径> --agent <署名> --kind <类型> --summary <摘要> [...]

规矩（PM-056 V2.0.0 第 13 节）：
1. 只用标准库和只读 git，不依赖 auto_pm 包；本脚本不进发布载荷，合并进 main 即生效。
2. 目录跨项目零冲突：
   - Python / 治理类项目：<project_root>/04_监控/交接交换区/
   - PLC 工程项目（0100_PLC自动化/ 下）：<project_root>/11_监控/交接交换区/
3. 双表结构：
   - focus.json（schema: local-handoff-focus.v1，覆盖写）
   - journal.jsonl（schema: local-handoff-event.v1，只追加）
4. 红线：绝非授权源，绝不覆盖 Git/账本机器事实；已存在的坏文件、未知 schema、缺字段、超长或越界路径一律失败关闭（退出 1）。
5. 写入保护：set-focus / log 默认禁止直接在控制根（.git 为目录）写入，避免制造未提交脏树阻断 pm_merge.py。

退出码：0＝正常；1＝校验失败/数据损坏（失败关闭）；2＝用法或环境不对。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = PROJECT_ROOT.parents[3]
REGISTRY = Path("SYS-2026-001_WorkspaceGovernance") / "workspace_registry.json"
PLC_PREFIX = "0100_PLC自动化/"
HANDOFF_DIR_NAME = "交接交换区"
DEFAULT_MONITOR_DIR = "04_监控"
PLC_MONITOR_DIR = "11_监控"
FOCUS_FILE = "focus.json"
JOURNAL_FILE = "journal.jsonl"

FOCUS_SCHEMA = "local-handoff-focus.v1"
EVENT_SCHEMA = "local-handoff-event.v1"
EVENT_KINDS: tuple[str, ...] = ("handoff", "takeover", "blocked", "merged", "decision_note")
PID_PATTERN = re.compile(r"^[A-Z]{2,4}-\d{4}-\d{3}$")

FOCUS_KEYS = frozenset(
    {
        "schema",
        "project_id",
        "updated_at",
        "updated_by",
        "stage_goal",
        "priorities",
        "active_work",
        "waiting_for_user",
        "next_action",
    }
)
PRIORITY_KEYS = frozenset({"rank", "item", "ref"})
ACTIVE_WORK_KEYS = frozenset({"card", "branch", "chg", "breakpoint"})
EVENT_KEYS = frozenset(
    {
        "schema",
        "ts",
        "agent",
        "kind",
        "card",
        "commit",
        "chg",
        "summary",
        "read_first",
        "next",
    }
)

STALE_DAYS = 7
MAX_ACTOR = 40
MAX_STAGE_GOAL = 120
MAX_PRIORITIES = 5
MAX_PRIORITY_ITEM = 100
MAX_REF = 120
MAX_CARD = 64
MAX_BRANCH = 120
MAX_CHG = 64
MAX_COMMIT = 40
MAX_BREAKPOINT = 150
MAX_WAITING = 5
MAX_WAITING_ITEM = 150
MAX_NEXT = 150
MAX_SUMMARY = 200
MAX_READ_FIRST = 10
DEFAULT_TAIL = 5
GIT_TIMEOUT = 30

EXIT_OK = 0
EXIT_INVALID = 1
EXIT_USAGE = 2

Runner = Callable[..., Any]


@dataclass
class LoadResult:
    """读取并校验项目交接交换区的结果。"""

    pid: str
    handoff_dir: Path
    handoff_rel: str
    exists: bool = False
    focus: dict[str, Any] | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _format_ts(moment: datetime | None = None) -> str:
    return (moment or _now_utc()).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso_utc(raw: Any, field_name: str, errors: list[str]) -> datetime | None:
    if not isinstance(raw, str) or not raw.strip():
        errors.append(f"{field_name} 必须是非空 UTC ISO-8601 时间字符串")
        return None
    text = raw.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{field_name} 时间格式不合法：{raw!r}")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{field_name} 必须带时区（如末尾 Z 或 +00:00）：{raw!r}")
        return None
    return parsed.astimezone(UTC)


def _safe_relative(path: Any) -> bool:
    if not isinstance(path, str):
        return False
    if (
        not path
        or path != path.strip()
        or "\\" in path
        or path.startswith("/")
        or re.match(r"^[A-Za-z]:", path)
    ):
        return False
    return all(part not in {"", ".", ".."} for part in path.split("/"))


def _check_str(
    value: Any,
    field_name: str,
    *,
    max_len: int,
    required: bool,
    errors: list[str],
) -> None:
    if not isinstance(value, str):
        errors.append(f"{field_name} 必须是字符串")
        return
    stripped = value.strip()
    if required and not stripped:
        errors.append(f"{field_name} 不能为空")
        return
    if len(value) > max_len:
        errors.append(f"{field_name} 长度 {len(value)} 超过上限 {max_len}")


def project_root_of(root: Path, pid: str) -> str | None:
    """从 workspace_registry.json 查项目相对路径（正斜杠，不带末尾斜杠）。"""
    try:
        data = json.loads((root / REGISTRY).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    for project in data.get("projects", []):
        if isinstance(project, dict) and project.get("project_id") == pid:
            rel = str(project.get("project_root", "")).replace("\\", "/").strip("/")
            return rel or None
    return None


def handoff_rel_of(project_root: str) -> str:
    """按项目类型返回跨项目零冲突的交接交换区相对路径。"""
    clean = project_root.replace("\\", "/").strip("/")
    monitor = PLC_MONITOR_DIR if (clean + "/").startswith(PLC_PREFIX) else DEFAULT_MONITOR_DIR
    return f"{clean}/{monitor}/{HANDOFF_DIR_NAME}"


def handoff_dir_of(root: Path, pid: str) -> tuple[Path, str] | None:
    project_root = project_root_of(root, pid)
    if project_root is None:
        return None
    rel = handoff_rel_of(project_root)
    return root / rel, rel


def is_control_root(root: Path) -> bool:
    """控制根的 .git 是目录；git worktree 的 .git 是文件。"""
    return (root / ".git").is_dir()


def validate_focus(data: Any, expected_pid: str) -> list[str]:
    """按 PM-056 V2.0.0 §13.2 严格校验 focus.json 对象，返回错误列表。"""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["focus.json 顶层必须是 JSON 对象"]
    missing = sorted(FOCUS_KEYS - set(data))
    extra = sorted(set(data) - FOCUS_KEYS)
    if missing:
        errors.append(f"focus.json 缺少必填字段：{', '.join(missing)}")
    if extra:
        errors.append(f"focus.json 含未定义字段：{', '.join(extra)}")
    if missing or extra:
        return errors

    if data["schema"] != FOCUS_SCHEMA:
        errors.append(f"focus.json schema 不匹配：期望 {FOCUS_SCHEMA!r}，实际 {data['schema']!r}")
    if data["project_id"] != expected_pid:
        errors.append(
            f"focus.json project_id 不匹配：期望 {expected_pid!r}，实际 {data['project_id']!r}"
        )
    _parse_iso_utc(data["updated_at"], "focus.updated_at", errors)
    _check_str(data["updated_by"], "focus.updated_by", max_len=MAX_ACTOR, required=True, errors=errors)
    _check_str(
        data["stage_goal"], "focus.stage_goal", max_len=MAX_STAGE_GOAL, required=True, errors=errors
    )
    _check_str(
        data["next_action"], "focus.next_action", max_len=MAX_NEXT, required=True, errors=errors
    )

    priorities = data["priorities"]
    if not isinstance(priorities, list):
        errors.append("focus.priorities 必须是数组")
    else:
        if len(priorities) > MAX_PRIORITIES:
            errors.append(f"focus.priorities 条数 {len(priorities)} 超过上限 {MAX_PRIORITIES}")
        seen_ranks: set[int] = set()
        for idx, item in enumerate(priorities, start=1):
            label = f"focus.priorities[{idx}]"
            if not isinstance(item, dict):
                errors.append(f"{label} 必须是对象")
                continue
            p_missing = sorted(PRIORITY_KEYS - set(item))
            p_extra = sorted(set(item) - PRIORITY_KEYS)
            if p_missing or p_extra:
                errors.append(
                    f"{label} 字段不合法（缺少 {p_missing or '无'}，多余 {p_extra or '无'}）"
                )
                continue
            rank = item["rank"]
            if isinstance(rank, bool) or not isinstance(rank, int) or not (1 <= rank <= MAX_PRIORITIES):
                errors.append(f"{label}.rank 必须是 1..{MAX_PRIORITIES} 整数")
            elif rank in seen_ranks:
                errors.append(f"{label}.rank 重复：{rank}")
            else:
                seen_ranks.add(rank)
            _check_str(
                item["item"], f"{label}.item", max_len=MAX_PRIORITY_ITEM, required=True, errors=errors
            )
            _check_str(item["ref"], f"{label}.ref", max_len=MAX_REF, required=False, errors=errors)

    active = data["active_work"]
    if active is not None:
        if not isinstance(active, dict):
            errors.append("focus.active_work 必须是对象或 null")
        else:
            a_missing = sorted(ACTIVE_WORK_KEYS - set(active))
            a_extra = sorted(set(active) - ACTIVE_WORK_KEYS)
            if a_missing or a_extra:
                errors.append(
                    f"focus.active_work 字段不合法（缺少 {a_missing or '无'}，多余 {a_extra or '无'}）"
                )
            else:
                _check_str(
                    active["card"], "focus.active_work.card", max_len=MAX_CARD, required=True, errors=errors
                )
                _check_str(
                    active["branch"],
                    "focus.active_work.branch",
                    max_len=MAX_BRANCH,
                    required=False,
                    errors=errors,
                )
                _check_str(
                    active["chg"], "focus.active_work.chg", max_len=MAX_CHG, required=False, errors=errors
                )
                _check_str(
                    active["breakpoint"],
                    "focus.active_work.breakpoint",
                    max_len=MAX_BREAKPOINT,
                    required=False,
                    errors=errors,
                )

    waiting = data["waiting_for_user"]
    if not isinstance(waiting, list):
        errors.append("focus.waiting_for_user 必须是数组")
    else:
        if len(waiting) > MAX_WAITING:
            errors.append(f"focus.waiting_for_user 条数 {len(waiting)} 超过上限 {MAX_WAITING}")
        for idx, item in enumerate(waiting, start=1):
            _check_str(
                item,
                f"focus.waiting_for_user[{idx}]",
                max_len=MAX_WAITING_ITEM,
                required=True,
                errors=errors,
            )

    return errors


def validate_event(data: Any, line_no: int) -> list[str]:
    """按 PM-056 V2.0.0 §13.2 严格校验 journal.jsonl 单行对象。"""
    prefix = f"journal.jsonl 第 {line_no} 行"
    if not isinstance(data, dict):
        return [f"{prefix}：必须是 JSON 对象"]
    missing = sorted(EVENT_KEYS - set(data))
    extra = sorted(set(data) - EVENT_KEYS)
    errors: list[str] = []
    if missing:
        errors.append(f"{prefix}：缺少必填字段 {', '.join(missing)}")
    if extra:
        errors.append(f"{prefix}：含未定义字段 {', '.join(extra)}")
    if errors:
        return errors

    if data["schema"] != EVENT_SCHEMA:
        errors.append(f"{prefix}：schema 不匹配，期望 {EVENT_SCHEMA!r}，实际 {data['schema']!r}")
    _parse_iso_utc(data["ts"], f"{prefix}.ts", errors)
    _check_str(data["agent"], f"{prefix}.agent", max_len=MAX_ACTOR, required=True, errors=errors)
    if data["kind"] not in EVENT_KINDS:
        errors.append(f"{prefix}.kind 不合法：{data['kind']!r}（只认 {', '.join(EVENT_KINDS)}）")
    _check_str(data["card"], f"{prefix}.card", max_len=MAX_CARD, required=False, errors=errors)
    _check_str(data["commit"], f"{prefix}.commit", max_len=MAX_COMMIT, required=False, errors=errors)
    _check_str(data["chg"], f"{prefix}.chg", max_len=MAX_CHG, required=False, errors=errors)
    _check_str(
        data["summary"], f"{prefix}.summary", max_len=MAX_SUMMARY, required=True, errors=errors
    )
    _check_str(data["next"], f"{prefix}.next", max_len=MAX_NEXT, required=False, errors=errors)

    read_first = data["read_first"]
    if not isinstance(read_first, list):
        errors.append(f"{prefix}.read_first 必须是数组")
    else:
        if len(read_first) > MAX_READ_FIRST:
            errors.append(f"{prefix}.read_first 条数 {len(read_first)} 超过上限 {MAX_READ_FIRST}")
        for idx, path in enumerate(read_first, start=1):
            if not _safe_relative(path):
                errors.append(
                    f"{prefix}.read_first[{idx}] 必须是合法相对正斜杠路径（禁止绝对路径或 ..）：{path!r}"
                )
    return errors


def load_handoff(root: Path, pid: str) -> LoadResult | None:
    """读取并严格校验项目交接交换区；项目未登记返回 None。"""
    located = handoff_dir_of(root, pid)
    if located is None:
        return None
    handoff_dir, handoff_rel = located
    result = LoadResult(pid=pid, handoff_dir=handoff_dir, handoff_rel=handoff_rel)
    focus_path = handoff_dir / FOCUS_FILE
    journal_path = handoff_dir / JOURNAL_FILE
    has_focus = focus_path.exists()
    has_journal = journal_path.exists()
    result.exists = has_focus or has_journal
    if not result.exists:
        return result

    if has_focus:
        try:
            raw_focus = focus_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            result.errors.append(f"{FOCUS_FILE} 读取失败（须为合法 UTF-8）：{error}")
        else:
            try:
                parsed_focus = json.loads(raw_focus)
            except ValueError as error:
                result.errors.append(f"{FOCUS_FILE} JSON 解析失败：{error}")
            else:
                focus_errors = validate_focus(parsed_focus, pid)
                if focus_errors:
                    result.errors.extend(focus_errors)
                else:
                    result.focus = parsed_focus

    if has_journal:
        try:
            raw_journal = journal_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            result.errors.append(f"{JOURNAL_FILE} 读取失败（须为合法 UTF-8）：{error}")
        else:
            for line_no, raw_line in enumerate(raw_journal.splitlines(), start=1):
                if not raw_line.strip():
                    continue
                try:
                    parsed_event = json.loads(raw_line)
                except ValueError as error:
                    result.errors.append(f"{JOURNAL_FILE} 第 {line_no} 行 JSON 解析失败：{error}")
                    continue
                event_errors = validate_event(parsed_event, line_no)
                if event_errors:
                    result.errors.extend(event_errors)
                else:
                    result.events.append(parsed_event)

    return result


def _run_git(root: Path, args: Sequence[str], runner: Runner) -> tuple[int, str]:
    try:
        done = runner(
            ["git", "-C", str(root), "-c", "core.fsmonitor=false", "-c", "core.quotepath=off", *args],
            capture_output=True,
            timeout=GIT_TIMEOUT,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 1, ""
    out = (
        done.stdout
        if isinstance(done.stdout, str)
        else (done.stdout or b"").decode("utf-8", errors="replace")
    )
    return int(done.returncode), out


def _live_dev_worktrees(root: Path, runner: Runner) -> list[tuple[str, str]] | None:
    """列出除控制根及只读 deploy-* 之外的活跃开发工位：(工位目录名, 短分支名)。非 git 仓库返回 None。"""
    rc, out = _run_git(root, ("worktree", "list", "--porcelain"), runner)
    if rc != 0:
        return None
    blocks = [block.strip() for block in out.replace("\r\n", "\n").split("\n\n") if block.strip()]
    dev: list[tuple[str, str]] = []
    for index, block in enumerate(blocks):
        wt_path = ""
        branch = ""
        for line in block.splitlines():
            if line.startswith("worktree "):
                wt_path = line[len("worktree ") :].strip()
            elif line.startswith("branch "):
                branch = line[len("branch ") :].strip().removeprefix("refs/heads/")
        if not wt_path:
            continue
        candidate = Path(wt_path)
        # git worktree list --porcelain 第 0 块固定为主工作树（控制根，其 .git 为目录）；
        # 不能按 candidate == root 排除，否则从工位执行 --root <工位> 时会误排除当前工位自身。
        if index == 0 or (candidate / ".git").is_dir():
            continue
        name = candidate.name
        if name.startswith("deploy-"):
            continue
        if branch:
            dev.append((name, branch))
    return dev


def collect_warnings(
    root: Path,
    focus: Mapping[str, Any] | None,
    shown_events: Sequence[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    runner: Runner = subprocess.run,
) -> list[str]:
    """现场生成陈旧提醒、Git 事实漂移提醒和缺失先读文件提醒（不阻断退出 0）。"""
    warnings: list[str] = []
    moment = (now or _now_utc()).astimezone(UTC)

    if focus is not None:
        ts_errors: list[str] = []
        updated = _parse_iso_utc(focus.get("updated_at"), "focus.updated_at", ts_errors)
        if updated is not None and (moment - updated) > timedelta(days=STALE_DAYS):
            age_days = int((moment - updated).total_seconds() // 86400)
            warnings.append(
                f"陈旧提醒：focus.json 已 {age_days} 天未更新（超过 {STALE_DAYS} 天，最后更新 {focus['updated_at']}），请核对后再动手"
            )

    live_wts = _live_dev_worktrees(root, runner)
    if live_wts is not None and focus is not None:
        active = focus.get("active_work")
        active_branch = (
            str(active.get("branch", "")).strip() if isinstance(active, Mapping) else ""
        )
        live_branches = {branch for _, branch in live_wts}
        if active_branch and active_branch not in live_branches:
            rc_ref, _ = _run_git(root, ("rev-parse", "--verify", "--quiet", f"refs/heads/{active_branch}"), runner)
            if rc_ref != 0:
                warnings.append(
                    f"事实漂移提醒：focus.json 的 active_work 分支 {active_branch} 在本机已不存在（可能已合并收工位），请以 Git 事实为准"
                )
            else:
                rc_merged, _ = _run_git(
                    root, ("merge-base", "--is-ancestor", f"refs/heads/{active_branch}", "refs/heads/main"), runner
                )
                if rc_merged == 0:
                    warnings.append(
                        f"事实漂移提醒：focus.json 的 active_work 分支 {active_branch} 已并入 main 且无活跃工位，请更新 focus.json"
                    )
                else:
                    warnings.append(
                        f"事实漂移提醒：focus.json 的 active_work 分支 {active_branch} 不在当前活跃工位列表中，请核对 worktree list"
                    )
        for wt_name, wt_branch in live_wts:
            if wt_branch != active_branch:
                warnings.append(
                    f"事实漂移提醒：本机存在未登记在 focus.json 的活跃工位 {wt_name}（分支 {wt_branch}），请以 Git 工位事实为准"
                )

    seen_missing: set[str] = set()
    for event in shown_events:
        for rel_path in event.get("read_first") or []:
            if isinstance(rel_path, str) and rel_path not in seen_missing:
                if not (root / rel_path).exists():
                    seen_missing.add(rel_path)
                    warnings.append(f"先读文件缺失：{rel_path}（当前仓库不存在）")

    return warnings


def show_handoff(
    pid: str,
    *,
    root: Path,
    tail: int = DEFAULT_TAIL,
    as_json: bool = False,
    now: datetime | None = None,
    runner: Runner = subprocess.run,
    out: Callable[[str], None] = print,
) -> int:
    """只读展示项目本机交接交换区；数据损坏失败关闭返回 1。"""
    if not PID_PATTERN.match(pid):
        out(f"项目号格式不对：{pid!r}（应像 SW-2026-008）")
        return EXIT_USAGE
    if tail < 0:
        out(f"--tail 不能为负数：{tail}")
        return EXIT_USAGE
    loaded = load_handoff(root, pid)
    if loaded is None:
        out(f"项目登记表里查不到 {pid}（{root / REGISTRY}）")
        return EXIT_USAGE

    if not loaded.exists:
        payload: dict[str, Any] = {
            "pid": pid,
            "handoff_dir": loaded.handoff_rel,
            "exists": False,
            "ok": True,
            "focus": None,
            "events_total": 0,
            "events": [],
            "warnings": [],
            "errors": [],
        }
        if as_json:
            out(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            out(f"【本机交接交换区】{pid}")
            out(f"本项目尚未建立本机交接交换区（{loaded.handoff_rel}），暂无本地焦点与交接记录。")
        return EXIT_OK

    if not loaded.ok:
        payload = {
            "pid": pid,
            "handoff_dir": loaded.handoff_rel,
            "exists": True,
            "ok": False,
            "focus": loaded.focus,
            "events_total": len(loaded.events),
            "events": [],
            "warnings": [],
            "errors": loaded.errors,
        }
        if as_json:
            out(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            out(f"【本机交接交换区】{pid}（目录：{loaded.handoff_rel}）")
            out("✗ 交接交换区校验失败（PM-056 失败关闭，请修复后重试）：")
            for error in loaded.errors:
                out(f"  - {error}")
        return EXIT_INVALID

    shown_events = loaded.events[-tail:] if tail > 0 else []
    warnings = collect_warnings(root, loaded.focus, shown_events, now=now, runner=runner)

    if as_json:
        payload = {
            "pid": pid,
            "handoff_dir": loaded.handoff_rel,
            "exists": True,
            "ok": True,
            "focus": loaded.focus,
            "events_total": len(loaded.events),
            "events": shown_events,
            "warnings": warnings,
            "errors": [],
        }
        out(json.dumps(payload, ensure_ascii=False, indent=2))
        return EXIT_OK

    out(f"【本机交接交换区】{pid}（目录：{loaded.handoff_rel}）")
    out("注意：本区仅承载阶段焦点、优先级与断点，不是授权源，不覆盖 Git 与账本机器事实（PM-056 V2.0.0）。")
    if loaded.focus is not None:
        focus = loaded.focus
        out(f"更新：{focus['updated_at']}（{focus['updated_by']}）")
        out(f"阶段目标：{focus['stage_goal']}")
        priorities = sorted(focus["priorities"], key=lambda item: item["rank"])
        if priorities:
            out("当前优先级：")
            for item in priorities:
                ref_part = f"（参考：{item['ref']}）" if item["ref"] else ""
                out(f"  {item['rank']}. {item['item']}{ref_part}")
        else:
            out("当前优先级：无")
        active = focus["active_work"]
        if active is None:
            out("当前在干：无")
        else:
            parts = [f"卡 {active['card']}"]
            if active["branch"]:
                parts.append(f"分支 {active['branch']}")
            if active["chg"]:
                parts.append(f"变更单 {active['chg']}")
            if active["breakpoint"]:
                parts.append(f"断点：{active['breakpoint']}")
            out("当前在干：" + " | ".join(parts))
        waiting = focus["waiting_for_user"]
        if waiting:
            out("待用户确认：")
            for item in waiting:
                out(f"  - {item}")
        else:
            out("待用户确认：无")
        out(f"下一步：{focus['next_action']}")
    else:
        out("focus.json 尚未建立（仅有 journal.jsonl）。")

    if shown_events:
        out(f"最近交接记录（共 {len(loaded.events)} 条，展示最后 {len(shown_events)} 条）：")
        for event in shown_events:
            meta = [f"[{event['ts']}]", event["kind"], event["agent"]]
            if event["card"]:
                meta.append(f"卡 {event['card']}")
            if event["commit"]:
                meta.append(f"提交 {event['commit']}")
            if event["chg"]:
                meta.append(event["chg"])
            out("  - " + " | ".join(meta))
            out(f"    摘要：{event['summary']}")
            if event["next"]:
                out(f"    下一棒：{event['next']}")
            if event["read_first"]:
                out("    先读：" + "、".join(event["read_first"]))
    else:
        out("最近交接记录：无")

    if warnings:
        out("⚠ 提醒：")
        for warning in warnings:
            out(f"  - {warning}")
    return EXIT_OK


def validate_command(
    pid: str,
    *,
    root: Path,
    require_exists: bool = False,
    out: Callable[[str], None] = print,
) -> int:
    if not PID_PATTERN.match(pid):
        out(f"项目号格式不对：{pid!r}（应像 SW-2026-008）")
        return EXIT_USAGE
    loaded = load_handoff(root, pid)
    if loaded is None:
        out(f"项目登记表里查不到 {pid}（{root / REGISTRY}）")
        return EXIT_USAGE
    if not loaded.exists:
        if require_exists:
            out(f"✗ 交接交换区不存在：{loaded.handoff_rel}")
            return EXIT_INVALID
        out(f"✓ {pid} 尚未建立交接交换区（{loaded.handoff_rel}），无格式错误。")
        return EXIT_OK
    if not loaded.ok:
        out(f"✗ {pid} 交接交换区校验失败（{len(loaded.errors)} 处）：")
        for error in loaded.errors:
            out(f"  - {error}")
        return EXIT_INVALID
    out(
        f"✓ {pid} 交接交换区校验通过（focus={'有' if loaded.focus else '无'}，journal={len(loaded.events)} 条）。"
    )
    return EXIT_OK


def parse_priority_arg(raw: str) -> dict[str, Any]:
    """解析 --priority '1:事项说明[:参考路径或卡号]'。"""
    parts = raw.split(":", 2)
    if len(parts) < 2:
        raise ValueError(f"--priority 格式应为 '序号:事项[:参考]'，实际：{raw!r}")
    rank_str = parts[0].strip()
    if not rank_str.isdigit():
        raise ValueError(f"--priority 序号必须是 1..5 整数，实际：{rank_str!r}")
    item = parts[1].strip()
    ref = parts[2].strip() if len(parts) == 3 else ""
    return {"rank": int(rank_str), "item": item, "ref": ref}


def set_focus_command(
    pid: str,
    *,
    root: Path,
    updated_by: str,
    stage_goal: str,
    next_action: str,
    priorities: Sequence[dict[str, Any]] = (),
    active_card: str = "",
    active_branch: str = "",
    active_chg: str = "",
    active_breakpoint: str = "",
    waiting_for_user: Sequence[str] = (),
    allow_control_root: bool = False,
    now: datetime | None = None,
    out: Callable[[str], None] = print,
) -> int:
    if not PID_PATTERN.match(pid):
        out(f"项目号格式不对：{pid!r}（应像 SW-2026-008）")
        return EXIT_USAGE
    if is_control_root(root) and not allow_control_root:
        out(
            "拒绝写入：目标路径是控制根（.git 为目录），直接改已跟踪的交接文件会造成未提交脏树阻断 pm_merge.py。\n"
            "请把 --root 指向你的工位目录后写入并提交；如确认必须写控制根，显式加 --allow-control-root。"
        )
        return EXIT_USAGE
    located = handoff_dir_of(root, pid)
    if located is None:
        out(f"项目登记表里查不到 {pid}（{root / REGISTRY}）")
        return EXIT_USAGE
    handoff_dir, handoff_rel = located

    active_work: dict[str, str] | None = None
    if active_card or active_branch or active_chg or active_breakpoint:
        active_work = {
            "card": active_card.strip(),
            "branch": active_branch.strip(),
            "chg": active_chg.strip(),
            "breakpoint": active_breakpoint.strip(),
        }

    payload: dict[str, Any] = {
        "schema": FOCUS_SCHEMA,
        "project_id": pid,
        "updated_at": _format_ts(now),
        "updated_by": updated_by.strip(),
        "stage_goal": stage_goal.strip(),
        "priorities": list(priorities),
        "active_work": active_work,
        "waiting_for_user": [item.strip() for item in waiting_for_user],
        "next_action": next_action.strip(),
    }
    errors = validate_focus(payload, pid)
    if errors:
        out("✗ 写入前校验失败（未修改文件）：")
        for error in errors:
            out(f"  - {error}")
        return EXIT_INVALID

    handoff_dir.mkdir(parents=True, exist_ok=True)
    target = handoff_dir / FOCUS_FILE
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    target.write_text(text, encoding="utf-8", newline="\n")
    out(f"✓ 已更新 {handoff_rel}/{FOCUS_FILE}")
    return EXIT_OK


def append_log_command(
    pid: str,
    *,
    root: Path,
    agent: str,
    kind: str,
    summary: str,
    card: str = "",
    commit: str = "",
    chg: str = "",
    read_first: Sequence[str] = (),
    next_hint: str = "",
    allow_control_root: bool = False,
    now: datetime | None = None,
    out: Callable[[str], None] = print,
) -> int:
    if not PID_PATTERN.match(pid):
        out(f"项目号格式不对：{pid!r}（应像 SW-2026-008）")
        return EXIT_USAGE
    if is_control_root(root) and not allow_control_root:
        out(
            "拒绝写入：目标路径是控制根（.git 为目录），直接改已跟踪的交接文件会造成未提交脏树阻断 pm_merge.py。\n"
            "请把 --root 指向你的工位目录后写入并提交；如确认必须写控制根，显式加 --allow-control-root。"
        )
        return EXIT_USAGE
    located = handoff_dir_of(root, pid)
    if located is None:
        out(f"项目登记表里查不到 {pid}（{root / REGISTRY}）")
        return EXIT_USAGE
    handoff_dir, handoff_rel = located

    # 先校验已有 journal.jsonl，避免向已损坏的文件继续追加（失败关闭）。
    journal_path = handoff_dir / JOURNAL_FILE
    if journal_path.exists():
        loaded = load_handoff(root, pid)
        if loaded is not None and not loaded.ok:
            out("✗ 现有交接交换区已存在校验错误，拒绝追加（请先修复）：")
            for error in loaded.errors:
                out(f"  - {error}")
            return EXIT_INVALID

    event: dict[str, Any] = {
        "schema": EVENT_SCHEMA,
        "ts": _format_ts(now),
        "agent": agent.strip(),
        "kind": kind.strip(),
        "card": card.strip(),
        "commit": commit.strip(),
        "chg": chg.strip(),
        "summary": summary.strip(),
        "read_first": [path.strip() for path in read_first if path.strip()],
        "next": next_hint.strip(),
    }
    errors = validate_event(event, 1)
    if errors:
        out("✗ 写入前校验失败（未修改文件）：")
        for error in errors:
            out(f"  - {error}")
        return EXIT_INVALID

    handoff_dir.mkdir(parents=True, exist_ok=True)
    need_leading_newline = False
    if journal_path.exists():
        raw_bytes = journal_path.read_bytes()
        need_leading_newline = bool(raw_bytes) and not raw_bytes.endswith(b"\n")
    line = ("\n" if need_leading_newline else "") + json.dumps(
        event, ensure_ascii=False, separators=(",", ":")
    ) + "\n"
    with journal_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
    out(f"✓ 已追加交接事件到 {handoff_rel}/{JOURNAL_FILE}")
    return EXIT_OK


def utf8_output(streams: Sequence[Any] | None = None) -> None:
    """保证中文 Windows 重定向/管道输出写 UTF-8 不崩。"""
    for stream in (sys.stdout, sys.stderr) if streams is None else streams:
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            tty = bool(stream.isatty())
        except (OSError, ValueError):
            tty = False
        try:
            if tty:
                reconfigure(errors="backslashreplace")
            else:
                reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):
            continue


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="本机轻轨交接交换区读写与核验工具（PM-056 V2.0.0，local-handoff.v1）"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_show = sub.add_parser("show", help="只读展示项目交接交换区，并核对陈旧与 Git 漂移")
    p_show.add_argument("pid", help="项目编号，如 SW-2026-008")
    p_show.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="仓库根（控制根或工位）")
    p_show.add_argument("--tail", type=int, default=DEFAULT_TAIL, help="展示最近几条 journal 事件")
    p_show.add_argument("--json", dest="as_json", action="store_true", help="以 JSON 输出")

    p_val = sub.add_parser("validate", help="只读校验 focus.json 与 journal.jsonl 结构与红线")
    p_val.add_argument("pid", help="项目编号，如 SW-2026-008")
    p_val.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="仓库根（控制根或工位）")
    p_val.add_argument(
        "--require-exists", action="store_true", help="交接交换区不存在时也报失败（退出 1）"
    )

    p_focus = sub.add_parser("set-focus", help="覆盖写入 focus.json（默认须在工位执行）")
    p_focus.add_argument("pid", help="项目编号")
    p_focus.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="目标工位根目录")
    p_focus.add_argument("--by", required=True, help="更新者署名，如 antigravity / claude")
    p_focus.add_argument("--goal", required=True, help="当前阶段总目标（<=120 字符）")
    p_focus.add_argument("--next", dest="next_action", required=True, help="新对话第一步（<=150 字符）")
    p_focus.add_argument(
        "--priority",
        action="append",
        default=[],
        help="优先事项，格式 '序号:事项[:参考]'，可重复最多 5 次",
    )
    p_focus.add_argument("--card", default="", help="当前在干卡号")
    p_focus.add_argument("--branch", default="", help="当前在干分支名")
    p_focus.add_argument("--chg", default="", help="当前关联变更单号")
    p_focus.add_argument("--breakpoint", default="", help="断点上下文（<=150 字符）")
    p_focus.add_argument(
        "--waiting", action="append", default=[], help="待用户确认事项（可重复最多 5 次）"
    )
    p_focus.add_argument(
        "--allow-control-root", action="store_true", help="显式允许在控制根直接写入（慎用）"
    )

    p_log = sub.add_parser("log", help="向 journal.jsonl 追加一条交接事件（默认须在工位执行）")
    p_log.add_argument("pid", help="项目编号")
    p_log.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="目标工位根目录")
    p_log.add_argument("--agent", required=True, help="记录者署名")
    p_log.add_argument("--kind", required=True, choices=EVENT_KINDS, help="事件类型")
    p_log.add_argument("--summary", required=True, help="一句话结论或断点（<=200 字符）")
    p_log.add_argument("--card", default="", help="关联卡号")
    p_log.add_argument("--commit", default="", help="关联 Git 提交号")
    p_log.add_argument("--chg", default="", help="关联变更单号")
    p_log.add_argument(
        "--read-first", action="append", default=[], help="接手前先读的相对路径（可重复最多 10 次）"
    )
    p_log.add_argument("--next", dest="next_hint", default="", help="下一棒建议（<=150 字符）")
    p_log.add_argument(
        "--allow-control-root", action="store_true", help="显式允许在控制根直接写入（慎用）"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    utf8_output()
    parser = _build_parser()
    options = parser.parse_args(argv)
    root = options.root.resolve()
    if options.command == "show":
        return show_handoff(
            options.pid,
            root=root,
            tail=options.tail,
            as_json=options.as_json,
        )
    if options.command == "validate":
        return validate_command(
            options.pid,
            root=root,
            require_exists=options.require_exists,
        )
    if options.command == "set-focus":
        try:
            priorities = [parse_priority_arg(item) for item in options.priority]
        except ValueError as error:
            print(str(error))
            return EXIT_USAGE
        return set_focus_command(
            options.pid,
            root=root,
            updated_by=options.by,
            stage_goal=options.goal,
            next_action=options.next_action,
            priorities=priorities,
            active_card=options.card,
            active_branch=options.branch,
            active_chg=options.chg,
            active_breakpoint=options.breakpoint,
            waiting_for_user=options.waiting,
            allow_control_root=options.allow_control_root,
        )
    if options.command == "log":
        return append_log_command(
            options.pid,
            root=root,
            agent=options.agent,
            kind=options.kind,
            summary=options.summary,
            card=options.card,
            commit=options.commit,
            chg=options.chg,
            read_first=options.read_first,
            next_hint=options.next_hint,
            allow_control_root=options.allow_control_root,
        )
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
