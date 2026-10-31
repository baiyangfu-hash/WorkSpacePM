"""N1: a new project never lands in the tool's release folder, and a relative path means where the user typed the command."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from auto_pm.application.core.paths import ProjectDestinationError, resolve_project_destination
from auto_pm.ui.cli.__main__ import cli

RELEASE = Path("00_Infrastructure") / "auto_pm" / "releases" / "1.3.3-aaaaaaa"


def _create(args: list[str], *, workspace: Path | None) -> Result:
    base = ["-w", str(workspace)] if workspace else []
    return CliRunner().invoke(
        cli,
        [
            *base,
            "project",
            "create",
            "--stack",
            "python",
            "--id",
            "SW-2026-901",
            "--name",
            "落点",
            "--dry-run",
            *args,
        ],
        catch_exceptions=False,
    )


@pytest.fixture
def launched(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """What the launcher does: the process sits in the release folder, the user's folder is in AUTO_PM_CALLER_CWD."""

    workspace = tmp_path / "ws"
    release = workspace / RELEASE
    release.mkdir(parents=True)
    caller = tmp_path / "caller"
    caller.mkdir()
    monkeypatch.chdir(release)
    monkeypatch.setenv("AUTO_PM_CALLER_CWD", str(caller))
    monkeypatch.delenv("AUTO_PM_WORKSPACE", raising=False)
    return {"workspace": workspace, "release": release, "caller": caller}


def test_a_relative_dest_dir_means_the_users_folder_not_the_release_folder(
    launched: dict[str, Path],
) -> None:
    result = _create(["--dest-dir", "out"], workspace=launched["workspace"])
    assert result.exit_code == 0, result.output
    assert str(launched["caller"] / "out" / "SW-2026-901_落点") in result.output.replace("\n", "")
    assert str(launched["release"]) not in result.output.replace("\n", "")


def test_a_dest_dir_inside_the_release_tree_is_refused(launched: dict[str, Path]) -> None:
    result = _create(
        ["--dest-dir", str(launched["release"] / "mine")], workspace=launched["workspace"]
    )
    assert result.exit_code == 1
    assert "发布目录" in result.output
    assert not (launched["release"] / "mine").exists()


def test_without_dest_dir_the_project_goes_below_the_workspace(launched: dict[str, Path]) -> None:
    result = _create([], workspace=launched["workspace"])
    assert result.exit_code == 0, result.output
    assert str(launched["workspace"] / "0100_项目" / "SW-2026-901_落点") in result.output.replace(
        "\n", ""
    )


def test_a_relative_workspace_means_the_users_folder_too(launched: dict[str, Path]) -> None:
    other = launched["caller"] / "other_ws"
    other.mkdir()
    result = CliRunner().invoke(
        cli,
        [
            "-w",
            "other_ws",
            "project",
            "create",
            "--stack",
            "python",
            "--id",
            "SW-2026-901",
            "--name",
            "落点",
            "--dry-run",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert str(other / "0100_项目" / "SW-2026-901_落点") in result.output.replace("\n", "")


def test_the_default_is_never_derived_from_the_running_release(tmp_path: Path) -> None:
    release_like = tmp_path / RELEASE
    release_like.mkdir(parents=True)
    with pytest.raises(ProjectDestinationError):
        resolve_project_destination(str(release_like), "python")


@pytest.mark.parametrize("stack", ["plc", "python"])
def test_default_destinations(stack: str, tmp_path: Path) -> None:
    expected = "0100_PLC自动化" if stack == "plc" else "0100_项目"
    assert Path(resolve_project_destination(str(tmp_path), stack)) == tmp_path / expected


def test_the_python_research_folder_wins_when_the_workspace_has_one(tmp_path: Path) -> None:
    research = tmp_path / "01_Project自动化项目管理" / "Python自动化项目总库" / "02_在研项目"
    research.mkdir(parents=True)
    assert Path(resolve_project_destination(str(tmp_path), "python")) == research


def test_the_release_check_follows_symlinks_and_ignores_case(tmp_path: Path) -> None:
    real = tmp_path / RELEASE
    real.mkdir(parents=True)
    link = tmp_path / "shortcut"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("no symlink support here")
    with pytest.raises(ProjectDestinationError):
        resolve_project_destination(str(tmp_path), "python", str(link))
    upper = Path(str(tmp_path / RELEASE).upper().replace(str(tmp_path).upper(), str(tmp_path)))
    if os.name == "nt":
        with pytest.raises(ProjectDestinationError):
            resolve_project_destination(str(tmp_path), "python", str(upper))


def test_a_folder_that_merely_resembles_the_release_tree_is_fine(tmp_path: Path) -> None:
    ok = tmp_path / "00_Infrastructure" / "auto_pm" / "releases_notes"
    assert Path(resolve_project_destination(str(tmp_path), "python", str(ok))) == ok


def test_the_workbench_window_uses_the_same_rule(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from auto_pm.application.workbench_use_cases import WorkbenchUseCases

    release_like = tmp_path / RELEASE
    release_like.mkdir(parents=True)
    uc = WorkbenchUseCases.__new__(WorkbenchUseCases)
    uc.template_service = object()  # type: ignore[assignment]
    uc.project_service = SimpleNamespace(workspace_root=str(release_like))
    outcome = uc.create_project("SW-2026-902", "窗", "python", "", "SW", "")
    assert outcome.success is False and "发布目录" in outcome.message
