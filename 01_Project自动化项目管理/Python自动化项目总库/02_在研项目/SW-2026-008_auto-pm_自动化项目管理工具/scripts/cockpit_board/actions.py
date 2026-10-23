"""工程工位的本机动作。整个包里只有这个文件允许起子进程和写文件。

    probe_online()     后台对 origin 跑 git ls-remote，3 秒超时，失败算离线；不访问别的外网。
    run_check()        跑 plc check / plc docs check / docs sync --dry-run，返回回执（命令 + 退出码）。
    bc_next_id()       按 02_业务变更记录.md 最后一行建议下一个 BC 编号（BC-<项目>-<年>_<月>_<序号>）。
    bc_header()        读目标表的表头（最后一张含“编号”的表，且它必须在文件末尾）。
    bc_preview()       按目标表头生成同样多的格；“改了什么 / 为什么 / 影响”由你在界面填，空的或占位字拒绝。不写。
    bc_append()        只往表末追加一行；写前按表头再核一遍（格数、必填栏），写后校验除最后一行外字节不变。
    operator_name()    提出人：--operator → 环境变量 WORKSPACEPM_OPERATOR → 人工工位的 git config user.name；都没有就不让写。

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
OPERATOR_ENV = "WORKSPACEPM_OPERATOR"
# 界面上要你填的栏（按表头名认，前缀匹配：表头“改了什么（原来 → 改成）”也算“改了什么”）
BC_REQUIRED = ("类型", "改了什么", "为什么", "影响")
# 看起来像没填的：空、模板占位字（“（填……）”“待补”“TODO”之类）
BC_PLACEHOLDER = re.compile(r"^\s*$|^[（(]\s*填|^待补$|^待定$|^todo$|^tbd$|^xxx+$|^[-—…。.]+$", re.IGNORECASE)


class BcError(ValueError):
    """BC 行不能生成或不能写：原因直接给用户看。"""


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


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator(line: str) -> bool:
    cells = _cells(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def bc_header(record: Path) -> list[str]:
    """目标表的表头。只认文件里最后一张含“编号”的表，而且表后面除了表格行和空行不能再有别的字——
    否则追加到文件末尾的那一行就不在表里了。"""
    lines = record.read_text(encoding="utf-8").splitlines()
    header_at = None
    for index in range(len(lines) - 1):
        if lines[index].lstrip().startswith("|") and "编号" in _cells(lines[index]) and _is_separator(lines[index + 1]):
            header_at = index
    if header_at is None:
        raise BcError(f"{record.name} 里找不到含“编号”的表头，不写")
    tail = [line for line in lines[header_at + 2:] if line.strip()]
    if any(not line.lstrip().startswith("|") for line in tail):
        raise BcError(f"{record.name} 的变更表后面还有别的内容，追加到文件末尾会落在表外，不写；请人工补这一行")
    header = _cells(lines[header_at])
    lacking = [name for name in ("编号", "改了什么", "状态") if not any(cell.startswith(name) for cell in header)]
    if lacking:
        raise BcError(f"{record.name} 的表头缺“{'、'.join(lacking)}”栏，不知道往哪格写，不写")
    return header


def _column(name: str) -> str:
    return next((key for key in BC_REQUIRED if name.startswith(key)), name)


def _clean(text: str) -> str:
    return " ".join(str(text).replace("|", "｜").split())


def bc_missing(fields: dict[str, str]) -> list[str]:
    """还没填（空或占位字）的必填栏名。"""
    return [key for key in BC_REQUIRED if BC_PLACEHOLDER.search(_clean(fields.get(key, "")))]


def bc_preview(record: Path, project_id: str, when: datetime, who: str, fields: dict[str, str]) -> str:
    """按目标表头逐列生成一行，格数和表头一样。提出时间到分钟。缺必填、没提出人、表头不对都抛 BcError。"""
    missing = bc_missing(fields)
    if missing:
        raise BcError("先填：" + "、".join(missing) + "（不能空着，也不能是“（填……）”“待补”这类占位字）")
    if not who or BC_PLACEHOLDER.search(who):
        raise BcError(f"提出人没配置：启动时加 --operator 名字，或设环境变量 {OPERATOR_ENV}，或在人工工位里设 git config user.name")
    header = bc_header(record)
    stamp = when.strftime("%Y-%m-%d %H:%M")
    values = {
        "编号": bc_next_id(record, project_id, when),
        "提出人": who,
        "状态": f"待批 {stamp}",
        **{key: fields[key] for key in BC_REQUIRED},
    }
    cells = []
    for name in header:
        key = _column(name)
        if key.startswith("提出") and key != "提出人":
            cells.append(stamp)  # 提出日期 / 提出时间：到分钟（用户 10-22 定）
        else:
            cells.append(_clean(values.get(key, "待补")))  # 批准人、批准日期、关联：批了以后人工补
    return "| " + " | ".join(cells) + " |"


def bc_check_line(record: Path, line: str) -> None:
    """写前再核一遍：格数等于表头格数，必填栏不是空的也不是占位字。不对抛 BcError。"""
    header = bc_header(record)
    cells = _cells(line)
    if len(cells) != len(header):
        raise BcError(f"这一行 {len(cells)} 格，表头 {len(header)} 格，对不上，不写")
    row = {_column(name): cell for name, cell in zip(header, cells, strict=True)}
    missing = [key for key in BC_REQUIRED if key in row and BC_PLACEHOLDER.search(row[key])]
    if missing:
        raise BcError("这一行的 " + "、".join(missing) + " 还是空的或占位字，不写")


def operator_name(configured: str, env: dict[str, str], worktree: Path, runner=subprocess.run) -> str:  # noqa: ANN001
    """提出人从配置读：命令行 --operator → 环境变量 → 人工工位的 git user.name。读不到返回空串。"""
    for value in (configured, env.get(OPERATOR_ENV, "")):
        if value.strip():
            return value.strip()
    if not worktree.is_dir():
        return ""
    try:
        result = runner(["git", "config", "user.name"], cwd=str(worktree), capture_output=True, encoding="utf-8",
                        timeout=PROBE_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return (result.stdout or "").strip() if result.returncode == 0 else ""


def bc_digest(record: Path) -> str:
    """预览时记下文件指纹；写入时文件变了就拒写（编号是按预览那一刻的最后一行算的）。"""
    return hashlib.sha256(record.read_bytes()).hexdigest()


def bc_append(record: Path, line: str, expected_digest: str | None = None) -> Receipt:
    """只往表末追加一行，用追加模式打开，不重写整份文件。

    同一时刻只允许一次写（锁）；预览之后文件被别人改过（外部编辑器、连点两下）就拒写，回执 rc 1，
    要你重新预览。写后校验：除新增的最后一行外，字节不变。
    """
    with _BC_LOCK:
        try:
            bc_check_line(record, line)
        except (BcError, OSError, UnicodeDecodeError) as error:
            return Receipt(_now_text(), "写入 BC 行", f"拒写 {record.name}：{error}", 1)
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
