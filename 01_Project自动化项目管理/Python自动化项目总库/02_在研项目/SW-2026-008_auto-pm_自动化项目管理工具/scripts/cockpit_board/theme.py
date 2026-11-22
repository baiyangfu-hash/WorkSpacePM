"""主题令牌：颜色、字体、间距、圆角只在这里定义。

改颜色、字体：改 LIGHT / DARK 两个 Tokens 的字段，或 FONT_STACK，不用碰任何画面代码。
画面代码只用 objectName 和动态属性（sev、health、state），样式由 build_qss() 从令牌生成。
"""

from __future__ import annotations

from dataclasses import dataclass, fields

# 字体：系统中文字体优先，不引外网字体（内网 / 断网也要能看）。
FONT_STACK = ("Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Segoe UI")
MONO_STACK = ("Cascadia Mono", "Consolas", "Menlo", "SF Mono", "DejaVu Sans Mono")
FONT_SIZE_PT = 10
FONT_SIZE_TITLE_PT = 15
FONT_SIZE_SMALL_PT = 9
FONT_SIZE_SECTION_PT = 11
# 令牌 v2（CHG-SCPT-2026-628 骨架 A）：字号只用这四级，画面代码用名字取，不写数字。
FONT_LADDER_PT = {"small": FONT_SIZE_SMALL_PT, "body": FONT_SIZE_PT, "section": FONT_SIZE_SECTION_PT,
                  "title": FONT_SIZE_TITLE_PT}

SPACE = 8  # 基本间距，其余都是它的倍数
RADIUS = 6
SIDEBAR_WIDTH = SPACE * 25  # 侧栏宽度（200 像素），1366×768 下右边还能放下整页 + 遥测面板


@dataclass(frozen=True)
class Tokens:
    bg: str  # 页面底
    card: str  # 卡片
    card2: str  # 卡片里的次级底
    line: str  # 分割线、边框
    line2: str  # 深一点的边框
    fg: str  # 正文
    fg2: str  # 次要文字
    fg3: str  # 辅助文字
    accent: str  # 导航、链接、选中
    accent_soft: str
    block: str  # 阻塞 / 挡路
    block_soft: str
    risk: str  # 风险 / 有风险
    risk_soft: str
    hint: str  # 提醒
    hint_soft: str
    ok: str  # 正常 / 过
    ok_soft: str
    na: str  # 没检查 / 无数据（灰）
    na_soft: str
    side: str  # 侧栏底（令牌 v2）


LIGHT = Tokens(
    bg="#f3f5f8",
    card="#ffffff",
    card2="#f7f9fc",
    line="#dfe4ec",
    line2="#c5cedb",
    fg="#151a22",
    fg2="#445062",
    fg3="#586477",
    accent="#1d5c8f",
    accent_soft="#e3eef7",
    block="#c62828",
    block_soft="#fdebec",
    risk="#b4690e",
    risk_soft="#fef3dc",
    hint="#2563a6",
    hint_soft="#e7f0fb",
    ok="#2e7d4f",
    ok_soft="#e6f4eb",
    na="#7a8494",
    na_soft="#eef1f5",
    side="#e9edf3",
)

DARK = Tokens(
    bg="#0e131b",
    card="#171f2b",
    card2="#1d2736",
    line="#283446",
    line2="#394960",
    fg="#ecf1f8",
    fg2="#a8b4c4",
    fg3="#8998ab",
    accent="#60a5fa",
    accent_soft="#172840",
    block="#f87171",
    block_soft="#3b1d23",
    risk="#f59e0b",
    risk_soft="#362712",
    hint="#38bdf8",
    hint_soft="#132c3d",
    ok="#34d399",
    ok_soft="#122e27",
    na="#8b97a8",
    na_soft="#202834",
    side="#121923",
)

# 三态标签（没检查 / 断网未知 / 读不懂）的语义色：前两种是灰（不知道），读不懂是风险色（读到了但看不懂，要人看）。
STATE_SEV = {"unchecked": "na", "offline": "na", "unreadable": "risk"}
# 项目健康 → 语义色。旧账（D-324：项目下已没有开着的卡时留下的账本问题）走提示色，不走风险色
HEALTH_SEV = {"ok": "ok", "risk": "risk", "block": "block", "old": "hint", "nodata": "na", "off": "na"}

# 语义名 -> (主色字段, 浅底字段)。严重度、健康、检查结果都只用这五种语义色。
SEMANTIC = {
    "block": ("block", "block_soft"),
    "risk": ("risk", "risk_soft"),
    "hint": ("hint", "hint_soft"),
    "ok": ("ok", "ok_soft"),
    "na": ("na", "na_soft"),
}


def font_css(stack: tuple[str, ...]) -> str:
    return ", ".join(f'"{name}"' for name in stack)


def build_qss(t: Tokens) -> str:
    """从令牌生成整张样式表。画面代码不写任何颜色。"""
    sem = []
    for name, (main, soft) in SEMANTIC.items():
        main_c, soft_c = getattr(t, main), getattr(t, soft)
        sem.append(
            f'QLabel#chip[sev="{name}"] {{ background: {soft_c}; color: {main_c}; }}\n'
            f'QFrame#card[sev="{name}"] {{ border-left: 4px solid {main_c}; }}\n'
            f'QLabel#mark[sev="{name}"] {{ background: {main_c}; color: {t.card}; }}\n'
            f'QFrame#bar[sev="{name}"] {{ background: {soft_c}; border: 1px solid {main_c}; }}\n'
            f'QLabel#check[sev="{name}"] {{ color: {main_c}; }}\n'
            f'QLabel#dot[sev="{name}"] {{ color: {main_c}; }}\n'
        )
    states = "".join(
        f'QLabel#state[state="{key}"] {{ background: {getattr(t, SEMANTIC[sev][1])}; color: {getattr(t, SEMANTIC[sev][0])}; }}\n'
        for key, sev in STATE_SEV.items()
    )
    return f"""
QMainWindow, QWidget#page, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {t.bg}; }}
QWidget {{ color: {t.fg}; font-family: {font_css(FONT_STACK)}; font-size: {FONT_SIZE_PT}pt; }}
QLabel#title {{ font-size: {FONT_SIZE_TITLE_PT}pt; font-weight: 600; }}
QLabel#section {{ font-weight: 600; margin-top: {SPACE // 2}px; }}
QLabel#q, QLabel#small {{ color: {t.fg3}; font-size: {FONT_SIZE_SMALL_PT}pt; }}
QLabel#muted {{ color: {t.fg2}; }}
QLabel#mono {{ font-family: {font_css(MONO_STACK)}; color: {t.fg2}; }}
QLabel#example {{ color: {t.fg3}; border: 1px dashed {t.fg3}; border-radius: 3px; padding: 0 3px;
    font-size: {FONT_SIZE_SMALL_PT}pt; }}
QLabel#chip {{ border-radius: 4px; padding: 1px 7px; font-size: {FONT_SIZE_SMALL_PT}pt;
    background: {t.card2}; color: {t.fg2}; border: 1px solid {t.line}; }}
QLabel#mark {{ border-radius: 9px; min-width: 18px; max-width: 18px; min-height: 18px; max-height: 18px;
    qproperty-alignment: AlignCenter; font-weight: 700; font-size: {FONT_SIZE_SMALL_PT}pt; }}
QFrame#card {{ background: {t.card}; border: 1px solid {t.line}; border-radius: {RADIUS}px; }}
QFrame#card[dashed="true"] {{ border-style: dashed; background: transparent; }}
QFrame#inner {{ background: {t.card2}; border: 1px solid {t.line}; border-radius: {RADIUS - 2}px; }}
QFrame#bar {{ border-radius: {RADIUS}px; }}
QFrame#idbar {{ background: {t.card}; border: 1px solid {t.line}; border-radius: {RADIUS}px; }}
QFrame#idbar[warn="true"] {{ background: {t.risk_soft}; border-color: {t.risk}; }}
QFrame#topbar {{ background: {t.bg}; border-bottom: 1px solid {t.line}; }}
QFrame#sidebar {{ background: {t.side}; border-right: 1px solid {t.line}; }}
QLabel#navgroup {{ color: {t.fg3}; font-size: {FONT_SIZE_SMALL_PT}pt; font-weight: 600;
    padding: {SPACE}px {SPACE}px {SPACE // 2}px {SPACE}px; }}
QPushButton#nav {{ border: none; background: transparent; color: {t.fg2}; text-align: left;
    padding: 5px {SPACE + 4}px; border-radius: {RADIUS}px; }}
QPushButton#nav:hover {{ background: {t.card2}; }}
QPushButton#nav:checked {{ background: {t.accent_soft}; color: {t.accent}; font-weight: 600; }}
QLabel#scope {{ color: {t.fg3}; font-size: {FONT_SIZE_SMALL_PT}pt; padding: {SPACE // 2}px {SPACE * 2}px 0 {SPACE * 2}px; }}
QLabel#heading {{ font-size: {FONT_SIZE_SECTION_PT}pt; font-weight: 600; }}
QLabel#state {{ border-radius: 4px; padding: 1px 7px; font-size: {FONT_SIZE_SMALL_PT}pt; }}
QPushButton {{ background: {t.card}; border: 1px solid {t.line2}; border-radius: {RADIUS}px;
    padding: 4px 11px; }}
QPushButton:hover {{ background: {t.card2}; }}
QPushButton:disabled {{ color: {t.fg3}; background: {t.card2}; border-color: {t.line}; }}
QPushButton#tab {{ border: none; background: transparent; color: {t.fg2}; padding: 5px 10px; }}
QPushButton#tab:checked {{ background: {t.accent_soft}; color: {t.accent}; font-weight: 600; }}
QPushButton#mode {{ padding: 3px 10px; border-radius: 0; }}
QPushButton#mode:checked {{ background: {t.fg}; color: {t.bg}; border-color: {t.fg}; }}
QPushButton#ghost {{ border-color: transparent; background: transparent; color: {t.accent}; }}
QTableWidget, QTreeWidget, QListWidget {{ background: {t.card}; border: 1px solid {t.line};
    border-radius: {RADIUS}px; gridline-color: {t.line}; }}
QHeaderView::section {{ background: {t.card2}; color: {t.fg2}; border: none;
    border-bottom: 1px solid {t.line}; padding: 5px 8px; font-size: {FONT_SIZE_SMALL_PT}pt; }}
QCheckBox {{ spacing: 6px; }}
QFrame#bc_form QLineEdit, QFrame#bc_form QComboBox, QFrame#tool_form QLineEdit, QFrame#tool_form QComboBox {{
    background: {t.card}; border: 1px solid {t.line2}; border-radius: 4px; padding: 3px 6px; }}
QPlainTextEdit#tool_output {{ background: {t.card2}; border: 1px solid {t.line}; border-radius: 4px; padding: 6px;
    font-family: {font_css(MONO_STACK)}; }}
QFrame#pre {{ background: {t.card2}; border: 1px solid {t.line}; border-radius: 4px; }}
QToolTip {{ background: {t.card}; color: {t.fg}; border: 1px solid {t.line2}; }}
QFrame[clickable="true"] {{ border: 1px solid transparent; border-radius: 4px; }}
QFrame[clickable="true"]:hover {{ background: {t.card2}; }}
QFrame[clickable="true"]:focus {{ border: 1px solid {t.accent}; }}
QFrame#numbox {{ background: {t.card}; border: 1px solid {t.line}; border-radius: {RADIUS}px; }}
QFrame#numbox[sev="block"] {{ background: {t.block_soft}; border: 1px solid {t.block}; }}
QFrame#numbox[sev="risk"] {{ background: {t.risk_soft}; border: 1px solid {t.risk}; }}
QFrame#numbox:focus {{ border: 2px solid {t.accent}; }}
QLabel#num {{ font-size: {FONT_SIZE_TITLE_PT}pt; font-weight: 600; }}
QFrame#lamp {{ background: {t.card}; border: 1px solid {t.line}; border-radius: {RADIUS}px; }}
QFrame#lamp[sev="block"] {{ background: {t.block_soft}; border: 1px solid {t.block}; }}
QFrame#lamp[sev="risk"] {{ background: {t.risk_soft}; border: 1px solid {t.risk}; }}
QFrame#lamp:focus {{ border: 2px solid {t.accent}; }}
QLabel#lampvalue {{ font-weight: 600; }}
QLabel#lampvalue[state="unchecked"], QLabel#lampvalue[state="offline"] {{ color: {t.fg3}; font-weight: 400; }}
QLabel#dot {{ color: {t.na}; }}
QLabel#cell {{ border: 1px solid {t.line}; padding: 1px 6px; color: {t.fg3}; font-size: {FONT_SIZE_SMALL_PT}pt; }}
QLabel#cell[at="done"] {{ color: {t.fg2}; background: {t.card2}; }}
QLabel#cell[at="current"] {{ color: {t.fg}; font-weight: 600; border: 1px solid {t.line2}; }}
QLabel#cell[at="current"][sev="block"] {{ background: {t.block_soft}; border: 1px solid {t.block}; }}
QLabel#cell[at="current"][sev="risk"] {{ background: {t.risk_soft}; border: 1px solid {t.risk}; }}
QFrame#version_pill {{ background: {t.card}; border: 1px solid {t.line2}; border-radius: {RADIUS}px; padding: 2px 8px; }}
QFrame#version_pill[warn="true"] {{ background: {t.risk_soft}; border-color: {t.risk}; }}
QFrame#gh_mode_pill {{ background: {t.card}; border: 1px solid {t.line2}; border-radius: {RADIUS}px; padding: 1px 4px; }}
QLabel#gh_seg {{ padding: 2px 6px; border-radius: 4px; color: {t.fg2}; font-size: {FONT_SIZE_SMALL_PT}pt; }}
QLabel#gh_seg[active="true"] {{ background: {t.accent_soft}; color: {t.accent}; font-weight: 600; }}
QFrame#telemetry_panel {{ background: {t.card2}; border: 1px solid {t.line}; border-radius: {RADIUS}px; padding: 6px; }}
QLabel#led[sev="ok"] {{ color: {t.ok}; font-weight: 700; }}
QLabel#led[sev="risk"] {{ color: {t.risk}; font-weight: 700; }}
QLabel#led[sev="block"] {{ color: {t.block}; font-weight: 700; }}
QLabel#led[sev="hint"] {{ color: {t.hint}; font-weight: 700; }}
QLabel#led[sev="na"] {{ color: {t.na}; }}
QFrame#project_bay {{ background: {t.card}; border: 1px solid {t.line2}; border-radius: {RADIUS + 2}px; }}
QFrame#bus_rail {{ background: {t.accent_soft}; border: 1px solid {t.accent}; border-radius: 3px; }}
QFrame#station_pod {{ background: {t.card2}; border: 1px solid {t.line}; border-radius: {RADIUS}px; }}
QFrame#station_pod[sev="block"] {{ border-left: 4px solid {t.block}; }}
QFrame#station_pod[sev="risk"] {{ border-left: 4px solid {t.risk}; }}
QFrame#console_drawer {{ background: {t.card2}; border-top: 1px solid {t.line2}; }}
QFrame#global_failure_bar {{ background: {t.block_soft}; border-bottom: 1px solid {t.block}; }}
QLabel#phase_pill {{ background: {t.card2}; color: {t.fg3}; border: 1px solid {t.line}; border-radius: 4px; padding: 2px 8px; font-size: {FONT_SIZE_SMALL_PT}pt; }}
QLabel#phase_pill[at="done"] {{ background: {t.ok_soft}; color: {t.ok}; border-color: {t.ok}; }}
QLabel#phase_pill[at="current"] {{ background: {t.accent_soft}; color: {t.accent}; border-color: {t.accent}; font-weight: 600; }}
QFrame#pill_filter {{ background: {t.card}; border: 1px solid {t.line}; border-radius: {RADIUS}px; padding: 2px 8px; }}
QFrame#pill_filter[active="true"] {{ background: {t.accent_soft}; border-color: {t.accent}; }}
QFrame#commands_filter QLineEdit {{ background: {t.card}; border: 1px solid {t.line2}; border-radius: 4px; padding: 4px 8px; color: {t.fg}; }}
{"".join(sem)}{states}"""


def token_names() -> list[str]:
    return [f.name for f in fields(Tokens)]
