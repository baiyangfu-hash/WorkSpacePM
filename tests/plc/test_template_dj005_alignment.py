"""Automated defense tests for PLC template alignment with DJ-2026-005 benchmark.

Covers:
1. Template contains 00_项目管理, 01_需求与设计, 03_HMI设计/原型/files.
2. Template HMI prototype contains standard HTML, CSS, JS, and tag mapping.
3. PlcChecker enforces HMI prototype and software scheme existence.
"""

import os
import sys
from pathlib import Path

# 工作空间根与 SW-2026-008 母体源码：按本文件位置推导，不依赖调用目录；导入路径与母体 pyproject 的 pythonpath 一致
_WS_ROOT = Path(__file__).resolve().parents[2]
_SW008_ROOT = (
    _WS_ROOT / "01_Project自动化项目管理" / "Python自动化项目总库" / "02_在研项目" / "SW-2026-008_auto-pm_自动化项目管理工具"
)
for _entry in (_SW008_ROOT / "auto_pm", _SW008_ROOT):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

from auto_pm.domain.plc.checker import PlcChecker  # noqa: E402


class TestTemplateDJ005Alignment:
    """验证 PLC 脚手架模板与 DJ-005 标杆架构对齐防御测试"""

    def test_template_directories_and_files_exist(self):
        ws_root = str(_WS_ROOT)
        tpl_dir = os.path.join(
            ws_root,
            "01_Project自动化项目管理",
            "Python自动化项目总库",
            "02_在研项目",
            "SW-2026-008_auto-pm_自动化项目管理工具",
            "templates",
            "plc-standard-project",
            "template",
        )

        assert os.path.isdir(os.path.join(tpl_dir, "00_项目管理", "01_立项与需求"))
        assert os.path.isdir(os.path.join(tpl_dir, "01_需求与设计", "13_软件方案"))
        assert os.path.isdir(os.path.join(tpl_dir, "03_HMI设计", "原型", "files"))

        # 检查 HMI 原型核心文件与标准部件库
        hmi_files = os.listdir(os.path.join(tpl_dir, "03_HMI设计", "原型", "files"))
        assert "HMI原型设计.html" in hmi_files or "HMI原型设计.html.jinja" in hmi_files
        assert "styles.css" in hmi_files or "styles.css.jinja" in hmi_files
        assert "hmi-components.js" in hmi_files
        assert "hmi-tokens.css" in hmi_files

    def test_checker_intercepts_missing_hmi_prototype(self, tmp_path):
        """验证 PlcChecker 能够拦截缺失 HMI 原型的残缺项目"""
        checker = PlcChecker(workspace_root=str(tmp_path))
        proj_dir = tmp_path / "DJ-TEST-INCOMPLETE"
        proj_dir.mkdir()
        (proj_dir / ".plc.json").write_text('{"name":"DJ-TEST","version":"V1.0.0"}', encoding="utf-8")

        result = checker.check_project(str(proj_dir))
        hmi_check = [item for item in result.items if item.item == "HMI 交互原型"]
        assert len(hmi_check) > 0
        assert hmi_check[0].status == "fail", "缺少 HMI 原型必须判定为 FAIL"
