"""Read-only pre-merge check for a pull request (``main.py pr ready <number>``).

It answers one question: may this PR be merged now?  It never merges, never comments, never edits a PR; the only
GitHub calls are reads (``gh pr view`` and ``gh api`` GETs).  Merging stays with the main executor or the user
after AUD-001.  Every missing condition is named in plain words; the exit code is non-zero if any is missing.

Conditions (the user's merge rule, plus the two the project added for audit and the safety zone):

1. the PR is open, not a draft, and merges into main without conflict;
2. an audit report for this PR exists under ``reviews/`` (or a ``--reports-dir``) and the head commit it names is the
   PR's current head, with a passing conclusion;
3. every check run and status on the current head is successful, and ``safety-zone`` is among them;
4. a PR that touches the safety zone carries a comment ``安全签字 <current head>`` from the named signer
   (judged by ``reviews/tools/safety_zone_check.find_signature``, the same function safety-gate uses).
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from auto_pm.application.core.agent_worktree_service import AgentWorktreeError
from auto_pm.application.core.pr_open_service import GhRunner, default_gh

PASSING_CONCLUSIONS = frozenset({"success", "neutral", "skipped"})
PLC_TOP = "0100_PLC自动化"
SAFETY_CONTEXT = "safety-zone"
SHA_TOKEN = re.compile(r"(?<![0-9A-Za-z])[0-9a-f]{7,40}(?![0-9A-Za-z])")
NEGATIVE_VERDICT = re.compile(r"不同意|不通过|未通过|不过|不能合并|不可合并")
POSITIVE_VERDICT = re.compile(r"同意|通过|过[\s*）)、，,。；;]|过$|可以合并")
SAFETY_DECLARATION = re.compile(r"^\s*安全回路\s*[:：]\s*是\s*$", re.MULTILINE)
WRITEBACK = re.compile(r"^##\s*建议回写\s*$(.*?)(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)
HEADER_LINES = 6


@dataclass(frozen=True)
class ReadyItem:
    name: str
    ok: bool
    detail: str


@dataclass
class ReadyReport:
    number: int
    head: str = ""
    items: list[ReadyItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    writeback: str = ""

    @property
    def ready(self) -> bool:
        return bool(self.items) and all(item.ok for item in self.items)

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.items.append(ReadyItem(name, ok, detail))


def load_safety_module(root: Path) -> ModuleType | None:
    script = root / "reviews" / "tools" / "safety_zone_check.py"
    if not script.is_file():
        return None
    spec = importlib.util.spec_from_file_location("pr_ready_safety_zone_check", script)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


def _head_matches(head: str, token: str) -> bool:
    return len(token) >= 7 and head.lower().startswith(token.lower())


def _verdict_line(text: str) -> str:
    """The conclusion: the line holding 结论, or the first line under a bare ``## 结论`` heading."""

    lines = text.splitlines()
    for index, line in enumerate(lines):
        if "结论" not in line:
            continue
        if line.strip().lstrip("#").strip().strip("*：: ") == "结论":
            return next((nxt for nxt in lines[index + 1 :] if nxt.strip()), "")
        return line
    return ""


def find_audit_report(
    number: int, head: str, report_dirs: Sequence[Path]
) -> tuple[bool, str]:
    """(ok, plain-words detail).  A report belongs to the PR when its file name or first lines say ``PR #<n>``."""

    pattern = re.compile(rf"(?i)(?:\bPR\s*#?\s*{number}\b|(?<![0-9])#{number}(?![0-9])|\bpr-?{number}(?![0-9]))")
    stale: list[str] = []
    negative: list[str] = []
    for directory in report_dirs:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.md")):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            head_lines = "\n".join(text.splitlines()[:HEADER_LINES])
            if not pattern.search(path.name) and not pattern.search(head_lines):
                continue
            shas = SHA_TOKEN.findall(text)
            if not any(_head_matches(head, sha) for sha in shas):
                named = "、".join(dict.fromkeys(sha[:8] for sha in shas[:3])) or "没有写提交号"
                stale.append(f"{path.name}（审的是 {named}）")
                continue
            verdict = _verdict_line(text)
            if NEGATIVE_VERDICT.search(verdict) or not POSITIVE_VERDICT.search(verdict):
                negative.append(f"{path.name}（结论行：{verdict.strip()[:60] or '找不到结论行'}）")
                continue
            return True, f"{path.name}，审的是当前头 {head[:8]}"
    if negative:
        return False, "找到审计报告但结论不是通过：" + "；".join(negative)
    if stale:
        return False, (
            f"审计报告审的不是当前头 {head[:8]}（PR 推过新提交后要重审）：" + "；".join(stale)
        )
    searched = "、".join(str(directory) for directory in report_dirs) or "(无目录)"
    return False, f"没有找到 PR #{number} 的审计报告（找过：{searched}；文件名或开头要写 PR #{number}）"


def judge_checks(runs: list[dict[str, Any]], statuses: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """(problems, passed names) over the check runs and commit statuses of the head commit."""

    problems: list[str] = []
    passed: list[str] = []
    for run in runs:
        name = str(run.get("name") or "?")
        if run.get("status") != "completed":
            problems.append(f"{name}：还没跑完（{run.get('status')}）")
        elif str(run.get("conclusion") or "").lower() not in PASSING_CONCLUSIONS:
            problems.append(f"{name}：{run.get('conclusion')}")
        else:
            passed.append(name)
    for status in statuses:
        name = str(status.get("context") or "?")
        if status.get("state") != "success":
            problems.append(f"{name}：{status.get('state')}")
        else:
            passed.append(name)
    return problems, passed


class PrReadyService:
    def __init__(
        self,
        control_root: str | Path,
        *,
        gh: GhRunner | None = None,
        report_dirs: Sequence[Path] | None = None,
        repo: str | None = None,
    ) -> None:
        self._root = Path(control_root)
        self._gh = gh or default_gh
        self._report_dirs = tuple(report_dirs) if report_dirs else (self._root / "reviews",)
        self._repo = repo

    # ── GitHub reads ─────────────────────────────────────────────────

    def _read(self, args: Sequence[str]) -> Any:
        result = self._gh(list(args), None)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
            raise AgentWorktreeError(f"`gh {' '.join(args[:3])}` 失败：{detail}")
        try:
            return json.loads(result.stdout or "null")
        except ValueError as error:
            raise AgentWorktreeError(f"`gh {' '.join(args[:3])}` 返回的不是 JSON：{error}") from error

    def _repo_name(self) -> str:
        if self._repo:
            return self._repo
        data = self._read(["repo", "view", "--json", "nameWithOwner"])
        name = str((data or {}).get("nameWithOwner") or "")
        if not name:
            raise AgentWorktreeError("认不出仓库名；加 --repo owner/name")
        self._repo = name
        return name

    def _paged(self, path: str, key: str | None = None) -> list[dict[str, Any]]:
        raw = self._read(["api", path, "--paginate", "--slurp"])
        pages = raw if isinstance(raw, list) else [raw]
        out: list[dict[str, Any]] = []
        for page in pages:
            items = (page or {}).get(key) if key and isinstance(page, dict) else page
            if isinstance(items, list):
                out += [item for item in items if isinstance(item, dict)]
            elif isinstance(items, dict):
                out.append(items)
        return out

    # ── the check ────────────────────────────────────────────────────

    def check(self, number: int) -> ReadyReport:
        report = ReadyReport(number)
        pr = self._read(
            ["pr", "view", str(number), "--json", "headRefOid,state,isDraft,mergeable,baseRefName,body,files"]
        )
        head = str(pr.get("headRefOid") or "")
        if not head:
            raise AgentWorktreeError(f"读不到 PR #{number} 的头提交")
        report.head = head
        body = str(pr.get("body") or "")
        match = WRITEBACK.search(body)
        report.writeback = match.group(1).strip() if match else ""

        state_ok = pr.get("state") == "OPEN" and not pr.get("isDraft") and pr.get("baseRefName") == "main"
        report.add(
            "PR 状态",
            state_ok,
            "开着、不是草稿、合入 main"
            if state_ok
            else f"现在是 {pr.get('state')}，草稿={pr.get('isDraft')}，目标分支 {pr.get('baseRefName')}；只有开着、非草稿、合入 main 的 PR 才能放行",
        )
        mergeable = pr.get("mergeable")
        report.add(
            "与 main 无冲突",
            mergeable == "MERGEABLE",
            "无冲突" if mergeable == "MERGEABLE" else f"GitHub 报 {mergeable}（UNKNOWN 是还在算，稍后再查；CONFLICTING 要先解决冲突）",
        )

        ok, detail = find_audit_report(number, head, self._report_dirs)
        report.add("独立审计报告", ok, detail)

        repo = self._repo_name()
        runs = self._paged(f"repos/{repo}/commits/{head}/check-runs", "check_runs")
        combined = self._read(["api", f"repos/{repo}/commits/{head}/status"]) or {}
        statuses = [s for s in combined.get("statuses") or [] if isinstance(s, dict)]
        problems, passed = judge_checks(runs, statuses)
        if SAFETY_CONTEXT not in passed and not any(SAFETY_CONTEXT in p for p in problems):
            problems.append(f"{SAFETY_CONTEXT}：没有出现（safety-gate 还没跑，或这个提交没触发）")
        report.add(
            "必过检查和 safety-zone",
            not problems,
            f"{len(passed)} 项全部 success，含 {SAFETY_CONTEXT}" if not problems else "；".join(problems),
        )
        if not runs and not statuses:
            report.notes.append("当前头没有任何检查结果：纯文档 PR 的 sw008-ci 按路径过滤不会自动跑，需要 workflow_dispatch 手动跑")

        files = [str(f.get("path") or "") for f in pr.get("files") or [] if isinstance(f, dict)]
        touches_plc = any(path == PLC_TOP or path.startswith(f"{PLC_TOP}/") for path in files)
        declared_yes = bool(SAFETY_DECLARATION.search(body))
        if touches_plc or declared_yes:
            self._check_signature(report, repo, number, head)
        else:
            report.add("安全签字", True, "没改 0100_PLC自动化、也没声明安全回路，不需要")
        report.notes.append("评审对话是否全部解决：本命令不查，请在 PR 页面确认（合并条件之一）")
        return report

    def _check_signature(self, report: ReadyReport, repo: str, number: int, head: str) -> None:
        module = load_safety_module(self._root)
        if module is None:
            report.add("安全签字", False, "找不到 reviews/tools/safety_zone_check.py，无法判断签字；不放行")
            return
        comments = self._paged(f"repos/{repo}/issues/{number}/comments")
        result = module.Result()
        found = module.find_signature(comments, head, result)
        if found:
            report.add("安全签字", True, found)
        else:
            why = "；".join(result.notes) or "评论里没有“安全签字 <当前头提交号>”这一行"
            report.add("安全签字", False, f"改到安全回路（或声明了涉及），但{why}")


def render(report: ReadyReport) -> list[str]:
    lines = [f"PR #{report.number} 当前头 {report.head[:8]}"]
    for item in report.items:
        lines.append(f"{'✓' if item.ok else '✗'} {item.name}：{item.detail}")
    lines += [f"注意 {note}" for note in report.notes]
    if report.ready:
        lines.append("结论：条件都满足，可以合并（本命令不合并；只用 Merge commit）。")
        lines.append("合并后请提醒主执行回写台账和 WBS，再执行 ledger reconcile。")
        if report.writeback:
            lines.append("PR 描述里的建议回写：" + " ".join(report.writeback.split()))
    else:
        missing = "、".join(item.name for item in report.items if not item.ok)
        lines.append(f"结论：不能合并，缺：{missing}。")
    return lines


__all__ = [
    "PrReadyService",
    "ReadyItem",
    "ReadyReport",
    "find_audit_report",
    "judge_checks",
    "render",
]
