# U02｜QML 目标输入与真实 PlanningDraft 实施卡

> 卡编号：`CARD-SW008-M2-U02`
> WBS 原子任务：`U02`；依赖：`U01`、`P11`
> 版本：V0.4（2026-09-28）；状态：`COMPLETED / ACCEPTED`
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
- U02 已在候选 `.auto-pm/worktrees/m2-u02-planning-draft` 完成五产品路径实现；定向 QML/Bridge/Cockpit 11 项、P11 Facade 27 项、Ruff、strict Mypy 与 `git diff --check` 均 Exit 0。Checkpoint `CP-SW008-M2-U02-001` 已绑定 `b7bb9357` 与七条授权路径，但不能替代最终提交后的当前字节验收。
- 首次正常提交被 Git Hook 正确阻断。根因不是产品代码、候选基线或 Hook 回归，而是执行时把主工作区现行完整台账（294 个 CHG 编号）直接复制到历史候选；该候选实际只有基线 173 份 CHG 加本次 `CHG-SCPT-2026-339`，因此出现 120 条孤儿和 `CHG-331/336/338` 三条状态差异。门禁实现与 `b7bb9357` 中的实现 Git blob 一致。
- 当前 Run `RUN-SW008-M2-U02-001` 与 Work `WORK-SW008-M2-U02-001` 均已如实置为 `BLOCKED`；CHG-339 保持 `implementing`。候选七条暂存路径完整保留，未提交、未合并、未部署。

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
6. 治理证据采用**候选分支本地快照**，不得把主工作区未来时点的完整台账复制到历史候选。候选台账必须由候选基线台账增量生成：保留 `b7bb9357` 的 173 条分支本地记录，仅增加本次 `CHG-SCPT-2026-339` 的一条 `implementing` 记录；预期候选 CHG 与台账均为 174 个编号，且候选对账严格为 0 缺失、0 孤儿、0 状态差异。主工作区 canonical 台账保持现行完整内容并单独维持 0/0/0，不得降级或覆盖。
7. 真实执行回执绑定当前 HEAD、五条产品路径和两条治理证据的当前字节。通过正常 Git Hook 形成一个本地隔离提交；再经高层服务验收、释放租约、关闭 CHG，并运行 `main.py ledger reconcile SW-2026-008`。提交、治理终态和 WBS 当前投影逐项核验；合并、推送、部署、release 切换各自另行授权。

## 5. 有界纠正路径

本节只纠正候选治理证据的时间点混用，不重新实现产品、不更换基线，也不扩大七条授权路径。

1. 保留候选 HEAD `b7bb9357`、五条产品修改、CHG-339 及全部失败现场；不新建工作树、CHG、Decision、Mission、Work 或平行 Run。
2. 在修改前只读核对：候选基线台账含 173 个唯一 CHG 编号，候选基线递归 CHG 文件集合也为 173，二者集合相等；主工作区现行台账与 canonical 项目对账仍为 0/0/0。
3. 仅在已授权的候选台账路径中恢复 `b7bb9357` 的分支本地台账内容，再通过受控台账服务或等价的可审计单行增量加入 `CHG-SCPT-2026-339`。禁止复制主工作区完整台账，禁止删除主工作区记录，禁止执行会处理其他编号的全量修复。
4. 纠正后先运行候选上下文对账；只有结果为 0/0/0，且集合证明为“基线 173 + CHG-339 = 174”时，才允许继续。任何额外增删、状态差异或第八条脏路径立即停止。
5. 台账字节改变后，`CP-SW008-M2-U02-001` 仅保留为首次尝试历史证据，**不得用于最终验收**。在租约、Decision 和 Authority 仍有效且无进程不确定性时，经高层服务将现有 Run 从 `BLOCKED` 恢复为 `RUNNING`；重新核验五产品文件哈希未变，复跑实施卡规定门禁并创建同一 Run 下的新序列 Checkpoint。
6. 新 Checkpoint 必须绑定纠正后的七条路径和完整门禁结果。随后使用正常 Hook 提交；Hook 非零时如实保留 `BLOCKED`，不得使用 `--no-verify`、不得启动第二条补偿链。
7. 正常提交成功后，才按 Run → Work → Mission → CHG 的合法顺序验收，并分别验证候选分支对账与主工作区 canonical 对账均为 0/0/0。

## 6. 防复发治理任务

U02 闭环后，将以下内容登记为独立 M2 治理原子任务，不夹带进本次七路径产品提交：

1. Worktree 创建时固化源码基线、CHG 集合哈希、台账哈希和 `governance_snapshot_mode=BRANCH_LOCAL`。
2. 提供候选台账增量生成入口，禁止 Agent 以文件复制方式同步 canonical 完整台账。
3. 将台账 0/0/0、CHG 集合哈希和状态一致性前移到 Checkpoint 创建前；预检失败不得生成可用于验收的 Checkpoint。
4. 实施卡机器合同增加 `governance_baseline_commit`、`ledger_update_mode=INCREMENTAL`、`canonical_ledger_copy_forbidden=true`、预期集合增量和停止条件。
5. 为“历史候选 + 未来 canonical 台账”编写回归测试，证明系统在复制、Checkpoint 和提交三个入口均 fail-closed。

## 7. 停止与交付

- 开工前必须先批准本卡及 WBS U02 的五路径/“范围待规划”口径修订；并核对 P11 前置验收、Git/runtime、路径占用和 quota。
- 周额度剩余 `<=20%` 时停止新的写入、测试批次或治理流转；正在运行的子进程先安全收集和回收，保留真实状态。
- 候选漂移、第六产品路径、权限或 lease 不匹配、进程回收不明、门禁未完整返回、无法证明 UI→Bridge→持久草稿，均停止并保留现场；不得补丁式另开平行 Run。至多一次有界执行和一次同范围内纠正，纠正前须有稳定根因和完整回收证据。
- 候选台账不得等同于主工作区现行完整台账；发现 CHG 文件集合与台账编号集合不相等、基线状态被未来状态覆盖，立即停止。不得用删除孤儿记录或补齐 120 份无关 CHG 的方式让门禁变绿。
- 验收交付为：实际 QML 操作录屏/可复核交互回执或等价 QML 测试、草稿持久化与幂等证据、无 Mission/Work/Run 旁效应、完整门禁结果、当前字节 Checkpoint、正常本地提交、Run/Work/Mission/CHG 终态及台账零差异。缺任一项不得把 U02 或 M2 标为完成。

本卡已按唯一有界纠正路径闭环：候选台账从错误的 canonical 294 条完整快照纠正为分支本地 173 条基线加 CHG-339，候选达到 174/174、0/0/0；完整复测通过，`CP-SW008-M2-U02-002` 与正常 Hook 提交 `74493c37` 成立，Run SUCCEEDED、Work/Mission CLOSED、CHG-339 completed。未合并、推送、部署或切换 release，也未使用已退役的 `pm-workflow`。
