"""驾驶舱总控屏入口（PySide6）。

项目经理看板只读（今天 / 问题 / 全部项目 / 项目页），工程工位（接着干 / 人工路线六步 / 控制台）。
所有代码在同目录的 cockpit_board 包里：theme（颜色字体一处改）、viewmodel（纯 Python 算法）、
policy（按钮规矩）、actions（本机动作）、widgets（画面）、app（主窗口）。本文件只负责启动。

运行方式（控制根下，或双击 控制根/00_Infrastructure/auto_pm/environment/双击打开驾驶舱看板.bat）：
    python -B <本脚本> --root .
    python -B <本脚本> --root . --screenshot 看板.png   # 离屏截图后退出（自查用）
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cockpit_board.app import (  # noqa: E402,F401 - 测试和 bat 从这里取
    BoardLoader,
    CockpitWindow,
    load_board,
    main,
    parse_options,
    run,
)

if __name__ == "__main__":
    sys.exit(run())
