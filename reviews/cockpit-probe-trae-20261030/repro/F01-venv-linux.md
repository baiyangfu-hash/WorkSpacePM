# F1 最短复现
ls .venv                 # 全新克隆不存在
ls setup_env.bat         # 根目录只有 Windows 引导
ls 00_Infrastructure/auto_pm/environment/setup_env.sh   # Linux 引导存在但入口文档未提
grep -n "venv" .trae/skills/cockpit-entry/SKILL.md | head -3   # 只见 Windows 路径
