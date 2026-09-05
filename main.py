"""Auto-PM 工业级 AI 研发工作台 - 根目录快捷启动入口（NG-WP-13 双槽版）

外部使用者在工作空间根目录运行 `python main.py`，即可一键拉起桌面驾驶舱。
本入口只从稳定部署容器 `00_Infrastructure/auto_pm` 的双槽指针解析 release：

    active_release.json 有效        → 加载 active release
    active 无效且 previous 有效     → 加载 previous release（唯一回退）
    双槽均无效                      → 打印诊断并以非零码退出（fail-closed）

不再回退研发母体、平铺源码或 editable/.pth 安装。
设置环境变量 AUTO_PM_ENTRY_RESOLVE_ONLY=1 时只做解析与 provenance 断言后退出，
供隔离验证子进程使用。

退出码：0 正常；2 容器布局无效；3 指针未初始化/不可读；
4 release 无效（越界/缺失/未登记 manifest）；5 provenance 断言失败。
"""

import os
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).parent.resolve()
CONTAINER_ROOT = WORKSPACE_ROOT / "00_Infrastructure" / "auto_pm"
RESOLVE_ONLY = os.environ.get("AUTO_PM_ENTRY_RESOLVE_ONLY") == "1"

sys.path.insert(0, str(CONTAINER_ROOT / "launcher"))

try:
    from bootstrap import BootstrapError, resolve_with_fallback
except ImportError as exc:  # 容器 launcher 缺失属于布局损坏
    print(f"main: 容器 launcher 缺失，无法解析 release: {exc}", file=sys.stderr)
    sys.exit(2)

try:
    release_dir, slot_used = resolve_with_fallback(CONTAINER_ROOT)
except BootstrapError as exc:
    print(f"main: {exc}", file=sys.stderr)
    print("main: 请先完成 NG-WP-14/15 的 release 部署与切流，或运行 setup_env.bat 重建环境", file=sys.stderr)
    sys.exit(exc.exit_code)

# 将 release 置于最前，任何后续 import 都必须来自 release
sys.path.insert(0, str(release_dir))
os.environ["AUTO_PM_WORKSPACE"] = str(WORKSPACE_ROOT)

if __name__ == "__main__":
    import auto_pm

    # provenance 硬断言：auto_pm 必须来自 release，禁止任何母体/平铺/持久安装泄漏
    if not Path(auto_pm.__file__).resolve().is_relative_to(release_dir):
        print(
            f"main: provenance 断言失败: auto_pm 来自 {auto_pm.__file__}，"
            f"而非 release {release_dir}",
            file=sys.stderr,
        )
        sys.exit(5)

    if RESOLVE_ONLY:
        print(f"main: resolve-only ok; slot={slot_used}; release={release_dir}")
        print(f"main: auto_pm provenance: {Path(auto_pm.__file__).resolve()}")
        sys.exit(0)

    from auto_pm.ui.qml_main_window import run_qml_gui

    # 启动桌面驾驶舱
    sys.exit(run_qml_gui(workspace_root=str(WORKSPACE_ROOT)))
