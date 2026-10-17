"""Mechanical PR audit for WorkSpacePM (reviewer tool, read-only).

Runs the checks every audit in reviews/ repeats by hand: merge shape, no extra
changes in the merge commit, conflicts, scope, privacy scan of added lines,
whether CI should run, the CI result, and an optional byte-for-byte comparison
with a review patch.  It never writes to the working tree, the index or any
branch; the only Git writes are fetched refs under refs/audit/.

Usage:
    python reviews/tools/audit_pr.py 4
    python reviews/tools/audit_pr.py 3 --patch reviews/patches/10_m3_envport.patch --patch-base 46aead1
    python reviews/tools/audit_pr.py 4 --json

Exit code: 0 when no check FAILs (WARN, INFO and UNVERIFIED do not fail), 1 when
at least one check FAILs, 2 on a usage or Git error.  The judgement part of an
audit is in reviews/21_audit_checklist.md; this script does not replace it.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass

DEFAULT_REPO = "baiyangfu-hash/WorkSpacePM"
WORKFLOW_FILE = ".github/workflows/sw008-ci.yml"
MERGE_SEARCH_LIMIT = 500

# Paths a reviewer must call out when a PR touches them (see the handoff, section 1).
PROTECTED_PATTERNS = (
    "AGENTS.md",
    ".github/workflows/*",
    "00_Obsidian_Base*",
    "00_Infrastructure/auto_pm/*",
    ".auto-pm/*",
    "*CHG-*",
    "*DEC-*",
    "*_WBS_PM.md",
    "*台账*",
)

# Hard failures: anything that looks like a live secret.
SECRET_PATTERNS = {
    "GitHub 令牌": re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}"),
    "API 密钥": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}|\bAKIA[0-9A-Z]{16}\b|\bAIza[0-9A-Za-z_-]{30,}"),
    "私钥": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
}
# Warnings: personal or local data a reviewer must look at (some are a known baseline on main).
PRIVACY_PATTERNS = {
    "长 base64 串": re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{60,}={0,2}(?![A-Za-z0-9+/])"),
    "邮箱": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "内网地址": re.compile(
        r"\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b"
    ),
    "手机号": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "身份证号": re.compile(r"(?<!\d)[1-9]\d{5}(19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)"),
    "本机路径": re.compile(r"[A-Za-z]:\\\\?Users\\\\?|/home/[a-z][a-z0-9_-]*/|/Users/[A-Za-z]"),
    "用户名 fubai": re.compile(r"fubai", re.IGNORECASE),
}
# Addresses that are known to be harmless in commit trailers and test fixtures.
ALLOWED_EMAILS = ("noreply@anthropic.com", "@example.invalid", "@example.com", "@users.noreply.github.com")


@dataclass
class Check:
    id: str
    status: str  # PASS / FAIL / WARN / INFO / UNVERIFIED
    detail: str


class GitError(RuntimeError):
    pass


def git(*args: str, cwd: str | None = None, env: dict[str, str] | None = None, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-c", "core.quotepath=off", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and result.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def git_ok(*args: str, cwd: str | None = None) -> bool:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False).returncode == 0


def short(sha: str) -> str:
    return sha[:7]


# --- Git facts -------------------------------------------------------------------------------------------------


def find_merge_commit(head: str, main_ref: str, cwd: str | None = None) -> tuple[str, list[str]] | None:
    """Return (merge commit, parents) of the first-parent merge on main that brought ``head`` in, if any."""
    out = git("rev-list", "--first-parent", "--merges", "--parents", f"--max-count={MERGE_SEARCH_LIMIT}", main_ref, cwd=cwd)
    for line in out.splitlines():
        sha, *parents = line.split()
        if head in parents[1:]:
            return sha, parents
    return None


def merge_result_tree(ours: str, theirs: str, cwd: str | None = None) -> tuple[bool, str]:
    """Return (clean, tree or conflict text) for merging ``theirs`` into ``ours`` without touching anything."""
    result = subprocess.run(
        ["git", "-c", "core.quotepath=off", "merge-tree", "--write-tree", "--name-only", ours, theirs],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    lines = result.stdout.strip().splitlines()
    if result.returncode == 0:
        return True, lines[0]
    if result.returncode == 1:
        return False, ", ".join(line for line in lines[1:] if line and "\t" not in line) or "冲突"
    raise GitError(f"git merge-tree: {result.stderr.strip()}")


def changed_files(base: str, head: str, cwd: str | None = None) -> list[str]:
    return [line for line in git("diff", "--name-only", f"{base}...{head}", cwd=cwd).splitlines() if line]


def added_lines(base: str, head: str, cwd: str | None = None) -> list[tuple[str, str]]:
    """Return (file, line) for every line the PR adds."""
    out = git("diff", "-U0", "--no-color", f"{base}...{head}", cwd=cwd)
    current = ""
    lines: list[tuple[str, str]] = []
    for line in out.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("+") and not line.startswith("+++"):
            lines.append((current, line[1:]))
    return lines


def ci_path_patterns(ref: str, cwd: str | None = None) -> list[str] | None:
    """Read the pull_request path filter of the CI workflow at ``ref``; ``None`` means the workflow runs for every PR."""
    try:
        text = git("show", f"{ref}:{WORKFLOW_FILE}", cwd=cwd)
    except GitError:
        return []
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == "pull_request:"), None)
    if start is None:
        return []
    indent = len(lines[start]) - len(lines[start].lstrip())
    patterns: list[str] = []
    in_paths = False
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if len(line) - len(line.lstrip()) <= indent:
            break
        if stripped == "paths:":
            in_paths = True
        elif in_paths and stripped.startswith("- "):
            patterns.append(stripped[2:].strip().strip("\"'"))
        else:
            in_paths = False
    return patterns or None


def path_matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-2])
    return fnmatch.fnmatchcase(path, pattern)


def patch_tree(patch: str, base: str, cwd: str | None = None) -> str:
    """Apply ``patch`` to ``base`` in a throw-away index and return the resulting tree (no worktree, no branch).

    ``patch`` is a file path, or ``<ref>:<path>`` to read the patch from a branch without checking it out.
    """
    with tempfile.TemporaryDirectory(prefix="audit_pr_") as tmp:
        env = dict(os.environ, GIT_INDEX_FILE=os.path.join(tmp, "index"))
        patch_file = os.path.abspath(patch) if os.path.exists(patch) else os.path.join(tmp, "patch")
        if not os.path.exists(patch):
            with open(patch_file, "w", encoding="utf-8", errors="replace", newline="") as handle:
                handle.write(git("show", patch, cwd=cwd))
        git("read-tree", base, cwd=cwd, env=env)
        git("apply", "--cached", "--whitespace=nowarn", patch_file, cwd=cwd, env=env)
        return git("write-tree", cwd=cwd, env=env).strip()


def tree_diff(left: str, right: str, cwd: str | None = None) -> list[str]:
    return [line for line in git("diff-tree", "-r", "--name-only", left, right, cwd=cwd).splitlines() if line]


# --- GitHub (public, unauthenticated, optional) -----------------------------------------------------------------


def github_json(path: str) -> dict | None:
    request = urllib.request.Request(f"https://api.github.com/repos/{path}", headers={"Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None


# --- Checks ----------------------------------------------------------------------------------------------------


def scan_privacy(lines: list[tuple[str, str]]) -> list[Check]:
    hard: dict[str, list[str]] = {}
    soft: dict[str, list[str]] = {}
    for path, text in lines:
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                hard.setdefault(label, []).append(path)
        for label, pattern in PRIVACY_PATTERNS.items():
            for match in pattern.finditer(text):
                if label == "邮箱" and any(match.group(0).endswith(a) or match.group(0) == a for a in ALLOWED_EMAILS):
                    continue
                soft.setdefault(label, []).append(path)
                break
    checks: list[Check] = []
    if hard:
        checks.append(Check("secrets", "FAIL", "; ".join(f"{k}: {len(v)} 处（{min(v)} 等）" for k, v in hard.items())))
    else:
        checks.append(Check("secrets", "PASS", "新增行里没有令牌、密钥、私钥"))
    if soft:
        checks.append(
            Check(
                "privacy",
                "WARN",
                "; ".join(f"{k}: {len(v)} 处（{min(v)} 等）" for k, v in soft.items())
                + "。本机路径和 fubai 在 main 上是已知基线，只需报告新增了哪一类",
            )
        )
    else:
        checks.append(Check("privacy", "PASS", "新增行里没有邮箱、内网地址、手机号、身份证号、本机路径、长 base64"))
    return checks


def audit(
    pr: int, *, repo: str, remote: str, patch: str | None, patch_base: str | None, network: bool, cwd: str | None = None
) -> tuple[dict, list[Check]]:
    git("fetch", "-q", remote, "main", f"+refs/pull/{pr}/head:refs/audit/pr-{pr}", cwd=cwd)
    main_ref = f"{remote}/main"
    head = git("rev-parse", f"refs/audit/pr-{pr}", cwd=cwd).strip()
    main = git("rev-parse", main_ref, cwd=cwd).strip()
    info = {"pr": pr, "head": head, "main": main}
    checks: list[Check] = []

    meta = github_json(f"{repo}/pulls/{pr}") if network else None
    if meta:
        info["title"] = meta.get("title")
        state = "merged" if meta.get("merged_at") else meta.get("state", "unknown")
    else:
        state = "unknown"

    found = find_merge_commit(head, main_ref, cwd=cwd)
    if found:
        state = "merged"
    info["state"] = state

    if state == "merged":
        if not found:
            checks.append(
                Check(
                    "merge_shape",
                    "FAIL",
                    "GitHub 显示已合并，但 main 上找不到以 PR 头部为第二个父提交的合并提交（可能用了 Squash 或 Rebase）",
                )
            )
            first_parent = None
        else:
            merge, parents = found
            info["merge"] = merge
            first_parent = parents[0]
            if len(parents) == 2:
                checks.append(
                    Check(
                        "merge_shape",
                        "PASS",
                        f"合并提交 {short(merge)}，父提交 {short(parents[0])}（原 main）和 {short(head)}（PR 头部）",
                    )
                )
            else:
                checks.append(Check("merge_shape", "WARN", f"合并提交 {short(merge)} 有 {len(parents)} 个父提交"))
            clean, expected = merge_result_tree(parents[0], head, cwd=cwd)
            actual = git("rev-parse", f"{merge}^{{tree}}", cwd=cwd).strip()
            if clean and expected == actual:
                checks.append(Check("merge_content", "PASS", "合并提交没有夹带额外改动（等于原 main 与 PR 头部的自动合并结果）"))
            elif clean:
                checks.append(
                    Check(
                        "merge_content",
                        "FAIL",
                        "合并提交和自动合并结果不同，多出的文件：" + ", ".join(tree_diff(expected, actual, cwd=cwd)[:10]),
                    )
                )
            else:
                checks.append(
                    Check("merge_content", "WARN", f"原 main 与 PR 头部之间有冲突（{expected}），合并时手工解决过，需要人工看")
                )
        base = first_parent or main
    else:
        base = main
        clean, detail = merge_result_tree(main, head, cwd=cwd)
        checks.append(
            Check("mergeable", "PASS" if clean else "FAIL", "和当前 main 合并无冲突" if clean else f"和当前 main 冲突：{detail}")
        )
        if git_ok("merge-base", "--is-ancestor", main, head, cwd=cwd):
            checks.append(Check("up_to_date", "PASS", "PR 已包含当前 main"))
        else:
            checks.append(Check("up_to_date", "INFO", "PR 不包含当前 main 的全部提交（无冲突时不影响合并）"))
    info["base"] = base

    files = changed_files(base, head, cwd=cwd)
    info["files"] = files
    protected = [
        f for f in files if any(path_matches(f, p) or fnmatch.fnmatchcase(os.path.basename(f), p) for p in PROTECTED_PATTERNS)
    ]
    checks.append(Check("scope", "INFO", f"{len(files)} 个文件"))
    if protected:
        checks.append(
            Check(
                "protected_paths",
                "WARN",
                "改到需要在报告里点名的路径：" + ", ".join(protected[:10]) + ("…" if len(protected) > 10 else ""),
            )
        )

    checks.extend(scan_privacy(added_lines(base, head, cwd=cwd)))

    patterns = ci_path_patterns(head, cwd=cwd)
    expected_ci = True if patterns is None else any(path_matches(f, p) for f in files for p in patterns)
    checks.append(
        Check(
            "ci_expected",
            "INFO",
            "改到 CI 关心的路径，应当跑 CI" if expected_ci else "只改了 CI 不关心的路径（paths 过滤），不会触发 CI",
        )
    )

    if network:
        shas = [head] + ([info["merge"]] if "merge" in info else [])
        runs = []
        for sha in shas:
            data = github_json(f"{repo}/actions/runs?head_sha={sha}&per_page=20")
            if data is None:
                runs = None
                break
            runs.extend(data.get("workflow_runs", []))
        if runs is None:
            checks.append(Check("ci_result", "UNVERIFIED", "取不到 GitHub Actions 记录（网络或限流）"))
        elif not runs:
            checks.append(
                Check(
                    "ci_result",
                    "UNVERIFIED" if expected_ci else "PASS",
                    "应当跑 CI，但没有找到运行记录（可能还在排队）" if expected_ci else "没有 CI 运行，符合预期",
                )
            )
        else:
            # Only the newest run per (workflow, event, commit) counts: older ones are re-runs or were cancelled by a newer push.
            newest: dict[tuple, dict] = {}
            for r in runs:
                key = (r.get("workflow_id"), r["event"], r["head_sha"])
                if key not in newest or r["id"] > newest[key]["id"]:
                    newest[key] = r
            runs = sorted(newest.values(), key=lambda r: r["id"])
            summary = ", ".join(
                f"run {r['id']}（{r['event']}，{short(r['head_sha'])}）: {r.get('conclusion') or r['status']}" for r in runs
            )
            bad = [r for r in runs if r.get("conclusion") not in (None, "success", "skipped")]
            pending = [r for r in runs if r["status"] != "completed"]
            status = "FAIL" if bad else "UNVERIFIED" if pending else "PASS"
            checks.append(
                Check("ci_result", status, summary + "。PASS 只代表 GitHub 显示 success；verdict 和失败数要看日志（清单第 3 步）")
            )
    else:
        checks.append(Check("ci_result", "UNVERIFIED", "离线模式，没有查 CI"))

    if patch:
        if not patch_base:
            raise GitError("--patch 需要同时给 --patch-base")
        try:
            tree = patch_tree(patch, patch_base, cwd=cwd)
        except GitError as exc:
            checks.append(Check("patch", "FAIL", f"补丁在 {short(patch_base)} 上应用失败：{exc}"))
        else:
            head_tree = git("rev-parse", f"{head}^{{tree}}", cwd=cwd).strip()
            diff = tree_diff(tree, head_tree, cwd=cwd)
            if not diff:
                checks.append(Check("patch", "PASS", "PR 头部和“补丁应用到基线”的结果逐字节一致"))
            else:
                checks.append(
                    Check("patch", "WARN", "以下文件和补丁结果不同（可能是有意取舍，需在报告里说明）：" + ", ".join(diff[:10]))
                )
    return info, checks


def render(info: dict, checks: list[Check]) -> str:
    rows = [f"# PR #{info['pr']} 机械检查", ""]
    if info.get("title"):
        rows.append(f"标题：{info['title']}")
    rows.append(
        f"状态：{info['state']}；PR 头部 `{short(info['head'])}`；main `{short(info['main'])}`"
        + (f"；合并提交 `{short(info['merge'])}`" if info.get("merge") else "")
    )
    rows += ["", "| 检查 | 结果 | 说明 |", "|---|---|---|"]
    rows += [f"| {c.id} | {c.status} | {c.detail.replace('|', '/')} |" for c in checks]
    failed = [c.id for c in checks if c.status == "FAIL"]
    rows += [
        "",
        f"机械检查：{'FAIL（' + ', '.join(failed) + '）' if failed else '没有 FAIL'}。判断部分按 reviews/21_audit_checklist.md 继续。",
    ]
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WorkSpacePM PR 机械检查（只读）")
    parser.add_argument("pr", type=int, help="PR 编号")
    parser.add_argument("--repo", default=DEFAULT_REPO, help="owner/name（查 GitHub 公开接口用）")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--patch", help="要对比的审阅补丁")
    parser.add_argument("--patch-base", help="补丁基于的提交")
    parser.add_argument("--offline", action="store_true", help="不访问 GitHub 接口")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)
    try:
        info, checks = audit(
            args.pr, repo=args.repo, remote=args.remote, patch=args.patch, patch_base=args.patch_base, network=not args.offline
        )
    except GitError as exc:
        print(f"audit_pr: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps({"info": info, "checks": [asdict(c) for c in checks]}, ensure_ascii=False, indent=2))
    else:
        print(render(info, checks))
    return 1 if any(c.status == "FAIL" for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
