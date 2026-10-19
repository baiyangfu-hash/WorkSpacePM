"""Tests for pr_scope_check.py: each test builds a throw-away repository with a base and a PR head.

Run with:  python -m pytest reviews/tools/test_pr_scope_check.py -q -p no:cacheprovider -o addopts=
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pr_scope_check as gate
from auto_pm.plc import doc_consistency as dc
from tests.plc.test_doc_consistency import build

CARD = "02_规划/001_X_实施卡_PM.md"
PLC_ROOT = "0100_PLC自动化/DJ-TEST-001"
SCL = f"{PLC_ROOT}/02_PLC程序/PLC_ST/01_泵/FB_Pump.scl"
IFC = f"{PLC_ROOT}/02_PLC程序/PLC_ST/01_泵/PRD/接口文档_IFC-FB_Pump.md"


def card(*rows: tuple[str, str]) -> str:
    table = "\n".join(f"| {n} | `{path}` | {state} |" for n, (path, state) in enumerate(rows, start=1))
    return (
        "# X｜实施卡\n\n> 隔离基线：`WORKTREE`\n> 路径根：`.`\n\n"
        f"## Owned Paths\n\n| # | 路径 | 基线状态 |\n|---|---|---|\n{table}\n"
    )


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "core.autocrlf=false",
         "-c", "core.quotepath=false", *args],
        check=True, capture_output=True, text=True, encoding="utf-8",
    )
    return result.stdout.strip()


def write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    write(root, "src/a.py", "a = 1\n")
    write(root, "src/b.py", "b = 1\n")
    write(root, "docs/guide.md", "guide\n")
    write(root, "AGENTS.md", "rules\n")
    write(root, CARD, card(("src/a.py", "存在"), ("docs", "存在"), ("src/new.py", "计划新增")))
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    git(root, "checkout", "-q", "-b", "pr")
    return root


def commit(repo: Path, files: dict[str, str] | None = None) -> tuple[str, str]:
    for rel, text in (files or {}).items():
        write(repo, rel, text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "change")
    return git(repo, "rev-parse", "main"), git(repo, "rev-parse", "HEAD")


def errors(result: gate.Result) -> str:
    return "\n".join(result.errors)


def test_s01_changes_inside_the_card_pass(repo: Path) -> None:
    base, head = commit(repo, {"src/a.py": "a = 2\n", "docs/guide.md": "new\n", "src/new.py": "n = 1\n"})
    result = gate.check(repo, base, head, f"任务卡: `{CARD}`")
    assert result.passed, errors(result)
    assert "任务卡" in result.source and "src/a.py" in result.allowed


def test_s02_a_file_outside_the_card_fails(repo: Path) -> None:
    base, head = commit(repo, {"src/b.py": "b = 2\n"})
    result = gate.check(repo, base, head, f"任务卡：{CARD}")
    assert not result.passed and "越界：`src/b.py`" in errors(result)


def test_s03_the_card_is_read_at_the_base_so_a_pr_cannot_widen_its_own_scope(repo: Path) -> None:
    widened = card(("src/a.py", "存在"), ("docs", "存在"), ("src/b.py", "存在"))
    base, head = commit(repo, {"src/b.py": "b = 2\n", CARD: widened})
    result = gate.check(repo, base, head, f"任务卡: {CARD}")
    assert "越界：`src/b.py`" in errors(result)
    assert any("改了任务卡本身" in note for note in result.notes)


def test_s04_a_card_missing_at_the_base_fails(repo: Path) -> None:
    new_card = "02_规划/002_Y_实施卡_PM.md"
    base, head = commit(repo, {new_card: card(("src/b.py", "存在")), "src/b.py": "b = 2\n"})
    result = gate.check(repo, base, head, f"任务卡: {new_card}")
    assert not result.passed and "在 PR 基线" in errors(result)


def test_s05_a_locked_file_needs_its_exact_path_not_a_directory(repo: Path) -> None:
    write(repo, "docs/台账.md", "ledger\n")  # matches the locked pattern *台账* but sits under the allowed `docs`
    base, head = commit(repo)
    result = gate.check(repo, base, head, f"任务卡: {CARD}")
    assert "锁定文件 `docs/台账.md`" in errors(result)
    assert "越界" not in errors(result)


def test_s06_a_locked_file_named_exactly_passes(repo: Path) -> None:
    base, head = commit(repo, {"AGENTS.md": "rules v2\n"})
    body = "可改范围:\n- `AGENTS.md`\n"
    result = gate.check(repo, base, head, body)
    assert result.passed, errors(result)
    assert "自报" in result.source


def test_s07_a_self_declared_scope_still_blocks_files_outside_it(repo: Path) -> None:
    base, head = commit(repo, {"src/a.py": "a = 2\n", "src/b.py": "b = 2\n"})
    body = "说明\n\n## 可改范围\n\n- src/a.py\n\n## 其他\n- src/b.py\n"
    result = gate.check(repo, base, head, body)
    assert "越界：`src/b.py`" in errors(result) and "src/a.py" not in errors(result)


def test_s08_no_scope_at_all_fails(repo: Path) -> None:
    base, head = commit(repo, {"src/a.py": "a = 2\n"})
    result = gate.check(repo, base, head, "随手改了一点")
    assert not result.passed and "无法判断范围" in errors(result)


def test_s09_paths_that_escape_the_repository_are_refused(repo: Path) -> None:
    base, head = commit(repo, {"src/a.py": "a = 2\n"})
    assert "相对路径" in errors(gate.check(repo, base, head, "任务卡: ../outside.md"))
    assert "相对路径" in errors(gate.check(repo, base, head, "可改范围\n- /etc/passwd\n"))


def test_s10_both_ends_of_a_rename_count(repo: Path) -> None:
    git(repo, "mv", "src/b.py", "src/new.py")  # an out-of-scope file moved onto an allowed path
    base, head = commit(repo)
    result = gate.check(repo, base, head, f"任务卡: {CARD}")
    assert "越界：`src/b.py`" in errors(result) and "src/new.py" not in errors(result)


def test_s11_a_card_without_a_path_table_fails(repo: Path) -> None:
    write(repo, "02_规划/003_Z_实施卡_PM.md", "# Z\n\n> 隔离基线：`WORKTREE`\n> 路径根：`.`\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "card z")
    git(repo, "branch", "-f", "main", "HEAD")
    base, head = commit(repo, {"src/a.py": "a = 2\n"})
    result = gate.check(repo, base, head, "任务卡: 02_规划/003_Z_实施卡_PM.md")
    assert "路径表不合格" in errors(result) and "没有列出任何路径" in errors(result)


def test_s12_plc_documents_out_of_step_with_the_code_fail(repo: Path) -> None:
    project = build(repo / "0100_PLC自动化")
    (project / ".plc.json").write_text('{"name": "DJ-TEST-001", "version": "V1.0.0", "description": "t"}', encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "plc project")
    git(repo, "branch", "-f", "main", "HEAD")
    scl = (repo / SCL).read_text(encoding="utf-8")
    base, head = commit(repo, {SCL: scl.replace(
        "    i_bStart : BOOL; // 启动命令\n", "    i_bStart : BOOL; // 启动命令\n    i_bNew : BOOL; // 新增信号\n")})
    result = gate.check(repo, base, head, f"可改范围\n- {PLC_ROOT}\n")
    assert "PLC 文档与代码一致性检查未通过" in errors(result)
    assert dc.MARKER  # the hook's own marker module is the one in use


def test_s13_plc_documents_in_step_pass(repo: Path) -> None:
    project = build(repo / "0100_PLC自动化")
    (project / ".plc.json").write_text('{"name": "DJ-TEST-001", "version": "V1.0.0", "description": "t"}', encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "plc project")
    git(repo, "branch", "-f", "main", "HEAD")
    scl = (repo / SCL).read_text(encoding="utf-8").replace("// 启动命令", "// 启动按钮命令")
    ifc = (repo / IFC).read_text(encoding="utf-8").replace("| 启动命令 |", "| 启动按钮命令 |")
    base, head = commit(repo, {SCL: scl, IFC: ifc})
    result = gate.check(repo, base, head, f"可改范围\n- {PLC_ROOT}\n")
    assert result.passed, errors(result)


def test_s14_main_exit_codes_and_step_summary(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    base, head = commit(repo, {"src/b.py": "b = 2\n"})
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("PR_BODY", f"任务卡: {CARD}")
    assert gate.main(["--base", base, "--head", head, "--repo", str(repo)]) == 1
    assert "结论：不通过" in summary.read_text(encoding="utf-8")
    monkeypatch.setenv("PR_BODY", "可改范围\n- src/b.py\n")
    assert gate.main(["--base", base, "--head", head, "--repo", str(repo)]) == 0
    assert gate.main(["--base", "nope", "--head", head, "--repo", str(repo)]) == 2
    capsys.readouterr()
