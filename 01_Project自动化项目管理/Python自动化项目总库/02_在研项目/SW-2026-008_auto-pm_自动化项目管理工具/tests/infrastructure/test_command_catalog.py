"""《命令总目录》《报警代码表》的生成脚本跑得通、不漏行（WBS 8.11）。

两页由 ``scripts/command_catalog.py`` 生成。入库的两页允许落后于代码（页头写明生成于哪个提交），
“入库的页和代码一致”只在发版入库那张单上用 ``--check`` 核一次；这里只核：脚本跑得通，每条叶子命令和每个
scripts 下的脚本在生成结果里恰好一行，没有未分类，``--check`` 本身能认出落后，报警代码没有漏掉的新前缀。
“新命令没分类就报红”由 tests/core/test_cockpit_board_contracts.py 管。只读本项目目录里的文件。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

PROJECT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT / "scripts" / "command_catalog.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("command_catalog_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def catalog() -> ModuleType:
    return _load()


def _rows(page: str) -> list[str]:
    return [
        line.split("|")[1].strip().strip("`")
        for line in page.splitlines()
        if line.startswith("| `")
    ]


def test_the_script_runs_and_prints_both_pages(
    catalog: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert catalog.main(["--print"]) == 0
    out = capsys.readouterr().out
    assert "# 命令总目录" in out and "# 报警代码表" in out
    assert "本页可能落后" in out


def test_every_leaf_command_and_script_gets_exactly_one_row(catalog: ModuleType) -> None:
    page, _ = catalog.build_pages(None)
    rows = _rows(page)
    expected = sorted(catalog.leaf_commands()) + [row.path for row in catalog.script_rows()]
    assert sorted(rows) == sorted(expected)
    assert len(rows) == len(set(rows))
    assert "未分类" not in page, "有命令没在 commands_map.json 里分类"


@pytest.fixture()
def pages_in_tmp(
    catalog: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> ModuleType:
    """把两页写到临时目录（按当前代码生成），--check 对着它们比。"""
    catalog_page, codes_page = tmp_path / "003.md", tmp_path / "004.md"
    monkeypatch.setattr(catalog, "CATALOG_PAGE", catalog_page)
    monkeypatch.setattr(catalog, "CODES_PAGE", codes_page)
    first, second = catalog.build_pages(None, "aaaaaaaaaaaa")
    catalog_page.write_text(first, encoding="utf-8")
    codes_page.write_text(second, encoding="utf-8")
    return catalog


def test_check_ignores_the_base_commit_line_and_passes_on_current_pages(
    pages_in_tmp: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    assert pages_in_tmp.main(["--check"]) == 0, capsys.readouterr().out


def test_check_notices_a_new_command_script_or_code(
    pages_in_tmp: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    catalog = pages_in_tmp
    real_commands, real_scripts, real_codes = (
        catalog.leaf_commands,
        catalog.script_rows,
        catalog.code_rows,
    )

    monkeypatch.setattr(
        catalog, "leaf_commands", lambda: {**real_commands(), "zz brand-new": object()}
    )
    assert catalog.main(["--check"]) == 1
    assert "003.md" in capsys.readouterr().out
    monkeypatch.setattr(catalog, "leaf_commands", real_commands)

    monkeypatch.setattr(
        catalog,
        "script_rows",
        lambda: [*real_scripts(), catalog.ScriptRow("scripts/zz.py", "新脚本")],
    )
    assert catalog.main(["--check"]) == 1
    monkeypatch.setattr(catalog, "script_rows", real_scripts)

    monkeypatch.setattr(
        catalog,
        "code_rows",
        lambda: [*real_codes(), catalog.CodeRow("CHK-999", "`x.py`", "新代码")],
    )
    assert catalog.main(["--check"]) == 1
    assert "004.md" in capsys.readouterr().out


def test_code_scan_takes_emitted_codes_and_skips_mentions(
    catalog: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "auto_pm"
    source.mkdir()
    (source / "sample.py").write_text(
        '﻿"""文档字符串里提到 CHK-901 不算；文件带 BOM 也要读。"""\n'
        "# 注释里的 CHK-902 不算\n"
        "def run(add, name):\n"
        '    add("CHK-900", "ERROR", f"缺少 {name}")\n'
        '    add(check_id="SHC-900", severity="WARNING", message="规范漂移")\n'
        '    issues = [{"rule": "LINT-900/stale", "severity": "ERROR", "message": "路径过期"}]\n'
        '    note = "DEV-ENC-001 和 CHK-903 写在一句话里也不算"\n'
        '    add("XYZ-001", "新前缀")\n'
        "    return issues, note\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(catalog, "SOURCE_DIR", source)
    monkeypatch.setattr(catalog, "PROJECT_ROOT", tmp_path)

    found = catalog.emitted_codes()

    assert sorted(found) == ["CHK-900", "LINT-900", "SHC-900"]
    assert found["CHK-900"] == {"files": {"auto_pm/sample.py"}, "messages": {"缺少 …"}}
    assert found["SHC-900"]["messages"] == {"规范漂移"}
    assert found["LINT-900"]["messages"] == {"路径过期"}
    assert catalog.unlisted_code_shapes() == {"XYZ-001": {"auto_pm/sample.py"}}


def test_no_alarm_code_hides_behind_an_unlisted_prefix(catalog: ModuleType) -> None:
    assert catalog.unlisted_code_shapes() == {}, (
        "源码里有形状像报警代码、前缀却不在 CODE_PATTERN 里的值：是报警代码就把前缀加进 CODE_PATTERN，"
        "不是就写进 NOT_ALARM_CODES 并写明理由"
    )


def test_writing_flags_and_who_can_run_come_from_the_command_map(catalog: ModuleType) -> None:
    rows = {row.path: row for row in catalog.command_rows(None)}
    assert rows["worktree sweep"].writes == "不写；带 `--apply` 时写"
    assert rows["pm accept"].who == "只有用户本人"
    assert rows["pm orient"].who == "任何人" and rows["pm orient"].writes == "不写"
    assert rows["pm orient"].documented == "未查"
