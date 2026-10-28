from __future__ import annotations

from auto_pm.infrastructure.config.app_config import AutoPmConfig


def test_settings() -> None:
    settings = AutoPmConfig()
    assert settings.app_name == "auto-pm"
    assert settings.log_level in ["INFO", "DEBUG"]
