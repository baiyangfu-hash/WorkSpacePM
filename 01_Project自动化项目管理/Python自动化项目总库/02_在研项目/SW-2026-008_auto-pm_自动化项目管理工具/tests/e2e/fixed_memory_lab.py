"""A lab copy of the long-gate scripts whose memory reading is fixed, so a test result never depends on the machine that runs it (D-205).

2026-11-09: 42 e2e tests failed on the laptop only because its committed memory was above the preflight's limit at that moment.
The preflight must keep refusing a hot machine, and it has (on purpose) no switch an agent could set.  So the tests do not touch
it: ``scripts/long_gate.py`` finds ``auto_pm/infrastructure/memory_preflight.py`` next to itself, and a copy of the script placed in a
throw-away tree finds the copy of that module with ``read_commit`` replaced by a fixed, healthy reading.  The product files are
read, never changed.
"""

from __future__ import annotations

import atexit
import shutil
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
SCRIPT_NAMES = ("long_gate.py", "long_gate_drill.py")
#: 8 GiB committed of a 64 GiB limit on a 32 GiB machine: far below every rule, whatever the rules are set to.
FIXED_READING = """

# --- lab copy (tests/e2e/fixed_memory_lab.py): a fixed, healthy reading instead of the host's -----------------------------
def read_commit() -> CommitSnapshot | None:
    return CommitSnapshot(committed=8 * GIB, limit=64 * GIB, physical=32 * GIB)
"""


def build_lab(root: Path) -> Path:
    """Copy the scripts and the patched preflight under ``root``; returns the lab's ``scripts`` folder."""

    scripts = root / "scripts"
    preflight_dir = root / "auto_pm" / "infrastructure"
    scripts.mkdir(parents=True)
    preflight_dir.mkdir(parents=True)
    for name in SCRIPT_NAMES:
        shutil.copyfile(PROJECT / "scripts" / name, scripts / name)
    real = (PROJECT / "auto_pm" / "infrastructure" / "memory_preflight.py").read_text(
        encoding="utf-8"
    )
    (preflight_dir / "memory_preflight.py").write_text(
        real + FIXED_READING, encoding="utf-8", newline="\n"
    )
    return scripts


def lab_script(name: str = "long_gate.py") -> Path:
    """A path to ``name`` inside a fresh lab, removed when the test process ends."""

    root = Path(tempfile.mkdtemp(prefix="long-gate-lab-"))
    atexit.register(shutil.rmtree, root, True)
    return build_lab(root) / name
