"""PLC 验收门“只拦新增失败”：按 DJ-2026-005 第 1 轮的真实形态做样件。

005 开工时插件命令行就有三条老问题：``check`` 报 05_公共报警 的数组路径错误（本单要修的），
``test`` 报 ``Test/basic_test.scltest:86`` 路径无效、``interlock_test`` 两条失败（本单范围外，不许改）。
插件只在用户本机有，这里用一个按文件内容出诊断的替身：``.scl`` 里写 ``// LSP-ERR: 说明``，
``.scltest`` 里写 ``// LSP-FAIL: 说明``，替身就在那一行报一条，和真插件一样带“文件:行:列”。
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from auto_pm.application.core import evidence_collection_service as ecs
from auto_pm.application.core.plc_baseline import export_plc_baseline
from auto_pm.domain.plc.baseline_compare import diff_failures, failure_keys
from auto_pm.domain.plc.language_service import LanguageServiceResult
from tests.core.test_plc_quality_gate import (
    BAD_SCL,
    PROJECT,
    _service,
    commit,
    git,
    plc_run,
    plc_workspace,
)

ST = f"{PROJECT}/02_PLC程序/PLC_ST"
ALARM = f"{ST}/05_公共报警/FB_2001_CommonAlarm.scl"
BASIC_TEST = f"{ST}/Test/basic_test.scltest"
INTERLOCK_TEST = f"{ST}/Test/interlock_test.scltest"
_MARK = re.compile(r"//\s*LSP-(ERR|FAIL):\s*(.+)$")


def fb(*marks: str) -> str:
    body = "".join(f"    ; // LSP-ERR: {mark}\n" for mark in marks)
    return (
        "// FB_2001 公共报警\nFUNCTION_BLOCK FB_2001_CommonAlarm\nVAR_INPUT\n    i_bReset : Bool;\n"
        f"END_VAR\nBEGIN\n    ;\n{body}END_FUNCTION_BLOCK\n"
    )


def scltest(*marks: str, pad: int = 0) -> str:
    return "// 单元测试\n" + "\n" * pad + "".join(f"// LSP-FAIL: {mark}\n" for mark in marks)


class FakeSiemensLsp:
    """按文件内容出诊断的插件替身（真插件只许在用户本机跑）。"""

    def __init__(self, incomplete: bool = False) -> None:
        self.incomplete = incomplete
        self.calls: list[tuple[str, Path]] = []

    @property
    def available(self) -> bool:
        return True

    def check(self, root: Path) -> LanguageServiceResult:
        return self._run("check", root, ".scl", "ERR", "error")

    def test(self, root: Path) -> LanguageServiceResult:
        return self._run("test", root, ".scltest", "FAIL", "FAIL")

    def _run(self, command: str, root: Path, suffix: str, kind: str, word: str) -> LanguageServiceResult:
        self.calls.append((command, root))
        if self.incomplete:
            return LanguageServiceResult(command, True, -1, 1, ("命令行未能完成: timeout",), "timeout", diagnostics=("命令行未能完成",))
        hits: list[str] = []
        for directory, _, files in sorted(os.walk(root)):
            for name in sorted(files):
                if not name.endswith(suffix):
                    continue
                path = Path(directory) / name
                relative = path.relative_to(root).as_posix()
                for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                    found = _MARK.search(line)
                    if found and found.group(1) == kind:
                        hits.append(f"./{relative}:{number}:5: {word}: {found.group(2)}")
        return LanguageServiceResult(
            command, True, 1 if hits else 0, len(hits), tuple(hits[:5]), hits[-1] if hits else "ok", diagnostics=tuple(hits)
        )


@pytest.fixture
def lsp(monkeypatch: pytest.MonkeyPatch) -> FakeSiemensLsp:
    fake = FakeSiemensLsp()
    monkeypatch.setattr(ecs, "_plc_language_service", lambda: fake)
    return fake


def dj005(tmp_path: Path) -> tuple[Path, Path, str]:
    """005 开工时的样子：三条插件老问题已经在基线上。"""

    workspace, candidate, _ = plc_workspace(tmp_path)
    files = {
        ALARM: fb("o_iMESAlarmQueue 不是数组", "o_iStationAlarmStatus 不是数组"),
        BASIC_TEST: scltest("GlobalVars.stExternal.i_bGlue 路径无效", pad=84),
        INTERLOCK_TEST: scltest("联锁用例 1 期望 TRUE 实际 FALSE", "联锁用例 2 期望 TRUE 实际 FALSE"),
    }
    for relative, text in files.items():
        target = candidate / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    commit(candidate, "DJ-2026-005 baseline with known plugin failures")
    return workspace, candidate, git(candidate, "rev-parse", "HEAD")


def gate(tmp_path: Path, alarm_text: str, *, extra: dict[str, str] | None = None, owned: tuple[str, ...] = (ALARM,)):
    workspace, candidate, baseline = dj005(tmp_path)
    (candidate / ALARM).write_text(alarm_text, encoding="utf-8")
    for relative, text in (extra or {}).items():
        (candidate / relative).write_text(text, encoding="utf-8")
    run = plc_run(candidate, baseline, owned)
    return _service(workspace).run_plc_checkpoint_quality_gates(run, candidate)


def test_b01_dj005_in_scope_fix_passes_while_out_of_scope_test_failures_stay_listed(
    tmp_path: Path, lsp: FakeSiemensLsp
) -> None:
    receipt = gate(tmp_path, fb())

    check = receipt.gates[0]
    assert receipt.status == "PASS", check.output_summary
    assert check.exit_code == 0
    first = check.output_summary.splitlines()[0]
    # 3 plugin failures + 2 "FB PRD 四件套" failures the sample block also had at the baseline
    assert "新增失败 0 条" in first and "基线已有失败 5 条" in first and "本单修好 2 条" in first
    assert "known | Siemens 语言服务 test · [.] ./02_PLC程序/PLC_ST/Test/basic_test.scltest:#: FAIL: GlobalVars.stExternal.i_bGlue 路径无效" in check.output_summary
    assert check.output_summary.count("known | Siemens 语言服务 test · ") == 3
    assert "fixed | Siemens 语言服务 check · " in check.output_summary
    # the plain project verdict is still recorded: this is "no new failures", not "all green"
    assert "fail | Siemens 语言服务 test" in check.output_summary
    # plugin ran on the candidate and on the baseline export, check and test each
    assert sorted(command for command, _ in lsp.calls) == ["check", "check", "test", "test"]


def test_b02_a_new_plugin_error_in_the_owned_block_is_blocked(tmp_path: Path, lsp: FakeSiemensLsp) -> None:
    receipt = gate(tmp_path, fb("i_bNewAlarm 未声明"))

    assert receipt.status == "FAIL"
    assert receipt.gates[0].exit_code == 1
    lines = receipt.gates[0].output_summary.splitlines()
    assert "新增失败 1 条" in lines[0]
    assert lines[1].startswith("new | Siemens 语言服务 check · ") and "i_bNewAlarm 未声明" in lines[1]


def test_b03_the_same_failure_occurring_more_often_is_blocked(tmp_path: Path, lsp: FakeSiemensLsp) -> None:
    # interlock_test is not owned, so put the extra occurrence where the Run may write: its own block
    receipt = gate(tmp_path, fb("o_iMESAlarmQueue 不是数组", "o_iMESAlarmQueue 不是数组", "o_iStationAlarmStatus 不是数组"))

    assert receipt.status == "FAIL"
    summary = receipt.gates[0].output_summary
    assert "新增失败 1 条" in summary and "基线已有失败 7 条" in summary
    assert "new | Siemens 语言服务 check · [.] ./02_PLC程序/PLC_ST/05_公共报警/FB_2001_CommonAlarm.scl:#: error: o_iMESAlarmQueue 不是数组" in summary


def test_b04_a_failure_that_only_moved_lines_is_still_the_known_one(tmp_path: Path, lsp: FakeSiemensLsp) -> None:
    owned = (ALARM, BASIC_TEST)
    receipt = gate(
        tmp_path,
        fb(),
        extra={BASIC_TEST: scltest("GlobalVars.stExternal.i_bGlue 路径无效", pad=88)},
        owned=owned,
    )

    assert receipt.status == "PASS", receipt.gates[0].output_summary
    assert "基线已有失败 5 条" in receipt.gates[0].output_summary


def test_b05_a_project_that_is_new_in_this_run_has_only_new_failures(tmp_path: Path, lsp: FakeSiemensLsp) -> None:
    workspace, candidate, baseline = plc_workspace(tmp_path)
    fresh = candidate / "0100_PLC" / "DJ-NEW-001"
    (fresh / "OB1").mkdir(parents=True)
    (fresh / ".plc.json").write_text('{"name": "DJ-NEW-001", "description": "n", "version": "V1"}', encoding="utf-8")
    (fresh / "OB1" / "OB1.scl").write_text(BAD_SCL, encoding="utf-8")
    run = plc_run(candidate, baseline, ("0100_PLC/DJ-NEW-001",))

    receipt = _service(workspace).run_plc_checkpoint_quality_gates(run, candidate)

    assert receipt.status == "FAIL"
    assert "开工基线上还没有这个工程" in receipt.gates[0].output_summary
    assert "基线已有失败 0 条" in receipt.gates[0].output_summary


def test_b06_a_plugin_run_that_did_not_finish_is_an_error_not_a_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeSiemensLsp(incomplete=True)
    monkeypatch.setattr(ecs, "_plc_language_service", lambda: fake)

    receipt = gate(tmp_path, fb())

    assert receipt.status == "FAIL"
    assert receipt.gates[0].exit_code is None
    assert "没有跑完" in receipt.gates[0].output_summary


def test_b07_owned_scl_lint_errors_already_there_pass_and_new_ones_block(tmp_path: Path) -> None:
    workspace, candidate, _ = plc_workspace(tmp_path)
    scl = candidate / PROJECT / "OB1" / "FB_Bad.scl"
    scl.write_text(BAD_SCL, encoding="utf-8")
    commit(candidate, "owned file already violates LSP-905")
    baseline = git(candidate, "rev-parse", "HEAD")
    owned = (f"{PROJECT}/OB1/FB_Bad.scl",)
    service = _service(workspace)

    scl.write_text("// 前面加一行注释，行号整体下移\n" + BAD_SCL, encoding="utf-8")
    kept = service.run_plc_checkpoint_quality_gates(plc_run(candidate, baseline, owned), candidate)
    assert kept.status == "PASS", [gate.output_summary for gate in kept.gates]
    assert "基线已有失败 1 条" in kept.gates[1].output_summary

    scl.write_text(BAD_SCL.replace("    Start : Bool;\n", "    Start : Bool;\n    Stop : Bool;\n"), encoding="utf-8")
    worse = service.run_plc_checkpoint_quality_gates(plc_run(candidate, baseline, owned), candidate)
    assert worse.status == "FAIL"
    assert worse.gates[1].exit_code == 1
    assert "new | OB1/FB_Bad.scl [" in worse.gates[1].output_summary


def test_b08_the_baseline_export_brings_shared_libraries_and_leaves_the_worktree_alone(tmp_path: Path) -> None:
    workspace, candidate, _ = plc_workspace(tmp_path)
    library = candidate / "0100_PLC" / "01_SharedLibraries" / "SysLib"
    library.mkdir(parents=True)
    (library / "FB_Timer.scl").write_text("// lib\n", encoding="utf-8")
    (candidate / PROJECT / ".plc.json").write_text(
        '{"name": "DJ-TEST-001", "description": "s", "version": "V1", "libraries": ["../01_SharedLibraries/SysLib"]}',
        encoding="utf-8",
    )
    commit(candidate, "project uses SysLib")
    head = git(candidate, "rev-parse", "HEAD")
    (candidate / PROJECT / "OB1" / "OB1.scl").write_text("// changed after start\n", encoding="utf-8")
    status_before = git(candidate, "status", "--porcelain")

    exported = export_plc_baseline(candidate, head, PROJECT, tmp_path / "base")

    assert exported == tmp_path / "base" / PROJECT
    assert (tmp_path / "base" / "0100_PLC" / "01_SharedLibraries" / "SysLib" / "FB_Timer.scl").is_file()
    assert "changed after start" not in (exported / "OB1" / "OB1.scl").read_text(encoding="utf-8")
    assert git(candidate, "status", "--porcelain") == status_before
    assert export_plc_baseline(candidate, head, "0100_PLC/NOPE", tmp_path / "none") is None


def test_b09_failure_keys_ignore_counts_and_count_repeats() -> None:
    from auto_pm.plc.models import CheckResult

    base = CheckResult(project_path="/p")
    base.add("PM_SESSION", "fail", "PM_SESSION 超过 300 行（312 行）")
    now = CheckResult(project_path="/p")
    now.add("PM_SESSION", "fail", "PM_SESSION 超过 300 行（330 行）")
    now.add("目录结构", "fail", "缺少 05_测试与验证")

    diff = diff_failures(failure_keys(now, "/p"), failure_keys(base, "/p"))

    assert diff.known == ("plc check · PM_SESSION：PM_SESSION 超过 # 行（# 行）",)
    assert diff.new == ("plc check · 目录结构：缺少 #_测试与验证",)
    assert not diff.passed


def test_b10_without_the_plugin_the_gate_still_compares_and_says_unverified(tmp_path: Path) -> None:
    receipt = gate(tmp_path, fb())

    assert receipt.status == "PASS"
    assert "warn | Siemens 语言服务 check | 未验证" in receipt.gates[0].output_summary


def test_b11_plc_check_baseline_reproduces_the_verdict_offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``plc check <ID> --baseline <提交号>``：用户不靠 AI、断网也能自己复现验收门的判定。"""
    import json

    from auto_pm.cli.__main__ import cli
    from click.testing import CliRunner

    import auto_pm.infrastructure.siemens_language_service as module
    from auto_pm.application.core.template_service import TemplateService

    templates = Path(__file__).resolve().parents[2] / "templates"
    root = tmp_path / "ws"
    project = root / "DJ-2026-901_测试机"
    TemplateService(str(templates)).copy_template(
        "plc-standard-project", str(project), {"project_id": "DJ-2026-901", "project_name": "测试机"}
    )
    inner = sorted(path.parent for path in project.rglob(".plc.json") if path.parent != project)
    st = inner[0] if inner else project
    (st / "Test").mkdir(parents=True, exist_ok=True)
    (st / "Test" / "basic_test.scltest").write_text(scltest("路径无效", pad=84), encoding="utf-8")
    git(root, "init")
    commit(root, "baseline")
    monkeypatch.setattr(module, "default_language_service", lambda: FakeSiemensLsp())

    def run(*flags: str):  # type: ignore[no-untyped-def]
        return CliRunner().invoke(
            cli, ["-w", str(root), "plc", "check", "DJ-2026-901", "--json", "--baseline", "HEAD", *flags], catch_exceptions=False
        )

    same = run()
    assert "{" in same.output, same.output
    data = json.loads(same.output[same.output.index("{"):])
    assert same.exit_code == 0, same.output
    assert any("basic_test.scltest:#: FAIL: 路径无效" in key for key in data["known"])
    assert data["new"] == []

    (st / "FB_New.scl").write_text(fb("新写的错"), encoding="utf-8")
    worse = run()
    data = json.loads(worse.output[worse.output.index("{"):])
    assert worse.exit_code == 1
    assert any("新写的错" in key for key in data["new"])


def test_b12_keys_match_the_plc_ci_rule_so_ci_and_acceptance_never_disagree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PLC 项目 CI（reviews/tools/plc_ci.py）和验收门用同一口径逐条比；这里锁住两边的键完全一样。"""
    import importlib.util
    import sys

    from auto_pm.plc.checker import PlcChecker

    repo = Path(__file__).resolve().parents[6]
    script = repo / "reviews" / "tools" / "plc_ci.py"
    if not script.is_file():
        pytest.skip("不在 WorkSpacePM 仓库里运行（发布副本没有 reviews/tools）")
    spec = importlib.util.spec_from_file_location("plc_ci_for_test", script)
    assert spec is not None and spec.loader is not None
    plc_ci = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, plc_ci)  # dataclasses look their module up here
    spec.loader.exec_module(plc_ci)

    _, candidate, _ = plc_workspace(tmp_path)
    (candidate / PROJECT / "OB1" / "OB2.scl").write_text(BAD_SCL, encoding="utf-8")
    (candidate / PROJECT / f"PM_SESSION_{Path(PROJECT).name}.md").unlink()
    project = candidate / PROJECT

    ours = failure_keys(PlcChecker(str(candidate)).check_project(str(project)), str(project))
    theirs = plc_ci.failure_keys(plc_ci.run_checks(repo, candidate, PROJECT))

    assert ours and ours == theirs
