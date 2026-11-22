# 卡 CHG-SCPT-2026-733：驾驶舱总控屏 GUI 方案 A 重构实施卡（CHG-SCPT-2026-733）

> 卡片编号：`CARD-CHG-SCPT-2026-733-COCKPIT-GUI-REDESIGN V1.0`
> 变更单：`CHG-SCPT-2026-733`（当前状态：`approved` / 已批准，批准凭据：`user-confirmation:2026-11-21T19:03:13-07:00`）
> 隔离基线：`9703dfbc`（`main`）
> 工作分支：`antigravity/20261121-gui-redesign`（工位 `.auto-pm/worktrees/antigravity-d2481c`）
> 一期方案原型提交：`9f5a4f80`（已完成）
> 档次：大改动建变更单 + 实施卡（用户已于 2026-11-21T19:03:13-07:00 批准 `CHG-SCPT-2026-733`，按 `CHG-SCPT-2026-733` + `领卡占位: CHG-SCPT-2026-733` 提交）
> 安全回路：否
> 分离的后续治理单：`CHG-SCPT-2026-734`（`draft`，单列 `pm_merge.py` / `hook_replay.py` / `AGENTS.md` / `roles/` 最小改造，**不混入本分支**）

用户授权：2026-11-21 19:03:13-07:00，用户在本机主对话明确回复：“批准变更单CHG-SCPT-2026-733”（及 19:04:15-07:00 “批准”，批准凭据 `user-confirmation:2026-11-21T19:03:13-07:00`）。

## 背景与目标

1. 原驾驶舱总控屏（`scripts/cockpit_board/`）14 页分散、缺乏单机优先视角（GitHub 联动三档 `关/备份/多机`、版本锁与 `HEAD` 对齐、按项目总线挂载 AI 工位、`pm_handoff.py` 轻轨交接状态与 `pm_merge.py` 近期本机收口回执）。
2. 用户已确认一期设计方案 `02_规划/008_总控屏GUI重设计方案.md`、数据桥接映射 `02_规划/Html原型预览/cockpit_board_bridge_mapping.json` 及离线 HTML 原型 `02_规划/Html原型预览/cockpit_board_redesign.html`（提交 `9f5a4f80`）。
3. 本卡实施期（Stage 1–4）将上述方案完整落地到 PySide6 实际应用 `scripts/cockpit_board/`，保持全部原有安全与只读不变量，并补齐专项单测与结构契约测试对齐。

## 改成什么

1. **只读本地适配器（`scripts/cockpit_board/local_data.py`）**：
   - 纯 Python、`Path.read_text(..., errors="replace")` 只读读取 `.auto-pm/reports/local_merge/github_mode.json`（默认 `备份`，损坏标 `读不懂`）、`merge_log.jsonl`（倒序 + 一键生成 `git revert -m 1 <sha>` 命令）与各项目交接交换区（区分 PLC `11_监控/交接交换区` 与软件 `04_监控/交接交换区`，解析 `local-handoff-focus.v1`、`journal.jsonl` 与 7 天陈旧判定）。
   - 提供 4 级工位归属项目解析 `resolve_station_project()`（`claim_paths` -> `focus.json` -> 分支/卡号正则 -> 空串 `UNKNOWN`）。
2. **全局控制台与顶栏/侧栏收敛（`widgets/console.py`、`shell.py`、`flow/pages.json`、`policy.py`、`tool_policy.py`、`theme.py`、`app.py`）**：
   - 侧栏收敛为 `产线主控`（6 导航页）+ `排查与诊断`（4 导航页）共 10 个侧栏页 + 1 个详情页 `project`，在 `app.goto` 中保留 `attention` / `tasks` / `spine` 兼容路由别名。
   - 侧栏底部接入 4 盏实时遥测灯（`账本`、`版本锁`、`GitHub`、`AI 标记`），顶栏接入 `version_pill`、可点击切换 `prs` 的 `gh_mode_pill` 三档指示与 `深色`/`浅色` 主题切换。
   - 新增 `GlobalFailureBar` 与底部折叠 `GlobalConsoleDrawer`，统一承接各页 `receipt_added` 回执，支持复制命令行与一键关掉失败提示。
   - 补足 `theme.py` 浅色/深色 `fg3`（及浅色 `fg2`）在 `bg`/`card`/`card2`/`side` 四种底色上的 WCAG AA（>= 4.5）对比度与新增控件 QSS 令牌样式。
3. **业务页与只读页升级**：
   - `worktrees.py` + `stations.py`：按所属项目将 AI 工位挂载到 `project_bay` + `bus_rail` + `station_pod`，每个工位展示 3 颗微联锁灯（工作树/推送/进 main），下方展示 `pm_merge` 近期记录与撤销命令复制键；未挂载目录单独分组。
   - `decisions.py` + `app.py`：同页整合 D-342 首页同源计入统计与可折叠 `att_detail` 只读明细。
   - `projects.py` / `project_page.py` / `tools.py` / `release.py` / `prs.py` / `flow.py` / `spine.py` / `commands.py` / `home.py` / `station.py`：`全部项目` 增设性质/健康 `ClickBox` 筛选与表格/卡片切换；`项目详情` 增设 8 段阶段周期（纯文本 `c.label`）、`交接事件流` 页签与实时 `missions/orient` 读取结果；`工程工具箱` 增设 `本机交接` 页签；`发版中心` 增设 3 列版本锁对比卡；`流程与状态机` 嵌入 `十步脊柱图` 子标签并适配深色画布令牌；`命令与契约` 支持分类过滤与关键字搜索。
4. **冒烟稳定性修复（`smoke.py`）**：
   - `smoke._busy(window)` 补充检查 `release_actions._jobs`、`release_actions._checking`、`worktree_actions._jobs` 与 `tools._jobs`，防止后台校验线程未退出时提前销毁窗口导致异常退出。

## 可改范围

*(均位于 `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/` 下)*

| 路径 | 状态 | 用途 |
|---|---|---|
| `02_规划/008_总控屏GUI重设计方案.md` | 一期已提交 (`9f5a4f80`) | 总控屏方案 A 重设计规格书 |
| `02_规划/Html原型预览/cockpit_board_bridge_mapping.json` | 一期已提交 (`9f5a4f80`) | HTML 原型与后端数据桥接映射表 |
| `02_规划/Html原型预览/cockpit_board_redesign.html` | 一期已提交 (`9f5a4f80`) | 离线可交互 HTML 原型 |
| `02_规划/CHG-SCPT-2026-733_总控屏GUI重设计实施卡_PM.md` | 本卡新增（工位未提交） | 本实施卡 |
| `scripts/cockpit_board/local_data.py` | 新增（工位未提交） | GitHub 三档、merge 日志、交接区与 4 级项目解析只读适配器 |
| `scripts/cockpit_board/widgets/console.py` | 新增（工位未提交） | 全局常驻失败条与底部可折叠回执终端 |
| `scripts/cockpit_board/app.py` | 修改（工位未提交） | 顶栏/主题切换/遥测同步/全局控制台/兼容路由 |
| `scripts/cockpit_board/shell.py` | 修改（工位未提交） | 2 组 10 页侧栏注册表与 4-LED 系统联锁遥测面板 |
| `scripts/cockpit_board/flow/pages.json` | 修改（工位未提交） | 页面分组名与只读契约配置同步 |
| `scripts/cockpit_board/policy.py` | 修改（工位未提交） | 按钮白名单与 `SIDEBAR_GROUPS` 同步 |
| `scripts/cockpit_board/tool_policy.py` | 修改（工位未提交） | 工具箱 `本机交接` 与 `NAV_BUTTONS` 同步 |
| `scripts/cockpit_board/theme.py` | 修改（工位未提交） | 明暗主题 WCAG AA 对比度修正与新增部件 QSS 规则 |
| `scripts/cockpit_board/stations.py` | 修改（工位未提交） | 联锁状态布尔保护与 `resolve_station_project` 接线 |
| `scripts/cockpit_board/viewmodel.py` | 修改（工位未提交） | 8 段周期 `PHASES` 与 `handoff` 视图模型接线 |
| `scripts/cockpit_board/smoke.py` | 修改（工位未提交） | `_busy` 纳入控制器后台任务等待 |
| `scripts/cockpit_board/widgets/home.py` | 修改（工位未提交） | 项目产线舱 `project_bay` 与焦点/陈旧交接提示 |
| `scripts/cockpit_board/widgets/worktrees.py` | 修改（工位未提交） | 项目总线挂载视图、3 颗微联锁灯、`pm_merge` 历史与信号 |
| `scripts/cockpit_board/widgets/decisions.py` | 修改（工位未提交） | D-342 同源计入与可折叠待办明细 |
| `scripts/cockpit_board/widgets/projects.py` | 修改（工位未提交） | 性质/健康快筛与表格/卡片切换 |
| `scripts/cockpit_board/widgets/project_page.py` | 修改（工位未提交） | 8 段周期条、`交接事件流` 页签与实时任务区 |
| `scripts/cockpit_board/widgets/release.py` | 修改（工位未提交） | 3 列版本锁对比卡与 `receipt_added` 信号 |
| `scripts/cockpit_board/widgets/tools.py` | 修改（工位未提交） | `本机交接` 页签、文案清理与 `receipt_added` 信号 |
| `scripts/cockpit_board/widgets/flow.py` | 修改（工位未提交） | 嵌入 `十步脊柱图` 子视图与主题令牌重绘 |
| `scripts/cockpit_board/widgets/spine.py` | 修改（工位未提交） | 兼容别名中文页名映射 |
| `scripts/cockpit_board/widgets/commands.py` | 修改（工位未提交） | 分类筛选与关键字过滤 |
| `scripts/cockpit_board/widgets/prs.py` | 修改（工位未提交） | GitHub 联动档位卡片展示与去重循环清理 |
| `scripts/cockpit_board/widgets/station.py` | 修改（工位未提交） | 统一 `receipt_added` 信号与过时说明清理 |
| `tests/core/test_cockpit_board_pages.py` | 修改（工位未提交） | 对齐收敛后侧栏键并保留无按钮/只读全量检查 |
| `tests/core/test_cockpit_board_shell.py` | 修改（工位未提交） | 对齐新侧栏分组、`项目详情` 范围字样 |
| `tests/core/test_cockpit_board_smoke.py` | 修改（工位未提交） | 对齐侧栏核心功能页与 `worktrees` 页头卡死回归 |
| `tests/core/test_cockpit_board_tools.py` | 修改（工位未提交） | 对齐 6 个工程工具页签顺序（含 `handoff`） |
| `tests/core/test_pm_dashboard_gui.py` | 修改（工位未提交） | 放行只读局部关键字过滤框 `commands_search` |
| `tests/core/test_cockpit_board_redesign.py` | 新增（工位未提交） | 覆盖 `local_data`、主题、版本锁、GitHub 三档、遥测、控制台、项目总线、筛选与 `smoke._busy` 的 14 条单测/控件测试 |

明确排除：`scripts/pm_merge.py`、`reviews/tools/hook_replay.py`、`AGENTS.md`、`roles/` 及 `00_Infrastructure/auto_pm/*` 发布指针均**未修改**（`pm_merge.py` / `hook_replay.py` / `AGENTS.md` / `roles/` 已单列为 `CHG-SCPT-2026-734`）。

## 实施与最后编辑后验证记录（2026-11-21）

均在工位 `.auto-pm/worktrees/antigravity-d2481c` 最后一次代码与测试编辑完成后顺序实测：

- `ruff check scripts/cockpit_board tests/core/test_cockpit_board*.py tests/core/test_pm_dashboard_gui.py` -> `All checks passed!`（退出码 `0`）
- `mypy scripts/cockpit_board` -> `Success: no issues found in 39 source files`（退出码 `0`）
- 全部 22 份核心/看板/重设计单元与控件测试（`-o addopts=""` 分 3 批无并发全量跑完）：
  - 批 1（13 份：`test_cockpit_board.py`、`contracts`、`flow`、`pages`、`tools`、`widgets`、`worktrees`、`wrap`、`decisions`、`decisions_widgets`、`net_probe`、`no_window`、`pm_dashboard_gui`）-> **`671 passed`** in 3281.10s（退出码 `0`）
  - 批 2（3 份：`test_cockpit_board_smoke.py`、`test_cockpit_board_redesign.py`、`test_pm_dashboard.py`）-> **`36 passed`** in 12.51s（退出码 `0`）
  - 批 3（6 份：`test_cockpit_board_pythonw.py`、`readers`、`release_page`、`reread_after_action`、`runner`、`shell`）-> **`111 passed`** in 5.15s（退出码 `0`）
  - 以上 22 份合计：**`818 passed, 0 failed`**
- 流程端到端测试（`tests/core/test_cockpit_board_incident_flow.py`、`tests/core/test_cockpit_board_full_flow.py`，`-o addopts=""`）-> **`4 passed, 4 xfailed`** in 1176.04s（退出码 `0`，4 条既定严格 `xfail` 保持原样）
- 离屏全页点检（`QT_QPA_PLATFORM=offscreen`、`AUTO_PM_AGENT=antigravity:ide`，`python -B scripts/cockpit_board/smoke.py --root <控制根> --out <scratch> --wait 120 --no-net --no-github`）-> **`合计 11/11 页过`**（退出码 `0`）
- 文档规范检查（控制根 `python -B main.py doc check`）-> `DOC-001 PASS`（43 组 CLI 命令）+ `DOC-004 PASS`（`1.3.3-9703dfb` 版本锁一致），退出码 `0`

## 验收与提交约定

1. 用户审核并批准变更单 `CHG-SCPT-2026-733`（看板点击“批准变更单”或在本机主对话明确授权批准 `CHG-SCPT-2026-733`）。
2. 提交工位 `antigravity-d2481c` 内全部变更到分支 `antigravity/20261121-gui-redesign`，提交说明包含 `CHG-SCPT-2026-733` 及独立一行 `领卡占位: CHG-SCPT-2026-733`。
3. 所有代码/测试护栏保持绿灯：`ruff`、`mypy`、22 份核心/重设计测试（`818 passed`）、`smoke.py` `11/11`、独立审计放行、`pm_merge.py merge antigravity-d2481c` 合入本机 `main`。
