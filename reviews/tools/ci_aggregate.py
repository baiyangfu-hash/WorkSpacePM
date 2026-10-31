"""汇总检查：按 PR 改动的路径算出哪些 CI 工作流该跑，等它们结束，缺了或红了就判不通过。

为什么要有它：sw008-ci、plc-ci 等工作流按路径过滤，该跑的 PR 也可能没触发（#294 就是），而按路径过滤的作业
不能设成 main 的必过检查（没触发就永远等不到）。本检查每个 PR 都跑，自己做“该跑什么”的判断，所以可以设必过。

判断全部取自 PR 基线（main）的工作流文件，PR 改不了它：由 ci-aggregate.yml 用 pull_request_target 在基线检出里运行。

规则：
* 只看有 ``pull_request:`` 触发的工作流；``pull_request_target`` 的（pr-gate、safety-gate）本来就每个 PR 必跑、已是必过检查，
  本工作流自己也不算；
* ``pull_request:`` 没有 ``paths:`` → 每个 PR 都该跑；有 ``paths:`` → 改动文件命中其中任一条才该跑；
  写法读不懂（行内列表、``paths-ignore``）一律按“该跑”处理，只会更严；
* 该跑的工作流在 PR 头上必须有运行记录（pull_request 或手动 workflow_dispatch 都算），且最新一次结论是 success/neutral（skipped 不算过）；
  失败、取消 → 不通过；还在跑 → 继续等；一直没出现（超过宽限时间）→ 不通过。
* 取不到 GitHub 的记录（网络、限流）→ 不通过（宁可挡住，也不假绿）。

用法（CI 里）::

    GITHUB_TOKEN=... python -I reviews/tools/ci_aggregate.py --repo owner/name --pr 12 --head <sha> [--workflows .github/workflows]

退出码：0 全部通过；1 有不通过；2 用法错误。只用标准库。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

SELF = "ci-aggregate.yml"
# skipped 不算过：该跑的工作流整体被跳过（配错过滤条件、作业级 if 写错）时，不能当成“跑过且绿”放行（反重力审计 SEC-004，用户授权协调者裁决）。
# 现有 pull_request 工作流都没有作业级 if，没有哪一个会合法地整体 skipped。
PASSING = {"success", "neutral"}
RUN_EVENTS = {"pull_request", "workflow_dispatch"}


@dataclass(frozen=True)
class Trigger:
    """一个工作流在 PR 上的触发规则：``always`` 为真表示每个 PR 都该跑。"""

    workflow: str
    always: bool
    paths: tuple[str, ...] = ()


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def parse_trigger(name: str, text: str) -> Trigger | None:
    """读出工作流的 ``pull_request`` 触发规则；没有这个触发（含只有 pull_request_target）返回 ``None``。"""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip().rstrip(":") == "pull_request" and line.strip().endswith(":")), None)
    # ``pull_request`` 作为独立的词出现（``pull_request_target`` 不算）；``on: [pull_request_target, pull_request]`` 也要认出来
    inline = next((line for line in lines if line.strip().startswith("on:") and re.search(r"\bpull_request\b", line)), None)
    if start is None:
        # ``on: [pull_request, push]`` 之类行内写法：读不懂路径，按每个 PR 都该跑算
        return Trigger(name, True) if inline is not None else None
    base = _indent(lines[start])
    paths: list[str] = []
    section = ""
    always = True
    for line in lines[start + 1 :]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _indent(line) <= base:
            break
        if stripped in ("paths:", "paths-ignore:"):
            section = stripped[:-1]
            if section == "paths-ignore":
                always = True  # 读不懂的写法，按每个 PR 都该跑算
                paths = []
                section = "ignored"
            else:
                always = False
        elif stripped.endswith(":") or ":" in stripped.split(" ")[0]:
            section = ""
        elif section == "paths" and stripped.startswith("- "):
            paths.append(stripped[2:].strip().strip("\"'"))
        elif section == "paths" and stripped.startswith("["):
            return Trigger(name, True)
    if not always and not paths:
        return Trigger(name, True)
    return Trigger(name, always, tuple(paths))


def _glob_regex(pattern: str) -> re.Pattern[str]:
    """GitHub ``paths:`` 通配转正则：``**/`` 可匹配零层目录，``**`` 跨目录，``*`` 和 ``?`` 不跨目录。"""
    out: list[str] = []
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out))


def path_matches(path: str, pattern: str) -> bool:
    return _glob_regex(pattern).fullmatch(path) is not None


def load_triggers(workflows_dir: Path) -> list[Trigger]:
    found: list[Trigger] = []
    for path in sorted(workflows_dir.glob("*.yml")):
        if path.name == SELF:
            continue
        trigger = parse_trigger(path.name, path.read_text(encoding="utf-8"))
        if trigger is not None:
            found.append(trigger)
    return found


def expected_workflows(triggers: list[Trigger], changed: list[str]) -> list[str]:
    return [t.workflow for t in triggers if t.always or any(path_matches(f, p) for f in changed for p in t.paths)]


def judge(expected: list[str], runs: list[dict], *, elapsed: float, grace: float) -> tuple[str, list[str]]:
    """``("pass"|"fail"|"wait", 说明)``；``wait`` 表示还有在跑或还没出现、且没超过宽限。"""
    newest: dict[str, dict] = {}
    for run in runs:
        name = str(run.get("path", "")).split("@")[0].rsplit("/", 1)[-1]
        if name in expected and run.get("event") in RUN_EVENTS and (name not in newest or run["id"] > newest[name]["id"]):
            newest[name] = run
    failed: list[str] = []
    waiting: list[str] = []
    notes: list[str] = []
    for name in expected:
        run = newest.get(name)
        if run is None:
            (failed if elapsed > grace else waiting).append(name)
            notes.append(f"{name}: 没有运行记录")
        elif run.get("status") != "completed":
            waiting.append(name)
            notes.append(f"{name}: 还在跑（{run.get('status')}）")
        elif run.get("conclusion") in PASSING:
            notes.append(f"{name}: {run.get('conclusion')}")
        else:
            failed.append(name)
            notes.append(f"{name}: {run.get('conclusion')}")
    if failed:
        return "fail", notes + ["不通过或缺失：" + "、".join(failed)]
    if waiting:
        return "wait", notes
    return "pass", notes


def github_json(repo: str, path: str, token: str) -> dict | list | None:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/{path}",
        headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None


def changed_files(fetch: Callable[[str], dict | list | None], pr: int) -> list[str] | None:
    files: list[str] = []
    for page in range(1, 31):  # GitHub 最多给 3000 个文件
        data = fetch(f"pulls/{pr}/files?per_page=100&page={page}")
        if not isinstance(data, list):
            return None
        for item in data:
            files.append(item["filename"])
            if item.get("previous_filename"):
                files.append(item["previous_filename"])
        if len(data) < 100:
            return files
    return files


def run(
    triggers: list[Trigger],
    fetch: Callable[[str], dict | list | None],
    pr: int,
    head: str,
    *,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    deadline: float = 100 * 60,
    grace: float = 12 * 60,
    interval: float = 30,
) -> tuple[int, str]:
    changed = changed_files(fetch, pr)
    if changed is None:
        return 1, "取不到 PR 改动文件列表（网络或限流），不能判断该跑哪些检查，按不通过处理"
    expected = expected_workflows(triggers, changed)
    start = clock()
    while True:
        data = fetch(f"actions/runs?head_sha={head}&per_page=100")
        runs = data.get("workflow_runs") if isinstance(data, dict) else None
        elapsed = clock() - start
        if runs is None:
            verdict, notes = ("fail" if elapsed > grace else "wait"), ["取不到运行记录（网络或限流）"]
        else:
            verdict, notes = judge(expected, runs, elapsed=elapsed, grace=grace)
        header = f"该跑的工作流：{', '.join(expected) or '无'}（改动 {len(changed)} 个文件）"
        if verdict == "wait" and elapsed < deadline:
            sleep(interval)
            continue
        if verdict == "wait":
            verdict, notes = "fail", notes + [f"超过 {int(deadline // 60)} 分钟仍未结束"]
        return (0 if verdict == "pass" else 1), "\n".join([header, *notes, "汇总：" + ("通过" if verdict == "pass" else "不通过")])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--workflows", default=".github/workflows")
    args = parser.parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("缺少 GITHUB_TOKEN", file=sys.stderr)
        return 2
    triggers = load_triggers(Path(args.workflows))
    code, report = run(triggers, lambda path: github_json(args.repo, path, token), args.pr, args.head)
    print(report)
    return code


if __name__ == "__main__":
    sys.exit(main())
