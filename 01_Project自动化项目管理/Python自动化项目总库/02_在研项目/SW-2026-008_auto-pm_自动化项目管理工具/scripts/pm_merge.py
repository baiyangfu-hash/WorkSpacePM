"""本机合并：日常改动在本机合进 main，GitHub 按需使用（CHG-SCPT-2026-718，卡 311）。

用法（在控制根，用控制根 .venv 里的 Python；Windows 是 .venv\\Scripts\\python.exe）：
  python <本项目>/scripts/pm_merge.py merge <工位名> [--pid <项目号>] [--full-gate]
  python <本项目>/scripts/pm_merge.py sync              从 GitHub 拉 main，只做快进
  python <本项目>/scripts/pm_merge.py push              把 main 推到 GitHub（“备份”“多机”档）
  python <本项目>/scripts/pm_merge.py github-mode [关|备份|多机]
  python <本项目>/scripts/pm_merge.py install-hook      装守 main 的本机钩子
  python <本项目>/scripts/pm_merge.py verify-log [--since <提交>]

``merge`` 按顺序查，任何一条不过就拒绝，什么都不改：
1. 控制根停在 main；工位 ``.auto-pm/worktrees/<工位名>`` 已全部提交，main 是工位分支的祖先，
   分支上至少一个提交带 ``领卡占位: <卡号>`` 这一行。
2. 改到“要你点头”那一类文件的（规则文件、PLC 项目文件、PLC 模板、本命令自己，以及删除或改名驾驶舱项目目录以外
   的已入库文件），以及明确绑定变更单的分支，核对实施卡、变更单、实际路径和独立审计凭证。
   审计绑定候选提交和当前 main。
3. GitHub 开启且可达时，``origin/main`` 必须已在本机 main 里；多机档无法对账时拒绝合并。
4. 控制根同路径副本须与候选相符。控制根索引干净且候选完全避开未提交的驾驶舱变更单和台账时，
   原样保留这些记录，合并前后核对摘要。其他无关未提交改动仍拒绝。
5. 适用的轻量自检与根目录检查通过。受保护改动、``--full-gate`` 或预检扩大为大范围选测时，
   核对驾驶舱持久任务里的全量门禁凭证。
都过了才 ``git merge --no-ff``，在 ``.auto-pm/reports/local_merge/merge_log.jsonl`` 记一笔；“备份”“多机”档
再把 main 推到 GitHub，推不上只记“待推送”，不算失败。

本机钩子（``install-hook`` 装在 ``.git/hooks/reference-transaction``）：凡是改 ``refs/heads/main`` 的，只放行
带 ``merge`` 一次性标记的，和新值正好是 ``origin/main`` 的（从 GitHub 同步）。它挡得住误操作，挡不住故意删钩子的人，
所以 ``verify-log`` 每次体检都核对：本命令上线后 main 上的每个提交，要么在合并记录里，要么是 GitHub 上的 PR 合并，
要么是另一台电脑经 GitHub 同步过来的本机合并；对不上的列出来，退出 1。

退出码：0＝做完或核对无误；1＝拒绝或核对有对不上的；2＝用法或环境不对。只用标准库和 git。本脚本不进发布载荷。
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = PROJECT_ROOT.parents[3]
STATE_DIR = Path(".auto-pm") / "reports" / "local_merge"
LOG_NAME = "merge_log.jsonl"
MODE_NAME = "github_mode.json"
TOKEN_NAME = "merge_token.json"
TOKEN_ENV = "PM_MERGE_TOKEN"
MAIN_REF = "refs/heads/main"
ORIGIN_REF = "refs/remotes/origin/main"
ZERO = "0" * 40
MODES = ("关", "备份", "多机")
DEFAULT_MODE = "备份"
MERGE_MARK = "合并方式: pm_merge.py merge"
RELEASE_ROOT = "00_Infrastructure/auto_pm"
RELEASE_POINTERS = frozenset(
    f"{RELEASE_ROOT}/{name}"
    for name in ("active_release.json", "previous_release.json", "deployment_manifest.json")
)
GITHUB_MERGE = re.compile(r"^Merge pull request #\d+ ")
CARD_LINE = re.compile(r"^领卡占位:\s*(\S+)\s*$", re.MULTILINE)
CHG_RE = re.compile(r"CHG-[A-Z]+-\d{4}-\d{3,}")
CHANGE_LINE = re.compile(rf"^变更单[:：][ \t]*({CHG_RE.pattern})[ \t]*$", re.MULTILINE)
CHANGE_SUBJECT = re.compile(rf"^(?:[^:：\[\]\r\n]+[:：][ \t]*)?\[({CHG_RE.pattern})\](?=\s|$)")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
STANDARD_CARD = re.compile(
    r"/(?:04|11)_监控/01_变更管理/03_实施卡/(CARD-([A-Z]+-\d{4}-\d{3})-(\d{3}))_[^/]+\.md$"
)
AUDIT_SCHEMA = "local-merge-audit.v1"
AUDIT_SESSION = re.compile(r"([a-z][a-z0-9]*)-([0-9a-f]{6})")
STATE_LINE = re.compile(r"\|\s*变更状态\s*\|\s*([a-z_]+)\s*\|")
CHANGE_FILES_ROW = re.compile(r"^\|\s*(?:\*\*)?涉及文件/交付物(?:\*\*)?\s*\|\s*([^|\n]*)\|", re.MULTILINE)
CARD_TIER = re.compile(r"^>\s*档次[：:]\s*[*`\s]*(文档|测试|产品|核心)", re.MULTILINE)
TIERS = {"文档": "docs", "测试": "tests", "产品": "product", "核心": "core"}
APPROVED_STATES = frozenset(
    {"approved", "conditionally_approved", "implementing", "pending_acceptance", "accepting"}
)
HOOK_NAME = "reference-transaction"
HOOK_MARK = "pm_merge.py install-hook"
GIT_TIMEOUT = 120
NET_TIMEOUT = 60
GATE_TIMEOUT = 4 * 60 * 60
STATUS_BATCH_CHARS = 8000
PRECHECK_JOBS = min(max((os.cpu_count() or 4) * 3 // 4, 4), 12)
SKIP_DIRS = frozenset({".git", ".auto-pm", "releases", "node_modules", ".venv", "__pycache__"})


def _rule_patterns() -> tuple[str, ...]:
    """规则文件清单，与 ``reviews/tools/rules_approval_check.py`` 的 ``RULE_PATTERNS`` 同一份（不在这里另抄一份）。"""
    tools = DEFAULT_ROOT / "reviews" / "tools"
    sys.path.insert(0, str(tools))
    try:
        from rules_approval_check import RULE_PATTERNS
    finally:
        sys.path.remove(str(tools))
    return tuple(RULE_PATTERNS)


# “要你点头”那一类：规则文件、PLC 项目文件、PLC 模板、本机合并命令与提交钩子自己（改它们就能把这道闸关掉）。
USER_PATTERNS: tuple[str, ...] = (
    *_rule_patterns(),
    "00_Infrastructure/auto_pm/releases/*",
    "0100_PLC自动化/*",
    "*/templates/plc-*",
    "*/scripts/pm_merge.py",
    "*/auto_pm/infrastructure/git_hook_enforcer.py",
    "*/auto_pm/infrastructure/change_status_guard.py",
    "*/auto_pm/domain/change/change_service.py",
    "*/auto_pm/domain/change/status_journal.py",
    "*/auto_pm/domain/change/guard_checker.py",
    "*/auto_pm/ui/cli/change.py",
)


class RefusedError(Exception):
    """拒绝合并：说明为什么，什么都没改。"""


@dataclass
class Git:
    cwd: Path
    env: dict[str, str] | None = None

    def run(
        self, *args: str, timeout: int = GIT_TIMEOUT, check: bool = False
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args],
            cwd=self.cwd,
            env=self.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        if check and result.returncode != 0:
            raise RefusedError(
                f"git {' '.join(args)} 失败（退出码 {result.returncode}）：{result.stderr.strip()}"
            )
        return result

    def out(self, *args: str) -> str:
        return self.run(*args, check=True).stdout.strip()

    def ok(self, *args: str) -> bool:
        return self.run(*args).returncode == 0

    def rev(self, ref: str) -> str:
        result = self.run("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
        return result.stdout.strip() if result.returncode == 0 else ""


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def state_dir(root: Path) -> Path:
    return root / STATE_DIR


def read_mode(root: Path) -> str:
    path = state_dir(root) / MODE_NAME
    try:
        mode = json.loads(path.read_text(encoding="utf-8", errors="replace")).get(
            "mode", DEFAULT_MODE
        )
    except (OSError, ValueError, AttributeError):
        return DEFAULT_MODE
    return mode if mode in MODES else DEFAULT_MODE


def write_mode(root: Path, mode: str) -> None:
    folder = state_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / MODE_NAME).write_text(
        json.dumps({"mode": mode, "set_at": _now()}, ensure_ascii=False),
        encoding="utf-8",
        errors="replace",
    )


def append_log(root: Path, entry: dict[str, Any]) -> None:
    folder = state_dir(root)
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / LOG_NAME).open("a", encoding="utf-8", errors="replace") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_log(root: Path) -> list[dict[str, Any]]:
    path = state_dir(root) / LOG_NAME
    if not path.exists():
        return []
    entries = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    return entries


def needs_user(path: str) -> bool:
    return any(fnmatch.fnmatchcase(path, pattern) for pattern in USER_PATTERNS)


def _same_ignoring_cr(a: bytes, b: bytes) -> bool:
    return a.replace(b"\r\n", b"\n") == b.replace(b"\r\n", b"\n")


def find_change_orders(root: Path, number: str, pid: str = "") -> list[Path]:
    """在控制根里找变更单原件 ``<号>.md``（只看 ``01_变更单`` 下面；跳过 .git、发布副本、工位）。"""
    found = []
    for folder, dirs, files in os.walk(root):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS]
        if f"{number}.md" in files and "01_变更单" in Path(folder).parts:
            path = Path(folder) / f"{number}.md"
            if not pid or pid in str(path):
                found.append(path)
    return found


def change_order_state(path: Path) -> str:
    match = STATE_LINE.search(path.read_text(encoding="utf-8", errors="replace"))
    return match.group(1) if match else ""


def _python(root: Path) -> str:
    for candidate in (root / ".venv" / "Scripts" / "python.exe", root / ".venv" / "bin" / "python"):
        if candidate.exists():
            return str(candidate)
    return sys.executable


@dataclass
class GateResult:
    ok: bool
    lines: list[str] = field(default_factory=list)


def _parse_precheck_json(stdout: str) -> dict[str, Any] | None:
    start = stdout.find("{")
    if start < 0:
        return None
    try:
        loaded = json.loads(stdout[start:])
    except ValueError:
        return None
    return loaded if isinstance(loaded, dict) else None


def managed_gate_receipt(root: Path, worktree: Path) -> str:
    command = [
        _python(root), "-B", str(root / "main.py"), "gate", "status",
        "--worktree", str(worktree),
    ]
    try:
        result = subprocess.run(
            command, cwd=root, capture_output=True, encoding="utf-8", errors="replace",
            timeout=120, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RefusedError(f"托管门禁凭证无法读取：{exc}") from exc
    record = _parse_precheck_json(result.stdout or "")
    if result.returncode or not record:
        raise RefusedError(
            "没有可核验的托管全量门禁凭证，请先用 gate start 登记候选。"
            + (result.stderr or "").strip()
        )
    if record.get("state") != "passed":
        raise RefusedError(f"托管门禁 {record.get('id')} 当前为 {record.get('state')}，请用 gate status 查状态")
    identity = record.get("candidate") or {}
    if (
        identity.get("commit") != Git(worktree).rev("HEAD")
        or identity.get("tree") != Git(worktree).out("rev-parse", "--verify", "HEAD^{tree}")
        or identity.get("base") != Git(root).rev("main")
        or not record.get("handle")
        or not record.get("detail")
    ):
        raise RefusedError("托管全量门禁凭证与候选或当前 main 不匹配")
    return f"托管全量门禁 PASS：{record['id']}（{record['backend']}，运行 {record['handle']}）"


def run_gates(root: Path, worktree: Path, full: bool) -> GateResult:
    """核对托管全量凭证，再跑轻量自检与适用的根目录检查。"""
    python = _python(root)
    wt_entry = (worktree / COCKPIT_PREFIX / "main.py") if COCKPIT_PREFIX else (worktree / "main.py")
    entry = str(wt_entry if wt_entry.is_file() else (root / "main.py"))
    precheck_cmd = [
        python,
        "-B",
        entry,
        "gate",
        "precheck",
        "--worktree",
        str(worktree),
        "--base",
        "main",
        "--jobs",
        str(PRECHECK_JOBS),
        "--json",
        "--defer-full",
    ]
    lines: list[str] = []
    if full:
        lines.append(managed_gate_receipt(root, worktree))
    try:
        result = subprocess.run(
            precheck_cmd,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=GATE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        lines.append(f"gate precheck：没跑完（{exc}）")
        return GateResult(False, lines)
    report = _parse_precheck_json(result.stdout or "")
    steps = (report.get("steps") or []) if report else []
    outside = (report.get("outside_changes") or []) if report else []
    deferred = bool(report and report.get("full_gate_required"))
    if deferred and not full:
        lines.append(managed_gate_receipt(root, worktree))
    steps_ok = (
        bool(steps)
        and all(isinstance(s, dict) and s.get("verdict") in ("PASS", "SKIPPED") for s in steps)
        and any(isinstance(s, dict) and s.get("verdict") == "PASS" for s in steps)
    )
    if result.returncode == 0:
        lines.append("gate precheck：退出码 0")
    elif steps_ok and (outside or deferred):
        lines.append("gate precheck：轻量步骤 PASS，继续核对适用检查")
    else:
        detail = ""
        for s in steps:
            if isinstance(s, dict) and s.get("verdict") not in ("PASS", "SKIPPED"):
                detail = f"（{s.get('name')} {s.get('verdict')}：{s.get('why') or s.get('exit')}）"
                break
        lines.append(f"gate precheck：退出码 {result.returncode}{detail}")
        return GateResult(False, lines)
    if (full or outside) and (worktree / "tests").is_dir():
        root_cmd = [
            python,
            "-B",
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-o",
            "addopts=",
            str(worktree / "tests"),
        ]
        try:
            root_res = subprocess.run(root_cmd, cwd=worktree, timeout=GATE_TIMEOUT, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            lines.append(f"root pytest：没跑完（{exc}）")
            return GateResult(False, lines)
        lines.append(f"root pytest：退出码 {root_res.returncode}")
        if root_res.returncode != 0:
            return GateResult(False, lines)
    return GateResult(True, lines)


@dataclass
class Plan:
    branch: str
    sha: str
    card: str
    chgs: list[str]
    paths: list[str]
    user_paths: list[str]
    replace: list[str]
    notes: list[str]
    archive_existing: bool = False
    base: str = ""
    audit: dict[str, Any] | None = None
    formal_change: str = ""
    preserved_governance: dict[str, str] = field(default_factory=dict)

    @property
    def requires_audit(self) -> bool:
        return bool(self.user_paths or self.formal_change)


def _commits(git: Git, base: str, tip: str) -> list[str]:
    raw = git.out("log", "--format=%B%x1e", f"{base}..{tip}")
    return [message.strip() for message in raw.split("\x1e") if message.strip()]


def _formal_change(branch_card: str, cards: list[str], messages: list[str]) -> str:
    """Recognize deliberate bindings while leaving prose references as ordinary text."""
    numbers = {value for value in [branch_card, *cards] if CHG_RE.fullmatch(value)}
    for message in messages:
        numbers.update(CHANGE_LINE.findall(message))
        subject = CHANGE_SUBJECT.match(message.partition("\n")[0])
        if subject:
            numbers.add(subject[1])
    if len(numbers) > 1:
        raise RefusedError("分支正式绑定了多张变更单：" + "、".join(sorted(numbers)))
    return next(iter(numbers), "")


# 记录类文件：驾驶舱目录里的也不能随手删（变更单原件、台账、批准记录、WBS），删它们算“要你点头”。
RECORD_PATTERNS = ("*CHG-*", "*台账*", "*DEC-*", "*WBS*")
COCKPIT_PREFIX = (
    PROJECT_ROOT.relative_to(DEFAULT_ROOT).as_posix() + "/"
    if PROJECT_ROOT.is_relative_to(DEFAULT_ROOT)
    else ""
)
GOVERNANCE_DIR = f"{COCKPIT_PREFIX}04_监控/01_变更管理/"
GOVERNANCE_LEDGER = f"{GOVERNANCE_DIR}02_变更记录/01_版本变更台账.md"
GOVERNANCE_CHANGE = re.compile(
    rf"{re.escape(GOVERNANCE_DIR)}01_变更单/(?:CHG-[A-Z]+/)?{CHG_RE.pattern}\.md"
)


def removed_outside_cockpit(git: Git, base: str, tip: str) -> list[str]:
    """删除或改名掉的已入库文件里，不在驾驶舱项目目录（SW-2026-008）下的，以及驾驶舱里的记录类文件：这些算“要你点头”。"""
    raw = git.run(
        "diff", "--name-status", "-z", "--no-renames", "--diff-filter=D", base, tip, check=True
    ).stdout
    parts = [part for part in raw.split("\0") if part]
    deleted = [parts[index + 1] for index in range(0, len(parts) - 1, 2) if parts[index] == "D"]
    return sorted(
        path
        for path in deleted
        if not (COCKPIT_PREFIX and path.startswith(COCKPIT_PREFIX))
        or any(fnmatch.fnmatchcase(path, pattern) for pattern in RECORD_PATTERNS)
    )


def card_files(git: Git, tip: str, card: str, pid: str) -> tuple[list[str], list[str]]:
    """按完整卡号查找；变更单号或传统短号以同项目的序号对应。"""
    raw = git.run("ls-tree", "-r", "-z", "--name-only", tip, check=True).stdout
    legacy_name = re.compile(rf"/02_规划/{re.escape(card)}_[^/]*\.md$")
    serial = card.rsplit("-", 1)[-1] if CHG_RE.fullmatch(card) or card.isdecimal() else ""
    standard, legacy = [], []
    for path in raw.split("\0"):
        match = STANDARD_CARD.search(path)
        if match and (not pid or match[2] == pid):
            if card == match[1] or serial == match[3]:
                standard.append(path)
        elif legacy_name.search(path):
            legacy.append(path)
    return standard, legacy


def _legacy_card_scope(text: str) -> list[str]:
    """旧卡的范围来自有基线状态的路径表，运行态条目不授权写入。"""
    allowed: list[str] = []
    columns: tuple[int, int] | None = None
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            columns = None
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if "路径" in cells and "基线状态" in cells:
            columns = (cells.index("路径"), cells.index("基线状态"))
        elif columns and len(cells) > max(columns):
            item, state = cells[columns[0]], cells[columns[1]]
            match = re.fullmatch(r"`([^\x00`]+)`", item)
            if match and re.match(r"^(存在|计划新增)(?:$|[（(])", state):
                path = match[1].rstrip("/")
                if path and not any(part in {"", ".", ".."} for part in path.split("/")):
                    allowed.append(path)
    return allowed


def _card_precheck(
    git: Git, worktree: Path, base: str, sha: str, path: str, pid: str, change: str,
) -> list[str]:
    """按与本合并脚本同一份源码的驾驶舱预检核对候选实施卡。"""
    file = worktree / path
    try:
        if file.resolve() != file.absolute():
            raise RefusedError(f"工位实施卡不能是转向其他路径的链接：{path}")
        raw = file.read_bytes()
        blob = bytes(git.run("show", f"{sha}:{path}", check=True).stdout, "utf-8")
        if not _same_ignoring_cr(raw, blob):
            raise RefusedError(f"工位实施卡和提交里的版本不同：{path}")
        result = subprocess.run(
            [_python(git.cwd), "-X", "utf8", "-B", str(PROJECT_ROOT / "main.py"),
             "--control-root", str(git.cwd), "implementation-card",
             "precheck", "--card-file", str(file), "--pid", pid],
            cwd=git.cwd, capture_output=True, encoding="utf-8", errors="replace",
            timeout=120, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RefusedError(f"实施卡预检无法运行：{exc}") from exc
    report = _parse_precheck_json(result.stdout)
    if (
        report is None
        or report.get("schema_version") != "implementation-card-precheck.v1"
        or report.get("card_format") != "new"
        or report.get("card_sha256") != hashlib.sha256(raw).hexdigest()
        or not isinstance(report.get("findings"), list)
        or not isinstance(report.get("paths"), list)
        or report.get("change") != change
    ):
        raise RefusedError(f"读不到与候选匹配的实施卡预检结果：{path} {result.stderr.strip()}")
    findings = report["findings"]
    if result.returncode or report.get("passed") is not True or findings:
        raise RefusedError(f"实施卡预检未通过：{json.dumps(findings, ensure_ascii=False)}")
    baseline = report.get("baseline")
    if (
        not isinstance(baseline, str)
        or re.fullmatch(r"[0-9a-f]{40}", baseline) is None
        or not git.ok("merge-base", "--is-ancestor", baseline, base)
    ):
        raise RefusedError("实施卡的隔离基线必须是当前 main 的历史提交")
    entries = report["paths"]
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("path"), str)
        or item.get("state") not in ("存在", "计划新增", "运行态")
        for item in entries
    ):
        raise RefusedError("实施卡预检没有返回有效的路径表")
    return [item["path"] for item in entries if item["state"] != "运行态"]


def _check_card_tier(root: Path, text: str, base: str, sha: str) -> None:
    """用驾驶舱现有分类器核对真实差异，包含卡片声明目录下的实际子文件。"""
    declared = CARD_TIER.search(text)
    if not declared:
        raise RefusedError("实施卡没有可核对的档次")
    classifier = root / COCKPIT_PREFIX / "tests" / "tools" / "tier_classifier.py"
    try:
        result = subprocess.run(
            [_python(root), "-X", "utf8", "-B", str(classifier), "--diff", base, sha,
             "--declared", TIERS[declared[1]]],
            cwd=root, capture_output=True, encoding="utf-8", errors="replace",
            timeout=120, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RefusedError(f"实施卡档次无法核验：{exc}") from exc
    if result.returncode:
        report = _parse_precheck_json(result.stdout) or {}
        problems = "、".join(report.get("problems") or []) or report.get("error") or result.stderr.strip()
        raise RefusedError(f"实施卡档次核验未过：{problems}")


def _check_card(
    git: Git, worktree: Path, base: str, sha: str, card: str, chgs: list[str],
    paths: list[str], pid: str, *, archive_existing: bool,
) -> None:
    standard, legacy = card_files(git, sha, card, pid)
    choices = standard or legacy
    if len(choices) != 1:
        problem = "没有本卡的实施卡" if not choices else "找到多张同号实施卡，请带 --pid 核对"
        raise RefusedError(problem)
    path = choices[0]
    text = git.run("show", f"{sha}:{path}", check=True).stdout
    if standard:
        match = STANDARD_CARD.search(path)
        assert match is not None
        pid = match[2]
        changes = re.findall(r"^>\s*变更单：`?(CHG-[A-Z]+-\d{4}-\d{3,})`?\s*$", text, re.MULTILINE)
    else:
        if not archive_existing and not git.ok("cat-file", "-e", f"{base}:{path}"):
            raise RefusedError("新增实施卡要放在项目的 04_监控或 11_监控实施卡目录")
        changes = CHG_RE.findall(text)
    approved: list[tuple[str, Path]] = []
    for number in chgs:
        if number not in changes:
            continue
        orders = find_change_orders(git.cwd, number, pid)
        if len(orders) > 1:
            raise RefusedError(f"找到 {len(orders)} 份 {number}，带 --pid 指明是哪个项目的")
        if orders and change_order_state(orders[0]) in APPROVED_STATES:
            approved.append((number, orders[0]))
    if len(approved) != 1:
        raise RefusedError("需有且仅有一张用户批准并写在本卡实施卡里的变更单；已完成的单不能开新活")
    change, order = approved[0]
    if standard:
        allowed = _card_precheck(git, worktree, base, sha, path, pid, change)
        row = CHANGE_FILES_ROW.search(order.read_text(encoding="utf-8", errors="replace"))
        approved_paths = [item.strip().rstrip("/") for item in row[1].split("<br>")] if row else []
        outside_approval = _outside_scope(paths, approved_paths)
        if outside_approval:
            raise RefusedError(f"超出变更单 {change} 批准范围：" + "、".join(outside_approval[:10]))
    else:
        allowed = _legacy_card_scope(text)
    outside = _outside_scope(paths, allowed)
    if outside:
        raise RefusedError("超出实施卡可改范围：" + "、".join(outside[:10]))
    if standard:
        _check_card_tier(git.cwd, text, base, sha)


def _outside_scope(paths: list[str], allowed: list[str]) -> list[str]:
    return [
        path for path in paths
        if not any(path == scope or path.startswith(f"{scope}/") for scope in allowed)
    ]


def _changed_paths(git: Git, base: str, tip: str) -> list[str]:
    raw = git.run("diff", "--name-only", "-z", "--no-renames", base, tip, check=True).stdout
    return sorted({path for path in raw.split("\0") if path})


def _chunk_paths(paths: Sequence[str], max_chars: int | None = None) -> list[list[str]]:
    """按字符总长分批路径，避免 Windows CreateProcess 命令行超 32767 字符上限报 WinError 206。"""
    limit = STATUS_BATCH_CHARS if max_chars is None else max_chars
    batches: list[list[str]] = []
    current: list[str] = []
    total = 0
    for path in paths:
        cost = len(path) + 3
        if current and total + cost > limit:
            batches.append(current)
            current = []
            total = 0
        current.append(path)
        total += cost
    if current:
        batches.append(current)
    return batches


@dataclass
class ControlRootCopies:
    replace: list[str]
    preserved: dict[str, str]


def _is_governance_record(path: str) -> bool:
    return path == GOVERNANCE_LEDGER or GOVERNANCE_CHANGE.fullmatch(path) is not None


def _governance_digest(root: Path, path: str) -> str:
    local = root / path
    try:
        if local.resolve() != local.absolute() or not local.is_file():
            raise RefusedError(f"只能保全控制根中的普通变更记录文件：{path}")
        return hashlib.sha256(local.read_bytes()).hexdigest()
    except (OSError, RuntimeError) as exc:
        raise RefusedError(f"无法核对控制根变更记录：{path}") from exc


def _control_root_copies(
    root_git: Git, root: Path, sha: str, paths: list[str], *, archive_existing: bool = False
) -> ControlRootCopies:
    """Identify matching copies and snapshot any governance records left on disk."""
    tracked = root_git.run(
        "status", "--porcelain=v1", "-z", "--no-renames", "--untracked-files=no", check=True
    ).stdout
    dirty = {entry[3:]: entry[:2] for entry in tracked.split("\0") if len(entry) > 3}
    unresolved = sorted(set(dirty) - set(paths))
    preserved: dict[str, str] = {}
    if unresolved and not archive_existing:
        other = [path for path in unresolved if dirty[path] != " M" or not _is_governance_record(path)]
        if other:
            raise RefusedError("控制根有未提交的改动，先处理再合并：" + "、".join(other[:10]))
        if not root_git.ok("diff", "--cached", "--quiet"):
            raise RefusedError("控制根有已暂存内容，不能保全台账后合并")
        pending = root_git.run(
            "status", "--porcelain=v1", "-z", "--no-renames", "--untracked-files=all", "--",
            GOVERNANCE_DIR, check=True,
        ).stdout
        records = {entry[3:] for entry in pending.split("\0") if len(entry) > 3 and _is_governance_record(entry[3:])}
        overlap = sorted(
            record for record in records
            if any(record == path or record.startswith(f"{path}/") or path.startswith(f"{record}/") for path in paths)
        )
        if overlap:
            raise RefusedError("候选与控制根未提交的变更记录重叠：" + "、".join(overlap[:10]))
        preserved = {path: _governance_digest(root, path) for path in sorted(records | set(unresolved))}
    replace = []
    candidates = set(dirty) - set(unresolved)
    for batch in _chunk_paths(paths):
        untracked = root_git.run(
            "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", *batch, check=True
        ).stdout
        candidates |= {entry[3:] for entry in untracked.split("\0") if entry.startswith("?? ")}
    for path in sorted(candidates):
        local = root / path
        if not local.is_file():
            raise RefusedError(f"控制根里 {path} 有未提交的改动（不是普通文件），先处理再合并")
        blob = subprocess.run(
            ["git", "cat-file", "-p", f"{sha}:{path}"],
            cwd=root,
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT,
        )
        if blob.returncode != 0:
            raise RefusedError(f"控制根里 {path} 有未提交的改动，分支里却删了它，先处理再合并")
        branch_bytes = blob.stdout
        working_bytes = local.read_bytes()
        matches = (
            working_bytes == branch_bytes
            if archive_existing and path.startswith(f"{RELEASE_ROOT}/releases/")
            else _same_ignoring_cr(working_bytes, branch_bytes)
        )
        if not matches and not (
            archive_existing
            and _archive_ledger_preserves_rows(root_git, path, paths, working_bytes, branch_bytes)
        ):
            raise RefusedError(
                f"控制根里 {path} 的未提交内容和分支里的不一样（不只差行尾），先把控制根的版本放进分支再合并"
            )
        replace.append(path)
    return ControlRootCopies(replace, preserved)


def _archive_ledger_preserves_rows(
    git: Git, path: str, paths: list[str], working: bytes, candidate: bytes
) -> bool:
    """只允许归档台账新增已入库原件对应的行，其余本地条目全部留在工作区。"""
    if not path.endswith("/02_变更记录/01_版本变更台账.md"):
        return False
    base_blob = subprocess.run(
        ["git", "cat-file", "blob", f"main:{path}"],
        cwd=git.cwd,
        capture_output=True,
        timeout=GIT_TIMEOUT,
        check=True,
    ).stdout
    try:
        base = base_blob.decode("utf-8").splitlines()
        incoming = candidate.decode("utf-8").splitlines()
        local_rows = working.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return False
    rows = [line for line in incoming if line and line not in base]
    if not rows or [line for line in incoming if line not in rows and line] != [
        line for line in base if line
    ]:
        return False
    change_names = {
        Path(file).stem for file in paths if "/01_变更单/" in file and file.endswith(".md")
    }
    return all(
        local_rows.count(row) == 1
        and row.startswith("| ")
        and any(f"{name}]" in row and f"/{name}.md)" in row for name in change_names)
        for row in rows
    )


def _check_release_archive(
    root: Path, git: Git, base: str, sha: str, paths: list[str], copies: list[str]
) -> None:
    """确认这是现役发布入库，且三个发布文件和整个载荷都已有相同的本机副本。"""
    if not RELEASE_POINTERS.issubset(copies):
        raise RefusedError("发布归档需要三个本机现役发布文件的完整、相符副本")
    if git.run("diff", "--no-renames", "--diff-filter=D", "--name-only", base, sha, check=True).stdout:
        raise RefusedError("发布归档不能删除或改名已有文件")
    try:
        pointer = json.loads((root / RELEASE_ROOT / "active_release.json").read_text(encoding="utf-8"))
        name = pointer["release_id"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RefusedError(f"读不出现役发布：{exc}") from exc
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise RefusedError("现役发布号格式不合法")
    prefix = f"{RELEASE_ROOT}/releases/{name}/"
    published = root / prefix
    expected = {
        item.relative_to(root).as_posix() for item in published.rglob("*") if item.is_file()
    }
    archived = {path for path in paths if path.startswith(f"{RELEASE_ROOT}/releases/")}
    if not expected or archived != expected or not archived.issubset(copies):
        raise RefusedError("归档必须覆盖且只覆盖现役发布完整载荷")
    if git.run("ls-tree", "-r", "--name-only", base, "--", prefix, check=True).stdout.strip():
        raise RefusedError("现役发布已经入库，不能再次按新载荷归档")


def plan_merge(root: Path, name: str, pid: str = "", *, archive_existing: bool = False) -> Plan:
    if not NAME_RE.match(name):
        raise RefusedError(f"工位名写法不对：{name}")
    root_git = Git(root)
    head = root_git.run("symbolic-ref", "--quiet", "HEAD").stdout.strip()
    if head != MAIN_REF:
        raise RefusedError(f"控制根没停在 main（现在是 {head or '分离的 HEAD'}），不合并")
    base = root_git.rev(MAIN_REF)
    if archive_existing and not root_git.ok("diff", "--cached", "--quiet"):
        raise RefusedError("控制根有已暂存内容，保留现场，不能归档")
    worktree = root / ".auto-pm" / "worktrees" / name
    if not (worktree / ".git").exists():
        raise RefusedError(f"找不到工位 {worktree}")
    wt_git = Git(worktree)
    branch = wt_git.run("symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip()
    if not branch or branch == "main":
        raise RefusedError("工位不在自己的分支上，不合并")
    if wt_git.run("status", "--porcelain", "--untracked-files=no", check=True).stdout.strip():
        raise RefusedError(f"工位 {name} 还有没提交的改动，先提交")
    sha = wt_git.rev("HEAD")
    if not root_git.ok("merge-base", "--is-ancestor", "main", sha):
        raise RefusedError(
            f"分支 {branch} 里还没有最新的 main，先在工位里合并 main（git merge main）再来"
        )
    messages = _commits(root_git, base, sha)
    if not messages:
        raise RefusedError(f"分支 {branch} 比 main 没有新提交，没什么可合的")
    cards = [match.group(1) for message in messages for match in CARD_LINE.finditer(message)]
    if not cards:
        raise RefusedError("分支上没有一个提交带“领卡占位: <卡号>”这一行")
    branch_card = branch.rsplit("/", 1)[-1]
    formal_change = _formal_change(branch_card, cards, messages)
    card = formal_change if formal_change in cards else cards[0]
    paths = _changed_paths(root_git, base, sha)
    user_paths = [path for path in paths if needs_user(path)]
    user_paths += [
        path for path in removed_outside_cockpit(root_git, base, sha) if path not in user_paths
    ]
    chgs: list[str] = []
    if user_paths or formal_change:
        allowed_cards = {card, branch_card} if formal_change == card else {card}
        if set(cards) - allowed_cards:
            raise RefusedError("只能使用本卡的领卡占位号；历史短名应与本分支名一致")
        chgs = [formal_change] if formal_change else sorted({
            number for message in messages for number in CHG_RE.findall(message)
        })
        try:
            _check_card(root_git, worktree, base, sha, card, chgs, paths, pid,
                        archive_existing=archive_existing)
        except RefusedError as exc:
            scope = "、".join(user_paths[:5]) or formal_change
            raise RefusedError(f"需核对实施卡的变更（{scope}）：{exc}") from exc
    notes: list[str] = []
    copies = _control_root_copies(root_git, root, sha, paths, archive_existing=archive_existing)
    if archive_existing:
        _check_release_archive(root, root_git, base, sha, paths, copies.replace)
    elif RELEASE_POINTERS.intersection(copies.replace):
        raise RefusedError("控制根有现役发布指针，归档请使用 --archive-existing")
    return Plan(
        branch, sha, card, chgs, paths, user_paths, copies.replace, notes,
        archive_existing=archive_existing, base=base, formal_change=formal_change,
        preserved_governance=copies.preserved,
    )


def check_github(root: Path, mode: str, notes: list[str]) -> None:
    """GitHub 开着且连得上时，另一台电脑推上去的 main 必须已在本机 main 里。"""
    if mode == "关":
        notes.append("GitHub 关着，没查另一台电脑的改动")
        return
    git = Git(root)
    fetch = git.run("fetch", "--quiet", "origin", "main", timeout=NET_TIMEOUT)
    if fetch.returncode != 0:
        if mode == "多机":
            raise RefusedError("多机档无法核对远端 main，请在恢复连接后重试")
        notes.append("连不上 GitHub，跳过“另一台电脑有没有新改动”这一条")
        return
    if not git.ok("merge-base", "--is-ancestor", "origin/main", "main"):
        raise RefusedError(
            "GitHub 上的 main 有本机没有的提交（多半是另一台电脑推的），先跑 sync 同步再合并"
        )


def _restore_failed_archive(git: Git, plan: Plan, base: str, started_merge: bool) -> None:
    staged = set(filter(None, git.run("diff", "--cached", "--name-only", "-z", check=True).stdout.split("\0")))
    if staged - set(plan.paths) or any(
        not git.ok("--literal-pathspecs", "diff", "--cached", "--quiet", plan.sha, "--", *batch)
        for batch in _chunk_paths(sorted(staged))
    ):
        raise RefusedError("索引有归档候选以外的改动，已保留现场，不能自动恢复")
    ordinary = sorted(set(plan.paths) - set(plan.replace))
    ordinary_changes = {
        entry[3:]
        for batch in _chunk_paths(ordinary)
        for entry in git.run(
            "--literal-pathspecs", "status", "--porcelain=v1", "-z", "--untracked-files=all",
            "--", *batch, check=True,
        ).stdout.split("\0")
        if len(entry) > 3
    } if started_merge else set()
    # read-tree 不加 -u，只恢复索引，从不写入现役文件。包含从未登记的新文件也可以完整回退。
    git.run("read-tree", base, check=True)
    if not started_merge:
        return
    overwritten = []
    for path in sorted(ordinary_changes):
        # 只有内容与失败的合并结果一致，才恢复这次 Git 写过的普通文件。
        current = git.cwd / path
        previous = subprocess.run(
            ["git", "cat-file", "--filters", f"{base}:{path}"],
            cwd=git.cwd, capture_output=True, timeout=GIT_TIMEOUT, check=False,
        )
        actual = current.read_bytes() if current.is_file() else None
        if (not previous.returncode and actual == previous.stdout) or (
            previous.returncode and actual is None
        ):
            continue
        expected = subprocess.run(
            ["git", "cat-file", "--filters", f"{plan.sha}:{path}"],
            cwd=git.cwd, capture_output=True, timeout=GIT_TIMEOUT, check=False,
        )
        if expected.returncode or actual != expected.stdout:
            overwritten.append(path)
            continue
        git.run("--literal-pathspecs", "restore", "--staged", f"--source={plan.sha}", "--", path, check=True)
        git.run("--literal-pathspecs", "restore", "--staged", "--worktree", f"--source={base}", "--", path, check=True)
    if overwritten:
        raise RefusedError("有普通文件在合并时发生其他变动，已保留：" + "、".join(overwritten))


def _archive_merge(git: Git, plan: Plan, base: str, title: str, body: str) -> None:
    """为现役副本只登记索引；用正常 fast-forward 安装其余文件并提交引用事务。"""
    if not git.ok("diff", "--cached", "--quiet"):
        raise RefusedError("控制根有已暂存内容，保留现场，不能归档")
    if not git.ok("merge-base", "--is-ancestor", base, plan.sha):
        raise RefusedError("main 已变化，归档候选无效")
    merge_sha = git.out("commit-tree", f"{plan.sha}^{{tree}}", "-p", base, "-p", plan.sha, "-m", title, "-m", body)
    started_merge = False
    try:
        for batch in _chunk_paths(plan.replace):
            git.run("--literal-pathspecs", "restore", "--staged", f"--source={plan.sha}", "--", *batch, check=True)
        if git.rev("main") != base:
            raise RefusedError("登记期间 main 已变动，保留现场")
        started_merge = True
        git.run("merge", "--ff-only", "--no-overwrite-ignore", "--no-verify", merge_sha, check=True)
    except (RefusedError, OSError, subprocess.SubprocessError, KeyboardInterrupt) as exc:
        head = git.rev("main")
        if head == merge_sha:
            return
        if head != base:
            raise RefusedError(f"归档期间 main 发生变化，保留现场：{exc}") from exc
        _restore_failed_archive(git, plan, base, started_merge)
        reason = "操作中断" if isinstance(exc, KeyboardInterrupt) else str(exc)
        raise RefusedError(f"发布归档合并失败，现役副本保留：{reason}") from exc


def _merge_existing_copies(root: Path, plan: Plan, merge_git: Git, title: str, body: str) -> None:
    """常规路径保留既有备份及合并行为。发布归档永远单独走索引登记。"""
    root_git = Git(root)
    backup = state_dir(root) / f"replaced_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    for path in plan.replace:
        target = backup / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / path, target)
    tracked = set(_tracked_dirty(root_git))
    for path in plan.replace:
        if path in tracked:
            root_git.run("checkout", "--", path, check=True)
        else:
            (root / path).unlink()
    result = merge_git.run("merge", "--no-ff", "--no-verify", "-m", title, "-m", body, plan.sha)
    if result.returncode != 0:
        root_git.run("merge", "--abort")
        for path in plan.replace:
            shutil.copy2(backup / path, root / path)
        raise RefusedError(
            f"git merge 失败，已退回，控制根原样：{(result.stdout + result.stderr).strip()[:400]}"
        )


@contextmanager
def _main_transaction(root: Path, base: str, sha: str) -> Iterator[Git]:
    """合并与同步串行；引用钩子同时核对令牌和变更前的 main。"""
    token = secrets.token_hex(16)
    token_file = state_dir(root) / TOKEN_NAME
    token_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = token_file.open("x", encoding="utf-8", errors="replace")
    except FileExistsError as exc:
        raise RefusedError("已有 main 更新令牌（可能正在合并或同步），保留现场") from exc
    try:
        with handle:
            json.dump({"token": token, "base": base, "sha": sha}, handle)
        yield Git(root, env={**os.environ, TOKEN_ENV: token})
    finally:
        token_file.unlink(missing_ok=True)


def do_merge(root: Path, plan: Plan, gates: GateResult, mode: str) -> dict[str, Any]:
    root_git = Git(root)
    body = [f"领卡占位: {plan.card}"]
    if plan.chgs:
        body.append("变更单: " + "、".join(plan.chgs))
    body.append(MERGE_MARK + "（本机门禁通过）")
    title = f"Merge branch '{plan.branch}'（本机合并）"
    base = plan.base
    with _main_transaction(root, base, plan.sha) as merge_git:
        if root_git.rev(MAIN_REF) != base or root_git.rev(plan.branch) != plan.sha:
            raise RefusedError("合并前 main 或候选已变动，请重新取得对应证据")
        copies = _control_root_copies(
            root_git, root, plan.sha, plan.paths, archive_existing=plan.archive_existing,
        )
        if copies.replace != plan.replace or copies.preserved != plan.preserved_governance:
            raise RefusedError("控制根副本范围在检查后变化，请重新核对")
        if plan.archive_existing:
            _check_release_archive(root, root_git, base, plan.sha, plan.paths, copies.replace)
            _archive_merge(merge_git, plan, base, title, "\n".join(body))
        else:
            _merge_existing_copies(root, plan, merge_git, title, "\n".join(body))
        merge_sha = root_git.rev("HEAD")
        governance_drift = []
        for path, before in plan.preserved_governance.items():
            try:
                same = _governance_digest(root, path) == before
            except RefusedError:
                same = False
            if not same:
                governance_drift.append(path)
    entry: dict[str, Any] = {
        "time": _now(),
        "branch": plan.branch,
        "branch_sha": plan.sha,
        "merge_sha": merge_sha,
        "card": plan.card,
        "chgs": plan.chgs,
        "user_paths": plan.user_paths,
        "gates": gates.lines,
        "replaced": [] if plan.archive_existing else plan.replace,
        "mode": mode,
        "pushed": False,
    }
    if plan.archive_existing:
        entry["adopted"] = plan.replace
    if plan.audit is not None:
        entry["audit"] = plan.audit
    if plan.preserved_governance:
        entry["preserved_governance"] = plan.preserved_governance
        entry["governance_drift"] = governance_drift
    if mode != "关":
        push = root_git.run("push", "--quiet", "origin", f"{merge_sha}:{MAIN_REF}", timeout=NET_TIMEOUT * 2)
        entry["pushed"] = push.returncode == 0
        if push.returncode != 0:
            entry["push_error"] = push.stderr.strip()[:300]
    append_log(root, entry)
    return entry


def _tracked_dirty(git: Git) -> list[str]:
    raw = git.run("status", "--porcelain=v1", "-z", "--untracked-files=no", check=True).stdout
    return [entry[3:] for entry in raw.split("\0") if len(entry) > 3]


def _audit_identity(root: Path, name: str, base: str, sha: str) -> dict[str, str]:
    return {
        "schema": AUDIT_SCHEMA,
        "worktree": name,
        "base": base,
        "candidate": sha,
        "tree": Git(root).out("rev-parse", "--verify", f"{sha}^{{tree}}"),
    }


def _reviewer_is_independent(reviewer: str, owner: str, branch: str) -> bool:
    review = AUDIT_SESSION.fullmatch(reviewer)
    author = AUDIT_SESSION.fullmatch(owner)
    if review is None:
        return False
    if author is not None:
        return review[2] != author[2]
    return review[1] != branch.partition("/")[0]


def _audit_path(root: Path, base: str, sha: str) -> Path:
    return state_dir(root) / "audits" / f"{base}-{sha}.json"


def audit_receipt(root: Path, name: str, plan: Plan) -> dict[str, Any]:
    identity = _audit_identity(root, name, plan.base, plan.sha)
    path = _audit_path(root, plan.base, plan.sha)
    try:
        receipt = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError) as exc:
        raise RefusedError("缺少对应当前 main 和候选提交的独立审计凭证，请由审计会话运行 audit-record") from exc
    if not isinstance(receipt, dict) or any(receipt.get(key) != value for key, value in identity.items()):
        raise RefusedError("独立审计凭证与当前 main、候选或工位不匹配")
    reviewer = receipt.get("reviewer")
    report = receipt.get("report")
    if not isinstance(reviewer, str) or not _reviewer_is_independent(reviewer, name, plan.branch):
        raise RefusedError("独立审计必须来自另一会话")
    if (
        receipt.get("verdict") != "PASS"
        or not isinstance(report, str)
        or plan.base not in report
        or plan.sha not in report
        or receipt.get("report_sha256") != hashlib.sha256(report.encode("utf-8")).hexdigest()
    ):
        raise RefusedError("独立审计未放行，或报告缺失、摘要不符")
    return {key: value for key, value in receipt.items() if key != "report"}


def cmd_audit_record(
    root: Path, name: str, base: str, sha: str, verdict: str, report_file: Path,
) -> int:
    try:
        worktree = root / ".auto-pm" / "worktrees" / name
        if not NAME_RE.fullmatch(name) or not (worktree / ".git").exists():
            raise RefusedError("找不到要审计的工位")
        git = Git(root)
        wt = Git(worktree)
        branch = wt.run("symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip()
        if not base or not sha or base != git.rev(MAIN_REF) or sha != wt.rev("HEAD") or not branch:
            raise RefusedError("审计期间 main 或候选已变化，请核对新版本")
        agent = os.getenv("AUTO_PM_AGENT", "").split(":", 1)[0].strip().lower()
        session = (os.getenv("AUTO_PM_SESSION_ID") or os.getenv("CLAUDE_CODE_SESSION_ID") or "").strip()
        compact = session.lower().replace("-", "")
        tag = (
            compact[:6] if re.fullmatch(r"[0-9a-f]{6,}", compact)
            else hashlib.sha256(session.encode("utf-8")).hexdigest()[:6]
        )
        reviewer = f"{agent}-{tag}"
        if not session or not _reviewer_is_independent(reviewer, name, branch):
            raise RefusedError("请由另一审计会话登记，携带 AUTO_PM_AGENT 和实际会话 ID")
        report = report_file.read_text(encoding="utf-8", errors="replace")
        if base not in report or sha not in report:
            raise RefusedError("审计报告须写明核对过的 main 和候选完整提交号")
        receipt = {
            **_audit_identity(root, name, base, sha),
            "reviewer": reviewer,
            "verdict": verdict,
            "time": _now(),
            "report_sha256": hashlib.sha256(report.encode("utf-8")).hexdigest(),
            "report": report,
        }
        path = _audit_path(root, base, sha)
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
            pending = Path(temporary.name)
        try:
            pending.write_text(json.dumps(receipt, ensure_ascii=False), encoding="utf-8", errors="replace")
            pending.replace(path)
        finally:
            pending.unlink(missing_ok=True)
    except (OSError, RefusedError) as exc:
        print(f"拒绝登记审计：{exc}")
        return 1
    print(f"已登记独立审计 {verdict}：{reviewer}，{sha[:8]} 对 {base[:8]}，凭证 {path}")
    return 0


def cmd_merge(root: Path, name: str, pid: str, full_gate: bool, *, archive_existing: bool = False) -> int:
    mode = read_mode(root)
    try:
        plan = plan_merge(root, name, pid, archive_existing=archive_existing)
        if plan.requires_audit:
            plan.audit = audit_receipt(root, name, plan)
        check_github(root, mode, plan.notes)
        gates = run_gates(
            root, root / ".auto-pm" / "worktrees" / name, full_gate or bool(plan.user_paths)
        )
        if not gates.ok:
            raise RefusedError("本机门禁没过：" + "；".join(gates.lines))
        if Git(root).rev("main") != plan.base or Git(root).rev(plan.branch) != plan.sha:
            raise RefusedError("检查期间 main 或候选已变更，请核对最新候选再合并")
        if plan.audit is not None and audit_receipt(root, name, plan) != plan.audit:
            raise RefusedError("检查期间独立审计凭证已变化，请核对后重新合并")
        entry = do_merge(root, plan, gates, mode)
    except RefusedError as exc:
        print(f"拒绝合并：{exc}")
        return 1
    for note in plan.notes:
        print(f"说明：{note}")
    print(
        f"已合并 {plan.branch}（{plan.sha[:8]}）进 main：合并提交 {entry['merge_sha'][:8]}，卡 {plan.card}"
    )
    if plan.requires_audit:
        print(
            "已核对变更单和独立审计："
            + "、".join(plan.chgs)
            + "；推到完成仍只有用户本人做"
        )
    if plan.archive_existing:
        print(f"已登记 {len(plan.replace)} 份本机副本，现役发布文件保留原样")
    elif plan.replace:
        print(
            "控制根里这些只差行尾的副本已换成分支版本（原件备份在 .auto-pm/reports/local_merge/）："
            + "、".join(plan.replace)
        )
    if entry.get("governance_drift"):
        print("合并后发现本机变更记录有并发更新，请核对：" + "、".join(entry["governance_drift"]))
    elif plan.preserved_governance:
        print(f"已核对 {len(plan.preserved_governance)} 份本机变更记录原样保留")
    if mode == "关":
        print("GitHub 关着，没有推送")
    elif entry["pushed"]:
        print("已推到 GitHub 备份")
    else:
        print("推到 GitHub 没成功，记成待推送，不影响使用；下次合并或跑 push 时再推")
    print(f"退回办法：git revert -m 1 {entry['merge_sha'][:12]}")
    return 0


def cmd_sync(root: Path) -> int:
    if read_mode(root) == "关":
        print("GitHub 关着（github-mode 关），不同步")
        return 1
    git = Git(root)
    if git.run("fetch", "--quiet", "origin", "main", timeout=NET_TIMEOUT).returncode != 0:
        print("连不上 GitHub，这次没同步，本机照常能用")
        return 1
    base, remote = git.rev(MAIN_REF), git.rev(ORIGIN_REF)
    if base == remote:
        print("本机 main 已和 GitHub 一样")
        return 0
    if git.ok("merge-base", "--is-ancestor", base, remote):
        try:
            with _main_transaction(root, base, remote) as sync_git:
                if git.rev(MAIN_REF) != base or git.rev(ORIGIN_REF) != remote:
                    raise RefusedError("同步前 main 或 origin/main 已变化，请重新核对")
                result = sync_git.run("merge", "--ff-only", remote)
        except RefusedError as exc:
            print(f"拒绝同步：{exc}")
            return 1
        if result.returncode != 0:
            print(f"快进没成功：{result.stderr.strip()[:300]}")
            return 1
        print(f"已从 GitHub 同步到 {remote[:8]}")
        return 0
    if git.ok("merge-base", "--is-ancestor", "origin/main", "main"):
        print("本机 main 比 GitHub 新：跑 push 推上去（“备份”“多机”档合并时也会自动推）")
        return 0
    print(
        "本机和 GitHub 各有对方没有的提交（两台电脑都合过东西）。不自动处理，请告诉 agent 先把 GitHub 的 main 合进一个工位分支，再走 merge"
    )
    return 1


def cmd_push(root: Path) -> int:
    if read_mode(root) == "关":
        print("GitHub 关着（github-mode 关），不推送")
        return 1
    result = Git(root).run("push", "--quiet", "origin", "main", timeout=NET_TIMEOUT * 2)
    if result.returncode != 0:
        print(f"没推上去：{result.stderr.strip()[:300]}")
        return 1
    print("已把 main 推到 GitHub")
    return 0


def cmd_mode(root: Path, mode: str | None) -> int:
    if mode is None:
        print(
            f"现在的 GitHub 档：{read_mode(root)}（关＝不碰网络；备份＝合并后推一次；多机＝领卡、PR、云端检查照旧）"
        )
        return 0
    write_mode(root, mode)
    print(f"GitHub 档已设为：{mode}")
    return 0


def hook_text(python: str, script: Path) -> str:
    return f"""#!/bin/sh
# 守 main 的本机钩子，由 {HOOK_MARK} 装（卡 311，CHG-SCPT-2026-718），别手改
[ "$1" = "prepared" ] || exit 0
input=$(cat)
case "$input" in
  *" {MAIN_REF}"*) ;;
  *) exit 0 ;;
esac
common=$(git rev-parse --path-format=absolute --git-common-dir) || exit 1
root=$(dirname "$common")
printf '%s\\n' "$input" | "{python}" -B "{script.as_posix()}" --root "$root" hook-check
"""


def hooks_dir(root: Path) -> Path:
    return Path(Git(root).out("rev-parse", "--path-format=absolute", "--git-path", "hooks"))


def cmd_install_hook(root: Path) -> int:
    path = hooks_dir(root) / HOOK_NAME
    if path.exists() and HOOK_MARK not in path.read_text(encoding="utf-8", errors="replace"):
        print(f"{path} 已有别人的钩子，不覆盖；请告诉 agent 先看清它是做什么的")
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    python = Path(_python(root)).as_posix()
    path.write_text(
        hook_text(python, Path(__file__).resolve()),
        encoding="utf-8",
        errors="replace",
        newline="\n",
    )
    path.chmod(0o755)
    print(f"已装守 main 的钩子：{path}")
    return 0


def hook_allows(root: Path, lines: Sequence[str], token: str | None) -> list[str]:
    """返回被拒的那些行（空＝全放行）。只管 refs/heads/main。"""
    denied = []
    token_file = state_dir(root) / TOKEN_NAME
    transaction = None
    if token_file.exists():
        try:
            loaded = json.loads(token_file.read_text(encoding="utf-8", errors="replace"))
            transaction = loaded if isinstance(loaded, dict) else {}
        except (OSError, ValueError):
            transaction = {}
    origin = ""
    for line in lines:
        parts = line.split()
        if len(parts) != 3 or parts[2] != MAIN_REF or parts[0] == parts[1]:
            continue
        if transaction is not None:
            expected = transaction.get("token")
            if (
                not token or not isinstance(expected, str) or not secrets.compare_digest(token, expected)
                or parts[0] != transaction.get("base")
            ):
                denied.append(line)
            continue
        origin = origin or Git(root).rev(ORIGIN_REF)
        if parts[1] != ZERO and parts[1] == origin:
            continue
        denied.append(line)
    return denied


def cmd_hook_check(root: Path) -> int:
    denied = hook_allows(root, sys.stdin.read().splitlines(), os.environ.get(TOKEN_ENV))
    if denied:
        sys.stderr.write(
            "本机钩子拒绝直接改 main：日常改动请在工位分支上提交，再由 pm_merge.py merge 合并"
            "（从 GitHub 同步用 pm_merge.py sync）。\n"
        )
        return 1
    return 0


def _intro_commit(git: Git) -> str:
    relative = (
        Path(__file__).resolve().relative_to(DEFAULT_ROOT).as_posix() if _under_root() else ""
    )
    if not relative:
        return ""
    return git.run(
        "log", "--diff-filter=A", "--format=%H", "-1", "main", "--", relative
    ).stdout.strip()


def _under_root() -> bool:
    try:
        Path(__file__).resolve().relative_to(DEFAULT_ROOT)
    except ValueError:
        return False
    return True


def unexplained_commits(root: Path, since: str) -> list[tuple[str, str]]:
    git = Git(root)
    if not since:
        return []
    known = {entry.get("merge_sha", "") for entry in read_log(root)}
    origin = git.rev("origin/main")
    raw = git.out(
        "rev-list",
        "--first-parent",
        "--format=%H%x1f%P%x1f%B%x1e",
        "--no-commit-header",
        f"{since}..main",
    )
    bad = []
    for record in raw.split("\x1e"):
        if not record.strip():
            continue
        sha, _parents, message = (record.strip("\n").split("\x1f") + ["", ""])[:3]
        subject = message.strip().splitlines()[0] if message.strip() else ""
        if sha in known or GITHUB_MERGE.match(subject):
            continue
        if MERGE_MARK in message and origin and git.ok("merge-base", "--is-ancestor", sha, origin):
            continue
        bad.append((sha, subject))
    return bad


def cmd_verify_log(root: Path, since: str | None) -> int:
    git = Git(root)
    start = since if since is not None else _intro_commit(git)
    if not start:
        print("本机合并命令还没进 main，没有要核对的")
        return 0
    if not git.rev(start):
        print(f"找不到起点提交 {start}")
        return 2
    bad = unexplained_commits(root, start)
    if not bad:
        print(
            "main 上本机合并以来的每个提交都有来历（本机合并记录、GitHub PR 合并或经 GitHub 同步的本机合并）"
        )
        return 0
    print(f"main 上有 {len(bad)} 个提交来历对不上（不在本机合并记录里，也不是 GitHub PR 合并）：")
    for sha, subject in bad:
        print(f"  {sha[:12]} {subject}")
    print("请用户决定：留着（说一句原因记下来）还是 git revert 退掉。agent 不要自己退。")
    return 1


def utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: Sequence[str] | None = None) -> int:
    utf8_output()
    parser = argparse.ArgumentParser(
        prog="pm_merge.py", description="本机合并，GitHub 按需使用（卡 311）"
    )
    parser.add_argument(
        "--root", type=Path, default=DEFAULT_ROOT, help="控制根（默认按本脚本位置推出）"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    merge = sub.add_parser("merge", help="把工位分支合进本机 main")
    merge.add_argument("worktree")
    merge.add_argument("--pid", default="")
    merge.add_argument("--full-gate", action="store_true", help="不管改了什么都跑一遍 gate run")
    merge.add_argument("--archive-existing", action="store_true", help="归档与现役相符的发布副本，保留本机发布文件")
    audit = sub.add_parser("audit-record", help="登记另一会话对当前候选的独立审计")
    audit.add_argument("worktree")
    audit.add_argument("--base", required=True, help="审计所读的 main 完整提交号")
    audit.add_argument("--candidate", required=True, help="审计所读的工位候选完整提交号")
    audit.add_argument("--verdict", required=True, choices=("PASS", "FAIL"))
    audit.add_argument("--report", required=True, type=Path)
    sub.add_parser("sync", help="从 GitHub 拉 main，只做快进")
    sub.add_parser("push", help="把 main 推到 GitHub")
    mode = sub.add_parser("github-mode", help="看或设 GitHub 档")
    mode.add_argument("mode", nargs="?", choices=MODES)
    sub.add_parser("install-hook", help="装守 main 的本机钩子")
    sub.add_parser("hook-check", help="钩子内部用")
    verify = sub.add_parser("verify-log", help="核对 main 上每个提交的来历（只读）")
    verify.add_argument("--since", default=None)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    if not (root / ".git").exists():
        print(f"{root} 不是控制根（没有 .git）")
        return 2
    if args.command == "merge":
        return cmd_merge(root, args.worktree, args.pid, args.full_gate, archive_existing=args.archive_existing)
    if args.command == "audit-record":
        return cmd_audit_record(root, args.worktree, args.base, args.candidate, args.verdict, args.report)
    if args.command == "sync":
        return cmd_sync(root)
    if args.command == "push":
        return cmd_push(root)
    if args.command == "github-mode":
        return cmd_mode(root, args.mode)
    if args.command == "install-hook":
        return cmd_install_hook(root)
    if args.command == "hook-check":
        return cmd_hook_check(root)
    return cmd_verify_log(root, args.since)


if __name__ == "__main__":
    sys.exit(main())
