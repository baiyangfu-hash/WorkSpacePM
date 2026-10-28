"""TD-202：提交钩子与 PR 检查共用的密钥识别。"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from auto_pm.domain import secret_patterns as sp
from auto_pm.infrastructure.git_hook_enforcer import enforce_pre_commit
from tests.git_support import run_git

GHP = "ghp_" + "a" * 36
PAT = "github_pat_" + "A1b2C3d4E5" * 3
REPO_ROOT = Path(__file__).resolve().parents[6]


def diff_for(path: str, line: str, blob: str = "1" * 40) -> str:
    return f"diff --git a/{path} b/{path}\nnew file mode 100644\nindex {'0' * 40}..{blob}\n--- /dev/null\n+++ b/{path}\n@@ -0,0 +1 @@\n+{line}\n"


@pytest.mark.parametrize(
    "secret",
    [
        GHP,
        PAT,
        "gho_" + "b" * 30,
        "sk-" + "x" * 30,
        "sk-ant-" + "y" * 30,
        "AKIA" + "A" * 16,
        "-----BEGIN RSA " + "PRIVATE KEY-----",
    ],
)
def test_p01_known_secret_formats_are_found(secret: str) -> None:
    findings = sp.scan_unified_diff(diff_for("a.txt", f"x = {secret}"))
    assert [f.path for f in findings] == ["a.txt"]


def test_p02_ordinary_text_and_short_prefixes_pass() -> None:
    assert (
        sp.scan_unified_diff(diff_for("a.txt", "ghp_short and github_pat_ and sk-1 and AKIA123"))
        == []
    )


def test_p03_findings_never_carry_the_secret_text() -> None:
    finding = sp.scan_unified_diff(diff_for("a.txt", GHP))[0]
    assert GHP not in repr(finding)


def test_p04_a_line_that_looks_like_a_diff_header_is_still_content() -> None:
    text = diff_for("a.txt", "x").replace("+x\n", f"++ {GHP}\n")
    assert len(sp.scan_unified_diff(text)) == 1


def test_p05_removed_and_context_lines_are_not_scanned() -> None:
    text = f"diff --git a/a b/a\nindex {'1' * 40}..{'2' * 40} 100644\n--- a/a\n+++ b/a\n@@ -1 +1 @@\n-{GHP}\n {PAT}\n+clean\n"
    assert sp.scan_unified_diff(text) == []


def test_p06_the_revoked_blob_is_allowlisted_but_other_blobs_are_not() -> None:
    (blob,) = sp.ALLOWED_SECRET_BLOBS
    assert blob.startswith("25c80b56e7") and len(blob) == 40
    assert sp.scan_unified_diff(diff_for("gittoken.txt", GHP, blob)) == []
    assert len(sp.scan_unified_diff(diff_for("gittoken.txt", GHP, "3" * 40))) == 1


def test_p07_findings_are_per_file_and_category_once() -> None:
    text = diff_for("a.txt", GHP) + diff_for("b.txt", GHP).replace("+" + GHP, f"+{GHP}\n+{GHP}")
    assert sorted(f.path for f in sp.scan_unified_diff(text)) == ["a.txt", "b.txt"]


def test_p08_audit_pr_patterns_stay_in_sync_with_the_shared_ones() -> None:
    spec = importlib.util.spec_from_file_location(
        "audit_pr_for_sync", REPO_ROOT / "reviews" / "tools" / "audit_pr.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclass 解析注解时要在 sys.modules 里找到本模块
    spec.loader.exec_module(module)
    assert {k: v.pattern for k, v in module.SECRET_PATTERNS.items()} == {
        k: v.pattern for k, v in sp.SECRET_PATTERNS.items()
    }


def git(repo: Path, *args: str) -> str:
    return run_git(repo, *args).stdout


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.invalid")
    git(tmp_path, "config", "user.name", "t")
    return tmp_path


def test_p09_pre_commit_rejects_a_staged_secret_and_does_not_echo_it(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / "notes.md").write_text(f"token {GHP}\n", encoding="utf-8")
    git(repo, "add", "notes.md")
    assert enforce_pre_commit(repo) == 1
    out = capsys.readouterr().out
    assert "notes.md" in out and "GitHub 令牌" in out and GHP not in out


def test_p10_pre_commit_passes_a_clean_staged_file(repo: Path) -> None:
    (repo / "notes.md").write_text("hello\n", encoding="utf-8")
    git(repo, "add", "notes.md")
    assert enforce_pre_commit(repo) == 0


def test_p11_pre_commit_allows_the_revoked_blob(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (repo / "gittoken.txt").write_text(f"{GHP}\n", encoding="utf-8")
    git(repo, "add", "gittoken.txt")
    assert enforce_pre_commit(repo) == 1
    blob = git(repo, "rev-parse", ":gittoken.txt").strip()
    monkeypatch.setattr(sp, "ALLOWED_SECRET_BLOBS", frozenset({blob}))
    assert enforce_pre_commit(repo) == 0


def test_p12_pre_commit_rejects_when_the_diff_cannot_be_read(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from auto_pm.infrastructure import git_hook_enforcer as hook

    real = subprocess.run

    def broken(cmd, *args, **kwargs):  # type: ignore[no-untyped-def]
        if "--cached" in cmd and "-U0" in cmd:
            raise OSError("boom")
        return real(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", broken)
    assert hook._enforce_secret_scan(repo) == 1
    assert "无法扫描暂存区密钥" in capsys.readouterr().out
