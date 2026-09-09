"""PLC-HMI 概念映射：SFB 库函数（应用配置（全局配置管理/设置持久化））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from auto_pm import __app_name__


class AutoPmConfig(BaseSettings):
    app_name: str = __app_name__
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    # Add more ...

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        env_file=".env",
        # if a setting is set to blah= in env, it will be ignored and
        # the default value will be used
        env_ignore_empty=True,
        # settings that are not in the model will be ignored
        extra="ignore",
        # if settings are re-defined the new ones will be validated
        validate_assignment=True,
    )
