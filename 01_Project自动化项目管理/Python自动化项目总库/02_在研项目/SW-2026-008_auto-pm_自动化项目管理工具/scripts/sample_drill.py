"""样件联调：一条命令跑完整条收口线（发版前门槛）。

用假任务当样件，在临时目录里从入箱一路跑到收口和台账对账，喂乱序、中文、多项目、故意违规等料型。
不碰真实工作区、不碰账本。退出码 0 才算过；已知缺陷以 xfail 登记，它一旦意外变绿（XPASS）也算不过，
提醒去掉对应的 xfail 标记。

用法（在 SW-2026-008 目录）：python scripts/sample_drill.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

DRILL_FILES = (
    "tests/e2e/test_closure_drill.py",
    "tests/e2e/test_closure_drill_agent_misconduct.py",
    "tests/e2e/test_release_pycache_drill.py",
)


def main() -> int:
    project = Path(__file__).resolve().parent.parent
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", QT_QPA_PLATFORM=os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    command = [
        sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", "-rxX", "-n", "4", *DRILL_FILES,
    ]
    result = subprocess.run(command, cwd=project, env=environment, check=False)
    print("样件联调：" + ("通过" if result.returncode == 0 else f"不通过（pytest 退出码 {result.returncode}）"))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
