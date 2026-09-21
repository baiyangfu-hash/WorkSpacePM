"""单元测试：变更单实质内容防御门禁与自动注入引擎（Substance Control & Injection）"""

import json
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest
from auto_pm.change.constants import ChangeRequest, TransitionGuardError

from auto_pm.application.core.pm_closure_service import PmClosureError, PmClosureService
from auto_pm.domain.change.guard_checker import TransitionGuardChecker
from auto_pm.domain.change.substance_checker import SubstanceChecker
from auto_pm.domain.change.substance_injector import SubstanceInjector
from auto_pm.infrastructure.continuity_store import ContinuityStore


def test_substance_checker_catches_placeholders() -> None:
    """测试 SubstanceChecker 能够准确识别未填写的模板占位符"""
    cr = ChangeRequest(
        change_number="CHG-PLC-2026-999",
        project_id="DJ-2026-005",
        status="completed",
        has_section_7=True,
        has_section_8_approval=True,
        has_section_9=True,
        has_section_10_verify=True,
        section_10_conclusion="全部通过",
    )
    # 模拟包含占位符的章节
    cr.sections = {
        "5": "### 5.1 变更前\n| 涉及文件 | （待填写） |\n### 5.2 变更后\n| 涉及文件 | （待填写） |",
        "7": "| 1 | 任务 | 负责人 | 2026-09-03 | 2026-09-03 | - | 已完成 |",
        "9": "| 2026-09-03 | fubai | 实施 | 内容 | 成功 | - |",
        "10": "| 1 | 测试 | 标准 | 预期 | 实际 | 通过 | fubai | 2026-09-03 |\n| **验证结论** | 全部通过 |",
    }
    violations = SubstanceChecker.check_substance(cr)
    assert any("包含未替换占位符: '（待填写）'" in v for v in violations)


def test_substance_checker_passes_on_full_substance() -> None:
    """测试 SubstanceChecker 在变更单实质内容完整时全绿通过"""
    cr = ChangeRequest(
        change_number="CHG-PLC-2026-999",
        project_id="DJ-2026-005",
        status="completed",
        has_section_7=True,
        has_section_8_approval=True,
        has_section_9=True,
        has_section_10_verify=True,
        section_10_conclusion="全部验证通过，门禁全绿",
    )
    cr.sections = {
        "5": "### 5.1 变更前\n| 涉及文件 | FB_2001.scl |\n### 5.2 变更后\n| 涉及文件 | FB_2001.scl (增加2009报警) |",
        "7": "| 1 | 编写SCL | plc-engineer | 2026-09-03 | 2026-09-03 | - | 已完成 |",
        "9": "| 2026-09-03 | plc-engineer | 实施 | 完成常量挂接 | 成功 | - |",
        "10": "| 1 | plc check | 51 PASS | 51 PASS | 51 PASS | 通过 | plc-engineer | 2026-09-03 |\n| **验证结论** | 全部验证通过，门禁全绿 |",
    }
    violations = SubstanceChecker.check_substance(cr)
    assert violations == []


def test_substance_checker_blocks_empty_closure_evidence() -> None:
    """完成或关闭不能以空审批、实施、验证或结论伪造证据。"""
    cr = ChangeRequest(
        change_number="CHG-PLC-2026-998",
        status="completed",
        section_10_conclusion="",
    )
    cr.sections = {"5": "已实施", "7": "计划", "8": "审批", "9": "", "10": ""}
    cr.has_section_8_approval = False
    cr.has_section_9 = False
    cr.has_section_10_verify = False

    violations = SubstanceChecker.check_substance(cr)

    assert "§8.1 审批记录为空" in violations
    assert "§9 实施记录为空" in violations
    assert "§10.1 验证项清单为空" in violations
    assert "§10.3 验证结论为空" in violations


def test_substance_checker_blocks_example_change_numbers() -> None:
    """示例传播链中的 CHG-xxx/yyy 不得进入完成态。"""
    cr = ChangeRequest(change_number="CHG-PLC-2026-997", status="closed")
    cr.sections = {"5": "CHG-xxx → CHG-yyy"}

    violations = SubstanceChecker.check_substance(cr)

    assert "包含未替换占位符: 'CHG-xxx'" in violations
    assert "包含未替换占位符: 'CHG-yyy'" in violations


def test_transition_guard_blocks_empty_substance() -> None:
    """测试状态流转守卫在遇到空壳单据时抛出 TransitionGuardError 阻断"""
    guard = TransitionGuardChecker()
    cr = ChangeRequest(
        change_number="CHG-PLC-2026-999",
        project_id="DJ-2026-005",
        status="implementing",
        has_section_7=True,
        has_section_9=False,
        has_section_10_verify=False,
        section_10_conclusion="",
    )
    cr.sections = {
        "5": "### 5.1 变更前\n| 涉及文件 | （待填写） |\n### 5.2 变更后\n| 涉及文件 | （待填写） |",
    }
    with pytest.raises(TransitionGuardError) as exc_info:
        guard.check(cr, target_status="completed", approver="fubai", comment="")
    assert "包含未替换占位符" in str(exc_info.value)


def test_substance_injector_replaces_placeholders(tmp_path: Path) -> None:
    """测试 SubstanceInjector 物理回填与占位符擦除逻辑"""
    chg_dir = tmp_path / "01_变更单" / "CHG-PLC"
    chg_dir.mkdir(parents=True)
    chg_file = chg_dir / "CHG-PLC-2026-888.md"

    initial_content = """# CHG-PLC-2026-888

## 5. 变更内容

### 5.1 变更前（当前状态）
| 项目 | 当前值/描述 |
|------|-----------|
| 涉及文件/交付物 | （待填写） |
| 关键参数/配置 | （待填写） |

### 5.2 变更后（目标状态）
| 项目 | 目标值/描述 |
|------|-----------|
| 涉及文件/交付物 | （待填写） |
| 关键参数/配置 | （待填写） |

## 6. 变更影响分析
**缓解措施**（风险应对策略）：
（待填写）

## 7. 变更实施计划
| 序号 | 任务描述 | 负责人(角色) | 开始日期 | 完成日期 | 前置依赖 | 备注 |
|------|----------|-------------|----------|----------|----------|------|
| | | | | | | |

## 9. 变更实施记录
| 实施日期 | 实施人 | 实施任务 | 实施内容摘要 | 实施结果 | 备注 |
|----------|--------|----------|-------------|----------|------|
| | | | | | |

## 10. 变更验证
### 10.1 验证项清单
| # | 验证项 | 验证标准 | 预期结果 | 实际结果 | 状态 | 验证人 | 验证日期 |
|---|--------|----------|----------|----------|------|--------|----------|
| | | | | | | | |

### 10.3 验证结论
| **验证结论** | （待填写） |
"""
    chg_file.write_text(initial_content, encoding="utf-8")

    substance = {
        "before_state": {
            "files": ["FB_Test.scl"],
            "parameters": ["初始参数未设置"],
        },
        "after_state": {
            "files": ["FB_Test.scl"],
            "parameters": ["已配置看门狗超时"],
        },
        "implementation_tasks": [
            {"task": "编写看门狗逻辑", "result": "成功"}
        ],
        "verification_records": [
            {"item": "门禁自检", "standard": "通过", "actual": "51 PASS", "passed": True}
        ],
        "verification_conclusion": "全部验证通过，门禁全绿",
    }

    updated_file = SubstanceInjector.inject(
        workspace_root=tmp_path,
        change_number="CHG-PLC-2026-888",
        substance=substance,
        changed_files=["FB_Test.scl"],
        executor_id="plc-electrical-engineer",
    )

    result_text = updated_file.read_text(encoding="utf-8")
    assert "（待填写）" not in result_text
    assert "FB_Test.scl" in result_text
    assert "已配置看门狗超时" in result_text
    assert "编写看门狗逻辑" in result_text
    assert "全部验证通过，门禁全绿" in result_text


def test_closure_evidence_injection_is_targeted_and_idempotent(tmp_path: Path) -> None:
    """C06 只能将已验证 evidence 写入唯一 CHG，重放不产生重复记录。"""
    target = _write_closure_chg(tmp_path, "CHG-SCPT-2026-280")
    evidence = _closure_evidence("CHG-SCPT-2026-280")

    first = SubstanceInjector.inject_closure_evidence(
        tmp_path,
        change_number="CHG-SCPT-2026-280",
        target_path="change://CHG-SCPT-2026-280",
        evidence=evidence,
    )
    first_content = first.read_text(encoding="utf-8")
    second = SubstanceInjector.inject_closure_evidence(
        tmp_path,
        change_number="CHG-SCPT-2026-280",
        target_path="change://CHG-SCPT-2026-280",
        evidence=evidence,
    )

    assert first == target == second
    assert second.read_text(encoding="utf-8") == first_content
    assert first_content.count("PM-CLOSURE-EVIDENCE") == 1
    assert evidence["closure_id"] in first_content
    assert evidence["checkpoint_id"] in first_content
    assert "（待填写）" not in first_content
    assert SubstanceChecker.check_placeholders(first_content) == []


def test_closure_evidence_rejects_non_target_and_has_zero_side_effects(tmp_path: Path) -> None:
    """target_path 漂移或多个同名 CHG 均必须在写入前拒绝。"""
    target = _write_closure_chg(tmp_path, "CHG-SCPT-2026-280")
    untouched = target.read_text(encoding="utf-8")
    _write_closure_chg(tmp_path / "duplicate", "CHG-SCPT-2026-280")

    with pytest.raises(ValueError, match="outbox target_path"):
        SubstanceInjector.inject_closure_evidence(
            tmp_path,
            change_number="CHG-SCPT-2026-280",
            target_path="change://CHG-SCPT-2026-999",
            evidence=_closure_evidence("CHG-SCPT-2026-280"),
        )
    with pytest.raises(ValueError, match="唯一存在"):
        SubstanceInjector.inject_closure_evidence(
            tmp_path,
            change_number="CHG-SCPT-2026-280",
            target_path="change://CHG-SCPT-2026-280",
            evidence=_closure_evidence("CHG-SCPT-2026-280"),
        )

    assert target.read_text(encoding="utf-8") == untouched


def test_pm_closure_service_only_accepts_verified_pending_outbox(tmp_path: Path) -> None:
    """C06 service validates the C05 identity chain before any CHG write."""
    _write_closure_chg(tmp_path, "CHG-SCPT-2026-280")
    payload = _prepared_closure_payload("CHG-SCPT-2026-280")
    closure_id = str(payload["closure"]["closure_id"])
    service = PmClosureService(tmp_path, store=cast(ContinuityStore, _ClosureStore(payload)))

    updated = service.inject_prepared_change_substance(closure_id)
    assert str(payload["closure"]["checkpoint_id"]) in updated.read_text(encoding="utf-8")

    tampered = _prepared_closure_payload("CHG-SCPT-2026-280")
    tampered_payload = json.loads(str(tampered["outbox"]["payload_json"]))
    tampered_payload["change_id"] = "CHG-SCPT-2026-999"
    tampered["outbox"]["payload_json"] = json.dumps(
        tampered_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    service = PmClosureService(tmp_path, store=cast(ContinuityStore, _ClosureStore(tampered)))
    before = updated.read_text(encoding="utf-8")
    with pytest.raises(PmClosureError, match="identity"):
        service.inject_prepared_change_substance(str(tampered["closure"]["closure_id"]))
    assert updated.read_text(encoding="utf-8") == before


def _closure_evidence(change_id: str) -> dict[str, str]:
    return {
        "closure_id": "CLOSURE-0123456789ABCDEF01234567",
        "work_id": "WORK-SW008-PMF-C05-001",
        "run_id": "RUN-SW008-PMF-C05-002",
        "checkpoint_id": "CP-SW008-PMF-C05-002",
        "change_id": change_id,
        "decision_id": "DEC-20260920-4BAC1FE5",
        "step_id": "CSTEP-0123456789ABCDEF01234567",
        "outbox_id": "OUTBOX-0123456789ABCDEF01234567",
        "request_hash": "a" * 64,
        "payload_hash": "b" * 64,
        "prepared_on": "2026-09-20",
    }


def _prepared_closure_payload(change_id: str) -> dict[str, dict[str, object]]:
    evidence = _closure_evidence(change_id)
    payload = {
        "schema_version": "closure-outbox.v1",
        "closure_id": evidence["closure_id"],
        "step_id": evidence["step_id"],
        "mission_id": "MISSION-SW008-C05-001",
        "change_id": change_id,
        "checkpoint_id": evidence["checkpoint_id"],
        "operation": "CHANGE_SUBSTANCE",
    }
    canonical_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "closure": {
            "closure_id": evidence["closure_id"],
            "mission_id": payload["mission_id"],
            "work_id": evidence["work_id"],
            "run_id": evidence["run_id"],
            "checkpoint_id": evidence["checkpoint_id"],
            "change_id": change_id,
            "decision_id": evidence["decision_id"],
            "state": "PREPARED",
            "request_hash": evidence["request_hash"],
            "version": 1,
            "created_at": "2026-09-20T12:00:00+00:00",
            "updated_at": "2026-09-20T12:00:00+00:00",
        },
        "step": {
            "step_id": evidence["step_id"],
            "closure_id": evidence["closure_id"],
            "sequence": 1,
            "step_kind": "CHANGE_SUBSTANCE",
            "state": "PENDING",
            "attempt_count": 0,
            "last_error": None,
            "created_at": "2026-09-20T12:00:00+00:00",
            "updated_at": "2026-09-20T12:00:00+00:00",
        },
        "outbox": {
            "outbox_id": evidence["outbox_id"],
            "closure_id": evidence["closure_id"],
            "step_id": evidence["step_id"],
            "artifact_kind": "CHANGE_SUBSTANCE",
            "target_path": f"change://{change_id}",
            "payload_json": canonical_payload,
            "payload_hash": sha256(canonical_payload.encode("utf-8")).hexdigest(),
            "published_at": None,
            "created_at": "2026-09-20T12:00:00+00:00",
        },
    }


class _ClosureStore:
    def __init__(self, payload: dict[str, dict[str, object]]) -> None:
        self._payload = payload

    def get_closure_preparation(self, closure_id: str) -> dict[str, dict[str, object]]:
        assert closure_id == self._payload["closure"]["closure_id"]
        return self._payload


def _write_closure_chg(root: Path, change_id: str) -> Path:
    directory = root / "changes"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{change_id}.md"
    path.write_text(
        f"""# {change_id}

## 9. 变更实施记录
| 实施日期 | 实施人 | 实施任务 | 实施内容摘要 | 实施结果 | 备注 |
|----------|--------|----------|-------------|----------|------|
| | | | | | |

## 10. 变更验证
### 10.1 验证项清单
| # | 验证项 | 验证标准 | 预期结果 | 实际结果 | 状态 | 验证人 | 验证日期 |
|---|--------|----------|----------|----------|------|--------|----------|
| | | | | | | | |

### 10.3 验证结论
| **验证结论** | （待填写） |
""",
        encoding="utf-8",
    )
    return path
