"""GovernanceService 单元测试 (CHG-SCPT-2026-155)"""

from pathlib import Path

from auto_pm.core.governance_service import ROOT_WHITELIST, GovernanceService


def test_governance_service_init(tmp_path: Path) -> None:
    service = GovernanceService(workspace_root=tmp_path)
    assert service.workspace_root == tmp_path.resolve()


def test_inspect_sanitation_clean(tmp_path: Path) -> None:
    # 创建白名单目录/文件
    (tmp_path / ".git").mkdir()
    (tmp_path / "README.md").touch()

    service = GovernanceService(workspace_root=tmp_path)
    report = service.inspect_sanitation()

    assert report.is_pure is True
    assert report.total_issues == 0


def test_inspect_sanitation_polluted(tmp_path: Path) -> None:
    # 创建非白名单临时文件
    (tmp_path / "mypy_errors.txt").touch()
    (tmp_path / "test_run.log").touch()
    (tmp_path / ".tmp_check.py").touch()
    (tmp_path / "random_junk.bin").touch()

    service = GovernanceService(workspace_root=tmp_path)
    report = service.inspect_sanitation()

    assert report.is_pure is False
    assert len(report.temp_files) == 3
    assert len(report.unauthorized_files) == 1
    assert report.total_issues == 4


def test_clean_workspace(tmp_path: Path) -> None:
    (tmp_path / "mypy_errors.txt").touch()
    (tmp_path / "test_run.log").touch()

    service = GovernanceService(workspace_root=tmp_path)
    cleaned = service.clean_workspace()

    assert len(cleaned) == 2
    assert not (tmp_path / "mypy_errors.txt").exists()
    assert not (tmp_path / "test_run.log").exists()


def test_claude_code_entry_files_are_whitelisted(tmp_path: Path) -> None:
    # 薄入口：Claude Code 读根目录 CLAUDE.md，设置放 .claude/；与 AGENTS.md 一样不算散落文件
    (tmp_path / "AGENTS.md").touch()
    (tmp_path / "CLAUDE.md").touch()
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text("{}", encoding="utf-8")

    report = GovernanceService(workspace_root=tmp_path).inspect_sanitation()

    assert report.is_pure is True, [issue.relative_path for issue in report.unauthorized_files]
    assert {"claude.md", ".claude"} <= ROOT_WHITELIST

