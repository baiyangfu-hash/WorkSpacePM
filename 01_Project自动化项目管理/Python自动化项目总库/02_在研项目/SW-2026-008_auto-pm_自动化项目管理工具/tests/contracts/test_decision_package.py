"""单元测试：阶段 1 结构化决策包契约与服务（Decision Package Contract & Service）"""

from pathlib import Path

import pytest

from auto_pm.contracts.decision_package import SCHEMA_VERSION, DecisionPackageDTO
from auto_pm.domain.change.decision_service import (
    DecisionService,
    DecisionValidationError,
)


def test_decision_package_dto_roundtrip() -> None:
    """测试 DecisionPackageDTO 序列化与反序列化一致性"""
    dto = DecisionPackageDTO(
        decision_id="DEC-20260903-TEST0001",
        project_id="TEST-2026-001",
        change_id="CHG-SCPT-2026-001",
        approved_scope="MODULE",
        approved_files=["src/service.py", "tests/test_service.py"],
        approver="fubai",
        approved_at="2026-09-03T12:00:00Z",
        decision_conclusion="approved",
        conditions=["无回归测试失败"],
        metadata={"note": "集成测试"},
    )
    data = dto.to_dict()
    assert data["decision_id"] == "DEC-20260903-TEST0001"
    assert data["schema_version"] == SCHEMA_VERSION
    assert len(data["approved_files"]) == 2

    restored = DecisionPackageDTO.from_dict(data)
    assert restored.decision_id == dto.decision_id
    assert restored.approved_files == dto.approved_files
    assert restored.conditions == ["无回归测试失败"]


def test_create_decision_rejects_unapproved_change(tmp_path: Path) -> None:
    """测试未批准的变更单被拒绝生成决策包"""
    chg_dir = tmp_path / "01_变更单" / "CHG-SCPT"
    chg_dir.mkdir(parents=True)
    chg_file = chg_dir / "CHG-SCPT-2026-001.md"
    chg_file.write_text(
        """# CHG-SCPT-2026-001
## 3. 变更基本信息
### 3.4 申请信息
| 变更状态 | draft |
""",
        encoding="utf-8",
    )

    service = DecisionService(tmp_path)
    with pytest.raises(DecisionValidationError) as exc:
        service.create_decision(
            change_id="CHG-SCPT-2026-001",
            approver="fubai",
        )
    assert "尚未获得批准" in str(exc.value)


def test_create_decision_success_from_approved_change(tmp_path: Path) -> None:
    """测试已批准变更单成功生成并持久化决策包"""
    chg_dir = tmp_path / "01_变更单" / "CHG-SCPT"
    chg_dir.mkdir(parents=True)
    chg_file = chg_dir / "CHG-SCPT-2026-001.md"
    chg_file.write_text(
        """# CHG-SCPT-2026-001
## 3. 变更基本信息
### 3.0 编号与项目
| 项目编号 | TEST-001 |
### 3.3 影响范围
| 影响范围 | MODULE |
### 3.4 申请信息
| 变更状态 | approved |

## 5. 变更内容
### 5.1 变更前
| 涉及文件/交付物 | src/app.py<br>tests/test_app.py |
### 5.2 变更后
| 涉及文件/交付物 | src/app.py<br>tests/test_app.py |
""",
        encoding="utf-8",
    )

    service = DecisionService(tmp_path)
    dto = service.create_decision(
        change_id="CHG-SCPT-2026-001",
        approver="fubai",
    )

    assert dto.decision_id.startswith("DEC-")
    assert dto.change_id == "CHG-SCPT-2026-001"
    assert dto.approver == "fubai"
    assert "src/app.py" in dto.approved_files
    assert "tests/test_app.py" in dto.approved_files

    # 验证读取
    fetched = service.get_decision(dto.decision_id)
    assert fetched.decision_id == dto.decision_id
    assert fetched.change_id == dto.change_id

    # 验证列表
    all_decisions = service.list_decisions(change_id="CHG-SCPT-2026-001")
    assert len(all_decisions) == 1
    assert all_decisions[0].decision_id == dto.decision_id


def test_create_decision_uses_project_id_to_disambiguate_duplicate_change_id(
    tmp_path: Path,
) -> None:
    """跨项目同号变更必须按项目绑定，禁止命中全局扫描首项。"""
    change_id = "CHG-DOCU-2026-006"
    for project_id, scope in (("PROJ-A", "MODULE"), ("PROJ-B", "SYSTEM")):
        chg_dir = tmp_path / project_id / "04_监控" / "01_变更管理" / "01_变更单"
        chg_dir.mkdir(parents=True)
        (chg_dir / f"{change_id}.md").write_text(
            f"""# {change_id}
## 3. 变更基本信息
### 3.0 编号与项目
| 项目编号 | {project_id} |
### 3.3 影响范围
| ☑ **{scope}** 范围 | **选中** |
### 3.4 申请信息
| 变更状态 | approved |
""",
            encoding="utf-8",
        )

    service = DecisionService(tmp_path)
    dto = service.create_decision(
        change_id=change_id,
        approver="fubai",
        project_id="PROJ-B",
    )
    assert dto.project_id == "PROJ-B"
    assert dto.approved_scope == "SYSTEM"


def test_create_decision_rejects_ambiguous_duplicate_change_id(tmp_path: Path) -> None:
    """未提供项目时，跨项目重号必须 fail-closed。"""
    change_id = "CHG-DOCU-2026-006"
    for project_id in ("PROJ-A", "PROJ-B"):
        chg_dir = tmp_path / project_id / "04_监控" / "01_变更管理" / "01_变更单"
        chg_dir.mkdir(parents=True)
        (chg_dir / f"{change_id}.md").write_text(
            f"""# {change_id}
## 3. 变更基本信息
### 3.0 编号与项目
| 项目编号 | {project_id} |
### 3.3 影响范围
| ☑ **SYSTEM** 范围 | **选中** |
### 3.4 申请信息
| 变更状态 | approved |
""",
            encoding="utf-8",
        )

    service = DecisionService(tmp_path)
    with pytest.raises(DecisionValidationError, match="跨项目重号"):
        service.create_decision(change_id=change_id, approver="fubai")


def test_create_decision_ignores_runtime_worktree_mirror(tmp_path: Path) -> None:
    """运行态 worktree 的镜像变更单不得制造正式资产的重号假阳性。"""
    change_id = "CHG-SCPT-2026-201"
    for root in (
        tmp_path / "SW-2026-008",
        tmp_path / ".auto-pm" / "worktrees" / "isolated" / "SW-2026-008",
    ):
        chg_dir = root / "04_监控" / "01_变更管理" / "01_变更单"
        chg_dir.mkdir(parents=True)
        (chg_dir / f"{change_id}.md").write_text(
            f"""# {change_id}
## 3. 变更基本信息
### 3.0 编号与项目
| 项目编号 | SW-2026-008 |
### 3.3 影响范围
| 影响范围 | MODULE |
### 3.4 申请信息
| 变更状态 | approved |
""",
            encoding="utf-8",
        )

    dto = DecisionService(tmp_path).create_decision(
        change_id=change_id,
        approver="fubai",
        project_id="SW-2026-008",
    )
    assert dto.project_id == "SW-2026-008"


def test_create_decision_rejects_same_project_formal_duplicate(tmp_path: Path) -> None:
    """正式项目目录中的同项目重号仍必须 fail-closed。"""
    change_id = "CHG-SCPT-2026-202"
    for source in ("SW-2026-008-A", "SW-2026-008-B"):
        chg_dir = tmp_path / source / "04_监控" / "01_变更管理" / "01_变更单"
        chg_dir.mkdir(parents=True)
        (chg_dir / f"{change_id}.md").write_text(
            f"""# {change_id}
## 3. 变更基本信息
### 3.0 编号与项目
| 项目编号 | SW-2026-008 |
### 3.3 影响范围
| 影响范围 | MODULE |
### 3.4 申请信息
| 变更状态 | approved |
""",
            encoding="utf-8",
        )

    with pytest.raises(DecisionValidationError, match="跨项目重号"):
        DecisionService(tmp_path).create_decision(
            change_id=change_id,
            approver="fubai",
            project_id="SW-2026-008",
        )
