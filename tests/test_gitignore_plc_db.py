"""忽略规则守护：PLC 数据块 .db（ST/SCL 文本源文件）不能被 .gitignore 挡掉。

根目录 .gitignore 用 *.db 挡运行时 SQLite 库（.auto-pm/index.db 等），
但 PLC 的 GlobalVars.db 也叫 .db，被一并忽略后新建项目 git add 会静默漏掉（审计 91）。
本测试只读，不写工作区：用 git check-ignore --no-index 判断规则，不依赖磁盘上有没有这些文件。
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SW008 = "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具"
SQLITE_MAGIC = b"SQLite format 3\x00"

# 新建或迁入 PLC 项目、PLC 模板里会出现的数据块路径：必须能入库
MUST_TRACK = [
    "0100_PLC自动化/DJ-2099-999_探针/DB1/GlobalVars.db",
    "0100_PLC自动化/DJ-2099-999_探针/02_PLC程序/PLC_ST/00_全局数据/GlobalVars.db",
    "0100_PLC自动化/DJ-2099-999_探针/02_PLC程序/PLC_ST/DB1/GlobalVars.db",
    "0100_PLC自动化/DJ-2099-999_探针/DB2/IEC_Timer_0_DB.db",
    "0100_PLC自动化/01_SharedLibraries/SysLib/DB1/GlobalVars.db",
    f"{SW008}/templates/plc-test-suite/template/DB1/GlobalVars.db",
    f"{SW008}/templates/plc-standard-project/template/02_PLC程序/PLC_ST/00_全局数据/GlobalVars.db",
    "00_Infrastructure/auto_pm/templates/plc-test-suite/template/DB1/GlobalVars.db",
    "00_Infrastructure/auto_pm/releases/9.9.9-probe/templates/plc-test-suite/template/DB1/GlobalVars.db",
]

# 运行时库和缓存：放行 PLC .db 之后仍必须挡住
MUST_IGNORE = [
    ".auto-pm/index.db",
    ".auto-pm/continuity.db",
    ".auto-pm/index.db-journal",
    "00_Infrastructure/auto_pm/.auto-pm/index.db",
    f"{SW008}/data/runtime.db",
    "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2099-999_探针/data/app.db",
    "0100_PLC自动化/DJ-2099-999_探针/.auto-pm/index.db",
    "0100_PLC自动化/DJ-2099-999_探针/Thumbs.db",
    "0100_PLC自动化/DJ-2099-999_探针/DB1/GlobalVars.db-journal",
    f"{SW008}/templates/plc-test-suite/template/.auto-pm/index.db",
]

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or not (WORKSPACE_ROOT / ".git").exists(),
    reason="需要 git 和仓库检出",
)


def _git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-c", "core.quotepath=off", *args],
        cwd=WORKSPACE_ROOT,
        capture_output=True,
        check=False,
    )


def _ignored(path: str) -> bool:
    proc = _git("check-ignore", "--no-index", "-q", path)
    if proc.returncode not in (0, 1):
        raise RuntimeError(proc.stderr.decode("utf-8", "replace"))
    return proc.returncode == 0


def _rule(path: str) -> str:
    return _git("check-ignore", "--no-index", "-v", path).stdout.decode("utf-8", "replace").strip()


@pytest.mark.parametrize("path", MUST_TRACK)
def test_plc_data_block_not_ignored(path: str) -> None:
    assert not _ignored(path), f"PLC 数据块会被忽略，git add 会漏掉：{_rule(path)}"


@pytest.mark.parametrize("path", MUST_IGNORE)
def test_runtime_db_still_ignored(path: str) -> None:
    assert _ignored(path), f"运行时库没被忽略，可能被误提交：{path}"


def test_tracked_text_db_files_not_ignored() -> None:
    """仓库里已跟踪、又命中忽略规则的 .db：只允许是 SQLite 库，文本 .db（PLC 源文件）一个都不许。"""
    proc = _git("ls-files", "-z", "-c", "-i", "--exclude-standard")
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    offenders = []
    for raw in proc.stdout.split(b"\0"):
        name = raw.decode("utf-8", "replace")
        if not name.lower().endswith(".db"):
            continue
        path = WORKSPACE_ROOT / name
        if not path.is_file():
            continue
        with path.open("rb") as fh:
            head = fh.read(len(SQLITE_MAGIC))
        if head != SQLITE_MAGIC:
            offenders.append(f"{name}  <- {_rule(name)}")
    assert not offenders, "这些 .db 不是 SQLite 库（多半是 PLC 源文件），却命中忽略规则：\n" + "\n".join(offenders)


def test_released_db_files_are_not_sqlite() -> None:
    """反向：放行范围（不被忽略）里已跟踪的 .db 必须是文本数据块，SQLite 运行时库不许借放行规则入库。"""
    proc = _git("ls-files", "-z", "-c")
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    offenders = []
    for raw in proc.stdout.split(b"\0"):
        name = raw.decode("utf-8", "replace")
        if not name.lower().endswith(".db") or _ignored(name):
            continue
        path = WORKSPACE_ROOT / name
        if not path.is_file():
            continue
        with path.open("rb") as fh:
            if fh.read(len(SQLITE_MAGIC)) == SQLITE_MAGIC:
                offenders.append(name)
    assert not offenders, "这些 SQLite 库借 PLC 放行规则入了库，应删掉或改放 .auto-pm/：\n" + "\n".join(offenders)
