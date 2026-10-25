"""图与文档一致性检查（WBS M3-FIG）：Mermaid 图能否解析，图里的信号在接口表、变量表里是否都有。

用途：流程图、状态机图随需求变更时，肉眼很难发现“图里画了信号 `bFoo`，接口表和变量表却没有”。本脚本只读，不改任何文档。
独立入口，不挂在 ``doc check`` 下：规范和现有文档都不动。

运行方式：
    python scripts/figure_consistency_check.py --diagram 018_流程图_FLOW.md \
        --interface 接口文档_INT.md --variables PLC变量定义文档_VAR.md [--json]

退出码：
    0 = 没有问题
    1 = 至少一处问题或未验证（输出里有 文件:行号）
    2 = 用法错误或文件读不到

两类检查：
    1. 图能否解析（只用标准库做结构检查，不替代 mmdc 渲染）：图类型已知、括号和引号成对、连线两端都有节点、``subgraph`` 与 ``end`` 配对。
    2. 信号对照：图里按 LSP-905 前缀写法识别出的信号（``i_`` / ``q_`` / ``io_`` / ``st`` / ``fb`` / ``ast`` /
       单字母类型前缀 ``b i r t`` 后接大写），必须在接口表或变量表里出现；
       没给接口表和变量表时，这一类检查报“未验证”，不会假装通过。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

DIAGRAM_TYPES = (
    "graph",
    "flowchart",
    "sequenceDiagram",
    "stateDiagram",
    "stateDiagram-v2",
    "classDiagram",
    "erDiagram",
    "gantt",
    "journey",
    "pie",
    "mindmap",
    "timeline",
    "gitGraph",
)
FLOW_TYPES = ("graph", "flowchart")
OPENERS = {"[": "]", "(": ")", "{": "}"}
CLOSERS = {value: key for key, value in OPENERS.items()}
EDGE_PATTERN = re.compile(r"(-->|---|-\.->|-\.-|==>|===|--[xo]|<-->)")
# 连线两端：箭头前后的节点 id（允许带形状括号），标签 |...| 或 -- text --> 先去掉
LABEL_PATTERN = re.compile(r"\|[^|]*\|")
SIGNAL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?:(?:i_|q_|io_)[A-Za-z]\w*|(?:ast|st|fb)[A-Z]\w*|[birt][A-Z]\w*)"
)
FENCE_OPEN = re.compile(r"^\s*```\s*mermaid\s*$")
FENCE_CLOSE = re.compile(r"^\s*```\s*$")
TABLE_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass(frozen=True)
class Finding:
    """一条问题：文件、行号、类别（parse / signal / unverified）与说明。"""

    file: str
    line: int
    kind: str
    message: str


@dataclass(frozen=True)
class MermaidBlock:
    """文档里的一个 mermaid 代码块；``start_line`` 是代码块第一行正文所在的文件行号。"""

    file: str
    start_line: int
    lines: tuple[str, ...]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig", errors="replace")


def extract_blocks(path: Path) -> list[MermaidBlock]:
    """取出 Markdown 里所有 mermaid 代码块；围栏没有闭合时按解析问题交给调用方（返回到文件末尾）。"""
    blocks: list[MermaidBlock] = []
    current: list[str] | None = None
    start = 0
    for number, line in enumerate(read_text(path).splitlines(), start=1):
        if current is None:
            if FENCE_OPEN.match(line):
                current, start = [], number + 1
        elif FENCE_CLOSE.match(line):
            blocks.append(MermaidBlock(path.as_posix(), start, tuple(current)))
            current = None
        else:
            current.append(line)
    if current is not None:
        blocks.append(MermaidBlock(path.as_posix(), start, (*current, "\x00UNCLOSED")))
    return blocks


def _strip_comment(line: str) -> str:
    return line.split("%%", 1)[0]


def _balanced(text: str) -> str | None:
    """括号与双引号成对检查；返回问题说明，没有问题返回 None。"""
    stack: list[str] = []
    in_quote = False
    for char in text:
        if char == '"':
            in_quote = not in_quote
        elif in_quote:
            continue
        elif char in OPENERS:
            stack.append(char)
        elif char in CLOSERS:
            if not stack or stack[-1] != CLOSERS[char]:
                return f"括号 {char!r} 没有对应的开括号"
            stack.pop()
    if in_quote:
        return "双引号没有闭合"
    if stack:
        return f"括号 {stack[-1]!r} 没有闭合"
    return None


def _endpoint_missing(statement: str) -> str | None:
    """flowchart 里一条连线两端都要有节点。"""
    cleaned = LABEL_PATTERN.sub("", statement)
    parts = EDGE_PATTERN.split(cleaned)
    # split 带分组：[左, 箭头, 中, 箭头, 右 ...]
    nodes = parts[0::2]
    if len(nodes) < 2:
        return None
    for index, node in enumerate(nodes):
        if not node.strip():
            return "连线一端缺少节点" if index in (0, len(nodes) - 1) else "连线之间缺少节点"
    return None


def check_block(block: MermaidBlock) -> list[Finding]:
    """检查一个图块能否解析；行号是文件里的真实行号。"""
    findings: list[Finding] = []
    lines = list(block.lines)
    if lines and lines[-1] == "\x00UNCLOSED":
        lines.pop()
        findings.append(
            Finding(block.file, block.start_line, "parse", "mermaid 代码块没有结束围栏 ```")
        )
    body = [(block.start_line + i, _strip_comment(text).strip()) for i, text in enumerate(lines)]
    body = [(number, text) for number, text in body if text]
    if not body:
        return [*findings, Finding(block.file, block.start_line, "parse", "mermaid 代码块是空的")]
    first_number, header = body[0]
    keyword = header.split()[0] if header.split() else ""
    if keyword not in DIAGRAM_TYPES:
        return [*findings, Finding(block.file, first_number, "parse", f"未知的图类型 {keyword!r}")]
    depth = 0
    for number, text in body[1:]:
        problem = _balanced(text)
        if problem:
            findings.append(Finding(block.file, number, "parse", problem))
            continue
        if keyword in FLOW_TYPES:
            if text.startswith("subgraph"):
                depth += 1
            elif text == "end":
                depth -= 1
                if depth < 0:
                    findings.append(Finding(block.file, number, "parse", "end 没有对应的 subgraph"))
                    depth = 0
            elif EDGE_PATTERN.search(text):
                missing = _endpoint_missing(text)
                if missing:
                    findings.append(Finding(block.file, number, "parse", missing))
    if keyword in FLOW_TYPES and depth > 0:
        findings.append(Finding(block.file, body[-1][0], "parse", "subgraph 没有对应的 end"))
    return findings


def signals_in_block(block: MermaidBlock) -> list[tuple[int, str]]:
    """图里出现的信号（行号, 名字）；``stStation1.bBusy`` 这类带点的写法逐段识别。"""
    found: list[tuple[int, str]] = []
    for i, text in enumerate(block.lines):
        if text == "\x00UNCLOSED":
            continue
        for match in SIGNAL_PATTERN.finditer(_strip_comment(text)):
            found.append((block.start_line + i, match.group(0)))
    return found


def table_names(path: Path) -> set[str]:
    """表格行里出现过的全部标识符（接口表、变量表的名字列和说明列都算，点号两侧分开记）。"""
    names: set[str] = set()
    for line in read_text(path).splitlines():
        if line.lstrip().startswith("|"):
            names.update(TABLE_TOKEN.findall(line))
    return names


def check_documents(
    diagrams: list[Path], interfaces: list[Path], variables: list[Path]
) -> list[Finding]:
    """全部检查；信号对照需要接口表或变量表至少一份，否则报“未验证”。"""
    findings: list[Finding] = []
    known: set[str] = set()
    for path in [*interfaces, *variables]:
        known |= table_names(path)
    for diagram in diagrams:
        blocks = extract_blocks(diagram)
        if not blocks:
            findings.append(Finding(diagram.as_posix(), 1, "parse", "文档里没有 mermaid 图"))
        for block in blocks:
            findings.extend(check_block(block))
            if not known:
                continue
            for number, name in signals_in_block(block):
                if name not in known:
                    findings.append(
                        Finding(
                            block.file,
                            number,
                            "signal",
                            f"图里的信号 {name} 在接口表和变量表里都没有",
                        )
                    )
    if diagrams and not known:
        findings.append(
            Finding(diagrams[0].as_posix(), 1, "unverified", "没有给接口表或变量表，信号对照未验证")
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="图与文档一致性检查（只读）")
    parser.add_argument(
        "--diagram", action="append", default=[], type=Path, help="含 mermaid 图的 Markdown，可重复"
    )
    parser.add_argument(
        "--interface", action="append", default=[], type=Path, help="接口表（INT）Markdown，可重复"
    )
    parser.add_argument(
        "--variables", action="append", default=[], type=Path, help="变量表（VAR）Markdown，可重复"
    )
    parser.add_argument("--json", action="store_true", help="机器可读输出")
    args = parser.parse_args(argv)
    if not args.diagram:
        print("至少给一个 --diagram", file=sys.stderr)
        return 2
    for path in [*args.diagram, *args.interface, *args.variables]:
        if not path.is_file():
            print(f"读不到文件：{path}", file=sys.stderr)
            return 2
    findings = check_documents(args.diagram, args.interface, args.variables)
    if args.json:
        print(json.dumps([asdict(item) for item in findings], ensure_ascii=False, indent=2))
    else:
        for item in findings:
            print(f"{item.file}:{item.line}: [{item.kind}] {item.message}")
        if not findings:
            print("图与文档一致：无问题")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
