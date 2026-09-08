"""文档自动区注入服务测试（V0.4.1 Step 2）"""

from __future__ import annotations

from pathlib import Path

import yaml
from auto_pm.core.doc_inject_service import DocInjectService
from auto_pm.models import ProjectInfo


def _setup_legacy_doc_project(tmp_path: Path) -> tuple[ProjectInfo, Path, Path]:
    """创建历史 PLC 项目（无 AUTO_PM 标记，仅锚点标题 + 手工内容）"""
    project_dir = tmp_path / "DJ-2026-041_历史文档项目"
    asset_dir = project_dir / "02_PLC程序" / "工程资产"
    doc_dir = project_dir / "02_PLC程序" / "程序文档"
    asset_dir.mkdir(parents=True)
    doc_dir.mkdir(parents=True)

    (asset_dir / "io_points.csv").write_text(
        "\n".join(
            [
                "station,signal_type,address,tag,signal_name,device,comment",
                "common,DI,I0.0,ESTOP_OK,急停回路正常,操作台,TRUE=安全链路闭合",
                "conveyor,DO,Q0.0,CONVEYOR_RUN,输送带运行,变频器,TRUE=正转运行",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (asset_dir / "program_blocks.yml").write_text(
        yaml.safe_dump(
            {
                "blocks": [
                    {
                        "name": "OB1",
                        "type": "OB",
                        "path": "02_PLC程序/PLC_ST/OB1/OB1.scl",
                        "responsibility": "主循环与调用编排",
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (asset_dir / "communications.yml").write_text(
        yaml.safe_dump(
            {
                "channels": [
                    {
                        "name": "HMI",
                        "protocol": "ethernet",
                        "role": "人机界面",
                        "endpoint": "Siemens S7-1200",
                        "notes": "补齐 IP、端口和变量映射",
                    }
                ]
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    # 历史文档：无 marker，仅锚点标题 + 手工内容
    program_doc = doc_dir / "016_DJ-2026-041_PLC程序设计总文档_PLC.md"
    program_doc.write_text(
        "\n".join(
            [
                "# PLC程序设计总文档",
                "",
                "## 4. 软件架构",
                "",
                "### 4.1 组件清单与职责",
                "",
                "手工组件清单内容",
                "",
                "## 8. 关联文档索引",
                "",
                "手工关联文档索引",
                "",
            ]
        ),
        encoding="utf-8",
    )
    io_doc = doc_dir / "015_DJ-2026-041_IO分配表_IO.md"
    io_doc.write_text(
        "\n".join(
            [
                "# IO分配表",
                "",
                "## 2. IO 总览",
                "",
                "手工IO总览内容",
                "",
            ]
        ),
        encoding="utf-8",
    )

    project = ProjectInfo(
        project_id="DJ-2026-041",
        name="历史文档项目",
        path=str(project_dir),
        stack="plc",
        phase="developing",
        version="0.4.0",
        description="V0.4.1 Step 2 历史项目注入测试",
        extra={},
    )
    return project, program_doc, io_doc


def test_inject_markers_standard_injection(tmp_path: Path) -> None:
    """标准注入：无 marker + 锚点存在 → 注入成功"""
    project, program_doc, io_doc = _setup_legacy_doc_project(tmp_path)
    service = DocInjectService(str(tmp_path))

    result = service.inject_markers(project, dry_run=False)

    assert result.updated is True
    assert len(result.injected_files) == 2

    program_content = program_doc.read_text(encoding="utf-8")
    io_content = io_doc.read_text(encoding="utf-8")

    # program-components marker 已注入
    assert "<!-- AUTO_PM:BEGIN plc-program-components -->" in program_content
    assert "<!-- AUTO_PM:END plc-program-components -->" in program_content
    # asset-index marker 已注入
    assert "<!-- AUTO_PM:BEGIN plc-asset-index -->" in program_content
    assert "<!-- AUTO_PM:END plc-asset-index -->" in program_content
    # io-overview marker 已注入
    assert "<!-- AUTO_PM:BEGIN plc-io-overview -->" in io_content
    assert "<!-- AUTO_PM:END plc-io-overview -->" in io_content
    # 注入内容来自工程资产数据
    assert "OB1" in program_content
    assert "io_points.csv" in program_content
    assert "### 2.1 自动区刷新摘要" in io_content


def test_inject_markers_preserves_original_content(tmp_path: Path) -> None:
    """原内容保留：注入后原手工内容仍在 marker 之后"""
    project, program_doc, io_doc = _setup_legacy_doc_project(tmp_path)
    service = DocInjectService(str(tmp_path))

    result = service.inject_markers(project, dry_run=False)

    program_content = program_doc.read_text(encoding="utf-8")
    io_content = io_doc.read_text(encoding="utf-8")

    # 原手工内容仍在
    assert "手工组件清单内容" in program_content
    assert "手工关联文档索引" in program_content
    assert "手工IO总览内容" in io_content

    # 原内容应在 END 标记之后（验证顺序）
    end_pos = program_content.find("<!-- AUTO_PM:END plc-program-components -->")
    original_pos = program_content.find("手工组件清单内容")
    assert end_pos >= 0
    assert original_pos > end_pos, "原手工内容应在 END 标记之后"

    # 验证注入文件结构
    assert len(result.injected_files) == 2
    for item in result.injected_files:
        assert item.changed is True
        assert len(item.injected_keys) > 0
        assert len(item.skipped_keys) == 0
        assert len(item.missing_anchors) == 0


def test_inject_markers_dry_run_does_not_write(tmp_path: Path) -> None:
    """dry-run：仅预览，不写入文档"""
    project, program_doc, io_doc = _setup_legacy_doc_project(tmp_path)
    service = DocInjectService(str(tmp_path))

    result = service.inject_markers(project, dry_run=True)

    assert result.updated is False
    assert len(result.injected_files) == 2
    # 注入预览有变更但未写入
    for item in result.injected_files:
        assert item.changed is True

    # 文档实际未被修改（无 marker）
    program_content = program_doc.read_text(encoding="utf-8")
    io_content = io_doc.read_text(encoding="utf-8")
    assert "AUTO_PM:BEGIN" not in program_content
    assert "AUTO_PM:BEGIN" not in io_content
    # 原手工内容保留
    assert "手工组件清单内容" in program_content
    assert "手工IO总览内容" in io_content


def test_inject_markers_skip_existing_marker(tmp_path: Path) -> None:
    """已存在 marker → 跳过（不替换内容）"""
    project, program_doc, io_doc = _setup_legacy_doc_project(tmp_path)
    # 在 program_doc 中预埋 plc-program-components marker
    program_doc.write_text(
        "\n".join(
            [
                "# PLC程序设计总文档",
                "",
                "## 4. 软件架构",
                "",
                "### 4.1 组件清单与职责",
                "",
                "<!-- AUTO_PM:BEGIN plc-program-components -->",
                "已存在的组件内容",
                "<!-- AUTO_PM:END plc-program-components -->",
                "",
                "## 8. 关联文档索引",
                "",
                "手工关联文档索引",
                "",
            ]
        ),
        encoding="utf-8",
    )
    service = DocInjectService(str(tmp_path))

    result = service.inject_markers(project, dry_run=False)

    program_content = program_doc.read_text(encoding="utf-8")

    # plc-program-components 已存在 → 跳过（保留原内容，不替换）
    assert "已存在的组件内容" in program_content
    # plc-asset-index 无 marker → 注入
    assert "<!-- AUTO_PM:BEGIN plc-asset-index -->" in program_content

    # 验证注入文件结构
    program_item = next(
        item for item in result.injected_files if item.file_path.endswith("PLC.md")
    )
    assert "plc-program-components" in program_item.skipped_keys
    assert "plc-asset-index" in program_item.injected_keys


def test_inject_markers_missing_anchor_reports_issue(tmp_path: Path) -> None:
    """锚点缺失 → 报 issue（不强制注入）"""
    project, program_doc, io_doc = _setup_legacy_doc_project(tmp_path)
    # 修改 program_doc：移除 "### 4.1 组件清单" 锚点标题
    program_doc.write_text(
        "\n".join(
            [
                "# PLC程序设计总文档",
                "",
                "## 4. 软件架构",
                "",
                "## 8. 关联文档索引",
                "",
                "手工关联文档索引",
                "",
            ]
        ),
        encoding="utf-8",
    )
    service = DocInjectService(str(tmp_path))

    result = service.inject_markers(project, dry_run=False)

    # 应有 issue 报告锚点缺失
    assert any("plc-program-components" in issue and "锚点" in issue for issue in result.issues)

    program_item = next(
        item for item in result.injected_files if item.file_path.endswith("PLC.md")
    )
    assert "plc-program-components" in program_item.missing_anchors
    # plc-asset-index 锚点存在 → 仍注入
    assert "plc-asset-index" in program_item.injected_keys

    program_content = program_doc.read_text(encoding="utf-8")
    # 缺失锚点的 marker 不应被注入
    assert "AUTO_PM:BEGIN plc-program-components" not in program_content
    # 存在锚点的 marker 仍被注入
    assert "AUTO_PM:BEGIN plc-asset-index" in program_content


def test_inject_markers_supports_real_project_heading_variants(tmp_path: Path) -> None:
    """兼容真实项目中的章节编号与标题变体。"""
    project, program_doc, io_doc = _setup_legacy_doc_project(tmp_path)
    program_doc.write_text(
        "\n".join(
            [
                "# PLC程序设计总文档",
                "",
                "## 5. 软件架构",
                "",
                "### 5.1 组件清单与职责",
                "",
                "手工组件清单内容",
                "",
                "## 13. 关联文档索引",
                "",
                "手工关联文档索引",
                "",
            ]
        ),
        encoding="utf-8",
    )
    io_doc.write_text(
        "\n".join(
            [
                "# IO分配表",
                "",
                "## 2. 系统硬件配置总览",
                "",
                "手工IO总览内容",
                "",
            ]
        ),
        encoding="utf-8",
    )
    service = DocInjectService(str(tmp_path))

    result = service.inject_markers(project, dry_run=False)

    assert result.updated is True
    program_content = program_doc.read_text(encoding="utf-8")
    io_content = io_doc.read_text(encoding="utf-8")
    assert "<!-- AUTO_PM:BEGIN plc-program-components -->" in program_content
    assert "<!-- AUTO_PM:BEGIN plc-asset-index -->" in program_content
    assert "<!-- AUTO_PM:BEGIN plc-io-overview -->" in io_content
    assert "手工组件清单内容" in program_content
    assert "手工IO总览内容" in io_content


def test_inject_result_to_dict_structure(tmp_path: Path) -> None:
    """to_dict 返回正确 JSON 结构"""
    project, program_doc, io_doc = _setup_legacy_doc_project(tmp_path)
    service = DocInjectService(str(tmp_path))

    result = service.inject_markers(project, dry_run=True)

    d = result.to_dict()
    assert d["project_id"] == "DJ-2026-041"
    assert d["dry_run"] is True
    assert d["updated"] is False
    assert isinstance(d["injected_files"], list)
    assert len(d["injected_files"]) == 2
    for item in d["injected_files"]:
        assert "file_path" in item
        assert "injected_keys" in item
        assert "skipped_keys" in item
        assert "missing_anchors" in item
        assert "changed" in item
        assert isinstance(item["injected_keys"], list)
        assert isinstance(item["skipped_keys"], list)
        assert isinstance(item["missing_anchors"], list)
        assert isinstance(item["changed"], bool)


def test_inject_markers_non_plc_project_reports_issue(tmp_path: Path) -> None:
    """非 PLC 项目 → 报 issue"""
    project_dir = tmp_path / "SW-2026-099_Python项目"
    project_dir.mkdir()
    project = ProjectInfo(
        project_id="SW-2026-099",
        name="Python项目",
        path=str(project_dir),
        stack="python",
        phase="developing",
        version="0.1.0",
        description="非 PLC 项目测试",
        extra={},
    )
    service = DocInjectService(str(tmp_path))

    result = service.inject_markers(project, dry_run=False)

    assert result.updated is False
    assert len(result.injected_files) == 0
    assert any("仅 PLC" in issue for issue in result.issues)
