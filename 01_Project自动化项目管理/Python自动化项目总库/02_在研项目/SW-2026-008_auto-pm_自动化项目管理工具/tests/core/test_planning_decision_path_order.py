"""既有 Decision 与规划卡的批准文件清单按集合比较，不依赖书写顺序（TD-SW008-051）"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from auto_pm.application.core.pm_facade_service import PmFacadeError, PmFacadeService
from auto_pm.contracts.decision_package import DecisionPackageDTO

_GRANT = {"grant": "x"}


def _card(scope_paths: tuple[str, ...]) -> SimpleNamespace:
    return SimpleNamespace(
        subject_project_id="SW-2026-008",
        change_id="CHG-SCPT-2026-001",
        scope_paths=scope_paths,
        plan_hash="h" * 64,
        request_id="REQ-1",
        execution_grant=SimpleNamespace(model_dump=lambda mode="json": dict(_GRANT)),
    )


def _decision(files: list[str]) -> DecisionPackageDTO:
    return DecisionPackageDTO(
        decision_id="DEC-1",
        project_id="SW-2026-008",
        change_id="CHG-SCPT-2026-001",
        approved_scope="MODULE",
        approved_files=files,
        approver="user",
        decision_conclusion="approved",
        metadata={
            "planning_approval": {
                "schema_version": "planning-approval.v2",
                "plan_hash": "h" * 64,
                "approval_evidence_ref": "user-confirmation:t1",
                "request_id": "REQ-1",
                "execution_grant": dict(_GRANT),
            }
        },
    )


def _validate(files: list[str], scope: tuple[str, ...]) -> None:
    PmFacadeService._validate_planning_decision(
        _decision(files),
        card=_card(scope),  # type: ignore[arg-type]
        approver="user",
        approval_evidence_ref="user-confirmation:t1",
    )


def test_same_files_in_the_same_order_pass() -> None:
    _validate(["b.py", "a.py"], ("b.py", "a.py"))


def test_same_files_in_another_order_pass() -> None:
    _validate(["a.py", "b.py"], ("b.py", "a.py"))


@pytest.mark.parametrize(
    ("files", "scope"),
    [
        (["a.py"], ("a.py", "b.py")),  # Decision 少一个
        (["a.py", "b.py", "c.py"], ("a.py", "b.py")),  # Decision 多一个
        (["a.py", "c.py"], ("a.py", "b.py")),  # 换了一个
        (["a.py", "a.py", "b.py"], ("a.py", "b.py", "b.py")),  # 重复项不能掩盖差异
        (["a.py", "a.py"], ("a.py",)),  # 多出重复项
    ],
)
def test_a_different_file_set_is_still_refused(files: list[str], scope: tuple[str, ...]) -> None:
    with pytest.raises(PmFacadeError, match="批准事实不一致"):
        _validate(files, scope)
