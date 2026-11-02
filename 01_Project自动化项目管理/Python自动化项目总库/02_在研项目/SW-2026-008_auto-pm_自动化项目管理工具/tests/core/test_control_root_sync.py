"""A control root that does not match ``origin/main`` is reported at ``pm inbox add``, ``pm approve`` and ``pm orient`` -- not only
when ``run start`` finally refuses (user 2026-11-02: "入箱或批准时就检查并提示，这个赶紧修").

Real Git repositories: a bare ``origin``, a control-root clone, and a second clone that moves ``origin/main`` forward.  The three
situations the user named are pinned: 200 commits behind, one duplicate commit ahead, and uncommitted files inside the scope.
The service must also stay read-only and must not fail offline.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from auto_pm.application.core.control_root_sync import ControlRootSyncService
from auto_pm.ui.cli import pm as pm_cli
from auto_pm.ui.cli import pm_closure as pm_closure_cli
from tests.git_support import git_do, git_out

SCOPE = ("proj",)
IDENTITY = ("user.email=t@example.invalid", "user.name=tester")


def _git(root: Path, *args: str) -> None:
    git_do(root, *args, config=IDENTITY)


def _out(root: Path, *args: str) -> str:
    return git_out(root, *args, config=IDENTITY)


def _commit_file(root: Path, relative: str, text: str, message: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    _git(root, "add", relative)
    _git(root, "commit", "-q", "-m", message)


class World:
    """origin (bare) + the control root + ``upstream``, a second clone that plays everybody else pushing to main."""

    def __init__(self, base: Path) -> None:
        self.origin = base / "origin.git"
        self.control = base / "control"
        self.upstream = base / "upstream"
        _git(base, "init", "-q", "--bare", "-b", "main", str(self.origin))
        _git(base, "clone", "-q", str(self.origin), str(self.control))
        _commit_file(self.control, "proj/a.txt", "v1\n", "seed")
        _commit_file(self.control, "other/b.txt", "b1\n", "seed other")
        _git(self.control, "push", "-q", "origin", "HEAD:main")
        _git(self.control, "fetch", "-q", "origin")
        _git(base, "clone", "-q", str(self.origin), str(self.upstream))

    def service(self) -> ControlRootSyncService:
        return ControlRootSyncService(self.control)

    def push_upstream(self) -> None:
        _git(self.upstream, "push", "-q", "origin", "HEAD:main")
        _git(self.control, "fetch", "-q", "origin")


@pytest.fixture
def world(tmp_path: Path) -> World:
    return World(tmp_path)


def test_a_control_root_that_matches_main_says_nothing(world: World) -> None:
    report = world.service().check(SCOPE)
    assert report.verified and not report.needs_attention and report.lines() == ()


def test_two_hundred_commits_behind_is_reported_with_what_to_do_and_blocks_run_start(world: World) -> None:
    for number in range(199):
        _git(world.upstream, "commit", "-q", "--allow-empty", "-m", f"filler {number}")
    _commit_file(world.upstream, "proj/a.txt", "v2\n", "the change that makes run start refuse")
    world.push_upstream()

    report = world.service().check(SCOPE)

    assert (report.behind, report.ahead) == (200, 0)
    assert report.drift_in_scope == ("proj/a.txt",)
    assert report.blocks_run_start
    text = "\n".join(report.lines())
    assert "落后 origin/main 200 个提交" in text and "git merge --ff-only origin/main" in text
    assert "run start" in text and "一定会被拒" in text


def test_being_behind_in_files_outside_the_scope_is_reported_but_does_not_block(world: World) -> None:
    _commit_file(world.upstream, "other/b.txt", "b2\n", "elsewhere")
    world.push_upstream()
    report = world.service().check(SCOPE)
    assert report.behind == 1 and not report.blocks_run_start


def test_one_duplicate_commit_ahead_is_named_as_a_duplicate_not_as_new_work(world: World) -> None:
    _commit_file(world.upstream, "proj/a.txt", "v2\n", "the real change")
    world.push_upstream()
    upstream_commit = _out(world.upstream, "rev-parse", "HEAD")
    _git(world.control, "cherry-pick", "-x", upstream_commit)  # the same change, committed again locally (-x: another hash)
    _git(world.upstream, "commit", "-q", "--allow-empty", "-m", "later")
    world.push_upstream()

    report = world.service().check(SCOPE)

    assert report.ahead == 1 and len(report.duplicate_ahead) == 1 and report.unique_ahead == ()
    assert report.behind == 2
    text = "\n".join(report.lines())
    assert "重复" in text and "需要用户决定" in text and "不要自行 reset" in text
    assert "这些重复提交让控制根无法快进" in text  # the reason the user is asked, not only the instruction


def test_a_local_commit_main_does_not_have_is_reported_as_unique(world: World) -> None:
    _commit_file(world.control, "proj/a.txt", "local\n", "only here")
    report = world.service().check(SCOPE)
    assert report.ahead == 1 and report.duplicate_ahead == () and len(report.unique_ahead) == 1
    assert "origin/main 里没有的本地提交" in "\n".join(report.lines())


def test_uncommitted_files_inside_the_scope_are_listed_and_block_run_start(world: World) -> None:
    (world.control / "proj" / "a.txt").write_text("edited by hand\n", encoding="utf-8")
    (world.control / "proj" / "new.txt").write_text("not tracked\n", encoding="utf-8")
    (world.control / "other" / "b.txt").write_text("outside the scope\n", encoding="utf-8")

    report = world.service().check(SCOPE)

    assert report.dirty_in_scope == ("proj/a.txt", "proj/new.txt")  # other/b.txt is not in the scope
    assert set(report.drift_in_scope) == {"proj/a.txt", "proj/new.txt"}
    assert report.blocks_run_start
    assert "未提交的文件" in "\n".join(report.lines())


def test_a_path_with_chinese_characters_is_listed_by_its_real_name(world: World) -> None:
    (world.control / "proj" / "变更单.md").write_text("中文\n", encoding="utf-8")
    assert world.service().check(SCOPE).dirty_in_scope == ("proj/变更单.md",)


def test_with_no_scope_only_the_commit_difference_is_judged(world: World) -> None:
    (world.control / "proj" / "a.txt").write_text("edited\n", encoding="utf-8")
    report = world.service().check(())
    assert report.dirty_in_scope == () and not report.blocks_run_start


# --- a Run already started: the same early word before the long verification ------------------------------------------------------------


def test_a_control_root_file_changed_since_the_run_started_is_named_before_verify(world: World) -> None:
    start = _out(world.control, "rev-parse", "HEAD")
    assert world.service().run_drift_lines(SCOPE, start) == ()
    _commit_file(world.control, "proj/a.txt", "changed in the control root\n", "someone commits in the control root")
    (world.control / "proj" / "loose.txt").write_text("x\n", encoding="utf-8")
    lines = world.service().run_drift_lines(SCOPE, start)
    assert len(lines) == 1 and "proj/a.txt" in lines[0] and "proj/loose.txt" in lines[0] and "pm close" in lines[0]


def test_an_unknown_start_commit_stays_silent_for_verify(world: World) -> None:
    assert world.service().run_drift_lines(SCOPE, "0" * 40) == ()


# --- offline and no origin: "not verified", never an error ---------------------------------------------------------------------------------


def test_a_repository_without_origin_is_not_verified_and_stays_quiet(tmp_path: Path) -> None:
    """Nothing to compare with: not verified, no error, and no hint line (it would only be noise on every command)."""

    repo = tmp_path / "alone"
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    _commit_file(repo, "proj/a.txt", "v1\n", "seed")
    report = ControlRootSyncService(repo).check(SCOPE)
    assert not report.verified and report.no_origin and not report.blocks_run_start
    assert not report.needs_attention and report.lines() == ()


def test_a_remote_that_was_never_fetched_is_not_verified(tmp_path: Path) -> None:
    origin = tmp_path / "origin.git"
    repo = tmp_path / "repo"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "init", "-q", "-b", "main", str(repo))
    _commit_file(repo, "proj/a.txt", "v1\n", "seed")
    _git(repo, "remote", "add", "origin", str(origin))  # configured, never fetched: refs/remotes/origin/main does not exist
    report = ControlRootSyncService(repo).check(SCOPE)
    assert not report.verified and not report.no_origin
    assert "未核实" in report.lines()[0] and "离线" in report.lines()[0]


def test_a_folder_that_is_not_a_repository_is_not_verified_and_does_not_fail(tmp_path: Path) -> None:
    assert not ControlRootSyncService(tmp_path).check(SCOPE).verified


def test_the_check_changes_nothing_in_the_control_root(world: World) -> None:
    _commit_file(world.upstream, "proj/a.txt", "v2\n", "moves main")
    world.push_upstream()
    (world.control / "proj" / "new.txt").write_text("x\n", encoding="utf-8")
    before = (_out(world.control, "rev-parse", "HEAD"), _out(world.control, "status", "--porcelain"), _out(world.control, "rev-parse", "origin/main"))
    world.service().check(SCOPE)
    after = (_out(world.control, "rev-parse", "HEAD"), _out(world.control, "status", "--porcelain"), _out(world.control, "rev-parse", "origin/main"))
    assert before == after
    assert not (world.control / ".git" / "FETCH_HEAD").read_text(encoding="utf-8").count("moves main")  # nothing was fetched by the check


def test_the_project_scope_is_the_projects_folder(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    folder = repo / "area" / "SW-2026-777_demo"
    folder.mkdir(parents=True)
    (folder / ".copier-answers.yml").write_text("project_id: SW-2026-777\nproject_name: demo\nstack: python\n", encoding="utf-8")
    service = ControlRootSyncService(repo)
    assert service.project_scope("SW-2026-777") == ("area/SW-2026-777_demo",)
    assert service.project_scope("SW-2026-000") == () and service.project_scope("") == ()


# --- the three commands ask --------------------------------------------------------------------------------------------------------------


def _ctx(control_root: Path) -> Any:
    root = SimpleNamespace(obj=SimpleNamespace(control_root=control_root, workspace_root=str(control_root)))
    return SimpleNamespace(find_root=lambda: root)


def test_the_notice_goes_to_stderr_in_plain_words(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    _commit_file(world.upstream, "proj/a.txt", "v2\n", "moves main")
    world.push_upstream()
    pm_cli._control_root_sync_notice(_ctx(world.control), scope_paths=SCOPE)
    captured = capsys.readouterr()
    assert captured.out == "" and "[控制根同步]" in captured.err and "落后 origin/main 1 个提交" in captured.err


def test_the_notice_is_silent_when_everything_matches(world: World, capsys: pytest.CaptureFixture[str]) -> None:
    pm_cli._control_root_sync_notice(_ctx(world.control), scope_paths=SCOPE)
    assert capsys.readouterr().err == ""


def test_the_notice_never_stops_the_command(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def _boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(pm_cli, "ControlRootSyncService", _boom)
    pm_cli._control_root_sync_notice(_ctx(tmp_path), project_id="SW-2026-777")
    assert "未能核对" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("module", "command", "callee"),
    [
        (pm_cli, "inbox_add", "_control_root_sync_notice"),
        (pm_cli, "approve_pm", "_control_root_sync_notice"),
        (pm_cli, "orient_pm", "_control_root_sync_notice"),
        (pm_cli, "resume_pm", "_control_root_sync_notice"),
        (pm_closure_cli, "verify_pm", "_echo_run_drift_hint"),
    ],
)
def test_each_command_asks_early(module: Any, command: str, callee: str) -> None:
    """Structure: a command that stops asking would bring back the 'found out at run start' failure."""

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == command)
    called = {
        node.func.id for node in ast.walk(function) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert callee in called


def test_verify_hint_survives_a_run_without_owned_paths(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    """A hint that cannot be computed is reported as unverified; verification itself must go on."""
    import types

    ctx = types.SimpleNamespace(control_root=tmp_path / "missing")
    pm_closure_cli._echo_run_drift_hint(ctx, types.SimpleNamespace())  # type: ignore[arg-type]
    # Nothing raised; stderr may be empty (no origin) or carry an "unverified" line.
    assert "Traceback" not in capsys.readouterr().err


def test_a_staged_rename_in_a_folder_whose_third_character_is_a_space_keeps_both_real_names(world: World) -> None:
    """Audit 539: the rename's old path has no status prefix; "项目 甲/…" has a space as its third character."""
    _commit_file(world.control, "项目 甲/a.txt", "x\n", "folder with a space")
    _git(world.control, "push", "-q", "origin", "HEAD:main")
    _git(world.control, "fetch", "-q", "origin")
    _git(world.control, "mv", "项目 甲/a.txt", "项目 甲/b.txt")

    report = world.service().check(("项目 甲",))

    assert report.dirty_in_scope == ("项目 甲/a.txt", "项目 甲/b.txt")
    assert all(not name.startswith("甲/") for name in report.dirty_in_scope)


def test_local_commits_whose_content_is_already_in_main_are_not_offered_for_another_pr(world: World) -> None:
    """Audit 539: main squashed two local commits into one (different patch); the scope already matches main."""
    _commit_file(world.control, "proj/a.txt", "v1.5\n", "local step 1")
    _commit_file(world.control, "proj/a.txt", "v2\n", "local step 2")
    _commit_file(world.upstream, "proj/a.txt", "v2\n", "squashed into main")
    world.push_upstream()

    report = world.service().check(SCOPE)

    assert report.ahead == 2 and len(report.unique_ahead) == 2 and not report.drift_in_scope
    assert report.maybe_squashed
    text = "\n".join(report.lines())
    assert "内容可能已被 squash 合并进 main" in text and "请用户确认后再对齐 main" in text
    assert "先推送成 PR" not in text


def test_an_empty_local_commit_says_nothing_about_squashing(world: World) -> None:
    _git(world.control, "commit", "-q", "--allow-empty", "-m", "empty")
    report = world.service().check(SCOPE)
    assert len(report.unique_ahead) == 1 and not report.maybe_squashed
    assert "先推送成 PR" in "\n".join(report.lines())


def test_a_scope_that_names_no_file_cannot_make_a_squash_guess(world: World) -> None:
    """Audit 543 follow-up: an empty or mistyped scope matches main trivially; it must not turn into a squash hint."""
    _commit_file(world.control, "proj/a.txt", "v1.5\n", "local step 1")
    _commit_file(world.control, "proj/a.txt", "v2\n", "local step 2")
    _commit_file(world.upstream, "proj/a.txt", "v2\n", "squashed into main")
    world.push_upstream()

    named = world.service().check(SCOPE)
    assert named.maybe_squashed  # control: with a real scope the very same history is called a probable squash

    for typo in (("no-such-folder/",), ("proj/typo.txt",)):
        report = world.service().check(typo)
        assert not report.maybe_squashed and not report.drift_in_scope, typo


def test_a_local_commit_outside_the_scope_does_not_make_the_scope_look_squashed(world: World) -> None:
    _commit_file(world.control, "elsewhere/b.txt", "x\n", "work in another folder")
    report = world.service().check(SCOPE)
    assert report.unique_ahead and not report.maybe_squashed


def test_a_local_commit_that_differs_from_main_in_the_scope_is_still_offered_as_work(world: World) -> None:
    _commit_file(world.control, "proj/a.txt", "only local\n", "real local work")
    report = world.service().check(SCOPE)
    assert not report.maybe_squashed and "先推送成 PR" in "\n".join(report.lines())


def test_a_local_merge_commit_ahead_of_main_is_not_silent(world: World) -> None:
    _git(world.control, "switch", "-q", "-c", "side")
    _commit_file(world.control, "other/side.txt", "s\n", "side work")
    _git(world.control, "switch", "-q", "main")
    _git(world.control, "merge", "-q", "--no-ff", "-m", "merge side", "side")

    report = world.service().check(SCOPE)

    assert report.ahead == 2 and len(report.unique_ahead) == 1 and report.other_ahead == 1
    assert "本地合并提交" in "\n".join(report.lines())


def test_the_notice_uses_the_cards_own_scope_paths_when_given(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Audit 539 (surviving mutant): approval must judge the card's paths, the project folder only when none are given."""
    asked: list[tuple[str, ...]] = []

    class Recorder:
        def __init__(self, _root: object) -> None:
            pass

        def project_scope(self, _project_id: str) -> tuple[str, ...]:
            return ("the-project-folder",)

        def check(self, scope: tuple[str, ...]) -> Any:
            asked.append(tuple(scope))
            return SimpleNamespace(lines=lambda: ())

    monkeypatch.setattr(pm_cli, "ControlRootSyncService", Recorder)
    pm_cli._control_root_sync_notice(_ctx(tmp_path), project_id="SW-2026-777", scope_paths=("a/x.py", "a/y.py"))
    pm_cli._control_root_sync_notice(_ctx(tmp_path), project_id="SW-2026-777")

    assert asked == [("a/x.py", "a/y.py"), ("the-project-folder",)]


def test_approve_hands_the_cards_scope_paths_to_the_notice() -> None:
    """Structure: the call in ``approve_pm`` names ``scope_paths`` (dropping it falls back to the whole project folder)."""
    tree = ast.parse(Path(pm_cli.__file__).read_text(encoding="utf-8"))
    function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "approve_pm")
    calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_control_root_sync_notice"
    ]
    assert calls and all("scope_paths" in {keyword.arg for keyword in call.keywords} for call in calls)


def test_an_empty_scope_tuple_cannot_make_a_squash_guess(world: World) -> None:
    """#478 deferred test: ``()`` (no scope at all) matches main trivially, so it must never read as "probably squashed"."""
    _commit_file(world.control, "proj/a.txt", "v1.5\n", "local step 1")
    _commit_file(world.control, "proj/a.txt", "v2\n", "local step 2")
    _commit_file(world.upstream, "proj/a.txt", "v2\n", "squashed into main")
    world.push_upstream()

    report = world.service().check(())

    assert len(report.unique_ahead) == 2
    assert not report.maybe_squashed and not report.drift_in_scope


def _rename(root: Path, old: str, new: str, message: str) -> None:
    (root / new).parent.mkdir(parents=True, exist_ok=True)
    _git(root, "mv", old, new)
    _git(root, "commit", "-q", "-m", message)


def test_a_local_rename_inside_the_scope_counts_as_changing_the_scope(world: World) -> None:
    """#478 deferred test: a rename is a delete plus an add for ``diff-tree``; both paths are in scope, the squash hint stays."""
    _commit_file(world.control, "proj/a.txt", "v2\n", "local edit")
    _rename(world.control, "proj/a.txt", "proj/renamed.txt", "local rename")
    (world.upstream / "proj/a.txt").write_text("v2\n", encoding="utf-8")
    _git(world.upstream, "add", "proj/a.txt")
    _rename(world.upstream, "proj/a.txt", "proj/renamed.txt", "edit and rename squashed into main")
    world.push_upstream()

    report = world.service().check(SCOPE)

    assert len(report.unique_ahead) == 2 and not report.drift_in_scope
    assert report.maybe_squashed


def test_a_local_rename_that_moves_a_file_out_of_the_scope_still_counts_as_scope_work(world: World) -> None:
    """The deleted old path is inside the scope even though the new path is not; the commit must not be treated as unrelated."""
    _rename(world.control, "proj/a.txt", "elsewhere/a.txt", "move out of the project")

    report = world.service().check(SCOPE)

    assert report.unique_ahead and report.drift_in_scope == ("proj/a.txt",)
    assert not report.maybe_squashed  # main still has the file, so this is real work, not a squash
    assert "先推送成 PR" in "\n".join(report.lines())
