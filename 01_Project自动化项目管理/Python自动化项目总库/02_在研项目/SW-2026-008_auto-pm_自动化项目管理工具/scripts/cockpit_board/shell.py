"""窗口的壳：侧栏三组、页面注册表、路由、范围标记（CHG-SCPT-2026-628 骨架 A）。

像配电柜的端子排图：每一页登记一行（键、按钮文字、属于哪一组），侧栏和路由都照这张表排，
加一页只在 PAGES 里加一行、在 app.py 里把画面挂上，不用改侧栏代码。
这里不起子进程、不写文件、不写颜色（规矩见 README 第 2 节）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from cockpit_board import policy, theme
from cockpit_board.widgets import common as c

# 侧栏三组，自上而下：每天看的、受管的客户项目、驾驶舱自己（组名的真源在 policy.SIDEBAR_GROUPS）。
GROUPS = policy.SIDEBAR_GROUPS


@dataclass(frozen=True)
class PageSpec:
    key: str  # 路由键，app.goto(key) 用
    text: str  # 侧栏按钮文字（必须在 policy / tool_policy 的白名单里）
    group: str  # GROUPS 之一
    tip: str = ""
    nav: bool = True  # False：不进侧栏（如项目详情页，只能从别的页点进去）


PAGES: tuple[PageSpec, ...] = (
    PageSpec("home", "今天", "日常", "今天要看的：挡路、有风险、要你决定的"),
    PageSpec("issues", "问题", "日常", "所有项目的挡路、风险、提醒，一张表"),
    PageSpec("decisions", "决定", "日常", "待你批准、验收的卡；每个按钮背后是同一条 main.py 命令"),
    PageSpec("attention", "要你出手", "日常", "等你本人拍板的范围卡和收件箱条目，只读"),
    PageSpec("projects", "全部项目", "受管项目", "受管的全部项目"),
    PageSpec("project", "项目详情", "受管项目", nav=False),
    PageSpec("tasks", "任务", "受管项目", "一个项目的四栏卡和进门定位，只读"),
    PageSpec("flow", "流程图", "驾驶舱", "看一张卡在状态流程里走到了哪一步"),
    PageSpec("tools", "工具", "驾驶舱", "变更单、决策、变量表的只读查询和预览"),
    PageSpec("prs", "PR 与审计", "驾驶舱", "开着的 PR 和审计结论，读窗口已有的 GitHub 采集"),
    PageSpec("worktrees", "工作树与分支", "驾驶舱", "每个工位的分支和改动，可清理的只列出不动"),
    PageSpec("release", "发版", "驾驶舱", "长任务（门禁等）在跑什么、跑完没有，只读"),
    PageSpec("spine", "脊柱图", "驾驶舱", "一张卡从进门到收口的十步"),
    PageSpec("commands", "命令与契约", "驾驶舱", "每条命令界面能不能碰、谁能按"),
)

# 骨架页读哪些命令：真源是 flow/pages.json（契约测试对过：只读 read 类命令、不带写开关、读法已登记）。
PAGES_JSON = Path(__file__).resolve().parent / "flow" / "pages.json"
PID = "<PID>"  # pages.json 参数里的占位：换成要读的项目号


@dataclass(frozen=True)
class PageRead:
    command: str  # 如 "pm missions"
    args: tuple[str, ...]  # 可能含 PID 占位
    reader: str  # readers.READERS 的键

    @property
    def needs_project(self) -> bool:
        return PID in self.args

    def argv(self, project_id: str) -> list[str]:
        """拼成交给 main.py 的参数；命令名按空格拆开（如 pm inbox list）。"""
        return [*self.command.split(), *(project_id if word == PID else word for word in self.args)]


def page_reads(path: Path = PAGES_JSON) -> dict[str, tuple[PageRead, ...]]:
    """页键 → 这一页要读的命令。文件读不出直接报错：它是随源码走的契约文件，坏了是代码问题，不是数据问题。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    return {page["key"]: tuple(PageRead(r["command"], tuple(r["args"]), r["reader"]) for r in page["reads"])
            for page in data["pages"]}


def page_texts(path: Path = PAGES_JSON) -> dict[str, tuple[str, str]]:
    """页键 → （空态文案, 错态文案）。和 page_reads 同一个来源，文件坏了同样直接报错。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    return {page["key"]: (str(page["empty_text"]), str(page["error_text"])) for page in data["pages"]}


def spec(key: str) -> PageSpec:
    for item in PAGES:
        if item.key == key:
            return item
    raise KeyError(f"没有登记的页面：{key}")


def scope_text(key: str) -> str:
    """范围标记：页面顶上一行小字，告诉你眼前这页说的是哪一块（日常 / 受管项目 / 驾驶舱自己）。"""
    item = spec(key)
    return f"{item.group} · {item.text}"


class Sidebar(QFrame):
    """左侧导航：三组标题，每组下面一列页面按钮；一次只亮一个。"""

    navigate = Signal(str)

    def __init__(self, pages: tuple[PageSpec, ...] = PAGES, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setFixedWidth(theme.SIDEBAR_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(theme.SPACE, theme.SPACE, theme.SPACE, theme.SPACE)
        layout.setSpacing(2)
        self.group = QButtonGroup(self)
        self.buttons: dict[str, QPushButton] = {}
        for group in GROUPS:
            members = [p for p in pages if p.group == group and p.nav]
            if not members:
                continue
            layout.addWidget(c.label(group, "navgroup", wrap=False))
            for page in members:
                item = c.button(page.text, "nav", page.tip)
                item.setCheckable(True)
                item.clicked.connect(lambda _checked=False, k=page.key: self.navigate.emit(k))
                self.group.addButton(item)
                layout.addWidget(item)
                self.buttons[page.key] = item
        layout.addStretch(1)

    def select(self, key: str) -> None:
        """点亮 key 对应的按钮；不在侧栏里的页（项目详情）全部熄灭。"""
        self.group.setExclusive(False)
        for name, item in self.buttons.items():
            item.setChecked(name == key)
        self.group.setExclusive(True)


class Router:
    """页面注册表：键 → 画面。app 把每一页挂进来，goto 只查这张表，查不到直接报错。"""

    def __init__(self, stack: QStackedWidget) -> None:
        self.stack = stack
        self.pages: dict[str, QWidget] = {}

    def register(self, key: str, widget: QWidget) -> None:
        spec(key)  # 没在 PAGES 登记的键不许挂
        if key in self.pages:
            raise ValueError(f"页面重复挂载：{key}")
        self.pages[key] = widget
        if self.stack.indexOf(widget) < 0:
            self.stack.addWidget(widget)

    def show(self, key: str, widget: QWidget | None = None) -> QWidget:
        """切到 key 那页；widget 给了就用它（“今天”在工程工位模式下换成工位页）。"""
        page = widget if widget is not None else self.pages[key]
        if self.stack.indexOf(page) < 0:
            self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)
        return page
