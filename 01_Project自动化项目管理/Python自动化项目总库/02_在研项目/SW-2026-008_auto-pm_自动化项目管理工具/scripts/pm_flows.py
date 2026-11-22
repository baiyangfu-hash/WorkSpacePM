"""自动流程第一批（WBS 10.6）：“项目体检”“交卷到收口”“PR 线收口”和“进门”，只按顺序调现有的驾驶舱命令。

用法（在控制根，用控制根 .venv 里的 Python；Windows 是 .venv\\Scripts\\python.exe）：
  python <本项目>/scripts/pm_flows.py entry <项目号>
  python <本项目>/scripts/pm_flows.py checkup <项目号>
  python <本项目>/scripts/pm_flows.py closeout <项目号> --mission-id <卡号> [--done <已做完的一步>]
  python <本项目>/scripts/pm_flows.py closeout-pr <项目号> --chg <变更单号> --card <占位卡号> [--done <已做完的一步>]
  python <本项目>/scripts/pm_flows.py steps <entry|checkup|closeout|closeout-pr>

“交卷到收口”给走 Run 的卡（看板“确认开工”一键流开出来的）；“PR 线收口”给不走 Run 的全流程、标准线卡
（凭已批准的变更单、领卡占位和 PR 干活，CHG-SCPT-2026-717）：PR 合进 main 后把变更单推到验收中、请用户推到完成、
对账、放下占位、收工位。

“进门”（新对话、换班接手时跑，全程只读）＝项目体检的每一步，加 ``pm_handoff.py show`` 读本机交接交换区
（PM-056 V2.0.0）；处于“多机”档时再跑 ``claim list`` 看占位表并对本项目每张卡跑 ``claim log``（单机模式跳过
远程占位表），最后列出本机交接摘要、先读文件并按卡类型提示该读哪个角色包（控制根 ``roles/`` 下每个有
``role.json`` 的包；本项目的卡按登记路径对上包里的 ``owned_paths_patterns``）。
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
MERGE_SCRIPT = PROJECT_ROOT / "scripts" / "pm_merge.py"
HANDOFF_SCRIPT = PROJECT_ROOT / "scripts" / "pm_handoff.py"
REGISTRY = Path("SYS-2026-001_WorkspaceGovernance") / "workspace_registry.json"
REPORTS = Path(".auto-pm") / "reports" / "flows"
GITHUB_MODE_FILE = Path(".auto-pm") / "reports" / "local_merge" / "github_mode.json"
MERGE_LOG_FILE = Path(".auto-pm") / "reports" / "local_merge" / "merge_log.jsonl"
GITHUB_MODES = ("关", "备份", "多机")
DEFAULT_GITHUB_MODE = "备份"
PLC_ROOT = "0100_PLC自动化/"
STEP_TIMEOUT = 900
GIT_READ_TIMEOUT = 30
OUTPUT_TAIL = 60
CHG_ID_RE = re.compile(r"CHG-[A-Z]+-\d{4}-\d{3,}")
CHG_STATE_RE = re.compile(r"\|\s*变更状态\s*\|\s*([a-z_]+)\s*\|")
LEDGER_SEP_RE = re.compile(r"^\|[\s\-:|]+\|$")
SKIP_CHANGE_DIRS = frozenset({".git", ".auto-pm", ".venv", "node_modules", "__pycache__"})

# 只在 PLC 项目上跑的步骤（项目登记表里 project_root 在 0100_PLC自动化/ 下）。
PLC_ONLY = "plc"

# 项目号和卡号的格式（项目号同 auto_pm/domain/models/project.py，卡号同 auto_pm/contracts/orchestration.py）。
# 不合格就报用法错、一条命令都不跑：防止把 ``--fix`` 这类开关当项目号带进只读命令。
PID_PATTERN = re.compile(r"^[A-Z]{2,4}-\d{4}-\d{3}$")
MISSION_PATTERN = re.compile(r"^MISSION-[A-Z0-9-]+$")
# 变更单号同 implementation_card_basis 的 CHG-<领域>-<年>-<序号>；占位卡号是 claims/<卡号> 分支名的那一段（如 309、716-rules-thin-entries）。
CHG_PATTERN = re.compile(r"^CHG-[A-Z]+-\d{4}-\d{3,}$")
CARD_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

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
    args 里的 ``{pid}``、``{mission}``、``{chg}``、``{card}`` 运行时换成项目号、Mission 号、变更单号和占位卡号；
    ``{catalog}`` 表示运行命令目录脚本而不是 main.py；
    ``{plan}`` 表示运行项目计划状态脚本（WBS 8.8，只算只显示，控制根由本脚本补上）；
    ``{merge}`` 表示运行本机合并脚本 ``pm_merge.py``（卡 311，控制根由本脚本补上）；
    ``{handoff}`` 表示运行本机轻轨交接脚本 ``pm_handoff.py``（卡 318，控制根由本脚本补上）。
    ``ok`` 是这条命令算“通过”的退出码：默认只有 0；``pr settle-scan`` 用 1 表示“有等收口的卡”，那是收口时的常态，不是红。
    """

    key: str
    label: str
    args: tuple[str, ...]
    kind: str = "run"
    who: str = ""
    say: str = ""
    only: str = ""
    note: str = ""
    ok: tuple[int, ...] = (0,)


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
        "local_merges",
        "本机合并对账",
        ("{merge}", "verify-log"),
        note="核对本机合并命令上线后 main 上每个提交的来历（本机合并记录、GitHub PR 合并或经 GitHub 同步的本机合并），只读",
    ),
    Step(
        "root_clean",
        "工作区根目录清洁",
        ("{rootclean}",),
        note="脚本自己看控制根顶层有没有 tmp_*、.coverage、htmlcov 这类临时文件；有就提醒，不算红，不删",
    ),
)

# 进门：体检全部步骤，再读本机交接交换区（PM-056 V2.0.0），多机档再看远程占位表并逐卡跑 claim log。
LOCAL_HANDOFF = Step(
    "local_handoff",
    "本机交接状态",
    ("{handoff}", "show", "{pid}"),
    note="读取项目交接交换区 focus.json 与最近 5 条 journal.jsonl，并核对陈旧与 Git 漂移（PM-056 V2.0.0）",
)
CLAIM_LIST = Step(
    "claims",
    "占位表",
    ("claim", "list", "--json"),
    note="多机档时找出登记路径落在本项目目录里、还没放下的卡（单机模式跳过，不联网读远程占位表）",
)
ENTRY: tuple[Step, ...] = (*CHECKUP, LOCAL_HANDOFF, CLAIM_LIST)

# pr settle-scan：0＝没有等收口的；1＝有（说明里写了下一步）；2＝判断不了（没有账本、没有基线分支）。
# 收口时正好就是“有等收口的”，所以 1 不算红；2 照样算红。
SETTLE_OK: tuple[int, ...] = (0, 1)
SETTLE_NOTE = "退出码 1 只说明有等收口的卡（收口时的常态，接着走）；2 是判断不了，算红"

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
    Step(
        "settle_scan",
        "合并后收口清单",
        ("pr", "settle-scan", "{pid}"),
        ok=SETTLE_OK,
        note=SETTLE_NOTE,
    ),
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

# PR 线收口（CHG-SCPT-2026-717）：全流程、标准线里不走 Run 的卡，凭已批准的变更单、领卡占位和 PR 干活。
# PR 合进 main 之后跑；会改状态的步骤全是停点，推到完成永远不由脚本执行。
CLOSEOUT_PR: tuple[Step, ...] = (
    Step("control_root", "控制根状态", ("pm", "control-root-status", "{pid}")),
    Step(
        "settle_scan",
        "合并后收口清单",
        ("pr", "settle-scan", "{pid}"),
        ok=SETTLE_OK,
        note=SETTLE_NOTE,
    ),
    Step(
        "accepting",
        "变更单推到验收中",
        ("change", "transition", "{chg}", "--to", "accepting", "--pid", "{pid}"),
        kind="stop",
        who="PR 合进 main 后由 agent 运行，不需要用户批：同一条命令依次 --to implementing、"
        "--to pending_acceptance、--to accepting（这里列的是最后一条）",
    ),
    Step(
        "transition",
        "变更单推到完成",
        ("change", "transition", "{chg}", "--to", "completed", "--pid", "{pid}"),
        kind="stop",
        who="只有用户本人；本脚本永远不执行这一步",
        say="（用户本人在看板“决定”页点“推到完成”；或在本机主对话里说“把 {chg} 推到完成”，"
        "agent 带上那句话的位置再跑）",
    ),
    Step(
        "reconcile", "对账", ("ledger", "reconcile", "{pid}"), note="不带 --fix，只报差异，不写台账"
    ),
    Step(
        "claim_release",
        "放下占位",
        ("claim", "release", "{card}"),
        kind="stop",
        who="PR 已合并后由 agent 运行（PR 没合不放）",
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

FLOWS: Mapping[str, tuple[Step, ...]] = {
    "entry": ENTRY,
    "checkup": CHECKUP,
    "closeout": CLOSEOUT,
    "closeout-pr": CLOSEOUT_PR,
}
FLOW_NAMES = {
    "entry": "进门",
    "checkup": "项目体检",
    "closeout": "交卷到收口",
    "closeout-pr": "PR 线收口",
}

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


def read_github_mode(root: Path) -> str:
    """读取本机 GitHub 档位（与 pm_merge.py 同一口径）；未配置时默认为「备份」（单机本地优先）。"""
    path = root / GITHUB_MODE_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        mode = data.get("mode", DEFAULT_GITHUB_MODE) if isinstance(data, dict) else DEFAULT_GITHUB_MODE
    except (OSError, ValueError):
        return DEFAULT_GITHUB_MODE
    return mode if mode in GITHUB_MODES else DEFAULT_GITHUB_MODE


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


def local_handoff_summary(text: str) -> dict[str, Any]:
    """从 ``pm_handoff.py show`` 的人类可读输出里提取关键字段，供进门尾段汇总展示。"""
    summary: dict[str, Any] = {
        "established": "尚未建立本机交接交换区" not in text,
        "updated": "",
        "stage_goal": "",
        "active_work": "",
        "next_action": "",
        "waiting": [],
        "warnings": [],
        "read_first": [],
    }
    section = ""
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("更新："):
            summary["updated"] = stripped[len("更新：") :]
            section = ""
        elif stripped.startswith("阶段目标："):
            summary["stage_goal"] = stripped[len("阶段目标：") :]
            section = ""
        elif stripped.startswith("当前在干："):
            summary["active_work"] = stripped[len("当前在干：") :]
            section = ""
        elif stripped.startswith("下一步："):
            summary["next_action"] = stripped[len("下一步：") :]
            section = ""
        elif stripped == "待用户确认：":
            section = "waiting"
        elif stripped == "⚠ 提醒：":
            section = "warnings"
        elif stripped.startswith(("当前优先级：", "最近交接记录", "待用户确认：无")):
            section = ""
        elif stripped.startswith("先读："):
            for path in stripped[len("先读：") :].split("、"):
                clean = path.strip()
                if clean and clean != "无" and clean not in summary["read_first"]:
                    summary["read_first"].append(clean)
        elif section in ("waiting", "warnings") and stripped.startswith("- "):
            summary[section].append(stripped[2:].strip())
    return summary


def _print_local_handoff(
    summary: Mapping[str, Any] | None,
    red: bool,
    out: Callable[[str], None],
) -> None:
    """进门尾段第一块：本机交接交换区摘要（不覆盖 Git/账本，不构成授权）。"""
    out("\n【本机交接摘要】（来自项目交接交换区，不是授权，状态以上方体检和 Git 事实为准）")
    if red:
        out("✗ 本机交接交换区校验未通过（失败关闭），请先看上方「本机交接状态」步骤报错并修复。")
        return
    if not summary or not summary.get("established"):
        out("本项目尚未建立本机交接交换区（可用 scripts/pm_handoff.py set-focus 在工位初始化）。")
        return
    if (
        not summary.get("stage_goal")
        and not summary.get("next_action")
        and not summary.get("warnings")
        and not summary.get("read_first")
    ):
        out("已读取本机交接交换区（详见上方「本机交接状态」步骤输出）。")
        return
    if summary.get("updated"):
        out(f"- 更新：{summary['updated']}")
    if summary.get("stage_goal"):
        out(f"- 阶段目标：{summary['stage_goal']}")
    if summary.get("active_work"):
        out(f"- 当前在干：{summary['active_work']}")
    if summary.get("waiting"):
        out("- 待用户确认：" + "；".join(summary["waiting"]))
    if summary.get("next_action"):
        out(f"- 下一步：{summary['next_action']}")
    if summary.get("warnings"):
        for warning in summary["warnings"]:
            out(f"- ⚠ {warning}")
    if summary.get("read_first"):
        out("本机交接先读文件（接手前先读完再向用户报告）：")
        for path in summary["read_first"]:
            out(f"  {path}")


def _print_change_archive_summary(summary: Mapping[str, Any], out: Callable[[str], None]) -> None:
    """进门与体检小结后展示只读变更单入库积压与主线同步状态。"""
    if not summary.get("available"):
        return
    completed = summary.get("completed_pending") or []
    in_progress = summary.get("in_progress_untracked") or []
    historical = summary.get("historical_off_main") or []
    out("\n【变更单入库积压摘要】（只读核对 main，不影响本步退出码）")
    out(
        f"- 本机已完成待入库 {len(completed)} 张 | 未完成未入库 {len(in_progress)} 张 | "
        f"GitHub 同步：{summary.get('github_sync', '未知')}"
    )
    if completed:
        items = "、".join(f"{item['chg']}（{item['reason']}）" for item in completed)
        out(f"- 已完成待入库：{items}")
        out(f"- 建议运行：scripts/pm_merge.py archive-changes {summary.get('pid', '')}")
    if in_progress:
        items = "、".join(f"{item['chg']}（{item['status']}）" for item in in_progress)
        out(f"- 未完成未入库：{items}")
    for item in historical:
        out(
            f"- ⚠ {item['note']}：{item['chg']}（历史合并 {item['merge_sha'][:8]}，"
            f"当前本机状态 {item['status']}）"
        )


def _git_read_bytes(root: Path, *args: str) -> tuple[int, bytes]:
    try:
        done = subprocess.run(
            ["git", "-c", "core.quotePath=false", "-C", str(root), *args],
            capture_output=True,
            check=False,
            timeout=GIT_READ_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return 1, b""
    return int(done.returncode), done.stdout


def _ledger_row_map(text: str) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or LEDGER_SEP_RE.match(stripped):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        match = CHG_ID_RE.search(cells[1])
        if match:
            rows.setdefault(match.group(0), []).append(line)
    return rows


def change_archive_summary(root: Path, pid: str, *, github_mode: str = "") -> dict[str, Any]:
    """只读比较项目本机变更单原件/台账与 Git main，输出积压与离主线历史合并提示。"""
    project_root = project_root_of(root, pid)
    if not project_root:
        return {"available": False, "reason": "登记表里找不到项目目录"}
    mgmt_dir: Path | None = None
    for folder in ("04_监控", "11_监控"):
        candidate = root / project_root / folder / "01_变更管理"
        if candidate.is_dir() and (candidate / "01_变更单").is_dir():
            mgmt_dir = candidate
            break
    if mgmt_dir is None:
        return {"available": False, "reason": "项目还没有变更管理目录"}
    if not (root / ".git").exists():
        return {"available": False, "reason": "控制根不是 Git 仓库"}
    rc_main, out_main = _git_read_bytes(root, "rev-parse", "--verify", "--quiet", "main^{commit}")
    if rc_main != 0:
        return {"available": False, "reason": "找不到本机 main 分支"}
    main_sha = out_main.decode("utf-8", errors="replace").strip()
    rc_origin, out_origin = _git_read_bytes(
        root, "rev-parse", "--verify", "--quiet", "origin/main^{commit}"
    )
    origin_sha = out_origin.decode("utf-8", errors="replace").strip() if rc_origin == 0 else ""
    if github_mode == "关":
        github_sync = "未启用同步（GitHub 关）"
    elif origin_sha and origin_sha == main_sha:
        github_sync = "已同步"
    elif origin_sha:
        github_sync = "GitHub 待同步"
    else:
        github_sync = "GitHub 未配置远端"

    chg_dir = mgmt_dir / "01_变更单"
    chg_rel = chg_dir.relative_to(root).as_posix()
    ledger_path = mgmt_dir / "02_变更记录" / "01_版本变更台账.md"
    ledger_rel = ledger_path.relative_to(root).as_posix()

    disk_chgs: dict[str, tuple[Path, str]] = {}
    for folder, dirs, files in os.walk(chg_dir):
        dirs[:] = sorted(name for name in dirs if name not in SKIP_CHANGE_DIRS)
        for name in sorted(files):
            if name.endswith(".md") and CHG_ID_RE.fullmatch(Path(name).stem):
                file_path = Path(folder) / name
                disk_chgs[Path(name).stem] = (file_path, file_path.relative_to(root).as_posix())

    rc_diff, out_diff = _git_read_bytes(
        root, "diff", "--name-only", "-z", "--no-renames", "main", "--", chg_rel
    )
    rc_untracked, out_untracked = _git_read_bytes(
        root, "ls-files", "--others", "--exclude-standard", "-z", "--", chg_rel
    )
    dirty_paths: set[str] = set()
    if rc_diff == 0:
        dirty_paths.update(p for p in out_diff.decode("utf-8", errors="replace").split("\0") if p)
    if rc_untracked == 0:
        dirty_paths.update(
            p for p in out_untracked.decode("utf-8", errors="replace").split("\0") if p
        )

    local_ledger_text = (
        ledger_path.read_text(encoding="utf-8", errors="replace") if ledger_path.is_file() else ""
    )
    rc_ledger, main_ledger_bytes = _git_read_bytes(root, "cat-file", "blob", f"main:{ledger_rel}")
    main_ledger_text = (
        main_ledger_bytes.decode("utf-8", errors="replace") if rc_ledger == 0 else ""
    )
    local_rows = _ledger_row_map(local_ledger_text)
    main_rows = _ledger_row_map(main_ledger_text)

    completed_pending: list[dict[str, str]] = []
    in_progress_untracked: list[dict[str, str]] = []
    non_completed_states: dict[str, str] = {}

    for chg, (file_path, rel_path) in sorted(disk_chgs.items()):
        try:
            raw_bytes = file_path.read_bytes()
        except OSError:
            continue
        state_match = CHG_STATE_RE.search(raw_bytes.decode("utf-8", errors="replace"))
        state = state_match.group(1) if state_match else ""
        if state != "completed":
            non_completed_states[chg] = state or "unknown"
        ledger_diff = local_rows.get(chg) != main_rows.get(chg)
        if rel_path not in dirty_paths and not ledger_diff:
            continue
        rc_blob, main_blob = _git_read_bytes(root, "cat-file", "blob", f"main:{rel_path}")
        file_missing = rc_blob != 0
        file_modified = (
            not file_missing and raw_bytes.replace(b"\r\n", b"\n") != main_blob.replace(b"\r\n", b"\n")
        )
        if not file_missing and not file_modified and not ledger_diff:
            continue
        if state == "completed":
            reason = (
                "原件未入主线"
                if file_missing
                else ("原件待同步到主线" if file_modified else "台账已完成行待同步到主线")
            )
            completed_pending.append({"chg": chg, "path": rel_path, "reason": reason})
        else:
            in_progress_untracked.append(
                {"chg": chg, "status": state or "unknown", "path": rel_path}
            )

    historical_off_main: list[dict[str, str]] = []
    log_path = root / MERGE_LOG_FILE
    if log_path.is_file() and non_completed_states:
        seen_history: set[tuple[str, str]] = set()
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            merge_sha = str(entry.get("merge_sha", "")).strip()
            if not re.fullmatch(r"[0-9a-f]{40}", merge_sha):
                continue
            for raw_chg in entry.get("chgs") or []:
                chg = str(raw_chg)
                if chg not in non_completed_states or (chg, merge_sha) in seen_history:
                    continue
                rc_obj, _ = _git_read_bytes(root, "cat-file", "-e", f"{merge_sha}^{{commit}}")
                if rc_obj != 0:
                    continue
                rc_anc, _ = _git_read_bytes(root, "merge-base", "--is-ancestor", merge_sha, "main")
                if rc_anc != 0:
                    seen_history.add((chg, merge_sha))
                    historical_off_main.append(
                        {
                            "chg": chg,
                            "merge_sha": merge_sha,
                            "status": non_completed_states[chg],
                            "note": "历史合并不在当前主线，待核对替代提交",
                        }
                    )

    return {
        "available": True,
        "pid": pid,
        "main": main_sha,
        "github_sync": github_sync,
        "completed_pending": completed_pending,
        "in_progress_untracked": in_progress_untracked,
        "historical_off_main": sorted(historical_off_main, key=lambda item: item["chg"]),
    }


def _fill(args: Sequence[str], pid: str, mission: str, chg: str = "", card: str = "") -> list[str]:
    return [
        arg.replace("{pid}", pid)
        .replace("{mission}", mission)
        .replace("{chg}", chg)
        .replace("{card}", card)
        for arg in args
    ]


def command_of(
    step: Step, python: Path, root: Path, pid: str, mission: str, chg: str = "", card: str = ""
) -> list[str]:
    """一步对应的整条命令（列表，不经过 shell）。"""
    args = _fill(step.args, pid, mission, chg, card)
    if args and args[0] == "{plan}":
        return [str(python), "-B", str(PLAN_SCRIPT), *args[1:], "--root", str(root)]
    if args and args[0] == "{catalog}":
        return [str(python), "-B", str(CATALOG_SCRIPT), *args[1:]]
    if args and args[0] == "{merge}":
        return [str(python), "-B", str(MERGE_SCRIPT), "--root", str(root), *args[1:]]
    if args and args[0] == "{handoff}":
        return [str(python), "-B", str(HANDOFF_SCRIPT), *args[1:], "--root", str(root)]
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
        args = _fill(step.args, "<项目编号>", "<卡号>", "<变更单号>", "<占位卡号>")
        if args[0] == "{plan}":
            command = f"scripts/plan_status.py {' '.join(args[1:])}（驾驶舱项目的 scripts 目录）"
        elif args[0] == "{catalog}":
            command = (
                f"scripts/command_catalog.py {' '.join(args[1:])}（驾驶舱项目的 scripts 目录）"
            )
        elif args[0] == "{merge}":
            command = f"scripts/pm_merge.py {' '.join(args[1:])}（驾驶舱项目的 scripts 目录）"
        elif args[0] == "{handoff}":
            command = f"scripts/pm_handoff.py {' '.join(args[1:])}（驾驶舱项目的 scripts 目录）"
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
    chg: str = "",
    card: str = "",
    done: str = "",
    runner: Runner = subprocess.run,
    out: Callable[[str], None] = print,
) -> int:
    """按顺序跑一个流程。返回 0＝走完；1＝有一步红了；2＝用法或环境不对（一条命令都没跑）；3＝停在停点。

    “项目体检”和“进门”每一步都跑完，最后出小结表，任一步红就退出 1；“交卷到收口”“PR 线收口”一步红就停在那一步。
    根目录清洁只提醒，不算红。一步算不算红看它的 ``ok`` 退出码（默认只有 0）。
    """
    steps = FLOWS[flow]
    if not PID_PATTERN.match(pid):
        out(f"项目号格式不对：{pid!r}（应像 DJ-2026-005），一条命令都没跑")
        return EXIT_USAGE
    if flow == "closeout" and not MISSION_PATTERN.match(mission):
        out(f"卡号格式不对：{mission!r}（应像 MISSION-3E5ED659C44DE219），一条命令都没跑")
        return EXIT_USAGE
    if flow == "closeout-pr" and not CHG_PATTERN.match(chg):
        out(f"变更单号格式不对：{chg!r}（应像 CHG-SCPT-2026-717），一条命令都没跑")
        return EXIT_USAGE
    if flow == "closeout-pr" and not CARD_PATTERN.match(card):
        out(f"占位卡号格式不对：{card!r}（应像 309，即 claims/<卡号> 的那一段），一条命令都没跑")
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
    github_mode = read_github_mode(root)
    record: dict[str, Any] = {
        "flow": flow,
        "flow_name": FLOW_NAMES[flow],
        "pid": pid,
        "mission": mission,
        "chg": chg,
        "card": card,
        "done": done,
        "started": _now(),
        "root": str(root),
        "github_mode": github_mode,
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
        + (f"，变更单 {chg}" if chg else "")
        + (f"，占位 {card}" if card else "")
        + f"；GitHub 档位 {github_mode}；解释器 {python}"
    )
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    code = EXIT_DONE
    queue = list(steps[start:])
    number = start
    finished = True
    handover: list[dict[str, Any]] = []
    project_claims: list[dict[str, Any]] = []
    local_handoff: dict[str, Any] | None = None
    local_handoff_red = False
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
        command = command_of(step, python, root, pid, mission, chg, card)
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
                "say": _fill((step.say,), pid, mission, chg, card)[0],
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
        if step.key == "claims" and github_mode in ("关", "备份"):
            result.command = "（单机模式跳过，不读远程占位表）"
            result.status = f"跳过（单机模式：{github_mode}，多机档才查远程占位表）"
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
        if step.key == "local_handoff":
            if result.rc == 0:
                local_handoff = local_handoff_summary(stdout)
            else:
                local_handoff_red = True
        result.output_tail = lines[-OUTPUT_TAIL:]
        # 进门与体检时命令目录不刷屏：全文照样存进运行记录目录，屏幕上只说存在哪。
        quiet = flow in ("entry", "checkup") and step.key == "catalog" and result.rc == 0
        for line in [] if quiet else lines:
            out(f"  {line}")
        if step.key == "catalog" and result.rc == 0:
            catalog_path = reports / f"{stamp}_{flow}_{pid}_命令目录.md"
            result.output_tail = [f"全文存在 {catalog_path}"]
            record.setdefault("catalog", str(catalog_path))
            record["_catalog_text"] = text
            if quiet:
                out(f"  命令目录全文存在 {catalog_path}（{len(lines)} 行）")
        step_red = result.rc is None or result.rc not in step.ok
        if step_red and flow in KEEP_GOING:
            result.status = "红"
            record["steps"].append(result.__dict__)
            shown_rc = "读不懂输出" if result.rc is None else f"退出码 {result.rc}"
            out(f"  ✗ 第 {number} 步「{step.label}」红：{shown_rc}（接着跑下一步）")
            code = EXIT_RED
            continue
        if step_red:
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
            archive_summary = change_archive_summary(root, pid, github_mode=github_mode)
            record["change_archive_summary"] = archive_summary
            _print_change_archive_summary(archive_summary, out)
            if flow == "entry":
                record["local_handoff"] = local_handoff
                _print_local_handoff(local_handoff, local_handoff_red, out)
                record["handover"] = handover
                if github_mode == "多机":
                    _print_handover(handover, out)
                else:
                    out(
                        f"\n【交接记录】（当前为单机模式「{github_mode}」，已跳过远程占位表，交接以上方【本机交接摘要】为准）"
                    )
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
        "name",
        choices=sorted(FLOWS),
        metavar="流程名",
        help="entry、checkup、closeout 或 closeout-pr",
    )
    checkup = sub.add_parser("checkup", help="项目体检：全程只读，每步都跑完，最后出小结表")
    checkup.add_argument("pid")
    closeout = sub.add_parser(
        "closeout", help="交卷到收口（走 Run 的卡）：只跑只读检查，改状态的步骤前停下"
    )
    closeout.add_argument("pid")
    closeout.add_argument("--mission-id", required=True)
    closeout.add_argument(
        "--done",
        default="",
        help="上次停在哪一步、那一步已经做完（verify、accept、close、transition、worktree）",
    )
    closeout_pr = sub.add_parser(
        "closeout-pr",
        help="PR 线收口（不走 Run 的全流程、标准线卡，PR 合进 main 后跑）：只跑只读检查，改状态的步骤前停下",
    )
    closeout_pr.add_argument("pid")
    closeout_pr.add_argument("--chg", required=True, help="这张卡的变更单号，如 CHG-SCPT-2026-717")
    closeout_pr.add_argument("--card", required=True, help="领卡占位的卡号，如 309")
    closeout_pr.add_argument(
        "--done",
        default="",
        help="上次停在哪一步、那一步已经做完（accepting、transition、claim_release、worktree）",
    )
    options = parser.parse_args(argv)
    if options.flow == "steps":
        return print_steps(options.name)
    return run_flow(
        options.flow,
        options.pid,
        root=options.root.resolve(),
        mission=getattr(options, "mission_id", ""),
        chg=getattr(options, "chg", ""),
        card=getattr(options, "card", ""),
        done=getattr(options, "done", ""),
    )


if __name__ == "__main__":
    raise SystemExit(main())
