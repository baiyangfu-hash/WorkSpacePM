#!/bin/sh
# 云端会话自检（只读，D-116；D-156 卡②起改成薄壳）：开工、跑测试之前先跑一遍。
# 用法：sh 00_Infrastructure/auto_pm/environment/cloud_selfcheck.sh
# 退出码：0＝可以开工；1＝至少一项不通过（看 [失败] 行）；127＝连 Python 都找不到。不改任何东西。
# 检查逻辑都在同目录的 env_check.py（只用标准库，Windows 也用它）；这里只负责找一个 Python 来跑它。
# 背景：SessionStart 钩子（.claude/hooks/session-start.sh）在“项目线程”这类会话里不一定被执行，
#       没有 .venv 时系统 python 3.13 缺 pytest-cov、xdist，Qt 缺 libEGL，测试会以难懂的方式失败。
here="$(dirname "$0")"
for py in python3 python; do
    # D-198：只认“真能跑”的 Python。Windows 的 python3.exe 常是应用商店别名占位桩，command -v 找得到，
    # 一运行就退出 49，不先试跑就 exec 会把它当成真 Python。
    if command -v "$py" >/dev/null 2>&1 && "$py" -c "" >/dev/null 2>&1; then
        exec "$py" "$here/env_check.py"
    fi
done
echo "[失败] 找不到 python3 或 python，没法运行 env_check.py" >&2
echo "       补救：先安装 Python 3.12，再运行 sh 00_Infrastructure/auto_pm/environment/setup_env.sh" >&2
exit 127
