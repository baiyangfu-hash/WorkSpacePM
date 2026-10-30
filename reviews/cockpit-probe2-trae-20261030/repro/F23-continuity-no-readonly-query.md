# F23 复现：continuity 没有只读查询命令（Work/Run/Lease 无 list/show）

被测：main `17b5faf5`，部署版 `1.3.3-d8f7c8b`（2026-10-30）

```bash
cd /workspace
.venv/bin/python main.py continuity --help        # exit 0：只有 checkpoint/handoff/lease/run/work
.venv/bin/python main.py continuity work --help   # exit 0：authorize/create/relate/transition（无 list/show）
.venv/bin/python main.py continuity run --help    # exit 0：start/transition（无 list/show）
.venv/bin/python main.py continuity lease --help  # exit 0：只有 renew
```

源码层（main 的 SW-2026-008 项目）同样没有只读查询，只多了 `adjudicate`：

```bash
cd /workspace
PYTHONPATH="01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具" \
  .venv/bin/python -m auto_pm -w /workspace continuity work --help   # exit 0
```

结论：想知道某个 Work/Run/租约当前状态，只能靠写入类命令的报错回显，或直读 `.auto-pm/continuity.db`。
