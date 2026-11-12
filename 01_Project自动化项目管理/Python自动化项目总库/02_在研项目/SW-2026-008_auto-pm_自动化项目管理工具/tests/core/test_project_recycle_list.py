"""TD-208：``project recycle-list`` 只读列出回收区；回收区没有任何自动清理，列表只为让人看见它在涨。"""

from __future__ import annotations

import datetime as datetime_module
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner, Result

from auto_pm.application.core.project_delete_guard import (
    RECYCLE_RELATIVE_DIR,
    list_recycled,
    recycle_project,
)
from auto_pm.ui.cli.__main__ import cli

pytestmark = pytest.mark.usefixtures("identity_guard_off")

NOW = datetime(2026, 11, 8, 12, 0, 0, tzinfo=UTC)


class _FrozenDatetime(datetime):
    """``datetime.now()`` stands still at ``NOW``: ``project recycle-list`` reads the clock itself."""

    @classmethod
    def now(cls, tz=None):  # type: ignore[no-untyped-def]
        return NOW.astimezone(tz) if tz is not None else NOW.replace(tzinfo=None)


@pytest.fixture(autouse=True)
def _frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """The samples are dated relative to ``NOW``; the command must measure from the same instant, or every
    boundary case ("exactly 30 days", "one day short") drifts with the real date (it broke on 2026-11-09 12:00Z).
    The command imports ``datetime`` inside the function, so replacing the module attribute is enough."""

    monkeypatch.setattr(datetime_module, "datetime", _FrozenDatetime)


def _recycle(root: Path, project_id: str, *, days_ago: int) -> Path:
    """用真的 ``recycle_project`` 搬一个项目进回收区，时间戳回拨 ``days_ago`` 天。"""

    project = root / "proj" / project_id
    project.mkdir(parents=True)
    (project / "a.txt").write_text("x", encoding="utf-8")
    return recycle_project(root, project, project_id, now=NOW - timedelta(days=days_ago))


def _tree(root: Path) -> list[tuple[str, bool]]:
    return sorted((path.relative_to(root).as_posix(), path.is_file()) for path in root.rglob("*"))


def test_no_recycle_dir_lists_nothing(tmp_path: Path) -> None:
    assert list_recycled(tmp_path) == []


def test_lists_recycled_projects_newest_first_with_age(tmp_path: Path) -> None:
    old = _recycle(tmp_path, "SW-2026-001", days_ago=40)
    new = _recycle(tmp_path, "SW-2026-002", days_ago=2)
    items = list_recycled(tmp_path)
    assert [item.path for item in items] == [new, old]
    assert [item.age_days(NOW) for item in items] == [2, 40]


def test_an_unreadable_stamp_is_still_listed_and_has_no_age(tmp_path: Path) -> None:
    odd = tmp_path / RECYCLE_RELATIVE_DIR / "SW-2026-003" / "hand-moved"
    odd.mkdir(parents=True)
    (item,) = list_recycled(tmp_path)
    assert item.path == odd and item.recycled_at is None and item.age_days(NOW) is None


def test_listing_changes_nothing_on_disk(tmp_path: Path) -> None:
    _recycle(tmp_path, "SW-2026-001", days_ago=40)
    before = _tree(tmp_path)
    list_recycled(tmp_path)
    assert _tree(tmp_path) == before


def test_cli_lists_json_filters_by_age_and_writes_nothing(tmp_path: Path) -> None:
    old = _recycle(tmp_path, "SW-2026-001", days_ago=400)
    _recycle(tmp_path, "SW-2026-002", days_ago=0)
    before = _tree(tmp_path)

    everything = CliRunner().invoke(cli, ["-w", str(tmp_path), "project", "recycle-list", "--json"], catch_exceptions=False)
    older = CliRunner().invoke(
        cli, ["-w", str(tmp_path), "project", "recycle-list", "--older-than", "30", "--json"], catch_exceptions=False
    )
    text = CliRunner().invoke(cli, ["-w", str(tmp_path), "project", "recycle-list"], catch_exceptions=False)

    assert everything.exit_code == older.exit_code == text.exit_code == 0
    assert len(json.loads(everything.output)) == 2
    (only,) = json.loads(older.output)
    assert only["project_id"] == "SW-2026-001" and only["path"] == str(old) and only["age_days"] >= 399
    assert "SW-2026-001" in text.output and "不会删除任何东西" in text.output
    assert _tree(tmp_path) == before


def test_cli_on_an_empty_workspace_says_so(tmp_path: Path) -> None:
    result = CliRunner().invoke(cli, ["-w", str(tmp_path), "project", "recycle-list"], catch_exceptions=False)
    assert result.exit_code == 0 and "没有符合条件" in result.output


def _stamped(root: Path, project_id: str, stamp: str) -> Path:
    path = root / RECYCLE_RELATIVE_DIR / project_id / stamp
    path.mkdir(parents=True)
    return path


def _ids(output: str) -> list[str]:
    return [item["path"] for item in json.loads(output)]


def _recycle_list(root: Path, *args: str) -> str:
    result = CliRunner().invoke(cli, ["-w", str(root), "project", "recycle-list", *args], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    return result.output


@pytest.mark.parametrize("older_than", ["0", "1", "30"])
def test_a_directory_whose_stamp_cannot_be_read_is_never_listed_under_older_than(
    tmp_path: Path, older_than: str
) -> None:
    """手工清理会照着 ``--older-than`` 的清单删：时间未知的目录不能被当成“很旧”列进去（审计 #689 P3）。"""
    odd = _stamped(tmp_path, "SW-2026-003", "hand-moved")
    old = _recycle(tmp_path, "SW-2026-001", days_ago=400)

    assert _ids(_recycle_list(tmp_path, "--older-than", older_than, "--json")) == [str(old)]
    assert str(odd) in _ids(_recycle_list(tmp_path, "--json"))  # 不加条件时仍照样列出，不丢项


def test_older_than_counts_whole_days_and_includes_the_boundary(tmp_path: Path) -> None:
    """审计 #689 P2：搬进来刚好满 N 天算“已满 N 天”，差一天不算。"""
    just_enough = _recycle(tmp_path, "SW-2026-001", days_ago=30)
    one_short = _recycle(tmp_path, "SW-2026-002", days_ago=29)
    output = _recycle_list(tmp_path, "--older-than", "30", "--json")

    assert str(just_enough) in _ids(output)
    assert str(one_short) not in _ids(output)


def test_a_stamp_in_the_future_never_shows_a_negative_age(tmp_path: Path) -> None:
    """审计 #689 P4：时钟回拨后目录名里的时间比现在晚，年龄钳到 0 天，不能出现负数。"""
    future = _recycle(tmp_path, "SW-2026-001", days_ago=-5)
    (item,) = list_recycled(tmp_path)

    assert item.path == future
    assert item.age_days(NOW) == 0


def test_loose_files_are_not_listed_as_recycled_projects(tmp_path: Path) -> None:
    """审计 #689 P7、P10：回收区根下、项目编号目录下散落的文件不是回收的项目目录，不进清单。"""
    real = _recycle(tmp_path, "SW-2026-001", days_ago=3)
    (tmp_path / RECYCLE_RELATIVE_DIR / "stray-at-root.txt").write_text("x", encoding="utf-8")
    (tmp_path / RECYCLE_RELATIVE_DIR / "SW-2026-001" / "stray-in-project.txt").write_text("x", encoding="utf-8")

    assert [item.path for item in list_recycled(tmp_path)] == [real]
    assert _ids(_recycle_list(tmp_path, "--json")) == [str(real)]


def test_the_listing_ends_with_the_read_only_notice_and_unknown_age_is_spelled_out(tmp_path: Path) -> None:
    _stamped(tmp_path, "SW-2026-003", "hand-moved")
    output = _recycle_list(tmp_path)

    assert "时间未知" in output
    assert output.rstrip().splitlines()[-1].startswith("只读列表：这里不会删除任何东西")


def test_the_command_measures_age_from_the_frozen_clock_not_the_real_date(tmp_path: Path) -> None:
    """Guards the fixture above: a sample dated 7 days before ``NOW`` is exactly 7 days old whatever today is."""

    _recycle(tmp_path, "SW-2026-001", days_ago=7)
    (item,) = json.loads(_recycle_list(tmp_path, "--json"))
    assert item["age_days"] == 7


# ---------------------------------------------------------------- CHG-SCPT-2026-650：project restore 搬回原处

USER_WORDS = "user-confirmation:cmsg_user_says_restore_ok"


@pytest.fixture
def no_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    from auto_pm.application.core.lease_handover_service import AGENT_MARKERS

    for name in AGENT_MARKERS:
        monkeypatch.delenv(name, raising=False)


def _registered_and_deleted(root: Path) -> tuple[Path, Path, Path]:
    """登记表里 DJ-2026-005 原是“暂停”；目录搬进回收区并标“已删除”，和 project delete 走的是同两步。"""
    from auto_pm.application.core.project_delete_guard import mark_registry_deleted
    from tests.core.test_workspace_registry_service import _workspace

    registry = _workspace(root)
    text = registry.read_text(encoding="utf-8").replace(
        '"runtime_root": ""\n    }\n  ]', '"runtime_root": "",\n      "status": "paused"\n    }\n  ]'
    )
    registry.write_text(text, encoding="utf-8", newline="\n")
    project = root / "0100_PLC自动化" / "DJ-2026-005"
    (project / "a.txt").write_text("keep me", encoding="utf-8")
    recycled = recycle_project(root, project, "DJ-2026-005", now=NOW)
    mark_registry_deleted(root, "DJ-2026-005")
    return registry, project, recycled


def _status(registry: Path) -> tuple[str, str]:
    entry = json.loads(registry.read_text(encoding="utf-8"))["projects"][1]
    return entry.get("status", ""), entry.get("status_before_delete", "")


def _restore(root: Path, *args: str) -> Result:
    return CliRunner().invoke(cli, ["-w", str(root), "project", "restore", *args], catch_exceptions=False)


def test_restore_without_apply_only_previews(tmp_path: Path, no_agent: None) -> None:
    registry, project, recycled = _registered_and_deleted(tmp_path)
    before = _tree(tmp_path)
    result = _restore(tmp_path, "DJ-2026-005")
    assert result.exit_code == 0, result.output
    assert "预演" in result.output and "0100_PLC自动化/DJ-2026-005" in result.output
    assert "回收区记录" in result.output
    assert _tree(tmp_path) == before and not project.exists() and recycled.is_dir()


@pytest.mark.parametrize("marker", ["AUTO_PM_AGENT", "CLAUDECODE", "CODEX_THREAD_ID"])
def test_restore_apply_is_refused_for_an_agent(
    tmp_path: Path, no_agent: None, monkeypatch: pytest.MonkeyPatch, marker: str
) -> None:
    registry, project, recycled = _registered_and_deleted(tmp_path)
    before = _tree(tmp_path)
    monkeypatch.setenv(marker, "1")
    result = _restore(tmp_path, "DJ-2026-005", "--apply", "--approval-evidence-ref", USER_WORDS)
    assert result.exit_code == 1 and "只听用户本人" in result.output
    assert _tree(tmp_path) == before


@pytest.mark.parametrize("words", [None, "yes please", "user-confirmation:claude_said_ok"])
def test_restore_apply_needs_the_users_own_words(tmp_path: Path, no_agent: None, words: str | None) -> None:
    _registered_and_deleted(tmp_path)
    before = _tree(tmp_path)
    extra = [] if words is None else ["--approval-evidence-ref", words]
    result = _restore(tmp_path, "DJ-2026-005", "--apply", *extra)
    assert result.exit_code == 1 and "只听用户本人" in result.output
    assert _tree(tmp_path) == before


def test_restore_apply_moves_the_folder_back_and_puts_the_status_back(tmp_path: Path, no_agent: None) -> None:
    from auto_pm.application.core.project_delete_guard import ORIGINS_RELATIVE_DIR

    registry, project, recycled = _registered_and_deleted(tmp_path)
    assert _status(registry) == ("deleted", "paused")
    result = _restore(tmp_path, "DJ-2026-005", "--apply", "--approval-evidence-ref", USER_WORDS)
    assert result.exit_code == 0, result.output
    assert (project / "a.txt").read_text(encoding="utf-8") == "keep me" and not recycled.exists()
    assert _status(registry) == ("paused", "")
    assert "暂停" in result.output
    assert not (tmp_path / RECYCLE_RELATIVE_DIR / "DJ-2026-005").exists()
    assert not (tmp_path / ORIGINS_RELATIVE_DIR / "DJ-2026-005").exists()
    assert list_recycled(tmp_path) == []


def test_restore_refuses_when_the_old_place_is_taken(tmp_path: Path, no_agent: None) -> None:
    registry, project, recycled = _registered_and_deleted(tmp_path)
    project.mkdir(parents=True)
    (project / "new.txt").write_text("someone else", encoding="utf-8")
    before = _tree(tmp_path)
    result = _restore(tmp_path, "DJ-2026-005", "--apply", "--approval-evidence-ref", USER_WORDS)
    assert result.exit_code == 1 and "已经有同名目录" in result.output
    assert _tree(tmp_path) == before and _status(registry) == ("deleted", "paused")


def test_restore_with_several_copies_needs_a_stamp(tmp_path: Path, no_agent: None) -> None:
    registry, project, first = _registered_and_deleted(tmp_path)
    project.mkdir(parents=True)
    (project / "b.txt").write_text("second", encoding="utf-8")
    second = recycle_project(tmp_path, project, "DJ-2026-005", now=NOW + timedelta(seconds=1))
    result = _restore(tmp_path, "DJ-2026-005")
    assert result.exit_code == 1 and "--stamp" in result.output
    chosen = _restore(tmp_path, "DJ-2026-005", "--stamp", first.name, "--apply", "--approval-evidence-ref", USER_WORDS)
    assert chosen.exit_code == 0, chosen.output
    assert (project / "a.txt").is_file() and second.is_dir()


def test_restore_without_an_origin_record_falls_back_to_the_registry(tmp_path: Path, no_agent: None) -> None:
    from auto_pm.application.core.project_delete_guard import ORIGINS_RELATIVE_DIR

    registry, project, recycled = _registered_and_deleted(tmp_path)
    for record in (tmp_path / ORIGINS_RELATIVE_DIR).rglob("*.json"):
        record.unlink()
    result = _restore(tmp_path, "DJ-2026-005", "--apply", "--approval-evidence-ref", USER_WORDS)
    assert result.exit_code == 0, result.output
    assert "登记表" in result.output and (project / "a.txt").is_file()


def test_restore_of_an_unregistered_project_only_hints_at_register(tmp_path: Path, no_agent: None) -> None:
    _recycle(tmp_path, "SW-2026-001", days_ago=1)
    result = _restore(tmp_path, "SW-2026-001", "--apply", "--approval-evidence-ref", USER_WORDS)
    assert result.exit_code == 0, result.output
    assert (tmp_path / "proj" / "SW-2026-001" / "a.txt").is_file()
    flat = " ".join(result.output.split())
    assert "project register SW-2026-001 --path proj/SW-2026-001" in flat
    assert not (tmp_path / "SYS-2026-001_WorkspaceGovernance").exists()  # 不自动登记，也不新建登记表


def test_restore_of_something_not_in_the_recycle_area_is_refused(tmp_path: Path, no_agent: None) -> None:
    result = _restore(tmp_path, "SW-2026-404")
    assert result.exit_code == 1 and "回收区里没有项目 SW-2026-404" in result.output
