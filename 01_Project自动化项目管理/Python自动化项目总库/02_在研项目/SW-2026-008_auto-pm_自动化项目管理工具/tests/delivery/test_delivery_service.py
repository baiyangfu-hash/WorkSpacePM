"""tests"""
from __future__ import annotations

from pathlib import Path

import pytest
from auto_pm.delivery.constants import DIR_DELIVERY, DIR_EXECUTABLE, DIR_PACKAGE, MB
from auto_pm.delivery.delivery_service import DeliveryService


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

class TestBuild:
    def test_ok(self, proj: Path) -> None:
        svc = DeliveryService(proj)
        r = svc.build(version="V1.0.1", skip_pyinstaller=True, auto_package=False, product_name="auto-pm", summary="t")
        assert r["success"]
    def test_no_dist(self, tmp_path: Path) -> None:
        p = tmp_path / "nd"
        p.mkdir()
        r = DeliveryService(p).build(version="V1.0.1", skip_pyinstaller=True, product_name="auto-pm")
        assert not r["success"]
    def test_with_archive(self, proj: Path) -> None:
        dd = proj / DIR_DELIVERY
        dd.mkdir()
        (dd / DIR_EXECUTABLE).mkdir()
        (dd / DIR_EXECUTABLE / "o.exe").write_bytes(b"\x00" * (15 * MB))
        (dd / "CHANGELOG.md").write_text("## [1.0.0]\no\n", encoding="utf-8")
        r = DeliveryService(proj).build(version="V1.0.1", skip_pyinstaller=True, auto_package=False, product_name="auto-pm", summary="u")
        assert r["success"] and r["archive_path"] is not None

class TestPackage:
    def test_no_del(self, tmp_path: Path) -> None:
        p = tmp_path / "nd"
        p.mkdir()
        r = DeliveryService(p).package(version="V1.0.1", product_name="auto-pm")
        assert not r["success"]
    def test_verify(self, tmp_path: Path) -> None:
        p = tmp_path / "nz"
        p.mkdir()
        (p / DIR_PACKAGE).mkdir()
        r = DeliveryService(p).package(version="V1.0.1", product_name="auto-pm", verify_only=True)
        assert not r["success"]

class TestStatus:
    def test_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "em"
        p.mkdir()
        s = DeliveryService(p).status()
        assert s["delivery"] is None and s["package"] is None
