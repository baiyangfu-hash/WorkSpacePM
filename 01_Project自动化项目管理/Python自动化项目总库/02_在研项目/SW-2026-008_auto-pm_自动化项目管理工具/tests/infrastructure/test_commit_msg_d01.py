"""D-01：commit-msg 钩子对小写单号和“没带进新内容的合并提交”的处理。"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from auto_pm.infrastructure.git_hook_enforcer import enforce_commit_msg


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path.parent, "init", str(tmp_path))
    _git(tmp_path, "config", "user.email", "t@example.com")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "base.py").write_text("base = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "base.py")
    _git(tmp_path, "commit", "-m", "base", "--no-verify")
    _git(tmp_path, "branch", "-M", "main")
    return tmp_path


def _message(repo: Path, text: str) -> Path:
    path = repo / ".git" / "MSG_TEST"
    path.write_text(text, encoding="utf-8")
    return path


def test_lowercase_change_number_counts_as_bound(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path)
    (repo / "x.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "x.py")

    enforce_commit_msg(repo, _message(repo, "fix: [chg-scpt-2026-170] y\n"))

    # 后面的变更单证据校验在这个裸仓里本来就过不了；这里只证明它不再被当成“未绑定变更单”。
    assert "未绑定变更单" not in capsys.readouterr().out


def test_message_without_any_change_number_is_still_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "x.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "x.py")

    assert enforce_commit_msg(repo, _message(repo, "fix: y\n")) == 1


def _start_merge(repo: Path, *, conflict_edit: str | None) -> None:
    _git(repo, "checkout", "-b", "feature")
    (repo / "feature.py").write_text("feature = 1\n", encoding="utf-8")
    (repo / "base.py").write_text("base = 2\n", encoding="utf-8")
    _git(repo, "add", "feature.py", "base.py")
    _git(repo, "commit", "-m", "feature", "--no-verify")
    _git(repo, "checkout", "main")
    _git(repo, "merge", "--no-ff", "--no-commit", "feature")
    if conflict_edit is not None:
        (repo / "base.py").write_text(conflict_edit, encoding="utf-8")
        _git(repo, "add", "base.py")


def test_merge_that_brings_in_nothing_new_needs_no_change_number(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    _start_merge(repo, conflict_edit=None)

    assert enforce_commit_msg(repo, _message(repo, "Merge branch 'feature' into main\n")) == 0


def test_merge_with_hand_edited_production_code_still_needs_a_change_number(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path)
    _start_merge(repo, conflict_edit="base = 999\n")

    assert enforce_commit_msg(repo, _message(repo, "Merge branch 'feature' into main\n")) == 1


def test_plain_commit_that_looks_like_a_merge_message_is_still_refused(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    (repo / "x.py").write_text("x = 1\n", encoding="utf-8")
    _git(repo, "add", "x.py")

    assert enforce_commit_msg(repo, _message(repo, "Merge branch 'feature' into main\n")) == 1
