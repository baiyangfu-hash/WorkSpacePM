"""Mechanical PR audit for WorkSpacePM (reviewer tool, read-only).

Runs the checks every audit in reviews/ repeats by hand: merge shape, no extra
changes in the merge commit, conflicts, scope, privacy scan of added lines,
whether CI should run, the CI result, and an optional byte-for-byte comparison
with a review patch.  It never writes to the working tree, the index or any
branch; the only Git writes are the fetch itself: refs/audit/pr-N, the
remote-tracking main and FETCH_HEAD.

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
from pathlib import Path

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
    "roles/*",
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


def decode(data: bytes, what: str) -> str:
    """严格 UTF-8 解码；遇到坏字节不静默吞掉：在标准错误明说，再用替身字符继续（text_encoding 检查另会判 FAIL）。"""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        print(f"警告：{what} 含非法 UTF-8 字节（第 {error.start} 字节），已用替身字符继续", file=sys.stderr)
        return data.decode("utf-8", errors="replace")


def git_bytes(*args: str, cwd: str | None = None, env: dict[str, str] | None = None, check: bool = True) -> bytes:
    result = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=cwd, env=env, capture_output=True, check=False)
    if check and result.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {result.stderr.decode('utf-8', errors='replace').strip()}")
    return result.stdout


def git(*args: str, cwd: str | None = None, env: dict[str, str] | None = None, check: bool = True) -> str:
    return decode(git_bytes(*args, cwd=cwd, env=env, check=check), f"git {args[0]} 输出")


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
        check=False,
    )
    lines = decode(result.stdout, "git merge-tree 输出").strip().splitlines()
    if result.returncode == 0:
        return True, lines[0]
    if result.returncode == 1:
        # Output: tree, conflicted file names, a blank line, then Git's informational messages.
        names = []
        for line in lines[1:]:
            if not line:
                break
            names.append(line)
        return False, ", ".join(names) or "冲突"
    raise GitError(f"git merge-tree: {result.stderr.decode('utf-8', errors='replace').strip()}")


def changed_files(base: str, head: str, cwd: str | None = None) -> list[str]:
    return [line for line in git("diff", "--name-only", f"{base}...{head}", cwd=cwd).splitlines() if line]


def added_lines(base: str, head: str, cwd: str | None = None) -> list[tuple[str, str]]:
    """Return (file, line) for every line the PR adds."""
    out = git("diff", "-U0", "--no-color", f"{base}...{head}", cwd=cwd)
    current = ""
    in_header = False
    lines: list[tuple[str, str]] = []
    for line in out.splitlines():
        # "+++ " names the file only in a file header; inside a hunk it is an added line that starts with "++ ".
        if line.startswith("diff --git "):
            in_header = True
        elif in_header and line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("@@"):
            in_header = False
        elif not in_header and line.startswith("+"):
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
            with open(patch_file, "wb") as handle:
                handle.write(git_bytes("show", patch, cwd=cwd))  # 原样字节写出，补丁里的坏字节也要逐字节比较
        git("read-tree", base, cwd=cwd, env=env)
        git("apply", "--cached", "--whitespace=nowarn", patch_file, cwd=cwd, env=env)
        return git("write-tree", cwd=cwd, env=env).strip()


def tree_diff(left: str, right: str, cwd: str | None = None) -> list[str]:
    return [line for line in git("diff-tree", "-r", "--name-only", left, right, cwd=cwd).splitlines() if line]


# --- GitHub (public, unauthenticated, optional) -----------------------------------------------------------------


def github_json(path: str) -> dict | None:
    headers = {"Accept": "application/vnd.github+json"}
    # In GitHub Actions the job token lifts the anonymous rate limit; the token is only sent to api.github.com.
    if os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    request = urllib.request.Request(f"https://api.github.com/repos/{path}", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError):  # UnicodeDecodeError 是 ValueError：读不懂就当取不到，判 UNVERIFIED
        return None


REQUIRED_CONTEXT = "safety-zone"
BAD_STATES = {"failure", "error"}
PASSING_CONCLUSIONS = {"success", "skipped", "neutral"}


def judge_ci(
    runs: list[dict], check_runs: list[dict], statuses: list[dict], expected_ci: bool
) -> tuple[str, str]:
    """Verdict over Actions runs, check runs and commit statuses. Any failing or unfinished required context is not a PASS."""
    # Only the newest run per (workflow, event, commit) counts: older ones are re-runs or were cancelled by a newer push.
    newest: dict[tuple, dict] = {}
    for r in runs:
        key = (r.get("workflow_id"), r["event"], r["head_sha"])
        if key not in newest or r["id"] > newest[key]["id"]:
            newest[key] = r
    runs = sorted(newest.values(), key=lambda r: r["id"])
    parts: list[str] = []
    bad: list[str] = []
    pending: list[str] = []
    for r in runs:
        label = f"run {r['id']}（{r['event']}，{short(r['head_sha'])}）"
        parts.append(f"{label}: {r.get('conclusion') or r['status']}")
        if r.get("conclusion") not in (None, *PASSING_CONCLUSIONS):
            bad.append(label)
        elif r["status"] != "completed":
            pending.append(label)
    for c in check_runs:
        name = f"检查项 {c.get('name') or '?'}"
        parts.append(f"{name}: {c.get('conclusion') or c.get('status')}")
        if c.get("status") != "completed":
            pending.append(name)
        elif str(c.get("conclusion") or "").lower() not in PASSING_CONCLUSIONS:
            bad.append(name)
    seen_contexts: set[str] = set()
    for st in statuses:
        context = str(st.get("context") or "?")
        seen_contexts.add(context)
        name = f"状态 {context}"
        state = st.get("state")
        parts.append(f"{name}: {state}")
        if state in BAD_STATES:
            bad.append(name)
        elif state != "success":
            # An unfinished `safety-zone` must not let the PR through; other pending contexts are only unverified.
            (bad if context == REQUIRED_CONTEXT else pending).append(name)
    if REQUIRED_CONTEXT not in seen_contexts:
        # Same rule as pr_ready: every PR into main must show `safety-zone`; absent means the gate has not reported yet.
        pending.append(f"状态 {REQUIRED_CONTEXT}（没有出现，safety-gate 还没跑或这个提交没触发）")
    if bad:
        status = "FAIL"
    elif pending:
        status = "UNVERIFIED"
    elif not runs and not check_runs and not statuses:
        status = "UNVERIFIED" if expected_ci else "PASS"
        parts.append("应当跑 CI，但没有找到任何记录（可能还在排队）" if expected_ci else "没有 CI 运行，符合预期")
    else:
        status = "PASS"
    detail = ", ".join(parts)
    if bad:
        detail += "。不通过：" + "、".join(bad)
    if pending:
        detail += "。未完成或缺失：" + "、".join(pending)
    return status, detail + "。PASS 只代表 GitHub 显示 success；verdict 和失败数要看日志（清单第 2 步）"


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


COMPLETION_CLAIM = re.compile(r"已完成|已修复|已偿还|已解决|已落地|已关闭|已搞定|已修好")
COMMIT_ID = re.compile(r"(?<![0-9A-Za-z])(?=[0-9a-f]*[0-9])[0-9a-f]{7,40}(?![0-9A-Za-z])")


def scan_completion_evidence(body: str | None) -> Check:
    """FIX-001 第 3 条：PR 描述写“已完成”之类，必须附提交号（7 位以上十六进制）或明写“未核实”。只报 WARN，不改通过/失败。"""
    if body is None:
        return Check("completion_evidence", "UNVERIFIED", "取不到 PR 描述，没法核“完成”是否附了证据")
    claims = sorted(set(COMPLETION_CLAIM.findall(body)))
    if not claims:
        return Check("completion_evidence", "PASS", "PR 描述里没有“已完成”类的断言")
    if COMMIT_ID.search(body) or "未核实" in body:
        return Check("completion_evidence", "PASS", "断言“" + "、".join(claims) + "”附了提交号或写明未核实")
    return Check(
        "completion_evidence",
        "WARN",
        "PR 描述写了“" + "、".join(claims) + "”，但没有提交号（7 位以上十六进制）也没有“未核实”字样（FIX-001 第 3 条），审计者需在报告里点名",
    )


def scan_encoding(files: list[str], head: str, cwd: str | None = None) -> Check:
    """PR 改动的文本文件必须是严格 UTF-8、没有乱码（审计 368）；坏字节在这里判 FAIL，不被 errors=replace 抹掉。"""
    import encoding_check

    try:
        findings, skipped = encoding_check.check(Path(cwd or "."), head, files, encoding_check.load_allowlist())
    except encoding_check.GitError as exc:
        return Check("text_encoding", "UNVERIFIED", f"取不到文件内容：{exc}")
    scanned = sum(1 for f in files if encoding_check.is_text_path(f))
    if findings:
        detail = "; ".join(f"{f.path}:{f.line} {f.reason}" for f in findings[:5]) + ("…" if len(findings) > 5 else "")
        return Check("text_encoding", "FAIL", f"{len(findings)} 个文件不是干净的 UTF-8 文本：{detail}")
    return Check("text_encoding", "PASS", f"{scanned} 个文本文件严格 UTF-8 解码通过，无乱码特征（登记在案的已知问题 {len(skipped)} 个）")


def audit(
    pr: int,
    *,
    repo: str,
    remote: str,
    patch: str | None,
    patch_base: str | None,
    network: bool,
    ci_result: bool = True,
    fetch: bool = True,
    cwd: str | None = None,
) -> tuple[dict, list[Check]]:
    if fetch:
        git("fetch", "-q", remote, "main", f"+refs/pull/{pr}/head:refs/audit/pr-{pr}", cwd=cwd)
    else:
        for ref in (f"refs/audit/pr-{pr}", f"{remote}/main"):
            if not git_ok("rev-parse", "--verify", "-q", f"{ref}^{{commit}}", cwd=cwd):
                raise GitError(f"离线模式不取远程，但本地没有 {ref}；联网时先不带 --offline 运行一次")
    main_ref = f"{remote}/main"
    head = git("rev-parse", f"refs/audit/pr-{pr}", cwd=cwd).strip()
    main = git("rev-parse", main_ref, cwd=cwd).strip()
    info = {"pr": pr, "head": head, "main": main}
    checks: list[Check] = []
    if not fetch:
        checks.append(Check("local_refs", "UNVERIFIED", "离线模式：PR 头和 main 取自本地已有的引用，可能不是最新；联网时不带 --offline 重跑"))

    meta = github_json(f"{repo}/pulls/{pr}") if network else None
    pr_base = None
    pr_body: str | None = None
    if meta:
        info["title"] = meta.get("title")
        pr_body = meta.get("body") or ""
        state = "merged" if meta.get("merged_at") else meta.get("state", "unknown")
        pr_base = (meta.get("base") or {}).get("sha")
    else:
        state = "unknown"

    found = find_merge_commit(head, main_ref, cwd=cwd)
    # Without a merge commit the head can still be on main: a fast-forward, or carried in by another merge.
    on_main = not found and git_ok("merge-base", "--is-ancestor", head, main_ref, cwd=cwd)
    if found or on_main:
        state = "merged"
    info["state"] = state
    checks.append(scan_completion_evidence(pr_body))

    base: str | None = main
    if state == "merged":
        if on_main:
            first_line = head in git("rev-list", "--first-parent", main_ref, cwd=cwd).split()
            how = "用了快进合并" if first_line else "PR 的提交随别的合并一起进了 main"
            checks.append(
                Check("merge_shape", "WARN", f"PR 头部 {short(head)} 已在 main 上，但没有合并提交（{how}），需要在报告里写明")
            )
            # The diff is measured from the PR's own base; GitHub reports it, offline it is unknown.
            first_parent = pr_base if pr_base and git_ok("merge-base", "--is-ancestor", pr_base, head, cwd=cwd) else None
            if first_parent is None:
                base = None
        elif not found:
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
        if base is not None:
            base = first_parent or main
    else:
        clean, detail = merge_result_tree(main, head, cwd=cwd)
        checks.append(
            Check("mergeable", "PASS" if clean else "FAIL", "和当前 main 合并无冲突" if clean else f"和当前 main 冲突：{detail}")
        )
        if git_ok("merge-base", "--is-ancestor", main, head, cwd=cwd):
            checks.append(Check("up_to_date", "PASS", "PR 已包含当前 main"))
        else:
            checks.append(Check("up_to_date", "INFO", "PR 不包含当前 main 的全部提交（无冲突时不影响合并）"))
    info["base"] = base

    if base is None:
        info["files"] = []
        expected_ci = True
        checks.append(
            Check(
                "scope", "UNVERIFIED", "快进合并的 PR，离线时不知道它原来的基线；文件范围、个人信息和 CI 路径检查没做，请联网重跑"
            )
        )
    else:
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
        checks.append(scan_encoding(files, head, cwd=cwd))

        patterns = ci_path_patterns(head, cwd=cwd)
        expected_ci = True if patterns is None else any(path_matches(f, p) for f in files for p in patterns)
        checks.append(
            Check(
                "ci_expected",
                "INFO",
                "改到 CI 关心的路径，应当跑 CI" if expected_ci else "只改了 CI 不关心的路径（paths 过滤），不会触发 CI",
            )
        )

    if not ci_result:
        checks.append(Check("ci_result", "INFO", "按 --skip-ci-result 跳过（在 CI 里运行时，CI 本身的结论由必需检查负责）"))
    elif network:
        shas = [head] + ([info["merge"]] if "merge" in info else [])
        runs: list[dict] | None = []
        check_runs: list[dict] | None = []
        statuses: list[dict] | None = []
        for sha in shas:
            data = github_json(f"{repo}/actions/runs?head_sha={sha}&per_page=20")
            runs = None if data is None or runs is None else runs + data.get("workflow_runs", [])
            data = github_json(f"{repo}/commits/{sha}/check-runs?per_page=100")
            check_runs = None if data is None or check_runs is None else check_runs + data.get("check_runs", [])
            # Commit statuses are a separate API from Actions runs: `safety-zone` is reported only there.
            data = github_json(f"{repo}/commits/{sha}/status?per_page=100")
            statuses = None if data is None or statuses is None else statuses + data.get("statuses", [])
        if runs is None or check_runs is None or statuses is None:
            checks.append(Check("ci_result", "UNVERIFIED", "取不到 GitHub 的 Actions、检查项或提交状态记录（网络或限流）"))
        else:
            status, summary = judge_ci(runs, check_runs, statuses, expected_ci)
            checks.append(Check("ci_result", status, summary))
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
    parser.add_argument("--offline", action="store_true", help="不访问网络：不查 GitHub 接口，也不 git fetch（要求本地已有 refs/audit/pr-N 和 <remote>/main）")
    parser.add_argument("--skip-ci-result", action="store_true", help="不查 CI 结论（在 CI 里运行时使用）")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)
    try:
        info, checks = audit(
            args.pr,
            repo=args.repo,
            remote=args.remote,
            patch=args.patch,
            patch_base=args.patch_base,
            network=not args.offline,
            fetch=not args.offline,
            ci_result=not args.skip_ci_result,
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
