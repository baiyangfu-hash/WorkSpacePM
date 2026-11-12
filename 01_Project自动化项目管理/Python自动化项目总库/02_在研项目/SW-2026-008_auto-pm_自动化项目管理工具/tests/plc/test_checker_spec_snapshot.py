"""PlcChecker 的 Spec Snapshot 检查项已退役（TD-SW008-561）

这一项读 PM_SESSION 里的 Spec Snapshot 表（PM_SESSION 已于 2026-10-10 退役），老工程永远报失败。
原来的五个场景（无漂移、主版本漂移、次版本漂移、快照表缺失、规范注册表缺失）都保留，改成断言：
检查器不再出这一项，也不会因为快照漂移让检查失败。
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


def _assert_retired(result: Any) -> None:
    """检查结果里没有 Spec Snapshot 这一项，也没有任何一项的说明在讲快照漂移。"""
    assert [i.item for i in result.items if i.item == "Spec Snapshot"] == []
    assert not any("漂移" in cast(CheckItem, i).message for i in result.items)


def _registry_three(v906: str = "V1.0.0", v907: str = "V1.0.0") -> dict[str, Any]:
    return {
        "LSP-905": {"version": "V1.0.2", "title": "SCL编程规范"},
        "LSP-906": {"version": v906, "title": "PLC编程错误预防规则"},
        "LSP-907": {"version": v907, "title": "PLC项目配置规范"},
    }


# ── 测试用例 ──────────────────────────────────────────


class TestSpecSnapshotCheck:
    """Spec Snapshot 检查项退役：五个老场景都不再出这一项"""

    def _session(self, project_id: str) -> str:
        return _PM_SESSION_TEMPLATE.format(project_id=project_id, v905="V1.0.2", v906="V1.0.0", v907="V1.0.0")

    def test_spec_snapshot_no_drift(self, tmp_path: Path) -> None:
        """无漂移：以前 PASS，现在不出这一项"""
        project_dir = _create_project(tmp_path, "DJ-2026-001", self._session("DJ-2026-001"))
        _write_registry(tmp_path, _registry_three())
        _assert_retired(PlcChecker(str(tmp_path)).check_project(str(project_dir)))

    def test_spec_snapshot_major_drift(self, tmp_path: Path) -> None:
        """主版本漂移：以前 FAIL（005、011、SysLib 永远红在这里），现在不出这一项、不因它失败"""
        project_dir = _create_project(tmp_path, "DJ-2026-002", self._session("DJ-2026-002"))
        _write_registry(tmp_path, _registry_three(v906="V2.0.0"))
        result = PlcChecker(str(tmp_path)).check_project(str(project_dir))
        _assert_retired(result)
        assert not any(i.status == "fail" and "LSP-906" in i.message for i in result.items)

    def test_spec_snapshot_minor_drift(self, tmp_path: Path) -> None:
        """次版本漂移：以前 WARN，现在不出这一项"""
        project_dir = _create_project(tmp_path, "DJ-2026-003", self._session("DJ-2026-003"))
        _write_registry(tmp_path, _registry_three(v907="V1.2.1"))
        _assert_retired(PlcChecker(str(tmp_path)).check_project(str(project_dir)))

    def test_spec_snapshot_missing_table(self, tmp_path: Path) -> None:
        """快照表缺失：以前 WARN，现在不出这一项"""
        project_dir = _create_project(tmp_path, "DJ-2026-004", _PM_SESSION_NO_TABLE.format(project_id="DJ-2026-004"))
        _write_registry(tmp_path, {"LSP-905": {"version": "V1.0.2", "title": "SCL编程规范"}})
        _assert_retired(PlcChecker(str(tmp_path)).check_project(str(project_dir)))

    def test_spec_snapshot_registry_missing(self, tmp_path: Path) -> None:
        """规范注册表缺失：以前 WARN，现在不出这一项"""
        project_dir = _create_project(tmp_path, "DJ-2026-005", self._session("DJ-2026-005"))
        result = PlcChecker(str(tmp_path)).check_project(str(project_dir))
        _assert_retired(result)
        assert not any("spec_registry.json" in i.message for i in result.items)

    def test_the_check_list_no_longer_offers_the_item(self) -> None:
        """plc check --list 也不再列这一项"""
        assert all(item["item"] != "Spec Snapshot" for item in PlcChecker.CHECK_ITEMS)

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
