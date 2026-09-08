from __future__ import annotations

import json
from pathlib import Path

import pytest
from auto_pm.core.ai_handoff_service import (
    AiHandoffService,
    HandoffConflictError,
    HandoffError,
    HandoffValidationError,
)


def test_list_pending_normalizes_handoff_v2_defaults(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """最小交接包也应被补齐为可消费的 V2 默认结构。"""
    workspace = tmp_path / "workspace"
    handoff_dir = workspace / ".auto-pm" / "handoffs"
    handoff_dir.mkdir(parents=True)
    payload = {
        "request_id": "AI-20260813-001",
        "project_id": "SW-2026-008",
        "executor_skill": "fullstack-engineer",
        "summary": "完成变更中心状态筛选改造",
    }
    (handoff_dir / "AI-20260813-001.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    service = AiHandoffService(workspace)
    handoffs = service.list_pending("SW-2026-008")

    assert len(handoffs) == 1
    handoff = handoffs[0]
    assert handoff["status"] == "pending"
    assert handoff["changed_files"] == []
    assert handoff["verification"]["other_checks"] == []
    assert handoff["product_impact"]["needs_user_validation"] is False
    assert handoff["pm_closure"]["required"] is True
    assert handoff["pm_closure"]["suggested_status"] == "pending_review"


def test_list_pending_skips_consumed_and_invalid_handoffs(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """只返回字段完整且状态为 pending 的交接包。"""
    workspace = tmp_path / "workspace"
    handoff_dir = workspace / ".auto-pm" / "handoffs"
    handoff_dir.mkdir(parents=True)
    valid_payload = {
        "request_id": "AI-20260813-002",
        "project_id": "SW-2026-008",
        "executor_skill": "plc-electrical-engineer",
        "summary": "待 PM 收口",
    }
    consumed_payload = {
        "request_id": "AI-20260813-003",
        "project_id": "SW-2026-008",
        "executor_skill": "fullstack-engineer",
        "summary": "已被消费",
        "status": "consumed",
    }
    invalid_payload = {
        "request_id": "AI-20260813-004",
        "project_id": "SW-2026-008",
        "executor_skill": "",
        "summary": "缺少执行技能",
    }
    (handoff_dir / "valid.json").write_text(
        json.dumps(valid_payload, ensure_ascii=False), encoding="utf-8"
    )
    (handoff_dir / "consumed.json").write_text(
        json.dumps(consumed_payload, ensure_ascii=False), encoding="utf-8"
    )
    (handoff_dir / "invalid.json").write_text(
        json.dumps(invalid_payload, ensure_ascii=False), encoding="utf-8"
    )

    service = AiHandoffService(workspace)
    handoffs = service.list_pending()

    assert [handoff["request_id"] for handoff in handoffs] == ["AI-20260813-002"]
    assert service.get_pending("AI-20260813-002") is not None
    assert service.get_pending("AI-20260813-003") is None


def test_validate_product_impact_detects_empty_and_platitudes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """product_impact 校验器能识别缺失假设与泛化套话。"""
    service = AiHandoffService(tmp_path)

    # 1. 缺失假设
    r1 = service.validate_product_impact({"hypothesis_id": "", "engineering_signal": "有效信号"})
    assert r1["valid"] is False
    assert any("hypothesis_id" in w for w in r1["warnings"])

    # 2. 缺失工程信号
    r2 = service.validate_product_impact({"hypothesis_id": "HYP-001", "engineering_signal": ""})
    assert r2["valid"] is False
    assert any("engineering_signal" in w for w in r2["warnings"])

    # 3. 泛化套话拦截
    r3 = service.validate_product_impact(
        {"hypothesis_id": "HYP-001", "engineering_signal": "优化了代码"}
    )
    assert r3["valid"] is False
    assert any("泛化" in w for w in r3["warnings"])

    # 4. 正常有效信号
    r4 = service.validate_product_impact(
        {
            "hypothesis_id": "HYP-DJ009-001",
            "engineering_signal": "在 FB_1002 移载状态机引入双路安全区互锁，未达安全高度禁止推料",
        }
    )
    assert r4["valid"] is True
    assert len(r4["warnings"]) == 0


def test_create_request_is_atomic_and_idempotent(tmp_path) -> None:  # type: ignore[no-untyped-def]
    service = AiHandoffService(tmp_path)

    first = service.create_request(
        "SW-2026-008",
        "fullstack-engineer",
        "实现 handoff CLI",
        request_id="AI-20260901-WBS2",
        mode="grooming",
        specs=["PM-042"],
    )
    second = service.create_request(
        "SW-2026-008",
        "fullstack-engineer",
        "实现 handoff CLI",
        request_id="AI-20260901-WBS2",
        mode="grooming",
        specs=["PM-042"],
    )

    assert first["request_id"] == second["request_id"]
    assert first["schema_version"] == "handoff.v1"
    assert Path(first["file"]).is_file()
    assert not list(service.inbox_dir.glob("*.tmp"))


def test_create_request_rejects_path_like_identity(tmp_path) -> None:  # type: ignore[no-untyped-def]
    service = AiHandoffService(tmp_path)

    with pytest.raises(HandoffValidationError):
        service.create_request(
            "../outside",
            "fullstack-engineer",
            "不应创建",
        )
    with pytest.raises(HandoffValidationError):
        service.create_request(
            "SW-2026-008",
            "fullstack-engineer",
            "不应创建",
            request_id="../outside",
        )


def test_close_requires_evidence_and_change_record(tmp_path) -> None:  # type: ignore[no-untyped-def]
    service = AiHandoffService(tmp_path)
    service.create_request(
        "SW-2026-008",
        "fullstack-engineer",
        "执行一项变更",
        request_id="AI-20260901-CLOSE",
    )

    with pytest.raises(HandoffValidationError, match="验证证据"):
        service.close_request("AI-20260901-CLOSE")

    with pytest.raises(HandoffValidationError, match="chg_updates"):
        service.close_request(
            "AI-20260901-CLOSE",
            result={
                "changed_files": ["some/file.py"],
                "verification": {"test_result": "PASS"},
            },
        )


def test_close_is_idempotent_and_rejects_conflicting_retry(tmp_path) -> None:  # type: ignore[no-untyped-def]
    service = AiHandoffService(tmp_path)
    (tmp_path / "CHG-PLC-2026-001.md").write_text("# verified\n", encoding="utf-8")
    service.create_request(
        "SW-2026-008",
        "plc-electrical-engineer",
        "执行静态 PLC 验收",
        request_id="AI-20260901-IDEMP",
    )
    result = {
        "summary": "静态验收通过",
        "verification": {
            "lint_result": "PASS",
            "test_result": "PASS",
        },
        "changed_files": ["DJ-2026-005/TEC.md"],
        "chg_updates": ["CHG-PLC-2026-001: verified"],
    }

    first = service.close_request(
        "AI-20260901-IDEMP",
        result=result,
        idempotency_key="close-001",
    )
    second = service.close_request(
        "AI-20260901-IDEMP",
        result=result,
        idempotency_key="close-001",
    )

    assert first["status"] == "consumed"
    assert second["closure"] == first["closure"]
    with pytest.raises(HandoffConflictError):
        service.close_request(
            "AI-20260901-IDEMP",
            result={
                "summary": "不同的结果",
                "verification": {"test_result": "PASS"},
                "changed_files": ["DJ-2026-005/TEC.md"],
                "chg_updates": ["CHG-PLC-2026-002: verified"],
            },
            idempotency_key="close-002",
        )


def test_list_requests_filters_consumed_records(tmp_path) -> None:  # type: ignore[no-untyped-def]
    service = AiHandoffService(tmp_path)
    service.create_request(
        "SW-2026-008",
        "fullstack-engineer",
        "保留一条记录",
        request_id="AI-20260901-LIST",
    )
    service.close_request(
        "AI-20260901-LIST",
        result={"verification": {"other_checks": ["PASS"]}},
    )

    assert service.list_pending("SW-2026-008") == []
    consumed = service.list_requests(status="consumed")
    assert [item["request_id"] for item in consumed] == ["AI-20260901-LIST"]


def test_close_finds_legacy_file_name(tmp_path) -> None:  # type: ignore[no-untyped-def]
    workspace = tmp_path / "workspace"
    handoff_dir = workspace / ".auto-pm" / "handoffs"
    handoff_dir.mkdir(parents=True)
    payload = {
        "request_id": "AI-20260901-LEGACY",
        "project_id": "SW-2026-008",
        "executor_skill": "fullstack-engineer",
        "summary": "兼容历史文件名",
    }
    (handoff_dir / "legacy-result.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )

    service = AiHandoffService(workspace)
    closed = service.close_request(
        "AI-20260901-LEGACY",
        result={"verification": {"other_checks": ["PASS"]}},
    )

    assert closed["status"] == "consumed"
    assert closed["file"].endswith("legacy-result.json")


def test_preflight_validates_identity_without_consuming(tmp_path) -> None:  # type: ignore[no-untyped-def]
    service = AiHandoffService(tmp_path)
    service.create_request(
        "SW-2026-008",
        "fullstack-engineer",
        "预检 handoff",
        request_id="AI-20260901-PREFLIGHT",
    )
    result = {"verification": {"other_checks": ["preflight PASS"]}}

    report = service.preflight_close(
        "AI-20260901-PREFLIGHT",
        result=result,
        expected_project_id="SW-2026-008",
        expected_executor_skill="fullstack-engineer",
    )

    assert report["ok"] is True
    assert report["already_consumed"] is False
    assert service.get_pending("AI-20260901-PREFLIGHT")["status"] == "pending"


def test_failed_atomic_write_is_logged_and_retryable(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    service = AiHandoffService(tmp_path)
    service.create_request(
        "SW-2026-008",
        "fullstack-engineer",
        "注入一次写入故障",
        request_id="AI-20260901-RETRY",
    )
    result = {"verification": {"other_checks": ["retry PASS"]}}

    def fail_write(path, payload):  # type: ignore[no-untyped-def]
        raise OSError("injected write failure")

    monkeypatch.setattr(service, "_write_atomic", fail_write)
    with pytest.raises(HandoffError, match="可安全重试"):
        service.close_request("AI-20260901-RETRY", result=result)

    assert service.get_pending("AI-20260901-RETRY") is not None
    events = service.list_failure_events("AI-20260901-RETRY")
    assert events[-1]["phase"] == "commit"
    assert events[-1]["retryable"] is True
    assert not (service.inbox_dir / ".handoff.lock").exists()

    monkeypatch.undo()
    closed = service.retry_close("AI-20260901-RETRY", result=result)
    assert closed["status"] == "consumed"


def test_preflight_rejects_cross_project_consumption(tmp_path) -> None:  # type: ignore[no-untyped-def]
    service = AiHandoffService(tmp_path)
    service.create_request(
        "SW-2026-008",
        "fullstack-engineer",
        "拒绝跨项目消费",
        request_id="AI-20260901-IDENTITY",
    )

    with pytest.raises(HandoffConflictError, match="项目不匹配"):
        service.preflight_close(
            "AI-20260901-IDENTITY",
            result={"verification": {"other_checks": ["PASS"]}},
            expected_project_id="DJ-2026-005",
        )


def test_close_request_extracts_chg_from_path_with_domain_dir(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """修复验证：路径中包含子目录（如 .../CHG-SPEC/CHG-SPEC-2026-001.md）时不被误截断为 CHG-SPEC"""
    service = AiHandoffService(tmp_path)
    # 创建目标变更单文件
    chg_file = tmp_path / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-SPEC" / "CHG-SPEC-2026-001.md"
    chg_file.parent.mkdir(parents=True, exist_ok=True)
    chg_file.write_text("# 变更单\n\n## 3. 变更基本信息\n", encoding="utf-8")

    # 创建目标 changed_file
    target_code = tmp_path / "docs" / "rules.md"
    target_code.parent.mkdir(parents=True, exist_ok=True)
    target_code.write_text("content", encoding="utf-8")

    service.create_request(
        "SYS-2026-001",
        "fullstack-engineer",
        "测试 SPEC 路径提取",
        request_id="AI-20260901-SPEC-PATH",
    )

    result = {
        "summary": "通过",
        "verification": {"lint_result": "PASS"},
        "changed_files": ["docs/rules.md"],
        "chg_updates": ["04_监控/01_变更管理/01_变更单/CHG-SPEC/CHG-SPEC-2026-001.md: completed"],
    }

    closed = service.close_request("AI-20260901-SPEC-PATH", result=result)
    assert closed["status"] == "consumed"
