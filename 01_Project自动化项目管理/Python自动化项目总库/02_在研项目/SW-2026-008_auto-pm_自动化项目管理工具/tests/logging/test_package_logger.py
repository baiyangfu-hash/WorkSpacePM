"""运行日志必须收得到各模块日志：AppContext 把 handler 挂在包日志器 ``auto_pm`` 上。"""

from __future__ import annotations

import io
import logging
import re
import sys
from collections.abc import Generator
from pathlib import Path

import pytest

from auto_pm.app_context import AppContext
from auto_pm.infrastructure.logging.logging import PACKAGE_LOGGER_NAME, setup_logger

_PACKAGE_DIR = Path(__file__).resolve().parents[2] / "auto_pm"


@pytest.fixture
def fresh_package_logger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Path, None, None]:
    """隔离 ``auto_pm`` 日志器的全局状态，并把 ``~`` 指到临时目录；返回 ``auto-pm.log`` 路径。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    package = logging.getLogger(PACKAGE_LOGGER_NAME)
    saved = (list(package.handlers), package.level)
    package.handlers.clear()
    yield tmp_path / ".auto-pm" / "logs" / "auto-pm.log"
    for handler in package.handlers:
        handler.close()
    package.handlers[:] = saved[0]
    package.setLevel(saved[1])


def _flush() -> None:
    for handler in logging.getLogger(PACKAGE_LOGGER_NAME).handlers:
        handler.flush()


def test_closure_refusal_reaches_auto_pm_log(fresh_package_logger: Path) -> None:
    from auto_pm.application.core import pm_cockpit_service

    AppContext(workspace_root=str(fresh_package_logger.parent))
    try:
        raise RuntimeError("C05 登记顺序与存证顺序不一致")
    except RuntimeError:
        pm_cockpit_service.log.exception("Cockpit closure refused: %s", "MIS-TEST-001")
    _flush()

    text = fresh_package_logger.read_text(encoding="utf-8")
    assert "Cockpit closure refused: MIS-TEST-001" in text
    assert "C05 登记顺序与存证顺序不一致" in text  # 回溯（真正的拒绝原因）也在
    assert "auto_pm.application.core.pm_cockpit_service" in text  # 能看出是哪个模块报的


def test_info_goes_to_file_but_not_to_console(
    fresh_package_logger: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """反例：控制台只放 WARNING 以上，命令行输出不因修复多出 INFO 噪声。"""
    monkeypatch.setattr(logging.getLogger(), "handlers", [])  # 真实命令行：根日志器没有 handler
    AppContext(workspace_root=str(fresh_package_logger.parent))
    module_logger = logging.getLogger("auto_pm.core.some_service")
    module_logger.info("普通进度")
    module_logger.warning("收口待同步")
    _flush()

    err = capsys.readouterr().err
    assert "普通进度" not in err
    assert "收口待同步" in err
    text = fresh_package_logger.read_text(encoding="utf-8")
    assert "普通进度" in text and "收口待同步" in text


def test_console_stays_quiet_when_the_host_configured_the_root_logger(
    fresh_package_logger: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """反例：宿主已给根日志器配了 handler（如 pytest），控制台不重复打印；修复前兜底输出在这种情况下也不打。"""
    monkeypatch.setattr(logging.getLogger(), "handlers", [logging.NullHandler()])
    AppContext(workspace_root=str(fresh_package_logger.parent))
    logging.getLogger("auto_pm.change.parser").warning("规范校验违规")
    _flush()

    assert "规范校验违规" not in capsys.readouterr().err
    assert "规范校验违规" in fresh_package_logger.read_text(encoding="utf-8")


def test_logger_outside_the_package_is_not_collected(fresh_package_logger: Path) -> None:
    """反例：与包无父子关系的名字（如旧的 ``auto-pm``）收不进来，说明判据确实是层级。"""
    AppContext(workspace_root=str(fresh_package_logger.parent))
    logging.getLogger("auto-pm.legacy").error("不该进文件")
    logging.getLogger("auto_pm.core.x").error("应该进文件")
    _flush()

    text = fresh_package_logger.read_text(encoding="utf-8")
    assert "应该进文件" in text
    assert "不该进文件" not in text


def test_console_handler_follows_the_current_stderr(
    fresh_package_logger: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Click 测试换掉再关闭 stderr 后，日志要写到当时的 stderr，而不是已关闭的旧流。"""
    first = io.StringIO()
    monkeypatch.setattr(sys, "stderr", first)
    setup_logger(app_name=PACKAGE_LOGGER_NAME, log_level="INFO", console_level="WARNING")
    first.close()
    second = io.StringIO()
    monkeypatch.setattr(sys, "stderr", second)

    logging.getLogger("auto_pm.core.y").warning("换流之后")

    assert "换流之后" in second.getvalue()


def test_console_level_never_goes_below_log_level(fresh_package_logger: Path) -> None:
    logger = setup_logger(app_name=PACKAGE_LOGGER_NAME, log_level="ERROR", console_level="WARNING")
    console = [h for h in logger.handlers if not isinstance(h, logging.FileHandler)]
    assert [h.level for h in console] == [logging.ERROR]


_GET_LOGGER = re.compile(r"logging\.getLogger\(([^)]*)\)")


def test_every_package_logger_sits_under_auto_pm() -> None:
    """同类排查固化成检查：包内每个 getLogger 要么用 ``__name__``，要么是 ``auto_pm`` 开头的字面名。"""
    offenders: list[str] = []
    for path in sorted(_PACKAGE_DIR.rglob("*.py")):
        for match in _GET_LOGGER.finditer(path.read_text(encoding="utf-8")):
            argument = match.group(1).strip()
            if argument in ("__name__", "app_name", ""):  # "" 是读根日志器（判断宿主是否已配置），不往里写日志
                continue
            literal = argument.strip("\"'")
            if literal == PACKAGE_LOGGER_NAME or literal.startswith(PACKAGE_LOGGER_NAME + "."):
                continue
            offenders.append(f"{path.relative_to(_PACKAGE_DIR)}: getLogger({argument})")
    assert offenders == []


def test_app_context_configures_the_package_logger(fresh_package_logger: Path) -> None:
    context = AppContext(workspace_root=str(fresh_package_logger.parent))
    assert context.logger.name == PACKAGE_LOGGER_NAME
    ancestors = []
    node: logging.Logger | None = logging.getLogger("auto_pm.application.core.pm_closure_service")
    while node is not None:
        ancestors.append(node.name)
        node = node.parent
    assert PACKAGE_LOGGER_NAME in ancestors
    assert any(
        isinstance(h, logging.FileHandler) for h in logging.getLogger(PACKAGE_LOGGER_NAME).handlers
    )
