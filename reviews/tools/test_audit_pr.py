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


# --- CI verdict: Actions runs, check runs and commit statuses --------------------------------------------------


def _run(rid: int = 1, conclusion: str | None = "success", status_: str = "completed") -> dict:
    return {"id": rid, "event": "pull_request", "head_sha": "a" * 40, "workflow_id": 1, "conclusion": conclusion, "status": status_}


def test_green_actions_with_failed_safety_zone_status_does_not_pass():
    verdict, detail = audit_pr.judge_ci([_run()], [], [{"context": "safety-zone", "state": "failure"}], True)
    assert verdict == "FAIL"
    assert "safety-zone" in detail


@pytest.mark.parametrize("state", ["failure", "error"])
def test_any_failed_or_errored_status_fails(state):
    assert audit_pr.judge_ci([_run()], [], [{"context": "other", "state": state}], True)[0] == "FAIL"


def test_pending_safety_zone_fails_but_other_pending_is_only_unverified():
    assert audit_pr.judge_ci([_run()], [], [{"context": "safety-zone", "state": "pending"}], True)[0] == "FAIL"
    assert audit_pr.judge_ci([_run()], [], [{"context": "other", "state": "pending"}], True)[0] == "UNVERIFIED"


def test_failed_check_run_fails_and_unfinished_check_run_is_unverified():
    bad = {"name": "lint", "status": "completed", "conclusion": "failure"}
    running = {"name": "lint", "status": "in_progress", "conclusion": None}
    assert audit_pr.judge_ci([_run()], [bad], [], True)[0] == "FAIL"
    assert audit_pr.judge_ci([_run()], [running], [], True)[0] == "UNVERIFIED"


def test_all_green_with_safety_zone_passes_and_a_missing_safety_zone_is_unverified_for_every_pr():
    ok = [{"context": "safety-zone", "state": "success"}]
    assert audit_pr.judge_ci([_run()], [], ok, True)[0] == "PASS"
    # Same rule as pr_ready: a green head without `safety-zone` has not been through the gate, whatever it changed.
    verdict, detail = audit_pr.judge_ci([_run()], [], [{"context": "other", "state": "success"}], True)
    assert verdict == "UNVERIFIED" and "safety-zone" in detail
    assert audit_pr.judge_ci([_run()], [], [], True)[0] == "UNVERIFIED"


def test_statuses_alone_count_when_there_are_no_actions_runs():
    # safety-gate is comment-triggered: its result is a status on a head that may have no workflow run at all.
    assert audit_pr.judge_ci([], [], [{"context": "safety-zone", "state": "failure"}], False)[0] == "FAIL"
    assert audit_pr.judge_ci([], [], [], False)[0] == "UNVERIFIED"  # nothing reported, safety-zone included
    assert audit_pr.judge_ci([], [], [], True)[0] == "UNVERIFIED"


def test_audit_reads_statuses_from_github(world, monkeypatch):
    head = world["open_pr"](31, {"src/app.py": "x = 31\n"})
    answers = {
        "/pulls/31": {"state": "open", "head": {"sha": head}, "base": {"sha": world["base"]}},
        "/actions/runs": {"workflow_runs": [_run() | {"head_sha": head}]},
        "/check-runs": {"check_runs": []},
        "/status": {"statuses": [{"context": "safety-zone", "state": "failure"}]},
    }

    def fake(path: str):
        return next((v for k, v in answers.items() if k in path), None)

    monkeypatch.setattr(audit_pr, "github_json", fake)
    _info, checks = world["audit"](31, network=True)
    assert status(checks, "ci_result") == "FAIL"
    answers["/status"] = {"statuses": [{"context": "safety-zone", "state": "success"}]}
    _info, checks = world["audit"](31, network=True)
    assert status(checks, "ci_result") == "PASS"
    answers["/status"] = None
    _info, checks = world["audit"](31, network=True)
    assert status(checks, "ci_result") == "UNVERIFIED"


def _cut_the_network(work: Path) -> None:
    run(work, "remote", "set-url", "origin", str(work.parent / "no-such-remote.git"))


def test_offline_audit_uses_local_refs_and_does_not_fetch(world, monkeypatch):
    head = world["open_pr"](40, {"src/app.py": "x = 2\n"})
    world["audit"](40)  # online once: leaves refs/audit/pr-40 and origin/main in the clone
    _cut_the_network(world["work"])
    info, _ = audit_pr.audit(40, repo="x/y", remote="origin", network=False, fetch=False, cwd=str(world["work"]), patch=None, patch_base=None)
    assert info["head"] == head
    monkeypatch.chdir(world["work"])
    assert audit_pr.main(["40", "--offline", "--skip-ci-result"]) in (0, 1)  # never 2: no fetch was tried


def test_offline_audit_without_local_refs_says_what_is_missing(world):
    world["open_pr"](41, {"src/app.py": "x = 2\n"})
    _cut_the_network(world["work"])
    with pytest.raises(audit_pr.GitError, match="refs/audit/pr-41"):
        audit_pr.audit(41, repo="x/y", remote="origin", network=False, fetch=False, cwd=str(world["work"]), patch=None, patch_base=None)


def test_online_audit_still_fetches_so_a_dead_network_is_an_error(world):
    world["open_pr"](42, {"src/app.py": "x = 2\n"})
    _cut_the_network(world["work"])
    with pytest.raises(audit_pr.GitError):
        world["audit"](42)


def test_roles_library_is_a_protected_path(world):
    world["open_pr"](50, {"roles/product-pm/SKILL.md": "x\n"})
    _, checks = world["audit"](50)
    detail = next(c.detail for c in checks if c.id == "protected_paths")
    assert status(checks, "protected_paths") == "WARN"
    assert "roles/product-pm/SKILL.md" in detail


def test_offline_audit_says_the_refs_may_be_stale(world):
    world["open_pr"](51, {"src/app.py": "x = 2\n"})
    world["audit"](51)
    _, checks = audit_pr.audit(51, repo="x/y", remote="origin", network=False, fetch=False, cwd=str(world["work"]), patch=None, patch_base=None)
    assert status(checks, "local_refs") == "UNVERIFIED"
    _, online = world["audit"](51)
    assert status(online, "local_refs") is None


def test_invalid_utf8_in_a_changed_text_file_fails(world):
    work = world["work"]
    run(work, "checkout", "-q", "-B", "enc", world["base"])
    (work / "docs").mkdir(exist_ok=True)
    (work / "docs/gbk.md").write_bytes("中文说明\n".encode("gbk"))
    head = commit(work, "gbk")
    run(work, "push", "-q", "-f", "origin", f"{head}:refs/pull/30/head")
    run(work, "checkout", "-q", "main")
    _, checks = world["audit"](30)
    assert status(checks, "text_encoding") == "FAIL"
    assert "docs/gbk.md" in next(c.detail for c in checks if c.id == "text_encoding")


def test_clean_text_and_non_text_files_pass_the_encoding_check(world):
    world["open_pr"](31, {"docs/ok.md": "中文 ä ö ü 日本語\n"})
    _, checks = world["audit"](31)
    assert status(checks, "text_encoding") == "PASS"


def test_newly_covered_suffixes_are_checked(world):
    work = world["work"]
    run(work, "checkout", "-q", "-B", "enc2", world["base"])
    (work / "a.scltest").write_bytes(b"ok \xff\xfe bad\n")
    head = commit(work, "scltest")
    run(work, "push", "-q", "-f", "origin", f"{head}:refs/pull/32/head")
    run(work, "checkout", "-q", "main")
    _, checks = world["audit"](32)
    assert status(checks, "text_encoding") == "FAIL"


def test_decode_reports_invalid_bytes_instead_of_swallowing_them(capsys):
    assert audit_pr.decode("中文".encode("utf-8"), "x") == "中文"
    assert capsys.readouterr().err == ""
    assert chr(0xFFFD) in audit_pr.decode("中文".encode("gbk"), "git diff 输出")
    assert "非法 UTF-8" in capsys.readouterr().err


def test_git_output_with_invalid_bytes_warns(world, capsys):
    work = world["work"]
    run(work, "checkout", "-q", "-B", "gbk", world["base"])
    (work / "docs").mkdir(exist_ok=True)
    (work / "docs/gbk.md").write_bytes("中文说明\n".encode("gbk"))
    commit(work, "gbk")
    out = audit_pr.git("diff", "--no-color", f"{world['base']}..HEAD", cwd=str(work))
    assert "docs/gbk.md" in out
    assert "非法 UTF-8" in capsys.readouterr().err


def test_patch_with_invalid_bytes_is_applied_byte_for_byte(world, tmp_path):
    work = world["work"]
    run(work, "checkout", "-q", "-B", "gbkpatch", world["base"])
    (work / "gbk.txt").write_bytes("中文\n".encode("gbk"))
    commit(work, "gbk")
    patch = tmp_path / "p.patch"
    patch.write_bytes(audit_pr.git_bytes("diff", "--binary", f"{world['base']}..HEAD", cwd=str(work)))
    tree = audit_pr.patch_tree(str(patch), world["base"], cwd=str(work))
    assert audit_pr.git_bytes("show", f"{tree}:gbk.txt", cwd=str(work)) == "中文\n".encode("gbk")


def test_github_reply_that_is_not_utf8_counts_as_unavailable(monkeypatch):
    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"a": "\xff"}'

    monkeypatch.setattr(audit_pr.urllib.request, "urlopen", lambda *a, **k: Reply())
    assert audit_pr.github_json("x/y") is None
