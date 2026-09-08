"""CLI delivery tests"""
from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.cli.__main__ import cli
from auto_pm.delivery.constants import MB
from click.testing import CliRunner


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()

@pytest.fixture
def proj(tmp_path: Path) -> Path:
    p = tmp_path / "tp"
    p.mkdir()
    d = p / "dist" / "auto-pm"
    d.mkdir(parents=True)
    (d / "auto-pm.exe").write_bytes(b"\x00" * (15 * MB))
    di = d / "_internal"
    di.mkdir()
    for i in range(500):
        (di / f"f_{i}.dll").write_text(f"d{i}", encoding="utf-8")
    return p

class TestDeliveryCLI:
    def test_build(self, runner: CliRunner, proj: Path) -> None:
        r = runner.invoke(cli, ["-w", str(proj), "delivery", "build", "--version", "V1.0.1", "--summary", "test"])
        assert r.exit_code == 0

    def test_status(self, runner: CliRunner, tmp_path: Path) -> None:
        p = tmp_path / "em"
        p.mkdir()
        r = runner.invoke(cli, ["-w", str(p), "delivery", "status"])
        assert r.exit_code == 0

    def test_archive_list(self, runner: CliRunner, tmp_path: Path) -> None:
        p = tmp_path / "al"
        p.mkdir()
        r = runner.invoke(cli, ["-w", str(p), "delivery", "archive", "list"])
        assert r.exit_code == 0

    def test_archive_clean(self, runner: CliRunner, tmp_path: Path) -> None:
        p = tmp_path / "ac"
        p.mkdir()
        r = runner.invoke(cli, ["-w", str(p), "delivery", "archive", "clean", "--dry-run"])
        assert r.exit_code == 0

    def test_package_no_delivery(self, runner: CliRunner, tmp_path: Path) -> None:
        p = tmp_path / "np"
        p.mkdir()
        r = runner.invoke(cli, ["-w", str(p), "delivery", "package", "--version", "V1.0.1"])
        assert r.exit_code != 0
