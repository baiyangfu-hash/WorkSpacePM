"""“决定”页的单一真源：哪些按钮、对应哪条命令行、什么状态下出现、要填什么（纯 Python，不 import Qt，不起子进程）。

读这个文件就能知道界面上每个决定按钮背后是哪条 `main.py pm …` 命令。界面只是命令行的另一层皮：

    * 按钮 → 下面 ``DECISIONS`` 里的一行 → ``build_args()`` 拼出命令行参数 → actions.run_cli() 在后台线程跑同一条命令；
    * 命令的退出码和原文输出原样进“控制台抽屉”，失败不静默（红色横条常驻，直到用户点“知道了”）；
    * 没有任何一个按钮绕过命令行里的护栏：门禁、租约、受保护路径、批准口令、agent 标记都由命令自己判，
      界面不替它判、不替它放行。所以“该不该出现这个按钮”只是方便用户看，不是安全边界。

永远不出现的按钮（测试按 ``NEVER_WORDS`` 清点）：合并、删除、切换发布、代签、绕过钩子、启动 agent。

批准口令（缺口⑨）：口令只能在终端里敲，命令行没有任何别的通道（approval_pin.py）。口令已生效时，本页不弹窗收口令，
而是用同一条命令在一个新的终端窗口里运行，用户在那个窗口里输入口令（见 actions.open_console）。
口令未生效时，批准人和“用户亲手点了这个按钮”的凭据由本页生成（见 ``click_evidence``）。

给 Trae：新增或修改一个按钮，只改本文件的 ``DECISIONS`` 和 DECISIONS.md 的对照表，再跑
tests/core/test_cockpit_decisions.py；测试会逐个按钮核对“对应的命令存在、必填项齐、没有禁用词”。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pm_dashboard as pd

from cockpit_board import policy

# ---------------------------------------------------------------- 按钮清单


@dataclass(frozen=True)
class Field:
    """对话框里要用户填的一栏；``key`` 同时是命令行选项名的来源。"""

    key: str
    label: str
    hint: str = ""
    required: bool = True
    multiline: bool = False
    default: str = ""  # 对话框打开时先填上的字（只用于命令自己就有同样缺省值的栏），用户可以改


@dataclass(frozen=True)
class Decision:
    """一个决定按钮。``kind`` 说明它作用在什么对象上：mission（一张卡）、scope_card（待批准的范围卡）、inbox（收件箱条目）、
    project（一个项目；只在项目详情页出现，“决定”页不挑这一类）、change（一张变更单）。"""

    key: str
    label: str
    kind: str
    summary: str  # 对话框第一行：点下去会发生什么（中文，用户读）
    command: tuple[str, ...]  # 命令行的固定前缀，不含 main.py
    states: frozenset[str] = frozenset()  # 只对 mission：哪些 Mission 状态出现这个按钮
    fields: tuple[Field, ...] = ()
    pin: bool = False  # 口令生效时这条命令会在终端里问口令
    user_words: bool = False  # 命令需要“用户亲手确认”的凭据（--approval-evidence-ref）
    danger: str = ""  # 非空：对话框里用警示色再确认一遍
    human_only: bool = False  # 只许你本人打开的看板点：看板进程带 AI 标记（或认不出带没带）时这个按钮灰着、也不运行


_SWITCH_FIELDS = (
    Field("reason", "手上这张为什么先放下", "例如：客户急改 IO 表"),
    Field("summary", "手上这张的断点", "干到哪了、下一步做什么（一行，不换行）"),
    Field("as_owner", "谁来干急活", "接手的 agent 身份，例如 claude:cloud 或 trae:cn"),
)

DECISIONS: tuple[Decision, ...] = (
    Decision(
        "approve_card", "批准范围", "scope_card",
        "批准这张范围卡：只批准你看过的这一版（哈希对不上命令会拒绝）。批准不会启动任何 agent。",
        ("pm", "approve"), pin=True, user_words=True, human_only=True,
        fields=(Field("admission_release_ref", "撞车放行（没有就留空）",
                      "新卡改的文件和开着的卡重叠，或项目已开满 8 张时，填你放行的原话位置", required=False),),
    ),
    Decision(
        "begin_work", "确认开工", "mission",
        "确认开工：任务转为进行中，不会启动任何 agent；之后由 IDE 里的 agent 按流程领取。",
        ("pm", "confirm-start"), states=frozenset({"DRAFT", "AWAITING_APPROVAL"}),
    ),
    Decision(
        "accept", "确认验收", "mission",
        "确认验收：记下你已经看过结果。验收后还要点“收口”才会把文件并回控制根。",
        ("pm", "accept"), states=frozenset({"ACCEPTANCE_PENDING"}), pin=True, human_only=True,
        danger="验收只能由你本人做；点之前确认你已经看过结果。",
    ),
    Decision(
        "close", "收口", "mission",
        "收口（也用于“重试同步”）：把验收过的文件按字节并回控制根，推进任务，把证据写进变更单。不替你提交 Git。",
        ("pm", "close"), states=frozenset({"ACCEPTED"}),
    ),
    Decision(
        "park", "搁着", "mission",
        "把这张卡记好断点放进“搁着”：交出钥匙，之后谁也不能往它的工作树里写，直到你拿回。",
        ("pm", "park"), states=frozenset({"ACTIVE"}), pin=True, user_words=True, human_only=True,
        fields=(Field("reason", "为什么先放下", "例如：客户急改 IO 表"),
                Field("summary", "断点", "干到哪了、下一步做什么（一行，不换行）")),
    ),
    Decision(
        "unpark", "拿回", "mission",
        "拿回这张卡：先核对工作树没被动过，再发新钥匙（钥匙存本机钱包，不显示）。拿回后先同步 main 再干活。",
        ("pm", "unpark"), states=frozenset({"PARKED", "BLOCKED"}), pin=True, user_words=True, human_only=True,
        fields=(Field("as_owner", "谁来接着干", "接手的 agent 身份，例如 claude:cloud 或 trae:cn"),),
    ),
    Decision(
        "switch", "插急活", "mission",
        "改干这一张：把手上在干的那张记好断点搁着，再把这张拿起来；第二步失败时第一张稳稳停在“搁着”。",
        ("pm", "switch"), states=frozenset({"PARKED", "DRAFT", "AWAITING_APPROVAL"}), pin=True, user_words=True, human_only=True,
        fields=_SWITCH_FIELDS,
    ),
    Decision(
        "inbox_confirm", "确认入箱", "inbox",
        "确认这条收件箱事项：只确认你看到的这一版（内容哈希对不上命令会拒绝）。确认不等于开工。",
        ("pm", "inbox", "confirm"), user_words=True, pin=True, human_only=True,
        fields=(Field("note", "备注（可空）", "一行", required=False),),
    ),
    Decision(
        "inbox_reject", "驳回入箱", "inbox",
        "驳回这条收件箱事项：写明理由，之后它不再出现在“等你”。",
        ("pm", "inbox", "reject"), user_words=True, pin=True, human_only=True,
        fields=(Field("note", "驳回理由", "一行"),),
    ),
    # 项目生命周期（CHG-SCPT-2026-654）：只在项目详情页的“项目状态”一块出现，而且要先跑过不带 --confirm 的预演、预演通过才出现。
    Decision(
        "project_archive", "确认归档", "project",
        "归档这个项目：只把登记表里的项目状态改成“已归档”，目录不搬，编号和路径不变。命令自己会再查一遍五项，有一项不过就拒绝。",
        ("project", "archive"), pin=True, user_words=True, human_only=True,
    ),
    Decision(
        "project_reactivate", "确认重新激活", "project",
        "把这个“已归档”的项目改回“在研”：只改登记表里的项目状态，目录不动。不是“已归档”的项目命令会拒绝。",
        ("project", "reactivate"), pin=True, user_words=True, human_only=True,
    ),
    # 变更单（M8 的 8.1）：命令是现成的 change transition，一次只推一步。按钮只对正好停在前一步的单出现。
    Decision(
        "change_approve", "批准变更单", "change",
        "批准这张变更单：从“审核中”推到“已批准”，批准人和这次点击的凭据写进变更单和审计日志。只批你看过的这一张。",
        ("change", "transition"), states=frozenset({"under_review"}), pin=True, user_words=True, human_only=True,
        fields=(Field("comment", "批准意见（可空）", "一行；不填时变更单里记“同意”", required=False),),
    ),
    Decision(
        "change_complete", "推到完成", "change",
        "把这张变更单从“验收中”推到“已完成”：验证结论写进变更单。命令会再查一遍验证项清单，有没过的就拒绝。",
        ("change", "transition"), states=frozenset({"accepting"}), user_words=True, human_only=True,
        fields=(Field("verification_conclusion", "验证结论", "要有“通过”两个字，例如：全部通过", default="全部通过"),),
    ),
)

# 变更单按钮推到哪个状态（change transition --to）；出现在哪个状态见上面的 states。
CHANGE_TARGET = {"change_approve": "approved", "change_complete": "completed"}
# 变更单状态的白话：和 auto_pm.domain.change.constants.STATUS_LABELS 逐字一致（测试对照）；本包不 import auto_pm，所以照抄用得到的几个。
CHANGE_STATUS_LABEL = {"draft": "草稿", "submitted": "已提交", "under_review": "审核中", "approved": "已批准",
                       "conditionally_approved": "有条件批准", "implementing": "实施中", "pending_acceptance": "待验收",
                       "accepting": "验收中"}
# 这几个状态的单还没走到按钮那一步：页面写一行说明，不出按钮（前面几步由 AI 用同一条命令推）。
CHANGE_BEFORE_APPROVE = ("draft", "submitted")
CHANGE_BEFORE_COMPLETE = ("approved", "conditionally_approved", "implementing", "pending_acceptance")
HUMAN_ONLY_AGENT = "这个看板是带 AI 标记的会话打开的（{markers}）：这个按钮只许你本人打开的看板点。请你自己双击看板的 bat 重新打开。"
HUMAN_ONLY_UNKNOWN = "认不出这个看板是不是 AI 会话打开的（找不到主程序里的标记名单，多半是看板被单独拷走了）：这个按钮先不开放。请用控制根里的 bat 打开看板。"



def human_only_block(markers: Sequence[str] | None) -> str:
    """看板进程带没带 AI 标记 → human_only 按钮灰着的原因；空串＝可以点。None（认不出）按不开放处理。"""
    if markers is None:
        return HUMAN_ONLY_UNKNOWN
    return HUMAN_ONLY_AGENT.format(markers="、".join(markers)) if markers else ""


BY_KEY = {item.key: item for item in DECISIONS}

# 决定页上允许出现的按钮文字，另加弹窗里的两个确认键。测试按它清点。
# （“确认归档”“确认重新激活”也在 DECISIONS 里，但“决定”页不画它们：build_vm 只挑 mission、scope_card、inbox 三类。）
DECISION_BUTTONS = frozenset({item.label for item in DECISIONS}) | frozenset({
    "确认并运行", "在终端窗口里运行", "取消", "知道了", "复制命令", "展开控制台", "收起控制台",
})
# 永远不加的动作（同 policy.NEVER，另加几条本页特有的）；按钮文字、对话框文字里都不许出现。
NEVER_WORDS = (*policy.NEVER, "启动 agent", "强推")

# 看板自己会起的只读命令。这张表里的命令一律不带 --confirm、--apply、--approval-evidence-ref（测试清点）。
READ_ONLY_COMMANDS = {
    "pending": ("pm", "pending", "--project-id"),
    "inbox": ("pm", "inbox", "list", "--project-id"),
    "pin_status": ("pm", "approver-pin", "status"),
    # 项目生命周期（CHG-SCPT-2026-654）。两条预演：后面只接项目号，不带 --confirm，命令只查不改；
    "project_archive_dry_run": ("project", "archive"),
    "project_reactivate_dry_run": ("project", "reactivate"),
    # 三条探测：本机发布版有没有这条命令、register 有没有 --kind（--help 不改任何东西）。
    "project_archive_help": ("project", "archive", "--help"),
    "project_reactivate_help": ("project", "reactivate", "--help"),
    "project_register_help": ("project", "register", "--help"),
}
LIFECYCLE_PROBES = ("project_archive_help", "project_reactivate_help", "project_register_help")


@dataclass(frozen=True)
class Lifecycle:
    """项目详情页“项目状态”一块的一个入口：先点 ``dry_label`` 跑预演，预演通过才出现 ``decision`` 那个确认键。"""

    decision: str  # DECISIONS 里的键
    dry_label: str  # 预演按钮的文字
    dry_run: str  # READ_ONLY_COMMANDS 里的键：预演
    probe: str  # READ_ONLY_COMMANDS 里的键：探测本机有没有这条命令


LIFECYCLES = {
    "archive": Lifecycle("project_archive", "归档…", "project_archive_dry_run", "project_archive_help"),
    "reactivate": Lifecycle("project_reactivate", "重新激活…", "project_reactivate_dry_run", "project_reactivate_help"),
}
RECHECK_LABEL = "重新检查"
# 看板凭这一句认“这是一次预演、而且走到了头”（auto_pm/ui/cli/project.py 里归档、重新激活各打印一次，测试对照源文本）。
DRY_RUN_MARK = "预演（没加 --confirm）"
REGISTER_KIND_OPTION = "--kind"


def dry_run_args(key: str, project_id: str) -> list[str]:
    """预演命令：``project archive <项目号>`` / ``project reactivate <项目号>``，不带任何别的选项。"""

    return [*READ_ONLY_COMMANDS[LIFECYCLES[key].dry_run], _ident(project_id, "项目编号")]


def dry_run_passed(rc: int | None, output: str) -> bool:
    """只看两样：退出码是 0，并且输出里有“预演（没加 --confirm）”这一句。不数“通过”有几个。"""

    return rc == 0 and DRY_RUN_MARK in (output or "")

# ---------------------------------------------------------------- 对象和命令行


@dataclass(frozen=True)
class Target:
    """按钮作用的对象：从看板和只读命令（pm pending / pm inbox list）读出来的编号，不由用户手填。"""

    project_id: str = ""
    mission_id: str = ""
    request_id: str = ""
    plan_hash: str = ""
    item_id: str = ""
    ticket_hash: str = ""
    title: str = ""
    state: str = ""
    change_id: str = ""


class DecisionError(ValueError):
    """缺必填项、缺对象编号：文字直接显示给用户，命令不会被运行。"""


def click_evidence(decision_key: str, subject: str, now: datetime) -> str:
    """口令未生效时，“用户亲手点了这个按钮”的凭据。

    形式是命令行认的 ``user-confirmation:<引用>``（至少 8 字符，不含 agent / 模型名）。引用里只放时间和一个短摘要，
    不含任何口令。口令未生效时这个凭据只是格式检查（P1，见 批准口令未生效方案）；口令生效后命令用口令代替它。
    """

    digest = hashlib.sha256(f"{decision_key}\x00{subject}".encode()).hexdigest()[:8]
    return f"user-confirmation:gui-click-{now.strftime('%Y%m%dT%H%M%S')}-{digest}"


def _need(value: str, label: str) -> str:
    if not value.strip():
        raise DecisionError(f"缺少{label}，不能运行")
    return value.strip()


# 进命令行的每一个值都先过白名单或黑名单，再拼参数。运行时命令是按“参数列表”直接起的，不经过任何 shell，
# 这些检查是第二道：编号和哈希来自账本，自由文本来自用户，复制出去的命令也不能在终端里变样。
_IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")  # 项目、任务、请求、条目编号
_HASH = re.compile(r"[A-Za-z0-9]{8,128}")  # 范围卡哈希、条目哈希
_OWNER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:@-]{0,63}")  # agent 身份，如 claude:cloud
_FREE_FORBIDDEN = re.compile(r"[\x00-\x1f\x7f\"%^$`]")  # 控制字符（含换行）和会让复制出去的命令变样的 " % ^ $ `
_FREE_MAX = 500


def _ident(value: str, label: str) -> str:
    value = _need(value, label)
    if not _IDENT.fullmatch(value):
        raise DecisionError(f"{label}“{value[:40]}”格式不对（只允许字母、数字和 . _ : -），不运行")
    return value


def _hash(value: str, label: str) -> str:
    value = _need(value, label)
    if not _HASH.fullmatch(value):
        raise DecisionError(f"{label}格式不对（只允许 8～128 位字母数字），不运行")
    return value


def _free(value: str, label: str) -> str:
    """用户自由填的字：不许换行和其他控制字符，不许出现 \" % ^ $ `（& 和 | 在命令里只是普通字符，允许）。"""
    value = value.strip()
    if _FREE_FORBIDDEN.search(value):
        raise DecisionError(f"“{label}”里有不能用的字符（换行、双引号 \" 和 % ^ $ `），请改掉再运行")
    if len(value) > _FREE_MAX:
        raise DecisionError(f"“{label}”太长（最多 {_FREE_MAX} 字）")
    return value


def missing_fields(decision: Decision, values: Mapping[str, str]) -> list[str]:
    return [item.label for item in decision.fields if item.required and not str(values.get(item.key, "")).strip()]


def build_args(
    decision: Decision,
    target: Target,
    values: Mapping[str, str],
    *,
    approver: str,
    pin_enforced: bool,
    now: datetime,
) -> list[str]:
    """拼出 ``main.py`` 后面的参数。拼不出来（缺编号、缺必填栏）抛 DecisionError，不运行。"""

    missing = missing_fields(decision, values)
    if missing:
        raise DecisionError("还没填：" + "、".join(missing))
    args = list(decision.command)
    labels = {item.key: item.label for item in decision.fields}
    value = {key: _free(str(text), labels.get(key, key)) for key, text in values.items()}
    if value.get("as_owner") and not _OWNER.fullmatch(value["as_owner"]):
        raise DecisionError("“谁来干”只允许字母、数字和 . _ : @ -，例如 claude:cloud 或 trae:cn")
    approver = _free(approver, "批准人")
    evidence = ""
    if decision.user_words:
        subject = target.project_id if decision.kind == "project" else (
            target.change_id or target.mission_id or target.request_id or target.item_id)
        evidence = click_evidence(decision.key, subject, now)

    if decision.key == "approve_card":
        args += ["--request-id", _ident(target.request_id, "范围卡请求编号"), "--plan-hash", _hash(target.plan_hash, "范围卡哈希")]
        if not pin_enforced:  # 口令生效时批准人和凭据由口令决定，不再传
            args += ["--approver", _need(approver, "批准人（你的名字）"), "--approval-evidence-ref", evidence]
        if value.get("admission_release_ref"):
            args += ["--admission-release-ref", value["admission_release_ref"]]
    elif decision.key in ("begin_work", "accept", "close"):
        args += ["--mission-id", _ident(target.mission_id, "任务编号")]
    elif decision.key == "park":
        args += ["--mission-id", _ident(target.mission_id, "任务编号"), "--reason", value["reason"], "--summary", value["summary"],
                 "--approval-evidence-ref", evidence]  # 有凭据才进“搁着”；没有只进“等你”
    elif decision.key == "unpark":
        args += ["--mission-id", _ident(target.mission_id, "任务编号"), "--as", value["as_owner"], "--approval-evidence-ref", evidence]
    elif decision.key == "switch":
        args += ["--pid", _ident(target.project_id, "项目编号"), "--to", _ident(target.mission_id, "要改干的任务编号"),
                 "--reason", value["reason"], "--summary", value["summary"], "--as", value["as_owner"],
                 "--approval-evidence-ref", evidence]
    elif decision.key in ("inbox_confirm", "inbox_reject"):
        args += [_ident(target.item_id, "收件箱条目编号"), "--ticket-hash", _hash(target.ticket_hash, "条目哈希"),
                 "--approver", _need(approver, "批准人（你的名字）"), "--approval-evidence-ref", evidence]
        if value.get("note"):
            args += ["--note", value["note"]]
    elif decision.kind == "change":  # 批准变更单 / 推到完成：同一条 change transition，一次一步；批准人和凭据两种情况都传（留痕）
        args += [_ident(target.change_id, "变更单号"), "--to", CHANGE_TARGET[decision.key], "--pid", _ident(target.project_id, "项目编号"),
                 "--approver", _need(approver, "批准人（你的名字）"), "--approval-evidence-ref", evidence]
        if decision.key == "change_complete":
            args += ["--verification-conclusion", _need(value.get("verification_conclusion", ""), "验证结论")]
        elif value.get("comment"):
            args += ["--comment", value["comment"]]
    elif decision.kind == "project":  # 归档 / 重新激活：项目号 + --confirm + “用户亲手点了这个按钮”的凭据
        args += [_ident(target.project_id, "项目编号"), "--confirm", "--approval-evidence-ref", evidence]
    else:  # pragma: no cover - 新按钮必须在这里接线，test_every_decision_builds_a_command 会拦住
        raise DecisionError(f"按钮 {decision.key} 没有接线")
    return args


_SHELL_SAFE = re.compile(r"[A-Za-z0-9._:/@=+,-]+")


def shown_command(args: Sequence[str]) -> str:
    """给人看的等价命令（控制台抽屉、对话框里的“复制命令”）。含空格的参数加引号。"""

    parts = [item if _SHELL_SAFE.fullmatch(item) else f'"{item}"' for item in args]
    return "main.py " + " ".join(parts)


# ---------------------------------------------------------------- 读只读命令的输出


def parse_pin_status(text: str) -> str:
    """``pm approver-pin status`` 的第一行 → ``enforced`` / ``off`` / ``suspended`` / ``unknown``。"""

    first = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
    if "所有批准暂停" in first:
        return "suspended"
    if "已生效" in first:
        return "enforced"
    if "未生效" in first:
        return "off"
    return "unknown"


def _json(text: str) -> dict[str, Any]:
    """命令输出里的 JSON 对象。

    控制根的启动器会在 stderr 打一行 ``launcher: release verified via …``，界面拿到的输出是 stdout 接 stderr，
    JSON 后面（有时前面）跟着这行横幅，整段交给 ``json.loads`` 一定失败、被当成“什么都没有”。所以从每个 ``{`` 起试着
    读出第一个完整的 JSON 对象，横幅和别的杂行不管。
    """

    text = text if isinstance(text, str) else ""
    decoder = json.JSONDecoder()
    start = text.find("{")
    for _ in range(20):  # 横幅里不会有几个 “{”；封顶，免得一大段乱码时反复试
        if start < 0:
            return {}
        try:
            data, _end = decoder.raw_decode(text, start)
        except ValueError:
            start = text.find("{", start + 1)
            continue
        if isinstance(data, dict):
            return data
        start = text.find("{", start + 1)
    return {}


def _has_list(text: str, key: str) -> bool:
    """输出是不是一份有 ``key`` 列表的 JSON（空列表也算读成功）；不是就说明没读懂，不能当成“没有”。"""

    return isinstance(_json(text).get(key), list)


def parse_pending(text: str, project_id: str) -> list[Target]:
    """``pm pending --project-id P`` 的 JSON → 待批准范围卡。被新版本取代的（superseded）不列。"""

    found = []
    cards = _json(text).get("cards")
    for item in cards if isinstance(cards, list) else []:  # 不是列表（读不懂）就当一条都没取到；红条由 read_failure 给
        card = item.get("card", {}) if isinstance(item, dict) else {}
        if not isinstance(item, dict) or not isinstance(card, dict) or item.get("superseded"):
            continue
        found.append(Target(project_id=project_id, request_id=str(card.get("request_id", "")),
                            plan_hash=str(card.get("plan_hash", "")), title=str(item.get("objective", ""))))
    return [t for t in found if t.request_id and t.plan_hash]


def parse_inbox(text: str, project_id: str) -> list[Target]:
    """``pm inbox list --project-id P`` 的 JSON → 等你确认的条目（状态 PROPOSED）。"""

    found = []
    items = _json(text).get("items")
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and str(item.get("status", "")).upper() == "PROPOSED":
            found.append(Target(project_id=project_id, item_id=str(item.get("item_id", "")),
                                ticket_hash=str(item.get("ticket_hash", "")), title=str(item.get("title", ""))))
    return [t for t in found if t.item_id and t.ticket_hash]


def _last_line(text: str, limit: int = 200) -> str:
    lines = [line.strip() for line in (text or "").strip().splitlines() if line.strip()]
    return lines[-1][:limit] if lines else ""


last_line = _last_line  # 控制器给空原文的红条补 stderr 末行时用


def read_failure(what: str, command: str, rc: int | None, output: str, *, key: str | None = None) -> ReadFailure | None:
    """一条只读命令读成功了没有；没读成返回 ReadFailure，读成功返回 None。

    ``key`` 为 ``"cards"`` / ``"items"`` 时，退出码 0 但输出不是带这个列表的 JSON 也算没读成（空列表才是“没有”）；
    ``key`` 为 None 时按口令状态判：第一行认不出也算没读成。
    """

    if rc != 0:
        return ReadFailure(what, command, "未验证" if rc is None else f"rc {rc}", _last_line(output))
    unreadable = parse_pin_status(output) == "unknown" if key is None else not _has_list(output, key)
    return ReadFailure(what, command, "输出读不懂", _last_line(output)) if unreadable else None


# ---------------------------------------------------------------- 决定页的版面数据（纯函数，可单测）


@dataclass(frozen=True)
class CardVM:
    """决定页上的一张卡：一个对象 + 现在可以点的按钮。"""

    column: str  # 在干 / 等你 / 搁着 / 已关 / 范围卡 / 收件箱 / 变更单
    heading: str
    detail: str
    target: Target
    decisions: tuple[Decision, ...]
    sev: str = ""  # "" / "risk"（搁着超过 7 天）
    blocked: str = ""  # 非空：这张卡上 human_only 的按钮灰着，旁边写这句原因


@dataclass(frozen=True)
class ReadFailure:
    """一次只读命令没读成：页面照实写“没读到”，不能把它当成“没有”。"""

    what: str  # 读什么：口令状态 / 读待批准范围卡 / 读收件箱
    command: str
    rc_text: str  # rc 1 / 未验证 / 输出读不懂
    detail: str = ""


@dataclass(frozen=True)
class DecisionsVM:
    cards: tuple[CardVM, ...] = ()
    pin_mode: str = "unknown"
    pin_text: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)
    failures: tuple[ReadFailure, ...] = ()
    blocked: str = ""  # 非空：这一页 human_only 的按钮都灰着（看板是 AI 会话打开的，或认不出），这句是原因


PIN_TEXT = {
    "enforced": "批准口令：已生效（批准、验收、搁着、拿回会在新的终端窗口里问口令）",
    "off": "批准口令：未生效（批准只做格式检查，这是已知缺口，口令设好后自动改走口令）",
    "suspended": "批准口令：所有批准暂停（登记文件有问题），决定类按钮会被命令拒绝",
    "unknown": "批准口令：没读到状态（按未生效处理，命令自己会判）",
}

_COLUMN_ORDER = ("变更单", "范围卡", "收件箱", "等你", "在干", "搁着", "已关")


def _for_state(state: str, mission_open_active: bool) -> tuple[Decision, ...]:
    picked = [d for d in DECISIONS if d.kind == "mission" and state in d.states]
    if not mission_open_active:  # 项目里没有“在干”的卡时，“插急活”没有东西可搁，只剩“拿回/确认开工”
        picked = [d for d in picked if d.key != "switch"]
    return tuple(picked)


def build_vm(
    missions: Sequence[Any],
    pending: Mapping[str, Sequence[Target]],
    inbox: Mapping[str, Sequence[Target]],
    pin_mode: str,
    *,
    stale_ids: frozenset[str] = frozenset(),
    failures: Sequence[ReadFailure] = (),
    changes: Sequence[tuple[str, Any]] = (),
    human_only_block: str = "",
) -> DecisionsVM:
    """把看板的 Mission（需有 mission_id / project_id / title / state / column）和只读命令读到的对象排成卡。

    “已关”栏里只有已验收未收口（ACCEPTED）的卡带按钮，其余（已收口、已作废）不出现，免得误点。
    """

    cards: list[CardVM] = []
    notes: list[str] = []
    waiting = {"change_approve": 0, "change_complete": 0}
    for pid, order in changes:  # （项目号, pm_dashboard.ChangeOrderInfo）：状态是变更单文件 §3.4 里的原文
        status = str(getattr(order, "status", "")).strip()
        buttons = tuple(d for d in DECISIONS if d.kind == "change" and status in d.states)
        waiting["change_approve"] += status in CHANGE_BEFORE_APPROVE
        waiting["change_complete"] += status in CHANGE_BEFORE_COMPLETE
        if not buttons:
            continue
        target = Target(project_id=pid, change_id=order.change_id, title=f"{order.change_id} {order.what}".strip(), state=status)
        cards.append(CardVM("变更单", target.title, f"{order.change_id} · {pid} · {CHANGE_STATUS_LABEL.get(status, status)}", target, buttons,
                            blocked=human_only_block))
    if waiting["change_approve"]:
        notes.append(f"另有 {waiting['change_approve']} 张变更单还是草稿或已提交，没送到“审核中”，所以这里没有“批准变更单”按钮。")
    if waiting["change_complete"]:
        notes.append(f"另有 {waiting['change_complete']} 张变更单已批准但还没走到“验收中”，所以这里没有“推到完成”按钮。")
    active_projects = {m.project_id for m in missions if m.state == "ACTIVE"}
    for pid, targets in pending.items():
        for t in targets:
            cards.append(CardVM("范围卡", t.title or t.request_id, f"请求 {t.request_id} · 哈希 {t.plan_hash[:12]}…", t,
                                (BY_KEY["approve_card"],), blocked=human_only_block))
    for pid, targets in inbox.items():
        for t in targets:
            cards.append(CardVM("收件箱", t.title or t.item_id, f"条目 {t.item_id} · 哈希 {t.ticket_hash[:12]}…", t,
                                (BY_KEY["inbox_confirm"], BY_KEY["inbox_reject"]), blocked=human_only_block))
    for m in missions:
        buttons = _for_state(m.state, m.project_id in active_projects)
        if m.state in ("CLOSED", "CANCELLED") or not buttons:
            continue
        target = Target(project_id=m.project_id, mission_id=m.mission_id, title=m.title, state=m.state)
        cards.append(CardVM(m.column, m.title or m.mission_id, f"{m.mission_id} · {m.project_id} · {pd.STATE_LABEL.get(m.state, m.state)}", target, buttons,
                            "risk" if m.mission_id in stale_ids else "", blocked=human_only_block))
    cards.sort(key=lambda c: (_COLUMN_ORDER.index(c.column) if c.column in _COLUMN_ORDER else 99, c.heading))
    return DecisionsVM(tuple(cards), pin_mode, PIN_TEXT.get(pin_mode, PIN_TEXT["unknown"]), tuple(notes), failures=tuple(failures),
                       blocked=human_only_block)
