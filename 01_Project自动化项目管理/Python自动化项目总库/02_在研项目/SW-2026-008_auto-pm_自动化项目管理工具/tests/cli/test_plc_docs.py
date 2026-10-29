"""plc docs CLI: exit codes, JSON output, dry-run, sync and confirm on real files (V01B)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from auto_pm.domain.plc import doc_consistency as dc
from auto_pm.ui.cli.__main__ import cli
from tests.identity_support import guard_off
from tests.plc.test_doc_consistency import FB_SCL, IFC_DOC, VAR_DOC, build, ifc_path, var_path


@pytest.fixture(autouse=True)
def _identity_guard_off(monkeypatch: pytest.MonkeyPatch) -> None:
    guard_off(monkeypatch, "plc.docs")


def project_in_workspace(workspace: Path, *, ifc: str | None = IFC_DOC, var: str | None = VAR_DOC) -> Path:
    """A project whose directory name carries the id, so ``plc docs <ID>`` can resolve it."""

    staging = workspace / "_staging"
    built = build(staging, ifc=ifc, var=var)
    target = workspace / "DJ-2026-DOCS_文档核对"
    built.rename(target)
    (target / ".plc.json").write_text(
        json.dumps({"name": "DJ-2026-DOCS", "version": "V1.0.0", "description": "docs"}), encoding="utf-8")
    staging.rmdir()
    return target


def invoke(workspace: Path, *args: str) -> tuple[int, str]:
    result = CliRunner(env={}).invoke(cli, ["-w", str(workspace), "plc", "docs", *args], catch_exceptions=False)
    return result.exit_code, result.output


def test_k01_check_exits_zero_for_a_consistent_project(tmp_path: Path) -> None:
    project_in_workspace(tmp_path)
    code, output = invoke(tmp_path, "check", "DJ-2026-DOCS")
    assert code == 0 and "拦住项 0" in output


def test_k02_check_exits_one_and_names_the_variable_and_both_locations(tmp_path: Path) -> None:
    project = project_in_workspace(tmp_path, ifc=IFC_DOC.replace("| `i_bStart` | BOOL |", "| `i_bStart` | INT |"))
    code, output = invoke(tmp_path, "check", "DJ-2026-DOCS")
    assert code == 1
    assert "FB_Pump.i_bStart" in output and ".scl:" in output and ".md:" in output
    assert "plc docs sync" in output
    assert ifc_path(project).exists()


def test_k03_check_json_is_machine_readable_and_carries_the_same_verdict(tmp_path: Path) -> None:
    project_in_workspace(tmp_path, ifc=IFC_DOC.replace("启动命令", "起动命令"))
    code, output = invoke(tmp_path, "check", "DJ-2026-DOCS", "--json")
    payload = json.loads(output)
    assert code == 1 and payload["schema_version"] == "plc-docs-check.v1"
    assert [f["kind"] for f in payload["findings"]] == ["comment"]
    assert {o["name"]: o["status"] for o in payload["objects"]}["FB_Pump"] == "fail"


def test_k04_strict_markers_fails_only_while_confirmation_markers_remain(tmp_path: Path) -> None:
    project = project_in_workspace(tmp_path, ifc=None, var=None)
    assert invoke(tmp_path, "check", "DJ-2026-DOCS")[0] == 0
    assert invoke(tmp_path, "sync", "DJ-2026-DOCS")[0] == 0
    assert invoke(tmp_path, "check", "DJ-2026-DOCS")[0] == 0
    code, output = invoke(tmp_path, "check", "DJ-2026-DOCS", "--strict-markers")
    assert code == 1 and "待确认" in output
    assert dc.MARKER in ifc_path(project).read_text(encoding="utf-8")
    assert invoke(tmp_path, "confirm", "DJ-2026-DOCS")[0] == 0
    assert invoke(tmp_path, "check", "DJ-2026-DOCS", "--strict-markers")[0] == 0


def test_k05_sync_dry_run_writes_nothing_and_sync_writes_documents_but_never_code(tmp_path: Path) -> None:
    project = project_in_workspace(tmp_path, ifc=None, var=None)
    before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    code, output = invoke(tmp_path, "sync", "DJ-2026-DOCS", "--dry-run")
    assert code == 0 and "预览" in output
    assert {p: p.read_bytes() for p in project.rglob("*") if p.is_file()} == before

    code, output = invoke(tmp_path, "sync", "DJ-2026-DOCS")
    assert code == 0 and "新建文档 2 份" in output
    assert ifc_path(project).exists() and var_path(project).exists()
    after = {p: p.read_bytes() for p in project.rglob("*") if p.is_file() and p.suffix in {".scl", ".db"}}
    assert after == {p: v for p, v in before.items() if p.suffix in {".scl", ".db"}}


def test_k06_sync_apply_suggestions_reports_what_it_still_needs_you_to_decide(tmp_path: Path) -> None:
    project = project_in_workspace(tmp_path, ifc=IFC_DOC.replace("启动命令", "起动命令"))
    code, output = invoke(tmp_path, "sync", "DJ-2026-DOCS")
    assert code == 0 and "还有 1 处需要人工处理" in output
    assert "起动命令" in ifc_path(project).read_text(encoding="utf-8")
    code, output = invoke(tmp_path, "sync", "DJ-2026-DOCS", "--apply-suggestions")
    assert code == 0 and "按建议改动 1 处" in output
    assert "起动命令" not in ifc_path(project).read_text(encoding="utf-8")
    assert invoke(tmp_path, "check", "DJ-2026-DOCS")[0] == 0


def test_k07_confirm_keeps_the_marker_on_rows_that_still_disagree_with_the_code(tmp_path: Path) -> None:
    project = project_in_workspace(tmp_path, ifc=None, var=None)
    invoke(tmp_path, "sync", "DJ-2026-DOCS")
    doc = ifc_path(project)
    doc.write_text(doc.read_text(encoding="utf-8").replace(f"| BOOL | {dc.MARKER}运行中", f"| INT | {dc.MARKER}运行中"),
                   encoding="utf-8")
    code, output = invoke(tmp_path, "confirm", "DJ-2026-DOCS")
    assert code == 0 and "未确认" in output
    assert f"| INT | {dc.MARKER}运行中" in doc.read_text(encoding="utf-8")


def test_k08_project_path_option_works_without_a_workspace_project_and_usage_errors_exit_two(tmp_path: Path) -> None:
    project = build(tmp_path / "iso", scl=FB_SCL)
    code, output = invoke(tmp_path, "check", "--project-path", str(project))
    assert code == 0 and "拦住项 0" in output
    assert invoke(tmp_path, "check")[0] == 2
    assert invoke(tmp_path, "check", "NOT-EXIST")[0] == 1


def test_k09_milestone_table_new_project_blocks_and_migrated_project_only_warns(tmp_path: Path) -> None:
    from tests.plc.test_milestones import FILLED, write

    project = project_in_workspace(tmp_path)
    code, output = invoke(tmp_path, "check", "DJ-2026-DOCS")
    assert code == 0 and "里程碑表：拦住项 0、提示 1" in output and "没有里程碑表" in output

    write(project, FILLED.format(origin="新项目").replace("| 仿真 | 2026-11-15 |", "| 仿真 | |"))
    code, output = invoke(tmp_path, "check", "DJ-2026-DOCS")
    assert code == 1 and "拦住项 0、" in output and "里程碑表：拦住项 1" in output
    assert "里程碑表.仿真：计划日期没填" in output and "_里程碑表.md:" in output

    write(project, FILLED.format(origin="老项目迁入").replace("| 仿真 | 2026-11-15 |", "| 仿真 | |"))
    code, output = invoke(tmp_path, "check", "DJ-2026-DOCS")
    assert code == 0 and "里程碑表：拦住项 0、提示 1" in output and "warn: 里程碑表.仿真" in output


def test_k10_milestones_are_in_the_json_output(tmp_path: Path) -> None:
    from tests.plc.test_milestones import FILLED, write

    project = project_in_workspace(tmp_path)
    write(project, FILLED.format(origin="新项目"))
    code, output = invoke(tmp_path, "check", "DJ-2026-DOCS", "--json")
    block = json.loads(output)["milestones"]
    assert code == 0 and block["origin"] == "新项目" and block["findings"] == []
    assert [(r["stage"], r["planned"], r["status"]) for r in block["rows"]][:2] == [
        ("需求", "2026-10-01", "已完成"), ("设计", "2026-10-20", "进行中")]
