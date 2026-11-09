from __future__ import annotations

import gc
import json
import os
import random
import sys
import tempfile
from collections.abc import Callable, Generator
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING

import pytest

from tests.ledger_isolation import INHERITED_COCKPIT_ENV, install_tripwire, real_ledger_paths
from tests.quality_tools_gate import missing_quality_modules, skip_reason

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


def identity_guard_use_is_refused(item: object) -> bool:
    """A test marked ``production_guards`` (exit drills, CHG-SCPT-2026-476) must not switch the runtime-identity guard off.

    The drills exist to show that the way out works with every guard the cockpit ships with; the old recovery tests switched
    the identity guard off while building the scene, which is why they could never see two guards block each other.
    """

    marker = getattr(item, "get_closest_marker")("production_guards")  # noqa: B009 - ``item`` is a pytest Item or a test double
    return marker is not None and "identity_guard_off" in getattr(item, "fixturenames", ())


def pytest_runtest_setup(item: pytest.Item) -> None:
    if identity_guard_use_is_refused(item):
        pytest.fail("production_guards 演练不许用 identity_guard_off：演练要在全部生产护栏打开时走出口", pytrace=False)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Randomise the order of tests to avoid flakiness.

    使用固定 seed 的 Random 实例，确保 pytest-xdist 多 worker 收集时
    各 worker 的收集顺序一致（xdist 会比较各 worker 的收集结果）。
    """
    rng = random.Random(20260627)
    rng.shuffle(items)
    reason = skip_reason(missing_quality_modules(), os.environ)
    if reason:
        skip = pytest.mark.skip(reason=reason)
        for item in items:
            if "needs_quality_tools" in item.keywords:
                item.add_marker(skip)


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


@pytest.fixture(autouse=True)
def _no_ambient_agent_markers(monkeypatch: pytest.MonkeyPatch) -> None:
    """A test never inherits "I am an agent" from the shell that started pytest.

    Approvals, project deletion and the PIN setup refuse a session that carries an agent marker (CLAUDECODE, AUTO_PM_AGENT,
    CODEX_*).  Run from inside an agent session, every test that approves something would fail for that reason alone, and
    the same test would pass in CI.  A test that needs a marker sets it itself with ``monkeypatch.setenv``.
    """

    from auto_pm.application.core.lease_handover_service import AGENT_MARKERS

    for name in AGENT_MARKERS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _no_inherited_cockpit_roots() -> Generator[None, None, None]:
    """A test never inherits the cockpit's workspace / control-root variables from the process that started pytest (D-108).

    ``long-run --worktree`` exports them for acceptance commands; a pytest run under it would otherwise let the e2e drills'
    child processes treat the real control root as the fixture's root.  A test that needs one sets it with ``monkeypatch.setenv``.
    It keeps its own ``MonkeyPatch`` (as ``identity_guard_off`` does): a test that calls the shared ``monkeypatch.undo()`` midway
    would otherwise put the inherited values back (19 such calls in the suite, audit 1 of #617).
    """

    with pytest.MonkeyPatch.context() as patcher:
        for name in INHERITED_COCKPIT_ENV:
            patcher.delenv(name, raising=False)
        yield


@pytest.fixture(scope="session", autouse=True)
def _real_ledger_is_off_limits() -> Generator[None, None, None]:
    """Opening a ``ContinuityStore`` on the real ledger from inside the test run raises, instead of writing to it (D-110)."""

    from auto_pm.infrastructure.continuity_store import ContinuityStore

    paths = real_ledger_paths(os.environ, Path(__file__).resolve().parent)
    remove = install_tripwire(ContinuityStore, paths)
    try:
        yield
    finally:
        remove()


@pytest.fixture(autouse=True)
def _memory_headroom_is_fine(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """``pm verify`` and ``long_gate launch`` refuse to start on a machine near its commit limit (11-03 laptop memory P1).

    A developer's laptop under load must not turn every test that calls them red, so the reading is a healthy one for every test.
    The rule and the readers have their own tests (``test_memory_preflight.py``), which pass their own readings.  A test marked
    ``real_machine`` compares the real reader with the operating system's own counter (11-03 real-machine check of ``long-run``);
    it gets the real function, or the comparison would be a fake number against a real one.
    """

    if request.node.get_closest_marker("real_machine") is not None:
        return
    from auto_pm.infrastructure import memory_preflight

    monkeypatch.setattr(
        memory_preflight, "read_commit", lambda: memory_preflight.CommitSnapshot(committed=4 * 2**30, limit=64 * 2**30, physical=32 * 2**30)
    )
    # D-168: ``require_headroom(label=...)`` arms the caller for the memory gate by writing a record into the real control root's
    # ``.auto-pm/memory-gate-arm``; no test may do that (the arming itself is tested with an explicit ``start`` in test_memory_gate.py).
    monkeypatch.setattr(memory_preflight, "arm_dir", lambda start=None: None)


@pytest.fixture(autouse=True)
def _process_table_of_this_host_is_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests that kill a child and expect "dead" must not depend on how the machine that runs them mounts /proc.

    A container, WSL or a ``hidepid`` mount makes the probe answer "could not observe" for a missing process on purpose
    (``process_probe.procfs_view_problem``).  Those cases are tested in ``test_process_probe.py`` with a fake /proc; every
    other test sees a complete table.
    """

    from auto_pm.infrastructure import process_probe

    monkeypatch.setattr(process_probe, "_view_problem", lambda: "")


@pytest.fixture(scope="session", autouse=True)
def _runs_may_start_in_the_test_repo() -> Generator[Callable[[Path, Path], bool], None, None]:
    """Throw-away test repositories use their own root as the Run's station; the real rule is tested on its own.

    ``ContinuityExecutionService.start_run`` refuses a worktree that is the control root (WS-001, TD-SW008-267).  Hundreds of
    fixtures build a repository in ``tmp_path`` and start the Run right there, which is the one thing production forbids, so the
    rule is off for the whole session (module- and class-scoped fixtures start Runs too, before any per-test fixture could act)
    except in tests that request ``control_root_guard_on`` (``test_run_start_control_root_guard.py``).  Yields the real rule for it.
    """

    from auto_pm.application.core import continuity_execution_service

    real = continuity_execution_service._worktree_is_the_control_root
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(continuity_execution_service, "_worktree_is_the_control_root", lambda _worktree, _root: False)
        yield real


@pytest.fixture
def control_root_guard_on(
    monkeypatch: pytest.MonkeyPatch, _runs_may_start_in_the_test_repo: Callable[[Path, Path], bool]
) -> None:
    """Put the production rule back after the autouse fixture above switched it off."""

    from auto_pm.application.core import continuity_execution_service

    monkeypatch.setattr(continuity_execution_service, "_worktree_is_the_control_root", _runs_may_start_in_the_test_repo)


@pytest.fixture
def control_root_guard_switch(
    monkeypatch: pytest.MonkeyPatch, _runs_may_start_in_the_test_repo: Callable[[Path, Path], bool]
) -> Callable[[], None]:
    """The switch that puts the production rule back, for a test that builds its scene with the rule off first.

    Same rule as ``control_root_guard_on`` (and listed in the same ratchet), but applied when the test calls the returned function:
    a scene that starts its historical Runs in the throw-away repository root must be built before the rule is on.
    """

    from auto_pm.application.core import continuity_execution_service

    def switch() -> None:
        monkeypatch.setattr(continuity_execution_service, "_worktree_is_the_control_root", _runs_may_start_in_the_test_repo)

    return switch


# Qt tests whose leftovers must not be freed by the cyclic garbage collector at a random later moment (the cockpit Modbus tool that this was written for has been removed; the same rule keeps protecting the other Qt tests).
_QT_TEST_PREFIXES = ("tests/qml/", "tests/ui/", "tests/e2e/test_pmf_gui.py")


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


IDENTITY_GUARD_NAMES = (
    "require_runtime_identity",
    "warn_runtime_identity",
    "require_runtime_identity_for_change",
    "require_runtime_identity_for_card",
    "require_runtime_identity_for_workspace",
)


def _no_identity_check(*_a: object, **_k: object) -> None:
    return None


def _command_modules() -> list[ModuleType]:
    """Every loaded command-line module, whatever its name (a fixed name list went stale: 24 names against 68 files, D-155)."""

    return [module for name, module in list(sys.modules.items()) if module is not None and name.startswith("auto_pm.ui.cli.")]


@pytest.fixture
def identity_guard_off() -> Generator[None, None, None]:
    """For tests about something other than the runtime identity, whose fixtures have no registered project anchor.

    The guard itself is covered in ``test_runtime_identity_guard.py``, which does not use this fixture.  It keeps its own
    ``MonkeyPatch`` so a test that calls the shared ``monkeypatch.undo()`` midway does not switch the guard back on.

    D-155: the scan covers ``runtime_identity_guard`` itself, which switches the checks off at their source, so a command module first
    imported *after* this fixture starts binds the no-op as well; modules already loaded are found by scanning, not by a name list.  On the way out, any module
    that bound the no-op while the fixture was on gets the original back, or it would carry "guard off" into the next test.
    """
    from auto_pm.ui.cli import runtime_identity_guard as source

    originals = {name: getattr(source, name) for name in IDENTITY_GUARD_NAMES}
    with pytest.MonkeyPatch.context() as patcher:
        for module in _command_modules():
            for name, original in originals.items():
                if getattr(module, name, None) is original:
                    patcher.setattr(module, name, _no_identity_check)
        try:
            yield
        finally:
            for module in _command_modules():
                for name, original in originals.items():
                    if getattr(module, name, None) is _no_identity_check:
                        setattr(module, name, original)
