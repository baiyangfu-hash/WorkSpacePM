"""D-44 并发测试查出的缺陷：同一 agent 的多个对话同时开工位，输家会把赢家的工位目录清掉。"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[2]

_WORKER = """
import sys, time
sys.path.insert(0, sys.argv[1])
from auto_pm.application.core.agent_worktree_service import AgentWorktreeService
while time.time() < float(sys.argv[4]):
    pass
try:
    AgentWorktreeService(sys.argv[2], run_state=lambda run_id: None).open("claude", sys.argv[3], fetch=False)
    print("OPEN_OK")
except Exception as error:
    print("OPEN_REFUSED", type(error).__name__)
"""


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


def _control_root(tmp_path: Path) -> Path:
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
    root = tmp_path / "root"
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True, capture_output=True)
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "c0")
    _git(root, "remote", "add", "origin", str(origin))
    _git(root, "push", "-q", "origin", "main")
    _git(root, "fetch", "-q", "origin")
    return root


@pytest.mark.parametrize("round_number", [1, 2])
def test_three_conversations_opening_the_same_agent_station_leave_one_intact_station(
    tmp_path: Path, round_number: int
) -> None:
    root = _control_root(tmp_path)
    start = time.time() + 4
    processes = [
        subprocess.Popen(
            [sys.executable, "-B", "-c", _WORKER, str(PROJECT), str(root), f"card{index}", str(start)],
            stdout=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        for index in range(3)
    ]
    outputs = [process.communicate(timeout=120)[0].strip() for process in processes]

    assert sorted(outputs).count("OPEN_OK") == 1, outputs
    station = root / ".auto-pm" / "worktrees" / "claude"
    assert (station / ".git").exists(), "赢家的工位目录被输家清掉了"
    listing = subprocess.run(
        ["git", "-C", str(root), "worktree", "list", "--porcelain"], check=True, capture_output=True, text=True
    ).stdout
    assert "prunable" not in listing
    branches = subprocess.run(
        ["git", "-C", str(root), "branch", "--list", "claude/*"], check=True, capture_output=True, text=True
    ).stdout.split()
    assert len([item for item in branches if item.startswith("claude/")]) == 1, "输家留下了孤儿分支"
