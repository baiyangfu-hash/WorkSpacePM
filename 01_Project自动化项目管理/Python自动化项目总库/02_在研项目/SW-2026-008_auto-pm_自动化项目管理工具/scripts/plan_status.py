"""项目计划状态（WBS 8.8 第一版）：读项目计划表，按实施卡号去 Git 里算每个任务、每个里程碑的状态，只显示。

用法（在控制根，用控制根 .venv 里的 Python；Windows 是 .venv\\Scripts\\python.exe）：
  python <本项目>/scripts/plan_status.py <项目号> [--json] [--offline] [--plan-file <文件>]

规矩：

1. 只算只显示。不写项目计划表、不写里程碑表、不写台账；本脚本没有任何写开关（回写放第二版）。
2. 状态一律现算，算法在 ``scripts/card_status.py``（和交接契约的状态单共用）。计划表里没有状态栏，
   写了也不读；实施卡文件里手写的“状态”行不读。
3. 计划表和证据文件都读 main 上的版本（``origin/main``），不读本机没提交的改动：合并进 main 才算数。
   想在合并前试一张计划表，用 ``--plan-file`` 指本机文件（只换计划表本身，证据仍读 main）。
4. 远程读不到时整张表的挂卡任务都显示“没查到”，退出 1；绝不显示成“未开始”。
5. 项目还没有计划表：说明一句，退出 0（现在只有 005 用这张表）。

项目计划表的格式（放在 ``<项目目录>/00_项目管理/01_立项与需求/NNN_<项目号>_项目计划表.md``）：

- 每个里程碑一节，标题 ``## L1 立项``（编号加名称）。
- 每节一张表，栏目固定：``| 编号 | 原子任务 | 实施卡 | 证据 | 备注 |``。
- 实施卡一格四种写法：反引号包卡号 ``CARD-<项目号>-NNN``；还没卡写“无”；
  只有用户本人能做的（放图纸、移植回执）写“用户”，并且必须列证据；这个项目用不上的写“不适用”。
- 证据一格：反引号包相对项目目录的路径，可多个可空。挂了卡的任务，证据文件里要写着这张卡的卡号才算数。
- 末尾一节 ``## 验收记录``，表头 ``| 里程碑 | 验收时间 | 凭据 |``；凭据写 ``user-confirmation:<用户那条消息的时间或编号>``。

任务状态：未开始、在干、已合并未验证、已完成（挂卡的四级，见 card_status）；
写“无”的：证据文件都在是“有东西缺证据”，否则“未开始”（文件在不等于做完，没人验证过）；
写“用户”的：证据文件都在是“用户已交”，否则“未开始”；“不适用”原样，不计数。
里程碑状态：挂卡任务全部已完成、写“用户”的全部已交，是“待用户验收”（写“无”的任务会挡住）；
再有一条有效的验收记录才是“已达成”。纯点头的事不列任务行，就是验收记录。

退出码：0＝算出来了；1＝远程没读到，或计划表格式有错（能算的照算，错处逐条列出）；2＝用法不对。
本脚本不进发布载荷。
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = PROJECT_ROOT.parents[3]
REGISTRY = "SYS-2026-001_WorkspaceGovernance/workspace_registry.json"
PLAN_DIR = "00_项目管理/01_立项与需求"
PLAN_SUFFIX = "_{pid}_项目计划表.md"
PID_PATTERN = re.compile(r"^[A-Z]{2,4}-\d{4}-\d{3}$")
MILESTONE_HEADING = re.compile(r"^##\s+([A-Z]+\d+)\s+(\S.*?)\s*$")
ACCEPT_HEADING = re.compile(r"^##\s+验收记录\s*$")
TASK_HEADER = ("编号", "原子任务", "实施卡", "证据", "备注")
ACCEPT_HEADER = ("里程碑", "验收时间", "凭据")
BACKTICK = re.compile(r"`([^`]+)`")
NO_CARD = "无"
NOT_APPLICABLE = "不适用"
BY_USER = "用户"
HAS_FILES = "有东西缺证据"
USER_DELIVERED = "用户已交"
ACCEPT_PREFIX = "user-confirmation:"

M_NOT_STARTED = "未开始"
M_RUNNING = "进行中"
M_WAITING = "待用户验收"
M_REACHED = "已达成"


def _load_card_status() -> ModuleType:
    """同目录的 card_status.py。按文件路径加载：scripts 不是包，也不靠 sys.path 碰巧有它。"""
    name = "auto_pm_scripts_card_status"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name("card_status.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError("找不到同目录的 card_status.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


card_status = _load_card_status()


@dataclass(frozen=True)
class Task:
    task_id: str
    title: str
    card: str  # 卡号；"" 表示没挂卡
    applicable: bool
    by_user: bool
    evidence: tuple[str, ...]
    line: int


@dataclass
class Milestone:
    milestone_id: str
    title: str
    tasks: list[Task] = field(default_factory=list)


@dataclass(frozen=True)
class Acceptance:
    milestone_id: str
    when: str
    proof: str


@dataclass
class Plan:
    milestones: list[Milestone] = field(default_factory=list)
    acceptances: list[Acceptance] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _cells(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    return [cell.strip() for cell in body.split("|")]


def _is_separator(cells: Sequence[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _safe_relative(path: str) -> bool:
    if (
        not path
        or path != path.strip()
        or "\\" in path
        or path.startswith("/")
        or re.match(r"^[A-Za-z]:", path)
    ):
        return False
    return all(part not in {"", ".", ".."} for part in path.split("/"))


def parse_plan(text: str, pid: str) -> Plan:
    """把项目计划表读成结构。格式不对的行记进 problems，不猜、不补。"""
    plan = Plan()
    card_pattern = re.compile(rf"^CARD-{re.escape(pid)}-\d{{3}}$")
    current: Milestone | None = None
    section = ""  # "milestone" | "accept" | ""
    header_seen = False
    seen_tasks: dict[str, int] = {}
    seen_cards: dict[str, str] = {}
    seen_milestones: set[str] = set()
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip()
        if line.startswith("## "):
            header_seen = False
            heading = MILESTONE_HEADING.match(line)
            if heading:
                milestone_id = heading.group(1)
                if milestone_id in seen_milestones:
                    plan.problems.append(f"第 {number} 行：里程碑编号 {milestone_id} 重复")
                seen_milestones.add(milestone_id)
                current = Milestone(milestone_id, heading.group(2))
                plan.milestones.append(current)
                section = "milestone"
            elif ACCEPT_HEADING.match(line):
                current = None
                section = "accept"
            else:
                current = None
                section = ""
            continue
        if not line.lstrip().startswith("|") or not section:
            continue
        cells = _cells(line)
        if _is_separator(cells):
            continue
        if not header_seen:
            expected = TASK_HEADER if section == "milestone" else ACCEPT_HEADER
            if tuple(cells) != expected:
                plan.problems.append(
                    f"第 {number} 行：表头应是 | {' | '.join(expected)} |，实际是 | {' | '.join(cells)} |"
                )
                section = ""  # 这张表的栏目对不上，整张不读
                continue
            header_seen = True
            continue
        if section == "accept":
            if len(cells) != len(ACCEPT_HEADER):
                plan.problems.append(f"第 {number} 行：验收记录应有 3 格，实际 {len(cells)} 格")
                continue
            milestone_id, when, proof = cells
            proof = proof.strip("`")
            if not milestone_id and not when and not proof:
                continue
            if (
                not when
                or not proof.startswith(ACCEPT_PREFIX)
                or len(proof) < len(ACCEPT_PREFIX) + 8
            ):
                plan.problems.append(
                    f"第 {number} 行：验收记录要有验收时间，凭据要写成 {ACCEPT_PREFIX}<用户那条消息的时间或编号>"
                )
                continue
            plan.acceptances.append(Acceptance(milestone_id, when, proof))
            continue
        assert current is not None
        if len(cells) != len(TASK_HEADER):
            plan.problems.append(f"第 {number} 行：任务行应有 5 格，实际 {len(cells)} 格")
            continue
        task_id, title, card_cell, evidence_cell, _note = cells
        if not task_id.startswith(current.milestone_id + ".") or not title:
            plan.problems.append(
                f"第 {number} 行：任务编号应以 {current.milestone_id}. 开头，并且要有任务名"
            )
            continue
        if task_id in seen_tasks:
            plan.problems.append(
                f"第 {number} 行：任务编号 {task_id} 和第 {seen_tasks[task_id]} 行重复"
            )
            continue
        applicable = True
        by_user = card_cell == BY_USER
        card = ""
        if card_cell == NOT_APPLICABLE:
            applicable = False
        elif card_cell not in (NO_CARD, BY_USER):
            tokens = BACKTICK.findall(card_cell)
            if (
                len(tokens) != 1
                or BACKTICK.sub("", card_cell).strip()
                or not card_pattern.match(tokens[0])
            ):
                plan.problems.append(
                    f"第 {number} 行：实施卡一格只能是“{NO_CARD}”“{BY_USER}”“{NOT_APPLICABLE}”或一个反引号包着的 CARD-{pid}-NNN"
                )
                continue
            card = tokens[0]
            if card in seen_cards:
                plan.problems.append(
                    f"第 {number} 行：{card} 已经挂在任务 {seen_cards[card]} 上，一张卡只对一个原子任务"
                )
                continue
        evidence = tuple(BACKTICK.findall(evidence_cell))
        if evidence_cell and not evidence:
            plan.problems.append(f"第 {number} 行：证据一格有字但没有反引号包着的路径")
            continue
        unsafe = [path for path in evidence if not _safe_relative(path)]
        if unsafe:
            plan.problems.append(
                f"第 {number} 行：证据路径要写相对项目目录的路径：{'、'.join(unsafe)}"
            )
            continue
        if by_user and not evidence:
            plan.problems.append(
                f"第 {number} 行：写“{BY_USER}”的任务必须列证据路径（用户交的东西放哪）"
            )
            continue
        seen_tasks[task_id] = number
        if card:
            seen_cards[card] = task_id
        current.tasks.append(Task(task_id, title, card, applicable, by_user, evidence, number))
    known = {milestone.milestone_id for milestone in plan.milestones}
    for acceptance in plan.acceptances:
        if acceptance.milestone_id not in known:
            plan.problems.append(f"验收记录里的里程碑 {acceptance.milestone_id} 在计划表里没有")
    if not plan.milestones:
        plan.problems.append("没读到任何里程碑（标题要像 ## L1 立项）")
    return plan


def project_root_of(root: Path, pid: str) -> str | None:
    """项目登记表里这个项目的目录（相对控制根，正斜杠）；查不到返回 None。"""
    try:
        data = json.loads((root / REGISTRY).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    for project in data.get("projects", []) if isinstance(data, dict) else []:
        if isinstance(project, dict) and project.get("project_id") == pid:
            value = str(project.get("project_root", "")).replace("\\", "/").strip("/")
            return value or None
    return None


def evaluate(plan: Plan, facts: Any, project_dir: str) -> dict[str, Any]:
    """算出每个任务、每个里程碑的状态。``facts`` 是已经取过数的 card_status.GitFacts。"""
    accepted = {item.milestone_id: item for item in plan.acceptances}
    milestones: list[dict[str, Any]] = []
    for milestone in plan.milestones:
        rows: list[dict[str, Any]] = []
        for task in milestone.tasks:
            paths = tuple(f"{project_dir}/{path}" for path in task.evidence)
            if not task.applicable:
                status, reasons, detail = NOT_APPLICABLE, ["计划表写明不适用"], None
            elif task.card:
                result = facts.card_status(task.card, paths)
                status, reasons, detail = result.status, list(result.reasons), result.as_json()
            elif not facts.snapshot.ok:
                status, reasons, detail = card_status.UNKNOWN, ["远程没读到，没法判断"], None
            else:
                missing = [path for path in paths if not (facts.file_text(path) or "").strip()]
                if task.by_user and not missing:
                    status, reasons = USER_DELIVERED, ["用户交的文件都在，等里程碑验收时由用户确认"]
                elif task.by_user:
                    status, reasons = M_NOT_STARTED, ["等用户本人放入：" + "、".join(missing)]
                elif paths and not missing:
                    status, reasons = HAS_FILES, ["文件都在，但没挂实施卡，没人验证过"]
                elif not paths:
                    status, reasons = M_NOT_STARTED, ["没挂实施卡，也没列文件"]
                else:
                    status, reasons = (
                        M_NOT_STARTED,
                        ["没挂实施卡；文件不在或是空的：" + "、".join(missing)],
                    )
                detail = None
            rows.append(
                {
                    "task_id": task.task_id,
                    "title": task.title,
                    "card": task.card,
                    "status": status,
                    "reasons": reasons,
                    "detail": detail,
                }
            )
        counted = [row for row in rows if row["status"] != NOT_APPLICABLE]
        done = [row for row in counted if row["status"] in (card_status.DONE, USER_DELIVERED)]
        unknown = [row for row in counted if row["status"] == card_status.UNKNOWN]
        moving = [
            row
            for row in counted
            if row["status"]
            in (
                card_status.IN_PROGRESS,
                card_status.MERGED,
                card_status.DONE,
                HAS_FILES,
                USER_DELIVERED,
            )
        ]
        if counted and len(unknown) == len(counted):
            state = card_status.UNKNOWN
        elif counted and len(done) == len(counted):
            state = M_REACHED if milestone.milestone_id in accepted else M_WAITING
        elif moving:
            state = M_RUNNING
        else:
            state = M_NOT_STARTED
        entry: dict[str, Any] = {
            "milestone_id": milestone.milestone_id,
            "title": milestone.title,
            "status": state,
            "tasks_total": len(counted),
            "tasks_done": len(done),
            "tasks_unknown": len(unknown),
            "tasks": rows,
        }
        if milestone.milestone_id in accepted:
            record = accepted[milestone.milestone_id]
            entry["acceptance"] = {"when": record.when, "proof": record.proof}
            if state != M_REACHED:
                entry["acceptance_note"] = "有验收记录，但任务没有全部已完成，不算已达成"
        milestones.append(entry)
    return {"milestones": milestones}


def render(report: dict[str, Any], out: Callable[[str], None]) -> None:
    out(f"【项目计划状态】{report['pid']}")
    out(report["snapshot"])
    out(f"计划表：{report['plan_file']}")
    out("")
    out("| 里程碑 | 状态 | 任务数 | 已完成或用户已交 | 没查到 |")
    out("|---|---|---|---|---|")
    for milestone in report["milestones"]:
        out(
            f"| {milestone['milestone_id']} {milestone['title']} | {milestone['status']} | "
            f"{milestone['tasks_total']} | {milestone['tasks_done']} | {milestone['tasks_unknown']} |"
        )
    for milestone in report["milestones"]:
        out("")
        out(f"## {milestone['milestone_id']} {milestone['title']}：{milestone['status']}")
        if "acceptance_note" in milestone:
            out(f"> {milestone['acceptance_note']}")
        out("| 编号 | 原子任务 | 实施卡 | 状态 | 依据 |")
        out("|---|---|---|---|---|")
        for row in milestone["tasks"]:
            out(
                f"| {row['task_id']} | {row['title']} | {row['card'] or '—'} | {row['status']} | "
                f"{'；'.join(row['reasons'])} |"
            )
    if report["problems"]:
        out("")
        out(f"✗ 计划表有 {len(report['problems'])} 处格式问题（这些行没算进去）：")
        for problem in report["problems"]:
            out(f"  - {problem}")


def run(
    pid: str,
    *,
    root: Path,
    offline: bool = False,
    as_json: bool = False,
    plan_file: Path | None = None,
    facts: Any = None,
    out: Callable[[str], None] = print,
) -> int:
    if not PID_PATTERN.match(pid):
        out(f"项目号格式不对：{pid!r}（应像 DJ-2026-005），什么都没算")
        return 2
    project_dir = project_root_of(root, pid)
    if project_dir is None:
        out(f"项目登记表里查不到 {pid}（{root / REGISTRY}），什么都没算")
        return 2
    source = facts if facts is not None else card_status.GitFacts(root)
    snapshot = source.refresh(offline=offline)
    if plan_file is not None:
        try:
            text: str | None = plan_file.read_text(encoding="utf-8-sig")
        except OSError as error:
            out(f"计划表读不了：{plan_file}（{type(error).__name__}: {error}）")
            return 2
        shown = f"{plan_file}（本机文件，--plan-file 指定）"
    elif not snapshot.ok:
        out(f"【项目计划状态】{pid}")
        out(f"✗ {snapshot.describe()}")
        out(
            "没查到：远程读不到，计划表和各卡状态都没法算。联网后再跑；要用本机旧数据就加 --offline。"
        )
        return 1
    else:
        suffix = PLAN_SUFFIX.format(pid=pid)
        found = [
            path
            for path in source.list_paths(f"{project_dir}/{PLAN_DIR}/")
            if path.endswith(suffix)
        ]
        if not found:
            out(f"【项目计划状态】{pid}")
            out(snapshot.describe())
            out(
                f"这个项目在 main 上还没有项目计划表（{project_dir}/{PLAN_DIR}/NNN{suffix}），没有可算的。"
            )
            return 0
        if len(found) > 1:
            out(f"{pid} 有 {len(found)} 张项目计划表，只能有一张：{'、'.join(found)}")
            return 1
        text = source.file_text(found[0])
        shown = f"{found[0]}（main 上的版本）"
        if text is None:
            out(f"计划表读不了：{found[0]}")
            return 1
    plan = parse_plan(text or "", pid)
    report: dict[str, Any] = {
        "pid": pid,
        "snapshot": snapshot.describe(),
        "snapshot_ok": snapshot.ok,
        "offline": snapshot.offline,
        "ref_commit": snapshot.commit,
        "plan_file": shown,
        "problems": plan.problems,
        **evaluate(plan, source, project_dir),
    }
    if as_json:
        out(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        render(report, out)
    return 1 if (plan.problems or not snapshot.ok) else 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="项目计划状态：按实施卡号现算，只显示")
    parser.add_argument("pid")
    parser.add_argument(
        "--root", type=Path, default=DEFAULT_ROOT, help="控制根（默认按本脚本位置往上找）"
    )
    parser.add_argument("--json", dest="as_json", action="store_true", help="只输出 JSON")
    parser.add_argument(
        "--offline", action="store_true", help="不联网，用本机上次取回的数据算（结果里会写明）"
    )
    parser.add_argument("--plan-file", type=Path, default=None, help="合并前试一张本机的计划表")
    options = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")  # 只影响显示，中文在 GBK 终端不致崩
    return run(
        options.pid,
        root=options.root.resolve(),
        offline=options.offline,
        as_json=options.as_json,
        plan_file=options.plan_file,
    )


if __name__ == "__main__":
    raise SystemExit(main())
