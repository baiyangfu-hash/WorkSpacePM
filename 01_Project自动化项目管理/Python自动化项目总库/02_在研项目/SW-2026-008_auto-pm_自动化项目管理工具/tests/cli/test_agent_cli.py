"""``main.py agent register / unregister / list``（CHG-SCPT-2026-712）按方案第 5 节的验收标准逐条实跑。

真的 git、真的账本、真的命令行入口（``auto_pm.ui.cli.__main__.cli``），只关掉与本题无关的运行身份检查（夹具里没有项目锚点）。
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.application.core.agent_registry import use_ledger_roster
from auto_pm.infrastructure.continuity_store import ContinuityStore
from auto_pm.ui.cli.__main__ import cli
from tests.git_support import git_out

IDENTITY = ("-c", "user.name=Agent CLI Test", "-c", "user.email=agent-cli@example.invalid")
MARKERS = (
    "AUTO_PM_AGENT",
    "CLAUDECODE",
    "CLAUDE_CODE_ENTRYPOINT",
    "AI_AGENT",
    "AUTO_PM_SESSION_ID",
    "CLAUDE_CODE_SESSION_ID",
    "TRAE_CHAT_SESSION_ID",
    "VSCODE_PID",
)
USER = dict.fromkeys(MARKERS, "")  # 用户本人的终端：一个 agent 标记都没有


def git(cwd: Path, *args: str) -> str:
    return git_out(cwd, *IDENTITY, *args)


@pytest.fixture(autouse=True)
def _user_terminal(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for key in list(os.environ):
        if key in MARKERS or key.upper().startswith("CODEX_"):
            monkeypatch.delenv(key, raising=False)
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


def run(root: Path, *args: str, **env: str) -> tuple[int, str]:
    result = CliRunner(env={**USER, **env}).invoke(cli, ["--workspace", str(root), *args])
    return result.exit_code, result.output


pytestmark = pytest.mark.usefixtures("identity_guard_off")


def test_1_the_user_registers_and_an_agent_is_refused(root: Path) -> None:
    code, out = run(root, "agent", "register", "antigravity", AUTO_PM_AGENT="claude")
    assert code == 1 and "只限用户本人" in out, out
    code, out = run(root, "agent", "register", "kiro", AI_AGENT="kiro_1")
    assert code == 1 and "只限用户本人" in out, out

    code, out = run(root, "agent", "register", "antigravity")
    assert code == 0, out
    assert "已登记 antigravity" in out and "antigravity/" in out and "pm-as-agent.ps1 antigravity" in out

    code, out = run(root, "agent", "register", "antigravity")
    assert code == 1 and "已经登记过" in out, out
    code, out = run(root, "agent", "register", "Bad_Name")
    assert code == 2 and "不合规则" in out, out


def test_2_a_registered_ai_opens_its_station_on_its_own_branch(root: Path) -> None:
    assert run(root, "agent", "register", "antigravity")[0] == 0

    code, out = run(root, "worktree", "open", "antigravity", "299", "--no-fetch", AUTO_PM_AGENT="antigravity")
    assert code == 0, out
    # 一个 agent 进程拿不到会话 ID 时驾驶舱按父进程号给它生成一个，所以工位是它自己的别名 antigravity-<6位十六进制>
    (station,) = (root / ".auto-pm" / "worktrees").iterdir()
    assert station.name.startswith("antigravity")
    assert git(station, "branch", "--show-current") == "antigravity/299"

    code, out = run(root, "worktree", "list", "--json")
    assert code == 0, out
    rows = {row["name"]: row for row in json.loads(out)}
    assert rows[station.name]["kind"] == "agent" and rows[station.name]["branch_prefix"] == "antigravity/"


def test_2b_the_session_alias_of_a_registered_ai_is_accepted(root: Path) -> None:
    assert run(root, "agent", "register", "antigravity")[0] == 0

    code, out = run(
        root, "worktree", "open", "antigravity", "300", "--no-fetch", AUTO_PM_AGENT="antigravity", AUTO_PM_SESSION_ID="1a2b3c4d5e"
    )
    assert code == 0, out
    assert (root / ".auto-pm" / "worktrees" / "antigravity-1a2b3c").is_dir()


def test_3_an_unregistered_name_is_refused_and_the_message_lists_the_registered(root: Path) -> None:
    assert run(root, "agent", "register", "antigravity")[0] == 0

    code, out = run(root, "worktree", "open", "foo", "1", "--no-fetch")
    assert code == 2, out
    flat = "".join(out.split())
    assert "foo" in flat and "antigravity" in flat and "claude" in flat and "登记" in flat


def test_5_unregister_refuses_a_name_with_a_station_and_then_forgets_it(root: Path) -> None:
    assert run(root, "agent", "register", "antigravity")[0] == 0
    assert run(root, "worktree", "open", "antigravity", "299", "--no-fetch", AUTO_PM_AGENT="antigravity")[0] == 0

    code, out = run(root, "agent", "unregister", "antigravity", AUTO_PM_AGENT="antigravity")
    assert code == 1 and "只限用户本人" in out, out
    code, out = run(root, "agent", "unregister", "antigravity")
    assert code == 1 and "还在用" in out and "工位 antigravity" in out, out

    (station,) = (root / ".auto-pm" / "worktrees").iterdir()
    git(root, "worktree", "remove", str(station))  # 收工位本身不是本题（worktree close 另有测试）：直接让 git 收掉
    code, out = run(root, "agent", "unregister", "antigravity")
    assert code == 0 and "已注销 antigravity" in out, out

    code, out = run(root, "worktree", "open", "antigravity", "301", "--no-fetch", AUTO_PM_AGENT="antigravity")
    assert code != 0, out


def test_list_shows_built_ins_and_registered_and_never_writes(root: Path) -> None:
    code, out = run(root, "agent", "list", "--json")
    assert code == 0, out
    data = json.loads(out)
    assert [item["name"] for item in data["builtin"]] == ["claude", "trae", "cursor", "vscode", "codex"]
    assert data["registered"] == []

    assert run(root, "agent", "register", "antigravity")[0] == 0
    assert run(root, "agent", "register", "kiro")[0] == 0
    assert run(root, "agent", "unregister", "kiro")[0] == 0

    code, out = run(root, "agent", "list", AUTO_PM_AGENT="claude")  # 只读：agent 也能看
    assert code == 0 and "antigravity" in out and "kiro" not in out, out
    code, out = run(root, "agent", "list", "--json", "--all")
    assert [(item["name"], item["status"]) for item in json.loads(out)["registered"]] == [
        ("antigravity", "active"),
        ("kiro", "retired"),
    ]


def test_board_source_is_written_down(root: Path) -> None:
    code, out = run(root, "agent", "register", "antigravity", "--via", "board")
    assert code == 0, out
    code, out = run(root, "agent", "list", "--json")
    assert json.loads(out)["registered"][0]["source_ref"].startswith("board:")
