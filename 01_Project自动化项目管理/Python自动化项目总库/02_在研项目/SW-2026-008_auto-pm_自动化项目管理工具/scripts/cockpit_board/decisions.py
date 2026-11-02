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


@dataclass(frozen=True)
class Decision:
    """一个决定按钮。``kind`` 说明它作用在什么对象上：mission（一张卡）、scope_card（待批准的范围卡）、inbox（收件箱条目）。"""

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


_SWITCH_FIELDS = (
    Field("reason", "手上这张为什么先放下", "例如：客户急改 IO 表"),
    Field("summary", "手上这张的断点", "干到哪了、下一步做什么（一行，不换行）"),
    Field("as_owner", "谁来干急活", "接手的 agent 身份，例如 claude:cloud 或 trae:cn"),
)

DECISIONS: tuple[Decision, ...] = (
    Decision(
        "approve_card", "批准范围", "scope_card",
        "批准这张范围卡：只批准你看过的这一版（哈希对不上命令会拒绝）。批准不会启动任何 agent。",
        ("pm", "approve"), pin=True, user_words=True,
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
        ("pm", "accept"), states=frozenset({"ACCEPTANCE_PENDING"}), pin=True,
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
        ("pm", "park"), states=frozenset({"ACTIVE"}), pin=True, user_words=True,
        fields=(Field("reason", "为什么先放下", "例如：客户急改 IO 表"),
                Field("summary", "断点", "干到哪了、下一步做什么（一行，不换行）")),
    ),
    Decision(
        "unpark", "拿回", "mission",
        "拿回这张卡：先核对工作树没被动过，再发新钥匙（钥匙存本机钱包，不显示）。拿回后先同步 main 再干活。",
        ("pm", "unpark"), states=frozenset({"PARKED", "BLOCKED"}), pin=True, user_words=True,
        fields=(Field("as_owner", "谁来接着干", "接手的 agent 身份，例如 claude:cloud 或 trae:cn"),),
    ),
    Decision(
        "switch", "插急活", "mission",
        "改干这一张：把手上在干的那张记好断点搁着，再把这张拿起来；第二步失败时第一张稳稳停在“搁着”。",
        ("pm", "switch"), states=frozenset({"PARKED", "DRAFT", "AWAITING_APPROVAL"}), pin=True, user_words=True,
        fields=_SWITCH_FIELDS,
    ),
    Decision(
        "inbox_confirm", "确认入箱", "inbox",
        "确认这条收件箱事项：只确认你看到的这一版（内容哈希对不上命令会拒绝）。确认不等于开工。",
        ("pm", "inbox", "confirm"), user_words=True, pin=True,
        fields=(Field("note", "备注（可空）", "一行", required=False),),
    ),
    Decision(
        "inbox_reject", "驳回入箱", "inbox",
        "驳回这条收件箱事项：写明理由，之后它不再出现在“等你”。",
        ("pm", "inbox", "reject"), user_words=True, pin=True,
        fields=(Field("note", "驳回理由", "一行"),),
    ),
)

BY_KEY = {item.key: item for item in DECISIONS}

# 决定页上允许出现的按钮文字，另加弹窗里的两个确认键。测试按它清点。
DECISION_BUTTONS = frozenset({item.label for item in DECISIONS}) | frozenset({
    "确认并运行", "在终端窗口里运行", "取消", "知道了", "复制命令", "展开控制台", "收起控制台",
})
# 永远不加的动作（同 policy.NEVER，另加几条本页特有的）；按钮文字、对话框文字里都不许出现。
NEVER_WORDS = (*policy.NEVER, "启动 agent", "强推")

READ_ONLY_COMMANDS = {
    "pending": ("pm", "pending", "--project-id"),
    "inbox": ("pm", "inbox", "list", "--project-id"),
    "pin_status": ("pm", "approver-pin", "status"),
}

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
        subject = target.mission_id or target.request_id or target.item_id
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
    for item in _json(text).get("cards", []):
        card = item.get("card", {}) if isinstance(item, dict) else {}
        if not isinstance(card, dict) or item.get("superseded"):
            continue
        found.append(Target(project_id=project_id, request_id=str(card.get("request_id", "")),
                            plan_hash=str(card.get("plan_hash", "")), title=str(item.get("objective", ""))))
    return [t for t in found if t.request_id and t.plan_hash]


def parse_inbox(text: str, project_id: str) -> list[Target]:
    """``pm inbox list --project-id P`` 的 JSON → 等你确认的条目（状态 PROPOSED）。"""

    found = []
    for item in _json(text).get("items", []):
        if isinstance(item, dict) and str(item.get("status", "")).upper() == "PROPOSED":
            found.append(Target(project_id=project_id, item_id=str(item.get("item_id", "")),
                                ticket_hash=str(item.get("ticket_hash", "")), title=str(item.get("title", ""))))
    return [t for t in found if t.item_id and t.ticket_hash]


def _last_line(text: str, limit: int = 200) -> str:
    lines = [line.strip() for line in (text or "").strip().splitlines() if line.strip()]
    return lines[-1][:limit] if lines else ""


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

    column: str  # 在干 / 等你 / 搁着 / 已关 / 范围卡 / 收件箱
    heading: str
    detail: str
    target: Target
    decisions: tuple[Decision, ...]
    sev: str = ""  # "" / "risk"（搁着超过 7 天）


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


PIN_TEXT = {
    "enforced": "批准口令：已生效（批准、验收、搁着、拿回会在新的终端窗口里问口令）",
    "off": "批准口令：未生效（批准只做格式检查，这是已知缺口，口令设好后自动改走口令）",
    "suspended": "批准口令：所有批准暂停（登记文件有问题），决定类按钮会被命令拒绝",
    "unknown": "批准口令：没读到状态（按未生效处理，命令自己会判）",
}

_COLUMN_ORDER = ("范围卡", "收件箱", "等你", "在干", "搁着", "已关")


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
) -> DecisionsVM:
    """把看板的 Mission（需有 mission_id / project_id / title / state / column）和只读命令读到的对象排成卡。

    “已关”栏里只有已验收未收口（ACCEPTED）的卡带按钮，其余（已收口、已作废）不出现，免得误点。
    """

    cards: list[CardVM] = []
    active_projects = {m.project_id for m in missions if m.state == "ACTIVE"}
    for pid, targets in pending.items():
        for t in targets:
            cards.append(CardVM("范围卡", t.title or t.request_id, f"请求 {t.request_id} · 哈希 {t.plan_hash[:12]}…", t,
                                (BY_KEY["approve_card"],)))
    for pid, targets in inbox.items():
        for t in targets:
            cards.append(CardVM("收件箱", t.title or t.item_id, f"条目 {t.item_id} · 哈希 {t.ticket_hash[:12]}…", t,
                                (BY_KEY["inbox_confirm"], BY_KEY["inbox_reject"])))
    for m in missions:
        buttons = _for_state(m.state, m.project_id in active_projects)
        if m.state in ("CLOSED", "CANCELLED") or not buttons:
            continue
        target = Target(project_id=m.project_id, mission_id=m.mission_id, title=m.title, state=m.state)
        cards.append(CardVM(m.column, m.title or m.mission_id, f"{m.mission_id} · {m.project_id} · {pd.STATE_LABEL.get(m.state, m.state)}", target, buttons,
                            "risk" if m.mission_id in stale_ids else ""))
    cards.sort(key=lambda c: (_COLUMN_ORDER.index(c.column) if c.column in _COLUMN_ORDER else 99, c.heading))
    return DecisionsVM(tuple(cards), pin_mode, PIN_TEXT.get(pin_mode, PIN_TEXT["unknown"]), failures=tuple(failures))
