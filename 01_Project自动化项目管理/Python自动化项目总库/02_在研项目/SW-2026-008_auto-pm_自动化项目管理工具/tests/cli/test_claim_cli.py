"""Claim CLI helpers (D-115 repository-root paths, offline hints for ``claim list``)."""

from __future__ import annotations

import json
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from auto_pm.application.core.claim_service import ClaimError
from auto_pm.ui.cli import claim as claim_cli

PROJECT = "proj/app"


def _tree(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "repo"
    project = root / PROJECT
    (project / "auto_pm").mkdir(parents=True)
    (project / "auto_pm" / "x.py").write_text("", encoding="utf-8")
    (root / "reviews").mkdir()
    return root, project


def test_a_path_typed_inside_the_project_folder_is_lifted_to_the_repository_root(tmp_path: Path) -> None:
    root, project = _tree(tmp_path)

    paths, notes = claim_cli.normalise_paths(root, project, ["auto_pm/x.py", "auto_pm/new_file.py", "./auto_pm"])

    assert paths == [f"{PROJECT}/auto_pm/x.py", f"{PROJECT}/auto_pm/new_file.py", f"{PROJECT}/auto_pm"]
    assert len(notes) == 3 and "auto_pm/x.py → proj/app/auto_pm/x.py" in notes[0]


def test_repository_root_paths_stay_as_they_are_from_any_folder(tmp_path: Path) -> None:
    root, project = _tree(tmp_path)
    given = [f"{PROJECT}/auto_pm/x.py", "reviews/tools/new.py"]

    assert claim_cli.normalise_paths(root, root, given) == (given, [])
    assert claim_cli.normalise_paths(root, project, given) == (given, [])


def test_a_top_level_folder_that_exists_at_the_root_is_not_second_guessed(tmp_path: Path) -> None:
    root, project = _tree(tmp_path)
    (project / "reviews").mkdir()

    assert claim_cli.normalise_paths(root, project, ["reviews/a.py"]) == (["reviews/a.py"], [])


def test_an_absolute_path_inside_the_repository_becomes_relative_and_one_outside_is_refused(tmp_path: Path) -> None:
    root, project = _tree(tmp_path)

    paths, notes = claim_cli.normalise_paths(root, project, [str(project / "auto_pm" / "x.py")])
    assert paths == [f"{PROJECT}/auto_pm/x.py"] and notes
    with pytest.raises(click.UsageError, match="仓库.*之外"):
        claim_cli.normalise_paths(root, project, [str(tmp_path / "elsewhere.py")])


class _Offline:
    def __init__(self, root: object) -> None:
        pass

    def all_claims(self, *, fetch: bool = True) -> list[object]:
        if fetch:
            raise ClaimError("offline")
        return []


def _invoke(monkeypatch: pytest.MonkeyPatch, *args: str) -> tuple[int, str]:
    monkeypatch.setattr(claim_cli, "ClaimService", _Offline)
    runner = CliRunner()
    result = runner.invoke(claim_cli.claim_group, list(args), obj=type("Ctx", (), {"control_root": "/x", "workspace_root": ""})())
    return result.exit_code, result.output


def test_claim_list_offline_failure_points_at_no_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    code, output = _invoke(monkeypatch, "list")
    assert code == 2 and "--no-fetch" in output and "错误 offline" in output


def test_claim_list_no_fetch_says_the_view_may_be_stale_and_keeps_json_clean(monkeypatch: pytest.MonkeyPatch) -> None:
    code, output = _invoke(monkeypatch, "list", "--no-fetch")
    assert code == 0 and "离线视图" in output

    monkeypatch.setattr(claim_cli, "ClaimService", _Offline)
    result = CliRunner().invoke(
        claim_cli.claim_group, ["list", "--no-fetch", "--json"], obj=type("Ctx", (), {"control_root": "/x", "workspace_root": ""})()
    )
    assert json.loads(result.stdout) == []
