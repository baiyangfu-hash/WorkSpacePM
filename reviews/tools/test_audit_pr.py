"""Tests for audit_pr.py: each test builds a throw-away repository with one planted defect.

Run with:  python -m pytest reviews/tools/test_audit_pr.py -q -p no:cacheprovider
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_pr

WORKFLOW = """name: ci
on:
  push:
    paths:
      - "src/**"
  pull_request:
    branches: [main]
    paths:
      - "src/**"
      - ".github/workflows/ci.yml"
  workflow_dispatch:
"""


def run(cwd: Path, *args: str) -> str:
    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
        "PATH": "/usr/bin:/bin",
        "HOME": str(cwd),
    }
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()


def write(repo: Path, name: str, text: str) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def commit(repo: Path, message: str) -> str:
    run(repo, "add", "-A")
    run(repo, "commit", "-q", "-m", message)
    return run(repo, "rev-parse", "HEAD")


@pytest.fixture()
def world(tmp_path: Path):
    """A remote with main and a PR branch, plus a clone the audit runs in."""
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    run(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    run(tmp_path, "clone", "-q", str(remote), str(work))
    run(work, "checkout", "-q", "-b", "main")
    write(work, "src/app.py", "x = 1\n")
    write(work, "docs/readme.md", "hello\n")
    write(work, audit_pr.WORKFLOW_FILE, WORKFLOW)
    base = commit(work, "base")
    run(work, "push", "-q", "origin", "main")

    def open_pr(number: int, files: dict[str, str], branch: str = "feature") -> str:
        run(work, "checkout", "-q", "-B", branch, base)
        for name, text in files.items():
            write(work, name, text)
        head = commit(work, f"pr {number}")
        run(work, "push", "-q", "-f", "origin", f"HEAD:refs/pull/{number}/head")
        run(work, "checkout", "-q", "main")
        return head

    def merge_pr(head: str, *, extra: dict[str, str] | None = None) -> str:
        run(work, "checkout", "-q", "main")
        run(work, "merge", "-q", "--no-ff", "--no-commit", head)
        for name, text in (extra or {}).items():
            write(work, name, text)
        merge = commit(work, "merge")
        run(work, "push", "-q", "origin", "main")
        return merge

    def audit(number: int, **kwargs):
        return audit_pr.audit(
            number,
            repo="x/y",
            remote="origin",
            network=kwargs.get("network", False),
            cwd=str(work),
            patch=kwargs.get("patch"),
            patch_base=kwargs.get("patch_base"),
        )

    return {"work": work, "base": base, "open_pr": open_pr, "merge_pr": merge_pr, "audit": audit}


def status(checks, check_id):
    return {c.id: c.status for c in checks}.get(check_id)


def test_clean_merge_passes(world):
    head = world["open_pr"](1, {"src/app.py": "x = 2\n"})
    world["merge_pr"](head)
    info, checks = world["audit"](1)
    assert info["state"] == "merged"
    assert status(checks, "merge_shape") == "PASS"
    assert status(checks, "merge_content") == "PASS"
    assert status(checks, "secrets") == "PASS"


def test_extra_change_hidden_in_merge_commit_fails(world):
    head = world["open_pr"](2, {"src/app.py": "x = 2\n"})
    world["merge_pr"](head, extra={"src/backdoor.py": "evil = True\n"})
    _, checks = world["audit"](2)
    detail = next(c.detail for c in checks if c.id == "merge_content")
    assert status(checks, "merge_content") == "FAIL"
    assert "src/backdoor.py" in detail


def test_open_pr_with_conflict_fails(world):
    head = world["open_pr"](3, {"src/app.py": "x = 3\n"})
    world["merge_pr"](world["open_pr"](4, {"src/app.py": "x = 4\n"}, branch="other"))
    assert head
    info, checks = world["audit"](3)
    assert info["state"] != "merged"
    assert status(checks, "mergeable") == "FAIL"
    assert next(c.detail for c in checks if c.id == "mergeable") == "和当前 main 冲突：src/app.py"


def test_token_in_added_line_fails(world):
    world["open_pr"](5, {"docs/readme.md": "token ghp_" + "a" * 36 + "\n"})
    _, checks = world["audit"](5)
    assert status(checks, "secrets") == "FAIL"
    # An added line starting with "++ " shows as "+++ " in the diff and must still be scanned.
    world["open_pr"](13, {"docs/readme.md": "++ ghp_" + "a" * 36 + "\n"}, branch="b13")
    _, checks = world["audit"](13)
    assert status(checks, "secrets") == "FAIL"


def test_personal_data_warns_but_allowed_addresses_do_not(world):
    world["open_pr"](6, {"docs/a.md": "mail me: someone@corp.cn\nCo-Authored-By: x <noreply@anthropic.com>\n"})
    _, checks = world["audit"](6)
    assert status(checks, "privacy") == "WARN"
    world["open_pr"](14, {"docs/c.md": "see C:/Users/someone/x\n"}, branch="b14")
    _, checks = world["audit"](14)
    assert "本机路径" in next(c.detail for c in checks if c.id == "privacy")
    world["open_pr"](7, {"docs/b.md": "Co-Authored-By: x <noreply@anthropic.com>\nstart 123456789012345678\n"}, branch="b7")
    _, checks = world["audit"](7)
    assert status(checks, "privacy") == "PASS"


def test_ci_path_filter(world):
    world["open_pr"](8, {"docs/readme.md": "only docs\n"})
    _, checks = world["audit"](8)
    assert "不会触发 CI" in next(c.detail for c in checks if c.id == "ci_expected")
    world["open_pr"](9, {"src/app.py": "x = 9\n"}, branch="b9")
    _, checks = world["audit"](9)
    assert "应当跑 CI" in next(c.detail for c in checks if c.id == "ci_expected")


def test_patch_comparison(world, tmp_path: Path):
    work = world["work"]
    run(work, "checkout", "-q", "-B", "patchsrc", world["base"])
    write(work, "src/app.py", "x = 10\n")
    write(work, "src/extra.py", "y = 1\n")
    run(work, "add", "-A")
    patch = tmp_path / "p.patch"
    patch.write_text(run(work, "diff", "--cached") + "\n", encoding="utf-8")
    run(work, "reset", "-q", "--hard", world["base"])
    run(work, "checkout", "-q", "main")

    world["open_pr"](10, {"src/app.py": "x = 10\n", "src/extra.py": "y = 1\n"})
    _, checks = world["audit"](10, patch=str(patch), patch_base=world["base"])
    assert status(checks, "patch") == "PASS"

    world["open_pr"](11, {"src/app.py": "x = 10\n"}, branch="b11")  # the PR drops src/extra.py
    _, checks = world["audit"](11, patch=str(patch), patch_base=world["base"])
    assert status(checks, "patch") == "WARN"
    assert "src/extra.py" in next(c.detail for c in checks if c.id == "patch")


def test_audit_leaves_worktree_and_index_untouched(world):
    work = world["work"]
    world["open_pr"](12, {"src/app.py": "x = 12\n"})
    run(work, "checkout", "-q", "main")
    write(work, "local.txt", "uncommitted\n")
    before = run(work, "status", "--porcelain")
    world["audit"](12)
    assert run(work, "status", "--porcelain") == before


def test_fast_forward_merge_warns_instead_of_failing(world, monkeypatch):
    work = world["work"]
    head = world["open_pr"](15, {"src/app.py": "x = 15\n"})
    run(work, "merge", "-q", "--ff-only", head)
    run(work, "push", "-q", "origin", "main")
    info, checks = world["audit"](15)
    assert info["state"] == "merged"
    assert status(checks, "merge_shape") == "WARN"
    assert status(checks, "scope") == "UNVERIFIED"  # offline the PR's own base is unknown
    assert not any(c.status == "FAIL" for c in checks)

    monkeypatch.setattr(audit_pr, "github_json", lambda path: {"merged_at": "x", "base": {"sha": world["base"]}})
    info, checks = world["audit"](15, network=True)
    assert info["files"] == ["src/app.py"]
    assert status(checks, "merge_shape") == "WARN"
