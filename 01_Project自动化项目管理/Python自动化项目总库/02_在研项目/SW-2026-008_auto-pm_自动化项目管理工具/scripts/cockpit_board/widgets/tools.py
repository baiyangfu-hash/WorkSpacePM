"""工程工具页：变更单（看、建、转状态）、决策（看）、变量表（IO 查重）、入箱（记一条新事项）、项目（新建、登记），以及“打开高级工作台”。

界面是命令行的另一层皮：每个按钮对应 tool_actions.TOOLS 白名单里的一条命令，命令和退出码都进“最近动作”。
会写文件的（建变更单、转状态、入箱）先点“预览命令”，看过整条命令再点运行；表单一改，预览作废。
批准类状态（已批准、有条件批准）这里不提供，只在终端里由你本人做。
入箱只记一条 PROPOSED 的条目，确认、驳回照旧在“决定”页；“用户原话”一栏只能由人亲手填，看板不预填、不拷、不给默认值。
项目页签（CHG-SCPT-2026-654）：新建、登记两个表单各有一个默认勾着的“只试一次，不写（--dry-run）”；看板不提交登记表。
本机命令没有 --kind 时（发版切换前）登记的“性质”一栏灰着，探测由 decision_controller 做，结果经 set_register_kind 递进来。
真正起子进程的是 tool_actions.py，这里只发请求、收回执。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from cockpit_board import iocheck, theme, tool_actions
from cockpit_board.actions import Receipt
from cockpit_board.widgets import common as c
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

TABS = (("change", "变更单"), ("decision", "决策"), ("vartable", "变量表"), ("inbox", "入箱"), ("project", "项目"))
DOMAIN_ZH = {"ELEC": "电气", "MECH": "机械", "PLC": "PLC", "HMI": "HMI", "SCPT": "脚本", "DOCU": "文档", "SAFE": "安全", "SPEC": "规范"}
NATURE_ZH = {"REQ": "需求变更", "DEF": "缺陷修复", "OPT": "优化", "CFG": "配置调整", "EMRG": "紧急处理"}
SCOPE_ZH = {"LOCAL": "局部", "MODULE": "模块", "SYSTEM": "系统", "CROSS": "跨系统", "SAFE": "安全"}
URGENCY_ZH = {"normal": "普通", "urgent": "紧急", "critical": "特急"}
# 入箱的几个下拉框（取值照 tool_actions.INBOX_*，测试对照）
INBOX_KIND_ZH = {"iteration": "迭代", "bug": "缺陷", "change": "变更", "urgent": "加急", "debt": "技术债"}
INBOX_ACTION_ZH = {"add": "新增", "modify": "修改", "reduce": "缩减", "freeze": "冻结", "remove": "去掉"}
INBOX_DISPOSITION_ZH = {"interrupt_now": "马上插进来", "after_current": "手上这张做完再做", "inbox_wait": "先放收件箱", "reject": "建议不做"}
INBOX_CRITERION_ZH = {"safety": "安全", "data_loss": "丢数据", "blocks_all": "全部卡住", "wrong_output": "输出错误"}
# 项目页签的几个下拉框（取值照 tool_actions.PROJECT_*，测试对照）
KIND_ZH = {"equipment": "设备", "library": "公共库", "tool": "工具", "test": "测试"}
STACK_ZH = dict(zip(tool_actions.PROJECT_STACKS, ("PLC", "Python"), strict=True))
MODE_ZH = {"standard-project": "标准项目", "shared-library": "共享库", "test-suite": "测试套件"}
PROJECT_TYPE_ZH = {"single_machine": "单机", "line_project": "产线", "retrofit_project": "改造", "maintenance_project": "维保",
                   "shared_library": "共享库", "test_suite": "测试套件"}
BY_KIND = "（不选：按性质的默认）"
UNCLASSIFIED = "（不填：登记后显示“未分类”）"
PICK_UNREGISTERED = "（从工作区里找到、还没登记的项目里选）"
DRY_RUN_TEXT = "只试一次，不写（--dry-run）"
KIND_NOT_PROBED = "还没探测本机的 project register 有没有 --kind；打开这个页签时会探测"
KIND_UNAVAILABLE = "发版切换后可填；现在登记后显示‘未分类’"
REGISTERED_NOTES = ("登记表有一处没提交的改动，提交后这个项目才能开工", "下一步：去「入箱」记这个项目的第一件事")
NOT_CHANGE = "（类别不是变更时不填）"
INFER = "（不填：按项目推断）"
NONE = "（不填）"
ALL_STATUSES = "（全部状态）"
PICK = "（请选择）"
NO_PROJECT = "（没有登记的项目）"


class _Job(QThread):
    done = Signal(object)

    def __init__(self, job: Callable[[], Any]) -> None:
        super().__init__()
        self._job = job

    def run(self) -> None:
        try:
            self.done.emit(self._job())
        except tool_actions.ToolError as error:
            self.done.emit(error)
        except Exception as error:  # noqa: BLE001 - 任何意外都变成回执里的一行字，窗口不挂
            self.done.emit(tool_actions.ToolResult(Receipt("", "意外错误", "", None, False, f"{type(error).__name__}: {error}")))


class ToolsPage(QWidget):
    """root＝控制根；runner / opener 可换成假的（测试用）；threaded=False 时在当前线程里直接跑。"""

    def __init__(
        self,
        root: Path,
        runner: Callable[..., Any] = tool_actions.run_tool,
        opener: Callable[[Path], Receipt] = tool_actions.open_workbench,
        threaded: bool = True,
    ) -> None:
        super().__init__()
        self.root, self.runner, self.opener, self.threaded = root, runner, opener, threaded
        self.receipts: list[Receipt] = []
        self.project_roots: dict[str, str] = {}
        self.preview: tuple[str, dict[str, Any]] | None = None
        self.preview_text = ""
        self._jobs: list[_Job] = []
        self.write_buttons: dict[str, QPushButton] = {}
        self.inputs: dict[str, QLineEdit | QComboBox | QPlainTextEdit] = {}
        self.scope_boxes: dict[str, QCheckBox] = {}
        self.inbox_scope_boxes: dict[str, QCheckBox] = {}
        self.project_boxes: dict[str, QCheckBox] = {}  # 项目页签的勾选框：两个“只试一次”和“显示高级选项”
        self.on_project_tab: Callable[[], None] | None = None  # 打开“项目”页签时叫一声（app 用它起一次后台探测）
        self.register_kind_available = False  # 本机的 project register 有没有 --kind；探测到了才亮
        self._last_params: dict[str, dict[str, Any]] = {}
        self.clock: Callable[[], str] = tool_actions.board_request_id  # 入箱请求号；测试可换成固定的
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll_area, self.layout_ = c.page()
        outer.addWidget(self.scroll_area)
        self.project_box = QComboBox()
        self.project_box.setObjectName("tool_project")
        self.project_box.currentIndexChanged.connect(self._clear_preview)
        self.pages: dict[str, QWidget] = {}
        self.output = QPlainTextEdit()
        self.output.setObjectName("tool_output")
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(200)
        self.output.setPlainText("还没有运行。点上面的按钮，命令的输出显示在这里。")
        self.note = c.label("", "small")
        self.receipts_holder = QWidget()
        self.receipts_layout = QVBoxLayout(self.receipts_holder)
        self.receipts_layout.setContentsMargins(0, 0, 0, 0)
        self._build()
        self.set_projects([])

    # ------------------------------------------------ 搭

    def _build(self) -> None:
        lay = self.layout_
        lay.addWidget(c.section("工程工具", "常用的几项；每个按钮都对应一条命令行，命令和退出码记在下面“最近动作”"))
        tabs = QButtonGroup(self)
        self.tab_buttons: dict[str, QPushButton] = {}
        items: list[QWidget | int] = []
        for key, text in TABS:
            tab = c.button(text, "tab", text)
            tab.setCheckable(True)
            tab.clicked.connect(lambda _checked=False, k=key: self.select_tab(k))
            tabs.addButton(tab)
            self.tab_buttons[key] = tab
            items.append(tab)
        items.append(1)
        self.workbench_button = c.button("打开高级工作台", "", "另起一个窗口：变量表、规范中心、模板、交付包、Modbus 调试等其余工具在那里")
        self.workbench_button.clicked.connect(self.open_workbench)
        items.append(self.workbench_button)
        lay.addWidget(c.hrow(*items))
        lay.addWidget(self._boxed(c.hrow(c.label("项目", "muted", wrap=False), self.project_box, 1)))
        builders = (self._change_tab, self._decision_tab, self._vartable_tab, self._inbox_tab, self._project_tab)
        for (key, _text), builder in zip(TABS, builders, strict=True):
            self.pages[key] = builder()  # 几页都放进布局，选哪页就显示哪页（不用 QStackedWidget：它按最高那页撑高，其余页会被拉出大空白）
            lay.addWidget(self.pages[key])
        lay.addWidget(self.note)
        lay.addWidget(c.section("输出", "命令的原样输出；失败也照实显示，不吞"))
        lay.addWidget(self.output)
        lay.addWidget(c.section("最近动作", "命令 + 退出码；rc 0＝成功，其余＝失败或没跑成"))
        lay.addWidget(self.receipts_holder)
        lay.addWidget(c.label("这里永远没有：批准、合并、删除、切换发布、替你签字。批准变更单只在终端里由你本人做。", "small"))
        self.select_tab("change")

    def _form(self) -> tuple[QFrame, QGridLayout]:
        frame, layout = c.inner("tool_form")
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.SPACE)
        grid.setVerticalSpacing(theme.SPACE // 2)
        grid.setColumnStretch(1, 1)
        holder = QWidget()
        holder.setLayout(grid)
        layout.addWidget(holder)
        return frame, grid

    def _boxed(self, *rows: QWidget) -> QFrame:
        """一块 tool_form 底的区域：输入框、下拉框的样式只在这样的框里生效（theme.py 里按它的名字配色，明暗都看得清）。"""
        frame, layout = c.inner("tool_form")
        for row in rows:
            layout.addWidget(row)
        return frame

    def _edit(self, key: str, hint: str = "") -> QLineEdit:
        edit = QLineEdit()
        edit.setObjectName("tool_" + key)
        edit.setPlaceholderText(hint)
        edit.textChanged.connect(self._clear_preview)
        self.inputs[key] = edit
        return edit

    def _combo(self, key: str, choices: dict[str, str], blank: str = "") -> QComboBox:
        box = QComboBox()
        box.setObjectName("tool_" + key)
        if blank:
            box.addItem(blank, "")
        for value, text in choices.items():
            box.addItem(f"{text}（{value}）" if text else value, value)
        box.currentIndexChanged.connect(self._clear_preview)
        self.inputs[key] = box
        return box

    def _text(self, key: str, hint: str, height: int = 64) -> QPlainTextEdit:
        """多行栏（用户原话、一行一个的清单）。看板从不往里预填字。"""
        edit = QPlainTextEdit()
        edit.setObjectName("tool_" + key)
        edit.setPlaceholderText(hint)
        edit.setFixedHeight(height)
        edit.textChanged.connect(self._clear_preview)
        self.inputs[key] = edit
        return edit

    def _change_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        # 看
        lay.addWidget(c.section("看变更单", "只读"))
        status = self._combo("status", {s: tool_actions.STATUS_LABELS_ZH[s] for s in tool_actions.CHANGE_STATUSES}, ALL_STATUSES)
        show_number = self._edit("show_number", "变更单号，例如 CHG-DJ-2026-001")
        list_button = c.button("列出变更单", "", "change list <项目> --full")
        list_button.clicked.connect(lambda: self.run("change_list", {"pid": self.pid(), "status": self._value("status")}))
        show_button = c.button("查看这张", "", "change show <单号> --pid <项目>")
        show_button.clicked.connect(lambda: self.run("change_show", {"pid": self.pid(), "number": self._value("show_number")}))
        lay.addWidget(self._boxed(c.hrow(status, list_button, 1, show_number, show_button)))
        # 建
        lay.addWidget(c.section("建一张变更单", "先预览命令，看过再创建；创建会在项目里生成变更单文件并更新台账"))
        frame, grid = self._form()
        rows: list[tuple[str, QWidget]] = [
            ("技术领域", self._combo("domain", DOMAIN_ZH, PICK)),
            ("业务性质", self._combo("nature", NATURE_ZH, PICK)),
        ]
        scope_row = QWidget()
        scope_lay = QGridLayout(scope_row)
        scope_lay.setContentsMargins(0, 0, 0, 0)
        for index, (value, text) in enumerate(SCOPE_ZH.items()):
            box = QCheckBox(f"{text}（{value}）")
            box.setObjectName("tool_scope_" + value)
            box.toggled.connect(self._clear_preview)
            self.scope_boxes[value] = box
            scope_lay.addWidget(box, 0, index)
        rows += [
            ("影响范围（可多选）", scope_row),
            ("紧急程度", self._combo("urgency", URGENCY_ZH)),
            ("申请人", self._edit("applicant", "提出改动的人，例如 张工（客户设备科）")),
            ("变更背景", self._edit("background", "现在是什么情况")),
            ("变更必要性", self._edit("necessity", "为什么要改")),
            ("参考依据", self._edit("references", "可不填：图纸、邮件、会议纪要")),
        ]
        for index, (label, widget) in enumerate(rows):
            grid.addWidget(c.label(label, "muted", wrap=False), index, 0)
            grid.addWidget(widget, index, 1)
        lay.addWidget(frame)
        lay.addWidget(self._preview_row("change_create", "创建变更单", self._create_params))
        # 转状态
        lay.addWidget(c.section("转状态", "批准类（已批准、有条件批准）不在这里：只在终端里由你本人做，有口令要输口令"))
        frame, grid = self._form()
        targets = {s: tool_actions.STATUS_LABELS_ZH[s] for s in tool_actions.CHANGE_TARGETS}
        rows = [
            ("变更单号", self._edit("number", "例如 CHG-DJ-2026-001")),
            ("转到", self._combo("to", targets)),
            ("意见 / 原因", self._edit("comment", "废弃必须写原因")),
            ("实施人", self._edit("approver", "可不填")),
            ("验证结论", self._edit("verification_conclusion", "转到“已完成”必须写")),
        ]
        for index, (label, widget) in enumerate(rows):
            grid.addWidget(c.label(label, "muted", wrap=False), index, 0)
            grid.addWidget(widget, index, 1)
        lay.addWidget(frame)
        lay.addWidget(self._preview_row("change_transition", "转状态", self._transition_params))
        return page

    def _decision_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(c.section("决策包", "只读：列出、查看。新建决策包要用户本人在终端里输口令，这里不提供"))
        change_id = self._edit("decision_change", "按变更单号筛选，可不填")
        list_button = c.button("列出决策", "", "decision list [--pid <项目>] [--change-id <变更单>]")
        list_button.clicked.connect(lambda: self.run("decision_list", {"pid": self.pid(), "change_id": self._value("decision_change")}))
        show_id = self._edit("decision_id", "决策编号，例如 DEC-20260923-XXXX")
        show_button = c.button("查看这个决策", "", "decision show <编号>")
        show_button.clicked.connect(lambda: self.run("decision_show", {"decision_id": self._value("decision_id")}))
        lay.addWidget(self._boxed(c.hrow(change_id, list_button), c.hrow(show_id, show_button)))
        return page

    def _vartable_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(c.section("变量表 / IO 查重", "读入 IO 点表，报告重复的地址和重复的变量名；只读，不改文件"))
        path = self._edit("vartable_file", "io_points.csv 等变量表文件的完整路径")
        pick = c.button("选择文件…", "", "在文件夹里选一个变量表文件")
        pick.clicked.connect(self.choose_file)
        find = c.button("在项目里找", "", "在当前项目的文件夹里找 io_points.csv")
        find.clicked.connect(self.find_in_project)
        check = c.button("查重", "", "vartable parse <文件> --output-format json，再数重复")
        check.clicked.connect(self.check_duplicates)
        lay.addWidget(self._boxed(c.hrow(path), c.hrow(pick, find, 1, check)))
        lay.addWidget(c.label("比较规则：地址去掉前面的 % 和空格、不分大小写；不同站里的同名同址不算重复；空地址、空变量名单独数。", "small"))
        return page

    def _inbox_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(c.section("记一条新事项进收件箱", "pm inbox add：先预览命令，看过再记；记进去是“等你确认”（PROPOSED），确认、驳回在“决定”页"))
        frame, grid = self._form()
        scope_row = QWidget()
        scope_lay = QGridLayout(scope_row)
        scope_lay.setContentsMargins(0, 0, 0, 0)
        for index, (value, text) in enumerate(SCOPE_ZH.items()):
            box = QCheckBox(f"{text}（{value}）")
            box.setObjectName("tool_inbox_scope_" + value)
            box.toggled.connect(self._clear_preview)
            self.inbox_scope_boxes[value] = box
            scope_lay.addWidget(box, 0, index)
        rows: list[tuple[str, QWidget]] = [
            ("标题", self._edit("inbox_title", "一行，至多 120 字")),
            ("类别", self._combo("inbox_kind", INBOX_KIND_ZH, PICK)),
            ("变更动作", self._combo("inbox_change_action", INBOX_ACTION_ZH, NOT_CHANGE)),
            ("用户原话", self._text("inbox_original_words", "照原样填你（或客户）说的话；看板不替你填", 80)),
            ("影响了什么", self._edit("inbox_affects", "项目、WBS 行、文件、依赖")),
            ("查重", self._edit("inbox_duplicate_check", "查了哪里、结论是什么")),
            ("重复的条目", self._text("inbox_duplicate_of", "可不填；一行一个编号，例如 IN-… / TD-… / CHG-…")),
            ("取证（至少一条）", self._text("inbox_evidence", "一行一条，写成 file:… / cmd:… / ledger:… / chg:… / commit:…")),
            ("建议处置", self._combo("inbox_disposition", INBOX_DISPOSITION_ZH, PICK)),
            ("紧急判据", self._combo("inbox_urgent_criterion", INBOX_CRITERION_ZH, NONE)),
            ("理由", self._edit("inbox_rationale", "为什么这样处置")),
            ("备选方案（至少一个）", self._text("inbox_alternatives", "一行一个")),
            ("成本与风险", self._edit("inbox_cost_risk", "大概多少工夫、有什么风险")),
            ("要你决定的点", self._text("inbox_asks", "可不填；一行一个")),
            ("技术领域", self._combo("inbox_domain", DOMAIN_ZH, INFER)),
            ("影响范围（不选＝模块）", scope_row),
        ]
        for index, (label, widget) in enumerate(rows):
            grid.addWidget(c.label(label, "muted", wrap=False), index, 0)
            grid.addWidget(widget, index, 1)
        lay.addWidget(frame)
        lay.addWidget(self._preview_row("inbox_add", "记入收件箱", self._inbox_params))
        lay.addWidget(c.label("请求号由看板按时间生成（board-<UTC 时间>），提出者写 cockpit-board；同一次预览只记一次。", "small"))
        return page

    def _check(self, key: str, text: str, checked: bool) -> QCheckBox:
        box = QCheckBox(text)
        box.setObjectName("tool_" + key)
        box.setChecked(checked)
        box.toggled.connect(self._clear_preview)
        self.project_boxes[key] = box
        return box

    def _project_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        # 新建
        lay.addWidget(c.section("新建项目", "project create：先预览命令，看过再运行；“只试一次”勾着时只显示将建在哪、用哪套模板，什么都不写"))
        frame, grid = self._form()
        kind = self._combo("create_kind", KIND_ZH, PICK)
        kind.currentIndexChanged.connect(self._kind_changed)
        self.kind_note = c.label("", "small")
        rows: list[tuple[str, QWidget]] = [
            ("项目名称", self._edit("create_name", "例如 上料机改造")),
            ("性质", kind),
            ("", self.kind_note),
            ("技术栈", self._combo("create_stack", STACK_ZH, BY_KIND)),
            ("模板（只在 PLC 时用）", self._combo("create_mode", MODE_ZH, BY_KIND)),
            ("业务线（自动编号用）", self._combo("create_business_line", dict.fromkeys(tool_actions.PROJECT_BUSINESS_LINES, ""), BY_KIND)),
        ]
        for index, (label, widget) in enumerate(rows):
            grid.addWidget(c.label(label, "muted", wrap=False), index, 0)
            grid.addWidget(widget, index, 1)
        advanced_toggle = self._check("create_advanced", "显示高级选项（手填编号、描述、项目类型、PLC 品牌和型号、存放目录）", False)
        grid.addWidget(advanced_toggle, len(rows), 1)
        lay.addWidget(frame)
        self.advanced_frame, grid = self._form()
        rows = [
            ("项目编号（手填）", self._edit("create_id", "不填＝自动编号；填了就不再自动编号，例如 DJ-2026-010")),
            ("项目描述", self._edit("create_desc", "可不填")),
            ("项目类型", self._combo("create_project_type", PROJECT_TYPE_ZH, NONE)),
            ("PLC 品牌", self._combo("create_plc_vendor", dict.fromkeys(tool_actions.PROJECT_PLC_VENDORS, ""), NONE)),
            ("PLC 型号", self._edit("create_plc_model", "可不填，例如 S7-1200")),
            ("存放目录", self._edit("create_dest_dir", "可不填：默认放工作区的分类目录")),
        ]
        for index, (label, widget) in enumerate(rows):
            grid.addWidget(c.label(label, "muted", wrap=False), index, 0)
            grid.addWidget(widget, index, 1)
        self.advanced_frame.setVisible(False)
        advanced_toggle.toggled.connect(self.advanced_frame.setVisible)
        lay.addWidget(self.advanced_frame)
        lay.addWidget(self._boxed(self._check("create_dry_run", DRY_RUN_TEXT, True)))
        lay.addWidget(self._preview_row("project_create", "新建项目", self._project_create_params))
        # 登记
        lay.addWidget(c.section("登记", "project register：把已有项目记进工作区登记表；先预览命令，看过再运行。看板不提交登记表"))
        frame, grid = self._form()
        pick = self._combo("register_pick", {}, PICK_UNREGISTERED)
        pick.currentIndexChanged.connect(self._picked_unregistered)
        register_kind = self._combo("register_kind", KIND_ZH, UNCLASSIFIED)
        register_kind.setEnabled(False)
        self.register_kind_note = c.label(KIND_NOT_PROBED, "small")
        rows = [
            ("项目编号", self._edit("register_pid", "要登记的项目编号，例如 DJ-2026-010")),
            ("", pick),
            ("性质", register_kind),
            ("", self.register_kind_note),
        ]
        for index, (label, widget) in enumerate(rows):
            grid.addWidget(c.label(label, "muted", wrap=False), index, 0)
            grid.addWidget(widget, index, 1)
        lay.addWidget(frame)
        lay.addWidget(self._boxed(self._check("register_dry_run", DRY_RUN_TEXT, True)))
        lay.addWidget(self._preview_row("project_register", "登记", self._project_register_params))
        self.register_note = c.label("", "small")
        lay.addWidget(self.register_note)
        lay.addWidget(c.label("归档、重新激活在项目详情页的“项目状态”一块；这里不提交登记表，也没有别的项目动作。", "small"))
        return page

    def _preview_row(self, key: str, run_text: str, params: Callable[[], dict[str, Any]]) -> QWidget:
        preview = c.button("预览命令", "", "只显示要运行的整条命令，不运行")
        preview.clicked.connect(lambda: self.preview_command(key, params()))
        write = c.button(run_text, "", "先点“预览命令”，看过再点", enabled=False)
        write.clicked.connect(self.run_preview)
        self.write_buttons[key] = write
        return c.hrow(preview, write, 1)

    # ------------------------------------------------ 取值

    def _value(self, key: str) -> str:
        widget = self.inputs[key]
        if isinstance(widget, QComboBox):
            return str(widget.currentData() or "")
        if isinstance(widget, QPlainTextEdit):
            return widget.toPlainText()  # 原样交出（用户原话不并空格、不改换行）；清单栏由 tool_actions 按行拆
        return widget.text().strip()

    def pid(self) -> str:
        return str(self.project_box.currentData() or "")

    def _create_params(self) -> dict[str, Any]:
        return {
            "pid": self.pid(), "domain": self._value("domain"), "nature": self._value("nature"),
            "scope": [value for value, box in self.scope_boxes.items() if box.isChecked()],
            "urgency": self._value("urgency"), "applicant": self._value("applicant"), "background": self._value("background"),
            "necessity": self._value("necessity"), "references": self._value("references"),
        }

    def _inbox_params(self) -> dict[str, Any]:
        """每次预览都按当时的时间生成新请求号；运行用的是预览那一份，所以预览一次只记一次。"""
        return {
            "pid": self.pid(), "request_id": self.clock(), "title": self._value("inbox_title"), "kind": self._value("inbox_kind"),
            "change_action": self._value("inbox_change_action"), "domain": self._value("inbox_domain"),
            "impact_scope": [value for value, box in self.inbox_scope_boxes.items() if box.isChecked()],
            "original_words": self._value("inbox_original_words"), "affects": self._value("inbox_affects"),
            "duplicate_check": self._value("inbox_duplicate_check"), "duplicate_of": self._value("inbox_duplicate_of"),
            "evidence": self._value("inbox_evidence"), "urgent_criterion": self._value("inbox_urgent_criterion"),
            "disposition": self._value("inbox_disposition"), "rationale": self._value("inbox_rationale"),
            "alternatives": self._value("inbox_alternatives"), "cost_risk": self._value("inbox_cost_risk"),
            "asks": self._value("inbox_asks"),
        }

    def _project_create_params(self) -> dict[str, Any]:
        return {
            "name": self._value("create_name"), "kind": self._value("create_kind"), "stack": self._value("create_stack"),
            "mode": self._value("create_mode"), "business_line": self._value("create_business_line"),
            "project_id": self._value("create_id"), "desc": self._value("create_desc"),
            "project_type": self._value("create_project_type"), "plc_vendor": self._value("create_plc_vendor"),
            "plc_model": self._value("create_plc_model"), "dest_dir": self._value("create_dest_dir"),
            "dry_run": self.project_boxes["create_dry_run"].isChecked(),
        }

    def _project_register_params(self) -> dict[str, Any]:
        """本机命令没有 --kind（或还没探测到）时不传性质：那一栏灰着，填不了。"""
        return {
            "project_id": self._value("register_pid"),
            "kind": self._value("register_kind") if self.register_kind_available else "",
            "dry_run": self.project_boxes["register_dry_run"].isChecked(),
        }

    def _transition_params(self) -> dict[str, Any]:
        return {
            "pid": self.pid(), "number": self._value("number"), "to": self._value("to"), "comment": self._value("comment"),
            "approver": self._value("approver"), "verification_conclusion": self._value("verification_conclusion"),
        }

    # ------------------------------------------------ 数据进来

    def set_projects(self, projects: list[tuple[str, str]]) -> None:
        """(项目编号, 项目相对路径)；账本读完后调。原来选的项目还在就保持。"""
        previous = self.pid()
        self.project_roots = dict(projects)
        self.project_box.blockSignals(True)
        self.project_box.clear()
        if not projects:
            self.project_box.addItem(NO_PROJECT, "")
        for project_id, _root in projects:
            self.project_box.addItem(project_id, project_id)
        index = self.project_box.findData(previous) if previous else -1
        self.project_box.setCurrentIndex(max(index, 0))
        self.project_box.blockSignals(False)
        self._clear_preview()

    def set_unregistered(self, project_ids: list[str]) -> None:
        """工作区里找到、还没登记的项目（板数据里 registered 为假的那些）：填进登记表单的下拉，选一个就写进“项目编号”。"""
        box = self.inputs["register_pick"]
        assert isinstance(box, QComboBox)
        box.blockSignals(True)
        box.clear()
        box.addItem(PICK_UNREGISTERED, "")
        for project_id in project_ids:
            box.addItem(project_id, project_id)
        box.blockSignals(False)

    def set_register_kind(self, available: bool, reason: str = "") -> None:
        """探测结果：本机的 project register 有 --kind 才让填“性质”；没有、没读成都灰着并写明原因。"""
        self.register_kind_available = available
        self.inputs["register_kind"].setEnabled(available)
        self.register_kind_note.setText("" if available else (reason or KIND_UNAVAILABLE))
        self._clear_preview()

    # ------------------------------------------------ 动作

    def select_tab(self, key: str) -> None:
        for name, button in self.tab_buttons.items():
            button.setChecked(name == key)
        for name, page in self.pages.items():
            page.setVisible(name == key)
        self._clear_preview()
        if key == "project" and self.on_project_tab is not None:
            self.on_project_tab()

    def _kind_changed(self, *_args: object) -> None:
        self.kind_note.setText(tool_actions.TEST_KIND_NOTE if self._value("create_kind") == "test" else "")

    def _picked_unregistered(self, *_args: object) -> None:
        picked = self._value("register_pick")
        if picked:
            self.inputs["register_pid"].setText(picked)  # type: ignore[union-attr]

    def _carry_to_register(self, params: dict[str, Any], output: str) -> None:
        """真建成功：把表单带到登记一步。编号读不出来就留空让你自己填，不猜。"""
        project_id = tool_actions.created_project_id(params, output)
        self.inputs["register_pid"].setText(project_id)  # type: ignore[union-attr]
        box = self.inputs["register_kind"]
        assert isinstance(box, QComboBox)
        box.setCurrentIndex(max(box.findData(params.get("kind", "")), 0))
        self.register_note.setText(
            f"项目建好了。下一步：登记（编号 {project_id} 和性质已带到上面的登记表单）。" if project_id
            else "项目建好了。下一步：登记。回执里没读出项目编号，请自己填到上面的登记表单。")

    def _clear_preview(self, *_args: object) -> None:
        self.preview, self.preview_text = None, ""
        for button in self.write_buttons.values():
            button.setEnabled(False)

    def preview_command(self, key: str, params: dict[str, Any]) -> None:
        self._clear_preview()
        try:
            args = tool_actions.build_command(key, params)
        except tool_actions.ToolError as error:
            self.note.setText("没法预览：" + str(error))
            return
        self.preview, self.preview_text = (key, params), tool_actions.shown_command(args)
        self.write_buttons[key].setEnabled(True)
        self.note.setText("要运行的命令（在控制根里）：" + self.preview_text + "\n确认无误再点运行；表单再改，预览作废。")
        self.output.setPlainText("预览，还没有运行：\n" + self.preview_text)

    def run_preview(self) -> None:
        if self.preview is None:
            self.note.setText("先点“预览命令”")
            return
        key, params = self.preview
        self._clear_preview()  # 一次预览只运行一次，连点也不会重复写
        self.run(key, params)

    def run(self, key: str, params: dict[str, Any]) -> None:
        try:
            tool_actions.build_command(key, params)  # 先在界面线程里验一遍：缺栏马上提示，不起线程
        except tool_actions.ToolError as error:
            self.note.setText("没法运行：" + str(error))
            return
        self.note.setText("正在运行……")
        self._last_params[key] = dict(params)
        self._dispatch(lambda: self.runner(self.root, key, params), key)

    def _dispatch(self, job: Callable[[], Any], key: str) -> None:
        if not self.threaded:
            self._finish(job(), key)
            return
        thread = _Job(job)
        thread.done.connect(lambda result, k=key: self._finish(result, k))
        thread.finished.connect(lambda: self._jobs.remove(thread))
        self._jobs.append(thread)
        thread.start()

    def _finish(self, result: Any, key: str) -> None:
        if isinstance(result, tool_actions.ToolError):
            self.note.setText("没法运行：" + str(result))
            return
        receipt = result.receipt
        text = receipt.output or "（命令没有输出）"
        if key == "vartable_parse" and receipt.rc == 0:
            text = self._duplicate_report(result.stdout) + "\n\n—— 命令原样输出 ——\n" + text
        self.output.setPlainText(f"{receipt.command}\n退出码：{receipt.rc_text}\n\n{text}")
        self.note.setText("")
        self.add_receipt(receipt)
        params = self._last_params.pop(key, {})
        if receipt.rc == 0 and not params.get("dry_run"):  # 真写成功才往下带；只试一次的不算
            if key == "project_create":
                self._carry_to_register(params, receipt.output)
            elif key == "project_register":
                self.register_note.setText("\n".join(REGISTERED_NOTES))

    def _duplicate_report(self, stdout: str) -> str:
        try:
            return iocheck.render_report(iocheck.find_duplicates(iocheck.extract_entries(stdout)))
        except iocheck.IoCheckError as error:
            return "没法查重：" + str(error)

    def add_receipt(self, receipt: Receipt) -> None:
        self.receipts.insert(0, receipt)
        c.clear(self.receipts_layout)
        for item in self.receipts[:8]:
            sev = "ok" if item.rc == 0 else ("na" if item.rc is None else "block")
            self.receipts_layout.addWidget(c.hrow(
                c.label(item.when, "mono", wrap=False), c.label(item.action, "", wrap=False),
                c.label(item.command, "mono"), 1, c.chip(item.rc_text, sev)))

    # -- 变量表

    def choose_file(self) -> None:
        start = str(self.root / self.project_roots.get(self.pid(), ""))
        name, _filter = QFileDialog.getOpenFileName(self, "选一个变量表文件", start, "变量表 (*.csv *.yml *.yaml *.scl *.asc *.wr3 *.xlsx);;全部文件 (*)")
        if name:
            self.inputs["vartable_file"].setText(name)  # type: ignore[union-attr]

    def find_in_project(self) -> None:
        project_root = self.root / self.project_roots.get(self.pid(), "")
        found = tool_actions.find_io_tables(project_root)
        if not found:
            self.note.setText(f"在 {self.pid() or '当前项目'} 里没找到 io_points.csv，请点“选择文件…”手动选。")
            return
        self.inputs["vartable_file"].setText(str(found[0]))  # type: ignore[union-attr]
        more = f"（共 {len(found)} 个，填了第一个）" if len(found) > 1 else ""
        self.note.setText(f"找到 {found[0].relative_to(self.root) if found[0].is_relative_to(self.root) else found[0]}{more}")

    def check_duplicates(self) -> None:
        self.run("vartable_parse", {"file": self._value("vartable_file")})

    def open_workbench(self) -> None:
        self._dispatch(lambda: tool_actions.ToolResult(self.opener(self.root)), "workbench")
