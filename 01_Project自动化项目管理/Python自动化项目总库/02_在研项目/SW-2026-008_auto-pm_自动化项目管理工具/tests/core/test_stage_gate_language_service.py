"""The monitoring -> closing gate also requires the Siemens language service (plugin command line) to pass (M3-PLUGIN).

A missing plugin is "unverified" and blocks the delivery gate; it is never a pass.
"""

from __future__ import annotations

from pathlib import Path

from auto_pm.application.core.gates.stage_gate_engine import StageGateEngine
from auto_pm.contracts.gate_dtos import GateCheckItemDTO, StageGateResultDTO
from auto_pm.domain.plc.language_service import LanguageServiceBinary, LanguageServiceResult
from tests.core.test_stage_gate_plc_docs import plc_project
from tests.plc.test_doc_consistency import build

ITEM = "G4-PLC-LANGUAGE-SERVICE"
BINARY = LanguageServiceBinary(path="x", version="2.17.2", sha256="0" * 64)


class FakeService:
    def __init__(self, available: bool = True, check_exit: int = 0, test_exit: int = 0) -> None:
        self._available = available
        self._check_exit = check_exit
        self._test_exit = test_exit
        self.calls: list[str] = []

    @property
    def available(self) -> bool:
        return self._available

    def check(self, root: Path) -> LanguageServiceResult:
        self.calls.append("check")
        return LanguageServiceResult("check", True, self._check_exit, error_count=0 if self._check_exit == 0 else 3, messages=() if self._check_exit == 0 else ("FB.scl:1:1: ERROR: x",), binary=BINARY)

    def test(self, root: Path) -> LanguageServiceResult:
        self.calls.append("test")
        return LanguageServiceResult("test", True, self._test_exit, error_count=0 if self._test_exit == 0 else 1, messages=() if self._test_exit == 0 else ("a.scltest:1:1: SCLTEST_X y",), binary=BINARY)


def evaluate(project: Path, service: FakeService | None) -> StageGateResultDTO:
    engine = StageGateEngine(str(project.parent), language_service=service)
    return engine.evaluate_stage_transition(str(project), "monitoring", "closing")


def item(result: StageGateResultDTO) -> GateCheckItemDTO | None:
    return next((i for i in result.items if i.id == ITEM), None)


def test_gl01_without_a_service_the_engine_has_no_language_item(tmp_path: Path) -> None:
    assert item(evaluate(plc_project(tmp_path), None)) is None


def test_gl02_a_passing_check_passes_the_item(tmp_path: Path) -> None:
    service = FakeService()
    found = item(evaluate(plc_project(tmp_path), service))
    assert found is not None and found.passed and found.severity == "BLOCKER" and "2.17.2" in found.message
    assert service.calls == ["check"]


def test_gl03_a_failing_check_blocks_closing_and_shows_the_diagnostic(tmp_path: Path) -> None:
    result = evaluate(plc_project(tmp_path), FakeService(check_exit=1))
    found = item(result)
    assert found is not None and not found.passed and result.can_proceed is False
    assert "check 退出码 1" in found.message and "FB.scl:1:1" in found.message


def test_gl04_a_missing_plugin_is_unverified_and_blocks(tmp_path: Path) -> None:
    service = FakeService(available=False)
    result = evaluate(plc_project(tmp_path), service)
    found = item(result)
    assert found is not None and not found.passed and "未验证" in found.message and result.can_proceed is False
    assert service.calls == []


def test_gl05_a_failing_scltest_blocks_closing(tmp_path: Path) -> None:
    project = plc_project(tmp_path)
    (project / "Test").mkdir()
    (project / "Test" / "a.scltest").write_text('TEST_CASE "x"\nEND_TEST_CASE\n', encoding="utf-8")
    service = FakeService(test_exit=1)
    found = item(evaluate(project, service))
    assert found is not None and not found.passed and "test 退出码 1" in found.message
    assert service.calls == ["check", "test"]


def test_gl06_a_project_without_plc_json_has_no_language_item(tmp_path: Path) -> None:
    project = build(tmp_path)
    service = FakeService()
    assert item(evaluate(project, service)) is None and service.calls == []
