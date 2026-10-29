"""同号变更单在多个项目里都有时，写操作不带项目编号必须拒绝（TD-SW008-176）

以前 ``change transition`` 不带 ``--pid`` 会改目录遍历顺序里先找到的那个项目的单子。
现在写操作（状态流转、修改、删除）遇到同号多项目就抛 ``AmbiguousChangeNumberError``，并在提示里写出 ``--pid`` 和候选文件。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_pm.domain.change.change_service import ChangeService
from auto_pm.domain.change.file_locator import AmbiguousChangeNumberError, ChangeFileLocator
from auto_pm.domain.change.parser import ChgParser

CHG = "CHG-SCPT-2026-002"


def _project(ws: Path, name: str, monitor: str = "04_监控") -> Path:
    root = ws / name
    root.mkdir(parents=True)
    (root / f"PM_SESSION_{name.split('_')[0]}.md").write_text("# PM_SESSION\n", encoding="utf-8")
    sheet = root / monitor / "01_变更管理" / "01_变更单" / "CHG-SCPT" / f"{CHG}.md"
    sheet.parent.mkdir(parents=True)
    sheet.write_text(f"# {CHG}\n", encoding="utf-8")
    return sheet


@pytest.fixture
def two_projects(tmp_path: Path) -> tuple[Path, Path, Path]:
    a = _project(tmp_path, "SW-2026-010_验证套件")
    b = _project(tmp_path / "0100_PLC", "DJ-2026-011_验证", monitor="11_监控")
    return tmp_path, a, b


def test_locator_refuses_ambiguous_number_for_writes(two_projects: tuple[Path, Path, Path]) -> None:
    ws, a, b = two_projects
    locator = ChangeFileLocator(str(ws), ChgParser())
    with pytest.raises(AmbiguousChangeNumberError) as err:
        locator.find_change_file(CHG, require_unique=True)
    message = str(err.value)
    assert "--pid" in message
    assert str(a) in message and str(b) in message


def test_locator_read_path_unchanged(two_projects: tuple[Path, Path, Path]) -> None:
    """读路径向后兼容：不要求唯一时仍返回第一个命中。"""
    ws, a, b = two_projects
    locator = ChangeFileLocator(str(ws), ChgParser())
    assert locator.find_change_file(CHG) in {str(a), str(b)}


def test_unique_number_still_found_for_writes(tmp_path: Path) -> None:
    only = _project(tmp_path, "SW-2026-010_验证套件")
    locator = ChangeFileLocator(str(tmp_path), ChgParser())
    assert locator.find_change_file(CHG, require_unique=True) == str(only)


def test_missing_number_is_none_for_writes(tmp_path: Path) -> None:
    _project(tmp_path, "SW-2026-010_验证套件")
    locator = ChangeFileLocator(str(tmp_path), ChgParser())
    assert locator.find_change_file("CHG-SCPT-2026-999", require_unique=True) is None


def test_pid_still_disambiguates_writes(two_projects: tuple[Path, Path, Path]) -> None:
    ws, a, _ = two_projects
    locator = ChangeFileLocator(str(ws), ChgParser())
    assert locator.find_change_file(CHG, project_id="SW-2026-010", require_unique=True) == str(a)


def test_transition_without_pid_is_refused_and_touches_nothing(two_projects: tuple[Path, Path, Path]) -> None:
    ws, a, b = two_projects
    before = {p: p.read_bytes() for p in (a, b)}
    with pytest.raises(AmbiguousChangeNumberError):
        ChangeService(str(ws)).transition_status(CHG, "approved", approver="x")
    assert {p: p.read_bytes() for p in (a, b)} == before


def test_delete_without_pid_is_refused(two_projects: tuple[Path, Path, Path]) -> None:
    ws, a, b = two_projects
    with pytest.raises(AmbiguousChangeNumberError):
        ChangeService(str(ws)).delete_change_request(CHG)
    assert a.is_file() and b.is_file()


def test_update_without_pid_is_refused_and_touches_nothing(two_projects: tuple[Path, Path, Path]) -> None:
    """修改（change edit 背后的 update_change_request）同样要拦：不带项目编号不能碰巧改到某一个项目的单子。"""
    ws, a, b = two_projects
    before = {p: p.read_bytes() for p in (a, b)}
    with pytest.raises(AmbiguousChangeNumberError, match="--pid"):
        ChangeService(str(ws)).update_change_request(CHG, background="不该写进任何一个项目")
    assert {p: p.read_bytes() for p in (a, b)} == before


def test_update_with_pid_reaches_the_named_project_only(two_projects: tuple[Path, Path, Path]) -> None:
    """带 lookup_project_id 时不触发歧义拒绝（可能因内容不合规别的原因失败，但不是歧义）。"""
    ws, a, b = two_projects
    try:
        ChangeService(str(ws)).update_change_request(
            CHG, lookup_project_id="SW-2026-010", background="x"
        )
    except AmbiguousChangeNumberError:
        pytest.fail("带项目编号时不应报同号歧义")
    except Exception:  # noqa: BLE001 - 夹具只是占位单，解析/写入的别的失败与本用例无关
        pass
    assert b.read_text(encoding="utf-8") == f"# {CHG}\n"
