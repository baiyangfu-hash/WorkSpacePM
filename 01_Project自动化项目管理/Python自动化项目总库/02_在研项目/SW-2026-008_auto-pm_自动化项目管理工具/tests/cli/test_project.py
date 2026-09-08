"""project CLI 命令测试"""

from __future__ import annotations

import json
from pathlib import Path

from auto_pm.cli.__main__ import cli
from click.testing import CliRunner


def test_project_list_via_main(cli_runner: CliRunner, tmp_workspace: Path) -> None:
    """通过主入口测试 project list"""
    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_workspace), "project", "list"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "DJ-2026-TEST" in result.output or "DJ-2026" in result.output


def test_project_show_via_main(cli_runner: CliRunner, tmp_workspace: Path) -> None:
    """通过主入口测试 project show"""
    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_workspace), "project", "show", "DJ-2026-TEST"],
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert "DJ-2026-TEST" in result.output or "DJ-2026" in result.output


def test_project_show_not_found(cli_runner: CliRunner, tmp_workspace: Path) -> None:
    """测试 show 不存在的项目"""
    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_workspace), "project", "show", "NOT-EXIST"],
    )
    assert result.exit_code == 1


def test_project_show_displays_v040_metadata(cli_runner: CliRunner, tmp_path: Path) -> None:
    """project show 展示 Week 2 项目元数据"""
    project_dir = tmp_path / "DJ-2026-020_单机项目"
    project_dir.mkdir()
    (project_dir / ".copier-answers.yml").write_text(
        "\n".join(
            [
                "project_id: DJ-2026-020",
                "project_name: 单机项目",
                "stack: plc",
                "project_type: single_machine",
                "equipment_type: conveyor",
                "plc_vendor: Siemens",
                "plc_model: S7-1200",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "project", "show", "DJ-2026-020"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "项目类型" in result.output
    assert "单机设备" in result.output
    assert "设备类型" in result.output
    assert "输送设备" in result.output
    assert "PLC品牌" in result.output
    assert "Siemens" in result.output
    assert "PLC型号" in result.output
    assert "S7-1200" in result.output


def test_project_show_displays_week3_asset_summary(cli_runner: CliRunner, tmp_path: Path) -> None:
    """project show 展示 Week 3 工程资产摘要"""
    project_dir = tmp_path / "DJ-2026-023_资产项目"
    (project_dir / "02_PLC程序" / "工程资产").mkdir(parents=True)
    (project_dir / ".copier-answers.yml").write_text(
        "\n".join(
            [
                "project_id: DJ-2026-023",
                "project_name: 资产项目",
                "stack: plc",
                "project_type: single_machine",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (project_dir / "02_PLC程序" / "工程资产" / "io_points.csv").write_text(
        "\n".join(
            [
                "station,signal_type,address,tag,signal_name,device,comment",
                "common,DI,I0.0,ESTOP_OK,急停回路正常,操作台,TRUE=安全链路闭合",
                "",
            ]
        ),
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

    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "project", "show", "DJ-2026-023"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "工程资产" in result.output
    assert "健康" in result.output
    assert "IO点表" in result.output
    assert "1 条" in result.output
    assert "程序块" in result.output
    assert "通讯对象" in result.output


def test_project_show_json_contains_asset_summary(cli_runner: CliRunner, tmp_path: Path) -> None:
    """project show --json 输出工程资产摘要"""
    project_dir = tmp_path / "DJ-2026-024_JSON项目"
    (project_dir / "02_PLC程序" / "工程资产").mkdir(parents=True)
    (project_dir / ".copier-answers.yml").write_text(
        "\n".join(
            [
                "project_id: DJ-2026-024",
                "project_name: JSON项目",
                "stack: plc",
                "project_type: single_machine",
                "",
            ]
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

    result = cli_runner.invoke(
        cli,
        ["-w", str(tmp_path), "project", "show", "DJ-2026-024", "--json"],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    asset_summary = payload["extra"]["asset_summary"]
    assert asset_summary["status"] == "healthy"
    assert asset_summary["io_points"]["count"] == 1
    assert asset_summary["program_blocks"]["count"] == 1
    assert asset_summary["communications"]["count"] == 1


def test_project_create_dry_run_displays_v040_metadata(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    """project create --dry-run 输出 Week 2 元数据"""
    result = cli_runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "project",
            "create",
            "--stack",
            "plc",
            "--id",
            "DJ-2026-021",
            "--name",
            "测试单机",
            "--project-type",
            "single_machine",
            "--equipment-type",
            "conveyor",
            "--plc-vendor",
            "Siemens",
            "--plc-model",
            "S7-1200",
            "--dry-run",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "项目类型: single_machine" in result.output
    assert "设备类型: conveyor" in result.output
    assert "PLC 品牌: Siemens" in result.output
    assert "PLC 型号: S7-1200" in result.output


def test_project_create_single_machine_generates_week2_template_assets(
    cli_runner: CliRunner, tmp_path: Path
) -> None:
    """project create 真实生成 Week 2 单机模板差异"""
    # V1.0.1: 默认项目存放目录改为 auto-pm 工具目录下 0100_项目/，
    # 测试中显式指定 --dest-dir 以保持隔离（避免污染真实工具目录）
    dest_dir = tmp_path / "0100_项目"
    result = cli_runner.invoke(
        cli,
        [
            "-w",
            str(tmp_path),
            "project",
            "create",
            "--stack",
            "plc",
            "--id",
            "DJ-2026-022",
            "--name",
            "周单机模板",
            "--project-type",
            "single_machine",
            "--equipment-type",
            "conveyor",
            "--plc-vendor",
            "Siemens",
            "--plc-model",
            "S7-1200",
            "--dest-dir",
            str(dest_dir),
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    project_dir = dest_dir / "DJ-2026-022_周单机模板"
    assert (project_dir / "01_启动" / "003_DJ-2026-022_项目立项表_PROJ.md").exists()
    assert (project_dir / "02_PLC程序" / "工程资产" / "io_points.csv").exists()
    assert (project_dir / "02_PLC程序" / "工程资产" / "program_blocks.yml").exists()
    assert (project_dir / "02_PLC程序" / "工程资产" / "communications.yml").exists()
    assert (project_dir / "02_PLC程序" / "PLC_ST" / ".plc.json").exists()

    plc_json = json.loads(
        (project_dir / "02_PLC程序" / "PLC_ST" / ".plc.json").read_text(encoding="utf-8")
    )
    assert plc_json["project_type"] == "single_machine"
    assert plc_json["equipment_type"] == "conveyor"
    assert plc_json["plc_vendor"] == "Siemens"
    assert plc_json["plc_model"] == "S7-1200"
    assert plc_json["libraries"] == ["../../../01_SharedLibraries/SysLib"]


# ── project snapshot 命令测试（V0.3.2 独立 Spec Snapshot 刷新） ──

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


def _setup_snapshot_workspace(
    tmp_path: Path, pm_session_content: str, with_registry: bool = True
) -> Path:
    """创建临时工作空间和项目目录（含 spec_registry.json）

    Args:
        tmp_path: pytest 临时目录
        pm_session_content: PM_SESSION 文件内容
        with_registry: 是否创建 spec_registry.json

    Returns:
        工作空间根目录路径（tmp_path）
    """
    # 创建项目目录（使用 .copier-answers.yml 标志文件以便 ProjectService 识别）
    project_dir = tmp_path / "SW-2026-TEST_测试项目"
    project_dir.mkdir()
    (project_dir / ".copier-answers.yml").write_text(
        "project_id: SW-2026-TEST\nproject_name: 测试项目\n",
        encoding="utf-8",
    )

    # 写入 PM_SESSION
    (project_dir / "PM_SESSION_SW-2026-TEST.md").write_text(pm_session_content, encoding="utf-8")

    # 写入 spec_registry.json
    if with_registry:
        registry_dir = tmp_path / "00_Obsidian_Base全局规范文件仓库"
        registry_dir.mkdir(parents=True, exist_ok=True)
        (registry_dir / "spec_registry.json").write_text(
            json.dumps(_REGISTRY_JSON, ensure_ascii=False), encoding="utf-8"
        )

    return tmp_path


def _setup_retrofit_workspace(tmp_path: Path, pm_session_content: str) -> Path:
    """创建缺少 .copier-answers.yml 且 PM_SESSION 无 Spec Snapshot 的 PLC 项目"""
    project_dir = tmp_path / "DJ-2026-TEST_补齐项目"
    project_dir.mkdir()
    (project_dir / ".plc.json").write_text(
        json.dumps(
            {
                "name": "DJ-2026-TEST",
                "version": "V1.0.0",
                "description": "补齐项目",
                "type": "standard",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (project_dir / "PM_SESSION_DJ-2026-TEST.md").write_text(pm_session_content, encoding="utf-8")

    registry_dir = tmp_path / "00_Obsidian_Base全局规范文件仓库"
    registry_dir.mkdir(parents=True, exist_ok=True)
    (registry_dir / "spec_registry.json").write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "specs": {
                    "PM-042": {"version": "V2.4.0"},
                    "DEV-001": {"version": "V1.1.0"},
                    "PROJ-016": {"version": "V1.0.0"},
                    "LSP-905": {"version": "V1.2.0"},
                    "LSP-906": {"version": "V2.1.0"},
                    "LSP-907": {"version": "V1.3.0"},
                    "TOOL-908": {"version": "V1.0.0"},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return tmp_path


class TestProjectSnapshot:
    """project snapshot 命令测试"""

    def test_snapshot_with_drift_updates_versions(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        """有漂移时更新版本号"""
        workspace = _setup_snapshot_workspace(tmp_path, _PM_SESSION_WITH_DRIFT)
        result = cli_runner.invoke(
            cli,
            ["-w", str(workspace), "project", "snapshot", "SW-2026-TEST"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Spec Snapshot 已更新" in result.output
        assert "LSP-906" in result.output
        assert "V1.0.0 → V2.0.0" in result.output
        assert "LSP-907" in result.output
        assert "V1.0.0 → V1.2.1" in result.output

        # 验证文件已更新
        pm_session = tmp_path / "SW-2026-TEST_测试项目" / "PM_SESSION_SW-2026-TEST.md"
        content = pm_session.read_text(encoding="utf-8")
        assert "| LSP-906 | V2.0.0 |" in content
        assert "| LSP-907 | V1.2.1 |" in content
        assert "| LSP-906 | V1.0.0 |" not in content

    def test_snapshot_dry_run_does_not_modify(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """dry-run 模式不修改文件"""
        workspace = _setup_snapshot_workspace(tmp_path, _PM_SESSION_WITH_DRIFT)
        result = cli_runner.invoke(
            cli,
            ["-w", str(workspace), "project", "snapshot", "SW-2026-TEST", "--dry-run"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "[DRY-RUN]" in result.output
        assert "LSP-906" in result.output

        # 验证文件未被修改
        pm_session = tmp_path / "SW-2026-TEST_测试项目" / "PM_SESSION_SW-2026-TEST.md"
        content = pm_session.read_text(encoding="utf-8")
        assert "| LSP-906 | V1.0.0 |" in content
        assert "| LSP-906 | V2.0.0 |" not in content

    def test_snapshot_no_drift(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """无漂移时输出已是最新"""
        workspace = _setup_snapshot_workspace(tmp_path, _PM_SESSION_NO_DRIFT)
        result = cli_runner.invoke(
            cli,
            ["-w", str(workspace), "project", "snapshot", "SW-2026-TEST"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "已是最新" in result.output

    def test_snapshot_not_found(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """项目不存在时报错"""
        workspace = _setup_snapshot_workspace(tmp_path, _PM_SESSION_WITH_DRIFT)
        result = cli_runner.invoke(
            cli,
            ["-w", str(workspace), "project", "snapshot", "NOT-EXIST"],
        )
        assert result.exit_code == 1
        assert "项目不存在" in result.output

    def test_snapshot_no_table(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """PM_SESSION 缺少 Spec Snapshot 表格时报错"""
        workspace = _setup_snapshot_workspace(tmp_path, _PM_SESSION_NO_TABLE)
        result = cli_runner.invoke(
            cli,
            ["-w", str(workspace), "project", "snapshot", "SW-2026-TEST"],
        )
        assert result.exit_code == 1
        assert "缺少 Spec Snapshot 表格" in result.output

    def test_snapshot_no_registry(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """spec_registry.json 不存在时报错"""
        workspace = _setup_snapshot_workspace(tmp_path, _PM_SESSION_WITH_DRIFT, with_registry=False)
        result = cli_runner.invoke(
            cli,
            ["-w", str(workspace), "project", "snapshot", "SW-2026-TEST"],
        )
        assert result.exit_code == 1
        assert "spec_registry.json" in result.output

    def test_snapshot_json_output(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """JSON 输出格式（dry-run）"""
        workspace = _setup_snapshot_workspace(tmp_path, _PM_SESSION_WITH_DRIFT)
        result = cli_runner.invoke(
            cli,
            [
                "-w",
                str(workspace),
                "project",
                "snapshot",
                "SW-2026-TEST",
                "--dry-run",
                "--json",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["dry_run"] is True
        assert data["updated"] is False
        assert len(data["drifts"]) == 2
        spec_ids = {d["spec_id"] for d in data["drifts"]}
        assert spec_ids == {"LSP-906", "LSP-907"}

    def test_snapshot_json_output_no_drift(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        """JSON 输出格式（无漂移）"""
        workspace = _setup_snapshot_workspace(tmp_path, _PM_SESSION_NO_DRIFT)
        result = cli_runner.invoke(
            cli,
            [
                "-w",
                str(workspace),
                "project",
                "snapshot",
                "SW-2026-TEST",
                "--json",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["drifts"] == []
        assert data["updated"] is False


class TestProjectRetrofit:
    """project retrofit 命令测试"""

    def test_retrofit_populates_copier_answers_and_spec_snapshot(
        self, cli_runner: CliRunner, tmp_path: Path
    ) -> None:
        workspace = _setup_retrofit_workspace(tmp_path, _PM_SESSION_NO_TABLE.replace("SW-2026-TEST", "DJ-2026-TEST"))

        result = cli_runner.invoke(
            cli,
            ["-w", str(workspace), "project", "retrofit", "DJ-2026-TEST"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        project_dir = tmp_path / "DJ-2026-TEST_补齐项目"
        assert (project_dir / ".copier-answers.yml").exists()
        pm_session = (project_dir / "PM_SESSION_DJ-2026-TEST.md").read_text(encoding="utf-8")
        assert "## Spec Snapshot" in pm_session
        assert "| LSP-905 | V1.2.0 |" in pm_session
        assert "| LSP-907 | V1.3.0 |" in pm_session


def _setup_doc_refresh_workspace(tmp_path: Path) -> Path:
    """创建最小 doc refresh 测试工作空间"""
    project_dir = tmp_path / "DJ-2026-041_文档刷新项目"
    (project_dir / "02_PLC程序" / "工程资产").mkdir(parents=True)
    (project_dir / "02_PLC程序" / "程序文档").mkdir(parents=True)
    (project_dir / ".copier-answers.yml").write_text(
        "\n".join(
            [
                "project_id: DJ-2026-041",
                "project_name: 文档刷新项目",
                "stack: plc",
                "project_type: single_machine",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (project_dir / "02_PLC程序" / "工程资产" / "io_points.csv").write_text(
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
    (project_dir / "02_PLC程序" / "程序文档" / "016_DJ-2026-041_PLC程序设计总文档_PLC.md").write_text(
        "\n".join(
            [
                "# PLC程序设计总文档",
                "",
                "## 4. 软件架构",
                "",
                "### 4.1 组件清单与职责",
                "",
                "<!-- AUTO_PM:BEGIN plc-program-components -->",
                "旧内容",
                "<!-- AUTO_PM:END plc-program-components -->",
                "",
                "## 8. 关联文档索引",
                "",
                "<!-- AUTO_PM:BEGIN plc-asset-index -->",
                "旧索引",
                "<!-- AUTO_PM:END plc-asset-index -->",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (project_dir / "02_PLC程序" / "程序文档" / "015_DJ-2026-041_IO分配表_IO.md").write_text(
        "\n".join(
            [
                "# IO分配表",
                "",
                "## 2. IO 总览",
                "",
                "<!-- AUTO_PM:BEGIN plc-io-overview -->",
                "旧IO概览",
                "<!-- AUTO_PM:END plc-io-overview -->",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return tmp_path


class TestDocRefresh:
    """doc refresh 命令测试"""

    def test_doc_refresh_dry_run_does_not_modify(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        workspace = _setup_doc_refresh_workspace(tmp_path)
        target_doc = (
            workspace
            / "DJ-2026-041_文档刷新项目"
            / "02_PLC程序"
            / "程序文档"
            / "016_DJ-2026-041_PLC程序设计总文档_PLC.md"
        )
        result = cli_runner.invoke(
            cli,
            ["-w", str(workspace), "doc", "refresh", "DJ-2026-041", "--dry-run"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert "[DRY-RUN]" in result.output
        assert "plc-program-components" in result.output
        assert "旧内容" in target_doc.read_text(encoding="utf-8")

    def test_doc_refresh_json_output(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        workspace = _setup_doc_refresh_workspace(tmp_path)
        result = cli_runner.invoke(
            cli,
            ["-w", str(workspace), "doc", "refresh", "DJ-2026-041", "--dry-run", "--json"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        payload = json.loads(result.output)
        assert payload["project_id"] == "DJ-2026-041"
        assert payload["dry_run"] is True
        assert len(payload["refreshed_files"]) == 2

    def test_doc_refresh_after_project_create(self, cli_runner: CliRunner, tmp_path: Path) -> None:
        # V1.0.1: 默认项目存放目录改为 auto-pm 工具目录下 0100_项目/，
        # 测试中显式指定 --dest-dir 以保持隔离（避免污染真实工具目录）
        dest_dir = tmp_path / "0100_项目"
        create_result = cli_runner.invoke(
            cli,
            [
                "-w",
                str(tmp_path),
                "project",
                "create",
                "--stack",
                "plc",
                "--id",
                "DJ-2026-042",
                "--name",
                "文档刷新集成",
                "--project-type",
                "single_machine",
                "--equipment-type",
                "conveyor",
                "--plc-vendor",
                "Siemens",
                "--plc-model",
                "S7-1200",
                "--dest-dir",
                str(dest_dir),
            ],
            catch_exceptions=False,
        )
        assert create_result.exit_code == 0

        result = cli_runner.invoke(
            cli,
            ["-w", str(tmp_path), "doc", "refresh", "DJ-2026-042"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "文档自动区处理完成" in result.output

        project_dir = dest_dir / "DJ-2026-042_文档刷新集成"
        program_doc = next(
            (project_dir / "02_PLC程序" / "程序文档").glob("*PLC程序设计总文档_PLC.md")
        )
        content = program_doc.read_text(encoding="utf-8")
        assert "auto-pm doc refresh" in content
        assert "program_blocks.yml" in content
