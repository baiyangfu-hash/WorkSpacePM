"""plc_ci.py 自测：检查必须能失败（新问题判 FAIL），老问题判 PASS_KNOWN_BASELINE，跳过的层写明原因。

样件取本仓库真实的 DJ-2026-009、DJ-2026-011、SysLib（以及引用 SysLib 的 DJ-2026-000），复制进临时 Git 仓库，
在 PR 头上动手脚，再用本仓库的 SW-2026-008 源码当裁判跑 plc_ci.main()。
"""

from __future__ import annotations

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
FB3001 = f"{D009}/02_PLC程序/PLC_ST/01_外部设备交互/FB_3001_ExternalInteraction.scl"
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
    assert f"[PASS_KNOWN_BASELINE] {D011}" in out  # OB1.scl 没有程序块，是基线上就有的老问题
    assert "OB1/OB1.scl" in out and "新增失败" not in out


def test_new_scl_and_doc_problem_in_009_fails(pr, capsys) -> None:
    head, run = pr
    path = head / FB3001
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("VAR_INPUT\n", "VAR_INPUT\n    Foo : BOOL; // 没有 i_ 前缀\n", 1), encoding="utf-8")
    code, out = run(capsys)
    assert code == 1
    assert f"[FAIL] {D009}" in out
    assert "新增失败：SCL 规范 · 02_PLC程序/PLC_ST/01_外部设备交互/FB_3001_ExternalInteraction.scl" in out
    assert "新增失败：plc docs check · FB_3001_ExternalInteraction.Foo" in out
    assert "基线已有的失败" in out  # 老问题照样列出，不被新问题盖掉


def test_one_more_of_an_existing_violation_kind_still_counts_as_new(pr, capsys) -> None:
    head, run = pr
    lib = head / SYSLIB / "log" / "FC_LogMsg.scl"
    text = lib.read_text(encoding="utf-8")
    # FC_LogMsg 的输入 Enable 本来就缺 i_ 前缀（基线 66 条之一）；把这一行原样再写一遍，
    # 同一条违规从 1 条变 2 条，说明完全相同，只有数量增加，也必须判新增
    line = next(x for x in text.splitlines(keepends=True) if x.strip().startswith("Enable"))
    lib.write_text(text.replace(line, line + line, 1), encoding="utf-8")
    code, out = run(capsys)
    assert code == 1
    assert f"[FAIL] {SYSLIB}" in out
    assert "新增失败：SCL 规范 · log/FC_LogMsg.scl [" in out and "'Enable'" in out
    assert f"{D009}（引用了改动的共享库 SysLib）" in out


def test_fixing_the_known_failure_turns_011_green(pr, capsys) -> None:
    head, run = pr
    (head / D011 / "OB1" / "OB1.scl").write_text(
        'ORGANIZATION_BLOCK "OB1"\nBEGIN\n    ;\nEND_ORGANIZATION_BLOCK\n', encoding="utf-8")
    code, out = run(capsys)
    assert code == 0
    assert f"[PASS] {D011}" in out


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
    shutil.copytree(head / D011, head / f"{plc_ci.PLC_TOP}/DJ-2026-099_新项目")
    code, out = run(capsys)
    assert code == 1
    assert "基线上没有这个项目" in out


def test_no_compare_mode_fails_on_known_problems(pr, capsys) -> None:
    head, run = pr
    (head / D011 / "PRD" / "备注.md").write_text("x\n", encoding="utf-8")
    code, out = run(capsys, "--no-compare")
    assert code == 1
    assert f"[FAIL] {D011}" in out


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
