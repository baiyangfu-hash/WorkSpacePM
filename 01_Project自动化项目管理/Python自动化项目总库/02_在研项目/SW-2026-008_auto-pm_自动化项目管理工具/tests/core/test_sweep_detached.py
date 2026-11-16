"""手工开的 detached 目录：HEAD 已在 origin/main 上、目录干净、没有长任务在用，sweep 才清（G 工位止血，卡 280；试车九条第 6 条 6c）。

以前 sweep 一律判“工位不在分支上（detached HEAD），不动”，``worktree close`` 又不认这种名字，门禁和人工核对用
``git worktree add --detach`` 开的目录只能用户开终端手敲 git 删。项目经理 14:15Z 定的判法和两道护栏：

* 门禁在跑的信号先核真实存在：``long-run start`` 在 ``.auto-pm/long-run/<任务>/status.json`` 记 ``cwd``、``worktree`` 和命令；
  STARTING/RUNNING 的任务用着这个目录（在里面跑，或命令里点了它的名）就不清，原因写明是哪个任务；状态读不出也不清；
* 只有用户本人清（带 AI 标记的 sweep 照旧不动名册外目录）；判词写明是门禁目录还是手工 detached 目录、HEAD 是哪个提交；
  ``auto-make-room`` 和 ``close`` 永远不动它。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_pm.application.core.agent_worktree_service import Station, StationRefusedError
from tests.core.test_agent_worktree_service import (  # noqa: F401 - lab 是按名字复用的夹具
    Lab,
    commit,
    git,
    lab,
)


def _detached(lab: Lab, name: str = "gate-f00d00") -> tuple[Path, str]:  # noqa: F811
    path = lab.root / ".auto-pm" / "worktrees" / name
    git(lab.root, "worktree", "add", "-q", "--detach", str(path), "origin/main")
    return path, git(path, "rev-parse", "HEAD")


def _long_run(lab: Lab, task: str, state: str, **fields: str) -> Path:  # noqa: F811
    folder = lab.root / ".auto-pm" / "long-run" / task
    folder.mkdir(parents=True)
    status = {"schema_version": "long-run.v1", "name": task, "state": state, "command_text": "python -m pytest", **fields}
    (folder / "status.json").write_text(json.dumps(status), encoding="utf-8")
    return folder


def _item(lab: Lab, path: Path, *, apply: bool = False) -> tuple[bool, str, list[str]]:  # noqa: F811
    report = lab.service().sweep(apply=apply)
    item = next(item for item in report.items if item.target == str(path))
    return item.remove, item.reason, list(report.done)


def test_a_clean_gate_directory_on_origin_main_is_listed_with_its_head_and_removed_on_apply(lab: Lab) -> None:  # noqa: F811
    path, head = _detached(lab)
    remove, reason, _ = _item(lab, path)
    assert remove, reason
    assert "门禁目录" in reason and head[:12] in reason and "origin/main" in reason, "判词写明是门禁目录、HEAD 是哪个提交"
    assert path.exists(), "不带 --apply 只列"

    remove, _, done = _item(lab, path, apply=True)
    assert str(path) in done and not path.exists()
    assert str(path) not in git(lab.root, "worktree", "list", "--porcelain")


def test_a_hand_made_detached_directory_says_so(lab: Lab) -> None:  # noqa: F811
    path, head = _detached(lab, "check-by-hand")
    remove, reason, _ = _item(lab, path)
    assert remove and "手工开的 detached 目录" in reason and head[:12] in reason, reason


@pytest.mark.parametrize("problem", ["dirty", "ignored", "own-commit"])
def test_anything_that_could_be_lost_keeps_it(lab: Lab, problem: str) -> None:  # noqa: F811
    path, _ = _detached(lab)
    if problem == "dirty":
        (path / "draft.txt").write_text("没提交\n", encoding="utf-8")
    elif problem == "ignored":
        (path / ".auto-pm").mkdir()
        (path / ".auto-pm" / "keep.txt").write_text("被忽略的文件\n", encoding="utf-8")
    else:
        commit(path, "d.txt")
    remove, reason, done = _item(lab, path, apply=True)
    assert not remove and path.exists() and str(path) not in done, reason
    expected = {"dirty": "未提交", "ignored": ".gitignore", "own-commit": "不在 origin/main 上"}[problem]
    assert expected in reason, reason


@pytest.mark.parametrize(
    ("state", "where", "kept"),
    [
        ("RUNNING", "cwd", True),
        ("STARTING", "worktree", True),
        ("RUNNING", "command", True),
        ("RUNNING", "elsewhere", False),
        ("DONE", "cwd", False),
        ("FAILED", "cwd", False),
        ("STOPPED", "cwd", False),
    ],
)
def test_a_long_run_in_it_keeps_it_and_names_the_task(lab: Lab, state: str, where: str, kept: bool) -> None:  # noqa: F811
    path, _ = _detached(lab)
    if where == "cwd":
        _long_run(lab, "gate-full", state, cwd=str(path / "01_Project"))
    elif where == "worktree":
        _long_run(lab, "gate-full", state, worktree=str(path))
    elif where == "command":
        _long_run(lab, "gate-full", state, cwd=str(lab.root), command_text=f"python main.py gate precheck --worktree {path}")
    else:
        _long_run(lab, "gate-full", state, cwd=str(lab.root), worktree=str(lab.root))
    remove, reason, done = _item(lab, path, apply=True)
    assert remove is not kept, reason
    if kept:
        assert "长任务 gate-full" in reason and state in reason and path.exists() and str(path) not in done, reason
    else:
        assert not path.exists()


def test_a_long_run_record_that_cannot_be_read_keeps_it(lab: Lab) -> None:  # noqa: F811
    path, _ = _detached(lab)
    folder = lab.root / ".auto-pm" / "long-run" / "gate-full"
    folder.mkdir(parents=True)
    (folder / "status.json").write_text("{半截", encoding="utf-8")
    remove, reason, _ = _item(lab, path, apply=True)
    assert not remove and path.exists() and "读不出" in reason, reason


def test_an_agent_never_cleans_it(lab: Lab, monkeypatch: pytest.MonkeyPatch) -> None:  # noqa: F811
    path, _ = _detached(lab)
    monkeypatch.setenv("AUTO_PM_AGENT", "claude")
    remove, reason, _ = _item(lab, path, apply=True)
    assert not remove and path.exists() and "只由用户" in reason, reason


@pytest.mark.parametrize("via", ["auto-make-room", "close", "release", "reclaim-stale"])
def test_only_sweep_removes_it_never_make_room_or_close(lab: Lab, via: str) -> None:  # noqa: F811
    path, _ = _detached(lab)
    station = next(item for item in lab.service().stations() if item.path == path)
    assert isinstance(station, Station)
    with pytest.raises(StationRefusedError, match="detached"):
        lab.service()._remove_station(station, via=via)
    assert path.exists()


def test_a_head_that_moved_after_listing_is_not_removed(lab: Lab) -> None:  # noqa: F811
    path, _ = _detached(lab)
    station = next(item for item in lab.service().stations() if item.path == path)
    git(lab.root, "fetch", "-q", "origin")
    other = commit(lab.github, "later.txt")
    git(lab.github, "push", "-q", "origin", "HEAD:main")
    git(lab.root, "fetch", "-q", "origin")
    git(path, "checkout", "-q", "--detach", other)  # 有人在里面换到了新提交（仍在 origin/main 上、仍干净）
    with pytest.raises(StationRefusedError, match="有人在用"):
        lab.service()._remove_station(station, via="sweep")
    assert path.exists()
