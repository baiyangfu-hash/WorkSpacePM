"""单元测试：阶段 1 结构化决策包契约与服务（Decision Package Contract & Service）"""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from auto_pm.contracts.decision_package import (
    RUNTIME_CAPABILITY_KEY,
    SCHEMA_VERSION,
    DecisionPackageDTO,
    RuntimeDecisionAction,
    RuntimeDecisionCapability,
    RuntimeDecisionOutcome,
)
from auto_pm.domain.change.decision_service import (
    DecisionNotFoundError,
    DecisionService,
    DecisionValidationError,
)


@pytest.fixture(autouse=True)
def _git_workspace(tmp_path: Path) -> None:
    subprocess.run(["git", "-C", str(tmp_path), "init"], check=True, capture_output=True)


def _approved_change(
    root: Path,
    change_id: str = "CHG-SCPT-2026-214",
    *,
    status: str = "approved",
    container: str = "",
) -> Path:
    project_root = root / container / "SW-2026-008_auto-pm"
    _workspace_registry(root, project_root)
    chg_dir = project_root / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-SCPT"
    chg_dir.mkdir(parents=True, exist_ok=True)
    path = chg_dir / f"{change_id}.md"
    path.write_text(
        f"""# {change_id}
## 3. 变更基本信息
### 3.0 编号与项目
| 变更编号 | {change_id} |
| 项目编号 | SW-2026-008 |
### 3.3 影响范围
| 影响范围 | MODULE |
### 3.4 申请信息
| 变更状态 | {status} |
""",
        encoding="utf-8",
        errors="replace",
    )
    return path


def _workspace_registry(root: Path, project_root: Path) -> None:
    project_root.mkdir(parents=True, exist_ok=True)
    registry = root / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    relative = project_root.relative_to(root).as_posix()
    registry.write_text(
        json.dumps(
            {
                "schema_version": "workspace-registry.v1",
                "projects": [
                    {
                        "project_id": "SW-2026-008",
                        "project_root": relative,
                        "development_root": relative,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def _runtime_capability() -> RuntimeDecisionCapability:
    return RuntimeDecisionCapability(
        allowed_runtime_actions=(RuntimeDecisionAction.SETTLE_EXPIRED_RUN,),
        target_run_ids=("RUN-SW008-A2-OLD",),
        allowed_outcomes=(RuntimeDecisionOutcome.CANCELLED,),
    )


def _directory_link(link: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    link.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0:
            pytest.skip(f"junction unavailable: {result.stderr or result.stdout}")
    else:
        link.symlink_to(target, target_is_directory=True)


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


def test_runtime_capability_is_typed_and_legacy_metadata_remains_compatible() -> None:
    capability = RuntimeDecisionCapability(
        allowed_runtime_actions=(RuntimeDecisionAction.SETTLE_EXPIRED_RUN,),
        target_run_ids=("RUN-SW008-A2-OLD",),
        allowed_outcomes=(RuntimeDecisionOutcome.CANCELLED,),
    )
    dto = DecisionPackageDTO(
        decision_id="DEC-20260911-5C37A985",
        project_id="SW-2026-008",
        change_id="CHG-SCPT-2026-214",
        approved_scope="MODULE",
        approver="fubai",
        approved_at="2026-09-11T00:00:00+00:00",
        metadata={RUNTIME_CAPABILITY_KEY: capability, "legacy_note": "preserved"},
    )

    restored = DecisionPackageDTO.from_dict(dto.to_dict())

    assert restored.runtime_capability == capability
    assert restored.metadata["legacy_note"] == "preserved"


@pytest.mark.parametrize(
    "runtime_capability",
    [
        {
            "allowed_runtime_actions": ["settle_expired_run"],
            "target_run_ids": ["RUN-OLD"],
        },
        {
            "allowed_runtime_actions": ["unknown_action"],
            "target_run_ids": ["RUN-OLD"],
            "allowed_outcomes": ["CANCELLED"],
        },
        {
            "allowed_runtime_actions": ["settle_expired_run"],
            "target_run_ids": ["RUN-OLD"],
            "allowed_outcomes": ["FAILED"],
        },
    ],
)
def test_runtime_capability_rejects_partial_or_unknown_values(
    runtime_capability: dict[str, list[str]],
) -> None:
    with pytest.raises(ValueError, match="runtime_capability|unknown"):
        DecisionPackageDTO.from_dict(
            {
                "schema_version": SCHEMA_VERSION,
                "decision_id": "DEC-20260911-5C37A985",
                "project_id": "SW-2026-008",
                "change_id": "CHG-SCPT-2026-214",
                "approved_scope": "MODULE",
                "approved_files": [".auto-pm/continuity.db"],
                "approver": "fubai",
                "approved_at": "2026-09-11T00:00:00+00:00",
                "decision_conclusion": "approved",
                "conditions": [],
                "metadata": {RUNTIME_CAPABILITY_KEY: runtime_capability},
            }
        )


def test_decision_reads_do_not_create_runtime_directories(tmp_path: Path) -> None:
    service = DecisionService(tmp_path)

    assert service.list_decisions() == []
    with pytest.raises(DecisionNotFoundError):
        service.get_decision("DEC-20260911-5C37A985")
    assert not (tmp_path / ".auto-pm").exists()


def test_runtime_decision_requires_explicit_id_and_never_overwrites(tmp_path: Path) -> None:
    _approved_change(tmp_path)
    service = DecisionService(tmp_path)
    capability = RuntimeDecisionCapability(
        allowed_runtime_actions=(RuntimeDecisionAction.SETTLE_EXPIRED_RUN,),
        target_run_ids=("RUN-SW008-A2-OLD",),
        allowed_outcomes=(RuntimeDecisionOutcome.CANCELLED,),
    )
    with pytest.raises(DecisionValidationError, match="显式"):
        service.create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            runtime_capability=capability,
        )

    decision_id = "DEC-20260911-5C37A985"
    service.create_decision(
        change_id="CHG-SCPT-2026-214",
        approver="fubai",
        project_id="SW-2026-008",
        decision_id=decision_id,
        runtime_capability=capability,
    )
    decision_path = tmp_path / ".auto-pm" / "decisions" / f"{decision_id}.json"
    original = decision_path.read_bytes()

    with pytest.raises(DecisionValidationError, match="拒绝覆盖"):
        service.create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="other",
            project_id="SW-2026-008",
            decision_id=decision_id,
            runtime_capability=capability,
        )
    assert decision_path.read_bytes() == original


def test_runtime_decision_canonicalizes_approver_before_signing(tmp_path: Path) -> None:
    _approved_change(tmp_path)
    service = DecisionService(tmp_path)

    created = service.create_decision(
        change_id="CHG-SCPT-2026-214",
        approver="  fubai  ",
        project_id="SW-2026-008",
        approved_files=[".auto-pm/continuity.db"],
        decision_id="DEC-20260911-5C37A985",
        runtime_capability=_runtime_capability(),
    )

    assert created.approver == "fubai"
    assert service.get_decision(created.decision_id).approver == "fubai"


def test_explicit_decision_id_rejects_path_traversal(tmp_path: Path) -> None:
    _approved_change(tmp_path)

    with pytest.raises(DecisionValidationError, match="格式非法"):
        DecisionService(tmp_path).create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            decision_id="../../escape",
        )
    assert not (tmp_path.parent / "escape.json").exists()


@pytest.mark.parametrize(
    "decision_id",
    [" DEC-20260911-5C37A985", "DEC-20260911-5C37A985 "],
)
def test_decision_id_whitespace_is_rejected_for_create_read_and_hash(
    tmp_path: Path, decision_id: str
) -> None:
    _approved_change(tmp_path)
    service = DecisionService(tmp_path)

    with pytest.raises(DecisionValidationError, match="空白"):
        service.create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            decision_id=decision_id,
        )
    with pytest.raises(DecisionValidationError, match="空白"):
        service.get_decision(decision_id)
    with pytest.raises(DecisionValidationError, match="空白"):
        service.get_decision_with_sha256(decision_id)
    assert not (tmp_path / ".auto-pm").exists()


def test_decision_read_rejects_payload_identity_and_unknown_schema(tmp_path: Path) -> None:
    decisions = tmp_path / ".auto-pm" / "decisions"
    decisions.mkdir(parents=True)
    mismatched_id = "DEC-20260911-5C37A985"
    future_id = "DEC-20260911-5C37A986"
    (decisions / f"{mismatched_id}.json").write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "decision_id": "DEC-20260911-5C37A987",
                "project_id": "SW-2026-008",
                "change_id": "CHG-SCPT-2026-214",
                "approved_scope": "MODULE",
            }
        ),
        encoding="utf-8",
    )
    (decisions / f"{future_id}.json").write_text(
        json.dumps(
            {
                "schema_version": "decision_package.v999",
                "decision_id": future_id,
                "project_id": "SW-2026-008",
                "change_id": "CHG-SCPT-2026-214",
                "approved_scope": "MODULE",
            }
        ),
        encoding="utf-8",
    )

    service = DecisionService(tmp_path)
    with pytest.raises(DecisionValidationError, match="identity"):
        service.get_decision(mismatched_id)
    with pytest.raises(DecisionValidationError, match="schema"):
        service.get_decision_with_sha256(future_id)
    with pytest.raises(DecisionValidationError, match="列表包含无效文件"):
        service.list_decisions()


def test_decision_list_fails_closed_when_valid_and_corrupt_files_are_mixed(
    tmp_path: Path,
) -> None:
    decisions = tmp_path / ".auto-pm" / "decisions"
    decisions.mkdir(parents=True)
    valid = DecisionPackageDTO(
        decision_id="DEC-20260911-5C37A984",
        project_id="SW-2026-008",
        change_id="CHG-SCPT-2026-214",
        approved_scope="MODULE",
    )
    (decisions / f"{valid.decision_id}.json").write_text(
        json.dumps(valid.to_dict()),
        encoding="utf-8",
    )
    (decisions / "DEC-20260911-5C37A985.json").write_text("{broken", encoding="utf-8")

    with pytest.raises(DecisionValidationError, match="列表包含无效文件"):
        DecisionService(tmp_path).list_decisions()


def test_decision_read_rejects_duplicate_json_fields(tmp_path: Path) -> None:
    decisions = tmp_path / ".auto-pm" / "decisions"
    decisions.mkdir(parents=True)
    decision_id = "DEC-20260911-5C37A985"
    serialized = json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "decision_id": decision_id,
            "project_id": "SW-2026-008",
            "change_id": "CHG-SCPT-2026-214",
            "approved_scope": "MODULE",
        }
    )
    duplicate = serialized.replace(
        f'"decision_id": "{decision_id}",',
        f'"decision_id": "{decision_id}", "decision_id": "{decision_id}",',
        1,
    )
    (decisions / f"{decision_id}.json").write_text(duplicate, encoding="utf-8")

    with pytest.raises(DecisionValidationError, match="重复字段"):
        DecisionService(tmp_path).get_decision(decision_id)


@pytest.mark.parametrize(
    ("field", "value", "remove"),
    [
        ("schema_version", None, True),
        ("decision_conclusion", None, True),
        ("conditions", None, True),
        ("approved_files", {".auto-pm/continuity.db": True}, False),
        ("conditions", {}, False),
        ("approver", 123, False),
        ("metadata", [[RUNTIME_CAPABILITY_KEY, {}]], False),
        ("unexpected", "field", False),
    ],
)
def test_runtime_decision_read_rejects_missing_extra_or_wrong_type_fields(
    tmp_path: Path,
    field: str,
    value: object,
    remove: bool,
) -> None:
    _approved_change(tmp_path)
    service = DecisionService(tmp_path)
    created = service.create_decision(
        change_id="CHG-SCPT-2026-214",
        approver="fubai",
        project_id="SW-2026-008",
        approved_files=[".auto-pm/continuity.db"],
        decision_id="DEC-20260911-5C37A985",
        runtime_capability=_runtime_capability(),
    )
    path = service.decisions_dir / f"{created.decision_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if remove:
        del payload[field]
    else:
        payload[field] = value
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(DecisionValidationError, match="Decision|metadata|runtime"):
        service.get_decision(created.decision_id)


@pytest.mark.parametrize(
    "change_id",
    [
        "../CHG-SCPT-2026-214",
        "CHG-*-2026-214",
        "CHG-SCPT-2026-214/other",
        "CHG-SCPT-2026-214\\other",
    ],
)
def test_runtime_decision_rejects_noncanonical_change_basename(
    tmp_path: Path, change_id: str
) -> None:
    with pytest.raises(DecisionValidationError, match="canonical CHG basename"):
        DecisionService(tmp_path).create_decision(
            change_id=change_id,
            approver="fubai",
            project_id="SW-2026-008",
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
        )
    assert not (tmp_path / ".auto-pm").exists()


@pytest.mark.parametrize(
    "status",
    ["conditionally_approved", "pending_acceptance", "completed", "closed"],
)
def test_runtime_decision_new_signature_rejects_non_current_chg_status(
    tmp_path: Path, status: str
) -> None:
    _approved_change(tmp_path, status=status)

    with pytest.raises(DecisionValidationError, match="approved/implementing"):
        DecisionService(tmp_path).create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
        )


def test_runtime_decision_rejects_change_payload_identity_mismatch(tmp_path: Path) -> None:
    change_path = _approved_change(tmp_path)
    content = change_path.read_text(encoding="utf-8", errors="replace")
    change_path.write_text(
        content.replace(
            "| 变更编号 | CHG-SCPT-2026-214 |",
            "| 变更编号 | CHG-SCPT-2026-999 |",
        ),
        encoding="utf-8",
        errors="replace",
    )

    with pytest.raises(DecisionValidationError, match="filename/request/payload identity"):
        DecisionService(tmp_path).create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            approved_files=[".auto-pm/continuity.db"],
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
        )
    assert not (tmp_path / ".auto-pm").exists()


@pytest.mark.parametrize(
    ("original", "replacement"),
    [
        ("| 变更编号 | CHG-SCPT-2026-214 |\n", ""),
        (
            "| 变更编号 | CHG-SCPT-2026-214 |",
            "| 变更编号 | CHG-SCPT-2026-214 |\n| 变更编号 | CHG-SCPT-2026-214 |",
        ),
        ("| 项目编号 | SW-2026-008 |\n", ""),
        (
            "| 项目编号 | SW-2026-008 |",
            "| 项目编号 | SW-2026-008 |\n| 项目编号 | SW-2026-008 |",
        ),
        ("| 变更状态 | approved |\n", ""),
        (
            "| 变更状态 | approved |",
            "| 变更状态 | approved |\n| 变更状态 | implementing |",
        ),
    ],
)
def test_runtime_decision_requires_unique_explicit_change_identity_and_status(
    tmp_path: Path,
    original: str,
    replacement: str,
) -> None:
    change_path = _approved_change(tmp_path)
    content = change_path.read_text(encoding="utf-8", errors="replace")
    change_path.write_text(
        content.replace(original, replacement),
        encoding="utf-8",
        errors="replace",
    )

    with pytest.raises(DecisionValidationError, match="恰好出现一次"):
        DecisionService(tmp_path).create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            approved_files=[".auto-pm/continuity.db"],
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
        )
    assert not (tmp_path / ".auto-pm").exists()


@pytest.mark.parametrize(
    "source",
    [
        """# CHG-SCPT-2026-214
## 2. 其他信息
### 3.0 编号与项目
| 变更编号 | CHG-SCPT-2026-214 |
| 项目编号 | SW-2026-008 |
## 3. 变更基本信息
### 3.3 影响范围
| 影响范围 | MODULE |
### 3.4 申请信息
| 变更状态 | approved |
""",
        """# CHG-SCPT-2026-214
## 3. 变更基本信息
### 3.0 编号与项目
| 变更编号 | CHG-SCPT-2026-214 |
| 项目编号 | SW-2026-008 |
### 3.3 影响范围
| 影响范围 | MODULE |
## 4. 其他信息
### 3.4 申请信息
| 变更状态 | approved |
""",
    ],
)
def test_runtime_decision_rejects_authority_subsections_outside_unique_section_three(
    tmp_path: Path,
    source: str,
) -> None:
    change_path = _approved_change(tmp_path)
    change_path.write_text(source, encoding="utf-8")

    with pytest.raises(DecisionValidationError, match="§3\\.[04]"):
        DecisionService(tmp_path).create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
        )
    assert not (tmp_path / ".auto-pm").exists()


@pytest.mark.parametrize("heading", ["###3.0 编号与项目", "###\n3.0 编号与项目"])
def test_runtime_decision_rejects_non_commonmark_authority_heading(
    tmp_path: Path,
    heading: str,
) -> None:
    change_path = _approved_change(tmp_path)
    source = change_path.read_text(encoding="utf-8", errors="replace")
    change_path.write_text(
        source.replace("### 3.0 编号与项目", heading),
        encoding="utf-8",
        errors="replace",
    )

    with pytest.raises(DecisionValidationError, match=r"§3\.0"):
        DecisionService(tmp_path).create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
        )
    assert not (tmp_path / ".auto-pm" / "decisions").exists()


@pytest.mark.parametrize(
    ("original", "replacement"),
    [
        ("## 3. 变更基本信息", "## 3.0 错误层级"),
        (
            "## 3. 变更基本信息",
            "## 3. 变更基本信息\n## 5.1 错误层级",
        ),
    ],
)
def test_runtime_decision_rejects_level_two_decimal_authority_sections(
    tmp_path: Path,
    original: str,
    replacement: str,
) -> None:
    change_path = _approved_change(tmp_path)
    source = change_path.read_text(encoding="utf-8", errors="replace")
    change_path.write_text(
        source.replace(original, replacement),
        encoding="utf-8",
        errors="replace",
    )

    with pytest.raises(DecisionValidationError, match="层级非法"):
        DecisionService(tmp_path).create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
        )
    assert not (tmp_path / ".auto-pm" / "decisions").exists()


@pytest.mark.parametrize(
    "source",
    [
        """# CHG-SCPT-2026-214
## 3. 变更基本信息
### 3.0 编号与项目
| 变更编号 | CHG-SCPT-2026-214 |
| 项目编号 | SW-2026-008 |
# 另一顶层文档
### 3.4 申请信息
| 变更状态 | approved |
""",
        """# CHG-SCPT-2026-214
## 3. 变更基本信息
### 3.0 编号与项目
| 变更编号 | CHG-SCPT-2026-214 |
| 项目编号 | SW-2026-008 |
### 3.3 影响范围
| 影响范围 | MODULE |
### 3.4 申请信息
| 变更状态 | approved |
## 5. 变更内容
# 另一顶层文档
| 涉及文件/交付物 | outside.py |
""",
    ],
)
def test_runtime_decision_stops_authority_at_intervening_level_one_heading(
    tmp_path: Path,
    source: str,
) -> None:
    change_path = _approved_change(tmp_path)
    change_path.write_text(source, encoding="utf-8", errors="replace")

    service = DecisionService(tmp_path)
    with pytest.raises(DecisionValidationError, match=r"§3\.4|§5"):
        service.create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
        )
    assert not (tmp_path / ".auto-pm" / "decisions").exists()


def test_runtime_decision_rejects_fenced_code_as_authority(tmp_path: Path) -> None:
    change_path = _approved_change(tmp_path)
    change_path.write_text(
        """# CHG-SCPT-2026-214
```markdown
## 3. 变更基本信息
### 3.0 编号与项目
| 变更编号 | CHG-SCPT-2026-214 |
| 项目编号 | SW-2026-008 |
### 3.3 影响范围
| 影响范围 | MODULE |
### 3.4 申请信息
| 变更状态 | approved |
```
""",
        encoding="utf-8",
    )

    with pytest.raises(DecisionValidationError, match="fenced"):
        DecisionService(tmp_path).create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
        )
    assert not (tmp_path / ".auto-pm").exists()


def test_runtime_decision_rejects_wrong_section_duplicate_beside_valid_authority(
    tmp_path: Path,
) -> None:
    change_path = _approved_change(tmp_path)
    change_path.write_text(
        change_path.read_text(encoding="utf-8")
        + """
## 4. 非授权章节
### 4.1 伪造数据
| 变更编号 | CHG-SCPT-2026-214 |
""",
        encoding="utf-8",
    )

    with pytest.raises(DecisionValidationError, match="只能出现在唯一 §3.0"):
        DecisionService(tmp_path).create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
        )


@pytest.mark.parametrize(
    ("opener", "closer"),
    [
        ("<pre data-test='authority'>", "</pre>"),
        ("<script type='text/plain'>", "</script>"),
        ("<style>", "</style>"),
        ("<textarea>", "</textarea>"),
        ("<div class='hidden'>", "</div>"),
    ],
)
def test_runtime_decision_rejects_authority_in_raw_html_blocks(
    tmp_path: Path,
    opener: str,
    closer: str,
) -> None:
    change_path = _approved_change(tmp_path)
    change_path.write_text(
        change_path.read_text(encoding="utf-8")
        + f"""
{opener}
## 5. 隐藏授权
| 涉及文件/交付物 | outside.py |
{closer}

""",
        encoding="utf-8",
    )

    with pytest.raises(DecisionValidationError, match="HTML|<pre>"):
        DecisionService(tmp_path).create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
        )
    assert not (tmp_path / ".auto-pm" / "decisions").exists()


@pytest.mark.parametrize(
    "hidden",
    [
        "    | 变更状态 | implementing |\n",
        "<!--\n| 变更状态 | implementing |\n-->\n",
        "<div>\n| 变更状态 | implementing |\n",
        "<div style='display:none'>\n\n| 变更状态 | implementing |\n</div>\n",
        ("<div style='display:none'>\n<div>\n</div>\n| 变更状态 | implementing |\n</div>\n"),
        ("<div style='display:none' data-x='</div>'>\n| 变更状态 | implementing |\n</div>\n"),
        "x<div style='display:none'>\n| 变更状态 | implementing |\n</div>\n",
        "\u200bx<div style='display:none'>\n| 变更状态 | implementing |\n</div>\n",
    ],
)
def test_runtime_decision_rejects_indented_comment_and_unclosed_html_spoofs(
    tmp_path: Path,
    hidden: str,
) -> None:
    change_path = _approved_change(tmp_path)
    change_path.write_text(
        change_path.read_text(encoding="utf-8") + "\n" + hidden,
        encoding="utf-8",
    )

    with pytest.raises(DecisionValidationError, match="fenced/indented|HTML"):
        DecisionService(tmp_path).create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
        )
    assert not (tmp_path / ".auto-pm" / "decisions").exists()


def test_runtime_decision_rejects_duplicate_top_level_authority_section(
    tmp_path: Path,
) -> None:
    change_path = _approved_change(tmp_path)
    change_path.write_text(
        change_path.read_text(encoding="utf-8")
        + "\n## 5. 变更内容\n| 涉及文件/交付物 | first.py |\n"
        + "\n## 5. 变更内容\n| 涉及文件/交付物 | second.py |\n",
        encoding="utf-8",
    )

    with pytest.raises(DecisionValidationError, match="§5"):
        DecisionService(tmp_path).create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
        )
    assert not (tmp_path / ".auto-pm" / "decisions").exists()


def test_runtime_decision_signature_survives_chg_close_and_removal(tmp_path: Path) -> None:
    change_path = _approved_change(tmp_path, status="implementing")
    service = DecisionService(tmp_path)
    created = service.create_decision(
        change_id="CHG-SCPT-2026-214",
        approver="fubai",
        project_id="SW-2026-008",
        decision_id="DEC-20260911-5C37A985",
        runtime_capability=_runtime_capability(),
    )
    decision_path = service.decisions_dir / f"{created.decision_id}.json"
    original = decision_path.read_bytes()

    change_path.write_text(
        change_path.read_text(encoding="utf-8").replace("implementing", "closed"),
        encoding="utf-8",
    )
    assert service.get_decision(created.decision_id) == created
    change_path.unlink()
    loaded, digest = service.get_decision_with_sha256(created.decision_id)

    assert loaded == created
    assert digest == hashlib.sha256(original).hexdigest()
    assert [item.decision_id for item in service.list_decisions()] == [created.decision_id]


def test_runtime_decision_rechecks_chg_snapshot_immediately_before_create(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    change_path = _approved_change(tmp_path, status="implementing")
    service = DecisionService(tmp_path)
    original_guard = service._require_control_root
    calls = 0

    def drift_after_second_guard() -> None:
        nonlocal calls
        calls += 1
        original_guard()
        if calls == 2:
            change_path.write_text(
                change_path.read_text(encoding="utf-8") + "\n<!-- changed -->\n",
                encoding="utf-8",
            )

    monkeypatch.setattr(service, "_require_control_root", drift_after_second_guard)

    with pytest.raises(DecisionValidationError, match="漂移"):
        service.create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
        )

    assert not service.decisions_dir.exists()


def test_runtime_decision_rejects_aba_bytes_before_any_decision_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    change_path = _approved_change(tmp_path)
    service = DecisionService(tmp_path)
    original_read_bytes = Path.read_bytes
    source_a = original_read_bytes(change_path)
    source_b = source_a.replace(b"MODULE", b"SYSTEM") + (
        b"\n## 5. authority\n| files | expanded.py |\n"
    )
    snapshots = iter((source_a, source_b, source_a))

    def alternating_change_snapshot(path: Path) -> bytes:
        if path.resolve() == change_path.resolve():
            return next(snapshots)
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", alternating_change_snapshot)

    with pytest.raises(DecisionValidationError, match="漂移"):
        service.create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
        )
    assert not service.decisions_dir.exists()


def test_runtime_decision_rechecks_complete_authority_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _approved_change(tmp_path)
    service = DecisionService(tmp_path)
    original_runtime_change = service._runtime_change
    calls = 0

    def projection_drift(change_id: str, project_id: str):
        nonlocal calls
        calls += 1
        path, change, digest = original_runtime_change(change_id, project_id)
        if calls == 2:
            change = change.model_copy(update={"impact_scope": ["SYSTEM"]})
        return path, change, digest

    monkeypatch.setattr(service, "_runtime_change", projection_drift)

    with pytest.raises(DecisionValidationError, match="漂移"):
        service.create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
        )
    assert not service.decisions_dir.exists()


def test_runtime_decision_rejects_conditions_and_archive_only_source(tmp_path: Path) -> None:
    _approved_change(tmp_path, container="backup")
    service = DecisionService(tmp_path)

    with pytest.raises(DecisionValidationError, match="附加条件"):
        service.create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
            conditions=["manual follow-up"],
        )
    with pytest.raises(DecisionValidationError, match="归档|备份|当前标准"):
        service.create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
        )


def test_runtime_decision_ignores_unregistered_scratch_clone(tmp_path: Path) -> None:
    registered = tmp_path / "projects" / "SW-2026-008_auto-pm"
    _workspace_registry(tmp_path, registered)
    scratch_change = (
        tmp_path
        / "scratch"
        / "SW-2026-008_copy"
        / "04_监控"
        / "01_变更管理"
        / "01_变更单"
        / "CHG-SCPT"
        / "CHG-SCPT-2026-214.md"
    )
    scratch_change.parent.mkdir(parents=True)
    scratch_change.write_text(
        """# CHG-SCPT-2026-214
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

    with pytest.raises(DecisionValidationError, match="当前标准"):
        DecisionService(tmp_path).create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
        )


@pytest.mark.parametrize(
    "variant",
    [
        "duplicate_project_root",
        "duplicate_development_root",
        "unknown_top",
        "unknown_project",
        "project_traversal",
        "development_traversal",
    ],
)
def test_runtime_decision_rejects_ambiguous_workspace_registry_json(
    tmp_path: Path,
    variant: str,
) -> None:
    change_path = _approved_change(tmp_path)
    project_root = change_path.parents[4]
    relative = project_root.relative_to(tmp_path).as_posix()
    registry = tmp_path / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
    project_root_value = f"alias/../{relative}" if variant == "project_traversal" else relative
    development_root_value = (
        f"alias/../{relative}" if variant == "development_traversal" else relative
    )
    quoted = json.dumps(relative)
    project_fields = (
        '"project_id":"SW-2026-008",'
        f'"project_root":{json.dumps(project_root_value)},'
        f'"development_root":{json.dumps(development_root_value)}'
    )
    if variant == "duplicate_project_root":
        project_fields += f',"project_root":{quoted}'
    elif variant == "duplicate_development_root":
        project_fields += f',"development_root":{quoted}'
    elif variant == "unknown_project":
        project_fields += ',"unexpected":"hidden"'
    top_extra = ',"unexpected":"hidden"' if variant == "unknown_top" else ""
    registry.write_text(
        '{"schema_version":"workspace-registry.v1","projects":[{'
        + project_fields
        + "}]"
        + top_extra
        + "}",
        encoding="utf-8",
        errors="replace",
    )

    with pytest.raises(DecisionValidationError, match="重复字段|未知|点路径段"):
        DecisionService(tmp_path).create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
        )
    assert not (tmp_path / ".auto-pm" / "decisions").exists()


@pytest.mark.parametrize("authority", ["registry", "change"])
def test_runtime_decision_rejects_hardlinked_authority_files(
    tmp_path: Path,
    authority: str,
) -> None:
    change_path = _approved_change(tmp_path)
    source = (
        tmp_path / "SYS-2026-001_WorkspaceGovernance" / "workspace_registry.json"
        if authority == "registry"
        else change_path
    )
    external = tmp_path.parent / f"{tmp_path.name}-{authority}-authority-alias"
    try:
        os.link(source, external)
    except OSError as error:
        pytest.skip(f"hardlink unavailable: {error}")

    with pytest.raises(DecisionValidationError, match="唯一链接"):
        DecisionService(tmp_path).create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
        )
    assert not (tmp_path / ".auto-pm" / "decisions").exists()


def test_decision_read_rejects_hardlinked_runtime_json(tmp_path: Path) -> None:
    decisions = tmp_path / ".auto-pm" / "decisions"
    decisions.mkdir(parents=True)
    decision_id = "DEC-20260911-5C37A985"
    source = decisions / f"{decision_id}.json"
    source.write_text(
        json.dumps(
            DecisionPackageDTO(
                decision_id=decision_id,
                project_id="SW-2026-008",
                change_id="CHG-SCPT-2026-214",
                approved_scope="MODULE",
            ).to_dict()
        ),
        encoding="utf-8",
        errors="replace",
    )
    external = tmp_path.parent / f"{tmp_path.name}-decision-authority-alias.json"
    try:
        os.link(source, external)
    except OSError as error:
        pytest.skip(f"hardlink unavailable: {error}")

    with pytest.raises(DecisionValidationError, match="唯一链接"):
        DecisionService(tmp_path).get_decision(decision_id)


def test_decision_directory_junction_is_rejected_without_external_write(tmp_path: Path) -> None:
    external = tmp_path.parent / f"{tmp_path.name}-external-decisions"
    link = tmp_path / ".auto-pm" / "decisions"
    _directory_link(link, external)
    service = DecisionService(tmp_path)

    with pytest.raises(DecisionValidationError, match="symlink/junction"):
        service.list_decisions()
    with pytest.raises(DecisionValidationError, match="symlink/junction"):
        service.create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            decision_id="DEC-20260911-5C37A985",
        )
    assert list(external.iterdir()) == []


def test_decision_target_symlink_is_rejected(tmp_path: Path) -> None:
    decisions = tmp_path / ".auto-pm" / "decisions"
    decisions.mkdir(parents=True)
    external_decision = tmp_path.parent / f"{tmp_path.name}-external-decision.json"
    external_decision.write_text("{}", encoding="utf-8")
    decision_link = decisions / "DEC-20260911-5C37A985.json"
    try:
        decision_link.symlink_to(external_decision)
    except OSError as error:
        pytest.skip(f"file symlink unavailable: {error}")

    with pytest.raises(DecisionValidationError, match="symlink/junction"):
        DecisionService(tmp_path).get_decision("DEC-20260911-5C37A985")


def test_runtime_change_external_junction_is_rejected(tmp_path: Path) -> None:
    external_changes = tmp_path.parent / f"{tmp_path.name}-external-changes"
    external_changes.mkdir()
    (external_changes / "CHG-SCPT-2026-214.md").write_text(
        """# CHG-SCPT-2026-214
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
    change_directory_link = (
        tmp_path / "SW-2026-008_auto-pm" / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-SCPT"
    )
    _workspace_registry(tmp_path, tmp_path / "SW-2026-008_auto-pm")
    _directory_link(change_directory_link, external_changes)

    with pytest.raises(DecisionValidationError, match="symlink/junction"):
        DecisionService(tmp_path).create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            project_id="SW-2026-008",
            decision_id="DEC-20260911-5C37A985",
            runtime_capability=_runtime_capability(),
        )
    assert not (tmp_path / ".auto-pm" / "decisions").exists()


def test_decision_create_directly_rejects_linked_worktree_without_side_effect(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text("baseline\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(tmp_path), "add", "README.md"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "-c",
            "user.name=Decision Test",
            "-c",
            "user.email=decision@example.invalid",
            "commit",
            "-m",
            "baseline",
        ],
        check=True,
        capture_output=True,
    )
    linked = tmp_path.parent / f"{tmp_path.name}-linked"
    subprocess.run(
        ["git", "-C", str(tmp_path), "worktree", "add", "--detach", str(linked), "HEAD"],
        check=True,
        capture_output=True,
    )

    with pytest.raises(DecisionValidationError, match="linked worktree"):
        DecisionService(linked).create_decision(
            change_id="CHG-SCPT-2026-214",
            approver="fubai",
            decision_id="DEC-20260911-5C37A985",
        )
    assert not (linked / ".auto-pm").exists()


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
