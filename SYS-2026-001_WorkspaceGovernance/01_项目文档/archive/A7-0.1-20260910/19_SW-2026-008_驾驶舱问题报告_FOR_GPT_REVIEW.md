# SW-2026-008 auto-pm 驾驶舱 问题报告（供 GPT 独立审查）

> 编制：ZCode，2026-09-05
> 审查对象：auto-pm 工业级 AI 研发工作台（PySide6+QML 桌面驾驶舱 + CLI）及其治理仓库
> 审查请求人：fubai（架构师/PM/最终决策人）
> 配套阅读：`18_SW-2026-008_切流回退与问题移交_GEMINI.md`（前期移交件）、根目录 `AGENTS.md`（协作规则）

## 1. 项目与架构一句话

`auto-pm` 是"一人全栈超级个体"工作台的驾驶舱工具（CLI + QML GUI），当前处于**架构迁移中期**：从"工作区级基础设施平铺源码直跑"（现状，功能完备）迁往"研发母体（SW-2026-008 candidate）为唯一真源 + 稳定部署容器双槽 release 切流"（目标，已跑通机制但暂缓切流）。

## 2. 迁移机制现状（全部已落地并验证）

| 组件 | 位置 | 状态 |
|---|---|---|
| 研发母体（新架构真源） | detached worktree：`C:/Users/fubai/.codex/visualizations/2026/09/05/01a06f4b-eb60-7e83-8ee7-f3d84cfec583/NG-WP-02/candidate`，HEAD `c0d7d0e` | 1981→2020 项测试全绿；含 NG-WP-03~09 安全加固 + CHG-020/021 首两批功能回收 |
| 稳定部署容器 | `00_Infrastructure/auto_pm/` | 平铺源码 200 文件（当前运行真源）+ 双槽骨架（launcher/bootstrap/releases/双指针/manifest/lock）+ tests |
| 双槽指针 | `active_release.json` / `previous_release.json` | 均 `null`（已回退切流，未部署） |
| 首个 release | `releases/1.2.3-d41eb38/`（450 文件 + manifest） | 保留作证据；功能面存在差距（见 P3），不用于切流 |
| 生产入口 | 根 `main.py`（平铺源码运行态） | 已回退并修正历史入口 bug（`run_qml_app`→`run_qml_gui`） |
| Git 钩子 | `.git/hooks/pre-commit`+`commit-msg`（v3） | 台账一致性 + CHG 绑定强制；经 `git-common-dir` 解析主工作区（worktree 兼容） |
| venv | 无 auto_pm 安装（NG-WP-13 已卸载 editable） | 入口/钩子均不再依赖 |

## 3. 已解决问题（CHG-018/019/021，全部 closed）

### P1 GUI 闪退（用户报告）— 已缓解
- 直接诱因：启动窗口期 SQLite 运行库锁竞态（残留实例持锁）+ `start` 控制台吞错误。
- 修复：`startup_guard.py`（内核级单实例锁 msvcrt/flock + SQLite 锁探测 + 崩溃日志 `.auto-pm/logs/startup_crash.log`），实测拦截二次启动（exit 6）；bat 重写为 ASCII 安全启动器。
- **审查点**：闪退的完整机理仍有未闭环处（用户唯一一次闪退发生时并无可见的锁持有者），建议 GPT 审查 `startup_guard.py` 的防护面是否充分（如 WAL 残留、杀进程后的 shm 状态）。

### P2 首同步 FK 失败 — 已防御
- release 代码首启同步曾报 `FOREIGN KEY constraint failed`（瞬态自愈，运行库 integrity ok / fk_check 0 违规）。
- 修复（Gemini）：sync/repository 四层防御——失败时自动 `PRAGMA foreign_key_check` 留证、过期项目拓扑逆序删除（先子后父）、project_id 三级回退（frontmatter→正文→扫描上下文）、存根补偿（`is_stub` 标记）+ 单条故障隔离。
- **审查点**：存根补偿会向 projects 表写入"(自动补偿存根)"行——评估其对 GUI 项目列表与台账语义的影响是否可接受。

### P3 功能差距 — 首两批完成，剩余已立项
- 量化：candidate 较稳定平铺源码缺 **14 个模块**、**156 个文件内容漂移**（例：ai_handoff_service 54KB→6KB）。
- 已完成（CHG-020）：14 模块 verbatim 回收 + CLI 注册补全 + ai_handoff_service 恢复至稳定版全量（确认瘦身版无自有符号，纯增量）+ 5 个测试迁移。
- 已完成（CHG-021）：符号级分诊 127 漂移文件 → **116 个 verbatim 回收**（candidate 无自有符号，stable 为超集）/ 3 个保留 candidate 加固 / 6 个需合并；其中 `ui/cli/project.py` 已外科合并（恢复只读 preflight/fact 命令，保留 NG-WP-09 加固，排除硬删除 `cmd_delete`）。
- **剩余**：① 5 个深度合并件（`project_archive_service` s17/c26、`workflow_orchestrator` s1/c5、`dashboard_service` s1/c14、`project_service` s1/c1、`project_scanner` s1/c3）——需逐符号评审 stable 功能增量 vs candidate 安全加固；② 内容级对账的尾巴；③ 4 个上下文依赖测试已适配 5 个（saga/binding/decision/doctor/handoff），substance 归并后复验。

### P4 测试基础设施（新发现，已修复 CHG-019）
- **Qt 单例顺序脆弱性**：`tests/ui/test_qml_syntax.py` 模块级创建裸 `QCoreApplication`；pytest 目录执行顺序取决于 NTFS 枚举序（非稳定排序），文件增删即改变 ui/qml 先后 → `tests/qml` 175 用例整目录假失败（`QApplication.instance()` 返回异型单例）。
- 修复：qml_engine 复用根 conftest session 级 `qapp`；modbus session fixture 同步 QApplication 化。连续两次全量 1968/2020 passed 确认顺序稳定。
- **审查点**：根 conftest 的 `qapp` 断言策略（fail-fast vs 容忍异型单例）与 NTFS 枚举序非确定性——建议评估 `pytest-randomly` 显式化或目录序稳定性方案。

### P5 既有问题（与本次变更无关，如实登记）
- 平铺全量 4 个既有失败：PM_SESSION 文件位置断言 ×2（平铺容器无该文件）、`MAX_FILE_LINES` 阈值断言、dashboard 断言——均经 HEAD 对照实验证实早于全部近期改动。
- candidate 全量历史上存在 175 个 qml setup 错误——本次 CHG-019 根因修复后归零（2020 passed）。

## 4. 当前提交与证据索引

| 提交 | 内容 |
|---|---|
| `efee250` | NG-WP-10 Gate1 整改收口（1900 tests 绿） |
| `6b02646` | NG-WP-11/12：candidate 冻结 + wheel + 双槽骨架 + 钩子修复 |
| `d41eb38`/`d461015` | NG-WP-13：入口双槽化 + editable 卸载 + 钩子 v3 |
| `d31f892` | NG-WP-14：release 部署非活动槽 + Gate 2 全绿 |
| `dc0b2fb` | NG-WP-15：Tag + 原子切流（后回退） |
| `8ca8960` | 回退切流，恢复平铺运行（User 决策） |
| `09ebdc0` | CHG-018：startup_guard + FK 防御落地 |
| `4fb2a11`/`97fecfd` | CHG-019：Qt 单例污染根因修复 |
| `3871d49`（candidate）/`c23b0e1` | CHG-020：P3 首批（14 模块 + ai_handoff） |
| `c0d7d0e`（candidate）/`d625ee7` | CHG-021：P3 漂移对账批次（116 文件） |
| 测试基线 | candidate 2020 passed / 18 skipped；平铺 1901 passed / 4 既有失败 |
| 门禁 | ruff 0 违规；mypy strict 203 文件 0 问题；台账一致性 pre-commit + CHG 绑定 commit-msg 强制 |

关键报告（`.auto-pm/reports/`）：`NG-WP-10_Gate1_remedy_report`、`NG-WP-13_isolation_evidence`、`NG-WP-14_gate2_report`、`NG-WP-15_switchover_report`、`CHG-021_drift_triage_2026-09-05.json`。

## 5. 请 GPT 重点审查的问题清单

1. **架构决策**：平铺运行（现状）与双槽 release（目标）之间的过渡策略是否合理？回退切流的时机与 P3 完成后再切流的路径是否有更优解？
2. **startup_guard 防护面**：单实例锁 + SQLite 锁探测 + 崩溃日志的组合是否足以覆盖全部闪退向量？崩溃日志落盘设计（`.auto-pm/logs/`）是否需要轮转？
3. **存根补偿语义**：sync 时自动创建 `is_stub` 项目行——数据完整性 vs 幻影项目污染的权衡是否正确？
4. **回收策略**：verbatim verbatim 的批量回收（116 文件）依赖测试网兜底——是否存在测试未覆盖的静默行为漂移？6 个深度合并件的合并策略建议。
5. **双槽机制**：`bootstrap.py`/`DeploymentContainer` 的指针原子性、containment、锁语义是否有遗漏的攻击面（符号链接、竞态、崩溃恢复）？
6. **治理流程**：CHG-015~021 的粒度与门禁强度是否恰当？台账/pre-commit/commit-msg 三层强制是否有绕过面？

## 6. 约束提醒（审查结论落地时必须遵守）

- 全部变更须经变更流程（`auto_pm change create` → User 批准 → 精确 pathspec 实施 → 机器门禁 → 收口）。
- 禁止：硬删除、`.trae`/Obsidian 覆写、真实 `.auto-pm` 运行库直接操作、`git add .`/reset/stash 冻结现场。
- 双槽指针只能经 `DeploymentContainer` 原子操作；重新切流前必须完成 P3 剩余批次并重建 release（NG-WP-11 流程）+ Gate 2 + User 批准。
