"""生成《命令总目录》和《报警代码表》两页（WBS 8.11）。

用法（在本项目目录 SW-2026-008 下）：
  python scripts/command_catalog.py           # 重新生成两页（入库的那两页）
  python scripts/command_catalog.py --print   # 不写文件，把两页的当前内容打印出来（以这个为准）
  python scripts/command_catalog.py --check   # 只比对，不写；入库的两页落后于代码就退出 1（发版入库那张单上核）

只读扫描三样东西，不执行任何驾驶舱命令：
1. 命令树：导入 click 根命令，逐级列出每一条叶子命令（和
   tests/core/test_cockpit_board_contracts.py 用同一走法）；
   “谁能跑”“会不会写文件”取自 scripts/cockpit_board/flow/commands_map.json 的分类。
2. scripts/ 下的独立脚本：顶层每个 .py 和每个子目录的 __main__.py，取文档字符串首行。
3. 报警代码：在 auto_pm 源码里按语法树找作为参数、字典值或返回值出现的
   “前缀-三位数字”字符串（注释和文档字符串里提到的不算），记下出现的文件和同一处的提示语。

“有没有记录”一列在生成时去查规则和手册原文（AGENTS.md、36 号操作手册、本项目 README），只作参考。
入库的两页允许落后于代码，页头写明生成于哪个提交；每个 PR 只核脚本跑得通、每条命令和脚本都能出一行
（tests/infrastructure/test_command_catalog.py），“新命令没分类就报红”仍由 tests/core/test_cockpit_board_contracts.py 管。
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = PROJECT_ROOT.parents[3]
COMMANDS_MAP = PROJECT_ROOT / "scripts" / "cockpit_board" / "flow" / "commands_map.json"
CATALOG_PAGE = PROJECT_ROOT / "06_交付物" / "003_命令总目录_COMMANDS.md"
CODES_PAGE = PROJECT_ROOT / "06_交付物" / "004_报警代码表_CODES.md"
SOURCE_DIR = PROJECT_ROOT / "auto_pm"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
CONSTRAINTS_DIR = SOURCE_DIR / "domain" / "constraint" / "definitions"

# 生成时去查“有没有记录”的原文（相对工作区根）。只用于参考列，测试不读这些文件。
DOC_SOURCES: tuple[str, ...] = (
    "AGENTS.md",
    "SYS-2026-001_WorkspaceGovernance/01_项目文档/36_驾驶舱与双技术栈日常迭代操作手册_PM.md",
    "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/"
    "SW-2026-008_auto-pm_自动化项目管理工具/README.md",
)

CODE_PATTERN = re.compile(r"^(SHC|RP|CHK|LINT|FILE|DOC|PROJ|ENC|SEC|CODE)-(\d{3})(/.*)?$")

WHO_CAN_RUN = {
    "read": "任何人",
    "write": "agent 可跑（看板经白名单按钮、先预览）",
    "user_only": "只有用户本人",
    "never": "看板不放（钩子调用或规则禁止单独跑）",
}
WRITES = {"read": "不写", "write": "写", "user_only": "写", "never": "写"}

GENERATED_NOTE = "> 本页由 `scripts/command_catalog.py` 生成，不要手改。"
BASE_PREFIX = "> 生成于提交 "

# 形状像报警代码、但前缀不在 CODE_PATTERN 里的字符串：确认不是报警代码的写在这里并写明理由，
# 其余的由测试点名（新前缀不会悄悄漏出报警代码表）。
NOT_ALARM_CODES: dict[str, str] = {
    "PM-042": "规范编号（auto_pm/domain/plc/checker.py 引用 PM-042 规范），不是报警代码",
}
CODE_SHAPE = re.compile(r"^[A-Z][A-Z0-9]{1,7}-\d{3}(/.*)?$")


def base_commit() -> str:
    """生成时所在的提交（12 位）；读不到写“未知”。"""
    try:
        result = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "rev-parse", "--short=12", "HEAD"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",  # 只取提交号，生僻字节不致崩
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "未知"
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else "未知"


def _base_line(base: str) -> str:
    return (
        f"{BASE_PREFIX}`{base}`。**本页可能落后**：之后改过命令或代码而没人重跑脚本，页上就是旧的；"
        "要最新的，运行 `python scripts/command_catalog.py --print`，以它的输出为准。"
    )


@dataclass(frozen=True)
class CommandRow:
    """总目录里一条叶子命令。"""

    path: str
    summary: str
    who: str
    writes: str
    documented: str


@dataclass(frozen=True)
class ScriptRow:
    """总目录里一个独立脚本。"""

    path: str
    summary: str


@dataclass(frozen=True)
class CodeRow:
    """报警代码表里一个代码。"""

    code: str
    files: str
    messages: str


def _cell(text: str) -> str:
    """表格单元：去掉换行和竖线，保持一行。"""
    return " ".join(text.replace("|", "／").split())


def leaf_commands() -> dict[str, object]:
    """命令树里每一条叶子命令，键是空格连起来的路径。"""
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    import click

    from auto_pm.ui.cli.__main__ import cli

    found: dict[str, object] = {}

    def walk(command: click.Command, path: list[str]) -> None:
        if isinstance(command, click.Group):
            context = click.Context(command)
            for name in command.list_commands(context):
                child = command.get_command(context, name)
                if child is not None:
                    walk(child, [*path, name])
        else:
            found[" ".join(path)] = command

    walk(cli, [])
    return found


def _first_help_line(command: object) -> str:
    text = getattr(command, "help", None) or getattr(command, "short_help", None) or ""
    for line in str(text).strip().splitlines():
        if line.strip():
            return _cell(line.strip())
    return "（命令没写说明）"


def _documented(path: str, doc_texts: Sequence[str] | None) -> str:
    if doc_texts is None:
        return "未查"
    return "有" if any(f"`{path}" in text or f" {path} " in text for text in doc_texts) else "没有"


def command_rows(doc_texts: Sequence[str] | None = None) -> list[CommandRow]:
    """每条叶子命令一行。commands_map 里没分类的写“未分类”，由测试报红。"""
    mapping = json.loads(COMMANDS_MAP.read_text(encoding="utf-8"))["commands"]
    rows = []
    for path, command in sorted(leaf_commands().items()):
        entry = mapping.get(path, {})
        klass = entry.get("class", "")
        writes = WRITES.get(klass, "未分类")
        flags = entry.get("write_flags") or []
        if klass == "read" and flags:
            writes = "不写；带 " + "、".join(f"`{flag}`" for flag in flags) + " 时写"
        rows.append(
            CommandRow(
                path=path,
                summary=_first_help_line(command),
                who=WHO_CAN_RUN.get(klass, "未分类"),
                writes=writes,
                documented=_documented(path, doc_texts),
            )
        )
    return rows


def _docstring_line(path: Path) -> str:
    try:
        module = ast.parse(
            path.read_text(encoding="utf-8-sig", errors="replace")
        )  # 只读源码，生僻字节不致崩
    except SyntaxError:
        return "（读不懂源码）"
    doc = ast.get_docstring(module) or ""
    for line in doc.splitlines():
        if line.strip():
            return _cell(line.strip())
    return "（脚本没写说明）"


def script_rows() -> list[ScriptRow]:
    """scripts/ 顶层每个 .py，和每个子目录的 __main__.py。"""
    rows = [
        ScriptRow(path=f"scripts/{path.name}", summary=_docstring_line(path))
        for path in sorted(SCRIPTS_DIR.glob("*.py"))
        if path.name != "__init__.py"
    ]
    rows += [
        ScriptRow(path=path.relative_to(PROJECT_ROOT).as_posix(), summary=_docstring_line(path))
        for path in sorted(SCRIPTS_DIR.glob("*/__main__.py"))
    ]
    return sorted(rows, key=lambda row: row.path)


SEVERITY_WORDS = frozenset({"ERROR", "WARNING", "WARN", "INFO", "FAIL", "PASS", "-"})
MESSAGE_KEYS = ("message", "title", "msg", "description")


def _text_of(node: ast.expr | None) -> str | None:
    """字符串常量或 f 字符串的文字；f 字符串里的变量写成“…”。其余返回 None。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            else:
                parts.append("…")
        return "".join(parts)
    return None


def _code_of(node: ast.expr | None) -> str | None:
    """这个值若是报警代码（如 ``RP-008``、``LINT-004/schema_mismatch``），返回代码本身。"""
    text = node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None
    match = CODE_PATTERN.match(text) if text is not None else None
    return f"{match.group(1)}-{match.group(2)}" if match else None


def _is_message(text: str | None) -> bool:
    return bool(
        text
        and text.strip()
        and text.strip() not in SEVERITY_WORDS
        and CODE_PATTERN.match(text.strip()) is None
    )


def _codes_in(node: ast.AST) -> list[tuple[str, str | None]]:
    """一个调用、字典或返回语句里报出的代码，配上同一处的提示语。

    提示语先取名叫 message、title 等的参数或字典键，其次取代码后面第一个文字参数。
    """
    if isinstance(node, ast.Call):
        named = {keyword.arg: keyword.value for keyword in node.keywords if keyword.arg}
        values: list[ast.expr] = [*node.args, *named.values()]
        after = list(node.args)
    elif isinstance(node, ast.Dict):
        named = {
            key.value: value
            for key, value in zip(node.keys, node.values, strict=True)
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        values = list(named.values())
        after = []
    elif isinstance(node, ast.Return) and node.value is not None:
        return [(code, None)] if (code := _code_of(node.value)) else []
    else:
        return []
    found = []
    for index, value in enumerate(values):
        code = _code_of(value)
        if code is None:
            continue
        message = next(
            (text for key in MESSAGE_KEYS if _is_message(text := _text_of(named.get(key)))), None
        )
        if message is None and value in after:
            message = next(
                (
                    text
                    for later in after[after.index(value) + 1 :]
                    if _is_message(text := _text_of(later))
                ),
                None,
            )
        found.append((code, message))
    return found


def emitted_codes() -> dict[str, dict[str, set[str]]]:
    """代码 → {"files": 出现的文件, "messages": 同一处的提示语}。"""
    found: dict[str, dict[str, set[str]]] = {}
    for path in sorted(SOURCE_DIR.rglob("*.py")):
        try:
            tree = ast.parse(
                path.read_text(encoding="utf-8-sig", errors="replace")
            )  # 只读源码，生僻字节不致崩
        except SyntaxError:
            continue
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        for node in ast.walk(tree):
            for code, message in _codes_in(node):
                slot = found.setdefault(code, {"files": set(), "messages": set()})
                slot["files"].add(relative)
                if message:
                    slot["messages"].add(_cell(message.strip()))
    return found


def constraint_rows() -> list[CodeRow]:
    """约束编号（CST-…）：取自 auto_pm/domain/constraint/definitions 下每个 YAML 的 id 和 name。"""
    rows = []
    for path in sorted(CONSTRAINTS_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8-sig", errors="replace")  # 只读定义，生僻字节不致崩
        ident = re.search(r'^id:\s*"?([^"\n]+)"?\s*$', text, re.MULTILINE)
        name = re.search(r'^name:\s*"?([^"\n]+)"?\s*$', text, re.MULTILINE)
        if ident:
            rows.append(
                CodeRow(
                    code=ident.group(1).strip(),
                    files=f"`{path.relative_to(PROJECT_ROOT).as_posix()}`",
                    messages=_cell(name.group(1).strip()) if name else "（定义里没写名字）",
                )
            )
    return sorted(rows, key=lambda row: row.code)


def code_rows() -> list[CodeRow]:
    """报警代码表每个代码一行。"""
    return [
        CodeRow(
            code=code,
            files="、".join(f"`{name}`" for name in sorted(slot["files"])),
            messages="；".join(sorted(slot["messages"])) or "（同一处没有提示语，要看源码）",
        )
        for code, slot in sorted(emitted_codes().items())
    ]


def render_catalog(
    commands: Sequence[CommandRow], scripts: Sequence[ScriptRow], base: str = "未知"
) -> str:
    """《命令总目录》全文。"""
    lines = [
        "---",
        'spec_id: "COMMANDS"',
        'project_id: "SW-2026-008"',
        'title: "auto-pm 命令总目录（脚本生成）"',
        "---",
        "",
        "# 命令总目录",
        "",
        GENERATED_NOTE,
        _base_line(base),
        "> 什么能用、什么不能用，看仓库根 `docs/功能清单.md`；本页只回答“有哪些命令、谁能跑、会不会写文件”。",
        "> “谁能跑”“会不会写”取自 `scripts/cockpit_board/flow/commands_map.json` 的分类；"
        "“有没有记录”指 AGENTS.md、36 号操作手册、本项目 README 里有没有写到这条命令，生成时查的，只作参考。",
        "",
        f"## 驾驶舱命令（{len(commands)} 条）",
        "",
        "| 命令 | 干什么 | 谁能跑 | 会不会写文件 | 有没有记录 |",
        "|---|---|---|---|---|",
    ]
    lines += [
        f"| `{row.path}` | {row.summary} | {row.who} | {row.writes} | {row.documented} |"
        for row in commands
    ]
    lines += [
        "",
        f"## scripts 下的独立脚本（{len(scripts)} 个）",
        "",
        "| 脚本 | 干什么 |",
        "|---|---|",
    ]
    lines += [f"| `{row.path}` | {row.summary} |" for row in scripts]
    return "\n".join(lines) + "\n"


def render_codes(
    codes: Sequence[CodeRow], constraints: Sequence[CodeRow], base: str = "未知"
) -> str:
    """《报警代码表》全文。"""
    lines = [
        "---",
        'spec_id: "CODES"',
        'project_id: "SW-2026-008"',
        'title: "auto-pm 报警代码表（脚本生成）"',
        "---",
        "",
        "# 报警代码表",
        "",
        GENERATED_NOTE,
        _base_line(base),
        "> 只收源码里真会报出来的代码（作为参数、字典值或返回值出现）；注释和文档字符串里提到的不算。"
        "“提示语”取自报出这个代码的同一处，看不懂时按“出在哪”去读源码。",
        "",
        f"## 检查代码（{len(codes)} 个）",
        "",
        "| 代码 | 出在哪 | 提示语 |",
        "|---|---|---|",
    ]
    lines += [f"| `{row.code}` | {row.files} | {row.messages} |" for row in codes]
    lines += [
        "",
        f"## 约束编号（{len(constraints)} 个）",
        "",
        "`constraint check` 报的编号，取自每条约束定义文件的 id 和 name。哪几条机器真查、哪几条跳过，不在本页判断。",
        "",
        "| 编号 | 定义文件 | 名字 |",
        "|---|---|---|",
    ]
    lines += [f"| `{row.code}` | {row.files} | {row.messages} |" for row in constraints]
    return "\n".join(lines) + "\n"


def _read_docs() -> list[str]:
    texts = []
    for relative in DOC_SOURCES:
        path = WORKSPACE_ROOT / relative
        if path.is_file():
            texts.append(
                path.read_text(encoding="utf-8", errors="replace")
            )  # 只读查找，生僻字节不致崩
    return texts


def _documented_from_page() -> dict[str, str]:
    """已生成页面里的“有没有记录”列，--check 时沿用，免得比对时还要去读规则原文。"""
    if not CATALOG_PAGE.is_file():
        return {}
    found = {}
    for line in CATALOG_PAGE.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 5 and cells[0].startswith("`"):
            found[cells[0].strip("`")] = cells[4]
    return found


def build_pages(doc_texts: Sequence[str] | None, base: str = "未知") -> tuple[str, str]:
    """两页的全文：(命令总目录, 报警代码表)。"""
    return (
        render_catalog(command_rows(doc_texts), script_rows(), base),
        render_codes(code_rows(), constraint_rows(), base),
    )


def _without_base(text: str) -> str:
    """去掉页头“生成于提交”那一行，比对时不看它。"""
    return "\n".join(line for line in text.splitlines() if not line.startswith(BASE_PREFIX))


def unlisted_code_shapes() -> dict[str, set[str]]:
    """auto_pm 源码里作为值出现、形状像报警代码、前缀却不在名单里的字符串 → 出现的文件。"""
    found: dict[str, set[str]] = {}
    for path in sorted(SOURCE_DIR.rglob("*.py")):
        try:
            tree = ast.parse(
                path.read_text(encoding="utf-8-sig", errors="replace")
            )  # 只读源码，生僻字节不致崩
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                values: list[ast.expr] = [*node.args, *(keyword.value for keyword in node.keywords)]
            elif isinstance(node, ast.Dict):
                values = [value for value in node.values if value is not None]
            elif isinstance(node, ast.Return) and node.value is not None:
                values = [node.value]
            else:
                continue
            for value in values:
                text = value.value if isinstance(value, ast.Constant) else None
                if (
                    isinstance(text, str)
                    and CODE_SHAPE.match(text)
                    and CODE_PATTERN.match(text) is None
                    and text not in NOT_ALARM_CODES
                ):
                    found.setdefault(text, set()).add(path.relative_to(PROJECT_ROOT).as_posix())
    return found


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成《命令总目录》和《报警代码表》")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="只比对，不写；入库的两页落后就退出 1")
    group.add_argument(
        "--print", dest="show", action="store_true", help="不写文件，打印两页当前内容"
    )
    options = parser.parse_args(argv)
    base = base_commit()
    if options.show:
        catalog, codes = build_pages(None, base)
        sys.stdout.write(catalog + "\n" + codes)
        return 0
    if options.check:
        kept = _documented_from_page()
        rows = [
            CommandRow(row.path, row.summary, row.who, row.writes, kept.get(row.path, "未查"))
            for row in command_rows(None)
        ]
        catalog = render_catalog(rows, script_rows(), base)
        codes = render_codes(code_rows(), constraint_rows(), base)
        stale = [
            page.name
            for page, text in ((CATALOG_PAGE, catalog), (CODES_PAGE, codes))
            if not page.is_file()
            or _without_base(page.read_text(encoding="utf-8")) != _without_base(text)
        ]
        if stale:
            print("落后于代码：" + "、".join(stale) + "。重跑 python scripts/command_catalog.py")
            return 1
        print("两页和代码一致")
        return 0
    catalog, codes = build_pages(_read_docs(), base)
    CATALOG_PAGE.write_text(catalog, encoding="utf-8", newline="\n")
    CODES_PAGE.write_text(codes, encoding="utf-8", newline="\n")
    print(f"已写 {CATALOG_PAGE.name}、{CODES_PAGE.name}（生成于提交 {base}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
