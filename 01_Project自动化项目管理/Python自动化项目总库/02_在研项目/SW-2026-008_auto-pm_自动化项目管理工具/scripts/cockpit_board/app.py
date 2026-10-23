"""主窗口：顶栏（页面、模式、网络）、后台读取、把 viewmodel 交给各画面。

读取只读：账本由 pm_dashboard 拷到临时目录后 mode=ro + query_only；老后台只在手动“重新读取”且
TD-105 合并后才调 snapshot()（见 LEGACY_ALLOWED）。工程工位的动作走 actions.py，在后台线程跑。
GitHub（PR、门禁、安全签字、审计）走 scripts/github_collector.py，只 GET，在后台线程跑；读不到画面显示“未知”。
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import traceback
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import github_collector as gh  # noqa: E402
import pm_dashboard as pd  # noqa: E402
from PySide6.QtCore import QObject, QThread, QTimer, Signal  # noqa: E402
from PySide6.QtGui import QGuiApplication, QPalette  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from cockpit_board import actions, theme  # noqa: E402
from cockpit_board import viewmodel as vm
from cockpit_board.widgets import common as c  # noqa: E402
from cockpit_board.widgets.home import HomePage  # noqa: E402
from cockpit_board.widgets.issues import IssuesPage  # noqa: E402
from cockpit_board.widgets.project_page import ProjectPage  # noqa: E402
from cockpit_board.widgets.projects import ProjectsPage  # noqa: E402
from cockpit_board.widgets.station import StationPage  # noqa: E402

WINDOW_TITLE = "驾驶舱总控屏"
AUTO_REFRESH_MINUTES = 10
# TD-105（Windows 禁写锁）合并前不调老后台 snapshot()；合并后改 True，且只在手动“重新读取”时调。
LEGACY_ALLOWED = False
GAP9_MERGED = False  # 缺口⑨防冒签合并后，“批准范围 / 开工”才开放


# ---------------------------------------------------------------- 后台线程


class BoardLoader(QThread):
    loaded = Signal(object, bool)
    failed = Signal(str)

    def __init__(self, options: argparse.Namespace, use_legacy: bool, parent: QObject | None) -> None:
        super().__init__(parent)
        self.options, self.use_legacy = options, use_legacy

    def run(self) -> None:
        try:
            self.loaded.emit(load_board(self.options, self.use_legacy), self.use_legacy)
        except Exception as error:  # noqa: BLE001 - 读失败只在状态栏说一声，窗口不挂
            self.failed.emit(f"{type(error).__name__}: {error}")


class ActionRunner(QThread):
    """工程工位的本机动作在后台跑，界面不卡；回执发回主线程。"""

    done = Signal(object)
    probed = Signal(bool)

    def __init__(self, job, parent: QObject | None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.job = job

    def run(self) -> None:
        result = self.job()
        if isinstance(result, bool):
            self.probed.emit(result)
        else:
            self.done.emit(result)


class GithubLoader(QThread):
    """GitHub 采集在后台读；collect() 自己吞掉所有读失败，变成 Snapshot.state。"""

    loaded = Signal(object)

    def __init__(self, options: argparse.Namespace, parent: QObject | None) -> None:
        super().__init__(parent)
        self.options = options

    def run(self) -> None:
        self.loaded.emit(load_github(self.options))


def load_github(options: argparse.Namespace) -> gh.Snapshot | None:
    if options.no_github:
        return None
    return gh.collect(
        options.github_repo, options.root, options.reviews_dirs, options.github_cache,
        options.now or datetime.now(UTC), fetch=getattr(options, "github_fetch", None), offline=options.no_net,
    )


def load_board(options: argparse.Namespace, use_legacy: bool) -> pd.Board:
    now = options.now or datetime.now(UTC)
    board = pd.build_board(
        options.root, options.db, now, use_git=not options.no_git,
        use_legacy=use_legacy, legacy_factory=getattr(options, "legacy_factory", None),
        ledger_reader=getattr(options, "ledger_reader", "auto"),
    )
    if options.examples:
        board = pd.add_examples(board, now)
    return board


# ---------------------------------------------------------------- 主窗口


class CockpitWindow(QMainWindow):
    def __init__(self, options: argparse.Namespace) -> None:
        super().__init__()
        self.options = options
        self.offset: timezone = options.offset
        self.board: pd.Board | None = None
        self.github: gh.Snapshot | None = None
        self.home_vm: vm.HomeVM | None = None
        self.online: bool | None = None if not options.no_net else False
        self.mode = "pm"
        self.bc_digest: str | None = None  # 预览那一刻 02_业务变更记录.md 的指纹
        self._threads: list[QThread] = []
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1360, 880)

        central = QWidget()
        central.setObjectName("page")
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._topbar())
        self.stack = QStackedWidget()
        self.home = HomePage(self.open_project, self.copy_text)
        self.issues = IssuesPage(self.open_project)
        self.projects = ProjectsPage(self.open_project)
        self.project = ProjectPage(lambda: self.goto("home"), self.copy_text)
        self.station = StationPage(self.open_project, self.copy_text)
        self.station.action.connect(self.run_action)
        for page in (self.home, self.issues, self.projects, self.project, self.station):
            self.stack.addWidget(page)
        outer.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.timer = QTimer(self)
        self.timer.setInterval(AUTO_REFRESH_MINUTES * 60 * 1000)
        self.timer.timeout.connect(self.reload)

    def _topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topbar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(theme.SPACE * 2, theme.SPACE, theme.SPACE * 2, theme.SPACE)
        row.addWidget(c.label("驾驶舱", "title", wrap=False))
        self.page_buttons: dict[str, object] = {}
        group = QButtonGroup(self)
        for key, text in (("home", "今天"), ("issues", "问题"), ("projects", "全部项目")):
            item = c.button(text, "tab", text)
            item.setCheckable(True)
            item.clicked.connect(lambda _checked=False, k=key: self.goto(k))
            group.addButton(item)
            row.addWidget(item)
            self.page_buttons[key] = item
        row.addSpacing(theme.SPACE * 2)
        mode_group = QButtonGroup(self)
        self.mode_buttons = {}
        for key, text in (("pm", "项目经理"), ("ws", "工程工位")):
            item = c.button(text, "mode", "你的两种身份：有 AI 时是项目经理，自己动手时是工程工位")
            item.setCheckable(True)
            item.setChecked(key == "pm")
            item.clicked.connect(lambda _checked=False, k=key: self.set_mode(k))
            mode_group.addButton(item)
            row.addWidget(item)
            self.mode_buttons[key] = item
        row.addSpacing(theme.SPACE * 2)
        net_group = QButtonGroup(self)
        self.net_buttons = {}
        for key, text in (("on", "在线"), ("off", "离线")):
            item = c.button(text, "mode", "真实判定：后台对 origin 跑 git ls-remote，3 秒超时算离线；点“离线”可手动切")
            item.setCheckable(True)
            item.clicked.connect(lambda _checked=False, k=key: self.set_net(k))
            net_group.addButton(item)
            row.addWidget(item)
            self.net_buttons[key] = item
        row.addStretch(1)
        self.status = c.label("正在读取账本和项目文件夹……", "small", wrap=False)
        row.addWidget(self.status)
        self.refresh_button = c.button("重新读取", "refresh", "把账本和项目文件夹再读一遍，不写任何东西")
        self.refresh_button.clicked.connect(self.reload)
        row.addWidget(self.refresh_button)
        return bar

    # ------------------------------------------------ 导航

    def goto(self, key: str) -> None:
        page = {"home": self.station if self.mode == "ws" else self.home, "issues": self.issues,
                "projects": self.projects, "project": self.project}[key]
        self.stack.setCurrentWidget(page)
        for name, button in self.page_buttons.items():
            button.setChecked(name == key)  # type: ignore[attr-defined]

    def open_project(self, project_id: str) -> None:
        if self.board is None or self.home_vm is None:
            return
        card = next((p for p in self.home_vm.hot + self.home_vm.rest if p.project_id == project_id), None)
        if card is None:
            return
        self.project.render(vm.project_vm(self.board, card, self.offset, self.online, self.home_vm.github),
                            self.board.generated_at, self.online)
        self.goto("project")

    def set_mode(self, key: str) -> None:
        self.mode = key
        self.mode_buttons[key].setChecked(True)
        if self.board is not None:
            self._render()
        self.goto("home")

    def set_net(self, key: str) -> None:
        if key == "off":
            self.online = False
            self._render()
        else:
            self.probe()

    def copy_text(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)
        self.status.setText("已复制：" + pd._short(text, 40))

    # ------------------------------------------------ 读取

    def reload(self) -> None:
        if any(t.isRunning() for t in self._threads):
            return
        self.refresh_button.setEnabled(False)
        self.status.setText("正在读取……")
        self._start(use_legacy=False)
        if not self.options.no_net:
            self.probe()
        if not self.options.no_github:
            loader = GithubLoader(self.options, self)
            loader.loaded.connect(self._on_github)
            self._track(loader)

    def _start(self, use_legacy: bool) -> None:
        loader = BoardLoader(self.options, use_legacy, self)
        loader.loaded.connect(self._on_loaded)
        loader.failed.connect(self._on_failed)
        self._track(loader)

    def _track(self, thread: QThread) -> None:
        thread.finished.connect(lambda: self._threads.remove(thread))
        self._threads.append(thread)
        thread.start()

    def _on_loaded(self, board: pd.Board, with_legacy: bool) -> None:
        self.show_board(board)
        if not with_legacy and LEGACY_ALLOWED and not self.options.no_legacy:
            self.status.setText("正在接老驾驶舱后台的措辞（约 20 秒），先看这一版……")
            self._start(use_legacy=True)
            return
        self.status.setText("")
        self.refresh_button.setEnabled(True)
        self.timer.start()

    def _on_failed(self, message: str) -> None:
        self.status.setText("这次没读成：" + pd._short(message, 80))
        self.refresh_button.setEnabled(True)

    def _on_github(self, snapshot: gh.Snapshot | None) -> None:
        self.github = snapshot
        self._render()

    def probe(self) -> None:
        runner = ActionRunner(lambda: actions.probe_online(self.options.root), self)
        runner.probed.connect(self._on_probed)
        self._track(runner)

    def _on_probed(self, online: bool) -> None:
        self.online = online
        self._render()

    # ------------------------------------------------ 画

    def show_board(self, board: pd.Board) -> None:
        self.board = board
        self._render()

    def _render(self) -> None:
        if self.board is None:
            return
        board = self.board
        self.home_vm = vm.home_vm(board, self.offset, self.online, not self.options.no_git, self.github)
        now = board.generated_at
        self.home.show_board(self.home_vm, now)
        self.issues.render(vm.all_issues(self.home_vm), now)
        self.projects.render(self.home_vm.hot + self.home_vm.rest)
        identity = {
            "source": self.options.source_version, "configured": self.options.source_version,
            "effective": self.options.effective_version, "control_root": "是" if (self.options.root / pd.REGISTRY_RELATIVE).is_file() else "否",
            "collected": vm.fmt(now, self.offset),
        }
        self.station.set_bc_time((self.options.now or datetime.now(UTC)).astimezone(self.offset).strftime("%Y-%m-%d %H:%M"))
        self.station.render(vm.station_vm(board, self.home_vm.hot + self.home_vm.rest, self.online, identity,
                                          self.options.manual_branch, [], GAP9_MERGED))
        for key, button in self.net_buttons.items():
            button.setChecked((key == "on") == bool(self.online))
        if self.stack.currentWidget() is self.project and self.project.vm is not None:
            self.open_project(self.project.vm.card.project_id)
        if self.stack.currentWidget() in (self.home, self.station):
            self.goto("home")

    # ------------------------------------------------ 工程工位动作

    def run_action(self, key: str) -> None:
        root, worktree, pid = self.options.root, self.options.manual_worktree, self.options.station_project
        if key in actions.CHECKS:
            job = lambda: actions.run_check(root, worktree, pid, key)  # noqa: E731
        elif key == "bc_preview":
            record = self._bc_record()
            when = (self.options.now or datetime.now(UTC)).astimezone(self.offset)
            self.bc_digest = None
            if record is None:
                self.station.set_bc_preview(None, self._bc_missing())
                self.status.setText(self._bc_missing())
                return
            try:
                digest = actions.bc_digest(record)
                preview = actions.bc_preview(record, pid, self.station.bc_form())
            except actions.BcError as error:
                self.station.set_bc_preview(None, "没法预览：" + str(error))
                self.status.setText("BC 表单没填好，看第 4 步的提示")
                return
            self.bc_digest = digest
            self.station.set_bc_preview(preview)
            self.station.add_receipt(actions.Receipt(when.strftime("%H:%M"), "写入 BC 行（预览）", f"append {record.name} ← {preview.columns[0][1]}", 0, True))
            return
        elif key == "bc_write":
            record, line, digest = self._bc_record(), self.station.bc_preview_text, self.bc_digest
            if not record or not line.startswith("|") or digest is None:
                self.status.setText("先预览，再写入")
                return
            # 一次预览只写一次：先清掉预览，“写入”按钮立刻变灰，连点也不会写第二行
            self.bc_digest = None
            self.station.set_bc_preview(None, "已提交写入，结果看底部控制台；要再记一行请重新预览。")
            job = lambda: actions.bc_append(record, line, digest)  # noqa: E731
        elif key == "bc_open":
            record = self._bc_record()
            self.status.setText("文件：" + str(record) if record else self._bc_missing())
            return
        else:
            self.status.setText("这个动作本版不做：" + key)
            return
        runner = ActionRunner(job, self)
        runner.done.connect(self.station.add_receipt)
        self._track(runner)

    def _bc_missing(self) -> str:
        worktree = self.options.manual_worktree
        if not worktree.is_dir():
            return f"没有人工工位 {worktree.name}/（先做第 1 步开 manual/ 分支），BC 行只写在人工工位里，不写控制根"
        return "人工工位里找不到这个项目的 02_业务变更记录.md"

    def _bc_record(self) -> Path | None:
        """BC 行写在人工工位（.auto-pm/worktrees/manual）里，跟着 manual/ 分支一起提交；绝不写控制根的 main。"""
        if self.board is None:
            return None
        project = next((p for p in self.board.projects if p.project_id == self.options.station_project), None)
        worktree = self.options.manual_worktree
        if project is None or not project.root or not worktree.is_dir():
            return None
        for folder in pd._change_dirs(worktree / project.root):
            record = folder / "02_变更记录" / "02_业务变更记录.md"
            if record.is_file():
                return record
        return None


# ---------------------------------------------------------------- 入口


def parse_options(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="驾驶舱总控屏（项目经理看板只读 + 工程工位）")
    parser.add_argument("--root", default=".", help="工作空间根（控制根）")
    parser.add_argument("--db", default="", help="账本路径，默认 <root>/.auto-pm/continuity.db")
    parser.add_argument("--now", default="", help="当作现在的时刻（测试用）")
    parser.add_argument("--utc-offset", type=float, default=None, help="显示时区，默认本机")
    parser.add_argument("--no-git", action="store_true", help="不跑 git log")
    parser.add_argument("--no-legacy", action="store_true", help="不调老驾驶舱后台")
    parser.add_argument("--no-net", action="store_true", help="不探测网络，按离线处理")
    parser.add_argument("--ledger-reader", choices=pd.LEDGER_READERS, default="auto",
                        help="账本读法：copy 本地拷贝 / store 复用 ContinuityStore 严格只读快照（TD-105）/ auto 自动")
    parser.add_argument("--examples", action="store_true", help="叠加示例卡")
    parser.add_argument("--no-github", action="store_true", help="不读 GitHub（PR、门禁、安全签字一律“没检查”）")
    parser.add_argument("--github-repo", default="", help="owner/name，默认取 <root>/.git/config 的 origin")
    parser.add_argument("--github-cache", default="", help="GitHub 本机缓存文件，默认放用户缓存目录（不在工作空间）")
    parser.add_argument("--reviews-dir", action="append", default=[], help="另读一个审计目录（可多次）；<root>/reviews 总会读")
    parser.add_argument("--station-project", default="", help="工程工位默认项目，默认第一个客户项目")
    parser.add_argument("--manual-branch", default="manual/<日期>-<主题>", help="人工分支名（显示用）")
    parser.add_argument("--source-version", default="", help="身份条：源码版本")
    parser.add_argument("--effective-version", default="", help="身份条：生效版本")
    parser.add_argument("--screenshot", default="", help="离屏画好后各页截一张 PNG 再退出（自查用）")
    options = parser.parse_args(argv)
    options.root = Path(options.root).resolve()
    options.db = Path(options.db).resolve() if options.db else options.root / pd.DB_RELATIVE
    options.now = pd.parse_time(options.now) if options.now else None
    if options.utc_offset is None:
        options.offset = datetime.now().astimezone().tzinfo or UTC
    else:
        options.offset = timezone(timedelta(hours=options.utc_offset))
    options.manual_worktree = options.root / ".auto-pm" / "worktrees" / "manual"
    options.github_repo = options.github_repo or gh.repo_from_git_config(options.root)
    options.github_cache = Path(options.github_cache) if options.github_cache else gh.default_cache_path(options.github_repo)
    options.reviews_dirs = [options.root / "reviews", *(Path(d) for d in options.reviews_dir)]
    return options


def _dark_mode(app: QApplication) -> bool:
    palette = app.palette()
    return palette.color(QPalette.ColorRole.Window).lightness() < 128


def main(argv: list[str] | None = None) -> int:
    options = parse_options(argv)
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setStyleSheet(theme.build_qss(theme.DARK if _dark_mode(app) else theme.LIGHT))
    window = CockpitWindow(options)
    if not options.station_project:
        options.station_project = next(
            (p.project_id for p in pd.discover_projects(options.root, pd.DEFAULT_TOOL_PROJECTS) if not p.tool and p.registered), "")
    if options.screenshot:
        window.github = load_github(options)
        window.show_board(load_board(options, use_legacy=False))
        window.resize(1360, 1600)
        target = Path(options.screenshot)
        for key, name in (("home", "项目经理"), ("issues", "问题"), ("projects", "全部项目")):
            window.goto(key)
            app.processEvents()
            window.grab().save(str(target.with_name(f"{target.stem}_{name}{target.suffix}")))
        window.set_mode("ws")
        app.processEvents()
        window.grab().save(str(target.with_name(f"{target.stem}_工程工位{target.suffix}")))
        return 0
    window.show()
    QTimer.singleShot(0, window.reload)
    return app.exec()


def _crash_report() -> None:
    """双击启动没有黑窗口，出错时把原因写到系统临时目录（不写进工作空间）。"""
    path = Path(tempfile.gettempdir()) / "驾驶舱总控屏_启动错误.txt"
    path.write_text(traceback.format_exc(), encoding="utf-8")


def run() -> int:
    try:
        return main()
    except Exception:  # noqa: BLE001
        _crash_report()
        raise
