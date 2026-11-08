#!/usr/bin/env python3
"""环境自检（只读，D-156 卡②）：换电脑、换云服务商、换 AI agent 之后，开工前先跑一遍。

用法（在工作空间任意目录执行都行，脚本自己找回仓库根）::

    Linux / 云端 / macOS:  python3 00_Infrastructure/auto_pm/environment/env_check.py
    Windows:               python 00_Infrastructure\\auto_pm\\environment\\env_check.py

退出码：0＝可以开工；1＝至少一项不通过（看 ``[失败]`` 行和它下面的“补救”）。不改任何东西。

只用标准库、不 import ``auto_pm``：它要在 ``.venv`` 还没装好（甚至系统 Python 什么依赖都没有）时就能跑。
``main.py`` 一启动就要 click、rich，所以做不了这件事；装好以后想看更多体检项用 ``main.py doctor``。
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

REQUIRED_PYTHON = (3, 12)  # 依赖锁定文件只覆盖 3.12
# 开发依赖：缺任何一个，测试会以难懂的方式失败（pytest-cov、xdist 是 pytest 的插件）
REQUIRED_MODULES = ("pytest", "pytest_cov", "xdist", "click", "rich", "PySide6")
PROBE_TIMEOUT_SECONDS = 180

Probe = Callable[[Sequence[str], dict[str, str] | None], tuple[int, str]]


@dataclass(frozen=True)
class Check:
    """一项检查的结果；``fix`` 只在没通过时有内容。"""

    name: str
    ok: bool
    fix: str = ""


def repo_root() -> Path:
    """本文件在 <根>/00_Infrastructure/auto_pm/environment/，往上三层就是工作空间根。"""

    return Path(__file__).resolve().parents[3]


def venv_python(root: Path, *, windows: bool) -> Path:
    return root / ".venv" / ("Scripts/python.exe" if windows else "bin/python")


def setup_command(*, windows: bool) -> str:
    return "双击根目录的 setup_env.bat" if windows else "sh 00_Infrastructure/auto_pm/environment/setup_env.sh"


def run_probe(command: Sequence[str], env: dict[str, str] | None = None) -> tuple[int, str]:
    """跑一条子进程，返回（退出码, 标准输出）；起不来或超时按失败处理，不抛异常。"""

    try:
        done = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",  # lenient-decode: 只读探针的输出，读不懂的字节不该让自检本身崩掉
            timeout=PROBE_TIMEOUT_SECONDS,
            env=env,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return done.returncode, done.stdout


_VERSION_CODE = "import sys; print('%d.%d' % sys.version_info[:2])"
_IMPORT_CODE = (
    "import importlib\n"
    "for name in {names!r}:\n"
    "    try:\n"
    "        importlib.import_module(name)\n"
    "    except Exception:\n"
    "        print(name)\n"
)
_QT_CODE = "from PySide6.QtWidgets import QApplication"


def run_checks(root: Path, *, windows: bool | None = None, probe: Probe = run_probe) -> list[Check]:
    """所有检查，按顺序；``.venv`` 不存在时后面依赖它的几项不再检查（会重复报同一个原因）。"""

    windows = (os.name == "nt") if windows is None else windows
    setup = setup_command(windows=windows)
    checks: list[Check] = []
    python = venv_python(root, windows=windows)

    if not python.is_file():
        checks.append(Check("没有 .venv（系统 Python 缺开发依赖）", False, setup))
    else:
        interpreter = str(python)
        code, out = probe([interpreter, "-c", _VERSION_CODE], None)
        wanted = f"{REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}"
        found = out.strip() if code == 0 else ""
        if found == wanted:
            checks.append(Check(f".venv 是 Python {wanted}", True))
        else:
            shown = found or "读不出版本"
            rename = r"把 .venv 改名为 .venv.old，再" if windows else "mv .venv .venv.old && "
            checks.append(Check(f".venv 不是 Python {wanted}（现在：{shown}）", False, f"{rename}{setup}"))

        code, out = probe([interpreter, "-c", _IMPORT_CODE.format(names=REQUIRED_MODULES)], None)
        missing = [line.strip() for line in out.splitlines() if line.strip()] if code == 0 else list(REQUIRED_MODULES)
        if missing:
            checks.append(Check(f".venv 里导入失败：{'、'.join(missing)}", False, setup))
        else:
            checks.append(Check("开发依赖都能导入（" + "、".join(REQUIRED_MODULES) + "）", True))

        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        code, _ = probe([interpreter, "-c", _QT_CODE], env)
        if code == 0:
            checks.append(Check("PySide6.QtWidgets 能导入（offscreen）", True))
        elif windows:
            checks.append(Check("PySide6.QtWidgets 导入失败", False, setup))
        else:
            checks.append(
                Check(
                    "PySide6.QtWidgets 导入失败（Linux 上通常缺系统库 libEGL 等）",
                    False,
                    "sudo apt-get update && sudo apt-get install -y libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3",
                )
            )

    code, out = probe(["git", "-C", str(root), "rev-parse", "--is-shallow-repository"], None)
    if code != 0:
        checks.append(Check("找不到 git，或这里不是 Git 仓库", False, "安装 git，并在克隆出来的仓库里运行本脚本"))
    elif out.strip() == "true":
        checks.append(Check("浅克隆：依赖锁定提交的 PLC 基准测试会失败", False, "git fetch --unshallow origin"))
    else:
        checks.append(Check("Git 历史完整", True))
    return checks


def format_report(checks: Sequence[Check]) -> str:
    lines: list[str] = []
    for check in checks:
        if check.ok:
            lines.append(f"[通过] {check.name}")
        else:
            lines.append(f"[失败] {check.name}")
            lines.append(f"       补救：{check.fix}")
    return "\n".join(lines)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        if stream.isatty():
            reconfigure(errors="replace")  # 真终端：用终端自己的编码，旧代码页打不出的字不要崩
        else:
            # 输出被重定向、接管道、被别的程序（CI、AI agent）读走时：Windows 默认是 ANSI 代码页，中文会变成 "?"，
            # 所以固定写 UTF-8，读的一方按 UTF-8 解就行
            reconfigure(encoding="utf-8", errors="replace")
    checks = run_checks(repo_root())
    print(format_report(checks))
    if all(check.ok for check in checks):
        print("[环境自检] 全部通过。可以开工：先读 AGENTS.md，再按 cockpit-entry 做只读定位。")
        return 0
    print("[环境自检] 有未通过项：先按上面的“补救”处理，再重跑本脚本；退出码非 0 不要开工。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
