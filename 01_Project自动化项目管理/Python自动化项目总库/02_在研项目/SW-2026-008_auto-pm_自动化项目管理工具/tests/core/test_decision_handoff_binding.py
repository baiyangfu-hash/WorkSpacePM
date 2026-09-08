"""单元测试：决策包与 Handoff 派发强校验绑定（Decision to Handoff Binding）"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from auto_pm.application.core.ai_handoff_service import (
    AiHandoffService,
    HandoffValidationError,
)
from auto_pm.contracts.decision_package import DecisionPackageDTO
from auto_pm.domain.change.decision_service import DecisionService


@pytest.fixture
def mock_decision(tmp_path: Path) -> DecisionPackageDTO:
    """创建测试用的已固化决策包"""
    service = DecisionService(tmp_path)
    # 直接写入一个标准的已固化决策包
    dto = DecisionPackageDTO(
        decision_id="DEC-20260903-TEST8888",
        project_id="SW-2026-009",
        change_id="CHG-SCPT-2026-002",
        approved_scope="MODULE",
        approved_files=["src/services/dictionary_service.py", "tests/test_services.py"],
        approver="fubai",
        approved_at="2026-09-03T12:00:00Z",
        decision_conclusion="approved",
    )
    dec_file = service.decisions_dir / f"{dto.decision_id}.json"
    dec_file.write_text(
        json.dumps(dto.to_dict(), ensure_ascii=False),
        encoding="utf-8",
        errors="replace",
    )
    return dto


def test_handoff_create_with_valid_decision(tmp_path: Path, mock_decision: DecisionPackageDTO) -> None:
    """测试携带合法决策包创建 handoff 成功并注入白名单"""
    service = AiHandoffService(tmp_path)
    payload = service.create_request(
        project_id="SW-2026-009",
        executor_skill="fullstack-engineer",
        summary="测试实施",
        change_id="CHG-SCPT-2026-002",
        decision_id=mock_decision.decision_id,
        mode="execution",
    )
    assert payload["decision_id"] == mock_decision.decision_id
    assert payload["change_id"] == "CHG-SCPT-2026-002"
    context = payload["skill_context"]
    assert context["decision_id"] == mock_decision.decision_id
    assert context["approved_scope"] == "MODULE"
    assert "src/services/dictionary_service.py" in context["approved_files"]


def test_handoff_create_rejects_nonexistent_decision(tmp_path: Path) -> None:
    """测试提供不存在的 decision_id 时抛出 HandoffValidationError 阻断"""
    service = AiHandoffService(tmp_path)
    with pytest.raises(HandoffValidationError) as exc_info:
        service.create_request(
            project_id="SW-2026-009",
            executor_skill="fullstack-engineer",
            summary="测试实施",
            decision_id="DEC-NON-EXISTENT",
        )
    assert "决策包验证失败" in str(exc_info.value)


def test_handoff_create_rejects_mismatched_project(tmp_path: Path, mock_decision: DecisionPackageDTO) -> None:
    """测试决策包项目编号与 handoff project_id 不匹配时阻断"""
    service = AiHandoffService(tmp_path)
    with pytest.raises(HandoffValidationError) as exc_info:
        service.create_request(
            project_id="DJ-2026-005",  # 与决策包 SW-2026-009 冲突
            executor_skill="plc-electrical-engineer",
            summary="测试实施",
            decision_id=mock_decision.decision_id,
        )
    assert "决策包项目编号不匹配" in str(exc_info.value)


def test_handoff_create_rejects_mismatched_change_id(tmp_path: Path, mock_decision: DecisionPackageDTO) -> None:
    """测试决策包关联变更单与 handoff change_id 不匹配时阻断"""
    service = AiHandoffService(tmp_path)
    with pytest.raises(HandoffValidationError) as exc_info:
        service.create_request(
            project_id="SW-2026-009",
            executor_skill="fullstack-engineer",
            summary="测试实施",
            change_id="CHG-SCPT-2026-999",  # 与决策包 CHG-SCPT-2026-002 冲突
            decision_id=mock_decision.decision_id,
        )
    assert "决策包关联变更单不匹配" in str(exc_info.value)


def test_closure_with_valid_decision_and_files_passes(tmp_path: Path, mock_decision: DecisionPackageDTO) -> None:
    """测试携带合法决策包、批准范围内修改文件、物理存在的变更单与真实交付物正常闭环"""
    service = AiHandoffService(tmp_path)
    # 创建物理存在的变更单文件
    chg_file = tmp_path / "CHG-SCPT-2026-002.md"
    chg_file.write_text("# CHG-SCPT-2026-002\n", encoding="utf-8", errors="replace")

    # 创建物理存在的交付物文件（大小大于0）
    report_file = tmp_path / "reports" / "summary.txt"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text("Verification passed\n", encoding="utf-8", errors="replace")

    req = service.create_request(
        project_id="SW-2026-009",
        executor_skill="fullstack-engineer",
        summary="正常实施",
        change_id="CHG-SCPT-2026-002",
        decision_id=mock_decision.decision_id,
        mode="execution",
    )
    request_id = str(req["request_id"])

    result = {
        "summary": "实施完毕且验证通过",
        "changed_files": [
            "src/services/dictionary_service.py",
            "tests/test_services.py",
        ],
        "chg_updates": ["CHG-SCPT-2026-002: completed"],
        "artifacts": ["reports/summary.txt"],
        "verification": {
            "lint_result": "PASS",
            "test_result": "pytest: 5 passed, 0 failed",
        },
    }

    closed = service.close_request(request_id, result=result)
    assert closed["status"] == "consumed"
    assert closed["closure"]["closed_by"] == "pm-workflow"


def test_closure_rejects_changed_files_out_of_approved_scope(
    tmp_path: Path,
    mock_decision: DecisionPackageDTO,
) -> None:
    """测试修改文件超出决策包 approved_files 白名单时被硬门禁阻断"""
    service = AiHandoffService(tmp_path)
    chg_file = tmp_path / "CHG-SCPT-2026-002.md"
    chg_file.write_text("# CHG-SCPT-2026-002\n", encoding="utf-8", errors="replace")

    req = service.create_request(
        project_id="SW-2026-009",
        executor_skill="fullstack-engineer",
        summary="越界实施测试",
        change_id="CHG-SCPT-2026-002",
        decision_id=mock_decision.decision_id,
        mode="execution",
    )
    request_id = str(req["request_id"])

    result = {
        "summary": "越界修改未授权文件",
        "changed_files": [
            "src/services/dictionary_service.py",
            "src/controllers/unauthorized_controller.py",  # 越界文件
        ],
        "chg_updates": ["CHG-SCPT-2026-002: completed"],
        "verification": {"test_result": "PASS"},
    }

    with pytest.raises(HandoffValidationError) as exc_info:
        service.close_request(request_id, result=result)

    assert "修改文件越界" in str(exc_info.value)
    assert "src/controllers/unauthorized_controller.py" in str(exc_info.value)


def test_closure_rejects_nonexistent_change_ticket(tmp_path: Path, mock_decision: DecisionPackageDTO) -> None:
    """测试关联虚构或物理不存在的变更单时被硬门禁阻断"""
    service = AiHandoffService(tmp_path)
    # 注意：不创建物理变更单文件

    req = service.create_request(
        project_id="SW-2026-009",
        executor_skill="fullstack-engineer",
        summary="虚构变更单测试",
        change_id="CHG-SCPT-2026-002",
        decision_id=mock_decision.decision_id,
        mode="execution",
    )
    request_id = str(req["request_id"])

    fake_chg = "CHG-FAKE-9999-NONEXISTENT"
    result = {
        "summary": "关联不存在的变更单尝试收口",
        "changed_files": ["src/services/dictionary_service.py"],
        "chg_updates": [f"{fake_chg}: completed"],
        "verification": {"test_result": "PASS"},
    }

    with pytest.raises(HandoffValidationError) as exc_info:
        service.close_request(request_id, result=result)

    assert "关联变更单在工作空间中不存在" in str(exc_info.value)


def test_closure_rejects_nonexistent_or_empty_artifact(
    tmp_path: Path,
    mock_decision: DecisionPackageDTO,
) -> None:
    """测试声明为文件路径的交付物在磁盘上不存在或为空时被硬门禁阻断"""
    service = AiHandoffService(tmp_path)
    chg_file = tmp_path / "CHG-SCPT-2026-002.md"
    chg_file.write_text("# CHG-SCPT-2026-002\n", encoding="utf-8", errors="replace")

    req = service.create_request(
        project_id="SW-2026-009",
        executor_skill="fullstack-engineer",
        summary="交付物真实性测试",
        change_id="CHG-SCPT-2026-002",
        decision_id=mock_decision.decision_id,
        mode="execution",
    )
    request_id = str(req["request_id"])

    # 1. 不存在的文件路径交付物
    result_nonexistent = {
        "summary": "虚构文件交付物",
        "changed_files": ["src/services/dictionary_service.py"],
        "chg_updates": ["CHG-SCPT-2026-002: completed"],
        "artifacts": ["dist/nonexistent_build.tar.gz"],
        "verification": {"test_result": "PASS"},
    }
    with pytest.raises(HandoffValidationError) as exc_info:
        service.close_request(request_id, result=result_nonexistent)
    assert "交付物声明的文件在磁盘上不存在或为空" in str(exc_info.value)
    assert "dist/nonexistent_build.tar.gz" in str(exc_info.value)

    # 2. 大小为 0 的空文件交付物
    empty_file = tmp_path / "empty_output.log"
    empty_file.write_text("", encoding="utf-8", errors="replace")

    result_empty = {
        "summary": "空文件交付物",
        "changed_files": ["src/services/dictionary_service.py"],
        "chg_updates": ["CHG-SCPT-2026-002: completed"],
        "artifacts": ["empty_output.log"],
        "verification": {"test_result": "PASS"},
    }
    with pytest.raises(HandoffValidationError) as exc_info:
        service.close_request(request_id, result=result_empty)
    assert "交付物声明的文件在磁盘上不存在或为空" in str(exc_info.value)
    assert "empty_output.log" in str(exc_info.value)


def test_closure_rejects_failed_verification_result(
    tmp_path: Path,
    mock_decision: DecisionPackageDTO,
) -> None:
    """测试 verification 中包含 FAIL / FAILED / error 等失败标识时被硬门禁阻断"""
    service = AiHandoffService(tmp_path)
    chg_file = tmp_path / "CHG-SCPT-2026-002.md"
    chg_file.write_text("# CHG-SCPT-2026-002\n", encoding="utf-8", errors="replace")

    req = service.create_request(
        project_id="SW-2026-009",
        executor_skill="fullstack-engineer",
        summary="验证失败收口测试",
        change_id="CHG-SCPT-2026-002",
        decision_id=mock_decision.decision_id,
        mode="execution",
    )
    request_id = str(req["request_id"])

    # 1. test_result 明确失败
    result_test_failed = {
        "summary": "测试失败仍尝试收口",
        "changed_files": ["src/services/dictionary_service.py"],
        "chg_updates": ["CHG-SCPT-2026-002: completed"],
        "verification": {
            "lint_result": "PASS",
            "test_result": "FAILED: 2 failed, 3 passed",
        },
    }
    with pytest.raises(HandoffValidationError) as exc_info:
        service.close_request(request_id, result=result_test_failed)
    assert "验证结果显示失败，禁止收口" in str(exc_info.value)

    # 2. lint_result 包含错误
    result_lint_error = {
        "summary": "Lint 失败仍尝试收口",
        "changed_files": ["src/services/dictionary_service.py"],
        "chg_updates": ["CHG-SCPT-2026-002: completed"],
        "verification": {
            "lint_result": "error: ruff check found 2 violations",
            "test_result": "PASS",
        },
    }
    with pytest.raises(HandoffValidationError) as exc_info:
        service.close_request(request_id, result=result_lint_error)
    assert "验证结果显示失败，禁止收口" in str(exc_info.value)

