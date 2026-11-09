# V05-B2｜驾驶舱的能力提示与有序关闭实施卡

> 卡片编号：`CARD-SW008-M2-V05B2`
> 对应 WBS：`V05-B`（WBS V3.0.22 §4.8）的余项，即 V05-B 卡 059 里明确“没做”的两项；台账 `TD-SW008-083` 的接线与生命周期部分
> 版本：`V1.1`（2026-10-07，一次定稿；执行期间不得修订，见 §9）
> 状态：`PLANNED / NOT_AUTHORIZED`（定稿，待授权；授权方式见 §7；**没有任何预批准在生效**）
> 档次：产品档（规则文档 §4：全量九组回归、相关静态与场景门禁、严格变异检查）
> 依赖：V05-B（卡 059）已提交并经用户本人验收收口（CHG-SCPT-2026-385 completed，由启动脚本核验）；V05-A 的共用查询已提交
> 隔离基线：`5686bd9f7dd514ca5963f95a0f07ce3f362d86de`（V05-B 的提交，分支 `codex/m2-v05b-dual-root`）
> 治理任务真源：WBS 提交 `0b56b2f4de2b35effea7e100ab2c56bc1cec0bc7`（V3.0.22）
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 推荐执行模型：`Claude Sonnet 4.6 (Thinking)` 或能力不低于它的模型；实际执行者 `Claude Sonnet 5.5`
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

> V1.1 定稿说明：GPT 只交付了**设计**（`.auto-pm/reports/m2-v05-survey-gpt-20261006/DESIGN_NOTES.md` §3 第 4 条与 §5 第 6 步的要求：GUI 显示“不支持挂起与插队”、关闭窗口要确定性收尾）；本卡的 6 个文件全部由我写成，并在全新基线副本上跑过（§1.5）。**用现有的 `notices` 提示列表显示，所以不改任何 QML 视图与合同**（`BossCockpitView.qml` 早已把 `notices` 逐条展示）。参考文件、变异计划与脚本、判卷脚本、安装脚本与演练输出归档于 `.auto-pm/reports/m2-v05b2/`，仅供参考；执行者不得现场修订本卡、扩大路径或放宽门禁；遇到本卡未覆盖的情况按 §9 停止并报告。

> V1.1 说明：V1.0 的第一次受治理执行（CHG-SCPT-2026-386，Run `RUN-SW008-M2-V05B2-001`）在 G2 失败：`core` 组的 `tests/core/test_pm_run_e2e.py::test_failed_execution_is_reported_without_verification` 里一个 `git hash-object` 子进程超过 30 秒限时（`subprocess.TimeoutExpired`），该路径与本卡 6 个文件无关；其余 G1、G3～G9 全部通过。该次的证据原样保留在 `.auto-pm/reports/m2-v05b2/attempt1/`，Run 已记为 FAILED、Work 为 BLOCKED、CHG-386 保持实施中不动。用户选择重新完整跑一遍受治理执行。**V1.1 与 V1.0 的唯一差别**：第二次运行的编号与名字（Work、Run、Checkpoint 为 -002，Decision 后缀 `V05B2R02`，分支与工作树加 `-r2`）、判卷脚本里的卡版本与 Run 编号，以及因此变化的三个工具指纹（`run_gates_fast.sh`、`run_gates_g2.sh`、`run_gates_v05b2.py`）；6 个文件的字节、变异计划、范围与门禁标准一字未改。

## 1. 背景与已核实事实（2026-10-07，基线 `5686bd9f`，均为命令、源码或日志核验）

1. **缺口一（GUI 没有说明能力）**：V05-A 的共用查询声明“挂起、恢复挂起、插队当前不支持”，但老板驾驶舱的快照从不显示这一点；设计要求 GUI 不生成可点击的假挂起控件，也要把不支持说清。驾驶舱本来就没有挂起或插队的按钮，缺的是一句明说的提示。
2. **缺口二（关闭窗口没有顺序）**：`run_boss_cockpit` 在 `app.exec()` 返回后直接退出——没有停新请求、没有等在跑的后台任务、引擎与桥的删除顺序也没有约束；桥的 `startExecution`（启动任务）与 `createPlanningDraft`（保存目标）两个入口没有“正在关闭”的防护（其余入口有），所以关闭过程中仍可能排入新的启动或写入。
3. **做什么**：
   ① `ContinuityQueryService.capabilities()`：能力声明只在这一处生成，`query()` 与驾驶舱都用它；
   ② 快照末尾加一条提示：声明完整且全部为“不支持”时写“挂起、恢复挂起与插队：当前版本不支持……驾驶舱不提供这些操作，也不会假装挂起”；声明查不到、不完整或抛错时写“能力查询未能确认；这些操作保持停用”（失败关闭）；追加在末尾，不改变既有提示的位置；
   ③ 桥新增“正在关闭”标志：启动、保存目标、快照、刷新、证据五个入口在关闭中都拒绝（测试逐个核实；批准与收尾沿用既有的关闭防护，关闭会先停掉交付开关）；`pending_tasks()` 列出已启动未完成的后台任务；`shutdown(timeout_ms)` 停刷新、有界等待在跑任务、**不动共用线程池**；
   ④ `shutdown_cockpit()`：先 `bridge.shutdown`；有任务超时未完成则**什么都不删**并返回假；否则先删 QML 引擎（它的销毁处理仍要用到桥）再删桥；`run_boss_cockpit` 在事件循环结束后调用，仍有任务在跑时打印说明并以非零（3）退出。
4. **明确不做**：任何取消或强行结束在跑任务（需要 V04-R1 的回收与 fencing 证据，仍是后续）；QML 视图与 `boss_main.qml`、`contracts/pm_cockpit.py`、`gui.py`；Store、resume 收集器、schema；真实双领域联验（V05-C）；任何真实模型调用。
5. **我在全新基线副本上的演练**（2026-10-07，非受治理执行，受治理执行里完整重跑，不采纳这些输出；输出在 `.auto-pm/reports/m2-v05b2/gates_rehearsal/`）：
   ① `ruff check` 与 `mypy --strict` 对 6 个文件零问题、`git diff --check` 通过；
   ② G1：26 passed、1 failed（既存，与基线相同：26 passed、1 failed）；
   ③ 两个新测试文件整体 **10 passed**（12.31s），含真实全局线程池与真实 QML 引擎；
   ④ **严格变异检查**：17 个变异全部被点名的测试以**真实断言失败**抓住，点名的测试先在未变异字节上为绿，每个文件逐字节还原：
   - M01-query-builds-its-own-capabilities：the query block and the cockpit notice come from one capability producer
   - M02-notice-not-appended：the snapshot carries the capability notice
   - M03-notice-always-unverified：a confirmed declaration is reported as not supported
   - M04-notice-ignores-the-declared-actions：an incomplete declaration fails closed
   - M05-notice-lets-a-raising-producer-through：a producer that raises fails closed instead of breaking the snapshot
   - M06-notice-first：the capability notice follows the other notices
   - M07-start-ignores-closing：no new start is queued while the cockpit closes
   - M08-draft-ignores-closing：no goal input is saved while the cockpit closes
   - M09-refresh-restarts-while-closing：the periodic refresh cannot be restarted while closing
   - M10-shutdown-does-not-wait：shutdown waits, bounded, for the tasks already running
   - M11-pending-ignores-the-snapshot-worker：the running snapshot task counts as pending
   - M12-shutdown-leaves-delivery-on：shutdown stops the refresh and suppresses late results
   - M13-teardown-deletes-the-bridge-first：the QML engine is deleted while the bridge is still alive
   - M14-teardown-ignores-a-running-task：a task that is still running keeps the engine and the bridge
   - M15-entry-point-skips-the-teardown：the window entry point tears the cockpit down after the event loop
   - M16-entry-point-hides-the-pending-task：the entry point reports a task that is still running with a non-zero exit
   - M17-closing-flag-never-set：shutdown marks the bridge as closing
   ⑤ **回归的一个子集**（与卡 059 的真实门禁输出逐组对照，失败集合相同）：
   - application：174 passed（基线 174）、0 failed、0 skipped（3.44s）
   - plc：144 passed（基线 144）、0 failed、0 skipped（41.40s）
   - change：230 passed（基线 230）、0 failed、0 skipped（3.61s）
   - contracts：210 passed（基线 210）、0 failed、1 skipped（41.25s）
   - infrastructure：68 passed（基线 68）、0 failed、0 skipped（0:02:51）
   - qml_debounce_alone：1 passed（基线 1）、0 failed、0 skipped（1.53s）
   - cli：347 passed（基线 347）、0 failed、1 skipped（0:09:54）
   - qml：293 passed（基线 288，另加新测试 5）、0 failed、0 skipped（0:08:25）
   - core 里与驾驶舱、SDK、门面、共用查询相关的 7 个文件：221 passed。
   **九组回归的 `core` 与 `rest` 两组没有在演练里整组跑**，受治理执行里全部重跑。
6. **基线数字**（本卡基线与卡 059 提交的代码字节相同，直接沿用卡 059 真实门禁的输出 `.auto-pm/reports/m2-v05b/gates/g2_candidate/`）：既存失败为 core 3 个、rest 15 个、G1 集合 1 个（`test_no_conditional_assertion_skips`）；G1 集合在基线上 **26 passed、1 failed（既存）、0 skipped**。
7. **新增测试**：共 **10** 个（能力提示 5 个、有序关闭 5 个）；两个文件都是新增，没有旧测试被改动；确切的节点清单归档在 `new_nodes.json`，G3 逐个比对。快照多一条提示不会弄坏既有测试：既有断言只看提示的第一条或“其中包含”。
8. **限度（如实）**：有序关闭的测试用无头的 QApplication 与真实 QML 引擎，证明“删除顺序正确且没有 QML 报错”，**不证明可见窗口里的交互**；有任务在跑时只**等待、不取消**——等待超过 60 秒后入口保留现场并以非零退出，在跑的任务仍在后台（真正的取消要等 V04-R1）；这些代码尚未被独立审计（M2 末由 GPT 整体审计）。

## 2. 单一目标（用户故事与完成定义）

作为用户，我希望老板驾驶舱明说“挂起与插队当前不支持”，并且关闭窗口时有序收尾、不丢在跑的任务：

1. 快照最后一条提示说明挂起、恢复挂起与插队不支持（失败关闭：查不到就说未能确认并保持停用）；
2. 提示与共用查询取自同一个能力生产者；生产者抛错时快照不崩；
3. 关闭中，启动、保存目标、快照、刷新、证据五个入口都拒绝新请求（批准与收尾沿用既有的关闭防护）；
4. 关闭会有界等待真实线程池里在跑的任务，不碰共用线程池，迟到的结果不再交付；
5. 窗口入口在事件循环结束后：先停新请求并等任务、再删 QML 引擎、最后删桥，且没有 QML 报错；
6. 仍有任务在跑时，引擎与桥都保留，入口打印说明并以非零退出；
7. 既有测试全部保留，九组回归与基线逐组一致（失败集合相同、通过数恰为基线加新测试数）。

依据 PM-042、PM-033、DEV-210 与 DEV-300；规范只读。本卡无 UI 视图改动，HTML 原型不适用。

## 3. 实施前预检（只读，先于任何写入）

1. 核验本卡字节 SHA-256 与向用户报告的一致；核验 V05-B（卡 059）的 CHG-SCPT-2026-385 已 completed、分支 `codex/m2-v05b-dual-root` 仍在 `5686bd9f`。
2. 运行 `main.py implementation-card precheck --card-file` 对本卡，退出码必须为 0。
3. 核验 §4 中 4 个“存在”路径在基线上存在、2 个“计划新增”路径在基线上不存在。
4. 在隔离候选里、安装之前，对 §6 G1 集合复现基线结果（**26 passed、1 failed（既存）、0 skipped**），输出写入 `.auto-pm/reports/m2-v05b2/gates/G1_baseline_candidate.txt`；不一致则停止。
5. 核验隔离候选 HEAD 等于基线且工作树干净。
6. 阅读 `.auto-pm/reports/m2-v05b2/proto/` 下的参考文件，核对 `reference_manifest.json` 中各文件与工具的 SHA-256。
7. 判卷、检查与变异脚本已在参考字节上跑通（§1.5）；工具字节一旦被证据绑定，任何修正都会使整个窗口重开。后台起长批次用 `nohup`，并确认输出文件真的开始增长。**九组回归的 `core` 组约需 2 小时**，所以 Run 需要续租循环（`p1_renew_loop.sh`，**必须从仓库根、用 `.auto-pm/reports/...` 开头的路径启动**，每 1200 秒续一次，带 6 小时上限），提交前租约须剩余 300 秒以上。**回归与变异检查必须顺序执行，不得与其他重负载同时跑**（开工时创建重负载标记 `.auto-pm/reports/HEAVY_GATES_RUNNING`）。

## 4. 精确 Owned Paths（6）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `auto_pm/application/core/continuity_query_service.py` | 存在 | 新增公开的 `capabilities()`：能力声明（挂起、恢复挂起、插队均不支持）只在这一处生成；`query()` 改用它 |
| 2 | `auto_pm/application/core/pm_cockpit_service.py` | 存在 | 快照末尾多一条能力提示，内容取自共用的能力生产者；声明查不到或不完整就失败关闭（“未能确认，保持停用”） |
| 3 | `auto_pm/ui/boss_qml_window.py` | 存在 | 新增 `shutdown_cockpit()`：先停新请求并等在跑任务，再删 QML 引擎（此时桥还活着），最后删桥；`run_boss_cockpit` 在事件循环结束后调用它，仍有任务在跑时保留现场、说明并以非零退出 |
| 4 | `auto_pm/ui/qml/bridges/pm_cockpit_bridge.py` | 存在 | 新增“正在关闭”标志（启动与输入目标两个入口原来没有这道关）、`pending_tasks()` 与有界等待的 `shutdown()`；不碰共用线程池 |
| 5 | `tests/core/test_pm_cockpit_capability_notice.py` | 计划新增 | 新增：能力提示与其失败关闭、单一生产者的测试 5 个 |
| 6 | `tests/qml/test_pm_cockpit_shutdown.py` | 计划新增 | 新增：有序关闭的测试 5 个（真实全局线程池、真实 QML 引擎） |

出现第 7 条脏路径即停止，不得现场扩大 Decision。治理证据对象在控制根落账，不计入上述路径；台账、WBS、需求说明本卡不改。

## 5. 合同（全部定稿，执行者不得改写含义）

### 5.1 最终字节

6 个文件的字节固定为参考字节（UTF-8、LF、无字节序标记），归档为 `.auto-pm/reports/m2-v05b2/proto/` 下的同相对路径文件；`install_candidate.py` 逐字节核验后装入候选（先确认既存文件等于基线字节、新增文件不存在），不得手工改写。

| # | 路径 | 基线状态 | 最终 SHA-256 |
|---|---|---|---|
| 1 | `auto_pm/application/core/continuity_query_service.py` | 存在 | `72e705972863258416cd18b164037548b5604b4b259e8cc4215e3afc71b84460` |
| 2 | `auto_pm/application/core/pm_cockpit_service.py` | 存在 | `0695a24b06612a89a89612dcaf924b881dc6a02a5603bcb0c7c485611225433a` |
| 3 | `auto_pm/ui/boss_qml_window.py` | 存在 | `33cb04c75be40f5098e094efec99d986709153d618d5b8e4fc9fd1aa9602bed6` |
| 4 | `auto_pm/ui/qml/bridges/pm_cockpit_bridge.py` | 存在 | `573b44bef550af20378dece94b1d123030f425102a549f76aaffc076177dd61a` |
| 5 | `tests/core/test_pm_cockpit_capability_notice.py` | 计划新增 | `ad51a3109c2d64a98213a095b358bb65672a5480d4db898aa9bb2fb7c57ce1e8` |
| 6 | `tests/qml/test_pm_cockpit_shutdown.py` | 计划新增 | `ddde66619141e0c6a54a6659d309d35e82ee63e9e92f72f51fea497242dd28c5` |

检查与构建工具（`reference_manifest.json` 里的 `tools/` 条目，字节固定）：

| 工具 | SHA-256 |
|---|---|
| `commit_msg.template.txt` | `a23dbf8d5abf89f4d80e98344373d5e4ea666ebc0e89de29ae6e26108923ad28` |
| `g6_check.py` | `888ef9c1ad8b797cf775b0f8497a6fad485025eaf031ee2b5324d82390d57589` |
| `install_candidate.py` | `0cda727afd3198a0b84866c572e71a8499eedbb91f2b279211ef618221550359` |
| `m2-tools/mutation_classify.py` | `0fff21f888cb1a50094f050ef8bc3b42ea25653ba508581e3c85fa1b28d79019` |
| `m2-tools/verdict_check.py` | `0fcbd53020b909b123f3819dcf0774d1f8d93dbc4354dcc5f3c1f72dd56f2188` |
| `mutation_plan.json` | `6911bb7e55ec415a4ad0359d98e870e52385a769a4f90e7e98268880359abbe4` |
| `mutation_run.py` | `4205572c6bb212e587b61df1bf1ae1d91548def053ae138536b7fa908981a551` |
| `new_nodes.json` | `6408c49375390139f1ce2622adb1140ac4c8a38975a5314e85614410ad167aac` |
| `run_g2.sh` | `6956748a33added47bde7bca81e837230d6e461e746f48da7a0770499cd578fc` |
| `run_gates_fast.sh` | `f36e409d184a1850ea7c117631f8058cf34c15175285765642fe2410bbd30500` |
| `run_gates_g2.sh` | `75ff415ef0a2fef44438f6e72b348702c10026d26377e027e89faa7e0eb3d2f2` |
| `run_gates_v05b2.py` | `ef4f4e8457b045bcf7a6ec331fd7de97191590444d29ef42b8d42548ab2e16c4` |

### 5.2 行为合同

**5.2.1 能力提示**：`ContinuityQueryService.capabilities()`（静态方法）返回 `RuntimeCapabilities`，三个动作（PARK、RESUME_PARKED、PREEMPT）均为 UNSUPPORTED、两个总开关为假；`query()` 用它构造查询块，内容与改动前逐字节一致。`PmCockpitService.snapshot()` 在末尾追加一条提示：声明完整（恰好这三个动作、都为 UNSUPPORTED、两个开关为假）时为“挂起、恢复挂起与插队：当前版本不支持（能力查询 runtime-capabilities.v1）；驾驶舱不提供这些操作，也不会假装挂起。”；任何偏离、或生产者抛 `TypeError`/`ValueError` 时为“挂起与插队的能力查询未能确认；为安全起见这些操作保持停用，驾驶舱不会假装挂起。”。注册表读取失败的早返回路径不变。

**5.2.2 `PmCockpitBridge`**：新增 `_closing` 标志。`startSnapshotRefresh`、`startExecution`、`createPlanningDraft` 在关闭中拒绝（消息“驾驶舱正在关闭。”，保存目标返回 `success=False`）；其余入口沿用既有的关闭防护。`pending_tasks()` 返回已启动且未完成的后台任务的类名元组（启动、收尾、批准、快照、证据）。`shutdown(timeout_ms=60000)`：置 `_closing`、停刷新与迟到结果的交付，每 20 毫秒检查一次在跑任务；超时返回假，全部完成则停全部计时器并返回真；**不调用线程池的任何清理或等待**。

**5.2.3 `shutdown_cockpit(engine, bridge, timeout_ms=60000)`**：`bridge.shutdown` 为假则返回假且不删任何对象；否则 `engine.deleteLater()` 并投递延迟删除事件，再对桥同样处理，返回真。`run_boss_cockpit` 在 `app.exec()` 返回后调用它；返回假时向标准错误打印“仍有后台任务未完成，已保留现场、没有强行结束（真正的取消要等运行回收能力 V04-R1）。”，退出码为事件循环的退出码，若为 0 则为 3。

**5.2.4 零写入**：能力提示与关闭都不写任何文件；本卡不改任何写守卫。

### 5.3 必测场景（G3）

新增的 10 个测试：

| 测试 | 要证明的行为 | 个数 |
|---|---|---|
| `test_the_snapshot_says_parking_and_preemption_are_not_supported` | 快照最后一条提示说明挂起与插队不支持，且不是“未能确认” | 1 |
| `test_the_notice_follows_the_shared_producer_and_fails_closed` | 共用生产者给出不完整的声明时，提示改为“未能确认、保持停用” | 1 |
| `test_a_producer_that_raises_also_fails_closed` | 生产者抛错时快照不崩，提示同样失败关闭 | 1 |
| `test_the_query_block_is_built_from_the_same_producer` | 查询块里的能力与驾驶舱用的是同一个生产者 | 1 |
| `test_the_notice_follows_the_other_notices_and_creates_nothing` | 提示排在其他提示之后，且不创建任何文件 | 1 |
| `test_shutdown_refuses_new_work_waits_for_the_running_worker_and_leaves_the_pool_alone` | 关闭时拒绝五个入口的新请求、有界等待真实池里在跑的任务、不碰共用线程池、迟到的结果不再交付 | 1 |
| `test_the_window_closes_in_order_without_qml_errors` | 真实 QML 引擎先于桥被删除，且没有 QML 报错 | 1 |
| `test_a_worker_that_will_not_finish_keeps_the_engine_and_the_bridge` | 任务不结束时引擎与桥都保留，结束后才按序删除 | 1 |
| `test_the_window_entry_point_tears_the_cockpit_down_after_the_event_loop` | 窗口入口在事件循环结束后把驾驶舱拆干净 | 1 |
| `test_the_window_entry_point_reports_a_task_that_is_still_running` | 仍有任务在跑时入口以非零退出、打印说明并保留现场 | 1 |

### 5.4 明确不做

见 §1.4。另：不改既有测试的任何字节（两个测试文件都是新增）；不用 `--no-verify`；不改 `.git/hooks` 下的真实钩子；不合并、不推送、不部署、不切换 release。

## 6. 门禁矩阵

门禁在隔离候选的最终字节上运行（快速部分 `run_gates_fast.sh`，九组回归 `run_gates_g2.sh`，判卷 `run_gates_v05b2.py`，均只读，判卷在任一门禁不过时以非零退出；变异检查会逐个改动并逐字节还原候选文件，所以排在其他快速门禁之后、九组回归之前单独跑，脚本已按此顺序编排）。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 夹具健康与冒烟 | `tests/test_fixture_health.py`、`tests/test_smoke.py`、`tests/test_import.py` | 候选与安装前的基线完全相同：26 passed、唯一失败是既存的 `test_no_conditional_assertion_skips`、0 skipped |
| G2 九组回归 | 十个输出逐组对照卡 059 的真实门禁输出 | 失败集合与基线逐个相同；通过数恰为基线加本卡新增（`core` +5、`qml` +5，其余 +0）；跳过数与基线相同；退出码与基线相同；无报错节点 |
| G3 必测场景 | 两个新测试文件的收集结果 | 恰为 `new_nodes.json` 的 10 个节点 |
| G4 静态质量 | 对 6 个 Python 文件运行 `ruff check --no-cache` 与 `mypy --strict --no-incremental`；`git diff --check`；字节扫描 | 全部退出码 0；字节扫描零发现；新增行（含两个新增文件的全部行）中没有 `type: ignore`、`noqa`、`follow-imports=skip`、`pylint: disable` |
| G5 范围与最终字节 | 变更集与指纹 | 变更集恰为 §4 的 6 个路径；6 个文件的 SHA-256 等于 §5.1；无缓存与临时文件残留；门禁前后字节记录相同 |
| G6 既有内容不变 | `g6_check.py` 对照由基线提交导出的目录树 | `templates` 字节不变；`auto_pm` 与基线的差异恰为 4 个既有产品文件；`tests` 与基线的差异恰为 2 个新增测试文件 |
| G7 不触碰生产 | 新增测试行扫描、真实钩子记录与残留进程检查 | 新增的测试行不含对真实控制根（`My_Workspace`）的引用；真实 `.git/hooks` 下的文件在全部门禁前后字节相同；门禁前后 pytest 相关的 Python 进程数相同 |
| G8 负向对照 | `mutation_run.py`（计划 `mutation_plan.json` 的 17 个变异，判据 `m2-tools/mutation_classify.py`） | 计划的 SHA-256 等于指纹清单；点名的测试组先在未变异字节上全绿；每个变异让点名的测试出现真实断言失败；每个文件逐字节还原；6 个文件前后与冻结字节相同 |
| G9 两个新测试文件整体 | `tests/core/test_pm_cockpit_capability_notice.py`、`tests/qml/test_pm_cockpit_shutdown.py` | **10 passed、0 failed、0 skipped**，退出码为 0 |

**提交与收尾**（由提交脚本执行）：创建当前字节 Checkpoint 后走正常 Hook 提交（不得 `--no-verify`）；提交内 blob 与 Checkpoint 逐一相同；`main.py ledger reconcile SW-2026-008` 为 0/0/0。

## 7. 实施授权签字门

### 7.1 当前签字状态

| 字段 | 当前值 |
|---|---|
| 卡片 | `CARD-SW008-M2-V05B2 V1.1` |
| 实施批准 | `PENDING`：待用户在对话中明确回复“批准”；回复前我会先在聊天里报出本卡最终 SHA-256 与摘要；**没有任何预批准在生效**（V05-A/B 的预批准已用完；用户已选择“重新完整跑一遍”，但 V1.1 的字节是新的，仍须对这一版回复批准） |
| 最终验收 | `PENDING`（由用户做出；CHG 收口须经用户确认） |
| 审批人 | `fubai / baiyang`（同一用户、等权署名） |
| 隔离基线 | `5686bd9f7dd514ca5963f95a0f07ce3f362d86de` |
| Owned Paths | §4 的 6 个路径 |
| 执行模型 | `Claude Sonnet 5.5` |
| 明确禁止 | 第 7 条路径、改 §4 之外的任何产品文件与既有测试、改 QML 与合同、改 `gui.py`、改 Store 与 resume 收集器、新增存储或 schema、改台账、WBS、既有 CHG、PM_SESSION、Obsidian 规范、Hook 脚本与 release、直接改真实库、历史改写、合并、推送、部署、取消或强行结束在跑任务、V05-C 的任何内容与真实模型调用 |

### 7.2 授权成立与失效

1. 卡片字节、隔离基线、owned paths、执行模型或禁止事项任一漂移，批准立即失效。
2. 外部 Approval Receipt 绑定本卡完整字节 SHA-256、基线、6 个路径、6 个最终文件 SHA-256、允许与禁止的动作、执行模型、审批人与时间；卡片自身不含自身 SHA-256。
3. 实施批准与最终验收分离；执行 Agent 不得自签验收。
4. V05-B 未验收收口前，本卡不得开工（由启动脚本核验）。

## 8. 治理执行顺序

1. 只读预检并输出事实表（§3），含安装前的 G1 基线。
2. 创建并批准 SW-2026-008 的独立 CHG（领域 SCPT，性质 OPT）与精确 Decision（§4 六路径；`DEC-<起卡当天日期>-V05B2R02`）。
3. 创建 Work（`--card-file` 指向本卡；`WORK-SW008-M2-V05B2-002`）、在全新隔离候选（自 `5686bd9f` 起，分支 `codex/m2-v05b2-notice-shutdown-r2`，工作树 `.auto-pm/worktrees/m2-v05b2-r2`）启动 Run（`RUN-SW008-M2-V05B2-002`，`--lease-seconds` 不超过 3600）；启动续租循环；全部门禁约 3 小时。
4. 装入参考字节、运行 §6 门禁；判卷结果写入 `.auto-pm/reports/m2-v05b2/gates/`。
5. 创建当前字节 Checkpoint（`git_head` 为基线，记录 6 个文件的 SHA-256 与判卷文件 SHA-256），**先于提交**；随后走正常 Hook 提交；提交后核验提交内 blob 与 Checkpoint 相同，否则停止。
6. Run/Work 终态、`main.py ledger reconcile SW-2026-008` 为 0/0/0；**CHG 收口须经用户确认**。
7. 向用户报告后停止；SHA 与 ID 写入交接文档。

## 9. 有界纠正与硬停止条件

本卡单提交，一个主 Run；**执行期间不得修订本卡**；需要修订本卡即属于硬停止。任何门禁失败都不得靠重跑、改字节或放宽判据达成通过：保留现场与输出、停止并报告，由用户裁决。

以下任一情况立即保留现场、停止并报告：

- 基线 HEAD、runtime 身份、Decision 字节或 owned paths 不一致，或需要第 7 条路径；
- 需要改 §4 之外的产品文件、既有测试、WBS、既有 CHG 才能让测试通过；
- 只能通过 Mock 业务结果、硬编码预期输出、跳过测试、放宽断言或抑制才能通过；
- 任一门禁不通过，或 G8 的任一变异存活、任一还原字节不一致；G7 发现测试结束后仍有遗留进程；
- 真实 `.git/hooks` 的文件前后字节不同；
- Checkpoint 不是当前字节，或质量门未完整返回；
- Run 租约已过期：停止并报告，不得自行走恢复链；
- 发现本卡与事实矛盾（先停止，由用户裁决是否出新版本，不得自行改卡）。

## 10. 交付物

1. 基线 SHA 与预检事实表（含安装前的 G1 基线）；
2. CHG / Decision / Work / Run / Checkpoint ID 与 Approval Receipt；
3. 精确 diff 与 6 个路径的最终 SHA-256；
4. G1～G9 矩阵、原始命令、Exit Code、输出位置；
5. G3 场景与测试名称的对照表；
6. 不可变提交 SHA 与 Checkpoint 绑定核对；
7. 明确声明：驾驶舱现在明说“挂起与插队当前不支持”（失败关闭）；关闭窗口时先停新请求、等在跑的任务、再按序删除引擎与桥；仍有任务在跑时保留现场并以非零退出。**已知限制必须如实报告**：只等待、不取消在跑任务（取消要等 V04-R1）；有序关闭的测试用无头 QApplication，不证明可见窗口里的交互；这些代码尚未被独立审计；真实双领域联验仍是 V05-C。

## 11. 与其他任务的关系与需要用户知悉的决策点

- 之后是 V05-C（真实双领域 GUI 联验；调用真实模型前须先获你的授权）。
- **需要你知悉的点**：
  ① **提示用现有的提示列表显示**，不动 QML，所以窗口里是一行文字，不是新控件；
  ② **只等待、不取消**：关闭时在跑的任务最多等 60 秒，超时就保留现场并以退出码 3 提示，真正的取消要等后续的 V04-R1；
  ③ **启动与保存目标两个入口原来没有关闭防护**，本卡补上了（这是我读源码发现的真缺口）；
  ④ **产品档**，九组回归全跑，约 3 小时；
  ⑤ **代码全部由我写、尚未被独立审计**：M2 全部做完后由 GPT 整体只读审计。
