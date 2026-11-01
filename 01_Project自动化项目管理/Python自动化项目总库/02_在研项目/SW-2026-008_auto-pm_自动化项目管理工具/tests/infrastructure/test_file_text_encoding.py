"""DEV-ENC-001 门禁：``auto_pm/`` 里读写文本文件必须写明 encoding，不依赖 Windows 默认的 GBK。

``Path.read_text()`` / ``write_text(x)`` / ``open(p)`` 不写 encoding 时，用的是这台电脑的默认编码：笔记本（中文 Windows）上是 GBK，
云端和 CI（Linux）上是 UTF-8。同一份代码在两边读写出不同的字节，中文文档、台账、卡片会在换一台电脑后变成乱码或直接读不出来，
而测试在 Linux 上照样全绿。``test_subprocess_text_encoding.py`` 已经管了子进程的文本模式，这里补上文件读写。

判定（语法树，不是正则）：

* ``<路径>.read_text()`` 没有 ``encoding``（关键字或第一个位置参数）；
* ``<路径>.write_text(数据)`` 没有 ``encoding``（关键字或第二个位置参数）；
* 内置 ``open(...)`` / ``io.open(...)`` 文本模式（没写 mode，或 mode 里没有 ``b``）却没有 ``encoding``；
* ``<路径>.open(...)`` 只在没有位置参数、或第一个参数是纯模式字符串（如 ``"r"``、``"w"``）时才算文本打开——
  ``os.open``、``webbrowser.open``、``tarfile.open(fileobj=...)``、``service.open(agent, card)`` 这类同名方法不是文件读写；
* ``NamedTemporaryFile`` / ``TemporaryFile`` / ``SpooledTemporaryFile`` 明确写了文本 mode 却没有 ``encoding``。

带 ``**kwargs`` 的调用不判（编码可能在字典里）。现状 ``auto_pm/`` 里是 0 处，基线就是 0：以后新增一处就变红。
``tests/``、``scripts/`` 里还有存量，不在本卡点范围。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = PROJECT_ROOT / "auto_pm"
TEMP_FILES = frozenset({"NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile"})
MODE_ONLY = re.compile(r"^[rwxat+U]{1,4}$")


def _call_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _constant_str(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _mode(call: ast.Call, position: int) -> tuple[bool, str | None]:
    """(a mode was given, its text when it is a plain string)."""

    for keyword in call.keywords:
        if keyword.arg == "mode":
            return True, _constant_str(keyword.value)
    if len(call.args) > position:
        return True, _constant_str(call.args[position])
    return False, None


def _has_encoding(call: ast.Call, position: int) -> bool:
    return any(k.arg == "encoding" for k in call.keywords) or len(call.args) > position


def _is_unencoded_text_io(call: ast.Call) -> bool:
    name = _call_name(call)
    if name is None or any(keyword.arg is None for keyword in call.keywords):
        return False
    is_attribute = isinstance(call.func, ast.Attribute)
    if name == "read_text":
        return not _has_encoding(call, 0)
    if name == "write_text":
        return not _has_encoding(call, 1)
    if name == "open" and not is_attribute:  # builtin open(file, mode, buffering, encoding, ...)
        given, mode = _mode(call, 1)
        text = not given or mode is None or "b" not in mode
        return text and not (any(k.arg == "encoding" for k in call.keywords) or len(call.args) > 3)
    if name == "open" and is_attribute:
        owner = call.func.value if isinstance(call.func, ast.Attribute) else None
        if isinstance(owner, ast.Name) and owner.id == "io":  # io.open has the builtin's signature
            given, mode = _mode(call, 1)
            text = not given or mode is None or "b" not in mode
            return text and not (
                any(k.arg == "encoding" for k in call.keywords) or len(call.args) > 3
            )
        # Path.open(mode, buffering, encoding, ...): only the bare form or a plain mode string is a text open
        first = _constant_str(call.args[0]) if call.args else None
        if call.args and (first is None or not MODE_ONLY.match(first)):
            return False
        if not call.args and any(
            k.arg not in {"mode", "buffering", "encoding", "errors", "newline"}
            for k in call.keywords
        ):
            return False
        given, mode = _mode(call, 0)
        text = not given or mode is None or "b" not in mode
        return text and not (any(k.arg == "encoding" for k in call.keywords) or len(call.args) > 2)
    if name in TEMP_FILES:
        given, mode = _mode(call, 0)
        text = given and mode is not None and "b" not in mode
        return text and not any(k.arg == "encoding" for k in call.keywords)
    return False


def unencoded_text_io(source: bytes, filename: str = "<source>") -> list[int]:
    """Lines of text-mode file reads and writes that do not name an encoding.

    ``source`` is parsed from its bytes, so a BOM or a coding cookie is Python's business; a file that cannot be parsed raises
    (and fails the test, naming the file) instead of being skipped.
    """

    tree = ast.parse(source, filename=filename)
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _is_unencoded_text_io(node)
    )


def _scan(sample: str) -> list[int]:
    return unencoded_text_io(sample.encode("utf-8"))


def test_no_text_file_io_in_the_package_misses_its_encoding() -> None:
    offenders: list[str] = []
    files = 0
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        files += 1
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        offenders.extend(
            f"{relative}:{line}" for line in unencoded_text_io(path.read_bytes(), relative)
        )
    assert files > 100, "the scan found almost nothing: the walker is broken"
    assert not offenders, (
        "auto_pm 里读写文本文件没写 encoding（DEV-ENC-001；中文 Windows 默认是 GBK，云端是 UTF-8，同一份代码两边读写的字节不同）。"
        '请显式写 encoding="utf-8"：' + "、".join(offenders)
    )


def test_missing_encodings_are_flagged() -> None:
    assert _scan("a = p.read_text()\n") == [1]
    assert _scan("p.write_text(data)\n") == [1]
    assert _scan("f = open(p)\n") == [1]
    assert _scan("f = open(p, 'w')\n") == [1]
    assert _scan("f = open(p, mode='r')\n") == [1]
    assert _scan("f = io.open(p)\n") == [1]
    assert _scan("f = p.open()\n") == [1]
    assert _scan("f = p.open('w')\n") == [1]
    assert _scan("f = tempfile.NamedTemporaryFile('w', delete=False)\n") == [1]
    assert _scan("f = tempfile.NamedTemporaryFile(mode='w+')\n") == [1]
    assert _scan("x = 1\ny = p.read_text()\nz = q.write_text('a')\n") == [2, 3]


def test_written_encodings_and_binary_modes_are_not_flagged() -> None:
    assert _scan("a = p.read_text(encoding='utf-8')\n") == []
    assert _scan("a = p.read_text('utf-8')\n") == []
    assert _scan("p.write_text(data, encoding='utf-8')\n") == []
    assert _scan("p.write_text(data, 'utf-8')\n") == []
    assert _scan("f = open(p, encoding='utf-8')\n") == []
    assert _scan("f = open(p, 'w', -1, 'utf-8')\n") == []
    assert _scan("f = open(p, 'rb')\n") == []
    assert _scan("f = open(p, mode='wb')\n") == []
    assert _scan("f = p.open('rb')\n") == []
    assert _scan("f = p.open('w', encoding='utf-8')\n") == []
    assert _scan("f = tempfile.NamedTemporaryFile(delete=False)\n") == []  # default mode is binary
    assert _scan("f = tempfile.NamedTemporaryFile('wb')\n") == []
    assert _scan("f = tempfile.NamedTemporaryFile('w', encoding='utf-8')\n") == []
    assert _scan("a = p.read_text(**kw)\n") == []  # the encoding may be in the dict


def test_same_named_methods_that_are_not_file_io_are_not_flagged() -> None:
    assert _scan("fd = os.open(path, os.O_RDONLY)\n") == []
    assert _scan("webbrowser.open('file:///x')\n") == []
    assert _scan("tarfile.open(fileobj=buf)\n") == []
    assert _scan("station = service.open(agent, card, fetch=True)\n") == []
    assert _scan("opened = service.open(plan)\n") == []
    assert _scan("text = raw.decode('utf-8')\n") == []
    assert _scan("x = text.replace('a', 'b')\n") == []


def test_a_file_with_a_bom_is_parsed() -> None:
    sample = b"\xef\xbb\xbf" + "a = p.read_text()\nb = '中文'\n".encode()
    assert unencoded_text_io(sample) == [1]


def test_a_file_that_cannot_be_parsed_fails_instead_of_counting_as_clean() -> None:
    import pytest

    with pytest.raises(SyntaxError):
        unencoded_text_io(b"a = p.read_text(\n")
