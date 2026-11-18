# 卡 313：看板 GUI 修复、彻底清理根目录过时启动脚本与本机合并门禁并发适配（CHG-SCPT-2026-720）

> 卡片编号：`CARD-313-BOARD-BAT-CLEANUP V1.0`
> 隔离基线：`2220bbc7609e5bafda3d787128e6d468be28492d`（`main`）
> 路径根：`.`
> 档次：核心档
> 安全回路：否

本卡给 `CHG-SCPT-2026-720` 的本机合并分支（`antigravity/313`）提供“可改范围”，并顺带归并卡 311/312 推到完成后的变更单原件与版本变更台账（`CHG-SCPT-2026-718`、`CHG-SCPT-2026-719`、`CHG-DOCU-2026-129`）。

用户批准：2026-11-18 06:10:25-07:00（即 `2026-11-18T13:10:25Z`），用户在本机主对话先说“先做看板gui修复；然后做方案A”，在审阅《需求分析与技术实施计划》后明确回复：“同意/批准 CHG-SCPT-2026-720”（批准凭据 `user-confirmation:2026-11-18T13:10:25Z`）。

## 改成什么

1. **修复驾驶舱看板两个 GUI 问题**：
   - `SW8/scripts/cockpit_board/widgets/worktrees.py` 与 `SW8/scripts/cockpit_board/widgets/release.py`：在 `add_receipt` 中收到 `rc is not None` 的完成回执时，移除同一动作 `rc is None` 的“正在运行……”临时占位回执，消除 `[未验证] 正在运行……` 残留在页上的问题。
   - `SW8/scripts/cockpit_board/stations.py`、`widgets/worktrees.py`、`worktree_controller.py`：新增只读函数 `read_registered(root)` 读取控制根 `.auto-pm/continuity.db` 的 `agent_registry` 表（`status = 'active'`），在“工作树与分支”页“登记的 AI”区域直接展示内置 5 个前缀和当前已登记 AI 花名册，并在登记/注销成功后实时刷新。
2. **方案 A：彻底删除根目录过时的 `双击启动驾驶舱.bat` 并清理引用**（`CHG-SCPT-2026-720`）：
   - 删除仓库根目录 `双击启动驾驶舱.bat`（只保留现行 `00_Infrastructure/auto_pm/environment/双击打开驾驶舱看板.bat`）。
   - 同步更新 `tests/test_bat_scripts.py`、`tests/test_workspace_hygiene.py`、`SW8/auto_pm/application/core/governance_service.py`、`00_Infrastructure/auto_pm/tests/infrastructure/test_startup_guard.py`、`setup_env.bat`、`README.md`。
3. **本机合并门禁 Windows 多核并发与项目外改动衔接**（`CHG-SCPT-2026-720`）：
   - `SW8/auto_pm/application/core/gate_precheck_service.py`：当相关测试触发并行运行（`len(tests) >= PARALLEL_FROM`，如带上全套源码树守卫测试）时，超时上限使用 `FULL_TIMEOUT_SECONDS`（45 分钟）。
   - `SW8/scripts/pm_merge.py`：`run_gates` 调用 `gate precheck` 时传入多核并发 `--jobs` 与 `--json`；当项目内步骤全部通过但存在项目外改动（`outside_changes`）或 `full=True` 时，自动续跑根目录 `tests/` 测试套件验证根目录改动。

## 可改范围

| 路径 | 基线状态 | 用途 |
|---|---|---|
| `双击启动驾驶舱.bat` | 存在 | 方案 A：彻底删除过时根目录启动脚本 |
| `setup_env.bat` | 存在 | 启动提示改为 `00_Infrastructure\auto_pm\environment\双击打开驾驶舱看板.bat` |
| `README.md` | 存在 | 第 5 节启动入口去掉已删除的 `双击启动驾驶舱.bat` |
| `tests/test_bat_scripts.py` | 存在 | 已知批处理清单改为断言 `双击打开驾驶舱看板.bat` 在列、`双击启动驾驶舱.bat` 不在列 |
| `tests/test_workspace_hygiene.py` | 存在 | `ROOT_FILES_ALLOWED` 移出 `双击启动驾驶舱.bat` |
| `00_Infrastructure/auto_pm/tests/infrastructure/test_startup_guard.py` | 存在 | CRLF 检查目标更新为现行批处理脚本 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/governance_service.py` | 存在 | `ROOT_WHITELIST` 移出 `双击启动驾驶舱.bat` |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/gate_precheck_service.py` | 存在 | 并行测试集使用 `FULL_TIMEOUT_SECONDS` |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/pm_merge.py` | 存在 | `run_gates` 传入 `--jobs`、`--json` 并衔接根目录 `tests/` |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/cockpit_board/stations.py` | 存在 | 新增 `read_registered` 只读读取已登记 AI 花名册 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/cockpit_board/widgets/worktrees.py` | 存在 | 展示已登记 AI 花名册；完成回执到达时清除运行中占位回执 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/cockpit_board/widgets/release.py` | 存在 | 完成回执到达时清除运行中占位回执 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/cockpit_board/worktree_controller.py` | 存在 | 登记/注销成功后清空 `pending_registry` 并触发重读 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_cockpit_board_worktrees.py` | 存在 | 看板工位页运行回执替换与已登记 AI 花名册测试 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_cockpit_board_release_page.py` | 存在 | 发版页运行回执替换测试 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_gate_precheck_service.py` | 存在 | 并行预检测试超时阈值单测 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/infrastructure/test_pm_merge.py` | 存在 | `run_gates` 并发与根目录测试衔接单测 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/313_看板GUI修复与启动脚本清理实施卡_PM.md` | 计划新增 | 本卡 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-720.md` | 计划新增 | 本次变更单原件 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-718.md` | 存在 | 顺带归并卡 311 推到完成后的变更单原件 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-719.md` | 存在 | 顺带归并卡 312 推到完成后的变更单原件 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-129.md` | 存在 | 顺带归并卡 312 推到完成后的变更单原件 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/02_变更记录/01_版本变更台账.md` | 存在 | 版本变更台账同步入库 |

## 验收

- `pytest tests/test_bat_scripts.py tests/test_workspace_hygiene.py 00_Infrastructure/auto_pm/tests/infrastructure/test_startup_guard.py` 退出 0；
- `pytest SW8/tests/core/test_cockpit_board_worktrees.py SW8/tests/core/test_cockpit_board_release_page.py SW8/tests/core/test_gate_precheck_service.py SW8/tests/infrastructure/test_pm_merge.py` 退出 0；
- 改动文件 `ruff check` 与 `mypy` 退出 0；
- 独立审计（另一个会话）放行后，`pm_merge.py merge antigravity-aa3162` 退出 0。
