"""PmClosureSagaCoordinator 单元测试与端到端事务验证。

测试覆盖：
- 正常全流程 Saga 顺序流转与 checkpoint 记录
- 在 chg_transitioned 或 ledger_reconciled 步骤进行故障注入（simulate_fail_at）
- resume_saga 能从断点检查点继续并成功收尾，且已完成步骤不发生重复执行（防双写）
- compensate_saga 能将已备份文件原样还原，状态变为 compensated
- 已 completed 的 saga 具有幂等性
- CLI handoff saga status/resume/compensate 命令组调用
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from auto_pm.application.core.ai_handoff_service import AiHandoffService
from auto_pm.application.core.pm_saga_service import (
    PmClosureSagaCoordinator,
    SagaExecutionError,
    SagaStatus,
    SagaStep,
)
from auto_pm.contracts.decision_package import DecisionPackageDTO
from auto_pm.domain.change.decision_service import DecisionService
from auto_pm.ui.cli.__main__ import cli


@pytest.fixture
def project_setup(tmp_path: Path) -> dict[str, Any]:
    """初始化测试用项目结构，包括决策包、变更单、台账、PM_SESSION与产物。"""
    project_id = "SW-2026-008"
    change_id = "CHG-SCPT-2026-172"
    decision_id = "DEC-20260904-TEST0001"

    # 1. 创建决策包
    dec_service = DecisionService(tmp_path)
    dec_dto = DecisionPackageDTO(
        decision_id=decision_id,
        project_id=project_id,
        change_id=change_id,
        approved_scope="SYSTEM",
        approved_files=["src/core/saga.py", "tests/test_saga.py"],
        approver="fubai",
        approved_at="2026-09-04T00:00:00Z",
        decision_conclusion="approved",
    )
    dec_file = dec_service.decisions_dir / f"{decision_id}.json"
    dec_file.parent.mkdir(parents=True, exist_ok=True)
    dec_file.write_text(
        json.dumps(dec_dto.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
        errors="replace",
    )

    # 2. 创建变更单文件
    chg_dir = tmp_path / "04_监控" / "01_变更管理" / "01_变更单" / "CHG-SCPT"
    chg_dir.mkdir(parents=True, exist_ok=True)
    chg_file = chg_dir / f"{change_id}.md"
    chg_content = f"""# 变更单

## 1. 文档基础信息
**文档标题**：变更单

## 2. 版本变更记录
| 版本号 | 变更内容 | 变更人 | 变更日期 | 详细说明 |
|--------|----------|--------|----------|----------|
| V1.0.0 | 初始版本 | fubai | 2026-09-03 | 变更单创建 |

## 3. 变更基本信息
### 3.0 编号与项目
| 字段 | 内容 |
|------|------|
| 变更编号 | {change_id} |
| 项目名称 | {project_id} |
| 项目编号 | {project_id} |

### 3.1 技术领域（必选）
| 领域 | 选择 | 说明 |
|------|------|------|
| ☑ **SCPT** Python脚本 | **选中** | 数据采集/MES接口/上位机应用 |

### 3.2 业务性质（必选）
| 性质 | 选择 | 典型场景 |
|------|------|----------|
| ☑ **OPT** 优化改进 | **选中** | 性能提升/可维护性改善/重构 |

### 3.3 影响范围（可多选）
| 范围 | 选择 | 审批要求 |
|------|------|----------|
| ☑ **SYSTEM** 系统级变更 | **选中** | 系统级变更 |

### 3.4 申请信息
| 字段 | 内容 |
|------|------|
| 变更申请人 | fubai |
| 申请日期 | 2026-09-03 |
| 预计实施日期 | 2026-09-03 |
| 紧急程度 | ☑一般 □紧急 □非常紧急 |
| 变更状态 | implementing |

## 4. 变更原因
**变更背景**：PM Saga 事务测试
**变更必要性**：验证 8 步 WAL 与 Checkpoint

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
**缓解措施**：
（待填写）

## 7. 变更实施计划
| 序号 | 任务描述 | 负责人(角色) | 开始日期 | 完成日期 | 前置依赖 | 备注 |
|------|----------|-------------|----------|----------|----------|------|

## 8. 变更审批
### 8.1 审批流程（按影响范围分级）
| 审批环节 | 审批人 | 审批意见 | 审批日期 | 签字/电子签章 |
|----------|--------|----------|----------|---------------|
| **已批准** | fubai | 同意 | 2026-09-03 | fubai |

## 9. 变更实施记录
| 实施日期 | 实施人 | 实施任务 | 实施内容摘要 | 实施结果 | 备注 |
|----------|--------|----------|-------------|----------|------|

## 10. 变更验证
### 10.1 验证项清单
| # | 验证项 | 验证标准 | 预期结果 | 实际结果 | 状态 | 验证人 | 验证日期 |
|---|--------|----------|----------|----------|------|--------|----------|

### 10.3 验证结论
| 结论 | （待填写） |
"""
    chg_file.write_text(chg_content, encoding="utf-8", errors="replace")

    # 3. 创建台账文件
    ledger_dir = tmp_path / "04_监控" / "01_变更管理" / "02_变更记录"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    ledger_file = ledger_dir / "01_版本变更台账.md"
    ledger_content = f"""# 版本变更台账

> 记录项目所有变更单的索引与状态

## 变更单索引

| 序号 | 变更编号 | 领域 | 申请人 | 申请日期 | 变更描述 | 完成日期 | 状态 |
|------|----------|------|--------|----------|----------|----------|------|
| 1 | {change_id} | SCPT | fubai | 2026-09-03 | PM Saga 实施 | | 🔄实施中 |
"""
    ledger_file.write_text(ledger_content, encoding="utf-8", errors="replace")

    # 4. 创建 PM_SESSION 文件
    pm_session_file = tmp_path / f"PM_SESSION_{project_id}.md"
    pm_session_content = """# PM_SESSION_SW-2026-008

## 2. Current Focus
- 验证 Saga 事务机制

## 8. Handoff Notes
- 初始备注
"""
    pm_session_file.write_text(pm_session_content, encoding="utf-8", errors="replace")

    # 5. 创建真实非空的产物证据文件
    artifact_file = tmp_path / "reports" / "verification.log"
    artifact_file.parent.mkdir(parents=True, exist_ok=True)
    artifact_file.write_text("All checks passed!\n", encoding="utf-8", errors="replace")

    # 6. 创建待消费的 handoff 请求
    handoff_service = AiHandoffService(tmp_path)
    req = handoff_service.create_request(
        project_id=project_id,
        executor_skill="fullstack-engineer",
        summary="Saga 端到端验证任务",
        change_id=change_id,
        decision_id=decision_id,
        mode="execution",
    )

    # 7. 标准回执数据
    result: dict[str, Any] = {
        "summary": "Saga 实施完毕，验证全绿",
        "changed_files": ["src/core/saga.py", "tests/test_saga.py"],
        "chg_updates": [f"{change_id}: completed"],
        "artifacts": ["reports/verification.log"],
        "verification": {
            "lint_result": "PASS",
            "test_result": "pytest: 10 passed, 0 failed",
        },
        "change_substance": {
            "change_number": change_id,
            "before_state": {
                "files": ["src/core/saga.py"],
                "parameters": ["初始无事务保证"],
            },
            "after_state": {
                "files": ["src/core/saga.py"],
                "parameters": ["已落地 Saga WAL 事务日志"],
            },
            "implementation_tasks": [
                {
                    "task": "实现 PmClosureSagaCoordinator",
                    "role": "fullstack-engineer",
                    "result": "☑成功 □部分成功 □失败",
                }
            ],
            "verification_records": [
                {
                    "item": "自动化单测",
                    "standard": "通过",
                    "actual": "通过",
                    "passed": True,
                }
            ],
            "verification_conclusion": "全部通过,可关闭",
        },
    }

    return {
        "workspace_root": tmp_path,
        "project_id": project_id,
        "change_id": change_id,
        "decision_id": decision_id,
        "request_id": str(req["request_id"]),
        "chg_file": chg_file,
        "ledger_file": ledger_file,
        "pm_session_file": pm_session_file,
        "artifact_file": artifact_file,
        "result": result,
    }


def test_full_saga_success_flow_and_checkpoints(project_setup: Mapping[str, Any]) -> None:
    """测试正常全流程 Saga 顺序流转与 checkpoint 记录。"""
    ws = project_setup["workspace_root"]
    request_id = project_setup["request_id"]
    result = project_setup["result"]
    chg_file: Path = project_setup["chg_file"]
    ledger_file: Path = project_setup["ledger_file"]
    pm_session_file: Path = project_setup["pm_session_file"]

    coordinator = PmClosureSagaCoordinator(ws)
    saga = coordinator.execute_saga(request_id, result=result, actor="pm-tester")

    # 1. 断言 Saga 状态与完成步骤
    assert saga["status"] == SagaStatus.COMPLETED.value
    assert saga["current_step"] == SagaStep.COMPLETED.value
    expected_steps = [
        "preflight",
        "handoff_consumed",
        "substance_injected",
        "chg_transitioned",
        "ledger_reconciled",
        "feedback_recorded",
        "pm_session_recorded",
        "completed",
    ]
    assert saga["completed_steps"] == expected_steps

    # 2. 断言 8 个检查点按序记录
    checkpoints = saga["checkpoints"]
    assert len(checkpoints) == 8
    recorded_steps = [cp["step"] for cp in checkpoints]
    assert recorded_steps == expected_steps
    for cp in checkpoints:
        assert cp["status"] == "completed"

    # 3. 断言磁盘上的 WAL 日志持久化
    log_path = coordinator.saga_log_path(request_id)
    assert log_path.is_file()
    disk_saga = json.loads(log_path.read_text(encoding="utf-8", errors="replace"))
    assert disk_saga["status"] == "completed"
    assert disk_saga["saga_id"] == saga["saga_id"]

    # 4. 断言 handoff 状态变为 consumed
    handoff_service = AiHandoffService(ws)
    req = handoff_service.get_request(request_id)
    assert req is not None
    assert req["status"] == "consumed"
    assert req["closure"]["closed_by"] == "pm-tester"

    # 5. 断言 CHG 文件实质内容注入并流转到 completed
    chg_content = chg_file.read_text(encoding="utf-8", errors="replace")
    assert "| 变更状态 | completed |" in chg_content
    assert "（待填写）" not in chg_content
    assert "已落地 Saga WAL 事务日志" in chg_content

    # 6. 断言台账已自动对账修复为 ✅已关闭，0 差异
    ledger_content = ledger_file.read_text(encoding="utf-8", errors="replace")
    assert "✅已关闭" in ledger_content

    # 7. 断言 ai_feedback.json 正确生成
    fb_file = ws / ".auto-pm" / "ai_feedback.json"
    assert fb_file.is_file()
    fb_data = json.loads(fb_file.read_text(encoding="utf-8", errors="replace"))
    assert fb_data["status"] == "completed"
    assert fb_data["change_number"] == project_setup["change_id"]

    # 8. 断言 PM_SESSION 登记了收口记录
    pm_session_content = pm_session_file.read_text(encoding="utf-8", errors="replace")
    assert f"skill_handoff_{request_id}" in pm_session_content


def test_fault_injection_at_chg_transitioned(project_setup: Mapping[str, Any]) -> None:
    """测试在 chg_transitioned 步骤进行故障注入（simulate_fail_at），断言中断后生成完整的中间检查点。"""
    ws = project_setup["workspace_root"]
    request_id = project_setup["request_id"]
    result = project_setup["result"]

    coordinator = PmClosureSagaCoordinator(ws)
    with pytest.raises(SagaExecutionError) as exc_info:
        coordinator.execute_saga(
            request_id,
            result=result,
            simulate_fail_at="chg_transitioned",
        )

    assert "Simulated failure at step: chg_transitioned" in str(exc_info.value)

    # 断言中间检查点状态
    saga = coordinator.get_saga_status(request_id)
    assert saga is not None
    assert saga["status"] == SagaStatus.FAILED.value
    assert saga["current_step"] == "chg_transitioned"
    assert saga["completed_steps"] == [
        "preflight",
        "handoff_consumed",
        "substance_injected",
    ]
    checkpoints = saga["checkpoints"]
    assert len(checkpoints) == 4
    assert checkpoints[-1]["step"] == "chg_transitioned"
    assert checkpoints[-1]["status"] == "failed"


def test_fault_injection_at_ledger_reconciled(project_setup: Mapping[str, Any]) -> None:
    """测试在 ledger_reconciled 步骤进行故障注入，断言中断并生成前序检查点。"""
    ws = project_setup["workspace_root"]
    request_id = project_setup["request_id"]
    result = project_setup["result"]

    coordinator = PmClosureSagaCoordinator(ws)
    with pytest.raises(SagaExecutionError) as exc_info:
        coordinator.execute_saga(
            request_id,
            result=result,
            simulate_fail_at="ledger_reconciled",
        )

    assert "Simulated failure at step: ledger_reconciled" in str(exc_info.value)

    saga = coordinator.get_saga_status(request_id)
    assert saga is not None
    assert saga["status"] == SagaStatus.FAILED.value
    assert saga["current_step"] == "ledger_reconciled"
    assert saga["completed_steps"] == [
        "preflight",
        "handoff_consumed",
        "substance_injected",
        "chg_transitioned",
    ]
    checkpoints = saga["checkpoints"]
    assert len(checkpoints) == 5
    assert checkpoints[-1]["step"] == "ledger_reconciled"
    assert checkpoints[-1]["status"] == "failed"


def test_resume_saga_resumes_from_breakpoint_without_duplicate_execution(
    project_setup: Mapping[str, Any],
) -> None:
    """测试 resume_saga 能从检查点继续并成功收尾，且已完成步骤不发生重复执行（防双写）。"""
    ws = project_setup["workspace_root"]
    request_id = project_setup["request_id"]
    result = project_setup["result"]
    chg_file: Path = project_setup["chg_file"]

    coordinator = PmClosureSagaCoordinator(ws)
    # 步骤在 chg_transitioned 前被中断
    with pytest.raises(SagaExecutionError):
        coordinator.execute_saga(
            request_id,
            result=result,
            simulate_fail_at="chg_transitioned",
        )

    # 此时 CHG 文件 status 仍应为 implementing
    initial_chg = chg_file.read_text(encoding="utf-8", errors="replace")
    assert "| 变更状态 | implementing |" in initial_chg

    # 调用 resume_saga 从 chg_transitioned 断点处恢复
    resumed = coordinator.resume_saga(request_id)
    assert resumed["status"] == SagaStatus.COMPLETED.value
    assert resumed["completed_steps"] == [
        "preflight",
        "handoff_consumed",
        "substance_injected",
        "chg_transitioned",
        "ledger_reconciled",
        "feedback_recorded",
        "pm_session_recorded",
        "completed",
    ]

    # 断言后续步骤成功完成
    after_chg = chg_file.read_text(encoding="utf-8", errors="replace")
    assert "| 变更状态 | completed |" in after_chg

    # 检查点中已跳过 preflight 与 handoff_consumed，未发生重复追加
    checkpoints = resumed["checkpoints"]
    preflight_cps = [cp for cp in checkpoints if cp["step"] == "preflight"]
    assert len(preflight_cps) == 1
    consumed_cps = [cp for cp in checkpoints if cp["step"] == "handoff_consumed"]
    assert len(consumed_cps) == 1


def test_compensate_saga_restores_all_backup_files(project_setup: Mapping[str, Any]) -> None:
    """测试 compensate_saga 能将已备份文件原样还原，状态变为 compensated。"""
    ws = project_setup["workspace_root"]
    request_id = project_setup["request_id"]
    result = project_setup["result"]
    chg_file: Path = project_setup["chg_file"]
    handoff_file = ws / ".auto-pm" / "handoffs" / f"{request_id}.json"

    original_chg_content = chg_file.read_text(encoding="utf-8", errors="replace")
    original_handoff_content = handoff_file.read_text(encoding="utf-8", errors="replace")

    coordinator = PmClosureSagaCoordinator(ws)
    # 在 ledger_reconciled 步骤中断（此时 handoff已更新、chg已注入且已流转）
    with pytest.raises(SagaExecutionError):
        coordinator.execute_saga(
            request_id,
            result=result,
            simulate_fail_at="ledger_reconciled",
        )

    # 确认中断时文件已被修改
    modified_chg = chg_file.read_text(encoding="utf-8", errors="replace")
    assert modified_chg != original_chg_content
    assert "| 变更状态 | completed |" in modified_chg

    # 执行补偿回滚
    compensated = coordinator.compensate_saga(request_id, actor="pm-compensator")
    assert compensated["status"] == SagaStatus.COMPENSATED.value
    assert compensated["current_step"] == "compensated"

    # 断言所有被修改文件原样还原
    restored_chg = chg_file.read_text(encoding="utf-8", errors="replace")
    assert restored_chg == original_chg_content

    restored_handoff = handoff_file.read_text(encoding="utf-8", errors="replace")
    assert restored_handoff == original_handoff_content


def test_completed_saga_is_idempotent(project_setup: Mapping[str, Any]) -> None:
    """测试已 completed 的 saga 具有幂等性。"""
    ws = project_setup["workspace_root"]
    request_id = project_setup["request_id"]
    result = project_setup["result"]

    coordinator = PmClosureSagaCoordinator(ws)
    saga1 = coordinator.execute_saga(request_id, result=result)
    assert saga1["status"] == SagaStatus.COMPLETED.value

    # 重复执行 execute_saga，返回原结果，不发生任何重复操作
    saga2 = coordinator.execute_saga(request_id, result=result)
    assert saga2["status"] == SagaStatus.COMPLETED.value
    assert saga2["saga_id"] == saga1["saga_id"]

    # 重复执行 resume_saga，同样幂等返回
    saga3 = coordinator.resume_saga(request_id)
    assert saga3["status"] == SagaStatus.COMPLETED.value
    assert saga3["saga_id"] == saga1["saga_id"]


def test_close_with_saga_integration(project_setup: Mapping[str, Any]) -> None:
    """测试 AiHandoffService.close_with_saga 与 close_request(use_saga=True) 联动。"""
    ws = project_setup["workspace_root"]
    request_id = project_setup["request_id"]
    result = project_setup["result"]

    service = AiHandoffService(ws)
    consumed = service.close_request(request_id, result=result, use_saga=True)

    assert consumed["status"] == "consumed"
    assert consumed.get("saga_id") is not None
    assert consumed.get("saga_status") == "completed"

    saga_status = service.get_saga_status(request_id)
    assert saga_status is not None
    assert saga_status["status"] == "completed"


def test_cli_saga_commands(project_setup: Mapping[str, Any]) -> None:
    """测试 handoff saga status/resume/compensate CLI 命令组。"""
    ws = project_setup["workspace_root"]
    request_id = project_setup["request_id"]
    result = project_setup["result"]

    coordinator = PmClosureSagaCoordinator(ws)
    # 模拟失败生成 failed 状态日志
    with pytest.raises(SagaExecutionError):
        coordinator.execute_saga(
            request_id,
            result=result,
            simulate_fail_at="chg_transitioned",
        )

    runner = CliRunner()

    # 1. 测试 handoff saga status
    res = runner.invoke(
        cli,
        ["--workspace", str(ws), "handoff", "saga", "status", request_id, "--json-output"],
    )
    assert res.exit_code == 0
    status_json = json.loads(res.output)
    assert status_json["status"] == "failed"
    assert status_json["current_step"] == "chg_transitioned"

    # 2. 测试 handoff saga resume
    res_resume = runner.invoke(
        cli,
        ["--workspace", str(ws), "handoff", "saga", "resume", request_id, "--json-output"],
    )
    assert res_resume.exit_code == 0
    resume_json = json.loads(res_resume.output)
    assert resume_json["status"] == "completed"

    # 3. 再次 status 验证为 completed
    res_status2 = runner.invoke(
        cli,
        ["--workspace", str(ws), "handoff", "saga", "status", request_id],
    )
    assert res_status2.exit_code == 0
    assert "completed" in res_status2.output

    # 4. 测试 handoff saga compensate
    res_comp = runner.invoke(
        cli,
        ["--workspace", str(ws), "handoff", "saga", "compensate", request_id, "--json-output"],
    )
    assert res_comp.exit_code == 0
    comp_json = json.loads(res_comp.output)
    assert comp_json["status"] == "compensated"
