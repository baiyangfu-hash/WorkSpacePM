"""TD-SW008-573：“SCL 代码规范”不再只说“包含 N 个规范建议”，文字和 --json 都逐条列出“文件:行 说明”。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from click.testing import CliRunner

from auto_pm.domain.plc.checker import PlcChecker
from auto_pm.ui.cli.__main__ import cli

# 四个静态变量都缺 s_ 前缀（建议级），一个输入缺 i_ 前缀（错误级）
_WARN_ONLY = """FUNCTION_BLOCK "FB_9101_Demo"
VERSION : 0.1
   VAR
      a : Bool;
      b : Bool;
      c : Int;
      d : Int;
   END_VAR

BEGIN
   #a := #b;
   #c := #d;
END_FUNCTION_BLOCK
"""
_WITH_ERROR = _WARN_ONLY.replace("   VAR\n", "   VAR_INPUT\n      Start : Bool;\n   END_VAR\n   VAR\n", 1)


def _project(tmp_path: Path, body: str) -> Path:
    project = tmp_path / "DJ-2026-961_明细"
    (project / "02_PLC程序" / "PLC_ST" / "02_工位").mkdir(parents=True)
    (project / ".plc.json").write_text(json.dumps({"name": "DJ-2026-961", "version": "V1.0.0", "description": "x"}), encoding="utf-8")
    (project / "02_PLC程序" / "PLC_ST" / "02_工位" / "FB_9101_Demo.scl").write_text(body, encoding="utf-8")
    return project


def _scl_item(project: Path, tmp_path: Path):  # type: ignore[no-untyped-def]
    result = PlcChecker(str(tmp_path)).check_project(str(project))
    return next(i for i in result.items if i.item == "SCL 代码规范")


def test_d01_every_suggestion_is_listed_with_file_and_line(tmp_path: Path) -> None:
    item = _scl_item(_project(tmp_path, _WARN_ONLY), tmp_path)
    assert item.status == "warn" and "包含 4 个规范建议" in item.message
    rel = "02_PLC程序/PLC_ST/02_工位/FB_9101_Demo.scl"
    assert [line.split(" ", 1)[0] for line in item.details] == [f"{rel}:{n}" for n in (4, 5, 6, 7)]
    assert all("'s_'" in line for line in item.details)


def test_d02_a_failing_item_lists_all_errors_then_all_suggestions(tmp_path: Path) -> None:
    item = _scl_item(_project(tmp_path, _WITH_ERROR), tmp_path)
    assert item.status == "fail"
    assert len(item.details) == 5  # 1 个错误 + 4 个建议，不再只举前 3 条
    assert "'Start'" in item.details[0] and all(line.endswith("（建议）") for line in item.details[1:])


def _workspace(tmp_path: Path, body: str) -> Path:
    root = tmp_path / "ws"
    (root / "0100_PLC自动化").mkdir(parents=True)
    _project(root / "0100_PLC自动化", body)
    return root


def test_d03_json_carries_the_list(tmp_path: Path) -> None:
    root = _workspace(tmp_path, _WARN_ONLY)
    out = CliRunner().invoke(cli, ["-w", str(root), "plc", "check", "DJ-2026-961", "--json", "--no-language-service"], catch_exceptions=False)
    data = json.loads(out.output[out.output.index("{"):])
    item = next(i for i in data["items"] if i["item"] == "SCL 代码规范")
    assert len(item["details"]) == 4


def test_d04_text_output_prints_each_line_as_file_and_line(tmp_path: Path) -> None:
    root = _workspace(tmp_path, _WARN_ONLY)
    out = CliRunner().invoke(cli, ["-w", str(root), "plc", "check", "DJ-2026-961", "--no-language-service"], catch_exceptions=False)
    hits = re.findall(r"FB_9101_Demo\.scl:(\d+)", out.output)
    assert hits == ["4", "5", "6", "7"]
    assert "SCL代码规范（WARN）逐条4条" in "".join(out.output.split())  # rich 按宽度折行，去掉空白再比
