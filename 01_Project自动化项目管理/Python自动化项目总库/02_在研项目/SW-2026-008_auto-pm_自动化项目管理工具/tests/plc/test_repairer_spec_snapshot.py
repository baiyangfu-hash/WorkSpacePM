"""PlcRepairer Spec Snapshot 修复单元测试（V2.0.3 规范漂移检测）

覆盖场景：
- 自动修复（版本号更新）
- dry-run 预览（不修改文件）
- 无漂移时跳过修复
- Spec Snapshot 缺失时补齐基线章节
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from auto_pm.domain.models.plc import CheckResult
from auto_pm.domain.plc.repairer import PlcRepairer

# ── 测试数据 ──────────────────────────────────────────

# PM_SESSION 内容（含 Spec Snapshot 表格，版本号故意设旧）
_PM_SESSION_WITH_DRIFT = """# PM_SESSION_SW-2026-TEST

## 0. Meta
- project_id: SW-2026-TEST
- project_name: 测试项目

## Spec Snapshot（初始化时锁定，供后续版本漂移检测）

> 以下版本号在项目初始化时从 spec_registry.json 读取并填入。

| 规范编号 | 版本号 | 记录日期 | 说明 |
|---------|--------|---------|------|
| LSP-906 | V1.0.0 | 2026-06-06 | PLC编程错误预防规则 |
| LSP-907 | V1.0.0 | 2026-06-06 | PLC项目配置规范 |

## 其他章节

一些内容。
"""

# PM_SESSION 内容（无漂移，版本号与注册表一致）
_PM_SESSION_NO_DRIFT = """# PM_SESSION_SW-2026-TEST

## 0. Meta
- project_id: SW-2026-TEST
- project_name: 测试项目

## Spec Snapshot（初始化时锁定，供后续版本漂移检测）

| 规范编号 | 版本号 | 记录日期 | 说明 |
|---------|--------|---------|------|
| LSP-906 | V2.0.0 | 2026-06-06 | PLC编程错误预防规则 |
| LSP-907 | V1.2.1 | 2026-06-06 | PLC项目配置规范 |
"""

# PM_SESSION 内容（无 Spec Snapshot 表格）
_PM_SESSION_NO_TABLE = """# PM_SESSION_SW-2026-TEST

## 0. Meta
- project_id: SW-2026-TEST
- project_name: 测试项目

## 其他章节

无 Spec Snapshot 表格。
"""

# spec_registry.json（版本号设新）
_REGISTRY_JSON = {
    "version": "1.0.0",
    "specs": [
        {"spec_id": "LSP-906", "version": "V2.0.0", "title": "PLC编程错误预防规则"},
        {"spec_id": "LSP-907", "version": "V1.2.1", "title": "PLC项目配置规范"},
    ],
}


# ── 辅助函数 ──────────────────────────────────────────


def _setup_workspace(tmp_path: Path, pm_session_content: str) -> Path:
    """创建临时工作空间和项目目录

    Args:
        tmp_path: pytest 临时目录
        pm_session_content: PM_SESSION 文件内容

    Returns:
        项目目录路径
    """
    # 创建项目目录
    project_dir = tmp_path / "SW-2026-TEST_测试项目"
    project_dir.mkdir()

    # 写入 PM_SESSION
    (project_dir / "PM_SESSION_SW-2026-TEST.md").write_text(
        pm_session_content, encoding="utf-8"
    )

    # 写入 spec_registry.json
    registry_dir = tmp_path / "00_Obsidian_Base全局规范文件仓库"
    registry_dir.mkdir(parents=True, exist_ok=True)
    (registry_dir / "spec_registry.json").write_text(
        json.dumps(_REGISTRY_JSON, ensure_ascii=False), encoding="utf-8"
    )

    return project_dir


def _make_check_result_with_spec_snapshot_fail(project_path: str) -> CheckResult:
    """构造包含 Spec Snapshot fail 项的检查结果

    用于 mock PlcChecker.check_project，使 repair_project 进入 Spec Snapshot 修复分支。
    """
    result = CheckResult(project_path=project_path)
    result.add("Spec Snapshot", "fail", "检测到规范版本漂移")
    return result


# ── 测试类 ──────────────────────────────────────────


class TestRepairSpecSnapshot:
    """Spec Snapshot 修复测试"""

    def test_repair_spec_snapshot_auto_fix(self, tmp_path: Path) -> None:
        """自动修复（版本号更新）"""
        project_dir = _setup_workspace(tmp_path, _PM_SESSION_WITH_DRIFT)
        project_path = str(project_dir)

        repairer = PlcRepairer(str(tmp_path))

        # Mock checker 返回包含 Spec Snapshot fail 项的检查结果
        with patch.object(
            repairer._checker,
            "check_project",
            return_value=_make_check_result_with_spec_snapshot_fail(project_path),
        ):
            result = repairer.repair_project(project_path, dry_run=False)

        # 断言修复结果
        spec_actions = [a for a in result.actions if a.item == "Spec Snapshot"]
        assert len(spec_actions) == 1
        assert spec_actions[0].status == "fixed"
        assert "LSP-906" in spec_actions[0].detail
        assert "LSP-907" in spec_actions[0].detail
        assert "V2.0.0" in spec_actions[0].detail
        assert "V1.2.1" in spec_actions[0].detail
        assert "更新 2 条规范版本" in spec_actions[0].detail

        # 读取修复后的 PM_SESSION，确认版本号已更新
        pm_session_path = project_dir / "PM_SESSION_SW-2026-TEST.md"
        content = pm_session_path.read_text(encoding="utf-8")
        assert "| LSP-906 | V2.0.0 |" in content
        assert "| LSP-907 | V1.2.1 |" in content
        # 旧版本号不应再出现
        assert "| LSP-906 | V1.0.0 |" not in content
        assert "| LSP-907 | V1.0.0 |" not in content

    def test_repair_spec_snapshot_dry_run(self, tmp_path: Path) -> None:
        """dry-run 预览（不修改文件）"""
        project_dir = _setup_workspace(tmp_path, _PM_SESSION_WITH_DRIFT)
        project_path = str(project_dir)

        repairer = PlcRepairer(str(tmp_path))

        # Mock checker 返回包含 Spec Snapshot fail 项的检查结果
        with patch.object(
            repairer._checker,
            "check_project",
            return_value=_make_check_result_with_spec_snapshot_fail(project_path),
        ):
            result = repairer.repair_project(project_path, dry_run=True)

        # 断言修复结果（dry_run 模式应跳过）
        spec_actions = [a for a in result.actions if a.item == "Spec Snapshot"]
        assert len(spec_actions) == 1
        assert spec_actions[0].status == "skipped"
        assert "将更新" in spec_actions[0].detail
        assert "LSP-906" in spec_actions[0].detail
        assert "LSP-907" in spec_actions[0].detail
        assert "V2.0.0" in spec_actions[0].detail
        assert "V1.2.1" in spec_actions[0].detail

        # 读取 PM_SESSION，确认版本号未变
        pm_session_path = project_dir / "PM_SESSION_SW-2026-TEST.md"
        content = pm_session_path.read_text(encoding="utf-8")
        assert "| LSP-906 | V1.0.0 |" in content
        assert "| LSP-907 | V1.0.0 |" in content

    def test_repair_spec_snapshot_no_drift(self, tmp_path: Path) -> None:
        """无漂移时跳过修复"""
        project_dir = _setup_workspace(tmp_path, _PM_SESSION_NO_DRIFT)
        project_path = str(project_dir)

        repairer = PlcRepairer(str(tmp_path))

        # Mock checker 返回包含 Spec Snapshot fail 项的检查结果
        # （即使 checker 报告 fail，repairer 内部重新分析发现无漂移应跳过）
        with patch.object(
            repairer._checker,
            "check_project",
            return_value=_make_check_result_with_spec_snapshot_fail(project_path),
        ):
            result = repairer.repair_project(project_path, dry_run=False)

        # 断言修复结果（无漂移应跳过）
        spec_actions = [a for a in result.actions if a.item == "Spec Snapshot"]
        assert len(spec_actions) == 1
        assert spec_actions[0].status == "skipped"
        assert "无版本漂移" in spec_actions[0].detail

        # 读取 PM_SESSION，确认版本号未变
        pm_session_path = project_dir / "PM_SESSION_SW-2026-TEST.md"
        content = pm_session_path.read_text(encoding="utf-8")
        assert "| LSP-906 | V2.0.0 |" in content
        assert "| LSP-907 | V1.2.1 |" in content

    def test_repair_spec_snapshot_missing_table(self, tmp_path: Path) -> None:
        """Spec Snapshot 缺失时补齐基线章节"""
        project_dir = _setup_workspace(tmp_path, _PM_SESSION_NO_TABLE)
        project_path = str(project_dir)

        repairer = PlcRepairer(str(tmp_path))

        # Mock checker 返回包含 Spec Snapshot fail 项的检查结果
        with patch.object(
            repairer._checker,
            "check_project",
            return_value=_make_check_result_with_spec_snapshot_fail(project_path),
        ):
            result = repairer.repair_project(project_path, dry_run=False)

        # 断言修复结果（Spec Snapshot 缺失应补齐）
        spec_actions = [a for a in result.actions if a.item == "Spec Snapshot"]
        assert len(spec_actions) == 1
        assert spec_actions[0].status == "fixed"
        assert "补齐 Spec Snapshot 区块" in spec_actions[0].action
        assert "写入" in spec_actions[0].detail

        # 读取 PM_SESSION，确认基线章节已生成
        pm_session_path = project_dir / "PM_SESSION_SW-2026-TEST.md"
        content = pm_session_path.read_text(encoding="utf-8")
        assert "## Spec Snapshot" in content
        assert "| LSP-906 | V2.0.0 |" in content
        assert "| LSP-907 | V1.2.1 |" in content
