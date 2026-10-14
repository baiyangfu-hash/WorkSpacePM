"""`plc check` runs the Siemens language service layer and judges by exit code (M3-PLUGIN)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from auto_pm.cli.__main__ import cli
from click.testing import CliRunner

from auto_pm.application.core.template_service import TemplateService
from auto_pm.domain.plc.language_service import LanguageServiceBinary, LanguageServiceResult

BINARY = LanguageServiceBinary(path="x", version="2.17.2", sha256="0" * 64)
TEMPLATES = Path(__file__).resolve().parents[2] / "templates"


class FakeService:
    def __init__(self, check_exit: int = 0, available: bool = True) -> None:
        self._check_exit = check_exit
        self._available = available

    @property
    def available(self) -> bool:
        return self._available

    def check(self, root: Path) -> LanguageServiceResult:
        failing = self._check_exit != 0
        return LanguageServiceResult("check", True, self._check_exit, error_count=2 if failing else 0, messages=("FB.scl:49:5: ERROR: x",) if failing else (), binary=BINARY)

    def test(self, root: Path) -> LanguageServiceResult:
        return LanguageServiceResult("test", True, 0, binary=BINARY, cases_run=2, cases_total=2)


@pytest.fixture(scope="module")
def workspace(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("lscli")
    TemplateService(str(TEMPLATES)).copy_template("plc-standard-project", str(root / "DJ-2026-901_测试机"), {"project_id": "DJ-2026-901", "project_name": "测试机"})
    return root


def _check(workspace: Path, monkeypatch: pytest.MonkeyPatch, service: FakeService | None, *flags: str):  # type: ignore[no-untyped-def]
    import auto_pm.infrastructure.siemens_language_service as module

    if service is not None:
        monkeypatch.setattr(module, "default_language_service", lambda: service)
    return CliRunner().invoke(cli, ["-w", str(workspace), "plc", "check", "DJ-2026-901", "--json", *flags], catch_exceptions=False)


def _item(output: str, name: str) -> dict | None:
    data = json.loads(output[output.index("{"):])
    return next((i for i in data["items"] if i["item"] == name), None)


def test_cx01_a_passing_language_service_keeps_the_exit_code_zero(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _check(workspace, monkeypatch, FakeService(0))
    assert result.exit_code == 0
    assert _item(result.output, "Siemens 语言服务 check")["status"] == "pass"  # type: ignore[index]


def test_cx02_a_failing_language_service_makes_the_exit_code_one(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _check(workspace, monkeypatch, FakeService(1))
    assert result.exit_code == 1
    assert _item(result.output, "Siemens 语言服务 check")["status"] == "fail"  # type: ignore[index]


def test_cx03_a_missing_plugin_is_a_warning_not_a_pass(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _check(workspace, monkeypatch, FakeService(0, available=False))
    found = _item(result.output, "Siemens 语言服务 check")
    assert found is not None and found["status"] == "warn" and "未验证" in found["message"]
    assert result.exit_code == 0  # the project itself has no failing item; the delivery gate is where "unverified" blocks


def test_cx04_the_flag_switches_the_layer_off(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    result = _check(workspace, monkeypatch, FakeService(1), "--no-language-service")
    assert result.exit_code == 0
    assert _item(result.output, "Siemens 语言服务 check") is None
