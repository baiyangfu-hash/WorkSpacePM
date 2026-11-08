"""TD-208：``project recycle-list`` 只读列出回收区；回收区没有任何自动清理，列表只为让人看见它在涨。"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.application.core.project_delete_guard import (
    RECYCLE_RELATIVE_DIR,
    list_recycled,
    recycle_project,
)
from auto_pm.ui.cli.__main__ import cli

pytestmark = pytest.mark.usefixtures("identity_guard_off")

NOW = datetime(2026, 11, 8, 12, 0, 0, tzinfo=UTC)


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
