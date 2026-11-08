# V05-B｜GUI 双根与生产线程池接线实施卡

> 卡片编号：`CARD-SW008-M2-V05B`
> 对应 WBS：`V05-B`（WBS V3.0.22 §4.8；台账 `TD-SW008-083` 的接线部分）
> 版本：`V1.0`（2026-10-07，一次定稿；执行期间不得修订，见 §9）
> 状态：`PLANNED / NOT_AUTHORIZED`（定稿，待授权；授权方式见 §7；**预批准条件见 §7.1**）
> 档次：产品档（规则文档 §4：全量九组回归、相关静态与场景门禁、严格变异检查）
> 依赖：V05-A（卡 058）已提交并验收收口（CHG-SCPT-2026-384 completed，由启动脚本核验）；WBS V3.0.22 已验收
> 隔离基线：`5a2f9c486b444dd0b8560b7612a0302c0f1d804c`（V05-A 的提交，分支 `codex/m2-v05a-query`）
> 治理任务真源：WBS 提交 `0b56b2f4de2b35effea7e100ab2c56bc1cec0bc7`（V3.0.22）
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 推荐执行模型：`Claude Sonnet 4.6 (Thinking)` 或能力不低于它的模型；实际执行者 `Claude Sonnet 5.5`
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

> V1.0 定稿说明：GPT 只交付了**设计**（`.auto-pm/reports/m2-v05-survey-gpt-20261006/DESIGN_NOTES.md` §2、§4 的 V05-B 行）；本卡的 6 个文件全部由我写成，并在全新基线副本上跑过（§1.5）。设计里 V05-B 还有两项**本卡没有做**（如实）：（一）让 GUI 消费 V05-A 的共用查询并显示“挂起与插队不支持”——那要改合同或 QML 视图，超出 6 个产品文件的上限且不属于“双根接线”这组关键反例，需要另一张小卡；（二）窗口关闭时对引擎、桥与执行线程的有序收尾——现状（窗口模块没有显式收尾）原样保留。参考文件、变异计划与脚本、判卷脚本、安装脚本与演练输出归档于 `.auto-pm/reports/m2-v05b/`，仅供参考；执行者不得现场修订本卡、扩大路径或放宽门禁；遇到本卡未覆盖的情况按 §9 停止并报告。

## 1. 背景与已核实事实（2026-10-07，基线 `5a2f9c48`，均为命令、源码或日志核验）

1. **缺陷（GPT 勘测，我已在源码里核实）**：老板驾驶舱（默认 GUI）从头到尾只收一个根：`gui` 命令只传工作区根，`run_boss_cockpit`、`build_cockpit_bridge`、`PmCockpitService`、`PmCockpitBridge` 都只收一个根并用它建存储、读注册表、建 Facade。从受控的链接候选启动 GUI 时，存储与全部写入落在候选上，被存储的控制根守卫拒绝——所以 V05-C 的真实双领域联验根本跑不起来。命令行的 `pm` 早已正确地用“控制根为主、工作区为执行根”（`PmFacadeService(control_root, execution_root=workspace)`）。
2. **做什么**：让 `PmCockpitService`、`PmCockpitBridge`、生产工厂 `build_cockpit_bridge`/`run_boss_cockpit` 与 `gui` 命令都同时带**控制根**与**执行根**：注册表、存储、事实读取、收尾与全部写入走控制根；执行跑在 GUI 自己的根；生产路径仍默认真实的全局 `QThreadPool`。不带控制根（单根启动）时，行为与改动前完全一致。控制根与候选互换（错映射）时，存储的控制根守卫拒绝，两边都零写入。
3. **明确不做**：GUI 消费 V05-A 的查询并显示能力（见定稿说明）；窗口关闭的有序收尾；QML 视图与 `boss_main.qml`、`contracts/pm_cockpit.py`；Store、resume 收集器、schema；真实双领域联验（V05-C）；任何真实模型调用。
4. **性质**：这些改动不新增任何授权，只让已有的写路径指向正确的根；写守卫（存储的控制根守卫）一字未改。
5. **我在全新基线副本上的演练**（2026-10-07，非受治理执行，受治理执行里完整重跑，不采纳这些输出；输出在 `.auto-pm/reports/m2-v05b/gates_rehearsal/`）：
   ① `ruff check` 与 `mypy --strict` 对 6 个文件零问题、`git diff --check` 通过；
   ② G1：26 passed、1 failed（既存，与基线相同：26 passed、1 failed）；
   ③ 两个新测试文件整体 **10 passed**（10.74s），含真实链接工作树与真实全局线程池；
   ④ **严格变异检查**：12 个变异全部被点名的测试以**真实断言失败**抓住，点名的测试先在未变异字节上为绿，每个文件逐字节还原：
   - M01-control-root-ignored：the service takes the registry, store and writes from the control root
   - M02-store-on-the-candidate：the store lives in the control root
   - M03-facade-without-execution-root：the facade runs against the GUI's own execution root
   - M04-facade-roots-swapped：the facade is governed by the control root, not the candidate
   - M05-relative-paths-from-the-candidate：registry paths are presented relative to the control root
   - M06-bridge-facade-ignores-control-root：the bridge's own facade is dual-root
   - M07-bridge-service-ignores-control-root：the bridge's default service is dual-root
   - M08-factory-drops-the-bridge-control-root：the factory hands the control root to the bridge
   - M09-factory-drops-the-service-control-root：the factory hands the control root to the service
   - M10-gui-command-drops-the-control-root：the gui command hands the control root to the cockpit
   - M11-private-thread-pool：production uses the real global thread pool
   - M12-gui-command-wrong-control-root：the gui command hands the real control root, not the workspace
   ⑤ **回归的一个子集**（与卡 058 的真实门禁输出逐组对照，失败集合相同）：
   - application：174 passed（基线 174）、0 failed、0 skipped（2.95s）
   - plc：144 passed（基线 144）、0 failed、0 skipped（33.81s）
   - change：230 passed（基线 230）、0 failed、0 skipped（3.23s）
   - contracts：210 passed（基线 210）、0 failed、1 skipped（39.98s）
   - infrastructure：68 passed（基线 68）、0 failed、0 skipped（0:02:31）
   - qml_debounce_alone：1 passed（基线 1）、0 failed、0 skipped（1.61s）
   - cli：347 passed（基线 347）、0 failed、1 skipped（0:07:57）
   - qml：288 passed（基线 283，另加新测试 5）、0 failed、0 skipped（0:07:33）
   - core 里与驾驶舱、SDK、门面相关的 6 个文件：204 passed。
   **九组回归的 `core` 与 `rest` 两组没有在演练里整组跑**，受治理执行里全部重跑。
6. **基线数字**（本卡基线与卡 058 提交的代码字节相同，直接沿用卡 058 真实门禁的输出 `.auto-pm/reports/m2-v05a/gates/g2_candidate/`）：既存失败为 core 3 个、rest 15 个、G1 集合 1 个（`test_no_conditional_assertion_skips`）；G1 集合在基线上 **26 passed、1 failed（既存）、0 skipped**。
7. **新增测试**：共 **10** 个（服务级 5 个、生产工厂与 gui 命令 5 个）；两个文件都是新增，没有旧测试被改动；确切的节点清单归档在 `new_nodes.json`，G3 逐个比对。
8. **限度（如实）**：真实全局线程池的测试用无头的 QApplication，证明“快照经真实池取得并在 GUI 线程交付”，**不证明可见的窗口与 QML 交互**；没有跨进程并发场景；这些代码尚未被独立审计（M2 末由 GPT 整体审计）。

## 2. 单一目标（用户故事与完成定义）

作为用户，我希望从受控的链接候选启动老板驾驶舱时，它读写的是受控的主根，而不是被守卫拒绝的候选：

1. 服务从控制根读注册表与存储，候选里不创建任何东西（单根启动时行为不变）；
2. Facade 以控制根为主、候选为执行根；
3. 经双根写入的内容只落在控制根；
4. 控制根与候选互换时被拒绝，两边零写入；
5. 生产工厂把两个根与真实的全局线程池接好，快照经真实池在 GUI 线程交付；
6. GUI 的“输入目标”在双根下落在控制根，互换时被拒绝；
7. `gui` 命令在控制根与工作区不同（链接候选）时把控制根交给驾驶舱；单根时仍是改动前的两参数原样调用（既有 `tests/cli/test_gui.py` 不改、仍绿）；
8. 既有测试全部保留，九组回归与基线逐组一致（失败集合相同、通过数恰为基线加新测试数）。

依据 PM-042、PM-033、DEV-210 与 DEV-300；规范只读。本卡无 UI 视图改动，HTML 原型不适用。

## 3. 实施前预检（只读，先于任何写入）

1. 核验本卡字节 SHA-256 与向用户报告的一致；核验 V05-A（卡 058）的 CHG-SCPT-2026-384 已 completed、分支 `codex/m2-v05a-query` 仍在 `5a2f9c48`。
2. 运行 `main.py implementation-card precheck --card-file` 对本卡，退出码必须为 0。
3. 核验 §4 中 4 个“存在”路径在基线上存在、2 个“计划新增”路径在基线上不存在。
4. 在隔离候选里、安装之前，对 §6 G1 集合复现基线结果（**26 passed、1 failed（既存）、0 skipped**），输出写入 `.auto-pm/reports/m2-v05b/gates/G1_baseline_candidate.txt`；不一致则停止。
5. 核验隔离候选 HEAD 等于基线且工作树干净。
6. 阅读 `.auto-pm/reports/m2-v05b/proto/` 下的参考文件，核对 `reference_manifest.json` 中各文件与工具的 SHA-256。
7. 判卷、检查与变异脚本已在参考字节上跑通（§1.5）；工具字节一旦被证据绑定，任何修正都会使整个窗口重开。后台起长批次用 `nohup`，并确认输出文件真的开始增长。**九组回归的 `core` 组约需 2 小时**，所以 Run 需要续租循环（`p1_renew_loop.sh`，每 1200 秒续一次，带 6 小时上限），提交前租约须剩余 300 秒以上。**回归与变异检查必须顺序执行，不得与其他重负载同时跑**（开工时创建重负载标记 `.auto-pm/reports/HEAVY_GATES_RUNNING`）。

## 4. 精确 Owned Paths（6）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `auto_pm/application/core/pm_cockpit_service.py` | 存在 | 新增 `control_root`：注册表、存储、事实读取、收尾与全部写入走控制根；执行跑在 GUI 自己的根；`_real_facade()` 同时带两个根；不带控制根时行为不变 |
| 2 | `auto_pm/ui/boss_qml_window.py` | 存在 | 生产工厂 `build_cockpit_bridge` 与 `run_boss_cockpit` 新增 `control_root` 并传给服务与桥 |
| 3 | `auto_pm/ui/cli/gui.py` | 存在 | `gui` 命令把全局的控制根交给老板驾驶舱 |
| 4 | `auto_pm/ui/qml/bridges/pm_cockpit_bridge.py` | 存在 | 桥新增 `control_root`，默认服务与自己的 Facade 都带两个根；线程池仍默认真实的全局池 |
| 5 | `tests/core/test_pm_cockpit_dual_root.py` | 计划新增 | 新增：真实链接工作树上的服务级测试 5 个 |
| 6 | `tests/qml/test_pm_cockpit_production_wiring.py` | 计划新增 | 新增：生产工厂、真实全局线程池与 gui 命令的测试 5 个 |

出现第 7 条脏路径即停止，不得现场扩大 Decision。治理证据对象在控制根落账，不计入上述路径；台账、WBS、需求说明本卡不改。

## 5. 合同（全部定稿，执行者不得改写含义）

### 5.1 最终字节

6 个文件的字节固定为参考字节（UTF-8、LF、无字节序标记），归档为 `.auto-pm/reports/m2-v05b/proto/` 下的同相对路径文件；`install_candidate.py` 逐字节核验后装入候选（先确认既存文件等于基线字节、新增文件不存在），不得手工改写。

| # | 路径 | 基线状态 | 最终 SHA-256 |
|---|---|---|---|
| 1 | `auto_pm/application/core/pm_cockpit_service.py` | 存在 | `7685dda56644fe4514f1c3e16e87215cf9b79e53bf0eaf7c09b0cc92e03da722` |
| 2 | `auto_pm/ui/boss_qml_window.py` | 存在 | `87aa971e1c9c7d4bca9c121918cfaba7141161a078f08eabc7e16233681c7cb7` |
| 3 | `auto_pm/ui/cli/gui.py` | 存在 | `216e3b7aba9b8f087e502872c88c105095189e4df54e9e39ed0b74da74ccff28` |
| 4 | `auto_pm/ui/qml/bridges/pm_cockpit_bridge.py` | 存在 | `21a21064a182b5c37f841602f6f1e4eeb05a52718e5c611376b4e95e18074ec5` |
| 5 | `tests/core/test_pm_cockpit_dual_root.py` | 计划新增 | `4858c8b9a081ee1f79bdad3424b82e0c22dce0b445d9b889356aaeccea0fe517` |
| 6 | `tests/qml/test_pm_cockpit_production_wiring.py` | 计划新增 | `ad1d51f7ba12939831b2c89c68b758046310f8a45650e1a0111b75665b97730c` |

检查与构建工具（`reference_manifest.json` 里的 `tools/` 条目，字节固定）：

| 工具 | SHA-256 |
|---|---|
| `commit_msg.template.txt` | `580ee8723325c6dd319a615211250d4b26ef70cc68c35c7e761e02468c3fe264` |
| `g6_check.py` | `ff26933e137d04b7a16c20ec3e91ae0344f5e2f461e1d86ee4608f091aa683ec` |
| `install_candidate.py` | `7dd7391819c94e981361e671e3a2789641917251af6f08ea117b0e7cb64a3d17` |
| `m2-tools/mutation_classify.py` | `0fff21f888cb1a50094f050ef8bc3b42ea25653ba508581e3c85fa1b28d79019` |
| `m2-tools/verdict_check.py` | `0fcbd53020b909b123f3819dcf0774d1f8d93dbc4354dcc5f3c1f72dd56f2188` |
| `mutation_plan.json` | `7a1a2672c27d9af358396d185afd280f6d4d7bae5e5dbc21627387216785b7c5` |
| `mutation_run.py` | `383fac9fe515d75761bac9a35bc5c208b9e2724ee87c0a365f28e250d6da819c` |
| `new_nodes.json` | `c9ca7c32d8ee0b000e47d11650097826696699a33a4f3036006f2336497c937c` |
| `run_g2.sh` | `6956748a33added47bde7bca81e837230d6e461e746f48da7a0770499cd578fc` |
| `run_gates_fast.sh` | `5a590fa9414ff9c313760956ef78df6509cc6ca49ae89f95b91d0daeb52cd519` |
| `run_gates_g2.sh` | `c3070eaed6e2116ed94ef44f8a800d85414025e4ba4ff3e67fa45d07219cba0c` |
| `run_gates_v05b.py` | `c04f563b2b8e789c6ec83f0937f0a8812e19b6b3c84d080e0fc2404bdb71e787` |

### 5.2 行为合同

**5.2.1 `PmCockpitService`**：新增关键字参数 `control_root`（默认空）。工作区根（GUI 启动所在的根）保持为执行根；控制根缺省等于工作区根。注册表路径（相对路径时）、`ContinuityStore`、`PmClosureService` 与路径相对化都以控制根为准；新增 `_real_facade()`：`PmFacadeService(控制根, execution_root=工作区根)`，原来直接用工作区根构造 Facade 的五处都改用它（原来优先使用注入的 Facade 的地方仍然优先使用注入的）。不带控制根时与改动前完全一致。

**5.2.2 `PmCockpitBridge`**：新增关键字参数 `control_root`；默认服务按控制根构造，自己的 Facade 在给出控制根时按“控制根为主、工作区为执行根”构造，否则与改动前一致；线程池仍默认 `QThreadPool.globalInstance()`。

**5.2.3 生产工厂与命令**：`build_cockpit_bridge(workspace_root, config=None, *, control_root=None)` 与 `run_boss_cockpit(workspace_root, debug=False, *, control_root=None)` 把控制根传给服务与桥；`gui` 命令在应用上下文里的控制根与工作区不同时把它传给老板驾驶舱，相同（单根）时保持改动前的 `_run_boss_cockpit(workspace, debug)` 原样调用（专业工作台路径不变）。

**5.2.4 零写拒绝**：本卡不改任何写守卫；控制根与候选互换时，由存储既有的控制根守卫拒绝，测试证明两边的存储文件在拒绝前后字节不变。

### 5.3 必测场景（G3）

新增的 10 个测试：

| 测试 | 要证明的行为 | 个数 |
|---|---|---|
| `test_the_service_reads_the_registry_and_the_store_of_the_control_root_and_creates_nothing_in_the_candidate` | 在真实链接工作树上，服务读控制根的注册表与存储，候选里不创建任何东西 | 1 |
| `test_without_a_control_root_the_service_behaves_exactly_as_before` | 不带控制根时，服务与改动前的单根行为一致 | 1 |
| `test_the_real_facade_is_built_on_the_control_root_with_the_candidate_as_execution_root` | Facade 以控制根为主、候选为执行根 | 1 |
| `test_a_write_through_the_dual_root_facade_lands_in_the_control_root_only` | 经双根 Facade 写入的草稿只落在控制根 | 1 |
| `test_swapped_roots_are_refused_and_nothing_is_written_anywhere` | 控制根与候选互换时被拒绝，两边都零写入 | 1 |
| `test_the_production_factory_wires_both_roots_and_the_global_thread_pool` | 生产工厂把两个根与真实的全局线程池接好 | 1 |
| `test_a_snapshot_through_the_real_global_pool_is_delivered_on_the_gui_thread` | 快照经真实全局线程池取得，并在 GUI 线程交付，不写任何东西 | 1 |
| `test_the_gui_goal_input_lands_in_the_control_root_and_swapped_roots_write_nothing` | GUI 的“输入目标”落在控制根；互换映射被拒绝且零写入 | 1 |
| `test_the_gui_command_hands_the_control_root_to_the_cockpit` | `gui` 命令在控制根与工作区不同时把控制根交给驾驶舱；单根时仍是改动前的原样调用 | 2 |

### 5.4 明确不做

见 §1.3。另：不改既有测试的任何字节（两个测试文件都是新增）；不用 `--no-verify`；不改 `.git/hooks` 下的真实钩子；不合并、不推送、不部署、不切换 release。

## 6. 门禁矩阵

门禁在隔离候选的最终字节上运行（快速部分 `run_gates_fast.sh`，九组回归 `run_gates_g2.sh`，判卷 `run_gates_v05b.py`，均只读，判卷在任一门禁不过时以非零退出；变异检查会逐个改动并逐字节还原候选文件，所以排在其他快速门禁之后、九组回归之前单独跑，脚本已按此顺序编排）。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 夹具健康与冒烟 | `tests/test_fixture_health.py`、`tests/test_smoke.py`、`tests/test_import.py` | 候选与安装前的基线完全相同：26 passed、唯一失败是既存的 `test_no_conditional_assertion_skips`、0 skipped |
| G2 九组回归 | 十个输出逐组对照卡 058 的真实门禁输出 | 失败集合与基线逐个相同；通过数恰为基线加本卡新增（`core` +5、`qml` +5，其余 +0）；跳过数与基线相同；退出码与基线相同；无报错节点 |
| G3 必测场景 | 两个新测试文件的收集结果 | 恰为 `new_nodes.json` 的 10 个节点 |
| G4 静态质量 | 对 6 个 Python 文件运行 `ruff check --no-cache` 与 `mypy --strict --no-incremental`；`git diff --check`；字节扫描 | 全部退出码 0；字节扫描零发现；新增行（含两个新增文件的全部行）中没有 `type: ignore`、`noqa`、`follow-imports=skip`、`pylint: disable` |
| G5 范围与最终字节 | 变更集与指纹 | 变更集恰为 §4 的 6 个路径；6 个文件的 SHA-256 等于 §5.1；无缓存与临时文件残留；门禁前后字节记录相同 |
| G6 既有内容不变 | `g6_check.py` 对照由基线提交导出的目录树 | `templates` 字节不变；`auto_pm` 与基线的差异恰为 4 个既有产品文件；`tests` 与基线的差异恰为 2 个新增测试文件 |
| G7 不触碰生产 | 新增测试行扫描、真实钩子记录与残留进程检查 | 新增的测试行不含对真实控制根（`My_Workspace`）的引用；真实 `.git/hooks` 下的文件在全部门禁前后字节相同；门禁前后 pytest 相关的 Python 进程数相同 |
| G8 负向对照 | `mutation_run.py`（计划 `mutation_plan.json` 的 12 个变异，判据 `m2-tools/mutation_classify.py`） | 计划的 SHA-256 等于指纹清单；点名的测试组先在未变异字节上全绿；每个变异让点名的测试出现真实断言失败；每个文件逐字节还原；6 个文件前后与冻结字节相同 |
| G9 两个新测试文件整体 | `tests/core/test_pm_cockpit_dual_root.py`、`tests/qml/test_pm_cockpit_production_wiring.py` | **10 passed、0 failed、0 skipped**，退出码为 0 |

**提交与收尾**（由提交脚本执行）：创建当前字节 Checkpoint 后走正常 Hook 提交（不得 `--no-verify`）；提交内 blob 与 Checkpoint 逐一相同；`main.py ledger reconcile SW-2026-008` 为 0/0/0。

## 7. 实施授权签字门

### 7.1 当前签字状态

| 字段 | 当前值 |
|---|---|
| 卡片 | `CARD-SW008-M2-V05B V1.0` |
| 实施批准 | `PRE_AUTHORIZED_CONDITIONALLY`：用户 2026-10-06 的有条件预批准（原话见 `.auto-pm/reports/PREAUTH_V05_20261006.txt`）——前提是本卡最终 SHA 已在聊天中向用户报告、卡字节与该 SHA 一致、机器预检通过、范围不超出 §4 的路径；任一门禁不过即停下保留现场并等用户，不得重跑到绿 |
| 最终验收 | `PENDING`（**不在委托内**：V05-B 的验收与 CHG 收口由用户本人做出） |
| 审批人 | `fubai / baiyang`（同一用户、等权署名） |
| 隔离基线 | `5a2f9c486b444dd0b8560b7612a0302c0f1d804c` |
| Owned Paths | §4 的 6 个路径 |
| 执行模型 | `Claude Sonnet 5.5` |
| 明确禁止 | 第 7 条路径、改 §4 之外的任何产品文件与既有测试、改 QML 与合同、改 Store 与 resume 收集器、新增存储或 schema、改台账、WBS、既有 CHG、PM_SESSION、Obsidian 规范、Hook 脚本与 release、直接改真实库、历史改写、合并、推送、部署、V05-C 的任何内容与真实模型调用 |

### 7.2 授权成立与失效

1. 卡片字节、隔离基线、owned paths、执行模型或禁止事项任一漂移，预批准立即失效。
2. 外部 Approval Receipt 绑定本卡完整字节 SHA-256、基线、6 个路径、6 个最终文件 SHA-256、允许与禁止的动作、执行模型、审批人与时间；卡片自身不含自身 SHA-256。
3. 实施批准与最终验收分离；执行 Agent 不得自签验收。
4. V05-A 未验收收口前，本卡不得开工（由启动脚本核验）。

## 8. 治理执行顺序

1. 只读预检并输出事实表（§3），含安装前的 G1 基线。
2. 创建并批准 SW-2026-008 的独立 CHG（领域 SCPT，性质 OPT）与精确 Decision（§4 六路径；`DEC-<起卡当天日期>-V05BDUAL`）。
3. 创建 Work（`--card-file` 指向本卡；`WORK-SW008-M2-V05B-001`）、在全新隔离候选（自 `5a2f9c48` 起，分支 `codex/m2-v05b-dual-root`，工作树 `.auto-pm/worktrees/m2-v05b`）启动 Run（`RUN-SW008-M2-V05B-001`，`--lease-seconds` 不超过 3600）；启动续租循环；全部门禁约 3 小时。
4. 装入参考字节、运行 §6 门禁；判卷结果写入 `.auto-pm/reports/m2-v05b/gates/`。
5. 创建当前字节 Checkpoint（`git_head` 为基线，记录 6 个文件的 SHA-256 与判卷文件 SHA-256），**先于提交**；随后走正常 Hook 提交；提交后核验提交内 blob 与 Checkpoint 相同，否则停止。
6. Run/Work 终态、`main.py ledger reconcile SW-2026-008` 为 0/0/0；**CHG 收口由用户本人做出**。
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
7. 明确声明：老板驾驶舱可以从受控的链接候选启动并读写控制根；互换映射零写拒绝；生产路径用真实的全局线程池；单根启动行为不变。**已知限制必须如实报告**：GUI 还没有消费 V05-A 的查询、没有显示“挂起与插队不支持”；窗口关闭的有序收尾没做；全局线程池的测试用无头 QApplication，不证明可见窗口；没有跨进程并发场景；这些代码尚未被独立审计；真实双领域联验仍是 V05-C。

## 11. 与其他任务的关系与需要用户知悉的决策点

- 之后是 V05-C（真实双领域 GUI 联验；调用真实模型前须先获你的授权）；GUI 消费共用查询的显示需要另一张小卡，建议在 V05-C 之前做。
- **需要你知悉的点**：
  ① **只接线、不改守卫**：互换映射的零写拒绝靠存储既有的守卫，测试证明它确实在双根下生效；
  ② **GUI 现在仍不显示“挂起与插队不支持”**，这是设计里 V05-B 的一部分，我这次没做（要改合同或 QML，超出上限），需要另一张小卡；
  ③ **窗口关闭的有序收尾没做**；
  ④ **产品档**，九组回归全跑，约 3 小时；
  ⑤ **代码全部由我写、尚未被独立审计**：M2 全部做完后由 GPT 整体只读审计。
