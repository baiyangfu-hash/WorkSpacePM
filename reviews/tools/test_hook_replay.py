"""Tests for hook_replay.py: each test builds a throw-away repository with a base and a PR head.

Run with:  python -m pytest reviews/tools/test_hook_replay.py -q -p no:cacheprovider -o addopts=
"""

from __future__ import annotations

import os
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


def test_a_non_utf8_file_name_is_a_warning_not_a_crash(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    folder = repo / ROOT / "auto_pm"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / os.fsdecode(b"\xff\xfe_bad.py")).write_text("x = 1\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "feat: no number")
    (finding,) = run(repo, base)
    assert "没有绑定变更单号" in finding.problem


def test_control_characters_in_names_and_titles_cannot_become_workflow_commands(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "fix\n::error::injected", {f"{ROOT}/auto_pm/a\n::warning::evil%0A.py": "x = 1\n"})
    monkeypatch.setattr(replay_mod, "build_bindings", lambda _repo: BINDINGS)
    assert replay_mod.main(["--base", base, "--head", "HEAD", "--repo", str(repo), "--ci"]) == 0
    lines = capsys.readouterr().out.splitlines()
    commands = [line for line in lines if line.startswith("::")]
    assert commands == [line for line in commands if line.startswith("::warning title=hook-replay::")]
    assert len(commands) == 1
    assert "\\x0a" in "\n".join(lines)


def test_command_data_escapes_percent_and_line_breaks() -> None:
    assert replay_mod.command_data("a%b\r\nc") == "a%25b\\x0d\\x0ac"
    assert "\n" not in replay_mod.plain("x\ny") and "\x1b" not in replay_mod.plain("\x1b[31m")


def test_the_unknown_project_warning_mentions_new_projects(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "feat: CHG-DOCU-2026-900", {"elsewhere/app.py": "x = 1\n"})
    (finding,) = run(repo, base)
    assert "新注册" in finding.problem


def test_the_script_uses_the_layered_import_paths() -> None:
    source = Path(replay_mod.__file__).read_text(encoding="utf-8")
    assert "auto_pm.core." not in source and "auto_pm.change." not in source


# ---- PR 描述里的单号或任务卡（用户 2026-11-01 裁决） ----

CARD = "docs/cards/CARD-SW-TEST-001-001.md"
CHG = "CHG-DOCU-2026-900"
EVIDENCE = {f"{CHG_DIR}/{CHG}.md": change_text(), LEDGER: f"| {CHG} |\n"}


def card_text(change_line: str = f"> 变更单：`{CHG}`") -> str:
    return f"# 卡\n\n> 依据：`BC-SW-TEST-001-2026_11_001`\n{change_line}\n> 状态：`PLANNED`\n"


def run_body(repo: Path, base: str, body: str) -> list[replay_mod.Finding]:
    return replay_mod.replay(repo, base, "HEAD", BINDINGS, body)


def test_one_change_number_in_the_pr_body_covers_commits_without_a_number(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "feat: no number in the message", {CODE: "x = 1\n", **EVIDENCE})
    (finding,) = run_body(repo, base, f"## 做了什么\n依据变更单 {CHG}\n")
    assert finding.problem == ""
    assert CHG in finding.via


def test_the_change_number_from_the_pr_body_still_needs_its_evidence(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "feat: no number in the message", {CODE: "x = 1\n"})
    (finding,) = run_body(repo, base, f"变更单 {CHG}")
    assert "找不到变更单文件" in finding.problem


def test_two_change_numbers_in_the_pr_body_are_reported(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "feat: no number", {CODE: "x = 1\n", **EVIDENCE})
    (finding,) = run_body(repo, base, "CHG-DOCU-2026-900 和 CHG-DOCU-2026-901")
    assert "PR 描述里写了 2 个变更单号" in finding.problem


def test_a_change_number_inside_an_html_comment_of_the_template_does_not_count(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "feat: no number", {CODE: "x = 1\n", **EVIDENCE})
    (finding,) = run_body(repo, base, f"<!-- 例如 {CHG} -->\n## 做了什么\n")
    assert "PR 描述里也没有变更单号或任务卡" in finding.problem


def test_the_number_in_the_commit_message_wins_over_the_pr_body(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "feat: CHG-DOCU-2026-777", {CODE: "x = 1\n", **EVIDENCE})
    (finding,) = run_body(repo, base, f"变更单 {CHG}")
    assert "CHG-DOCU-2026-777.md" in finding.problem and finding.via == ""


def test_a_task_card_on_the_base_with_a_change_number_binds_the_pr(repo: Path) -> None:
    commit(repo, "card", {CARD: card_text(), **EVIDENCE})
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "feat: no number", {CODE: "x = 1\n"})
    (finding,) = run_body(repo, base, f"任务卡: {CARD}\n")
    assert finding.problem == ""
    assert CARD in finding.via


def test_a_task_card_whose_change_number_has_no_evidence_is_reported(repo: Path) -> None:
    commit(repo, "card", {CARD: card_text()})
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "feat: no number", {CODE: "x = 1\n"})
    (finding,) = run_body(repo, base, f"任务卡: {CARD}")
    assert "找不到变更单文件" in finding.problem


def test_a_task_card_that_declares_no_change_order_does_not_cover_production_code(repo: Path) -> None:
    """与本机钩子一致：含生产代码的提交必须绑定变更单，卡里写“无”不能替代。"""
    commit(repo, "card", {CARD: card_text("> 变更单：`无`")})
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "feat: no number", {CODE: "x = 1\n"})
    (finding,) = run_body(repo, base, f"任务卡: {CARD}")
    assert "写的是 `无`" in finding.problem and finding.via == ""


def test_a_task_card_that_exists_only_in_the_pr_head_does_not_count(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "feat: no number", {CODE: "x = 1\n", CARD: card_text("> 变更单：`无`")})
    (finding,) = run_body(repo, base, f"任务卡: {CARD}")
    assert "在 PR 基线上读不到" in finding.problem


@pytest.mark.parametrize(
    ("card", "expected"),
    [
        ("# 旧式卡，没有头部\n", "头部有 0 行"),
        (card_text(f"> 变更单：`{CHG}`\n> 变更单：`CHG-DOCU-2026-901`"), "头部有 2 行"),
        (card_text("> 变更单：`待补`"), "既不是变更单号也不是"),
    ],
)
def test_a_task_card_without_a_usable_change_order_header_is_reported(repo: Path, card: str, expected: str) -> None:
    commit(repo, "card", {CARD: card})
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "feat: no number", {CODE: "x = 1\n"})
    (finding,) = run_body(repo, base, f"任务卡: {CARD}")
    assert expected in finding.problem


def test_a_task_card_path_that_escapes_the_repository_is_reported(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "feat: no number", {CODE: "x = 1\n"})
    (finding,) = run_body(repo, base, "任务卡: ../../etc/passwd")
    assert "不是仓库内的相对路径" in finding.problem


def test_the_report_says_which_binding_a_passing_commit_used(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "feat: no number", {CODE: "x = 1\n", **EVIDENCE})
    text = replay_mod.render(run_body(repo, base, f"变更单 {CHG}"))
    assert "✅" in text and "经PR 描述里的变更单" in text


def test_main_reads_the_pr_body_from_the_environment_not_the_command_line(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = git(repo, "rev-parse", "HEAD")
    commit(repo, "feat: no number", {CODE: "x = 1\n", **EVIDENCE})
    monkeypatch.setattr(replay_mod, "build_bindings", lambda _repo: BINDINGS)
    argv = ["--base", base, "--head", "HEAD", "--repo", str(repo), "--enforce"]
    monkeypatch.delenv("PR_BODY", raising=False)
    assert replay_mod.main(argv) == 1
    monkeypatch.setenv("PR_BODY", f"变更单 {CHG}")
    assert replay_mod.main(argv) == 0
