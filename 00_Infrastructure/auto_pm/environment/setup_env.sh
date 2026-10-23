#!/bin/sh
# Auto-PM 研发工作台 - Linux/macOS 环境初始化（与 setup_env.bat 同一套步骤、同一份锁定文件）
# 用法：sh 00_Infrastructure/auto_pm/environment/setup_env.sh（在哪个目录执行都行，脚本自己回到工作空间根）
# 放在这里而不是根目录：根目录有白名单（governance_service.py），新增根文件会被驾驶舱体检判为不合规。
# 可选环境变量：PIP_INDEX_URL（默认用 pip 自己的源；国内可设为清华源）
set -eu

cd "$(dirname "$0")/../../.."

echo "=============================================================================="
echo "       Auto-PM 工业级 AI 研发工作台 - 一键环境初始化（Linux）"
echo "=============================================================================="

# 1. 找 Python 3.12：锁定文件只覆盖 3.12
PY_EXE=""
for candidate in python3.12 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1 \
        && "$candidate" -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)" >/dev/null 2>&1; then
        PY_EXE="$candidate"
        break
    fi
done
if [ -z "$PY_EXE" ]; then
    echo "[错误] 未找到 Python 3.12。依赖锁定文件只覆盖 Python 3.12。" >&2
    echo "       Ubuntu 24.04: sudo apt-get install python3.12 python3.12-venv" >&2
    exit 1
fi
echo "[1/5] Python: $("$PY_EXE" --version)"

# 2. 虚拟环境（.venv/bin/python 也是 Git 钩子会优先找的解释器）
if [ ! -d ".venv" ]; then
    echo "[2/5] 正在创建虚拟环境 (.venv)..."
    "$PY_EXE" -m venv .venv
else
    echo "[2/5] 虚拟环境 (.venv) 已存在，跳过创建。"
fi
VENV_PY=".venv/bin/python"
if ! "$VENV_PY" -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)" >/dev/null 2>&1; then
    echo "[错误] 已有的 .venv 不是 Python 3.12。请把 .venv 改名备份（例如 .venv.old）后重新运行本脚本。" >&2
    exit 1
fi

# 3. 按锁定文件安装（精确版本，不解析新依赖）
LOCK_FILE="00_Infrastructure/auto_pm/environment/requirements-lock-py312-win.txt"
if [ ! -f "$LOCK_FILE" ]; then
    echo "[错误] 依赖锁定文件缺失: $LOCK_FILE" >&2
    exit 1
fi
echo "[3/5] 正在按锁定文件安装依赖..."
"$VENV_PY" -m pip install --quiet --no-deps -r "$LOCK_FILE"
"$VENV_PY" -m pip check

# 4. Qt（PySide6）需要的系统库：缺了图形界面和 Qt 相关测试会在导入时失败
echo "[4/5] 正在检查 Qt 运行库..."
if ! QT_QPA_PLATFORM=offscreen "$VENV_PY" -c "from PySide6.QtWidgets import QApplication" >/dev/null 2>&1; then
    echo "[警告] PySide6 无法加载（通常缺 libEGL/libGL 等系统库）。命令行可用，界面和 Qt 测试不可用。" >&2
    echo "       Ubuntu/Debian: sudo apt-get install -y libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3" >&2
fi

# 5. 稳定入口的三件套必须在
for required in \
    "00_Infrastructure/auto_pm/launcher/launch.py" \
    "00_Infrastructure/auto_pm/active_release.json" \
    "00_Infrastructure/auto_pm/deployment_manifest.json"; do
    if [ ! -f "$required" ]; then
        echo "[错误] 稳定入口文件缺失: $required" >&2
        exit 1
    fi
done
echo "[5/5] 稳定入口已就绪；运行时由 stable launcher 校验 active release。"

# 已装的 Git 门禁钩子必须可执行：没有执行位时 Git 会静默跳过，门禁等于没装。
# 1.3.3 及更早的发布版写钩子时不设执行位，这里补上（只处理已存在的钩子，不替你安装）。
for hook in .git/hooks/pre-commit .git/hooks/commit-msg; do
    if [ -f "$hook" ] && [ ! -x "$hook" ]; then
        chmod +x "$hook"
        echo "      已给 $hook 加上执行位（否则 Git 会跳过这道门禁）"
    fi
done

echo
echo "  [成功] 环境就绪。"
echo "  • 命令行：.venv/bin/python main.py --help"
echo "  • 体检：  .venv/bin/python main.py doctor"
echo "  • 没有显示器时用界面/Qt 测试前先设：export QT_QPA_PLATFORM=offscreen"
