"""Tests for hook_replay.py: each test builds a throw-away repository with a base and a PR head.

Run with:  python -m pytest reviews/tools/test_hook_replay.py -q -p no:cacheprovider -o addopts=
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hook_replay as replay_mod
from auto_pm.infrastructure.git_hook_enforcer import ProjectBinding

ROOT = "proj/SW-TEST-001"
CHG_DIR = f"{ROOT}/04_监控/01_变更管理/01_变更单/CHG-DOCU"
LEDGER = f"{ROOT}/04_监控/01_变更管理/02_变更记录/01_版本变更台账.md"
CODE = f"{ROOT}/auto_pm/service.py"
BINDINGS = (ProjectBinding("SW-TEST-001", ROOT), ProjectBinding("SW-TEST-002", "proj/SW-TEST-002"))
REAL_CHG = (
    replay_mod.SW008_ROOT / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-DOCU" / "CHG-DOCU-2026-090.md"
)


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "core.autocrlf=false",
         "-c", "core.quotepath=false", *args],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    return done.stdout.strip()


def change_text(chg_id: str = "CHG-DOCU-2026-900", pid: str = "SW-TEST-001", status: str = "completed") -> str:
    text = REAL_CHG.read_text(encoding="utf-8").replace("CHG-DOCU-2026-090", chg_id)
    text = text.replace("| 项目编号 | SW-2026-008 |", f"| 项目编号 | {pid} |")
    return text.replace("| 变更状态 | completed |", f"| 变更状态 | {status} |")


def write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    write(tmp_path, "README.md", "base\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def commit(repo: Path, message: str, files: dict[str, str]) -> str:
    for rel, text in files.items():
        write(repo, rel, text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def run(repo: Path, base: str) -> list[replay_mod.Finding]:
    return replay_mod.replay(repo, base, "HEAD", BINDINGS)


def test_commit_without_production_code_is_not_checked(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "docs only", {"docs/a.md": "x\n", "tests/test_x.py": "x = 1\n"})
    assert run(repo, base) == []


def test_production_code_without_change_number_is_reported(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "feat: no number", {CODE: "x = 1\n"})
    (finding,) = run(repo, base)
    assert "没有绑定变更单号" in finding.problem


def test_two_change_numbers_are_reported(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "feat: CHG-DOCU-2026-900 and CHG-DOCU-2026-901", {CODE: "x = 1\n"})
    (finding,) = run(repo, base)
    assert "必须且只能一个" in finding.problem


def test_a_bound_commit_with_complete_evidence_passes(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(
        repo,
        "feat: CHG-DOCU-2026-900 ok",
        {CODE: "x = 1\n", f"{CHG_DIR}/CHG-DOCU-2026-900.md": change_text(), LEDGER: "| CHG-DOCU-2026-900 |\n"},
    )
    (finding,) = run(repo, base)
    assert finding.problem == ""


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ({}, "找不到变更单文件"),
        ({"chg": change_text(pid="SW-TEST-002")}, "项目编号是 SW-TEST-002"),
        ({"chg": change_text(status="draft")}, "不是合法执行态"),
        ({"chg": change_text()}, "缺少版本变更台账"),
        ({"chg": change_text(), "ledger": "| other |\n"}, "台账里没有 CHG-DOCU-2026-900"),
    ],
)
def test_incomplete_evidence_is_reported(repo: Path, files: dict[str, str], expected: str) -> None:
    base = git(repo, "rev-parse", "HEAD")
    payload = {CODE: "x = 1\n"}
    if "chg" in files:
        payload[f"{CHG_DIR}/CHG-DOCU-2026-900.md"] = files["chg"]
    if "ledger" in files:
        payload[LEDGER] = files["ledger"]
    commit(repo, "feat: CHG-DOCU-2026-900", payload)
    (finding,) = run(repo, base)
    assert expected in finding.problem


def test_evidence_that_is_only_in_the_base_counts(repo: Path) -> None:
    commit(repo, "gov", {f"{CHG_DIR}/CHG-DOCU-2026-900.md": change_text(), LEDGER: "| CHG-DOCU-2026-900 |\n"})
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "feat: CHG-DOCU-2026-900", {CODE: "x = 1\n"})
    (finding,) = run(repo, base)
    assert finding.problem == ""


def test_code_owned_by_no_project_is_reported(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "feat: CHG-DOCU-2026-900", {"elsewhere/app.py": "x = 1\n"})
    (finding,) = run(repo, base)
    assert "归属未知或不唯一" in finding.problem


def test_code_spanning_two_projects_is_reported(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "feat: CHG-DOCU-2026-900", {CODE: "x = 1\n", "proj/SW-TEST-002/a.py": "y = 1\n"})
    (finding,) = run(repo, base)
    assert "归属多个项目" in finding.problem


def test_merge_commits_are_not_checked(repo: Path) -> None:
    git(repo, "checkout", "-q", "-b", "side")
    commit(repo, "side docs", {"docs/s.md": "s\n"})
    git(repo, "checkout", "-q", "main")
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "merge", "--no-ff", "-q", "-m", "Merge side", "side")
    assert run(repo, base) == []


def test_warnings_do_not_fail_the_job_unless_enforced(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "feat: no number", {CODE: "x = 1\n"})
    # 报警期恒绿；--enforce 才退出 1。build_bindings 换成固定样例，不扫文件系统。
    monkeypatch.setattr(replay_mod, "build_bindings", lambda _repo: BINDINGS)
    argv = ["--base", base, "--head", "HEAD", "--repo", str(repo)]
    assert replay_mod.main(argv) == 0
    assert replay_mod.main([*argv, "--enforce"]) == 1


def test_unusable_git_input_is_exit_2_not_a_pass(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(replay_mod, "build_bindings", lambda _repo: BINDINGS)
    assert replay_mod.main(["--base", "nope", "--head", "HEAD", "--repo", str(repo)]) == 2
