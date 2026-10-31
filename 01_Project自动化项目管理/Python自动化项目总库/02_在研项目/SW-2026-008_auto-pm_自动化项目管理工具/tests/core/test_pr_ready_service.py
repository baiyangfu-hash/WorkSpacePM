"""``pr ready``：用假的 gh 喂各种 GitHub 状态，逐条验证“缺一条就不放行、并说清缺什么”。"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from auto_pm.application.core.pr_ready_service import (
    PrReadyService,
    judge_checks,
    render,
)
from auto_pm.ui.cli.__main__ import cli

REPO_ROOT = Path(__file__).resolve().parents[2].parents[3]
HEAD = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
OLD = "0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f"
SIGNER = {"login": "baiyangfu-hash", "id": 246858089}
GOOD_RUNS: list[dict[str, object]] = [{"name": "sw008-ci", "status": "completed", "conclusion": "success"}]
GOOD_STATUS: dict[str, object] = {"statuses": [{"context": "safety-zone", "state": "success"}]}


class FakeGh:
    def __init__(self, **over: object) -> None:
        self.pr: dict[str, object] = {
            "headRefOid": HEAD,
            "state": "OPEN",
            "isDraft": False,
            "mergeable": "MERGEABLE",
            "baseRefName": "main",
            "body": "## 建议回写\n\nTD-1 已偿还，证据 提交号 a1b2c3d4\n",
            "files": [{"path": "docs/a.md"}],
        }
        self.runs: list[dict[str, object]] = list(GOOD_RUNS)
        self.status: dict[str, object] = dict(GOOD_STATUS)
        self.comments: list[dict[str, object]] = []
        self.calls: list[tuple[str, ...]] = []
        self.__dict__.update(over)

    def __call__(self, args: Sequence[str], stdin: str | None) -> subprocess.CompletedProcess[str]:
        self.calls.append(tuple(args))
        a = list(args)
        if a[:2] == ["pr", "view"]:
            out: object = self.pr
        elif a[0] == "api" and a[1].endswith("/check-runs"):
            out = [{"check_runs": self.runs}]
        elif a[0] == "api" and a[1].endswith("/status"):
            out = self.status
        elif a[0] == "api" and "/issues/" in a[1]:
            out = [self.comments]
        else:
            return subprocess.CompletedProcess(args, 1, "", f"unexpected {args}")
        return subprocess.CompletedProcess(args, 0, json.dumps(out), "")


def report_dir(tmp_path: Path, text: str, name: str = "216_audit_PR170.md") -> Path:
    directory = tmp_path / "reviews"
    directory.mkdir(exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8")
    return directory


def verdict(sha: str, word: str) -> str:
    return f"放行判定: {sha[:8]} {word}"


GOOD_REPORT = f"# 216 PR #170 审计\n\n## 结论\n\n同意，可以合并。\n\n{verdict(HEAD, '过')}\n"


def check(tmp_path: Path, gh: FakeGh, text: str | None = GOOD_REPORT, number: int = 170) -> Any:
    directory = report_dir(tmp_path, text) if text is not None else tmp_path / "reviews"
    return PrReadyService(REPO_ROOT, gh=gh, report_dirs=[directory], repo="o/r").check(number)


def failed(report: Any) -> set[str]:
    return {item.name for item in report.items if not item.ok}


def test_r01_everything_in_place_is_ready_and_prints_the_writeback(tmp_path: Path) -> None:
    report = check(tmp_path, FakeGh())
    assert report.ready, render(report)
    text = "\n".join(render(report))
    assert "可以合并" in text and "回写台账" in text and "TD-1 已偿还" in text


def test_r02_a_missing_audit_report_blocks_and_says_where_it_looked(tmp_path: Path) -> None:
    report = check(tmp_path, FakeGh(), text=None)
    assert failed(report) == {"独立审计报告"}
    assert "没有找到 PR #170 的审计报告" in "\n".join(render(report))


def test_r03_a_report_for_an_older_head_blocks(tmp_path: Path) -> None:
    report = check(tmp_path, FakeGh(), text=GOOD_REPORT.replace(HEAD[:8], OLD[:8]))
    assert failed(report) == {"独立审计报告"}
    assert "不是当前头" in "\n".join(render(report))


def test_r04_a_report_for_another_pr_does_not_count(tmp_path: Path) -> None:
    assert failed(check(tmp_path, FakeGh(), number=171)) == {"独立审计报告"}


def test_r05_only_a_conditional_pass_is_blocked(tmp_path: Path) -> None:
    report = check(tmp_path, FakeGh(), text=GOOD_REPORT.replace("过\n", "有条件过\n").replace(" 有条件有条件", " 有条件"))
    assert failed(report) == {"独立审计报告"}
    assert "有条件过" in "\n".join(render(report))


def test_r05b_a_report_without_the_verdict_line_is_blocked_with_the_exact_hint(tmp_path: Path) -> None:
    report = check(tmp_path, FakeGh(), text="# 216 PR #170 审计\n\n结论：同意，可以合并，头 " + HEAD[:8] + "\n")
    assert failed(report) == {"独立审计报告"}
    assert "缺放行判定行" in "\n".join(render(report))


def two_reports(tmp_path: Path, first: str, second: str, same_file: bool = False) -> Path:
    directory = tmp_path / "reviews"
    directory.mkdir(exist_ok=True)
    head = "# {n} PR #170 审计\n\n"
    if same_file:
        text = head.format(n=216) + f"## 首审\n{verdict(HEAD, first)}\n\n## 复审\n{verdict(HEAD, second)}\n"
        (directory / "216_audit_PR170.md").write_text(text, encoding="utf-8")
    else:
        (directory / "216_audit_PR170.md").write_text(head.format(n=216) + verdict(HEAD, first) + "\n", encoding="utf-8")
        (directory / "220_reaudit_PR170.md").write_text(head.format(n=220) + verdict(HEAD, second) + "\n", encoding="utf-8")
    return directory


@pytest.mark.parametrize("same_file", [False, True])
@pytest.mark.parametrize("first", ["有条件过", "不过"])
def test_r05c_a_later_pass_after_a_conditional_or_failed_first_audit_lets_it_through(
    tmp_path: Path, first: str, same_file: bool
) -> None:
    directory = two_reports(tmp_path, first, "过", same_file)
    report = PrReadyService(REPO_ROOT, gh=FakeGh(), report_dirs=[directory], repo="o/r").check(170)
    assert report.ready, render(report)


@pytest.mark.parametrize("same_file", [False, True])
def test_r05d_a_later_fail_after_a_pass_blocks_the_last_line_decides(tmp_path: Path, same_file: bool) -> None:
    directory = two_reports(tmp_path, "过", "不过", same_file)
    report = PrReadyService(REPO_ROOT, gh=FakeGh(), report_dirs=[directory], repo="o/r").check(170)
    assert failed(report) == {"独立审计报告"}


def test_r05e_file_order_is_by_leading_number_not_by_text(tmp_path: Path) -> None:
    directory = tmp_path / "reviews"
    directory.mkdir()
    (directory / "99_audit_PR170.md").write_text(f"# PR #170\n{verdict(HEAD, '不过')}\n", encoding="utf-8")
    (directory / "100_reaudit_PR170.md").write_text(f"# PR #170\n{verdict(HEAD, '过')}\n", encoding="utf-8")
    assert PrReadyService(REPO_ROOT, gh=FakeGh(), report_dirs=[directory], repo="o/r").check(170).ready


def test_r05f_verdict_lines_must_be_exact(tmp_path: Path) -> None:
    for line in (f"放行判定: {HEAD[:8]} 过（有保留）", f"放行判定: {HEAD[:7]} 过", f"结论 放行判定: {HEAD[:8]} 过"):
        text = f"# PR #170\n\n{line}\n"
        assert failed(check(tmp_path, FakeGh(), text=text)) == {"独立审计报告"}, line


def test_r06_a_failing_or_unfinished_check_blocks_by_name() -> None:
    problems, passed = judge_checks(
        [
            {"name": "unit", "status": "completed", "conclusion": "failure"},
            {"name": "win", "status": "in_progress", "conclusion": None},
            {"name": "ok", "status": "completed", "conclusion": "skipped"},
        ],
        [{"context": "safety-zone", "state": "pending"}],
    )
    assert len(problems) == 3 and passed == ["ok"]


def test_r07_a_missing_safety_zone_status_blocks(tmp_path: Path) -> None:
    report = check(tmp_path, FakeGh(status={"statuses": []}))
    assert failed(report) == {"必过检查和 safety-zone"}
    assert "safety-zone：没有出现" in "\n".join(render(report))


def test_r08_a_failing_status_blocks(tmp_path: Path) -> None:
    gh = FakeGh(status={"statuses": [{"context": "safety-zone", "state": "failure"}]})
    assert failed(check(tmp_path, gh)) == {"必过检查和 safety-zone"}


@pytest.mark.parametrize(
    "override",
    [{"state": "MERGED"}, {"isDraft": True}, {"baseRefName": "dev"}],
)
def test_r09_closed_draft_or_wrong_base_blocks(tmp_path: Path, override: dict[str, object]) -> None:
    gh = FakeGh()
    gh.pr.update(override)
    assert failed(check(tmp_path, gh)) == {"PR 状态"}


def test_r10_a_conflict_blocks(tmp_path: Path) -> None:
    gh = FakeGh()
    gh.pr["mergeable"] = "CONFLICTING"
    assert failed(check(tmp_path, gh)) == {"与 main 无冲突"}


def plc_pr(comments: list[dict[str, object]]) -> FakeGh:
    gh = FakeGh(comments=comments)
    gh.pr["files"] = [{"path": "0100_PLC自动化/DJ-1/02_PLC程序/FB.scl"}]
    return gh


def signed(sha: str, user: dict[str, object] | None = None) -> dict[str, object]:
    return {"body": f"安全签字 {sha}", "user": user or SIGNER, "html_url": "u"}


def test_r11_a_plc_change_without_a_signature_blocks(tmp_path: Path) -> None:
    report = check(tmp_path, plc_pr([]))
    assert failed(report) == {"安全签字"}


def test_r12_a_signature_for_an_old_head_blocks(tmp_path: Path) -> None:
    assert failed(check(tmp_path, plc_pr([signed(OLD[:12])]))) == {"安全签字"}


def test_r13_a_signature_for_the_current_head_by_the_signer_passes(tmp_path: Path) -> None:
    assert check(tmp_path, plc_pr([signed(HEAD[:12])])).ready


def test_r13b_a_signature_of_10_digits_no_longer_counts(tmp_path: Path) -> None:
    """TD-SW008-215：与 safety-gate 同一个口径，短于 12 位不认。"""
    report = check(tmp_path, plc_pr([signed(HEAD[:10])]))
    assert failed(report) == {"安全签字"}
    assert "不足 12 位" in "".join(item.detail for item in report.items)


def test_r14_a_signature_by_someone_else_blocks(tmp_path: Path) -> None:
    other = {"login": "someone", "id": 1}
    assert failed(check(tmp_path, plc_pr([signed(HEAD[:12], other)]))) == {"安全签字"}


def test_r15_a_declared_yes_needs_the_signature_even_without_plc_files(tmp_path: Path) -> None:
    gh = FakeGh()
    gh.pr["body"] = "## 安全回路\n\n安全回路: 是\n"
    assert failed(check(tmp_path, gh)) == {"安全签字"}


def test_r16_only_reads_are_issued_and_nothing_merges(tmp_path: Path) -> None:
    gh = FakeGh()
    check(tmp_path, gh)
    assert gh.calls
    for call in gh.calls:
        assert call[0] in {"pr", "api", "repo"}
        assert call[:2] != ("pr", "merge") and "-X" not in call and "--method" not in call
        assert not {"merge", "comment", "edit", "close", "review"} & set(call[:2])


def test_r18_cli_exit_codes_and_plain_words(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gh = FakeGh()
    monkeypatch.setattr("auto_pm.application.core.pr_ready_service.default_gh", gh)
    directory = report_dir(tmp_path, GOOD_REPORT)
    args = ["-w", str(REPO_ROOT), "--control-root", str(REPO_ROOT), "pr", "ready", "170", "--repo", "o/r"]
    ok = CliRunner().invoke(cli, [*args, "--reports-dir", str(directory)])
    assert ok.exit_code == 0, ok.output
    gh.pr["mergeable"] = "CONFLICTING"
    bad = CliRunner().invoke(cli, [*args, "--reports-dir", str(directory)])
    assert bad.exit_code == 1 and "不能合并，缺：与 main 无冲突" in bad.output
