"""视图模型：把 pm_dashboard 读出的数据算成画面要显示的东西。纯 Python，不 import Qt。

规则（设计稿第 0、3、6 节）：
    - 问题三档：block 阻塞（不处理会延期）/ risk 风险（要留意，还不挡路）/ hint 提醒（排班时顺手处理）。
    - 每条问题写明谁动手、依据是什么、等了多久；“等了多久”只在有起点时间时才算。
    - 六项机器检查三态：number 有数 / unchecked 没检查 / offline 断网未知。没数据源不得渲染为 0。
    - 健康：off 未接入 / block 受阻 / risk 有风险 / nodata 无数据（账本里没活，看不出好坏）/ ok 正常。
      缺账本或缺 Git 不许显示 ok。
    - “要你出手”只取谁动手 = 用户的问题，严重的在前、等得久的在前，每件附一句可复制的回复。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
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

    @property
    def sev(self) -> str:
        if self.state != "number":
            return "na"
        if self.value == 0:
            return "ok"
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


@dataclass
class ProjectVM:
    card: ProjectCard
    columns: list[BoardColumn]
    evidence: list[EvidenceRow]
    changes: list[ChangeRow]
    activity: list[tuple[str, str, str, bool]]  # (时间, 说明, 谁, 示例)
    recipe: list[tuple[str, str]]


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


# ---------------------------------------------------------------- 六项检查


def checks_of(board: pd.Board, cards: list[ProjectCard], online: bool | None) -> list[Check]:
    """六项机器检查。没有数据源的一律 unchecked，绝不渲染为 0（设计稿第 3.1 节）。"""
    net = "number" if online else ("offline" if online is False else "unchecked")
    lost = sum(1 for c in cards for i in c.issues if i.title == "执行者失联")
    mismatch = sum(1 for c in cards for i in c.issues if i.title in ("账本对不上", "工作项卡住"))
    unverified = sum(
        1
        for p in board.projects
        for m in p.missions
        if m.state == "CLOSED" and m.closure_state and m.closure_state != "COMPLETED"
    )
    return [
        Check(
            "gate_red", "门禁红的分支", "unchecked",
            note="CI 只按 SW-008 / SW-005 路径触发，PLC 项目的 PR 没有门禁；GitHub 采集未接",
        ),
        Check("scope", "越界改动", "unchecked", note="越界检查（pr-scope-check）还没合进 main"),
        Check(
            "unverified", "说完成但机器没过", "number", unverified, "张",
            "只查账本路线：已关的卡收口单是否 COMPLETED。PR 路线（审计编号）算不出",
        ),
        Check(
            "safety_unsigned", "安全区待签", "offline" if net == "offline" else "unchecked",
            note="安全签字检查（safety-signoff-check）还没合进 main",
        ),
        Check("mismatch", "账本对不上", "number", mismatch, "条", "收口单与卡状态、工作项 BLOCKED"),
        Check(
            "lost", "执行者失联", "number", lost, "个",
            "卡开着 + 租约过期 + 最近断点超过 1 小时；只覆盖写账本的执行者",
        ),
    ]


# ---------------------------------------------------------------- 首页 / 问题 / 项目页


def home_vm(board: pd.Board, offset: timezone, online: bool | None, use_git: bool) -> HomeVM:
    now = board.generated_at
    ledger_ok = board.ledger_note.startswith("账本只读")
    cards = [project_card(p, now, offset, ledger_ok, use_git, bool(online)) for p in board.projects]
    decisions = sorted(
        (d for c in cards for d in c.decisions),
        key=lambda d: (-SEV_RANK[d.sev], d.since or datetime.max.replace(tzinfo=UTC)),
    )
    checks = checks_of(board, cards, online)
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
    )


def all_issues(home: HomeVM) -> list[Issue]:
    far = datetime.max.replace(tzinfo=UTC)
    return sorted(
        (i for c in home.hot + home.rest for i in c.issues),
        key=lambda i: (-SEV_RANK[i.sev], i.since or far),
    )


def project_vm(board: pd.Board, card: ProjectCard, offset: timezone, online: bool | None) -> ProjectVM:
    now = board.generated_at
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
        EvidenceRow("na", "门禁", "没跑：CI 只按 SW-008 / SW-005 路径触发；GitHub 采集未接"),
        EvidenceRow("na", "越界检查", "没检查：pr-scope-check 未合"),
        EvidenceRow("na", "安全区签字", "没检查：safety-signoff-check 未合；现在靠人读 PR 评论"),
        EvidenceRow("na", "仿真实跑", "无记录：现场回传设计稿 D09 后落地"),
        EvidenceRow("na", "独立审计", "没检查：审计编号只在共享文件夹，仓库和账本无字段"),
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
    return ProjectVM(card, columns, evidence, changes, activity, recipe)


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
