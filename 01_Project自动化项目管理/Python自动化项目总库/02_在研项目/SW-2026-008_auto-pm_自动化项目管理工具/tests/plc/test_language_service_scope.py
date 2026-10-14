"""插件的 PLC 范围与结果汇总（M3-PLUGIN）：标准项目有两层 .plc.json，命令行必须在程序源码所在的那一层运行。"""

from __future__ import annotations

from pathlib import Path

from auto_pm.domain.plc.language_service import (
    LanguageServiceBinary,
    LanguageServiceResult,
    evaluate_project,
    has_scltest,
    merge_results,
    plc_scope_roots,
)

BINARY = LanguageServiceBinary(path="x", version="2.17.2", sha256="0" * 64)


def _touch(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_sc01_a_standard_project_runs_in_the_inner_scope(tmp_path: Path) -> None:
    _touch(tmp_path / ".plc.json")
    inner = tmp_path / "02_PLC程序" / "PLC_ST"
    _touch(inner / ".plc.json")
    _touch(inner / "00_主程序" / "OB1.scl")
    assert plc_scope_roots(tmp_path) == [inner]


def test_sc02_a_single_marker_at_the_project_root_is_the_scope(tmp_path: Path) -> None:
    _touch(tmp_path / ".plc.json")
    _touch(tmp_path / "02_PLC程序" / "PLC_ST" / "OB1.scl")
    assert plc_scope_roots(tmp_path) == [tmp_path]


def test_sc03_independent_scopes_are_all_returned(tmp_path: Path) -> None:
    for name in ("A", "B"):
        _touch(tmp_path / name / ".plc.json")
        _touch(tmp_path / name / "src" / "FB.scl")
    assert plc_scope_roots(tmp_path) == [tmp_path / "A", tmp_path / "B"]


def test_sc04_archive_folders_and_markerless_trees_are_ignored(tmp_path: Path) -> None:
    _touch(tmp_path / "archive" / "old" / ".plc.json")
    _touch(tmp_path / "archive" / "old" / "OB1.scl")
    assert plc_scope_roots(tmp_path) == []
    _touch(tmp_path / ".plc.json")
    assert plc_scope_roots(tmp_path) == [tmp_path]  # a marker without sources still names the scope


def test_sc05_has_scltest_looks_below_the_scope_but_not_into_archives(tmp_path: Path) -> None:
    assert has_scltest(tmp_path) is False
    _touch(tmp_path / "archive" / "a.scltest")
    assert has_scltest(tmp_path) is False
    _touch(tmp_path / "Test" / "a.scltest")
    assert has_scltest(tmp_path) is True


def test_sc06_merged_results_keep_the_worst_exit_and_name_the_scope(tmp_path: Path) -> None:
    ok = LanguageServiceResult("check", True, 0, binary=BINARY)
    bad = LanguageServiceResult("check", True, 1, error_count=2, messages=("FB.scl:1:1: ERROR: x",), binary=BINARY)
    merged = merge_results("check", tmp_path, [(tmp_path / "A", ok), (tmp_path / "B", bad)])
    assert merged.exit_code == 1 and merged.error_count == 2 and not merged.passed
    assert merged.messages == ("[B] FB.scl:1:1: ERROR: x",)
    gone = LanguageServiceResult("check", False, None)
    assert merge_results("check", tmp_path, [(tmp_path / "A", ok), (tmp_path / "B", gone)]).available is False


def test_sc07_evaluate_project_runs_test_only_where_scltest_files_exist(tmp_path: Path) -> None:
    for name in ("A", "B"):
        _touch(tmp_path / name / ".plc.json")
        _touch(tmp_path / name / "FB.scl")
    _touch(tmp_path / "B" / "Test" / "a.scltest")
    calls: list[tuple[str, Path]] = []

    class Service:
        available = True

        def check(self, root: Path) -> LanguageServiceResult:
            calls.append(("check", root))
            return LanguageServiceResult("check", True, 0, binary=BINARY)

        def test(self, root: Path) -> LanguageServiceResult:
            calls.append(("test", root))
            return LanguageServiceResult("test", True, 0, binary=BINARY, cases_run=1, cases_total=1)

    report = evaluate_project(Service(), tmp_path)
    assert calls == [("check", tmp_path / "A"), ("check", tmp_path / "B"), ("test", tmp_path / "B")]
    assert report.check.passed and report.test is not None and report.test.cases_total == 1


def test_sc08_an_unavailable_service_is_reported_without_running_anything(tmp_path: Path) -> None:
    _touch(tmp_path / ".plc.json")

    class Gone:
        available = False

        def check(self, root: Path) -> LanguageServiceResult:  # pragma: no cover - must not be called
            raise AssertionError("check must not run when the plugin is missing")

        test = check

    report = evaluate_project(Gone(), tmp_path)
    assert report.check.available is False and report.test is None
