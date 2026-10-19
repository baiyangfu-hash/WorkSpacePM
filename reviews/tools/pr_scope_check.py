"""PR 越界检查：一个 PR 改到的文件是否都在它被允许的范围里（GitHub Actions 的 gate 任务调用）。

范围从哪里来（按顺序）：

1. PR 描述里的一行 ``任务卡: <工作区相对路径>``：读 **PR 基线（base）上的那份卡**，用驾驶舱的
   ``precheck_markdown_card`` 解析其中“路径 / 基线状态”表，所以 PR 不能靠改卡给自己扩大范围；
2. 没有任务卡时，读 PR 描述里的 ``可改范围`` 清单（每行 ``- 路径``），结果标为“自报”。

判定（任何一项不通过即退出 1）：

* 每个改到的文件（新增、修改、删除、改名的两端）都等于某个允许路径或在其目录下（复用 ``scopes_outside_card``）；
* 落在锁定清单里的文件，必须在范围里**逐字写出完整路径**，目录前缀不算授权。锁定清单是
  ``reviews/tools/audit_pr.py`` 的 ``PROTECTED_PATTERNS`` 加上裁判自己的文件（``JUDGE_PATTERNS``：本脚本、它导入的
  驾驶舱代码、安装依赖用的文件），所以 PR 改裁判、改配置、改依赖都要被点名；
* PR 改到的 PLC 文件，用提交前钩子同一套 ``enforce_plc_docs`` 核对文档与代码一致性。

不做的事：不读也不验 CHG 单与台账（CHG 文件只在本机控制根上，CI 里查必然失败）；不写仓库，不访问网络。
PR 描述从环境变量 ``PR_BODY`` 读入，不进入任何命令行。

用法（在仓库根执行）::

    PR_BODY="..." python reviews/tools/pr_scope_check.py --base <base sha> --head <head sha> [--repo <被检查的检出>]

``--repo`` 默认是脚本所在的仓库。CI 里裁判（本脚本、它读取的配置、安装依赖用的文件）一律取自 PR 基线的检出，
``--repo`` 指向 PR 头部的另一份检出，PR 头里的东西只当被检查对象读取、从不导入或执行；``--ci`` 要求两者不是同一份检出。

退出码：0 通过；1 越界或检查不通过；2 用法或 Git 出错。
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

TOOL_ROOT = Path(__file__).resolve().parents[2]
SW008_ROOT = (
    TOOL_ROOT / "01_Project自动化项目管理" / "Python自动化项目总库" / "02_在研项目" / "SW-2026-008_auto-pm_自动化项目管理工具"
)
for _entry in (Path(__file__).resolve().parent, SW008_ROOT / "auto_pm", SW008_ROOT):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from audit_pr import PROTECTED_PATTERNS, path_matches
from auto_pm.application.core.implementation_card_precheck import (
    CardPath,
    PrecheckReport,
    precheck_markdown_card,
    scopes_outside_card,
)

CARD_LINE = re.compile(r"^\s*任务卡\s*[:：]\s*`?([^`\s]+)`?\s*$")
SCOPE_HEADER = re.compile(r"^\s*(?:#+\s*)?可改范围\s*[:：]?\s*$")
SCOPE_ITEM = re.compile(r"^\s*[-*]\s+`?([^`\s]+)`?")
# 裁判自己的文件：改它们等于改判卷规则，必须逐字点名（与 PROTECTED_PATTERNS 一样处理）
_SW008 = "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具"
JUDGE_PATTERNS = (
    "reviews/tools/pr_scope_check.py",
    "reviews/tools/audit_pr.py",
    "requirements.txt",
    f"{_SW008}/pyproject.toml",
    f"{_SW008}/auto_pm/**",
)
# 只有这些规则关乎“范围”；命令、审批占位等属于卡的生命周期，不在本检查判定
SCOPE_RULES = frozenset({"header", "path_table"})


class GitError(RuntimeError):
    pass


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def changed_files(repo: Path, base: str, head: str) -> list[str]:
    """PR 相对合并基点改到的全部路径；改名的新旧两端都算。"""

    raw = git(repo, "diff", "--name-only", "--no-renames", "-z", f"{base}...{head}")
    return sorted({item for item in raw.split("\0") if item})


def normalized(path: str) -> str | None:
    candidate = path.strip().replace("\\", "/").rstrip("/")
    while candidate.startswith("./"):
        candidate = candidate[2:]
    parts = PurePosixPath(candidate).parts
    if not candidate or candidate.startswith("/") or ".." in parts or re.match(r"^[A-Za-z]:", candidate):
        return None
    return "/".join(parts)


def is_protected(path: str) -> bool:
    """锁定文件：audit_pr.py 的 protected_paths 判定，再加裁判自己的文件。"""

    name = PurePosixPath(path).name
    if any(path_matches(path, p) for p in JUDGE_PATTERNS):
        return True
    return any(path_matches(path, p) or fnmatch.fnmatchcase(name, p) for p in PROTECTED_PATTERNS)


def card_path_from_body(body: str) -> str | None:
    for line in body.splitlines():
        match = CARD_LINE.match(line)
        if match:
            return match.group(1)
    return None


def declared_scope(body: str) -> list[str]:
    """PR 描述里 ``可改范围`` 标题下的清单项；遇到空行（已有清单项之后）或下一个标题即结束。"""

    items: list[str] = []
    inside = False
    for line in body.splitlines():
        if SCOPE_HEADER.match(line):
            inside = True
            continue
        if not inside:
            continue
        if line.lstrip().startswith("#") or (not line.strip() and items):
            break
        match = SCOPE_ITEM.match(line)
        if match:
            items.append(match.group(1))
    return items


@dataclass
class Result:
    source: str = ""
    allowed: tuple[str, ...] = ()
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors


def scope_from_card(repo: Path, card: str, base: str, result: Result) -> PrecheckReport | None:
    """读 PR 基线上的卡（不是 PR 里改过的那份），用驾驶舱的卡片预检解析路径表。"""

    try:
        content = git(repo, "show", f"{base}:{card}")
    except GitError:
        result.errors.append(f"任务卡 `{card}` 在 PR 基线 {base[:8]} 上不存在：卡要先合入 main，范围才算数")
        return None
    with tempfile.TemporaryDirectory(prefix="pr_scope_") as tmp:
        copy = Path(tmp) / PurePosixPath(card).name
        copy.write_text(content, encoding="utf-8")
        report = precheck_markdown_card(copy, workspace_root=repo, command_tree={})
    for finding in report.findings:
        if finding.rule in SCOPE_RULES:
            result.errors.append(f"任务卡路径表不合格：[{finding.rule}] {finding.subject}: {finding.message}")
        else:
            result.notes.append(f"任务卡预检（不影响本检查）：[{finding.rule}] {finding.subject}: {finding.message}")
    if not report.paths:
        result.errors.append(f"任务卡 `{card}` 没有列出任何路径")
    return report


def scope_from_body(body: str, result: Result) -> PrecheckReport | None:
    entries = declared_scope(body)
    if not entries:
        result.errors.append("PR 描述里既没有 `任务卡: <路径>` 一行，也没有 `可改范围` 清单，无法判断范围")
        return None
    paths: list[CardPath] = []
    for entry in entries:
        path = normalized(entry)
        if path is None:
            result.errors.append(f"可改范围里的路径必须是仓库内的相对路径：{entry}")
            continue
        paths.append(CardPath(path, "自报"))
    return PrecheckReport("PR 描述", "", "", ".", tuple(paths), (), ())


def check(repo: Path, base: str, head: str, body: str) -> Result:
    result = Result()
    card = card_path_from_body(body)
    if card is not None:
        card_normalized = normalized(card)
        if card_normalized is None:
            result.errors.append(f"任务卡路径必须是仓库内的相对路径：{card}")
            return result
        result.source = f"任务卡 `{card_normalized}`（取 PR 基线上的版本）"
        report = scope_from_card(repo, card_normalized, base, result)
    else:
        card_normalized = None
        result.source = "PR 描述里的 `可改范围`（自报，没有任务卡）"
        report = scope_from_body(body, result)
    if report is None:
        return result
    result.allowed = tuple(item.path for item in report.paths)

    files = changed_files(repo, base, head)
    exact = set(result.allowed)
    in_scope = [f for f in files if f != card_normalized]
    if card_normalized in files:
        result.notes.append(f"PR 改了任务卡本身 `{card_normalized}`：允许，但范围仍按基线上的版本判定")
    for path in scopes_outside_card(in_scope, report):
        result.errors.append(f"越界：`{path}` 不在允许范围内")
    for path in in_scope:
        if is_protected(path) and path not in exact:
            result.errors.append(f"锁定文件 `{path}` 必须在范围里逐字写出完整路径（目录前缀不算授权）")

    plc_code = plc_docs(repo, files)
    if plc_code != 0:
        result.errors.append("PLC 文档与代码一致性检查未通过（详见上面的输出）")
    return result


def plc_docs(repo: Path, files: list[str]) -> int:
    """提交前钩子的 PLC 文档门禁；CI 检出的是 PR 内容，暂存区与它一致，只看仍存在的文件。"""

    from auto_pm.infrastructure.plc_doc_hook import enforce_plc_docs

    present = [f for f in files if (repo / f).is_file()]
    return enforce_plc_docs(repo, present)


def render(result: Result, files: list[str]) -> str:
    lines = ["## PR 越界检查", "", f"- 范围来源：{result.source or '（无）'}", f"- 改到的文件：{len(files)} 个"]
    lines.append(f"- 允许的路径：{len(result.allowed)} 条")
    lines += [f"  - `{p}`" for p in result.allowed[:50]]
    if len(result.allowed) > 50:
        lines.append(f"  - …（另有 {len(result.allowed) - 50} 条）")
    lines.append("")
    lines.append("**结论：通过**" if result.passed else "**结论：不通过**")
    lines += [f"- ❌ {e}" for e in result.errors]
    lines += [f"- ℹ️ {n}" for n in result.notes]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PR 越界检查（只读）")
    parser.add_argument("--base", required=True, help="PR 基线提交（base.sha）")
    parser.add_argument("--head", required=True, help="PR 头部提交（head.sha）")
    parser.add_argument("--repo", type=Path, default=TOOL_ROOT, help="被检查的仓库检出（默认：脚本所在仓库）")
    parser.add_argument("--ci", action="store_true", help="CI 模式：裁判与被检查对象必须是两份不同的检出")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    if args.ci and (repo == TOOL_ROOT or TOOL_ROOT.is_relative_to(repo) or repo.is_relative_to(TOOL_ROOT)):
        print(f"拒绝运行：裁判 {TOOL_ROOT} 与被检查的检出 {repo} 必须分开（裁判取自 PR 基线）", file=sys.stderr)
        return 2
    body = os.environ.get("PR_BODY", "")
    try:
        result = check(repo, args.base, args.head, body)
        files = changed_files(repo, args.base, args.head)
    except GitError as error:
        print(f"git 出错：{error}", file=sys.stderr)
        return 2
    report = render(result, files)
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8", errors="replace") as handle:
            handle.write(report)
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
