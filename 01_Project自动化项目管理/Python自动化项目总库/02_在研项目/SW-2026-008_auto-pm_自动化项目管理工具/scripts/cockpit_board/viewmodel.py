"""视图模型：把 pm_dashboard 读出的数据算成画面要显示的东西。纯 Python，不 import Qt。

规则（设计稿第 0、3、6 节）：
    - 问题三档：block 阻塞（不处理会延期）/ risk 风险（要留意，还不挡路）/ hint 提醒（排班时顺手处理）。
    - 每条问题写明谁动手、依据是什么、等了多久；“等了多久”只在有起点时间时才算。
    - 六项机器检查三态：number 有数 / unchecked 没检查 / offline 断网未知。没数据源不得渲染为 0。
    - 健康：off 未接入 / block 受阻 / risk 有风险 / nodata 无数据（账本里没活，看不出好坏）/ ok 正常。
      缺账本或缺 Git 不许显示 ok。
    - “要你出手”只取谁动手 = 用户的问题，严重的在前、等得久的在前，每件附一句可复制的回复。
    - GitHub（PR、门禁、安全签字、审计）：这次没真读到（断网 / 限流 / 令牌 / 读失败 / 只有缓存）就一律“未知”、
      灰色，旧值只放小字参考；读到一部分的，没读到的那几格“未知”，汇总数遇到未知不许说 0。
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import github_collector as gh  # noqa: E402 - scripts/github_collector.py 数据层（GitHub，只读）
import pm_dashboard as pd  # noqa: E402 - scripts/pm_dashboard.py 数据层

SEV_RANK = {"block": 3, "risk": 2, "hint": 1}
SEV_LABEL = {"block": "阻塞", "risk": "风险", "hint": "提醒"}
HEALTH_LABEL = {"ok": "正常", "risk": "有风险", "block": "受阻", "old": "旧账", "nodata": "无数据", "off": "未接入"}
HEALTH_RANK = {"block": 5, "risk": 4, "old": 3, "nodata": 2, "ok": 1, "off": 0}
# D-324：项目下已没有开着的卡（全部 CLOSED / CANCELLED，或没有卡）时，账本一致性检查留下的问题算“旧账”：
# 降一级成提示、项目标“旧账”不标“有风险”，首页格子分开写“在干 X，旧账 Y”；不隐藏。
OLD_BASIS = "账本一致性检查（项目下已没有开着的卡，算旧账）"
CLOSED_STATES = ("CLOSED", "CANCELLED")
LOST_HOURS = 1  # 执行者失联：卡开着 + 租约过期 + 最近断点都超过这么久
USER = "你"

PHASES = ("需求", "设计", "编程", "仿真", "现场", "收尾")


@dataclass(frozen=True)
class Issue:
    sev: str
    project_id: str
    title: str
    detail: str
    who: str
    basis: str
    since: datetime | None
    example: bool = False


@dataclass(frozen=True)
class Decision:
    sev: str
    project_id: str
    ask: str
    why: str
    reply: str
    basis: str
    since: datetime | None
    example: bool = False
    link: str = ""  # 要去哪个网页回：PR 页面。有它时首页写“在 PR 页面评论这一行”，并给“复制链接”


@dataclass(frozen=True)
class Check:
    key: str
    label: str
    state: str  # number / unchecked / offline
    value: int = 0
    unit: str = ""
    note: str = ""
    soft: bool = False  # 数是真的，但有没跑 / 没声明的，0 也不给绿
    split: str = ""  # 分开写的数（D-324：“在干 X，旧账 Y”）；有它时格子显示它，颜色仍按 value（在干的数）

    @property
    def sev(self) -> str:
        if self.state != "number":
            return "na"
        if self.value == 0:
            return "na" if self.soft else "ok"
        return "block" if self.key in ("lost", "gate_red", "safety_unsigned") else "risk"

    @property
    def text(self) -> str:
        if self.state == "unchecked":
            return "没检查"
        if self.state == "offline":
            return "断网未知"
        if self.split:
            return self.split
        return f"{self.value} {self.unit}".strip()


@dataclass(frozen=True)
class Coverage:
    ledger: bool
    git: bool
    github: bool

    def text(self) -> str:
        return " ".join(
            f"{name} {'✓' if flag else '✗'}"
            for name, flag in (("账本", self.ledger), ("Git", self.git), ("GitHub", self.github))
        )


@dataclass
class ProjectCard:
    project_id: str
    name: str
    tool: bool
    registered: bool
    health: str
    coverage: Coverage
    milestone: str
    due_text: str
    now_card: str
    now_who: str
    now_step: str
    last_text: str
    issues: list[Issue] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    closed: bool = False  # 项目下已没有开着的卡（D-324）

    @property
    def health_label(self) -> str:
        return HEALTH_LABEL[self.health]


@dataclass
class BoardColumn:
    name: str
    note: str
    cards: list[tuple[str, str, str, bool]]  # (编号, 标题, 说明, 示例)


@dataclass
class EvidenceRow:
    state: str  # ok / block / risk / na
    title: str
    detail: str


@dataclass
class ChangeRow:
    change_id: str
    date: str
    kind: str
    what: str
    status: str
    when: datetime | None = None  # 排序用；没有日期（实施卡、“日期待补”）就是 None


@dataclass(frozen=True)
class Cell:
    text: str
    sev: str  # ok / risk / block / hint / na
    tip: str = ""


@dataclass
class PrRow:
    number: int
    title: str
    url: str
    author: str
    projects: list[str]
    gate: Cell
    ci: list[tuple[str, Cell]]
    safety: Cell
    audit: Cell
    note: str = ""
    rules: Cell = field(default_factory=lambda: Cell("未知", "na", "这次没从 GitHub 读到"))


@dataclass
class GithubVM:
    state: str  # ok / partial / offline / rate_limited / auth / error / disabled
    fresh: bool
    headline: str
    as_of: str
    main_ci: list[tuple[str, Cell]]
    rows: list[PrRow]
    notes: list[str]


@dataclass
class ProjectVM:
    card: ProjectCard
    columns: list[BoardColumn]
    evidence: list[EvidenceRow]
    changes: list[ChangeRow]
    activity: list[tuple[str, str, str, bool]]  # (时间, 说明, 谁, 示例)
    recipe: list[tuple[str, str]]
    github: GithubVM | None = None
    prs: list[PrRow] = field(default_factory=list)
    changes_more: str = ""  # “还有 M 条……”：变更记录只列最近 CHANGES_SHOWN 条，没列的在这里交代；全列了就是空


@dataclass
class HomeVM:
    decisions: list[Decision]
    decisions_total: int
    checks: list[Check]
    checks_ran: int
    hot: list[ProjectCard]
    rest: list[ProjectCard]
    activity: list[tuple[str, str, str, bool]]  # (时间, 项目, 说明, 示例)
    notes: list[str]
    github: GithubVM | None = None
    extra_issues: list[Issue] = field(default_factory=list)  # 归不到任何一张项目卡的问题（PR 只改了仓库公共文件等）
    issue_notes: list[str] = field(default_factory=list)  # 问题页顶上要说的：哪些没检查、条数不含它们


@dataclass
class Step:
    number: int
    title: str
    detail: str
    state: str  # done / cur / todo / unk（没核对：界面不知道，不冒充）
    command: str = ""
    buttons: list[tuple[str, str, bool, str]] = field(default_factory=list)  # (文字, 动作键, 可用, 原因)


@dataclass
class StationVM:
    identity: list[tuple[str, str]]
    warn: bool
    online: bool
    banner: str
    projects: list[tuple[ProjectCard, str, str, list[str], str, bool]]  # 卡, 上次干到, 下一步, 文件, 分支, 安全区
    steps: list[Step]
    records: list[tuple[str, list[str]]]
    safety_hits: list[str]


# ---------------------------------------------------------------- 小工具


def fmt(moment: datetime | None, offset: timezone) -> str:
    return moment.astimezone(offset).strftime("%m-%d %H:%M") if moment else "—"


def ago(now: datetime, moment: datetime | None) -> str:
    if moment is None:
        return "—"
    hours = (now - moment).total_seconds() / 3600
    if hours < 1:
        return f"{int(hours * 60)} 分钟前"
    if hours < 48:
        return f"{int(hours)} 小时前"
    return f"{int(hours / 24)} 天前"


def waited(now: datetime, moment: datetime | None) -> str:
    if moment is None:
        return "日期待补"
    hours = (now - moment).total_seconds() / 3600
    if hours < 24:
        return f"等了 {max(0, int(hours))} 小时"
    return f"等了 {int(hours / 24)} 天"


def _date(text: str) -> datetime | None:
    return pd.parse_time(text[:10]) if text[:4].isdigit() else None


def _open(project: pd.Project) -> list[pd.MissionInfo]:
    return [m for m in project.missions if m.column != "已关"]


def project_closed(project: pd.Project) -> bool:
    """D-324 判据（审计裁定）：项目下没有开着的卡＝全部卡是 CLOSED 或 CANCELLED，或者没有卡。不用旧文件里的“阶段”。"""
    return all(m.state in CLOSED_STATES for m in project.missions)


# ---------------------------------------------------------------- 问题三档


def project_issues(project: pd.Project, now: datetime) -> list[Issue]:
    issues: list[Issue] = []
    pid = project.project_id
    if not project.registered:
        return issues
    closed = project_closed(project)
    for m in _open(project):
        if m.state == "BLOCKED":
            issues.append(
                Issue(
                    "block", pid, "卡住要拿主意", pd._short(m.title, 60), USER + " → 主执行",
                    "账本里这张卡的状态是“卡住”", m.updated_at, m.example,
                )
            )
        elif m.state == "DRAFT" and not m.work_id and not m.approved:
            # D-328（审计裁定②）：没有工作项、也查不到批准记录的草稿，不是在等你拍板，多半是没开起来的陈卡；
            # 只提示，谁来办写主执行，不进“要你出手”。有批准记录、还没开工的照常算“等你”。
            issues.append(
                Issue(
                    "hint", pid, "草稿，没有工作项，也没有批准记录", pd._short(m.title, 60), "主执行（补工作项或作废）",
                    "账本里这张卡是草稿，下面没有工作项，也查不到你的批准记录", m.updated_at, m.example,
                )
            )
        elif m.column == "等你":
            ask = pd.waiting_ask(m)
            if pd._days(now, m.updated_at) > pd.WAITING_RED_DAYS:
                issues.append(
                    Issue(
                        "block", pid, f"等你超过 {pd.WAITING_RED_DAYS} 天：{ask}",
                        pd._short(m.title, 60), USER,
                        f"账本里这张卡的状态是“{pd.STATE_LABEL.get(m.state, m.state)}”，从进入这个状态算起", m.updated_at, m.example,
                    )
                )
            else:
                issues.append(
                    Issue(
                        "hint", pid, ask, pd._short(m.title, 60), USER,
                        f"账本里这张卡的状态是“{pd.STATE_LABEL.get(m.state, m.state)}”", m.updated_at, m.example,
                    )
                )
        elif m.state == "ACTIVE" and (m.run is None or m.run.state not in pd.OPEN_RUN_STATES or m.work_state == "CANCELLED"):
            # D-327：卡开着，但下面的工作项或最近一次执行已结束（如都已取消）：不是执行者失联，是卡没跟着收；主执行来办
            why = "没有执行记录" if m.run is None else f"最近一次执行 {m.run.run_id} 已是 {m.run.state}"
            if m.work_state == "CANCELLED":
                why = "工作项已取消，" + why
            issues.append(
                Issue(
                    "hint", pid, "卡开着，但下面没有在跑的执行", f"{why}：{pd._short(m.title, 40)}",
                    "主执行（关卡或重新派工）", "账本里这张卡还开着，下面的工作项和执行已经结束", m.updated_at, m.example,
                )
            )
        elif m.state == "ACTIVE" and m.run is not None:
            lease = m.run.lease_expires
            last = m.run.updated_at
            if (
                lease is not None
                and lease < now
                and (last is None or now - last > timedelta(hours=LOST_HOURS))
            ):
                issues.append(
                    Issue(
                        "block", pid, "执行者失联",
                        f"{m.run.executor} 的租约 {lease.strftime('%H:%M')} 到期，之后没有新断点："
                        f"{pd._short(m.title, 40)}",
                        "主执行立即查",
                        "账本里执行者的租约到期时间和最近一次断点", lease, m.example,
                    )
                )
        elif m.column == "搁着" and pd._days(now, m.updated_at) > pd.PARKED_YELLOW_DAYS:
            issues.append(
                Issue(
                    "hint", pid, f"搁了超过 {pd.PARKED_YELLOW_DAYS} 天", pd._short(m.title, 60),
                    USER + "（继续搁 / 取消）", "账本里这张卡的状态是“搁着”", m.updated_at, m.example,
                )
            )
    if len(_open(project)) > pd.OPEN_SOFT_LIMIT:
        issues.append(
            Issue(
                "hint", pid, f"开着的卡超过 {pd.OPEN_SOFT_LIMIT} 张",
                f"共 {len(_open(project))} 张", USER + "（挂起或关卡）", "账本里开着的卡", None,
            )
        )
    for a in project.attention:
        sev, who = {
            "执行记录没结账": ("hint", "主执行 D09 后结账"),
            "收口停在半路": ("risk", "主执行对账"),
            "工作项卡住": ("risk", "主执行"),
        }.get(a.what, ("hint", "主执行"))
        title = {"执行记录没结账": "账本遗留", "收口停在半路": "账本对不上"}.get(a.what, a.what)
        if closed:
            issues.append(Issue("hint", pid, title, a.detail, who, OLD_BASIS, a.since))
        else:
            issues.append(Issue(sev, pid, title, a.detail, who, "账本一致性检查", a.since))
    for c in project.changes:
        if c.status.startswith("待批"):
            issues.append(
                Issue(
                    "hint", pid, "业务变更待批", f"{c.change_id} {pd._short(c.what, 50)}", USER,
                    "02_业务变更记录.md 状态栏", _date(c.raised) or _date(c.status[2:].strip()),
                )
            )
    for pending in project.asks:  # 还没有 Mission 的“等你拍板”：口径同 pm pending / pm inbox list 的 PROPOSED（CHG-SCPT-2026-639）
        if pending.kind == "scope":
            issues.append(
                Issue(
                    "hint", pid, "批准范围", f"{pending.ref} {pending.subject}", USER,
                    f"账本里的范围卡第 {pending.revision} 版，还没批准（同 pm pending）", pending.since,
                )
            )
        elif pending.kind == "inbox":
            issues.append(
                Issue(
                    "hint", pid, "核对需求", f"{pending.ref} {pending.subject}", USER,
                    "账本收件箱里这一条还没确认（同 pm inbox list）", pending.since,
                )
            )
    for card in project.cards:
        if card.status.startswith("待批"):
            issues.append(
                Issue(
                    "hint", pid, "实施卡待批准派工", f"{card.card_id} {pd._short(card.title, 50)}",
                    USER, "03_实施卡 状态行", None,
                )
            )
    moments = [m.updated_at for m in _open(project) if m.updated_at]
    if project.last_commit:
        moments.append(project.last_commit)
    if _open(project) and moments and pd._days(now, max(moments)) > pd.QUIET_YELLOW_DAYS:
        issues.append(
            Issue(
                "hint", pid, f"{pd.QUIET_YELLOW_DAYS} 天没动静", "有活开着，账本和 git log 都没更新",
                USER + "看一眼", "账本最近一次更新和最近一次提交，取较晚的那个", max(moments),
            )
        )
    return sorted(issues, key=lambda i: (-SEV_RANK[i.sev], i.since or now))


# ---------------------------------------------------------------- 要你出手


def _reply(issue: Issue) -> str:
    subject = issue.detail.split(" ", 1)[0] if issue.title.startswith(("业务变更", "实施卡")) else issue.detail
    subject = pd._short(subject, 30)
    if "批准范围" in issue.title:
        return f"{subject} 范围认"
    if "验收" in issue.title:
        return f"{subject} 验收"
    if "核对需求" in issue.title:
        return f"{subject} 需求认（或写改哪里）"
    if "卡住" in issue.title:
        return f"{subject} 拿主意：…"
    if issue.title.startswith("业务变更"):
        return f"{subject} 批准"
    if issue.title.startswith("实施卡"):
        return f"{subject} 派工批准"
    if "搁" in issue.title:
        return f"{subject} 继续搁 / 取消"
    return f"{subject} 看过了"


def decisions_from(issues: list[Issue]) -> list[Decision]:
    out = [
        Decision(i.sev, i.project_id, i.title, i.detail, _reply(i), i.basis, i.since, i.example)
        for i in issues
        if i.who.startswith(USER)
    ]
    far = datetime.max.replace(tzinfo=UTC)
    return sorted(out, key=lambda d: (-SEV_RANK[d.sev], d.since or far))


def legacy_decision(project: pd.Project, covered: list[Decision]) -> Decision | None:
    """老驾驶舱后台的“要你做的动作”，没被账本状态覆盖时补一条。"""
    legacy = project.legacy
    if legacy is None or not legacy.readable:
        return None
    ask = pd.LEGACY_ASK.get(legacy.user_action, "")
    if not ask or any(d.project_id == project.project_id for d in covered):
        return None
    return Decision(
        "hint", project.project_id, ask, pd._short(legacy.next_action, 60), f"{ask}：认",
        "老驾驶舱后台给这个项目的状态卡", None,
    )


# ---------------------------------------------------------------- 健康、覆盖、卡片


def health_of(project: pd.Project, issues: list[Issue], coverage: Coverage) -> str:
    if not project.registered:
        return "off"
    top = max((SEV_RANK[i.sev] for i in issues), default=0)
    if top == 3:
        return "block"
    if top == 2:
        return "risk"
    if project_closed(project) and any(i.basis == OLD_BASIS for i in issues):
        return "old"
    if not _open(project) or not (coverage.ledger and coverage.git):
        return "nodata"
    return "ok"


def project_card(
    project: pd.Project, now: datetime, offset: timezone, ledger_ok: bool, git_ok: bool, github_ok: bool
) -> ProjectCard:
    issues = project_issues(project, now)
    cov = Coverage(ledger_ok and project.registered, git_ok and project.last_commit is not None, github_ok)
    active = next((m for m in _open(project) if m.state == "ACTIVE"), None)
    waiting = next((m for m in _open(project) if m.column == "等你"), None)
    now_card, who, step = "没有开着的活", "—", ""
    if active is not None:
        now_card = pd._short(active.title, 60)
        who = active.run.executor if active.run else "—"
        step = active.run.checkpoint if active.run else ""
    elif waiting is not None:
        now_card = f"（{pd.STATE_LABEL.get(waiting.state, waiting.state)}）{pd._short(waiting.title, 56)}"
    elif not project.registered:
        now_card, step = "只有文件夹，没登记进驾驶舱", "迁入时登记进 workspace_registry.json"
    moments = [m.updated_at for m in project.missions if m.updated_at]
    if project.last_commit:
        moments.append(project.last_commit)
    last = max(moments, default=None)
    legacy = project.legacy
    milestone = (
        f"阶段 {legacy.milestone}" if legacy and legacy.readable and legacy.milestone else "里程碑未填"
    )
    card = ProjectCard(
        project_id=project.project_id,
        name=project.name or project.project_id,
        tool=project.tool,
        registered=project.registered,
        health="",
        coverage=cov,
        milestone=milestone,
        due_text="到期未填",
        now_card=now_card,
        now_who=who,
        now_step=step,
        last_text=ago(now, last),
        issues=issues,
    )
    card.health = health_of(project, issues, cov)
    card.closed = project.registered and project_closed(project)
    card.decisions = decisions_from(issues)
    extra = legacy_decision(project, card.decisions)
    if extra is not None:
        card.decisions.append(extra)
    return card


# ---------------------------------------------------------------- GitHub：PR、门禁、安全签字、审计

GATE_TEXT = {"pass": "过", "fail": "红", "running": "在跑", "notrun": "没跑", "unknown": "未知", "na": "不适用"}
GATE_SEV = {"pass": "ok", "fail": "block", "running": "hint", "notrun": "na", "unknown": "na", "na": "na"}
SAFETY_TEXT = {"signed": "已签", "waiting": "等你签", "declared_no": "填了否", "undeclared": "没声明",
               "na": "不涉及", "unknown": "未知"}
SAFETY_SEV = {"signed": "ok", "waiting": "block", "declared_no": "na", "undeclared": "risk", "na": "na", "unknown": "na"}
RULES_TEXT = {"na": "不涉及", "waiting": "等你批准", "running": "检查在跑", "approved": "已批准", "unknown": "未知"}
RULES_SEV = {"na": "na", "waiting": "block", "running": "hint", "approved": "ok", "unknown": "na"}
AUDIT_TEXT = {"pass": "通过", "fail": "不通过", "conditional": "有条件通过", "unknown": "结论看不出"}
AUDIT_SEV = {"pass": "ok", "fail": "block", "conditional": "risk", "unknown": "na"}
GITHUB_HEADLINE = {
    "ok": "已从 GitHub 读到",
    "partial": "只读到一部分，没读到的格子标“未知”",
    "offline": "断网：下面全按“未知”显示",
    "rate_limited": "GitHub 限流：下面全按“未知”显示",
    "auth": "令牌不对或没给：下面全按“未知”显示",
    "error": "这次没读成：下面全按“未知”显示",
    "disabled": "没开 GitHub 采集",
}


def _audit_cell(pull: gh.PullInfo) -> Cell:
    audit = pull.audit
    if audit is None:
        return Cell("没审计记录", "na", "reviews/ 里没有对上这个 PR 号或分支名的审计")
    tip = f"审计 {audit.number}：{audit.summary}"
    if pull.audit_stale:
        return Cell(f"{audit.number} {AUDIT_TEXT[audit.verdict]}（审的是旧头 {audit.head[:8]}）", "risk",
                    tip + f"；现在的头是 {pull.head_sha[:8]}，之后的提交没审")
    return Cell(f"{audit.number} {AUDIT_TEXT[audit.verdict]}", AUDIT_SEV[audit.verdict], tip)


def pr_row(pull: gh.PullInfo, fresh: bool, as_of: str) -> PrRow:
    """一行 PR。fresh=False（断网 / 限流 / 只有缓存）时每格都是“未知”、灰色，旧值只进小字。"""
    ci = [(c.workflow, Cell(GATE_TEXT[c.state] if c.state != "na" else "不跑", GATE_SEV[c.state], c.detail))
          for c in pull.ci]
    gate = Cell(GATE_TEXT[pull.gate], GATE_SEV[pull.gate], "合起来看：有红就红，有未知就未知，应跑没跑算没跑")
    safety = Cell(SAFETY_TEXT[pull.safety.state], SAFETY_SEV[pull.safety.state], pull.safety.detail)
    audit = _audit_cell(pull)
    rules = Cell(RULES_TEXT[pull.rules.state], RULES_SEV[pull.rules.state], pull.rules.detail)
    note = "；".join(pull.errors)
    if not fresh:
        note = (f"上次读到 · {as_of}：门禁 {gate.text} · 安全签字 {safety.text}"
                + (f" · {note}" if note else ""))
        unknown = Cell("未知", "na", "这次没从 GitHub 读到")
        ci = [(name, unknown) for name, _cell in ci]
        gate, safety, rules = unknown, unknown, unknown
        audit = Cell(audit.text, "na", audit.tip + "（PR 头提交是旧数据，审的是不是当前头不确定）")
    projects = list(pull.projects) or ["未知"]
    title = ("【草稿】" if pull.draft else "") + pull.title
    return PrRow(pull.number, pd._short(title, 70), pull.url, pull.author, projects, gate, ci, safety, audit, note, rules)


def github_vm(snapshot: gh.Snapshot | None, now: datetime, offset: timezone) -> GithubVM:
    if snapshot is None:
        return GithubVM("disabled", False, GITHUB_HEADLINE["disabled"], "数据截至：没读过", [], [],
                        ["PR、门禁、安全签字都按“没检查”显示"])
    fresh = snapshot.fresh
    if snapshot.fetched_at is None:
        as_of = "数据截至：从没读到过"
    else:
        as_of = f"数据截至 {fmt(snapshot.fetched_at, offset)}（{ago(max(now, snapshot.checked_at), snapshot.fetched_at)}）"
    headline = GITHUB_HEADLINE.get(snapshot.state, GITHUB_HEADLINE["error"])
    if snapshot.state == "rate_limited" and snapshot.reset_at:
        headline = f"GitHub 限流，{fmt(snapshot.reset_at, offset)} 恢复：下面全按“未知”显示"
    if snapshot.from_cache:
        headline += "（列表是上次读到的旧数据）"
    unknown = Cell("未知", "na", "这次没从 GitHub 读到")
    main_ci = [
        (c.workflow, Cell(GATE_TEXT[c.state], GATE_SEV[c.state], c.detail) if fresh else unknown)
        for c in snapshot.main_ci
    ]
    notes = list(snapshot.errors)
    if snapshot.env_token_problem:
        notes.append(snapshot.env_token_problem)
    if snapshot.login_refused and not snapshot.authenticated:
        notes.append("登录被拒，暂用游客读取，重启后重试（每小时 60 次；也可以在终端重新运行 gh auth login）")
    elif not snapshot.authenticated and snapshot.state != "disabled":
        notes.append("没给令牌（本机没找到 GitHub 登录，也没有环境变量 GITHUB_TOKEN），按游客读：每小时 60 次，仓库改私有后就读不到；"
                     "在终端运行 gh auth login 登录后点“重新读取”")
    if snapshot.authenticated:
        notes.append("已用 GitHub 登录凭据（本机 gh 登录或环境变量里的令牌）读取：以你的身份只读，不写 GitHub")
    drafts = [p.number for p in snapshot.pulls if p.draft and p.rules.state in ("waiting", "running")]
    if fresh and drafts:
        notes.append("草稿 PR " + "、".join(f"#{n}" for n in drafts)
                     + " 也改了规则文件：转成可审（ready）后才会出现在“要你出手”里，现在批了，再推提交也要重批")
    notes.append(f"审计结论读自本机 reviews/ 目录，共 {len(snapshot.audits)} 份")
    rows = [pr_row(p, fresh, as_of) for p in snapshot.pulls]
    return GithubVM(snapshot.state, fresh, headline, as_of, main_ci, rows, notes)


RULE_FILES_SHOWN = 2


def _rule_files_text(files: tuple[str, ...]) -> str:
    shown = "、".join(pd._short(f, 40) for f in files[:RULE_FILES_SHOWN])
    return f"{shown} 等 {len(files)} 个" if len(files) > RULE_FILES_SHOWN else shown


def github_decisions(snapshot: gh.Snapshot | None) -> list[Decision]:
    """PR 上等你出手的：安全签字、规则批准。只在这次真读到时给；旧数据不催你。

    规则批准只列已转 ready 的 PR：草稿还会继续推提交，批准按头提交算，推一次就作废，现在批没有用（草稿数量写在 GitHub 区块的小字里）。
    回复那一行永远用这次读到的头提交前 12 位：PR 推了新提交，下一次读取（自动每 10 分钟，或点“重新读取”）这句话就跟着换。
    """
    if snapshot is None or not snapshot.fresh:
        return []
    out = []
    for pull in snapshot.pulls:
        pid = next((p for p in pull.projects if p != gh.SHARED), gh.SHARED)
        if pull.safety.state == "waiting":
            out.append(
                Decision(
                    "block", pid, f"PR #{pull.number} 等你安全签字", "仿真过了再在 PR 页面评论这一行 · " + pd._short(pull.title, 60),
                    # 只给那一行本身（“复制”复制的就是它，多一个字判卷都不认）；签字至少 12 位，短了 safety-zone 不认
                    f"安全签字 {pull.head_sha[:gh.MIN_SIGN_LEN]}",
                    "PR 描述“安全回路: 是”+ 评论里没有你签当前头提交", pd.parse_time(pull.updated_at), link=pull.url,
                )
            )
        if pull.rules.state in ("waiting", "running") and not pull.draft:
            check = "红（评论里还没有你对当前头提交的批准）" if pull.rules.state == "waiting" else "在跑（评论后约 1～2 分钟出结果）"
            out.append(
                Decision(
                    "block", pid, f"PR #{pull.number} 等你规则批准",
                    f"{pd._short(pull.title, 50)} · 改了规则文件 {_rule_files_text(pull.rules.files)} · "
                    f"审计：{_audit_cell(pull).text} · rules-approval 检查：{check} · 批准只对这个头提交有效，推了新提交要重批",
                    f"{gh.RULES_APPROVE_WORD} {pull.head_sha[:gh.RULES_SIGN_LEN]}",
                    "改了规则文件 + rules-gate 没绿",
                    pd.parse_time(pull.updated_at), link=pull.url,
                )
            )
    return out


def _red_checks(pull: gh.PullInfo) -> str:
    waiting = pull.rules.state == "waiting"  # 等你规则批准时 rules-gate 红是你的事，不算作者要修的
    names = [c.workflow for c in pull.ci if c.state == "fail" and not (waiting and c.workflow == gh.RULES_WORKFLOW)]
    return "、".join(names) if names else "合起来看是红"


def github_issues(snapshot: gh.Snapshot | None) -> list[Issue]:
    """开着的 PR 门禁红 → 问题页“风险”档（门禁红不是用户要定的事，是作者线程要修的事）。

    只在这次真读到时给；没读到（断网、限流、只有缓存）不凭旧数据报警，也不给 0——这一点由 ``github_issue_notes`` 在问题页上说明。
    """

    if snapshot is None or not snapshot.fresh:
        return []
    out = []
    for pull in snapshot.pulls:
        if pull.gate != "fail":
            continue
        pid = next((p for p in pull.projects if p != gh.SHARED), gh.SHARED)
        draft = "（草稿）" if pull.draft else ""
        out.append(
            Issue(
                "risk", pid, f"PR #{pull.number} 门禁红{draft}", f"红的检查：{_red_checks(pull)}；{pd._short(pull.title, 50)}",
                f"PR 作者线程修（{pull.author}）", "GitHub 检查结果（check-runs）；按 PR 改到的项目归属",
                pd.parse_time(pull.updated_at),
            )
        )
    return out


def github_issue_notes(snapshot: gh.Snapshot | None) -> list[str]:
    """问题页顶上的说明：GitHub 这一类没读到或没读全时，必须告诉用户“这页的条数不含它”，不能让空白当成没有。"""
    if snapshot is None or snapshot.state == "disabled":
        return ["GitHub 没开采集：PR 门禁红、安全区待签这类问题没检查，这页的条数不含它们。"]
    if not snapshot.fresh:
        why = GITHUB_HEADLINE.get(snapshot.state, "没读成").split("：")[0]
        return [f"GitHub 这次没读到（{why}）：PR 门禁红、安全区待签这类问题没检查，这页的条数不含它们。"]
    unknown = [p.number for p in snapshot.pulls if p.gate == "unknown"]
    if unknown:
        shown = "、".join(f"#{n}" for n in unknown[:6]) + ("…" if len(unknown) > 6 else "")
        return [f"{len(unknown)} 个 PR 的检查没读全（{shown}）：它们红不红不知道，没算进这页的条数。"]
    return []


def _gh_checks(snapshot: gh.Snapshot | None) -> tuple[Check, Check]:
    """门禁红的分支、安全区待签：没真读到就是没检查 / 断网未知；读到一部分且遇到未知，0 不许出现。"""
    if snapshot is None or not snapshot.fresh:
        state = "offline" if snapshot is not None and snapshot.state == "offline" else "unchecked"
        why = GITHUB_HEADLINE["disabled"] if snapshot is None else GITHUB_HEADLINE.get(snapshot.state, "没读成")
        return (
            Check("gate_red", "门禁红的分支", state, note=f"GitHub {why}"),
            Check("safety_unsigned", "安全区待签", state, note=f"GitHub {why}"),
        )
    pulls = snapshot.pulls
    red = sum(1 for p in pulls if p.gate == "fail")
    unknown = sum(1 for p in pulls if p.gate == "unknown")
    notrun = sum(1 for p in pulls if p.gate == "notrun")
    gate_note = f"开着的 PR {len(pulls)} 个；没跑 {notrun} 个（CI 按路径触发）"
    if unknown:
        gate_note += f"；{unknown} 个没读全"
    if red == 0 and unknown:
        gate = Check("gate_red", "门禁红的分支", "unchecked", note=gate_note + "，不能说 0")
    else:
        gate = Check("gate_red", "门禁红的分支", "number", red, "个", gate_note, soft=bool(notrun or unknown))
    waiting = sum(1 for p in pulls if p.safety.state == "waiting")
    undeclared = sum(1 for p in pulls if p.safety.state == "undeclared")
    s_unknown = sum(1 for p in pulls if p.safety.state == "unknown")
    safety_note = "按 PR 描述“安全回路: 是”且没有你签当前头提交计"
    if undeclared:
        safety_note += f"；改了 PLC 没声明的 {undeclared} 个"
    safety_note += "；填“否”却碰了安全区的要等 safety-gate 合进 main 才算得到"
    if waiting == 0 and s_unknown:
        safety = Check("safety_unsigned", "安全区待签", "unchecked", note=f"{s_unknown} 个 PR 评论没读到，不能说 0")
    else:
        safety = Check("safety_unsigned", "安全区待签", "number", waiting, "个", safety_note,
                       soft=bool(undeclared or s_unknown or any(p.safety.state == "declared_no" for p in pulls)))
    return gate, safety


def _rows_of(github: GithubVM | None, project_id: str) -> list[PrRow]:
    return [r for r in (github.rows if github else []) if project_id in r.projects]


def _gh_evidence(github: GithubVM | None, rows: list[PrRow]) -> list[EvidenceRow]:
    if github is None or github.state == "disabled":
        return [
            EvidenceRow("na", "门禁", "没检查：GitHub 采集没开"),
            EvidenceRow("na", "安全区签字", "没检查：GitHub 采集没开"),
            EvidenceRow("na", "独立审计", "没检查：GitHub 采集没开"),
        ]
    if not github.fresh:
        why = f"未知：{github.headline}；{github.as_of}"
        audit = "；".join(f"#{r.number} {r.audit.text}" for r in rows) or "没有开着的 PR"
        return [
            EvidenceRow("na", "门禁", why),
            EvidenceRow("na", "安全区签字", why),
            EvidenceRow("na", "独立审计", f"本机 reviews/ 读到：{audit}（PR 是旧数据，不判过）"),
        ]
    if not rows:
        none = f"没有改到这个项目的开着的 PR · {github.as_of}"
        return [EvidenceRow("na", "门禁", none), EvidenceRow("na", "安全区签字", none),
                EvidenceRow("na", "独立审计", none)]

    def worst(cells: list[Cell]) -> str:
        sevs = [c.sev for c in cells]
        for sev in ("block", "risk", "na", "hint"):
            if sev in sevs:
                return "na" if sev == "hint" else sev
        return "ok"

    def line(pick: Callable[[Any], Any]) -> str:
        return "；".join(f"#{r.number} {pick(r).text}" for r in rows) + f" · {github.as_of}"

    return [
        EvidenceRow(worst([r.gate for r in rows]), "门禁", line(lambda r: r.gate)),
        EvidenceRow(worst([r.safety for r in rows]), "安全区签字", line(lambda r: r.safety)),
        EvidenceRow(worst([r.audit for r in rows]), "独立审计", line(lambda r: r.audit)),
    ]


# ---------------------------------------------------------------- 六项检查


def checks_of(
    board: pd.Board, cards: list[ProjectCard], online: bool | None, github: gh.Snapshot | None = None
) -> list[Check]:
    """六项机器检查。没有数据源的一律 unchecked，绝不渲染为 0（设计稿第 3.1 节）。"""
    gate, safety = _gh_checks(github)
    if online is False and (github is None or not github.fresh):
        gate = Check(gate.key, gate.label, "offline", note=gate.note)
        safety = Check(safety.key, safety.label, "offline", note=safety.note)
    lost = sum(1 for c in cards for i in c.issues if i.title == "执行者失联")
    mismatch_titles = ("账本对不上", "工作项卡住")
    mismatch = sum(1 for c in cards if not c.closed for i in c.issues if i.title in mismatch_titles)
    mismatch_old = sum(1 for c in cards if c.closed for i in c.issues if i.title in mismatch_titles)
    unverified = sum(
        1
        for p in board.projects
        for m in p.missions
        if m.state == "CLOSED" and m.closure_state and m.closure_state != "COMPLETED"
    )
    return [
        gate,
        Check("scope", "越界改动", "unchecked", note="越界检查（pr-scope-check）还没合进 main"),
        Check(
            "unverified", "说完成但机器没过", "number", unverified, "张",
            "只查账本路线：已关的卡收口单是否 COMPLETED。PR 路线（审计编号）算不出",
        ),
        safety,
        Check(
            "mismatch", "账本对不上", "number", mismatch, "条",
            "收口单与卡状态、工作项 BLOCKED；旧账＝项目下已没有开着的卡时留下的，分开计、不算风险",
            soft=bool(mismatch_old), split=f"在干 {mismatch}，旧账 {mismatch_old}" if mismatch_old else "",
        ),
        Check(
            "lost", "执行者失联", "number", lost, "个",
            "卡开着 + 租约过期 + 最近断点超过 1 小时；只覆盖写账本的执行者",
        ),
    ]


# ---------------------------------------------------------------- 首页 / 问题 / 项目页


def home_vm(
    board: pd.Board, offset: timezone, online: bool | None, use_git: bool, github: gh.Snapshot | None = None
) -> HomeVM:
    now = board.generated_at
    ledger_ok = board.ledger_note.startswith("账本只读")
    github_ok = github is not None and github.fresh
    cards = [project_card(p, now, offset, ledger_ok, use_git, github_ok) for p in board.projects]
    pr_decisions = github_decisions(github)
    for card in cards:
        card.decisions += [d for d in pr_decisions if d.project_id == card.project_id]
    by_card = {c.project_id: c for c in cards}
    extra_issues: list[Issue] = []
    for issue in github_issues(github):
        if issue.project_id in by_card:
            by_card[issue.project_id].issues.append(issue)
        else:
            extra_issues.append(issue)
    known = {c.project_id for c in cards}
    decisions = sorted(
        [*(d for c in cards for d in c.decisions), *(d for d in pr_decisions if d.project_id not in known)],
        key=lambda d: (-SEV_RANK[d.sev], d.since or datetime.max.replace(tzinfo=UTC)),
    )
    checks = checks_of(board, cards, online, github)
    hot = sorted(
        [c for c in cards if c.health in ("block", "risk")],
        key=lambda c: (-HEALTH_RANK[c.health], c.tool, c.project_id),
    )
    rest = sorted(
        [c for c in cards if c.health not in ("block", "risk")],
        key=lambda c: (-HEALTH_RANK[c.health], c.tool, c.project_id),
    )
    activity = [
        (moment.strftime("%m-%d") if date_only else fmt(moment, offset), pid, text, example)
        for moment, pid, text, example, date_only in pd.recent_events(board)
    ]
    notes = [board.ledger_note]
    if board.legacy_note:
        notes.append(board.legacy_note)
    if board.example:
        notes.append("含示例卡（标【示例】的不是真数据）")
    return HomeVM(
        decisions=decisions[: pd.MAX_DECISIONS],
        decisions_total=len(decisions),
        checks=checks,
        checks_ran=sum(1 for c in checks if c.state == "number"),
        hot=hot,
        rest=rest,
        activity=activity,
        notes=notes,
        github=github_vm(github, now, offset),
        extra_issues=extra_issues,
        issue_notes=github_issue_notes(github),
    )


def all_issues(home: HomeVM) -> list[Issue]:
    far = datetime.max.replace(tzinfo=UTC)
    return sorted(
        (*(i for c in home.hot + home.rest for i in c.issues), *home.extra_issues),
        key=lambda i: (-SEV_RANK[i.sev], i.since or far),
    )


CHANGES_SHOWN = 30  # 变更记录页只列最近这么多条（SW-2026-008 有 400 多张变更单，全列一页要翻很久，最新的还在最底下）


def _day(text: str) -> datetime | None:
    """“2026-10-21” 或 “2026-10-21 14:00” 这类开头是日期的文字 → 当天零点（UTC）；其他写法（含“日期待补”）→ None。"""
    return pd.parse_time(text[:10]) if text[:4].isdigit() else None


# 还没收口的变更：不论多旧都列出来，不占“最近 N 条”的名额（协调者 2026-11-02 裁决：未收口的变更绝不藏起来）
UNCLOSED_STATUS = frozenset({"draft", "approved", "implementing", "pending_acceptance", "未读到状态"})


def is_unclosed(row: ChangeRow) -> bool:
    """变更单状态在 UNCLOSED_STATUS 里，或业务变更还是“待批…”；收口记录、实施卡不算。"""
    if row.kind == "收口" or row.kind == "实施卡":
        return False
    return row.status.strip().lower() in UNCLOSED_STATUS or row.status.startswith("待批")


def _newest_first(rows: list[ChangeRow]) -> list[ChangeRow]:
    """有日期的从新到旧（同一天编号大的在前），没有日期的排在后面，不会冒充最新。"""
    dated = sorted((r for r in rows if r.when is not None),
                   key=lambda r: (r.when or datetime.min.replace(tzinfo=UTC), r.change_id), reverse=True)
    return dated + [r for r in rows if r.when is None]


def recent_changes(rows: list[ChangeRow], root: str, limit: int = CHANGES_SHOWN) -> tuple[list[ChangeRow], str]:
    """没收口的变更全列在最上面（不占名额）；已收口的从新到旧，只留最近 ``limit`` 条。

    返回（要显示的行, “还有 M 条……”那一句）。M 只数没列出的已收口变更；全列了就是空串。
    """

    open_rows = _newest_first([r for r in rows if is_unclosed(r)])
    closed = _newest_first([r for r in rows if not is_unclosed(r)])
    shown_closed, hidden = closed[:limit], closed[limit:]
    shown = open_rows + shown_closed
    if not hidden:
        return shown, ""
    undated = sum(1 for r in hidden if r.when is None)
    where = f"{root}/…/01_变更管理/" if root else "项目文件夹的 01_变更管理/"
    note = (f"还有 {len(hidden)} 条更早的已收口变更没在这里列出（没收口的都在上面，不占名额；已收口的列了最近 {limit} 条，从新到旧"
            + (f"；没列出的里有 {undated} 条没写日期" if undated else "") + f"）。完整清单在 {where}")
    return shown, note


def project_vm(
    board: pd.Board, card: ProjectCard, offset: timezone, online: bool | None, github: GithubVM | None = None
) -> ProjectVM:
    now = board.generated_at
    rows = _rows_of(github, card.project_id)
    project = next(p for p in board.projects if p.project_id == card.project_id)
    columns: list[BoardColumn] = []
    for name in pd.COLUMNS:
        if name == "已关":
            missions = pd._recent_closed(project, now)
        else:
            missions = [m for m in project.missions if m.column == name]
        card_rows = []  # 这一栏的卡；别和上面的 PR 行 rows 混用
        for m in missions:
            bits = [pd.STATE_LABEL.get(m.state, m.state)]
            if m.run and m.column == "在干":
                bits.append(m.run.executor)
                if m.run.lease_expires:
                    bits.append("租约到 " + fmt(m.run.lease_expires, offset))
            if m.change_id:
                bits.append(m.change_id)
            if m.column == "搁着":
                if m.park_reason:
                    bits.append("原因：" + pd._short(m.park_reason, 40))
                if m.park_summary:
                    bits.append("断点：" + pd._short(m.park_summary, 60))
            card_rows.append((m.mission_id, pd._short(m.title, 70), " · ".join(bits), m.example))
        note = "没有搁着的卡" if name == "搁着" and not card_rows else ""
        columns.append(BoardColumn(name, note, card_rows))
    evidence = [
        EvidenceRow(
            "ok" if not any(i.title == "账本对不上" for i in card.issues) else "na" if card.closed else "risk",
            "账本一致性",
            "收口单与卡状态、工作项、过期执行记录（本机账本副本）"
            + ("；项目下已没有开着的卡，留下的算旧账，不算风险" if card.closed else ""),
        ),
        EvidenceRow(
            "ok" if not any(m.state == "CLOSED" and m.closure_state not in ("", "COMPLETED") for m in project.missions) else "block",
            "质量回执",
            "已关的卡收口单是否 COMPLETED（账本路线）",
        ),
        *_gh_evidence(github, rows),
        EvidenceRow("na", "越界检查", "没检查：pr-scope-check 未合"),
        EvidenceRow("na", "仿真实跑", "无记录：现场回传设计稿 D09 后落地"),
    ]
    dated = [
        ChangeRow(c.change_id, c.raised or "日期待补", c.kind, c.what, c.status, _day(c.raised))
        for c in project.changes
    ]
    dated += [
        ChangeRow(o.change_id, o.raised or "日期待补", f"变更单 {o.domain}", o.what, o.status, _day(o.raised))
        for o in project.change_orders
    ]
    dated += [
        ChangeRow(m.change_id, fmt(m.updated_at, offset), "收口", pd._short(m.title, 50), m.closure_state, m.updated_at)
        for m in project.missions
        if m.change_id
    ]
    cards = [ChangeRow(c.card_id, "", "实施卡", c.title, c.status) for c in project.cards]
    changes, more = recent_changes(dated, project.root)
    changes += cards  # 实施卡没有日期、数量也少：全列，放在最后，不占“最近 N 条”的名额
    activity = [
        (fmt(m.updated_at, offset), f"{pd.STATE_LABEL.get(m.state, m.state)}：{pd._short(m.title, 50)}",
         m.run.executor if m.run else "", m.example)
        for m in sorted(project.missions, key=lambda m: m.updated_at or now, reverse=True)[:8]
    ]
    recipe = [
        ("规范", "00_Obsidian_Base… 规范库（git log 取版本）"),
        ("模板", "0100_PLC自动化/00_通用规范/项目文档模板"),
        ("共享库", "01_SharedLibraries（LSP-903 文件头 VERSION）"),
        ("所在文件夹", project.root or "—"),
    ]
    return ProjectVM(card, columns, evidence, changes, activity, recipe, github, rows, more)


# ---------------------------------------------------------------- 工程工位


STEP_TITLES = (
    ("开分支", "从 origin/main 切人工分支 manual/<日期>-<主题>"),
    ("改程序并同步 .scl", "编译过没过只认 InoProShop / 博图，本页不判"),
    ("跑检查", "结果来自本机真实运行；没装语言服务插件显示“未验证”，不显示通过"),
    ("记一行业务变更（BC）", "本页唯一会写文件的动作：只往表末追加一行，写前预览，写后 git status"),
    ("本机提交", "只给提交说明；提交在命令提示符里做；绕过联锁只限你本人，本页没有这个按钮"),
    ("有网之后", "推 manual/ 分支、开 PR；AI 回来后补跑提交检查和审计，安全签字后才合并"),
)


def station_vm(
    board: pd.Board,
    cards: list[ProjectCard],
    online: bool | None,
    identity: dict[str, str],
    manual_branch: str,
    safety_hits: list[str],
    decisions_wired: bool = False,
    net_note: str = "",
) -> StationVM:
    off = online is False
    projects = []
    for card in cards:
        if card.tool or not card.registered:
            continue
        project = next(p for p in board.projects if p.project_id == card.project_id)
        files = [project.root + "/"]  # PM_SESSION 已于 2026-10-10 退役，不再引导去打开它
        files += [f"{project.root}/…/03_实施卡/{c.card_id}.md" for c in project.cards[:2]]
        safety = any("安全" in c.what or "安全" in c.status for c in project.changes) or bool(
            safety_hits and card.project_id in safety_hits[0]
        )
        left = card.now_step or card.now_card
        nxt = "照实施卡的未勾项接着做" if project.cards else "没有实施卡：先在第 4 步记一行业务变更（BC），再开卡"
        projects.append((card, left, nxt, files, f"manual/{card.project_id.lower()}", safety))
    # net_note 是探测给出的具体原因（超时 / 认证失败 / 地址错误 / 没有 origin …）；按钮灰着时把它写在按钮旁边
    reason = net_note if net_note.startswith("离线") else "离线：读不到 origin" + (f"（{net_note}）" if net_note else "")
    dis_off = (not off, reason)
    steps = [
        # 开分支、改程序都是人在本机做的事，界面没有去核对，所以写“没核对”，不冒充“已完成 / 进行中”
        Step(1, *STEP_TITLES[0], "unk", f"git switch -c {manual_branch} origin/main"),
        Step(2, *STEP_TITLES[1], "unk"),
        Step(
            3, *STEP_TITLES[2], "todo", "",
            [("重新跑 plc check", "plc_check", True, ""), ("plc docs check", "docs_check", True, ""),
             ("docs sync 预览", "docs_sync_preview", True, "")],
        ),
        Step(4, *STEP_TITLES[3], "todo", "", [("预览", "bc_preview", True, ""), ("写入 02_业务变更记录.md", "bc_write", True, "写前先预览"), ("打开文件", "bc_open", True, "")]),
        Step(5, *STEP_TITLES[4], "todo", "", [("复制提交说明", "copy_commit", True, ""), ("提交", "commit", False, "提交在命令提示符里做，本页不替你提交")]),
        Step(
            6, *STEP_TITLES[5], "todo", "",
            # 推送 / 开 PR 本版只给提示不做：在命令提示符里 git push，到 GitHub 网页开 PR
            [("推送 manual/ 分支", "push", False, dis_off[1] if off else "本版不做：在命令提示符里 git push -u origin manual/…"),
             ("打开 GitHub 开 PR", "open_pr", False, dis_off[1] if off else "本版不做：推送后到 GitHub 网页开 PR"),
             ("批准范围", "approve", decisions_wired, "界面里的批准要等接上批准口令弹窗才开放；现在请在终端运行 main.py pm approve"),
             ("开工", "start", decisions_wired, "界面里的开工要等接线后才开放，且和批准分开；不启动任何 agent；现在请运行 main.py pm confirm-start")],
        ),
    ]
    records = []
    for card, _left, _nxt, _files, branch, safety in projects:
        items = ["实施卡状态改“执行中 · 人工 日期”", f"有网后：推 {branch}、开 PR"]
        if safety:
            items.insert(1, "改了安全区：业务变更记录加一行，注明“安全区，待仿真 + 签字”；PR 上写“安全签字 + 提交号”")
        records.append((card.project_id, items))
    ident = [
        ("身份", "工程工位 · 人工"),
        ("源码", identity.get("source") or "—"),
        ("生效版本", identity.get("effective") or "—"),
        ("控制根", identity.get("control_root") or "—"),
        ("网络", (net_note or "离线（git ls-remote 读不到 origin）") if off else ("在线" if online else "未探测")),
        ("采集", identity.get("collected", "—")),
    ]
    warn = off or identity.get("source", "") != identity.get("configured", identity.get("source", ""))
    if not off:
        banner = ""
    elif decisions_wired:  # 批准、开工只写本机账本，不需要网，离线照常可用
        banner = "当前离线：推送、开 PR 已灰化并写明原因；本机检查、记 BC、批准、开工、复制提交说明照常可用。"
    else:
        banner = "当前离线：推送、开 PR、批准、开工都已灰化并写明原因；本机检查、记 BC、复制提交说明照常可用。"
    return StationVM(ident, warn, bool(online), banner, projects, steps, records, safety_hits)
