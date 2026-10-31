"""PLC-HMI 概念映射：程序入口（auto-pm 主入口（python -m auto_pm 的启动点））

像 PLC 的启动流程，程序的上电入口点。

--- 原始注释 ---

auto-pm 包入口 - 支持 python -m auto_pm 执行

Windows GBK 环境下，site 模块加载含中文路径的 .pth 文件时会触发
UnicodeDecodeError 崩溃。设置 PYTHONUTF8=1 可防止此问题。
对于 Rich 输出的终端编码适配，在 cli/__main__.py 中处理。
"""

from __future__ import annotations

import os
import sys

_package_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_package_dir)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# 必须在导入 cli 模块之前修复编码，因为 rich Console 在模块导入时初始化
if sys.platform == "win32" and sys.stdout is not None:
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)  # UTF-8
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

from auto_pm.cli.__main__ import cli  # noqa: E402

if __name__ == "__main__" or __name__ == "auto_pm.__main__":
    if len(sys.argv) == 1:
        sys.argv.append("gui")
    cli()
