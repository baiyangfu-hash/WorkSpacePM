"""doctor 版本真源回归测试。"""

from __future__ import annotations

from pathlib import Path

from auto_pm.cli.doctor import run_doctor_check


def test_doctor_uses_active_infrastructure_version_when_workspace_has_no_pyproject(
    tmp_path: Path,
) -> None:
    result = run_doctor_check(tmp_path)

    assert result["project_version"] == "1.2.3"
    assert result["version_source"].endswith("pyproject.toml")
    # CHG-SCPT-2026-021: 平铺布局回退 00_Infrastructure，candidate 布局回退包自身 pyproject
