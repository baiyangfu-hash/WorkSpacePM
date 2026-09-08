"""PlcRepairer 单元测试"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from auto_pm.plc.repairer import PlcRepairer

# ── Fixtures ──────────────────────────────────────────


@pytest.fixture
def broken_project(tmp_path: Path) -> Path:
    """创建一个缺少多个标准文件的项目（有 .plc.json 可被 scan 识别）"""
    project_dir = tmp_path / "DJ-2026-BROKEN_损坏项目"
    project_dir.mkdir()
    (project_dir / ".plc.json").write_text(
        json.dumps(
            {
                "name": "DJ-2026-BROKEN",
                "version": "V1.0.0",
                "description": "损坏项目",
                "type": "standard",
                "libraries": [],
            }
        ),
        encoding="utf-8",
    )
    (project_dir / "PM_SESSION_DJ-2026-BROKEN.md").write_text(
        "# PM_SESSION_DJ-2026-BROKEN\n", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def project_without_plc_json(tmp_path: Path) -> Path:
    """创建一个缺少 .plc.json 的项目（仅 PM_SESSION）"""
    project_dir = tmp_path / "DJ-2026-NOPLC_无配置文件"
    project_dir.mkdir()
    (project_dir / "PM_SESSION_DJ-2026-NOPLC.md").write_text(
        "# PM_SESSION_DJ-2026-NOPLC\n", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def project_with_nonstandard_prd(tmp_path: Path) -> Path:
    """创建一个 PRD 文档命名不规范的项目"""
    project_dir = tmp_path / "DJ-2026-NSPRD_非标准PRD"
    project_dir.mkdir()

    # .plc.json
    (project_dir / ".plc.json").write_text(
        json.dumps(
            {
                "name": "DJ-2026-NSPRD",
                "version": "V1.0.0",
                "description": "非标准PRD项目",
                "type": "standard",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # PM_SESSION
    (project_dir / "PM_SESSION_DJ-2026-NSPRD.md").write_text(
        "# PM_SESSION_DJ-2026-NSPRD\n", encoding="utf-8"
    )

    # PRD 目录 + 非标准命名文档
    # NAMING_RULES 中 "接口文档_INT.md" 的 patterns:
    #   r"^接口文档_IFC-.*\.md$" 和 r"^.*_INT\.md$"
    # "接口文档_IFC-001.md" 匹配第一个 pattern
    # checker 前缀: "接口文档_INT.md" → prefix="接口文档"，"接口文档_IFC-001.md" 以 "接口文档" 开头 → 匹配
    prd_dir = project_dir / "PRD"
    prd_dir.mkdir()
    (prd_dir / "接口文档_IFC-001.md").write_text("# 接口文档\n", encoding="utf-8")

    # 标准目录（LSP-907 §3.1，12 个）
    for d in [
        "00_项目管理", "01_需求与设计", "02_PLC程序", "03_HMI设计",
        "04_现场调试", "12_驱动器与设备", "05_测试与验证", "06_文档与交付",
        "07_技术支持", "08_备件管理", "09_项目总结", "10_知识库",
    ]:
        (project_dir / d).mkdir()

    return tmp_path


@pytest.fixture
def complete_project(tmp_path: Path) -> Path:
    """创建一个完整的项目（用于标准化工测试）"""
    project_dir = tmp_path / "DJ-2026-COMP_完整项目"
    project_dir.mkdir()

    # .plc.json
    (project_dir / ".plc.json").write_text(
        json.dumps(
            {
                "name": "DJ-2026-COMP",
                "version": "V1.0.0",
                "description": "完整项目",
                "type": "standard",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # PM_SESSION
    (project_dir / "PM_SESSION_DJ-2026-COMP.md").write_text(
        "# PM_SESSION_DJ-2026-COMP\n", encoding="utf-8"
    )

    # PRD 目录 + 标准命名文档
    prd_dir = project_dir / "PRD"
    prd_dir.mkdir()
    for doc in ["需求分析文档_REQ.md", "接口文档_INT.md", "详细设计说明书_DSN.md", "技术方案文档_TEC.md"]:
        (prd_dir / doc).write_text(f"# {doc}\n", encoding="utf-8")

    # 标准目录（LSP-907 §3.1，12 个）
    for d in [
        "01_启动", "02_PLC程序", "03_HMI设计",
        "04_现场调试", "05_测试与验证", "06_文档与交付",
        "07_技术支持", "08_备件管理", "09_项目总结", "10_知识库",
        "11_监控", "12_驱动器与设备",
    ]:
        (project_dir / d).mkdir()

    # 变更管理体系
    chg_dir = project_dir / "11_监控" / "01_变更管理"
    (chg_dir / "01_变更单").mkdir(parents=True, exist_ok=True)
    (chg_dir / "02_变更记录").mkdir(parents=True, exist_ok=True)
    (chg_dir / "02_变更记录" / "01_版本变更台帐.md").write_text("# 版本变更台帐\n", encoding="utf-8")

    # 交付文档实质化
    (project_dir / "04_现场调试" / "现场调试计划.md").write_text("# 现场调试计划\n", encoding="utf-8")
    (project_dir / "06_文档与交付" / "验收交付清单.md").write_text("# 验收交付清单\n", encoding="utf-8")

    return tmp_path


# ── repair_project 测试 ───────────────────────────────


class TestRepairProject:
    """单项目修复测试"""

    def test_repair_missing_plc_json(self, project_without_plc_json: Path) -> None:
        """修复缺少 .plc.json 的项目"""
        project_dir = project_without_plc_json / "DJ-2026-NOPLC_无配置文件"
        repairer = PlcRepairer(str(project_without_plc_json))
        result = repairer.repair_project(str(project_dir))

        assert result.fixed_count >= 1
        assert any(
            a.item == ".plc.json" and a.status == "fixed" for a in result.actions
        )
        # 验证文件已创建
        assert (project_dir / ".plc.json").exists()

    def test_repair_missing_pm_session(self, tmp_path: Path) -> None:
        """修复缺少 PM_SESSION 的项目"""
        project_dir = tmp_path / "DJ-2026-NOPM_无PM项目"
        project_dir.mkdir()
        # 只有 .plc.json，无 PM_SESSION
        (project_dir / ".plc.json").write_text(
            json.dumps(
                {"name": "DJ-2026-NOPM", "version": "V1.0.0", "description": "无PM项目"},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        repairer = PlcRepairer(str(tmp_path))
        result = repairer.repair_project(str(project_dir))

        assert any(
            a.item == "PM_SESSION" and a.status == "fixed" for a in result.actions
        )
        # 验证文件已创建
        project_id = "DJ-2026-NOPM"
        assert (project_dir / f"PM_SESSION_{project_id}.md").exists()

    def test_repair_missing_prd_dir(self, broken_project: Path) -> None:
        """修复缺少 PRD 目录的项目"""
        project_dir = broken_project / "DJ-2026-BROKEN_损坏项目"
        repairer = PlcRepairer(str(broken_project))
        result = repairer.repair_project(str(project_dir))

        assert any(
            a.item == "PRD 目录" and a.status == "fixed" for a in result.actions
        )
        assert (project_dir / "PRD").is_dir()

    def test_repair_missing_std_dirs(self, broken_project: Path) -> None:
        """修复缺少标准目录的项目"""
        project_dir = broken_project / "DJ-2026-BROKEN_损坏项目"
        repairer = PlcRepairer(str(broken_project))
        result = repairer.repair_project(str(project_dir))

        # 应该修复标准目录
        dir_actions = [
            a for a in result.actions if a.item.startswith("目录 ") and a.status == "fixed"
        ]
        assert len(dir_actions) >= 1

    def test_repair_dry_run(self, project_without_plc_json: Path) -> None:
        """dry_run 模式不创建文件"""
        project_dir = project_without_plc_json / "DJ-2026-NOPLC_无配置文件"
        repairer = PlcRepairer(str(project_without_plc_json))
        result = repairer.repair_project(str(project_dir), dry_run=True)

        # dry_run 模式不应创建文件
        assert not (project_dir / ".plc.json").exists()
        # 但 before_check 和 after_check 应该相同
        assert result.after_check == result.before_check

    def test_repair_rename_confirm_skipped_without_flag(self, project_with_nonstandard_prd: Path) -> None:
        """未确认重命名时，命名不匹配项应跳过"""
        project_dir = project_with_nonstandard_prd / "DJ-2026-NSPRD_非标准PRD"
        repairer = PlcRepairer(str(project_with_nonstandard_prd))
        result = repairer.repair_project(str(project_dir), rename_confirm=False)

        # 命名不匹配项应标记为 skipped
        rename_skipped = [
            a for a in result.actions
            if a.destructive and a.status == "skipped"
        ]
        assert len(rename_skipped) >= 1

    def test_repair_rename_confirm_with_flag(self, project_with_nonstandard_prd: Path) -> None:
        """确认重命名后，命名不匹配项应被修复"""
        project_dir = project_with_nonstandard_prd / "DJ-2026-NSPRD_非标准PRD"
        repairer = PlcRepairer(str(project_with_nonstandard_prd))
        result = repairer.repair_project(str(project_dir), rename_confirm=True)

        # 命名不匹配项应被重命名
        rename_fixed = [
            a for a in result.actions
            if a.destructive and a.status == "fixed"
        ]
        assert len(rename_fixed) >= 1

    def test_repair_complete_project_no_fixes(self, complete_project: Path) -> None:
        """完整项目修复后无需修复"""
        project_dir = complete_project / "DJ-2026-COMP_完整项目"
        repairer = PlcRepairer(str(complete_project))
        result = repairer.repair_project(str(project_dir))

        assert result.fixed_count == 0
        assert result.failed_count == 0

    def test_repair_plc_json_missing_fields(self, tmp_path: Path) -> None:
        """修复 .plc.json 缺少必填字段"""
        project_dir = tmp_path / "DJ-2026-MISS_缺字段项目"
        project_dir.mkdir()
        # 创建缺少 description 的 .plc.json
        (project_dir / ".plc.json").write_text(
            json.dumps({"name": "DJ-2026-MISS"}, ensure_ascii=False),
            encoding="utf-8",
        )

        repairer = PlcRepairer(str(tmp_path))
        result = repairer.repair_project(str(project_dir))

        assert any(
            a.item == ".plc.json" and a.status == "fixed" for a in result.actions
        )
        # 验证字段已补全
        with open(project_dir / ".plc.json", encoding="utf-8") as f:
            cfg = json.load(f)
        assert "description" in cfg
        assert "version" in cfg

    def test_repair_creates_plc_json_under_plc_st_when_directory_exists(self, tmp_path: Path) -> None:
        """标准项目存在 PLC_ST 时，repair 应在该目录创建 .plc.json"""
        project_dir = tmp_path / "DJ-2026-PLCST_标准项目"
        (project_dir / "02_PLC程序" / "PLC_ST").mkdir(parents=True)
        (project_dir / "PM_SESSION_DJ-2026-PLCST.md").write_text(
            "# PM_SESSION_DJ-2026-PLCST\n", encoding="utf-8"
        )

        repairer = PlcRepairer(str(tmp_path))
        result = repairer.repair_project(str(project_dir))

        assert any(
            a.item == ".plc.json" and a.status == "fixed" for a in result.actions
        )
        plc_json_path = project_dir / "02_PLC程序" / "PLC_ST" / ".plc.json"
        assert plc_json_path.exists()
        cfg = json.loads(plc_json_path.read_text(encoding="utf-8"))
        assert cfg["libraries"] == ["../../../01_SharedLibraries/SysLib"]


# ── repair_workspace 测试 ─────────────────────────────


class TestRepairWorkspace:
    """工作空间批量修复测试"""

    def test_repair_workspace(self, broken_project: Path) -> None:
        """批量修复工作空间"""
        repairer = PlcRepairer(str(broken_project))
        results = repairer.repair_workspace()

        assert len(results) >= 1
        assert any(r.fixed_count >= 1 for r in results)

    def test_repair_workspace_skips_passing(self, complete_project: Path) -> None:
        """批量修复跳过已通过的项目"""
        repairer = PlcRepairer(str(complete_project))
        results = repairer.repair_workspace()

        # 完整项目应被跳过（all_pass=True）
        assert len(results) == 0


# ── standardize_docs 测试 ─────────────────────────────


class TestStandardizeDocs:
    """文档标准化测试"""

    def test_standardize_docs_preview(self, project_with_nonstandard_prd: Path) -> None:
        """预览模式不执行重命名"""
        project_dir = project_with_nonstandard_prd / "DJ-2026-NSPRD_非标准PRD"
        repairer = PlcRepairer(str(project_with_nonstandard_prd))
        result = repairer.standardize_docs(str(project_dir), apply=False)

        # 应有重命名计划
        assert len(result.plans) >= 1
        # 但 skipped_count > 0（未执行）
        assert result.skipped_count >= 1
        # 原文件仍存在
        assert (project_dir / "PRD" / "接口文档_IFC-001.md").exists()

    def test_standardize_docs_apply(self, project_with_nonstandard_prd: Path) -> None:
        """执行模式完成重命名"""
        project_dir = project_with_nonstandard_prd / "DJ-2026-NSPRD_非标准PRD"
        repairer = PlcRepairer(str(project_with_nonstandard_prd))
        result = repairer.standardize_docs(str(project_dir), apply=True)

        # 应有重命名计划且已应用
        assert len(result.plans) >= 1
        assert result.applied_count >= 1
        # 标准文件应存在（接口文档_IFC-001.md → 接口文档_INT.md）
        assert (project_dir / "PRD" / "接口文档_INT.md").exists()

    def test_standardize_docs_no_prd_dir(self, tmp_path: Path) -> None:
        """无 PRD 目录时标准化应安全返回"""
        project_dir = tmp_path / "DJ-2026-NOPRD_无PRD"
        project_dir.mkdir()
        (project_dir / ".plc.json").write_text(
            json.dumps({"name": "DJ-2026-NOPRD", "version": "V1.0.0", "description": "无PRD"}, ensure_ascii=False),
            encoding="utf-8",
        )

        repairer = PlcRepairer(str(tmp_path))
        result = repairer.standardize_docs(str(project_dir))

        assert len(result.plans) == 0

    def test_standardize_docs_already_standard(self, complete_project: Path) -> None:
        """已是标准命名的文档不需要标准化"""
        project_dir = complete_project / "DJ-2026-COMP_完整项目"
        repairer = PlcRepairer(str(complete_project))
        result = repairer.standardize_docs(str(project_dir))

        assert len(result.plans) == 0


# ── standardize_workspace 测试 ────────────────────────


class TestStandardizeWorkspace:
    """工作空间批量标准化测试"""

    def test_standardize_workspace(self, project_with_nonstandard_prd: Path) -> None:
        """批量标准化工作空间"""
        repairer = PlcRepairer(str(project_with_nonstandard_prd))
        results = repairer.standardize_workspace()

        assert len(results) >= 1

    def test_standardize_workspace_apply(self, project_with_nonstandard_prd: Path) -> None:
        """批量标准化工作空间（执行模式）"""
        repairer = PlcRepairer(str(project_with_nonstandard_prd))
        results = repairer.standardize_workspace(apply=True)

        assert len(results) >= 1
        assert any(r.applied_count >= 1 for r in results)
