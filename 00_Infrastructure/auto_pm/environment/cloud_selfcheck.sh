#!/bin/sh
# 云端会话自检（只读，D-116）：会话里跑测试之前先跑一遍，缺什么直接报错并给出补救命令。
# 用法：sh 00_Infrastructure/auto_pm/environment/cloud_selfcheck.sh
# 退出码：0＝可以跑测试；1＝至少一项不通过（看 [失败] 行）。不改任何东西。
# 背景：SessionStart 钩子（.claude/hooks/session-start.sh）在“项目线程”这类会话里不一定被执行，
#       没有 .venv 时系统 python 3.13 缺 pytest-cov、xdist，Qt 缺 libEGL，测试会以难懂的方式失败。
cd "$(dirname "$0")/../../.." || exit 1

bad=0
fail() { echo "[失败] $1" >&2; echo "       补救：$2" >&2; bad=1; }
ok() { echo "[通过] $1"; }

VENV_PY=".venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
    fail "没有 .venv（系统 python 缺 pytest-cov、xdist 等开发依赖）" "sh 00_Infrastructure/auto_pm/environment/setup_env.sh"
else
    if "$VENV_PY" -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 12) else 1)" >/dev/null 2>&1; then
        ok ".venv 是 Python 3.12"
    else
        fail ".venv 不是 Python 3.12" "mv .venv .venv.old && sh 00_Infrastructure/auto_pm/environment/setup_env.sh"
    fi
    for mod in pytest pytest_cov xdist; do
        if "$VENV_PY" -c "import $mod" >/dev/null 2>&1; then
            ok ".venv 里能导入 $mod"
        else
            fail ".venv 里导入 $mod 失败" "sh 00_Infrastructure/auto_pm/environment/setup_env.sh"
        fi
    done
    if QT_QPA_PLATFORM=offscreen "$VENV_PY" -c "from PySide6.QtWidgets import QApplication" >/dev/null 2>&1; then
        ok "PySide6.QtWidgets 能导入（offscreen）"
    else
        fail "PySide6.QtWidgets 导入失败（通常缺系统库 libEGL 等）" "sudo apt-get update && sudo apt-get install -y libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3"
    fi
fi

if [ "$(git rev-parse --is-shallow-repository 2>/dev/null)" = "true" ]; then
    fail "浅克隆：依赖锁定提交的 PLC 基准测试会失败" "git fetch --unshallow origin"
else
    ok "Git 历史完整"
fi

if [ "$bad" -eq 0 ]; then
    echo "[云端自检] 全部通过。用 .venv/bin/python -m pytest 跑测试。"
else
    echo "[云端自检] 有未通过项：先按上面的“补救”处理，再跑测试。" >&2
fi
exit "$bad"
