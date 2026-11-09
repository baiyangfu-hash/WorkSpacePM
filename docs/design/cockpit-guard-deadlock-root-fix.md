> **状态（2026-11-04）**：P0 已在分支 `claude/project-thread-u0qdo3` 实现（变更单 CHG-SCPT-2026-476），P1、P2、P3 未做。
> 代码位置：矩阵 `auto_pm/contracts/interlock_matrix.py`；拒绝类 `auto_pm/contracts/guard_refusal.py`；
> 静态检查 `tests/contract/test_interlock_matrix.py`（基线在 `tests/contract/baselines/`）；
> 出口演练 `tests/e2e/test_exit_drill.py`；只读命令 `continuity recovery plan`；探测器见 `pm orient` 的新冲突码 `LIVE_RUN_UNDER_FINISHED_WORK`。
> 本文件原稿放在项目共享文件夹 plans/，入库时原样带入，未做内容修改（第 1.5 节之后新增的样本、rev 3.1 的五条裁决已在正文里）。

# 驾驶舱护栏死锁根治设计（rev 3，已含审计 559 的 5 条★、4 组建议和增量复核的条件）

起草：云端线程“根治驾驶舱护栏互相死锁”，2026-11-02（MST）。**rev 3（15:00 MST）并入协调者对 559 增量复核的裁决**：哈希入账**加**提交（两者都要，rev 2 写成“提交可选”是错的，已更正）；回退场景的出口是“先修 active 再恢复”；`recovery open` 只豁免“身份冲突拒绝写入”这一道闸；拒绝统一带 guard_id；自动出口链打印提前到 P0；口令联锁入演练。
**rev 3.1（15:05 MST）并入 559 第三轮五条文字项**：①恢复提交推回的做法与三天提醒；②“修 active”标人工步骤；③needs_code_version 不得高于被测候选；④`recovery.require_pin` 开关与封存措辞；⑤guard_id 优先迁出口链、xfail 带 TD 号与翻转期限且只减不增；另写明账本核心路径改动单独 PR、审计逐点核。
**协调者裁决（14:56 MST）已并入**：①批准时哈希入账，取代“HEAD 不得前移”，Decision 仍须入库；②本文件暂放 plans/，P0 的 PR 把它带进仓库 docs/design/；③回退造成的身份不一致必须能被恢复链清除，列入 P0 回归夹具；④口令与出差预授权由用户定，用户答复前设计默认“无口令、无预授权”。对照代码：main c7224288。冻结期内**只出设计，不提交载荷 PR**。
Claude Doc 版（rev 1，含图表式排版）：https://claude.ai/artifact/PJSKkhVp7x1UH5AUCAEzgq ；本文件是 rev 2 的完整版，以本文件为准。
标“实测”的是在沙箱里用真命令跑过的；标“读码”的是读代码得出；标“未核实”的没有跑过，不要当事实用。

## 0. 摘要（给用户的话）

驾驶舱只设计了“自动模式”，没有设计“手动/复位模式”，各道联锁是一道一道加的，从来没拿一张联锁矩阵交叉核对过。像产线：每加一道新安全联锁，就可能把某个复位出口封死。10-29 到 11-02 已经撞了 6 处。

根治办法是三件事一起做，缺一不可：
1. **联锁矩阵写成数据**（命令表、护栏表、异常状态表），“死锁”有机器可判的定义，用自动测试核对；
2. **统一的恢复模式（恢复令）**：像手动钥匙开关，只有用户本人能拧，范围窄、自动复位、每步留痕，收编散落的例外；
3. **发版检查只判候选版自己能控制的事**：切换和回退永远不以账本状态为前置。

第一步（P0）只加表和测试，不改任何拦截。

## 1. 病根与证据

### 1.1 历史上已撞的 6 处

| 日期 | 死锁 | 怎么补的 |
|---|---|---|
| 10-29 | TD-240：租约过期后，续租说“已过期”，回收说“你已是持有者请续租”，下一步为空 | 改提示、换名回收；自救功能待批 |
| 10-31 | TD-256：纯文档卡走到 VERIFYING，验收/收口/搁置全拒 | #407 文档验证档 |
| 10-31 | TD-259：VERIFYING 不能搁置，转 FAILED 后又搁置不了 | #407 |
| 10-31 | TD-260：新工作区无账本库，登记收件箱要先建别的东西 | #407 首次自动建库 |
| 11-02 | B2：run start 禁控制根（#410），而结算过期 Run 必须在控制根 | #496 窄豁免 |
| 11-02 | 发版检查 G3：要求控制根无冲突，但清冲突的修复就在待发的这一版里 | 发版卡具名例外 |

### 1.2 对代码核实的事实

1. **拒绝没有“出口”概念**：全库 2438 处 raise，账本层异常 601 处，都是自由文字，无编号、无“拒了之后做什么”的登记。（读码+AST 计数）
2. **异常提示几乎全空**：`continuity_resume_service.py` 只有 `conflicts == ["LEASE_EXPIRED"]`（恰好等于）才给下一步；其余冲突码，以及 LEASE_EXPIRED 同时伴随别的冲突时，`next_legal_action` 置空。（读码，审计 559 同意）
3. **租约一过期，持有者连自己的 Run 都不能动**：`_require_lease_in_tx` 对所有写入查“未过期”，不能转 FAILED、不能写检查点；没有“安全中止/复位”这一档。（读码）
4. **出口链前置步骤守的是正常模式的闸**：结算过期 Run 只有最后一步 `settle-expired` 在运行身份不一致时只警告，前置步骤全带 `require_runtime_identity`。（**实测**，见 1.3）
5. **测试在关掉护栏的条件下造场景**：`test_continuity_recovery_run.py` 用 `identity_guard_off`，场景造好后才用 `control_root_guard_switch` 打开控制根规则，只验最后一步。整条出口链在生产护栏下没有任何测试走过。（读码）

### 1.3 实测（沙箱，11-02）：身份不一致时恢复链走不通

做法：在 SW-2026-008 的测试仓库里，用真 CLI（`CliRunner`），控制根规则全开，带 #496 的代码，把恢复链后 6 步跑两遍；第二遍用补丁让运行身份解析返回 `RUNTIME_IDENTITY_DIVERGENCE`。

| 条件 | 结果 |
|---|---|
| 身份干净 | work create（带实施卡）、work authorize、work transition、run start（--recovery-change）、run transition→RUNNING、run settle-expired，6 步退出码全为 0 |
| 注入 DIVERGENCE | 第 1 步 work create 即被拒“运行身份未通过校验，已拒绝写入”；run start、work transition、work authorize 单独跑也各自被拒；只有 settle-expired 放行（只警告） |

现有 `test_continuity_runtime_identity.py`（pytest 实跑 52 passed，含参数化）同样把 work create/authorize/transition、run start/transition 登记为“身份冲突即拒”，作者写明“恢复命令只警告”的原则，但只覆盖最后一步，没覆盖它的前置。

**更正与新发现**：
- 前置不是 8 步而是至少 10 步：写入型 Work 必须带通过预检的实施卡（`--card-file`，含档次检查）。完整链：建并推进恢复变更单 → 建恢复 Decision（需用户原话/口令）→ git 提交 → 实施卡 → 建 Work → 授权 → 转进行中 → 开 Run → 转 RUNNING → 结算。
- 踩坑点：恢复 Work 范围必须含 `.auto-pm/continuity.db`，卡片路径表里把它标“存在”会被拒（它不在 git 基线），只能标“计划新增”。应写进恢复手册和卡模板。
- 未在沙箱单独跑：变更单、Decision 两步（按各自运行身份测试和 `require_runtime_identity_for_change` 判断同样会拒）。
- 回退本身会制造这个状态：启动器在 active 校验失败时退回 previous，`launch.py` 的警告写明此时写入会被运行身份检查拒绝。**回退 = 运行身份不一致 = 恢复链前置被拒**。
- 探针脚本：`plans/tools/probe_recovery_chain_20261102.py`（不入库；放进 tests/cli/ 后用 pytest -o addopts="" 运行），待转成防线 2 的第一个用例。

### 1.4 本轮按审计 559 补核的四项（读码）

| 项 | 核实结果 |
|---|---|
| **控制根与 origin 分叉** | 存储层要求恢复 Decision 在控制根“被 git 跟踪且相对 HEAD 干净”（`decision_git_binding_issues`），首次结算要求“当前 Git HEAD 精确匹配恢复 Run 的 git_head”，即从开 Run 到结算 HEAD 不得前移。恢复 Decision 只能本地提交（main 走 PR），控制根随即“领先 origin/main”。`control_root_sync` 是只读提示，不拦；它建议“fetch + ff-only”，并写明“不能快进说明有本地提交，先推送成 PR 或交用户处理”。结论：没有哪行代码因“领先”拒绝，但**同步卫生（快进/拉取）与 HEAD 钉死互相冲突，对齐 main 要走 GitHub（外网）**，是流程层的环。没在真克隆上跑过 |
| **发版切换的实现** | 仓库里**没有**发版切换的实现。启动器（`launcher/bootstrap.py`、`launch.py`，纯标准库）只读指针文件、manifest 和载荷哈希，**不读账本**；发版卡和 G 检查在主执行本机，不在仓库。`pm_switch.py` 是卡的切换，不是发版切换。所以“切换不查账本”对启动器成立，对切换流程只能靠卡模板入库后才能测 |
| **准入/占钥匙/范围撞车** | `create_run` 只检查：Work 状态 READY/IN_PROGRESS、owned ⊆ Work scope、所属 Mission 是否搁着、同一 Work 只有一个非终态 Run。准入（8 张上限、范围撞车放行）在 `pm approve` / `mission_admission`，**不在 `continuity` 恢复链上**——恢复链直接建 Work，不经 Mission。结论：当前代码恢复链不撞准入；矩阵仍要登记这类护栏并标“是否在出口链上”，且设计规定**恢复令不得改走 pm approve/Mission**（否则会撞准入）。另：目标 Run 所属 Mission 处于搁着时，`settle_expired_run` 拒绝（`_refuse_if_parked`），出口是用户 `pm unpark`，需要用户原话 |
| **用户离线步骤** | 结算链里要用户本人的：恢复变更单批准、恢复 Decision（agent 会话需用户原话凭据，#402）；回收（reclaim）在原持有者进程判不出时要 `pm sign-risk`；搁置/拿回/切换、`lease extend-hold`、删除/切换发布都要用户原话。用户 11-30 起离线约 4 个月，这些步骤一旦成为出口就会卡住 |

### 1.5 新样本（协调者 11-02 16:10 MST）：orient 看不见的卡死 Run

样本：账本里有一个 9-10 的旧 Codex Run `RUN-SW008-A2-201-03`，状态 RUNNING、租约早已过期、所属 Work 已被验收；`pm orient` 不报它。**这是一个“没有出口、连异常都看不见”的状态，比死锁更早一步：探测器本身有盲区。**

**读码得出的根因（未对该真账本核实，沙箱没有这个账本）**：`ContinuityResumeService.collect()` 是**从上往下**找：先选 Mission → 取 Work → 再列这个 Work 的 Run。
1. `list_works()` 默认只列**执行活动态** Work；已验收（ACCEPTED/CLOSED）的 Work 不在列表里。
2. 即使选中了已验收的 Work，代码走“历史选择”分支（`POST_ACCEPTANCE_WORK_STATES | TERMINAL_WORK_STATES`）：注释写明“历史选择**永不暴露**活动 Run 或租约”，且如果显式给 `run_id` 且该 Run 非终态，直接抛“验收后 Work 不可恢复非终态 Run”。
3. 租约过期（`LEASE_EXPIRED`）的判断只对“执行活动态 Work 下、在 `run_candidates` 里”的 Run 做。
所以“Run 活着、但它的 Work 已验收”这个组合，**三条路径都走不到**：不报冲突，`next_legal_action` 照常，`ledger reconcile` 的变更单对账器（`domain/change/ledger_reconciler.py`）也不看 Run。orient 不空、不红，用户以为没事。这是探测器按“对象树”而不是“账本全表”找异常的设计缺口，与 1.1 的死锁同一类病根：**没有人规定“账本里每一种不正常的对象，都必须有一个探测器看得见”**。

**出口是否存在也未必**：`settle_expired_run` 不要求目标 Work 处于活动态，所以理论上可结算；但它要求目标 Work **非只读且绑定 canonical 的 immutable Decision**（`is_canonical_decision_id`）并通过 Decision 的 git 快照比对。9-10 的 Codex 旧 Run 很可能是 v8 之前的 Work/Decision 格式——**这点要在真账本上用只读命令核实**（我没有该账本）。如果不满足，出口也不存在，这一行同时是“看不见 + 没出口”。

**纳入设计的做法**：
- **矩阵加一行异常状态**“Run 存活（非终态）但所属 Work 已验收/关闭/取消”，探测方式是**账本全表扫描**，不经过 Mission→Work→Run 的树：`SELECT run_id FROM run_items r JOIN work_items w ON w.work_id=r.work_id WHERE r.state NOT IN ('SUCCEEDED','FAILED','CANCELLED') AND w.state IN ('ACCEPTED','CLOSED','CANCELLED')`；再加“租约已过期”作为子类（与 LEASE_EXPIRED 区分编码 `LIVE_RUN_UNDER_FINISHED_WORK`）。
- **防线 1 加“探测器完整性”规则**：对 `run_items`/`lease`/`work_items`/`mission` 每一种非终态 × 每一种父对象状态的组合（自动生成），必须有一个冲突码能看到它，或在矩阵里明写“该组合不可能出现（由 schema/状态机保证）”。这条规则会直接拦住这次盲区。
- **P0 就能做、不改任何拒绝**：`pm orient` / `resume` 增加一个与 Mission 树**无关**的“全表扫描”冲突来源，只读，产生新冲突码 `LIVE_RUN_UNDER_FINISHED_WORK`，并在 `continuity recovery plan <Run>` 里打印该状态的出口链。因为是新增只读探测，不属于“放宽拦截”，不要用户点头；**但它会让 orient 变红，发版 7 切换前不要放进载荷**，否则 G3 又多一条冲突（与 11-02 已定的发版 7 冻结一致，P0 本来就等开闸）。
- **出口链**：先用只读命令核实该 Run 的 Work 绑定情况（是否 canonical Decision、是否只读）；满足则走既有的“恢复变更单 → 恢复 Decision → 恢复 Work/Run → `settle-expired`”链（recovery plan 打印）；不满足则需要新的出口（例如对“验收前格式的旧 Work”的结算变体），那是放宽，属 P1，**要用户点头**，并在 Decision 里点名这个 Run、写明不重写旧事件。
- **演练行**：造“Work 已验收、Run 仍 RUNNING 且租约过期”的账本（种状态可直接写表）→ 断言 orient 报 `LIVE_RUN_UNDER_FINISHED_WORK`（探测）→ 按 recovery plan 全护栏打开跑出口 → orient 无冲突、reconcile 0/0/0；再加变体“Work 为 v8 前格式（非 canonical Decision）”，在出口补上之前按**已知缺口、严格 xfail** 登记（带 TD 号与翻转期限）。

## 2. 异常状态与出口（联锁矩阵首版草表）

新增两列：**谁能做**（用户亲口 / 主执行 / 任一 agent）、**switch_safe**（切换发版时候选版能收拾的才可放行；缺省 FAIL）。

| 异常状态 | 现有出口 | 前置 / 被谁挡 | 谁能做 | switch_safe | 现状 |
|---|---|---|---|---|---|
| 租约过期 | 换名回收；结算过期 Run；自救（未建） | 结算前置≥10 步，多数带身份校验（实测）；#496 的例外要发版 7 | 回收：任一 agent（持有者判不出时要用户 sign-risk）；结算：用户（Decision、变更单） | 是（仅限对象明确的 Run） | 已死锁过 |
| 终态 Run 租约未摘 | fence/reconcile-terminal-lease | 同上 | 用户（Decision） | 是 | 待演练 |
| Work 被 BLOCKED | work adjudicate | 裁决证据+恢复 Run | 用户 | 否（需裁决） | 待演练 |
| Run 建了没启动 | revoke-unstarted | 恢复 Decision；不在 #496 例外内 | 用户 | 是 | 待演练 |
| 重启后执行进程已死 | pm recover → --apply 记 EXECUTOR_LOST | 发版 7 才有；写后账本不能回 6a9f127 及以前 | 主执行 | 否（进程仍活要 FAIL） | 单向 |
| 验证中卡住 | 搁置；续租 | #407 已合，等发版 | 持有者 | 是 | 待发版 |
| 运行身份不一致 ①：指针与加载包不一致，但加载包自身载荷哈希校验通过、代码能打开该账本 | 恢复令（豁免“身份冲突拒绝写入”这一道闸）；或修指针 | 前置步骤被它自己挡住（实测） | 用户 | — | 已死锁过 |
| 运行身份不一致 ②：启动器已回退到 previous | **先修 active（重建/重指指针、让 active 校验通过；此步在仓库之外，矩阵标“人工步骤”，不是命令）**，再在 active 上恢复；禁止在 previous 上写账本 | 回退后跑的是旧代码：没有 `--recovery-change`、没有恢复令命令；若账本已写 EXECUTOR_LOST，旧版连快照都打不开。所以在 previous 上“豁免身份”没有意义 | 用户（切换只认亲口） | — | 已死锁过（G3 的根） |
| 多个活动 Mission/Work/Run；Mission 根未激活 | **无登记出口** | next_legal_action 为空 | — | 否（未知一律 FAIL） | 缺口 |
| 收口写一半 | pm close 重试 | 需用户已验收 | 用户验收后任一 agent | 否 | 待演练 |
| 控制根落后/领先 main、工位满、范围内文件脏 | 快进同步；worktree close/sweep | 与 HEAD 钉死冲突（1.4）；删除须用户“收” | 主执行 / 用户 | 否 | 待演练 |
| 账本被新版本写过 | 无回退，只能向前 | 旧版打不开快照 | — | — | 规则，须明写 |
| **Run 存活（非终态）但所属 Work 已验收/关闭/取消**（样本 RUN-SW008-A2-201-03） | **orient 看不见**（探测盲区，见 1.5）；理论出口 settle-expired，Work 非 canonical Decision 时无出口（待真账本核实） | 探测只经 Mission→Work→Run 树；结算要目标 Work 绑 canonical Decision 且非只读 | 用户（恢复 Decision） | 是（切换后可处理） | **缺口：看不见 + 出口待核**，P0 先补探测，P1 补出口 |
| 目标 Mission 搁着 | 用户 pm unpark | `_refuse_if_parked` 拒结算 | 用户 | 否 | 待演练 |

**`needs_code_version` 列（异常状态表的一列，此处用附表）**：能收拾该状态的出口至少需要哪一版代码。

| 异常状态 | needs_code_version |
| --- | --- |
| 租约过期（结算）、终态租约围栏/对账、Work 裁决 | 含 #496 的版本（发版 7 及以后）；在此之前的版本只有换名回收 |
| 重启后进程已死 | 发版 7 及以后（`pm recover`） |
| 运行身份不一致 ② | 任何能让 active 校验通过的版本；出口不依赖 previous |
| Run 存活但 Work 已验收 | 探测：新探测器所在版本（P0 后）；出口：含 #496 的版本，旧格式 Work 的结算变体见 P1 |
| 其余 | 现行版 |

演练按此列执行：一个出口只在“needs_code_version 满足的载荷”上演练。**铁律（协调者 15:05 裁）：任何行的 needs_code_version 不得高于被测候选自身，高于即判红**（候选版自己必须能收拾自己造成的异常）；只有对“现行部署版”做的只报告演练，才可把该行标“需先升级”而不是红。

用户离线时哪些异常会一直卡着：“谁能做”完全只有用户的有 5 行（终态租约、Work 被 BLOCKED、Run 没启动、运行身份不一致、目标 Mission 搁着），另有 2 行（租约过期的结算、收口）部分步骤要用户。**出差前要对着这张汇总看一眼，决定预授权什么（见第 4 节）。**

## 3. 推荐架构

### A. 联锁矩阵 = 数据

文件 `auto_pm/contracts/interlock_matrix.py`（随载荷）。三张表加一个“事实词汇表”：

- **事实**：`worktree=control_root`、`identity=clean`、`lease=live`、`actor=user|agent`、`git=head_pinned`、`decision=sealed` 等。
- **命令表**：每条 CLI 命令一类（只读 / 正常 / 恢复），所需事实，谁能做。并入现有 `test_all_commands_identity_classified.py` 与各 `*_runtime_identity.py` 里的分类（那是已有的半张表，不另起一张）。
- **护栏表**：每个跨命令护栏——适用模式、禁止/要求哪些事实、恢复模式下可否豁免。**护栏用“抛出点”标识（模块.函数），不靠命名**：B2 的闸 `_worktree_is_the_control_root` 就不叫 require/refuse。含准入类、占钥匙类、范围撞车、搁着、收口已准备、工位上限。
- **异常状态表**：探测器、有序出口链、谁能做、switch_safe、不能与之共存的状态。

死锁定义（机器可判）：某出口步骤需要的事实，被适用于它且未豁免的护栏禁止；或出口链里某步以“本状态已解除”为前提（环）。B2 = 结算需要 `worktree=control_root`，而“禁控制根当工位”对它无豁免。

### B. 统一恢复模式（恢复令）

**结构性收窄（审计 559 ★3）**
- 豁免集合**写死在矩阵里**：`EXEMPTIONS[动作类] = {护栏编号…}`。Decision 只能“点名目标 + 动作类”，**不能携带护栏编号**。
- **继承 #496 的全部条件，只能更严**：写入型恢复 Work 绑定 canonical Decision；Decision 无条件 approved 且带恢复类 runtime_capability；Decision 的 CHG 与所给一致、与目标原 CHG 独立；同一项目；Decision/Work scope/owned 都覆盖 canonical continuity.db，控制根上的恢复 Run owned 恰好是 continuity.db；Decision 与原 Decision 已入库（见 ★2 的替换）；点名目标仍待处理；同一恢复 Work 同时只许一个活 Run；撤销未启动 Run 不在例外内。
- 迁移 #496 的 19 个测试（`tests/cli/test_continuity_recovery_run.py`）进防线 2，原样作为回归。
- **恢复类命令名单只能缩**：固定名单测试（同 `test_all_commands_identity_classified` 做法）；矩阵文件进受保护清单（改它的 PR 必须手动 sw008-ci 并有审计，需在 `reviews/tools/audit_pr.py` 的 PROTECTED_PATTERNS 里登记）。
- 同一项目同一时刻只许一张恢复令；有次数和有效期上限；开令的人不能是被恢复 Run 的持有会话；恢复 Run 的执行者必须不同于目标的持有者。
- **不改走 Mission**：恢复令不经 `pm approve`，避免撞准入。

**用户批准的前提（协调者提出，逐条写明）**

| 约束 | 规定 | 保证方式 |
|---|---|---|
| 谁能进入 | 只有用户本人；agent（含 Trae）自己进不去 | `recovery open` 先识别 agent 标记并拒绝（同 `refuse_agent_approval`）；**若用户设了批准口令**，再要求用户在终端输入口令（agent 不知道口令、不得索要），错误锁定沿用现有机制；**默认（无口令）**时靠：agent 标记拒绝 + 必须有用户批准并已封存、已入库的 Decision + 用户原话凭据的格式校验，见第 4 节的残留风险 |
| 前提 | 已入库、已入账哈希、用户批准、点名目标的恢复 Decision | 不新造权限，沿用 runtime_capability |
| 范围 | 只限点名的目标、动作类；只限矩阵登记为恢复类的命令；只豁免矩阵为该动作类写死的护栏 | 逐条查表，不靠临时参数 |
| 自动退出 | 目标全处理完（账本出现结算/围栏事件）、或超时（默认 2 小时，最长 4 小时）、或用户 `recovery close` | 退出后同一命令立即恢复被拒；超时未关的令在 `pm orient`/`doctor` 亮红；开令期间**禁止对控制根做同步/拉取/提交**（HEAD 钉死），orient 显示横幅 |
| 留痕 | 开令、每次豁免、每个步骤、关令各写一条只追加事件：谁、哪条命令、哪道护栏、结果 | 事件表只追加；`ledger reconcile` 核对“每次豁免都有对应开令” |
| 永不豁免 | 用户批准与口令、安全区签字、载荷哈希校验与账本 schema 版本校验、Decision 封存哈希与 git 绑定比对、删除确认、agent 不能自批、写审计事件本身、owned 超出 continuity.db 的任何写 | 护栏表标“不可豁免”，防线 1 检查这几项没有任何豁免路径 |
| **`recovery open` 自己** | 登记为恢复类，**只豁免“因身份冲突拒绝写入”这一道闸**，且仅当①加载包自身的载荷哈希校验通过、②当前代码的账本 schema 版本能打开该账本。这两项比对任何情况下都**不豁免**（它们才是“版本号与指纹比对”）。启动器已回退到 previous 时不适用本条：出口是先修 active | 写进矩阵；防线 2 覆盖：载荷哈希被改 → 拒；schema 打不开 → 拒；仅身份冲突 → 放行 |
| 矩阵坏了 | 读不到或自相矛盾时拒绝开令，不默认放行 | 旧版（无矩阵）继续用现有显式恢复命令 |

**★2（协调者已裁，rev 3 更正）：批准时哈希入账 + Decision 仍须提交，两者都要；只取消“HEAD 不得前移”**
- 现状（1.4）：Decision 要入 git 且从开 Run 到结算 HEAD 钉死，造成同步卫生冲突，且对齐 main 依赖外网。
- 定案：
  1. `decision create` 批准时，**在同一事务内**写账本事件 `DECISION_SEALED{decision_id, sha256, 用户确认}`；哈希对 Decision 文件的规范字节，与现在 `get_decision_with_sha256` 同一口径。这样闭上“批准到提交之间字节被改”的窗口。
  2. **同一 Decision id 只能封存一次**；二次封存（哪怕哈希不同）必须拒。
  3. **两个检查都要，不得二选一**：已封存的 Decision，哈希必须匹配，**且**必须已被控制根 git 跟踪、相对 HEAD 干净。没有封存事件的旧 Decision 按现行 git 规则，**不出现“哈希对或 git 对任一即可”的路径**，免得两个检查各自的漏洞叠加成并集。
  4. **旧 Decision 迁移**：P2 之前批准的 Decision 没有封存事件，行为定义为“按旧规则”，矩阵标“无封存”，不回填、不改旧事件。
  5. 只删掉“当前 HEAD 必须精确等于恢复 Run 的 git_head”这一条；store 里把 Decision 绑到 git 的各处（`_control_root_decision_binding`、`settle_expired_run` 的 `require_current_head`、服务层与 `work_registry_service` 的 `decision_git_binding_issues`）逐处改，属核心路径行为改动，随 P2 做，审计逐处核。
  6. **本地提交带来的“领先 origin/main”**（不再被 HEAD 钉死，但仍存在）：恢复令开着时“领先”是**预期状态**，`pm orient` 横幅标明而不报警；**恢复后必须把这个恢复提交走 PR 推回**，列为恢复令的收口步骤和“恢复后责任”，并写进矩阵“控制根领先 main”一行的出口。**做法（协调者 15:05 裁）**：把控制根本地 main 推到一个新分支 → 开 PR → 只用 Merge commit 合并（不 Squash、不 Rebase，否则本地提交哈希变了，控制根与 origin 再次分叉）。**“开令期间禁止同步/提交”只管到 P2 之前**，P2 删除 HEAD 钉死后取消。**恢复提交超过 3 天仍未推回，`pm orient` 亮标记**（矩阵“控制根领先 main”一行的探测项，演练行：造一个 3 天前的未推回恢复提交 → orient 报）。
  7. **events 表只追加**：库里没有触发器（grep TRIGGER 无结果），“只追加”目前是代码约定。封存的防篡改强度取决于此：防线 1 加静态检查“代码里没有对 events 表的 UPDATE/DELETE”；是否再加库层触发器作为 P2 的一项由协调者另裁。
  8. 测试：封存后改一个字节 → 开令被拒；哈希与文件一致但无 git 提交 → 被拒；二次封存被拒；旧 Decision（无封存）走旧规则。
- 落地前现有路径照旧：矩阵把“HEAD 钉死”登记为事实 `git=head_pinned`，并规定开令期间禁止对控制根做同步/拉取/提交；P2 删除该钉死后，这条禁令随之取消。

### C. 发版检查不被账本绑架

- 每条发版检查标 **scope**：`candidate`（构建可重现、测试、演练、载荷校验）/ `environment`（现行账本冲突、工位数）。**缺省按 environment 处理，不得当切换前硬条件**。
- 增加 **switch_safe** 列（见第 2 节）：只有“候选版能收拾”的才可放行；仍有活着的执行进程、半写收口、账本完整性问题**默认 FAIL**；**未知冲突码一律 FAIL**。这也保住原 G3“切换发生在静止点”的作用。
- G3 改为：用**账本备份副本 + 一个控制根克隆 + 候选载荷**（不只拷 db：要复现 git 状态、恢复 Decision、工位和真实运行身份）跑 `pm orient`，每个冲突必须对得上**载荷外**的已知死锁回归夹具并演练通过。
- **判卷夹具放在载荷之外**（`reviews/tools/` 下，由发版脚本/CI 独立复跑，符合 AGENTS.md 第 8 条验证与生成隔离）；载荷只提供被测对象。否则候选版把所有冲突都登记成“可恢复”，闸就形同虚设。
- **G3 窄例外要有到期条件**：只对本次发版卡、冲突恰好等于 `['LEASE_EXPIRED']` 且对象恰好是指定 Run 有效，切换完成即失效；反例测试：换对象或换发版卡不生效。
- **“切换永不查账本”要有测试**：（a）启动器 `launcher/*.py` 只 import 标准库、不打开 `continuity.db`（静态测试）；（b）账本带 LEASE_EXPIRED 与运行身份不一致时，`resolve_release` 与回退仍成功（动态测试）；（c）发版卡的 G 检查清单入库为数据文件（`reviews/tools/release_gates.json`，含 scope、switch_safe），卡生成器只能读它。发版卡在仓库外，(c) 要主执行配合。
- **“旧版也能恢复”怎么说**：对已发出的旧版没法回头证明。能保证的是：①从演练上线那一版起，每版必须过出口演练才能构建；②“前进永远通”——有缺陷的旧版用修复版替换，不必先在旧版里恢复。做不到的是写过单向事件后回退，矩阵里明写“只能向前”。

## 4. 需要用户定的事

1. **批准口令（只给恢复模式用）——用户未答复，设计默认：不设口令**。用户 10-25 取消了口令。无口令时，一个没带 agent 标记的进程会被当成用户，所以“Trae 自己进不去”只由三层叠加保证：标记拒绝；恢复 Decision 必须是用户批准过的（agent 会话批准需用户原话凭据，#402）且已封存入库；恢复令范围窄、限时、全程留痕。**残留风险**：一个丢掉标记、又能伪造出合法用户原话凭据格式的 agent 理论上可开令（但仍需一份用户批准过的 Decision）。推荐方案是口令只给恢复令用：`recovery open` 在口令没设时直接拒，用 `pm approver-pin init` 设一次（该命令不依赖账本状态）；这是用户的决定，协调者 17:00 汇报时问。
出差前的前提（与是否启用口令无关）：`pm approver-pin init` 必须在出发前能跑通——它不依赖账本状态，口令是否已设（`pin=configured`）登记为矩阵事实，口令未设时 `recovery open` 被拒有对应演练行。**是否启用口令仍由用户定**，协调者 17:00 汇报时问。

**口令开关（协调者 15:05 裁）**：设配置项 `recovery.require_pin`，**答复前默认 false**；演练**两种模式都跑**（false：靠标记拒绝 + 已封存已入库的 Decision；true：口令未设/错/连错锁定一律拒）。文档措辞必须写明：**“封存证明字节没被改，不证明批准人是用户本人。”**无口令时“是用户”只靠标记拒绝与用户原话凭据格式，这是残留风险而不是已解决。

2. **出差期预授权（11-30 起约 4 个月）——用户未答复，设计默认：不预授权**。凡“谁能做”只有用户的出口，用户离线就会卡住（5 行）。备选方案：出发前由用户预先批准一类窄恢复令——仅限“过期 Run 结算”、列出的项目、结果只能 CANCELLED、对象须过期超过 N 小时、带到期日。风险是接近长期许可，而 #496 明确不做长期许可。协调者 17:00 汇报时问。
3. P1/P2 属“放宽拦截”，按既定规矩要用户点头；AGENTS.md WS-001 补“恢复令”说法要用户原话“确认改规则”。

## 5. 自动测试

### 防线 1：静态（秒级，每个 PR）`tests/contract/test_interlock_matrix.py`
1. 每条 CLI 命令必须在命令表里；名单只能缩。
2. **护栏以 guard_id 登记，不靠命名，也不靠抛出点**：新护栏一律抛带 `guard_id` 的类型化拒绝 `GuardRefusal(guard_id, …)`（是现有 `ContinuityStoreError`/`ClickException` 等的子类，捕获方不受影响）。原因：抛出点（模块.函数）粒度太粗——往已登记函数里的同一个 `if … raise` 再塞一个新条件（#496 就是这样改的 `start_run`），抛出点不变，对账仍绿。规则：**已登记模块里没有 guard_id 的拒绝算违规**（逐文件基线棘轮，改基线要改受保护文件，评审可见）；抛出点聚合只做过渡期的兜底，用来发现 `_worktree_is_the_control_root` 这类不叫 require/refuse 的闸。
3. 死锁判定（第 3 节 A）；**组合状态**：已登记状态两两自动生成并按“不能共存”表剔除。
4. 每个冲突码（AST 扫 `conflicts.append(...)` 与身份冲突码）必须是异常状态表一行；`pm orient` 永不空，且对**多个冲突同时出现**也给出下一步。
5. 恢复类名单只能缩；不可豁免项没有豁免路径；`recovery open` 是恢复类且只豁免“身份冲突拒绝写入”。
6. **events 表只追加**：静态检查代码里没有对 events 表的 UPDATE/DELETE。
7. 检测器自测（见防线 2 的灵敏度自测）。
8. **探测器完整性（11-02 新增，来自样本 RUN-SW008-A2-201-03）**：账本里每一种“子对象非终态 × 父对象已终态/已验收”的组合（自动从状态机生成），必须有一个冲突码看得见它，或矩阵里明写“不可能出现”；探测器必须是**全表扫描**，不得只经 Mission→Work→Run 的树。

### 防线 2：出口演练（分钟级，放 `tests/e2e/`，随 PR 的 e2e 分片自动跑）`tests/e2e/test_exit_drill.py`
- **种状态与出口分段**：造状态可以直接写账本（进程已死、租约过期本来就要这样造）；**出口步骤必须全护栏打开**，`production_guards` 标记只约束出口段。
- 出口走真 CLI，不调服务层；每步退出码 0；终点 `pm orient` 无冲突、`ledger reconcile` 0/0/0。
- **拦截对账（审计 559 ★5）**：给每个出口步骤在“扰动电池”（身份不一致、控制根领先/落后、范围内文件脏、持有者不符、恢复令未开等）下运行，捕获**实际触发的拦截**（统一拦截入口打点：包装各异常类的构造并取抛出点），断言“触发的 guard_id 集合 ⊆ 矩阵为该命令登记的 guard_id 集合”。矩阵漏登记会在真实运行里被抓出；没有 guard_id 的拒绝在已登记模块里直接判违规。
- **灵敏度自测**：注入一个合成护栏，逐个禁止出口链中每一步需要的每个事实，断言演练**一定变红**，证明检测器对任何一条出口都有牙；B2 回放只是其中一例。
- **组合场景**：异常 × 异常、异常 × 元状态（身份不一致、控制根分叉、工位满）自动生成。
- **新增演练行（559 增量复核）**：①口令未设 → `recovery open` 被拒（`pin=configured` 登记为事实）；②恢复令超时到期时目标做到一半 → 令自动关闭、同一命令立即被拒、`pm orient` 给出重新开令的出口；③封存后改一个字节 → 开令被拒；封存哈希对但无 git 提交 → 被拒；④启动器回退到 previous → 出口是修 active（人工步骤，演练**只核两件事**：在 previous 上写账本被拒；active 修好后恢复链走得通）；⑤载荷哈希被改 / schema 打不开 → `recovery open` 仍拒。
- **探测盲区演练（11-02 新增）**：造“Work 已验收、Run 仍 RUNNING、租约已过期”→ orient 必须报 `LIVE_RUN_UNDER_FINISHED_WORK`；变体“Work 为 v8 前格式”按已知缺口严格 xfail（TD 号 + 翻转期限）。
- **guard_id 迁移顺序与 xfail 纪律（协调者 15:05 裁）**：P0/P1 先把**出口链上**的拒绝点迁到 `GuardRefusal`（再扩到其余）；扰动电池必须覆盖**完整词表**（含所有已登记 guard_id，不只覆盖出口链）；**每个严格 xfail 必须带 TD 编号和翻转期限，xfail 总数只能减、不能增**（防线 1 棘轮）。
- **Trae 自己进不去**：带 agent 标记、无口令、口令错、连错锁定——四种都拒绝且账本不变。
- 迁入 #496 的 19 个用例；恢复令没开时同一命令仍被拒；豁免不超出点名目标；每次豁免都有事件。

### 防线 3：发版闸（放在载荷外）
- `reviews/tools/` 下的发版闸脚本复跑已知死锁回归夹具（B2、G3、TD-240…）；对候选载荷跑演练必须全过。
- 同一套演练对“现行部署版”再跑一次，**只报告不阻断**，结果写进发版说明：得到“现行版能不能自己恢复”这个事实。
- 每条发版检查必须有 scope 与 switch_safe 标签；未标按最严处理。

## 6. 分阶段落地

| 阶段 | 内容 | 改行为吗 | 要用户点头吗 |
|---|---|---|---|
| P0 | 矩阵数据 + 防线 1 + 已可走行的演练（含拦截对账、灵敏度自测）+ 死锁回归夹具（含“回退后身份不一致 × 过期 Run 必须能清除”，在 P2 前按**已知死锁、严格 xfail**登记，修好即翻转）；`pm orient` 读矩阵（含多冲突）；**只读命令 `continuity recovery plan <目标>`：按矩阵的出口链打印完整参数的命令清单**（提前自原 P2，10 步靠人手跑易错，Trae 模型弱）；`GuardRefusal` 类与“无 guard_id 的拒绝”棘轮基线；**账本全表扫描探测器（新冲突码 `LIVE_RUN_UNDER_FINISHED_WORK`，只读）与防线 1 第 8 条**；本设计文档入库 `docs/design/`；**不改任何拒绝** | 只改提示 | 不要 |
| P1 | 演练补齐全部行；缺口行的出口；发版闸与夹具入 `reviews/tools/`、发版卡检查入库 | 新增出口（放宽） | 要 |
| P2 | 恢复令（含 ★2 的入账哈希并删 HEAD 钉死、`recovery open`、豁免表、自动退出、留痕），收编 `--recovery-change` 与“只警告”散点 | 放宽，有留痕 | 要（含口令、出差预授权） |
| P3 | G3 改“候选版能否恢复”，窄例外到期 | 改发版流程 | 发版卡口径由协调者裁；切换仍须用户亲口 |

矩阵文件要随载荷走，所以每一步都是载荷 PR：等协调者开闸，进发版 8；变更单号向主执行领取。

**账本核心路径改动单独成 PR**（协调者 15:05 裁）：凡改动 store 里 Decision/git 绑定、`settle_expired_run`、`create_run`、恢复令豁免查表等核心路径的，不与矩阵/测试/文档混在一个 PR；审计对这类 PR **逐点核**（对应上文 ★2 第 5 点列出的各处）。

## 7. 未核实
- 发版卡与 G 检查原文不在仓库，按协调者转述写；切换流程是否还有别的账本前置，需主执行对着卡再过一遍。
- 变更单、Decision 两步在身份不一致时被拒，只由代码和既有测试推断，没在沙箱单独跑。
- 控制根领先/分叉的流程环只读码，没有在真克隆上演练；GitHub 外网依赖是推断。
- 沙箱不是真账本；`tier` 分档器在沙箱里按既有测试的办法打了补丁（`card_is_new → False`）。
- 护栏数量（约 20 个跨命令护栏）是估计，以 AST 对账表为准（审计 559 数到 `require_*/refuse_*` 53 处、47 个去重名，本稿 rev 1 写 52）。
- 异常状态表后 9 行“待演练”，出口是否真能走通都没跑过。
