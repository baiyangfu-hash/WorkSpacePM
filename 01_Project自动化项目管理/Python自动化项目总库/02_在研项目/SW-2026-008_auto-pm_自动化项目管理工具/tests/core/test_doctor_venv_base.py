"""doctor: the virtual environment's base Python is still there, is a normal install and is the recorded version."""

from __future__ import annotations

from pathlib import Path

from auto_pm.ui.cli.doctor import check_venv_base


def _venv(tmp_path: Path, home: Path, version: str = "3.12.14") -> Path:
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "pyvenv.cfg").write_text(
        f"home = {home}\ninclude-system-site-packages = false\nversion = {version}\n",
        encoding="utf-8",
    )
    return venv


def _check(venv: Path, base: Path, running: str = "3.12.14") -> dict[str, object]:
    return check_venv_base(str(venv), str(base), running)


def test_outside_a_virtual_environment_nothing_is_judged(tmp_path: Path) -> None:
    result = check_venv_base(str(tmp_path), str(tmp_path), "3.12.14")
    assert result["status"] == "info"


def test_a_normal_base_python_with_the_recorded_version_is_fine(tmp_path: Path) -> None:
    home = tmp_path / "Python312"
    home.mkdir()
    result = _check(_venv(tmp_path, home), home)
    assert result["status"] == "ok" and result["reasons"] == []


def test_a_base_python_that_is_gone_is_reported(tmp_path: Path) -> None:
    gone = tmp_path / "Python312-removed"
    result = _check(_venv(tmp_path, gone), gone)
    assert result["status"] == "warn"
    assert any("已不存在" in reason for reason in result["reasons"])  # type: ignore[attr-defined]


def test_a_base_python_inside_another_tools_cache_is_reported_while_it_still_works(
    tmp_path: Path,
) -> None:
    home = tmp_path / "Users" / "someone" / ".cache" / "codex-runtimes" / "python312"
    home.mkdir(parents=True)
    result = _check(_venv(tmp_path, home), home)
    assert result["status"] == "warn"
    assert any("缓存目录" in reason for reason in result["reasons"])  # type: ignore[attr-defined]


def test_a_windows_style_cache_path_is_recognised_too(tmp_path: Path) -> None:
    venv = tmp_path / ".venv"
    venv.mkdir()
    windows_home = "C:\\Users\\fubai\\.cache\\codex-runtimes\\python312"
    (venv / "pyvenv.cfg").write_text(
        f"home = {windows_home}\nversion = 3.12.14\n", encoding="utf-8"
    )
    result = _check(venv, tmp_path)
    assert any("缓存目录" in reason for reason in result["reasons"])  # type: ignore[attr-defined]


def test_a_replaced_base_python_is_reported_as_version_drift(tmp_path: Path) -> None:
    home = tmp_path / "Python312"
    home.mkdir()
    result = _check(_venv(tmp_path, home, version="3.12.13"), home, running="3.12.14")
    assert result["status"] == "warn"
    assert any("3.12.13" in reason and "3.12.14" in reason for reason in result["reasons"])  # type: ignore[attr-defined]


def test_version_is_compared_whole_not_by_prefix(tmp_path: Path) -> None:
    home = tmp_path / "Python312"
    home.mkdir()
    drifted = _check(_venv(tmp_path, home, version="3.12.1"), home, running="3.12.14")
    assert drifted["status"] == "warn"


def test_a_short_recorded_version_still_matches_the_same_minor(tmp_path: Path) -> None:
    home = tmp_path / "Python312"
    home.mkdir()
    assert _check(_venv(tmp_path, home, version="3.12"), home, running="3.12.14")["status"] == "ok"


def test_an_unreadable_pyvenv_cfg_is_reported_not_ignored(tmp_path: Path) -> None:
    venv = tmp_path / ".venv"
    venv.mkdir()
    result = _check(venv, tmp_path)
    assert result["status"] == "warn"
    assert any("pyvenv.cfg" in reason for reason in result["reasons"])  # type: ignore[attr-defined]
