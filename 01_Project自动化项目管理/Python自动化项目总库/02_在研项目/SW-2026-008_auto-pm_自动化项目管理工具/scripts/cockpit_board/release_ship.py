"""发版页的“同意切换”（CHG-SCPT-2026-707，卡 290）：候选版本从哪来、``release ship --json`` 怎么读、按钮什么时候能点、凭据长什么样。

纯函数，不起子进程、不写文件（写批准记录在 actions.record_board_approval，起命令在 release_controller 经 actions.run_cli）。
命令的输出格式按 ``release ship`` 接口约定（CHG-SCPT-2026-706）：一个 JSON 对象，含 commit、release_id、active_release、
gate、audit、preflight、changes、can_switch、deployed、result。

像 HMI 上的“允许启动”：按钮亮不亮由上位机按联锁条件算，PLC（这里是 ``release ship``）收到命令还要自己再判一遍。
页上的判断只是让人先看明白差哪一条，真正的护栏在命令里。
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cockpit_board import policy

CANDIDATE_DIR = Path(".auto-pm") / "release-candidates"
APPROVAL_RECORD = Path(".auto-pm") / "reports" / "board_approvals" / "release_ship.jsonl"  # .auto-pm/reports/ 已被忽略，留得住
RELEASE_ID = re.compile(r"\d+\.\d+\.\d+-([0-9a-f]{7})")
COMMIT = re.compile(r"[0-9a-f]{7,40}")
SESSION = re.compile(r"[0-9a-f]{8,32}")
LISTED_CANDIDATES = 5  # 最多列几个候选版本（按文件夹修改时间，新的在前）
LISTED_CHANGES = 12
CHECK_TIMEOUT = 180  # 只看：要从 GitHub 下门禁判决，比普通只读命令慢
SWITCH_TIMEOUT = 1800  # 真发版：演练、部署、失败时自动退回，都在这一条命令里
SWITCH_PREFIX = policy.RELEASE_BUTTON_PREFIX  # “同意切换到 ”：例外的来由和护栏见 policy.py
CONFIRM_PREFIX = "user-confirmation:board-click:"
REF_PLACEHOLDER = "<点确认那一刻生成的凭据>"

GATE_ZH = {"pass": "判决 PASS", "fail": "判决 FAIL", "running": "门禁还在跑", "missing": "没有判决", "error": "读判决出错"}
AUDIT_ZH = {"present": "审计已放行（有放行记录）", "missing": "还没有审计放行记录"}  # 不写“签字”：policy.NEVER 里有这个词


@dataclass(frozen=True)
class Candidate:
    """一个候选版本：发布号和它对应的提交前 7 位（来自 ``.auto-pm/release-candidates/<发布号>/`` 文件夹名）。"""

    release_id: str
    commit: str


@dataclass(frozen=True)
class Check:
    """``release ship <提交> --json`` 读出来的一份结论；``problem`` 非空表示没读懂，别的字段不可信。"""

    candidate: Candidate
    rc: int | None
    problem: str = ""
    commit: str = ""
    release_id: str = ""
    active_release: str = ""
    gate: dict[str, Any] = field(default_factory=dict)
    audit: dict[str, Any] = field(default_factory=dict)
    preflight: dict[str, Any] = field(default_factory=dict)
    changes: tuple[dict[str, Any], ...] = ()
    can_switch: bool = False
    deployed: bool = False
    result: dict[str, Any] | None = None
    output: str = ""  # 原文（stdout 接 stderr），没读懂时贴给人看


def list_candidates(root: Path | None) -> list[Candidate]:
    """控制根 ``.auto-pm/release-candidates/`` 下按发布号命名的文件夹，新的在前；名字不像发布号的不认（不猜）。

    门禁判决和审计放行记录都放在这个文件夹里（接口约定“文件位置”），没有这个文件夹的提交按钮本来就是灰的，所以只列它们。
    """
    folder = (root / CANDIDATE_DIR) if root is not None else None
    if folder is None or not folder.is_dir():
        return []
    found: list[tuple[float, Candidate]] = []
    for path in folder.iterdir():
        match = RELEASE_ID.fullmatch(path.name)
        if not match or not path.is_dir():
            continue
        try:
            stamp = path.stat().st_mtime
        except OSError:
            continue
        found.append((stamp, Candidate(path.name, match.group(1))))
    found.sort(key=lambda item: (-item[0], item[1].release_id))
    return [candidate for _, candidate in found[:LISTED_CANDIDATES]]


def check_args(commit: str) -> tuple[str, ...]:
    return ("release", "ship", _commit(commit), "--json")


def switch_args(commit: str, confirm_ref: str, approver: str) -> tuple[str, ...]:
    return ("release", "ship", _commit(commit), "--no-check-only", "--confirm-ref", confirm_ref, "--approver", approver, "--json")


def shown_command(args: Sequence[str]) -> str:
    return "main.py " + " ".join(f'"{item}"' if " " in item or not item else item for item in args)


def allowed_command(args: Sequence[str]) -> bool:
    """只认 policy.RELEASE_COMMANDS 登记的两种形状：只看，或带凭据和批准人的真发版。别的参数一律不运行。"""
    items = tuple(args)
    if len(items) == 4:
        return items[:2] == ("release", "ship") and bool(COMMIT.fullmatch(items[2])) and items[3] == "--json"
    if len(items) == 9:
        return (items[:2] == ("release", "ship") and bool(COMMIT.fullmatch(items[2]))
                and items[3:4] == ("--no-check-only",) and items[4] == "--confirm-ref" and is_confirm_ref(items[5])
                and items[6] == "--approver" and bool(items[7].strip()) and not items[7].startswith("-") and items[8] == "--json")
    return False


def _commit(value: str) -> str:
    value = value.strip().lower()
    if not COMMIT.fullmatch(value):
        raise ValueError(f"提交号不对：{value!r}（只认 7～40 位十六进制）")
    return value


def utc_text(now: datetime) -> str:
    """凭据里的时间：UTC，精确到秒，带 Z。没带时区的当成本机时间再换成 UTC。"""
    moment = now if now.tzinfo is not None else now.astimezone()
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def confirm_ref(now: datetime, session: str) -> str:
    """``user-confirmation:board-click:<UTC 时间>:<看板会话号>``（接口约定）。只在用户本人点了确认键那一刻生成。"""
    if not SESSION.fullmatch(session):
        raise ValueError(f"看板会话号不对：{session!r}")
    return f"{CONFIRM_PREFIX}{utc_text(now)}:{session}"


def is_confirm_ref(value: str) -> bool:
    if not value.startswith(CONFIRM_PREFIX):
        return False
    stamp, _, session = value[len(CONFIRM_PREFIX):].rpartition(":")
    try:
        datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return bool(SESSION.fullmatch(session))


def parse_check(candidate: Candidate, rc: int | None, stdout: str, output: str = "") -> Check:
    """命令的 stdout → Check。不是一个 JSON 对象、缺 gate/audit、发布号对不上，都算没读懂，不猜、不补默认值。"""
    text = (stdout or "").strip()
    try:
        data = json.loads(text) if text else None
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        return Check(candidate, rc, "命令没有给出一个 JSON 对象", output=output or stdout)
    gate, audit = data.get("gate"), data.get("audit")
    if not isinstance(gate, dict) or not isinstance(audit, dict):
        return Check(candidate, rc, "输出里缺 gate 或 audit", output=output or stdout)
    release_id = str(data.get("release_id") or "")
    if release_id != candidate.release_id:
        return Check(candidate, rc, f"命令说的发布号是 {release_id or '（空）'}，不是 {candidate.release_id}", output=output or stdout)
    preflight = data.get("preflight") if isinstance(data.get("preflight"), dict) else {}
    changes = tuple(row for row in data.get("changes") or [] if isinstance(row, dict))
    result = data.get("result") if isinstance(data.get("result"), dict) else None
    return Check(candidate, rc, "", str(data.get("commit") or ""), release_id, str(data.get("active_release") or ""), gate, audit,
                 preflight or {}, changes, data.get("can_switch") is True, data.get("deployed") is True, result, output or stdout)


def gate_text(check: Check) -> str:
    state = str(check.gate.get("state") or "")
    parts = [GATE_ZH.get(state, state or "（没写）")]
    if check.gate.get("run_id") is not None:
        parts.append(f"运行 {check.gate['run_id']}")
    if check.gate.get("detail"):
        parts.append(str(check.gate["detail"]))
    return " · ".join(parts)


def audit_text(check: Check) -> str:
    state = str(check.audit.get("state") or "")
    parts = [AUDIT_ZH.get(state, state or "（没写）")]
    if check.audit.get("detail"):
        parts.append(str(check.audit["detail"]))
    return " · ".join(parts)


def preflight_rows(check: Check) -> list[tuple[str, str]]:
    rows = []
    for item in check.preflight.get("checks") or []:
        if isinstance(item, dict):
            mark = "✓" if item.get("ok") is True else "✗"
            rows.append((f"{mark} {item.get('name') or '（没写名字）'}", str(item.get("detail") or "")))
    return rows


def change_lines(check: Check) -> list[str]:
    lines = [f"#{row.get('pr')} {row.get('title') or ''}".rstrip() for row in check.changes[:LISTED_CHANGES]]
    if len(check.changes) > LISTED_CHANGES:
        lines.append(f"……另有 {len(check.changes) - LISTED_CHANGES} 条")
    return lines


def blocked_reason(check: Check | None, human_block: str = "", busy: bool = False) -> str:
    """“同意切换”按钮为什么灰着；空串＝可以点。一条一条按顺序判，只说差的第一条。"""
    if human_block:
        return human_block
    if busy:
        return "上一次切换还在跑，跑完再说"
    if check is None:
        return "还没读到这个版本的检查结论（正在检查，或检查没跑起来）"
    if check.problem:
        return "检查结论没读懂：" + check.problem
    if check.deployed or (check.active_release and check.active_release == check.release_id):
        return "已经是现在生效的版本"
    if str(check.gate.get("state") or "") != "pass":
        return "门禁没有 PASS 判决：" + gate_text(check)
    if str(check.audit.get("state") or "") != "present":
        return "审计还没放行：" + audit_text(check)
    if check.preflight.get("ok") is not True:
        failed = [name for name, _detail in preflight_rows(check) if name.startswith("✗")]
        return "预检没过：" + ("、".join(name[2:] for name in failed) or "命令没说是哪一项")
    if not check.can_switch:
        return "release ship 说现在不能切（can_switch 为 false）"
    if not COMMIT.fullmatch(check.commit or ""):
        return "命令没给出完整的提交号"
    if not check.commit.startswith(check.candidate.commit):
        return f"命令说的提交号 {check.commit[:12]} 和候选版本的 {check.candidate.commit} 对不上"
    return ""


def result_text(result: dict[str, Any] | None, rc: int | None, deployed: bool = True) -> tuple[str, str]:
    """真发版跑完：（一句话，sev）。sev 给卡片上色：ok / risk / block。

    ``deployed`` 为 False（命令自己再判一遍没过，退出码 2）：什么都没动，不是“没能退回”。"""
    if result is None:
        return ("没读到发版结果（命令没给出 result），看下面的原文和退出码", "block")
    message = str(result.get("message") or "")
    if result.get("ok") is True:
        return ("切换成了" + (f"：{message}" if message else ""), "ok")
    if result.get("rolled_back") is True:
        return ("没切成，已自动退回旧版本" + (f"：{message}" if message else ""), "risk")
    if not deployed or rc == 2:
        return ("没切成，命令再判一遍没过，版本没动" + (f"：{message}" if message else ""), "risk")
    return ("没切成，也没能退回旧版本，要人处理" + (f"：{message}" if message else "") + (f"（退出码 {rc}）" if rc else ""), "block")


def approval_record(check: Check, ref: str, approver: str, now: datetime, session: str) -> dict[str, Any]:
    """看板批准记录的一行：谁、何时点了“同意切换”，点的时候页上看到的门禁判决和审计放行记录是什么。"""
    return {
        "kind": "release_ship_switch",
        "confirm_ref": ref,
        "approver": approver,
        "clicked_at": utc_text(now),
        "session": session,
        "release_id": check.release_id,
        "commit": check.commit,
        "active_release": check.active_release,
        "gate_state": check.gate.get("state"),
        "gate_run_id": check.gate.get("run_id"),
        "verdict_sha256": check.gate.get("verdict_sha256"),
        "audit_state": check.audit.get("state"),
        "audit_path": check.audit.get("path"),
    }
