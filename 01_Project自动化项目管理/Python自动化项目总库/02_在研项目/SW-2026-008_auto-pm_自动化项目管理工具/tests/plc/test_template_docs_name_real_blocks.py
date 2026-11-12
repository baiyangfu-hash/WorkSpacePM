"""TD-SW008-501、509（D-236、D-244）：PLC 标准模板生成的文档只讲模板里真有的块和真有的路径。

以前模板带的接口、设计文档还是来源项目 005 的内容（输送机、取放料、DB1/OB1 目录），说明文件也还叫 IFC-OB1。
这里生成一个两工位项目，从生成的 .scl/.db 里读出真有的块，再逐行查文档：
文档里出现的块名、反引号里的路径、相对链接、《程序架构文档》目录树，都必须在生成结果里找得到。以后改模板时自动拦。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from auto_pm.application.core.template_service import TemplateService

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
PID = "DJ-2026-907"
TAG = "DJ2026907"
STATIONS = ["Station1", "Station2"]

_DECL = re.compile(r'^\s*(?:FUNCTION_BLOCK|FUNCTION|DATA_BLOCK|ORGANIZATION_BLOCK|TYPE)\s+"?([A-Za-z_]\w*)"?', re.MULTILINE)
_BLOCK_TOKEN = re.compile(r"(?<![A-Za-z0-9_])((?:FB|FC|DB|OB|ST|UDT)_?\d+[A-Za-z0-9_]*)")
_SHORT_FORM = re.compile(r"(FB|FC|DB|ST)_?(\d+)_?")
_PATH_TOKEN = re.compile(r'`([^`\s]*/[^`\s]*)`|"(02_PLC程序/[^"\s]+)"')
_LINK = re.compile(r"\]\((\.{1,2}/[^)\s]+)\)")
_TREE_ENTRY = re.compile(r"[├└]──\s+([^\s#]+)")
_DOC_SUFFIXES = (".md", ".yml", ".yaml", ".csv")


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    destination = tmp_path_factory.mktemp("docs") / PID
    TemplateService(str(TEMPLATES_DIR)).copy_template(
        "plc-standard-project", str(destination), {"project_id": PID, "project_name": "文档对块", "station_instances": STATIONS}
    )
    return destination


def _docs(project: Path) -> list[Path]:
    return sorted(p for p in (project / "02_PLC程序").rglob("*") if p.is_file() and p.suffix.lower() in _DOC_SUFFIXES)


def _lines(path: Path) -> list[tuple[int, str]]:
    return list(enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1))


def _declared_blocks(project: Path) -> set[str]:
    names: set[str] = set()
    for path in project.rglob("*"):
        if path.is_file() and path.suffix.lower() in (".scl", ".db", ".udt"):
            names |= set(_DECL.findall(path.read_text(encoding="utf-8-sig")))
    return names


def _is_real_block(token: str, declared: set[str], ob_files: set[str]) -> bool:
    untagged = {name.removesuffix(f"_{TAG}") for name in declared}
    if token in declared or token in untagged or token in ob_files:
        return True
    short = _SHORT_FORM.fullmatch(token)  # 文档里的简称：FB_2001、FB2001、DB_1001_<工位名>
    if short is None:
        return False
    return any(re.match(rf"{short[1]}_{short[2]}(_|$)", name) for name in untagged)


def test_the_generated_project_declares_the_template_blocks(project: Path) -> None:
    declared = _declared_blocks(project)
    assert {f"{TAG}_Main", f"GlobalVars_{TAG}", f"FB_1001_Station1_{TAG}", f"DB_1001_Station2_{TAG}"} <= declared


def test_every_block_name_in_the_documents_is_a_block_of_the_template(project: Path) -> None:
    declared = _declared_blocks(project)
    ob_files = {p.stem for p in project.rglob("OB*.scl")}
    stale = [
        f"{doc.relative_to(project).as_posix()}:{number} {token}"
        for doc in _docs(project)
        for number, line in _lines(doc)
        for token in _BLOCK_TOKEN.findall(line)
        if not _is_real_block(token, declared, ob_files)
    ]
    assert stale == []


def test_every_path_and_relative_link_in_the_documents_exists(project: Path) -> None:
    roots = [project, project / "02_PLC程序", project / "02_PLC程序" / "PLC_ST"]
    missing = []
    for doc in _docs(project):
        for number, line in _lines(doc):
            candidates = [a or b for a, b in _PATH_TOKEN.findall(line)] + _LINK.findall(line)
            for target in candidates:
                if "<" in target or "*" in target or "{" in target or target.startswith("http"):
                    continue  # 占位写法（<工位名>）不是具体路径
                bases = [doc.parent] if target.startswith(".") else [doc.parent, *roots]
                target = target.split("#", 1)[0]
                if not any((base / target.rstrip("/")).exists() for base in bases):
                    missing.append(f"{doc.relative_to(project).as_posix()}:{number} {target}")
    assert missing == []


def test_the_architecture_directory_tree_lists_only_folders_and_files_that_exist(project: Path) -> None:
    arc = project / "02_PLC程序" / "程序文档" / "程序架构文档_ARC.md"
    existing = {p.name for p in project.rglob("*")}
    text = arc.read_text(encoding="utf-8")
    section = text[text.index("## 6. 目录结构") : text.index("## 7.")]
    listed = [m for line in section.splitlines() for m in _TREE_ENTRY.findall(line)]
    assert listed and [name for name in listed if name.rstrip("/") not in existing] == []


def test_the_main_program_documents_are_named_after_ob123(project: Path) -> None:
    prd = project / "02_PLC程序" / "PLC_ST" / "00_主程序" / "PRD"
    assert sorted(p.name for p in prd.iterdir()) == ["变更记录_CHG-OB123.md", "接口文档_IFC-OB123.md", "详细设计说明书_DSN-OB123.md"]
    for station in STATIONS:
        assert f"DB_1001_{station}_{TAG}" in (prd / "接口文档_IFC-OB123.md").read_text(encoding="utf-8")


def test_program_blocks_yml_lists_real_blocks_at_real_paths(project: Path) -> None:
    data = yaml.safe_load((project / "02_PLC程序" / "工程资产" / "program_blocks.yml").read_text(encoding="utf-8"))
    declared = _declared_blocks(project)
    assert [b["name"] for b in data["blocks"] if b["name"] not in declared] == []
    assert [b["path"] for b in data["blocks"] if not (project / b["path"]).exists()] == []
