"""TD-193：``project delete --confirm`` 的护栏——只听用户本人、开着任务或有未提交改动时拒绝、目录搬进回收区。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from click.testing import CliRunner

from auto_pm.application.core import project_delete_guard as guard
from auto_pm.application.core.approval_proof_service import ApprovalProofService, make_key
from auto_pm.application.core.lease_handover_service import AGENT_MARKERS
from auto_pm.ui.cli.__main__ import cli
from tests.core.test_mission_park_store import PROJECT, Scene
from tests.git_support import run_git

USER_WORDS = "user-confirmation:cmsg_user_says_delete_ok"
PIN = "relay-K1-on"


def git(root: Path, *args: str) -> str:
    return run_git(root, *args, config=["user.email=t@example.invalid", "user.name=t"]).stdout


def project_command_module() -> Any:
    """``cli`` 实际调用的那份 project 命令模块（``auto_pm.cli`` 是 ``auto_pm.ui.cli`` 的别名，各有一份模块对象）。"""
    return sys.modules[cli.commands["project"].commands["delete"].callback.__module__]  # type: ignore[attr-defined]


class World:
    """一个工作区：项目目录 ``proj`` 已提交；没有开着的任务。"""

    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project_cli = project_command_module()

        root.mkdir(parents=True)
        self.root = root
        self.project = root / "proj"
        (self.project / "src").mkdir(parents=True)
        (self.project / "src" / "a.py").write_text("print('keep me')\n", encoding="utf-8")
        git(root, "init", "-q", "-b", "main")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "base")
        stub = SimpleNamespace(path=str(self.project), name="Demo")
        monkeypatch.setattr(
            project_cli,
            "ProjectService",
            lambda _root: SimpleNamespace(get_project=lambda pid: stub if pid == PROJECT else None),
        )
        self.audit: list[dict[str, Any]] = []
        monkeypatch.setattr(
            "auto_pm.logging.audit.audit_log",
            lambda action, **details: self.audit.append({"action": action, **details}),
        )

    def run(self, *args: str) -> Any:
        return CliRunner().invoke(
            cli, ["-w", str(self.root), "project", "delete", PROJECT, *args], catch_exceptions=False
        )

    def recycled(self) -> list[Path]:
        base = self.root / ".auto-pm" / "recycle" / PROJECT
        return sorted(base.iterdir()) if base.is_dir() else []


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    for name in AGENT_MARKERS:
        monkeypatch.delenv(name, raising=False)
    return World(tmp_path / "ws", monkeypatch)


def test_d01_without_confirm_nothing_is_touched(world: World) -> None:
    result = world.run()
    assert result.exit_code == 1
    assert "请使用 --confirm 确认删除" in result.output
    assert world.project.is_dir() and world.recycled() == []


@pytest.mark.parametrize("marker", ["AUTO_PM_AGENT", "CLAUDECODE", "CODEX_THREAD_ID"])
def test_d02_an_agent_environment_is_refused_even_with_the_users_words(
    world: World, monkeypatch: pytest.MonkeyPatch, marker: str
) -> None:
    monkeypatch.setenv(marker, "1")
    result = world.run("--confirm", "--approval-evidence-ref", USER_WORDS)
    assert result.exit_code == 1 and "只听用户本人" in result.output
    assert (
        (world.project / "src" / "a.py").is_file() and world.recycled() == [] and world.audit == []
    )


@pytest.mark.parametrize(
    "words", [None, "yes please", "user-confirmation:x", "user-confirmation:claude_said_ok"]
)
def test_d03_the_users_own_words_are_required(world: World, words: str | None) -> None:
    args = ["--confirm"] + ([] if words is None else ["--approval-evidence-ref", words])
    result = world.run(*args)
    assert result.exit_code == 1 and "只听用户本人" in result.output
    assert world.project.is_dir() and world.recycled() == []


def test_d04_uncommitted_changes_block_the_delete(world: World) -> None:
    (world.project / "src" / "a.py").write_text("print('edited')\n", encoding="utf-8")
    (world.project / "new.txt").write_text("untracked\n", encoding="utf-8")
    result = world.run("--confirm", "--approval-evidence-ref", USER_WORDS)
    assert result.exit_code == 1 and "没提交的改动" in result.output
    assert (world.project / "new.txt").is_file() and world.recycled() == []


def test_d05_a_clean_project_moves_into_the_recycle_area_and_can_be_moved_back(
    world: World,
) -> None:
    result = world.run("--confirm", "--approval-evidence-ref", USER_WORDS)
    assert result.exit_code == 0, result.output
    assert not world.project.exists()
    (moved,) = world.recycled()
    assert (moved / "src" / "a.py").read_text(encoding="utf-8") == "print('keep me')\n"
    assert world.audit == [
        {
            "action": "project_delete",
            "project_id": PROJECT,
            "project_name": "Demo",
            "path": str(world.project),
            "recycled_to": str(moved),
            "approval_evidence_ref": USER_WORDS,
        }
    ]
    moved.rename(world.project)  # 搬回即恢复
    assert (world.project / "src" / "a.py").is_file()


def test_d06_an_open_mission_blocks_the_delete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in AGENT_MARKERS:
        monkeypatch.delenv(name, raising=False)
    scene = Scene(tmp_path / "ws")  # MISSION-A 开着，RUN-001 在跑
    world = World.__new__(World)
    project_cli = project_command_module()

    world.root, world.project, world.audit = scene.root, scene.root / "proj", []
    (world.project / "src").mkdir(parents=True)
    (world.project / "src" / "a.py").write_text("x\n", encoding="utf-8")
    git(scene.root, "add", "-A")
    git(scene.root, "commit", "-q", "-m", "proj")
    monkeypatch.setattr(
        project_cli,
        "ProjectService",
        lambda _root: SimpleNamespace(
            get_project=lambda pid: SimpleNamespace(path=str(world.project), name="Demo")
        ),
    )
    result = world.run("--confirm", "--approval-evidence-ref", USER_WORDS)
    assert result.exit_code == 1
    assert "开着的 Mission MISSION-A" in result.output
    assert (
        "MISSION-A" in result.output and "WORK-001" in result.output and "RUN-001" in result.output
    )
    assert world.project.is_dir() and world.recycled() == []
    # 同一份账本里别的项目开着的卡不挡这个项目
    assert guard.open_work_blockers(scene.root, "SW-2026-999") == []
    assert guard.open_work_blockers(scene.root, PROJECT)


def test_d07_an_unreadable_ledger_is_not_a_green_light(world: World) -> None:
    db = world.root / ".auto-pm" / "continuity.db"
    db.parent.mkdir(parents=True)
    db.write_bytes(b"not a database")
    result = world.run("--confirm", "--approval-evidence-ref", USER_WORDS)
    assert result.exit_code == 1 and "读不出本机账本" in result.output
    assert world.project.is_dir() and world.recycled() == []


def test_d08_unreadable_git_state_is_not_a_green_light(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: Any, **kwargs: Any) -> Any:
        raise OSError("no git")

    monkeypatch.setattr(subprocess, "run", broken)
    result = world.run("--confirm", "--approval-evidence-ref", USER_WORDS)
    assert result.exit_code == 1 and "读不出 Git 状态" in result.output and world.project.is_dir()


@pytest.fixture
def committed_pin(monkeypatch: pytest.MonkeyPatch) -> None:
    key = make_key("baiyang", PIN, n=2**10)
    monkeypatch.setattr(ApprovalProofService, "committed_state", lambda self: ([key], ""))


def test_d09_with_a_committed_pin_a_session_without_a_terminal_is_refused(
    world: World, committed_pin: None
) -> None:
    result = world.run("--confirm")
    assert result.exit_code == 1 and "用户本人在自己的终端" in result.output
    assert world.project.is_dir() and world.recycled() == []


def test_d10_with_a_committed_pin_the_wrong_pin_deletes_nothing_and_the_right_one_does(
    world: World, committed_pin: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    import auto_pm.ui.cli.approval_pin as approval_pin

    monkeypatch.setattr(approval_pin, "_stdin_is_tty", lambda: True)
    answers = iter(["wrong-pin-123", PIN])
    monkeypatch.setattr(approval_pin, "_prompt_hidden", lambda text: next(answers))
    wrong = world.run("--confirm")
    assert wrong.exit_code == 1 and world.project.is_dir() and world.recycled() == []
    right = world.run("--confirm")
    assert right.exit_code == 0, right.output
    assert not world.project.exists() and len(world.recycled()) == 1
    assert world.audit[-1]["approval_evidence_ref"].startswith("user-confirmation:")


def test_d11_the_recycle_move_refuses_paths_outside_the_workspace_or_the_workspace_itself(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "ws"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    with pytest.raises(guard.ProjectDeleteError, match="工作区里面"):
        guard.recycle_project(workspace, outside, "P-1")
    with pytest.raises(guard.ProjectDeleteError, match="工作区里面"):
        guard.recycle_project(workspace, workspace, "P-1")
    recycle = workspace / ".auto-pm" / "recycle"
    recycle.mkdir(parents=True)
    with pytest.raises(guard.ProjectDeleteError, match="回收区"):
        guard.recycle_project(workspace, recycle, "P-1")
    assert outside.is_dir() and workspace.is_dir()


def test_d12_two_deletes_of_the_same_id_never_overwrite_each_other(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    workspace = tmp_path / "ws"
    first, second = workspace / "a", workspace / "b"
    for folder, text in ((first, "1"), (second, "2")):
        folder.mkdir(parents=True)
        (folder / "f.txt").write_text(text, encoding="utf-8")
    t1 = guard.recycle_project(workspace, first, "P-1", now=datetime(2026, 10, 26, tzinfo=UTC))
    t2 = guard.recycle_project(
        workspace, second, "P-1", now=datetime(2026, 10, 26, 0, 0, 1, tzinfo=UTC)
    )
    assert (
        t1 != t2
        and (t1 / "f.txt").read_text(encoding="utf-8") == "1"
        and (t2 / "f.txt").read_text(encoding="utf-8") == "2"
    )


def test_d13_import_force_recycles_the_existing_project_instead_of_deleting_it(
    world: World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from auto_pm.application.core.paths import WORKSPACE_PROJECTS_SUBDIR
    from auto_pm.application.core.project_service import ProjectService

    monkeypatch.setattr(project_command_module(), "ProjectService", ProjectService)

    source = tmp_path / "incoming" / "SW-2026-123_X"
    source.mkdir(parents=True)
    (source / "new.txt").write_text("new\n", encoding="utf-8")
    dest = world.root / WORKSPACE_PROJECTS_SUBDIR / source.name
    dest.mkdir(parents=True)
    (dest / "old.txt").write_text("old\n", encoding="utf-8")
    git(world.root, "add", "-A")
    git(world.root, "commit", "-q", "-m", "old project")

    result = CliRunner().invoke(
        cli,
        ["-w", str(world.root), "project", "import", str(source), "--force", "--approval-evidence-ref", USER_WORDS],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    assert (dest / "new.txt").is_file() and not (dest / "old.txt").exists()
    (moved,) = list((world.root / ".auto-pm" / "recycle" / source.name).iterdir())
    assert (moved / "old.txt").read_text(encoding="utf-8") == "old\n"


def _import_force_world(world: World, monkeypatch: pytest.MonkeyPatch, name: str) -> tuple[Path, Path]:
    from auto_pm.application.core.paths import WORKSPACE_PROJECTS_SUBDIR
    from auto_pm.application.core.project_service import ProjectService

    monkeypatch.setattr(project_command_module(), "ProjectService", ProjectService)
    source = world.root.parent / "incoming" / name
    source.mkdir(parents=True)
    (source / "new.txt").write_text("new\n", encoding="utf-8")
    dest = world.root / WORKSPACE_PROJECTS_SUBDIR / name
    dest.mkdir(parents=True)
    (dest / "old.txt").write_text("old\n", encoding="utf-8")
    return source, dest


def _import_force(world: World, source: Path, *extra: str) -> Any:
    return CliRunner().invoke(
        cli, ["-w", str(world.root), "project", "import", str(source), "--force", *extra], catch_exceptions=False
    )


@pytest.mark.parametrize("marker", ["AUTO_PM_AGENT", "CLAUDECODE", "CODEX_THREAD_ID"])
def test_d14_import_force_is_refused_in_an_agent_environment_and_changes_nothing(
    world: World, monkeypatch: pytest.MonkeyPatch, marker: str
) -> None:
    source, dest = _import_force_world(world, monkeypatch, "SW-2026-123_X")
    monkeypatch.setenv(marker, "1")
    result = _import_force(world, source)
    assert result.exit_code == 1 and "只听用户本人" in result.output
    assert (dest / "old.txt").is_file() and not (dest / "new.txt").exists() and world.recycled() == []
    assert not (world.root / ".auto-pm" / "recycle" / source.name).exists()


def test_d15_import_force_is_refused_while_the_project_still_has_open_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in AGENT_MARKERS:
        monkeypatch.delenv(name, raising=False)
    scene = Scene(tmp_path / "ws")  # MISSION-A 开着，RUN-001 在跑
    world = World.__new__(World)
    world.root, world.project, world.audit = scene.root, scene.root / "proj", []
    source, dest = _import_force_world(world, monkeypatch, f"{PROJECT}_X")
    result = _import_force(world, source)
    assert result.exit_code == 1 and "开着的 Mission MISSION-A" in result.output
    assert (dest / "old.txt").is_file() and not (dest / "new.txt").exists()
    assert not (scene.root / ".auto-pm" / "recycle").exists()


def test_d16_overwrite_blockers_ignore_a_directory_without_a_project_number(tmp_path: Path) -> None:
    scene = Scene(tmp_path / "ws")
    assert guard.overwrite_blockers(scene.root, "scratch_dir") == []
    assert guard.overwrite_blockers(scene.root, f"{PROJECT}_X")


def test_d17_the_surface_identity_gate_refuses_agents_and_a_committed_pin(
    tmp_path: Path, committed_pin: None
) -> None:
    assert "只听用户本人" in guard.surface_identity_problem(tmp_path, {"CLAUDECODE": "1"})
    assert "批准口令" in guard.surface_identity_problem(tmp_path, {})


def test_d18_the_surface_identity_gate_lets_the_user_through_without_a_pin(tmp_path: Path) -> None:
    assert guard.surface_identity_problem(tmp_path, {}) == ""
    assert guard.surface_identity_problem(tmp_path, {"CLAUDECODE": ""}) == ""


def test_d19_an_unreadable_approval_pin_config_is_not_a_green_light(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from auto_pm.application.core.approval_proof_service import ApprovalProofError

    def broken(self: ApprovalProofService) -> bool:
        raise ApprovalProofError("口令配置损坏")

    monkeypatch.setattr(ApprovalProofService, "enforced", broken)
    problem = guard.surface_identity_problem(tmp_path, {})
    assert "读不出批准口令配置" in problem and "口令配置损坏" in problem


def _commit_all(root: Path) -> None:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "old project")


@pytest.mark.parametrize("words", [None, "yes please", "user-confirmation:x", "user-confirmation:claude_said_ok"])
def test_d20_import_force_needs_the_users_own_words(
    world: World, monkeypatch: pytest.MonkeyPatch, words: str | None
) -> None:
    source, dest = _import_force_world(world, monkeypatch, "SW-2026-123_X")
    _commit_all(world.root)
    extra = [] if words is None else ["--approval-evidence-ref", words]
    result = _import_force(world, source, *extra)
    assert result.exit_code == 1 and "只听用户本人" in result.output
    assert (dest / "old.txt").is_file() and not (dest / "new.txt").exists()
    assert not (world.root / ".auto-pm" / "recycle" / source.name).exists()


def test_d21_import_force_refuses_to_cover_uncommitted_changes(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, dest = _import_force_world(world, monkeypatch, "SW-2026-123_X")  # old.txt 没提交
    result = _import_force(world, source, "--approval-evidence-ref", USER_WORDS)
    assert result.exit_code == 1 and "没提交的改动" in result.output
    assert (dest / "old.txt").is_file() and not (dest / "new.txt").exists()
    assert not (world.root / ".auto-pm" / "recycle" / source.name).exists()


def test_d22_import_force_with_a_committed_pin_ignores_the_evidence_text_and_needs_the_pin(
    world: World, monkeypatch: pytest.MonkeyPatch, committed_pin: None
) -> None:
    source, dest = _import_force_world(world, monkeypatch, "SW-2026-123_X")
    _commit_all(world.root)
    result = _import_force(world, source, "--approval-evidence-ref", USER_WORDS)
    assert result.exit_code == 1 and "用户本人在自己的终端" in result.output
    assert (dest / "old.txt").is_file() and not (dest / "new.txt").exists()
