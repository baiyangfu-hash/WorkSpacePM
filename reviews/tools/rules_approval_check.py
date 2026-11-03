"""规则文件批准检查：PR 改到规则文件时，必须有用户本人对当前头提交的批准（GitHub Actions 的 rules-gate 调用）。

为什么要有它：仓库里有两个账号能写（用户主账号 Admin、给 Trae 用的第二账号 Write）。main 的规则集只要求检查全绿，
第二账号只要检查绿了就能自己合并改 ``AGENTS.md``、``.trae/``、规范库的 PR，而这几类按规矩必须有用户本人的原话。
本检查把“用户本人批准”变成一道机器门：没有批准，检查报红，合并按钮点不了。

判定：

* 取 PR 相对合并基点改到的全部路径（新增、修改、删除、改名的两端都算）；
* 命中 ``RULE_PATTERNS`` 的路径叫“规则文件”（含工作流和判卷脚本）。一个也没改到 → 通过，不要求任何批准（Trae 的普通 PR 不受影响）；
* 改到了 → PR 评论里必须有一条用户本人写的评论，某一行是 ``规则批准 <PR 当前头提交号，至少 12 位>``。
  只认 ``SIGNERS`` 里的账号（登录名和数字用户 ID 都要对上）；经由 GitHub App 发出的评论不算；提交号不是当前头提交前缀的不算
  （批准完又推新提交，批准自动作废，要重批）；以 ``>`` 开头的引用行、句子中间提到的“规则批准”不算。
* 取不到评论（网络、限流）→ 退出码 2，检查报红，宁可挡住也不假绿。

和 ``safety_zone_check.py`` 的安全签字是两回事：安全签字管 PLC 安全回路，本检查管规则文件；两个用不同的口令行，不能互相顶替。

已知局限：本机 agent 如果用用户已登录的 ``gh`` 命令行代发评论，机器分不出是不是本人（与安全签字同一个漏洞）；
本检查挡的是“第二账号自己合并”，不是“拿到用户登录态的人”。

本脚本不写仓库、不访问网络：PR 评论由工作流用 ``gh api`` 取成 JSON 文件，经 ``--comments`` 传入。

用法（在仓库根执行）::

    python -I reviews/tools/rules_approval_check.py --base <main 当前头> --head <PR 头> --comments <comments.json> [--repo <检出>]

退出码：0 通过；1 不通过（改了规则文件而没有有效批准）；2 用法或 Git/输入出错。只用标准库。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_pr import path_matches

# 规则文件和判卷文件：改它们必须有用户本人的批准。必须是 ``audit_pr.PROTECTED_PATTERNS`` 加 ``pr_scope_check.JUDGE_PATTERNS``
# 里已锁定路径的子集（test_rules_approval_check 钉死），这样锁定清单一份真源，这里只是“其中哪些要用户原话”。
RULE_PATTERNS = (
    "AGENTS.md",
    "CLAUDE.md",
    ".trae/*",
    ".cursor/rules/*",
    ".agent/rules/*",
    ".claude/*",
    ".agents/skills.json",
    "SYS-2026-001_WorkspaceGovernance/approvers.json",
    "00_Obsidian_Base*",
    "roles/*",
    # 判卷本身：改工作流或判卷脚本就能把本检查（和其他门禁）关掉，所以同样要用户本人批准
    ".github/workflows/*",
    "reviews/tools/*",
)
# 能批准的人：GitHub 登录名 → 数字用户 ID（ID 不随改名变化，两个都要对上；与 safety_zone_check.SIGNERS 同一人）
SIGNERS = {"baiyangfu-hash": 246858089}
APPROVE_WORD = "规则批准"
# 至少 12 位（48 位），理由同安全签字（TD-SW008-215）：短前缀可被在 PR 头上反复改内容撞出来，拿批准复用到别的提交。
MIN_SIGN_LEN = 12
APPROVE_LINE = re.compile(rf"^\s*{APPROVE_WORD}\s*[:：]?\s*`?([0-9a-fA-F]{{7,40}})`?(?:\s.*|[，。；：！、）】」』,;.!)\]].*)?$")
GIT_TIMEOUT_SECONDS = 300


class GitError(RuntimeError):
    pass


@dataclass
class Result:
    rule_files: list[str] = field(default_factory=list)
    approval: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.rule_files or self.approval is not None


def is_rule_file(path: str) -> bool:
    return any(path_matches(path, pattern) for pattern in RULE_PATTERNS)


def git(repo: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", "-c", "core.quotepath=false", *args],
            cwd=str(repo),
            capture_output=True,
            check=False,
            stdin=subprocess.DEVNULL,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise GitError(f"git {' '.join(args[:4])} 超过 {GIT_TIMEOUT_SECONDS} 秒没有返回") from error
    if result.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {result.stderr.decode('utf-8', errors='replace').strip()}")
    return result.stdout


def changed_files(repo: Path, base: str, head: str) -> list[str]:
    """PR 相对合并基点改到的全部路径；改名的新旧两端都算（把规则文件改名搬走也是改它）。"""

    raw = git(repo, "diff", "--name-only", "--no-renames", "-z", f"{base}...{head}")
    # 路径按字节取，再宽松解码：非 UTF-8 文件名也不会让某个路径逃出判断
    return sorted({item.decode("utf-8", errors="replace") for item in raw.split(b"\0") if item})  # lenient-decode: 文件名只用于匹配和显示


def flatten_comments(data: Any) -> list[dict[str, Any]]:
    """``gh api --paginate --slurp`` 给出“页的列表”；单页的列表、本地手写的列表也认。"""

    if not isinstance(data, list):
        raise ValueError("评论文件应是 JSON 列表")
    comments: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, list):
            comments.extend(c for c in item if isinstance(c, dict))
        elif isinstance(item, dict):
            comments.append(item)
    return comments


def find_approval(comments: list[dict[str, Any]], head_sha: str, result: Result) -> str | None:
    head_sha = head_sha.lower()
    for comment in comments:
        body = str(comment.get("body") or "")
        shas = [m.group(1).lower() for m in (APPROVE_LINE.match(line) for line in body.splitlines()) if m]
        if not shas:
            continue
        where = f"评论 {comment.get('html_url') or comment.get('id')}"
        long_enough = [sha for sha in shas if len(sha) >= MIN_SIGN_LEN]
        if not long_enough:
            result.notes.append(f"{where}：批准 {', '.join(shas)} 不足 {MIN_SIGN_LEN} 位，不认；请写 `{APPROVE_WORD} {head_sha[:MIN_SIGN_LEN]}`")
            continue
        user = comment.get("user") or {}
        login, uid = user.get("login"), user.get("id")
        where = f"{where}（{login}）"
        if login not in SIGNERS or SIGNERS[login] != uid:
            result.notes.append(f"{where}：不是指定批准人，不算")
            continue
        if comment.get("performed_via_github_app"):
            app = (comment["performed_via_github_app"] or {}).get("slug", "某个 App")
            result.notes.append(f"{where}：经由 GitHub App `{app}` 发出，不是本人手写，不算")
            continue
        if not any(head_sha.startswith(sha) for sha in long_enough):
            result.notes.append(f"{where}：批准的是 {', '.join(long_enough)}，不是当前头提交 {head_sha[:12]}（批准后又推过提交），要重批")
            continue
        return f"{where}，批准 {head_sha[:12]}"
    return None


def judge(files: list[str], comments: list[dict[str, Any]], head_sha: str) -> Result:
    result = Result(rule_files=[f for f in files if is_rule_file(f)])
    if result.rule_files:
        result.approval = find_approval(comments, head_sha, result)
    return result


def render(result: Result, head_sha: str) -> str:
    lines: list[str] = []
    if not result.rule_files:
        lines.append("通过：这个 PR 没有改规则文件，不需要用户批准。")
    elif result.approval:
        lines.append(f"通过：改了 {len(result.rule_files)} 个规则文件，有用户本人的批准：{result.approval}")
    else:
        lines.append(f"不通过：这个 PR 改了 {len(result.rule_files)} 个规则文件，但 PR 评论里没有用户本人对当前头提交的批准。")
        lines.append(f"用户请在本 PR 页面评论一行：`{APPROVE_WORD} {head_sha[:MIN_SIGN_LEN]}`（评论后检查会自动重跑；之后再推新提交，要重批）。")
    if result.rule_files:
        lines.append("规则文件：")
        lines.extend(f"- `{f}`" for f in result.rule_files)
    lines.extend(f"注：{note}" for note in result.notes)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", required=True, help="main 当前头（裁判）")
    parser.add_argument("--head", required=True, help="PR 头提交（完整 40 位）")
    parser.add_argument("--comments", required=True, help="PR 评论 JSON 文件（gh api --paginate --slurp 的输出）")
    parser.add_argument("--repo", default=".", help="用来取 diff 的检出（只读 git 对象，默认当前目录）")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[0-9a-fA-F]{40}", args.head):
        print("出错：--head 必须是完整的 40 位提交号", file=sys.stderr)
        return 2
    try:
        comments = flatten_comments(json.loads(Path(args.comments).read_text(encoding="utf-8")))
        files = changed_files(Path(args.repo), args.base, args.head)
    except (OSError, ValueError, GitError) as error:
        print(f"出错：{error}", file=sys.stderr)
        return 2
    result = judge(files, comments, args.head)
    print(render(result, args.head))
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
