"""工程工位的本机动作。整个包里只有这个文件允许起子进程和写文件。

    probe_online()     后台对 origin 跑 git ls-remote，3 秒超时，失败算离线；不访问别的外网。
    run_check()        跑 plc check / plc docs check / docs sync --dry-run，返回回执（命令 + 退出码）。
    bc_next_id()       按 02_业务变更记录.md 最后一行建议下一个 BC 编号（BC-<项目>-<年>_<月>_<序号>）。
    bc_preview()       生成要追加的那一行，不写。
    bc_append()        只往表末追加一行；写前读一遍、写后校验除最后一行外字节不变。

永远没有：合并、删除、切换发布、代签、绕过提交钩子、启动任何 agent。
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROBE_TIMEOUT = 3
CHECK_TIMEOUT = 600
BC_PATTERN = re.compile(r"^BC-([A-Z]+-\d{4}-\d{3})-(\d{4})_(\d{2})_(\d{3})$")
_BC_LOCK = threading.Lock()


@dataclass(frozen=True)
class Receipt:
    when: str
    action: str
    command: str
    rc: int | None
    preview: bool = False
    output: str = ""

    @property
    def rc_text(self) -> str:
        return "预览" if self.preview else ("未验证" if self.rc is None else f"rc {self.rc}")


def _now_text() -> str:
    return datetime.now().strftime("%H:%M")


def probe_online(root: Path, runner=subprocess.run) -> bool:  # noqa: ANN001
    try:
        result = runner(
            ["git", "ls-remote", "--exit-code", "origin", "HEAD"],
            cwd=str(root), capture_output=True, encoding="utf-8", timeout=PROBE_TIMEOUT, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


CHECKS = {
    "plc_check": ("plc check", ["plc", "check"]),
    "docs_check": ("plc docs check", ["plc", "docs", "check"]),
    "docs_sync_preview": ("docs sync 预览", ["plc", "docs", "sync", "--dry-run"]),
}


def run_check(root: Path, worktree: Path, project_id: str, key: str, runner=subprocess.run) -> Receipt:  # noqa: ANN001
    label, args = CHECKS[key]
    command = ["python", "-B", str(root / "main.py"), "-w", str(worktree), *args, project_id]
    shown = " ".join(command)
    try:
        result = runner(command, cwd=str(root), capture_output=True, encoding="utf-8", timeout=CHECK_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError) as error:
        return Receipt(_now_text(), label, shown, None, key.endswith("preview"), f"{type(error).__name__}: {error}")
    return Receipt(_now_text(), label, shown, result.returncode, key.endswith("preview"), (result.stdout or "") + (result.stderr or ""))


def bc_next_id(record: Path, project_id: str, when: datetime) -> str:
    """读表最后一行 BC 编号；同年月序号 +1，跨月归 001；旧号不改。"""
    last = None
    if record.is_file():
        for line in record.read_text(encoding="utf-8").splitlines():
            cell = line.strip().strip("|").split("|")[0].strip()
            if BC_PATTERN.match(cell):
                last = cell
    year, month = f"{when.year:04d}", f"{when.month:02d}"
    seq = 1
    if last:
        m = BC_PATTERN.match(last)
        if m and m.group(2) == year and m.group(3) == month:
            seq = int(m.group(4)) + 1
    return f"BC-{project_id}-{year}_{month}_{seq:03d}"


def bc_preview(record: Path, project_id: str, when: datetime, who: str, what: str, impact: str) -> str:
    change_id = bc_next_id(record, project_id, when)
    date = when.strftime("%Y-%m-%d")
    cells = [change_id, f"{date} 现场", who, what.replace("|", "｜"), impact.replace("|", "｜"), f"待批 {date}"]
    return "| " + " | ".join(cells) + " |"


def bc_digest(record: Path) -> str:
    """预览时记下文件指纹；写入时文件变了就拒写（编号是按预览那一刻的最后一行算的）。"""
    return hashlib.sha256(record.read_bytes()).hexdigest()


def bc_append(record: Path, line: str, expected_digest: str | None = None) -> Receipt:
    """只往表末追加一行，用追加模式打开，不重写整份文件。

    同一时刻只允许一次写（锁）；预览之后文件被别人改过（外部编辑器、连点两下）就拒写，回执 rc 1，
    要你重新预览。写后校验：除新增的最后一行外，字节不变。
    """
    with _BC_LOCK:
        before = record.read_bytes()
        if expected_digest is not None and hashlib.sha256(before).hexdigest() != expected_digest:
            return Receipt(_now_text(), "写入 BC 行", f"拒写 {record.name}：预览后文件变了，请重新预览", 1)
        sep = b"" if before.endswith(b"\n") or not before else b"\n"
        with open(record, "ab") as stream:
            stream.write(sep + (line + "\n").encode("utf-8"))
        after = record.read_bytes()
    if not after.startswith(before) or after[len(before):] != sep + (line + "\n").encode("utf-8"):
        return Receipt(_now_text(), "写入 BC 行", f"追加写校验失败：{record.name} 写入期间被别人改了，请人工核对", 1)
    return Receipt(_now_text(), "写入 BC 行", f"append {record.name} ← {line.split('|')[1].strip()}", 0)
