"""Claim CLI helpers (D-115 repository-root paths, offline hints for ``claim list``)."""

from __future__ import annotations

import json
from pathlib import Path

import click
import pytest
from click.testing import CliRunner, Result

from auto_pm.application.core.claim_service import ClaimError, ClaimService
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
            # TD-SW008-611 起命令看 written：服务真推了新提交才说“已追加”
            return Claim(card, owner, "m", ("a", *paths), "g", "t", "c", written=True)

    monkeypatch.setattr(claim_cli, "_service", lambda ctx: _Service())
    monkeypatch.setattr(claim_cli, "_root", lambda ctx: str(root))
    monkeypatch.chdir(project)

    result = CliRunner().invoke(claim_cli.claim_group, ["add-paths", "340", "--paths", "auto_pm/x.py", "--as", "claude"])

    assert result.exit_code == 0, result.output
    assert seen == {"card": "340", "owner": "claude", "paths": [f"{PROJECT}/auto_pm/x.py"]}
    assert "已追加路径" in result.output and "领卡时间和到期时间不变" in result.output


def test_add_paths_command_says_nothing_was_written_when_the_paths_were_already_held(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """TD-SW008-611（D-346）：要加的路径都已在占位里，服务原样返回、什么都没推；命令不说“已追加”。"""
    from auto_pm.application.core.claim_service import Claim

    root, project = _tree(tmp_path)

    class _Service:
        def add_paths(self, card: str, *, owner: str, paths: list[str]) -> Claim:
            return Claim(card, owner, "m", tuple(paths), "g", "t", "c")  # written 默认 False：没推

    monkeypatch.setattr(claim_cli, "_service", lambda ctx: _Service())
    monkeypatch.setattr(claim_cli, "_root", lambda ctx: str(root))
    monkeypatch.chdir(project)

    result = CliRunner().invoke(claim_cli.claim_group, ["add-paths", "340", "--paths", "auto_pm/x.py", "--as", "claude"])

    assert result.exit_code == 0, result.output
    assert "已追加路径" not in result.output
    assert "这次什么都没写" in result.output


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


def _write_outcome(monkeypatch: pytest.MonkeyPatch, *args: str, released: bool = True, reclaimed: bool = True) -> str:
    from auto_pm.application.core.claim_service import Claim

    class _Service:
        def __init__(self, root: object) -> None:
            pass

        def release(self, card: str, *, owner: str) -> bool:
            return released

        def reclaim(self, card: str, *, by: str, reason: str, approval_ref: str) -> Claim:
            return Claim(card=card, owner="o", machine="m", paths=(), goal="", claimed_at="", commit="c", status="reclaimed", written=reclaimed)

    monkeypatch.setattr(claim_cli, "ClaimService", _Service)
    result = CliRunner().invoke(claim_cli.claim_group, list(args), obj=type("Ctx", (), {"control_root": "/x", "workspace_root": ""})())
    assert result.exit_code == 0, result.output
    return result.output


def test_td397_release_says_released_only_when_it_wrote_and_says_nothing_was_written_otherwise(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "已放下卡 c1（远程已记为 released）" in _write_outcome(monkeypatch, "release", "c1", "--as", "claude", released=True)
    said = _write_outcome(monkeypatch, "release", "c1", "--as", "claude", released=False)
    assert "这次什么都没写" in said and "已放下卡" not in said


def test_td485_reclaim_says_reclaimed_only_when_it_wrote(monkeypatch: pytest.MonkeyPatch) -> None:
    args = ("reclaim", "c2", "--reason", "r", "--approval-evidence-ref", "user-confirmation:cmsg_01", "--as", "claude")
    assert "卡 c2 的占位已收回（远程已记为 reclaimed）" in _write_outcome(monkeypatch, *args, reclaimed=True)
    said = _write_outcome(monkeypatch, *args, reclaimed=False)
    assert "早就是 reclaimed，这次什么都没写" in said and "已收回" not in said


# ── claim note / claim log (hand-over record) ─────────────────────────────


def _note_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A bare origin with one commit on main and one clone that holds claim CARD-T-001 on ``p``."""

    from tests.git_support import git_do

    identity = ("user.email=t@example.invalid", "user.name=tester")
    origin = tmp_path / "origin.git"
    clone = tmp_path / "clone"
    git_do(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin), config=identity)
    git_do(tmp_path, "clone", "-q", str(origin), str(clone), config=identity)
    (clone / "p").mkdir()
    (clone / "p" / "draft.md").write_text("draft\n", encoding="utf-8")
    git_do(clone, "add", ".", config=identity)
    git_do(clone, "commit", "-q", "-m", "seed", config=identity)
    git_do(clone, "push", "-q", "origin", "HEAD:main", config=identity)
    ClaimService(clone, machine="m").open("CARD-T-001", paths=["p"], goal="g", owner="claude", machine="m")
    return origin, clone


def _note_cli(clone: Path, *args: str) -> Result:
    return CliRunner().invoke(
        claim_cli.claim_group, list(args), obj=type("Ctx", (), {"control_root": str(clone), "workspace_root": ""})()
    )


def test_note_then_log_tells_who_is_next_what_to_do_and_what_to_read(tmp_path: Path) -> None:
    _, clone = _note_repo(tmp_path)

    first = _note_cli(
        clone, "note", "CARD-T-001", "--kind", "draft", "--to", "audit", "--next", "预核草稿", "--as", "claude",
        "--ref", "p/draft.md", "--read-first", "p/draft.md", "--ref-outside", "plans/x.md#" + "a" * 64,
    )
    assert first.exit_code == 0, first.output
    assert "已记第 1 笔（起草" in first.output and "下一棒：audit，预核草稿" in first.output
    second = _note_cli(
        clone, "note", "CARD-T-001", "--kind", "ask-user", "--to", "user", "--next", "等用户在本机说话", "--as", "audit",
        "--ask-user", "批准 CHG-SCPT-2026-900", "--chg", "CHG-SCPT-2026-900",
    )
    assert second.exit_code == 0, second.output

    shown = _note_cli(clone, "log", "CARD-T-001")
    assert shown.exit_code == 0, shown.output
    lines = shown.output.strip().splitlines()
    assert lines[-3].startswith("最后一笔：请用户，audit → user，")
    assert lines[-2] == "下一棒：user，等用户在本机说话"
    assert lines[-1] == "先读：无"
    assert "仓库外引用 plans/x.md" in shown.output and "（没核）" in shown.output
    assert "请用户说（只是提示，不是批准）：批准 CHG-SCPT-2026-900" in shown.output

    as_json = _note_cli(clone, "log", "CARD-T-001", "--json")
    assert [item["kind"] for item in json.loads(as_json.output)] == ["draft", "ask-user"]


def test_note_refusal_exits_one_says_why_and_pushes_nothing(tmp_path: Path) -> None:
    from tests.git_support import git_out

    origin, clone = _note_repo(tmp_path)
    before = git_out(origin, "for-each-ref")

    wrong_state = _note_cli(clone, "note", "CARD-T-001", "--kind", "draft", "--to", "audit", "--next", "用户已批准", "--as", "claude")
    wrong_hash = _note_cli(clone, "note", "CARD-T-001", "--kind", "draft", "--to", "a", "--next", "x", "--ref", "p/none.md", "--as", "c")

    assert wrong_state.exit_code == 1 and "状态词“已批准”" in wrong_state.output and "状态去状态单里看" in wrong_state.output
    assert wrong_hash.exit_code == 1 and "里不存在" in wrong_hash.output
    assert git_out(origin, "for-each-ref") == before


def test_note_offline_exits_two_and_prints_the_note_to_record_again(tmp_path: Path) -> None:
    from tests.git_support import git_do

    _, clone = _note_repo(tmp_path)
    git_do(clone, "remote", "set-url", "origin", str(tmp_path / "gone.git"))

    result = _note_cli(clone, "note", "CARD-T-001", "--kind", "draft", "--to", "audit", "--next", "预核", "--as", "claude")

    assert result.exit_code == 2
    assert "没有记上，也没有存在本机" in result.output
    assert '"next_step": "预核"' in result.output and '"card": "CARD-T-001"' in result.output


def test_log_empty_record_missing_claim_and_offline_view(tmp_path: Path) -> None:
    _, clone = _note_repo(tmp_path)

    empty = _note_cli(clone, "log", "CARD-T-001")
    missing = _note_cli(clone, "log", "CARD-T-404")
    offline = _note_cli(clone, "log", "CARD-T-001", "--no-fetch")

    assert empty.exit_code == 0 and "这张卡还没有交接记录。" in empty.output
    assert missing.exit_code == 1 and "没有这张卡的占位" in missing.output
    assert offline.exit_code == 0 and "离线视图" in offline.output


def test_note_usage_error_exits_two(tmp_path: Path) -> None:
    _, clone = _note_repo(tmp_path)

    result = _note_cli(clone, "note", "CARD-T-001", "--kind", "draft", "--to", "audit")

    assert result.exit_code == 2 and "--next" in result.output
