# F10 最短复现
ls -d "0100_项目/ZZ-2026-901_cockpit_probe_fake"   # 目录存在
.venv/bin/python main.py context resolve --path "0100_项目/ZZ-2026-901_cockpit_probe_fake"             # exit 2: Directory does not exist
.venv/bin/python main.py context resolve --path "/workspace/0100_项目/ZZ-2026-901_cockpit_probe_fake"  # 过存在性检查（撞 F9）
