"""doctor: the release pointers on main must match the release deployed on this machine (TD-244)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from auto_pm.ui.cli.doctor import POINTER_DIR, check_release_pointers

ACTIVE, PREVIOUS = "1.3.4-aaaaaaa", "1.3.3-bbbbbbb"


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=ci", "-c", "user.email=ci@example.invalid", *args],
        check=True,
        capture_output=True,
    )


def _write(root: Path, active: str, previous: str, manifest_ids: list[str]) -> None:
    folder = root / POINTER_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "active_release.json").write_text(json.dumps({"release_id": active}), encoding="utf-8")
    (folder / "previous_release.json").write_text(json.dumps({"release_id": previous}), encoding="utf-8")
    (folder / "deployment_manifest.json").write_text(
        json.dumps({"releases": {release: {} for release in manifest_ids}}), encoding="utf-8"
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _write(tmp_path, ACTIVE, PREVIOUS, [PREVIOUS, ACTIVE])
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "release pointers")
    return tmp_path


def test_pointers_that_match_the_deployed_release_pass(repo: Path) -> None:
    result = check_release_pointers(str(repo))
    assert result["status"] == "ok" and result["reasons"] == []


def test_a_machine_ahead_of_main_is_reported_for_each_stale_pointer(repo: Path) -> None:
    _write(repo, "1.3.5-ccccccc", ACTIVE, [PREVIOUS, ACTIVE, "1.3.5-ccccccc"])
    result = check_release_pointers(str(repo))
    assert result["status"] == "fail"
    joined = "；".join(result["reasons"])
    assert "active_release.json" in joined and "previous_release.json" in joined and "deployment_manifest.json" in joined
    assert "1.3.5-ccccccc" in joined


def test_only_the_previous_pointer_lagging_is_still_reported(repo: Path) -> None:
    _write(repo, ACTIVE, "1.3.2-ddddddd", [PREVIOUS, ACTIVE])
    result = check_release_pointers(str(repo))
    assert result["status"] == "fail" and len(result["reasons"]) == 1
    assert "previous_release.json" in result["reasons"][0]


def test_a_test_build_is_never_the_deployed_release(tmp_path: Path) -> None:
    test_build = "1.3.4.test.1-eeeeeee"
    _git(tmp_path, "init", "-q")
    _write(tmp_path, test_build, PREVIOUS, [PREVIOUS, test_build])
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "test build pointers")
    result = check_release_pointers(str(tmp_path))
    assert result["status"] == "fail"
    assert any("测试构建" in reason for reason in result["reasons"])


def test_pointers_missing_on_main_are_reported(repo: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    other = tmp_path_factory.mktemp("noptr")
    _git(other, "init", "-q")
    (other / "x.txt").write_text("x", encoding="utf-8")
    _git(other, "add", "-A")
    _git(other, "commit", "-q", "-m", "empty")
    _write(other, ACTIVE, PREVIOUS, [ACTIVE])
    result = check_release_pointers(str(other))
    assert result["status"] == "fail"
    assert any("读不到" in reason for reason in result["reasons"])


def test_no_local_pointer_means_nothing_to_judge(tmp_path: Path) -> None:
    assert check_release_pointers(str(tmp_path))["status"] == "info"


def test_a_broken_local_pointer_is_a_failure_not_a_guess(repo: Path) -> None:
    (repo / POINTER_DIR / "active_release.json").write_text(json.dumps({"slot": "x"}), encoding="utf-8")
    result = check_release_pointers(str(repo))
    assert result["status"] == "fail" and "release_id" in result["reasons"][0]


@pytest.mark.parametrize("name", ["active_release.json", "previous_release.json", "deployment_manifest.json"])
@pytest.mark.parametrize("damage", [b"{not json", b"\xff\xfe\x00bad bytes", b'["a list"]'])
def test_a_damaged_local_pointer_never_passes_silently(repo: Path, name: str, damage: bytes) -> None:
    (repo / POINTER_DIR / name).write_bytes(damage)
    result = check_release_pointers(str(repo))
    assert result["status"] == "fail"
    assert any(name in reason and "读不出来" in reason for reason in result["reasons"])


def test_the_doctor_command_exits_nonzero_when_the_pointers_lag(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from click.testing import CliRunner

    # This fixture only has pointers; the record cross-check has its own tests (tests/core/test_release_consistency.py).
    monkeypatch.setattr("auto_pm.ui.cli.doctor.check_release_consistency", lambda root: {"status": "info", "failures": [], "warnings": []})

    from auto_pm.ui.cli.doctor import doctor_command

    clean = CliRunner().invoke(doctor_command, ["-w", str(repo)])
    assert "发布指针与本机部署" in clean.output and "PASS" in clean.output
    assert clean.exit_code == 0, clean.output
    _write(repo, "1.3.5-ccccccc", ACTIVE, [PREVIOUS, ACTIVE, "1.3.5-ccccccc"])
    lagging = CliRunner().invoke(doctor_command, ["-w", str(repo)])
    assert lagging.exit_code == 1, lagging.output
    assert "发布指针落后" in lagging.output


# --- the release PR: a branch that itself moves the pointers is compared with its own commit, not with main -------------------

NEW = "1.3.5-ccccccc"


def _commit(root: Path, message: str) -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


def _mark_main(root: Path) -> None:
    """Pretend the commit now checked out is origin/main (a bare remote is not needed: only the ref is read)."""

    _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")


@pytest.fixture
def pr_repo(repo: Path) -> Path:
    """``repo`` is main; the checkout moves to a PR branch off it."""

    _mark_main(repo)
    _git(repo, "checkout", "-q", "-b", "pr")
    return repo


def test_a_release_pr_that_moves_the_pointers_is_compared_with_its_own_head(pr_repo: Path) -> None:
    _write(pr_repo, NEW, ACTIVE, [PREVIOUS, ACTIVE, NEW])
    _commit(pr_repo, "release pointers + manifest entry")
    result = check_release_pointers(str(pr_repo))
    assert result["status"] == "ok" and result["reasons"] == [], result
    assert result["ref"] == "HEAD" and result["pr_head"] is True


def test_the_same_release_is_red_against_main_when_the_branch_changes_no_pointer(pr_repo: Path) -> None:
    """Without the pointer change in the branch the old rule stands: a machine ahead of main stays red."""

    _write(pr_repo, NEW, ACTIVE, [PREVIOUS, ACTIVE, NEW])  # not committed: the machine is ahead, the branch did nothing
    result = check_release_pointers(str(pr_repo))
    assert result["status"] == "fail" and result["ref"] == "origin/main" and result["pr_head"] is False
    assert "发版后的指针还没入库" in "；".join(result["reasons"])


def test_pointers_moved_by_the_pr_but_not_listed_in_the_manifest_stay_red(pr_repo: Path) -> None:
    """The mutation: tamper with the pointers and leave the manifest alone -- the PR rule must not wave it through."""

    _write(pr_repo, NEW, ACTIVE, [PREVIOUS, ACTIVE])  # NEW is deployed and committed, but the manifest does not list it
    _commit(pr_repo, "pointers without a manifest entry")
    result = check_release_pointers(str(pr_repo))
    assert result["status"] == "fail" and result["pr_head"] is True
    assert any("deployment_manifest.json" in reason and NEW in reason for reason in result["reasons"]), result


def test_a_machine_ahead_of_the_pr_head_stays_red(pr_repo: Path) -> None:
    """The PR moved the pointers, but this machine deploys something newer that no commit carries."""

    _write(pr_repo, NEW, ACTIVE, [PREVIOUS, ACTIVE, NEW])
    _commit(pr_repo, "release pointers + manifest entry")
    _write(pr_repo, "1.3.6-ddddddd", NEW, [PREVIOUS, ACTIVE, NEW])
    result = check_release_pointers(str(pr_repo))
    assert result["status"] == "fail" and result["pr_head"] is True
    assert "发版后的指针还没入库" in "；".join(result["reasons"])


def test_a_branch_that_is_only_behind_a_main_that_moved_the_pointers_is_not_a_release_pr(pr_repo: Path) -> None:
    """Three dots: main moved the pointers after this branch left it; the branch itself changed none, so the old rule applies."""

    (pr_repo / "other.txt").write_text("work", encoding="utf-8")
    _commit(pr_repo, "unrelated work on the branch")
    _git(pr_repo, "checkout", "-q", "-b", "main-moves-on", "HEAD~1")
    _write(pr_repo, NEW, ACTIVE, [PREVIOUS, ACTIVE, NEW])
    _commit(pr_repo, "main ships a release")
    _mark_main(pr_repo)
    _git(pr_repo, "checkout", "-q", "pr")
    result = check_release_pointers(str(pr_repo))
    assert result["status"] == "fail" and result["ref"] == "origin/main" and result["pr_head"] is False, result


def test_an_explicit_ref_is_never_overridden_by_the_pr_rule(pr_repo: Path) -> None:
    _write(pr_repo, NEW, ACTIVE, [PREVIOUS, ACTIVE, NEW])
    _commit(pr_repo, "release pointers + manifest entry")
    result = check_release_pointers(str(pr_repo), ref="origin/main")
    assert result["status"] == "fail" and result["ref"] == "origin/main" and result["pr_head"] is False


def test_when_git_cannot_say_what_the_branch_changed_the_strict_rule_stays(pr_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing ``git diff`` must make the check stricter or equal, never laxer."""

    _write(pr_repo, NEW, ACTIVE, [PREVIOUS, ACTIVE, NEW])
    _commit(pr_repo, "release pointers + manifest entry")
    monkeypatch.setattr("auto_pm.ui.cli.doctor._pointers_changed_by_head", lambda *_a, **_k: False)
    result = check_release_pointers(str(pr_repo))
    assert result["status"] == "fail" and result["ref"] == "origin/main"


def test_a_release_pr_must_name_the_release_it_replaced_as_previous(pr_repo: Path) -> None:
    """Self-consistency is not exemption: the active pointer moved from ACTIVE to NEW, so previous has to say ACTIVE."""

    _write(pr_repo, NEW, PREVIOUS, [PREVIOUS, ACTIVE, NEW])  # previous left at the version before ACTIVE
    _commit(pr_repo, "pointers where previous skips a release")
    result = check_release_pointers(str(pr_repo))
    assert result["status"] == "fail" and result["pr_head"] is True
    assert any("previous_release.json" in reason and ACTIVE in reason for reason in result["reasons"]), result


def test_a_pr_that_only_adds_a_manifest_entry_does_not_need_a_previous_change(pr_repo: Path) -> None:
    """The active pointer did not move, so the previous rule has nothing to say; the machine still matches its own head."""

    _write(pr_repo, ACTIVE, PREVIOUS, [PREVIOUS, ACTIVE, NEW])
    _commit(pr_repo, "manifest entry only")
    result = check_release_pointers(str(pr_repo))
    assert result["status"] == "ok" and result["pr_head"] is True, result


def _tree(root: Path, release: str) -> None:
    folder = root / POINTER_DIR / "releases" / release
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "release_meta.json").write_text(json.dumps({"release_id": release}), encoding="utf-8")


def test_the_payload_tree_check_still_runs_for_a_release_pr(pr_repo: Path) -> None:
    """The other half of 'not exempt': the cross-check of manifest and payload folders is not touched by the PR rule.

    The new release is in the manifest but its folder is missing -> the consistency check is red; with the folder it is not.
    """

    from auto_pm.application.core.release_consistency import check_release_consistency

    for release in (PREVIOUS, ACTIVE):
        _tree(pr_repo, release)
    _write(pr_repo, NEW, ACTIVE, [PREVIOUS, ACTIVE, NEW])
    _commit(pr_repo, "release pointers + manifest entry, payload folder forgotten")
    assert check_release_pointers(str(pr_repo))["status"] == "ok"  # the pointer check alone cannot see the folder
    missing = check_release_consistency(str(pr_repo))
    assert missing["status"] == "fail"
    assert any(NEW in failure and "目录" in failure for failure in missing["failures"]), missing

    _tree(pr_repo, NEW)
    # (the bare fixture manifest has no source_commit, so other lines stay red; only the folder lines must be gone)
    assert not any("目录" in failure for failure in check_release_consistency(str(pr_repo))["failures"])
