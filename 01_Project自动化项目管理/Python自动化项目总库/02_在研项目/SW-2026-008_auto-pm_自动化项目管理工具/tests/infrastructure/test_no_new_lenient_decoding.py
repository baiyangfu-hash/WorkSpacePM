"""TD-SW008-237: no NEW lenient decoding (``errors="replace"`` / ``"ignore"``) in ``auto_pm/`` without a written reason.

A lenient decode turns bytes it cannot read into ``?`` or drops them, so a damaged file or a git output in an unexpected encoding is
read as something else and nobody is told (the backup rollback once wrote the damage back to disk).  Each use must be reviewed: either
decode strictly (and report what cannot be read), or keep the lenient decode and say why on the same line::

    text = path.read_text(encoding="utf-8", errors="replace")  # lenient-decode: display only, never written back

What counts: a call with ``errors="replace"`` / ``errors="ignore"``, and ``.decode(encoding, "replace")`` / ``.decode(encoding, "ignore")``.
Counts are baselined per file at today's numbers (the 67 uses already in ``auto_pm/``, not yet reviewed one by one); a file may not use more
than its baseline, a file not in the baseline may use none, and a reviewed use (marker with a reason) is not counted.  When you convert or
mark one, lower the numbers with ``python tests/infrastructure/test_no_new_lenient_decoding.py --write``.  This ratchet does not close
TD-SW008-237: it only stops the debt from growing while the existing uses are reviewed.
"""

from __future__ import annotations

import ast
import io
import json
import re
import sys
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "auto_pm"
BASELINE = Path(__file__).with_name("lenient_decoding_baseline.json")
LENIENT = frozenset({"replace", "ignore"})
MARKER = re.compile(r"#\s*lenient-decode:\s*\S")


def _is_lenient(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in LENIENT


def _lenient_calls(tree: ast.AST) -> list[ast.Call]:
    found: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        keyword = any(kw.arg == "errors" and _is_lenient(kw.value) for kw in node.keywords)
        decode = (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "decode"
            and len(node.args) >= 2
            and _is_lenient(node.args[1])
        )
        if keyword or decode:
            found.append(node)
    return found


def count_lenient_decodes(path: Path) -> int:
    """Lenient decodes in ``path`` that carry no written reason.

    The file is parsed from its raw bytes, so a BOM or a coding cookie is handled by Python itself.  A file that cannot be parsed or
    decoded raises (and fails the test, naming the file): counting it as 0 would let it hide any number of lenient decodes.
    """

    data = path.read_bytes()
    tree = ast.parse(data, filename=str(path))
    encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
    lines = data.decode(
        encoding
    ).splitlines()  # strict: ast.parse above already accepted these bytes
    total = 0
    for call in _lenient_calls(tree):
        end = call.end_lineno or call.lineno
        if any(MARKER.search(line) for line in lines[call.lineno - 1 : end]):
            continue
        total += 1
    return total


def over_baseline(counts: dict[str, int], baseline: dict[str, int]) -> dict[str, tuple[int, int]]:
    """Files that use more lenient decodes than allowed: ``{path: (now, allowed)}``; a file not in the baseline is allowed none."""

    return {p: (n, baseline.get(p, 0)) for p, n in counts.items() if n > baseline.get(p, 0)}


def slack_baseline(counts: dict[str, int], baseline: dict[str, int]) -> dict[str, tuple[int, int]]:
    """Files whose baseline is looser than reality: ``{path: (baseline, now)}``; a baselined file now gone or clean counts as 0."""

    return {p: (b, counts.get(p, 0)) for p, b in baseline.items() if counts.get(p, 0) < b}


def current_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        n = count_lenient_decodes(path)
        if n:
            counts[path.relative_to(ROOT).as_posix()] = n
    return counts


def test_keyword_and_positional_lenient_decodes_are_counted(tmp_path: Path) -> None:
    sample = tmp_path / "s.py"
    sample.write_text(
        "a = p.read_text(encoding='utf-8', errors='replace')\n"
        "b = open(p, encoding='utf-8', errors='ignore')\n"
        "c = raw.decode('utf-8', 'replace')\n"
        "d = raw.decode('utf-8', errors='replace')\n"
        "e = subprocess.run(cmd, text=True, errors='replace')\n",
        encoding="utf-8",
    )
    assert count_lenient_decodes(sample) == 5


def test_strict_and_unrelated_decoding_is_not_counted(tmp_path: Path) -> None:
    sample = tmp_path / "s.py"
    sample.write_text(
        "a = p.read_text(encoding='utf-8')\n"
        "b = raw.decode('utf-8')\n"
        "c = raw.decode('utf-8', 'strict')\n"
        "d = p.read_text(encoding='utf-8', errors=mode)\n"  # decided elsewhere: not judged here
        "e = text.replace('a', 'b')\n"  # str.replace is not a decode
        "f = raw.decode('utf-8', 'surrogateescape')\n",  # lossless round trip
        encoding="utf-8",
    )
    assert count_lenient_decodes(sample) == 0


def test_a_reviewed_use_with_a_written_reason_is_not_counted_but_an_empty_marker_is(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "s.py"
    sample.write_text(
        "a = p.read_text(encoding='utf-8', errors='replace')  # lenient-decode: display only, never written back\n"
        "b = p.read_text(encoding='utf-8', errors='replace')  # lenient-decode:\n"
        "c = p.read_text(encoding='utf-8', errors='replace')  # fine\n"
        "d = p.read_text(\n"
        "    encoding='utf-8',\n"
        "    errors='replace',  # lenient-decode: multi-line call, reason on a later line\n"
        ")\n",
        encoding="utf-8",
    )
    assert count_lenient_decodes(sample) == 2


def test_the_scan_covers_the_package_and_finds_the_known_uses() -> None:
    counts = current_counts()
    assert PACKAGE.is_dir() and counts, (
        "the scan found nothing: the walker or the detector is broken"
    )
    assert sum(counts.values()) >= 20


def test_a_file_with_a_bom_is_parsed_and_counted(tmp_path: Path) -> None:
    sample = tmp_path / "s.py"
    sample.write_bytes(
        b"\xef\xbb\xbf"
        + (
            "a = p.read_text(encoding='utf-8', errors='replace')\n"
            "b = p.read_text(encoding='utf-8', errors='replace')  # lenient-decode: reviewed\n"
            "c = '\u4e2d\u6587'\n"
        ).encode("utf-8")
    )
    assert count_lenient_decodes(sample) == 1


def test_a_file_that_cannot_be_parsed_fails_instead_of_counting_as_zero(tmp_path: Path) -> None:
    broken = tmp_path / "broken.py"
    broken.write_bytes(b"a = p.read_text(errors='replace'\n")  # unclosed parenthesis
    with pytest.raises(SyntaxError):
        count_lenient_decodes(broken)
    undecodable = tmp_path / "undecodable.py"
    undecodable.write_bytes(b"# -*- coding: utf-8 -*-\nx = '\xff\xfe'\n")
    with pytest.raises(SyntaxError):
        count_lenient_decodes(undecodable)


def test_over_baseline_flags_growth_and_unlisted_files_using_synthetic_counts() -> None:
    baseline = {"a.py": 2, "b.py": 1, "gone.py": 3}
    counts = {"a.py": 3, "b.py": 1, "new.py": 1}
    assert over_baseline(counts, baseline) == {"a.py": (3, 2), "new.py": (1, 0)}
    assert over_baseline({"a.py": 2, "b.py": 0}, baseline) == {}  # equal or lower is fine


def test_slack_baseline_flags_loose_entries_using_synthetic_counts() -> None:
    baseline = {"a.py": 2, "b.py": 1, "gone.py": 3}
    counts = {"a.py": 1, "b.py": 1, "new.py": 1}
    assert slack_baseline(counts, baseline) == {"a.py": (2, 1), "gone.py": (3, 0)}
    assert slack_baseline({"a.py": 2, "b.py": 1, "gone.py": 3, "extra.py": 5}, baseline) == {}


def test_no_file_uses_more_lenient_decodes_than_the_baseline() -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    over = over_baseline(current_counts(), baseline)
    assert not over, (
        '新增了宽松解码（errors="replace"/"ignore"，坏字节会被悄悄换成问号或丢掉）。请改成严格解码并报告读不了的内容；'
        "确需保留就在同一行写 `# lenient-decode: <理由>`（理由不能为空）："
        + "；".join(f"{p} 现 {n} 处，基线 {b} 处" for p, (n, b) in sorted(over.items()))
    )


def test_the_baseline_is_tight_so_reviewed_uses_cannot_come_back() -> None:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    slack = slack_baseline(current_counts(), baseline)
    assert not slack, (
        "基线比实际宽松（有的宽松解码已改严格或已写理由），请运行 `python tests/infrastructure/test_no_new_lenient_decoding.py --write` 收紧："
        + "；".join(f"{p} 基线 {b} 实际 {c}" for p, (b, c) in sorted(slack.items()))
    )


if __name__ == "__main__":
    if "--write" in sys.argv:
        BASELINE.write_text(
            json.dumps(current_counts(), ensure_ascii=False, indent=1, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {BASELINE}")
    else:
        print(json.dumps(current_counts(), ensure_ascii=False, indent=1, sort_keys=True))
