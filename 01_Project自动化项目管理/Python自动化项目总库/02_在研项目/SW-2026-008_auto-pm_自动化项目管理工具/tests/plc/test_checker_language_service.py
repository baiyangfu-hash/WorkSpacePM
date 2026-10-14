"""PlcChecker 的 Siemens 语言服务这一层（M3-PLUGIN）：用伪造的语言服务验证“通过 / 失败 / 未验证”三种结果的映射。"""

from __future__ import annotations

import json
from pathlib import Path

from auto_pm.domain.plc.checker import PlcChecker
from auto_pm.domain.plc.language_service import LanguageServiceBinary, LanguageServiceResult

BINARY = LanguageServiceBinary(path="x", version="2.17.2", sha256="0" * 64)


class FakeService:
    def __init__(self, available: bool = True, check: LanguageServiceResult | None = None, test: LanguageServiceResult | None = None) -> None:
        self._available = available
        self._check = check or LanguageServiceResult("check", True, 0, binary=BINARY, summary="check metrics: ok")
        self._test = test or LanguageServiceResult("test", True, 0, binary=BINARY, cases_run=2, cases_total=2)
        self.calls: list[tuple[str, Path]] = []

    @property
    def available(self) -> bool:
        return self._available

    def check(self, root: Path) -> LanguageServiceResult:
        self.calls.append(("check", root))
        return self._check

    def test(self, root: Path) -> LanguageServiceResult:
        self.calls.append(("test", root))
        return self._test


def _project(tmp_path: Path, with_scltest: bool = False) -> Path:
    project = tmp_path / "DJ-2026-LS"
    project.mkdir()
    (project / ".plc.json").write_text(json.dumps({"name": "DJ-2026-LS", "version": "V1.0.0", "description": "x"}), encoding="utf-8")
    if with_scltest:
        (project / "Test").mkdir()
        (project / "Test" / "a.scltest").write_text("TEST_CASE \"x\"\nEND_TEST_CASE\n", encoding="utf-8")
    return project


def _items(result, prefix: str = "Siemens 语言服务"):  # type: ignore[no-untyped-def]
    return {i.item: i for i in result.items if i.item.startswith(prefix)}


def test_cl01_without_a_language_service_the_layer_is_absent(tmp_path: Path) -> None:
    result = PlcChecker(str(tmp_path)).check_project(str(_project(tmp_path)))
    assert _items(result) == {}


def test_cl02_a_passing_check_is_a_pass_item(tmp_path: Path) -> None:
    service = FakeService()
    result = PlcChecker(str(tmp_path), language_service=service).check_project(str(_project(tmp_path)))
    item = _items(result)["Siemens 语言服务 check"]
    assert item.status == "pass" and "2.17.2" in item.message
    assert [c for c, _ in service.calls] == ["check"]  # no .scltest file, so no test run


def test_cl03_errors_make_a_fail_item_with_the_first_messages(tmp_path: Path) -> None:
    failing = LanguageServiceResult("check", True, 1, error_count=2, messages=("FB.scl:49:5: ERROR: a", "OB1.scl:15:5: ERROR: b"), binary=BINARY)
    result = PlcChecker(str(tmp_path), language_service=FakeService(check=failing)).check_project(str(_project(tmp_path)))
    item = _items(result)["Siemens 语言服务 check"]
    assert item.status == "fail" and "2 个错误" in item.message and "FB.scl:49:5" in item.message
    assert result.fail_count >= 1


def test_cl04_a_missing_plugin_is_not_verified_and_never_a_pass(tmp_path: Path) -> None:
    service = FakeService(available=False)
    result = PlcChecker(str(tmp_path), language_service=service).check_project(str(_project(tmp_path)))
    item = _items(result)["Siemens 语言服务 check"]
    assert item.status == "warn" and "未验证" in item.message
    assert service.calls == []


def test_cl05_scltest_files_add_a_test_item_and_a_failing_test_fails(tmp_path: Path) -> None:
    broken = LanguageServiceResult("test", True, 1, error_count=1, messages=("basic_test.scltest:8:9: SCLTEST_SEM_INVALID_PATH x",), binary=BINARY)
    service = FakeService(test=broken)
    result = PlcChecker(str(tmp_path), language_service=service).check_project(str(_project(tmp_path, with_scltest=True)))
    items = _items(result)
    assert items["Siemens 语言服务 check"].status == "pass"
    assert items["Siemens 语言服务 test"].status == "fail" and "SCLTEST_SEM_INVALID_PATH" in items["Siemens 语言服务 test"].message
    assert [c for c, _ in service.calls] == ["check", "test"]


def test_cl06_a_project_without_plc_json_does_not_call_the_service(tmp_path: Path) -> None:
    folder = tmp_path / "not-a-plc-project"
    folder.mkdir()
    (folder / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    service = FakeService()
    result = PlcChecker(str(tmp_path), language_service=service).check_project(str(folder))
    assert result.not_applicable and service.calls == []
