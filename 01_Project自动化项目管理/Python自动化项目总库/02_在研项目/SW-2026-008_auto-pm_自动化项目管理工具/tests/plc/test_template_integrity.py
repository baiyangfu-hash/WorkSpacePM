"""PLC 黄金模板完整性与无死角门禁回归测试 (Template Integrity & Gatekeeper Test)

确保 templates/plc-standard-project 在通过 Copier 渲染后，
直接通过 PlcChecker 门禁，达到 0 Fail、0 冲突、无空壳目录。
"""

from __future__ import annotations

from pathlib import Path

from auto_pm.application.core.template_service import TemplateService
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


def test_plc_standard_template_with_three_stations_passes_the_checker(tmp_path: Path) -> None:
    """3 个工位：3 个背景 DB 各在工位 FB 文件夹里，PlcChecker 仍然零 Fail（CHG-SCPT-2026-635）"""
    templates_dir = Path(__file__).resolve().parent.parent.parent / "templates"
    target_proj = tmp_path / "DJ-2026-998_ThreeStations"
    data = {"project_id": "DJ-2026-998", "project_name": "三工位机", "description": "三工位", "version": "V1.0.0",
            "station_instances": ["Station1", "Station2", "Station3"]}
    TemplateService(str(templates_dir)).copy_template("plc-standard-project", str(target_proj), data)
    station_dir = target_proj / "02_PLC程序" / "PLC_ST" / "02_工位1_动作机构"
    assert sorted(p.name for p in station_dir.glob("DB_1001_*.scl")) == [
        "DB_1001_Station1.scl", "DB_1001_Station2.scl", "DB_1001_Station3.scl"]
    check_res = PlcChecker(workspace_root=str(tmp_path)).check_project(str(target_proj))
    failures = [item for item in check_res.items if item.status == "fail"]
    assert not failures, failures


def test_slot_files_and_shared_db_fragment_are_in_place() -> None:
    """8 个槽位文件名只含 {{ db_slot_N }}，DB 内容只有 _includes 里一份（槽位不复制内容）"""
    root = Path(__file__).resolve().parent.parent.parent / "templates" / "plc-standard-project"
    fragment = root / "_includes" / "DB_1001_Station.scl.jinja"
    assert fragment.read_bytes().startswith(b"\xef\xbb\xbf")  # TIA 要 UTF-8 带 BOM（LSP-905 §4.10）
    station_dir = root / "template" / "02_PLC程序" / "PLC_ST" / "02_工位1_动作机构"
    for n in range(1, 9):
        slot = station_dir / f"{{{{ db_slot_{n} }}}}.jinja"
        assert slot.read_text(encoding="utf-8") == f'{{% set slot = {n} %}}{{% include "_includes/DB_1001_Station.scl.jinja" %}}'
    assert not list(station_dir.glob("{{ db_slot_9 }}*"))
    assert not list((root / "template" / "02_PLC程序" / "PLC_ST" / "00_全局数据").glob("DB_*"))
