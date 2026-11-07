"""PR 撞车检查（GitHub Actions 的 gate 任务调用，D-101）：两个开着的 PR 不能改同一批文件；PR 必须先订卡再改代码。

为什么要有：云端会话用 GitHub 工具直接开 PR，不走 ``pm pr open``，本机的领卡占位闸门管不到它们。这里把同一批判断
搬到 GitHub 上，裁判取自 PR 基线（main），PR 改不了它；本脚本只用标准库，不读 PR 头里的任何文件。

两项判定（任何一项不通过即退出 1）：

A. **范围重叠**：本 PR 的范围（``可改范围`` 清单，加上它实际改到的文件）和**编号比它小**的其它开着的 PR（含草稿）的范围
   （同样取清单加实际改动）有重叠，就报红并点名撞了哪个 PR、哪些路径。只让后来的 PR 等先来的，避免两边互相红死；先来的
   PR 合并或关闭后，后来的在下一次事件（推送、改描述）重新判定。确需并行的，在描述里写 ``重叠放行: #<编号> <理由>``，
   检查改为在报告里点名，不报红；放行是自报的，由独立审计核对理由。
B. **先订卡再改代码**：描述里要有一行 ``领卡占位: <卡号>``；远程要有分支 ``claims/<卡号>``，它的占位提交里记的领卡时间
   不晚于本 PR 最早的提交；占位在那一刻是有效的（没有被收回，没有已放下，租期没有过）；本 PR 的 ``可改范围``
   每一条和**实际改到的每个文件**都落在占位登记的路径里；同一张卡不能被编号更小的、开着的 PR 同时引用。
   A、B 都只对 ``CLAIM_ENFORCE_FROM`` 之后创建的 PR 强制，之前已开着的 PR 只在报告里提示（不把存量 PR 一夜打红）。
   占位的持有者记在占位里，但 GitHub 上所有 agent 用同一个账号开 PR，查不出“是不是自己的卡”，这一项没有判定。

读不到 GitHub 的回答就不放行（失败关闭）：重跑检查即可。令牌只需 ``pull-requests: read``，不写任何东西。

用法（CI 里；PR 描述只经环境变量 ``PR_BODY`` 进入）::

    PR_BODY=... GITHUB_TOKEN=... python reviews/tools/pr_overlap_check.py --ci --repo owner/name --pr 123

退出码：0 通过；1 撞车或没订卡；2 用法或网络出错。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pr_scope_check import declared_scope, normalized

API = "https://api.github.com"
TIMEOUT_SECONDS = 30
CLAIM_LINE = re.compile(r"^\s*领卡占位\s*[:：]\s*`?([A-Za-z0-9][A-Za-z0-9._-]{0,62})`?\s*$", re.MULTILINE)
WAIVER_LINE = re.compile(r"^\s*重叠放行\s*[:：]\s*#(\d+)\s+(\S.*?)\s*$", re.MULTILINE)
CLAIM_REF_PREFIX = "claims/"

Fetch = Callable[[str], object]


class ApiError(RuntimeError):
    """GitHub 没有给出可用的回答（网络、权限、限流）；不放行。"""


class NotFound(ApiError):
    pass


@dataclass
class Result:
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors


def make_fetch(token: str) -> Fetch:
    def fetch(path: str) -> object:
        request = urllib.request.Request(
            f"{API}{path}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
        )
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise NotFound(path) from error
            raise ApiError(f"GitHub 回了 {error.code}：{path}") from error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as error:
            raise ApiError(f"读不到 GitHub：{path}（{error}）") from error

    return fetch


def paged(fetch: Fetch, path: str) -> list[dict[str, object]]:
    """GitHub 列表接口翻页取全（每页 100，最多 30 页；还不够就当出错，不静默截断）。"""

    items: list[dict[str, object]] = []
    separator = "&" if "?" in path else "?"
    for page in range(1, 31):
        chunk = fetch(f"{path}{separator}per_page=100&page={page}")
        if not isinstance(chunk, list):
            raise ApiError(f"GitHub 回的不是列表：{path}")
        items.extend(item for item in chunk if isinstance(item, dict))
        if len(chunk) < 100:
            return items
    raise ApiError(f"{path} 超过 3000 项，不再翻页")


def overlap(first: Sequence[str], second: Sequence[str]) -> list[str]:
    """两组路径的重叠：相等，或一个在另一个的目录下；返回较具体的那个路径，去重排序。"""

    hits: set[str] = set()
    for a in first:
        for b in second:
            if a == b or b.startswith(a + "/"):
                hits.add(b)
            elif a.startswith(b + "/"):
                hits.add(a)
    return sorted(hits)


def scope_paths(body: str, changed: Sequence[str]) -> list[str]:
    """一个 PR 的范围：描述里 ``可改范围`` 清单里的路径，加上它实际改到的文件。"""

    declared = [path for entry in declared_scope(body) if (path := normalized(entry)) is not None]
    return sorted({*declared, *changed})


def changed_files(fetch: Fetch, repo: str, number: int) -> list[str]:
    return sorted(str(item["filename"]) for item in paged(fetch, f"/repos/{repo}/pulls/{number}/files") if "filename" in item)


def check_overlap(fetch: Fetch, repo: str, number: int, body: str, result: Result, *, enforced: bool = True) -> None:
    mine = scope_paths(body, changed_files(fetch, repo, number))
    waivers = {int(match.group(1)): match.group(2) for match in WAIVER_LINE.finditer(body)}
    for other in paged(fetch, f"/repos/{repo}/pulls?state=open&base=main"):
        other_number = other.get("number")
        if not isinstance(other_number, int) or other_number >= number:
            continue  # 只让编号更大的（后来的）PR 等先来的
        other_body = str(other.get("body") or "")
        theirs = scope_paths(other_body, changed_files(fetch, repo, other_number))
        hits = overlap(mine, theirs)
        if not hits:
            continue
        shown = "、".join(f"`{path}`" for path in hits[:8]) + ("…" if len(hits) > 8 else "")
        title = str(other.get("title") or "")
        draft = "（草稿）" if other.get("draft") else ""
        if not enforced:
            result.notes.append(f"与更早开着的 #{other_number}{draft}《{title}》范围重叠：{shown}（本 PR 创建于强制起点之前，只提示）")
            continue
        if other_number in waivers:
            result.notes.append(f"与 #{other_number}{draft} 范围重叠：{shown}；已按描述放行，理由：{waivers[other_number]}（审计要核对）")
            continue
        result.errors.append(
            f"范围撞车：与更早开着的 PR #{other_number}{draft}《{title}》都要改 {shown}。"
            f"等 #{other_number} 合并或关闭后再推一次；确需并行就在描述里写 `重叠放行: #{other_number} <理由>`"
        )


def claim_payload(fetch: Fetch, repo: str, card: str) -> dict[str, object]:
    ref = fetch(f"/repos/{repo}/git/ref/heads/{CLAIM_REF_PREFIX}{card}")
    sha = ref.get("object", {}).get("sha") if isinstance(ref, dict) and isinstance(ref.get("object"), dict) else None
    if not isinstance(sha, str):
        raise ApiError(f"claims/{card} 的引用格式不对")
    commit = fetch(f"/repos/{repo}/git/commits/{sha}")
    message = str(commit.get("message", "")) if isinstance(commit, dict) else ""
    try:
        payload = json.loads(message.split("\n", 1)[1]) if "\n" in message else {}
    except json.JSONDecodeError:
        payload = {}
    return payload if isinstance(payload, dict) else {}


def earliest_commit_time(fetch: Fetch, repo: str, number: int) -> str:
    stamps: list[str] = []
    for item in paged(fetch, f"/repos/{repo}/pulls/{number}/commits"):
        commit = item.get("commit")
        committer = commit.get("committer") if isinstance(commit, dict) else None
        date = committer.get("date") if isinstance(committer, dict) else None
        if isinstance(date, str):
            stamps.append(date)
    return min(stamps) if stamps else ""


def referenced_cards(body: str) -> set[str]:
    return {match.group(1) for match in CLAIM_LINE.finditer(body)}


def check_claim(fetch: Fetch, repo: str, number: int, body: str, created_at: str, enforce_from: str, result: Result) -> None:
    enforced = is_enforced(created_at, enforce_from)
    problems: list[str] = []
    match = CLAIM_LINE.search(body)
    if match is None:
        problems.append("描述里没有 `领卡占位: <卡号>` 一行：开工先 `main.py claim list` 看占位表，再 `main.py claim open <卡号> --paths … --goal …` 订卡，订上才改代码")
    else:
        card = match.group(1)
        try:
            payload = claim_payload(fetch, repo, card)
        except NotFound:
            problems.append(f"远程没有 `claims/{card}`：先订卡再开 PR（`main.py claim open {card} --paths … --goal …`）")
        else:
            problems.extend(claim_problems(fetch, repo, number, body, card, payload))
            for other in paged(fetch, f"/repos/{repo}/pulls?state=open&base=main"):
                other_number = other.get("number")
                if isinstance(other_number, int) and other_number < number and card in referenced_cards(str(other.get("body") or "")):
                    problems.append(f"卡 {card} 已被更早开着的 PR #{other_number} 引用：一张卡一个 PR，另订一张卡")
    if enforced:
        result.errors.extend(problems)
    else:
        result.notes.extend(f"领卡检查（本 PR 创建于 {created_at or '未知'}，早于强制起点 {enforce_from or '未设'}，只提示）：{item}" for item in problems)


def claim_problems(fetch: Fetch, repo: str, number: int, body: str, card: str, payload: dict[str, object]) -> list[str]:
    problems: list[str] = []
    claimed_at = str(payload.get("claimed_at", ""))
    first = earliest_commit_time(fetch, repo, number)
    status = str(payload.get("status", ""))
    if status == "reclaimed":
        problems.append(f"卡 {card} 的占位已被收回（{payload.get('reclaimed_reason', '无原因')}）：重新订卡")
    elif status == "released" and first and str(payload.get("released_at", "")) <= first:
        problems.append(f"卡 {card} 的占位在本 PR 最早的提交（{first}）之前就已放下：重新订卡")
    expires_at = str(payload.get("expires_at", ""))
    if first and expires_at and expires_at < first:
        problems.append(f"卡 {card} 的占位在 {expires_at} 就到期了，早于本 PR 最早的提交（{first}）：占位无效时改了代码，重新订卡并续租")
    if not claimed_at:
        problems.append(f"`claims/{card}` 里读不到领卡时间")
    elif first and claimed_at > first:
        problems.append(f"先改代码后订卡：卡 {card} 订于 {claimed_at}，本 PR 最早的提交在 {first}")
    claimed = [path for item in payload.get("paths", []) if isinstance(item, str) and (path := normalized(item)) is not None]

    def covered(path: str) -> bool:
        return any(path == c or path.startswith(c + "/") for c in claimed)

    declared = [path for entry in declared_scope(body) if (path := normalized(entry)) is not None]
    for path in declared:
        if not covered(path):
            problems.append(f"可改范围里的 `{path}` 不在卡 {card} 订的路径里：补订或收窄范围")
    for path in changed_files(fetch, repo, number):
        if not covered(path) and path not in declared:
            problems.append(f"实际改到的 `{path}` 不在卡 {card} 订的路径里：补订或收窄范围")
    return problems


def is_enforced(created_at: str, enforce_from: str) -> bool:
    return bool(enforce_from) and created_at >= enforce_from


def check(fetch: Fetch, repo: str, number: int, body: str, enforce_from: str) -> Result:
    result = Result()
    pr = fetch(f"/repos/{repo}/pulls/{number}")
    created_at = str(pr.get("created_at", "")) if isinstance(pr, dict) else ""
    check_overlap(fetch, repo, number, body, result, enforced=is_enforced(created_at, enforce_from))
    check_claim(fetch, repo, number, body, created_at, enforce_from, result)
    return result


def render(result: Result) -> str:
    lines = ["## PR 撞车与领卡检查", "", "**结论：通过**" if result.passed else "**结论：不通过**"]
    lines += [f"- ❌ {item}" for item in result.errors]
    lines += [f"- ℹ️ {item}" for item in result.notes]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PR 撞车与领卡检查（只读）")
    parser.add_argument("--repo", required=True, help="owner/name")
    parser.add_argument("--pr", required=True, type=int)
    parser.add_argument("--ci", action="store_true", help="CI 模式：必须有令牌")
    args = parser.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN", "")
    if args.ci and not token:
        print("拒绝运行：CI 模式需要 GITHUB_TOKEN", file=sys.stderr)
        return 2
    body = os.environ.get("PR_BODY", "")
    enforce_from = os.environ.get("CLAIM_ENFORCE_FROM", "")
    try:
        result = check(make_fetch(token), args.repo, args.pr, body, enforce_from)
    except ApiError as error:
        print(f"读不到 GitHub，不放行：{error}", file=sys.stderr)
        return 2
    report = render(result)
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(report)
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
