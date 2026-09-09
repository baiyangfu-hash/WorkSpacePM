"""Windows PDF export isolation coverage for CHG-SCPT-2026-195."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_pdf_export_in_clean_process_has_no_windows_com_trace(tmp_path: Path) -> None:
    """Export a real PDF in a child process without printer-backend COM output."""
    source = tmp_path / "source.md"
    output = tmp_path / "export.pdf"
    source.write_text("# CHG-195 PDF isolation\n\nQPdfWriter export.", encoding="utf-8")

    script = """
import os
from pathlib import Path
from auto_pm.ui.qml.bridges.delivery_bridge import DeliveryBridge
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
result = DeliveryBridge(facade=None).exportDocToPdf(
    os.environ[\"CHG195_SOURCE\"], os.environ[\"CHG195_OUTPUT\"]
)
if not result[\"success\"]:
    raise RuntimeError(result[\"message\"])
output = Path(os.environ[\"CHG195_OUTPUT\"])
if not output.exists() or not output.read_bytes().startswith(b\"%PDF-\"):
    raise RuntimeError(\"PDF output is missing or invalid\")
"""
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment["CHG195_SOURCE"] = str(source)
    environment["CHG195_OUTPUT"] = str(output)
    environment["PYTHONPATH"] = str(Path(__file__).parents[2])

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[2],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    diagnostics = f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    assert completed.returncode == 0, diagnostics
    assert "0x80040155" not in diagnostics.lower(), diagnostics
    assert output.read_bytes().startswith(b"%PDF-")
