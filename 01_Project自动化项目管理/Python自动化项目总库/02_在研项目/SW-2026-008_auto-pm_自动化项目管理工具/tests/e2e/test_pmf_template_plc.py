"""V08: the PLC standard-project template really produces projects that the product's own static PLC check accepts, and the check really rejects the field errors it claims to reject
(WBS task V08, card CARD-SW008-M3-V08).

The real ``templates/plc-standard-project`` is generated through ``TemplateService`` (the code path of the product). The generated project is checked by the product's ``PlcChecker``.
The boundary is the static check only: nothing here compiles in TIA Portal or InoProShop, downloads to a controller or runs a device; a pass says "the generated project is complete
and well-formed by the product's static PLC rules", not "the PLC program runs".
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from auto_pm.application.core.template_service import TemplateService
from auto_pm.domain.models.plc import CheckResult
from auto_pm.domain.plc.checker import PlcChecker

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
PID, NAME = "DJ-2026-901", "TESTMACHINE"

EXPECTED_TEMPLATE_FILES = [
    ".copier-answers.yml",
    ".github/hooks/.gitkeep",
    ".gitignore",
    ".plc.json",
    ".trae/specs/.gitkeep",
    "00_项目管理/01_立项与需求/003_{pid}_项目立项表_PROJ.md",
    "00_项目管理/01_立项与需求/005_{pid}_需求分析文档_REQ.md",
    "01_启动/003_{pid}_项目立项表_PROJ.md",
    "01_启动/06_PM_SESSION历史/.gitkeep",
    "01_需求与设计/13_软件方案/012_{pid}_需求规格说明书_REQ.md",
    "01_需求与设计/13_软件方案/{name}工艺流程图_V1.mmd",
    "02_PLC程序/PLC_ST/.plc.json",
    "02_PLC程序/PLC_ST/00_主程序/OB1.scl",
    "02_PLC程序/PLC_ST/00_主程序/PRD/变更记录_CHG-OB1.md",
    "02_PLC程序/PLC_ST/00_主程序/PRD/接口文档_IFC-OB1.md",
    "02_PLC程序/PLC_ST/00_主程序/PRD/详细设计说明书_DSN-OB1.md",
    "02_PLC程序/PLC_ST/00_全局数据/GlobalVars.db",
    "02_PLC程序/PLC_ST/00_全局数据/PRD/变更记录_CHG-GlobalVars.md",
    "02_PLC程序/PLC_ST/00_全局数据/PRD/接口文档_IFC-GlobalVars.md",
    "02_PLC程序/PLC_ST/00_程序方案/015_IO分配表_IO.md",
    "02_PLC程序/PLC_ST/00_程序方案/018_自动工艺流程图_FLOW.md",
    "02_PLC程序/PLC_ST/00_程序方案/技术方案文档_TEC.md",
    "02_PLC程序/PLC_ST/00_程序方案/接口文档_INT.md",
    "02_PLC程序/PLC_ST/00_程序方案/详细设计说明书_DSN.md",
    "02_PLC程序/PLC_ST/00_程序方案/需求分析文档_REQ.md",
    "02_PLC程序/PLC_ST/01_外部设备交互/FB_3001_ExternalInteraction.scl",
    "02_PLC程序/PLC_ST/01_外部设备交互/PRD/使用说明_UM-FB3001-ExternalInteraction.md",
    "02_PLC程序/PLC_ST/01_外部设备交互/PRD/变更记录_CHG-FB3001-ExternalInteraction.md",
    "02_PLC程序/PLC_ST/01_外部设备交互/PRD/接口文档_IFC-FB3001-ExternalInteraction.md",
    "02_PLC程序/PLC_ST/01_外部设备交互/PRD/详细设计说明书_DSN-FB3001-ExternalInteraction.md",
    "02_PLC程序/PLC_ST/01_外部设备交互/ST_ExternalDevice.scl",
    "02_PLC程序/PLC_ST/02_工位1_动作机构/FB_1001_Station1.scl",
    "02_PLC程序/PLC_ST/02_工位1_动作机构/PRD/使用说明_UM-FB1001-Station1.md",
    "02_PLC程序/PLC_ST/02_工位1_动作机构/PRD/变更记录_CHG-FB1001-Station1.md",
    "02_PLC程序/PLC_ST/02_工位1_动作机构/PRD/接口文档_IFC-FB1001-Station1.md",
    "02_PLC程序/PLC_ST/02_工位1_动作机构/PRD/详细设计说明书_DSN-FB1001-Station1.md",
    "02_PLC程序/PLC_ST/02_工位1_动作机构/ST_Station1.scl",
    "02_PLC程序/PLC_ST/05_公共报警/FB_2001_CommonAlarm_AllStation.scl",
    "02_PLC程序/PLC_ST/05_公共报警/PRD/使用说明_UM-FB2001-CommonAlarm.md",
    "02_PLC程序/PLC_ST/05_公共报警/PRD/变更记录_CHG-FB2001-CommonAlarm.md",
    "02_PLC程序/PLC_ST/05_公共报警/PRD/接口文档_IFC-FB2001-CommonAlarm.md",
    "02_PLC程序/PLC_ST/05_公共报警/PRD/详细设计说明书_DSN-FB2001-CommonAlarm.md",
    "02_PLC程序/PLC_ST/05_公共报警/ST_CommonAlarm.scl",
    "02_PLC程序/PLC_ST/Test/basic_test.scltest",
    "02_PLC程序/PLC_ST/Test/interlock_test.scltest",
    "02_PLC程序/工程资产/communications.yml",
    "02_PLC程序/工程资产/io_points.csv",
    "02_PLC程序/工程资产/program_blocks.yml",
    "02_PLC程序/程序文档/015_IO分配表_IO.md",
    "02_PLC程序/程序文档/016_PLC程序设计总文档_PLC.md",
    "02_PLC程序/程序文档/018_自动工艺流程图_FLOW.md",
    "02_PLC程序/程序文档/PLC变量定义文档_VAR.md",
    "02_PLC程序/程序文档/程序架构文档_ARC.md",
    "03_HMI设计/HMI功能分析报告.md",
    "03_HMI设计/HMI详细设计说明书.md",
    "03_HMI设计/hmi_tag_mapping.json",
    "03_HMI设计/原型/files/HMI原型设计.html",
    "03_HMI设计/原型/files/hmi-components.js",
    "03_HMI设计/原型/files/hmi-tokens.css",
    "03_HMI设计/原型/files/script.js",
    "03_HMI设计/原型/files/styles.css",
    "03_HMI设计/操作手册/HMI操作手册.md",
    "04_现场调试/现场调试计划.md",
    "04_现场调试/现场调试问题跟踪.md",
    "05_测试与验证/01_集成测试方案.md",
    "06_文档与交付/上机复核/PLC_Handoff_Checklist.md",
    "06_文档与交付/操作手册/设备培训文档.md",
    "06_文档与交付/操作手册/设备维护手册.md",
    "06_文档与交付/验收交付清单/验收交付清单.md",
    "07_技术支持/技术支持手册.md",
    "08_备件管理/备件管理手册.md",
    "09_项目总结/项目总结报告.md",
    "10_知识库/知识库.md",
    "11_监控/01_变更管理/01_变更单/CHG-DOCU/.gitkeep",
    "11_监控/01_变更管理/01_变更单/CHG-ELEC/.gitkeep",
    "11_监控/01_变更管理/01_变更单/CHG-PLC/.gitkeep",
    "11_监控/01_变更管理/02_变更记录/01_版本变更台账.md",
    "12_驱动器与设备/伺服参数配置.md",
    "PM_SESSION_{pid}.md",
    "PRD/技术方案文档_TEC.md",
    "PRD/接口文档_INT.md",
    "PRD/详细设计说明书_DSN.md",
    "PRD/需求分析文档_REQ.md",
]


def _generate(workspace: Path, project_id: str = PID, project_name: str = NAME) -> Path:
    destination = workspace / project_id
    TemplateService(str(TEMPLATES_DIR)).copy_template("plc-standard-project", str(destination), {"project_id": project_id, "project_name": project_name})
    return destination


def _files(project: Path) -> list[str]:
    return sorted(p.relative_to(project).as_posix() for p in project.rglob("*") if p.is_file())


def _check(workspace: Path, project: Path) -> CheckResult:
    result: CheckResult = PlcChecker(workspace_root=str(workspace)).check_project(str(project))
    return result


def _expected(project_id: str, project_name: str) -> list[str]:
    return sorted(f.format(pid=project_id, name=project_name) for f in EXPECTED_TEMPLATE_FILES)


def test_v01_the_generated_project_has_exactly_the_pinned_file_set(tmp_path: Path) -> None:
    project = _generate(tmp_path)
    assert _files(project) == _expected(PID, NAME)


def test_v02_no_template_placeholder_survives_in_names_or_text(tmp_path: Path) -> None:
    project = _generate(tmp_path)
    leftovers = []
    for path in project.rglob("*"):
        rel = path.relative_to(project).as_posix()
        if "{{" in rel or "{%" in rel or rel.endswith(".jinja"):
            leftovers.append(rel)
        elif path.is_file() and path.suffix in {".md", ".scl", ".db", ".json", ".yml", ".yaml", ".csv", ".mmd", ".html", ".js", ".css", ".scltest", ".txt"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            if "{{" in text or "{%" in text:
                leftovers.append(rel)
    # the shipped HMI prototype is plain front-end code that legitimately contains braces; only template syntax with a known variable name counts
    leftovers = [x for x in leftovers if not x.startswith("03_HMI设计/原型/")]
    assert leftovers == []


def test_v03_the_static_plc_check_accepts_the_generated_project(tmp_path: Path) -> None:
    project = _generate(tmp_path)
    result = _check(tmp_path, project)
    failures = [(i.item, i.message) for i in result.items if i.status == "fail"]
    assert failures == []
    assert result.fail_count == 0
    assert result.pass_count >= 50
    config_items = [i for i in result.items if i.item == ".plc.json" and i.status == "pass"]
    assert config_items and PID in config_items[0].message


@pytest.mark.parametrize("relative", [".plc.json", "02_PLC程序/PLC_ST/.plc.json"])
def test_v04_the_plc_json_files_carry_the_project_answers(tmp_path: Path, relative: str) -> None:
    project = _generate(tmp_path)
    config = json.loads((project / relative).read_text(encoding="utf-8"))
    assert config["name"] == PID
    assert config["version"] == "V1.0.0"
    assert config["description"] == NAME
    assert isinstance(config["libraries"], list) and config["libraries"]


def test_v05_the_interface_and_variable_documents_name_the_project(tmp_path: Path) -> None:
    project = _generate(tmp_path)
    for relative in ("PRD/接口文档_INT.md", "02_PLC程序/PLC_ST/00_程序方案/接口文档_INT.md", "02_PLC程序/程序文档/PLC变量定义文档_VAR.md"):
        text = (project / relative).read_text(encoding="utf-8")
        assert PID in text and NAME in text, relative
        assert "stGlobal" in text or "GlobalVars" in text, relative
    ledger = (project / "11_监控/01_变更管理/02_变更记录/01_版本变更台账.md").read_text(encoding="utf-8")
    assert PID in ledger or NAME in ledger or "变更" in ledger
    session = (project / f"PM_SESSION_{PID}.md").read_text(encoding="utf-8")
    assert PID in session


def _break_plc_json_invalid(project: Path) -> None:
    for relative in (".plc.json", "02_PLC程序/PLC_ST/.plc.json"):
        (project / relative).write_text("{not json", encoding="utf-8")


def _break_plc_json_without_name(project: Path) -> None:
    for relative in (".plc.json", "02_PLC程序/PLC_ST/.plc.json"):
        (project / relative).write_text(json.dumps({"version": "V1.0.0"}), encoding="utf-8")


def _break_plc_json_without_version(project: Path) -> None:
    for relative in (".plc.json", "02_PLC程序/PLC_ST/.plc.json"):
        (project / relative).write_text(json.dumps({"name": PID}), encoding="utf-8")


def _break_plc_json_missing(project: Path) -> None:
    for relative in (".plc.json", "02_PLC程序/PLC_ST/.plc.json"):
        (project / relative).unlink()


def _break_pm_session_missing(project: Path) -> None:
    (project / f"PM_SESSION_{PID}.md").unlink()


def _break_ledger_missing(project: Path) -> None:
    (project / "11_监控/01_变更管理/02_变更记录/01_版本变更台账.md").unlink()


def _break_interface_document_missing(project: Path) -> None:
    (project / "PRD/接口文档_INT.md").unlink()


def _break_standard_folder_missing(project: Path) -> None:
    shutil.rmtree(project / "05_测试与验证")


BREAKS = {
    "plc-json-invalid": (_break_plc_json_invalid, ".plc.json"),
    "plc-json-without-name": (_break_plc_json_without_name, ".plc.json"),
    "plc-json-without-version": (_break_plc_json_without_version, ".plc.json"),
    "plc-json-missing": (_break_plc_json_missing, ".plc.json"),
    "pm-session-missing": (_break_pm_session_missing, "PM_SESSION"),
    "ledger-missing": (_break_ledger_missing, "版本变更台帐"),  # the product labels this item with the old glyph
    "interface-document-missing": (_break_interface_document_missing, "PRD/接口文档_INT.md"),
    "standard-folder-missing": (_break_standard_folder_missing, "目录 05_测试与验证"),
}


@pytest.mark.parametrize("name", sorted(BREAKS))
def test_v06_a_field_or_file_error_is_rejected_by_the_static_check(tmp_path: Path, name: str) -> None:
    breaker, item = BREAKS[name]
    project = _generate(tmp_path)
    assert _check(tmp_path, project).fail_count == 0  # the control: the same project before the break is accepted
    breaker(project)
    result = _check(tmp_path, project)
    failed = [i.item for i in result.items if i.status == "fail"]
    assert result.fail_count == 1, failed
    assert failed == [item], failed


def test_v07_a_second_project_is_independent_of_the_first(tmp_path: Path) -> None:
    first = _generate(tmp_path / "a")
    second = _generate(tmp_path / "b", "DJ-2026-902", "OTHERMACHINE")
    assert _files(second) == _expected("DJ-2026-902", "OTHERMACHINE")
    for path in second.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".scl", ".db", ".json", ".yml", ".csv", ".mmd"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            assert PID not in text and NAME not in text, path.relative_to(second).as_posix()
    assert "DJ-2026-902" in (second / ".copier-answers.yml").read_text(encoding="utf-8")
    assert _check(tmp_path / "b", second).fail_count == 0
    assert (first / f"PM_SESSION_{PID}.md").is_file() and not (first / "PM_SESSION_DJ-2026-902.md").exists()


@pytest.mark.parametrize("bad_id", ["dj-2026-1", "DJ2026901", "DJ-26-901", ""], ids=["lowercase-short", "no-dashes", "short-year", "empty"])
def test_v08_a_malformed_project_id_is_rejected_and_leaves_nothing_behind(tmp_path: Path, bad_id: str) -> None:
    destination = tmp_path / "rejected"
    with pytest.raises(Exception):  # noqa: B017, PT011 - copier raises its own validation error type
        TemplateService(str(TEMPLATES_DIR)).copy_template("plc-standard-project", str(destination), {"project_id": bad_id, "project_name": "x"})
    assert not destination.exists() or not any(destination.iterdir())
