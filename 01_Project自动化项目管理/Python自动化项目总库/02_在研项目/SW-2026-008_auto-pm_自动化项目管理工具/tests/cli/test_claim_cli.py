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


class _Recording:
    received: list[tuple[str, ...]] = []

    def __init__(self, root: object) -> None:
        pass

    def open(self, card: str, *, paths: tuple[str, ...], goal: str, owner: str) -> object:
        _Recording.received.append(tuple(paths))
        return type("Claimed", (), {"label": lambda self: f"卡 {card}", "paths": tuple(paths)})()


def test_claim_open_hands_the_service_repository_root_paths_and_says_so_on_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, project = _tree(tmp_path)
    monkeypatch.chdir(project)
    monkeypatch.setattr(claim_cli, "ClaimService", _Recording)
    _Recording.received = []

    result = CliRunner().invoke(
        claim_cli.claim_group,
        ["open", "card-1", "--paths", "auto_pm/x.py", "--paths", "reviews/tools/a.py", "--goal", "g"],
        obj=type("Ctx", (), {"control_root": str(root), "workspace_root": ""})(),
    )

    assert result.exit_code == 0, result.output
    assert _Recording.received == [(f"{PROJECT}/auto_pm/x.py", "reviews/tools/a.py")]
    assert "路径已按仓库根补全：auto_pm/x.py → proj/app/auto_pm/x.py" in result.stderr
    assert "reviews/tools/a.py →" not in result.stderr, "a path that already is a repository-root path is not mentioned"


def test_add_paths_command_lifts_paths_to_the_root_and_reports_the_new_list(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from auto_pm.application.core.claim_service import Claim

    root, project = _tree(tmp_path)
    seen: dict[str, object] = {}

    class _Service:
        def add_paths(self, card: str, *, owner: str, paths: list[str]) -> Claim:
            seen.update(card=card, owner=owner, paths=paths)
            return Claim(card, owner, "m", ("a", *paths), "g", "t", "c")

    monkeypatch.setattr(claim_cli, "_service", lambda ctx: _Service())
    monkeypatch.setattr(claim_cli, "_root", lambda ctx: str(root))
    monkeypatch.chdir(project)

    result = CliRunner().invoke(claim_cli.claim_group, ["add-paths", "340", "--paths", "auto_pm/x.py", "--as", "claude"])

    assert result.exit_code == 0, result.output
    assert seen == {"card": "340", "owner": "claude", "paths": [f"{PROJECT}/auto_pm/x.py"]}
    assert "已追加路径" in result.output and "领卡时间和到期时间不变" in result.output


def test_add_paths_command_exits_one_with_the_refusal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root, _ = _tree(tmp_path)

    class _Service:
        def add_paths(self, card: str, *, owner: str, paths: list[str]) -> None:
            raise ClaimError("要追加的路径和别人的占位重叠")

    monkeypatch.setattr(claim_cli, "_service", lambda ctx: _Service())
    monkeypatch.setattr(claim_cli, "_root", lambda ctx: str(root))
    monkeypatch.chdir(root)

    result = CliRunner().invoke(claim_cli.claim_group, ["add-paths", "340", "--paths", "reviews/a.py", "--as", "claude"])

    assert result.exit_code == 1 and "拒绝 要追加的路径和别人的占位重叠" in (result.output + (result.stderr if result.stderr_bytes else ""))


def test_d34_number_command_reports_the_number_and_how_to_add_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from auto_pm.application.core.claim_service import Claim

    root, _ = _tree(tmp_path)
    seen: dict[str, object] = {}

    class _Service:
        def reserve_number(self, *, goal: str, owner: str) -> Claim:
            seen.update(goal=goal, owner=owner)
            return Claim("245", owner, "m", (), goal, "t", "c")

    monkeypatch.setattr(claim_cli, "_service", lambda ctx: _Service())
    monkeypatch.setattr(claim_cli, "_root", lambda ctx: str(root))

    result = CliRunner().invoke(claim_cli.claim_group, ["number", "--goal", "落卡", "--as", "claude"])

    assert result.exit_code == 0, result.output
    assert seen == {"goal": "落卡", "owner": "claude"}
    assert "已领号 245" in result.output
    assert "02_规划/245_<名称>_PM.md" in result.output
    assert "claim add-paths 245 --paths" in result.output


def test_d34_number_command_exits_one_with_the_refusal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root, _ = _tree(tmp_path)

    class _Service:
        def reserve_number(self, *, goal: str, owner: str) -> None:
            raise ClaimError("推占位分支失败，未领到卡")

    monkeypatch.setattr(claim_cli, "_service", lambda ctx: _Service())
    monkeypatch.setattr(claim_cli, "_root", lambda ctx: str(root))

    result = CliRunner().invoke(claim_cli.claim_group, ["number", "--goal", "落卡", "--as", "claude"])

    assert result.exit_code == 1 and "拒绝 推占位分支失败" in (result.output + (result.stderr if result.stderr_bytes else ""))


def test_d152_number_command_requires_a_goal(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root, _ = _tree(tmp_path)
    monkeypatch.setattr(claim_cli, "_root", lambda ctx: str(root))

    result = CliRunner().invoke(claim_cli.claim_group, ["number", "--as", "claude"])

    assert result.exit_code == 2 and "--goal" in result.output


def test_d152_list_shows_a_number_only_claim_as_such(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from auto_pm.application.core.claim_service import Claim

    root, _ = _tree(tmp_path)

    class _Service:
        def all_claims(self, *, fetch: bool = True) -> list[Claim]:
            return [Claim("245", "claude", "m", (), "落卡", "2026-11-08T00:00:00+00:00", "c")]

    monkeypatch.setattr(claim_cli, "_service", lambda ctx: _Service())
    monkeypatch.setattr(claim_cli, "_root", lambda ctx: str(root))

    result = CliRunner().invoke(claim_cli.claim_group, ["list"])

    assert result.exit_code == 0, result.output
    assert "路径：（只占号，未补路径）" in result.output
