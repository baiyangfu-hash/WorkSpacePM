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
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import github_collector as gh  # noqa: E402 - scripts/github_collector.py 数据层（GitHub，只读）
import pm_dashboard as pd  # noqa: E402 - scripts/pm_dashboard.py 数据层

SEV_RANK = {"block": 3, "risk": 2, "hint": 1}
SEV_LABEL = {"block": "阻塞", "risk": "风险", "hint": "提醒"}
HEALTH_LABEL = {"ok": "正常", "risk": "有风险", "block": "受阻", "nodata": "无数据", "off": "未接入"}
HEALTH_RANK = {"block": 4, "risk": 3, "nodata": 2, "ok": 1, "off": 0}
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


@dataclass(frozen=True)
class Check:
    key: str
    label: str
    state: str  # number / unchecked / offline
    value: int = 0
    unit: str = ""
    note: str = ""
    soft: bool = False  # 数是真的，但有没跑 / 没声明的，0 也不给绿

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


@dataclass
class Step:
    number: int
    title: str
    detail: str
    state: str  # done / cur / todo
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


# ---------------------------------------------------------------- 问题三档


def project_issues(project: pd.Project, now: datetime) -> list[Issue]:
    issues: list[Issue] = []
    pid = project.project_id
    if not project.registered:
        return issues
    for m in _open(project):
        if m.state == "BLOCKED":
            issues.append(
                Issue(
                    "block", pid, "卡住要拿主意", pd._short(m.title, 60), USER + " → 主执行",
                    "账本 mission.state = BLOCKED", m.updated_at, m.example,
                )
            )
        elif m.column == "等你":
            ask = pd.WAITING_ASK.get(m.state, "看一眼")
            if pd._days(now, m.updated_at) > pd.WAITING_RED_DAYS:
                issues.append(
                    Issue(
                        "block", pid, f"等你超过 {pd.WAITING_RED_DAYS} 天：{ask}",
                        pd._short(m.title, 60), USER,
                        f"账本 mission.state = {m.state}，进入该状态的时间", m.updated_at, m.example,
                    )
                )
            else:
                issues.append(
                    Issue(
                        "hint", pid, ask, pd._short(m.title, 60), USER,
                        f"账本 mission.state = {m.state}", m.updated_at, m.example,
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
                        "账本 execution_leases.expires_at + checkpoints 最近一条", lease, m.example,
                    )
                )
        elif m.column == "搁着" and pd._days(now, m.updated_at) > pd.PARKED_YELLOW_DAYS:
            issues.append(
                Issue(
                    "hint", pid, f"搁了超过 {pd.PARKED_YELLOW_DAYS} 天", pd._short(m.title, 60),
                    USER + "（继续搁 / 取消）", "账本 mission.state = PARKED", m.updated_at, m.example,
                )
            )
    if len(_open(project)) > pd.OPEN_SOFT_LIMIT:
        issues.append(
            Issue(
                "hint", pid, f"开着的卡超过 {pd.OPEN_SOFT_LIMIT} 张",
                f"共 {len(_open(project))} 张", USER + "（挂起或关卡）", "账本 mission_items", None,
            )
        )
    for a in project.attention:
        sev, who = {
            "执行记录没结账": ("hint", "主执行 D09 后结账"),
            "收口停在半路": ("risk", "主执行对账"),
            "工作项卡住": ("risk", "主执行"),
        }.get(a.what, ("hint", "主执行"))
        title = {"执行记录没结账": "账本遗留", "收口停在半路": "账本对不上"}.get(a.what, a.what)
        issues.append(Issue(sev, pid, title, a.detail, who, "账本一致性检查", a.since))
    for c in project.changes:
        if c.status.startswith("待批"):
            issues.append(
                Issue(
                    "hint", pid, "业务变更待批", f"{c.change_id} {pd._short(c.what, 50)}", USER,
                    "02_业务变更记录.md 状态栏", _date(c.raised) or _date(c.status[2:].strip()),
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
                USER + "看一眼", "max(账本 updated_at, git log -1)", max(moments),
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
        "老驾驶舱后台 snapshot()", None,
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
    note = "；".join(pull.errors)
    if not fresh:
        note = (f"上次读到 · {as_of}：门禁 {gate.text} · 安全签字 {safety.text}"
                + (f" · {note}" if note else ""))
        unknown = Cell("未知", "na", "这次没从 GitHub 读到")
        ci = [(name, unknown) for name, _cell in ci]
        gate, safety = unknown, unknown
        audit = Cell(audit.text, "na", audit.tip + "（PR 头提交是旧数据，审的是不是当前头不确定）")
    projects = list(pull.projects) or ["未知"]
    title = ("【草稿】" if pull.draft else "") + pull.title
    return PrRow(pull.number, pd._short(title, 70), pull.url, pull.author, projects, gate, ci, safety, audit, note)


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
    if not snapshot.authenticated and snapshot.state != "disabled":
        notes.append("没给令牌（环境变量 GITHUB_TOKEN），按游客读：每小时 60 次，仓库改私有后就读不到")
    notes.append(f"审计结论读自本机 reviews/ 目录，共 {len(snapshot.audits)} 份")
    rows = [pr_row(p, fresh, as_of) for p in snapshot.pulls]
    return GithubVM(snapshot.state, fresh, headline, as_of, main_ci, rows, notes)


def github_decisions(snapshot: gh.Snapshot | None) -> list[Decision]:
    """PR 上等你安全签字的。只在这次真读到时给；旧数据不催你签。"""
    if snapshot is None or not snapshot.fresh:
        return []
    out = []
    for pull in snapshot.pulls:
        if pull.safety.state != "waiting":
            continue
        pid = next((p for p in pull.projects if p != gh.SHARED), gh.SHARED)
        out.append(
            Decision(
                "block", pid, f"PR #{pull.number} 等你安全签字", pd._short(pull.title, 60),
                f"仿真过了再在 PR #{pull.number} 上评论：安全签字 {pull.head_sha[:8]}",
                "PR 描述“安全回路: 是”+ 评论里没有你签当前头提交", pd.parse_time(pull.updated_at),
            )
        )
    return out


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

    def line(pick) -> str:  # noqa: ANN001
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
    mismatch = sum(1 for c in cards for i in c.issues if i.title in ("账本对不上", "工作项卡住"))
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
        Check("mismatch", "账本对不上", "number", mismatch, "条", "收口单与卡状态、工作项 BLOCKED"),
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
    )


def all_issues(home: HomeVM) -> list[Issue]:
    far = datetime.max.replace(tzinfo=UTC)
    return sorted(
        (i for c in home.hot + home.rest for i in c.issues),
        key=lambda i: (-SEV_RANK[i.sev], i.since or far),
    )


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
        rows = []
        for m in missions:
            bits = [pd.STATE_LABEL.get(m.state, m.state)]
            if m.run and m.column == "在干":
                bits.append(m.run.executor)
                if m.run.lease_expires:
                    bits.append("租约到 " + fmt(m.run.lease_expires, offset))
            if m.change_id:
                bits.append(m.change_id)
            rows.append((m.mission_id, pd._short(m.title, 70), " · ".join(bits), m.example))
        note = "PARKED 状态账本里还没有，TD-071 合并后才有数据" if name == "搁着" else ""
        columns.append(BoardColumn(name, note, rows))
    evidence = [
        EvidenceRow(
            "ok" if not any(i.title == "账本对不上" for i in card.issues) else "risk",
            "账本一致性",
            "收口单与卡状态、工作项、过期执行记录（本机账本副本）",
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
    changes = [ChangeRow(c.change_id, c.raised or "日期待补", c.kind, c.what, c.status) for c in project.changes]
    changes += [ChangeRow(c.card_id, "", "实施卡", c.title, c.status) for c in project.cards]
    changes += [
        ChangeRow(m.change_id, fmt(m.updated_at, offset), "收口", pd._short(m.title, 50), m.closure_state)
        for m in project.missions
        if m.change_id
    ]
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
    return ProjectVM(card, columns, evidence, changes, activity, recipe, github, rows)


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
    gap9_merged: bool = False,
) -> StationVM:
    off = online is False
    projects = []
    for card in cards:
        if card.tool or not card.registered:
            continue
        project = next(p for p in board.projects if p.project_id == card.project_id)
        files = [project.root + "/", f"PM_SESSION_{card.project_id}.md"]
        files += [f"{project.root}/…/03_实施卡/{c.card_id}.md" for c in project.cards[:2]]
        safety = any("安全" in c.what or "安全" in c.status for c in project.changes) or bool(
            safety_hits and card.project_id in safety_hits[0]
        )
        left = card.now_step or card.now_card
        nxt = "照实施卡的未勾项接着做" if project.cards else "先在 PM_SESSION 写明要做什么"
        projects.append((card, left, nxt, files, f"manual/{card.project_id.lower()}", safety))
    dis_off = (not off, "离线：读不到 origin")
    steps = [
        Step(1, *STEP_TITLES[0], "done", f"git switch -c {manual_branch} origin/main"),
        Step(2, *STEP_TITLES[1], "cur"),
        Step(
            3, *STEP_TITLES[2], "todo", "",
            [("重新跑 plc check", "plc_check", True, ""), ("plc docs check", "docs_check", True, ""),
             ("docs sync 预览", "docs_sync_preview", True, "")],
        ),
        Step(4, *STEP_TITLES[3], "todo", "", [("预览", "bc_preview", True, ""), ("写入 02_业务变更记录.md", "bc_write", True, "写前先预览"), ("打开文件", "bc_open", True, "")]),
        Step(5, *STEP_TITLES[4], "todo", "", [("复制提交说明", "copy_commit", True, ""), ("提交", "commit", False, "提交在命令提示符里做，本页不替你提交")]),
        Step(
            6, *STEP_TITLES[5], "todo", "",
            [("推送 manual/ 分支", "push", *dis_off), ("打开 GitHub 开 PR", "open_pr", *dis_off),
             ("批准范围", "approve", gap9_merged, "缺口⑨防冒签合并后才开放：批准只写一条凭据"),
             ("开工", "start", gap9_merged, "缺口⑨合并后才开放，且和批准分开；不启动任何 agent")],
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
        ("网络", "离线（git ls-remote 3 秒超时）" if off else ("在线" if online else "未探测")),
        ("采集", identity.get("collected", "—")),
    ]
    warn = off or identity.get("source", "") != identity.get("configured", identity.get("source", ""))
    banner = "当前离线：推送、开 PR、批准、开工都已灰化并写明原因；本机检查、记 BC、复制提交说明照常可用。" if off else ""
    return StationVM(ident, warn, bool(online), banner, projects, steps, records, safety_hits)
