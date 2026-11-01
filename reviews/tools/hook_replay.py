"""hook_replay.py - 把本机提交钩子的“生产代码提交必须绑定变更单”检查在 PR 上复跑一遍（盘点 P1-2，方案 plans/P1-2_钩子进CI复跑方案_20261029.md）。

为什么要有：本机 ``commit-msg`` 钩子会拒绝没有绑定变更单的生产代码提交，但 ``git commit --no-verify`` 一个参数就能绕过，
换一台没装钩子的电脑（云端、Trae）也没人拦。这里在服务器上把同一套规则对 PR 里的每个提交复跑一次。

判什么（与 ``auto_pm.infrastructure.git_hook_enforcer.enforce_commit_msg`` 同一套函数，不另写一份）：
* 提交里有生产代码文件（``.py/.scl/.st/.qml``，测试、文档、规范库等豁免，同钩子）时：
  1. 提交说明里有且只有一个变更单号 ``CHG-…``；
  2. 这些生产文件归属唯一一个注册项目；
  3. 该变更单文件存在、写的项目编号与归属一致、状态是合法执行态；
  4. 该项目的版本变更台账里出现这个变更单号。
* 合并提交不查（它自己没有新代码，代码在被合并的提交里）。
* 云端 PR 的提交说明常常不写变更单号（用户 2026-11-01 裁决：认 PR 描述）：提交说明里没有单号时，退而看 PR 描述——
  描述里恰有一个 ``CHG-…`` 就按它做上面 3、4 两项证据检查；没有则看描述里的 ``任务卡: <路径>`` 一行，
  读 **PR 基线上** 那张卡的 ``变更单：`` 头部（``CHG-…`` 照样查证据；``无`` 不算，钩子本来就要求生产代码绑定变更单）。
  提交说明里自己写了单号的，仍以提交说明为准。

只报警，不判通过/失败（方案“第一步”）：默认退出码 0，结果写进作业摘要和 ``::warning::`` 标注，用来观察两周的误报；
``--enforce`` 才在有警告时退出 1（转必过检查前不得启用，需用户点头）。退出码 2 = 用法或 Git 出错。

裁判全部取自 PR 基线：本脚本和它导入的 auto_pm 都来自基线检出；PR 头只当 git 对象读，其中的文件不导入、不执行。
本检查没有复跑的部分：``pre-commit`` 的台账对账（``ledger reconcile``）要账本数据库，CI 上没有，见方案“暂不做”。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parents[2]
SW008_ROOT = (
    TOOL_ROOT / "01_Project自动化项目管理" / "Python自动化项目总库" / "02_在研项目" / "SW-2026-008_auto-pm_自动化项目管理工具"
)
for _entry in (Path(__file__).resolve().parent, SW008_ROOT):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

# 这些是钩子模块的私有函数：复用是本脚本的目的（同一套判定），钩子改名时 test_hook_replay 的导入会先变红。
from auto_pm.application.core import implementation_card_basis as card_basis
from auto_pm.domain.change.parser import ChgParser
from auto_pm.infrastructure import git_hook_enforcer as hook
from pr_scope_check import card_path_from_body, normalized

CHANGE_DIRS = ("04_监控", "11_监控")
LEDGER_TAIL = "01_变更管理/02_变更记录/01_版本变更台账.md"
CHANGE_TAIL = "01_变更管理/01_变更单/"


@dataclass(frozen=True)
class Finding:
    commit: str
    subject: str
    problem: str  # 空串 = 通过
    via: str = ""  # 通过时的绑定来源：空串 = 提交说明自带；否则是“PR 描述单号”“任务卡 …”之类，只用于显示


@dataclass(frozen=True)
class PrBinding:
    """PR 描述给出的整体绑定：``chg`` 是要查证据的变更单号（``via`` 说明来源），``problem`` 非空 = 描述写得不合格。"""

    chg: str = ""
    via: str = ""
    problem: str = ""

    @property
    def present(self) -> bool:
        return bool(self.chg or self.via or self.problem)


class GitError(RuntimeError):
    pass


def decode_name(raw: bytes) -> str:
    """文件名按 UTF-8 解码；PR 里有非 UTF-8 的文件名时不抛错，坏字节换成 U+FFFD（只用于判扩展名和显示）。"""
    return raw.decode("utf-8", errors="replace")  # lenient-decode: 文件名只用来判扩展名和显示，抛错会让报警作业变红


def plain(text: str) -> str:
    """把控制字符（含换行、回车、ESC）换成可见的 ``\\xNN`` / ``\\n``，文件名和提交标题里的它们不得进入输出。"""
    return "".join(ch if ch.isprintable() else f"\\x{ord(ch):02x}" if ord(ch) < 256 else f"\\u{ord(ch):04x}" for ch in text)


def command_data(text: str) -> str:
    """GitHub 工作流命令（``::warning::``）的消息体转义：``%`` ``\\r`` ``\\n`` 必须转义，否则内容能被当成新命令。"""
    return plain(text).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def git(repo: Path, *args: str) -> bytes:
    done = subprocess.run(
        ["git", "-C", str(repo), "-c", "core.quotepath=false", "-c", "core.autocrlf=false", *args],
        capture_output=True,
        check=False,
        timeout=120,
    )
    if done.returncode != 0:
        raise GitError(f"git {' '.join(args)} 失败: {done.stderr.decode('utf-8', 'replace').strip()}")
    return done.stdout


def commits_in(repo: Path, base: str, head: str) -> list[str]:
    out = git(repo, "rev-list", "--reverse", "--no-merges", f"{base}..{head}").decode("ascii")
    return out.split()


def commit_files(repo: Path, commit: str) -> list[str]:
    raw = git(repo, "diff-tree", "-r", "--root", "--no-commit-id", "--name-only", "--no-renames", "--diff-filter=ACMRT", "-z", commit)
    return [decode_name(item) for item in raw.split(b"\0") if item]


def commit_message(repo: Path, commit: str) -> str:
    return git(repo, "log", "-1", "--format=%B", commit).decode("utf-8", "replace")


def tree_paths(repo: Path, ref: str, prefix: str) -> list[str]:
    raw = git(repo, "ls-tree", "-r", "--name-only", "-z", ref, "--", prefix)
    return [decode_name(item) for item in raw.split(b"\0") if item]


def read_blob(repo: Path, ref: str, path: str) -> str:
    return git(repo, "show", f"{ref}:{path}").decode("utf-8")


def _first(repo: Path, refs: tuple[str, ...], project_root: str, tail: str, suffix: str = "") -> tuple[str, str] | None:
    """在 refs 里依次找项目下的文件，返回 (ref, 路径)；``suffix`` 非空时按文件名结尾匹配。"""
    for ref in refs:
        for top in CHANGE_DIRS:
            prefix = f"{project_root}/{top}/{tail}"
            found = [p for p in tree_paths(repo, ref, prefix.rstrip("/")) if not suffix or p.endswith("/" + suffix)]
            if found and not suffix:
                return ref, prefix.rstrip("/")
            if found:
                return ref, min(found)
    return None


def check_evidence(repo: Path, refs: tuple[str, ...], binding: object, chg_id: str) -> str:
    """变更单与台账证据；空串 = 通过。``refs`` 先 PR 头再基线（变更单可能早已在基线里）。"""
    root = binding.relative_root  # type: ignore[attr-defined]
    pid = binding.project_id  # type: ignore[attr-defined]
    change = _first(repo, refs, root, CHANGE_TAIL, f"{chg_id}.md")
    if change is None:
        return f"项目 {pid} 下找不到变更单文件 {chg_id}.md（本 PR 和基线都没有；若变更单稍后由主执行随另一个 PR 补入，属报警期已知情形）"
    ref, path = change
    try:
        content = read_blob(repo, ref, path)
        declared = hook._staged_change_project_id(content, chg_id)
    except (UnicodeDecodeError, hook.StagedSnapshotError, GitError) as exc:
        return f"变更单 {chg_id} 读不出项目编号: {exc}"
    if declared != pid:
        return f"变更单 {chg_id} 写的项目编号是 {declared}，生产代码归属是 {pid}"
    with tempfile.TemporaryDirectory() as tmp:
        temp = Path(tmp) / f"{chg_id}.md"
        temp.write_text(content, encoding="utf-8", newline="")
        try:
            parsed = ChgParser().parse(str(temp))
        except Exception as exc:  # noqa: BLE001 解析器的任何失败都按“证据不完整”报，与钩子一致
            return f"变更单 {chg_id} 解析失败: {exc}"
    if parsed.change_number != chg_id or parsed.project_id != pid:
        return f"变更单 {chg_id} 的解析结果与归属不一致"
    if parsed.status not in hook._VALID_CHANGE_STATUSES:
        return f"变更单 {chg_id} 状态是 {parsed.status}，不是合法执行态"
    ledger = None
    for ref_ in refs:
        for top in CHANGE_DIRS:
            candidate = f"{root}/{top}/{LEDGER_TAIL}"
            if tree_paths(repo, ref_, candidate):
                ledger = (ref_, candidate)
                break
        if ledger:
            break
    if ledger is None:
        return f"项目 {pid} 缺少版本变更台账"
    try:
        if chg_id not in read_blob(repo, *ledger):
            return f"项目 {pid} 的版本变更台账里没有 {chg_id}"
    except (UnicodeDecodeError, GitError) as exc:
        return f"项目 {pid} 的版本变更台账读不出: {exc}"
    return ""


_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def pr_binding(repo: Path, base: str, body: str) -> PrBinding:
    """从 PR 描述读整体绑定：先认描述里恰一个变更单号，再认 ``任务卡: <路径>``（读基线上的卡）。描述里的 HTML 注释（模板说明）不算。"""
    text = _HTML_COMMENT.sub("", body)
    chgs = tuple(dict.fromkeys(hook._CHG_ID_PATTERN.findall(text)))
    if len(chgs) == 1:
        return PrBinding(chg=chgs[0], via=f"PR 描述里的变更单 {chgs[0]}")
    if len(chgs) > 1:
        return PrBinding(problem=f"PR 描述里写了 {len(chgs)} 个变更单号（{'、'.join(chgs)}），必须且只能一个")
    raw_card = card_path_from_body(text)
    if raw_card is None:
        return PrBinding()
    card = normalized(raw_card)
    if card is None:
        return PrBinding(problem=f"PR 描述里的任务卡路径不是仓库内的相对路径: {raw_card}")
    try:
        content = read_blob(repo, base, card)
    except (GitError, UnicodeDecodeError):
        return PrBinding(problem=f"PR 描述里的任务卡 {card} 在 PR 基线上读不到（卡要先合入 main 才算数）")
    header = card_basis.parse_header(content.splitlines())
    if len(header.change) != 1:
        return PrBinding(problem=f"任务卡 {card} 的 `变更单：` 头部有 {len(header.change)} 行，必须恰好一行（没有就写 `无`）")
    if header.change_id and card_basis.CHG_ID.fullmatch(header.change_id):
        return PrBinding(chg=header.change_id, via=f"任务卡 {card}（变更单 {header.change_id}）")
    if card_basis._first_value(header.change[0]) == card_basis.NO_CHANGE:
        # 与本机 commit-msg 钩子一致：含生产代码的提交必须绑定变更单，任务卡写“无”不能替代（卡的“无”只对不动生产代码的卡成立）。
        return PrBinding(problem=f"任务卡 {card} 的 `变更单：` 写的是 `无`，但含生产代码的提交必须绑定一张变更单")
    return PrBinding(problem=f"任务卡 {card} 的 `变更单：` 既不是变更单号也不是 `无`: {header.change[0]}")


def replay(
    repo: Path, base: str, head: str, bindings: tuple[object, ...], pr_body: str = ""
) -> list[Finding]:
    """对 base..head 里每个有生产代码的非合并提交复跑钩子判定；提交说明没有单号时按 PR 描述的整体绑定补位。"""
    findings: list[Finding] = []
    overall = pr_binding(repo, base, pr_body) if pr_body else PrBinding()
    evidence_cache: dict[tuple[str, str], str] = {}
    for commit in commits_in(repo, base, head):
        production = hook.filter_production_files(commit_files(repo, commit))
        if not production:
            continue
        message = commit_message(repo, commit)
        subject = message.strip().splitlines()[0] if message.strip() else ""
        short = commit[:8]
        chgs = tuple(dict.fromkeys(hook._CHG_ID_PATTERN.findall(message)))
        via = ""
        problem = ""
        if not chgs and overall.present:
            if overall.problem:
                problem = f"提交说明没有变更单号，PR 描述的绑定也不合格: {overall.problem}"
            else:
                via = overall.via
                chgs = (overall.chg,)
        if problem:
            pass
        elif not chgs:
            problem = f"含生产代码（{production[0]} 等 {len(production)} 个）但提交说明没有绑定变更单号，PR 描述里也没有变更单号或任务卡"
        elif len(chgs) != 1:
            problem = f"提交说明绑定了 {len(chgs)} 个变更单（{'、'.join(chgs)}），必须且只能一个"
        else:
            try:
                owners = {hook._binding_for_staged_file(path, bindings).project_id for path in production}  # type: ignore[arg-type]
            except hook.StagedSnapshotError as exc:
                # 裁判是基线检出：本 PR 新注册的项目基线还不认识，这里会误报；报警期的已知情形，写进提示免得被当成缺陷。
                problem = f"{exc}（若本 PR 新注册了这个项目，基线还不认识它，属报警期已知误报）"
            else:
                if len(owners) != 1:
                    problem = f"生产代码归属多个项目: {'、'.join(sorted(owners))}"
                else:
                    pid = next(iter(owners))
                    key = (chgs[0], pid)
                    if key not in evidence_cache:
                        binding = next(b for b in bindings if b.project_id == pid)  # type: ignore[attr-defined]
                        evidence_cache[key] = check_evidence(repo, (head, base), binding, chgs[0])
                    problem = evidence_cache[key]
        findings.append(Finding(short, plain(subject), plain(problem), plain(via) if not problem else ""))
    return findings


def render(findings: list[Finding]) -> str:
    bad = [f for f in findings if f.problem]
    lines = [
        "### hook-replay：提交钩子“绑定变更单”检查复跑（报警期，不拦合并）",
        "",
        f"有生产代码的提交 {len(findings)} 个，其中 {len(bad)} 个有警告。",
        "",
    ]
    for f in findings:
        tail = f" — {f.problem}" if f.problem else (f"（经{f.via}）" if f.via else "")
        lines.append(f"- {'⚠️' if f.problem else '✅'} `{f.commit}` {f.subject}{tail}")
    if not findings:
        lines.append("没有含生产代码的提交，无需复跑。")
    return "\n".join(lines) + "\n"


def build_bindings(repo: Path) -> tuple[object, ...]:
    from auto_pm.application.core.project_service import ProjectService

    return hook._project_bindings(repo, list(ProjectService(str(repo)).list_projects()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", required=True, help="裁判（基线）提交")
    parser.add_argument("--head", required=True, help="PR 头提交（只当数据读）")
    parser.add_argument("--repo", default=".", help="含基线检出和 PR 头 git 对象的仓库（默认当前目录）")
    parser.add_argument("--ci", action="store_true", help="输出 GitHub ::warning:: 标注并写作业摘要")
    parser.add_argument("--enforce", action="store_true", help="有警告时退出 1（报警期不得启用）")
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    try:
        findings = replay(repo, args.base, args.head, build_bindings(repo), os.environ.get("PR_BODY", ""))
    except (GitError, OSError, subprocess.SubprocessError) as exc:
        print(f"hook-replay 无法运行（未核实，不是通过）: {exc}", file=sys.stderr)
        return 2
    text = render(findings)
    print(text)
    bad = [f for f in findings if f.problem]
    if args.ci:
        if bad:  # 一条汇总标注，细节在作业摘要里：报警期云端 PR 几乎每个提交都有警告，逐条标注会淹没真正的信息
            note = f"{len(bad)}/{len(findings)} 个含生产代码的提交没有通过提交钩子的变更单绑定检查（报警期，不拦合并，明细见作业摘要）"
            print(f"::warning title=hook-replay::{command_data(note)}")
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as handle:
                handle.write(text)
    return 1 if (args.enforce and bad) else 0


if __name__ == "__main__":
    sys.exit(main())
