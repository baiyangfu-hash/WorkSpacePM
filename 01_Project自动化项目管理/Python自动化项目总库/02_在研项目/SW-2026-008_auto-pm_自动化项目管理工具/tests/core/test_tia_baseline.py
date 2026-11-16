"""PLC 标准模板生成的程序，必须是用户在 TIA 里实测过的那一份（CHG-SCPT-2026-702）。

用户 2026-11-16：“测完的样例，竟然没有吸收，还靠着记忆来回回顾，浪费时间”。三工位样例 11-11 在 TIA V19
全部重建 0 错误，之后模板又改了公共报警块约 160 行（72fa94c8），没人发现、也没重测。

基准件在 ``tests/fixtures/tia_baseline/``：用户实测过的源文件原样存放，``manifest.json`` 记每个文件的
sha256、实测日期、TIA 版本、结果和证据。这里按 manifest 的参数真生成一遍模板，逐个 ``.scl``/``.db`` 比哈希：
和“已实测”一致的通过；登记在 ``pending``（待实测）的通过但必须写明原因；两样都不是就报红。
改了模板，要么撤回，要么出包请用户在 TIA 里重测，把结果记进 manifest（只记用户回传的结果）。
只读本项目 templates/ 和 tests/fixtures/，生成结果写在临时目录。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from auto_pm.application.core.template_service import TemplateService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = PROJECT_ROOT / "templates"
BASELINE_DIR = PROJECT_ROOT / "tests" / "fixtures" / "tia_baseline"
MANIFEST = BASELINE_DIR / "manifest.json"
PLC_ST = "02_PLC程序/PLC_ST"
SOURCE_SUFFIXES = {".scl", ".db"}
BOM = b"\xef\xbb\xbf"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return data


def _tested_by_template_path(manifest: dict[str, Any]) -> dict[str, set[str]]:
    tested: dict[str, set[str]] = {}
    for sample in manifest["samples"]:
        for entry in sample["files"]:
            if "template_path" in entry:
                tested.setdefault(entry["template_path"], set()).add(entry["sha256"])
    return tested


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """按 manifest 的参数真生成一遍模板，返回 {PLC_ST 下相对路径: 文件}。"""
    manifest = _manifest()
    dest = tmp_path_factory.mktemp("tia_baseline") / "project"
    TemplateService(str(TEMPLATES_DIR)).copy_template(
        manifest["template"], str(dest), dict(manifest["template_data"])
    )
    plc_st = dest / PLC_ST
    return {
        f"{PLC_ST}/{path.relative_to(plc_st).as_posix()}": path
        for path in sorted(plc_st.rglob("*"))
        if path.is_file() and path.suffix in SOURCE_SUFFIXES
    }


def test_baseline_files_match_the_manifest() -> None:
    """基准件目录里的文件和 manifest 一一对应，哈希不变：实测过的文件不许悄悄改。"""
    manifest = _manifest()
    problems: list[str] = []
    for sample in manifest["samples"]:
        assert (
            sample.get("实测日期")
            and sample.get("结果")
            and sample.get("证据")
            and sample.get("tia")
        ), sample["id"]
        root = BASELINE_DIR / sample["dir"]
        # 命中仓库忽略规则的文件（*.db）存成“原名.baseline”，stored_as 记存放名
        listed = {
            entry.get("stored_as", entry["package_path"]): entry["sha256"]
            for entry in sample["files"]
        }
        on_disk = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
        problems += [
            f"{sample['id']}：目录里有、manifest 没登记：{name}"
            for name in sorted(on_disk - set(listed))
        ]
        problems += [
            f"{sample['id']}：manifest 登记了、目录里没有：{name}"
            for name in sorted(set(listed) - on_disk)
        ]
        problems += [
            f"{sample['id']}：{name} 的哈希和 manifest 不一致"
            for name in sorted(on_disk & set(listed))
            if _sha256(root / name) != listed[name]
        ]
        # 用户的实测截图跟着基准件一起入库，下次不用翻聊天记录找
        for evidence in sample.get("evidence_files", []):
            path = BASELINE_DIR / evidence["path"]
            if not path.is_file():
                problems.append(f"{sample['id']}：证据文件不在：{evidence['path']}")
            elif _sha256(path) != evidence["sha256"]:
                problems.append(
                    f"{sample['id']}：证据文件哈希和 manifest 不一致：{evidence['path']}"
                )
    assert problems == []


def test_generated_plc_sources_are_tia_tested_or_pending(generated: dict[str, Path]) -> None:
    """模板生成的每个 .scl/.db 都要么和用户实测过的一字不差，要么登记成待实测。"""
    manifest = _manifest()
    tested = _tested_by_template_path(manifest)
    pending = {entry["template_path"]: entry["sha256"] for entry in manifest["pending"]}
    untested = [
        f"{rel}（sha256 {_sha256(path)[:12]}…）"
        for rel, path in generated.items()
        if _sha256(path) not in tested.get(rel, set()) and _sha256(path) != pending.get(rel)
    ]
    assert untested == [], (
        "模板生成的这些 PLC 源文件没在 TIA 里实测过：要么撤回模板改动，要么出包请用户在 TIA 里重测，"
        "测完把结果记进 tests/fixtures/tia_baseline/manifest.json（改之前可先登记到 pending 写明原因）：\n"
        + "\n".join(untested)
    )


def test_every_tested_file_is_still_generated(generated: dict[str, Path]) -> None:
    """用户定的结构、块名、文件夹不许悄悄变：实测过的每个文件，模板都还要在原位置生成出来。"""
    missing = sorted(set(_tested_by_template_path(_manifest())) - set(generated))
    assert missing == [], (
        f"实测过的这些文件模板不再生成（改名、挪文件夹或删了要先问用户）：{missing}"
    )


def test_pending_entries_are_current(generated: dict[str, Path]) -> None:
    """待实测清单只登记眼下真的待测的文件：写明原因和下一步，哈希就是现在生成的那份。"""
    tested = _tested_by_template_path(_manifest())
    stale: list[str] = []
    for entry in _manifest()["pending"]:
        rel = entry["template_path"]
        assert entry.get("原因") and entry.get("下一步"), rel
        if rel not in generated:
            stale.append(f"{rel}：模板已经不生成这个文件")
        elif _sha256(generated[rel]) != entry["sha256"]:
            stale.append(f"{rel}：模板又改了，待实测清单里的哈希过期")
        elif entry["sha256"] in tested.get(rel, set()):
            stale.append(f"{rel}：已经实测过，从待实测清单删掉")
    assert stale == []


def test_generated_sources_have_bom(generated: dict[str, Path]) -> None:
    """交给 TIA 导入的源文件一律 UTF-8 带 BOM（LSP-905 §4.10、LSP-906 规则 7.1）。"""
    assert [rel for rel, path in generated.items() if not path.read_bytes().startswith(BOM)] == []


CALL = re.compile(r'^\s*"(DB_[A-Za-z0-9_]+)"\s*\(', re.MULTILINE)
DATA_BLOCK = re.compile(r'^\s*DATA_BLOCK\s+"?([A-Za-z0-9_]+)"?', re.MULTILINE)


def test_each_fb_call_in_ob123_has_its_own_background_db(generated: dict[str, Path]) -> None:
    """外部源文件导入时背景 DB 要事先建好：OB 里同一 FB 调用几次就有几个背景 DB（LSP-905 §4.11 第 1 条）。"""
    ob = generated[f"{PLC_ST}/00_主程序/OB123.scl"].read_text(encoding="utf-8-sig")
    calls = CALL.findall(ob)
    declared = {
        name
        for path in generated.values()
        for name in DATA_BLOCK.findall(path.read_text(encoding="utf-8-sig"))
    }
    stations = _manifest()["template_data"]["station_instances"]
    assert len(calls) >= len(stations) + 2, calls  # 每个工位一次，加外部交互、公共报警
    assert len(calls) == len(set(calls)), f"同一个背景 DB 被调用了不止一次：{calls}"
    assert sorted(set(calls) - declared) == [], (
        f"OB123 调用的这些背景 DB 没有对应的 DB 源文件：{sorted(set(calls) - declared)}"
    )
