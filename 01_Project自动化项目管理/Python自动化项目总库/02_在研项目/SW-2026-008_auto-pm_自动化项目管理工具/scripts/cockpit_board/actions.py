"""工程工位的本机动作。整个包里只有这个文件允许起子进程和写文件。

    probe_online()     后台对 origin 跑 git ls-remote，3 秒超时，失败算离线；不访问别的外网。
    run_check()        跑 plc check / plc docs check / docs sync --dry-run，返回回执（命令 + 退出码）。
    bc_next_id()       按 02_业务变更记录.md 里同年月用过的最大序号给下一个 BC 编号（每月从 000 起）。
    bc_preview()       按目标表头（11 栏）和用户填的表单生成整行，不写；没填好就拒绝。
    bc_append()        只往表末追加一行；写前读一遍、写后校验除最后一行外字节不变。
    run_cli()          “决定”页的按钮：在控制根跑同一条 `main.py pm …` 命令，回执带命令和退出码（见 decisions.py）。
    resolve_github_token()  向本机已登录的 gh 要 GitHub 令牌（只在内存里用，不落盘、不进回执、不打印）。
    open_console()     批准口令已生效时，同一条命令在新的终端窗口里跑，口令由用户在那个窗口里输入。

永远没有：合并、删除、切换发布、代签、绕过提交钩子、启动任何 agent。
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import github_collector as gh

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
    output: str = ""  # 显示用：stdout 接 stderr
    stdout: str = ""  # 要解析的只用这个；stderr 里有启动器横幅等杂行，只用来在出错时给人看
    stderr: str = ""

    @property
    def rc_text(self) -> str:
        return "预览" if self.preview else ("未验证" if self.rc is None else f"rc {self.rc}")


def _now_text() -> str:
    return datetime.now().strftime("%H:%M")


def no_window_flag() -> int:
    """Windows 的 CREATE_NO_WINDOW；别的系统返回 0。测试替换这一处，不去改全局 os.name。

    后台读数据、跑检查的命令都用它：界面从没有控制台的 pythonw 启动时，每条子命令不加这个标志就会各弹一个黑窗口，
    点“重新读取”时一连弹好几个（用户 2026-11-01 S3 试用看到）。要给用户看的新终端窗口（open_console）不走这里。
    """
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0


def quiet() -> dict[str, Any]:
    """后台子进程的附加参数：不弹窗口。非 Windows 返回空，不传 creationflags。"""
    flag = no_window_flag()
    return {"creationflags": flag} if flag else {}


# ---------------------------------------------------------------- 本机 GitHub 登录 → 令牌（只读 GitHub 用，不落盘）

GH_TOKEN_TIMEOUT = 5


def find_on_path(
    name: str, *, path: str | None = None, windows: bool | None = None, cwd: str | None = None,
    is_file: Callable[[str], bool] | None = None,
) -> str | None:
    """在 PATH 里找可执行文件，只认 PATH 里写成绝对路径的目录；当前目录和相对目录一律跳过。

    不用 ``shutil.which``：它在 Windows 上默认先搜当前目录（Linux 上遇到 PATH 里的空项也当当前目录），
    仓库根里有人放了 ``gh.exe`` 就会被当成 gh 执行。这里自己逐项查：
    - PATH 里的空项、``.``、任何相对路径、以及恰好等于当前目录的项，都跳过；
    - Windows 只认 ``<name>.exe``（不认 .bat/.cmd/.com，那些会被命令解释器再解释一遍）；别的系统认带执行权限的 ``<name>``。
    参数只给测试替换：``windows`` / ``cwd`` / ``path`` / ``is_file``。
    """

    is_windows = os.name == "nt" if windows is None else windows
    raw_path = os.environ.get("PATH", "") if path is None else path
    here = os.path.normcase(os.path.realpath(os.getcwd() if cwd is None else cwd))
    exists = is_file or (lambda p: os.path.isfile(p) and (is_windows or os.access(p, os.X_OK)))
    file_name = f"{name}.exe" if is_windows else name
    for entry in raw_path.split(";" if is_windows else ":"):
        entry = entry.strip().strip('"')
        if not entry or not os.path.isabs(entry):
            continue
        if os.path.normcase(os.path.realpath(entry)) == here:
            continue
        candidate = os.path.join(entry, file_name)
        if exists(candidate):
            return candidate
    return None


def resolve_github_token(runner: Callable[..., Any] = subprocess.run, which: Callable[[str], str | None] = find_on_path) -> str:
    """向本机已登录的 GitHub CLI 要令牌；要不到返回空串（按游客读），绝不抛、绝不弹登录框。

    - 只用 ``gh``：用 ``find_on_path`` 在 PATH 的绝对目录里找出绝对路径再执行（跳过当前目录，不让仓库里的同名程序顶替）；命令固定
      ``gh auth token --hostname github.com``；工作目录固定为主目录（没有就用临时目录），不是仓库里。
    - 不走 ``run_cli``：令牌不能进回执。输出只在这个函数里取出、校验形状（``github_collector.valid_token``），
      不符合形状（报错文字、空白、带换行的东西）一律当没有。令牌不写日志，异常文字里也不带。
    - ``stdin`` 关闭、5 秒超时、GH_PROMPT_DISABLED=1：没登录时 gh 直接失败，不会停下来等人输入。
    """

    found = which("gh")
    if not found or not Path(found).is_absolute():
        return ""
    home = Path.home()
    cwd = str(home) if home.is_dir() else tempfile.gettempdir()
    env = {**os.environ, "GH_PROMPT_DISABLED": "1", "GH_NO_UPDATE_NOTIFIER": "1", "NO_COLOR": "1"}
    try:
        result = runner([found, "auth", "token", "--hostname", "github.com"], cwd=cwd, capture_output=True,
                        encoding="utf-8", errors="replace",  # lenient-decode: 令牌只认固定形状，乱码就是不合格
                        timeout=GH_TOKEN_TIMEOUT, check=False, stdin=subprocess.DEVNULL, env=env, **quiet())
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    out = (result.stdout or "").strip()
    return out if gh.valid_token(out) else ""


class GithubTokenCache:
    """窗口进程内的令牌小仓库：第一次要用时才去问 gh，放在内存里；被 GitHub 拒了就丢掉，最多再问一次。

    线程安全（采集在后台线程跑）。令牌只存在 ``_token`` 里，``repr`` 不显示它。
    """

    MAX_REJECTIONS = 2  # 连续被拒这么多次就不再问 gh，按游客读，直到有一次成功或重启

    def __init__(self, resolver: Callable[[], str] = resolve_github_token) -> None:
        self._resolver = resolver
        self._lock = threading.Lock()
        self._token: str | None = None  # None＝还没问过；""＝问过没有
        self._rejections = 0

    def __repr__(self) -> str:
        return f"GithubTokenCache(resolved={self._token is not None}, rejections={self._rejections})"

    @property
    def refused(self) -> bool:
        """连续被拒已到上限：不再问 gh，按游客读，重启后重试。"""
        with self._lock:
            return self._rejections >= self.MAX_REJECTIONS

    def get(self) -> str:
        with self._lock:
            if self._token is None:
                self._token = "" if self._rejections >= self.MAX_REJECTIONS else self._resolver()
            return self._token

    def rejected(self) -> None:
        with self._lock:
            self._rejections += 1
            self._token = None if self._rejections < self.MAX_REJECTIONS else ""

    def accepted(self) -> None:
        with self._lock:
            self._rejections = 0


def no_prompt_env() -> dict[str, str]:
    """后台联网 git 的环境：不许停下来问密码，也不许凭据管理器弹登录窗口（没登录就直接失败，按离线算）。"""
    return {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}


def probe_online(root: Path, runner: Callable[..., Any] = subprocess.run) -> bool:
    try:
        result = runner(
            ["git", "ls-remote", "--exit-code", "origin", "HEAD"],
            cwd=str(root), capture_output=True, encoding="utf-8", timeout=PROBE_TIMEOUT, check=False,
            env=no_prompt_env(), **quiet(),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return bool(result.returncode == 0)


CHECKS = {
    "plc_check": ("plc check", ["plc", "check"]),
    "docs_check": ("plc docs check", ["plc", "docs", "check"]),
    "docs_sync_preview": ("docs sync 预览", ["plc", "docs", "sync", "--dry-run"]),
}


def run_check(root: Path, worktree: Path, project_id: str, key: str, runner: Callable[..., Any] = subprocess.run) -> Receipt:
    label, args = CHECKS[key]
    command = ["python", "-B", str(root / "main.py"), "-w", str(worktree), *args, project_id]
    shown = " ".join(command)
    try:
        result = runner(command, cwd=str(root), capture_output=True, encoding="utf-8", timeout=CHECK_TIMEOUT, check=False, **quiet())
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


# ---------------------------------------------------------------- “决定”页：同一条命令行，换一层皮
#
# 按钮拼出的参数见 decisions.build_args()。这里只负责“在控制根运行 main.py <参数>”：
#   * 不带任何 agent 标记、不加任何绕过选项；环境原样继承（agent 启动的界面会被命令按 agent 会话处理）；
#   * stdin 关掉：命令要口令时立刻回“必须在终端里输入”，不会挂住界面；
#   * 退出码和原文输出原样进回执，界面不改写、不吞掉。

NEEDS_TERMINAL_HINT = "必须由用户本人在自己的终端"


def cli_command(root: Path, args: Sequence[str]) -> list[str]:
    return [sys.executable, "-B", str(root / "main.py"), *args]


def needs_terminal(receipt: Receipt) -> bool:
    """命令说“要口令、不是交互终端”：界面改用 open_console 在新终端窗口里再运行同一条命令。"""
    return receipt.rc not in (0, None) and NEEDS_TERMINAL_HINT in receipt.output


def run_cli(root: Path, label: str, args: Sequence[str], runner: Callable[..., Any] = subprocess.run,
            timeout: int = CHECK_TIMEOUT) -> Receipt:
    command = cli_command(root, args)
    shown = " ".join(f'"{item}"' if " " in item or not item else item for item in command)
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    try:
        result = runner(command, cwd=str(root), capture_output=True, encoding="utf-8", errors="replace",  # lenient-decode: 命令输出只用于显示
                        timeout=timeout, check=False, stdin=subprocess.DEVNULL, env=env, **quiet())
    except (OSError, subprocess.SubprocessError) as error:
        return Receipt(_now_text(), label, shown, None, False, f"{type(error).__name__}: {error}")
    out, err = result.stdout or "", result.stderr or ""
    return Receipt(_now_text(), label, shown, result.returncode, False, out + err, out, err)


def console_flag() -> int:
    """Windows 的 CREATE_NEW_CONSOLE；别的系统返回 0（没有可弹的终端窗口）。测试替换这一处，不去改全局 os.name。"""
    return int(getattr(subprocess, "CREATE_NEW_CONSOLE", 0)) if os.name == "nt" else 0


# 新终端窗口里跑的小包装：把同一条命令当子进程跑完，再等用户按回车，好让用户看清结果。
# 命令的每个参数都当 argv 原样传进来（sys.argv[1:]），没有任何 shell 参与，参数里的 " & | ^ % 都只是普通字符。
_CONSOLE_WRAPPER = (
    "import subprocess, sys\n"
    "code = subprocess.call(sys.argv[1:])\n"
    "input('\\n命令已结束，退出码 %s。看完按回车关闭这个窗口……' % code)\n"
)


def open_console(root: Path, label: str, args: Sequence[str], opener: Callable[..., Any] = subprocess.Popen) -> Receipt:
    """在新的终端窗口里运行同一条命令（只在 Windows 有效）；界面看不到退出码，回执 rc 为“未验证”，
    用户在那个窗口里看结果，回来点“重新读取”。不经过 cmd：直接起 Python 小包装，参数按列表传。"""
    command = cli_command(root, args)
    shown = subprocess.list2cmdline(command)
    new_console = console_flag()
    if not new_console:
        return Receipt(_now_text(), label, shown, None, False, "这台电脑没有可弹出的终端窗口：请把上面的命令复制到终端里运行")
    try:
        opener([sys.executable, "-B", "-c", _CONSOLE_WRAPPER, *command], cwd=str(root), creationflags=new_console)
    except OSError as error:
        return Receipt(_now_text(), label, shown, None, False, f"{type(error).__name__}: {error}")
    return Receipt(_now_text(), label, shown, None, False, "已在新的终端窗口打开：在那里输入口令、看到结果后，回到这里点“重新读取”")
