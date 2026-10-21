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


CHECKER = Path(gate.__file__).resolve()
WORKFLOW = Path(gate.__file__).resolve().parents[2] / ".github" / "workflows" / "pr-gate.yml"
LOCK = "00_Infrastructure/auto_pm/environment/requirements-lock-py312-win.txt"


def run_ci(repo: Path, base: str, head: str, body: str) -> subprocess.CompletedProcess[str]:
    """Run the checker exactly as the workflow does: base judge, PR checkout as data, cwd inside the PR checkout."""

    return subprocess.run(
        [sys.executable, "-I", str(CHECKER), "--ci", "--base", base, "--head", head, "--repo", str(repo)],
        cwd=repo, env={"PR_BODY": body, "PATH": "/usr/bin:/bin"}, capture_output=True, text=True, encoding="utf-8",
        check=False,
    )


def test_s15_a_pr_that_rewrites_the_judges_configuration_is_still_judged_by_the_base(repo: Path) -> None:
    write(repo, "docs/台账.md", "ledger\n")  # locked, but only covered by the `docs` directory scope
    poison = {
        "reviews/tools/audit_pr.py": "print('POISONED')\nPROTECTED_PATTERNS = ()\ndef path_matches(p, q):\n    return False\n",
        "reviews/tools/pr_scope_check.py": "print('POISONED')\nraise SystemExit(0)\n",
        "auto_pm/__init__.py": "print('POISONED')\nraise SystemExit(0)\n",
    }
    base, head = commit(repo, poison)
    body = "可改范围\n- docs\n- reviews/tools\n- auto_pm\n"
    result = run_ci(repo, base, head, body)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "POISONED" not in result.stdout + result.stderr
    assert "锁定文件 `docs/台账.md`" in result.stdout
    assert "锁定文件 `reviews/tools/audit_pr.py`" in result.stdout
    assert "锁定文件 `reviews/tools/pr_scope_check.py`" in result.stdout


def test_s16_a_pr_that_changes_the_dependency_files_must_name_them(repo: Path) -> None:
    base, head = commit(repo, {LOCK: "evil-package==6.6.6\n", "requirements.txt": "evil-package\n"})
    blocked = run_ci(repo, base, head, "可改范围\n- 00_Infrastructure\n")
    assert blocked.returncode == 1
    assert f"锁定文件 `{LOCK}`" in blocked.stdout
    assert "锁定文件 `requirements.txt`" in blocked.stdout
    named = run_ci(repo, base, head, f"可改范围\n- {LOCK}\n- requirements.txt\n")
    assert named.returncode == 0, named.stdout  # allowed only when named exactly, so a reviewer sees it


def test_s17_the_judges_own_code_must_be_named_exactly(repo: Path) -> None:
    sw008 = gate._SW008
    base, head = commit(repo, {f"{sw008}/auto_pm/infrastructure/plc_doc_hook.py": "x = 1\n"})
    result = gate.check(repo, base, head, f"可改范围\n- {sw008}\n")
    assert f"锁定文件 `{sw008}/auto_pm/infrastructure/plc_doc_hook.py`" in errors(result)


def test_s18_ci_mode_refuses_when_the_judge_and_the_checked_tree_are_one_checkout(repo: Path) -> None:
    base, head = commit(repo, {"src/a.py": "a = 2\n"})
    same = subprocess.run(
        [sys.executable, "-I", str(CHECKER), "--ci", "--base", base, "--head", head, "--repo", str(CHECKER.parents[2])],
        env={"PR_BODY": "可改范围\n- src/a.py\n", "PATH": "/usr/bin:/bin"}, capture_output=True, text=True,
        encoding="utf-8", check=False,
    )
    assert same.returncode == 2 and "必须分开" in same.stderr


def test_s19_the_workflow_takes_the_judge_from_the_base_and_never_runs_the_pr_head() -> None:
    yaml = pytest.importorskip("yaml")
    flow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    assert list(flow[True]) == ["pull_request_target"]  # the base's copy of this workflow runs, not the PR's
    assert flow["permissions"] == {"contents": "read"}
    steps = flow["jobs"]["gate"]["steps"]
    checkout = next(s for s in steps if s.get("uses", "").startswith("actions/checkout"))
    assert checkout["with"]["ref"] == "${{ github.event.pull_request.base.sha }}"
    assert checkout["with"]["persist-credentials"] is False
    runs = [s.get("run", "") for s in steps]
    install = next(r for r in runs if "pip install" in r)
    assert "pr-head" not in install and "RUNNER_TEMP" not in install
    check = next(r for r in runs if "pr_scope_check.py" in r)
    assert '"$GITHUB_WORKSPACE/reviews/tools/pr_scope_check.py" --ci' in check
    assert "python -I " in check
    fetch = next(r for r in runs if "refs/pull/" in r)
    assert 'test "$(git rev-parse refs/remotes/pr/head)" = "$HEAD_SHA"' in fetch  # the fetched head is the event's head
    worktree = " ".join(fetch.split())
    for flag in ("-c core.symlinks=false", "-c filter.lfs.smudge=", "-c filter.lfs.process=", "-c filter.lfs.required=false"):
        assert f"git {flag}" in worktree or f" {flag} " in worktree, flag
    assert worktree.index("core.symlinks=false") < worktree.index("worktree add")
    for run in runs:  # the PR head appears only as the worktree that is created and as --repo data
        for line in run.splitlines():
            if "pr-head" in line:
                assert "worktree add --detach" in line or '--repo "$RUNNER_TEMP/pr-head"' in line


def test_s20_a_locked_card_does_not_exempt_itself(repo: Path) -> None:
    wbs = "plan_WBS_PM.md"  # a WBS file named as the task card: locked by *_WBS_PM.md
    write(repo, wbs, card(("src/a.py", "存在")))
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "wbs card")
    git(repo, "branch", "-f", "main", "HEAD")
    base, head = commit(repo, {wbs: "# 整篇改写\n"})
    result = gate.check(repo, base, head, f"任务卡: {wbs}")
    assert not result.passed
    assert f"锁定文件 `{wbs}`" in errors(result) and f"越界：`{wbs}`" in errors(result)
    assert any("不享受豁免" in note for note in result.notes)


def test_s21_an_ordinary_card_may_edit_itself(repo: Path) -> None:
    base, head = commit(repo, {CARD: card(("src/a.py", "存在")) + "\n补充说明\n", "src/a.py": "a = 3\n"})
    result = gate.check(repo, base, head, f"任务卡: {CARD}")
    assert result.passed, errors(result)
    assert any("改了任务卡本身" in note for note in result.notes)


def test_s22_a_locked_file_deep_in_a_subdirectory_is_locked_by_its_name(repo: Path) -> None:
    base, head = commit(repo, {"docs/sub/AGENTS.md": "copy\n"})  # matches the bare pattern AGENTS.md only by file name
    result = gate.check(repo, base, head, f"任务卡: {CARD}")
    assert "锁定文件 `docs/sub/AGENTS.md`" in errors(result) and "越界" not in errors(result)


def test_s23_paths_after_a_blank_line_in_the_scope_list_are_not_authorised(repo: Path) -> None:
    base, head = commit(repo, {"src/a.py": "a = 2\n", "src/b.py": "b = 2\n"})
    result = gate.check(repo, base, head, "可改范围\n- src/a.py\n\n- src/b.py\n")
    assert "越界：`src/b.py`" in errors(result) and "src/a.py" not in errors(result)
