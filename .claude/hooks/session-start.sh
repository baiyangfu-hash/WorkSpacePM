#!/bin/bash
# 云端会话开机自检（Claude Code 云端会话的 SessionStart 钩子；本机会话直接跳过）
# 做三件事：补全 Git 历史（PLC 基准测试要锁定提交 1e1ef760）、装 Qt 系统库、跑 setup_env.sh 建 .venv。
# 每一步失败都打印原因和手动补救命令，但不中断会话；最后一行汇总给 Claude 和用户看。可重复运行。
set -uo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
    exit 0
fi

ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$ROOT" || exit 0

PIN_COMMIT="1e1ef760c6f9c8814dbe47d681da760c887d28ee"
QT_PACKAGES="libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3"
FAILED=()

step() { echo "[云端自检] $*"; }
fail() { FAILED+=("$1"); echo "[云端自检][失败] $1：$2" >&2; echo "            补救：$3" >&2; }

# 1. Git 历史：浅克隆时补全；补全失败至少把锁定提交拉下来
if [ "$(git rev-parse --is-shallow-repository 2>/dev/null)" = "true" ]; then
    step "浅克隆，正在补全 Git 历史..."
    git fetch --quiet --unshallow origin 2>&1 | tail -n 3 \
        || step "补全历史未成功，改为只拉锁定提交 ${PIN_COMMIT:0:8}"
fi
if ! git cat-file -e "${PIN_COMMIT}^{commit}" 2>/dev/null; then
    git fetch --quiet origin "$PIN_COMMIT" 2>&1 | tail -n 3
fi
if git cat-file -e "${PIN_COMMIT}^{commit}" 2>/dev/null; then
    step "Git 历史就绪（含锁定提交 ${PIN_COMMIT:0:8}）"
else
    fail "Git 历史" "缺锁定提交 ${PIN_COMMIT:0:8}，PLC 基准测试会失败" "git fetch --unshallow origin"
fi

# 2. Qt 系统库：缺哪个装哪个
missing=()
for pkg in $QT_PACKAGES; do
    dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed" || missing+=("$pkg")
done
if [ ${#missing[@]} -eq 0 ]; then
    step "Qt 系统库已齐"
else
    SUDO=""
    [ "$(id -u)" -ne 0 ] && SUDO="sudo"
    step "正在安装 Qt 系统库：${missing[*]}"
    if $SUDO apt-get update -qq >/dev/null 2>&1 \
        && DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y -qq "${missing[@]}" >/dev/null 2>&1; then
        step "Qt 系统库安装完成"
    else
        fail "Qt 系统库" "apt 安装失败，界面和 Qt 测试会在导入时失败" "sudo apt-get install -y $QT_PACKAGES"
    fi
fi

# 3. Python 环境（.venv，按锁定文件装依赖）
if sh 00_Infrastructure/auto_pm/environment/setup_env.sh; then
    step ".venv 就绪"
else
    fail "Python 环境" "setup_env.sh 未成功（看上面的 [错误] 行）" "sh 00_Infrastructure/auto_pm/environment/setup_env.sh"
fi

# 本会话后续命令：优先用 .venv 里的 python/pytest；无显示器时 Qt 走 offscreen
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
    {
        echo "export PATH=\"$ROOT/.venv/bin:\$PATH\""
        echo "export QT_QPA_PLATFORM=offscreen"
    } >> "$CLAUDE_ENV_FILE"
fi

if [ ${#FAILED[@]} -eq 0 ]; then
    echo "[云端自检] 全部就绪：Git 历史、Qt 系统库、.venv。可直接跑 pytest。"
else
    echo "[云端自检] 未完成：${FAILED[*]}。先按上面的“补救”命令处理，再跑测试。"
fi
exit 0
