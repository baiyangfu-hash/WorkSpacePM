"""Spec Snapshot 解析器单元测试（V2.0.3 规范漂移检测）

覆盖场景：
- parse_spec_snapshot: 标准表格/非标准格式/文件不存在
- load_spec_registry: 正常加载/文件缺失/JSON 格式错误
- compare_versions: 主版本/次版本/补丁漂移/无漂移/snapshot 子集
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from auto_pm.domain.plc.spec_snapshot import (
    DriftItem,
    compare_versions,
    load_spec_registry,
    parse_spec_snapshot,
)

# ── 辅助常量 ──────────────────────────────────────────

# 标准表格内容（列名：规范编号/版本号）
_STANDARD_SNAPSHOT = """# PM_SESSION_DJ-2026-TEST

## Spec Snapshot（初始化时锁定，供后续版本漂移检测）

> 以下版本号在项目初始化时从 spec_registry.json 读取并填入。

| 规范编号 | 版本号 | 记录日期 | 说明 |
|---------|--------|---------|------|
| LSP-905 | V1.0.2 | 2026-06-06 | SCL编程规范 |
| LSP-906 | V1.0.0 | 2026-06-06 | PLC编程错误预防规则 |
| LSP-907 | V1.0.0 | 2026-06-06 | PLC项目配置规范 |

## 其他章节

一些内容。
"""

# 列名变体表格（spec_id/版本）
_VARIANT_SNAPSHOT = """# PM_SESSION

## Spec Snapshot

| spec_id | 版本 | 记录日期 | 说明 |
|---------|------|---------|------|
| LSP-906 | V1.0.0 | 2026-06-06 | 说明 |
"""

# 非标准格式：无表格
_NO_TABLE_SNAPSHOT = """# PM_SESSION

## Spec Snapshot

本章节无表格内容。
"""

# 非标准格式：列名不匹配
_MISMATCHED_HEADER_SNAPSHOT = """# PM_SESSION

## Spec Snapshot

| 名称 | 数值 | 日期 |
|------|------|------|
| LSP-906 | V1.0.0 | 2026-06-06 |
"""

# spec_registry.json（list 形式，对齐任务描述）
_REGISTRY_LIST_JSON = {
    "version": "1.0.0",
    "specs": [
        {"spec_id": "LSP-905", "version": "V1.0.2", "title": "SCL编程规范"},
        {"spec_id": "LSP-906", "version": "V2.0.0", "title": "PLC编程错误预防规则"},
        {"spec_id": "LSP-907", "version": "V1.2.1", "title": "PLC项目配置规范"},
        {"spec_id": "LSP-904", "version": "V1.2.0", "title": "SCL注释规范"},
    ],
}

# spec_registry.json（dict 形式，对齐实际文件结构）
_REGISTRY_DICT_JSON = {
    "version": "1.0.0",
    "specs": {
        "LSP-905": {"version": "V1.0.2", "title": "SCL编程规范"},
        "LSP-906": {"version": "V2.0.0", "title": "PLC编程错误预防规则"},
        "LSP-907": {"version": "V1.2.1", "title": "PLC项目配置规范"},
    },
}


# ── 辅助函数 ──────────────────────────────────────────


def _write_pm_session(tmp_path: Path, content: str, filename: str = "PM_SESSION.md") -> str:
    """写入临时 PM_SESSION 文件，返回路径"""
    path = tmp_path / filename
    path.write_text(content, encoding="utf-8")
    return str(path)


def _write_registry(tmp_path: Path, data: dict[str, Any]) -> str:
    """在工作空间根目录下写入 spec_registry.json，返回工作空间根路径"""
    registry_dir = tmp_path / "00_Obsidian_Base全局规范文件仓库"
    registry_dir.mkdir(parents=True, exist_ok=True)
    (registry_dir / "spec_registry.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )
    return str(tmp_path)


# ── parse_spec_snapshot 测试 ──────────────────────────


class TestParseSpecSnapshot:
    """parse_spec_snapshot 测试"""

    def test_parse_spec_snapshot_standard(self, tmp_path: Path) -> None:
        """标准表格解析（含"规范编号"/"版本号"列名）"""
        path = _write_pm_session(tmp_path, _STANDARD_SNAPSHOT)
        result = parse_spec_snapshot(path)

        assert result == {
            "LSP-905": "V1.0.2",
            "LSP-906": "V1.0.0",
            "LSP-907": "V1.0.0",
        }

    def test_parse_spec_snapshot_column_variants(self, tmp_path: Path) -> None:
        """列名变体解析（spec_id/版本）"""
        path = _write_pm_session(tmp_path, _VARIANT_SNAPSHOT)
        result = parse_spec_snapshot(path)

        assert result == {"LSP-906": "V1.0.0"}

    def test_parse_spec_snapshot_non_standard_no_table(self, tmp_path: Path) -> None:
        """非标准格式（无表格）返回空 dict"""
        path = _write_pm_session(tmp_path, _NO_TABLE_SNAPSHOT)
        result = parse_spec_snapshot(path)

        assert result == {}

    def test_parse_spec_snapshot_non_standard_mismatched_header(self, tmp_path: Path) -> None:
        """非标准格式（列名不匹配）返回空 dict"""
        path = _write_pm_session(tmp_path, _MISMATCHED_HEADER_SNAPSHOT)
        result = parse_spec_snapshot(path)

        assert result == {}

    def test_parse_spec_snapshot_no_heading(self, tmp_path: Path) -> None:
        """无 Spec Snapshot 章节返回空 dict"""
        content = "# PM_SESSION\n\n## 其他章节\n\n| 规范编号 | 版本号 |\n|------|------|\n| LSP-906 | V1.0.0 |\n"
        path = _write_pm_session(tmp_path, content)
        result = parse_spec_snapshot(path)

        assert result == {}

    def test_parse_spec_snapshot_file_not_found(self, tmp_path: Path) -> None:
        """文件不存在返回空 dict，不抛异常"""
        path = str(tmp_path / "nonexistent.md")
        result = parse_spec_snapshot(path)

        assert result == {}


# ── load_spec_registry 测试 ───────────────────────────


class TestLoadSpecRegistry:
    """load_spec_registry 测试"""

    def test_load_spec_registry_normal_list_form(self, tmp_path: Path) -> None:
        """正常加载 spec_registry.json（list 形式）"""
        ws_root = _write_registry(tmp_path, _REGISTRY_LIST_JSON)
        result = load_spec_registry(ws_root)

        assert result is not None
        assert result["LSP-905"] == "V1.0.2"
        assert result["LSP-906"] == "V2.0.0"
        assert result["LSP-907"] == "V1.2.1"
        assert result["LSP-904"] == "V1.2.0"

    def test_load_spec_registry_normal_dict_form(self, tmp_path: Path) -> None:
        """正常加载 spec_registry.json（dict 形式，对齐实际文件结构）"""
        ws_root = _write_registry(tmp_path, _REGISTRY_DICT_JSON)
        result = load_spec_registry(ws_root)

        assert result is not None
        assert result["LSP-905"] == "V1.0.2"
        assert result["LSP-906"] == "V2.0.0"
        assert result["LSP-907"] == "V1.2.1"

    def test_load_spec_registry_missing(self, tmp_path: Path) -> None:
        """文件缺失返回 None"""
        result = load_spec_registry(str(tmp_path))

        assert result is None

    def test_load_spec_registry_invalid_json(self, tmp_path: Path) -> None:
        """JSON 格式错误返回 None"""
        registry_dir = tmp_path / "00_Obsidian_Base全局规范文件仓库"
        registry_dir.mkdir(parents=True, exist_ok=True)
        (registry_dir / "spec_registry.json").write_text(
            "{invalid json content", encoding="utf-8"
        )

        result = load_spec_registry(str(tmp_path))

        assert result is None


# ── compare_versions 测试 ─────────────────────────────


class TestCompareVersions:
    """compare_versions 测试"""

    def test_compare_versions_major(self) -> None:
        """主版本漂移（V1.0.0→V2.0.0）"""
        snapshot = {"LSP-906": "V1.0.0"}
        registry = {"LSP-906": "V2.0.0"}

        drifts = compare_versions(snapshot, registry)

        assert len(drifts) == 1
        drift = drifts[0]
        assert drift.spec_id == "LSP-906"
        assert drift.snapshot_version == "V1.0.0"
        assert drift.registry_version == "V2.0.0"
        assert drift.drift_level == "major"

    def test_compare_versions_minor(self) -> None:
        """次版本漂移（V1.0.0→V1.2.0）"""
        snapshot = {"LSP-907": "V1.0.0"}
        registry = {"LSP-907": "V1.2.0"}

        drifts = compare_versions(snapshot, registry)

        assert len(drifts) == 1
        drift = drifts[0]
        assert drift.spec_id == "LSP-907"
        assert drift.snapshot_version == "V1.0.0"
        assert drift.registry_version == "V1.2.0"
        assert drift.drift_level == "minor"

    def test_compare_versions_patch(self) -> None:
        """补丁漂移（V1.0.0→V1.0.1）"""
        snapshot = {"LSP-905": "V1.0.0"}
        registry = {"LSP-905": "V1.0.1"}

        drifts = compare_versions(snapshot, registry)

        assert len(drifts) == 1
        drift = drifts[0]
        assert drift.spec_id == "LSP-905"
        assert drift.snapshot_version == "V1.0.0"
        assert drift.registry_version == "V1.0.1"
        assert drift.drift_level == "patch"

    def test_compare_versions_no_drift(self) -> None:
        """无漂移返回空列表"""
        snapshot = {"LSP-906": "V1.0.0", "LSP-907": "V1.2.1"}
        registry = {"LSP-906": "V1.0.0", "LSP-907": "V1.2.1"}

        drifts = compare_versions(snapshot, registry)

        assert drifts == []

    def test_compare_versions_snapshot_subset(self) -> None:
        """snapshot 是 registry 的子集，仅对比 snapshot 中存在的规范"""
        snapshot = {"LSP-906": "V1.0.0", "LSP-907": "V1.0.0"}
        registry = {
            "LSP-906": "V2.0.0",
            "LSP-907": "V1.0.0",  # 无漂移
            "LSP-904": "V1.2.0",  # 不在 snapshot 中，不对比
            "LSP-905": "V1.0.2",  # 不在 snapshot 中，不对比
        }

        drifts = compare_versions(snapshot, registry)

        # 仅 LSP-906 有漂移
        assert len(drifts) == 1
        assert drifts[0].spec_id == "LSP-906"
        assert drifts[0].drift_level == "major"

    def test_compare_versions_missing_in_registry(self) -> None:
        """snapshot 中的规范不在 registry 中时跳过"""
        snapshot = {"UNKNOWN-001": "V1.0.0", "LSP-906": "V1.0.0"}
        registry = {"LSP-906": "V2.0.0"}

        drifts = compare_versions(snapshot, registry)

        # UNKNOWN-001 不在 registry 中，跳过；仅 LSP-906 漂移
        assert len(drifts) == 1
        assert drifts[0].spec_id == "LSP-906"

    def test_compare_versions_multiple_drifts(self) -> None:
        """多条漂移同时存在"""
        snapshot = {
            "LSP-905": "V1.0.0",  # patch 漂移
            "LSP-906": "V1.0.0",  # major 漂移
            "LSP-907": "V1.0.0",  # minor 漂移
            "LSP-904": "V1.2.0",  # 无漂移
        }
        registry = {
            "LSP-905": "V1.0.1",
            "LSP-906": "V2.0.0",
            "LSP-907": "V1.2.0",
            "LSP-904": "V1.2.0",
        }

        drifts = compare_versions(snapshot, registry)

        assert len(drifts) == 3
        drift_map = {d.spec_id: d.drift_level for d in drifts}
        assert drift_map == {
            "LSP-905": "patch",
            "LSP-906": "major",
            "LSP-907": "minor",
        }


# ── DriftItem 数据类测试 ──────────────────────────────


class TestDriftItem:
    """DriftItem dataclass 测试"""

    def test_drift_item_fields(self) -> None:
        """DriftItem 字段完整性"""
        item = DriftItem(
            spec_id="LSP-906",
            snapshot_version="V1.0.0",
            registry_version="V2.0.0",
            drift_level="major",
        )

        assert item.spec_id == "LSP-906"
        assert item.snapshot_version == "V1.0.0"
        assert item.registry_version == "V2.0.0"
        assert item.drift_level == "major"
