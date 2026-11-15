"""TemplateService 单元测试"""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_pm.application.core.template_service import (
    TemplateService,
    TemplateUpdateUnavailableError,
)


class TestListTemplates:
    """模板列表测试"""

    def test_list_templates_empty_dir(self, tmp_path: Path) -> None:
        """空目录返回空列表"""
        svc = TemplateService(str(tmp_path))
        assert svc.list_templates() == []

    def test_list_templates_nonexistent_dir(self, tmp_path: Path) -> None:
        """不存在的目录返回空列表"""
        svc = TemplateService(str(tmp_path / "nonexistent"))
        assert svc.list_templates() == []

    def test_list_templates_with_valid_template(self, tmp_path: Path) -> None:
        """有 copier.yml 的子目录被识别为模板"""
        tpl_dir = tmp_path / "plc-standard"
        tpl_dir.mkdir()
        (tpl_dir / "copier.yml").write_text("project_id: test\n", encoding="utf-8")

        svc = TemplateService(str(tmp_path))
        templates = svc.list_templates()

        assert "plc-standard" in templates

    def test_list_templates_ignores_files(self, tmp_path: Path) -> None:
        """非目录文件被忽略"""
        (tmp_path / "readme.txt").write_text("not a template\n", encoding="utf-8")

        svc = TemplateService(str(tmp_path))
        templates = svc.list_templates()

        assert "readme.txt" not in templates

    def test_list_templates_ignores_no_copier_yml(self, tmp_path: Path) -> None:
        """无 copier.yml 的子目录被忽略"""
        no_yml_dir = tmp_path / "no-copier"
        no_yml_dir.mkdir()

        svc = TemplateService(str(tmp_path))
        templates = svc.list_templates()

        assert "no-copier" not in templates


class TestGetTemplatePath:
    """模板路径查询测试"""

    def test_get_template_path_exists(self, tmp_path: Path) -> None:
        """存在的模板返回路径"""
        tpl_dir = tmp_path / "plc-standard"
        tpl_dir.mkdir()
        (tpl_dir / "copier.yml").write_text("project_id: test\n", encoding="utf-8")

        svc = TemplateService(str(tmp_path))
        path = svc.get_template_path("plc-standard")

        assert path == str(tpl_dir)

    def test_get_template_path_not_found(self, tmp_path: Path) -> None:
        """不存在的模板抛出 FileNotFoundError"""
        svc = TemplateService(str(tmp_path))

        with pytest.raises(FileNotFoundError, match="模板不存在"):
            svc.get_template_path("nonexistent")

    def test_get_template_path_no_copier_yml(self, tmp_path: Path) -> None:
        """目录存在但无 copier.yml 抛出 FileNotFoundError"""
        tpl_dir = tmp_path / "no-copier"
        tpl_dir.mkdir()

        svc = TemplateService(str(tmp_path))

        with pytest.raises(FileNotFoundError, match="模板不存在"):
            svc.get_template_path("no-copier")


class TestCopyTemplate:
    """模板复制测试"""

    def test_copy_template_not_found(self, tmp_path: Path) -> None:
        """模板不存在时抛出 FileNotFoundError"""
        svc = TemplateService(str(tmp_path))
        dest = str(tmp_path / "dest")

        with pytest.raises(FileNotFoundError, match="模板不存在"):
            svc.copy_template("nonexistent", dest, {"project_id": "TEST"})

    def test_copy_template_dest_exists(self, tmp_path: Path) -> None:
        """目标路径已存在时抛出 FileExistsError"""
        tpl_dir = tmp_path / "plc-standard"
        tpl_dir.mkdir()
        (tpl_dir / "copier.yml").write_text("project_id: test\n", encoding="utf-8")

        dest = tmp_path / "dest"
        dest.mkdir()

        svc = TemplateService(str(tmp_path))

        with pytest.raises(FileExistsError, match="目标路径已存在"):
            svc.copy_template("plc-standard", str(dest), {"project_id": "TEST"})


class TestUpdateTemplate:
    """模板更新测试"""

    def test_update_template_no_answers(self, tmp_path: Path) -> None:
        """缺少 .copier-answers.yml 时抛出 FileNotFoundError"""
        svc = TemplateService(str(tmp_path))

        with pytest.raises(FileNotFoundError, match="缺少 .copier-answers.yml"):
            svc.update_template(str(tmp_path))

    def test_update_template_without_a_station_list_passes_no_stations(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TD-SW008-525：老工程答案文件里没有工位清单，就不传，不回填（D-376 起：先过“跑得起来”的检查）。"""
        import copier

        (tmp_path / ".copier-answers.yml").write_text("project_id: DJ-2026-005\nstack: plc\n", encoding="utf-8")
        seen: dict[str, object] = {}
        monkeypatch.setattr(copier, "run_update", lambda **kwargs: seen.update(kwargs))
        monkeypatch.setattr(TemplateService, "_update_blocker", lambda self, answers: "")
        TemplateService(str(tmp_path)).update_template(str(tmp_path), overwrite=True)
        assert seen["data"] == {}

# ── D-343 / D-376：真跑 copier，不换假的 ────────────────────────────────────

_OWN_TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
_PLC_ANSWERS = {
    "project_id": "DJ-2026-098",
    "project_name": "更新测",
    "business_line": "DJ",
    "project_type": "single_machine",
    "equipment_type": "conveyor",
    "plc_vendor": "Siemens",
    "plc_model": "1500",
    "station_instances": ["StationA", "StationB"],
}


def _git(cwd: Path, *args: str) -> str:
    import os
    import subprocess

    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}
    done = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, check=True, env=env)
    return done.stdout.decode("utf-8").strip()


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file() and ".git" not in p.parts}


def _git_template(tmp_path: Path) -> tuple[Path, str]:
    """把驾驶舱自带的 plc-standard-project 拷进一个独立 Git 仓库（copier 只能从这种模板增量更新）。"""
    import shutil

    root = tmp_path / "tpl"
    shutil.copytree(_OWN_TEMPLATES / "plc-standard-project", root / "plc-standard-project")
    template = root / "plc-standard-project"
    _git(template, "init", "-q")
    _git(template, "add", "-A")
    _git(template, "commit", "-qm", "t")
    return root, _git(template, "rev-parse", "HEAD")


class TestUpdateTemplateWithRealCopier:
    """D-343（TD-SW008-608）与 D-376（TD-SW008-641）：真跑 copier。"""

    def test_answers_without_template_source_refuse_in_chinese_and_touch_nothing(self, tmp_path: Path) -> None:
        """驾驶舱生成的答案文件不记 _src_path/_commit：说中文真话、退出，项目一个字节不动。"""
        project = tmp_path / "DJ-2026-098"
        TemplateService(str(_OWN_TEMPLATES)).copy_template("plc-standard-project", str(project), dict(_PLC_ANSWERS))
        _git(project, "init", "-q")
        _git(project, "add", "-A")
        _git(project, "commit", "-qm", "i")
        before = _snapshot(project)
        with pytest.raises(TemplateUpdateUnavailableError, match="没记模板来源和版本"):
            TemplateService(str(_OWN_TEMPLATES)).update_template(str(project), overwrite=True)
        assert _snapshot(project) == before

    def test_template_inside_the_workspace_repository_refuses_in_chinese(self, tmp_path: Path) -> None:
        """DJ-2026-005 的写法（_src_path: templates/plc-standard-project）：模板不是独立 Git 仓库，说真话、不动文件。"""
        project = tmp_path / "DJ-2026-098"
        TemplateService(str(_OWN_TEMPLATES)).copy_template("plc-standard-project", str(project), dict(_PLC_ANSWERS))
        with (project / ".copier-answers.yml").open("a", encoding="utf-8") as f:
            f.write("_commit: HEAD\n_src_path: templates/plc-standard-project\n")
        _git(project, "init", "-q")
        _git(project, "add", "-A")
        _git(project, "commit", "-qm", "i")
        before = _snapshot(project)
        with pytest.raises(TemplateUpdateUnavailableError, match="不是独立的 Git 仓库"):
            TemplateService(str(_OWN_TEMPLATES)).update_template(str(project), overwrite=True)
        assert _snapshot(project) == before

    def test_update_without_overwrite_refuses_before_copier(self, tmp_path: Path) -> None:
        """copier 增量更新必须 overwrite；没带就先说清楚，不让 copier 抛英文。"""
        templates, commit = _git_template(tmp_path)
        project = tmp_path / "DJ-2026-098"
        service = TemplateService(str(templates))
        service.copy_template("plc-standard-project", str(project), dict(_PLC_ANSWERS))
        with (project / ".copier-answers.yml").open("a", encoding="utf-8") as f:
            f.write(f"_commit: {commit}\n_src_path: {templates / 'plc-standard-project'}\n")
        _git(project, "init", "-q")
        _git(project, "add", "-A")
        _git(project, "commit", "-qm", "i")
        before = _snapshot(project)
        with pytest.raises(TemplateUpdateUnavailableError, match="--overwrite"):
            service.update_template(str(project))
        assert _snapshot(project) == before

    def test_update_keeps_the_brand_model_and_business_line_answers(self, tmp_path: Path) -> None:
        """D-343：when: false 的 5 项（业务线、项目类型、设备类型、品牌、型号）读回来传给 copier，更新后答案文件、
        .plc.json、communications.yml、立项表里的品牌型号不变；型号 1500 按字符串传。"""
        import json

        import yaml

        templates, commit = _git_template(tmp_path)
        project = tmp_path / "DJ-2026-098"
        service = TemplateService(str(templates))
        service.copy_template("plc-standard-project", str(project), dict(_PLC_ANSWERS))
        with (project / ".copier-answers.yml").open("a", encoding="utf-8") as f:
            f.write(f"_commit: {commit}\n_src_path: {templates / 'plc-standard-project'}\n")
        _git(project, "init", "-q")
        _git(project, "add", "-A")
        _git(project, "commit", "-qm", "i")
        kept = [
            "02_PLC程序/PLC_ST/.plc.json",
            "02_PLC程序/工程资产/communications.yml",
            "00_项目管理/01_立项与需求/003_DJ-2026-098_项目立项表_PROJ.md",
        ]
        before = {name: (project / name).read_bytes() for name in kept}

        data = service._kept_answers(service._read_answers(str(project)))
        assert {key: data[key] for key in ("business_line", "project_type", "equipment_type", "plc_vendor", "plc_model")} == {
            "business_line": "DJ",
            "project_type": "single_machine",
            "equipment_type": "conveyor",
            "plc_vendor": "Siemens",
            "plc_model": "1500",
        }
        assert data["station_instances"] == ["StationA", "StationB"]

        assert service.update_template(str(project), overwrite=True)["updated"] is True

        answers = yaml.safe_load((project / ".copier-answers.yml").read_text(encoding="utf-8"))
        assert (answers["plc_vendor"], str(answers["plc_model"]), answers["business_line"]) == ("Siemens", "1500", "DJ")
        assert json.loads((project / kept[0]).read_text(encoding="utf-8"))["plc_model"] == "1500"
        assert {name: (project / name).read_bytes() for name in kept} == before
