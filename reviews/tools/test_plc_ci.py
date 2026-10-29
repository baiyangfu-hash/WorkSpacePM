"""plc_ci.py 自测：检查必须能失败（新问题判 FAIL），老问题判 PASS_KNOWN_BASELINE，跳过的层写明原因。

样件取本仓库真实的 DJ-2026-009、DJ-2026-011、SysLib（以及引用 SysLib 的 DJ-2026-000），复制进临时 Git 仓库，
在 PR 头上动手脚，再用本仓库的 SW-2026-008 源码当裁判跑 plc_ci.main()。

“基线上的老问题”一律由测试自己注入（每个样件项目里放一个故意缺 i_ 前缀的 FB_CiSample.scl），
不依赖真实项目眼下有没有失败——项目修好了，这些测试照样成立（D09 彩排第 4 轮发现的问题）。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plc_ci  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
PLC = REPO / plc_ci.PLC_TOP
D009 = f"{plc_ci.PLC_TOP}/DJ-2026-009_汇川换型改造"
D011 = f"{plc_ci.PLC_TOP}/DJ-2026-011_驾驶舱A6PLC续作验证套件"
D000 = f"{plc_ci.PLC_TOP}/DJ-2026-000"
SYSLIB = f"{plc_ci.PLC_TOP}/{plc_ci.SHARED}/SysLib"
# 注入的老问题：一个输入故意缺 i_ 前缀（SCL 规范 1 条失败）；放进 009、011、SysLib 的基线
SAMPLE_NAME = "FB_CiSample.scl"
SAMPLE_SCL = (
    'FUNCTION_BLOCK "FB_CiSample"\n'
    "VAR_INPUT\n"
    "    Enable : BOOL; // 样件：故意缺 i_ 前缀\n"
    "END_VAR\n"
    "BEGIN\n"
    "    ;\n"
    "END_FUNCTION_BLOCK\n"
)
SAMPLE_OK = SAMPLE_SCL.replace("    Enable : BOOL;", "    i_bEnable : BOOL;")
SAMPLE_DIR = "CI样件"


def sample_file(root: Path, project: str) -> Path:
    return root / project / SAMPLE_DIR / SAMPLE_NAME
SPEC = "00_Obsidian_Base全局规范文件仓库"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8").stdout.strip()


@pytest.fixture(scope="module")
def sample(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """临时仓库：真实样件 + 规范库，提交为基线。"""
    root = tmp_path_factory.mktemp("ws")
    for rel in (D009, D011, D000, SYSLIB, f"{plc_ci.PLC_TOP}/00_通用规范"):
        shutil.copytree(REPO / rel, root / rel)
    shutil.copytree(REPO / SPEC, root / SPEC)
    for project in (D009, D011, SYSLIB):
        path = sample_file(root, project)
        path.parent.mkdir(parents=True)
        path.write_text(SAMPLE_SCL, encoding="utf-8")
    # .scltest 也自己放一份，不依赖项目里现有的测试文件
    (root / D009 / SAMPLE_DIR / "ci_sample_test.scltest").write_text("// 样件\n", encoding="utf-8")
    # 检查代码也放进样件仓库：推到 main 的场景里裁判取自样件自己的提交
    shutil.copytree(REPO / plc_ci.SW008 / "auto_pm", root / plc_ci.SW008 / "auto_pm",
                    ignore=shutil.ignore_patterns("__pycache__"))
    git(root, "init", "-q", "-b", "main")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "base")
    return root


@pytest.fixture()
def pr(sample: Path, tmp_path: Path):
    """返回 (改动函数, 运行函数)：在样件的一个克隆上做 PR 头提交，基线放在另一个检出里。"""
    head = tmp_path / "head"
    base = tmp_path / "base"
    git(tmp_path, "clone", "-q", str(sample), str(head))
    git(tmp_path, "clone", "-q", str(sample), str(base))
    base_sha = git(head, "rev-parse", "HEAD")

    def run(capsys: pytest.CaptureFixture[str], *extra: str) -> tuple[int, str]:
        git(head, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
        git(head, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "head")
        code = plc_ci.main(["--base-root", str(base), "--head-root", str(head), "--judge-root", str(REPO),
                            "--base-sha", base_sha, "--head-sha", git(head, "rev-parse", "HEAD"), *extra])
        return code, capsys.readouterr().out

    return head, run


# ── 选项目 ────────────────────────────────────────────────


def test_owner_maps_paths_to_projects() -> None:
    assert plc_ci.owner(f"{D009}/02_PLC程序/x.scl") == D009
    assert plc_ci.owner(f"{SYSLIB}/timer/FB_TON.scl") == SYSLIB
    assert plc_ci.owner(f"{plc_ci.PLC_TOP}/00_通用规范/README.md") is None
    assert plc_ci.owner(f"{plc_ci.PLC_TOP}/_archive/DJ-2026-009/a.scl") is None
    assert plc_ci.owner("README.md") is None


def test_shared_library_change_also_checks_dependents(sample: Path) -> None:
    targets, _ = plc_ci.select(sample, sample, [f"{SYSLIB}/timer/FB_TON.scl"], False)
    rels = {t.rel: t.reason for t in targets}
    assert rels[SYSLIB] == "PR 改到"
    assert {D000, D009, D011} <= set(rels)
    assert "引用了改动的共享库" in rels[D009]


def test_non_project_dir_is_noted_not_silently_passed(sample: Path) -> None:
    targets, notes = plc_ci.select(sample, sample, [f"{plc_ci.PLC_TOP}/00_通用规范/README.md"], False)
    assert targets == []
    assert any("不是 PLC 项目目录" in n for n in notes)


def test_judge_change_checks_everything(sample: Path) -> None:
    targets, notes = plc_ci.select(sample, sample, ["reviews/tools/plc_ci.py"], False)
    assert {t.rel for t in targets} == {D000, D009, D011, SYSLIB}
    assert notes


# ── 真样件联调 ─────────────────────────────────────────────


def test_unchanged_known_failures_are_baseline_not_green(pr, capsys) -> None:
    head, run = pr
    (head / D011 / "PRD" / "备注.md").write_text("只改文档\n", encoding="utf-8")
    code, out = run(capsys)
    assert code == 0
    assert f"[PASS_KNOWN_BASELINE] {D011}" in out  # 注入的 FB_CiSample 是基线上就有的老问题
    assert f"{SAMPLE_DIR}/{SAMPLE_NAME}" in out and "新增失败" not in out


def test_new_scl_and_doc_problem_in_009_fails(pr, capsys) -> None:
    head, run = pr
    # 新加一个功能块，输入没有 i_ 前缀：SCL 规范多一条，必须判新增
    new = head / D009 / SAMPLE_DIR / "FB_CiNew.scl"
    new.write_text(SAMPLE_SCL.replace("FB_CiSample", "FB_CiNew").replace("Enable", "Foo"), encoding="utf-8")
    code, out = run(capsys)
    assert code == 1
    assert f"[FAIL] {D009}" in out
    assert f"新增失败：SCL 规范 · {SAMPLE_DIR}/FB_CiNew.scl [" in out and "'Foo'" in out
    assert f"      - SCL 规范 · {SAMPLE_DIR}/{SAMPLE_NAME}" in out  # 老问题照样列出，不被新问题盖掉


def test_one_more_of_an_existing_violation_kind_still_counts_as_new(pr, capsys) -> None:
    head, run = pr
    lib = sample_file(head, SYSLIB)
    text = lib.read_text(encoding="utf-8")
    # 注入的 Enable 本来就缺 i_ 前缀（基线老问题）；把这一行原样再写一遍，
    # 同一条违规从 1 条变 2 条，说明完全相同，只有数量增加，也必须判新增
    line = next(x for x in text.splitlines(keepends=True) if x.strip().startswith("Enable"))
    lib.write_text(text.replace(line, line + line, 1), encoding="utf-8")
    code, out = run(capsys)
    assert code == 1
    assert f"[FAIL] {SYSLIB}" in out
    assert f"新增失败：SCL 规范 · {SAMPLE_DIR}/{SAMPLE_NAME} [" in out and "'Enable'" in out
    assert f"{D009}（引用了改动的共享库 SysLib）" in out


def test_fixing_a_known_failure_removes_it(pr, capsys) -> None:
    head, run = pr
    sample_file(head, D011).write_text(SAMPLE_OK, encoding="utf-8")
    code, out = run(capsys)
    assert code == 0
    assert f"[FAIL] {D011}" not in out and "新增失败" not in out
    assert SAMPLE_NAME not in out  # 修好的老问题不再列出


def test_skipped_layers_are_spelled_out(pr, capsys) -> None:
    head, run = pr
    (head / D009 / "PRD" / "备注.md").write_text("x\n", encoding="utf-8")
    _, out = run(capsys)
    assert "SKIPPED：Siemens 语言服务插件 check/test 没跑" in out
    assert "SKIPPED：厂家软件编译没跑" in out and "InoProShop" in out
    assert ".scltest 仿真测试没跑" in out
    assert "SKIPPED（全局）：安全区规则检查" in out


def test_new_project_without_baseline_counts_every_failure(pr, capsys) -> None:
    head, run = pr
    shutil.copytree(head / D011, head / f"{plc_ci.PLC_TOP}/DJ-2026-099_新项目")  # 带着注入的 FB_CiSample
    code, out = run(capsys)
    assert code == 1
    assert "基线上没有这个项目" in out
    assert f"新增失败：SCL 规范 · {SAMPLE_DIR}/{SAMPLE_NAME}" in out


def test_no_compare_mode_fails_on_known_problems(pr, capsys) -> None:
    head, run = pr
    (head / D011 / "PRD" / "备注.md").write_text("x\n", encoding="utf-8")
    code, out = run(capsys, "--no-compare")
    assert code == 1
    assert f"[FAIL] {D011}" in out
    assert f"新增失败：SCL 规范 · {SAMPLE_DIR}/{SAMPLE_NAME}" in out


def test_broken_judge_is_a_failure_not_a_pass(pr, capsys, tmp_path: Path) -> None:
    head, _ = pr
    (head / D011 / "PRD" / "备注.md").write_text("x\n", encoding="utf-8")
    fake = tmp_path / "judge" / plc_ci.SW008 / "auto_pm"
    fake.mkdir(parents=True)
    (fake / "__init__.py").write_text("raise ImportError('坏裁判')\n", encoding="utf-8")
    git(head, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    git(head, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "head")
    code = plc_ci.main(["--base-root", str(tmp_path / "base"), "--head-root", str(head),
                        "--judge-root", str(tmp_path / "judge"), "--base-sha", "HEAD~1", "--head-sha", "HEAD"])
    out = capsys.readouterr().out
    assert code == 1
    assert "检查程序出错" in out and "坏裁判" in out


# ── 防明细漏展开（审计 79）────────────────────────────────


def _data(scl_status: str, scl: list, docs_status: str = "pass", docs: list | None = None) -> dict:
    return {"check": {"items": [{"item": "SCL 代码规范", "status": scl_status, "message": ""},
                                {"item": "文档一致性 [功能块 FB_X]", "status": docs_status, "message": ""}]},
            "docs": docs or [], "scl": scl}


def test_consistent_flags_scl_fail_without_details() -> None:
    assert "SCL 代码规范" in plc_ci.consistent(_data("fail", []))
    assert "SCL 代码规范" in plc_ci.consistent(_data("pass", [{"file": "a.scl", "rule": "R", "message": "m"}]))


def test_consistent_flags_docs_fail_without_details() -> None:
    assert "文档一致性" in plc_ci.consistent(_data("pass", [], "fail", [{"severity": "warn"}]))


def test_consistent_accepts_matching_details() -> None:
    assert plc_ci.consistent(_data("pass", [])) == ""
    assert plc_ci.consistent(_data("fail", [{"file": "a.scl", "rule": "R", "message": "m"}], "fail",
                                   [{"severity": "fail"}])) == ""


def test_mismatch_between_verdict_and_details_fails_the_project(monkeypatch, sample: Path) -> None:
    # plc check 判 SCL 失败，逐条明细却为空：不能因为没有可比对的键就判通过
    monkeypatch.setattr(plc_ci, "run_checks", lambda judge, ws, rel: _data("fail", []))
    out = plc_ci.evaluate(REPO, sample, sample, plc_ci.Target(D011, "测试"), compare=True)
    assert out.verdict == "FAIL"
    assert "不一致" in out.error


# ── Codex 评审两条 ─────────────────────────────────────────


def test_deleting_only_plc_json_is_a_failure(pr, capsys) -> None:
    head, run = pr
    (head / SYSLIB / ".plc.json").unlink()
    code, out = run(capsys)
    assert code == 1
    assert f"[FAIL] {SYSLIB}（{plc_ci.LOST_CONFIG}）" in out


def test_deleting_the_whole_project_is_only_noted(pr, capsys) -> None:
    head, run = pr
    shutil.rmtree(head / D011)
    code, out = run(capsys)
    assert code == 0
    assert "PR 里整个删掉了" in out


def _structural(message: str) -> dict:
    return {"check": {"items": [{"item": "目录唯一性与冲突排查", "status": "fail", "message": message}]},
            "docs": [], "scl": []}


def test_structural_item_compares_its_message_not_only_its_name() -> None:
    before = plc_ci.failure_keys(_structural("序号冲突: 01_A, 01_B"))
    after = plc_ci.failure_keys(_structural("序号冲突: 01_A, 01_B, 02_C, 02_D"))
    assert before != after  # 同一项里多了一处冲突，键必须不同，才会判新增


def test_structural_item_ignores_changing_numbers() -> None:
    assert plc_ci.failure_keys(_structural("PM_SESSION 189 行（阈值 150 行）")) == \
        plc_ci.failure_keys(_structural("PM_SESSION 201 行（阈值 150 行）"))


# ── 每个 PR 都跑 / 推到 main 时检查代码改了也查 ────────────────

LINTER = f"{plc_ci.SW008}/auto_pm/domain/plc/scl_linter.py"


def _commit(head: Path) -> None:
    git(head, "-c", "user.name=t", "-c", "user.email=t@t", "add", "-A")
    git(head, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "head")


def _scope(head: Path, base: Path, monkeypatch, tmp_path: Path, *extra: str) -> tuple[int, str]:
    out = tmp_path / "gh_output"
    out.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    _commit(head)
    code = plc_ci.main(["--base-root", str(base), "--head-root", str(head), "--base-sha", "HEAD~1",
                        "--head-sha", "HEAD", "--scope-only", *extra])
    return code, out.read_text(encoding="utf-8")


def test_scope_only_reports_not_applicable_for_a_non_plc_pr(pr, capsys, monkeypatch, tmp_path: Path) -> None:
    head, _ = pr
    (head / "README_其他.md").write_text("与 PLC 无关\n", encoding="utf-8")
    code, out = _scope(head, tmp_path / "base", monkeypatch, tmp_path)
    assert code == 0
    assert out == "applies=false\n"
    assert "不适用（N/A）" in capsys.readouterr().out


def test_scope_only_says_applies_for_a_plc_pr(pr, capsys, monkeypatch, tmp_path: Path) -> None:
    head, _ = pr
    (head / D011 / "PRD" / "备注.md").write_text("x\n", encoding="utf-8")
    code, out = _scope(head, tmp_path / "base", monkeypatch, tmp_path)
    assert code == 0
    assert out == "applies=true\n"
    assert D011 in capsys.readouterr().out


def test_full_run_on_a_non_plc_pr_says_not_applicable(pr, capsys) -> None:
    head, run = pr
    (head / "README_其他.md").write_text("x\n", encoding="utf-8")
    code, out = run(capsys)
    assert code == 0
    assert "不适用（N/A）" in out and "[PASS" not in out


def test_checker_change_on_a_pr_is_noted_but_not_judged(pr, capsys, monkeypatch, tmp_path: Path) -> None:
    head, _ = pr
    path = head / LINTER
    path.write_text(path.read_text(encoding="utf-8") + "\n# 改了一行\n", encoding="utf-8")
    _, out = _scope(head, tmp_path / "base", monkeypatch, tmp_path)
    assert out == "applies=false\n"
    assert "PLC 检查代码（SW-2026-008）有改动" in capsys.readouterr().out


def test_stricter_checker_pushed_to_main_is_caught(pr, capsys, tmp_path: Path) -> None:
    # 推到 main：检查代码换了一条规则的说法（相当于规则变了），推送前 vs 推送后整体比，SysLib 的结果变了必须报出来
    head, _ = pr
    path = head / LINTER
    text = path.read_text(encoding="utf-8")
    assert "缺失 'i_' 前缀" in text
    path.write_text(text.replace("缺失 'i_' 前缀", "缺失 'i_' 前缀（新规则）"), encoding="utf-8")
    _commit(head)
    code = plc_ci.main(["--base-root", str(tmp_path / "base"), "--head-root", str(head), "--base-sha", "HEAD~1",
                        "--head-sha", "HEAD", "--checker-from-head"])
    out = capsys.readouterr().out
    assert code == 1
    assert "PLC 检查代码（SW-2026-008）有改动：用新代码把所有 PLC 项目查一遍" in out
    assert f"[FAIL] {SYSLIB}（PLC 检查代码有改动）" in out
    assert f"新增失败：SCL 规范 · {SAMPLE_DIR}/{SAMPLE_NAME}" in out and "（新规则）" in out
    assert "检查代码取自PR 头检出（推到 main" in out


def test_judge_root_and_checker_from_head_are_exclusive(tmp_path: Path) -> None:
    assert plc_ci.main(["--base-root", str(tmp_path), "--head-root", str(tmp_path), "--judge-root", str(tmp_path),
                        "--checker-from-head", "--all"]) == 2


def test_workflow_and_script_agree_on_protocol_and_checker_paths() -> None:
    wf = (REPO / ".github" / "workflows" / "plc-ci.yml").read_text(encoding="utf-8")
    assert f'PLC_CI_PROTOCOL: "{plc_ci.PLC_CI_PROTOCOL}"' in wf
    for p in plc_ci.CHECKER_PATHS:
        assert f'"{p}**"' in wf if p.endswith("/") else f'"{p}"' in wf


def test_changing_only_the_self_test_still_applies(sample: Path) -> None:
    # 只改自测文件也要跑（否则自测被削弱也能以“不适用”合进去）——Codex 评审 #40
    targets, _ = plc_ci.select(sample, sample, ["reviews/tools/test_plc_ci.py"], False)
    assert targets


def test_every_judge_file_triggers_the_main_push() -> None:
    wf = (REPO / ".github" / "workflows" / "plc-ci.yml").read_text(encoding="utf-8")
    for path in plc_ci.JUDGE_FILES:
        assert f'- "{path}"' in wf


_LOADED = r"""
import contextlib, io, json, os, sys
sw008, workspace, project, child = sys.argv[1:5]
sys.argv = ["x", sw008, workspace, project]
with contextlib.redirect_stdout(io.StringIO()):
    exec(child)
root = os.path.abspath(os.path.join(sw008, "auto_pm"))
print(json.dumps(sorted({os.path.relpath(os.path.abspath(m.__file__), root).replace(os.sep, "/")
                         for m in list(sys.modules.values())
                         if getattr(m, "__file__", None) and os.path.abspath(m.__file__).startswith(root + os.sep)})))
"""


@pytest.mark.parametrize("project", [D009, D011, SYSLIB])
def test_checker_paths_cover_every_loaded_module(project: str) -> None:
    # 检查子进程真正加载了哪些 SW-2026-008 模块，每一个都必须在 CHECKER_PATHS 里（审计 82：漏了 vartable 等）
    proc = subprocess.run(
        [sys.executable, "-B", "-I", "-c", _LOADED, str(REPO / plc_ci.SW008), str(REPO), str(REPO / project), plc_ci._CHILD],
        capture_output=True, text=True, encoding="utf-8", check=True,
        env={**os.environ, "AUTO_PM_WORKSPACE": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"},
    )
    loaded = json.loads(proc.stdout.strip().splitlines()[-1])
    assert "domain/plc/checker.py" in loaded  # 确实跑到了检查代码
    missing = [rel for rel in loaded if not plc_ci.is_checker(f"{plc_ci.SW008}/auto_pm/{rel}")]
    assert missing == []


def test_vartable_parser_change_is_a_checker_change() -> None:
    assert plc_ci.is_checker(f"{plc_ci.SW008}/auto_pm/domain/vartable/parsers/scl_parser.py")
    assert not plc_ci.is_checker(f"{plc_ci.SW008}/auto_pm/ui/cli/project.py")


def test_scl_source_with_invalid_utf8_is_reported_not_swallowed(pr, capsys) -> None:
    head, run = pr
    bad = head / D009 / SAMPLE_DIR / "FB_CiBad.scl"
    bad.write_bytes(SAMPLE_SCL.replace("FB_CiSample", "FB_CiBad").encode("utf-8") + "// 中文\n".encode("gbk"))
    code, out = run(capsys)
    assert code == 1
    assert f"SCL 编码 · {SAMPLE_DIR}/FB_CiBad.scl：不是合法 UTF-8" in out
