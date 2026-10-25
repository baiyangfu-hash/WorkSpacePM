"""TD-SW008-034: the hash-less (legacy) Decision looks a change number up inside one project, not across the workspace."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from auto_pm.domain.change.decision_service import (
    DecisionNotFoundError,
    DecisionService,
    DecisionValidationError,
)
from tests.core.test_decision_change_cabinets import (
    CHANGE_ID,
    CHG_TEXT,
    PROJECT_ID,
    PROJECT_ROOT,
    _repository,
    _write_change,
)

OTHER_PROJECT = "DJ-2026-902"
DECISION_ID = "DEC-20261025-A1B2C3D4"


def _legacy(service: DecisionService, *, project_id: str = PROJECT_ID) -> str:
    decision = service.create_decision(
        CHANGE_ID,
        "fubai",
        project_id=project_id,
        approved_files=["02_PLC程序/PLC_ST/FB_3001.scl"],
        decision_id=DECISION_ID,
    )
    return decision.project_id


def _copy_of_the_chg(root: Path, where: str, *, project_id: str = PROJECT_ID) -> Path:
    path = root / where / "01_变更管理" / "01_变更单" / "CHG-PLC" / f"{CHANGE_ID}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CHG_TEXT.replace(PROJECT_ID, project_id), encoding="utf-8")
    return path


def test_a_backup_copy_with_the_same_number_is_not_a_duplicate(tmp_path: Path) -> None:
    """The control-root backup under ``.auto-pm/backups`` holds a full copy of every change order."""

    _repository(tmp_path, "04_监控")
    backup = tmp_path / ".auto-pm" / "backups" / "control-root-20261024" / PROJECT_ROOT / "04_监控"
    shutil.copytree(tmp_path / PROJECT_ROOT / "04_监控", backup)

    assert _legacy(DecisionService(tmp_path)) == PROJECT_ID


def test_an_archive_copy_with_the_same_number_is_not_a_duplicate(tmp_path: Path) -> None:
    _repository(tmp_path, "04_监控")
    _copy_of_the_chg(tmp_path, "03_归档/旧副本")
    _copy_of_the_chg(tmp_path, "archive_2026/old")

    assert _legacy(DecisionService(tmp_path)) == PROJECT_ID


def test_another_project_with_the_same_number_does_not_matter_when_the_project_is_given(
    tmp_path: Path,
) -> None:
    _repository(tmp_path, "04_监控")
    _copy_of_the_chg(tmp_path, "0100_PLC自动化/DJ-2026-902/04_监控", project_id=OTHER_PROJECT)

    assert _legacy(DecisionService(tmp_path)) == PROJECT_ID


def test_two_real_projects_with_the_same_number_are_refused_without_a_project_and_name_both_files(
    tmp_path: Path,
) -> None:
    _repository(tmp_path, "04_监控")
    other = _copy_of_the_chg(
        tmp_path, "0100_PLC自动化/DJ-2026-902/04_监控", project_id=OTHER_PROJECT
    )

    with pytest.raises(DecisionValidationError, match="变更单编号跨项目重号") as refused:
        _legacy(DecisionService(tmp_path), project_id="")

    message = str(refused.value)
    assert "请通过 --pid" in message
    assert f"{OTHER_PROJECT}: {other.relative_to(tmp_path).as_posix()}" in message
    assert (
        f"{PROJECT_ID}: {(tmp_path / PROJECT_ROOT / '04_监控' / '01_变更管理' / '01_变更单' / 'CHG-PLC' / (CHANGE_ID + '.md')).relative_to(tmp_path).as_posix()}"
        in message
    )


def test_without_a_project_a_backup_copy_is_still_not_a_second_candidate(tmp_path: Path) -> None:
    _repository(tmp_path, "04_监控")
    _copy_of_the_chg(tmp_path, f".auto-pm/backups/control-root-20261024/{PROJECT_ROOT}/04_监控")

    assert _legacy(DecisionService(tmp_path), project_id="") == PROJECT_ID


def test_a_project_the_registry_does_not_know_still_finds_its_change_by_searching_the_workspace(
    tmp_path: Path,
) -> None:
    _write_change(tmp_path, "04_监控")  # no Workspace Registry at all
    import subprocess

    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=T",
            "-c",
            "user.email=t@example.invalid",
            "commit",
            "-qm",
            "b",
        ],
        check=True,
    )
    _copy_of_the_chg(tmp_path, "备份/old")

    assert _legacy(DecisionService(tmp_path)) == PROJECT_ID


def test_a_missing_change_in_a_registered_project_is_reported_as_missing(tmp_path: Path) -> None:
    _repository(tmp_path)
    (tmp_path / PROJECT_ROOT).mkdir(parents=True, exist_ok=True)
    _copy_of_the_chg(tmp_path, "archive/elsewhere")  # only an archived copy exists

    with pytest.raises(DecisionNotFoundError, match="未找到变更单文件"):
        _legacy(DecisionService(tmp_path))
