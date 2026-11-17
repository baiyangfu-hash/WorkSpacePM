"""自动流程第一批（WBS 10.6）：“项目体检”“交卷到收口”和“进门”，只按顺序调现有的驾驶舱命令。

用法（在控制根，用控制根 .venv 里的 Python；Windows 是 .venv\\Scripts\\python.exe）：
  python <本项目>/scripts/pm_flows.py entry <项目号>
  python <本项目>/scripts/pm_flows.py checkup <项目号>
  python <本项目>/scripts/pm_flows.py closeout <项目号> --mission-id <卡号> [--done <已做完的一步>]
  python <本项目>/scripts/pm_flows.py steps <entry|checkup|closeout>

“进门”（新对话、换班接手时跑，全程只读）＝项目体检的每一步，加 ``claim list`` 看占位表，再对登记路径落在
本项目目录里的每张卡跑 ``claim log``，最后列出交接记录的最后三行和“先读”的文件，再按卡类型提示该读哪个角色包
（控制根 ``roles/`` 下每个有 ``role.json`` 的包；本项目的卡按登记路径对上包里的 ``owned_paths_patterns``）。
“steps”只列出一个流程的每一步和整条命令，一条都不跑，也不写运行记录。

规矩（协调者 2026-11-14 01:35Z 裁定的做法，这里照做）：
1. 只串联：每一步都是一条现成的 ``main.py`` 命令，原样运行，原样显示输出和退出码；脚本不判断、不改写结果。
   两处例外，都只读：体检最后一步“工作区根目录清洁”是脚本自己看一眼控制根顶层有没有临时文件（DEV-TMP-001），
   有就提醒，不算红、不删；“进门”从 ``claim list --json`` 的输出里挑出路径落在本项目目录里的卡，再逐张跑 ``claim log``；
   进门最后的角色包提示也是脚本自己读控制根 ``roles/*/role.json``，只提示，不算红。
2. 退出码不是 0 就算这一步红。“交卷到收口”停在红的那一步，报出整条命令和退出码，后面的不跑；
   “项目体检”全是只读，每一步都跑完，最后出小结表点名红的步骤和命令，有红就退出 1（协调者 03:55Z 裁定）。
   项目号、卡号格式不对直接报用法错，一条命令都不跑。
   退出码：0＝走完；1＝有一步红了；2＝用法或环境不对（项目号、卡号、``--done`` 停点名写错，或控制根没有
   ``main.py``），一条命令都没跑；3＝停在停点，等人做完那一步再带 ``--done`` 接着走（不是走完，也不是失败）。
3. “项目体检”全程只读。“交卷到收口”只跑只读的检查；每个会改状态的步骤前都停下，打印要用户本人说的话
   和那一步的命令，由用户或经用户同意的 agent 去跑，跑完再带 ``--done`` 接着走。推到完成那一步永远不由脚本执行。
4. 每次运行都在控制根 ``.auto-pm/reports/flows/`` 落一份运行记录（时间、项目号、逐步命令原文、退出码、停在哪一步）。
5. 解释器：不靠 PATH 上的 ``python``。和看板的 bat 一样先找控制根的 ``.venv``，没有才用运行本脚本的这个 Python；
   入口一律是控制根的 ``main.py``（它再转给现役发布）。

本脚本不进发布载荷，不进 ``workflow history``；以后工作流引擎补上传参和中途停等后再迁进引擎（另立任务）。
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = PROJECT_ROOT.parents[3]
CATALOG_SCRIPT = PROJECT_ROOT / "scripts" / "command_catalog.py"
PLAN_SCRIPT = PROJECT_ROOT / "scripts" / "plan_status.py"
REGISTRY = Path("SYS-2026-001_WorkspaceGovernance") / "workspace_registry.json"
REPORTS = Path(".auto-pm") / "reports" / "flows"
PLC_ROOT = "0100_PLC自动化/"
STEP_TIMEOUT = 900
OUTPUT_TAIL = 60

# 只在 PLC 项目上跑的步骤（项目登记表里 project_root 在 0100_PLC自动化/ 下）。
PLC_ONLY = "plc"

# 项目号和卡号的格式（项目号同 auto_pm/domain/models/project.py，卡号同 auto_pm/contracts/orchestration.py）。
# 不合格就报用法错、一条命令都不跑：防止把 ``--fix`` 这类开关当项目号带进只读命令。
PID_PATTERN = re.compile(r"^[A-Z]{2,4}-\d{4}-\d{3}$")
MISSION_PATTERN = re.compile(r"^MISSION-[A-Z0-9-]+$")

# 一步红了还接着跑的流程：体检和进门全只读，是一张报警一览，红了也要看到后面几步（协调者 03:55Z 裁定）。
KEEP_GOING = frozenset({"checkup", "entry"})

# 工作区根目录清洁（DEV-TMP-001 第 1、3 条）：控制根顶层不该留这些。只看顶层，只提醒，不删。
ROOT_LITTER_PREFIXES = ("tmp_",)
ROOT_LITTER_NAMES = frozenset({".coverage", "htmlcov", ".pytest_cache", "coverage.xml"})
ROOT_LITTER_SUFFIXES = (".log", ".tmp")

# 进门最后按卡类型提示该读哪个角色包（CHG-SCPT-2026-711）。包的正本在控制根 roles/<角色号>/，规范、命令、门禁和
# 可改范围上限（owned_paths_patterns）在包里的 role.json；这里只记每个包对应哪类卡。roles/ 下新加一个包，这张表就要
# 加一行，否则 tests/core/test_role_pack_wiring.py 红。
ROLES_DIR = Path("roles")
ROLE_CARD_TYPES: Mapping[str, str] = {
    "plc-electrical-engineer": "PLC 卡（SCL/ST 程序、点表和接口文档）",
    "fullstack-engineer": "Python 卡（上位机、驾驶舱、脚本和测试）",
    "test-engineer": "审计卡、测试验证卡（审 PR、跑门禁）",
    "ui-designer": "画面卡（HTML 原型、HMI 画面、QML 视图）",
    "product-pm": "计划卡（需求、计划、派活、验收和收口）",
}

# 旧发布版本没有交接记录命令时 click 报的原话（AGENTS.md FLOW-002 进门三步）。
NO_LOG_COMMAND = "No such command 'log'"


@dataclass(frozen=True)
class Step:
    """流程里的一步。

    kind 为 ``run``：脚本运行这条只读命令。kind 为 ``stop``：脚本停下，只打印这条命令和要用户本人说的话。
    args 里的 ``{pid}``、``{mission}`` 运行时换成项目号和卡号；``{catalog}`` 表示运行命令目录脚本而不是 main.py；
    ``{plan}`` 表示运行项目计划状态脚本（WBS 8.8，只算只显示，控制根由本脚本补上）。
    """

    key: str
    label: str
    args: tuple[str, ...]
    kind: str = "run"
    who: str = ""
    say: str = ""
    only: str = ""
    note: str = ""


CHECKUP: tuple[Step, ...] = (
    Step("orient", "定位", ("pm", "orient", "{pid}")),
    Step("control_root", "控制根状态", ("pm", "control-root-status", "{pid}")),
    Step("missions", "开着的卡", ("pm", "missions", "--pid", "{pid}")),
    Step(
        "reconcile", "对账", ("ledger", "reconcile", "{pid}"), note="不带 --fix，只报差异，不写台账"
    ),
    Step("plc_check", "程序检查", ("plc", "check", "{pid}"), only=PLC_ONLY, note="不带 --fix"),
    Step("doc_check", "文档检查", ("doc", "check")),
    Step("plc_docs", "接口和变量文档检查", ("plc", "docs", "check", "{pid}"), only=PLC_ONLY),
    Step("prototype", "原型检查", ("prototype", "check", "--pid", "{pid}"), only=PLC_ONLY),
    Step(
        "plan",
        "项目计划状态",
        ("{plan}", "{pid}"),
        note="按实施卡号现算每个任务、每个里程碑的状态，只显示；项目还没有计划表时说明一句，不算红",
    ),
    Step(
        "catalog",
        "当前命令目录",
        ("{catalog}", "--print"),
        note="现场生成，存进运行记录目录，不入库",
    ),
    Step(
        "root_clean",
        "工作区根目录清洁",
        ("{rootclean}",),
        note="脚本自己看控制根顶层有没有 tmp_*、.coverage、htmlcov 这类临时文件；有就提醒，不算红，不删",
    ),
)

# 进门：体检全部步骤，再看占位表；占位表之后对本项目的每张卡跑 claim log（运行时按占位表补上）。
CLAIM_LIST = Step(
    "claims",
    "占位表",
    ("claim", "list", "--json"),
    note="找出登记路径落在本项目目录里、还没放下的卡（租约到期但没放下的也算，交接记录照样要读）",
)
ENTRY: tuple[Step, ...] = (*CHECKUP, CLAIM_LIST)

CLOSEOUT: tuple[Step, ...] = (
    Step("acceptance_scan", "验收命令预检", ("pm", "acceptance-scan", "--pid", "{pid}")),
    Step("control_root", "控制根状态", ("pm", "control-root-status", "{pid}")),
    Step(
        "verify",
        "验证",
        ("pm", "verify", "--mission-id", "{mission}", "--lease-wallet"),
        kind="stop",
        who="经用户同意后由 agent 运行",
        say="同意 {mission} 交卷验证",
    ),
    Step("missions_after_verify", "看卡的状态", ("pm", "missions", "--pid", "{pid}")),
    Step(
        "accept",
        "验收",
        ("pm", "accept", "--mission-id", "{mission}"),
        kind="stop",
        who="只有用户本人",
        say="（用户本人在驾驶舱看板点“确认验收”，验收和收口一步做完，之后用 --done close；"
        "或在自己的终端运行这条命令，之后用 --done accept）",
    ),
    Step(
        "close",
        "收口",
        ("pm", "close", "--mission-id", "{mission}"),
        kind="stop",
        who="经用户同意后由 agent 运行",
        say="同意 {mission} 收口",
    ),
    Step("settle_scan", "合并后收口清单", ("pr", "settle-scan", "{pid}")),
    Step(
        "transition",
        "变更单推到完成",
        ("change", "transition", "<变更单号，见上一步输出>", "--to", "completed", "--pid", "{pid}"),
        kind="stop",
        who="只有用户本人；本脚本永远不执行这一步",
        say="（看板“推到完成”按钮合并前：用户本人在本地主力对话里说“把 <变更单号> 推到完成”；"
        "合并后：用户本人在看板“决定”页点“推到完成”）",
    ),
    Step(
        "reconcile", "对账", ("ledger", "reconcile", "{pid}"), note="不带 --fix，只报差异，不写台账"
    ),
    Step(
        "worktree",
        "收工位",
        ("worktree", "close", "<agent 名>"),
        kind="stop",
        who="经用户同意后由 agent 运行",
        say="同意收工位",
    ),
)

FLOWS: Mapping[str, tuple[Step, ...]] = {"entry": ENTRY, "checkup": CHECKUP, "closeout": CLOSEOUT}
FLOW_NAMES = {"entry": "进门", "checkup": "项目体检", "closeout": "交卷到收口"}

# 分类表里归“写”、但读码确认不带写开关时只读的命令。每条写明依据；测试核它们在流程里不带写开关。
READ_BY_CODE: Mapping[str, str] = {
    "ledger reconcile": "auto_pm/ui/cli/ledger.py：只有 --fix 才校验身份并写台账，不带时只报差异（代码注释“the plain report stays a read”）",
    "prototype check": "auto_pm/application/core/prototype_service.py 的 check()：只打开原型文件读，不写",
}


@dataclass
class StepResult:
    """运行记录里的一步。"""

    number: int
    key: str
    label: str
    command: str
    rc: int | None = None
    seconds: float = 0.0
    status: str = ""
    output_tail: list[str] = field(default_factory=list)


Runner = Callable[..., Any]


def resolve_python(root: Path, os_name: str | None = None) -> Path:
    """控制根 .venv 里的 Python（和看板 bat 同一找法）；没有就用运行本脚本的 Python。绝不用 PATH 上的 python。"""
    name = os.name if os_name is None else os_name
    candidate = root / ".venv" / ("Scripts/python.exe" if name == "nt" else "bin/python")
    return candidate if candidate.is_file() else Path(sys.executable)


def project_root_of(root: Path, pid: str) -> str | None:
    """项目登记表里这个项目的目录（仓库根起，正斜杠，不带末尾斜杠）；读不到登记表或查不到项目返回 None。"""
    try:
        data = json.loads((root / REGISTRY).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    for project in data.get("projects", []):
        if isinstance(project, dict) and project.get("project_id") == pid:
            return str(project.get("project_root", "")).replace("\\", "/").strip("/") or None
    return None


def is_plc_project(root: Path, pid: str) -> bool | None:
    """项目登记表里这个项目在 0100_PLC自动化/ 下返回 True；读不到登记表或查不到项目返回 None。"""
    project_root = project_root_of(root, pid)
    return None if project_root is None else (project_root + "/").startswith(PLC_ROOT)


def root_litter(root: Path) -> list[str]:
    """控制根顶层的临时文件名（DEV-TMP-001），按名字排好；只看不删。"""
    try:
        names = sorted(entry.name for entry in root.iterdir())
    except OSError:
        return []
    return [
        name
        for name in names
        if name in ROOT_LITTER_NAMES
        or name.startswith(ROOT_LITTER_PREFIXES)
        or name.endswith(ROOT_LITTER_SUFFIXES)
    ]


def project_cards(claims: Any, project_root: str) -> tuple[list[dict[str, Any]], int]:
    """占位表（``claim list --json`` 的输出）里，有登记路径落在 ``project_root`` 下、还没放下的卡（按卡号排好），
    和落在本项目下但已放下（status ``released``，PR 已合、卡已收）的张数。租约到期但没放下的照样算：交接记录还要读。
    """
    if not isinstance(claims, list):
        raise ValueError("占位表不是列表")
    prefix = project_root.rstrip("/") + "/"
    picked = []
    released = 0
    for claim in claims:
        if not isinstance(claim, dict) or not isinstance(claim.get("card"), str):
            raise ValueError("占位表里有一项缺卡号")
        paths = [str(path).replace("\\", "/").lstrip("/") for path in claim.get("paths") or []]
        if not any(path == project_root or path.startswith(prefix) for path in paths):
            continue
        if claim.get("status") == "released":
            released += 1
        else:
            picked.append(claim)
    return sorted(picked, key=lambda claim: str(claim["card"])), released


def role_packs(root: Path) -> list[dict[str, Any]]:
    """控制根 ``roles/`` 下每个有 ``role.json`` 和 ``SKILL.md`` 的角色包，按 ``ROLE_CARD_TYPES`` 的顺序排（表外的排最后）。

    每项：角色号、岗位名（role.json 的 title）、卡类型、``SKILL.md`` 的路径（控制根起，正斜杠）、可改范围上限的模式。
    读不到或读不懂的包跳过（``main.py role check`` 会报它）。
    """
    try:
        folders = sorted(path for path in (root / ROLES_DIR).iterdir() if path.is_dir())
    except OSError:
        return []
    order = list(ROLE_CARD_TYPES)
    packs: list[dict[str, Any]] = []
    for folder in folders:
        if not (folder / "SKILL.md").is_file():
            continue
        try:
            config = json.loads((folder / "role.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(config, dict):
            continue
        patterns = config.get("owned_paths_patterns")
        packs.append(
            {
                "id": folder.name,
                "title": str(config.get("title", folder.name)),
                "card_type": ROLE_CARD_TYPES.get(folder.name, "（进门表里还没登记这类卡）"),
                "skill": f"{ROLES_DIR.as_posix()}/{folder.name}/SKILL.md",
                "patterns": [str(item) for item in patterns] if isinstance(patterns, list) else [],
            }
        )
    return sorted(
        packs, key=lambda pack: order.index(pack["id"]) if pack["id"] in order else len(order)
    )


def _path_matches(path: str, pattern: str) -> bool:
    """``**/*.py`` 这类模式也认仓库根下的 ``a.py``；``*`` 跨目录（同 fnmatch）。"""
    candidates = [pattern]
    if pattern.startswith("**/"):
        candidates.append(pattern[3:])
    return any(fnmatch.fnmatchcase(path, candidate) for candidate in candidates)


def packs_for_paths(packs: Sequence[Mapping[str, Any]], paths: Sequence[str]) -> list[str]:
    """登记路径对得上哪些包的可改范围上限，按包的顺序给角色号；一个都对不上返回空。"""
    clean = [str(path).replace("\\", "/").lstrip("/") for path in paths]
    return [
        str(pack["id"])
        for pack in packs
        if any(_path_matches(path, pattern) for path in clean for pattern in pack["patterns"])
    ]


def _print_role_hints(
    packs: Sequence[Mapping[str, Any]],
    cards: Sequence[Mapping[str, Any]],
    out: Callable[[str], None],
) -> list[dict[str, Any]]:
    """进门最后一段：按卡类型该读哪个角色包；本项目的每张卡按登记路径猜一个。返回写进运行记录的那几行。"""
    out("\n【该读哪个角色包】（按卡类型；包里要守的规范、能用的命令、门禁在同目录 role.json）")
    if not packs:
        out("控制根里没有 roles/ 角色包，没法提示；先跑 main.py role check 看看。")
        return []
    for pack in packs:
        out(f"- {pack['card_type']}：{pack['skill']}（{pack['title']}）")
    by_id = {str(pack["id"]): pack for pack in packs}
    hints: list[dict[str, Any]] = []
    if cards:
        out("本项目的卡（按登记路径猜，是提示不是状态；对不上就按卡的目标照上表挑）：")
    for card in cards:
        matched = packs_for_paths(packs, card.get("paths") or [])
        hints.append({"card": str(card["card"]), "roles": matched})
        shown_roles = "、".join(str(by_id[role]["skill"]) for role in matched)
        out(
            f"  {card['card']}：{shown_roles}"
            if matched
            else f"  {card['card']}：登记路径认不出卡类型（多半是文档或计划），按上表对卡的目标挑"
        )
    return hints


def handover_lines(text: str) -> dict[str, str]:
    """``claim log`` 输出末尾的三行（最后一笔、下一棒、先读），原话照抄；没有交接记录时返回空。"""
    found: dict[str, str] = {}
    for line in text.splitlines():
        for label in ("最后一笔", "下一棒", "先读"):
            if line.startswith(label + "："):
                found[label] = line[len(label) + 1 :]
    return found


def _fill(args: Sequence[str], pid: str, mission: str) -> list[str]:
    return [arg.replace("{pid}", pid).replace("{mission}", mission) for arg in args]


def command_of(step: Step, python: Path, root: Path, pid: str, mission: str) -> list[str]:
    """一步对应的整条命令（列表，不经过 shell）。"""
    args = _fill(step.args, pid, mission)
    if args and args[0] == "{plan}":
        return [str(python), "-B", str(PLAN_SCRIPT), *args[1:], "--root", str(root)]
    if args and args[0] == "{catalog}":
        return [str(python), "-B", str(CATALOG_SCRIPT), *args[1:]]
    return [str(python), "-B", str(root / "main.py"), *args]


def shown(command: Sequence[str]) -> str:
    return (
        subprocess.list2cmdline(list(command))
        if os.name == "nt"
        else " ".join(f'"{part}"' if (" " in part or not part) else part for part in command)
    )


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# 退出码（见文件头规矩第 2 条）。
EXIT_DONE = 0
EXIT_RED = 1
EXIT_USAGE = 2
EXIT_STOPPED = 3


def _stage_index(steps: Sequence[Step], done: str) -> int | None:
    """--done 给的那一步之后从哪一步开始；停点名不对返回 None。"""
    if not done:
        return 0
    for index, step in enumerate(steps):
        if step.key == done and step.kind == "stop":
            return index + 1
    return None


def _print_handover(handover: Sequence[Mapping[str, Any]], out: Callable[[str], None]) -> None:
    """进门最后一段：每张卡交接记录的最后三行（原话），和接手前先读的文件。"""
    out("\n【交接记录】（下面是记录里的原话，不是状态；卡的状态看上面的体检和占位表）")
    if not handover:
        out("本项目目录下没有没放下的占位，没有交接记录要读。")
        return
    read_first: list[str] = []
    for item in handover:
        free = "（占位已放下或租约到期）" if item.get("free") else ""
        out(f"- {item['card']}{free}")
        if "最后一笔" not in item:
            out(
                f"  {item['note']}。"
                if item.get("note")
                else "  这张卡还没有交接记录，或记录没读出来（看上面那一步的输出）。"
            )
            continue
        for label in ("最后一笔", "下一棒", "先读"):
            out(f"  {label}：{item.get(label, '')}")
        for path in str(item.get("先读", "")).split("、"):
            if path and path != "无" and path not in read_first:
                read_first.append(path)
    if read_first:
        out("接手前先读完这些文件，再向用户报告，不要直接动手：")
        for path in read_first:
            out(f"  {path}")


def print_steps(flow: str, out: Callable[[str], None] = print) -> int:
    """只列出一个流程的每一步和整条命令（项目号写成 <项目编号>），一条都不跑，不写运行记录。"""
    out(f"【{FLOW_NAMES[flow]}】的步骤（只列不跑）：")
    out("| 步 | 名字 | 命令 | 谁来做 | 说明 |")
    out("|---|---|---|---|---|")
    rows = list(FLOWS[flow])
    for number, step in enumerate(rows, start=1):
        args = [
            arg.replace("{pid}", "<项目编号>").replace("{mission}", "<卡号>") for arg in step.args
        ]
        if args[0] == "{plan}":
            command = f"scripts/plan_status.py {' '.join(args[1:])}（驾驶舱项目的 scripts 目录）"
        elif args[0] == "{catalog}":
            command = (
                f"scripts/command_catalog.py {' '.join(args[1:])}（驾驶舱项目的 scripts 目录）"
            )
        elif args[0] == "{rootclean}":
            command = "（脚本自己看控制根顶层）"
        else:
            command = "main.py " + " ".join(args)
        who = step.who or "脚本跑（只读）"
        note = "；".join(
            part for part in (step.note, "只 PLC 项目" if step.only == PLC_ONLY else "") if part
        )
        out(f"| {number} | {step.label} | `{command}` | {who} | {note} |")
    if flow == "entry":
        out(
            f"| {len(rows) + 1}… | 交接记录 | `main.py claim log <卡号>` | 脚本跑（只读） | "
            "对上一步挑出的每张卡各跑一次，最后列出最后三行和先读的文件 |"
        )
        out(
            f"| {len(rows) + 2}… | 角色包提示 | （脚本自己读控制根 roles/*/role.json） | 脚本（只读） | "
            "按卡类型列出该读哪个角色包，本项目的卡按登记路径猜一个；只提示，不算红 |"
        )
    return EXIT_DONE


def run_flow(
    flow: str,
    pid: str,
    *,
    root: Path,
    mission: str = "",
    done: str = "",
    runner: Runner = subprocess.run,
    out: Callable[[str], None] = print,
) -> int:
    """按顺序跑一个流程。返回 0＝走完；1＝有一步红了；2＝用法或环境不对（一条命令都没跑）；3＝停在停点。

    “项目体检”和“进门”每一步都跑完，最后出小结表，任一步红就退出 1；“交卷到收口”一步红就停在那一步。
    根目录清洁只提醒，不算红。
    """
    steps = FLOWS[flow]
    if not PID_PATTERN.match(pid):
        out(f"项目号格式不对：{pid!r}（应像 DJ-2026-005），一条命令都没跑")
        return EXIT_USAGE
    if flow == "closeout" and not MISSION_PATTERN.match(mission):
        out(f"卡号格式不对：{mission!r}（应像 MISSION-3E5ED659C44DE219），一条命令都没跑")
        return EXIT_USAGE
    if not (root / "main.py").is_file():
        out(f"控制根里没有 main.py：{root}（请在控制根运行，或用 --root 指过去）")
        return EXIT_USAGE
    start = _stage_index(steps, done)
    if start is None:
        stops = "、".join(s.key for s in steps if s.kind == "stop") or "（这个流程没有停点）"
        out(f"--done 写的停点名不对：{done!r}；只认这些停点：{stops}。一条命令都没跑")
        return EXIT_USAGE
    python = resolve_python(root)
    plc = is_plc_project(root, pid)
    record: dict[str, Any] = {
        "flow": flow,
        "flow_name": FLOW_NAMES[flow],
        "pid": pid,
        "mission": mission,
        "done": done,
        "started": _now(),
        "root": str(root),
        "interpreter": str(python),
        "entry": str(root / "main.py"),
        "steps": [],
        "stopped_at": None,
        "result": "",
    }
    reports = root / REPORTS
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    record_path = reports / f"{stamp}_{flow}_{pid}.json"
    out(
        f"【{FLOW_NAMES[flow]}】项目 {pid}"
        + (f"，卡 {mission}" if mission else "")
        + f"；解释器 {python}"
    )
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    code = EXIT_DONE
    queue = list(steps[start:])
    number = start
    finished = True
    handover: list[dict[str, Any]] = []
    project_claims: list[dict[str, Any]] = []
    while queue:
        step = queue.pop(0)
        number += 1
        if step.args[0] == "{rootclean}":
            result = StepResult(number, step.key, step.label, "（脚本自己看控制根顶层，不跑命令）")
            litter = root_litter(root)
            result.status = "提醒" if litter else "通过"
            result.output_tail = (
                [f"根目录有临时文件：{'、'.join(litter)}（DEV-TMP-001：用完就删；本脚本不删）"]
                if litter
                else ["根目录没有临时文件"]
            )
            record["steps"].append(result.__dict__)
            out(f"\n▶ 第 {number} 步「{step.label}」：{result.command}")
            for line in result.output_tail:
                out(f"  {line}")
            continue
        command = command_of(step, python, root, pid, mission)
        result = StepResult(number, step.key, step.label, shown(command))
        if step.kind == "stop":
            result.status = "停点"
            record["steps"].append(result.__dict__)
            record["stopped_at"] = {
                "number": number,
                "key": step.key,
                "label": step.label,
                "next_command": result.command,
                "who": step.who,
                "say": _fill((step.say,), pid, mission)[0],
                "resume": f"做完后带 --done {step.key} 再运行本流程",
            }
            record["result"] = "停在停点"
            out(f"\n⏸ 第 {number} 步「{step.label}」会改状态，脚本停在这里。")
            out(f"  谁来做：{step.who}")
            if step.say:
                out(f"  要用户本人说的话：{record['stopped_at']['say']}")
            out(f"  这一步的命令：{result.command}")
            out(f"  做完后接着走：在原命令后面加 --done {step.key}")
            code = EXIT_STOPPED
            finished = False
            break
        if step.only == PLC_ONLY and plc is not True:
            result.status = (
                "跳过（不是 PLC 项目）"
                if plc is False
                else "跳过（登记表里查不到这个项目，没法判断是不是 PLC 项目）"
            )
            record["steps"].append(result.__dict__)
            out(f"\n· 第 {number} 步「{step.label}」{result.status}")
            continue
        out(f"\n▶ 第 {number} 步「{step.label}」：{result.command}")
        began = time.monotonic()
        stdout = ""
        try:
            completed = runner(
                command,
                cwd=str(root),
                capture_output=True,
                encoding="utf-8",
                errors="replace",  # 输出只用于显示和记录，生僻字节不致崩
                timeout=STEP_TIMEOUT,
                check=False,
                stdin=subprocess.DEVNULL,
                env=env,
            )
            result.rc = int(completed.returncode)
            stdout = completed.stdout or ""
            text = stdout + (completed.stderr or "")
        except subprocess.TimeoutExpired:
            text = f"超过 {STEP_TIMEOUT} 秒没跑完，已停"
        except OSError as error:
            text = f"起不来：{type(error).__name__}: {error}"
        result.seconds = round(time.monotonic() - began, 2)
        lines = text.splitlines()
        if step.key == "claims" and result.rc == 0:
            project_root = project_root_of(root, pid)
            released = 0
            try:
                cards, released = project_cards(json.loads(stdout), project_root or "")
            except ValueError as error:
                lines = [f"占位表的输出读不懂（{error}），没法挑出本项目的卡", *lines[:OUTPUT_TAIL]]
                result.rc = None
                cards = []
            else:
                if project_root is None:
                    lines = ["登记表里查不到这个项目的目录，没法挑出本项目的卡；不跑交接记录"]
                    cards = []
                else:
                    lines = [f"本项目目录：{project_root}"] + (
                        [
                            f"{claim['card']} 持有人 {claim.get('owner', '')} 领卡 {claim.get('claimed_at', '')}"
                            + ("（已放下或租约到期，视为空闲）" if claim.get("free") else "")
                            for claim in cards
                        ]
                        or ["本项目目录下没有没放下的占位"]
                    )
                    if released:
                        lines.append(
                            f"另有 {released} 张已放下的卡（PR 已合、卡已收），不读交接记录"
                        )
                project_claims = list(cards)
                for claim in cards:
                    card = str(claim["card"])
                    handover.append({"card": card, "free": bool(claim.get("free"))})
                    queue.append(Step("claim_log", f"交接记录 {card}", ("claim", "log", card)))
        if step.key == "claim_log" and result.rc == 0:
            for item in handover:
                if item["card"] == step.args[2]:
                    item.update(handover_lines(stdout))
        if step.key == "claim_log" and result.rc != 0 and NO_LOG_COMMAND in text:
            # 本机生效的发布版本还没有交接记录命令：后面几张卡结果一样，不再跑；照实报，不绕过（FLOW-002）。
            skipped = [later for later in queue if later.key == "claim_log"]
            queue = [later for later in queue if later.key != "claim_log"]
            lines.append(
                "本机生效的发布版本还没有交接记录命令（claim log）：照实告诉用户，不要绕过去；"
                + (f"后面 {len(skipped)} 张卡的交接记录也读不了，不再跑" if skipped else "")
            )
            for item in handover:
                item.setdefault("note", "发布版本没有 claim log，没读")
        result.output_tail = lines[-OUTPUT_TAIL:]
        # 进门时命令目录不刷屏：全文照样存进运行记录目录，屏幕上只说存在哪。
        quiet = flow == "entry" and step.key == "catalog" and result.rc == 0
        for line in [] if quiet else lines:
            out(f"  {line}")
        if step.key == "catalog" and result.rc == 0:
            catalog_path = reports / f"{stamp}_{flow}_{pid}_命令目录.md"
            result.output_tail = [f"全文存在 {catalog_path}"]
            record.setdefault("catalog", str(catalog_path))
            record["_catalog_text"] = text
            if quiet:
                out(f"  命令目录全文存在 {catalog_path}（{len(lines)} 行）")
        if result.rc != 0 and flow in KEEP_GOING:
            result.status = "红"
            record["steps"].append(result.__dict__)
            shown_rc = "读不懂输出" if result.rc is None else f"退出码 {result.rc}"
            out(f"  ✗ 第 {number} 步「{step.label}」红：{shown_rc}（接着跑下一步）")
            code = EXIT_RED
            continue
        if result.rc != 0:
            result.status = "失败"
            record["steps"].append(result.__dict__)
            record["stopped_at"] = {
                "number": number,
                "key": step.key,
                "label": step.label,
                "failed_command": result.command,
                "rc": result.rc,
            }
            record["result"] = "失败"
            out(
                f"\n✗ 停在第 {number} 步「{step.label}」：命令 {result.command} 退出码 {result.rc}，后面的步骤没跑。"
            )
            code = EXIT_RED
            finished = False
            break
        result.status = "通过"
        record["steps"].append(result.__dict__)
    if finished:
        if flow in KEEP_GOING:
            record["result"] = "走完，有红" if code else "走完，全过"
            out(f"\n【{FLOW_NAMES[flow]}】小结：")
            out("| 步 | 名字 | 结果 | 命令 | 退出码 |")
            out("|---|---|---|---|---|")
            for item in record["steps"]:
                rc = "" if item["rc"] is None else str(item["rc"])
                out(
                    f"| {item['number']} | {item['label']} | {item['status']} | {item['command']} | {rc} |"
                )
            red = [item for item in record["steps"] if item["status"] == "红"]
            out(
                f"✗ 有 {len(red)} 步红："
                + "、".join(f"第 {item['number']} 步「{item['label']}」" for item in red)
                if red
                else "✓ 没有红的步骤。"
            )
            if flow == "entry":
                record["handover"] = handover
                _print_handover(handover, out)
                record["role_hints"] = _print_role_hints(role_packs(root), project_claims, out)
        else:
            record["result"] = "走完"
            out(f"\n✓ 【{FLOW_NAMES[flow]}】走完。")
    record["finished"] = _now()
    catalog_text = record.pop("_catalog_text", None)
    try:
        reports.mkdir(parents=True, exist_ok=True)
        if catalog_text is not None:
            Path(record["catalog"]).write_text(catalog_text, encoding="utf-8")
        record_path.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        out(f"运行记录：{record_path}")
    except OSError as error:
        out(f"运行记录没写成：{type(error).__name__}: {error}")
        return code or EXIT_RED
    return code


def utf8_output(streams: Sequence[Any] | None = None) -> None:
    """启动时把 stdout、stderr 改成写 UTF-8，免得中文 Windows 上输出一重定向就崩。

    用户本机 2026-11-16 实测：输出接到文件或管道、没设 PYTHONUTF8 时，Python 按系统代码页（GBK）写，
    第 500 行 ``out(f"\\n▶ 第 {number} 步…")`` 的“▶”GBK 里没有，``UnicodeEncodeError: 'gbk' codec can't encode character '▶'``，
    进门流程第一步就停。和 ``00_Infrastructure/auto_pm/environment/env_check.py`` 同一做法：
    真终端用终端自己的编码，写不出的字换成 ``\\u25b6`` 这样的转义，看得见、不崩；
    重定向、接管道、被别的程序（AI agent、CI）读走时一律写 UTF-8，读的一方按 UTF-8 解。
    子命令的输出本来就按 UTF-8 读（``run_flow`` 给子进程设了 PYTHONUTF8=1，读时 ``encoding="utf-8"``），这里只管本脚本自己写出去的。
    """
    for stream in (sys.stdout, sys.stderr) if streams is None else streams:
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # 测试把输出换成 StringIO 时没有这个方法
            continue
        try:
            tty = bool(stream.isatty())
        except (OSError, ValueError):
            tty = False
        try:
            if tty:
                reconfigure(errors="backslashreplace")
            else:
                reconfigure(encoding="utf-8", errors="backslashreplace")
        except (OSError, ValueError):  # 已经读过的流不许改编码：照旧写，最多回到原来的样子，不因此不跑
            continue


def main(argv: Sequence[str] | None = None) -> int:
    utf8_output()
    parser = argparse.ArgumentParser(
        description="自动流程第一批：项目体检、交卷到收口（只串联现有命令）"
    )
    parser.add_argument(
        "--root", type=Path, default=DEFAULT_ROOT, help="控制根（默认按本脚本位置往上找）"
    )
    sub = parser.add_subparsers(dest="flow", required=True)
    entry = sub.add_parser(
        "entry",
        help="进门：项目体检，再看占位表和本项目每张卡的交接记录，最后提示该读哪个角色包；全程只读",
    )
    entry.add_argument("pid")
    steps = sub.add_parser("steps", help="只列出一个流程的每一步和整条命令，一条都不跑")
    steps.add_argument(
        "name", choices=sorted(FLOWS), metavar="流程名", help="entry、checkup 或 closeout"
    )
    checkup = sub.add_parser("checkup", help="项目体检：全程只读，每步都跑完，最后出小结表")
    checkup.add_argument("pid")
    closeout = sub.add_parser("closeout", help="交卷到收口：只跑只读检查，改状态的步骤前停下")
    closeout.add_argument("pid")
    closeout.add_argument("--mission-id", required=True)
    closeout.add_argument(
        "--done",
        default="",
        help="上次停在哪一步、那一步已经做完（verify、accept、close、transition、worktree）",
    )
    options = parser.parse_args(argv)
    if options.flow == "steps":
        return print_steps(options.name)
    return run_flow(
        options.flow,
        options.pid,
        root=options.root.resolve(),
        mission=getattr(options, "mission_id", ""),
        done=getattr(options, "done", ""),
    )


if __name__ == "__main__":
    raise SystemExit(main())
