"""PlcChecker Spec Snapshot 检查项单元测试（V2.0.3 规范漂移检测）

覆盖场景：
- 无漂移（PASS）
- 主版本漂移（FAIL）
- 次版本漂移（WARN）
- Spec Snapshot 表格缺失（WARN）
- spec_registry.json 缺失（WARN）
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from auto_pm.domain.plc.checker import PlcChecker
from auto_pm.domain.plc.models import CheckItem

# ── 辅助常量 ──────────────────────────────────────────

# PM_SESSION 模板（含 Spec Snapshot 表格）
_PM_SESSION_TEMPLATE = """# PM_SESSION_{project_id}

## Spec Snapshot（初始化时锁定，供后续版本漂移检测）

| 规范编号 | 版本号 | 记录日期 | 说明 |
|---------|--------|---------|------|
| LSP-905 | {v905} | 2026-06-06 | SCL编程规范 |
| LSP-906 | {v906} | 2026-06-06 | PLC编程错误预防规则 |
| LSP-907 | {v907} | 2026-06-06 | PLC项目配置规范 |

## 其他章节

一些内容。
"""

# PM_SESSION 模板（无 Spec Snapshot 表格）
_PM_SESSION_NO_TABLE = """# PM_SESSION_{project_id}

## 其他章节

无 Spec Snapshot 表格。
"""


# ── 辅助函数 ──────────────────────────────────────────


def _create_project(
    tmp_path: Path,
    project_id: str,
    pm_session_content: str,
) -> Path:
    """创建临时项目目录，含 .plc.json 和 PM_SESSION，返回项目路径"""
    project_dir = tmp_path / f"{project_id}_测试项目"
    project_dir.mkdir()

    # .plc.json
    (project_dir / ".plc.json").write_text(
        json.dumps(
            {
                "name": project_id,
                "version": "V1.0.0",
                "description": "测试项目",
                "type": "standard",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # PM_SESSION
    (project_dir / f"PM_SESSION_{project_id}.md").write_text(
        pm_session_content, encoding="utf-8"
    )

    return project_dir


def _write_registry(tmp_path: Path, specs: dict[str, Any]) -> None:
    """在工作空间根目录下写入 spec_registry.json（dict 形式 specs）"""
    registry_dir = tmp_path / "00_Obsidian_Base全局规范文件仓库"
    registry_dir.mkdir(parents=True, exist_ok=True)
    (registry_dir / "spec_registry.json").write_text(
        json.dumps({"version": "1.0.0", "specs": specs}, ensure_ascii=False),
        encoding="utf-8",
    )


def _get_spec_snapshot_item(result: Any) -> CheckItem:
    """从 CheckResult 中提取 Spec Snapshot 检查项"""
    items = [i for i in result.items if i.item == "Spec Snapshot"]
    assert items, "未找到 Spec Snapshot 检查项"
    return cast(CheckItem, items[0])


# ── 测试用例 ──────────────────────────────────────────


class TestSpecSnapshotCheck:
    """PlcChecker Spec Snapshot 检查项测试"""

    def test_spec_snapshot_no_drift(self, tmp_path: Path) -> None:
        """无漂移：Spec Snapshot 与 registry 一致 → PASS"""
        project_id = "DJ-2026-001"
        pm_session = _PM_SESSION_TEMPLATE.format(
            project_id=project_id,
            v905="V1.0.2",
            v906="V1.0.0",
            v907="V1.0.0",
        )
        project_dir = _create_project(tmp_path, project_id, pm_session)

        _write_registry(
            tmp_path,
            {
                "LSP-905": {"version": "V1.0.2", "title": "SCL编程规范"},
                "LSP-906": {"version": "V1.0.0", "title": "PLC编程错误预防规则"},
                "LSP-907": {"version": "V1.0.0", "title": "PLC项目配置规范"},
            },
        )

        checker = PlcChecker(str(tmp_path))
        result = checker.check_project(str(project_dir))

        item = _get_spec_snapshot_item(result)
        assert item.status == "pass"
        assert "一致" in item.message

    def test_spec_snapshot_major_drift(self, tmp_path: Path) -> None:
        """主版本漂移：LSP-906 V1.0.0 → V2.0.0 → FAIL"""
        project_id = "DJ-2026-002"
        pm_session = _PM_SESSION_TEMPLATE.format(
            project_id=project_id,
            v905="V1.0.2",
            v906="V1.0.0",
            v907="V1.0.0",
        )
        project_dir = _create_project(tmp_path, project_id, pm_session)

        _write_registry(
            tmp_path,
            {
                "LSP-905": {"version": "V1.0.2", "title": "SCL编程规范"},
                "LSP-906": {"version": "V2.0.0", "title": "PLC编程错误预防规则"},
                "LSP-907": {"version": "V1.0.0", "title": "PLC项目配置规范"},
            },
        )

        checker = PlcChecker(str(tmp_path))
        result = checker.check_project(str(project_dir))

        item = _get_spec_snapshot_item(result)
        assert item.status == "fail"
        assert "LSP-906" in item.message
        assert "V1.0.0" in item.message
        assert "V2.0.0" in item.message
        assert "主版本漂移" in item.message

    def test_spec_snapshot_minor_drift(self, tmp_path: Path) -> None:
        """次版本漂移：LSP-907 V1.0.0 → V1.2.1 → WARN"""
        project_id = "DJ-2026-003"
        pm_session = _PM_SESSION_TEMPLATE.format(
            project_id=project_id,
            v905="V1.0.2",
            v906="V1.0.0",
            v907="V1.0.0",
        )
        project_dir = _create_project(tmp_path, project_id, pm_session)

        _write_registry(
            tmp_path,
            {
                "LSP-905": {"version": "V1.0.2", "title": "SCL编程规范"},
                "LSP-906": {"version": "V1.0.0", "title": "PLC编程错误预防规则"},
                "LSP-907": {"version": "V1.2.1", "title": "PLC项目配置规范"},
            },
        )

        checker = PlcChecker(str(tmp_path))
        result = checker.check_project(str(project_dir))

        item = _get_spec_snapshot_item(result)
        assert item.status == "warn"
        assert "LSP-907" in item.message
        assert "V1.0.0" in item.message
        assert "V1.2.1" in item.message
        assert "次版本漂移" in item.message

    def test_spec_snapshot_missing_table(self, tmp_path: Path) -> None:
        """Spec Snapshot 表格缺失 → WARN"""
        project_id = "DJ-2026-004"
        pm_session = _PM_SESSION_NO_TABLE.format(project_id=project_id)
        project_dir = _create_project(tmp_path, project_id, pm_session)

        _write_registry(
            tmp_path,
            {
                "LSP-905": {"version": "V1.0.2", "title": "SCL编程规范"},
            },
        )

        checker = PlcChecker(str(tmp_path))
        result = checker.check_project(str(project_dir))

        item = _get_spec_snapshot_item(result)
        assert item.status == "warn"
        assert "缺少" in item.message

    def test_spec_snapshot_registry_missing(self, tmp_path: Path) -> None:
        """spec_registry.json 缺失 → WARN"""
        project_id = "DJ-2026-005"
        pm_session = _PM_SESSION_TEMPLATE.format(
            project_id=project_id,
            v905="V1.0.2",
            v906="V1.0.0",
            v907="V1.0.0",
        )
        project_dir = _create_project(tmp_path, project_id, pm_session)

        # 不创建 spec_registry.json

        checker = PlcChecker(str(tmp_path))
        result = checker.check_project(str(project_dir))

        item = _get_spec_snapshot_item(result)
        assert item.status == "warn"
        assert "spec_registry.json" in item.message

    def test_compatible_stage_dirs_do_not_fail_duplicate_check(self, tmp_path: Path) -> None:
        """01_启动 + 01_需求与设计 兼容共存时不应触发 fail"""
        project_id = "DJ-2026-006"
        project_dir = _create_project(
            tmp_path,
            project_id,
            _PM_SESSION_TEMPLATE.format(
                project_id=project_id,
                v905="V1.0.2",
                v906="V1.0.0",
                v907="V1.0.0",
            ),
        )
        for subdir in [
            "01_启动",
            "01_需求与设计",
            "02_PLC程序",
            "03_HMI设计",
            "04_现场调试",
            "05_测试与验证",
            "06_文档与交付",
            "07_技术支持",
            "08_备件管理",
            "09_项目总结",
            "10_知识库",
        ]:
            (project_dir / subdir).mkdir(exist_ok=True)

        _write_registry(
            tmp_path,
            {
                "LSP-905": {"version": "V1.0.2", "title": "SCL编程规范"},
                "LSP-906": {"version": "V1.0.0", "title": "PLC编程错误预防规则"},
                "LSP-907": {"version": "V1.0.0", "title": "PLC项目配置规范"},
            },
        )

        checker = PlcChecker(str(tmp_path))
        result = checker.check_project(str(project_dir))

        duplicate_items = [i for i in result.items if i.item == "目录唯一性与冲突排查"]
        assert duplicate_items
        assert duplicate_items[0].status == "pass"
