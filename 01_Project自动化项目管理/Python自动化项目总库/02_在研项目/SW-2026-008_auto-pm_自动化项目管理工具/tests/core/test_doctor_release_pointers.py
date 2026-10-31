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

    # This fixture only has pointers; the record cross-check has its own tests (tests/infrastructure/test_release_consistency.py).
    monkeypatch.setattr("auto_pm.ui.cli.doctor.check_release_consistency", lambda root: {"status": "info", "failures": [], "warnings": []})

    from auto_pm.ui.cli.doctor import doctor_command

    clean = CliRunner().invoke(doctor_command, ["-w", str(repo)])
    assert "发布指针与本机部署" in clean.output and "PASS" in clean.output
    assert clean.exit_code == 0, clean.output
    _write(repo, "1.3.5-ccccccc", ACTIVE, [PREVIOUS, ACTIVE, "1.3.5-ccccccc"])
    lagging = CliRunner().invoke(doctor_command, ["-w", str(repo)])
    assert lagging.exit_code == 1, lagging.output
    assert "发布指针落后" in lagging.output
