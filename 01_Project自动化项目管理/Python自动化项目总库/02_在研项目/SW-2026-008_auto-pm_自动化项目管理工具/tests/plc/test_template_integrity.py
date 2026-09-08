"""PLC 黄金模板完整性与无死角门禁回归测试 (Template Integrity & Gatekeeper Test)

确保 templates/plc-standard-project 在通过 Copier 渲染后，
直接通过 PlcChecker 门禁，达到 0 Fail、0 冲突、无空壳目录。
"""

from __future__ import annotations

from pathlib import Path

from auto_pm.core.template_service import TemplateService

from auto_pm.domain.plc.checker import PlcChecker


def test_plc_standard_template_render_and_check(tmp_path: Path) -> None:
    """测试标准 PLC 模板渲染出的项目能够 100% 通过 PlcChecker 门禁"""
    templates_dir = (
        Path(__file__).resolve().parent.parent.parent
        / "templates"
    )
    assert templates_dir.exists(), f"模板目录不存在: {templates_dir}"

    target_proj = tmp_path / "DJ-2026-999_TestMachine"

    tpl_svc = TemplateService(str(templates_dir))
    data = {
        "project_id": "DJ-2026-999",
        "project_name": "自动化测试机",
        "description": "用于自动化门禁回归验证的标准机台",
        "version": "V1.0.0",
    }

    # 执行模板拷贝
    tpl_svc.copy_template("plc-standard-project", str(target_proj), data)
    assert target_proj.exists()

    # 1. 断言关键基础设施文件已渲染
    assert (target_proj / ".plc.json").exists(), "根目录缺少 .plc.json"
    ledger_paths = (
        target_proj / "11_监控" / "01_变更管理" / "02_变更记录",
        target_proj / "04_监控" / "01_变更管理" / "02_变更记录",
    )
    assert any((path / "01_版本变更台账.md").exists() for path in ledger_paths), (
        "缺少变更台账"
    )
    assert not any((path / "01_版本变更台帐.md").exists() for path in ledger_paths), (
        "新模板不得生成旧字形台帐"
    )
    assert (target_proj / "04_现场调试" / "现场调试计划.md").exists(), "现场调试计划未实质化"
    assert (target_proj / "06_文档与交付" / "验收交付清单" / "验收交付清单.md").exists(), "验收交付清单未实质化"
    assert (target_proj / "03_HMI设计" / "HMI详细设计说明书.md").exists(), "HMI详细设计说明书未实质化"
    assert (target_proj / "02_PLC程序" / "PLC_ST" / "Test" / "interlock_test.scltest").exists(), "缺少安全联锁测试套件"

    # 2. 断言执行 PlcChecker 零 Fail
    checker = PlcChecker(workspace_root=str(tmp_path))
    check_res = checker.check_project(str(target_proj))

    failures = [item for item in check_res.items if item.status == "fail"]
    assert not failures, f"模板渲染出的项目存在门禁失败项: {failures}"
    assert check_res.fail_count == 0, f"Fail 数不为 0: {check_res.fail_count}"
