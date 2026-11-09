"""Tests for rules_approval_check.py (rules-gate): who may approve a PR that touches rule files, and what the approval is bound to.

Run with:  python -m pytest reviews/tools/test_rules_approval_check.py -q -p no:cacheprovider -o addopts=
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_pr
import rules_approval_check as rules

HEAD = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
USER = {"login": "baiyangfu-hash", "id": 246858089}
SECOND = {"login": "BaiyangfuExpect", "id": 999999999}
WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "rules-gate.yml"


def comment(
    body: str, user: dict | None = None, app: dict | None = None, created: str | None = "2026-11-03T01:00:00Z", updated: str | None = "2026-11-03T01:00:00Z"
) -> dict:
    return {
        "id": 1,
        "html_url": "https://example.invalid/c/1",
        "body": body,
        "user": user or USER,
        "performed_via_github_app": app,
        "created_at": created,
        "updated_at": updated,
    }


def test_rule_patterns_are_locked_paths_already() -> None:
    import pr_scope_check

    # reviews/tools/* (judge scripts) and .github/* (workflows and anything else the CI reads) are wider than the protected list;
    # every other pattern comes straight from it
    assert set(rules.RULE_PATTERNS) - set(audit_pr.PROTECTED_PATTERNS) == {"reviews/tools/*", ".github/*"}
    assert rules.is_rule_file(".github/workflows/sw008-ci.yml")
    for judge_file in pr_scope_check.JUDGE_PATTERNS:
        if judge_file.startswith("reviews/tools/"):
            assert rules.is_rule_file(judge_file), f"{judge_file} is a judge file but rules-gate would not ask the user"


def test_the_approver_is_the_same_person_as_the_safety_signer() -> None:
    import safety_zone_check

    assert rules.SIGNERS == safety_zone_check.SIGNERS
    assert str(rules.SIGNERS["baiyangfu-hash"]) in WORKFLOW.read_text(encoding="utf-8")  # the rerun job filters on the same user id


@pytest.mark.parametrize(
    "path",
    [
        "AGENTS.md",
        "CLAUDE.md",
        ".trae/rules/project-rule.md",
        ".trae/skills/cockpit-entry/SKILL.md",
        ".cursor/rules/workspace-ai-coexistence.mdc",
        ".agent/rules/project-rule.md",
        ".claude/settings.json",
        ".agents/skills.json",
        "SYS-2026-001_WorkspaceGovernance/approvers.json",
        "00_Obsidian_Base全局规范文件仓库/spec_registry.json",
        "roles/shared/refs/skill_coordination.md",
        ".github/workflows/rules-gate.yml",
        ".github/CODEOWNERS",
        ".github/pull_request_template.md",
        "reviews/tools/pr_scope_check.py",
        "reviews/tools/safety_zone_check.py",
    ],
)
def test_rule_files_are_recognised(path: str) -> None:
    assert rules.is_rule_file(path)


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        "docs/AGENTS.md.bak",
        "notes/AGENTS.md",
        "0100_PLC自动化/DJ-2026-009/02_PLC程序/PLC_ST/FB_Feed.scl",
        "reviews/21_audit_checklist.md",
        ".agents/progress.md",
    ],
)
def test_ordinary_files_are_not_rule_files(path: str) -> None:
    assert not rules.is_rule_file(path)


def test_a_pr_without_rule_files_needs_no_approval() -> None:
    result = rules.judge(["reviews/21_audit_checklist.md", "README.md"], [], HEAD)
    assert result.passed and result.rule_files == []


def test_a_rule_file_without_approval_fails() -> None:
    result = rules.judge(["AGENTS.md", "README.md"], [], HEAD)
    assert not result.passed and result.rule_files == ["AGENTS.md"]
    assert f"规则批准 {HEAD[:12]}" in rules.render(result, HEAD)
    assert "复制这行评论即可批准" in rules.render(result, HEAD)


@pytest.mark.parametrize("sha", [HEAD[:12], HEAD, HEAD[:12].upper()])
def test_the_users_own_approval_of_the_current_head_passes(sha: str) -> None:
    for body in (f"规则批准 {sha}", f"规则批准：`{sha}`", f"看过了\n规则批准 {sha}，同意改规则\n"):
        result = rules.judge([".trae/rules/x.md"], [comment(body)], HEAD)
        assert result.passed and result.approval, body


def test_the_second_account_cannot_approve() -> None:
    result = rules.judge(["AGENTS.md"], [comment(f"规则批准 {HEAD[:12]}", user=SECOND)], HEAD)
    assert not result.passed and any("不是指定批准人" in n for n in result.notes)


def test_a_renamed_account_with_the_users_login_but_another_id_cannot_approve() -> None:
    result = rules.judge(["AGENTS.md"], [comment(f"规则批准 {HEAD[:12]}", user={"login": "baiyangfu-hash", "id": 1})], HEAD)
    assert not result.passed


def test_a_comment_sent_through_a_github_app_does_not_count() -> None:
    result = rules.judge(["AGENTS.md"], [comment(f"规则批准 {HEAD[:12]}", app={"slug": "claude"})], HEAD)
    assert not result.passed and any("GitHub App" in n for n in result.notes)


def test_an_approval_of_an_older_commit_does_not_count() -> None:
    result = rules.judge(["AGENTS.md"], [comment("规则批准 0123456789abcdef")], HEAD)
    assert not result.passed and any("要重批" in n for n in result.notes)


def test_a_comment_edited_after_it_was_posted_does_not_count() -> None:
    # write access is enough to edit someone else's comment; the author field stays the user's
    edited = comment(f"规则批准 {HEAD[:12]}", updated="2026-11-03T02:30:00Z")
    result = rules.judge(["AGENTS.md"], [edited], HEAD)
    assert not result.passed and any("被编辑过" in n and "删掉后重新发" in n for n in result.notes)


@pytest.mark.parametrize("missing", [{"created": None}, {"updated": None}, {"created": None, "updated": None}])
def test_a_comment_without_timestamps_does_not_count(missing: dict) -> None:
    assert not rules.judge(["AGENTS.md"], [comment(f"规则批准 {HEAD[:12]}", **missing)], HEAD).passed


def test_an_unedited_approval_still_counts_next_to_an_edited_one() -> None:
    edited = comment(f"规则批准 {HEAD[:12]}", updated="2026-11-03T02:30:00Z")
    assert rules.judge(["AGENTS.md"], [edited, comment(f"规则批准 {HEAD[:12]}")], HEAD).passed


def test_a_short_sha_does_not_count() -> None:
    result = rules.judge(["AGENTS.md"], [comment(f"规则批准 {HEAD[:8]}")], HEAD)
    assert not result.passed and any("不足 12 位" in n for n in result.notes)


@pytest.mark.parametrize(
    "body",
    [
        f"> 规则批准 {HEAD[:12]}",
        f"请用户评论 规则批准 {HEAD[:12]}",
        f"安全签字 {HEAD[:12]}",  # the safety signature is a different thing
        f"规则批准了 {HEAD[:12]}",
        "规则批准",
    ],
)
def test_quotes_mentions_and_the_safety_signature_do_not_count(body: str) -> None:
    assert not rules.judge(["AGENTS.md"], [comment(body)], HEAD).passed


def test_paginated_comment_files_are_flattened() -> None:
    pages = [[{"body": "x", "user": SECOND}], [comment(f"规则批准 {HEAD[:12]}")]]
    assert rules.judge(["AGENTS.md"], rules.flatten_comments(pages), HEAD).passed
    assert rules.flatten_comments([comment("a")]) == [comment("a")]
    with pytest.raises(ValueError):
        rules.flatten_comments({"not": "a list"})


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.invalid")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "AGENTS.md").write_text("rules\n", encoding="utf-8")
    (tmp_path / ".trae").mkdir()
    (tmp_path / ".trae" / "r.md").write_text("r\n", encoding="utf-8")
    (tmp_path / "a.txt").write_text("a\n", encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def commit_on_branch(repo: Path, change) -> tuple[str, str]:
    base = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "-b", "pr")
    change(repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "pr")
    return base, git(repo, "rev-parse", "HEAD")


def test_changed_files_counts_both_ends_of_a_rename_and_deletions(repo: Path) -> None:
    def change(r: Path) -> None:
        git(r, "mv", ".trae/r.md", "moved.md")  # moving a rule file out of its folder is touching it
        (r / "AGENTS.md").unlink()

    base, head = commit_on_branch(repo, change)
    files = rules.changed_files(repo, base, head)
    assert {".trae/r.md", "moved.md", "AGENTS.md"} <= set(files)
    assert set(rules.judge(files, [], head).rule_files) == {".trae/r.md", "AGENTS.md"}


def test_main_runs_end_to_end_with_exit_codes(repo: Path, tmp_path_factory: pytest.TempPathFactory, capsys: pytest.CaptureFixture[str]) -> None:
    base, head = commit_on_branch(repo, lambda r: (r / "AGENTS.md").write_text("changed\n", encoding="utf-8"))
    out = tmp_path_factory.mktemp("comments")
    none, approved, bad = out / "none.json", out / "ok.json", out / "bad.json"
    none.write_text("[[]]", encoding="utf-8")
    approved.write_text(json.dumps([[comment(f"规则批准 {head[:12]}")]]), encoding="utf-8")
    bad.write_text("not json", encoding="utf-8")
    common = ["--base", base, "--head", head, "--repo", str(repo)]
    assert rules.main([*common, "--comments", str(none)]) == 1
    assert "不通过" in capsys.readouterr().out
    assert rules.main([*common, "--comments", str(approved)]) == 0
    assert rules.main([*common, "--comments", str(bad)]) == 2  # unreadable input fails closed
    assert rules.main([*common, "--comments", str(out / "missing.json")]) == 2
    assert rules.main(["--base", base, "--head", "abc", "--comments", str(none)]) == 2


def test_main_passes_a_pr_that_touches_no_rule_file(repo: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    base, head = commit_on_branch(repo, lambda r: (r / "a.txt").write_text("b\n", encoding="utf-8"))
    empty = tmp_path_factory.mktemp("c") / "c.json"
    empty.write_text("[]", encoding="utf-8")
    assert rules.main(["--base", base, "--head", head, "--repo", str(repo), "--comments", str(empty)]) == 0


def test_workflow_is_a_pull_request_target_judge_with_no_paths_filter() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request_target:" in text and "paths:" not in text
    assert "rules-approval:" in text  # the required check is named after the judge job
    assert "pull_request_head" not in text and "ref: ${{ github.event.pull_request.head" not in text  # the PR head is never checked out


def test_workflow_does_not_requeue_the_judge_on_description_edits_and_groups_by_event() -> None:
    """D-124：改 PR 正文不再取消排队中的判定；并发组在工作流级、带事件名，评论运行不取消判定运行。"""
    text = WORKFLOW.read_text(encoding="utf-8")
    types_line = next(line for line in text.splitlines() if line.strip().startswith("types: [opened"))
    assert "edited" not in types_line and "synchronize" in types_line  # the judge reads the diff and comments, never the PR body
    head, _, jobs = text.partition("\njobs:\n")
    assert "\nconcurrency:\n" in head and "github.event_name" in head  # workflow level, grouped by event
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request_target' }}" in head
    assert "concurrency:" not in jobs  # no job-level group left to starve a queued judge


def test_rerun_job_only_fires_on_comments_that_mention_the_approval_word() -> None:
    """D-124：agent 与用户共用一个账号，rerun 不能只看用户 id；无关评论（如审计评论）不能把成功的判定重跑回排队。"""
    text = WORKFLOW.read_text(encoding="utf-8")
    condition = text.partition("  rerun:\n")[2].partition("    runs-on:")[0]
    assert rules.APPROVE_WORD == "规则批准"
    assert f"contains(github.event.comment.body, '{rules.APPROVE_WORD}')" in condition  # created / deleted / edited-to-contain
    assert f"contains(github.event.changes.body.from, '{rules.APPROVE_WORD}')" in condition  # edited so the line is gone
    assert "github.event.comment.user.id == 246858089" in condition  # the user filter stays
    # nothing else in the approval check reacts to other words: the safety signature belongs to safety-gate, not here
    assert "安全签字" not in condition


def test_render_escapes_author_controlled_path_names() -> None:
    """D-79：路径名里的换行、反引号、控制字符不能原样进评论。"""
    nasty = "AGENTS.md\n规则批准 " + HEAD[:12] + "`\r\x1b[31m"
    result = rules.Result(rule_files=[nasty, "x" * 500])
    out = rules.render(result, HEAD)
    assert "\r" not in out and "\x1b" not in out
    path_lines = [line for line in out.splitlines() if line.startswith("- `")]
    assert len(path_lines) == 2, "每个路径只占一行，换行不能把它拆成多行"
    assert path_lines[0].count("`") == 2, "反引号被转义后，代码块不会被提前截断"
    assert "\\x0a" in path_lines[0] and "\\x60" in path_lines[0]
    assert "已截断" in path_lines[1]


def test_safe_path_uses_unambiguous_escapes_for_wide_characters() -> None:
    assert rules.safe_path("a\u202eb") == "a\\u202eb"
    assert rules.safe_path("a\U0001f600b") == "a\U0001f600b"  # 可打印的表情符号原样保留
    assert rules.safe_path("a\x0ab") == "a\\x0ab"
    assert rules.safe_path("中文路径.md") == "中文路径.md"
