"""主题令牌：颜色、字体、间距、圆角只在这里定义。

改颜色、字体：改 LIGHT / DARK 两个 Tokens 的字段，或 FONT_STACK，不用碰任何画面代码。
画面代码只用 objectName 和动态属性（sev、health、state），样式由 build_qss() 从令牌生成。
"""

from __future__ import annotations

from dataclasses import dataclass, fields

# 字体：系统中文字体优先，不引外网字体（内网 / 断网也要能看）。
FONT_STACK = ("Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Segoe UI")
MONO_STACK = ("Consolas", "Menlo", "SF Mono", "DejaVu Sans Mono")
FONT_SIZE_PT = 10
FONT_SIZE_TITLE_PT = 15
FONT_SIZE_SMALL_PT = 9

SPACE = 8  # 基本间距，其余都是它的倍数
RADIUS = 6


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
    block: str  # 阻塞 / 受阻
    block_soft: str
    risk: str  # 风险 / 有风险
    risk_soft: str
    hint: str  # 提醒
    hint_soft: str
    ok: str  # 正常 / 过
    ok_soft: str
    na: str  # 没检查 / 无数据（灰）
    na_soft: str


LIGHT = Tokens(
    bg="#f3f4f6",
    card="#ffffff",
    card2="#f8f9fb",
    line="#e2e5ea",
    line2="#cfd4db",
    fg="#17191d",
    fg2="#5c6470",
    fg3="#8b93a0",
    accent="#1d5c8f",
    accent_soft="#e3eef7",
    block="#c6262e",
    block_soft="#fbe9ea",
    risk="#b7700a",
    risk_soft="#fdf1dc",
    hint="#2f6db3",
    hint_soft="#e6eef9",
    ok="#3b7d4f",
    ok_soft="#e5f2e8",
    na="#8b93a0",
    na_soft="#eef0f3",
)

DARK = Tokens(
    bg="#17191d",
    card="#1f2228",
    card2="#24282f",
    line="#2f343c",
    line2="#3d434d",
    fg="#e8eaed",
    fg2="#a9b0ba",
    fg3="#7c8491",
    accent="#7fb3e0",
    accent_soft="#1f3346",
    block="#ef6b6b",
    block_soft="#3a2224",
    risk="#e2a73a",
    risk_soft="#3a2f1a",
    hint="#7fb3e0",
    hint_soft="#1f3346",
    ok="#7cc48f",
    ok_soft="#1f3326",
    na="#7c8491",
    na_soft="#262a31",
)

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
QFrame#bc_form QLineEdit, QFrame#bc_form QComboBox {{ background: {t.card}; border: 1px solid {t.line2}; border-radius: 4px; padding: 3px 6px; }}
QFrame#pre {{ background: {t.card2}; border: 1px solid {t.line}; border-radius: 4px; }}
QToolTip {{ background: {t.card}; color: {t.fg}; border: 1px solid {t.line2}; }}
{"".join(sem)}
"""


def token_names() -> list[str]:
    return [f.name for f in fields(Tokens)]
