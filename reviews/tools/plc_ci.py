"""PLC 项目 CI：PR 改到 ``0100_PLC自动化`` 下的项目或共享库时，在 Linux 上跑能跑的静态检查，并和 PR 基线比对。

GitHub Actions 的 plc-ci 工作流调用。说明见项目文件夹 ``plans/PLC项目CI_说明_20261022.md``。

跑什么（检查代码一律取 PR 基线上的 SW-2026-008 源码——裁判取自基线，PR 头只当数据读）：

1. ``plc check``：等同于 ``main.py plc check <ID> --no-language-service``（同一个 ``PlcService.check``，不带 ``--fix``）。
2. ``plc docs check``：等同于 ``main.py plc docs check --project-path <目录>``（同一个 ``doc_consistency.analyze_project``）。
3. SCL 规范逐条明细：``plc check`` 里“SCL 代码规范”一项只给总数和前 3 条，这里用同一个 ``SclLinter`` 逐条列出，好和基线逐条比。

没跑、明确跳过的（日志和汇总表里逐项写原因，不算通过）：Siemens 语言服务插件 ``check``/``test``（含 ``.scltest`` 仿真测试）、
厂家软件编译（博图 TIA Portal / 汇川 InoProShop）、安全区签字（由 safety-gate 工作流负责；它还没合进 main 时写明未覆盖）。

判定（每个项目）：

* ``PASS``：没有失败项；
* ``PASS_KNOWN_BASELINE``：有失败项，但全部是 PR 基线上就有的老问题——**不是全绿**，汇总表里逐条列出；
* ``FAIL``：出现基线上没有的新失败项（或检查程序本身出错）——整个作业失败。
* 没碰任何 PLC 项目：``不适用（N/A）``，作业通过但写明没跑检查（工作流对每个 PR 都运行，好设成必过检查）。

比对粒度：``plc check`` 的结构类检查按检查项名；文档一致性按 ``plc docs check`` 的每条发现（对象、变量、说明，不含行号）；
SCL 规范按每条违规（文件、规则、说明，不含行号，同类数量增加也算新增）。

用法（仓库外任意目录执行）::

    python plc_ci.py --base-root <基线检出> --head-root <PR 头检出> --base-sha <sha> --head-sha <sha>
    python plc_ci.py --base-root <基线检出> --head-root <PR 头检出> --all            # 全部 PLC 项目
    python plc_ci.py ... --scope-only          # 只判断要不要跑（没碰 PLC 时报“不适用”），不需要装依赖
    python plc_ci.py ... --checker-from-head   # 推到 main：检查代码取自推送后的提交，检查代码改了就全量查

退出码：0 通过（含 PASS_KNOWN_BASELINE）；1 有新失败或检查出错；2 用法错误。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

PLC_TOP = "0100_PLC自动化"
SHARED = "01_SharedLibraries"
SW008 = "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具"
SAFETY_TOOL = "reviews/tools/safety_zone_check.py"
# 改到这些文件说明检查程序本身变了：所有 PLC 项目都跑一遍
JUDGE_FILES = (".github/workflows/plc-ci.yml", "reviews/tools/plc_ci.py", "reviews/tools/test_plc_ci.py")
# SW-2026-008 里检查子进程实际加载的代码（自测 test_checker_paths_cover_every_loaded_module 逐个核对）；
# 推到 main 时它们变了，用新代码把所有 PLC 项目查一遍。另加锁定依赖：第三方库换版本也可能改结果
CHECKER_PATHS = (
    f"{SW008}/auto_pm/__init__.py",
    f"{SW008}/auto_pm/application/core/__init__.py",
    f"{SW008}/auto_pm/application/core/paths.py",
    f"{SW008}/auto_pm/domain/__init__.py",
    f"{SW008}/auto_pm/domain/change/__init__.py",
    f"{SW008}/auto_pm/domain/modbus/__init__.py",
    f"{SW008}/auto_pm/domain/models/",
    f"{SW008}/auto_pm/domain/plc/",
    f"{SW008}/auto_pm/domain/project/__init__.py",
    f"{SW008}/auto_pm/domain/project/state_machine.py",
    f"{SW008}/auto_pm/domain/spec/__init__.py",
    f"{SW008}/auto_pm/domain/vartable/",
    f"{SW008}/auto_pm/infrastructure/__init__.py",
    f"{SW008}/auto_pm/infrastructure/db/",
    f"{SW008}/auto_pm/infrastructure/logging/__init__.py",
    f"{SW008}/auto_pm/infrastructure/utils/__init__.py",
    f"{SW008}/auto_pm/infrastructure/utils/file_utils.py",
    f"{SW008}/auto_pm/ui/__init__.py",
    "00_Infrastructure/auto_pm/environment/requirements-lock-py312-win.txt",
)
# 工作流按这个版本号调用本脚本；基线上的脚本版本低于工作流要求时，工作流改取 PR 头的脚本并明说
PLC_CI_PROTOCOL = 2
LOST_CONFIG = "PR 删掉了 .plc.json，但项目目录还在"
NOT_APPLICABLE = "不适用（N/A）：本次改动没碰任何 PLC 项目或共享库，没有跑 PLC 检查（这不是“检查通过”）。"
_DIGITS = re.compile(r"\d+")

# 子进程里执行：用基线上的 SW-2026-008 源码检查一个项目目录，结果以 JSON 打印
_CHILD = r"""
import json, os, sys
from dataclasses import asdict
sys.path.insert(0, sys.argv[1])
workspace, project = sys.argv[2], sys.argv[3]
from auto_pm.plc.service import PlcService
from auto_pm.plc import doc_consistency as dc
from auto_pm.domain.plc.scl_linter import SclLinter
result = PlcService(workspace, language_service=None).check(project, fix=False)
analysis = dc.analyze_project(project)
scl = []
for root, _, files in os.walk(project):
    for name in sorted(files):
        if name.lower().endswith(".scl"):
            path = os.path.join(root, name)
            rel = os.path.relpath(path, project).replace(os.sep, "/")
            for v in SclLinter.lint_file(path).violations:
                if v.severity == "ERROR":
                    scl.append({"file": rel, "rule": v.rule_id, "message": v.message, "line": v.line_number})
print(json.dumps({
    "check": result.model_dump(),
    "docs": [asdict(f) for f in analysis.findings],
    "scl": scl,
}, ensure_ascii=False))
"""

SKIP_LANGUAGE_SERVICE = (
    "Siemens 语言服务插件 check/test 没跑：插件只许在用户本机调用，按约定不复制、不放进仓库或 CI"
    "（siemens_language_service.py 模块说明）。本机用 main.py plc check <ID> 跑这一层。"
)
SKIP_VENDOR = (
    "厂家软件编译没跑：博图 TIA Portal / 汇川 InoProShop 只有 Windows 版且要授权，GitHub 的 Linux 机器上没有。"
    "编译与下载前的检查仍在本机或虚拟机上做。"
)


@dataclass
class Target:
    rel: str  # 相对仓库根，POSIX 形式
    reason: str


@dataclass
class Outcome:
    target: Target
    verdict: str = "PASS"
    new: list[str] = field(default_factory=list)
    known: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    error: str = ""
    counts: str = ""


# ── 找要检查的项目 ─────────────────────────────────────────


def is_project(root: Path, rel: str) -> bool:
    return (root / rel / ".plc.json").is_file()


def all_projects(root: Path) -> list[str]:
    top = root / PLC_TOP
    found: list[str] = []
    if not top.is_dir():
        return found
    for child in sorted(top.iterdir()):
        if not child.is_dir() or child.name.startswith(("00_", "_", ".")):
            continue
        if child.name == SHARED:
            found.extend(f"{PLC_TOP}/{SHARED}/{lib.name}" for lib in sorted(child.iterdir())
                         if lib.is_dir() and (lib / ".plc.json").is_file())
        elif (child / ".plc.json").is_file():
            found.append(f"{PLC_TOP}/{child.name}")
    return found


def owner(path: str) -> str | None:
    """改动文件所属的项目目录（相对仓库根）；不属于任何项目返回 None。"""
    parts = PurePosixPath(path).parts
    if len(parts) < 3 or parts[0] != PLC_TOP:
        return None
    if parts[1] == SHARED:
        return f"{PLC_TOP}/{SHARED}/{parts[2]}" if len(parts) >= 4 else None
    if parts[1].startswith(("00_", "_", ".")):
        return None
    return f"{PLC_TOP}/{parts[1]}"


def dependents(root: Path, lib_rel: str) -> list[str]:
    """引用该共享库的项目（按 .plc.json 的 libraries 解析）。"""
    lib = (root / lib_rel).resolve()
    found: list[str] = []
    for rel in all_projects(root):
        try:
            libs = json.loads((root / rel / ".plc.json").read_text(encoding="utf-8")).get("libraries") or []
        except (OSError, ValueError, AttributeError):
            continue
        if any((root / rel / str(entry)).resolve() == lib for entry in libs):
            found.append(rel)
    return found


def is_checker(path: str) -> bool:
    return any(path == p or (p.endswith("/") and path.startswith(p)) for p in CHECKER_PATHS)


def select(head: Path, base: Path, changed: list[str], check_all: bool,
           checker_from_head: bool = False) -> tuple[list[Target], list[str]]:
    """返回 (要检查的项目, 说明性日志行)。"""
    notes: list[str] = []
    if check_all:
        return [Target(rel, "全量检查") for rel in all_projects(head)], notes
    if any(path in JUDGE_FILES for path in changed):
        notes.append("改到了 PLC CI 本身（工作流、plc_ci.py 或它的自测）：自测和所有 PLC 项目都跑一遍")
        return [Target(rel, "PLC CI 本身有改动") for rel in all_projects(head)], notes
    if any(is_checker(path) for path in changed):
        if checker_from_head:
            notes.append("PLC 检查代码（SW-2026-008）有改动：用新代码把所有 PLC 项目查一遍")
            return [Target(rel, "PLC 检查代码有改动") for rel in all_projects(head)], notes
        notes.append("PLC 检查代码（SW-2026-008）有改动，但 PR 上裁判取基线、看不出新代码的效果："
                     "合进 main 后推送那次会用新代码全量查；代码本身的测试归 sw008-ci")
    targets: dict[str, str] = {}
    other: set[str] = set()
    for path in changed:
        rel = owner(path)
        if rel is None:
            if path.startswith(PLC_TOP + "/"):
                other.add("/".join(PurePosixPath(path).parts[:2]))
            continue
        if not is_project(head, rel):
            if is_project(base, rel) and (head / rel).is_dir() and any(p.is_file() for p in (head / rel).rglob("*")):
                # 只删配置、留下程序：不能借此躲开检查（也包括共享库）
                targets.setdefault(rel, LOST_CONFIG)
            elif is_project(base, rel):
                notes.append(f"{rel}：PR 里整个删掉了，不再检查")
            else:
                other.add(rel)
            continue
        targets.setdefault(rel, "PR 改到")
        if targets[rel] != LOST_CONFIG and rel.startswith(f"{PLC_TOP}/{SHARED}/"):
            for dep in dependents(head, rel):
                targets.setdefault(dep, f"引用了改动的共享库 {PurePosixPath(rel).name}")
    for rel in sorted(other):
        notes.append(f"{rel}：不是 PLC 项目目录（没有 .plc.json），没有可跑的 PLC 检查")
    return [Target(rel, why) for rel, why in sorted(targets.items())], notes


# ── 运行与比对 ─────────────────────────────────────────────


def run_checks(judge: Path, workspace: Path, rel: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP")}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "AUTO_PM_WORKSPACE": str(workspace), "PYTHONIOENCODING": "utf-8"})
    proc = subprocess.run(
        [sys.executable, "-B", "-I", "-c", _CHILD, str(judge / SW008), str(workspace), str(workspace / rel)],
        cwd=str(workspace), env=env, capture_output=True, text=True, encoding="utf-8", timeout=600, check=False,
    )
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise RuntimeError(f"检查程序出错（退出码 {proc.returncode}）：\n{tail}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def failure_keys(data: dict) -> Counter:
    """把一次检查的失败项展开成可逐条比对的键（不含行号）。"""
    keys: Counter = Counter()
    for item in data["check"]["items"]:
        if item["status"] != "fail":
            continue
        name = item["item"]
        # 这两项另有逐条明细，下面单独展开
        if name == "SCL 代码规范" or name.startswith("文档一致性"):
            continue
        # 说明里常带行数、计数，数字抹平后连说明一起比：同一项里多出一处新问题（说明变了）也算新增
        keys[f"plc check · {name}：{_DIGITS.sub('#', item['message'])}"] += 1
    for f in data["docs"]:
        if f["severity"] == "fail":
            who = f"{f['obj']}.{f['variable']}" if f["variable"] else f["obj"]
            keys[f"plc docs check · {who}：{f['message']}"] += 1
    for v in data["scl"]:
        keys[f"SCL 规范 · {v['file']} [{v['rule']}] {v['message']}"] += 1
    return keys


def consistent(data: dict) -> str:
    """plc check 自己的判卷与逐条明细对不上时返回说明（防止明细漏展开而误判通过）。"""
    items = {i["item"]: i["status"] for i in data["check"]["items"]}
    scl_fail = items.get("SCL 代码规范") == "fail"
    if scl_fail != bool(data["scl"]):
        return "plc check 的“SCL 代码规范”判卷与逐条明细不一致"
    docs_fail = any(n.startswith("文档一致性") and s == "fail" for n, s in items.items())
    if docs_fail and not any(f["severity"] == "fail" for f in data["docs"]):
        return "plc check 的文档一致性判卷与 plc docs check 明细不一致"
    return ""


def evaluate(judge: Path, base: Path, head: Path, target: Target, *, compare: bool,
             base_judge: Path | None = None) -> Outcome:
    """base_judge：跑基线那一次用的检查代码（默认同 judge）。推到 main 时它是推送前的代码，比的是“推送前 vs 推送后”整体。"""
    out = Outcome(target)
    rel = target.rel
    out.skipped.append(SKIP_LANGUAGE_SERVICE)
    scltests = sorted(p.relative_to(head / rel).as_posix() for p in (head / rel).rglob("*.scltest"))
    if scltests:
        out.skipped.append(f"{len(scltests)} 个 .scltest 仿真测试没跑（同样要本机插件 test）：{'、'.join(scltests)}")
    out.skipped.append(SKIP_VENDOR)
    if target.reason == LOST_CONFIG:
        out.verdict, out.error = "FAIL", f"{LOST_CONFIG}：没有 .plc.json 就跑不了 PLC 检查，要么恢复配置，要么连目录一起删"
        return out
    try:
        now = run_checks(judge, head, rel)
        mismatch = consistent(now)
        if mismatch:
            raise RuntimeError(mismatch)
        before = run_checks(base_judge or judge, base, rel) if compare and is_project(base, rel) else None
    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        out.verdict, out.error = "FAIL", str(exc)
        return out
    c = now["check"]
    out.counts = f"plc check 通过 {c['pass_count']}、警告 {c['warn_count']}、失败 {c['fail_count']}"
    if c.get("not_applicable"):
        out.counts += f"（不适用：{c.get('not_applicable_reason', '')}）"
    head_keys = failure_keys(now)
    base_keys = failure_keys(before) if before is not None else Counter()
    for key, n in sorted(head_keys.items()):
        old = min(n, base_keys.get(key, 0))
        out.known.extend([key] * old)
        out.new.extend([key] * (n - old))
    if out.new:
        out.verdict = "FAIL"
    elif out.known:
        out.verdict = "PASS_KNOWN_BASELINE"
    if before is None and compare:
        out.counts += "；基线上没有这个项目，所有失败项都算新增"
    return out


def safety_note(base: Path) -> str:
    if (base / SAFETY_TOOL).is_file():
        return ("安全区规则检查不在本工作流重复跑：由 safety-gate 工作流（提交状态 safety-zone，"
                f"{SAFETY_TOOL}）负责，包括签字和 OR TRUE 旁路、安全点漏接两项硬检查。")
    return ("安全区规则检查没跑：检查脚本还没合进 main（预做分支 claude/safety-signoff-check，D09 后落地卡 B）。"
            "在它合并并启用之前，PLC 改动的安全区（急停、安全门、光栅、联锁）仍靠人工审计和用户安全签字。")


# ── 输出 ──────────────────────────────────────────────────


def render_log(outcomes: list[Outcome], notes: list[str], safety: str, judge_note: str) -> str:
    lines = ["== PLC CI ==", judge_note]
    lines += [f"注意：{n}" for n in notes]
    lines.append(f"SKIPPED（全局）：{safety}")
    if not outcomes:
        lines.append(NOT_APPLICABLE)
    for o in outcomes:
        lines.append("")
        lines.append(f"[{o.verdict}] {o.target.rel}（{o.target.reason}）")
        if o.counts:
            lines.append(f"    {o.counts}")
        if o.error:
            lines += [f"    出错：{line}" for line in o.error.splitlines()]
        for key in o.new:
            lines.append(f"    新增失败：{key}")
        if o.known:
            lines.append(f"    基线已有的失败 {len(o.known)} 条（不是本 PR 引入，仍需另行修复）：")
            lines += [f"      - {key}" for key in o.known]
        for s in o.skipped:
            lines.append(f"    SKIPPED：{s}")
    return "\n".join(lines)


def render_summary(outcomes: list[Outcome], notes: list[str], safety: str, judge_note: str) -> str:
    md = ["## PLC CI", "", judge_note, ""]
    md += [f"- 注意：{n}" for n in notes]
    md += [f"- **跳过（全局）**：{safety}", ""]
    if not outcomes:
        md.append(NOT_APPLICABLE)
        return "\n".join(md)
    md += ["| 项目 | 判定 | 新增失败 | 基线已有失败 | 说明 |", "|---|---|---|---|---|"]
    for o in outcomes:
        md.append(f"| `{o.target.rel}` | **{o.verdict}** | {len(o.new)} | {len(o.known)} | "
                  f"{o.target.reason}；{o.counts or o.error.splitlines()[0]} |")
    md += ["", "`PASS_KNOWN_BASELINE` 不是全绿：失败项都是 PR 基线上就有的，本 PR 没有加新的。逐条清单见作业日志。", ""]
    md.append("**每个项目都没跑的层（不算通过）：**")
    md += [f"- {SKIP_LANGUAGE_SERVICE}", f"- {SKIP_VENDOR}", "- `.scltest` 仿真测试：需要本机插件 `test`。"]
    for o in outcomes:
        if o.new:
            md += ["", f"### `{o.target.rel}` 新增失败"]
            md += [f"- {key}" for key in o.new[:50]]
            if len(o.new) > 50:
                md.append(f"- ……另有 {len(o.new) - 50} 条，见作业日志")
    return "\n".join(md)


def scope_only(targets: list[Target], notes: list[str]) -> int:
    applies = bool(targets)
    for n in notes:
        print(f"注意：{n}")
    if applies:
        print(f"要检查 {len(targets)} 个 PLC 项目：")
        for t in targets:
            print(f"  - {t.rel}（{t.reason}）")
    else:
        print(NOT_APPLICABLE)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as handle:
            handle.write(f"applies={'true' if applies else 'false'}\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and not applies:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("## PLC CI\n\n" + "".join(f"- 注意：{n}\n" for n in notes) + f"\n{NOT_APPLICABLE}\n")
    if os.environ.get("GITHUB_ACTIONS") == "true" and not applies:
        print(f"::notice title=PLC CI 不适用::{NOT_APPLICABLE}")
    return 0


def changed_files(head: Path, base_sha: str, head_sha: str) -> list[str]:
    proc = subprocess.run(
        ["git", "-c", "core.quotepath=off", "diff", "--name-only", "--no-renames", f"{base_sha}...{head_sha}"],
        cwd=str(head), capture_output=True, text=True, encoding="utf-8", check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git diff 失败：{proc.stderr.strip()}")
    return [line for line in proc.stdout.splitlines() if line]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-root", type=Path, required=True, help="PR 基线的检出（检查代码与基线数据都取自这里）")
    parser.add_argument("--head-root", type=Path, required=True, help="PR 头的检出（被检查的数据）")
    parser.add_argument("--judge-root", type=Path, help="检查代码所在的检出（默认就是 --base-root；只在自测里另给）")
    parser.add_argument("--base-sha", help="PR 基线提交")
    parser.add_argument("--head-sha", help="PR 头提交")
    parser.add_argument("--all", action="store_true", help="检查全部 PLC 项目")
    parser.add_argument("--no-compare", action="store_true", help="不和基线比（盘点模式：有失败项就判 FAIL）")
    parser.add_argument("--checker-from-head", action="store_true",
                        help="检查代码取自 --head-root（只用于推到 main：代码已审过合入）；检查代码改了就全量查")
    parser.add_argument("--scope-only", action="store_true",
                        help="只判断要不要跑（不需要装依赖）：打印要查的项目，向 GITHUB_OUTPUT 写 applies=true/false")
    args = parser.parse_args(argv)
    if args.judge_root and args.checker_from_head:
        print("用法错误：--judge-root 和 --checker-from-head 只能给一个", file=sys.stderr)
        return 2
    base, head = args.base_root.resolve(), args.head_root.resolve()
    judge = head if args.checker_from_head else (args.judge_root or args.base_root).resolve()
    if not args.all and not (args.base_sha and args.head_sha):
        print("用法错误：要么给 --base-sha 和 --head-sha，要么用 --all", file=sys.stderr)
        return 2
    try:
        changed = [] if args.all else changed_files(head, args.base_sha, args.head_sha)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    targets, notes = select(head, base, changed, args.all, args.checker_from_head)
    if args.scope_only:
        return scope_only(targets, notes)
    if not (judge / SW008 / "auto_pm").is_dir():
        print(f"用法错误：检查代码所在检出里没有 {SW008}/auto_pm", file=sys.stderr)
        return 2
    where = "基线检出" if judge == base else ("PR 头检出（推到 main，代码已合入）" if judge == head else f"指定检出 {judge}")
    judge_note = f"检查代码取自{where}（{SW008}），被检查数据取自 PR 头检出；比对基线：{'不比对（盘点模式）' if args.no_compare else '是'}。"
    safety = safety_note(base)
    # 推到 main 时基线那一次用推送前的检查代码：检查代码自己变严/变松造成的差异也算进来
    base_judge = base if args.checker_from_head else judge
    outcomes = [evaluate(judge, base, head, t, compare=not args.no_compare, base_judge=base_judge) for t in targets]
    print(render_log(outcomes, notes, safety, judge_note))
    if os.environ.get("GITHUB_ACTIONS") == "true":
        # 显示在 PR 的检查页上：跳过的层与新失败一眼可见
        print(f"::warning title=PLC CI 跳过::{safety}")
        print(f"::warning title=PLC CI 跳过::{SKIP_LANGUAGE_SERVICE}")
        print(f"::warning title=PLC CI 跳过::{SKIP_VENDOR}")
        for o in outcomes:
            if o.verdict == "FAIL":
                print(f"::error title=PLC CI {o.target.rel}::新增失败 {len(o.new)} 条{'；' + o.error.splitlines()[0] if o.error else ''}")
            elif o.verdict == "PASS_KNOWN_BASELINE":
                print(f"::notice title=PLC CI {o.target.rel}::不是全绿：基线已有失败 {len(o.known)} 条，本 PR 没有新增")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(render_summary(outcomes, notes, safety, judge_note) + "\n")
    return 1 if any(o.verdict == "FAIL" for o in outcomes) else 0


if __name__ == "__main__":
    raise SystemExit(main())
