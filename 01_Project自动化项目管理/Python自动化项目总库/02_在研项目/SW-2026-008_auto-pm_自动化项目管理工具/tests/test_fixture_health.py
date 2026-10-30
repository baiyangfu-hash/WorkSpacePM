"""元测试：检查所有测试 fixture 是否创建了项目标志文件。

背景：ChangeFileLocator._is_project_dir 依赖项目标志文件
（PM_SESSION_*.md / .plc.json / .copier-answers.yml）识别项目目录。
若 fixture 创建了项目目录但缺标志文件，locator 无法找到变更单，
导致测试假通过（if cr is not None: 跳过断言）或假失败（assert None is not None）。

本测试扫描 tests/ 下所有 .py 文件，查找创建项目目录的 fixture，
验证同一 fixture（或其调用的辅助函数）是否创建了项目标志文件。

检测逻辑（V2 改进）：
- 用 AST 分析 mkdir/makedirs 调用检测"创建目录"，替代字符串模式匹配
- 用 AST 分析 write_text/open 调用检测"创建标志文件"
- 递归检查辅助函数调用（最多 2 层深度），避免误报
- SERVICE_PATTERNS 使用单词边界，避免 get_change_request 误匹配 get_change_requests_paths
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

# 项目标志文件模式（用于检测 write_text/open 调用中的文件名）
MARKER_PATTERNS = [
    r"PM_SESSION_",
    r"\.plc\.json",
    r"\.copier-answers",
]

# 需要 ChangeService 的文件才需要项目标志文件（使用单词边界避免误匹配）
SERVICE_PATTERNS = [
    r"\bChangeService\b",
    r"\bchange_service\b",
    r"\bfind_change_file\b",
    r"\btransition_status\b",
    r"\bget_change_request\b",
]


def _find_test_files(tests_dir: Path) -> list[Path]:
    """递归查找 tests/ 下所有 .py 文件（排除 __pycache__ 和 helpers/）。"""
    return [
        p
        for p in tests_dir.rglob("*.py")
        if "__pycache__" not in str(p)
        and p.name != "__init__.py"
        and p.name != "test_fixture_health.py"  # 排除自身
        and "helpers" not in p.parts  # 排除辅助目录
    ]


def _test_contains_none_compare(node: ast.expr) -> bool:
    """递归检查表达式 AST 中是否包含 `is None` 或 `is not None` 比较。

    覆盖以下变体（R-C05 升级）：
    - 直接比较：`x is None` / `x is not None`
    - BoolOp 组合：`x is not None and y` / `x is None or z`
    - 属性访问：`obj.attr is not None`（left 为 Attribute）
    - 一元否定：`not (x is not None)`

    不误判的合理用法：
    - `if x:` / `if not x:`（真值比较，无 is/is not None）
    - `assert x is not None`（断言，非 if/IfExp 的 test）
    """
    if isinstance(node, ast.Compare):
        has_none_check = False
        for op, comparator in zip(node.ops, node.comparators, strict=False):
            if isinstance(op, (ast.Is, ast.IsNot)) and isinstance(
                comparator, ast.Constant
            ) and comparator.value is None:
                has_none_check = True
        return has_none_check
    if isinstance(node, ast.BoolOp):
        # `x is not None and y` / `x is None or z` 等组合
        return any(_test_contains_none_compare(v) for v in node.values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        # `not (x is not None)`
        return _test_contains_none_compare(node.operand)
    return False


def _body_contains_assert(stmts: list[ast.stmt]) -> bool:
    """检查 if 语句的 body/orelse 是否含 assert 语句（fake-pass 模式判定）。

    fake-pass 模式：`if cr is not None: assert ...` —— 当 cr 为 None 时
    断言被跳过，测试假通过。仅当 body 含 assert 才标记为违规。
    """
    for stmt in stmts:
        for n in ast.walk(stmt):
            if isinstance(n, ast.Assert):
                return True
    return False


# ── AST 分析工具 ──────────────────────────────────────────


def _extract_functions(source: str) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """提取源码中所有函数定义，返回 {函数名: AST 节点}。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _extract_fixtures(source: str) -> list[tuple[str, ast.FunctionDef]]:
    """提取源码中所有 fixture 函数和辅助函数，返回 (函数名, AST 节点) 列表。"""
    funcs = _extract_functions(source)
    fixtures: list[tuple[str, ast.FunctionDef]] = []
    # 排除创建规范文件/报告等非项目目录的辅助函数
    exclude_hints = ("spec_file", "spec_dir", "create_spec", "report", "scan_log")
    for name, node in funcs.items():
        if not isinstance(node, ast.FunctionDef):
            continue
        # 检查是否是 fixture（有 @pytest.fixture 装饰器）
        is_fixture = any(
            isinstance(d, ast.Attribute) and d.attr == "fixture"
            or isinstance(d, ast.Name) and d.id == "fixture"
            for d in node.decorator_list
        )
        # 也检查辅助函数（非 fixture 但创建工作空间/项目）
        if not is_fixture:
            name_lower = name.lower()
            name_hints = ("workspace", "create_chg", "build_chg", "_create")
            if not any(hint in name_lower for hint in name_hints):
                continue
            # 排除创建规范文件/报告等非项目目录的辅助函数
            if any(hint in name_lower for hint in exclude_hints):
                continue
        fixtures.append((name, node))
    return fixtures


def _calls_mkdir(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """检查函数 AST 是否包含 mkdir/makedirs 调用（创建目录）。"""
    for child in ast.walk(node):
        if isinstance(child, ast.Attribute) and child.attr in ("mkdir", "makedirs"):
            return True
    return False


def _extract_strings_from_node(node: ast.AST) -> list[str]:
    """从 AST 节点中提取所有字符串值（包括 f-string 的字面量部分）。"""
    strings: list[str] = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            strings.append(sub.value)
        elif isinstance(sub, ast.JoinedStr):
            # f-string：提取每个 FormattedValue 之间的字面量部分
            for value in sub.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    strings.append(value.value)
    return strings


def _creates_marker_file(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """检查函数 AST 是否创建项目标志文件。

    检测 write_text/open 调用中是否包含标志文件名模式（包括 f-string）。
    """
    for child in ast.walk(node):
        # 检测 write_text 调用（Path 对象方法）
        if isinstance(child, ast.Attribute) and child.attr == "write_text":
            # 检查调用链中的所有字符串（包括 f-string 字面量部分）
            for s in _extract_strings_from_node(child):
                if any(re.search(p, s) for p in MARKER_PATTERNS):
                    return True
        # 检测 open 调用中的标志文件名
        if isinstance(child, ast.Call):
            func = child.func
            # open(...) 调用
            if isinstance(func, ast.Name) and func.id == "open":
                for s in _extract_strings_from_node(child):
                    if any(re.search(p, s) for p in MARKER_PATTERNS):
                        return True
            # os.path.join(...) 中包含标志文件名
            if isinstance(func, ast.Attribute) and func.attr == "join":
                for s in _extract_strings_from_node(child):
                    if any(re.search(p, s) for p in MARKER_PATTERNS):
                        return True
    return False


def _get_called_functions(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """提取函数 AST 中调用的所有函数名（用于递归检查辅助函数）。"""
    called: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name):
                called.append(func.id)
            elif isinstance(func, ast.Attribute):
                called.append(func.attr)
    return called


def _fixture_creates_dir_with_marker(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    all_funcs: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    depth: int = 0,
    max_depth: int = 2,
) -> tuple[bool, bool]:
    """递归检查函数是否创建目录且创建标志文件。

    返回 (creates_dir, has_marker)。
    递归检查调用的辅助函数（最多 max_depth 层）。
    """
    creates_dir = _calls_mkdir(node)
    has_marker = _creates_marker_file(node)

    # 如果当前函数已创建目录且有标志文件，直接返回
    if creates_dir and has_marker:
        return (True, True)

    # 递归检查调用的辅助函数
    if depth < max_depth:
        for called_name in _get_called_functions(node):
            if called_name in all_funcs and called_name != node.name:
                sub_dir, sub_marker = _fixture_creates_dir_with_marker(
                    all_funcs[called_name], all_funcs, depth + 1, max_depth
                )
                creates_dir = creates_dir or sub_dir
                has_marker = has_marker or sub_marker

    return (creates_dir, has_marker)


# ── 兼容旧接口（保留但不再使用字符串模式匹配）──────────────


def _fixture_creates_project_dir(source: str) -> bool:
    """[已废弃] 检查源码是否包含创建项目目录的代码模式。"""
    return False  # 不再使用字符串模式匹配


def _fixture_has_marker(source: str) -> bool:
    """[已废弃] 检查源码是否包含创建项目标志文件的代码模式。"""
    return False  # 不再使用字符串模式匹配


class TestFixtureHealth:
    """元测试：验证所有测试 fixture 的项目标志文件完整性。"""

    @pytest.fixture
    def tests_dir(self) -> Path:
        """测试目录"""
        return Path(__file__).parent

    def test_all_fixtures_have_project_markers(self, tests_dir: Path) -> None:
        """扫描使用 ChangeService 的测试文件，确保创建项目目录的 fixture 同时创建了项目标志文件。

        V2 改进：用 AST 分析 mkdir/makedirs 调用检测"创建目录"，
        递归检查辅助函数调用，避免字符串模式匹配的误报。

        本测试为 FAIL 级别（TD-T07 已升级）：发现问题时阻断测试套件，
        防止技术债再次累积。依赖 TD-T03/T04 已偿还（0 violations）。
        """
        test_files = _find_test_files(tests_dir)
        assert len(test_files) > 0, "未找到测试文件"

        violations: list[str] = []

        for file_path in test_files:
            rel_path = file_path.relative_to(tests_dir)
            source = file_path.read_text(encoding="utf-8")

            # 筛选：文件必须使用 ChangeService 相关 API
            if not any(re.search(p, source) for p in SERVICE_PATTERNS):
                continue

            # 提取所有函数（fixture + 辅助函数）
            all_funcs = _extract_functions(source)
            if not all_funcs:
                continue

            # 提取 fixture 和辅助函数
            fixtures = _extract_fixtures(source)

            for func_name, func_node in fixtures:
                # 递归检查：是否创建目录且创建标志文件
                creates_dir, has_marker = _fixture_creates_dir_with_marker(
                    func_node, all_funcs
                )

                # 只报告"创建目录但缺标志文件"的 fixture
                if creates_dir and not has_marker:
                    violations.append(
                        f"  - {rel_path}::{func_name}"
                    )

        if violations:
            msg = "\n".join(violations)
            pytest.fail(
                f"[FIXTURE HEALTH FAIL] 发现 {len(violations)} 个 fixture 缺项目标志文件：\n{msg}\n"
                f"这些 fixture 会导致 ChangeFileLocator 无法定位项目目录，"
                f"必须修复以避免假通过/假失败。"
            )

    def test_no_conditional_assertion_skips(self, tests_dir: Path) -> None:
        """检查是否存在 `if cr is not None: assert ...` 类条件断言跳过（假通过模式）。

        本测试为 FAIL 级别（TD-T07 已升级）：发现问题时阻断测试套件，
        防止假通过模式再次出现。依赖 TD-T04 已偿还（0 violations）。

        V2.1.0 升级（R-C05）：从正则字符串匹配改为 AST 分析，
        精准定位 fake-pass 模式——`ast.If` 语句且 test 含
        `is None`/`is not None` 比较且 body 含 `assert` 语句。

        AST walk 覆盖以下 test 变体（满足"能检测"要求）：
        - `if x is not None:`（基础）
        - `if x is not None and y:` / `if x is None or y:`（BoolOp 组合）
        - `if x is None:`（反向 None 比较）
        - `if obj.attr is not None:`（属性访问）
        - `x if x is not None else y`（三元表达式 IfExp，AST walk 访问）

        不误判的合理用法（不 FLAG）：
        - `if x is None: return/continue/skip`（无 assert 的合理控制流）
        - `if x:` / `if not x:`（真值比较）
        - `x if x is not None else y`（三元数据构造，IfExp 无法含 assert）
        - `assert x is not None`（断言本身，非 if 语句）
        """
        test_files = _find_test_files(tests_dir)
        violations: list[str] = []

        for file_path in test_files:
            rel_path = file_path.relative_to(tests_dir)
            source = file_path.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source, filename=str(file_path))
            except SyntaxError:
                continue  # 跳过无法解析的文件

            count = 0
            for node in ast.walk(tree):
                # 仅检查 ast.If（语句）的 test 字段；IfExp（三元）无法含 assert，
                # 数据构造用法不构成 fake-pass，不标记
                if isinstance(node, ast.If) and _test_contains_none_compare(node.test):
                    # body 含 assert 才是 fake-pass 模式
                    if _body_contains_assert(node.body) or _body_contains_assert(node.orelse):
                        count += 1

            if count:
                violations.append(f"  - {rel_path}（{count}处）")

        if violations:
            msg = "\n".join(violations)
            pytest.fail(
                f"[FIXTURE HEALTH FAIL] 发现 {len(violations)} 个文件存在条件断言跳过模式：\n{msg}\n"
                f"必须改为 `assert x is not None` 暴露 fixture 缺陷，避免假通过。"
            )
