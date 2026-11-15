"""三个手写的 .copier-answers.yml 模板把字符串答案写成字符串（D-386）。

PLC 型号只填数字（如 1500）时，旧模板写出 ``plc_model: 1500``，YAML 读回来是整数，扫描器报
“字段 plc_model 的值无效”，驾驶舱就找不到这个项目。版本 ``1.0`` 读成小数、描述 ``yes`` 读成布尔，
是同一个毛病。这里用产品自己的 ``TemplateService`` 真生成一遍，读回答案文件，逐个核是字符串、和填的
一字不差；标准项目再让扫描器认一次。只读本项目 templates/ 下的模板，生成结果写在临时目录。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from auto_pm.application.core.project_scanner import ProjectScanner
from auto_pm.application.core.template_service import TemplateService

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"

# 每个值都是 YAML 不加引号时会读歪的写法：整数、小数、布尔、空值、带单引号、带冒号和井号
TRICKY = {
    "description": "yes",
    "version": "1.0",
    "business_line": "on",
    "equipment_type": "null",
    "plc_vendor": "O'Brien",
    "plc_model": "1500",
    "project_type": "single_machine: #2",
}

CASES = {
    "plc-standard-project": {
        "project_id": "DJ-2026-901",
        "project_name": "1500",
        **TRICKY,
    },
    "plc-test-suite": {
        "project_id": "DJ-2026-902",
        "project_name": "007",
        "description": "no",
        "version": "1.10",
        "business_line": "~",
    },
    "plc-shared-library": {
        "library_name": "SysLib",  # 校验只许大写字母开头，名字本身读不歪
        "description": "true",
        "version": "1.0",
        "business_line": "O'Brien: #1",
    },
}


def _render(template: str, data: dict[str, str], dest: Path) -> dict[str, object]:
    TemplateService(str(TEMPLATES_DIR)).copy_template(template, str(dest), data)
    text = (dest / ".copier-answers.yml").read_text(encoding="utf-8")
    loaded = yaml.safe_load(text)
    assert isinstance(loaded, dict), text
    return loaded


@pytest.mark.parametrize("template", sorted(CASES))
def test_string_answers_read_back_as_the_same_strings(template: str, tmp_path: Path) -> None:
    data = CASES[template]
    answers = _render(template, data, tmp_path / "out")

    for key, value in data.items():
        if key not in answers:
            continue  # 这个模板不记这一题
        assert answers[key] == value, (
            f"{template}: {key} 读回来是 {answers[key]!r}，填的是 {value!r}"
        )


def test_standard_project_with_a_digits_only_plc_model_is_found_by_the_scanner(
    tmp_path: Path,
) -> None:
    project = tmp_path / "DJ-2026-901_1500"
    _render("plc-standard-project", CASES["plc-standard-project"], project)

    info = ProjectScanner(str(tmp_path)).try_identify_project(str(project))

    assert info is not None
    assert info.project_id == "DJ-2026-901"
    assert info.plc_model == "1500"
    assert info.version == "1.0"
    assert info.description == "yes"


def test_unanswered_when_false_questions_still_read_back_as_empty_strings(tmp_path: Path) -> None:
    answers = _render(
        "plc-standard-project",
        {"project_id": "DJ-2026-903", "project_name": "边框缓存机"},
        tmp_path / "out",
    )

    for key in ("business_line", "equipment_type", "plc_vendor", "plc_model"):
        assert answers[key] == "", f"{key} 读回来是 {answers[key]!r}"
    assert answers["project_name"] == "边框缓存机"
    assert "\\u" not in (tmp_path / "out" / ".copier-answers.yml").read_text(encoding="utf-8")


def test_project_charter_front_matter_reads_back_as_the_same_strings(tmp_path: Path) -> None:
    """立项表头部是同一种写法（同类排查）：项目名 1500、版本 1.0 读回来也得是原样的字符串。"""
    data = CASES["plc-standard-project"]
    project = tmp_path / "out"
    _render("plc-standard-project", data, project)
    charter = project / "00_项目管理" / "01_立项与需求" / "003_DJ-2026-901_项目立项表_PROJ.md"
    text = charter.read_text(encoding="utf-8")
    front = yaml.safe_load(text.split("---", 2)[1])

    for key in ("project_id", "project_name", "project_type", "business_line", "version"):
        assert front[key] == data[key], f"{key} 读回来是 {front[key]!r}，填的是 {data[key]!r}"


# 一个值里同时带单引号、双引号、反斜杠、冒号加空格、井号：哪一种没转义好都读不回原样
HARD = 'O\'Brien "S7" C:\\PLC: #1'
# 有校验的题喂不进这种值（编号要合格式，库名只许字母数字）；标准项目的名称会进文件名，
# Windows 文件名不许带双引号、反斜杠、冒号，只喂单引号和井号
FREE_TEXT: dict[str, dict[str, Any]] = {
    "plc-standard-project": {
        "fixed": {"project_id": "DJ-2026-904", "project_name": "O'Brien #1"},
        "free": (
            "description",
            "version",
            "stack",
            "mode",
            "business_line",
            "project_type",
            "equipment_type",
            "plc_vendor",
            "plc_model",
        ),
    },
    "plc-test-suite": {
        "fixed": {"project_id": "DJ-2026-905"},
        "free": ("project_name", "description", "version", "stack", "mode", "business_line"),
    },
    "plc-shared-library": {
        "fixed": {"library_name": "SysLib"},
        "free": ("description", "version", "stack", "mode", "business_line"),
    },
}


@pytest.mark.parametrize("template", sorted(FREE_TEXT))
def test_every_free_text_answer_survives_quotes_backslashes_colons_and_hashes(
    template: str, tmp_path: Path
) -> None:
    case = FREE_TEXT[template]
    data: dict[str, str] = {**case["fixed"], **dict.fromkeys(case["free"], HARD)}
    answers = _render(template, data, tmp_path / "out")

    for key, value in data.items():
        assert answers[key] == value, f"{template}: {key} 读回来是 {answers[key]!r}"


def test_every_charter_front_matter_field_survives_the_hard_value(tmp_path: Path) -> None:
    data = {
        "project_id": "DJ-2026-906",
        "project_name": "O'Brien #1",
        "version": HARD,
        "business_line": HARD,
        "project_type": HARD,
    }
    project = tmp_path / "out"
    _render("plc-standard-project", data, project)
    charter = project / "00_项目管理" / "01_立项与需求" / "003_DJ-2026-906_项目立项表_PROJ.md"
    front = yaml.safe_load(charter.read_text(encoding="utf-8").split("---", 2)[1])

    for key, value in data.items():
        assert front[key] == value, f"{key} 读回来是 {front[key]!r}"
