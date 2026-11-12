"""模板生成正确性测试

验证 3 套 PLC 模板生成的项目结构正确性:
- .plc.json 位置正确
- libraries 路径有效
- 目录结构完整

不依赖 copier 实际渲染，仅验证模板文件结构。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from auto_pm.application.core.template_service import TemplateService


class TestTemplateGeneration:
    """模板生成正确性测试"""

    @pytest.fixture
    def template_service(self) -> TemplateService:
        """获取项目的 TemplateService（模板在项目根的 templates/ 下）"""
        project_root = Path(__file__).parent.parent.parent
        templates_dir = project_root / "templates"
        return TemplateService(str(templates_dir))

    def test_list_templates_includes_3_plc_templates(
        self, template_service: TemplateService
    ) -> None:
        """list_templates 应包含 3 套 PLC 模板"""
        templates = template_service.list_templates()
        assert "plc-shared-library" in templates
        assert "plc-test-suite" in templates
        assert "plc-standard-project" in templates

    def test_plc_shared_library_template_structure(
        self, template_service: TemplateService
    ) -> None:
        """plc-shared-library 模板结构正确"""
        path = template_service.get_template_path("plc-shared-library")
        # 验证 copier.yml 存在
        assert os.path.isfile(os.path.join(path, "copier.yml"))
        # 验证 template/ 目录存在
        assert os.path.isdir(os.path.join(path, "template"))
        # 验证 .plc.json.jinja 存在（根级）
        assert os.path.isfile(os.path.join(path, "template", ".plc.json.jinja"))

    def test_plc_test_suite_template_structure(
        self, template_service: TemplateService
    ) -> None:
        """plc-test-suite 模板结构正确"""
        path = template_service.get_template_path("plc-test-suite")
        assert os.path.isfile(os.path.join(path, "copier.yml"))
        assert os.path.isdir(os.path.join(path, "template"))
        assert os.path.isfile(os.path.join(path, "template", ".plc.json.jinja"))
        # 验证扁平结构（DB1/OB1 在根级）
        assert os.path.isdir(os.path.join(path, "template", "DB1"))
        assert os.path.isdir(os.path.join(path, "template", "OB1"))

    def test_plc_standard_project_template_structure(
        self, template_service: TemplateService
    ) -> None:
        """plc-standard-project 模板结构正确（含根级 .plc.json 与 02_PLC程序 资产）"""
        path = template_service.get_template_path("plc-standard-project")
        assert os.path.isfile(os.path.join(path, "copier.yml"))
        # 验证根级 .plc.json.jinja
        assert os.path.isfile(os.path.join(path, "template", ".plc.json.jinja"))
        # 验证 .plc.json.jinja 在 02_PLC程序/PLC_ST/ 下
        plc_json_jinja = os.path.join(
            path, "template", "02_PLC程序", "PLC_ST", ".plc.json.jinja"
        )
        assert os.path.isfile(plc_json_jinja)

    def test_plc_standard_project_has_12_std_dirs(
        self, template_service: TemplateService
    ) -> None:
        """plc-standard-project 模板含 12 个标准目录（CHG-SCPT-2026-146: 01_启动 替代 00_项目管理）"""
        from auto_pm.domain.plc.models import PM_DIR_CANDIDATES, STD_DIRS

        path = template_service.get_template_path("plc-standard-project")
        template_dir = os.path.join(path, "template")
        for d in STD_DIRS:
            # 项目管理目录：接受任一候选（01_启动 或 00_项目管理）
            if d in PM_DIR_CANDIDATES or d in ("00_项目管理", "01_启动"):
                assert any(
                    os.path.isdir(os.path.join(template_dir, c))
                    for c in PM_DIR_CANDIDATES
                ), f"缺少项目管理目录（候选: {PM_DIR_CANDIDATES}）"
            else:
                assert os.path.isdir(os.path.join(template_dir, d)), f"缺少标准目录: {d}"

    def test_plc_standard_project_includes_week2_assets_and_overview(
        self, template_service: TemplateService
    ) -> None:
        """plc-standard-project 模板包含工程资产样例与立项表"""
        path = template_service.get_template_path("plc-standard-project")
        template_dir = os.path.join(path, "template")

        has_proj_file = os.path.isfile(
            os.path.join(
                template_dir, "01_启动", "003_{{ project_id }}_项目立项表_PROJ.md.jinja"
            )
        ) or os.path.isfile(
            os.path.join(
                template_dir, "00_项目管理", "01_立项与需求", "003_{{ project_id }}_项目立项表_PROJ.md.jinja"
            )
        )
        assert has_proj_file, "缺少项目立项表模板文件"
        for asset_name in (
            "README.md.jinja",
            "io_points.csv.jinja",
            "program_blocks.yml.jinja",
            "communications.yml.jinja",
        ):
            assert os.path.isfile(
                os.path.join(template_dir, "02_PLC程序", "工程资产", asset_name)
            ), f"缺少工程资产样例: {asset_name}"


# ---- CHG-SCPT-2026-635：按工位清单生成背景 DB、结构体/FB/DB 同目录、独占结构体带 FB 编号 ----------------------------

_STANDARD = Path(__file__).resolve().parent.parent.parent / "templates" / "plc-standard-project"
_BASE_DATA = {"project_id": "DJ-2026-901", "project_name": "样例", "description": "样例", "version": "V1.0.0"}


def _render(tmp_path: Path, stations: list[str] | None) -> Path:
    import copier

    data = dict(_BASE_DATA, **({"station_instances": stations} if stations is not None else {}))
    dest = tmp_path / ("p" + str(len(stations or [])))
    copier.run_copy(str(_STANDARD), str(dest), data=data, defaults=True, unsafe=True, quiet=True)
    return dest / "02_PLC程序" / "PLC_ST"


@pytest.mark.parametrize(("stations", "expected"), [
    (None, ["Station1"]),
    (["Station1", "Station2", "Station3"], ["Station1", "Station2", "Station3"]),
    ([f"S{i}" for i in range(1, 9)], [f"S{i}" for i in range(1, 9)]),
])
def test_one_instance_db_per_station_in_the_station_fb_folder(
    tmp_path: Path, stations: list[str] | None, expected: list[str]
) -> None:
    plc = _render(tmp_path, stations)
    station_dir = plc / "02_工位_动作机构"
    assert sorted(p.name for p in station_dir.glob("DB_1001_*.scl")) == sorted(f"DB_1001_{s}.scl" for s in expected)
    assert not list(plc.glob("00_全局数据/DB_*"))  # 背景 DB 不再放 00_全局数据
    assert (plc / "01_外部设备交互" / "DB_3001_ExternalInteraction.scl").is_file()
    assert (plc / "05_公共报警" / "DB_2001_CommonAlarm.scl").is_file()
    global_vars = (plc / "00_全局数据" / "GlobalVars.db").read_text(encoding="utf-8-sig")
    ob = (plc / "00_主程序" / "OB123.scl").read_text(encoding="utf-8-sig")
    for station in expected:
        db = (station_dir / f"DB_1001_{station}.scl").read_bytes()
        assert db.startswith(b"\xef\xbb\xbf")
        text = db.decode("utf-8-sig")
        assert f'DATA_BLOCK "DB_1001_{station}_DJ2026901"\n"FB_1001_Station1_DJ2026901"\nBEGIN\nEND_DATA_BLOCK' in text
        assert f"st{station}" in global_vars and f": ST_1001_Station1;  // {station} 全局交互结构体" in global_vars
        assert f'"DB_1001_{station}_DJ2026901"(io_stStation := "GlobalVars_DJ2026901".st{station});' in ob
    assert ob.count('"DB_1001_') == len(expected)
    assert not list(plc.rglob("*{*")) and not (plc.parent.parent / "_includes").exists()


@pytest.mark.parametrize(("stations", "message"), [
    ([f"S{i}" for i in range(9)], "1～8"),
    ([], "1～8"),
    (["S1", "S1"], "重复"),
    (["1st"], "不合规"),
    (["Station 2"], "不合规"),
])
def test_bad_station_lists_are_rejected_by_the_template(tmp_path: Path, stations: list[str], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _render(tmp_path, stations)


def test_owned_structs_carry_their_fb_number(tmp_path: Path) -> None:
    """LSP-905 V1.7.0 §3.3 第 3 条：只被一个 FB 用的结构体写成 ST_<FB编号>_<名>，和 FB 同文件夹；共用的才放 00_公共类型/"""
    import re

    plc = _render(tmp_path, ["Station1", "Station2"])
    types = {m.group(1): p.parent.name for p in plc.rglob("*.scl")
             for m in re.finditer(r"^TYPE\s+(ST_\w+)", p.read_text(encoding="utf-8-sig"), flags=re.M)}
    assert types, "模板里应有结构体"
    for name, folder in types.items():
        if folder == "00_公共类型":
            continue
        number = re.match(r"ST_(\d{4})_", name)
        assert number, name
        assert any(f.name.startswith("FB_" + number.group(1)) for f in (plc / folder).glob("FB_*.scl")), (name, folder)


def test_template_paths_fit_in_windows_max_path() -> None:
    """用户电脑上放进工位目录后：本单新增的槽位文件和公共片段完整路径不超过 250 个字符，模板里任何文件不超过 Windows 默认上限 260"""
    control_root = r"C:\Users\fubai\Documents\My_Workspace"
    worktree = r"\.auto-pm\worktrees\claude-xxxxxx"
    project = r"\01_Project自动化项目管理\Python自动化项目总库\02_在研项目\SW-2026-008_auto-pm_自动化项目管理工具\templates\plc-standard-project"
    prefix = len(control_root + worktree + project) + 1
    def length(path: Path) -> int:
        return prefix + len(path.relative_to(_STANDARD).as_posix())

    longest = max(_STANDARD.rglob("*"), key=length)
    assert length(longest) <= 260, longest
    added = [*(_STANDARD / "template/02_PLC程序/PLC_ST/02_工位_动作机构").glob("{{ db_slot_*"), *(_STANDARD / "_includes").glob("*")]
    assert len(added) == 9 and all(length(p) <= 250 for p in added), [(p.name, length(p)) for p in added]
