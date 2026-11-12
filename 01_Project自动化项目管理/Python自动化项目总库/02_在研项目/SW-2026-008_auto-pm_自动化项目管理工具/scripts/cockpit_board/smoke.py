"""驾驶舱总控屏冒烟：照双击启动的路子开窗口，挨页点一遍，看有没有报错、有没有卡在“正在读”、有没有空白页。

像设备上电后的点检：每个画面切过去看一眼，灯不红、数不乱、没有卡住，就算过；不判数据对不对。

用法（在 SW-2026-008 目录下；没有显示器的机器先设 QT_QPA_PLATFORM=offscreen）：
    python -B scripts/cockpit_board/smoke.py --root <控制根> [--out <截图目录>] [--wait 60] [其余参数同看板]
退出码：0＝每页都过；1＝至少一页没过（逐页写原因）；2＝窗口都没开起来。
只读：页面上的只读命令照常在后台跑（和真窗口一样），本脚本不点任何按钮、不写账本；给了 --out 才存截图。
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if __package__ in (None, ""):  # 直接 python scripts/cockpit_board/smoke.py 运行时
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QtMsgType, qInstallMessageHandler  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from cockpit_board import app as gui  # noqa: E402
from cockpit_board import shell, theme  # noqa: E402

READING = "正在读"
# Qt 自己的提示里这些是无害的（离屏插件、字体），不算页面报错
QT_NOISE = ("offscreen", "propagateSizeHints", "QFont", "fontconfig", "Fontconfig")


@dataclass
class PageCheck:
    key: str
    name: str
    problems: list[str] = field(default_factory=list)
    labels: int = 0
    shot: str = ""

    @property
    def ok(self) -> bool:
        return not self.problems


@dataclass
class SmokeReport:
    pages: list[PageCheck]
    startup_errors: list[str]

    @property
    def ok(self) -> bool:
        return not self.startup_errors and all(p.ok for p in self.pages)

    def lines(self) -> list[str]:
        out = [f"启动报错：{e}" for e in self.startup_errors]
        for page in self.pages:
            verdict = "过" if page.ok else "没过：" + "；".join(page.problems)
            out.append(f"{page.name}（{page.key}）{verdict}  文字 {page.labels} 处" + (f"  截图 {page.shot}" if page.shot else ""))
        out.append(f"合计 {sum(p.ok for p in self.pages)}/{len(self.pages)} 页过" + ("" if self.ok else "，有没过的"))
        return out


def nav_pages() -> list[tuple[str, str]]:
    """侧栏上能点到的页（项目经理身份），加最后一个“工程工位”身份页。"""
    return [(p.key, p.text) for p in shell.PAGES if p.nav] + [("ws", "工程工位")]


def _busy(window: Any) -> bool:
    jobs = [*window._threads, *window.decisions._jobs]
    return bool(window._reading_pages or window.decisions._reading or any(t.isRunning() for t in jobs))


def settle(qt: QApplication, window: Any, wait: float, sleep: Callable[[float], None] = time.sleep) -> bool:
    """转事件循环，直到后台读取都结束；超时返回 False。"""
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        qt.processEvents()
        if not _busy(window):
            qt.processEvents()
            return True
        sleep(0.05)
    qt.processEvents()
    return not _busy(window)


def _texts(widget: Any) -> list[str]:
    return [label.text() for label in widget.findChildren(QLabel) if label.isVisibleTo(widget)]


def run(window: Any, qt: QApplication, *, wait: float = 60.0, out: Path | None = None,
        pages: Sequence[tuple[str, str]] | None = None) -> SmokeReport:
    """window 已经建好（真窗口或测试窗口）。先等首次读取，再挨页切过去检查。"""
    errors: list[str] = []
    old_hook = sys.excepthook

    def hook(kind: type[BaseException], value: BaseException, tb: Any) -> None:  # Qt 槽函数里抛的异常走这里，不会打断循环
        errors.append("".join(traceback.format_exception_only(kind, value)).strip())

    def qt_message(mode: QtMsgType, _context: Any, message: str) -> None:
        if mode in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg) or (
            mode == QtMsgType.QtWarningMsg and not any(n in message for n in QT_NOISE)
        ):
            errors.append(f"Qt：{message}")

    sys.excepthook = hook
    previous_handler = qInstallMessageHandler(qt_message)
    startup: list[str] = []
    checks: list[PageCheck] = []
    try:
        if not settle(qt, window, wait):
            startup.append(f"首次读取 {wait:.0f} 秒没读完")
        startup += errors
        errors.clear()
        for key, name in pages or nav_pages():
            check = PageCheck(key, name)
            try:
                if key == "ws":
                    window.set_mode("ws")
                else:
                    if getattr(window, "mode", "pm") != "pm":
                        window.set_mode("pm")
                    window.goto(key)
            except Exception as error:  # noqa: BLE001 - 冒烟要把每一页的崩溃都记下来，不能停在第一页
                check.problems.append(f"切换时出错：{type(error).__name__}: {error}")
            if not settle(qt, window, wait):
                check.problems.append(f"{wait:.0f} 秒还在读")
            page = window.stack.currentWidget()
            texts = _texts(page)
            check.labels = len(texts)
            if not texts:
                check.problems.append("页面上一个字都没有")
            if key in window.read_pages and READING in window.read_pages[key].project_line.text():
                check.problems.append("页头还写着“正在读”")
            check.problems += errors
            errors.clear()
            if out is not None:
                out.mkdir(parents=True, exist_ok=True)
                path = out / f"{len(checks) + 1:02d}_{name}.png"
                window.grab().save(str(path))
                check.shot = path.name
            checks.append(check)
    finally:
        sys.excepthook = old_hook
        qInstallMessageHandler(previous_handler)
    return SmokeReport(checks, startup)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="驾驶舱总控屏冒烟（挨页点检，只读）", add_help=True)
    parser.add_argument("--out", default="", help="截图存这里（不给就不存）")
    parser.add_argument("--wait", type=float, default=60.0, help="每页最多等几秒读完")
    own, rest = parser.parse_known_args(argv)
    qt_existing = QApplication.instance()
    qt = qt_existing if isinstance(qt_existing, QApplication) else QApplication(sys.argv[:1])
    try:
        options = gui.parse_options(rest)
        qt.setStyleSheet(theme.build_qss(theme.LIGHT))
        gui.fill_identity(options)
        window = gui.CockpitWindow(options)
        if not options.station_project:
            options.station_project = gui.default_station_project(options.root)
        window.resize(1360, 1400)
        window.show()
        window.reload()
    except Exception:  # noqa: BLE001 - 窗口都没开起来：写清楚原因，退出码 2
        print("窗口没开起来：\n" + traceback.format_exc(), file=sys.stderr)
        return 2
    report = run(window, qt, wait=own.wait, out=Path(own.out) if own.out else None)
    for line in report.lines():
        print(line)
    window.close()
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
