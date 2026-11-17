"""AI 登记表（CHG-SCPT-2026-712）：用户登记一个名字，工位、身份标记、分支前缀、批准证据检查马上都认它；agent 不能自己登记。

每个测试一个临时控制根（裸 origin 克隆出来、账本已初始化），全程真的 git 和真的 SQLite，不打桩。
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from auto_pm.application.core import agent_registry as registry
from auto_pm.application.core import agent_worktree_service as service
from auto_pm.application.core.agent_registry import (
    AgentRegistryError,
    AgentRegistryRefusedError,
    AgentRegistryService,
    name_problem,
    use_ledger_roster,
)
from auto_pm.application.core.agent_worktree_service import (
    AGENT_ROSTER,
    BUILTIN_ROSTER,
    AgentWorktreeError,
    AgentWorktreeService,
    base_agent,
    caller_agent,
    is_alias,
    session_alias,
)
from auto_pm.contracts.user_evidence import names_an_agent, user_evidence_problem
from auto_pm.infrastructure.continuity_store import ContinuityStore
from tests.git_support import git_out

IDENTITY = ("-c", "user.name=Registry Test", "-c", "user.email=registry@example.invalid")
MARKERS = ("AUTO_PM_AGENT", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "AI_AGENT", "AUTO_PM_SESSION_ID", "CLAUDE_CODE_SESSION_ID")


def git(cwd: Path, *args: str) -> str:
    return git_out(cwd, *IDENTITY, *args)


@pytest.fixture(autouse=True)
def _built_in_roster_after_each_test(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key in list(os.environ):
        if key in MARKERS or key.upper().startswith("CODEX_"):
            monkeypatch.delenv(key, raising=False)
    use_ledger_roster(None)
    yield
    use_ledger_roster(None)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    tmp_path = tmp_path.resolve()
    origin, seed, control = tmp_path / "origin.git", tmp_path / "seed", tmp_path / "root"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(seed))
    git(seed, "checkout", "-q", "-b", "main")
    (seed / ".gitignore").write_text(".auto-pm/\n", encoding="utf-8")
    git(seed, "add", ".gitignore")
    git(seed, "commit", "-q", "-m", "ignore")
    git(seed, "push", "-q", "origin", "main")
    git(tmp_path, "clone", "-q", str(origin), str(control))
    ContinuityStore(control).initialize("2026-11-17T05:00:00+00:00", "test")
    return control


def _rows(root: Path, sql: str) -> list[tuple[object, ...]]:
    conn = sqlite3.connect(root / ".auto-pm" / "continuity.db")
    try:
        return list(conn.execute(sql).fetchall())
    finally:
        conn.close()


# ── 名字规则 ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", ["antigravity", "kiro", "gemini2", "ok", "windsurf"])
def test_good_names_pass(name: str) -> None:
    assert name_problem(name) == ""


@pytest.mark.parametrize(
    ("name", "why"),
    [
        ("a", "不合规则"),
        ("Antigravity", "不合规则"),
        ("anti-gravity", "不合规则"),
        ("2fast", "不合规则"),
        ("a" * 21, "不合规则"),
        ("ag/x", "不合规则"),
        ("claude", "内置"),
        ("codex", "内置"),
        ("main", "保留"),
        ("claims", "保留"),
        ("project", "固定词"),
        ("user", "固定词"),
        ("manual", "保留"),
        ("board", "固定词"),
        ("click", "固定词"),
        ("cmsg", "固定词"),
        ("confirmation", "固定词"),
        ("pin", "固定词"),
        ("deadbeef", "十六进制"),
        ("ab12", "十六进制"),
    ],
)
def test_bad_names_are_refused_with_the_reason(name: str, why: str) -> None:
    assert why in name_problem(name)


# ── 登记、注销 ────────────────────────────────────────────────────────


def test_register_writes_one_row_and_one_event_and_the_roster_knows_it(root: Path) -> None:
    done = AgentRegistryService(root).register("antigravity")

    assert (done.name, done.branch_prefix, done.status) == ("antigravity", "antigravity/", "active")
    assert done.registered_by == "no-agent-marker", "用户终端记作 no-agent-marker，不冒充“用户”"
    assert done.source_ref.startswith("terminal:")
    assert _rows(root, "SELECT name, branch_prefix, status FROM agent_registry") == [("antigravity", "antigravity/", "active")]
    assert _rows(root, "SELECT aggregate_type, aggregate_id, event_type FROM events WHERE aggregate_type='agent_registry'") == [
        ("agent_registry", "antigravity", "AGENT_REGISTERED")
    ]
    assert AGENT_ROSTER["antigravity"] == "antigravity/"
    assert "antigravity" in AGENT_ROSTER and set(BUILTIN_ROSTER) < set(AGENT_ROSTER)


def test_an_agent_cannot_register_or_unregister(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_PM_AGENT", "claude")
    with pytest.raises(AgentRegistryRefusedError, match="只限用户本人"):
        AgentRegistryService(root).register("antigravity")
    with pytest.raises(AgentRegistryRefusedError, match="只限用户本人"):
        AgentRegistryService(root).unregister("antigravity")
    monkeypatch.delenv("AUTO_PM_AGENT")
    monkeypatch.setenv("AI_AGENT", "antigravity_1")  # 任何 agent 标记都算，哪怕是要登记的那个 AI 自己
    with pytest.raises(AgentRegistryRefusedError):
        AgentRegistryService(root).register("antigravity")
    assert not (root / ".auto-pm" / "continuity.db").read_bytes().count(b"antigravity/")


def test_register_twice_is_refused_and_bad_names_write_nothing(root: Path) -> None:
    AgentRegistryService(root).register("antigravity")
    with pytest.raises(AgentRegistryRefusedError, match="已经登记过"):
        AgentRegistryService(root).register("antigravity")
    with pytest.raises(AgentRegistryError, match="内置"):
        AgentRegistryService(root).register("trae")
    with pytest.raises(AgentRegistryError, match="via"):
        AgentRegistryService(root).register("kiro", via="email")
    assert [row[0] for row in _rows(root, "SELECT name FROM agent_registry")] == ["antigravity"]


def test_register_needs_an_initialised_ledger(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q", "-b", "main", str(tmp_path / "bare"))
    with pytest.raises(AgentRegistryError, match="初始化"):
        AgentRegistryService(tmp_path / "bare").register("antigravity")
    assert not (tmp_path / "bare" / ".auto-pm" / "continuity.db").exists()


def test_listing_never_creates_the_table(root: Path) -> None:
    assert AgentRegistryService(root).list() == ()
    assert _rows(root, "SELECT name FROM sqlite_master WHERE name='agent_registry'") == [], "只读不建表"


def test_unregister_keeps_the_row_and_the_name_is_no_longer_known(root: Path) -> None:
    AgentRegistryService(root).register("antigravity")
    done = AgentRegistryService(root).unregister("antigravity")

    assert done.status == "retired" and done.retired_by == "no-agent-marker" and done.retired_at
    assert "antigravity" not in AGENT_ROSTER and base_agent("antigravity") == ""
    assert [item.name for item in AgentRegistryService(root).list(include_retired=True)] == ["antigravity"]
    assert AgentRegistryService(root).list() == ()
    events = [row[0] for row in _rows(root, "SELECT event_type FROM events WHERE aggregate_type='agent_registry' ORDER BY rowid")]
    assert events == ["AGENT_REGISTERED", "AGENT_UNREGISTERED"]
    again = AgentRegistryService(root).register("antigravity")  # 注销后可以再登记
    assert again.active and again.retired_at == ""


def test_unregister_refuses_built_ins_unknown_names_and_names_still_in_use(root: Path) -> None:
    with pytest.raises(AgentRegistryRefusedError, match="内置"):
        AgentRegistryService(root).unregister("claude")
    with pytest.raises(AgentRegistryRefusedError, match="没有登记"):
        AgentRegistryService(root).unregister("kiro")
    AgentRegistryService(root).register("antigravity")
    (root / ".auto-pm" / "worktrees" / "antigravity-1a2b3c").mkdir(parents=True)

    with pytest.raises(AgentRegistryRefusedError, match="工位 antigravity-1a2b3c"):
        AgentRegistryService(root).unregister("antigravity")
    assert "antigravity" in AGENT_ROSTER


# ── 读表：名册、别名、身份标记 ────────────────────────────────────────


def test_registered_names_count_as_roster_names_aliases_and_markers(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTO_PM_AGENT", "antigravity")
    assert caller_agent() == "?", "没登记时照旧认不出（失败关闭）"
    assert base_agent("antigravity-1a2b3c") == "" and not is_alias("antigravity-1a2b3c")

    monkeypatch.delenv("AUTO_PM_AGENT")
    AgentRegistryService(root).register("antigravity")
    monkeypatch.setenv("AUTO_PM_AGENT", "antigravity")

    assert caller_agent() == "antigravity"
    assert base_agent("antigravity-1a2b3c") == "antigravity" and is_alias("antigravity-1a2b3c")
    assert base_agent("foo") == "" and base_agent("foo-1a2b3c") == ""
    assert session_alias({"AUTO_PM_SESSION_ID": "1a2b3c4d", "AUTO_PM_AGENT": "antigravity"}) == "antigravity-1a2b3c"
    monkeypatch.setenv("AUTO_PM_AGENT", "foo")
    assert caller_agent() == "?", "没登记的名字照旧被拒"


def test_a_roster_that_cannot_be_read_is_the_built_in_roster(root: Path) -> None:
    AgentRegistryService(root).register("antigravity")
    service.AGENT_ROSTER.use(lambda: (_ for _ in ()).throw(OSError("disk gone")))

    assert "antigravity" not in AGENT_ROSTER and dict(AGENT_ROSTER) == BUILTIN_ROSTER


def test_the_user_terminal_and_built_in_agents_never_read_the_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    reads: list[int] = []

    def source() -> dict[str, str]:
        reads.append(1)
        return {}

    service.AGENT_ROSTER.use(source)
    assert caller_agent() == ""
    monkeypatch.setenv("AUTO_PM_AGENT", "claude")
    assert "claude" in AGENT_ROSTER and AGENT_ROSTER["claude"] == "claude/" and base_agent("claude") == "claude"
    assert reads == []


def test_a_bad_row_written_around_the_service_is_ignored(root: Path) -> None:
    AgentRegistryService(root).register("antigravity")
    conn = sqlite3.connect(root / ".auto-pm" / "continuity.db")
    with conn:
        conn.execute(
            "INSERT INTO agent_registry (name, branch_prefix, status, registered_by, registered_at, source_ref)"
            " VALUES ('claude', 'main/', 'active', 'x', 'x', 'x'), ('Bad-Name', 'Bad-Name/', 'active', 'x', 'x', 'x'),"
            " ('wrongprefix', 'main/', 'active', 'x', 'x', 'x')"
        )
    conn.close()
    registry._ROSTER_ROOT.clear()
    use_ledger_roster(root)

    assert AGENT_ROSTER["claude"] == "claude/", "内置的前缀不能被登记表改"
    assert "Bad-Name" not in AGENT_ROSTER and "wrongprefix" not in AGENT_ROSTER
    assert "antigravity" in AGENT_ROSTER


# ── 工位：登记后能开 ──────────────────────────────────────────────────


def test_a_registered_ai_can_open_its_station_on_its_own_prefix(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stations = AgentWorktreeService(root, run_state=lambda _run: None, lease_probe=lambda _path: "", measure_size=False)
    with pytest.raises(AgentWorktreeError, match="登记新 AI"):
        stations.open("antigravity", "299")

    AgentRegistryService(root).register("antigravity")
    monkeypatch.setenv("AUTO_PM_AGENT", "antigravity")
    opened = AgentWorktreeService(root, run_state=lambda _run: None, lease_probe=lambda _path: "", measure_size=False).open(
        "antigravity", "299"
    )

    assert git(opened.path, "branch", "--show-current") == "antigravity/299"
    listed = {item.name: item.kind for item in stations.stations()}
    assert listed["antigravity"] == "agent"
    with pytest.raises(AgentWorktreeError, match="名册"):
        stations.open("foo", "300")


# ── 批准证据：登记的名字也算 agent 名字 ───────────────────────────────


def test_approval_evidence_that_names_a_registered_ai_is_not_the_users(root: Path) -> None:
    evidence = "user-confirmation:antigravity-said-ok-2026"
    assert user_evidence_problem(evidence) == "", "没登记时它只是一串字"

    AgentRegistryService(root).register("antigravity")

    assert names_an_agent("antigravity") and names_an_agent("by:Antigravity/1")
    assert "不能是 agent" in user_evidence_problem(evidence)
    assert user_evidence_problem("user-confirmation:2026-11-17T04:27:30Z") == ""
    assert "不能是 agent" in user_evidence_problem("user-confirmation:vscode-auto-ok"), "内置名册的名字也算"


# ── 看板“工作树与分支”页：登记的 AI 的工位按命令给的前缀判 ───────────


def test_the_board_judges_a_registered_ai_station_by_the_prefix_the_command_gives() -> None:
    import sys

    scripts = str(Path(__file__).resolve().parents[2] / "scripts")
    sys.path.insert(0, scripts)
    try:
        from cockpit_board import stations as board
    finally:
        sys.path.remove(scripts)
    row = {"name": "antigravity-1a2b3c", "kind": "agent", "checked": True, "dirty": 0, "unpushed": 0, "merged": True,
           "branch": "claude/299", "branch_prefix": "antigravity/", "path": "x"}

    assert "不是 antigravity/ 开头" in board.close_block(row), "别人的分支不收"
    assert board.close_block({**row, "branch": "antigravity/299"}) == ""
    view = board.build_view([{**row, "branch": "antigravity/299"}], [], [], {}, human_block="", now=datetime.now(UTC))
    (shown,) = view.rows
    assert shown.action is not None and shown.action.args == ("worktree", "close", "antigravity-1a2b3c")
    assert "antigravity（会话别名）" in shown.who


# ── 审计 865 §3.1：登记任何合法名字后，用户本人的凭据都还能过 ──────────────────

USER_EVIDENCE = (
    "user-confirmation:board-click:2026-11-17T04:40:44Z:1a2b3c4d5e6f",  # 看板点击（release_ship.confirm_ref）
    "user-confirmation:2026-11-17T04:40:44Z-cmsg_013MFzja8RTUptLcFWxTQMoxKPxHjYBqNpHRNmrfxvHRGC",  # 引用用户消息号
    "user-confirmation:2026-11-17T04:27:30Z",  # 纯时间
    "user-confirmation:gui-click-20261117T042730-1a2b3c4d",  # 旧看板点击（decisions.click_evidence）
    "user-confirmation:cockpit-0123456789abcdef-1a2b3c4d",  # 驾驶舱点击（pm_cockpit_service）
    "user-confirmation:pin-0123456789ab-change-approve-0123456789abcdef",  # 口令证明（approval_proof_service）
)


def test_every_reserved_word_is_refused_and_user_evidence_keeps_passing(root: Path) -> None:
    from auto_pm.application.core.agent_registry import RESERVED_NAMES
    from auto_pm.contracts.user_evidence import EVIDENCE_FORMAT_WORDS

    assert EVIDENCE_FORMAT_WORDS <= RESERVED_NAMES
    for word in sorted(RESERVED_NAMES):
        assert name_problem(word), f"{word} 必须登记不上"
    for name in ("antigravity", "kiro", "zulu", "windsurf"):
        AgentRegistryService(root).register(name)
    for evidence in USER_EVIDENCE:
        assert user_evidence_problem(evidence) == "", evidence
    assert "不能是 agent" in user_evidence_problem("user-confirmation:windsurf-2026-11-17")


def test_a_reserved_word_written_around_the_service_still_does_not_block_user_evidence(root: Path) -> None:
    AgentRegistryService(root).register("antigravity")
    conn = sqlite3.connect(root / ".auto-pm" / "continuity.db")
    with conn:
        conn.executemany(
            "INSERT INTO agent_registry (name, branch_prefix, status, registered_by, registered_at, source_ref)"
            " VALUES (?, ?, 'active', 'x', 'x', 'x')",
            [(word, f"{word}/") for word in ("board", "click", "cmsg", "confirmation")],
        )
    conn.close()
    registry._ROSTER_ROOT.clear()
    use_ledger_roster(root)

    for evidence in USER_EVIDENCE:
        assert user_evidence_problem(evidence) == "", evidence
    assert "board" not in AGENT_ROSTER, "凭据固定词即使被直接写进账本也不当 AI 名字"


def test_the_evidence_word_list_covers_every_format_the_code_writes() -> None:
    """代码里新增一种用户凭据格式（user-confirmation:<词>-…）或口令用途（purpose="…"）时，词表必须跟上。"""

    import re

    from auto_pm.contracts.user_evidence import EVIDENCE_FORMAT_WORDS

    project = Path(__file__).resolve().parents[2]
    found: set[str] = set()
    for folder in (project / "auto_pm", project / "scripts"):
        for path in folder.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="replace")
            for match in re.finditer(r"user-confirmation:([a-z]+(?:-[a-z]+)*)", text):
                found.update(part for part in match.group(1).split("-") if part)
            for match in re.finditer(r'purpose="([a-z-]+)"', text):
                found.update(part for part in match.group(1).split("-") if part)
    assert {"board", "click", "gui", "cockpit", "pin", "approve"} <= found, "扫描本身要找得到已知格式"
    assert found <= EVIDENCE_FORMAT_WORDS, f"凭据格式里新出现的词要加进 user_evidence.EVIDENCE_FORMAT_WORDS：{sorted(found - EVIDENCE_FORMAT_WORDS)}"


# ── 审计 865 §3.2、§3.3：读不出来时失败关闭 ─────────────────────────────


def test_an_unreadable_registry_makes_user_evidence_fail_closed(root: Path) -> None:
    AgentRegistryService(root).register("antigravity")
    service.AGENT_ROSTER.use(lambda: (_ for _ in ()).throw(OSError("disk gone")))

    problem = user_evidence_problem("user-confirmation:2026-11-17T04:27:30Z")
    assert "读不出来" in problem, "读不出登记表时不能把凭据当成用户的"
    assert names_an_agent("2026-11-17T04:27:30Z")
    assert "不能是 agent" in user_evidence_problem("user-confirmation:claude-ok-2026"), "写着内置名字的照旧按 agent 拒"


def test_unregister_is_refused_when_the_claim_table_cannot_be_read(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.application.core import claim_service

    AgentRegistryService(root).register("antigravity")

    def broken(self: object, *, fetch: bool = True) -> list[object]:
        raise claim_service.ClaimError("git for-each-ref 失败")

    monkeypatch.setattr(claim_service.ClaimService, "all_claims", broken)
    with pytest.raises(AgentRegistryRefusedError, match="占位表读不出来"):
        AgentRegistryService(root).unregister("antigravity")
    assert "antigravity" in AGENT_ROSTER
