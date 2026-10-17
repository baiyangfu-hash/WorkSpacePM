# U06｜GUI 验收与待同步状态实施卡

> 卡片编号：`CARD-SW008-M2-U06`
> 对应 WBS：`U06`（WBS V3.0.18 §4.7）
> 版本：`V1.0`（2026-09-30，一次定稿；执行期间不得修订，见 §9）
> 状态：`PLANNED / NOT_AUTHORIZED`（定稿，待授权；授权方式见 §7）
> 依赖：U05 已验收（提交 `ace7a959`，CHG-SCPT-2026-362 completed）；收尾服务 C05～C08 已验收
> 隔离基线：`ace7a9593d6841c2dc1a434d466b39990969511d`
> 治理任务真源：WBS 提交 `572932a7d7fe23cf799c6f8800d77263aec3c3ee`；WBS SHA-256 `33EE746A6D9495B7B39D09921605D3745A405AE26D1EBC51450C60213ACD5FCD`
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 推荐执行模型：`Claude Sonnet 4.6 (Thinking)` 或能力不低于它的模型；实际执行者 `Claude Sonnet 5.5`
> 禁用能力：`pm-workflow`

> V1.0 定稿说明：本卡在编写前已对基线做完只读勘测（§1），并把执行中最可能引发返工的点一次定死：产品路径、DTO 字段、状态判定、幂等键、线程模型、必测场景、对 U05 既有断言的**唯一允许的两处改动**、基线数字与停止条件全部写在本卡内。执行者只做填空与验证，不得现场修订本卡、扩大路径或放宽门禁；遇到本卡未覆盖的情况按 §9 停止并报告。

## 1. 背景与已核实事实（2026-09-30，基线 `ace7a959`，均为命令或源码核验）

1. WBS U06 原文：单一交付“GUI 验收与待同步状态”；验收“验收→投影失败→重试→完成可观测；缺必要证据不能点成‘已完成’”。WBS 只列了 3 个路径（Bridge、`BossCockpitView.qml`、视图测试）。
2. 收尾能力已存在但驾驶舱从未调用：`PmClosureService`（`auto_pm/application/core/pm_closure_service.py`）已提供 `prepare_closure`（Mission 须为 `ACCEPTED`、根 Work 须为 `IN_PROGRESS`、最新 Run 须为 `VERIFYING` 且有绑定的 Checkpoint，否则抛 `PmClosureError`）与 `complete_closure`（先同步变更单实质与台账；同步失败返回 `PENDING_SYNC` 且**不改动** Run/Work/Mission；成功才原子地把 Run、Work、Mission 推到终态）。全仓库没有任何其它调用方。`ContinuityStore` 的收尾表按 `mission_id` 唯一，`prepare_closure` 与 `complete_closure` 都按幂等键精确重放。
3. 现状缺口：用户点“确认最终验收”后，Facade 只把 Mission 记为 `ACCEPTED`（卡片文案承诺“确认后驾驶舱才会执行关闭和台账闭环”），但没有任何代码去执行收尾；驾驶舱快照把 `ACCEPTED` 显示为“验收完成”，看起来像已完成，实际变更单与台账并未同步。这正是 U06 要修的“假完成”。
4. 现状 Bridge：`confirmAcceptance` 同步调用服务并返回确认卡；没有后台收尾、没有重试入口、没有“待同步”信号。现状 `CockpitUserAction` 有 `NONE / CONFIRM_START / CONFIRM_ACCEPTANCE / REVIEW_ESCALATION`，没有重试同步动作。
5. U05 已落地的相关行为（本卡会触及其两处）：U05 把 `ACCEPTED` 与 `CLOSED/CANCELLED` 一并视为“已结束”（恢复状态 `NO_ACTIVE_WORK`、证据当前性 `NOT_APPLICABLE` 且文案“该需求已结束，证据仅供追溯。”）；U05 契约测试对 `CockpitUserAction` 做了“取值集合恰好等于四个”的断言。
6. 已验证基线质量（`ace7a959` 隔离检出，U05 验收时的同一提交、同一命令）：分目录回归 contracts 187 passed 1 skipped；infrastructure 32 passed；cli 216 passed 1 skipped；qml 219 passed（排除一个测试）+ 该测试单独 1 passed；core 755 passed 1 skipped 3 failed（失败即 E-G1-1，位于 `tests/core/test_implementation_card_service.py`，非本卡路径）。U05 判卷与原始输出：`.auto-pm/reports/m2-u05/gates/`。
7. 已登记的基线例外沿用 U05：E-G1-1（3 个 core 失败）、E-G1-2（`tests/qml` 整组进程会在 `test_file_watcher_bridge.py::test_debounce_coalesces_events` 处 Qt 崩溃，该测试单独运行通过）、E-G1-3、E-G3-1。
8. 对 WBS 三路径的偏差（有意，定稿前已确认）：①“待同步/已完成”是服务端事实，必须由服务与契约产出，放进 Bridge 或 QML 会让界面层做领域判断；②后台收尾与重试要改 `boss_main.qml` 接线；③U05 的恢复状态与证据当前性对 `ACCEPTED` 的处理须随之更正。路径总数 9，少于 U05。WBS 将在本卡验收后的修订中回写实际路径。
9. 不修改：`PmClosureService`、`ContinuityStore`、`PmFacadeService`、`PmConfirmationCard.qml`、`ActivityTimeline.qml`、`EvidenceDrawer.qml`、`WorkGraphView.qml`、Hook、release、任何 SQLite schema 或事件类型。

## 2. 单一目标（用户故事与完成定义）

作为驾驶舱使用者，我点“确认最终验收”之后：

1. 驾驶舱自动在后台完成收尾（同步变更单与台账，并关闭 Run/Work/Mission），界面不卡住；
2. 在收尾真正完成之前，卡片**不得**显示为“已完成”；同步失败时明确显示“待同步”及原因类别，并给我一个“重试同步”按钮；
3. 重试可重复点击而不产生重复事件；成功后才显示“已完成”，且重开驾驶舱后状态仍一致；
4. 缺少必要证据或状态不满足时，收尾拒绝执行并保持现场，绝不把它显示成已完成。

## 3. 实施前预检（只读，先于任何写入）

1. 核验本卡字节 SHA-256 已被外部 Approval Receipt 绑定；核验 `隔离基线` 是 U05 提交且可解析、WBS 提交与 SHA-256 一致。
2. 运行 `main.py implementation-card precheck --card-file` 对本卡，退出码必须为 0。
3. 核验 §4 九个路径在基线上均存在，与标注一致。
4. 在隔离候选中，对 §6 G1 的目标测试文件复现基线结果并记录数字（修改前），ruff 与 mypy 对 §4 的 Python 路径通过；不一致则停止。
5. 核验隔离候选 HEAD 等于基线，configured/effective runtime 与加载路径一致且无 fallback。

## 4. 精确 Owned Paths（9）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `auto_pm/contracts/pm_cockpit.py` | 存在 | 新增完成状态枚举、卡片字段、收尾结果 DTO、`RETRY_SYNC` 动作（向后兼容） |
| 2 | `auto_pm/application/core/pm_cockpit_service.py` | 存在 | 快照投影完成状态；新增 `close_accepted` 收尾入口；更正 U05 对 `ACCEPTED` 的处理 |
| 3 | `auto_pm/ui/qml/bridges/pm_cockpit_bridge.py` | 存在 | 验收成功后后台收尾；重试槽；完成信号 |
| 4 | `auto_pm/ui/qml/views/BossCockpitView.qml` | 存在 | 显示待同步/已完成与“重试同步”按钮及忙碌态 |
| 5 | `auto_pm/ui/qml/boss_main.qml` | 存在 | 验收、重试、完成信号的接线与快照刷新 |
| 6 | `tests/contracts/test_pm_cockpit.py` | 存在 | DTO 合同测试（只加不删，唯一允许改动见 §5.6） |
| 7 | `tests/core/test_pm_cockpit_service.py` | 存在 | 服务测试（真实存储，唯一允许改动见 §5.6） |
| 8 | `tests/qml/test_pm_cockpit_bridge.py` | 存在 | 后台收尾与重试的线程合同测试 |
| 9 | `tests/qml/test_boss_cockpit_view.py` | 存在 | 视图与 `boss_main.qml` 接线测试 |

出现第 10 条产品脏路径即停止，不得现场扩大 Decision。治理证据对象在控制根落账，不计入上述路径。

## 5. 合同（全部定稿，执行者不得改写含义）

### 5.1 DTO（`contracts/pm_cockpit.py`，所有新增字段都有默认值，`schema_version` 字面量不变，旧载荷必须仍能通过校验）

1. `PmCockpitCompletionState(StrEnum)`：`NOT_STARTED`、`PENDING_SYNC`、`COMPLETED`。
2. `CockpitUserAction` 新增 `RETRY_SYNC`（其余四个值与含义不变）。
3. `PmCockpitProjectCard` 新增 `completion_state: PmCockpitCompletionState = NOT_STARTED`、`completion_note: str = ""`（≤200 字符）。
4. 新增冻结 DTO `PmCockpitCompletion`：`mission_id: str`、`state: PmCockpitCompletionState`、`message: str`（≤200 字符，固定句，不含路径、异常文本或标识符）。
5. 所有新增字符串不得包含英文词 `lease`、`token`、绝对路径；既有“不含 lease/token”断言必须继续通过。

### 5.2 服务：快照投影（`pm_cockpit_service.py`，`snapshot()` 仍只读）

1. 卡片完成状态**仅由 Mission 状态推出**：`CLOSED` → `COMPLETED`，说明“已验收并完成变更单与台账同步。”；`ACCEPTED` → `PENDING_SYNC`，说明“验收已记录，变更单与台账尚未同步完成；完成前不会显示为已完成。”；其余所有状态 → `NOT_STARTED`，说明为空。**任何情况下，除 `CLOSED` 外都不得出现 `COMPLETED`。**
2. `ACCEPTED` 的卡片：里程碑“验收已记录，待同步”，下一步动作 `RETRY_SYNC`、文案“重试台账同步”，风险“中：验收已记录，变更单与台账尚未同步”，`user_action` 为 `RETRY_SYNC`。`CLOSED` 的卡片：里程碑沿用“已关闭”，动作 `NONE`。其它状态的既有行为不变。
3. 不得在 `snapshot()` 中读取或修改收尾表、不得触发同步。

### 5.3 服务：收尾入口 `close_accepted(mission_id) -> PmCockpitCompletion`

1. 构造函数新增可选参数 `closure_service: PmClosureService | None = None`（默认用同一存储新建，供测试注入台账同步桩；这是测试注入点，不是旁路）。
2. 按顺序：①Mission 为 `CLOSED` → 直接返回 `COMPLETED`，**不写任何数据**；②Mission 不是 `ACCEPTED` → 抛 `PmCockpitError`，文本“该需求尚未验收，不能收尾。”，不写任何数据；③`prepare_closure(mission_id, idempotency_key="cockpit-close-prepare:" + mission_id)`；④`complete_closure(closure_id, idempotency_key="cockpit-close-complete:" + mission_id)`。两个幂等键固定如上，保证重试与重开后重放而不产生重复事件。
3. 结果映射（固定句）：回执 `COMPLETED` → `COMPLETED`，“已完成：变更单与台账已同步。”；回执 `PENDING_SYNC` → `PENDING_SYNC`，“台账同步未完成，已保留现场；可稍后重试。”；任一 `PmClosureError` → `PENDING_SYNC`，“无法完成收尾：必要证据或状态未就绪，已保留现场；请向 PM 说明。”。回执中的 `pending_reason`、异常文本、路径一律只写日志，**不进入返回值**。
4. 只有回执 `COMPLETED` 才可返回 `COMPLETED`；服务不得自行推进任何状态，也不得绕过 `PmClosureService`。
5. 不得 Mock `PmClosureService` 的业务结果；测试只允许注入台账同步器与变更单实质写入这两个外部副作用点（与 `tests/core/test_pm_closure_service.py` 的既有做法一致）。

### 5.4 服务：更正 U05 对 `ACCEPTED` 的处理

1. 恢复状态：Mission `ACCEPTED` → `WAITING_FOR_USER`、动作 `RETRY_SYNC`、说明“验收已记录，变更单与台账尚未同步完成；可重试同步，完成前不会显示为已完成。”。该行放在“终态 → `NO_ACTIVE_WORK`”这一行**之前**，且终态集合不再含 `ACCEPTED`（仍含 `CLOSED`、`CANCELLED`）。
2. 证据当前性：Mission `ACCEPTED` → `NOT_APPLICABLE`，说明“验收已记录，验证证据已封存。”；`CLOSED`/`CANCELLED` 的“该需求已结束，证据仅供追溯。”不变。
3. 除上述两处外，U05 的焦点、恢复状态表与证据当前性规则不得改动。

### 5.5 Bridge、QML

1. Bridge 新增信号 `closureFinished = Signal(str, bool, str)`，参数为 `mission_id`、`completed`、`message`。
2. `confirmAcceptance(mission_id)`：行为与返回键保持不变，仅在服务确认成功时**追加返回键** `closing`（布尔）：成功且已排入后台收尾 → `True`；验收被拒绝或未排队 → `False`。验收被拒绝时不得排任何收尾任务。
3. 新增槽 `retryClosure(mission_id) -> QVariant`，返回 `{"accepted", "busy", "message"}`；空 ID → `accepted False, busy False`；同一 Mission 已有收尾在途 → `accepted False, busy True`，不堆积；线程池拒绝 → 清理在途标记，`accepted False, busy False`。
4. 收尾在后台 `QRunnable` 中调用 `service.close_accepted`；结果信号**恰好发射一次**，沿用既有“50 ms 轮询 Timer + 工作对象 done 标记”模式；`PmCockpitError` → `completed False`，消息取其文本；其它异常 → 记日志，消息固定为“无法完成收尾，已保留现场。”，不带异常文本；Bridge 销毁或 `stopSnapshotRefresh` 后晚到结果不得发射。同一 Mission 的在途标记按 Mission 区分，不同 Mission 互不阻塞。
5. `BossCockpitView.qml`：新增信号 `syncRetryRequested(string missionId)`、按 Mission 区分的忙碌态与 `isCloseBusy`/`setCloseBusy`（与既有 `startBusyByMission` 同一模式，重复点击在忙碌期间被抑制）；每张卡片：`completion_state === "PENDING_SYNC"` 时显示 `completion_note`（警示色）和“重试同步”按钮（忙碌时禁用并显示“正在同步…”）；`"COMPLETED"` 时显示“已完成并同步台账”（成功色）；其它状态两者都不显示。不显示百分比，不显示任何令牌/租约信息。
6. `boss_main.qml`：`onAcceptanceConfirmed` 在响应 `success` 且 `closing` 为真时 `setCloseBusy(missionId, true)`，并保留既有的状态消息与快照刷新；新增 `onSyncRetryRequested`：调用 `retryClosure`，`accepted` 时 `setCloseBusy(true)`，否则显示 `message`；新增对 `closureFinished` 的处理：`setCloseBusy(false)`、显示消息、刷新快照。`boss_main.qml` 中既有的启动、快照、证据接线保持原样。

### 5.6 对 U05 既有测试的唯一允许改动（其余一律不得改动、不得跳过）

1. `tests/contracts/test_pm_cockpit.py` 中 `test_u05_enums_expose_exactly_the_agreed_values` 对 `CockpitUserAction` 的期望集合，加入 `RETRY_SYNC`；
2. `tests/core/test_pm_cockpit_service.py` 中恢复状态表参数化用例里 `MissionState.ACCEPTED` 那一行，期望改为 `WAITING_FOR_USER`、`RETRY_SYNC`、片段“尚未同步完成”。

### 5.7 明确不做

不改 `PmClosureService`、`ContinuityStore`、Facade 与 §1.9 列出的其它文件；不新增 schema、事件类型或迁移；不新增会启动、重启 Run 或改写租约的入口；不做自动定时重试（只在用户点击或验收成功后触发）；不做收尾的详细日志浏览；不合并、不推送、不部署、不切换 release。

## 6. 门禁矩阵

所有命令均在隔离候选的项目根执行，使用工作区 `.venv` 解释器与 `-B`，先 `-o addopts= --no-cov -p no:cacheprovider`。

**G1 定向测试**（修改前先对基线跑同一集合并记录数字；修改后全部通过，0 失败，不新增跳过）：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider `
  tests/contracts/test_pm_cockpit.py tests/core/test_pm_cockpit_service.py tests/core/test_pm_facade_service.py `
  tests/core/test_pm_closure_service.py tests/core/test_pm_closure_saga.py `
  tests/qml/test_pm_cockpit_bridge.py tests/qml/test_boss_cockpit_view.py
```

**G2 分目录回归**（固定方法，同 U05；基线数字见 §1.6，候选相对基线：失败集合相同——core 仅 E-G1-1 的 3 个既存失败、通过数不少于基线、无新增失败、无新增跳过）：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/contracts
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/infrastructure
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/cli
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/core
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/qml --deselect tests/qml/test_file_watcher_bridge.py::test_debounce_coalesces_events
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/qml/test_file_watcher_bridge.py::test_debounce_coalesces_events
```

基线数字取自 §1.6 已记录的同一提交结果，不要求重跑 core 基线；候选的 core 约 40 分钟，须后台运行并在租约到期前至少 10 分钟续租。本卡 9 个路径内的测试出现 Qt access violation 不得按 E-G1-2 豁免：先在全新进程单独重跑该文件一次并保存两次原始输出；仍崩溃则按 §9 停止。

**G3 必测场景（真实存储；测试只允许注入台账同步器与变更单实质写入）**：

1. 快照：对每个 `MissionState`，完成状态与动作符合 §5.2；**只有 `CLOSED` 才出现 `COMPLETED`**；`ACCEPTED` 为 `PENDING_SYNC` 且动作 `RETRY_SYNC`；快照前后存储字节不变；
2. 收尾成功：已验收谱系 + 台账同步桩成功 → 返回 `COMPLETED`，Mission `CLOSED`、Work `CLOSED`、Run `SUCCEEDED`，且仅新增预期事件；
3. 同步失败：同步桩抛 `OSError` 或返回非干净结果 → 返回 `PENDING_SYNC` 固定句，Mission 仍 `ACCEPTED`、Work 仍 `IN_PROGRESS`、Run 仍 `VERIFYING`，无 `CLOSURE_COMPLETED` 事件，返回值不含异常文本与路径；
4. 重试：失败后令同步桩恢复 → 再次 `close_accepted` 成功；对已完成的 Mission 再次调用不写任何数据且不新增事件；同一幂等键的两次调用不产生重复事件；
5. 缺少必要证据：根 Work 非 `IN_PROGRESS`、最新 Run 非 `VERIFYING` 或缺 Checkpoint → `PENDING_SYNC`（`PmClosureError` 句），不改动任何状态；
6. 未验收的 Mission 调用 `close_accepted` → `PmCockpitError` 且不写数据；
7. 对 `ACCEPTED` 的恢复状态与证据当前性符合 §5.4，对 `CLOSED` 仍为 `NO_ACTIVE_WORK`；
8. Bridge：验收成功恰好排一个收尾任务且返回 `closing True`；验收被拒绝不排任务且 `closing False`；`retryClosure` 的三种返回；重复点击只产生一个任务；不同 Mission 互不阻塞；`closureFinished` 恰好一次、失败不带异常文本；销毁或 `stopSnapshotRefresh` 后晚到结果不发射；既有 `confirmAcceptance` 返回键保持；至少一个使用真实服务（注入同步桩）的端到端用例；
9. QML：视图在 `PENDING_SYNC` 显示说明与“重试同步”按钮、点击发出携带正确 `missionId` 的信号一次、忙碌期间禁用并抑制重复；`COMPLETED` 显示“已完成并同步台账”；其它状态两者都不显示；`boss_main.qml` 与视图可加载无 QML 警告；源码断言接线（`retryClosure`、`closureFinished`、`syncRetryRequested`）；至少一个用真实 Bridge 与服务的端到端用例：快照显示待同步 → 点击重试 → 后台完成 → 界面变为已完成；
10. 合同：旧载荷（无完成字段）仍可校验；新 DTO 冻结；枚举取值完整；`RETRY_SYNC` 存在；字符串长度边界。

测试不得通过 Mock 业务结果、硬编码预期字段或跳过来变绿。

**G4 静态质量**：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m ruff check --no-cache `
  auto_pm/contracts/pm_cockpit.py auto_pm/application/core/pm_cockpit_service.py auto_pm/ui/qml/bridges/pm_cockpit_bridge.py `
  tests/contracts/test_pm_cockpit.py tests/core/test_pm_cockpit_service.py tests/qml/test_pm_cockpit_bridge.py tests/qml/test_boss_cockpit_view.py
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m mypy --strict --no-incremental `
  auto_pm/contracts/pm_cockpit.py auto_pm/application/core/pm_cockpit_service.py auto_pm/ui/qml/bridges/pm_cockpit_bridge.py `
  tests/contracts/test_pm_cockpit.py tests/core/test_pm_cockpit_service.py tests/qml/test_pm_cockpit_bridge.py tests/qml/test_boss_cockpit_view.py
git diff --check
```

不得使用 `--follow-imports=skip`，不得新增文件级抑制或为通过门禁新增 `type: ignore`（测试中加载 QML 对象的既有用法除外）。

**G5 范围与洁净**：`git diff --name-only` 与 `git status --porcelain` 的路径集合精确等于 §4 的 9 个路径；无 `.coverage`、缓存、`tmp_*` 残留（DEV-TMP-001）。

**G6 既有断言不变**：除 §5.6 的两处外，所有既有测试断言保持不变（只允许新增测试与整理 import）；已有的 U05 抽屉、证据、恢复状态、启动防重与快照刷新用例全部通过。

**G7 不触碰生产**：测试只使用临时仓库与临时库，不读写真实控制面；不改 Hook、release、`.auto-pm` 下任何运行态对象。

## 7. 实施授权签字门

### 7.1 当前签字状态

| 字段 | 当前值 |
|---|---|
| 卡片 | `CARD-SW008-M2-U06 V1.0` |
| 实施批准 | `PENDING`（须用户在对话中明确批准；批准后以委托方式由 Claude 执行，回执另行生成） |
| 最终验收 | `PENDING`（验收与 CHG 最终收口由用户亲自执行，不委托） |
| 审批人 | `fubai / baiyang`（同一用户、等权署名） |
| 隔离基线 | `ace7a9593d6841c2dc1a434d466b39990969511d` |
| Owned Paths | §4 的 9 个路径 |
| 执行模型 | `Claude Sonnet 5.5` |
| 明确禁止 | 第 10 条路径、直接 SQL、历史改写、Hook/release 修改、绕过收尾服务、新增启动或重启入口、自动定时重试、合并、推送、部署 |

### 7.2 授权成立与失效

1. 卡片字节、隔离基线、WBS 真源、owned paths、执行模型或禁止事项任一漂移，审批立即失效。
2. 外部 Approval Receipt 绑定本卡完整字节 SHA-256、基线、WBS 提交、9 个路径、允许/禁止动作、执行模型、审批人与时间；卡片自身不含自身 SHA-256。
3. 实施批准与最终验收分离；执行 Agent 不得自签验收。

## 8. 治理执行顺序

1. 只读预检并输出事实表（§3）。
2. 用户批准本卡后，创建并批准 SW-2026-008 的独立 CHG（领域 SCPT）与精确 Decision（§4 九路径）。
3. 创建 Work（`--card-file` 指向本卡，Work 与 Decision 的项目一致，均为 SW-2026-008）、在全新隔离候选（自 U05 提交起，分支 `codex/m2-u06-sync-state`）启动 Run（`--lease-seconds` 不超过 3600，必要时续租）。
4. 在候选中按 §5 实现并完成 §6 门禁；判卷结果写入 `.auto-pm/reports/m2-u06/` 下机器可读判卷文件。
5. 创建当前字节 Checkpoint（`git_head` 为基线，逐文件记录 SHA-256 与判卷文件 SHA-256），**先于提交**；随后走正常 Hook 提交（不得 `--no-verify`）；提交后核验提交内 blob 与 Checkpoint 逐一相同，否则停止。
6. Run/Work 终态、台账 `main.py ledger reconcile SW-2026-008` 为 0/0/0；**CHG 最终收口由用户执行**。
7. 向用户报告后停止；SHA 与 ID 写入交接文档。WBS 回写为独立的后续修订，不在本卡范围。

## 9. 有界纠正与硬停止条件

本卡单提交，一个主 Run；仅当失败稳定复现、完全落在 §4 路径内、无需合同或路径扩展时，允许一个纠正 Run（必须新建 Run 并重建 Checkpoint）。**执行期间不得修订本卡**；需要修订本卡即属于硬停止。

以下任一情况立即保留现场、停止并报告：

- 基线 HEAD、runtime 身份、Decision 字节或 owned paths 不一致，或需要第 10 条路径；
- 需要改 `PmClosureService`、`ContinuityStore`、Facade、事件类型或 SQLite schema 才能实现；
- 只能通过 Mock 收尾服务的业务结果、硬编码 `COMPLETED`、跳过测试、放宽断言、文件级抑制或手改数据库才能通过；
- 需要新增启动、重启 Run、改写租约或自动定时重试的入口；
- 需要改动 §5.6 之外的 U05 既有断言；
- 本卡 9 个路径内的测试出现可复现的 Qt 崩溃（按 G2 流程仍无法通过）；
- Checkpoint 不是当前字节，或质量门未完整返回；
- 发现本卡与代码事实矛盾（先停止，由用户裁决是否出新版本，不得自行改卡）。

## 10. 交付物

1. 基线 SHA 与预检事实表（含 G1 修改前的基线数字）；
2. CHG / Decision / Work / Run / Checkpoint ID 与 Approval Receipt；
3. 精确 diff 与 9 个路径的最终 SHA-256；
4. G1～G7 矩阵、原始命令、Exit Code、输出位置，以及 G2 对基线的逐目录对照；
5. G3 十类场景与测试名称的对照表；
6. 不可变提交 SHA 与 Checkpoint 绑定核对；
7. 明确声明：驾驶舱现在会在验收后自动调用收尾服务；除 `CLOSED` 外绝不显示“已完成”；运行时 `1.3.3-a808fa8` 不含 U05/U06 代码，不得据此声称稳定运行时验收。

## 11. 与其他任务的关系

U07 依赖 C09、与本卡无路径交集。WBS 对 U05/U06 的回写与 M2 总审计不在本卡范围。
