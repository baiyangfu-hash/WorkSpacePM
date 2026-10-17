# U07D｜GUI 开工接线实施卡

> 卡片编号：`CARD-SW008-M2-U07D`
> 对应 WBS：`U06`/`U07` 之间的接线缺口（卡 032 §11 已登记的“GUI 开工接线”）；为 V05（GUI 双领域联合验收）提供“驾驶舱点开始 → 验证 → 验收 → 收尾”的真实链路
> 版本：`V1.0`（2026-10-01，一次定稿；执行期间不得修订，见 §9）
> 状态：`PLANNED / NOT_AUTHORIZED`（定稿，待授权；授权方式见 §7）
> 依赖：U07A（`795fe448`）、U07B（`35379585`）、U07C（`9a92e9b7`）均已验收收口（CHG-SCPT-2026-364/365/366/367 completed）
> 隔离基线：`9a92e9b7a38324703efda83d5c252a0e88d74adc`
> 治理任务真源：WBS 提交 `572932a7d7fe23cf799c6f8800d77263aec3c3ee`；WBS SHA-256 `33EE746A6D9495B7B39D09921605D3745A405AE26D1EBC51450C60213ACD5FCD`
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 推荐执行模型：`Claude Sonnet 4.6 (Thinking)` 或能力不低于它的模型；实际执行者 `Claude Sonnet 5.5`
> 禁用能力：`pm-workflow`

> V1.0 定稿说明：本卡写于一次**可行性演练**之后（§1.3、§1.4）。演练在 U07A/U07C 的真实夹具上复现了 GUI 启动缺口，并用现有 API 把“从草稿任务恢复范围卡 → 一次调用执行并验证 → 驾驶舱确认验收 → 收尾”真实跑通到 `COMPLETED`。演练脚本归档于 `.auto-pm/reports/m2-u07d/`（`diag_gui1.py` 复现缺口、`diag_gui2.py` 验证修复链，仅供参考，不是产品代码）。执行者只做填空与验证，不得现场修订本卡、扩大路径或放宽门禁；遇到本卡未覆盖的情况按 §9 停止并报告。

## 1. 背景与已核实事实（2026-10-01，基线 `9a92e9b7`，均为命令或源码核验）

1. 驾驶舱现有流程（U03～U06 已完成并验收）：卡片上的 `user_action == CONFIRM_START` 才显示“确认开始”；点击经 QML `startConfirmed` → `PmCockpitBridge.startExecution` → 后台 `_StartWorker` → `PmCockpitService.start_execution` → `PmFacadeService.start_approved_mission_foreground`；执行后用户在 `CONFIRM_ACCEPTANCE` 时确认验收，驾驶舱自动后台收尾（U06）。
2. **缺口一：新批准的规划任务在驾驶舱里没有“开始”入口。** 范围卡被批准并物化为 Mission 后处于 `DRAFT`，且没有绑定根 Work。`PmCockpitService` 对 `DRAFT` 一律返回 `user_action=NONE`、文案“向 PM 描述下一项需求”（`_resume`/`_next_action` 只对 `AWAITING_APPROVAL` 给 `CONFIRM_START`）。
3. **缺口二：就算强行调用，启动也失败。** 演练复现：对该 Mission 调 `PmCockpitService.confirm_start` 得到 `PmCockpitError: 该需求尚未完成内部授权，暂时不能开始执行`（`PmFacadeService.approve` 需要已绑定的根 Work，而根 Work 只在 `run_approved_planning` 的“plan→approve(root_work)→execute”序列里绑定）。
4. **缺口三：启动流程只执行不验证。** `start_approved_mission_foreground` 在 `VERIFYING` 处结束，没有任何一步生成验证 Checkpoint 或把 Mission 推到 `ACCEPTANCE_PENDING`（U07A 已提供 `run_approved_planning` 补上，但驾驶舱尚未使用），所以用户永远点不到“确认验收”。
5. **修复链可行性（演练）**：对 `DRAFT` 规划 Mission，`facade.recover_planning_scope_card(mission_id)` 能恢复出与原卡相等的范围卡；`facade.run_approved_planning(...)` 一次调用完成 plan/approve/execute、真实执行、自动验证，得到 `verified=True`、`ACCEPTANCE_PENDING`；此后驾驶舱快照给出 `CONFIRM_ACCEPTANCE`，`PmCockpitService.confirm_acceptance` 得 `ACCEPTED`，`close_accepted` 得 `COMPLETED`（U06/U07B 既有能力）。即**只需要把启动这一步接对**，验收与收尾无需改动。
6. 可判别“已获批准的规划任务”的信息就在 Mission 上：规划批准创建的 Mission 的 `authority.routing` 为 `required_worktree_mode == ISOLATED`、`approved_model` 非空、`allowed_execution_adapters` 非空；旧式 Mission（测试夹具默认路由）不满足。无需额外读取 Decision。
7. 现有 Bridge 测试 `tests/qml/test_pm_cockpit_bridge.py` 用假服务 `_StartService` 返回 `ForegroundExecutionReceipt`，并断言成功提示语“任务已启动，正在验证。”；本卡把服务的启动结果改为 `PmRunOutcome`，因此该测试夹具与这一条提示语断言必须随之改动（§6 G6 逐项登记，是本卡唯一允许改动的既有断言）。`tests/core/test_pm_cockpit_service.py` 没有 `start_execution` 相关用例。
8. 基线质量（`9a92e9b7`，U07C 验收时的同一提交、同一命令）：contracts 191 passed 1 skipped；infrastructure 32 passed；cli 216 passed 1 skipped；qml 232 passed（排除一个测试）+ 该测试单独 1 passed；core 800 passed 1 skipped 3 failed（失败即 E-G1-1，位于 `tests/core/test_implementation_card_service.py`，非本卡路径）；`tests/change` 230 passed。原始输出：`.auto-pm/reports/m2-u07c/gates/`。G1 基线（本卡 §6 G1 同一集合去掉计划新增的 `test_pm_cockpit_start_e2e.py`、`9a92e9b7` 干净检出、改动前实测）：84 passed、0 failed、0 skipped；原始输出 `.auto-pm/reports/m2-u07d/gates/G1_baseline.txt`（退出码 0）。本卡 §4 已存在的 4 个 Python 路径在基线上 `ruff` 与 `mypy --strict` 均通过（预检再核）。
9. 已登记的基线例外沿用：E-G1-1、E-G1-2（`tests/qml` 整组进程会在 `test_file_watcher_bridge.py::test_debounce_coalesces_events` 处 Qt 崩溃，该测试单独通过）、E-G1-3、E-G3-1。
10. 明确**不在本卡**：驾驶舱从“新目标”到“范围卡/批准”的 GUI 化（草稿的“范围待规划”之后的规划与批准动作，属于 V05 的两次业务决策）；进程在“执行完成、验证未做”的间隙崩溃后的恢复（令牌只在内存，见 §5.1-5，属于故障恢复项）；QML 文件、CLI、SDK、`PmFacadeService`、收尾服务。

## 2. 单一目标（用户故事与完成定义）

作为在驾驶舱里的用户，对一个已经批准范围卡的新任务，我必须能：

1. 在驾驶舱看到“确认开始执行”；
2. 点击后任务在后台真实执行并自动质量验证，界面不卡死，成功时提示“已执行并通过质量验证，等待您的最终验收。”并刷新出“确认最终验收”；
3. 执行失败、状态未确认、质量验证不通过时，得到固定中文提示，**不**显示成功、**不**进入验收、现场保留，界面可再次操作或保持只读；
4. 之后沿用 U06/U07B 的验收与收尾直到任务关闭；
5. 界面上不出现异常原文、路径或租约令牌。

## 3. 实施前预检（只读，先于任何写入）

1. 核验本卡字节 SHA-256 已被外部 Approval Receipt 绑定；核验 `隔离基线` 是 U07C 提交且可解析、WBS 提交与 SHA-256 一致。
2. 运行 `main.py implementation-card precheck --card-file` 对本卡，退出码必须为 0。
3. 核验 §4 中 4 个“存在”路径在基线上存在、1 个“计划新增”路径在基线上不存在。
4. 在隔离候选中，对 §6 G1 的目标测试文件（不含计划新增文件）复现基线结果并记录数字（修改前），ruff 与 mypy 对 §4 已存在的 Python 路径通过；不一致则停止。
5. 核验隔离候选 HEAD 等于基线，configured/effective runtime 与加载路径一致且无 fallback。
6. 阅读 `.auto-pm/reports/m2-u07d/diag_gui1.py`、`diag_gui2.py`，确认其调用顺序与本卡 §5 一致。
7. **续租（硬性）**：开始任何超过 30 分钟的门禁（G2 的 core 约 55 分钟）之前，先后台启动 `bash .auto-pm/reports/m2_renew_loop.sh <close.env>`；门禁结束后创建 `STOP_RENEW` 文件停止它。续租失效（租约过期）时停止并报告，不得自行走恢复链。

## 4. 精确 Owned Paths（5）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `auto_pm/application/core/pm_cockpit_service.py` | 存在 | 草稿规划任务的 `CONFIRM_START` 判定；`start_execution` 改为“恢复范围卡 + 一次调用执行并验证”；构造函数新增可选 `facade` 注入点 |
| 2 | `auto_pm/ui/qml/bridges/pm_cockpit_bridge.py` | 存在 | `_StartWorker` 按 `PmRunOutcome` 给出固定提示，不再泄漏异常原文 |
| 3 | `tests/core/test_pm_cockpit_service.py` | 存在 | 服务层新增测试（只加不改既有断言） |
| 4 | `tests/qml/test_pm_cockpit_bridge.py` | 存在 | Bridge 新增测试；仅 §6 G6 登记的夹具与一条提示语断言允许改动 |
| 5 | `tests/qml/test_pm_cockpit_start_e2e.py` | 计划新增 | 真实子进程、真实 Git 隔离工作树、真实质量门的驾驶舱整链测试 |

出现第 6 条产品脏路径即停止，不得现场扩大 Decision。治理证据对象在控制根落账，不计入上述路径。**QML 文件不在 owned paths 内**：按钮由既有的 `user_action == CONFIRM_START` 驱动，无需改 QML。

## 5. 合同（全部定稿，执行者不得改写含义）

### 5.1 驾驶舱服务（`pm_cockpit_service.py`）

1. 构造函数新增**最后一个**关键字参数 `facade: PmFacadeService | None = None`（默认 `None`，行为与基线一致）。仅 `start_execution` 使用它：为空则 `PmFacadeService(self._workspace_root)`；`confirm_start`、`confirm_acceptance`、`close_accepted` 及其它方法行为与实现不变。
2. **开始入口判定**：新增私有静态方法 `_is_start_ready(mission: Mission) -> bool`，当且仅当 `mission.state is MissionState.DRAFT` 且 `mission.authority.routing.required_worktree_mode is WorktreeMode.ISOLATED` 且 `mission.authority.routing.approved_model` 非空且 `mission.authority.routing.allowed_execution_adapters` 非空时为真。`_resume`（在 `AWAITING_APPROVAL` 分支之后、`DRAFT` 分支之前判定）对 `_is_start_ready` 为真的 Mission 返回 `PmCockpitResume(state=WAITING_FOR_USER, user_action=CONFIRM_START, reason="等待您确认开工；确认前不会创建或启动任何执行。")`；`_next_action` 对同一条件返回 `(CockpitUserAction.CONFIRM_START, "确认开始执行")`。其它状态与不满足该条件的 `DRAFT`（旧式 Mission）的行为、文案与基线逐字一致。
3. **`start_execution(self, mission_id: str) -> PmRunOutcome`**（返回类型由 `ForegroundExecutionReceipt` 改为 `PmRunOutcome`），顺序固定：
   1. `mission_id = mission_id.strip()`，为空抛 `PmCockpitError("未找到可启动的需求。")`；
   2. 读取 Mission：`self._store.get_mission(mission_id)`；`ContinuityStoreError`/`sqlite3.Error`/`OSError`/`ValueError` → 抛 `PmCockpitError("无法读取该需求，已保留现场。")`；
   3. `ACCEPTANCE_PENDING` → 抛 `PmCockpitError("该需求已执行并验证，等待验收；请直接确认验收，不要重复执行。")`；不在 `{DRAFT, AWAITING_APPROVAL, ACTIVE}` 的其它状态 → 抛 `PmCockpitError("该需求当前不能开始执行。")`；以上均不写任何数据；
   4. `facade = self._facade_override or PmFacadeService(self._workspace_root)`；`card = facade.recover_planning_scope_card(mission_id)`；令牌 `secrets.token_urlsafe(32)` 只在本次调用栈内；`outcome = facade.run_approved_planning(card, expected_plan_hash=card.plan_hash, lease_token=令牌, lease_token_environment="AUTO_PM_EXECUTION_LEASE_TOKEN")`；返回 `outcome`；
   5. `PmFacadeError` → 抛 `PmCockpitError(str(error)) from error`（沿用既有做法）；其它异常不在服务层吞掉。
4. 令牌不得写入日志、返回值、异常文本、任何持久化对象，不得新增任何口令落点；`ContinuityStore` 既有的 `execution_leases.lease_token` 是唯一落点（租约存续期间），本卡不触碰。
5. 已知限制（不处理，写入交付声明）：令牌只在内存。若进程在“执行完成、验证尚未完成”的间隙崩溃，重启后同一任务无法补做验证（会得到“质量验证未通过”类结果且现场保留）；这是故障恢复项，不在本卡。

### 5.2 Bridge（`pm_cockpit_bridge.py`）

`_StartWorker.run` 改为：

1. `outcome = self._bridge._service.start_execution(self._mission_id)`；
2. `outcome.verified` 为真 → `self.result = (True, outcome.message)`；
3. 否则 `outcome.receipt_status == "FAILED"` → `(False, "任务启动失败，执行记录已保留。")`；`== "PENDING"` → `(False, "无法确认任务已启动，已保留待核验状态。")`；其它（执行已完成但验证未通过）→ `(False, outcome.message)`；
4. `PmCockpitError` → `(False, str(error) or "任务启动失败。")`（服务层文案均为受控中文，保持原样）；**其它所有 `Exception` → `(False, "任务启动失败，已保留现场。")`，不得再返回 `str(error)`**，异常用 `log.exception` 记录；
5. `finally: self.done = True` 与其余结构（`_start_workers` 一次性、`startFinished` 信号、轮询计时器、关闭时抑制）一字不变。QML 不改：成功后 `onStartFinished` 已有“刷新快照”逻辑，快照会给出 `CONFIRM_ACCEPTANCE`。

### 5.3 测试夹具约定

1. `tests/qml/test_pm_cockpit_start_e2e.py` 复用 `tests/core/test_cockpit_api.py` 与 `tests/core/test_pm_run_e2e.py` 已有的 `_workspace`、`_plan`、`PROJECT_ID`、`APPROVER`、`EVIDENCE` 等夹具（真实 Git 工作区、真实子进程辅助脚本、真实 pytest/ruff/mypy 质量门），不复制其代码；不 Mock `EvidenceCollectionService`、`ContinuityExecutionService`、`PmClosureService`、`PmFacadeService.run_approved_planning`、质量收据或任何业务结果；
2. 整链测试用 `_HoldingThreadPool`（保存 worker、测试线程内同步 `worker.run()`）驱动 Bridge，再调 `bridge._poll_start_workers()`/`_poll_close_workers()`——这与既有 Bridge 测试的做法一致，避免依赖 Qt 事件循环时序（降低 E-G1-3 类偶发崩溃的暴露面）；真实服务通过 `PmCockpitService(root, store=…, facade=夹具 facade)` 注入带假执行器的 facade；
3. 每个场景结束不得在仓库内残留 `.coverage`、缓存、`tmp_*`。

### 5.4 必测场景（G3）

1. **开始入口判定**（服务层）：用真实 Store 里的 Mission 断言：规划批准的 `DRAFT` Mission → 卡片 `user_action == CONFIRM_START`、`next_user_action == "确认开始执行"`、resume 文案为 §5.1-2 的固定句；旧式 `DRAFT` Mission（默认路由）→ 仍为 `NONE`/“向 PM 描述下一项需求”；`AWAITING_APPROVAL` 行为不变；
2. **成功整链**（e2e）：规划批准的 `DRAFT` Mission → 快照 `CONFIRM_START` → `bridge.startExecution` → worker 运行并 `_poll_start_workers` 后 `startFinished` 恰好一次且为 `(mission_id, True, "已执行并通过质量验证，等待您的最终验收。")` → 快照变为 `CONFIRM_ACCEPTANCE`（证据 CURRENT）→ `bridge.confirmAcceptance` → 后台收尾 → `closureFinished` 为成功 → Mission `CLOSED`、Run `SUCCEEDED`、Work `CLOSED`；变更单无占位且含 `**验证结论**` 行；`LedgerReconciler().reconcile(root).is_clean`；源工作区范围文件字节不变；
3. **一次性与忙碌**（e2e）：同一 Mission 在 worker 完成前重复 `startExecution` 被拒（`busy True`），完成后辅助进程总共只启动过 1 次（计数文件）；
4. **执行失败**（e2e，辅助进程非零退出）：`startFinished` 为 `(…, False, "任务启动失败，执行记录已保留。")`；无 Checkpoint；Mission 仍 `ACTIVE`；快照**不**出现 `CONFIRM_ACCEPTANCE`；
5. **质量验证不通过**（e2e，辅助进程写入会使测试失败的代码）：`startFinished` 为 `(…, False, "质量验证未通过，已保留现场；未进入验收。")`；无 Checkpoint；Mission 仍 `ACTIVE`；
6. **服务层前置拒绝**：空 `mission_id`、不存在的 Mission、`ACCEPTANCE_PENDING`、`ACCEPTED`/`CLOSED`、无规划批准的旧式 Mission 各一例 → 抛 `PmCockpitError` 且文案为 §5.1-3 的固定句（旧式 Mission 为包装后的 Facade 文案）；调用前后数据库事件总数不变；
7. **Bridge 提示映射**（单元，假服务）：`verified` → 成功句；`FAILED` → 失败句；`PENDING` → 待核验句；验证未通过 → `outcome.message`；`PmCockpitError("授权已失效")` → 原文；其它 `Exception`（含带路径、令牌样字符串的消息）→ 固定句“任务启动失败，已保留现场。”，信号文本不含该异常文本；
8. **隐私**：整链后，数据库除 `execution_leases.lease_token` 列外全部文本、`startFinished`/`closureFinished` 信号文本、日志捕获中都不含租约令牌；整链收尾后该列也不含令牌（租约已释放）；
9. **既有行为不变**：`tests/core/test_pm_cockpit_service.py`、`tests/qml/test_pm_cockpit_bridge.py`、`tests/qml/test_boss_cockpit_view.py` 的既有用例除 §6 G6 登记的唯一改动外全部原样通过；`test_boss_cockpit_view.py` 中对 `pmCockpitBridge.startExecution(missionId)` 的 QML 源码断言保持通过（证明 QML 未改）。

测试不得通过 Mock 业务结果、硬编码预期字段或跳过来变绿；单元层可对“外部副作用点”注入故障，但场景 2、4、5 必须使用真实子进程、真实质量门与真实收尾服务。

### 5.5 明确不做

不改 QML、CLI、SDK、`PmFacadeService`、`PmClosureService`、收尾/变更单代码；不把“新目标 → 范围卡 → 批准”搬进 GUI；不处理崩溃间隙的恢复；不新增 schema、事件类型或迁移；不新增会在没有批准链的情况下启动执行的入口（`CONFIRM_START` 只对已获规划批准的 Mission 出现）；不合并、不推送、不部署、不切换 release。

## 6. 门禁矩阵

所有命令均在隔离候选的项目根执行，使用工作区 `.venv` 解释器与 `-B`，先 `-o addopts= --no-cov -p no:cacheprovider`。

**G1 定向测试**（修改前先对基线跑同一集合（不含计划新增文件）并记录数字；修改后全部通过，0 失败，不新增跳过）：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider `
  tests/core/test_pm_cockpit_service.py tests/qml/test_pm_cockpit_bridge.py tests/qml/test_boss_cockpit_view.py `
  tests/qml/test_pm_cockpit_start_e2e.py
```

基线数字：84 passed（§1.8）；候选须不少于 84 + 本卡新增测试数，且 0 failed、0 skipped。`tests/qml` 出现 Qt access violation 时按 G2 流程处理，不得豁免。

**G2 分目录回归**（固定方法，同 U05～U07C；基线数字见 §1.8，候选相对基线：失败集合相同——core 仅 E-G1-1 的 3 个既存失败、通过数不少于基线、无新增失败、无新增跳过；`tests/change` 同样对比）：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/contracts
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/infrastructure
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/cli
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/change
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/core
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/qml --deselect tests/qml/test_file_watcher_bridge.py::test_debounce_coalesces_events
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m pytest -o addopts= --no-cov -p no:cacheprovider tests/qml/test_file_watcher_bridge.py::test_debounce_coalesces_events
```

各组都必须在**最终字节**上全量重跑；core 约 55 分钟，**必须先按 §3-7 启动续租循环**。`tests/qml` 组出现 Qt access violation 不得按 E-G1-2 豁免（E-G1-2 只针对被排除的那一个测试）：先在全新进程单独重跑出问题的文件一次并保存两次原始输出；仍崩溃则按 §9 停止。

**G3 必测场景**：§5.4 的 9 项各至少一个独立测试，并在判卷报告中列出“场景 → 测试名”对照。

**G4 静态质量**：

```powershell
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m ruff check --no-cache `
  auto_pm/application/core/pm_cockpit_service.py auto_pm/ui/qml/bridges/pm_cockpit_bridge.py `
  tests/core/test_pm_cockpit_service.py tests/qml/test_pm_cockpit_bridge.py tests/qml/test_pm_cockpit_start_e2e.py
& C:\Users\fubai\Documents\My_Workspace\.venv\Scripts\python.exe -B -m mypy --strict --no-incremental `
  auto_pm/application/core/pm_cockpit_service.py auto_pm/ui/qml/bridges/pm_cockpit_bridge.py `
  tests/core/test_pm_cockpit_service.py tests/qml/test_pm_cockpit_bridge.py tests/qml/test_pm_cockpit_start_e2e.py
git diff --check
```

不得使用 `--follow-imports=skip`，不得新增文件级抑制或为通过门禁新增 `type: ignore`；`pm_cockpit_bridge.py` 既有的 `# noqa: BLE001` 行（`_CloseWorker` 内）不得改动，`_StartWorker` 中既有的 `# noqa: BLE001` 在重写后若仍需要其说明，可保留同一条既有注释，但不得新增其它 `noqa`；在最终字节上运行。

**G5 范围与洁净**：`git diff --name-only` 加未跟踪文件的路径集合精确等于 §4 的 5 个路径（尤其**无任何 `.qml` 文件改动**）；无 `.coverage`、缓存、`tmp_*` 残留（DEV-TMP-001）。

**G6 既有断言不变（唯一允许的改动，逐项登记）**：`tests/qml/test_pm_cockpit_bridge.py` 中**仅允许**：(a) `_StartService.start_execution` 的返回类型/类型标注与 `_receipt` 辅助函数改为返回 `PmRunOutcome`（保持函数名与调用点 `_receipt("VERIFYING")`、`_receipt("PENDING")` 不变），相应的 import 行；(b) `test_start_execution_is_one_shot_until_worker_finishes` 中断言 `[("MISSION-001", True, "任务已启动，正在验证。")]` 的提示语改为 `"已执行并通过质量验证，等待您的最终验收。"`。其它既有断言（含 `test_start_execution_failure_clears_busy_without_false_success` 的“授权已失效”与“无法确认任务已启动，已保留待核验状态。”）一字不改；`tests/core/test_pm_cockpit_service.py` 只允许新增测试与整理 import。

**G7 不触碰生产**：测试只使用临时仓库与临时库，不读写真实控制面与真实 `00_Infrastructure`；不改 Hook、release、`.auto-pm` 下任何运行态对象；e2e 的临时工作区在测试结束后被清理；测试中的“codex”可执行文件一律是真实子进程的假辅助脚本，**不得启动真实的 codex**。

## 7. 实施授权签字门

### 7.1 当前签字状态

| 字段 | 当前值 |
|---|---|
| 卡片 | `CARD-SW008-M2-U07D V1.0` |
| 实施批准 | `PENDING`（须用户在对话中明确批准；批准后以委托方式由 Claude 执行，回执另行生成） |
| 最终验收 | `PENDING`（验收由用户做出；CHG 收口须经用户在对话弹窗确认后才可由 Claude 代跑） |
| 审批人 | `fubai / baiyang`（同一用户、等权署名） |
| 隔离基线 | `9a92e9b7a38324703efda83d5c252a0e88d74adc` |
| Owned Paths | §4 的 5 个路径 |
| 执行模型 | `Claude Sonnet 5.5` |
| 明确禁止 | 第 6 条路径、任何 QML 改动、直接 SQL、历史改写、Hook/release 修改、改动 CLI/SDK/Facade/收尾/变更单代码、启动真实 codex、新增无批准链的启动入口、`os.chdir` 之类的全局状态、合并、推送、部署 |

### 7.2 授权成立与失效

1. 卡片字节、隔离基线、WBS 真源、owned paths、执行模型或禁止事项任一漂移，审批立即失效。
2. 外部 Approval Receipt 绑定本卡完整字节 SHA-256、基线、WBS 提交、5 个路径、允许/禁止动作、执行模型、审批人与时间；卡片自身不含自身 SHA-256。
3. 实施批准与最终验收分离；执行 Agent 不得自签验收。

## 8. 治理执行顺序

1. 只读预检并输出事实表（§3），含 G1 修改前的基线数字。
2. 用户批准本卡后，创建并批准 SW-2026-008 的独立 CHG（领域 SCPT）与精确 Decision（§4 五路径，计划新增路径不检查基线存在）。
3. 创建 Work（`--card-file` 指向本卡，Work 与 Decision 的项目一致，均为 SW-2026-008）、在全新隔离候选（自 U07C 提交起，分支 `codex/m2-u07d-gui-start`）启动 Run（`--lease-seconds` 不超过 3600）；**随即后台启动续租循环**（§3-7）。
4. 在候选中按 §5 实现并完成 §6 门禁；判卷结果写入 `.auto-pm/reports/m2-u07d/` 下机器可读判卷文件。
5. 创建当前字节 Checkpoint（`git_head` 为基线，逐文件记录 SHA-256 与判卷文件 SHA-256），**先于提交**；随后走正常 Hook 提交（不得 `--no-verify`）；提交后核验提交内 blob 与 Checkpoint 逐一相同，否则停止。
6. Run/Work 终态、台账 `main.py ledger reconcile SW-2026-008` 为 0/0/0；CHG 收口须经用户弹窗确认后由 Claude 代跑，或由用户自己运行。
7. 向用户报告后停止；SHA 与 ID 写入交接文档。WBS 回写为独立的后续修订，不在本卡范围。

## 9. 有界纠正与硬停止条件

本卡单提交，一个主 Run；仅当失败稳定复现、完全落在 §4 路径内、无需合同或路径扩展时，允许一个纠正 Run（必须新建 Run 并重建 Checkpoint）。**执行期间不得修订本卡**；需要修订本卡即属于硬停止。

以下任一情况立即保留现场、停止并报告：

- 基线 HEAD、runtime 身份、Decision 字节或 owned paths 不一致，或需要第 6 条路径；
- 需要改任何 QML 文件、CLI、SDK、`PmFacadeService`、`PmClosureService`、收尾/变更单代码或 `ContinuityStore` 才能实现；
- 只能通过 Mock 业务结果/质量门/收尾、硬编码 `verified=True`/`COMPLETED`、跳过测试、放宽断言、文件级抑制或手改数据库才能通过；
- 测试会启动真实的 codex，或需要联网/真实外部工具；
- 需要 `os.chdir` 或其它进程级全局状态才能让测试通过；
- 令牌出现在 `execution_leases.lease_token` 以外的任何持久化对象、日志、信号文本、异常文本或返回值中；
- 既有 Bridge/QML 测试出现除 §6 G6 登记之外的断言改动需求；
- 本卡路径内的测试出现可复现的 Qt 崩溃（按 G2 流程仍无法通过）；`tests/core`、`tests/change` 内出现无法归因于 E-G1-1 的失败，同样停止；
- Run 租约已过期（说明续租循环失效）：停止并报告，不得自行走恢复链；
- Checkpoint 不是当前字节，或质量门未完整返回；
- 发现本卡与代码事实矛盾（先停止，由用户裁决是否出新版本，不得自行改卡）。

## 10. 交付物

1. 基线 SHA 与预检事实表（含 G1 修改前的基线数字）；
2. CHG / Decision / Work / Run / Checkpoint ID 与 Approval Receipt；
3. 精确 diff 与 5 个路径的最终 SHA-256；
4. G1～G7 矩阵、原始命令、Exit Code、输出位置，以及 G2 对基线的逐目录对照；
5. G3 九类场景与测试名称的对照表；
6. 不可变提交 SHA 与 Checkpoint 绑定核对；
7. 明确声明：已获规划批准的新任务现在能在驾驶舱里点“确认开始执行”，在后台真实执行并自动验证，成功后出现“确认最终验收”，再经既有验收与收尾到任务关闭；QML 未改；“从新目标到批准”的 GUI 化与崩溃间隙恢复未做；运行时 `1.3.3-a808fa8` 不含 U05～U07D 代码。

## 11. 与其他任务的关系

- **V05｜GUI 双领域联合验收**（依赖 U06、U07、V02、V04）：本卡补齐其“GUI 点开始到验收”的链路；“GUI 输入目标 → 范围卡 → 批准”仍待后续卡。
- **U08｜旧 workflow 接口兼容**：与本卡无路径交集，可并行。
- **故障恢复项（令牌在内存、崩溃间隙）**：登记为已知限制（§5.1-5），由后续恢复类卡处理。
- WBS 对 U05/U06/U07/U07D 的回写与 M2 总审计不在本卡范围。
