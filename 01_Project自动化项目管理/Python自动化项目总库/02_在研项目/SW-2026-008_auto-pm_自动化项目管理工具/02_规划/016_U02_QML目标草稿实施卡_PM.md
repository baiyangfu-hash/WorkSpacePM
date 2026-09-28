# U02｜QML 目标输入与真实 PlanningDraft 实施卡

> 卡编号：`CARD-SW008-M2-U02`
> WBS 原子任务：`U02`；依赖：`U01`、`P11`
> 版本：V0.2（2026-09-28）；状态：`USER_APPROVED / GOVERNED_AUTHORIZATION_PENDING`
> 控制根：`C:\Users\fubai\Documents\My_Workspace`
> 不可变源码基线：`b7bb935773242b2cf2e2dfcb411619d24d314344`

## 1. 本卡的决定与边界

用户故事：我在驾驶舱选择项目、输入想达成的目标和可验证的验收条件；提交后看到真实保存的、**尚未获批**的草稿，不需要填写任何 CHG、Decision、Mission、Work、Run 或 request ID。

U02 只打通 `BossCockpitView.qml → boss_main.qml → PmCockpitBridge → PmFacadeService.create_planning_draft → ContinuityStore`。草稿必须是 `PRE_AUTH`，提交行为不得自动调用 `create_planning_draft_change`、`create_planning_scope_card` 或创建 Mission/Work/Run。既有的开工和最终验收确认仍使用原通道，不得与草稿提交混用。

`PmIntent` 目前只含项目、目标、验收条件、内部 request ID；`PlanningDraft` **不含 scope_paths**。因此 UI 在这一阶段只能如实显示“范围待 PM 规划”，不能伪造确定的路径/执行范围。未来有真实 `PlanningScopeCard` 后才显示其明确范围。此解释须在开工前同步修订 WBS U02 的“显示项目/范围/验收”验收口径；如必须在 U02 当场显示已确定范围，应另行规划 P11 范围卡接入，本卡不能假装满足。

## 2. 已核实的准入事实

- WBS V3.0.6：M0/M1 已验收，M2 进行中，U01 与 `M2-GOV-IC01` 已验收；U02 为下一项，尚无执行授权。
- 干净候选 `.auto-pm/worktrees/m2-implementation-card` 的 HEAD 为上述 `b7bb9357`，`git status --short` 为空；P11 提交已在祖先链。U01 的原独立提交不在祖先链，但 U01 两个交付文件的 Git blob 与其已验收提交逐字节一致。开工时仍须复核，不以本卡代替现场检查。
- WBS 原写三个产品路径；现有 QML 结构在 `boss_main.qml` 接线，且 `tests/qml/test_boss_cockpit_view.py` 是视图入口测试。若遗漏二者，不能证明端到端输入链。需要在开工前把 U02 的产品路径精确修订为下列五条，不得默默增加第六条。
- 根入口 `pm resume SW-2026-008` 目前仍提示历史 `MULTIPLE_ACTIVE_WORKS`；只读路径对照尚未发现这些 Work 占用下列五个 U02 路径。启动新治理链前需重新做**路径级**冲突预检；不为此重开 C09/P2 历史清障。

## 3. 精确产品路径与治理证据路径

产品 owned paths（相对 SW008 项目根）：

1. `auto_pm/ui/qml/bridges/pm_cockpit_bridge.py`
2. `auto_pm/ui/qml/views/BossCockpitView.qml`
3. `auto_pm/ui/qml/boss_main.qml`
4. `tests/qml/test_pm_cockpit_bridge.py`
5. `tests/qml/test_boss_cockpit_view.py`

提交治理证据路径（**不是**产品测试目标）：

1. `04_监控/01_变更管理/01_变更单/CHG-SCPT/<本次由服务分配的 CHG>.md`
2. `04_监控/01_变更管理/02_变更记录/01_版本变更台账.md`

最终 Decision/Work/Run/Checkpoint 与 Git Hook 所需提交范围，须按现有实施卡合同分别声明五条产品路径和两条治理证据路径，再校验其并集。CHG 编号不能预造；当前文档本身不构成执行授权。需要更改 Facade、Store、QML 组件、规范或其他第六产品路径时，停在预检，更新卡片与授权后再开工；不得边做边扩。

## 4. 实施与验证合同

1. 用不可变 `b7bb9357` 派生专用干净隔离候选；复核 Git HEAD、全部脏/暂存/未跟踪路径、root launcher 的 configured/effective runtime 与加载路径。源码/runtime 身份不一致则 fail-closed，绝不手改 release 指针。
2. 经用户批准后按现行高层服务创建单目标 CHG、Decision、Mission、Work、Run、lease，声明上述路径；不用直接 SQL 或手工伪造 Checkpoint。实现职责限制为五条产品路径。
3. QML 输入只收项目、目标、显式验收条件。Bridge 在内部生成并持有一次提交的 request ID，重试同一提交须复用它；输入变更才开始新草稿。服务验证失败须向用户显示错误，不得显示“已创建”。成功展示项目、目标、验收条件、`PRE_AUTH` 与“范围待规划”，内部 ID 不作用户输入项。
4. 验证正常提交在隔离控制根创建可重新读取的 `PlanningDraft`；重复提交幂等；同 request ID 改输入应被拒绝；失败不得产生 Mission/Work/Run/授权状态。还需验证 QML 信号确实抵达 Bridge、提交按钮的重复触发、空目标/空验收拒绝、原有快照/证据/确认功能不回归。
5. 在候选 SW008 项目根，以工作区 `.venv\Scripts\python.exe -B` 执行：
   - `-m pytest -o addopts= --no-cov -p no:cacheprovider tests/qml/test_pm_cockpit_bridge.py tests/qml/test_boss_cockpit_view.py`（无头 Qt 环境配置须在预检中核对）；
   - `-m ruff check --no-cache auto_pm/ui/qml/bridges/pm_cockpit_bridge.py tests/qml/test_pm_cockpit_bridge.py tests/qml/test_boss_cockpit_view.py`；
   - `-m mypy --strict --no-incremental auto_pm/ui/qml/bridges/pm_cockpit_bridge.py tests/qml/test_pm_cockpit_bridge.py tests/qml/test_boss_cockpit_view.py`，不得使用 `--follow-imports=skip` 隔离真实依赖；
   - `git diff --check`，以及 QML 入口加载/信号回归。所有质量门均须完整返回 Exit 0；任何基线债先做差异判定，不得改写失败为 PASS。
6. 真实执行回执绑定当前 HEAD、五条产品路径和两条治理证据的当前字节。通过正常 Git Hook 形成一个本地隔离提交；再经高层服务验收、释放租约、关闭 CHG，并运行 `main.py ledger reconcile SW-2026-008`。提交、治理终态和 WBS 当前投影逐项核验；合并、推送、部署、release 切换各自另行授权。

## 5. 停止与交付

- 开工前必须先批准本卡及 WBS U02 的五路径/“范围待规划”口径修订；并核对 P11 前置验收、Git/runtime、路径占用和 quota。
- 周额度剩余 `<=20%` 时停止新的写入、测试批次或治理流转；正在运行的子进程先安全收集和回收，保留真实状态。
- 候选漂移、第六产品路径、权限或 lease 不匹配、进程回收不明、门禁未完整返回、无法证明 UI→Bridge→持久草稿，均停止并保留现场；不得补丁式另开平行 Run。至多一次有界执行和一次同范围内纠正，纠正前须有稳定根因和完整回收证据。
- 验收交付为：实际 QML 操作录屏/可复核交互回执或等价 QML 测试、草稿持久化与幂等证据、无 Mission/Work/Run 旁效应、完整门禁结果、当前字节 Checkpoint、正常本地提交、Run/Work/Mission/CHG 终态及台账零差异。缺任一项不得把 U02 或 M2 标为完成。

本卡目前只完成规划，不修改产品代码、WBS、canonical 数据库或 release；不使用已退役的 `pm-workflow`。
