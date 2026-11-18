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
   的已入库文件），提交说明里引用、又写在分支里本卡实施卡（``02_规划/<卡号>_*.md``）里的变更单，至少一张已被用户
   批准、还没推到完成（变更单原件里的状态是已批准到验收中之间）。
3. GitHub 不是“关”档、而且连得上时，``origin/main`` 必须已在本机 main 里；连不上就跳过这一条并说明。
4. 控制根里和分支改到的路径重叠的未提交文件，只允许是和分支内容一样的副本（只差行尾）；合并前先备份再换掉，
   合并失败就放回去。别的未提交改动一律拒绝。
5. 本机门禁：``main.py gate precheck``（对照本机 main）退出 0；“要你点头”那一类或带 ``--full-gate`` 的，
   再跑 ``main.py gate run``，退出 0 才算过。
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
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from collections.abc import Sequence
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
GITHUB_MERGE = re.compile(r"^Merge pull request #\d+ ")
CARD_LINE = re.compile(r"^领卡占位:\s*(\S+)\s*$", re.MULTILINE)
CHG_RE = re.compile(r"CHG-[A-Z]+-\d{4}-\d{3,}")
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
STATE_LINE = re.compile(r"\|\s*变更状态\s*\|\s*([a-z_]+)\s*\|")
APPROVED_STATES = frozenset(
    {"approved", "conditionally_approved", "implementing", "pending_acceptance", "accepting"}
)
HOOK_NAME = "reference-transaction"
HOOK_MARK = "pm_merge.py install-hook"
GIT_TIMEOUT = 120
NET_TIMEOUT = 60
GATE_TIMEOUT = 4 * 60 * 60
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


# “要你点头”那一类：规则文件、PLC 项目文件、PLC 模板、本机合并命令自己（改它就能把这道闸关掉）。
USER_PATTERNS: tuple[str, ...] = (
    *_rule_patterns(),
    "0100_PLC自动化/*",
    "*/templates/plc-*",
    "*/scripts/pm_merge.py",
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


def run_gates(root: Path, worktree: Path, full: bool) -> GateResult:
    """本机门禁：跑 ``gate precheck``（带 ``--jobs`` 与 ``--json``）；有项目外改动或 ``full`` 时再跑根目录 ``tests/``。"""
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
    ]
    lines: list[str] = []
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
    steps_ok = (
        bool(steps)
        and all(isinstance(s, dict) and s.get("verdict") in ("PASS", "SKIPPED") for s in steps)
        and any(isinstance(s, dict) and s.get("verdict") == "PASS" for s in steps)
    )
    if result.returncode == 0:
        lines.append("gate precheck：退出码 0")
    elif steps_ok and outside:
        lines.append("gate precheck：项目内步骤 PASS（含项目外改动，续跑根目录 tests）")
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


def _commits(git: Git, base: str, tip: str) -> list[str]:
    raw = git.out("log", "--format=%B%x1e", f"{base}..{tip}")
    return [message.strip() for message in raw.split("\x1e") if message.strip()]


# 记录类文件：驾驶舱目录里的也不能随手删（变更单原件、台账、批准记录、WBS），删它们算“要你点头”。
RECORD_PATTERNS = ("*CHG-*", "*台账*", "*DEC-*", "*WBS*")
COCKPIT_PREFIX = (
    PROJECT_ROOT.relative_to(DEFAULT_ROOT).as_posix() + "/"
    if PROJECT_ROOT.is_relative_to(DEFAULT_ROOT)
    else ""
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


def card_files(git: Git, tip: str, card: str) -> list[str]:
    """分支里本卡的实施卡文件（``02_规划/<卡号>_*.md``）。"""
    raw = git.run("ls-tree", "-r", "-z", "--name-only", tip, check=True).stdout
    return [
        path
        for path in raw.split("\0")
        if re.search(rf"/02_规划/{re.escape(card)}_[^/]*\.md$", path)
    ]


def _changed_paths(git: Git, base: str, tip: str) -> list[str]:
    raw = git.run("diff", "--name-only", "-z", "--no-renames", base, tip, check=True).stdout
    return sorted({path for path in raw.split("\0") if path})


def _control_root_copies(root_git: Git, root: Path, sha: str, paths: list[str]) -> list[str]:
    """控制根里与这些路径重叠的未提交文件：和分支版本只差行尾的列出来（合并前换掉），不一样的直接拒绝。"""
    tracked = root_git.run(
        "status", "--porcelain=v1", "-z", "--untracked-files=no", check=True
    ).stdout
    dirty = [entry[3:] for entry in tracked.split("\0") if len(entry) > 3]
    unresolved = [path for path in dirty if path not in paths]
    if unresolved:
        raise RefusedError("控制根有未提交的改动，先处理再合并：" + "、".join(unresolved[:10]))
    replace = []
    candidates = set(dirty)
    if paths:
        untracked = root_git.run(
            "status", "--porcelain=v1", "-z", "--untracked-files=all", "--", *paths, check=True
        ).stdout
        candidates |= {entry[3:] for entry in untracked.split("\0") if entry.startswith("?? ")}
    for path in sorted(candidates):
        local = root / path
        if not local.is_file():
            raise RefusedError(f"控制根里 {path} 有未提交的改动（不是普通文件），先处理再合并")
        blob = root_git.run("cat-file", "-p", f"{sha}:{path}")
        if blob.returncode != 0:
            raise RefusedError(f"控制根里 {path} 有未提交的改动，分支里却删了它，先处理再合并")
        branch_bytes = subprocess.run(
            ["git", "cat-file", "-p", f"{sha}:{path}"],
            cwd=root,
            capture_output=True,
            check=True,
            timeout=GIT_TIMEOUT,
        ).stdout
        if not _same_ignoring_cr(local.read_bytes(), branch_bytes):
            raise RefusedError(
                f"控制根里 {path} 的未提交内容和分支里的不一样（不只差行尾），先把控制根的版本放进分支再合并"
            )
        replace.append(path)
    return replace


def plan_merge(root: Path, name: str, pid: str = "") -> Plan:
    if not NAME_RE.match(name):
        raise RefusedError(f"工位名写法不对：{name}")
    root_git = Git(root)
    head = root_git.run("symbolic-ref", "--quiet", "HEAD").stdout.strip()
    if head != MAIN_REF:
        raise RefusedError(f"控制根没停在 main（现在是 {head or '分离的 HEAD'}），不合并")
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
    messages = _commits(root_git, "main", sha)
    if not messages:
        raise RefusedError(f"分支 {branch} 比 main 没有新提交，没什么可合的")
    cards = [match.group(1) for message in messages for match in CARD_LINE.finditer(message)]
    if not cards:
        raise RefusedError("分支上没有一个提交带“领卡占位: <卡号>”这一行")
    chgs = sorted({number for message in messages for number in CHG_RE.findall(message)})
    paths = _changed_paths(root_git, "main", sha)
    user_paths = [path for path in paths if needs_user(path)]
    user_paths += [
        path for path in removed_outside_cockpit(root_git, "main", sha) if path not in user_paths
    ]
    if user_paths:
        card = cards[0]
        cards_text = "".join(
            root_git.run("show", f"{sha}:{path}").stdout for path in card_files(root_git, sha, card)
        )
        if not cards_text:
            raise RefusedError(
                "改到了要用户点头的文件（"
                + "、".join(user_paths[:5])
                + f"），分支里却没有本卡的实施卡（02_规划/{card}_*.md），变更单和卡对不上"
            )
        approved = []
        for number in chgs:
            if number not in cards_text:
                continue
            orders = find_change_orders(root, number, pid)
            if len(orders) > 1:
                raise RefusedError(f"找到 {len(orders)} 份 {number}，带 --pid 指明是哪个项目的")
            if orders and change_order_state(orders[0]) in APPROVED_STATES:
                approved.append(number)
        if not approved:
            raise RefusedError(
                "改到了要用户点头的文件（"
                + "、".join(user_paths[:5])
                + "），却没有一张用户批准过、又写在本卡实施卡里的变更单"
                + (f"（提交说明引用了 {'、'.join(chgs)}）" if chgs else "")
                + "；已推到完成的单不能再用来开新活"
            )
    notes: list[str] = []
    replace = _control_root_copies(root_git, root, sha, paths)
    return Plan(branch, sha, cards[0], chgs, paths, user_paths, replace, notes)


def check_github(root: Path, mode: str, notes: list[str]) -> None:
    """GitHub 开着且连得上时，另一台电脑推上去的 main 必须已在本机 main 里。"""
    if mode == "关":
        notes.append("GitHub 关着，没查另一台电脑的改动")
        return
    git = Git(root)
    fetch = git.run("fetch", "--quiet", "origin", "main", timeout=NET_TIMEOUT)
    if fetch.returncode != 0:
        notes.append("连不上 GitHub，跳过“另一台电脑有没有新改动”这一条")
        return
    if not git.ok("merge-base", "--is-ancestor", "origin/main", "main"):
        raise RefusedError(
            "GitHub 上的 main 有本机没有的提交（多半是另一台电脑推的），先跑 sync 同步再合并"
        )


def do_merge(root: Path, plan: Plan, gates: GateResult, mode: str) -> dict[str, Any]:
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
    token = secrets.token_hex(16)
    token_file = state_dir(root) / TOKEN_NAME
    token_file.parent.mkdir(parents=True, exist_ok=True)
    token_file.write_text(
        json.dumps({"token": token, "sha": plan.sha}), encoding="utf-8", errors="replace"
    )
    body = [f"领卡占位: {plan.card}"]
    if plan.chgs:
        body.append("变更单: " + "、".join(plan.chgs))
    body.append(MERGE_MARK + "（本机门禁通过）")
    merge_git = Git(root, env={**os.environ, TOKEN_ENV: token})
    try:
        result = merge_git.run(
            "merge",
            "--no-ff",
            "--no-verify",
            "-m",
            f"Merge branch '{plan.branch}'（本机合并）",
            "-m",
            "\n".join(body),
            plan.sha,
        )
    finally:
        token_file.unlink(missing_ok=True)
    if result.returncode != 0:
        root_git.run("merge", "--abort")
        for path in plan.replace:
            shutil.copy2(backup / path, root / path)
        raise RefusedError(
            f"git merge 失败，已退回，控制根原样：{(result.stdout + result.stderr).strip()[:400]}"
        )
    merge_sha = root_git.rev("HEAD")
    entry: dict[str, Any] = {
        "time": _now(),
        "branch": plan.branch,
        "branch_sha": plan.sha,
        "merge_sha": merge_sha,
        "card": plan.card,
        "chgs": plan.chgs,
        "user_paths": plan.user_paths,
        "gates": gates.lines,
        "replaced": plan.replace,
        "mode": mode,
        "pushed": False,
    }
    if mode != "关":
        push = root_git.run("push", "--quiet", "origin", "main", timeout=NET_TIMEOUT * 2)
        entry["pushed"] = push.returncode == 0
        if push.returncode != 0:
            entry["push_error"] = push.stderr.strip()[:300]
    append_log(root, entry)
    return entry


def _tracked_dirty(git: Git) -> list[str]:
    raw = git.run("status", "--porcelain=v1", "-z", "--untracked-files=no", check=True).stdout
    return [entry[3:] for entry in raw.split("\0") if len(entry) > 3]


def cmd_merge(root: Path, name: str, pid: str, full_gate: bool) -> int:
    mode = read_mode(root)
    try:
        plan = plan_merge(root, name, pid)
        check_github(root, mode, plan.notes)
        gates = run_gates(
            root, root / ".auto-pm" / "worktrees" / name, full_gate or bool(plan.user_paths)
        )
        if not gates.ok:
            raise RefusedError("本机门禁没过：" + "；".join(gates.lines))
        entry = do_merge(root, plan, gates, mode)
    except RefusedError as exc:
        print(f"拒绝合并：{exc}")
        return 1
    for note in plan.notes:
        print(f"说明：{note}")
    print(
        f"已合并 {plan.branch}（{plan.sha[:8]}）进 main：合并提交 {entry['merge_sha'][:8]}，卡 {plan.card}"
    )
    if plan.user_paths:
        print(
            "这次改到了要用户点头的文件，变更单："
            + "、".join(plan.chgs)
            + "；推到完成仍只有用户本人做"
        )
    if plan.replace:
        print(
            "控制根里这些只差行尾的副本已换成分支版本（原件备份在 .auto-pm/reports/local_merge/）："
            + "、".join(plan.replace)
        )
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
    if git.rev("main") == git.rev("origin/main"):
        print("本机 main 已和 GitHub 一样")
        return 0
    if git.ok("merge-base", "--is-ancestor", "main", "origin/main"):
        result = git.run("merge", "--ff-only", "origin/main")
        if result.returncode != 0:
            print(f"快进没成功：{result.stderr.strip()[:300]}")
            return 1
        print(f"已从 GitHub 同步到 {git.rev('main')[:8]}")
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
    common = Git(root).out("rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(common) / "hooks"


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
    expected = ""
    token_file = state_dir(root) / TOKEN_NAME
    if token and token_file.exists():
        try:
            expected = json.loads(token_file.read_text(encoding="utf-8", errors="replace")).get(
                "token", ""
            )
        except ValueError:
            expected = ""
    origin = ""
    for line in lines:
        parts = line.split()
        if len(parts) != 3 or parts[2] != MAIN_REF or parts[0] == parts[1]:
            continue
        if token and expected and secrets.compare_digest(token, expected):
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
        return cmd_merge(root, args.worktree, args.pid, args.full_gate)
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
