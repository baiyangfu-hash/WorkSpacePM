"""D-295 方案①：没找到西门子插件时，`plc check` 的汇总不再写 ALL PASS，`--json` 写明语言服务这一层有没有真跑。

退出码口径不变（没有 fail 就是 0）；交付阶段门禁照旧把“未验证”按失败处理。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result

from auto_pm.application.core.template_service import TemplateService
from auto_pm.domain.models.plc import LANGUAGE_SERVICE_CHECK, CheckResult
from auto_pm.ui.cli.__main__ import cli
from tests.cli.test_plc_language_service import FakeService

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
UNVERIFIED = "结构检查通过；语法和类型未验证（本机没有西门子插件）"


@pytest.fixture(scope="module")
def workspace(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("lsunverified")
    TemplateService(str(TEMPLATES)).copy_template(
        "plc-standard-project", str(root / "DJ-2026-902_测试机"), {"project_id": "DJ-2026-902", "project_name": "测试机"}
    )
    return root


def _run(workspace: Path, monkeypatch: pytest.MonkeyPatch, service: FakeService, *args: str) -> Result:
    import auto_pm.infrastructure.siemens_language_service as module

    monkeypatch.setattr(module, "default_language_service", lambda: service)
    return CliRunner().invoke(cli, ["-w", str(workspace), "plc", "check", *args], catch_exceptions=False)


def _flat(text: str) -> str:
    """rich 按终端宽度折行，比对前去掉空白。"""
    return "".join(text.split())


def _json(output: str) -> Any:
    start = min(i for i in (output.find("{"), output.find("[")) if i >= 0)
    return json.loads(output[start:])


def test_u01_missing_plugin_summary_does_not_say_all_pass(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(workspace, monkeypatch, FakeService(0, available=False), "DJ-2026-902")
    assert result.exit_code == 0  # 口径不变：项目本身没有失败项
    assert "ALL PASS" not in result.output
    assert _flat(UNVERIFIED) in _flat(result.output)


def test_u02_a_real_plugin_pass_still_says_all_pass(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(workspace, monkeypatch, FakeService(0), "DJ-2026-902")
    assert result.exit_code == 0
    assert "ALL PASS" in result.output and _flat(UNVERIFIED) not in _flat(result.output)


def test_u03_a_failure_is_still_has_fail_with_or_without_the_plugin(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(workspace, monkeypatch, FakeService(1), "DJ-2026-902")
    assert result.exit_code == 1 and "HAS FAIL" in result.output


@pytest.mark.parametrize(
    ("service", "flags", "expected"),
    [
        (FakeService(0, available=False), (), False),
        (FakeService(0), (), True),
        (FakeService(1), (), True),  # 跑了、没过：过没过看 fail_count，这个字段只说有没有真跑
        (FakeService(0), ("--no-language-service",), None),
    ],
    ids=["missing-plugin", "plugin-pass", "plugin-fail", "layer-off"],
)
def test_u04_json_names_whether_the_language_service_really_ran(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, service: FakeService, flags: tuple[str, ...], expected: bool | None
) -> None:
    result = _run(workspace, monkeypatch, service, "DJ-2026-902", "--json", *flags)
    assert _json(result.output)["language_service_verified"] is expected


def test_u05_the_all_projects_summary_names_unverified_passes(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _run(workspace, monkeypatch, FakeService(0, available=False), "--all")
    assert result.exit_code == 0
    flat = _flat(result.output)
    assert _flat("PASS（语法未验证）") in flat
    assert _flat("其中 1 个 PASS 只是结构检查通过：本机没有西门子插件，语法和类型未验证") in flat
    listed = _json(_run(workspace, monkeypatch, FakeService(0, available=False), "--all", "--json").output)
    assert [r["language_service_verified"] for r in listed] == [False]


def test_u06_the_field_round_trips_and_follows_the_items() -> None:
    result = CheckResult(project_path="x")
    assert result.language_service_verified is None
    result.add(LANGUAGE_SERVICE_CHECK, "warn", "未验证：本机未找到插件")
    dumped = result.model_dump()
    assert dumped["language_service_verified"] is False
    again = CheckResult.model_validate(dumped)  # 读回旧 JSON 不报错，字段照条目重算
    assert again.language_service_verified is False and again.all_pass


@pytest.mark.parametrize(("status", "verdict"), [("warn", UNVERIFIED), ("pass", "ALL PASS")])
def test_u07_the_after_repair_line_uses_the_same_verdict(monkeypatch: pytest.MonkeyPatch, status: str, verdict: str) -> None:
    """`plc repair` 末尾那行“修复后检查”和 `plc check` 同一口径：插件没跑就不写 ALL PASS。"""
    from rich.console import Console

    import auto_pm.ui.cli.plc as plc_cli
    from auto_pm.domain.models.plc import RepairResult

    after = CheckResult(project_path="x")
    after.add(LANGUAGE_SERVICE_CHECK, status, "未验证：本机未找到插件" if status == "warn" else "插件命令行 check 退出码 0")
    recorder = Console(record=True, width=200)
    monkeypatch.setattr(plc_cli, "console", recorder)
    plc_cli._print_repair_result(RepairResult(project_path="x", after_check=after))
    line = next(text for text in recorder.export_text().splitlines() if text.startswith("修复后检查"))
    assert line.endswith(verdict)
    assert ("ALL PASS" in line) is (status == "pass")


def test_u08_the_checker_writes_the_names_the_field_and_the_baseline_read(tmp_path: Path) -> None:
    """检查器写入的两项名字就是 LANGUAGE_SERVICE_CHECK / LANGUAGE_SERVICE_TEST：哪边改一个字，
    language_service_verified 就会悄悄变成 None、基线逐条比也认不出来，这条要红。"""
    from auto_pm.domain.models.plc import LANGUAGE_SERVICE_TEST
    from auto_pm.domain.plc import baseline_compare
    from auto_pm.domain.plc.checker import PlcChecker
    from tests.plc.test_checker_language_service import _project

    project = str(_project(tmp_path, with_scltest=True))
    written = {i.item for i in PlcChecker(str(tmp_path), FakeService(0)).check_project(project).items}
    assert {LANGUAGE_SERVICE_CHECK, LANGUAGE_SERVICE_TEST} <= written
    missing = PlcChecker(str(tmp_path), FakeService(0, available=False)).check_project(project)
    assert [i.item for i in missing.items if i.status == "warn" and i.message.startswith("未验证")] == [LANGUAGE_SERVICE_CHECK]
    assert missing.language_service_verified is False
    assert set(baseline_compare.LANGUAGE_ITEMS) == {LANGUAGE_SERVICE_CHECK, LANGUAGE_SERVICE_TEST}


def test_u09_no_module_spells_the_item_names_out_again() -> None:
    """名字只在 domain/models/plc.py 写一次；检查器、基线逐条比、证据摘要都引用常量，不再各写一份。"""
    package = Path(__file__).resolve().parents[2] / "auto_pm"
    spelled = sorted(
        str(path.relative_to(package)).replace("\\", "/")
        for path in package.rglob("*.py")
        if any(f'"{name}"' in path.read_text(encoding="utf-8", errors="replace") for name in ("Siemens 语言服务 check", "Siemens 语言服务 test"))
    )
    assert spelled == ["domain/models/plc.py"]
