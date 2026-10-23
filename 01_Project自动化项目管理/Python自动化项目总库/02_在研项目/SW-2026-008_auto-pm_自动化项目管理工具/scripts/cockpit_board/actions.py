"""工程工位的本机动作。整个包里只有这个文件允许起子进程和写文件。

    probe_online()     后台对 origin 跑 git ls-remote，3 秒超时，失败算离线；不访问别的外网。
    run_check()        跑 plc check / plc docs check / docs sync --dry-run，返回回执（命令 + 退出码）。
    bc_next_id()       按 02_业务变更记录.md 里同年月用过的最大序号给下一个 BC 编号（每月从 000 起）。
    bc_preview()       按目标表头（11 栏）和用户填的表单生成整行，不写；没填好就拒绝。
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


# ---------------------------------------------------------------- 业务变更（BC）行
#
# 格式以模板 0100_PLC自动化/00_通用规范/项目文档模板/02_业务变更记录模板.md 为准：
#   11 栏：编号 | 提出时间 | 提出人 | 类型 | 改了什么（原来 → 改成） | 为什么 | 影响 | 批准人 | 批准日期 | 状态 | 关联 CHG / 提交
#   编号 BC-<项目号>-<年>_<月>_<序号>，序号每月从 000 起、最多 999、不重复；年月取“提出时间”。
#   提出时间写到分钟 YYYY-MM-DD HH:MM，后面括号写渠道。类型只能是 需求 / 参数 / 硬件。
# 列按表头的名字对上，表头有几栏就写几格；表头认不出就拒绝，不猜。

BC_TYPES = ("需求", "参数", "硬件")
BC_CHANNELS = ("当面", "电话", "邮件", "微信")
BC_TIME = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
PLACEHOLDER = re.compile(r"[（(]\s*填|<[^>]*>|待填|TODO", re.IGNORECASE)
# 表头栏名（去掉括号里的说明后）→ 表单字段；“提出日期”是 10-22 前的旧名，同一栏。
BC_COLUMNS = {
    "编号": "id", "提出时间": "raised", "提出日期": "raised", "提出人": "who", "类型": "kind",
    "改了什么": "what", "为什么": "why", "影响": "impact", "批准人": "approver", "批准日期": "approved_on",
    "状态": "status", "关联 CHG / 提交": "link", "关联": "link",
}
BC_REQUIRED = ("id", "raised", "who", "kind", "what", "why", "impact", "status")


@dataclass(frozen=True)
class BcForm:
    """用户在工程工位第 4 步填的内容。提出人是提出改动的人（如“张工（客户设备科）”），不是操作界面的人。"""

    raised: str  # YYYY-MM-DD HH:MM
    channel: str
    who: str
    kind: str
    what: str
    why: str
    impact: str


@dataclass(frozen=True)
class BcPreview:
    line: str  # 要追加的那一行
    columns: tuple[tuple[str, str], ...]  # (表头栏名, 这一格) 全部栏，预览时逐栏给人看


class BcError(ValueError):
    """表单没填好或表头认不出；文字直接显示给用户。"""


def _clean(text: str) -> str:
    return " ".join(str(text).split()).replace("|", "｜")


def bc_form_errors(form: BcForm) -> list[str]:
    errors = []
    if not BC_TIME.match(form.raised.strip()):
        errors.append("提出时间要写到分钟：YYYY-MM-DD HH:MM")
    else:
        try:
            datetime.strptime(form.raised.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            errors.append("提出时间不是真实日期")
    if form.channel not in BC_CHANNELS:
        errors.append("渠道只能是 " + " / ".join(BC_CHANNELS))
    if form.kind not in BC_TYPES:
        errors.append("类型只能是 " + " / ".join(BC_TYPES))
    for label, value in (("提出人", form.who), ("改了什么", form.what), ("为什么", form.why), ("影响", form.impact)):
        if not value.strip():
            errors.append(f"“{label}”没填（影响没有就写“无”）" if label == "影响" else f"“{label}”没填")
        elif PLACEHOLDER.search(value):
            errors.append(f"“{label}”还是占位字，请写实际内容")
    return errors


def bc_header(record: Path) -> list[str]:
    """变更记录表的表头：第一格是“编号”、下一行是 |---| 分隔线的那一行（“填写说明”表里的“编号”行不算）。

    这张表后面除了表格行和空行不许再有别的字，否则追加到文件末尾的那一行就落在表外了。
    """
    lines = record.read_text(encoding="utf-8").splitlines()
    for index, (line, below) in enumerate(zip(lines, lines[1:], strict=False)):
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and cells[0] == "编号" and re.fullmatch(r"\|?(\s*:?-+:?\s*\|)+\s*:?-*:?\s*", below.strip()):
            if any(rest.strip() and not rest.lstrip().startswith("|") for rest in lines[index + 2:]):
                raise BcError(f"{record.name} 的变更表后面还有别的内容，追加会落在表外，不写；请人工补这一行")
            return cells
    raise BcError(f"{record.name} 里没有找到以“编号”开头的表头")


def _column_key(name: str) -> str | None:
    base = re.sub(r"[（(].*?[）)]", "", name).strip()
    return BC_COLUMNS.get(base)


def bc_next_id(record: Path, project_id: str, when: datetime) -> str:
    """同一年月已用过的最大序号 +1；这个月还没有就从 000 起；旧编号（如 BC-…-001）不算。"""
    year, month = f"{when.year:04d}", f"{when.month:02d}"
    used = []
    if record.is_file():
        for line in record.read_text(encoding="utf-8").splitlines():
            cell = line.strip().strip("|").split("|")[0].strip()
            m = BC_PATTERN.match(cell)
            if m and m.group(1) == project_id and m.group(2) == year and m.group(3) == month:
                used.append(int(m.group(4)))
    seq = max(used) + 1 if used else 0
    if seq > 999:
        raise BcError(f"{year} 年 {month} 月的 BC 序号已到 999，不能再编")
    return f"BC-{project_id}-{year}_{month}_{seq:03d}"


def bc_preview(record: Path, project_id: str, form: BcForm) -> BcPreview:
    """按目标文件的表头生成整行（有几栏写几格），不写文件。表单没填好、表头认不出都抛 BcError。"""
    errors = bc_form_errors(form)
    if errors:
        raise BcError("；".join(errors))
    header = bc_header(record)
    keys = [_column_key(name) for name in header]
    missing = [k for k in BC_REQUIRED if k not in keys]
    if missing:
        raise BcError(f"表头认不出（缺 {', '.join(missing)}）：{' | '.join(header)}，请按模板改表头后再写")
    when = datetime.strptime(form.raised.strip(), "%Y-%m-%d %H:%M")
    values = {
        "id": bc_next_id(record, project_id, when),
        "raised": f"{form.raised.strip()}（{form.channel}）",
        "who": _clean(form.who), "kind": form.kind, "what": _clean(form.what), "why": _clean(form.why),
        "impact": _clean(form.impact), "approver": "", "approved_on": "", "status": "待批", "link": "",
    }
    cells = [values.get(key, "") if key else "" for key in keys]
    line = "| " + " | ".join(cells) + " |"
    return BcPreview(line, tuple(zip(header, cells, strict=True)))


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
