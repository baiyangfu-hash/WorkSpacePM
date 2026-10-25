"""DEV-ENC-001 门禁：文本模式的 subprocess 调用必须写明 encoding，不依赖 Windows 终端默认的 GBK。"""

from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCANNED_DIRECTORIES = ("auto_pm", "scripts", "tests")
SUBPROCESS_CALLS = {"run", "check_output", "check_call", "Popen", "call"}


def _is_truthy_keyword(call: ast.Call, name: str) -> bool:
    for keyword in call.keywords:
        if keyword.arg == name:
            return not (isinstance(keyword.value, ast.Constant) and keyword.value.value is False)
    return False


def _unencoded_text_calls(source: str) -> list[int]:
    """文本模式（text / universal_newlines）却没有 encoding 的 subprocess 调用所在行；带 ``**kwargs`` 的调用不判。"""
    lines: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        owner = node.func.value
        if not (
            isinstance(owner, ast.Name)
            and owner.id == "subprocess"
            and node.func.attr in SUBPROCESS_CALLS
        ):
            continue
        if any(keyword.arg is None for keyword in node.keywords):
            continue
        text_mode = _is_truthy_keyword(node, "text") or _is_truthy_keyword(
            node, "universal_newlines"
        )
        if text_mode and not any(keyword.arg == "encoding" for keyword in node.keywords):
            lines.append(node.lineno)
    return lines


def test_no_text_mode_subprocess_without_encoding() -> None:
    offenders: list[str] = []
    for directory in SCANNED_DIRECTORIES:
        for path in sorted((PROJECT_ROOT / directory).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            source = path.read_text(encoding="utf-8-sig", errors="replace")
            offenders.extend(
                f"{path.relative_to(PROJECT_ROOT).as_posix()}:{line}"
                for line in _unencoded_text_calls(source)
            )
    assert not offenders, f"文本模式 subprocess 缺 encoding（DEV-ENC-001）：{offenders}"


def test_detector_flags_missing_encoding_and_accepts_the_fixed_forms() -> None:
    bad = "import subprocess\nsubprocess.run(['x'], capture_output=True, text=True)\n"
    assert _unencoded_text_calls(bad) == [2]
    assert _unencoded_text_calls(
        "import subprocess\nsubprocess.Popen(['x'], universal_newlines=True)\n"
    ) == [2]
    good = (
        "import subprocess\nsubprocess.run(['x'], text=True, encoding='utf-8', errors='replace')\n"
    )
    assert _unencoded_text_calls(good) == []
    assert (
        _unencoded_text_calls("import subprocess\nsubprocess.run(['x'], capture_output=True)\n")
        == []
    )
    assert _unencoded_text_calls("import subprocess\nsubprocess.run(['x'], text=False)\n") == []
    assert (
        _unencoded_text_calls("import subprocess\nsubprocess.run(['x'], text=True, **kw)\n") == []
    )
