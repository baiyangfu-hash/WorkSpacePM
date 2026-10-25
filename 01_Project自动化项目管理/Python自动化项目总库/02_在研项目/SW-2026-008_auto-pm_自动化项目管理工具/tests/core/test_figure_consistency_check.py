"""图与文档一致性检查（scripts/figure_consistency_check.py）：一致的样例通过，故意做的不一致样例要报出具体行号。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import figure_consistency_check as fig  # noqa: E402

FLOW_OK = """# 流程图

```mermaid
graph TD
    S0([待机]) -->|bStart 触发| S1[夹紧 stClamp.bExtended]
    S1 -->|i_bSensor ON| S0
```
"""

INT_OK = """# 接口

| 变量名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `i_bSensor` | BOOL | 传感器 |
| `stClamp` | ST_Clamp | 夹紧结构体 |
"""

VAR_OK = """# 变量

| 名字 | 类型 |
|---|---|
| `bStart` | BOOL |
| `bExtended` | BOOL |
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_consistent_sample_passes(tmp_path: Path) -> None:
    flow, inter, var = (
        _write(tmp_path, "f.md", FLOW_OK),
        _write(tmp_path, "i.md", INT_OK),
        _write(tmp_path, "v.md", VAR_OK),
    )
    assert fig.check_documents([flow], [inter], [var]) == []
    assert (
        fig.main(["--diagram", str(flow), "--interface", str(inter), "--variables", str(var)]) == 0
    )


def test_signal_missing_from_tables_is_reported_with_line(tmp_path: Path) -> None:
    bad = FLOW_OK.replace("i_bSensor ON", "i_bGhost ON")
    flow = _write(tmp_path, "f.md", bad)
    findings = fig.check_documents(
        [flow], [_write(tmp_path, "i.md", INT_OK)], [_write(tmp_path, "v.md", VAR_OK)]
    )
    assert [(f.kind, f.line) for f in findings] == [("signal", 6)]
    assert "i_bGhost" in findings[0].message


def test_without_tables_signal_check_is_unverified_not_green(tmp_path: Path) -> None:
    flow = _write(tmp_path, "f.md", FLOW_OK)
    findings = fig.check_documents([flow], [], [])
    assert [f.kind for f in findings] == ["unverified"]
    assert fig.main(["--diagram", str(flow)]) == 1


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("graph TD\n    A[开始 --> B\n", "括号"),
        ("graph TD\n    A --> \n", "缺少节点"),
        ("flowgraph TD\n    A --> B\n", "未知的图类型"),
        ("graph TD\n    subgraph x\n    A --> B\n", "没有对应的 end"),
        ("graph TD\n    A --> B\n    end\n", "没有对应的 subgraph"),
        ('graph TD\n    A["开始 --> B\n', "引号"),
    ],
)
def test_unparsable_diagrams_are_reported(tmp_path: Path, body: str, expected: str) -> None:
    flow = _write(tmp_path, "f.md", f"# t\n\n```mermaid\n{body}```\n")
    findings = fig.check_documents([flow], [_write(tmp_path, "i.md", INT_OK)], [])
    parse = [f for f in findings if f.kind == "parse"]
    assert parse, findings
    assert expected in parse[0].message
    assert parse[0].line >= 4


def test_unclosed_fence_and_empty_block(tmp_path: Path) -> None:
    unclosed = _write(tmp_path, "u.md", "x\n```mermaid\ngraph TD\n    A --> B\n")
    assert any(
        "结束围栏" in f.message
        for f in fig.check_documents([unclosed], [_write(tmp_path, "i.md", INT_OK)], [])
    )
    empty = _write(tmp_path, "e.md", "x\n```mermaid\n```\n")
    assert any(
        "空的" in f.message
        for f in fig.check_documents([empty], [_write(tmp_path, "i2.md", INT_OK)], [])
    )


def test_document_without_diagram_is_reported(tmp_path: Path) -> None:
    flow = _write(tmp_path, "f.md", "# 只有文字\n")
    assert [
        f.message for f in fig.check_documents([flow], [_write(tmp_path, "i.md", INT_OK)], [])
    ] == ["文档里没有 mermaid 图"]


def test_json_output_and_usage_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    flow = _write(tmp_path, "f.md", FLOW_OK.replace("i_bSensor ON", "i_bGhost ON"))
    inter = _write(tmp_path, "i.md", INT_OK)
    assert fig.main(["--diagram", str(flow), "--interface", str(inter), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["kind"] == "signal"
    assert fig.main([]) == 2
    assert fig.main(["--diagram", str(tmp_path / "missing.md")]) == 2


def test_script_does_not_modify_inputs(tmp_path: Path) -> None:
    flow = _write(tmp_path, "f.md", FLOW_OK)
    before = flow.read_bytes()
    fig.main(["--diagram", str(flow)])
    assert flow.read_bytes() == before


def test_bracket_inside_quotes_is_not_an_unbalanced_bracket(tmp_path: Path) -> None:
    flow = _write(
        tmp_path,
        "f.md",
        '```mermaid\ngraph TD\n    A["a ( b"] --> B["c ] d"]\n```\n',
    )
    assert [f for block in fig.extract_blocks(flow) for f in fig.check_block(block)] == []


def test_io_prefixed_signal_is_checked_against_the_tables(tmp_path: Path) -> None:
    flow = _write(tmp_path, "f.md", "```mermaid\ngraph TD\n    A[io_Door 开] --> B[done]\n```\n")
    inter = _write(tmp_path, "i.md", "| 变量名 |\n|---|\n| `i_bSensor` |\n")
    var = _write(tmp_path, "v.md", "| 名字 |\n|---|\n| `bStart` |\n")
    findings = fig.check_documents([flow], [inter], [var])
    assert any("io_Door" in str(item) for item in findings)
