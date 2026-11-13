"""“工具”页的本机命令。和 actions.py 一样：界面上每个按钮只调同一条命令行，不绕过任何护栏。

这个文件做三件事：
    build_command()   把表单拼成 main.py 的参数；只认下面 TOOLS 白名单里的命令，拼不出就抛 ToolError；
    run_tool()        在控制根里跑它，返回回执（命令 + 退出码 + 输出）；
    open_workbench()  另起一个窗口打开专业工作台（main.py gui --advanced）。

和 actions.py 分开放，是为了两条线（决定类按钮、工程类工具）各改各的文件、不抢同一份。
整个包里起子进程的只有 actions.py 和本文件，test_cockpit_board_tools.py 会数。

入箱（pm inbox add）只记一条 PROPOSED 的条目，确认、驳回照旧在“决定”页由你做；“用户原话”一栏看板从不预填。
新建项目（project create）、登记（project register）也在这里（CHG-SCPT-2026-654）：表单上“只试一次，不写”勾着时带 --dry-run；
看板不提交登记表，归档、重新激活在项目详情页走决定类按钮（decisions.py），删除、恢复不上看板。

永远没有：批准（approved、有条件批准）、合并、删除、切换发布、代签、绕过提交钩子、启动任何 agent。
批准变更单只能用户本人在终端里做（有口令要输口令），这里连选项都不给。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cockpit_board.actions import Receipt, _now_text, quiet

TOOL_TIMEOUT = 120  # 秒；这几个命令都是读文件或写一个变更单，超过两分钟一定是卡住了
OUTPUT_LIMIT = 20000  # 回执里最多留这么多字，其余丢掉并写明

# 变更单创建的选项。取值照 `main.py change create --help`，测试会对照真实命令。
CHANGE_DOMAINS = ("ELEC", "MECH", "PLC", "HMI", "SCPT", "DOCU", "SAFE", "SPEC")
CHANGE_NATURES = ("REQ", "DEF", "OPT", "CFG", "EMRG")
CHANGE_SCOPES = ("LOCAL", "MODULE", "SYSTEM", "CROSS", "SAFE")
CHANGE_URGENCIES = ("normal", "urgent", "critical")
# 变更单能转到的状态（`change transition --to` 的取值）。去掉两个批准类：
# approved、conditionally_approved 只在终端里由用户本人做（approved 在启用口令后要输口令），界面不提供。
CHANGE_TARGETS = (
    "draft", "submitted", "under_review", "rejected", "implementing", "pending_acceptance",
    "accepting", "completed", "closed", "archived", "abandoned",
)
USER_ONLY_TARGETS = ("approved", "conditionally_approved")
# 状态的中文名，和 auto_pm/domain/change/constants.py 的 STATUS_LABELS 一致（测试对照）。
STATUS_LABELS_ZH = {
    "draft": "草稿", "submitted": "已提交", "under_review": "审核中", "approved": "已批准", "conditionally_approved": "有条件批准",
    "rejected": "已驳回", "implementing": "实施中", "pending_acceptance": "待验收", "accepting": "验收中", "completed": "已完成",
    "closed": "已关闭", "archived": "已归档", "abandoned": "已废弃",
}
CHANGE_STATUSES = CHANGE_TARGETS + USER_ONLY_TARGETS  # change list --status 可筛的全部状态

# 入箱（`pm inbox add`）的选项。取值照 `main.py pm inbox add --help`，测试会对照真实命令和 auto_pm/contracts/intake.py。
INBOX_KINDS = ("iteration", "bug", "change", "urgent", "debt")
INBOX_ACTIONS = ("add", "modify", "reduce", "freeze", "remove")  # 只有类别是 change 时才填，其余类别不许填
INBOX_DISPOSITIONS = ("interrupt_now", "after_current", "inbox_wait", "reject")
INBOX_CRITERIA = ("safety", "data_loss", "blocks_all", "wrong_output")
INBOX_EVIDENCE_KINDS = ("file", "cmd", "ledger", "chg", "commit")
INBOX_PROPOSED_BY = "cockpit-board"  # 看板入箱时的提出者；看板以你的身份运行，不冒充别的 agent

# 新建项目（`project create`）和登记（`project register`）的选项。取值照两条命令的 --help，测试会对照真实命令。
PROJECT_STACKS = ("plc", "python")  # 栈名常量：整个看板包里只有这一行出现带引号的 python（test_no_bare_python_left_in_the_board_package）
PROJECT_MODES = ("shared-library", "test-suite", "standard-project")  # PLC 项目的模板；只在技术栈是 plc 时传
PROJECT_BUSINESS_LINES = ("SW", "DJ", "ZD", "XT", "WX")
PROJECT_TYPES = ("single_machine", "line_project", "retrofit_project", "maintenance_project", "shared_library", "test_suite")
PROJECT_PLC_VENDORS = ("Siemens", "Mitsubishi", "Omron", "Keyence", "Beckhoff", "Delta", "Other")
PROJECT_KINDS = ("equipment", "library", "test", "tool")  # 项目性质（`project register --kind`）
_PLC, _PY = PROJECT_STACKS


@dataclass(frozen=True)
class KindDefaults:
    """选了性质以后带出来的默认值；空＝不给默认。用户在表单里另选的，以用户选的为准。"""

    stack: str = ""
    mode: str = ""
    business_line: str = ""


# 性质到默认值的对照（CHG-SCPT-2026-654 第 1.2 节）：设备＝PLC、标准项目、DJ；公共库＝PLC、共享库、DJ；工具＝Python、SW；
# 测试＝不给默认，必须自己选技术栈。
KIND_DEFAULTS: dict[str, KindDefaults] = {
    "equipment": KindDefaults(_PLC, "standard-project", "DJ"),
    "library": KindDefaults(_PLC, "shared-library", "DJ"),
    "tool": KindDefaults(_PY, "", "SW"),
    "test": KindDefaults(),
}
TEST_KIND_NOTE = "测试套件临时项目一般不登记"


class ToolError(ValueError):
    """表单没填好或不在白名单里；文字直接显示给用户，不跑任何命令。"""


@dataclass(frozen=True)
class ToolSpec:
    label: str  # 给人看的名字（回执里的“动作”列）
    writes: bool  # 会不会写文件（写的先预览命令，再点运行）


# 白名单：键＝界面上的动作；没有在这里的，build_command 一律拒绝。
TOOLS: dict[str, ToolSpec] = {
    "change_list": ToolSpec("change list", False),
    "change_show": ToolSpec("change show", False),
    "change_create": ToolSpec("change create", True),
    "change_transition": ToolSpec("change transition", True),
    "decision_list": ToolSpec("decision list", False),
    "decision_show": ToolSpec("decision show", False),
    "vartable_parse": ToolSpec("vartable parse", False),
    "inbox_add": ToolSpec("pm inbox add", True),
    "project_create": ToolSpec("project create", True),
    "project_register": ToolSpec("project register", True),
}


def _need(params: dict[str, Any], *names: str) -> None:
    missing = [name for name in names if not str(params.get(name, "")).strip()]
    if missing:
        raise ToolError("还没填：" + "、".join(missing))


def _choice(params: dict[str, Any], name: str, allowed: tuple[str, ...], label: str) -> str:
    value = str(params.get(name, "")).strip()
    if value not in allowed:
        raise ToolError(f"{label}只能是：{' / '.join(allowed)}")
    return value


def _flag_text(value: str, label: str) -> str:
    text = " ".join(value.split())
    if text.startswith("-"):
        raise ToolError(f"“{label}”不能以 - 开头（会被当成命令选项）")
    return text


def build_command(key: str, params: dict[str, Any]) -> list[str]:
    """返回 main.py 后面的参数（不含 python、main.py、-w）。不在白名单、缺栏、取值不对都抛 ToolError。"""
    if key not in TOOLS:
        raise ToolError(f"没有这个工具：{key}")
    if key == "change_list":
        _need(params, "pid")
        args = ["change", "list", _flag_text(params["pid"], "项目编号"), "--full"]
        if str(params.get("status", "")).strip():
            args += ["--status", _choice(params, "status", CHANGE_STATUSES, "状态")]
        return args
    if key == "change_show":
        _need(params, "pid", "number")
        return ["change", "show", _flag_text(params["number"], "变更单号"), "--pid", _flag_text(params["pid"], "项目编号")]
    if key == "change_create":
        return _change_create(params)
    if key == "change_transition":
        return _change_transition(params)
    if key == "inbox_add":
        return _inbox_add(params)
    if key == "project_create":
        return _project_create(params)
    if key == "project_register":
        return _project_register(params)
    if key == "decision_list":
        args = ["decision", "list"]
        for name, option, label in (("pid", "--pid", "项目编号"), ("change_id", "--change-id", "变更单号")):
            if str(params.get(name, "")).strip():
                args += [option, _flag_text(params[name], label)]
        return args
    if key == "decision_show":
        _need(params, "decision_id")
        return ["decision", "show", _flag_text(params["decision_id"], "决策编号")]
    # vartable_parse：只读，输出 JSON 给查重用
    _need(params, "file")
    return ["vartable", "parse", _flag_text(str(params["file"]), "文件路径"), "--output-format", "json"]


def _change_create(params: dict[str, Any]) -> list[str]:
    _need(params, "pid", "applicant", "background", "necessity")
    scopes = params.get("scope") or []
    if isinstance(scopes, str):
        scopes = [scopes]
    if not scopes:
        raise ToolError("影响范围至少选一个")
    args = [
        "change", "create", "--pid", _flag_text(params["pid"], "项目编号"),
        "--domain", _choice(params, "domain", CHANGE_DOMAINS, "技术领域"),
        "--nature", _choice(params, "nature", CHANGE_NATURES, "业务性质"),
    ]
    for scope in scopes:
        if scope not in CHANGE_SCOPES:
            raise ToolError(f"影响范围只能是：{' / '.join(CHANGE_SCOPES)}")
        args += ["--scope", scope]
    args += [
        "--applicant", _flag_text(params["applicant"], "申请人"),
        "--background", _flag_text(params["background"], "变更背景"),
        "--necessity", _flag_text(params["necessity"], "变更必要性"),
        "--urgency", _choice({"urgency": params.get("urgency") or "normal"}, "urgency", CHANGE_URGENCIES, "紧急程度"),
    ]
    if str(params.get("references", "")).strip():
        args += ["--references", _flag_text(params["references"], "参考依据")]
    return args


def _change_transition(params: dict[str, Any]) -> list[str]:
    _need(params, "pid", "number")
    target = str(params.get("to", "")).strip()
    if target in USER_ONLY_TARGETS:
        raise ToolError("批准类的状态只在终端里由你本人做（有口令要输口令），界面不提供；命令：main.py change transition "
                        f"<单号> --to {target} --pid <项目>")
    args = ["change", "transition", _flag_text(params["number"], "变更单号"), "--to", _choice(params, "to", CHANGE_TARGETS, "目标状态"),
            "--pid", _flag_text(params["pid"], "项目编号")]
    if target == "abandoned":
        _need(params, "comment")  # 废弃必须写原因（B10）
    if target == "completed":
        _need(params, "verification_conclusion")  # 完成必须写验证结论
    for name, option, label in (("comment", "--comment", "意见"), ("approver", "--approver", "实施人"),
                                ("verification_conclusion", "--verification-conclusion", "验证结论")):
        if str(params.get(name, "")).strip():
            args += [option, _flag_text(params[name], label)]
    return args


def _lines(params: dict[str, Any], name: str, label: str) -> list[str]:
    """多值栏：一行一个，空行不算；每行照单行栏的规矩收拾，重复的行直接拒（命令那头也会拒，这里先说人话）。"""
    raw = params.get(name) or []
    values = raw.splitlines() if isinstance(raw, str) else [str(item) for item in raw]
    out = [_flag_text(value, label) for value in values if value.strip()]
    if len(set(out)) != len(out):
        raise ToolError(f"“{label}”有重复的行")
    return out


def _words_text(value: str, label: str) -> str:
    """用户原话：照人填的原样交给命令（不并空格、不改换行），只拒以 - 开头。看板从不替你填这一栏。"""
    if value.lstrip().startswith("-"):
        raise ToolError(f"“{label}”不能以 - 开头（会被当成命令选项）")
    return value


def _inbox_add(params: dict[str, Any]) -> list[str]:
    _need(params, "pid", "request_id", "title", "original_words", "affects", "duplicate_check", "rationale", "cost_risk")
    kind = _choice(params, "kind", INBOX_KINDS, "类别")
    evidence = _lines(params, "evidence", "取证")
    alternatives = _lines(params, "alternatives", "备选方案")
    missing = [label for label, values in (("取证（至少一条）", evidence), ("备选方案（至少一个）", alternatives)) if not values]
    if missing:
        raise ToolError("还没填：" + "、".join(missing))
    for entry in evidence:
        prefix, colon, rest = entry.partition(":")
        if not colon or prefix not in INBOX_EVIDENCE_KINDS or not rest.strip():
            raise ToolError("取证每行要写成 " + "|".join(k + ":" for k in INBOX_EVIDENCE_KINDS) + " 之一开头，例如 file:说明书.md")
    args = [
        "pm", "inbox", "add", "--project-id", _flag_text(params["pid"], "项目编号"),
        "--request-id", _flag_text(params["request_id"], "请求号"),
        "--title", _flag_text(params["title"], "标题"), "--kind", kind,
    ]
    action = str(params.get("change_action", "")).strip()
    if kind == "change":
        args += ["--change-action", _choice(params, "change_action", INBOX_ACTIONS, "变更动作")]
    elif action:
        raise ToolError("只有类别是“变更”（change）时才填变更动作")
    if str(params.get("domain", "")).strip():
        args += ["--domain", _choice(params, "domain", CHANGE_DOMAINS, "技术领域")]
    for scope in _lines(params, "impact_scope", "影响范围"):
        if scope not in CHANGE_SCOPES:
            raise ToolError(f"影响范围只能是：{' / '.join(CHANGE_SCOPES)}")
        args += ["--impact-scope", scope]
    args += [
        "--original-words", _words_text(str(params["original_words"]), "用户原话"),
        "--affects", _flag_text(params["affects"], "影响了什么"),
        "--duplicate-check", _flag_text(params["duplicate_check"], "查重"),
    ]
    for ref in _lines(params, "duplicate_of", "重复的条目"):
        args += ["--duplicate-of", ref]
    for entry in evidence:
        args += ["--evidence", entry]
    if str(params.get("urgent_criterion", "")).strip():
        args += ["--urgent-criterion", _choice(params, "urgent_criterion", INBOX_CRITERIA, "紧急判据")]
    args += [
        "--disposition", _choice(params, "disposition", INBOX_DISPOSITIONS, "建议处置"),
        "--rationale", _flag_text(params["rationale"], "理由"),
    ]
    for item in alternatives:
        args += ["--alternative", item]
    args += ["--cost-risk", _flag_text(params["cost_risk"], "成本与风险")]
    for ask in _lines(params, "asks", "要你决定的点"):
        args += ["--ask", ask]
    return args + ["--proposed-by", INBOX_PROPOSED_BY]


def _given(params: dict[str, Any], name: str) -> str:
    return str(params.get(name, "") or "").strip()


def _project_create(params: dict[str, Any]) -> list[str]:
    """project create：性质不进这条命令（带给下一步登记），只用来带出技术栈、模板、业务线的默认值。"""
    missing = [label for name, label in (("name", "项目名称"), ("kind", "性质")) if not _given(params, name)]
    if missing:
        raise ToolError("还没填：" + "、".join(missing))
    defaults = KIND_DEFAULTS[_choice(params, "kind", PROJECT_KINDS, "性质")]
    stack = _given(params, "stack") or defaults.stack
    if not stack:
        raise ToolError("性质是“测试”时没有默认的技术栈，请自己选技术栈")
    stack = _choice({"stack": stack}, "stack", PROJECT_STACKS, "技术栈")
    args = ["project", "create", "--stack", stack, "--name", _flag_text(params["name"], "项目名称")]
    line = _given(params, "business_line")
    if _given(params, "project_id"):  # 手填编号：不带 --auto-id（两样互斥）；业务线只在用户自己选了时才传
        args += ["--id", _flag_text(params["project_id"], "项目编号")]
    else:
        args += ["--auto-id"]
        line = line or defaults.business_line
    if line:
        args += ["--business-line", _choice({"business_line": line}, "business_line", PROJECT_BUSINESS_LINES, "业务线")]
    mode = _given(params, "mode") or defaults.mode
    if stack == _PLC and mode:  # 模板只在 PLC 时传；别的技术栈选了也不传，预览里看得到
        args += ["--mode", _choice({"mode": mode}, "mode", PROJECT_MODES, "模板")]
    if _given(params, "desc"):
        args += ["--desc", _flag_text(params["desc"], "项目描述")]
    if _given(params, "project_type"):
        args += ["--project-type", _choice(params, "project_type", PROJECT_TYPES, "项目类型")]
    if _given(params, "plc_vendor"):
        args += ["--plc-vendor", _choice(params, "plc_vendor", PROJECT_PLC_VENDORS, "PLC 品牌")]
    if _given(params, "plc_model"):
        args += ["--plc-model", _flag_text(params["plc_model"], "PLC 型号")]
    if _given(params, "dest_dir"):
        args += ["--dest-dir", _flag_text(params["dest_dir"], "存放目录")]
    return args + (["--dry-run"] if params.get("dry_run") else [])


def _project_register(params: dict[str, Any]) -> list[str]:
    """project register：从不传 --status（新登记的按命令的默认就是在研）；性质可空。"""
    if not _given(params, "project_id"):
        raise ToolError("还没填：项目编号")
    args = ["project", "register", _flag_text(params["project_id"], "项目编号")]
    if _given(params, "kind"):
        args += ["--kind", _choice(params, "kind", PROJECT_KINDS, "性质")]
    return args + (["--dry-run"] if params.get("dry_run") else [])


_AUTO_ID_LINE = re.compile(r"^自动生成项目编号: (\S+)\s*$", re.MULTILINE)


def created_project_id(params: dict[str, Any], output: str) -> str:
    """真建成功后的项目编号：手填的就是手填的那个；自动编号的从回执里那一行读，读不出来（没有或不止一个）返回空，不猜。"""
    if _given(params, "project_id"):
        return _given(params, "project_id")
    found = _AUTO_ID_LINE.findall(output or "")
    return found[0] if len(found) == 1 else ""


def board_request_id(now: datetime | None = None) -> str:
    """看板入箱的请求号：board-<UTC 时间>。预览时生成一次，运行用同一个（同号重放同内容不会重复入箱）。"""
    return "board-" + (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


# ---------------------------------------------------------------- 跑


def full_command(root: Path, args: list[str]) -> list[str]:
    """真正执行的整条命令：和人在命令提示符里敲的一致（-w 控制根）。用界面自己所在的 Python，依赖一定齐。"""
    return [sys.executable, "-B", str(root / "main.py"), "-w", str(root), *args]


def shown_command(args: list[str]) -> str:
    """回执里显示给人看的命令（不带 Python 路径，人复制到终端里照样能跑）。"""
    return "main.py " + " ".join(f'"{a}"' if (" " in a or not a) else a for a in args)


def _environment() -> dict[str, str]:
    env = dict(os.environ)
    env.update({"COLUMNS": "200", "NO_COLOR": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    return env


def _clip(text: str) -> str:
    if len(text) <= OUTPUT_LIMIT:
        return text
    return text[:OUTPUT_LIMIT] + f"\n……（输出共 {len(text)} 字，只留前 {OUTPUT_LIMIT} 字；完整输出请在命令提示符里运行上面的命令）"


@dataclass(frozen=True)
class ToolResult:
    receipt: Receipt
    stdout: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def run_tool(root: Path, key: str, params: dict[str, Any], runner: Callable[..., Any] = subprocess.run) -> ToolResult:
    """拼命令、在控制根跑、回执。拼不出命令抛 ToolError（调用方显示给用户）；命令本身失败不抛，看回执的 rc。"""
    args = build_command(key, params)
    label = TOOLS[key].label
    shown = shown_command(args)
    try:
        result = runner(
            full_command(root, args), cwd=str(root), capture_output=True, encoding="utf-8", errors="replace",
            timeout=TOOL_TIMEOUT, check=False, env=_environment(), **quiet(),
        )
    except (OSError, subprocess.SubprocessError) as error:
        return ToolResult(Receipt(_now_text(), label, shown, None, False, f"{type(error).__name__}: {error}"))
    stdout, stderr = result.stdout or "", result.stderr or ""
    return ToolResult(Receipt(_now_text(), label, shown, result.returncode, False, _clip(stdout + stderr)), stdout)


def open_workbench(root: Path, opener: Callable[..., Any] = subprocess.Popen) -> Receipt:
    """另起一个进程打开专业工作台；不等它，窗口关掉就结束。起不来只在回执里说，不抛。"""
    args = ["gui", "--advanced"]
    shown = shown_command(args)
    kwargs: dict[str, Any] = {"cwd": str(root), "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    try:
        opener(full_command(root, args), **kwargs)
    except OSError as error:
        return Receipt(_now_text(), "打开高级工作台", shown, None, False, f"{type(error).__name__}: {error}")
    return Receipt(_now_text(), "打开高级工作台", shown, 0, False, "已另起一个窗口；这个窗口和它互不影响，关掉它不影响这里。")


def find_io_tables(project_root: Path, limit: int = 20) -> list[Path]:
    """在项目目录里找 io_points.csv（只读列目录，最多 limit 个）。"""
    found: list[Path] = []
    if not project_root.is_dir():
        return found
    for path in sorted(project_root.rglob("io_points.csv")):
        if ".git" in path.parts or ".venv" in path.parts:
            continue
        found.append(path)
        if len(found) >= limit:
            break
    return found
