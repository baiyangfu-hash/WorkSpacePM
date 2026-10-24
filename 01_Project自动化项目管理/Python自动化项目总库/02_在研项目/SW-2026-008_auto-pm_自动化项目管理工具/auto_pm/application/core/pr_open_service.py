"""Open a pull request for an agent station (WS-001 follow-up, WBS X05 card C).

``main.py pr open <agent> <card> --task-card <path>`` replaces the hand-written part of handing work in:
branch name, PR title, the ``任务卡:`` line and the CHG numbers are filled in by the command, and the same
scope judge that runs on GitHub (``reviews/tools/pr_scope_check.py``) runs locally first.

The command only ever *opens*:

* it never merges, never enables auto-merge and never edits an existing PR (merging follows AUD-001);
* it never force-pushes and never touches a branch other than ``<prefix><card>`` of the station;
* every refusal happens before anything leaves the machine; a push is the first outward action.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from auto_pm.application.core.agent_worktree_service import (
    AGENT_ROSTER,
    MAIN_REF,
    AgentWorktreeError,
    AgentWorktreeService,
    StationRefusedError,
    caller_agent,
)
from auto_pm.infrastructure.control_root_guard import clean_git_environment

UNKNOWN_CALLER = "?"  # what caller_agent() returns when the markers name nobody on the roster
# Whitelist: the only accepted form is CHG-<PROJECT>-YYYY-NNN in ASCII.  Any other mention of "CHG"
# (to be registered, pending, 待申请, TBA, full-width digits or spaces ...) is refused, not matched by wording.
CHG_NUMBER = re.compile(r"CHG-[A-Z]+-[0-9]{4}-[0-9]{3,}", re.ASCII)
PUSH_BACKOFF_SECONDS = (2, 4, 8, 16)
NETWORK_FAILURE = re.compile(
    r"could not resolve|connection (?:reset|refused|timed out)|timed out|unable to access|"
    r"rpc failed|remote end hung up|early eof|network is unreachable|temporary failure|"
    r"ssl connect|ssl_|tls|http/2 stream|returned error: 50[234]",
    re.IGNORECASE,
)
PR_URL = re.compile(r"https?://[^\s]+/pull/(\d+)")
PLC_TOP = "0100_PLC自动化"  # a PR touching it must carry the 安全回路 line (safety_zone_check.py)
SAFETY_ANSWERS = ("是", "否")
JUDGE_RELATIVE = Path("reviews") / "tools" / "pr_scope_check.py"

GhRunner = Callable[[Sequence[str], "str | None"], "subprocess.CompletedProcess[str]"]
Judge = Callable[[Path, str, str, str], "tuple[int, str]"]
Sleeper = Callable[[float], None]


class PrOpenRefusedError(StationRefusedError):
    """A check refused to open the PR; the message says why and what to do next."""


@dataclass(frozen=True)
class PrPlan:
    """Everything the PR will carry; ``--dry-run`` stops after this."""

    agent: str
    branch: str
    title: str
    body: str
    task_card: str
    chg_numbers: tuple[str, ...]
    commits: tuple[str, ...]
    base_sha: str
    head_sha: str
    scope_report: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PrOpened:
    plan: PrPlan
    number: int
    url: str
    pushed: bool


def default_gh(args: Sequence[str], stdin: str | None) -> subprocess.CompletedProcess[str]:
    gh = shutil.which("gh")
    if gh is None:
        raise PrOpenRefusedError(
            "本机没有装 GitHub 命令行 `gh`；先装好并 `gh auth login`，或把分支交给用户在网页上开 PR"
        )
    return subprocess.run(
        [gh, *args],
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        stdin=None if stdin is not None else subprocess.DEVNULL,
    )


def gh_status() -> tuple[bool, bool]:
    """(installed, logged in) for ``doctor``; read-only."""

    if shutil.which("gh") is None:
        return False, False
    try:
        return True, default_gh(["auth", "status"], None).returncode == 0
    except OSError:
        return True, False


class PrOpenService:
    """Check an agent's finished station and open (never merge) its pull request."""

    def __init__(
        self,
        control_root: str | Path,
        *,
        gh: GhRunner | None = None,
        judge: Judge | None = None,
        judge_script: Path | None = None,
        sleep: Sleeper = time.sleep,
    ) -> None:
        self._stations = AgentWorktreeService(control_root, measure_size=False)
        self._root = Path(control_root).resolve()
        self._gh = gh or default_gh
        self._judge_script = judge_script or self._root / JUDGE_RELATIVE
        self._judge = judge or self._run_judge
        self._sleep = sleep

    # ── plan (all refusals live here; nothing is sent) ───────────────

    def plan(
        self,
        agent: str,
        card: str,
        task_card: str,
        *,
        evidence: Sequence[str] = (),
        safety_circuit: str | None = None,
        title: str | None = None,
        fetch: bool = True,
    ) -> PrPlan:
        prefix = AGENT_ROSTER.get(agent)
        if prefix is None:
            raise PrOpenRefusedError(
                f"`{agent}` 不在 agent 名册里（{'、'.join(sorted(AGENT_ROSTER))}）"
            )
        self._require_caller(agent)
        branch = f"{prefix}{card}"
        task_card = self._normalize_card_path(task_card)
        if fetch:
            fetched = self._git(self._root, "fetch", "origin", "main")
            if fetched.returncode != 0:
                raise AgentWorktreeError(
                    f"`git fetch origin main` 失败：{_detail(fetched)}；断网时可加 --no-fetch"
                )
        station = next(
            (s for s in self._stations.stations() if s.name == agent and s.registered), None
        )
        if station is None or station.kind != "agent":
            raise PrOpenRefusedError(
                f"{agent} 没有登记的工位；先 `main.py worktree open {agent} {card}`"
            )
        if station.branch != branch:
            raise PrOpenRefusedError(
                f"工位在分支 {station.branch or '(无)'}，应为 {branch}（前缀 {prefix} + 卡号 {card}）；"
                "分支名不符，不开 PR"
            )
        if station.dirty_paths:
            shown = "、".join(station.dirty_paths[:3])
            raise PrOpenRefusedError(
                f"工位有未提交的改动（{shown} 等）；先提交，PR 只带已提交的内容"
            )
        base_sha = self._rev(station.path, MAIN_REF)
        head_sha = self._rev(station.path, "HEAD")
        commits = self._commits(station.path, base_sha)
        if not commits:
            raise PrOpenRefusedError(f"{branch} 相对 origin/main 没有新提交，没有东西可交")
        chg_numbers = self._chg_numbers(commits)
        notes = [
            f"提交 {sha[:8]} 的说明里没有 CHG 号"
            for sha, message in commits
            if not CHG_NUMBER.search(message)
        ]
        safety_circuit = self._safety_declaration(station.path, base_sha, safety_circuit)
        card_text = self._card_at_base(task_card, base_sha)
        card_title = _card_title(card_text, task_card)
        body = self._body(task_card, chg_numbers, commits, evidence, safety_circuit)
        code, report = self._judge(station.path, base_sha, head_sha, body)
        if code != 0:
            raise PrOpenRefusedError(
                "越界检查不通过（和 GitHub 上的 gate 同一套判据），不开 PR：\n" + report.strip()
            )
        return PrPlan(
            agent=agent,
            branch=branch,
            title=title or f"[{card}] {card_title}",
            body=body,
            task_card=task_card,
            chg_numbers=chg_numbers,
            commits=tuple(sha for sha, _ in commits),
            base_sha=base_sha,
            head_sha=head_sha,
            scope_report=report,
            notes=notes,
        )

    # ── open ─────────────────────────────────────────────────────────

    def open(self, plan: PrPlan) -> PrOpened:
        auth = self._gh(["auth", "status"], None)
        if auth.returncode != 0:
            raise PrOpenRefusedError(
                f"`gh` 没登录：{_detail(auth)}；先 `gh auth login`，分支还没推，什么都没发生"
            )
        existing = self._gh(
            ["pr", "list", "--head", plan.branch, "--state", "open", "--json", "number,url"], None
        )
        if existing.returncode != 0:
            raise AgentWorktreeError(f"查已有 PR 失败：{_detail(existing)}；分支还没推")
        if '"number"' in existing.stdout:
            raise PrOpenRefusedError(
                f"分支 {plan.branch} 已有打开的 PR：{existing.stdout.strip()}；不重复开，也不改它"
            )
        station = self._stations.stations_dir / plan.agent
        self._push(station, plan.branch, plan.head_sha)
        created = self._gh(
            [
                "pr", "create", "--base", "main", "--head", plan.branch,
                "--title", plan.title, "--body-file", "-",
            ],
            plan.body,
        )  # fmt: skip
        match = PR_URL.search(created.stdout)
        if created.returncode != 0 or match is None:
            raise AgentWorktreeError(
                f"分支已推送，但开 PR 失败：{_detail(created)}；重跑本命令即可（已推送的分支不会重复推）"
            )
        return PrOpened(plan, int(match.group(1)), match.group(0), pushed=True)

    # ── pieces ───────────────────────────────────────────────────────

    def _require_caller(self, agent: str) -> None:
        caller = caller_agent()
        if caller == UNKNOWN_CALLER:
            raise PrOpenRefusedError(
                "认不出是哪个 agent 在执行（环境标记不在名册里或互相矛盾），不开 PR；请用户在自己的终端执行"
            )
        if caller and caller != agent:
            raise PrOpenRefusedError(f"你是 {caller}，不能替 {agent} 开 PR")

    @staticmethod
    def _normalize_card_path(task_card: str) -> str:
        path = task_card.strip().replace("\\", "/")
        while path.startswith("./"):
            path = path[2:]
        parts = path.split("/")
        if not path or path.startswith("/") or ".." in parts or re.match(r"^[A-Za-z]:", path):
            raise PrOpenRefusedError(f"任务卡路径必须是仓库内的相对路径：{task_card}")
        return path

    def _safety_declaration(self, station: Path, base_sha: str, declared: str | None) -> str | None:
        """The 安全回路 answer is the agent's/user's call, never derived: PLC changes must state it."""

        if declared is not None and declared not in SAFETY_ANSWERS:
            raise PrOpenRefusedError(f"--safety-circuit 只能是 是 或 否，现在是：{declared}")
        changed = self._git(station, "diff", "--name-only", "-z", f"{base_sha}...HEAD")
        if changed.returncode != 0:
            raise AgentWorktreeError(f"读改动文件失败：{_detail(changed)}")
        touches_plc = any(
            name == PLC_TOP or name.startswith(f"{PLC_TOP}/") for name in changed.stdout.split("\0")
        )
        if touches_plc and declared is None:
            raise PrOpenRefusedError(
                f"改动里有 {PLC_TOP} 下的文件，必须声明是否涉及安全回路（急停、安全门、光栅、联锁、"
                "安全继电器、双手启动）：加 --safety-circuit 是 或 --safety-circuit 否；"
                "填“是”要先仿真、再由用户在 PR 上写“安全签字 + 提交号”"
            )
        return declared

    def _card_at_base(self, task_card: str, base_sha: str) -> str:
        shown = self._git(self._root, "show", f"{base_sha}:{task_card}")
        if shown.returncode != 0:
            raise PrOpenRefusedError(
                f"任务卡 `{task_card}` 在 origin/main（{base_sha[:8]}）上不存在：卡要先合入 main，范围才算数"
            )
        return shown.stdout

    def _commits(self, station: Path, base_sha: str) -> list[tuple[str, str]]:
        revs = self._git(station, "rev-list", "--no-merges", "--reverse", f"{base_sha}..HEAD")
        if revs.returncode != 0:
            raise AgentWorktreeError(f"读提交失败：{_detail(revs)}")
        commits: list[tuple[str, str]] = []
        for sha in revs.stdout.split():
            message = self._git(station, "show", "-s", "--format=%B", sha)
            commits.append((sha, message.stdout.strip()))
        return commits

    @staticmethod
    def _chg_numbers(commits: list[tuple[str, str]]) -> tuple[str, ...]:
        for sha, message in commits:
            leftover = unicodedata.normalize("NFKC", CHG_NUMBER.sub("", message))
            if "chg" in leftover.casefold():
                raise PrOpenRefusedError(
                    f"提交 {sha[:8]} 的说明里有 CHG 字样但不是合格的号（占位、待登记、写法不对都算）；"
                    "只认 CHG-项目-年份-三位以上序号（半角，如 CHG-SCPT-2026-451）；"
                    "换成真实 CHG 号再开 PR（`git commit --amend` 或加一个带 CHG 号的提交说明）"
                )
        found: list[str] = []
        for _sha, message in commits:
            for number in CHG_NUMBER.findall(message):
                if number not in found:
                    found.append(number)
        if not found:
            raise PrOpenRefusedError(
                "所有提交的说明里都没有 CHG 号（形如 CHG-SCPT-2026-451）；请主执行登记变更单后，把号写进提交说明"
            )
        return tuple(found)

    @staticmethod
    def _body(
        task_card: str,
        chg_numbers: tuple[str, ...],
        commits: list[tuple[str, str]],
        evidence: Sequence[str],
        safety_circuit: str | None,
    ) -> str:
        lines = [f"任务卡: {task_card}"]
        if safety_circuit:
            lines.append(f"安全回路: {safety_circuit}")
        lines += ["", "## 变更单", ""]
        lines += [f"- {number}" for number in chg_numbers]
        lines += ["", "## 提交", ""]
        lines += [
            f"- {sha[:8]} {message.splitlines()[0] if message else ''}" for sha, message in commits
        ]
        lines += ["", "## 验收证据", ""]
        lines += [f"- {item}" for item in evidence] or ["- 未提供（由审计者自行核验）"]
        lines += ["", "由 `main.py pr open` 生成；只开不合，合并按 AUD-001 独立审计。"]
        return "\n".join(lines) + "\n"

    def _run_judge(self, station: Path, base_sha: str, head_sha: str, body: str) -> tuple[int, str]:
        script = self._judge_script
        if not script.is_file():
            return 2, f"找不到越界检查脚本 {script}（控制根不是 main 的最新内容？）；不放行"
        env = {**os.environ, "PR_BODY": body, "PYTHONIOENCODING": "utf-8"}
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(script),
                "--base",
                base_sha,
                "--head",
                head_sha,
                "--repo",
                str(station),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=env,
            stdin=subprocess.DEVNULL,
        )
        return result.returncode, (result.stdout + result.stderr)

    def _push(self, station: Path, branch: str, head_sha: str) -> None:
        # Explicit refspec: push exactly the commit that was checked, whatever remote.origin.push or push.default say.
        attempts = len(PUSH_BACKOFF_SECONDS) + 1
        for attempt in range(attempts):
            pushed = self._git(station, "push", "origin", f"{head_sha}:refs/heads/{branch}")
            if pushed.returncode == 0:
                self._git(station, "branch", f"--set-upstream-to=origin/{branch}", branch)
                return
            detail = _detail(pushed)
            if not NETWORK_FAILURE.search(detail):
                raise AgentWorktreeError(f"推送被拒（不是网络问题，不重试、不强推）：{detail}")
            if attempt < len(PUSH_BACKOFF_SECONDS):
                self._sleep(PUSH_BACKOFF_SECONDS[attempt])
        raise AgentWorktreeError(f"推送失败，网络重试 {attempts} 次都不通：{detail}")

    def _rev(self, cwd: Path, ref: str) -> str:
        result = self._git(cwd, "rev-parse", ref)
        if result.returncode != 0:
            raise AgentWorktreeError(f"git rev-parse {ref} 失败：{_detail(result)}")
        return result.stdout.strip()

    @staticmethod
    def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            env=clean_git_environment(),
            stdin=subprocess.DEVNULL,
        )


def _card_title(card_text: str, task_card: str) -> str:
    for line in card_text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return Path(task_card).stem


def _detail(result: subprocess.CompletedProcess[str]) -> str:
    return result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
