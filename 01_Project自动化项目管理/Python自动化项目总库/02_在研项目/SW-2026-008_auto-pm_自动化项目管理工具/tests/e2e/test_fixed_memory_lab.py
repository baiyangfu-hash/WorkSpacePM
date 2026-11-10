"""D-205: the lab copies give a fixed memory reading and change nothing in the product."""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from tests.e2e import fixed_memory_lab as lab
from tests.e2e.test_closure_drill import LAUNCHER

REAL = lab.PROJECT / "auto_pm" / "infrastructure" / "memory_preflight.py"


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses look the module up by name while it executes
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def test_m01_the_lab_preflight_reads_a_fixed_healthy_value(tmp_path: Path) -> None:
    scripts = lab.build_lab(tmp_path)
    module = _load(tmp_path / "auto_pm" / "infrastructure" / "memory_preflight.py", "lab_memory_preflight")
    snapshot = module.read_commit()
    assert (snapshot.committed, snapshot.limit) == (8 * module.GIB, 64 * module.GIB)
    assert module.run_preflight().ok is True
    assert (scripts / "long_gate.py").is_file() and (scripts / "long_gate_drill.py").is_file()


def test_m02_the_product_rule_is_not_loosened_by_the_lab() -> None:
    """The same module, with a hot reading handed in, still refuses: only the *reading* is fixed in the lab."""

    module = _load(REAL, "real_memory_preflight")
    hot = module.CommitSnapshot(committed=40 * module.GIB, limit=64 * module.GIB, physical=32 * module.GIB, available=2 * module.GIB)  # D-207: 2 GiB left
    assert module.run_preflight(read=lambda: hot, list_all=lambda: ()).ok is False


def test_m03_building_a_lab_never_writes_into_the_product(tmp_path: Path) -> None:
    before = hashlib.sha256(REAL.read_bytes()).hexdigest()
    lab.build_lab(tmp_path)
    assert hashlib.sha256(REAL.read_bytes()).hexdigest() == before


def test_m04_the_drill_launcher_fixes_the_reading_before_the_cockpit_starts() -> None:
    assert LAUNCHER.index("read_commit") < LAUNCHER.index("cli()")
