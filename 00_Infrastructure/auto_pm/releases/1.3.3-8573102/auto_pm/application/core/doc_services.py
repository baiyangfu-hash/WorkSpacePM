"""Application services for doc sync and consistency auditing (moved from domain.doc: they drive infrastructure extractors, TD-SW008-057)."""
import json
import tomllib
from pathlib import Path

from auto_pm.domain.doc.models import DocCheckResult
from auto_pm.infrastructure.doc.extractors.bridge_ast_extractor import BridgeAstExtractor
from auto_pm.infrastructure.doc.extractors.cli_ast_extractor import CliAstExtractor
from auto_pm.infrastructure.doc.extractors.gate_ast_extractor import GateAstExtractor
from auto_pm.infrastructure.doc.injector.marker_injector import MarkdownMarkerInjector


class DocSyncService:
    """Synchronizes code AST metadata into living Markdown documents."""

    def __init__(self, workspace_root: Path):
        self.ws = workspace_root
        self.app_root = workspace_root / "01_Project自动化项目管理" / "Python自动化项目总库" / "02_在研项目" / "SW-2026-008_auto-pm_自动化项目管理工具"

    def sync_all(self) -> list[str]:
        logs: list[str] = []
        # 1. Extract CLI Commands
        cli_dir = self.app_root / "auto_pm" / "ui" / "cli"
        cli_commands = CliAstExtractor.extract_from_directory(cli_dir)

        # Format CLI table
        cli_table = "| 命令分组 | 模块源文件 | 核心职责说明 |\n|:---|:---|:---|\n"
        for cmd in sorted(cli_commands, key=lambda x: x.group):
            cli_table += f"| `{cmd.group}` | `{cmd.file_source}` | {cmd.doc} |\n"

        # 2. Extract QML Bridges
        bridges_dir = self.app_root / "auto_pm" / "ui" / "qml" / "bridges"
        bridge_methods = BridgeAstExtractor.extract_from_directory(bridges_dir)
        bridge_table = "| Bridge 模块 | 导出方法 / 信号 | 参数列表 | 说明 |\n|:---|:---|:---|:---|\n"
        for m in sorted(bridge_methods, key=lambda x: (x.bridge_name, x.method_name)):
            args_str = ", ".join(m.args) if m.args else "无"
            bridge_table += f"| `{m.bridge_name}` | `{m.method_name}` | `{args_str}` | {m.doc} |\n"

        # 3. Extract Gate Rules
        checker_file = self.app_root / "auto_pm" / "domain" / "plc" / "checker.py"
        gate_rules = GateAstExtractor.extract_from_checker(checker_file)
        gate_table = "| 规则编号 | 门禁检查项 | 类别 | 规则职责 |\n|:---|:---|:---|:---|\n"
        for g in sorted(gate_rules, key=lambda x: x.rule_id):
            gate_table += f"| `{g.rule_id}` | `{g.rule_name}` | `{g.category}` | {g.doc} |\n"

        # 4. Inject into USER_GUIDE.md
        user_guide = self.app_root / "06_交付物" / "001_用户操作指南与排障手册_USER_GUIDE.md"
        if user_guide.exists():
            ok, msg = MarkdownMarkerInjector.inject(user_guide, "CLI_COMMANDS", cli_table)
            logs.append(msg)

        # 5. Inject into INT.md
        int_doc = self.app_root / "02_规划" / "002_接口文档_INT.md"
        if int_doc.exists():
            ok, msg = MarkdownMarkerInjector.inject(int_doc, "QML_BRIDGES", bridge_table)
            logs.append(msg)

        # 6. Inject into DSN.md
        dsn_doc = self.app_root / "02_规划" / "003_详细设计说明书_DSN.md"
        if dsn_doc.exists():
            ok, msg = MarkdownMarkerInjector.inject(dsn_doc, "GATE_RULES", gate_table)
            logs.append(msg)

        return logs

class DocCheckService:
    """Audits doc-code consistency and version lock."""

    def __init__(self, workspace_root: Path):
        self.ws = workspace_root
        self.app_root = workspace_root / "01_Project自动化项目管理" / "Python自动化项目总库" / "02_在研项目" / "SW-2026-008_auto-pm_自动化项目管理工具"

    def check_all(self) -> list[DocCheckResult]:
        results: list[DocCheckResult] = []

        # Check 1: CLI modules exist in USER_GUIDE
        user_guide = self.app_root / "06_交付物" / "001_用户操作指南与排障手册_USER_GUIDE.md"
        cli_dir = self.app_root / "auto_pm" / "ui" / "cli"
        cli_commands = CliAstExtractor.extract_from_directory(cli_dir)
        if user_guide.exists():
            text = user_guide.read_text(encoding="utf-8")
            missing_groups = [cmd.group for cmd in cli_commands if cmd.group not in text]
            if missing_groups:
                results.append(DocCheckResult(
                    check_id="DOC-001",
                    name="CLI 命令与用户指南同步",
                    passed=False,
                    message=f"USER_GUIDE 缺少以下 CLI 分组说明: {', '.join(set(missing_groups))}"
                ))
            else:
                results.append(DocCheckResult(
                    check_id="DOC-001",
                    name="CLI 命令与用户指南同步",
                    passed=True,
                    message=f"已覆盖全量 {len(cli_commands)} 组 CLI 命令"
                ))

        # Check 2: Version lock (DOC-004, D-294): the project's own version must equal the version of the active release.
        results.append(self._version_lock())

        return results

    def _version_lock(self) -> DocCheckResult:
        """DOC-004: ``[project] version`` of pyproject.toml against ``version`` in the active release's release_meta.json.

        D-294: this check used to end in ``passed_ver or True`` (always green), read the last ``version =`` line of
        pyproject.toml (``required-version`` of ruff, so ``>=0.8.4``) and compared it with PM_SESSION, which is retired
        (user 2026-10-10) and no longer read.  When either side cannot be read the check fails and says so: an unknown
        comparison is not a pass.
        """

        name = "全系统版本锁一致性"
        source = self._project_version()
        released, where = self._active_release_version()
        if not source:
            return DocCheckResult(check_id="DOC-004", name=name, passed=False,
                                  message="无法比对：读不到 pyproject.toml 的 [project] version")
        if not released:
            return DocCheckResult(check_id="DOC-004", name=name, passed=False,
                                  message=f"无法比对：{where}（pyproject={source}）")
        if source != released:
            return DocCheckResult(check_id="DOC-004", name=name, passed=False,
                                  message=f"版本不一致：pyproject={source}，现役发布 {where} 的 version={released}")
        return DocCheckResult(check_id="DOC-004", name=name, passed=True,
                              message=f"pyproject={source}，现役发布 {where} 的 version={released}")

    def _project_version(self) -> str:
        try:
            data = tomllib.loads((self.app_root / "pyproject.toml").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            return ""
        project = data.get("project")
        version = project.get("version") if isinstance(project, dict) else None
        return version if isinstance(version, str) else ""

    def _active_release_version(self) -> tuple[str, str]:
        """(version, where) of the active release; version is "" and ``where`` says what is missing when it cannot be read."""

        container = self.ws / "00_Infrastructure" / "auto_pm"
        try:
            pointer = json.loads((container / "active_release.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            return "", "读不到 00_Infrastructure/auto_pm/active_release.json"
        release_path = pointer.get("release_path") if isinstance(pointer, dict) else None
        if not isinstance(release_path, str) or not release_path or "/" in release_path or "\\" in release_path or release_path in {".", ".."}:
            return "", "active_release.json 里没有可用的 release_path"
        where = f"releases/{release_path}/release_meta.json"
        try:
            meta = json.loads((container / "releases" / release_path / "release_meta.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError):
            return "", f"读不到 {where}"
        version = meta.get("version") if isinstance(meta, dict) else None
        if not isinstance(version, str) or not version:
            return "", f"{where} 里没有 version"
        return version, where
