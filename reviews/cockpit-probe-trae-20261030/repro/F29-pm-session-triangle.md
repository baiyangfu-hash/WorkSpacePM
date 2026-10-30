# F29 最短复现
ls "0100_项目/ZZ-2026-901_cockpit_probe_fake/PM_SESSION_ZZ-2026-901.md"   # 生成器新建（F7）
.venv/bin/python main.py python check ZZ-2026-901 | grep PM_SESSION       # 门禁要求存在（✓）
grep -n "已退役" AGENTS.md | head -1                                       # 治理禁止新建
