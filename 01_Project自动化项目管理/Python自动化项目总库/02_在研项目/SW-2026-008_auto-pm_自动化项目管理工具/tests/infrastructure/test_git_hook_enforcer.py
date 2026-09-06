"""单元测试：Git 提交硬锁门禁护航器（Git Hook Enforcer）"""

from pathlib import Path

from auto_pm.infrastructure.git_hook_enforcer import (
    enforce_commit_msg,
    filter_production_files,
)


def test_filter_production_files():
    """测试生产代码过滤规则：排除测试、文档与会话，准确识别生产代码"""
    files = [
        "00_Infrastructure/auto_pm/auto_pm/main.py",
        "0100_PLC自动化/DJ-2026-005/02_PLC程序/PLC_ST/FB_2001.scl",
        "00_Infrastructure/auto_pm/tests/test_main.py",
        "01_Project/SW-2026-009/tests/test_service.py",
        "SYS-2026-001_WorkspaceGovernance/PM_SESSION_SYS-2026-001.md",
        "00_Obsidian_Base全局规范文件仓库/spec.md",
    ]
    prod = filter_production_files(files)
    assert "00_Infrastructure/auto_pm/auto_pm/main.py" in prod
    assert "0100_PLC自动化/DJ-2026-005/02_PLC程序/PLC_ST/FB_2001.scl" in prod
    assert len(prod) == 2


def test_enforce_commit_msg_exempts_docs(tmp_path: Path, monkeypatch):
    """测试纯文档或测试提交豁免变更单号"""
    msg_file = tmp_path / "COMMIT_EDITMSG"
    msg_file.write_text("docs: update session log", encoding="utf-8")

    # 模拟暂存区只有文档
    monkeypatch.setattr(
        "auto_pm.infrastructure.git_hook_enforcer.get_staged_files",
        lambda ws: ["PM_SESSION_SYS-2026-001.md", "README.md"],
    )

    code = enforce_commit_msg(tmp_path, msg_file)
    assert code == 0


def test_enforce_commit_msg_blocks_code_without_chg(tmp_path: Path, monkeypatch):
    """测试暂存区包含生产代码但未关联单号时物理阻断"""
    msg_file = tmp_path / "COMMIT_EDITMSG"
    msg_file.write_text("feat: add new feature without ticket", encoding="utf-8")

    # 模拟暂存区包含生产 Python 源码
    monkeypatch.setattr(
        "auto_pm.infrastructure.git_hook_enforcer.get_staged_files",
        lambda ws: ["00_Infrastructure/auto_pm/auto_pm/core.py"],
    )

    code = enforce_commit_msg(tmp_path, msg_file)
    assert code == 1


def test_enforce_commit_msg_blocks_nonexistent_chg(tmp_path: Path, monkeypatch):
    """测试关联了不存在的变更单号时物理阻断"""
    msg_file = tmp_path / "COMMIT_EDITMSG"
    msg_file.write_text("feat: [CHG-SCPT-2026-999] fake ticket", encoding="utf-8")

    monkeypatch.setattr(
        "auto_pm.infrastructure.git_hook_enforcer.get_staged_files",
        lambda ws: ["00_Infrastructure/auto_pm/auto_pm/core.py"],
    )

    code = enforce_commit_msg(tmp_path, msg_file)
    assert code == 1


def test_enforce_commit_msg_passes_valid_chg(tmp_path: Path, monkeypatch):
    """测试关联真实存在且已批准/关闭的变更单号时放行"""
    chg_dir = tmp_path / "01_变更单" / "CHG-SCPT"
    chg_dir.mkdir(parents=True)
    chg_file = chg_dir / "CHG-SCPT-2026-170.md"
    chg_file.write_text(
        """# CHG-SCPT-2026-170
## 3. 变更基本信息
### 3.4 申请信息
| 变更状态 | closed |
""",
        encoding="utf-8",
    )

    msg_file = tmp_path / "COMMIT_EDITMSG"
    msg_file.write_text("feat: [CHG-SCPT-2026-170] valid ticket commit", encoding="utf-8")

    monkeypatch.setattr(
        "auto_pm.infrastructure.git_hook_enforcer.get_staged_files",
        lambda ws: ["00_Infrastructure/auto_pm/auto_pm/core.py"],
    )

    code = enforce_commit_msg(tmp_path, msg_file)
    assert code == 0
