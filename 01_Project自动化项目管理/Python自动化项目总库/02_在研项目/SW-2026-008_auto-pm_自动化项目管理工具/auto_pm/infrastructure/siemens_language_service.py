"""auto_pm.infrastructure.siemens_language_service - 调用 Dynamic Siemens Language Support 插件自带的命令行（M3-PLUGIN）。

只在本机调用用户已安装的插件命令行 ``siemens-lsp``（``check`` 诊断、``test`` 运行 ``.scltest``），不复制、不分发、不放进仓库或 CI；
用户为非商业使用并尊重其著作权。找不到命令行时返回 ``available=False`` 的结果——调用方必须把它当作“未验证”，而不是通过。

定位顺序：环境变量 ``AUTO_PM_SIEMENS_LSP``（指向可执行文件）→ ``~/.vscode/extensions`` 下版本号最高的
``dynamicengineering.dynamic-siemens-language-support-*`` 里随平台的 ``out/go/<平台>/siemens-lsp``。
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path

from auto_pm.domain.plc.language_service import LanguageServiceBinary, LanguageServiceResult
from auto_pm.infrastructure.process_scope import run_in_scope

ENV_BINARY = "AUTO_PM_SIEMENS_LSP"
EXTENSION_PREFIX = "dynamicengineering.dynamic-siemens-language-support-"
MAX_MESSAGES = 5
DEFAULT_TIMEOUT_SECONDS = 600

_PLATFORM_DIRS = {"win32": ("windows-amd64", "siemens-lsp.exe"), "linux": ("linux-amd64", "siemens-lsp"), "darwin": ("darwin-arm64", "siemens-lsp")}
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_CHECK_ERROR = re.compile(r": ERROR: ")
_TEST_ERROR = re.compile(r"\bSCLTEST_[A-Z0-9_]+\b")
_TEST_FAIL = re.compile(r"^\s*--- FAIL: |^FAIL\b|ASSERT failed")
_CASES = re.compile(r"running (\d+)/(\d+) cases")
_VERSION = re.compile(r"-(\d+(?:\.\d+)*)$")

Runner = Callable[[list[str], Path, Mapping[str, str], int], "subprocess.CompletedProcess[str]"]


def _version_key(name: str) -> tuple[int, ...]:
    m = _VERSION.search(name)
    return tuple(int(x) for x in m.group(1).split(".")) if m else (0,)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def locate_binary(env: Mapping[str, str] | None = None, home: Path | None = None, platform: str | None = None) -> LanguageServiceBinary | None:
    """找到本机的命令行；找不到返回 None（不抛异常）。"""

    environ = os.environ if env is None else env
    explicit = environ.get(ENV_BINARY, "").strip()
    if explicit:
        path = Path(explicit)
        return LanguageServiceBinary(str(path), "env", _sha256(path)) if path.is_file() else None
    plat = platform or sys.platform
    entry = next((v for k, v in _PLATFORM_DIRS.items() if plat.startswith(k)), None)
    if entry is None:
        return None
    folder, exe = entry
    extensions = (home or Path.home()) / ".vscode" / "extensions"
    if not extensions.is_dir():
        return None
    candidates = [p for p in extensions.iterdir() if p.is_dir() and p.name.lower().startswith(EXTENSION_PREFIX)]
    for ext in sorted(candidates, key=lambda p: _version_key(p.name), reverse=True):
        binary = ext / "out" / "go" / folder / exe
        if binary.is_file():
            version = ext.name[len(EXTENSION_PREFIX):]
            return LanguageServiceBinary(str(binary), version, _sha256(binary))
    return None


def _default_runner(args: list[str], cwd: Path, env: Mapping[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
    # TD-SW008-188：命令行起在门禁的进程范围里，门禁超时被放弃时连同它的子孙进程一起收掉
    return run_in_scope(args, cwd, env, timeout)


def _relative(text: str, root: Path) -> str:
    """输出里的绝对路径换成相对工程根的路径，证据里不留机器相关的前缀。"""

    for variant in {str(root), str(root.resolve())}:
        text = text.replace(variant + os.sep, "").replace(variant, ".")
    return text


class SiemensLanguageService:
    """实现 ``auto_pm.domain.plc.language_service.LanguageService`` 端口。"""

    def __init__(self, binary: LanguageServiceBinary | None, runner: Runner | None = None, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> None:
        self._binary = binary
        self._runner: Runner = runner or _default_runner
        self._timeout = timeout

    @classmethod
    def discover(cls, runner: Runner | None = None, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> SiemensLanguageService:
        return cls(locate_binary(), runner=runner, timeout=timeout)

    @property
    def available(self) -> bool:
        return self._binary is not None

    @property
    def binary(self) -> LanguageServiceBinary | None:
        return self._binary

    @property
    def timeout(self) -> int:
        """Seconds each ``check`` / ``test`` call may run before its process is killed."""
        return self._timeout

    def check(self, root: Path) -> LanguageServiceResult:
        return self._run("check", root)

    def test(self, root: Path) -> LanguageServiceResult:
        return self._run("test", root)

    def _run(self, command: str, root: Path) -> LanguageServiceResult:
        if self._binary is None:
            return LanguageServiceResult(command=command, available=False, exit_code=None, summary="未找到 Dynamic Siemens Language Support 插件命令行")
        with tempfile.TemporaryDirectory(prefix="auto_pm_lsp_") as scratch:
            env = {**os.environ, "TEMP": scratch, "TMP": scratch, "TMPDIR": scratch}
            try:
                done = self._runner([self._binary.path, command, "."], root, env, self._timeout)
            except (OSError, subprocess.TimeoutExpired) as exc:
                return LanguageServiceResult(command=command, available=True, exit_code=-1, error_count=1, messages=(f"命令行未能完成: {exc}",), summary=str(exc), binary=self._binary, diagnostics=("命令行未能完成",))
        text = _relative(_ANSI.sub("", (done.stdout or "") + (done.stderr or "")), root)
        lines = [ln for ln in text.splitlines() if ln.strip()]
        if command == "check":
            hits = [ln for ln in lines if _CHECK_ERROR.search(ln)]
        else:
            hits = [ln for ln in lines if _TEST_ERROR.search(ln) or _TEST_FAIL.search(ln)]
        error_count = len(hits)
        if done.returncode != 0 and error_count == 0:
            error_count = 1  # 退出码非零而没有解析到诊断行：按一个未归类错误算，不能当作通过
            hits = lines[-3:] or ["命令行退出码非零且没有输出"]
        cases = _CASES.search(text)
        return LanguageServiceResult(
            command=command, available=True, exit_code=done.returncode, error_count=error_count, messages=tuple(hits[:MAX_MESSAGES]),
            summary=lines[-1] if lines else "", binary=self._binary,
            cases_run=int(cases.group(1)) if cases else None, cases_total=int(cases.group(2)) if cases else None,
            diagnostics=tuple(hits),
        )


def default_language_service(timeout: int | None = None) -> SiemensLanguageService:
    """应用层组合根用：发现本机的命令行（可能不可用）。

    ``timeout`` 是命令行单次调用的时限（秒），不传用 ``DEFAULT_TIMEOUT_SECONDS``。
    """

    return SiemensLanguageService.discover() if timeout is None else SiemensLanguageService.discover(timeout=timeout)
