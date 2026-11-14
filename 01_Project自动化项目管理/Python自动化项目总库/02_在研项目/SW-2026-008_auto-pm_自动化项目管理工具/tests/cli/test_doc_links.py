"""TD-SW008-606（D-341）：`doc check --project <项目>` 查项目 .md 文档里的相对链接死链，报“文件:行”，跳过归档目录，只读。"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from auto_pm.application.core.template_service import TemplateService
from auto_pm.domain.doc.link_check import dead_links, links_of
from auto_pm.ui.cli.__main__ import cli

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
PID = "DJ-2026-965"

_DOC = """# 立项表

见 [需求说明](需求/需求说明.md#r1) 和 [图](<图纸/总图 1.png> "总图")，目录 [需求](需求/)。
坏的：[立项表](00_项目管理/立项表.md)，图 ![接线](图纸/接线.png)。
网址不查：[官网](https://example.com)、[信](mailto:a@b.c)、[本页](#上面)、[根](/abs/x.md)、[占位]({{ project_id }}.md)。
双链不查：[[立项表]]。行内代码不查：`[x](不存在.md)`。
编码过的路径：[空格](需求/需求%20说明.md)。

```markdown
[代码块里](不存在也不报.md)
```

[引用式]: 不存在的引用.md
[好的引用]: 需求/需求说明.md
"""


def _project(workspace: Path) -> Path:
    project = workspace / f"{PID}_链接"
    (project / "需求").mkdir(parents=True)
    (project / "图纸").mkdir()
    (project / ".copier-answers.yml").write_text(f"project_id: {PID}\nproject_name: 链接\nstack: plc\n", encoding="utf-8")
    (project / "需求" / "需求说明.md").write_text("# 需求\n", encoding="utf-8")
    (project / "需求" / "需求 说明.md").write_text("# 需求\n", encoding="utf-8")
    (project / "图纸" / "总图 1.png").write_bytes(b"")
    (project / "README.md").write_text(_DOC, encoding="utf-8")
    for skipped in ("_archive", "旧版归档", "Archive_Cold", ".git"):
        (project / skipped).mkdir()
        (project / skipped / "旧.md").write_text("[坏](不存在.md)\n", encoding="utf-8")
    return project


def _line(needle: str) -> int:
    return next(i for i, line in enumerate(_DOC.splitlines(), start=1) if needle in line)


def test_l01_only_relative_links_that_do_not_exist_are_reported_with_file_and_line(tmp_path: Path) -> None:
    report = dead_links(_project(tmp_path))
    assert [(d.file, d.line, d.target) for d in report.dead] == [
        ("README.md", _line("坏的"), "00_项目管理/立项表.md"),
        ("README.md", _line("坏的"), "图纸/接线.png"),
        ("README.md", _line("[引用式]"), "不存在的引用.md"),
    ]
    assert report.scanned == 3 and report.unreadable == [] and not report.passed


def test_l02_archive_hidden_and_underscore_folders_are_skipped(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "README.md").write_text("ok\n", encoding="utf-8")
    report = dead_links(project)
    assert report.passed and report.dead == []


def test_l03_a_gbk_document_is_still_checked_and_an_unreadable_one_is_reported(tmp_path: Path) -> None:
    project = _project(tmp_path)
    (project / "README.md").write_text("[坏](没有这份.md)\n[好](需求/需求说明.md)\n", encoding="gbk")
    (project / "坏编码.md").write_bytes(b"\xff\xfe\x00\xd8 [x](y.md)")
    report = dead_links(project)
    assert [(d.file, d.line, d.target) for d in report.dead] == [("README.md", 1, "没有这份.md")]
    assert report.unreadable == ["坏编码.md"] and not report.passed


def test_l04_code_and_unclosed_fences_hide_links() -> None:
    assert links_of("~~~\n[a](b.md)\n~~~\n[c](d.md)\n```\n[e](f.md)\n") == [(4, "d.md")]


def test_l05_the_command_prints_file_line_and_exits_1_and_touches_nothing(tmp_path: Path) -> None:
    project = _project(tmp_path)
    before = {p: p.read_bytes() for p in project.rglob("*") if p.is_file()}
    result = CliRunner().invoke(cli, ["-w", str(tmp_path), "doc", "check", "--project", PID])
    assert result.exit_code == 1, result.output
    assert f"README.md:{_line('坏的')} 链接找不到：00_项目管理/立项表.md" in result.output
    assert f"README.md:{_line('[引用式]')} 链接找不到：不存在的引用.md" in result.output
    assert "死链 3 处" in result.output
    assert "文档门禁检查报告" not in result.output and "doc sync" not in result.output  # 不跑驾驶舱自己的 DOC-001、DOC-004
    assert {p: p.read_bytes() for p in project.rglob("*") if p.is_file()} == before  # 只读


def test_l06_an_unknown_project_exits_1(tmp_path: Path) -> None:
    result = CliRunner().invoke(cli, ["-w", str(tmp_path), "doc", "check", "--project", "DJ-2026-999"])
    assert result.exit_code == 1 and "项目不存在" in result.output


def test_l07_a_new_template_project_passes(tmp_path: Path) -> None:
    project = tmp_path / PID
    TemplateService(str(TEMPLATES_DIR)).copy_template("plc-standard-project", str(project), {"project_id": PID, "project_name": "链接"})
    report = dead_links(project)
    assert report.scanned > 0
    assert [(d.file, d.line, d.target) for d in report.dead] == []
    assert report.unreadable == []
    result = CliRunner().invoke(cli, ["-w", str(tmp_path), "doc", "check", "--project", PID])
    assert result.exit_code == 0, result.output
    assert "相对链接都找得到" in result.output
