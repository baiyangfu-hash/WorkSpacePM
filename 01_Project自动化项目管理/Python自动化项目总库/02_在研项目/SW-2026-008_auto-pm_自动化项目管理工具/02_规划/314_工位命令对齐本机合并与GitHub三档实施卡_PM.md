# 卡 314：工位命令全链路对齐本机合并与 GitHub 三档（CHG-SCPT-2026-721）

> 卡片编号：`CARD-314-WORKTREE-LOCAL-MAIN V1.0`
> 隔离基线：`cfbb2316b595`（`main`）
> 路径根：`.`
> 档次：普通改动（按 `FLOW-001` 属驾驶舱代码/看板/测试，走本机收口；因现役发布版 `1.3.3-65fb143` 的提交钩子仍要求单号，配 `CHG-SCPT-2026-721`）
> 安全回路：否

本卡实现《驾驶舱减肥方案》核心要求「本机断开 GitHub 也能完整走完改、查、批、收」中的工位衔接环节（卡点 2），并顺带归并卡 313 推到完成后的变更单原件与版本变更台账（`CHG-SCPT-2026-720`、`CHG-SCPT-2026-721`、`01_版本变更台账.md`）。

用户授权：2026-11-18 18:48:32-07:00（即 `2026-11-19T01:48:32Z`），用户在本机主对话明确回复：“授权做卡点2，走驾驶舱开始吧”（批准凭据 `user-confirmation:2026-11-19T01:48:32Z`）。

## 根因与全库同类排查（FIX-001）

- **根因**：[agent_worktree_service.py](../auto_pm/application/core/agent_worktree_service.py) 原写死 `MAIN_REF = "refs/remotes/origin/main"`，`_refusal` 仅凭 `station.unpushed`（未推远端提交数）拒绝收工位，且 `worktree open/close/sweep` 未读取本机 GitHub 三档配置（`.auto-pm/reports/local_merge/github_mode.json`），导致经 `pm_merge.py merge` 合入本机 `main` 但尚未推到 `origin/main` 的工位无法 `worktree close`、新开工位落后于本机 `main`、GitHub `关` 档下无法离线开/收/清工位。
- **全库同类排查**：
  1. `agent_worktree_service.py` 中共 6 处同源引用：`_open_locked`、`_make_room`、`_close_locked`、`sweep`、`_sweep_gone`/`_delete_local_branch`/`_inspect`/`_remove_station_checked`/`_refusal`/`_detached_hold`、`_require_main_ref` — **全部一并修复**；
  2. `scripts/cockpit_board/stations.py` 的 `close_block()` 仅看 `dirty or unpushed` 未放行已并进 `main` 的工位 — **同步修复**；
  3. 排查 `pr_open_service.py` 与 `control_root_sync.py`：前者仅用于“多机”PR 模式，后者专门对比本机与 `origin/main` 同步差，保留 `MAIN_REF = "refs/remotes/origin/main"` 常量不变，理由充分不改。

## 改成什么

1. `SW8/auto_pm/application/core/agent_worktree_service.py`：
   - 新增 `LOCAL_MAIN_REF = "refs/heads/main"`，保留 `MAIN_REF = "refs/remotes/origin/main"` 兼容外部导入；
   - 新增只读 `_github_off()` 读取 `.auto-pm/reports/local_merge/github_mode.json`：档位为 `关` 时，`open`/`close`/`sweep`/`_make_room` 自动免 `fetch`，完全不碰网络；
   - 新增 `_is_merged_into_main(commit)`：提交已并进本机 `refs/heads/main` 或 `refs/remotes/origin/main` 均判 `merged=True`；
   - `_refusal()` 改为 `if station.unpushed and not station.merged:`：未并进 `main` 且未推远端时依然硬拒（不丢任何未保存提交）；已并进本机 `main` 时允许 `close`/`sweep` 并删本地分支，回执写明“已并进本机 main，本地分支已删（待推到 GitHub 备份）”；
   - `_open_base_ref()`：在 `refs/heads/main` 与 `refs/remotes/origin/main` 之间自动选更新的一端作新工位起点；纯本机无 `origin/main` 时直接用 `refs/heads/main`；两者分叉（互不为祖先）时拒绝（Fail-Closed）；
   - `_require_main_ref()`、`sweep`、`_sweep_gone`、`_delete_local_branch`、`_detached_hold` 同步采用双基线判定。
2. `SW8/auto_pm/ui/cli/worktree.py`：`open` 命令帮助与输出提示同步本机合并与 `main` 起点说明。
3. `SW8/scripts/cockpit_board/stations.py`：`close_block()` 在 `merged=True` 且无未提交改动时放行看板「收工位」按钮，与后端口径一致。
4. 测试与变异锚点：更新 `agent_worktree_mutants.py`（2 处锚点），在 `test_agent_worktree_service.py` 和 `test_cockpit_board_worktrees.py` 新增本机合并后收工位/清理、本机 `main` 领先开工位、分叉拒开、GitHub `关` 档纯离线全闭环及看板按钮回归测试。

## 可改范围

| 路径 | 基线状态 | 用途 |
|---|---|---|
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/agent_worktree_service.py` | 存在 | 工位全链路对齐本机 `main` 与 GitHub 三档 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/ui/cli/worktree.py` | 存在 | `worktree open` 提示文案同步 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/cockpit_board/stations.py` | 存在 | 看板 `close_block` 与本机合并口径一致 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_agent_worktree_service.py` | 存在 | 新增 5 条本机合并/分叉/关档纯离线测试 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/agent_worktree_mutants.py` | 存在 | 同步 2 条变异锚点 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_cockpit_board_worktrees.py` | 存在 | 修正 fixture 的 `merged=False` 并新增本机已合并允许收工位断言 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/314_工位命令对齐本机合并与GitHub三档实施卡_PM.md` | 计划新增 | 本卡 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-720.md` | 存在 | 顺带归并卡 313 推到完成后的变更单原件 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-721.md` | 计划新增 | 本次变更单原件 |
| `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/02_变更记录/01_版本变更台账.md` | 存在 | 版本变更台账同步入库 |

## 验收

- `test_agent_worktree_service.py`、`test_agent_worktree_alias.py`、`test_agent_worktree_mutant_anchors.py`、`test_sweep_detached.py`、`test_cockpit_board_worktrees.py`、`test_cockpit_board_worktrees_flow.py`、`test_no_new_lenient_decoding.py`、`test_layer_import_direction.py` 全部退出 0；
- `ruff check` 与 `mypy --platform win32` 退出 0；
- `pm_merge.py merge antigravity-c31400` 门禁全绿并合入本机 `main`；
- 生效说明：本卡改动落入 `auto_pm/`，需后续发版切换才会在本机现役发布中激活。
