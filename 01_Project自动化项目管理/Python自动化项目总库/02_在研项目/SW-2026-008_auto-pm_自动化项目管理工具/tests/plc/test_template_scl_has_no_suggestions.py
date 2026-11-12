"""TD-SW008-574（D-309）：刚生成的 PLC 标准模板工程自己不带 SCL 规范建议。

以前公共报警块 FB_2001 的静态解包/封包变量沿用 i_/q_ 前缀，生成后 plc check 就报 16 条建议。
现在照标杆 DJ-2026-011 的写法改成 s_ 前缀（数组 s_arr），规则和 LSP-905 规范本身不动。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_pm.application.core.template_service import TemplateService
from auto_pm.domain.models.plc import CheckResult
from auto_pm.domain.plc.checker import PlcChecker
from auto_pm.domain.plc.scl_linter import SclLinter

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"


def _generate(tmp_path: Path, stations: list[str] | None) -> Path:
    data: dict[str, object] = {"project_id": "DJ-2026-908", "project_name": "零建议"}
    if stations:
        data["station_instances"] = stations
    destination = tmp_path / "DJ-2026-908"
    TemplateService(str(TEMPLATES_DIR)).copy_template("plc-standard-project", str(destination), data)
    return destination


@pytest.mark.parametrize("stations", [None, ["Station1", "Station2", "Station3"]])
def test_the_generated_template_has_no_scl_violation_at_all(tmp_path: Path, stations: list[str] | None) -> None:
    project = _generate(tmp_path, stations)
    sources = sorted(p for p in project.rglob("*") if p.is_file() and p.suffix.lower() in (".scl", ".db", ".udt"))
    assert len(sources) >= 10
    hits = [
        f"{path.relative_to(project).as_posix()}:{v.line_number} {v.severity} {v.rule_id}"
        for path in sources
        for v in SclLinter.lint_file(path).violations
    ]
    assert hits == []


def test_the_scl_compliance_item_passes_on_the_generated_template(tmp_path: Path) -> None:
    project = _generate(tmp_path, ["Station1", "Station2"])
    result = CheckResult(project_path=str(project))
    PlcChecker(str(tmp_path))._check_scl_code_compliance(str(project), result)
    item = next(i for i in result.items if i.item == "SCL 代码规范")
    assert (item.status, item.details) == ("pass", [])
