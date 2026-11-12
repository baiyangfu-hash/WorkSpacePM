"""doctor's last line says what did not pass, and never "一切正常" while a row warns (TD-SW008-518, TD-SW008-576)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner

from auto_pm.ui.cli.doctor import doctor_command, doctor_verdict, run_doctor_check
from tests.core.test_doctor_worktree_floor import _git

ALL_GOOD = "一切正常"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    (tmp_path / "README.md").write_text("x\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def _rows(monkeypatch: pytest.MonkeyPatch, *, stray: int = 0, consistency: dict[str, Any] | None = None, gh: bool = True) -> None:
    """Every row doctor reads is fixed here, so only what a test changes can move the verdict."""

    monkeypatch.setattr("auto_pm.ui.cli.doctor.importlib.util.find_spec", lambda name: object())
    monkeypatch.setattr(
        "auto_pm.ui.cli.doctor.GovernanceService",
        lambda **kwargs: SimpleNamespace(inspect_sanitation=lambda: SimpleNamespace(is_pure=stray == 0, total_issues=stray)),
    )
    monkeypatch.setattr("auto_pm.ui.cli.doctor.check_venv_base", lambda: {"status": "ok", "home": "/py", "reasons": []})
    monkeypatch.setattr("auto_pm.ui.cli.doctor.check_release_pointers", lambda root: {"status": "info", "reasons": [], "ref": ""})
    monkeypatch.setattr(
        "auto_pm.ui.cli.doctor.check_release_consistency",
        lambda root: consistency or {"status": "info", "failures": [], "warnings": []},
    )
    monkeypatch.setattr("auto_pm.ui.cli.doctor.check_change_status_history", lambda root: {"status": "ok", "reasons": []})
    monkeypatch.setattr("auto_pm.application.core.pr_open_service.gh_status", lambda: (gh, gh))


def _last_lines(root: Path) -> str:
    result = CliRunner().invoke(doctor_command, ["-w", str(root)])
    assert result.exit_code == 0, result.output
    assert "┘" in result.output, result.output
    return result.output.rsplit("┘", 1)[-1]  # what doctor prints after the table


def test_a_healthy_machine_still_says_all_is_well(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _rows(monkeypatch)
    assert doctor_verdict(run_doctor_check(str(root))) == ([], [])
    assert ALL_GOOD in _last_lines(root)


def test_d253_stray_files_are_named_as_the_cause_not_dependencies(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _rows(monkeypatch, stray=3)
    res = run_doctor_check(str(root))
    blocking, _ = doctor_verdict(res)
    assert res["all_passed"] is False and blocking == ["工作空间纯净度守卫（3 个游离文件）"]
    tail = _last_lines(root)
    assert "没通过：工作空间纯净度守卫（3 个游离文件）" in tail
    assert "依赖" not in tail and ALL_GOOD not in tail


def test_a_missing_package_is_named(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _rows(monkeypatch)
    monkeypatch.setattr("auto_pm.ui.cli.doctor.importlib.util.find_spec", lambda name: None if name == "mypy" else object())
    assert doctor_verdict(run_doctor_check(str(root)))[0] == ["缺依赖：mypy"]


def test_d311_a_warning_row_means_no_all_is_well_line(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    warned = {"status": "warn", "failures": [], "warnings": ["12 个版本没有在 release_annotations.json 里标注（回退资格没有书面依据）：a、b"]}
    _rows(monkeypatch, consistency=warned)
    res = run_doctor_check(str(root))
    assert res["all_passed"] is True, "a warning still does not block"
    assert doctor_verdict(res) == ([], ["发布记录互相核对（1 条提示）"])
    tail = _last_lines(root)
    assert "要留意（不挡路）：发布记录互相核对（1 条提示）" in tail and ALL_GOOD not in tail


def test_gh_missing_is_a_note_not_a_failure(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _rows(monkeypatch, gh=False)
    assert doctor_verdict(run_doctor_check(str(root))) == ([], ["GitHub 命令行 gh（未安装）"])


@pytest.mark.parametrize("stray", [0, 2])
@pytest.mark.parametrize("missing", [False, True])
def test_the_blocking_list_is_empty_exactly_when_all_passed(
    root: Path, monkeypatch: pytest.MonkeyPatch, stray: int, missing: bool
) -> None:
    _rows(monkeypatch, stray=stray)
    if missing:
        monkeypatch.setattr("auto_pm.ui.cli.doctor.importlib.util.find_spec", lambda name: None)
    res = run_doctor_check(str(root))
    assert (doctor_verdict(res)[0] == []) is res["all_passed"]
