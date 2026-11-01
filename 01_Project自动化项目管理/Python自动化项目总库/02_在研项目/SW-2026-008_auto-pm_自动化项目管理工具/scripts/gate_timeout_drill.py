"""质量门超时演练（TD-SW008-188 / 189 在 Windows 上的实测脚本，Linux 上也能跑）。

做三件事，每件都打印 PASS 或 FAIL，全过退出码 0，否则 1：
1. 门禁里起“子进程 + 孙进程”（孙进程每 50 毫秒写一次心跳文件），门禁超时后整棵进程树必须死透（Windows 上走 ``taskkill /F /T``）。
2. 超时按时返回，不会被孙进程占着的管道拖住。
3. 门禁卡在纯 Python 死循环里，超时后检查线程必须被中止，不在后台继续空转。

运行方式（在 SW-2026-008 项目目录里）::

    python scripts/gate_timeout_drill.py
"""

from __future__ import annotations

import sys
import tempfile
import threading
import time
from pathlib import Path

# 自动将项目根目录加入 sys.path
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from auto_pm.application.core import evidence_collection_service as ecs  # noqa: E402
from auto_pm.infrastructure.process_scope import leaked_threads, run_in_scope  # noqa: E402

# 孙进程：不停写心跳；整棵树死透以后心跳才会停。
_GRANDCHILD = "import pathlib, sys, time\nbeat = pathlib.Path(sys.argv[1])\nwhile True:\n    beat.write_text(str(time.time()))\n    time.sleep(0.05)\n"
# 子进程：起孙进程（继承输出管道）后自己睡着。
_CHILD = "import subprocess, sys, time\nsubprocess.Popen([sys.executable, '-c', sys.argv[2], sys.argv[1]])\ntime.sleep(120)\n"
_GATE_THREAD = "plc-quality-gate"


def _report(name: str, passed: bool, detail: str) -> bool:
    """打印一条结果并原样返回是否通过。"""

    print(f"[{'PASS' if passed else 'FAIL'}] {name}：{detail}")
    return passed


def _heartbeat_stopped(beat: Path) -> bool:
    """心跳文件一整秒没有再被写过，就算整棵树已经死透。"""

    before = beat.read_text(encoding="utf-8", errors="replace")
    time.sleep(1.5)
    return beat.read_text(encoding="utf-8", errors="replace") == before


def _drill_process_tree(workdir: Path) -> bool:
    """演练 1、2：超时杀整棵进程树，并且按时返回。"""

    beat = workdir / "beat.txt"

    def work() -> tuple[str, int | None]:
        run_in_scope([sys.executable, "-c", _CHILD, str(beat), _GRANDCHILD], workdir, {}, 120)
        return "unreachable", 0

    started = time.monotonic()
    try:
        ecs._run_bounded(work, 3)
    except ecs._PlcGateTimeoutError:
        pass
    elapsed = time.monotonic() - started
    in_time = _report(
        "按时返回（不被孙进程占着的管道拖住）",
        elapsed < 25,
        f"用时 {elapsed:.1f} 秒（期望 3～10 秒）",
    )
    deadline = time.monotonic() + 10
    while not beat.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    dead = beat.exists() and _heartbeat_stopped(beat)
    tree = _report(
        "整棵进程树已被杀掉",
        dead,
        "孙进程的心跳已停" if dead else "孙进程还在写心跳，进程树没杀干净",
    )
    return in_time and tree


def _drill_python_loop() -> bool:
    """演练 3：纯 Python 死循环的检查线程超时后被中止。"""

    def spin() -> tuple[str, int | None]:
        counter = 0
        while True:
            counter += 1

    try:
        ecs._run_bounded(spin, 1)
    except ecs._PlcGateTimeoutError as error:
        message = str(error)
    else:
        return _report("纯 Python 死循环的检查线程被中止", False, "超时没有触发")
    deadline = time.monotonic() + 10
    while (
        any(t.name == _GATE_THREAD and t.is_alive() for t in threading.enumerate())
        and time.monotonic() < deadline
    ):
        time.sleep(0.05)
    gone = not any(t.name == _GATE_THREAD and t.is_alive() for t in threading.enumerate())
    return _report("纯 Python 死循环的检查线程被中止", gone and not leaked_threads(), message)


def main() -> int:
    """跑完全部演练，返回退出码。"""

    print(f"平台 {sys.platform}，Python {sys.version.split()[0]}")
    with tempfile.TemporaryDirectory(prefix="gate-drill-") as tmp:
        results = [_drill_process_tree(Path(tmp)), _drill_python_loop()]
    print("全部通过" if all(results) else "有失败项，见上")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
