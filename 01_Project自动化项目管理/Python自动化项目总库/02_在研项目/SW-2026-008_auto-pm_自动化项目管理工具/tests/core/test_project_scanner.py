"""ProjectScanner 单元测试（M3-Iter1）

验证从 ProjectService 提取的扫描/识别逻辑独立可用。
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from auto_pm.application.core.project_scanner import ProjectScanner


class TestScan:
    """ProjectScanner.scan 测试"""

    def test_scan_finds_copier_project(self, tmp_path: Path) -> None:
        """扫描能识别 .copier-answers.yml 项目"""
        project_dir = tmp_path / "SW-2026-001_测试项目"
        project_dir.mkdir()
        (project_dir / ".copier-answers.yml").write_text(
            yaml.safe_dump(
                {
                    "project_id": "SW-2026-001",
                    "project_name": "测试项目",
                    "_src_path": "templates/python-tool",
                    "version": "V1.0.0",
                    "description": "Python 项目",
                    "project_type": "single_machine",
                    "equipment_type": "conveyor",
                    "plc_vendor": "Siemens",
                    "plc_model": "S7-1200",
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )

        scanner = ProjectScanner(str(tmp_path))
        results = scanner.scan(scan_depth=2)

        assert len(results) == 1
        assert results[0].project_id == "SW-2026-001"
        assert results[0].stack == "python"
        assert results[0].source == "copier"
        assert results[0].project_type == "single_machine"
        assert results[0].equipment_type == "conveyor"
        assert results[0].plc_vendor == "Siemens"
        assert results[0].plc_model == "S7-1200"

    def test_scan_finds_plc_project(self, tmp_path: Path) -> None:
        """扫描能识别 .plc.json 项目"""
        project_dir = tmp_path / "DJ-2026-002_PLC项目"
        project_dir.mkdir()
        (project_dir / ".plc.json").write_text(
            json.dumps(
                {
                    "name": "DJ-2026-002",
                    "version": "V1.0.0",
                    "description": "PLC 项目",
                    "project_type": "single_machine",
                    "equipment_type": "conveyor",
                    "plc_vendor": "Siemens",
                    "plc_model": "S7-1200",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        scanner = ProjectScanner(str(tmp_path))
        results = scanner.scan(scan_depth=2)

        assert len(results) == 1
        assert results[0].project_id == "DJ-2026-002"
        assert results[0].stack == "plc"
        assert results[0].source == "plc_json"
        assert results[0].project_type == "single_machine"
        assert results[0].plc_vendor == "Siemens"

    def test_scan_finds_pm_session_project(self, tmp_path: Path) -> None:
        """扫描能识别 PM_SESSION_*.md 项目"""
        project_dir = tmp_path / "某目录"
        project_dir.mkdir()
        (project_dir / "PM_SESSION_ZD-2026-003.md").write_text(
            "# 会话记录", encoding="utf-8"
        )

        scanner = ProjectScanner(str(tmp_path))
        results = scanner.scan(scan_depth=2)

        assert len(results) == 1
        assert results[0].project_id == "ZD-2026-003"
        assert results[0].source == "pm_session"

    def test_scan_sorts_by_project_id(self, tmp_path: Path) -> None:
        """扫描结果按 project_id 排序"""
        for pid in ("ZD-2026-003", "DJ-2026-002", "SW-2026-001"):
            d = tmp_path / f"{pid}_项目"
            d.mkdir()
            (d / ".copier-answers.yml").write_text(
                yaml.safe_dump({"project_id": pid, "project_name": pid}, allow_unicode=True),
                encoding="utf-8",
            )

        scanner = ProjectScanner(str(tmp_path))
        results = scanner.scan(scan_depth=2)

        ids = [p.project_id for p in results]
        assert ids == ["DJ-2026-002", "SW-2026-001", "ZD-2026-003"]

    def test_scan_respects_max_depth(self, tmp_path: Path) -> None:
        """scan_depth 限制递归深度

        目录结构：tmp_path/level1/level2/level3/.copier-answers.yml
        _scan 从 tmp_path 开始 depth=0：
        - depth=0: 扫描 tmp_path 子目录 level1
        - depth=1: 扫描 level1 子目录 level2
        - depth=2: 扫描 level2 子目录 level3（此处发现项目）
        所以 depth=1 不足以到达 level3，depth=2 能到达。
        """
        deep_dir = tmp_path / "level1" / "level2" / "level3"
        deep_dir.mkdir(parents=True)
        (deep_dir / ".copier-answers.yml").write_text(
            yaml.safe_dump({"project_id": "SW-2026-999", "project_name": "深项目"}, allow_unicode=True),
            encoding="utf-8",
        )

        scanner = ProjectScanner(str(tmp_path))
        # depth=1 不足以到达 level3（在 level2 处 depth=1，不会进入 level3）
        shallow = scanner.scan(scan_depth=1)
        assert all(p.project_id != "SW-2026-999" for p in shallow)
        # depth=2 能到达 level3
        deep = scanner.scan(scan_depth=2)
        assert any(p.project_id == "SW-2026-999" for p in deep)


class TestTryIdentifyProject:
    """ProjectScanner.try_identify_project 测试"""

    def test_identify_priority_copier_over_plc(self, tmp_path: Path) -> None:
        """同时存在 .copier-answers.yml 和 .plc.json 时，copier 优先"""
        project_dir = tmp_path / "DJ-2026-010_混合"
        project_dir.mkdir()
        (project_dir / ".copier-answers.yml").write_text(
            yaml.safe_dump(
                {"project_id": "DJ-2026-010", "project_name": "Copier来源", "_src_path": "templates/plc-standard"},
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        (project_dir / ".plc.json").write_text(
            json.dumps({"name": "DJ-2026-010-PLC"}, ensure_ascii=False),
            encoding="utf-8",
        )

        scanner = ProjectScanner(str(tmp_path))
        info = scanner.try_identify_project(str(project_dir))

        assert info is not None
        assert info.source == "copier"
        assert info.name == "Copier来源"

    def test_identify_returns_none_for_non_project(self, tmp_path: Path) -> None:
        """非项目目录返回 None"""
        non_project = tmp_path / "普通目录"
        non_project.mkdir()

        scanner = ProjectScanner(str(tmp_path))
        assert scanner.try_identify_project(str(non_project)) is None

    def test_identify_sets_file_mtime(self, tmp_path: Path) -> None:
        """识别成功时设置 file_mtime"""
        project_dir = tmp_path / "SW-2026-001_项目"
        project_dir.mkdir()
        (project_dir / ".copier-answers.yml").write_text(
            yaml.safe_dump({"project_id": "SW-2026-001", "project_name": "x"}, allow_unicode=True),
            encoding="utf-8",
        )

        scanner = ProjectScanner(str(tmp_path))
        info = scanner.try_identify_project(str(project_dir))

        assert info is not None
        assert info.file_mtime > 0


class TestReadCopierAnswers:
    """ProjectScanner.read_copier_answers 测试"""

    def test_read_copier_answers_extracts_business_line(self, tmp_path: Path) -> None:
        """从 answers 读取 business_line"""
        project_dir = tmp_path / "SW-2026-001_项目"
        project_dir.mkdir()
        (project_dir / ".copier-answers.yml").write_text(
            yaml.safe_dump(
                {
                    "project_id": "SW-2026-001",
                    "project_name": "项目",
                    "business_line": "SW",
                    "_src_path": "templates/python-tool",
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )

        scanner = ProjectScanner(str(tmp_path))
        info = scanner.read_copier_answers(str(project_dir))

        assert info is not None
        assert info.business_line == "SW"
        assert info.stack == "python"

    def test_read_copier_answers_infers_business_line_from_id(self, tmp_path: Path) -> None:
        """answers 无 business_line 时从 project_id 推断"""
        project_dir = tmp_path / "DJ-2026-010_项目"
        project_dir.mkdir()
        (project_dir / ".copier-answers.yml").write_text(
            yaml.safe_dump(
                {"project_id": "DJ-2026-010", "project_name": "项目"},
                allow_unicode=True,
            ),
            encoding="utf-8",
        )

        scanner = ProjectScanner(str(tmp_path))
        info = scanner.read_copier_answers(str(project_dir))

        assert info is not None
        assert info.business_line == "DJ"

    def test_read_copier_answers_extracts_id_from_dirname(self, tmp_path: Path) -> None:
        """answers 无 project_id 时从目录名提取"""
        project_dir = tmp_path / "SW-2026-008_auto-pm"
        project_dir.mkdir()
        (project_dir / ".copier-answers.yml").write_text(
            yaml.safe_dump({"project_name": "auto-pm"}, allow_unicode=True),
            encoding="utf-8",
        )

        scanner = ProjectScanner(str(tmp_path))
        info = scanner.read_copier_answers(str(project_dir))

        assert info is not None
        assert info.project_id == "SW-2026-008"

    def test_read_copier_answers_returns_none_if_no_file(self, tmp_path: Path) -> None:
        """无 .copier-answers.yml 返回 None"""
        project_dir = tmp_path / "空目录"
        project_dir.mkdir()

        scanner = ProjectScanner(str(tmp_path))
        assert scanner.read_copier_answers(str(project_dir)) is None

    def test_read_copier_answers_reads_v040_metadata(self, tmp_path: Path) -> None:
        """读取 Week 2 元数据字段"""
        project_dir = tmp_path / "DJ-2026-020_项目"
        project_dir.mkdir()
        (project_dir / ".copier-answers.yml").write_text(
            yaml.safe_dump(
                {
                    "project_id": "DJ-2026-020",
                    "project_name": "项目",
                    "_src_path": "templates/plc-standard-project",
                    "project_type": "single_machine",
                    "equipment_type": "conveyor",
                    "plc_vendor": "Siemens",
                    "plc_model": "S7-1200",
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )

        scanner = ProjectScanner(str(tmp_path))
        info = scanner.read_copier_answers(str(project_dir))

        assert info is not None
        assert info.project_type == "single_machine"
        assert info.equipment_type == "conveyor"
        assert info.plc_vendor == "Siemens"
        assert info.plc_model == "S7-1200"

    def test_read_copier_answers_attaches_asset_summary(self, tmp_path: Path) -> None:
        """PLC 项目扫描时附加工程资产摘要"""
        project_dir = tmp_path / "DJ-2026-021_项目"
        (project_dir / "02_PLC程序" / "工程资产").mkdir(parents=True)
        (project_dir / ".copier-answers.yml").write_text(
            yaml.safe_dump(
                {
                    "project_id": "DJ-2026-021",
                    "project_name": "项目",
                    "_src_path": "templates/plc-standard-project",
                    "project_type": "single_machine",
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        (project_dir / "02_PLC程序" / "工程资产" / "io_points.csv").write_text(
            "station,signal_type,address,tag,signal_name,device,comment\n"
            "common,DI,I0.0,ESTOP_OK,急停回路正常,操作台,TRUE=安全链路闭合\n",
            encoding="utf-8",
        )
        (project_dir / "02_PLC程序" / "工程资产" / "program_blocks.yml").write_text(
            "blocks:\n"
            '  - name: "OB1"\n'
            '    type: "OB"\n'
            '    path: "02_PLC程序/PLC_ST/OB1/OB1.scl"\n'
            '    responsibility: "主循环"\n',
            encoding="utf-8",
        )
        (project_dir / "02_PLC程序" / "工程资产" / "communications.yml").write_text(
            "channels:\n"
            '  - name: "HMI"\n'
            '    protocol: "ethernet"\n'
            '    role: "人机界面"\n'
            '    endpoint: "Siemens S7-1200"\n'
            '    notes: "补齐映射"\n',
            encoding="utf-8",
        )

        scanner = ProjectScanner(str(tmp_path))
        info = scanner.read_copier_answers(str(project_dir))

        assert info is not None
        asset_summary = info.extra.get("asset_summary")
        assert isinstance(asset_summary, dict)
        assert asset_summary["status"] == "healthy"
        assert asset_summary["io_points"]["count"] == 1
        assert asset_summary["program_blocks"]["count"] == 1
        assert asset_summary["communications"]["count"] == 1

    def test_read_copier_answers_handles_invalid_yaml(self, tmp_path: Path) -> None:
        """YAML 解析失败返回 None（不抛异常）"""
        project_dir = tmp_path / "坏项目"
        project_dir.mkdir()
        (project_dir / ".copier-answers.yml").write_text(
            "invalid: yaml: content: [", encoding="utf-8"
        )

        scanner = ProjectScanner(str(tmp_path))
        assert scanner.read_copier_answers(str(project_dir)) is None


class TestStaticMethods:
    """ProjectScanner 静态方法测试"""

    def test_extract_id_from_dirname(self, tmp_path: Path) -> None:
        """从目录名提取项目编号"""
        assert (
            ProjectScanner.extract_id_from_dirname(str(tmp_path / "SW-2026-008_auto-pm"))
            == "SW-2026-008"
        )
        assert (
            ProjectScanner.extract_id_from_dirname(str(tmp_path / "DJ-2026-010_项目"))
            == "DJ-2026-010"
        )
        # 无项目编号格式 → 返回目录名
        assert (
            ProjectScanner.extract_id_from_dirname(str(tmp_path / "普通目录"))
            == "普通目录"
        )

    def test_infer_stack(self) -> None:
        """根据模板源路径推断技术栈"""
        assert ProjectScanner.infer_stack("templates/plc-standard") == "plc"
        assert ProjectScanner.infer_stack("templates/python-tool") == "python"
        assert ProjectScanner.infer_stack("templates/unknown") == "unknown"
        assert ProjectScanner.infer_stack("") == "unknown"

    def test_get_project_mtime(self, tmp_path: Path) -> None:
        """获取项目标志文件 mtime"""
        project_dir = tmp_path / "SW-2026-001_项目"
        project_dir.mkdir()
        (project_dir / ".copier-answers.yml").write_text("x: 1", encoding="utf-8")

        mtime = ProjectScanner.get_project_mtime(str(project_dir))
        assert mtime > 0

    def test_get_project_mtime_zero_for_no_markers(self, tmp_path: Path) -> None:
        """无标志文件时 mtime 为 0"""
        project_dir = tmp_path / "空目录"
        project_dir.mkdir()

        assert ProjectScanner.get_project_mtime(str(project_dir)) == 0.0


class TestBackwardCompatibility:
    """ProjectService 通过组合使用 ProjectScanner 的向后兼容测试"""

    def test_project_service_delegates_to_scanner(self, tmp_path: Path) -> None:
        """ProjectService 内部委托给 ProjectScanner"""
        from auto_pm.application.core.project_service import ProjectService

        project_dir = tmp_path / "SW-2026-001_项目"
        project_dir.mkdir()
        (project_dir / ".copier-answers.yml").write_text(
            yaml.safe_dump(
                {"project_id": "SW-2026-001", "project_name": "项目"}, allow_unicode=True
            ),
            encoding="utf-8",
        )

        svc = ProjectService(str(tmp_path))
        # list_projects 应委托给 scanner.scan
        results = svc.list_projects(scan_depth=2)
        assert len(results) == 1
        assert results[0].project_id == "SW-2026-001"

        # 旧私有方法签名应仍可用（委托给 scanner）
        info = svc._read_copier_answers(str(project_dir))
        assert info is not None
        assert info.project_id == "SW-2026-001"

        # 静态方法委托
        assert svc._extract_id_from_dirname(str(project_dir)) == "SW-2026-001"
        assert svc._infer_stack("templates/plc-standard") == "plc"
        assert svc._get_project_mtime(str(project_dir)) > 0


class TestStackFallback:
    """V0.5.3 Fix 2: 路径兜底推断 stack 测试"""

    def test_infer_stack_from_python_path(self, tmp_path: Path) -> None:
        """路径含 Python自动化项目总库 → python"""
        scanner = ProjectScanner(str(tmp_path))
        path = r"C:\workspace\01_Project自动化项目管理\Python自动化项目总库\02_在研项目\SW-2026-008"
        assert scanner._infer_stack_from_path(path) == "python"

    def test_infer_stack_from_plc_path(self, tmp_path: Path) -> None:
        """路径含 0100_PLC自动化 → plc"""
        scanner = ProjectScanner(str(tmp_path))
        path = r"C:\workspace\0100_PLC自动化\DJ-2026-001"
        assert scanner._infer_stack_from_path(path) == "plc"

    def test_infer_stack_from_unknown_path(self, tmp_path: Path) -> None:
        """其他路径 → unknown"""
        scanner = ProjectScanner(str(tmp_path))
        path = r"C:\workspace\SYS-2026-001_WorkspaceGovernance"
        assert scanner._infer_stack_from_path(path) == "unknown"

    def test_infer_stack_forward_slash_normalized(self, tmp_path: Path) -> None:
        """正斜杠路径应被归一化后匹配"""
        scanner = ProjectScanner(str(tmp_path))
        path = "C:/workspace/01_Project自动化项目管理/Python自动化项目总库/SW-2026-001"
        assert scanner._infer_stack_from_path(path) == "python"

    def test_infer_stack_backslash_path_written_on_windows_is_recognised_anywhere(
        self, tmp_path: Path
    ) -> None:
        """Windows 写下的反斜杠路径换到 Linux 机器上读，也要能推断出 stack"""
        scanner = ProjectScanner(str(tmp_path))
        assert scanner._infer_stack_from_path(r"D:\ws\0100_PLC自动化\DJ-2026-001") == "plc"
        assert scanner._infer_stack_from_path("/home/u/ws/0100_PLC自动化/DJ-2026-001") == "plc"
        assert scanner._infer_stack_from_path("/home/u/ws/0100_PLC自动化X/DJ") == "unknown"

    def test_apply_stack_fallback_skips_when_already_set(
        self, tmp_path: Path
    ) -> None:
        """stack 已为 plc/python 时不应被路径推断覆盖"""
        from auto_pm.domain.models import ProjectInfo

        scanner = ProjectScanner(str(tmp_path))
        info = ProjectInfo(
            project_id="SW-2026-001",
            name="test",
            path=r"C:\workspace\0100_PLC自动化\DJ-2026-001",
            stack="python",
            source="copier",
        )
        scanner._apply_stack_fallback(info)
        assert info.stack == "python"  # 不被覆盖

    def test_apply_stack_fallback_infers_when_unknown(
        self, tmp_path: Path
    ) -> None:
        """stack=unknown 时应按路径推断"""
        from auto_pm.domain.models import ProjectInfo

        scanner = ProjectScanner(str(tmp_path))
        info = ProjectInfo(
            project_id="SW-2026-001",
            name="test",
            path=r"C:\workspace\01_Project自动化项目管理\Python自动化项目总库\SW-2026-001",
            stack="unknown",
            source="pm_session",
        )
        scanner._apply_stack_fallback(info)
        assert info.stack == "python"


class TestNoPhaseFromPmSession:
    """CHG-SCPT-2026-650：PM_SESSION 已退役，扫描不再从它推阶段；项目状态以工作区登记表为准。"""

    _SESSION = """# PM_SESSION

- current_focus: 项目正在开发中，尚未进入调试
- current_state: 已投产运行，进入稳定运行阶段
phase: production
"""

    def test_read_pm_session_only_names_the_project(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "SW-2026-001_项目"
        project_dir.mkdir()
        (project_dir / "PM_SESSION_SW-2026-001.md").write_text(self._SESSION, encoding="utf-8")

        info = ProjectScanner(str(tmp_path)).read_pm_session(str(project_dir))

        assert info is not None
        assert info.project_id == "SW-2026-001"
        assert info.source == "pm_session"
        assert info.phase == ""

    def test_scan_does_not_derive_developing_from_pm_session(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "SW-2026-001_项目"
        project_dir.mkdir()
        (project_dir / "PM_SESSION_SW-2026-001.md").write_text(self._SESSION, encoding="utf-8")

        results = ProjectScanner(str(tmp_path)).scan(scan_depth=2)

        assert [(r.project_id, r.phase) for r in results] == [("SW-2026-001", "")]

    def test_copier_project_without_phase_does_not_fall_back_to_pm_session(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "SW-2026-002_项目"
        project_dir.mkdir()
        (project_dir / ".copier-answers.yml").write_text(
            "project_id: SW-2026-002\nproject_name: 测试\nstack: python\n", encoding="utf-8"
        )
        (project_dir / "PM_SESSION_SW-2026-002.md").write_text(self._SESSION, encoding="utf-8")

        info = ProjectScanner(str(tmp_path)).read_copier_answers(str(project_dir))

        assert info is not None and info.phase == ""

    def test_copier_phase_is_still_read_from_the_answers(self, tmp_path: Path) -> None:
        project_dir = tmp_path / "SW-2026-003_项目"
        project_dir.mkdir()
        (project_dir / ".copier-answers.yml").write_text(
            "project_id: SW-2026-003\nproject_name: 测试\nstack: python\nphase: commissioning\n", encoding="utf-8"
        )

        info = ProjectScanner(str(tmp_path)).read_copier_answers(str(project_dir))

        assert info is not None and info.phase == "commissioning"

    def test_the_pm_session_phase_helpers_are_gone(self) -> None:
        for name in ("_read_phase_from_pm_session", "_derive_phase_from_pm_session_content", "_matches_phase_patterns"):
            assert not hasattr(ProjectScanner, name), name
