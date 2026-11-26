from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


def _load_conftest() -> Any:
    path = Path(__file__).with_name("conftest.py")
    spec = importlib.util.spec_from_file_location("sw8_conftest_guard", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Config:
    def __init__(self, args: list[str], workers: int, record: str = "") -> None:
        self.args = args
        self.option = SimpleNamespace(numprocesses=workers)
        self._record = record

    def getoption(self, name: str, default: Any = None) -> Any:
        return self._record if name == "gate_execution" else default


def test_full_suite_with_many_workers_is_refused_without_a_record(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_conftest()
    monkeypatch.delenv("CI", raising=False)

    with pytest.raises(pytest.UsageError, match="拒绝未经受控入口"):
        module._refuse_uncontrolled_full_suite(_Config(["tests"], 8))


def test_targeted_suite_and_small_concurrency_are_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_conftest()
    monkeypatch.delenv("CI", raising=False)

    module._refuse_uncontrolled_full_suite(_Config(["tests/core"], 8))
    module._refuse_uncontrolled_full_suite(_Config(["tests"], 4))


def test_ci_and_a_matching_execution_record_are_allowed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _load_conftest()
    monkeypatch.setenv("CI", "true")
    module._refuse_uncontrolled_full_suite(_Config(["tests"], 8))

    monkeypatch.delenv("CI")
    head = subprocess.run(
        ["git", "-C", str(Path.cwd()), "rev-parse", "HEAD"],
        capture_output=True,
        encoding="utf-8",
        check=True,
    ).stdout.strip()
    record = tmp_path / "exec.json"
    record.write_text(
        json.dumps(
            {"schema": "gate-execution.v1", "project": str(Path.cwd().resolve()), "commit": head}
        ),
        encoding="utf-8",
    )
    module._refuse_uncontrolled_full_suite(_Config(["tests"], 8, str(record)))


def test_a_record_for_another_commit_is_refused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    module = _load_conftest()
    monkeypatch.delenv("CI", raising=False)
    record = tmp_path / "exec.json"
    record.write_text(
        json.dumps(
            {"schema": "gate-execution.v1", "project": str(Path.cwd().resolve()), "commit": "0" * 40}
        ),
        encoding="utf-8",
    )

    with pytest.raises(pytest.UsageError):
        module._refuse_uncontrolled_full_suite(_Config(["tests"], 8, str(record)))
