"""TD-SW008-237 batch C: every strict decode below used to be ``errors="replace"/"ignore"`` and judged on damaged text.

Each test feeds bytes that are not UTF-8 and pins the strict answer; the ones for valid text pin that nothing moved.  The reasons for the
sites that stayed lenient are written on their own lines (``# lenient-decode:``), and ``test_no_new_lenient_decoding`` keeps the count at 0.
"""

from __future__ import annotations

import hashlib
import json
import queue
import sys
import threading
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import click
import pytest
from click.testing import CliRunner

from auto_pm.infrastructure import process_probe
from auto_pm.infrastructure.doc.extractors.bridge_ast_extractor import BridgeAstExtractor
from auto_pm.infrastructure.doc.extractors.cli_ast_extractor import CliAstExtractor
from auto_pm.infrastructure.doc.extractors.gate_ast_extractor import GateAstExtractor
from auto_pm.infrastructure.local_executor import LocalCodexExecutor, _BoundedCapture
from auto_pm.ui.cli import continuity_backup as backup_cli
from auto_pm.ui.cli.doctor import check_venv_base
from auto_pm.ui.cli.handoff import _load_result_file
from auto_pm.ui.cli.spec import spec_group

BAD = b"\xff\xfe"


# --- process_probe: the recorded fingerprint ------------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "abc", "C:\\Python\\python.exe", "/usr/bin/python3.12", "路径/解释器 é"])
def test_fingerprint_of_valid_text_is_the_plain_sha256_of_its_utf8(text: str) -> None:
    """Hashes already written to the ledger must not move: valid text hashes exactly as before."""

    assert process_probe._sha256_text(text) == hashlib.sha256(text.encode("utf-8")).hexdigest()


def test_fingerprint_keeps_an_undecodable_path_distinct() -> None:
    """``os.readlink`` hands back undecodable bytes as lone surrogates; they used to all become '?', so two different images collided."""

    first, second = "/opt/\udcff/python", "/opt/\udcfe/python"
    assert process_probe._sha256_text(first) != process_probe._sha256_text(second)
    assert process_probe._sha256_text(first) != process_probe._sha256_text("/opt/?/python")


def test_host_id_is_unknown_when_the_machine_id_does_not_decode(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePath:
        def __init__(self, _path: str) -> None: ...

        def read_text(self, **kwargs: Any) -> str:
            return BAD.decode("utf-8", errors=kwargs.get("errors", "strict"))  # a real file read honours the error handler

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(process_probe, "Path", FakePath)
    assert process_probe.local_host_id() == ""


def test_host_id_of_a_readable_machine_id_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakePath:
        def __init__(self, _path: str) -> None: ...

        def read_text(self, **_kwargs: Any) -> str:
            return "0123456789abcdef\n"

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(process_probe, "Path", FakePath)
    assert process_probe.local_host_id() == "host:" + hashlib.sha256(b"0123456789abcdef").hexdigest()[:32]


# --- handoff result file --------------------------------------------------------------------------------------------------


def test_handoff_result_file_that_is_not_utf8_is_refused(tmp_path: Path) -> None:
    (tmp_path / "result.json").write_bytes(b'{"summary": "ok \xff"}')
    with pytest.raises(click.ClickException, match="UTF-8"):
        _load_result_file(tmp_path.resolve(), "result.json")
    (tmp_path / "good.json").write_text('{"summary": "完成"}', encoding="utf-8")
    assert _load_result_file(tmp_path.resolve(), "good.json") == {"summary": "完成"}


# --- venv base check ------------------------------------------------------------------------------------------------------


def test_pyvenv_cfg_that_is_not_utf8_is_a_reason_not_a_guess(tmp_path: Path) -> None:
    (tmp_path / "pyvenv.cfg").write_bytes(b"home = /opt/\xff/bin\nversion = 3.12.1\n")
    result = check_venv_base(prefix=str(tmp_path), base_prefix=str(tmp_path / "base"), running_version="3.12.1")
    assert any("不是合法 UTF-8" in reason for reason in result["reasons"])
    assert result["status"] != "ok"


# --- doc extractors -------------------------------------------------------------------------------------------------------


def test_extractors_skip_a_source_file_that_is_not_utf8_instead_of_reading_around_it(tmp_path: Path) -> None:
    checker = tmp_path / "checker.py"
    checker.write_bytes(b'def check_demo():\n    """Demo rule."""\n    # \xff\n')
    assert GateAstExtractor.extract_from_checker(checker) == []
    bridges = tmp_path / "bridges"
    bridges.mkdir()
    (bridges / "demo_bridge.py").write_bytes(b"from PySide6.QtCore import Slot\n\n# \xff\n\n@Slot()\ndef run():\n    pass\n")
    assert BridgeAstExtractor.extract_from_directory(bridges) == []
    cli_dir = tmp_path / "cli"
    cli_dir.mkdir()
    (cli_dir / "demo.py").write_bytes(b"# \xff\n\ndef cmd_run():\n    pass\n")
    # Skipped like a file that does not parse: the module falls back to its own entry instead of a command read out of damaged text.
    assert [command.name for command in CliAstExtractor.extract_from_directory(cli_dir)] == ["demo"]


def test_extractors_still_read_a_valid_source_file(tmp_path: Path) -> None:
    checker = tmp_path / "checker.py"
    checker.write_text('def check_demo():\n    """示例规则。"""\n', encoding="utf-8")
    assert [rule.rule_id for rule in GateAstExtractor.extract_from_checker(checker)] == ["GATE-DEMO"]


# --- backup list ----------------------------------------------------------------------------------------------------------


def test_backup_list_says_the_manifest_is_unreadable_when_it_does_not_decode(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    backup = tmp_path / "ledger.bak"
    backup.write_bytes(b"x")
    manifest = tmp_path / "ledger.bak.manifest.json"
    manifest.write_bytes(b'{"events": 3, "head_event_id": "e\xff"}')
    service = SimpleNamespace(list_backups=lambda: [backup], workspace_root=tmp_path.resolve())
    monkeypatch.setattr(backup_cli, "_service", lambda ctx: service)
    monkeypatch.setattr(backup_cli, "manifest_path", lambda path: manifest)

    result = CliRunner().invoke(backup_cli.list_backups_command, [])

    assert result.exit_code == 0 and "（清单无法读取）" in result.output and "3 条事件" not in result.output


# --- controlled executor event stream -------------------------------------------------------------------------------------


def test_event_stream_skips_a_line_that_is_not_utf8_but_keeps_its_bytes() -> None:
    lines = [b'{"event": "a\xff"}\n', b'{"event": "ok"}\n']
    capture = _BoundedCapture(1024)
    events: queue.Queue[dict[str, object] | None] = queue.Queue()
    stream = BytesIO(b"".join(lines))

    thread: threading.Thread = LocalCodexExecutor._drain_control_pipe(stream, capture, events)
    thread.join(timeout=5)

    seen = []
    while (item := events.get(timeout=1)) is not None:
        seen.append(item)
    assert seen == [{"event": "ok"}]
    assert b"a\xff" in bytes(capture._data)


# --- spec lint ------------------------------------------------------------------------------------------------------------


@pytest.mark.usefixtures("identity_guard_off")
def test_spec_lint_reports_a_spec_file_that_is_not_utf8(tmp_path: Path) -> None:
    spec_root = tmp_path / "00_Obsidian_Base全局规范文件仓库"
    domain_dir = spec_root / "01_项目管理域"
    domain_dir.mkdir(parents=True)
    (domain_dir / "001_测试规范_DEV.md").write_bytes("---\nspec_id: DEV-001\ntitle: 测试\nlifecycle: stable\n---\n".encode() + b"\xff\n")
    (spec_root / "spec_registry.json").write_text(
        json.dumps(
            {
                "workspace_root": str(tmp_path),
                "specs": {"DEV-001": {"canonical_path": "00_Obsidian_Base全局规范文件仓库/01_项目管理域/001_测试规范_DEV.md"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(spec_group, ["lint", "-w", str(tmp_path), "--format", "json"])

    assert result.exit_code == 0, result.output
    messages = [item["message"] for item in json.loads(result.output)["lint_results"]]
    assert any("不是合法 UTF-8" in message for message in messages)
