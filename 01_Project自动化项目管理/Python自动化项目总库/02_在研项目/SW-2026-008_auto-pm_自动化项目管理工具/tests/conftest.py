from __future__ import annotations

import gc
import json
import os
import random
import tempfile
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

# 测试环境禁用审计日志文件写入：默认路径 ~/.auto-pm/audit/ 在 Trae Sandbox 等
# 受限环境下不可写，写操作会被沙箱拦截并污染 pytest 退出码（TD 修复统一收口）。
# 需在 auto_pm 任何 audit_log 触发前设置，故置于 conftest 顶层。
os.environ.setdefault("AUTO_PM_AUDIT_DIR", "off")
# 测试不调用本机真的 Siemens 插件命令行（PLC 验收门会自动去找它）；要用插件的测试自己注入替身。
# 指向一个不存在的文件 = “未找到插件”；子进程继承这个环境变量。用户显式设置时不覆盖。
os.environ.setdefault(
    "AUTO_PM_SIEMENS_LSP", str(Path(tempfile.gettempdir()) / "auto-pm-tests-no-siemens-lsp.exe")
)

# rich 按终端宽度给 console.print 折行；窄终端会把整句话拆开，字符串断言随之失败。
# 测试一律按 200 列输出（强制覆盖，不管开发者终端多宽；子进程继承）。
os.environ["COLUMNS"] = "200"

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

# botocore likes us-east-1
TEST_AWS_REGION = "us-east-1"
TEST_S3_BUCKET = "test-bucket"
_TEST_QAPPLICATION: object | None = None


def pytest_configure(config: pytest.Config) -> None:
    """在模块级 fixture 创建 QCoreApplication 前固定唯一 QApplication。"""
    del config
    global _TEST_QAPPLICATION
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    if not isinstance(app, QApplication):
        raise pytest.UsageError("测试进程已创建非 Widgets 的 Qt 应用实例")
    _TEST_QAPPLICATION = app


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Randomise the order of tests to avoid flakiness.

    使用固定 seed 的 Random 实例，确保 pytest-xdist 多 worker 收集时
    各 worker 的收集顺序一致（xdist 会比较各 worker 的收集结果）。
    """
    rng = random.Random(20260627)
    rng.shuffle(items)


@pytest.fixture(scope="session")
def qapp() -> Generator[QApplication, None, None]:
    """全测试目录共享的 QApplication 实例（TD-T14 修复统一收口）。

    tests/ui 和 tests/gui 共用同一 session 级 qapp，避免：
    - tests/ui/test_vartable_tab.py 的 module 级 qapp 覆盖 session 级
    - tests/gui/conftest.py 的本地 qapp 与 tests/ui/conftest.py 重复定义
    两者均返回 QApplication.instance()，但作为两个独立 fixture 会被
    pytest 分别管理，放大 Qt 会话 teardown 的不确定性。
    """
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication

    app = _TEST_QAPPLICATION
    assert isinstance(app, QApplication)
    yield app


# Qt tests whose leftovers must not be freed by the cyclic garbage collector at a random later moment (see tests/modbus/conftest.py).
_QT_TEST_PREFIXES = ("tests/modbus/", "tests/qml/", "tests/ui/", "tests/e2e/test_pmf_gui.py")


@pytest.fixture(autouse=True)
def _qt_garbage_is_collected_on_the_gui_thread(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """After a Qt test: let the global thread pool finish, then collect garbage here, on the GUI thread.

    Left to itself the collector runs on whichever thread allocates next - possibly a QThreadPool worker - and would then
    destroy a dead test's QObjects and timers from the wrong thread (access violation 0xC0000005 in the single-process gate run).
    """
    yield
    if not request.node.nodeid.replace("\\", "/").startswith(_QT_TEST_PREFIXES):
        return
    from PySide6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(10_000)
    gc.collect()


@pytest.fixture
def tests_dir() -> Path:
    """返回 tests/ 目录路径（供元测试扫描测试文件用）。"""
    return Path(__file__).parent


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """创建临时工作空间，含一个模拟 PLC 项目（对齐 LSP-907 标准目录结构）"""
    project_dir = tmp_path / "DJ-2026-TEST_测试项目"
    project_dir.mkdir()
    # .plc.json
    (project_dir / ".plc.json").write_text(
        json.dumps(
            {
                "name": "DJ-2026-TEST",
                "version": "V1.0.0",
                "description": "测试项目",
                "type": "standard",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    # LSP-907 标准目录结构（12 个）
    for d in [
        "01_启动", "02_PLC程序", "03_HMI设计",
        "04_现场调试", "05_测试与验证", "06_文档与交付",
        "07_技术支持", "08_备件管理", "09_项目总结", "10_知识库",
        "11_监控", "12_驱动器与设备",
    ]:
        (project_dir / d).mkdir()

    # 变更管理体系
    chg_dir = project_dir / "11_监控" / "01_变更管理"
    (chg_dir / "01_变更单").mkdir(parents=True, exist_ok=True)
    (chg_dir / "02_变更记录").mkdir(parents=True, exist_ok=True)
    (chg_dir / "02_变更记录" / "01_版本变更台帐.md").write_text("# 版本变更台帐\n", encoding="utf-8")

    # 交付文档实质化
    (project_dir / "04_现场调试" / "现场调试计划.md").write_text("# 现场调试计划\n", encoding="utf-8")
    (project_dir / "06_文档与交付" / "验收交付清单.md").write_text("# 验收交付清单\n", encoding="utf-8")

    # PM_SESSION
    (project_dir / "PM_SESSION_DJ-2026-TEST.md").write_text(
        "# PM_SESSION\n", encoding="utf-8"
    )
    # PRD 目录
    (project_dir / "PRD").mkdir()
    return tmp_path
