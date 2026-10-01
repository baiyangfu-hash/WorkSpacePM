"""单元测试：变更单实质内容防御门禁与自动注入引擎（Substance Control & Injection）"""

import json
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from auto_pm.change.constants import ChangeRequest, TransitionGuardError

from auto_pm.application.core.pm_closure_service import PmClosureError, PmClosureService
from auto_pm.domain.change.guard_checker import TransitionGuardChecker
from auto_pm.domain.change.substance_checker import SubstanceChecker
from auto_pm.domain.change.substance_injector import SubstanceInjectionError, SubstanceInjector
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

    def get_mission(self, mission_id: str) -> Any:
        return SimpleNamespace(
            objective="Fix add()", acceptance_criteria=("add(2, 3) == 5",)
        )

    def get_work(self, work_id: str) -> Any:
        return SimpleNamespace(scope_paths=("SW-TEST-001/src/calc.py",))

    def get_run(self, run_id: str) -> Any:
        return SimpleNamespace(git_head="8b7f199a527e5b6f0c1d2e3f4a5b6c7d8e9f0a1b")


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


_TEMPLATE_CHG = """# {change_id}

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

### 6.1 项目约束影响（PMBOK五大约束）

| 约束维度 | 影响程度 | 影响描述 | 应对措施 |
|---------|:--------:|----------|----------|
| **范围(Scope)** | □无 □低 □中 □高 |  |  |
| **进度(Schedule)** | □无 □低 □中 □高 | 延迟___天 |  |

**缓解措施**（风险应对策略）：
（待填写）

### 6.3 变更传播链（跨领域变更必填！）

**本次变更传播链:**
```
[___________] → [___________] → [___________]
     ↓               ↓               ↓
  (领域)          (领域)           (领域)
```

**关联变更单清单:**
| 关联单号 | 关联领域 | 关联原因 | 状态 |
|----------|----------|----------|:----:|
| CHG-______ |  |  | □待发起 □已发起 □已完成 |

## 8. 变更审批

### 8.2 审批结论
| 结论 | □ 通过 □ 有条件通过(附条件) □ 驳回(附原因) □ 拒绝(附原因) |
|------|----------------------------------------------------------|

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
| 结论 | □ 全部通过,可关闭 □ 部分不通过,需返工 □ 需补充验证 |
|------|-------------------------------------------------------|
"""

_APPROVAL_ROW = "| 结论 | □ 通过 □ 有条件通过(附条件) □ 驳回(附原因) □ 拒绝(附原因) |"
_PLACEHOLDERS = ("（待填写）", "(待填写)", "待补充", "[在此填写", "[___________]")


def _change_facts() -> dict[str, str]:
    return {
        "baseline_ref": "8b7f199a527e",
        "scope_files": "SW-TEST-001/src/calc.py\nSW-TEST-001/tests/test_calc.py",
        "objective": "Fix add()",
        "acceptance": "add(2, 3) == 5\nadd(-1, 1) == 0",
        "checkpoint_id": "CP-SW008-PMF-C05-002",
    }


def _write_template_chg(root: Path, change_id: str, text: str | None = None) -> Path:
    directory = root / "changes"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{change_id}.md"
    path.write_text((text or _TEMPLATE_CHG).format(change_id=change_id), encoding="utf-8")
    return path


def _inject(
    root: Path, change_id: str, facts: dict[str, str] | None
) -> Path:
    return SubstanceInjector.inject_closure_evidence(
        root,
        change_number=change_id,
        target_path=f"change://{change_id}",
        evidence=_closure_evidence(change_id),
        change_facts=facts,
    )


def test_template_shaped_change_is_completed_from_facts_and_replays_byte_identically(
    tmp_path: Path,
) -> None:
    target = _write_template_chg(tmp_path, "CHG-SCPT-2026-281")

    result = _inject(tmp_path, "CHG-SCPT-2026-281", _change_facts())

    content = result.read_text(encoding="utf-8")
    assert result == target
    assert not [item for item in _PLACEHOLDERS if item in content]
    assert (
        "| 涉及文件/交付物 | 基线 8b7f199a527e 中的范围文件：<br>SW-TEST-001/src/calc.py"
        "<br>SW-TEST-001/tests/test_calc.py |"
    ) in content
    assert "| 关键参数/配置 | 需求：Fix add() |" in content
    assert (
        "| 涉及文件/交付物 | 按批准范围修改：<br>SW-TEST-001/src/calc.py"
        "<br>SW-TEST-001/tests/test_calc.py<br>Checkpoint CP-SW008-PMF-C05-002 |"
    ) in content
    assert "| 关键参数/配置 | 验收条件：add(2, 3) == 5；add(-1, 1) == 0 |" in content
    assert "范围限定于批准的文件清单；在隔离工作树执行；" in content
    assert "[本次变更仅涉及 SCPT 领域] → [无跨领域传播] → [无需联动]" in content
    assert "| **验证结论** | Closure CLOSURE-0123456789ABCDEF01234567" in content
    assert content.count("| 结论 |") == 1
    assert _APPROVAL_ROW in content
    assert content.count("PM-CLOSURE-EVIDENCE") == 1
    # The stricter transition checker only objects to the untouched related-CHG list row.
    assert all("CHG-______" in item for item in SubstanceChecker.check_placeholders(content))

    replay = _inject(tmp_path, "CHG-SCPT-2026-281", _change_facts())
    assert replay.read_text(encoding="utf-8") == content


def test_placeholders_are_still_refused_without_facts_and_nothing_is_written(
    tmp_path: Path,
) -> None:
    target = _write_template_chg(tmp_path, "CHG-SCPT-2026-282")
    before = target.read_bytes()

    with pytest.raises(SubstanceInjectionError, match="空壳或占位"):
        _inject(tmp_path, "CHG-SCPT-2026-282", None)

    assert target.read_bytes() == before


def test_hostile_fact_text_cannot_break_the_tables_or_inject_regex_templates(
    tmp_path: Path,
) -> None:
    _write_template_chg(tmp_path, "CHG-SCPT-2026-283")
    facts = _change_facts()
    facts["objective"] = "a | b\nc \\g<1> " + "x" * 300
    facts["scope_files"] = "p|q.py\n\n" + "y" * 300 + ".py"

    content = _inject(tmp_path, "CHG-SCPT-2026-283", facts).read_text(encoding="utf-8")

    rows = [line for line in content.splitlines() if "需求：" in line]
    assert len(rows) == 1
    assert rows[0].count("|") == 3
    assert "a / b c \\g<1> " in rows[0]
    assert len(rows[0].split("需求：", 1)[1]) <= 202
    file_rows = [line for line in content.splitlines() if "范围文件：" in line]
    assert len(file_rows) == 1
    assert file_rows[0].count("|") == 3
    assert "p/q.py<br>" in file_rows[0]
    assert "y" * 201 not in file_rows[0]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda facts: facts.pop("objective"),
        lambda facts: facts.update({"extra": "x"}),
        lambda facts: facts.update({"acceptance": "  "}),
    ],
    ids=["missing-key", "extra-key", "blank-value"],
)
def test_change_facts_must_be_exactly_the_agreed_non_empty_keys(
    tmp_path: Path, mutate: Callable[[dict[str, str]], object]
) -> None:
    target = _write_template_chg(tmp_path, "CHG-SCPT-2026-284")
    before = target.read_bytes()
    facts = _change_facts()
    mutate(facts)

    with pytest.raises(SubstanceInjectionError, match="change_facts"):
        _inject(tmp_path, "CHG-SCPT-2026-284", facts)

    assert target.read_bytes() == before


def test_a_change_without_any_conclusion_row_is_refused_without_writing(tmp_path: Path) -> None:
    text = _TEMPLATE_CHG.replace(
        "### 10.3 验证结论\n| 结论 | □ 全部通过,可关闭 □ 部分不通过,需返工 □ 需补充验证 |\n"
        "|------|-------------------------------------------------------|\n",
        "",
    )
    target = _write_template_chg(tmp_path, "CHG-SCPT-2026-285", text)
    before = target.read_bytes()

    with pytest.raises(SubstanceInjectionError, match="§10.3 验证结论字段"):
        _inject(tmp_path, "CHG-SCPT-2026-285", _change_facts())

    assert target.read_bytes() == before
