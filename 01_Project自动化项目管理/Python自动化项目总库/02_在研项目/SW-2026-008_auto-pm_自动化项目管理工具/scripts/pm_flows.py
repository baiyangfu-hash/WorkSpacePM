"""自动流程第一批（WBS 10.6）：“项目体检”和“交卷到收口”，只按顺序调现有的驾驶舱命令。

用法（在控制根，用控制根 .venv 里的 Python；Windows 是 .venv\\Scripts\\python.exe）：
  python <本项目>/scripts/pm_flows.py checkup <项目号>
  python <本项目>/scripts/pm_flows.py closeout <项目号> --mission-id <卡号> [--done <已做完的一步>]

规矩（协调者 2026-11-14 01:35Z 裁定的做法，这里照做）：
1. 只串联：每一步都是一条现成的 ``main.py`` 命令，原样运行，原样显示输出和退出码；脚本不判断、不改写结果。
2. 退出码不是 0 就算这一步红。“交卷到收口”停在红的那一步，报出整条命令和退出码，后面的不跑；
   “项目体检”全是只读，每一步都跑完，最后出小结表点名红的步骤和命令，有红就退出 1（协调者 03:55Z 裁定）。
   项目号、卡号格式不对直接报用法错，一条命令都不跑。
3. “项目体检”全程只读。“交卷到收口”只跑只读的检查；每个会改状态的步骤前都停下，打印要用户本人说的话
   和那一步的命令，由用户或经用户同意的 agent 去跑，跑完再带 ``--done`` 接着走。推到完成那一步永远不由脚本执行。
4. 每次运行都在控制根 ``.auto-pm/reports/flows/`` 落一份运行记录（时间、项目号、逐步命令原文、退出码、停在哪一步）。
5. 解释器：不靠 PATH 上的 ``python``。和看板的 bat 一样先找控制根的 ``.venv``，没有才用运行本脚本的这个 Python；
   入口一律是控制根的 ``main.py``（它再转给现役发布）。

本脚本不进发布载荷，不进 ``workflow history``；以后工作流引擎补上传参和中途停等后再迁进引擎（另立任务）。
"""

from __future__ import annotations

import argparse
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

# 一步红了还接着跑的流程：体检九步全只读，是一张报警一览，红了也要看到后面几步（协调者 03:55Z 裁定）。
KEEP_GOING = frozenset({"checkup"})


@dataclass(frozen=True)
class Step:
    """流程里的一步。

    kind 为 ``run``：脚本运行这条只读命令。kind 为 ``stop``：脚本停下，只打印这条命令和要用户本人说的话。
    args 里的 ``{pid}``、``{mission}`` 运行时换成项目号和卡号；``{catalog}`` 表示运行命令目录脚本而不是 main.py。
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
        "catalog",
        "当前命令目录",
        ("{catalog}", "--print"),
        note="现场生成，存进运行记录目录，不入库",
    ),
)

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

FLOWS: Mapping[str, tuple[Step, ...]] = {"checkup": CHECKUP, "closeout": CLOSEOUT}
FLOW_NAMES = {"checkup": "项目体检", "closeout": "交卷到收口"}

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


def is_plc_project(root: Path, pid: str) -> bool | None:
    """项目登记表里这个项目在 0100_PLC自动化/ 下返回 True；读不到登记表或查不到项目返回 None。"""
    try:
        data = json.loads((root / REGISTRY).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    for project in data.get("projects", []):
        if isinstance(project, dict) and project.get("project_id") == pid:
            return str(project.get("project_root", "")).replace("\\", "/").startswith(PLC_ROOT)
    return None


def _fill(args: Sequence[str], pid: str, mission: str) -> list[str]:
    return [arg.replace("{pid}", pid).replace("{mission}", mission) for arg in args]


def command_of(step: Step, python: Path, root: Path, pid: str, mission: str) -> list[str]:
    """一步对应的整条命令（列表，不经过 shell）。"""
    args = _fill(step.args, pid, mission)
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


def _stage_index(steps: Sequence[Step], done: str) -> int:
    """--done 给的那一步之后从哪一步开始。"""
    if not done:
        return 0
    for index, step in enumerate(steps):
        if step.key == done and step.kind == "stop":
            return index + 1
    raise SystemExit(f"--done 只认这些停点：{'、'.join(s.key for s in steps if s.kind == 'stop')}")


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
    """按顺序跑一个流程。返回 0＝走完或停在停点；1＝有一步红了；2＝用法或环境不对（一条命令都没跑）。

    “项目体检”每一步都跑完，最后出小结表，任一步红就退出 1；“交卷到收口”一步红就停在那一步。
    """
    steps = FLOWS[flow]
    if not PID_PATTERN.match(pid):
        out(f"项目号格式不对：{pid!r}（应像 DJ-2026-005），一条命令都没跑")
        return 2
    if flow == "closeout" and not MISSION_PATTERN.match(mission):
        out(f"卡号格式不对：{mission!r}（应像 MISSION-3E5ED659C44DE219），一条命令都没跑")
        return 2
    if not (root / "main.py").is_file():
        out(f"控制根里没有 main.py：{root}（请在控制根运行，或用 --root 指过去）")
        return 2
    python = resolve_python(root)
    plc = is_plc_project(root, pid)
    start = _stage_index(steps, done)
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
    code = 0
    for number, step in enumerate(steps[start:], start=start + 1):
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
            text = (completed.stdout or "") + (completed.stderr or "")
        except subprocess.TimeoutExpired:
            text = f"超过 {STEP_TIMEOUT} 秒没跑完，已停"
        except OSError as error:
            text = f"起不来：{type(error).__name__}: {error}"
        result.seconds = round(time.monotonic() - began, 2)
        lines = text.splitlines()
        result.output_tail = lines[-OUTPUT_TAIL:]
        for line in lines:
            out(f"  {line}")
        if step.key == "catalog" and result.rc == 0:
            catalog_path = reports / f"{stamp}_{flow}_{pid}_命令目录.md"
            result.output_tail = [f"全文存在 {catalog_path}"]
            record.setdefault("catalog", str(catalog_path))
            record["_catalog_text"] = text
        if result.rc != 0 and flow in KEEP_GOING:
            result.status = "红"
            record["steps"].append(result.__dict__)
            out(f"  ✗ 第 {number} 步「{step.label}」红：退出码 {result.rc}（接着跑下一步）")
            code = 1
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
            code = 1
            break
        result.status = "通过"
        record["steps"].append(result.__dict__)
    else:
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
        return code or 1
    return code


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="自动流程第一批：项目体检、交卷到收口（只串联现有命令）"
    )
    parser.add_argument(
        "--root", type=Path, default=DEFAULT_ROOT, help="控制根（默认按本脚本位置往上找）"
    )
    sub = parser.add_subparsers(dest="flow", required=True)
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
    return run_flow(
        options.flow,
        options.pid,
        root=options.root.resolve(),
        mission=getattr(options, "mission_id", ""),
        done=getattr(options, "done", ""),
    )


if __name__ == "__main__":
    raise SystemExit(main())
