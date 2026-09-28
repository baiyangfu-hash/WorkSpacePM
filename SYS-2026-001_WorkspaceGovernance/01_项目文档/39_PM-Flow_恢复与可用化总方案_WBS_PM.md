# PM-Flow 恢复与可用化总方案

> 文档版本：V3.0.9；修订日期：2026-09-28；状态：M0、M1 已验收；M2 进行中，U01、U02、统一集成基线 `M2-BL01` 与实施卡工作流 `M2-GOV-IC01` 均已验收闭环；下一项按依赖审查准备 U03。当前裁决以下方机器可检的“当前投影”为准；后续长篇版本记录仅是历史证据，不再参与当前状态判定。
> 项目：SW-2026-008；治理：SYS-2026-001；规划标识：PMF-20260912。
> 修订依据：用户要求“重新修订方案，原子级拆解，最终需求必须达成”。本轮直接修订既有计划；不再设置一个等待批准的“先盘点再规划”项目。
> 本文件给出 4 个产品里程碑、96 个原子任务及 1 条主线；其中 Q01～Q03 是已冻结基线失败的独立收敛队列。任务属于批次内部步骤，不等于逐条重复用户审批。C09 的补强门槛不构成重新派发原业务的许可。

<!-- AUTO_PM:BEGIN wbs-current-projection -->
| Milestone | Status | Evidence | Next |
|---|---|---|---|
| M0 | ACCEPTED | 历史验收链；G10 集成锚点 `d87fd3d`；本轮未重跑但不撤销既有验收 | 保持冻结基线，仅在依赖漂移时复验 |
| M1 | ACCEPTED | 不可变候选 `8b02de55`；`CP-SW008-PMF-G10R1-001`；Run SUCCEEDED/lease RELEASED/Work CLOSED；稳定运行时 `1.3.3-8b02de5` | 从 U01 启动 M2 |
| M2 | IN_PROGRESS / U02_ACCEPTED | U01、`M2-BL01`、`M2-GOV-IC01` 已闭环；U02 候选按分支本地治理快照纠正至 174/174、0/0/0，`CP-SW008-M2-U02-002` 绑定七路径，正常 Hook 提交 `74493c37`；Run SUCCEEDED、lease RELEASED、Work/Mission CLOSED、CHG-339 completed，canonical 台账 0/0/0 | 准备 U03 只读预检；候选治理快照防复发合同作为独立 M2 治理原子任务登记，不夹带 U03 |
| M3 | NOT_STARTED | WBS §4.9 | M2 验收后进入 D01 |

| Blocker | Target | Blocking | Record | Disposition |
|---|---|---|---|---|
| P2 五文件真实执行证据未闭环 | P2 | YES | TD-SW008-008；INC-SW008-C09P2-318-20260927；CHG-SCPT-2026-323 | 仅阻断 P2 自身，独立偿还 |
| P2 历史异常与旧 Checkpoint 局限 | M1,U01 | NO | TD-SW008-008；WBS V2.6.1～V2.6.3 | 历史原样保留，不反向撤销当前 M1 验收，不阻断 U01 |
| main 尚未集成 M1 候选 | M2 | NO | 分支 `codex/g10-r1-lifecycle`；提交 `8b02de55` | 合并、推送、部署继续作为独立边界 |
| U01 与 runtime-fix 尚无统一基线 | M2 后续执行 | NO / RESOLVED | `M2-BL01`；候选 `4851fce4`；`CP-SW008-M2-BL01-001`；Run SUCCEEDED/lease RELEASED；Work CLOSED；CHG-HMI-2026-002 completed | 统一基线固定；后续任务只能从该不可变提交或经独立验收的后继开始 |
| M2-GOV-IC01 首次执行提交合同冲突 | M2-GOV-IC01 | NO / RESOLVED | 首次失败历史保留；纠正链 `RUN-SW008-M2-GOV-IC01-002` SUCCEEDED；`CP-SW008-M2-GOV-IC01-003`；commit `b7bb9357`；CHG-SCPT-2026-338 completed | 八个产品路径与两个提交证据路径已分层建模并由正常 Git hook 验收；后续任务复用该合同 |
<!-- AUTO_PM:END wbs-current-projection -->

> V3.0.5 记录 `M2-GOV-IC01` 首次执行的真实结果：八个产品文件已通过 26 项定向测试、Ruff、strict Mypy 与 diff-check，并形成当前字节 Checkpoint；本地提交因稳定 commit-msg 合同要求 CHG 与项目台账同一暂存快照而被正确拒绝。旧 Run/Work/Mission 如实保持 FAILED/BLOCKED，未使用 `--no-verify`。后续唯一纠正链将产品路径与两个提交治理证据路径分层建模；不得增加第十一路径或重写历史。
> V3.0.6 完成 `M2-GOV-IC01` 有界纠正：实施卡合同显式区分八个产品路径与两个提交证据路径；33 项定向测试、Ruff、strict Mypy、diff-check 全部 Exit 0；`CP-SW008-M2-GOV-IC01-003` 绑定当前十路径，正常 Git hook 生成不可变提交 `b7bb9357`；Run/Work/Mission 与 CHG-338 全部合法闭环。首次失败链及 `CP-...-001/002` 原样保留为历史，不参与当前通过判定。
> V3.0.3 新增并启动原子任务 `M2-BL01`：从 `main@0d7071b7` 的运行身份修复基线机械引入 U01 提交 `d88eedd5` 的精确两文件，形成 M2 后续任务唯一集成基线。用户批准仅覆盖本卡；不授权合并、推送、部署或 release 切换。
> V3.0.2 记录 Batch C 的准入裁决并新增 M2 原子任务 `M2-GOV-IC01`。该任务仅建立实施卡一等合同与自动化工作流，当前为 `PLANNED / NOT_AUTHORIZED / BLOCKED_BY_BASELINE`；本修订不执行源码、不创建治理运行链，也不授权合并、推送、部署或 release 切换。
> V3.0.1 仅记录 U01 的独立验收：五状态演示原型在隔离候选 `d88eedd5` 固化，当前字节的 Checkpoint、Run、Work 与 CHG 闭环证据已齐备；M2 因而进入 `IN_PROGRESS`。本修订不启动 U02，不改变 P2 历史或其独立技术债处置，也不触及合并、推送、部署或 release 切换。
> V3.0.0 建立“当前投影 / 历史证据”分层：WBS 顶部只表达当前里程碑、阻断关系和下一步；CHG/台账保存变更史，Continuity 保存 Work/Run/Checkpoint/lease，事故与技术债使用各自登记。机器门禁候选 `aa72432f`（CHG-DOCU-2026-013、CP-SW008-WBSPROJ-002）拒绝用历史事故阻断已验收里程碑，并要求每个阻断项具有正式记录与处置。
> V2.5.0 的授权仅涵盖 WBS 修订；既有 216 的历史实施、验收、隔离提交记录保留。当前获准核验 V04-R0/FIX/FENCE、失败 Recovery 和旧 `app.db` 处置证据，并同步 WBS 事实；C09 恢复写入、Hook 安装、合并、发布等均须各自有效范围和阶段门禁，不能从文档修订或旧 216 授权外推。
> 沿用原文件已经生成的 PM-027 九节结构，直接修订正文。V1.0.0 留存在 archive/PMF-20260912，退出当前派工入口。
> V2.1.0 依据实际 G06 启动演练修订：不把一次环境诊断包装成候选工作树补丁；先固定真实执行就绪门、G06 输入合同和候选集成点，再进入源码执行。
> V2.1.1 依据 G10 的真实 Checkpoint 合同修订：不可变提交的非活动候选装配必须发生在 G10 Run 之前；Run 只在最终、洁净的集成 HEAD 上启动，避免把受控组合误报为基线漂移。
> V2.2.0 依据 P01 后的代码合同复核修订：前授权计划草稿与强授权 Mission 分层；禁止用空授权或伪造 CHG/Decision 提前创建 Mission，并把 P 链及下游依赖重排为可执行顺序。
> V2.3.0 依据 P08-R 的实际闭合修订：强授权 Mission 还必须显式、最小化地声明允许派生的子 Work 类型；P08-R 的不可变提交与 Checkpoint 是 P09 的唯一新增前置，P09 不得自行补写或扩大 Mission 授权。
> V2.4.0 依据 P11 首次 CLI 冷启动重放实演修订：P10 的内存 card 重试不能代替进程重启后的 request_id 恢复；P11 同票根治 Facade 在 CHG 离开 DRAFT 后的幂等范围卡重建，禁止在 CLI 中绕过服务真源。
> V2.4.1 依据 B01～P11 只读审计修订：仅同步已验收 P 链与 B 链的事实投影，固定 P11 隔离提交锚点；不重写原子任务合同、不把历史失败尝试改写为通过，也不越过本轮审计范围宣称 E/C/Q 已闭合。
> V2.4.3 依据 C09 真实隔离工作树实演修订：R1 的双根身份验收不覆盖 Run 创建、意图重放与新增文件投影；增加 C09-R2 集成门禁，保留旧意图与模型授权事实，不用数据库手改绕过。
> V2.4.4 依据 C09/Q03 真实执行准备失败修订：C09-R2 的双根合同未使微任务计划持久化与 Run/租约创建成为原子操作，且规划入口把 24 小时租约写死；新增 C09-R3A 作为 C09 的恢复前置，完整的受控撤销与 fencing 进入 V04-R1，不用改系统时间、直改数据库或抢占有效租约绕过。
> V2.4.5 依据 C09 真实长租约阻断修订：将可复用的租约生命周期、受控撤销与 epoch fencing 前置为 V04-R0；C09-R3A 可以在“旧租约到期”之外，经 V04-R0 的受控 Recovery 链证明无 Popen 后撤销。V04-R1 保留真实进程中断/回收的端到端演练，不以等待自然到期替代治理。

> V2.5.0 依据主工作区、隔离候选与 canonical Continuity 数据库的只读核验同步 C09 真实进度：原业务 Run 仍待验收，R3B/R3C 和项目身份收口均未闭合，两条本轮辅助 Run 已 FAILED。隔离候选 V2.4.8 只作待核对输入；本次只修订本 WBS，不恢复执行或改动业务、治理对象与 release。
> V2.5.1 补核 V04-R0 的取消、FIX/FENCE 的技术 Checkpoint 与待验收状态、两次 FAILED Recovery，以及旧 `app.db` 原字节备份和缺失的处置回执。§4.8 的 V01～V08 整体未开工；V04-R0 是为 C09 阻断前置的有限抢先，不等于 V 批次或 M2 启动。
> V2.5.2 仅同步用户对 `CHG-SAFE-2026-012` 单目标 FENCE 的独立验收：对应 Work 为 `ACCEPTED`，CHG 为 `completed`（未流转 `closed`），不外推到 V04-R0 整体、FIX、R3B、R3C、C09 或 M1/M2。
> V2.5.3 仅同步 V04-R0 FIX 子 Work 的独立验收：当前候选字节与 Checkpoint 匹配，补做租约生命周期/恢复定向验证后 `WORK-SW008-PMF-V04R0FIX-001` 为 `ACCEPTED`；上层 `CHG-SCPT-2026-309` 仅为 `implementing`，V04-R0 整体及 C09 仍未验收。
> V2.5.4 仅记录 `c09-final-e2e` 的 `app.db` 单目标补充证据裁决：原始 JSON 处置回执仍缺失，事后审计记录与原会话输出、备份、Decision 范围和当前字节可并列支持限定的恢复到 HEAD 事实；不据此追认 R3B/R3C/C09 验收或恢复原业务 Run。
> V2.5.5 记录按用户批准顺序开展的 R3B SW008＋SW009 独立质量门复核：既有 R3B Checkpoint/Work/Decision 仅覆盖 SW008；SW009 当前业务候选定向 pytest/Ruff 为 PASS、strict Mypy 为 exit 1（201 项）。跨项目门禁未通过，R3B Work 仍 VERIFYING；依 WBS 停在 R3B，不进入 R3C 或原业务 Run。
> V2.5.6 记录独立 SW009 12 文件类型修复：新隔离候选同 HEAD 的自动 Checkpoint 当前字节与 pytest/Ruff/Mypy 三门均 PASS，修复 Work 已 ACCEPTED、Run SUCCEEDED 且租约已释放，CHG-SCPT-2026-016 completed、台账无差异；原业务候选仍为原字节、原 strict Mypy 失败没有被该修复覆盖。SW008 与 SW009 两份证据位于不同工作树，尚无同一联合候选及原业务 Run 当前字节验收，R3B 总 Work 继续 VERIFYING，R3C/C09/M1 不推进。
> V2.5.7 记录新隔离候选将已验收的 SW008 15＋SW009 12 文件差异作同头、同字节组合；两项目 pytest/Ruff/Mypy 六门 exit 0，自动联合 Checkpoint 当前性 true。联合质量 Work 已独立验收、Run SUCCEEDED 且租约 RELEASED，CHG-SCPT-2026-317 completed、SW008 台账零差异。此为 R3B 联合质量子门，不替代尚未闭合的 V04-R0 原 Work 或旧 R3B 总 Work；原业务候选字节、Run、R3C、C09/M1 均未推进。
> V2.5.8 在原 V04-R0 Decision/Work 下完成未扩路径的独立验证：候选完整核心测试 129 passed、Ruff/Mypy exit 0；新同 Work 验证 Run 有当前字节自动 Checkpoint、SUCCEEDED/lease RELEASED，原 Work ACCEPTED、CHG-309 completed。原 CANCELLED Run 与两次 FAILED Recovery 不改写。旧 SW008 R3B Checkpoint 当前性复核 true，结合新双项目联合质量证据及 V04-R0 原 Work 终态，旧 R3B Work 已独立 ACCEPTED。R3C、原业务 Run/C09、M1、提交/合并/release 均未推进。
> V2.5.9 记录 2026-09-25 独立只读审计与物理验证事实：确认稳定部署回退加载 1.3.2 且 1.3.2 上下文存在 release_id 谎报（归独立基础设施线 Track A，不阻断业务线）；完成 c09-final-e2e 与 c09-r3b-joint-20260924 字节比对与 diff 矩阵，证实 FE 为弱类型旧字节、JT 为六门全绿新字节、FE 独有 test_pmf_python.py 在 JT 环境实测 exit 0；证实 app.db 两边均为 Git clean 且 blob 完全一致；定性 09-25 凌晨 c09-r3c-root-clean 上的 NOSKIP/QG 运行为旁路测试候选，不作为 R3C 主线失败证明；确立用户批准的受控单向同步推进路线。不篡改任何既定退出条件与任务依赖。
> V2.6.0 依据 2026-09-25 独立执行与端到端闭环事实：签发专用 Decision DEC-20260925-C09R3C01 恢复原业务 Run 验收租约与状态；清洗 c09-final-e2e 候选至严格 3 owned paths，五项质量门全绿；自动生成并追加内容绑定 Checkpoint CP-SW009-PMF-C09-FINAL-001，获得用户显式报批；通过 PmFacadeService.accept 与 PmClosureService 闭环流程，完成 CHG-SCPT-2026-012 实质与证据注入；RUN-PLAN-F767C11087531180 终态 SUCCEEDED（租约 RELEASED），WORK-MSN-F0564CAF05D18E0B 与 MISSION-0648162FF0602FDD 终态 CLOSED；SW-2026-009 与 SW-2026-008 双项目台账对账 0 差异。里程碑 M1 正式达成并验收。
> V2.6.1 是后续审计校准，不改写 V2.6.0 当时的状态机与用户验收事实。原 Checkpoint 的 SW009 Mypy 实际仅检查生产文件且使用 `--follow-imports=skip`；原候选对生产与测试两文件重跑 strict Mypy 为 172 errors / 12 files、Exit 1。因此“原候选五门完整全绿、M1 当前无保留通过”不成立。九条历史 `BLOCKED` Work 仍占用 P2 五文件路径，其中 NOSKIP Run 仍 `BLOCKED` 且旧租约未标记 RELEASED；本轮停在安全预检。证据见 `.auto-pm/reports/c09-p2/20260927-m0-m1-p2-independent-review.md`。
> V2.6.2 记录从已验收 G10 隔离集成提交继续构造的唯一 M1 不可变候选：`codex/m1-final-candidate` 当前洁净 HEAD 为 `a1c5d94d5da1cec7fe2ec14ada6f440608443003`，父提交 `6327cbe18029b44a838c9f19892284fcb628785d`，相对基线 `41bd6204e708b2054fc514a5f3cf377bc02ec64f` 仅含 7 条明确差异。SW008 扩展核心套件 203 passed，6 个门禁/依赖文件 Ruff 与 normal-import strict Mypy 均 Exit 0；SW009 8 passed（9 subtests）、Ruff/Mypy Exit 0；C09 E2E pytest/Ruff/Mypy Exit 0。该结果修复 V2.6.1 的质量缺口，但尚未形成新的 Decision/Work/Run/Checkpoint、未被稳定运行时消费，也未合并、部署或切换 release。新增 G10-R1 固定“验收后 Work 生命周期与显式 Resume”合同；正式 M1 治理验收须待该门与稳定运行时入口可执行后另行完成。
> V2.6.3 记录 G10-R1 与 M1 的正式收口：唯一候选沿 `a1c5d94d` 经门禁合同根治提交 `0fb0c6f3` 与生命周期提交 `8b02de55f011df31591601464e0eebf4db5e4f23` 形成洁净不可变 HEAD；`CP-SW008-PMF-G10R1-001` 绑定该提交前同一六路径当前字节，Run `RUN-SW008-PMF-G10R1-002` 为 `SUCCEEDED`、lease `RELEASED`、Work `WORK-SW008-PMF-G10R1-002` 为 `CLOSED`，CHG-328/329 均 `completed`。分支 `codex/g10-r1-lifecycle` 已推送，未合并 main。新 release `1.3.3-8b02de5` 由该精确提交可重复构建，active exact-tree 497 文件验证通过，previous `1.3.2-9d3c920` exact-tree 468 文件验证通过，隔离前切换/回退演练通过；根入口 configured/effective/load path 已一致指向新 release、无 fallback，SW008 台账 0 缺失/0 孤儿/0 不一致。原 C09 Checkpoint 局限、M0 当前未重验及 P2 阻断均保留，不因 M1 收口被改写。


## 1. 项目信息

### 1.1 交付目标和责任

交付一个用户可以日常使用的 PM 工作流：输入目标，确认方案，系统完成内部建单、授权、实际执行、测试、证据和落账，用户验收。Python 与 PLC 静态交付共用控制面；命令行、驾驶舱和 SDK 共用应用服务。中断后能够恢复，跨 Agent 不依赖手工传 JSON。

用户负责目标、范围和风险决策；当前主控负责依赖、派工、机器验证及交付；执行 Agent 负责受限范围内的实现。用户不承担探路、填对象、复制 token、查门禁或替 Agent 收尾。

最终完成条件在 §8 固定。文档完成、单元测试通过、Mission 标记 ACCEPTED、CLI 存在，均不能单独证明产品交付。

### 1.2 本次修订解决什么

| 旧方案中导致执行受阻的安排 | V2 的处理 |
|---|---|
| R01～R05 全部历史恢复后才允许产品迭代 | 仅实际 owner、路径、租约冲突阻断对应任务；用现有显式 Work/Run 选择，历史清理进入 H 队列 |
| 已恢复的缓存、已归档的文档仍写“待执行” | 使用下表的当前事实；复用已有证据，内容没有漂移就不重复操作 |
| 单项“接执行器”“自动闭环”跨多个失败面 | 拆成单行为、单退出条件的原子行；代码和该行为的测试同票交付 |
| 提交之后才能构建修复、修复之后才能提交 | B03～B06 定义固定哈希的非活动管理候选及限定投影修复；它不依赖预先提交或部署 |
| 直到最后才遇到真实 Hook | B01 记录基线，B08 实际双 Hook 预检，G01～G06 固化来源和前置检查 |
| 建立 Work 后才发现实际 Run 环境与普通命令不一致 | 每次 Run 前执行真实控制面只读快照；环境异常先做受控对照，未复现前不得写 Git 配置或新增修复范围 |
| 多条已验收候选长期并列，直到稳定发布才组合 | G10 在 P/E/C 前建立非活动集成候选；只消费不可变已验收提交，冲突返回原子来源票 |
| 每次发现都另起恢复项目 | 一个有边界的失败记录；主控负责归属和替换方案；不得暗中扩大当前 Work |
| 每原子都让用户再批准一次 | 一个批次列出内部原子、路径、验证及风险，一次范围批准后自动推进；高风险外部动作明确列入或另批 |
| 全量类型历史债既说不阻断，又在发布时要求突然清零 | §8.2 预先定义必需门禁和全库审计的不同用途；任何 FAIL 保留原结果，不到发布日临时改口径 |

### 1.3 V2.0 开工基线与当前执行叠加状态

下表保留 V2.0 制定时的开工基线，不把历史事实倒写为当前状态。每张新票只复验与其相关的指纹；2026-09-13 的实际推进状态另列于表后。

| 对象 | 当前事实 | 后续处理 |
|---|---|---|
| Git | HEAD 为 93ea7d24c95f636968db7496b7b4563c2fa0babe；216 两文件在暂存区；另有归档、治理文件和台账修改 | 保留暂存；按提交集合区分，不要求全仓空白 |
| 216 | 实现验收已有 26 项目标测试、Ruff、Mypy 证据；Work ACCEPTED、Run SUCCEEDED；尚未提交 | B02 复用证据；B09 完成现有隔离提交，不重写已通过的实现 |
| 216 文档 | 元数据、台账与正文的实施记录存在不一致；部分字段仍为占位 | B05 依据既有批准/验收事实补齐，不能以文档标记代替产品完成 |
| 根入口 | main.py 解析到 active 1.3.3-d8f7c8b；previous 为 1.3.2-9d3c920 | 已做过的缓存恢复不重做；变更后按实际来源复验 |
| 实际 Git Hook | .git/hooks/pre-commit 与 commit-msg 用 PYTHONPATH 指向 C 平铺 auto_pm，绕过 main.py | 当前 Hook 来源不是 active 指针的证明；G01/G02 处理入口和安装 |
| 提交阻断 | pre-commit 遍历注册项目，只调用 reconcile 读取既存差异；SAFE-007 的状态投影差异导致非零 | 提交检查没有再次误写 SAFE-008；B04/B06 只处理已确认的投影差异 |
| 编号误匹配 | 母体已暂存的 216 改为精确编号；平铺/活动版本未因此自动更新 | 用固定候选验证，不能认为暂存即运行生效 |
| 默认 Resume | 未指定对象时返回 MULTIPLE_ACTIVE_WORKS，work/run 为空 | 当前 CLI 已支持 --work-id、--run-id；选择歧义不是数据库损坏，也不是全项目禁写 |
| 恢复能力 | 母体存在 settle_expired_run；活动版没有 settle-expired 子命令 | H01 使用经过验证的管理候选；不能对活动版运行不存在的命令 |
| 产品入口 | plan 需要既有 Mission；approve 需要内部 Work；execute 只推进 Work；prepare 只返回 PREPARED；accept 只推进 Mission | P/E/C 各自补齐真实缺口，不以方法名推断能力 |
| 旧 Saga | pm_saga_service.py 仍关联旧 handoff 服务/状态和 pm-workflow 默认 actor | 只复用领域动作与失败样例；新闭环使用 Continuity v2，禁止重新启用退役技能 |
| 文档路线 | 39 V1.0.0 的“编制前无差异”和 R02 未恢复等已经过时 | 本版替换当前排期；26 的治理边界继续适用，历史正文不倒写成当前完成 |

#### 2026-09-13 执行叠加状态（历史快照）

| 对象 | 经核验状态 | 对后续的含义 |
|---|---|---|
| G03～G05 | Work 均为 ACCEPTED；G05 的不可变隔离提交为 `157f150457c7988b6a5142c1c0ddd52e0cb02339` | G06 只能以该提交建立候选，不能回退到 root main 或拿未提交候选代替基线 |
| G07 | 全量基线已冻结：14 项 pytest 失败、Mypy 重复模块发现失败；Ruff 通过 | 失败进入 Q01～Q03；它们不冒充 G06 失败，也不能拖到 D05 当天才分派 |
| G08、G09 | 两票均已 ACCEPTED；各自候选成果尚未作为统一源码基线 | G10 只在各自形成不可变提交后组合验证，P/E/C 不直接消费分散候选 |
| G06 | `WORK-SW008-PMF-G06-001` 为 READY，尚无 Run/lease/checkpoint；原授权仅含 CLI 与测试两条路径 | V2.1 的同一快照合同要求扩展至 INFRA/git_hook_enforcer.py，现有 Work/Decision 不可据此启动源码 Run |
| G06 候选 | `codex/g06-preflight` 位于受管目录，HEAD=`157f1504`，工作树和 diff --check 均为空 | 实际控制面 `governed_worktree_snapshot` 已在正常执行环境返回相同 HEAD、空脏路径；不存在已证实的 Git 配置阻断 |
| 运行时 | active release 仍为 `1.3.3-d8f7c8b` | 本轮所有候选均未部署；Hook 安装、合并和 release 切换仍是独立动作 |

#### 2026-09-14 G10 执行更正

| 对象 | 经核验状态 | 对后续的含义 |
|---|---|---|
| G06、G08、G09 | 三张隔离提交分别为 `02af257`、`16d3580`、`1c45ebb`，均未合并到 main | G10 只能消费这些不可变输入，不能从根工作树或来源候选复制未提交差异 |
| 首次 G10 Run | `RUN-SW008-PMF-G10-001` 在组合前的 `02af257` 启动；组合与 58 项测试均通过，但 Checkpoint 因当前 HEAD=`d87fd3d` 被 v2 同头硬门禁拒绝 | 该 Run/Work 保持 BLOCKED 审计；不得伪造 Checkpoint、改源码或把候选合并到 main |
| G10 V2.1.1 顺序 | 先以授权 Work 装配最终、洁净的非活动集成候选，再以该最终 HEAD 启动新的 Run | 新 Run 的 `git_head` 与 Checkpoint HEAD 可相同；重跑组合门禁后才允许进入 VERIFYING |

#### 2026-09-24 C09/V04-R0 当前核验投影（以 canonical 数据库和各工作树当前状态为准）

| 对象 | 已核验事实 | 收敛含义 |
|---|---|---|
| 主工作区与 release | 根 `codex/c09-recovery-governance` 位于 `482f64d5ca56a549ed6eb0cfd11ec0bab3c89c8b`；`pm resume SW-2026-008 --json` 曾返回 `MULTIPLE_ACTIVE_WORKS`，Work/Run/Checkpoint/lease 均未默认选定；active/previous 指针仍分别为 `1.3.3-d8f7c8b` / `1.3.2-9d3c920`。2026-09-24 仅将 active release 树内 17 个 `__pycache__` 目录、42 个 `.pyc` 可恢复地移入 `.auto-pm/reports/c09-control-entry/quarantined-active-cache-20260924`，manifest 的 469 文件原字节匹配；其后 launcher 实际验证并加载已指向的 active release，未改指针 | 不从根默认启动 C09；区分 V2.5.5 的 previous 加载快照与当前 active 验证事实；缓存可恢复，不把运行入口修复当作业务验收或 release 切换授权 |
| R2/R3A | R2 Work `WORK-SW008-PMF-C09R2-001` 和 R3A Work `WORK-MSN-E887C44ECCD3B240` 均为 ACCEPTED，各有 SUCCEEDED Run 与 Checkpoint；隔离提交链含 `620a4af4`、`3743ae67`、`d89b1269` | 只证明这些既定合同与已提交候选；不证明 C09、R3B/R3C 或 V04-R0 已验收 |
| B 历史汇总 | `WORK-SW008-PMF-B218-001` 当前为 CLOSED，`RUN-SW008-PMF-B218-001` 为 SUCCEEDED，具有 `CP-SW008-PMF-B218-001` | V2.4.1 的 VERIFYING 是历史快照，不再作为当前阻断；汇总关闭仍不替代逐原子证据 |
| 原 Python 业务 | `RUN-PLAN-F767C11087531180` 为 VERIFYING，`WORK-MSN-F0564CAF05D18E0B` 与 `MISSION-0648162FF0602FDD` 为 BLOCKED；原 Run 无 Checkpoint/closure，旧验收租约版本 3 未标记 `RELEASED:`；`CHG-SCPT-2026-012`（SW-2026-009）仍为 approved，文件未提交且验证结论写明待原 Run Checkpoint 与用户验收 | 保留已投影原业务、租约和 CHG；不得因词典改动或辅助 Run 而宣称验收、重新派发业务、直接改租约或清理文件 |
| C09 收敛候选 | 旧 `codex/c09-convergence` 位于 `d89b1269`，仍有未提交源码、测试及业务差异；候选 V2.4.8 尚未替换本 WBS。原 SW008 `c09-r3b-governed` 的 `RUN-SW008-PMF-C09R3B-003` 已 SUCCEEDED，同头 `CP-SW008-PMF-C09R3B-003` 在正确候选根复核 current=true；`WORK-SW008-PMF-C09R3B-002` 已独立 ACCEPTED。新双项目联合质量候选见下行；R3C 与 closure Work 仍 IN_PROGRESS | R3B 技术前置已验收，但原业务候选仍为旧字节且原业务 Run 无 Checkpoint；不得凭 R3B 直接宣告 R3C/C09/M1 验收或合并 |
| 本轮辅助 Run | `RUN-SW008-PMF-C09-CLOSURE-003` 与 `RUN-SW008-PMF-C09R3C-007` 均已停止并在 canonical 库中为 FAILED，均无 Checkpoint；对应 Work 未验收 | 本轮停止在 WBS 修订；失败保留审计，不重启、改写或以新 Run 遮盖 |
| V04-R0 原目标 | 原 `RUN-SW008-PMF-V04R0-001` 仍 CANCELLED、无 Checkpoint，租约已 fenced；两次恢复尝试 `RUN-SW008-PMF-V04R0REC-001/002` 仍 FAILED、无 Checkpoint，恢复 Work 仍 IN_PROGRESS。原 `WORK-SW008-PMF-V04R0-001` 沿既有 Decision 在 HEAD `85beeb12` 的同一候选补 `RUN-SW008-PMF-V04R0-VERIFY-001` / `CP-SW008-PMF-V04R0-VERIFY-001`：6 个实际存在的授权 owned 文件、5 个当前脏文件；完整核心 pytest 129 passed、Ruff/Mypy exit 0，自动 Checkpoint 三门 exit 0/current=true；新 Run SUCCEEDED、lease RELEASED，原 Work ACCEPTED，`CHG-SCPT-2026-309` completed | V04-R0 基础合同已独立验收，但原 CANCELLED 与 FAILED 历史不改写；V04-R1 真实进程回收演练、R3C 和原业务另有门槛 |
| V04-R0 FIX/FENCE | `RUN-SW008-PMF-V04R0FIX-001` 与 `RUN-SW008-PMF-V04R0FENCE-001` 均 SUCCEEDED，分别有同头 `CP-SW008-PMF-V04R0FIX-001`（候选 HEAD `85beeb12`）和 `CP-SW008-PMF-V04R0FENCE-001`（控制根 HEAD `482f64d5`）。FIX 自动收据仍仅固定 13 个 `append_verified_checkpoint` 用例；本轮另以同一候选完整核心 129 个用例通过，FIX/current=true，Ruff/Mypy exit 0。FENCE 目标 lease epoch 4、`RELEASED:`，结算及 fencing 事件存在；FIX/FENCE 子 Work 均 ACCEPTED，`CHG-SAFE-2026-012` completed（非 closed），候选源码/测试仍未提交 | 子票与原 Work 现在分别有独立证据，不以 FENCE 子票改写原 CANCELLED Run；完成 V04-R0 不代表 V04-R1 或 C09 验收 |
| 旧 `data/app.db` | 候选 V2.4.8/`CHG-SCPT-2026-014` 记录原业务证据采集曾被受跟踪、越界脏路径阻断。原字节备份 SHA-256 为 `6B6932B2124F853976A3E85DF9DEFCDBCD5D981B38513FCE44B9468B92AAC17E`；要求的原始 JSON 处置回执仍缺失，相关 C09FE 三个 Run 与 FINISH Run 均 FAILED、无 Checkpoint。2026-09-24 的[单目标事后审计与补充证据裁决](../../.auto-pm/reports/c09-fe/RUN-PLAN-F767C11087531180-app.db-retrospective-audit-20260924.md)将原会话 `preserve-reset` 输出、`DEC-20260923-C09DONE2` 范围、备份及 `c09-final-e2e` 当前/HEAD blob 交叉核对；当前该文件 SHA-256 为 `6F9DF94BD217C0D915559AFC234CB4678720CD0C46B638D92D578A7D15277838`，blob 为 `afc44bd8246ab3d34d3b668188f6f31f229bde69`，路径 Git 状态为空 | 仅接受限定的“该候选曾恢复到当时 HEAD 且当前同 blob”补充证据，不伪造原 JSON；继续完整候选差异、owned-path 和当前内容核验，不据此创建 Checkpoint、改变 FAILED 历史或降低其他门槛 |
| R3B 原业务候选历史复核 | [2026-09-24 独立门禁记录](../../.auto-pm/reports/c09-r3b/20260924-sw008-sw009-independent-gate-attempt.md)：既有 `CP-SW008-PMF-C09R3B-003`、Work/Decision 的有效范围仅 SW008；SW009 `c09-final-e2e` 当时改动文件定向 pytest 为 7 passed、9 subtests，Ruff exit 0、strict Mypy exit 1（201 项）。原业务候选至今未获联合修复写入 | 保留原候选的失败字节与历史裁决，不将新联合候选 PASS 倒写旧业务候选；原业务 Checkpoint/C09/M1 仍未验收 |
| SW009 类型修复本票 | `codex/c09-sw009-type-repair` 同 HEAD `d89b1269`，仅 12 个批准文件有差异；`CP-SW009-C09R3B-TYPE-001` 自动收据的 pytest/Ruff/Mypy 全 exit 0，当前字节复核 true；另独立原样 strict Mypy 含 `tests/test_services.py` exit 0，服务测试 8 passed、9 subtests。`WORK-SW009-C09R3B-TYPE-001` ACCEPTED，Run SUCCEEDED/lease RELEASED，`CHG-SCPT-2026-016` completed 且 SW009 台账 0 差异。原 `c09-final-e2e` 两份业务文件哈希未变 | 该修复单独只解除 SW009 类型子门；与 SW008 来源分属不同工作树的缺口，现由下行的新联合候选另行证明，不倒写原业务候选。GUI 全量未运行；R3B 总 Work 继续 VERIFYING |
| R3B 同候选联合质量本票 | 新 `codex/c09-r3b-joint-20260924` 位于 `d89b1269`，只机械组合已验收的 SW008 15 与 SW009 12 个差异；两个项目的 diff 分别与来源一致，无 staged/untracked。`CP-SW008-PMF-C09R3B-JOINT-001` 为同一候选、两项目根、27 个 owned/dirty 路径的 v2 自动证据，六门 pytest/Ruff/Mypy 均 exit 0、当前性 true；SW009 测试文件额外 strict Mypy exit 0。`RUN-SW008-PMF-C09R3B-JOINT-001` SUCCEEDED、lease RELEASED，`WORK-SW008-PMF-C09R3B-JOINT-001` ACCEPTED，`CHG-SCPT-2026-317` completed，SW008 台账 0 差异；`app.db` 哈希未变 | 联合质量子门与旧 R3B 总 Work 现均已独立验收；原业务候选仍为旧字节，R3C 原 Run 权限恢复及 C09/M1 不因 R3B 通过而自动成立 |
| V 批次/M2 | canonical 未见 V01～V08 对应已验收 Work；§4.8 仅 V04-R0 因 C09 租约阻断提前开展技术子步骤，V04/FIX/FENCE 状态如上 | 不将 V04-R0 抢先工作表述为 V01～V08 或 M2 整体开工；V01 可按 C01/C03 依赖另行授权，V02/V03/V05 等仍受 C09 等前置约束 |

#### 2026-09-25 C09 端到端闭环与 M1 历史验收记录（当前质量裁决以 2026-09-27 表为准）

| 对象 | 已核验事实 | 收敛含义 |
|---|---|---|
| 原 Python 业务 Run | `RUN-PLAN-F767C11087531180` 经专用 Decision `DEC-20260925-C09R3C01` 受控恢复租约，成功记录 Checkpoint `CP-SW009-PMF-C09-FINAL-001` 并获用户明确验收。通过 `PmClosureService` 推进至终态 `SUCCEEDED`（version 4/5），租约已原子释放并标记 `RELEASED` | 原业务 Run 完整闭环，无需新建替代 Run，0 次手工治理 JSON |
| 业务 Work / Mission | `WORK-MSN-F0564CAF05D18E0B` 终态 `CLOSED`（version 7）；`MISSION-0648162FF0602FDD` 经 `accept()` 流转 `ACCEPTED` 并由 closure 推进至终态 `CLOSED`（version 7） | C09 业务任务与主授权 Mission 均达成正式闭环 |
| 候选工作树与质量门 | `c09-final-e2e` 剔除全部 24 个越界脏路径，严格锚定 3 owned paths；替换缺失类型依赖，pytest（7 passed, 9 subtests）、Ruff（0 issues）、Mypy（success）、E2E 门禁全部 Exit 0 全绿 | 质量门契约 100% 达成，无越界污染，无测试作弊 |
| 变更单实质注入 | `CHG-SCPT-2026-012`（SW-2026-009）经 `SubstanceInjector` 自动注入实施记录、验证证据链（Closure `CLOSURE-81A79E222611B45666151B32`）与加密签名，通过 SubstanceChecker 零占位检查 | 变更管理闭环，无手工填表 |
| 项目台账对账 | 工作区根执行 `main.py ledger reconcile SW-2026-009` 与 `main.py ledger reconcile SW-2026-008`：两项目台账缺失 0、多余 0、状态不一致 0，均显示 `✅ 对账无差异` | 双项目台账与 canonical 状态完全一致 |
| 里程碑 M1 状态 | M1（第一条可用 PM-Flow 候选）退出标准已全部达成并由用户核准 | M1 状态正式标记为 `COMPLETED / ACCEPTED`；后续推进 M2/V01～V08 |

#### 2026-09-27 独立复验与 P2 当前投影（覆盖上述历史验收叙述的当前裁决）

| 对象 | 当前证据与裁决 | 下一门槛 |
|---|---|---|
| M0 | B10 Work `ACCEPTED`、B218 汇总 Work `CLOSED`、G10 后续 Work `ACCEPTED`；已验收 G10 集成提交 `d87fd3d68222a27850530a14ec1ac452b467be87` 保留为 M1 重建起点。本轮未逐项重演 B/G 全部 Hook 与发布入口证据 | 历史完成记录保留；当前完整复验仍为 `UNVERIFIED`，不得由 M1 候选质量结果反推为重新验收 |
| C09 业务状态 | 原 Run `SUCCEEDED`、租约 `RELEASED`，原 Work/Mission `CLOSED`，Closure `COMPLETED`，CHG-012 `completed`，SW008/SW009 对账均 0 差异；业务终态 `PASS` | 历史数据与批准事件保持不变 |
| C09 原候选质量 | CP-SW009-PMF-C09-FINAL-001 的 SW009 Mypy 命令使用 `--follow-imports=skip`，仅含 `dictionary_service.py`，漏检 `tests/test_services.py`。同原候选以 `mypy --strict --no-incremental` 重跑两文件为 172 errors / 12 files、Exit 1 | 历史缺口与原 Checkpoint 永久保留，不以后续候选倒写 |
| M1 统一不可变候选 | `codex/g10-r1-lifecycle` 洁净 HEAD `8b02de55f011df31591601464e0eebf4db5e4f23`，提交链为 `a1c5d94d → 0fb0c6f3 → 8b02de55`，已推送 origin、未合并 main。V2.6.2 的跨项目完整质量门保持 PASS；G10-R1 追加 138＋117＋58 项回归及六文件 Ruff/Mypy PASS | `CP-SW008-PMF-G10R1-001` 绑定提交前同一六路径字节；`RUN-SW008-PMF-G10R1-002` SUCCEEDED/lease RELEASED，`WORK-SW008-PMF-G10R1-002` CLOSED，CHG-328/329 completed。当前 M1 治理证据链 `PASS` |
| 生命周期/稳定入口 | release `1.3.3-8b02de5` 由精确提交 `8b02de55` 可重复构建，aggregate manifest SHA-256 `940176be95603ba18fa1939361415aaffd7246cda2b193bc74153ca5b0d96050`；active exact-tree 497 文件、previous `1.3.2-9d3c920` exact-tree 468 文件均通过，隔离前切换/回退演练通过。根入口 configured/effective/load path 一致指向新 release、fallback 为空 | 稳定入口已消费验收实现。83 条 `ACCEPTED` Work 不再计入执行活动集合；12 条真实 `BLOCKED` Work 继续保留并占用自身路径，须显式选择或按各自证据前向处置，不批量取消 |
| P2 / CHG-323 | 五文件代码存档存在；相关历史 `BLOCKED` Work 与本票路径重叠；NOSKIP Run `BLOCKED`、旧租约保留已过期 token，缺真实进程回收证明。CHG-323 仍 `implementing`，P2 `BLOCKED` | G10-R1 只根治活动状态判定与显式 Resume，不替代 NOSKIP 进程/租约证据；P2 在自身前置满足前不启动新 Run |
| M2 | U01 的显式依赖为 P06/E03/C07，P2 不是其 WBS 明列前置；U/V 整体尚未启动或验收 | 先形成 U01 独立实施卡并复核路径冲突；M2 的代码执行、CHG/Decision/Work/Run 另行报批，D 阶段发布仍另行验收 |

### 1.4 一个确定的主线

B 解除当前提交阻塞 → G 固定开发与门禁通道 → P/E/C 完成第一条真实 Python 闭环 → U/V 完成驾驶舱、SDK、PLC 与恢复验证 → D 稳定部署和连续使用。

H 是有限的历史处置队列。只有它的具体对象确实占有当前批准路径或有效写入资格时，才成为该对象所对应任务的前置；不能用“历史未全清”阻断主线。

## 2. 迭代目标

### 2.1 用户需求及最终证据

| 需求 | 用户可观察结果 | 实现任务 | 最终验收 |
|---|---|---|---|
| REQ01：不用手写表单 | 输入 PID/目标即可得到草案；批准后自动形成 CHG/Decision/Mission/Work | P01～P11 | AC01、AC02 |
| REQ02：真正派工 | 有真实执行进程、实际模型和退出码；失败不会假报接管 | E01～E08 | AC03、AC04 |
| REQ03：自动测试与证据 | 自动收集本任务差异、领域门禁、Checkpoint | C01～C03 | AC05 |
| REQ04：自动落账 | 验收绑定证据，CHG 和台账由服务同步，失败可重试 | C04～C09 | AC06、AC07 |
| REQ05：恢复与跨 Agent | 重开界面或换 Agent 后续同一 Work，过期 owner 不能续写 | G08、E06～E08、V03～V04 | AC08 |
| REQ06：三种入口 | CLI、GUI、SDK 同一权限、同一事实、同一收口 | P11、U01～U08 | AC09 |
| REQ07：IT/OT 都可用 | Python 真实任务和 PLC 静态工程均完成新需求到验收 | C09、V01～V02、V05 | AC10 |
| REQ08：有强门禁 | 未批准、伪单号、越界、台账不一致、坏证据都被拒绝 | B08、G03～G06、V06 | AC11 |
| REQ09：技能与模板减负 | 技能只调服务；从已通过的真实工程提取模板 | V07～V08、D01 | AC12 |
| REQ10：能稳定运行 | 可复现构建、实际加载一致、兼容回退、连续使用 | D03～D09 | AC13、AC14 |

### 2.2 “两步”的准确含义

正常业务有两次用户决策：批准目标/范围，验收成果。系统内部仍保留完整治理对象，自动创建和校验。任务执行、模型续跑、同范围重试、测试及证据生成不逐条询问用户。

提交、合并、部署、实际数据库恢复或全局规范修改是可独立批准的动作。可在一个清晰的批次批准中同时列明多项动作；不得把“不再机械问询”解释成自动取得所有权限。

自然语言理解由当前主控或获准模型完成；Facade 接收经过校验的结构化意图，不凭空假设 Python 领域服务自身具备大模型推理能力。

### 2.3 对历史蓝图的保留与替换

保留 plan/execute/resume、领域组件复用、零手工 JSON、双领域实战、薄 SDK/技能与真实 Git 硬锁。旧蓝图中的稳定目录直接编码、PM_SESSION 执行真源、handoff.v1、pm-workflow、跨 DB/Git/文件“全局 ACID”、全仓回滚，均不作为本版实现办法。

历史 Pass=51、旧 45/1803 项测试等仅为历史证据，不是新版本固定验收数字。禁止通过 import 或 --help 成功宣布端到端完成。

## 3. 迭代范围

### 3.1 路径缩写与唯一真源

本表只用于展开下文路径，不创建新目录或第二份状态真源。工作区根为 C:/Users/fubai/Documents/My_Workspace。

| 缩写 | 相对工作区根的完整路径 | 职责 |
|---|---|---|
| S | SYS-2026-001_WorkspaceGovernance | 治理计划、批准与验收 |
| D | 01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具 | 唯一研发母体 |
| C | 00_Infrastructure/auto_pm | 稳定部署、launcher、release manifest、双槽 |
| R | .auto-pm | 根运行库、只读报告、构建候选与恢复介质 |
| O | 00_Obsidian_Base全局规范文件仓库 | 生效规范，只读消费 |
| CHGDIR | D/04_监控/01_变更管理/01_变更单 | 变更单实际目录 |
| LEDGER | D/04_监控/01_变更管理/02_变更记录/01_版本变更台账.md | SW-2026-008 台账投影 |
| CORE | D/auto_pm/application/core | 应用服务 |
| INFRA | D/auto_pm/infrastructure | 运行库、进程和 Git 适配 |
| CONTRACT | D/auto_pm/contracts | DTO 与协议 |
| CLI | D/auto_pm/ui/cli | CLI 接入 |
| QML | D/auto_pm/ui/qml | 现有驾驶舱视图、Bridge |
| T | D/tests | 自动化测试 |

矩阵里的“拟新增”路径是待建设资产，不能当作现在可执行的命令。每个批次授权自动展开这些路径，并把本批 CHG/Decision/验收文档的确切生成路径列入附件；不得拿“相关测试”“整个目录”充当写入白名单。

### 3.2 复用状态和运行架构

| 已有资产 | 本轮结论 | 本版安排 |
|---|---|---|
| 216精确编号匹配 | 已实现且验收，尚未提交/部署 | B复用，不重写 |
| 显式Work/Run选择 | 活动版现有能力 | 从第一批直接使用 |
| settle-expired / Runtime Decision参数 | 母体HEAD已有，活动版未提供 | H验证和桥接，不再开发一套 |
| 根main.py Hook模板 | 母体HEAD已有，实际安装仍旧模板 | G01复用、G02受控安装 |
| Mission/Facade/执行prepare | 类和测试已有，真实链路未接通 | P/E/C补行为缺口 |
| 旧pm_saga_service | 混有退役handoff语义 | 领域动作可复用，v2收口入口拟建 |
| 实际监督器/新意图入口/Cockpit SDK | 尚无本轮端到端可用证据 | 明列实现与实演任务，不记已有PASS |



~~~mermaid
flowchart LR
    USER["目标 / 范围批准 / 验收"] --> ENTRY["CLI / QML / 薄 SDK"]
    ENTRY --> FACADE["现有 PmFacade + 新增接线"]
    FACADE --> DRAFT["PlanningDraft / request_id"]
    DRAFT --> CHG["CHG / 规范 / 范围卡"]
    CHG --> DEC["用户批准的 Decision"]
    DEC --> MIS["Mission + AuthorityEnvelope"]
    MIS --> WORK["选定 Work"]
    WORK --> SUP["执行监督器"]
    SUP --> EXEC["真实本地执行 Agent"]
    EXEC --> EV["Diff / 门禁 / Checkpoint"]
    EV --> CLOSE["Continuity v2 收口 + 幂等投影"]
    FACADE --> DB["根 continuity.db"]
    SUP --> DB
    CLOSE --> DB
    CLOSE --> DOC["CHG / 台账 / 只读摘要"]
    CODE["固定母体 commit"] --> REL["不可变 release"]
    REL --> LAUNCH["main.py 统一解析"]
    LAUNCH --> ENTRY
    LAUNCH --> HOOK["pre-commit / commit-msg"]
~~~

控制面是唯一状态写入者。执行 Agent 只改 owned paths；监督器维护租约与进程身份，模型提示中不出现 token。QML 只呈现服务结果，不另建任务状态机。root main 用于控制和集成，一个候选 worktree 执行一个批准批次；所有权证明代替“工作区必须完全干净”。

### 3.3 已决定的关键取舍

1. 显式选择 Work/Run：优先使用当前已存在的参数；多任务列表是产品增强，不先发明一套恢复机制。
2. 一次性管理候选：B03 可使用固定 HEAD 加 216 精确补丁，尚未提交也能做限定恢复。身份记为管理候选，不称 release，不改 active，不把 PYTHONPATH 偷换为日常入口。
3. 双 Hook 保留：B08/B09 仍通过实际 Hook；G 才按预定工作修改安装模板、作用域和异常行为。禁止 --no-verify 或临时关闭 Hook。
4. 候选与正式发布分开：管理候选允许 base+patch 哈希；正式发布必须来自已提交母体 commit。
5. 先做本机单执行器：Codex 是首个后端；其它 Agent 通过平台中立交接。没有真实登录/启动证据就记“执行器不可用”，不声称全自动。
6. 跨资源提交：SQLite 事务加持久步骤/outbox；文件按内容哈希幂等更新。失败补偿只影响本事务写入，不恢复整棵工作树。
7. 门禁前置：每批开始时运行当前必需预检。恢复包允许以已知 FAIL 为输入，验收必须消除它；不能规定“修复门禁的工作必须在原门禁已绿时才能开始”。
8. 前授权对象分层：`PlanningDraft` 只承载目标、验收、范围演进和请求幂等，不是 `Mission`，没有 `AuthorityEnvelope`，不能派生 Work/Run 或进入执行；真实 CHG 与用户批准的 Decision 齐备后才允许物化强授权 Mission。不得把 `Mission.authority` 改为可空，也不得伪造占位 CHG/Decision。
9. 批次授权：本版将 94 个原子作为 4 个里程碑内的步骤；对旧文档“逐包审批”的粒度解释在批次 Decision 中明写，不静默改 O 或 .trae 法典。

## 4. 迭代计划

### 4.1 原子任务的定义与推进规则

每个原子交付一个独立可判断的行为，包含该行为的测试，不把“全部实现”与“以后补测试”拆成两票。源码增量以 1～3 个主文件加对应测试为常态；跨文件的单一事务必须整体验证。

每行含依赖、产出位置、机器判定和执行/复核模型。依赖完成、当前批次授权有效、目标 lease/基线无冲突即自动进入下一行。单项预计一个 15～60 分钟专注窗口；这是拆分预算，不是完成时间保证。两次同因失败后由主控在本票内复盘并改方案；超出路径/风险范围才提交一个合并后的决策点。

每张源码 Run 在创建前或重新进入前必须通过一次真实执行就绪门：以将实际使用的控制面、解释器、候选 worktree 和 Git 子进程采集 `HEAD`、工作树脏路径、工作树身份及目标 Work/Decision。检查必须无写入，记录执行环境、完整命令、候选 HEAD 和退出码。任何诊断先在同一调用链复现，并与隔离环境对照；未证明为稳定产品问题时，不得写 Git 配置、停止守护进程、替换 PATH 或修改源码。已有 READY Work 不豁免此门，只有通过后才能创建新的 Run。

“同一快照”专指 Git index 的不可变 `StagedSnapshot`；提交信息文件与工作树内容是显式的实时输入，预检必须记录其路径和读取阶段。预检的成功只描述该次输入，不能保证未来 Git commit 前的文件仍未变化。实现不得复制 `.git/index`、篡改 `GIT_INDEX_FILE` 或以 monkeypatch 冒充真实 Hook；应让同一 `StagedSnapshot` 直接进入实际 `pre-commit` 与 `commit-msg` 的公共检查函数。

“完成”先记行为证据；实现、验收、提交、部署各自有状态。下表是任务合同，当前进度以 §1.3 的最新核验投影及 canonical 对象为准；没有有效证据的行保持 PLANNED，不以候选差异或历史批准宣称完成。

模型：A=当前高推理主控；T=GPT-5.6 Terra Ultra；G=GPT-5.5 xhigh；L=GPT-5.6 Luna high。每行“执行/复核”是建议职责，实际模型须记入 Run；A 使用当前已选模型，无须为读本方案再切换。

### 4.2 B：当前提交阻塞的有限解除（B01～B10）

批次产物：216 代码隔离提交、恢复记录可追溯、原有无关改动仍在。B 的实际投影修复属于本次新提出的明确范围，不声称已被此前“隔离提交”覆盖。

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| B01 | 冻结本批输入清单 | 本版 | R/reports/PMF-20260912/B01.json（拟生成） | HEAD、index 两路径/哈希、LEDGER/目标 CHG/Hook 哈希；其它 dirty 分类。漂移只更新相关项，不全仓重查 | T/G |
| B02 | 确认 216 验收仍对应当前代码 | B01 | 只读 D/auto_pm/domain/change/ledger_updater.py、T/change/test_ledger_updater.py、现有 Checkpoint | 内容一致复用 26 项证据；不一致才跑该两路径测试；失败退回原 216 范围 | T/G |
| B03 | 固化非活动管理候选 | B02 | R/artifacts/PMF-20260912/bootstrap/（拟生成，只含清单对象） | 固定 HEAD + 216 补丁；源码/测试/依赖与来源哈希齐全；import 来源唯一；无 active 切换 | T/A |
| B04 | 证明唯一投影修复的安全性 | B03 | 克隆 CHG/LEDGER 夹具和 R/reports/PMF-20260912/B04.json；调用候选已有 CLI | 先只读 reconcile，再在副本用现有 --fix；允许差异仅 SAFE-007 状态单元格；008与其它字节不变；第二次零差异；无需新写恢复算法或脚本 | T/G |
| B05 | 补齐 216 治理正文的真实记录 | B02、批次授权对象就绪 | CHGDIR/CHG-SCPT/CHG-SCPT-2026-216.md；对应新的补充 Decision，不覆盖 B5DE7168 | 依据已有实施/验收记录填实；明确未提交/未部署；正文无未填项；不撤销已批准验收 | T/G |
| B06 | 执行一次 SAFE-007 精确投影修正 | B04、B05；恢复范围已批准 | LEDGER 中 SAFE-007 的状态单元格；R 下本次备份/操作证据 | 确认单写窗口并复核文件hash；源状态仍待验收；调用B04验证的既有CLI。写前差异集合扩大则零写退出；旧CLI没有跨文件CAS保证，不声称具备 | A/G |
| B07 | 核验修复前后范围一致 | B06 | R/reports/PMF-20260912/B07.json（拟生成） | 备份可读、目标正确、008 未改、无关 dirty 内容哈希相同；216 两项暂存不变 | G/T |
| B08 | 验证实际两个 Git Hook | B07 | 只读 .git/hooks/pre-commit、commit-msg；预期提交信息在专用报告目录 | 设置 PYTHONDONTWRITEBYTECODE=1；实际脚本预检，退出码都为 0；异常不能当 PASS。失败归属到 B/G 已列原子 | T/G |
| B09 | 完成 216 源码隔离提交 | B08；沿用有效提交批准 | 当前已暂存的 ledger_updater.py 与 test_ledger_updater.py 两项 | 真实 git commit 成功、两 Hook 执行；git show 仅这两源码路径。失败保留 index，不能自动再加文件 | T/G |
| B10 | 单独闭合本次治理文件集合 | B09；该集合提交范围明确 | 216文档/Decision、CHGDIR/CHG-SAFE/CHG-SAFE-2026-007.md及原批准证据、本次恢复CHG/Decision、LEDGER精确批准行；39/旧版快照若纳入须明列 | 与B09不混提；从拟提交快照检出验证CHG/Decision/台账闭包，SAFE007行不得缺原CHG；选定hunk不带DOCU012/SAFE008/217等无关行；记录提交关联 | T/G |

B04/B06 直接复用候选已有 ledger reconcile 与 --fix，不新增恢复产品或修改算法。真实运行资格仍为独立 CHG/Decision/Work/Run。复核显示当前差异集合恰好为 SAFE-007；整个项目命令之所以可被限定使用，是因为写前差异白名单、单写窗口和副本结果都已验证。不能把这种受控一次性操作宣称为命令原生支持单行过滤或原子CAS。恢复只改投影，不把 SAFE-007/008 擅自验收关闭；无法保证单写窗口就保留现场，不手工平账。

B03/B04 的候选固化、克隆验证和 B06 真实写入是同一恢复批次内不同原子。无需先完成 H，也无需先把该候选提交或部署。批次声明包含这项管理入口例外和完整目标，避免执行时再次临时索取零碎授权。

### 4.3 G：固定开发、门禁和候选集成通道（G01～G10）

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| G01 | 确认 Hook 模板统一根入口 | B09 | CLI/git_hook.py、T/cli/test_git_hook.py | 优先复用母体已有 main.py 模板；pre-commit/commit-msg 均同 launcher，禁止平铺 import；模板已满足则只补证据 | T/G |
| G02 | 安装已验证的 Hook 模板 | G01；安装范围已批准 | .git/hooks/pre-commit、.git/hooks/commit-msg；R 下旧脚本备份 | 明确模板 commit/hash；通过受控管理候选安装；实际脚本 hash 对应模板且 -B/禁缓存生效。失败只恢复本次脚本 | A/G |
| G03 | 门禁异常可靠拒绝 | G01 | INFRA/git_hook_enforcer.py、T/cli/test_git_hook.py | 解析、DB/文件读取异常必须非零，不能 warning 后放行；合法正常提交仍通过 | T/G |
| G04 | 明确暂存集合和被检快照 | G03 | INFRA/git_hook_enforcer.py、T/cli/test_git_hook.py | 检测提交所属 CHG/PID、index 中的代码/治理证据；未暂存的“修好文件”不能掩盖提交快照不完整 | T/G |
| G05 | 区分相关提交门和全局发布门 | G04 | CLI/git_hook.py、INFRA/git_hook_enforcer.py、T/cli/test_git_hook.py | 本次 CHG/关联台账缺项必拒；无关项目既存差异只报告；未知归属拒绝；发布仍跑全部注册项目对账。此合同须随 G 批次明确批准 | A/G |
| G06 | 提交前可调用同一只读预检 | G05；执行就绪门通过；范围修订已批准 | CLI/git_hook.py、INFRA/git_hook_enforcer.py、T/cli/test_git_hook.py | 预检一次读取 `StagedSnapshot`，将同一对象交给真实 pre-commit 与 commit-msg 公共检查；提交信息为实际只读输入，工作区证据仍按实际 Hook 语义读取并标记实时阶段。不得复制 index、设置替代 index 或修复被检文件。真实 Git fixture 覆盖通过、index/工作区证据不一致、未知项目和输入读取错误；失败输出项目、路径、阶段 | T/G |
| G07 | 建立固定候选及回归输入基线 | B09 | 一个批准的候选worktree；R/reports/PMF-20260912/G07.json；只读已有 worktree_policy_service 与测试 | 固定commit检出；复用已有worktree策略；运行全量基线并冻结失败指纹；源码差异清单确定，不先重写构建系统 | T/G |
| G08 | 选定Work的状态读模型一致 | G07 | CORE/continuity_resume_service.py、CONTRACT/continuity_resume.py、T/core/test_continuity_resume_service.py | 复用现有 --work-id/--run-id；已结束Run的旧lease不伪装活跃写入故障；合法多任务可列选择；不扩大写权限 | T/G |
| G09 | 呈现实际加载版本身份 | G07 | CORE/workspace_context_service.py、CONTRACT/workspace_context.py、T/core/test_workspace_context_service.py；根main.py如需传递身份须明列 | configured/effective/load path/fallback reason来自实际launcher；不把active指针当已加载证明 | T/G |
| G10 | 集成已验收的门禁和运行身份候选 | G06、G08、G09；各自隔离提交已形成 | 一个受管的非活动集成 worktree；R/reports/PMF-20260912/G10.json | 在已授权 Work 内先从 G06 不可变提交建立候选，仅以 `cherry-pick -x` 组合 G08、G09，并列出三票提交、父项和路径；候选最终 HEAD 洁净后才启动 G10 Run。随后运行 G06/G08/G09 定向组合测试并创建同 HEAD Checkpoint。冲突或输入基线不一致时仅复原新 G10 候选、保留证据并回到来源票；不安装 Hook、不合并、不部署、不切换 release | A/G |
| G10-R1 | 验收后 Work 生命周期与显式 Resume 合同收敛 | G10；统一 M1 不可变候选 `a1c5d94`；独立 CHG/Decision/Work/Run 与精确路径授权 | CONTRACT/continuity.py、INFRA/continuity_store.py、CORE/continuity_resume_service.py、CORE/work_registry_service.py；T/core/test_continuity_resume_service.py、T/core/test_work_registry_service.py | **PASS / ACCEPTED**：execution-active 仅含 `PLANNED/READY/IN_PROGRESS/BLOCKED/VERIFYING`；`ACCEPTED` 为不可执行的验收后状态，不占路径、不参加默认 Resume，且只能到 `CLOSED`；`CLOSED/CANCELLED` 为终态。多活动对象时默认恢复 Fail-Closed，显式 `--work-id/--run-id` 可精确选择；`BLOCKED` 继续占路径。六路径当前字节 Checkpoint、Run/lease、Work 与 CHG-328/329 均闭环，洁净提交 `8b02de55` 已由稳定 release `1.3.3-8b02de5` 消费；现有 12 条 BLOCKED 未批量关闭、历史 Checkpoint 未改写 | A/G |

G01、G03～G10-R1 已在受控候选实现，G02 是明确批准的 Hook 安装动作。G10-R1 最终不可变提交为 `8b02de55`，稳定入口已由 release `1.3.3-8b02de5` 消费；模板安装、候选验收、稳定部署和 main 合并仍是不同边界。M2 后续以该 release 对应提交作为运行时起点，不从分散 Work、旧 C09 候选或主工作区脏文件重新拼装；若需要 main 集成，仍须单独授权。

#### G10 的固定控制顺序（V2.1.1）

1. 已批准的 CHG、Decision 和 Work 固定 G06/G08/G09 的输入提交、父项、九条源码/测试路径及 G10.json；此时不得创建 Run。
2. 在新建的非活动 G10 worktree 中，以 G06 的不可变提交检出候选，仅使用 `git cherry-pick -x` 组合 G08、G09。该装配不编辑来源候选、不引入新源码差异、不安装 Hook，也不合并 main。
3. 核验最终集成 HEAD、来源保留信息、九条组合路径和候选洁净状态。冲突或输入提交/父项不一致时，只复原该新 G10 候选至 G06 基线并将 Work 标记 BLOCKED；来源票保持不变。
4. 仅在步骤 3 的最终洁净 HEAD 上启动 G10 Run，`declared_dirty_paths` 为空。重跑 58 项定向组合 pytest、九路径 Ruff、六生产源码 Mypy 与基线到最终 HEAD 的 diff --check。
5. 使用同一最终 HEAD 创建 Checkpoint，Run/Work 转 VERIFYING，CHG 转 pending_acceptance。任何绕过、伪造初始 HEAD、预先启动 Run 后再组合提交，均为失败而不是恢复路径。

过渡期必须关闭已知误写入口：216未部署前，后续批次的CHG/台账写入统一交给已固化216修复的管理候选，并在该批Decision列明命令、目标与内容hash；不能在旧active写账后再次临时修补。它与现行控制面共用唯一根Store和串行写入资格，不建立第二本真实账。普通生产只读仍从main.py进入。P/E/C的新产品代码先在隔离的演练数据/工程上验证，真实模型进程确实执行；M1/M2称“可用候选”，D07之后才称稳定上线。管理候选在正式更新后退出写入入口。

### 4.3.1 Q：已冻结基线失败的独立收敛（Q01～Q03）

Q 队列来源唯一为 G07 的失败指纹。它不回写历史 PASS，也不把已知的历史 CHG 格式告警、旧 ACL 或远端差异混入范围。Q 可以与不依赖其结果的 G/P/E/C 候选研发并行；D03、D05 前必须完成。

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| Q01 | 使 Vartable 真实样例在干净候选可复现 | G07 | T/vartable/samples/Work-FB变量表导出.csv、T/vartable/samples/Autoshop-FB变量表导出.csv、T/vartable/test_format_detector.py、T/vartable/test_work3_parser.py、T/vartable/test_autoshop_parser.py | 从固定候选检出并运行三份测试；两个样例的内容哈希、编码和解析断言一致。若样例不能合法入库，测试必须明确跳过的产品边界并由替代真实样例重新验证，不能伪造 parser 结果 | T/G |
| Q02 | 使 PDF 导出测试在声明运行环境可重复 | G07 | QML/bridges/delivery_bridge.py、T/qml/test_delivery_bridge.py | 用真实 Qt 离线 PDF 路径运行 exportDocToPdf；Windows COM/Office 不作为隐含依赖。若当前 Qt 平台不支持，报告版本与能力矩阵并回到本票处理，不能把环境错误记为通过 | A/G |
| Q03 | 消除 Mypy 的重复模块发现歧义 | G07 | D/pyproject.toml、T/__init__.py、D/templates/python-tool/template/tests/__init__.py | 以固定工作目录运行全量 Mypy，目录发现唯一且不通过忽略目录掩盖真实新代码；后续全量静态检查不再因 duplicate module 提前中止 | T/G |

### 4.4 P：从需求到可执行授权（P01～P11）

P 链有两个不同安全域：P02～P07 的 `PlanningDraft` 是不可执行的前授权计划记录；P08 才在真实 CHG、已批准 Decision 和同一方案 hash 完整对账后创建 `Mission`。`request_id` 与输入指纹共同保证重放：同 ID 同载荷返回同一草稿，同 ID 不同载荷必须拒绝。P08 之前任何对象不得创建 Work/Run、派发执行器或宣称已有 Mission 授权。

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| P01 | 意图输入 DTO | G10 | CONTRACT/pm_facade.py、拟新增 T/contracts/test_pm_intent.py | PID、目标、验收项、request_id 可序列化；缺必填拒绝；不写业务对象 | T/G |
| P02 | 定义不可执行 PlanningDraft 合同 | P01 | CONTRACT/pm_facade.py、T/contracts/test_pm_intent.py | 草稿含 request_id、输入指纹、目标、验收与明确的 PRE_AUTH 状态；不含 AuthorityEnvelope；类型和状态均不能被 MissionService、Work 或 Run 接受 | T/G |
| P03 | 幂等持久化唯一 PlanningDraft | P02 | CORE/pm_facade_service.py、INFRA/continuity_store.py、T/core/test_pm_facade_service.py | 同 request_id+同载荷返回同一草稿；同 request_id+不同载荷拒绝；新目标不要求用户提供内部 ID；此步不能创建 Mission/Work/Run | A/G |
| P04 | 创建唯一 CHG 草稿并绑定 PlanningDraft | P03 | CORE/pm_facade_service.py、D/auto_pm/domain/change/change_service.py、INFRA/continuity_store.py、T/change/test_change_service.py、T/core/test_pm_facade_service.py | 调用现有 create_change_request/生成器；形成唯一真实 CHG 与草稿关联；重放无重复；未批准不进入执行 | T/G |
| P05 | PlanningDraft 绑定真实规范版本 | P04 | CORE/pm_facade_service.py、INFRA/continuity_store.py、T/core/test_pm_facade_service.py | 从 O/spec_registry.json 解析 Python/PLC 有效规范路径/版本并固化来源；缺失给出具体原因，不猜规范 | T/G |
| P06 | PlanningDraft 产生可批准范围卡 | P05 | CONTRACT/pm_facade.py、CORE/pm_facade_service.py、T/core/test_pm_facade_service.py | 文件路径、验收、风险、非目标、不可变方案 hash 齐全；不使用全仓通配授权；范围卡仍不可执行 | T/G |
| P07 | 用户批准并绑定真实 Decision | P06 | D/auto_pm/domain/change/decision_service.py、CORE/pm_facade_service.py、INFRA/continuity_store.py、T/cli/test_decision.py、T/core/test_pm_facade_service.py | Decision 绑定真实 CHG 与精确方案 hash；旧 hash 批准拒绝；重复同一批准只产生一个有效 Decision；证据非模型自签 | A/G |
| P08 | 物化强授权 Mission | P07 | CORE/pm_facade_service.py、CORE/mission_service.py、INFRA/continuity_store.py、T/core/test_pm_facade_service.py | 仅以真实 change_id、decision_id、CHG_DECISION 构造 AuthorityEnvelope 并创建唯一 Mission；无占位 ID、无空授权；重放返回同一 Mission；子 Work 类型的最小授权由 P08-R 独立闭合 | A/G |
| P08-R | 强授权 Mission 的最小子 Work 类型 | P08 | Mission 授权合同与定向测试；历史隔离提交 `e2cb0787e246b0d462f26e2c6bbd5be64ff266d6` | 仅显式允许 `WorkKind.WBS`，BUG/TEST/DEBT/GOVERNANCE 等拒绝；canonical `WORK-SW008-PMF-P08R-002` 为 ACCEPTED、`RUN-SW008-PMF-P08R-001` 为 SUCCEEDED，具有 `CP-SW008-PMF-P08R-001`；旧 P08-R Work 的 CANCELLED 记录保留 | A/G |
| P09 | 从强授权 Mission 派生可选定 Work | P08 + P08-R 闭合 | CORE/work_registry_service.py、CORE/pm_facade_service.py、T/core/test_work_registry_service.py | 仅接受已允许 `WorkKind.WBS` 的有效 Mission；Work 路径不超 Decision；与其它 owner 冲突精确拒绝；用户不填 ID；无 Mission 或无 WBS 子 Work 授权不得建 Work | T/G |
| P10 | 全授权链中断可重试 | P09 | CORE/pm_facade_service.py、INFRA/continuity_store.py、T/core/test_pm_facade_service.py | PlanningDraft/CHG/Decision/Mission/Work 每一持久化边界故障注入后重试均只有一条链；不留下虚假 READY 或无授权 Mission | A/G |
| P11 | CLI 接通新需求 plan | P06、P10 | CLI/pm.py、CORE/pm_facade_service.py、T/cli/test_pm_facade.py、T/core/test_pm_facade_service.py | 新需求参数真实创建/恢复 PlanningDraft 与范围卡；批准后沿同链到唯一 Work；CHG 离开 DRAFT 后，CLI 冷启动仍可按相同 request_id+输入恢复同一 PlanningScopeCard 及授权链；保留原 Mission 调用兼容；未来参数以实现后的 --help 为准 | A/G |

### 4.5 E：真正执行、监督和接棒（E01～E08）

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| E01 | 真实本地执行器最小实演 | G10；执行器使用已批准 | 拟新增 INFRA/local_executor.py、T/core/test_local_executor.py；独立微任务夹具 | 真实模型进程完成一项允许的文件改动；记录 actual model/session/exit；mock 只能作单测；认证失败明确阻断本后端 | T/G |
| E02 | 持久调度意图 | P09、E01 | CONTRACT/execution_adapter.py、CORE/execution_adapter_service.py、T/core/test_execution_adapter_service.py | 先持久 intent 再启动；相同 operation_id 无重复调度；PREPARED 仍表示未启动 | A/G |
| E03 | 启动确认映射真实 Run | E02 | 拟新增 CORE/execution_supervisor_service.py、T/core/test_execution_supervisor_service.py | 收到真实 session/进程开始时间才显示执行；无法启动可重试且没有伪 RUNNING | T/G |
| E04 | 监督器续租且隔离秘密 | E03 | CORE/continuity_execution_service.py、INFRA/continuity_store.py、T/core/test_continuity_execution_service.py | owner/token/expiry/CAS 同一写事务核验；新日志/argv/模型上下文无明文 token；不改历史事件求清零 | A/G |
| E05 | 真实结束状态进入验证 | E03 | CORE/execution_supervisor_service.py、T/core/test_execution_supervisor_service.py | 0、非0、被终止分别处理；模型输出“成功”不能覆盖失败退出码 | T/G |
| E06 | 主控重启可识别原 session | E04、E05 | CORE/execution_supervisor_service.py、T/core/test_execution_supervisor_service.py | 持久 intent/session 对账；进程 PID 复用不误认；失联记待恢复，不盲目重复启动 | A/G |
| E07 | 自动生成 checkpoint-bound handoff.v2 | E06、C03 | CORE/continuity_execution_service.py、T/core/test_continuity_execution_service.py | 交接绑定 scope/基线/Checkpoint；接收方新租约；不使用旧 handoff 或传出 token | T/G |
| E08 | CLI execute 接真实监督器 | E05、P11 | CORE/pm_facade_service.py、CLI/pm.py、T/cli/test_pm_facade.py | execute 返回真实 dispatch 状态；先前“只改 Work 就称已接管”的路径消失 | T/G |

E07 依赖 C03，C01～C03 只依赖 E05，因此没有 E→C→E 的循环。首条 Python 闭环可在 E07 尚待跨 Agent 场景时完成；恢复是正式完成必验项，不是首条演示的虚假前置。

### 4.6 C：自动证据、验收和落账（C01～C09）

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| C01 | 采集本任务实际差异 | E05 | 拟新增 CORE/evidence_collection_service.py、T/core/test_evidence_collection_service.py | owned paths 外差异拒绝纳入；基线与暂存/未暂存分别记录；不偷收他人修改 | T/G |
| C02 | 自动执行 Python 质量门 | C01 | CORE/evidence_collection_service.py、T/core/test_evidence_collection_service.py | 真实 pytest/Ruff/Mypy 命令和退出码绑定内容 hash；非零不能伪装 PASS | T/G |
| C03 | 自动构造并追加 Checkpoint | C02 | CORE/evidence_collection_service.py、CORE/continuity_execution_service.py、T/core/test_continuity_execution_service.py | 系统生成完整证据；用户不填 result.json；代码/证据被改动后旧验证失效 | T/G |
| C04 | 用户验收绑定最新通过证据 | C03 | CORE/pm_facade_service.py、T/core/test_pm_facade_service.py | 旧 Checkpoint、失败证据、重复验收有明确结果；仅推进 Mission 不算完成 | T/G |
| C05 | 建立 v2 可恢复收口步骤 | C04 | 拟新增 CORE/pm_closure_service.py、T/core/test_pm_closure_service.py；INFRA/continuity_store.py | DB 状态和步骤/outbox 原子落库；不消费 AiHandoffService 或 HANDOFF_CONSUMED | A/G |
| C06 | 证据回填目标 CHG 实质 | C05 | D/auto_pm/domain/change/substance_injector.py、CORE/pm_closure_service.py、T/change/test_substance_control.py | 从验证证据填真实实施/验证字段；SubstanceChecker 无空壳；只改本 CHG | T/G |
| C07 | 精确台账投影和失败重试 | C06 | CORE/pm_closure_service.py、D/auto_pm/domain/change/ledger_reconciler.py、T/core/test_pm_closure_service.py | 复用216匹配；投影失败显示待同步；重复操作无重复事件；必要投影未完成不得最终关闭 | A/G |
| C08 | 按证据闭合Run/Work/Mission | C07 | CORE/pm_closure_service.py、INFRA/continuity_store.py、T/core/test_pm_closure_service.py | 合法顺序推进Run、Work、Mission的对应终态；必要投影完成后才整体完成；重放不重复事件/验收 | A/G |
| C09-R1 | 候选执行根与控制根双根绑定 | C08、E08、G10 | CLI/Facade/运行身份合同及定向测试 | 候选源码从隔离 worktree 实际加载；CHG、Decision、Mission、Work、Run 仅使用 canonical 根 Store；拒绝创建第二本 continuity.db；回执同时记录 execution_root、control_root、候选 commit 与实际加载路径 | A/G |
| C09-R2 | 双根执行链和新文件投影集成补强 | C09-R1 | 候选 CORE/INFRA/执行合同及定向测试；仅 canonical 控制根承载治理 Store | 同仓库外部隔离 worktree 可建 Run，异仓库拒绝；已持久意图仅在原洁净 HEAD 上补建唯一 Run；新增文件有明确缺失基线、成功回执及失败回滚；旧 v1 计划可读；候选身份不冒充 active release；旧提交意图不得跨提交复用 | A/G |
| C09-R3A | 执行准备原子性与有界租约 | C09-R2；目标旧 C09/Q03 Run 已到期并经 Recovery 链结算，或已由 V04-R0 的 Recovery 链证明未启动并撤销 | 候选 CORE/pm_facade_service.py、CORE/execution_adapter_service.py、CORE/execution_microtask_service.py、INFRA/continuity_store.py；T/core/test_pm_facade_service.py、test_execution_adapter_service.py、test_execution_microtask_service.py、test_local_execution_orchestrator.py | 先验证并持久化 execution_root 下的微任务计划，再创建唯一 Run/lease；准备失败不得留下 READY/RUNNING Run 或有效 lease；lease_seconds 为受边界约束的显式合同，不得硬编码 86_400；同仓库外部 worktree 的计划路径可验证，异仓库拒绝；token 不进入 argv、环境、日志、事件或公开回执 | A/G |
| C09-R3B | 跨项目质量证据与现有修复联合收敛 | C09-R3A、C08、V04-R0 的可核验证据 | 历史 `codex/c09-r3b-cross-project-gates` / `codex/c09-convergence` 与现行 `codex/c09-r3b-joint-20260924` 均为隔离候选；仅按有效 Decision 组合 SW008 15＋SW009 12 个精确路径，不扩大为整仓修改 | 每个 owned path 取得所属项目、当前字节与候选身份绑定的真实质量证据；跨项目 pytest/Ruff/Mypy 任一失败即拒绝；创建及续租使用同一有界策略；终态原子释放 lease 并 fencing 旧持有者；保留失败 Run。V04-R0 原 Work、旧 SW008 R3B Work 与新双项目联合质量 Work 均已独立 ACCEPTED，R3B 技术前置已闭合；原业务候选仍为旧字节，本门不替代 R3C/原业务验收 | A/G |
| C09-R3C | 原 VERIFYING Run 的验收权限恢复门 | C09-R3B、V04-R0 的可核验证据；原 Run 的投影、start claim、进程回收/缺失、当前租约与专门批准均经重核 | `CONTRACT/decision_package.py`、`CORE/continuity_execution_service.py`、`INFRA/continuity_store.py`、`CLI/continuity.py` 及定向测试；原 Run 与事件只读保留 | 已验收通过 (ACCEPTED)：专用 Decision `DEC-20260925-C09R3C01` 签发（SHA-256: `d05f6d0d7c922c3e873b6be0def7e2827860ad38352205293c70247975d49ab6`），恢复租约至 `antigravity:c09-verifier`（version 4），epoch/secret CAS 轮换，追加 `VERIFICATION_LEASE_RECOVERED` 事件，Work 恢复 `IN_PROGRESS`、Mission 恢复 `ACCEPTANCE_PENDING`。 | A/G |
| C09 | 第一条 Python 新需求闭环实演 | C09-R3B、C09-R3C 联合验收、C08、E08、G10；原业务 Run 沿合法续接路径完成 | 拟新增 T/e2e/test_pmf_python.py；批准的真实 Python 演练工程；保留 `CHG-SCPT-2026-012` 与原 Run | **PASS / ACCEPTED**：2026-09-25 业务验收终态成立，原 Run `SUCCEEDED`、Work/Mission `CLOSED`、CHG 实质注入、双台账零差异。原 Checkpoint 的覆盖不足永久保留；后续统一不可变候选补足完整技术质量，G10-R1 当前字节治理链闭环并由稳定入口消费，因此 C09/M1 当前验收成立，但不得倒写原 Checkpoint。 | T/A |

2026-09-25 的业务状态机验收事实保留：原业务 `RUN-PLAN-F767C11087531180` 为 `SUCCEEDED`（lease `RELEASED`），原 Work `WORK-MSN-F0564CAF05D18E0B` 与 Mission `MISSION-0648162FF0602FDD` 均为 `CLOSED`；用户验收、实质注入与台账对账记录仍有效。隔离 worktree 承载候选源码与产品改动，canonical 控制根承载唯一 Continuity Store、CHG、Decision 与台账。**2026-09-27 的统一不可变候选由 `a1c5d94` 合法派生至 `8b02de55`，补足技术质量、G10-R1 当前字节治理链及稳定入口消费；原 Checkpoint 覆盖不足仍按原样保留。M1 当前为 `COMPLETED / ACCEPTED`。M2 只能按各原子任务的显式依赖、独立实施卡与当前控制面预检推进，不从 M1 验收外推执行授权。**

2026-09-25 最终验收核对结果：

1. 原业务 Run、ExecutionIntent、投影回执、候选 HEAD（`d89b1269`）与三个 owned paths 当前字节完全匹配；候选工作树严格剔除 24 个越界脏路径。
2. R3B 联合质量证据（两项目 27 文件、六门全绿）与 V04-R0 基础合同此前均已独立 ACCEPTED；R3C 经专用 Decision `DEC-20260925-C09R3C01` 完成 CAS 租约受控恢复，Work 恢复 `IN_PROGRESS`，Mission 恢复 `ACCEPTANCE_PENDING`。
3. 当时记录 `c09-final-e2e` 候选质量门通过；2026-09-27 核对原 Checkpoint 后纠正其覆盖口径：SW009 Mypy 实际仅含生产文件，使用 `--follow-imports=skip`，未覆盖 `tests/test_services.py`，不得再称“五门完整通过、无跳过”。原候选生产与测试两文件 strict Mypy 独立复验为 172 errors / 12 files、Exit 1。
4. 成功追加内容绑定 Checkpoint `CP-SW009-PMF-C09-FINAL-001`（schema `checkpoint-evidence.v2`，quality `PASS`），并获得用户明确验收批准。
5. 通过 `PmFacadeService.accept` 将 Mission 流转至 `ACCEPTED`；通过 `PmClosureService.prepare_closure`、`inject_prepared_change_substance` 将验证与实施实质自动注入 `CHG-SCPT-2026-012`；通过 `complete_closure` 推进 Run 至 `SUCCEEDED`（lease `RELEASED`）、Work 与 Mission 推进至 `CLOSED`。
6. 工作区根入口执行 `ledger reconcile SW-2026-009` 与 `ledger reconcile SW-2026-008` 对账无差异（0 缺失、0 多余、0 不一致）。实际提交预检通过，全过程 0 次人工手写治理 JSON。

历史辅助 Run `RUN-SW008-PMF-C09-CLOSURE-003` 和 `RUN-SW008-PMF-C09R3C-007` 的 FAILED 记录只读保留作审计证据，不改写历史。稳定部署运行时回退加载 1.3.2 归属独立基础设施线 Track A，后续与 M2 推进并行或单独处置。合并、推送、部署和 release 切换仍为独立后续边界。

### 4.7 U：用户界面与 SDK（U01～U08）

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| U01 | 五状态可点击界面原型 | P06、E03、C07 | 拟新增 S/01_项目文档/prototypes/pm-flow-v2.html | 新目标、确认、执行、失败/恢复、验收五场景可达；标明演示数据；按钮/函数/导航无死链 | T/G |
| U02 | QML 输入目标生成真实草稿 | U01、P11 | QML/bridges/pm_cockpit_bridge.py、QML/views/BossCockpitView.qml、QML/boss_main.qml、T/qml/test_pm_cockpit_bridge.py、T/qml/test_boss_cockpit_view.py | Bridge→Facade 实际持久化 `PRE_AUTH` PlanningDraft；显示项目、目标、验收与“范围待规划”，不让用户填内部 ID；未形成真实范围卡前不得虚构范围，批准前不得展示为 Mission；按实施卡 016 五产品路径及独立治理证据门禁验收 | ACCEPTED / `74493c37` / `CP-SW008-M2-U02-002` |
| U03 | 一次确认启动真实任务 | U02、E08 | QML/bridges/pm_cockpit_bridge.py、QML/components/PmConfirmationCard.qml、T/qml/test_pm_cockpit_bridge.py | 连点只启动一次；实际 session 未确认时不显示执行中 | T/G |
| U04 | QML 进度和失败来自真实事件 | U03 | CORE/pm_cockpit_service.py、QML/components/ActivityTimeline.qml、T/core/test_pm_cockpit_service.py | QRunnable/Signal 更新；主线程不阻塞；无伪百分比，失败原因能定位步骤 | T/G |
| U05 | 恢复同一任务与证据抽屉 | U04、E06、C03 | QML/bridges/pm_cockpit_bridge.py、QML/components/EvidenceDrawer.qml、T/qml/test_pm_cockpit_bridge.py | 关闭重开后同 Work/Run；证据匹配当前内容；恢复动作受服务资格限制 | T/G |
| U06 | GUI 验收与待同步状态 | U05、C07 | QML/bridges/pm_cockpit_bridge.py、QML/views/BossCockpitView.qml、T/qml/test_boss_cockpit_view.py | 验收→投影失败→重试→完成可观测；缺必要证据不能点成“已完成” | T/G |
| U07 | 薄 Cockpit SDK | C09 | 拟新增 D/auto_pm/api.py、T/core/test_cockpit_api.py；D/auto_pm/__init__.py | SDK经统一运行身份/Facade从新目标到批准、真实execute、验收落账完整实演；生产初始化不落到editable/母体；不只验import/查询 | T/G |
| U08 | 旧 workflow 接口兼容 | U07 | CLI/workflow.py、拟新增 T/cli/test_workflow_compat.py | 现有命令保留；新 workflow 别名只委托 pm；不能恢复旧写入状态机；未知旧动作明确拒绝 | T/G |

U01 已于 2026-09-27 独立验收：隔离候选提交 `d88eedd5` 仅含 `S/01_项目文档/prototypes/pm-flow-v2.html` 与其静态测试；`CP-SW008-U01-001` 绑定验收前候选字节，Run `SUCCEEDED`、lease `RELEASED`、Work `CLOSED`，`CHG-HMI-2026-001` 为 `completed`。U02～U08 未启动，仍须逐项按实施卡和独立授权推进。

U01 是在现有 PySide6/QML 方案上的交互原型，不换 Web 技术栈。界面核心信息固定为：目标、当前阶段、实际执行器、下一可行动作、证据、验收；复杂内部对象默认折叠。

### 4.7.1 M2 横向治理原子任务

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 状态 |
|---|---|---|---|---|---|
| M2-BL01 | runtime-fix 与 U01 两文件形成唯一不可变集成基线 | active runtime 源 `f4626947`；`main@0d7071b7`；U01 `d88eedd5` | `02_规划/016_M2统一集成基线实施卡_PM.md` 规定的两个 U01 owned paths；独立规划卡/WBS 不进入产品提交 | 候选 `4851fce4` 精确两文件、blob 等同 U01、pytest/Ruff/Mypy Exit 0、候选入口 fail-closed、canonical runtime 无 fallback、Checkpoint 当前；Run SUCCEEDED/lease RELEASED、Work CLOSED、CHG completed | ACCEPTED / CLOSED |
| M2-GOV-IC01 | 实施卡一等合同、模板、校验与 dispatch/verify 工作流 | PM-033 V2.1；`M2-BL01` ACCEPTED | 实施卡 015 的八个产品路径；CHG-338 与 SW008 台账仅作为提交证据路径 | 33 passed；Ruff/Mypy/diff-check Exit 0；`CP-SW008-M2-GOV-IC01-003`；commit `b7bb9357` 恰含十路径；Run SUCCEEDED、Work/Mission CLOSED、CHG completed | ACCEPTED / CLOSED |

产品代码范围与提交治理证据必须分层表达。实施卡建立本身不等于验收；最终仍须新的 Decision、有效 Work/Run、当前字节 Checkpoint、正常 Git Hook 本地提交及合法治理终态。

### 4.8 V：双领域、恢复和模板（V01～V08）

当前进度：V01～V08 尚未作为整体开工，M2 未启动或验收。仅 V04-R0 因 C09 的旧租约阻断提前开展：原 Run 保留 CANCELLED，新同 Work 验证 Run SUCCEEDED、有当前字节 Checkpoint、lease RELEASED，原 Work ACCEPTED、CHG-309 completed；FIX/FENCE 子 Work 各自 ACCEPTED，FENCE CHG completed（非 closed），两次早期 Recovery 仍 FAILED。V04-R0 基础合同已闭合，不等于 V04/V04-R1 的真实进程回收演练完成，也不表示 V 批次整体启动。V01 仅可在 C01/C03 的独立授权及真实 PLC 门禁证据下启动。

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| V01 | PLC 静态质量门插件 | C01、C03 | CORE/evidence_collection_service.py、T/core/test_evidence_collection_service.py | 复用现行 PLC checker；违规 SCL 确实失败；.plc.json/SCL/INT/VAR 证据同基线 | T/G |
| V02 | PLC 新需求静态闭环 | V01、C09 | 拟新增 T/e2e/test_pmf_plc.py；批准的 PLC 演练工程 | 新目标到真实 SCL 变化、静态门禁、验收落账；上机编译/下发单列未执行，不虚报工业运行成功 | T/A |
| V03 | 真实更换 Agent 续跑 | E07、C09 | 拟新增 T/e2e/test_pmf_handoff.py；R 下本场景证据 | 第二 Agent 接同一 Work，旧 owner 后续写入拒绝；无需用户搬 JSON/token | T/A |
| V04-R0 | 租约生命周期、受控撤销与 epoch fencing 基础 | C08、E08 | 候选 lease/执行合同、CORE/continuity_execution_service.py、INFRA/continuity_store.py、CLI/continuity.py；T/core/test_continuity_execution_service.py | 正常 SUCCEEDED/FAILED/CANCELLED 在同一事务释放 lease；提前撤销必须由新的 Recovery CHG/Decision/Work/Run 明确授权，且仅在无 Popen 证据时取消；无法证明 child 回收即 PENDING；撤销/接管提升 epoch，旧 epoch 写入被拒绝；不得直改 expires_at 或泄露 token | A/G |
| V04 | 进程中断/lease 到期恢复实演 | E06、V03 | 拟新增 T/e2e/test_pmf_recovery.py | 杀执行进程、主控重启各实演；到期不冒记成功；取消/续跑有合法证据与幂等事件 | A/G |
| V04-R1 | 受控租约撤销与 fencing 真实进程演练 | V04、V04-R0、C09-R3A | T/e2e/test_pmf_lease_recovery.py；R 下真实本机场景证据 | 短租约心跳续租；已启动进程先以 PID/job 指纹证明回收，否则 PENDING；每次接管提升 lease epoch，旧 epoch 的回写被拒绝；不得直改 expires_at、泄露 token 或抢占未知进程 | A/G |
| V05 | GUI 双领域联合验收 | U06、U07、V02、V04 | 拟新增 T/e2e/test_pmf_gui.py；R 下截图/事件证据 | Python/PLC 各从GUI输入目标到验收；两次业务决策；真实进程/静态检查；无人工改库 | T/A |
| V06 | 双 Hook 与坏证据负向实演 | G06、C09 | 拟新增 T/e2e/test_pmf_gate_failures.py；隔离 Git 测试仓 | 错 CHG、坏台账、空壳证据、越权文件、预检异常分别拒绝；不得破坏真实用户项目来造测试 | T/G |
| V07 | 从通过的 Python 基准提取模板 | C09 | D/auto_pm/templates/python_cockpit 中基准确定的最小文件清单；拟新增 T/e2e/test_pmf_template_python.py | 先固定活体基准 commit/测试，再提模板；生成第二个新工程复测；不能用预制空壳替代 | T/G |
| V08 | 从通过的 PLC 基准提取模板 | V02 | 母体实际 PLC Copier 模板中基准确定的最小文件清单；拟新增 T/e2e/test_pmf_template_plc.py | .plc.json/INT/VAR/门禁生成后完整；字段错误真实被拒绝；不擅改 O 正式规范 | T/G |

演练目标优先复用已存在的 SW-2026-010、DJ-2026-011，确认其所属和用途后固化精确路径。它们不是运行前假定有效的资产；若不可用，则以 SW-2026-009/DJ-2026-005 的固定只读基准创建隔离演练副本并纳入 V 批次，不默认修改真实业务项目。

V07/V08 的模板文件清单由已经验收的基准差异机械提取；这是依赖于前序产物的确定输入，不是执行代理随意选整棵 templates。基准不通过时停在本原子，不传播模板。

### 4.9 D：稳定交付（D01～D09）

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| D01 | 日常指引和薄适配引用 | V05、U08 | S/01_项目文档/36_驾驶舱与双技术栈日常迭代操作手册_PM.md、AGENTS.md、.agent/rules/project-rule.md、.cursor/rules/workspace-ai-coexistence.mdc；.trae 两执行技能仅在明确授权时纳入 | 所有操作指向已验证高阶入口；技能不手工填表；无死链/双真源；pm-workflow 继续隔离 | L/T |
| D02 | 实现可复现构建入口 | G10 | 拟新增 D/scripts/pmf_build.py、T/core/test_pmf_build.py | 固定Git输入构建载荷，拒绝dirty或缺失依赖；同输入两次清单相同；此源码在D03冻结前完成并验收 | T/G |
| D03 | 固定最终母体提交集合 | D01、D02、Q01～Q03、V06～V08、G03～G10 | 批准路径的 Git 提交；R 下最终源码清单 | 所有必需源码/测试/模板都可从固定 commit 检出；没有只在本机未跟踪文件中的依赖 | T/G |
| D04 | 构建不可变候选 | D03 | 只调用D03提交中已有D/scripts/pmf_build.py；R/artifacts/PMF-20260912/release/ | 相同 commit 两次构建载荷清单一致；manifest/依赖/读写 schema 兼容齐全；尚未 active | T/G |
| D05 | 候选全量门禁 | D04、Q01～Q03 | R/reports/PMF-20260912/D05/ | 按§8.2实际跑必需集合；缺任何项不得发布；全库审计原始失败单列且不得称全绿 | T/G |
| D06 | 新旧版本与数据回退演练 | D05 | 隔离数据副本与候选/previous；R 下证据 | 回退程序保留新事件；不兼容写入拒绝；不拿旧 DB 备份覆盖发布后新事务 | A/G |
| D07 | 受控安装并切换有效版本 | D06；部署范围已批准 | C 的 manifest/新 release/active/previous；实际 Hook 安装映射 | 根 CLI/GUI/Hook/SDK 真实加载同一已验证制品；失败恢复本次指针/脚本，不改母体和业务库 | A/G |
| D08 | 连续三次真实日常交付 | D07 | R 下三次任务与验收证据 | 至少一次 Python、一次 PLC 静态、一次跨会话恢复；每次从新目标开始且无人工改库/治理 JSON | T/A |
| D09 | 项目级最终交付判定 | D08、全部 AC | 本文验收区和 S 中项目交付记录 | 列出实际发布、所有必需 AC/提交、明确历史队列；未达成的承诺不得移出验收表求关闭 | A/G |

D08 用三次可重复任务验收替代“等三天看一看”。无需新增定时器或让用户等一个未定义的观察期；真实日常使用反馈仍可在后续独立迭代接收。

### 4.10 H：有限历史队列（H01～H10，不作全局前置）

| ID | 单一交付 | 依赖/触发 | 精确对象 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| H01 | 固化过期 Run 结算候选 | G07；需要结算时 | CORE/continuity_execution_service.py、CLI/continuity.py、CLI/decision.py、T/core/test_continuity_execution_service.py | 复用现有 settle_expired_run；独立恢复 CHG/Work/Run、目标 Decision、CAS/到期/scope 在克隆库通过；只用合法 CANCELLED，不伪成功 | A/G |
| H02 | 处置 R4-215 的单一过期 Run | H01；目标处置已批准 | RUN-SW008-R4-215-IMPL-01 | 沿用已有中断事实，恢复链自身可终态；CHG215未完成安全目标转 E04，不重开另一产品计划 | A/G |
| H03 | 处置 SAFE004 的单一过期 Run | H01；目标处置已批准 | RUN-SW008-SAFE-004-ACL-01 | 只结算该 Run，不触碰旧 release ACL；未做的 ACL 工作仍保留真实待办 | A/G |
| H04 | 结算A2目标04 | H01；目标处置已批准 | RUN-SW008-A2-201-04 | 只处理该过期非终态Run；CAS/事件可核验；不覆盖母Work已有验收 | A/G |
| H05 | 结算A2目标03 | H01；目标处置已批准 | RUN-SW008-A2-201-03 | 同H04机制、独立目标/幂等键；不夹带其它Run | A/G |
| H06 | 结算A2目标01 | H01；目标处置已批准 | RUN-SW008-A2-201-01 | 同H04机制；已终态则只返回幂等证据，不重复写 | A/G |
| H07 | 判断REC-001的真实剩余范围 | 本轮记录可用 | WORK-SW008-REC-001、RUN-SW008-REC-001-06 | 比对原授权/证据：已完成才收口；否则保留具名剩余项；Run成功不代替Work验收 | A/G |
| H08 | A2工作树处置 | H04～H06；目录处置已批准 | git worktree list 中对应 codex/a2-pm-facade 的精确物理路径 | 无有效占用、独有提交/忽略资产保全后才退役；达不到条件则登记保留理由；禁止git clean | T/G |
| H09 | 已批准文档归档闭环 | 既有归档授权仍有效 | 既有PMF-20260912归档清单的9组源/目标与引用 | 已移动不重复移动；源/目标hash/引用核验后独立提交该清单；不把后续发现混入归档 | T/G |
| H10 | wbs8-candidate用途定性 | 本轮事实可用 | 实际wbs8-candidate目录及其现有索引记录 | 判明普通目录/候选资产而非Git工作树；明确保留/隔离标签；不在其中错误向父Git写入 | T/G |

H01先核对上述五个Run是否仍为原状态/版本；任何已变化目标单独退出，其它获批目标继续。恢复Run自身也必须有合法终态回执。历史CHG161～164格式、旧release ACL、远端同步不扩成此队列的额外原子。

### 4.11 里程碑、依赖与第一张执行卡

| 里程碑 | 范围 | 用户拿到的结果 | 退出标准 |
|---|---|---|---|
| M0 交付通道恢复 | B01～B10、G01～G10 | 216 可提交；后续任务知道用什么代码、检什么范围、在哪执行 | 历史完成记录保留；2026-09-27 只核到 B10 `ACCEPTED`、B218 `CLOSED`、G10 后续 Work `ACCEPTED`，未逐项重演双 Hook 与集成候选，当前完整复验 `UNVERIFIED`。 |
| M1 第一条可用 PM-Flow 候选 | P01～P11、E01～E08、C01～C09、G10-R1 | CLI在候选环境完成真实Python新任务；内部对象和证据由系统生成 | **COMPLETED / ACCEPTED**：历史业务终态与台账成立；统一不可变候选最终为 `8b02de55`，完整技术门 PASS；G10-R1 当前字节 Checkpoint、SUCCEEDED/RELEASED Run、CLOSED Work 与 CHG-328/329 终态成立；release `1.3.3-8b02de5` 可重复构建、前切换/回退演练和 exact-tree 验证通过，根入口 configured/effective/load path 一致且无 fallback。原 C09 Checkpoint 局限保留，不回写历史；main 尚未合并。 |
| M2 驾驶舱与双领域候选 | U01～U08、V01～V08 | GUI、SDK、PLC、跨Agent、故障恢复在候选中走同一条链 | V05/V06真实正反验收；模板源于实演基准 |
| M3 稳定使用 | Q01～Q03、D01～D09 | 根入口稳定运行，三次真实任务可重复交付 | 全部 AC、制品一致性、兼容回退、全量门禁与 D08 均有证据 |

主依赖：
~~~text
B01 -> B02 -> B03 -> B04 -----> B06 -> B07 -> B08 -> B09 -> B10
               \-> B05 ------/
B09 -> G01 -> G02
        \-> G03 -> G04 -> G05 -> G06
B09 -> G07 -> G08/G09
G06 + G08 + G09 -> G10 -> G10-R1
G10 -> P01 -> P02 -> P03 -> P04 -> P05 -> P06 -> P07 -> P08 -> P08-R -> P09 -> P10 -> P11
G10 -> E01; P09 + E01 -> E02 -> E03 -> E04/E05 -> E06
E05 -> C01 -> C02 -> C03 -> C04 -> C05 -> C06 -> C07 -> C08
C03 + E06 -> E07; E05 + P11 -> E08
C08 + E08 + G10 -> C09-R1 -> C09-R2 -> C09-R3A -> C09-R3B -> C09-R3C -> C09 -> U/V -> D
G07 -> Q01/Q02/Q03 -> D03 -> D04 -> D05
~~~

V2.0 的第一张执行卡为 B 批次；其历史输入、输出和批准边界保留如下，不能作为 2026-09-13 的当前启动指令：

- 输入：当前 HEAD、216 暂存两文件及已验收证据、SAFE-007 单个差异、当前双 Hook。
- 输出：限定投影修复证据、真实双 Hook 通过、216 两源码隔离提交、独立治理记录集合。
- 批次需要新增声明：允许固定哈希非活动管理候选；允许本次 SAFE-007 投影单元格写入；允许补齐216治理正文；这些不属于之前两代码文件的实施 scope。
- 机器对象：由主控使用现有服务生成恢复 CHG/Decision/Work/Run，明确选定 Work/Run，内部持有有效 lease；不需要先完成 H。
- 原子顺序：B01～B10，内部常规检查/克隆/重试不再逐项问用户。
- 2026-09-19 历史审计投影：P01～P11 均已有最终 ACCEPTED Work、SUCCEEDED Run 与 Checkpoint；P08-R 已以 `e2cb0787e246b0d462f26e2c6bbd5be64ff266d6` 闭合 Mission 的最小 WBS 子 Work 授权，P11 已形成隔离提交 `50a929ccb60de32365fafe0f1819c9c195401656`。P 链从 G10 集成提交 `d87fd3d68222a27850530a14ec1ac452b467be87` 连续可达至该 P11 提交，尚未合并到根 `main`。当时 B218 Work 为 VERIFYING；最新 canonical 核验已是 CLOSED、Run SUCCEEDED、Checkpoint 存在，见 §1.3。该历史审计不授予 C09 恢复执行权。

## 5. 资源分配

### 5.1 每个模型承担什么

模型定位参考本会话已经打开的 OpenAI 官方模型说明；下表是本项目工程分配，不是模型性能保证或账单预测。

| 简称 | 推荐用途 | 约束 |
|---|---|---|
| A | GPT-6 Astra 高推理；架构、候选集成、恢复范围、CAS/事务、最终验收 | 负责边界与反证，不替代机器门禁，也不在明确代码票内擅自扩大整改范围 |
| T | Terra Ultra；一般代码、测试、CLI、QML、构建和明确的恢复算法实现 | 216 继续复用；模型名字和推理档在 Run 记录，不从 UI 名称猜启动模型 |
| G | GPT-5.5 xhigh；独立读差异和失败证据、反证关键事务 | 不代替机器门禁；不让复核者自行扩大整改范围 |
| L | Luna high；已确定映射的日常指引与证据索引 | 不独立处理 DB、lease、Hook、发布或授权 |
| Spark | 可选：已定位的1～2文件文案/命名微修 | 不负责整个WBS包，也不为“每个模型用一下”制造交接 |

A/T 的推荐依据分别是复杂推理与端到端工作、能力成本平衡。G06 和 Q01/Q03 由 Terra Ultra 执行、GPT-5.5 xhigh 独立复核；G10 与 Q02 由 Astra 负责候选边界和运行环境判定。Ultra 是否可用以当前客户端/执行器能力为准；执行器不支持该档时明确报错或使用批次预先允许的替代，不能静默升级费用或换模型。

### 5.2 派工与执行上下文

每个票据只带：WBS ID、用户批准引用、CHG/Decision、选定 Work/Run、完整 owned paths、输入 hash、单行为目标、验收命令、失败边界。批准对象和运行凭据由系统维护，不要求用户复制粘贴。

先单写者、一个执行 Agent、一个只读复核者。只读审计或互不重叠的独立模块可以并行；CORE/pm_facade_service.py、INFRA/continuity_store.py、QML/bridges/pm_cockpit_bridge.py 的写入串行。

同一问题两次失败后，复核者收到的是最小复现、diff 和原始失败，不是整个历史文件夹。模型切换延续同一 Work，按协议建立新 Run/接棒，不再复制一个同名工作项目。

## 6. 风险管理

### 6.1 失败归属和停止范围

| 失败类别 | 处理者及动作 | 能否阻断主线 |
|---|---|---|
| 本原子实现/测试不合格 | 执行者在批准路径内修复；两次同因失败由主控复盘 | 阻断本原子及依赖它的任务 |
| 精确目标已被其它 owner 修改 | 保留现场，主控裁定当前对象和基线；未依赖任务可继续 | 只阻断竞争对象 |
| 已知历史文档格式/旧ACL/远端差异 | 记录到既有 CHG 或 H 的明确条目；不写历史求全绿 | 未证明影响本交付即不阻断 |
| 新的发布必需失败 | 在本批范围内修复；确需范围变化时给出一份最小替换方案及影响 | 阻断对应里程碑，不能删验收条件 |
| 无法启动实际执行器 | E01报告真实错误；其它已授权开发可继续；具名人工接力仅作开发手段 | 真实自动执行验收仍阻断，不能假报完成 |
| 执行环境与普通命令结果不同 | 先用真实控制面函数和同一候选对照；记录环境、argv、HEAD、脏路径与诊断。只有稳定复现并影响产品合同才另列原子范围 | 只阻断当前 Run；不作为候选配置补丁或全局历史清理理由 |
| 真实投影恢复集合扩大 | B06零写退出；固定输入和候选，主控检查为何漂移 | 阻断B06，不自动改全部台账 |

“发现截止”限制当前批次的 scope，不意味着停止报告新事实。每个新事实必须回答它破坏哪一项已定验收；没有这个关联就进入下一轮候选，不形成另一个无限前置计划。

### 6.2 回退约束

B 的文件写入前保留内容备份、hash 和操作事件；补偿仅在目标仍为本次写出的 hash 时执行。G02 安装只备份/恢复两 Hook，不改变 Git 历史。源码失败保留候选 worktree 与证据，禁止 reset/clean/stash 他人改动。D06/D07 回退程序和指针，不自动覆盖已产生新事件的数据库。

读取 SQLite 要考虑 WAL；在线一致副本使用只读连接和 SQLite backup 机制，不把正在变化的 db 主文件单独复制当完整快照。报告不打印租约秘密。正式 verify-only 对被检业务文件保持无写入；需要输出报告时写专用证据目录并明确这项诊断副作用。

## 7. 沟通计划

本轮已经完成方案修订授权内的工作。后续对一个写入批次给用户的是完整范围卡，不是“是否允许我再检查一下”。技术负责人负责准备机器对象及脚本参数，不让用户从多个恢复方案中承担技术选型。

| 时点 | 用户看到的内容 |
|---|---|
| 批次首次开工 | 单一推荐、全部内部原子、精确范围、验证和必要风险动作 |
| 普通执行期间 | 当前可用能力及关键结果；同范围测试/重试自动推进 |
| 真正越界或外部风险变化 | 一个汇总决策：发生什么、影响哪个验收、最小调整是什么 |
| 里程碑验收 | 可重复操作、机器证据、实际未通过项；不把代码验收称运行生效 |
| 提交/发布 | 使用已有明确批准；新增范围一次列清，不重复索取已授予的权限 |

计划、执行、验收和发布状态分别显示。旧39、归档37和其它历史WBS只作引用，本版是当前产品排期入口；26继续提供治理边界。新聊天只需本文件、当前WBS ID及系统Checkpoint，不能靠聊天记录重建第二账本。

## 8. 验收标准

### 8.1 固定验收场景

| AC | 必须通过的行为 | 主责 | 最终所需证据 |
|---|---|---|---|
| AC01 | 新PID+目标生成方案，无需预先手造内部对象 | P11 | 入口调用、PlanningDraft/范围卡hash、0次用户手写JSON |
| AC02 | 同一确认重放/中断重试不重复授权 | P10 | 每持久化边界失败注入、对象数量与事件 |
| AC03 | 实际执行进程启动 | E03/E08 | actual model、session、进程身份、真实启动回执 |
| AC04 | 失败退出不因文字“成功”变成成功 | E05 | 0/非0/终止三类实演 |
| AC05 | 差异和门禁证据绑定当前内容 | C03 | 命令/cwd/版本/hash/Exit Code；坏证据拒绝 |
| AC06 | 验收后正确CHG与精确台账落账 | C07/C09 | 无占位字段、目标零差异、相邻编号未改 |
| AC07 | 投影写失败可重试且不重复结算 | C05/C07 | 崩溃点/权限错误演练、待同步状态、幂等事件 |
| AC08 | 重启、到期、真实换Agent可恢复 | V03/V04 | 同Work续跑、旧owner拒绝、恢复自身终态 |
| AC09 | CLI/GUI/SDK行为与权限一致 | U07/V05 | 三入口共享Facade/运行身份的联测；U07提供SDK完整闭环，V05提供GUI实演 |
| AC10 | Python与PLC静态新任务完成 | C09/V02/V05 | 两领域真实差异、领域门禁、验收/落账；硬件未测明确 |
| AC11 | 双Hook与scope防御真实有效 | V06 | 正常放行；伪号/坏账/异常/越权均拒绝 |
| AC12 | 已验证模板与薄技能可复用 | V07/V08/D01 | 活体基准→模板→第二工程；规则与指引无死链 |
| AC13 | 可复现制品、入口一致、回退保留数据 | D04/D06/D07 | commit、manifest、实际加载路径、schema兼容 |
| AC14 | 连续三次无需人工修治理对象 | D08/D09 | 三条完整任务记录，至少含Python/PLC/跨会话 |

所有 AC 均为必需。研发阶段已实现不代表稳定环境已通过，D09只在部署和日常使用证据齐全后判定产品完成。

### 8.2 开始时就确定的门禁合同

执行与发布使用下表，不再用一句“全量全绿”遮蔽实际范围。这是修订方案中的显式合同，须进入批次批准；不是把现有失败擅自改为 PASS。

| 门禁 | 每原子/批次 | 最终候选 | 判定 |
|---|---|---|---|
| 本行为与受影响组件测试 | 每原子必跑 | 全部纳入回归 | 必需 Exit 0，无新增 skip 或硬编码成功 |
| 母体全量 pytest | G07跑基线；Q01/Q02 和公共状态机改动后复跑 | D05必跑全量 | 必需 Exit 0；既存skip逐项列明，覆盖必需AC的skip不能豁免 |
| Ruff/Mypy | 本次变更文件及其必要依赖 | D05对产品批准范围、依赖和新增代码再跑 | 必需 Exit 0；不能排除本次实际影响路径求通过 |
| 全库 Ruff/Mypy 审计 | G07固定全库原始结果/诊断指纹 | D05以相同配置重跑 | 所有FAIL如实展示；既存且不在交付依赖的债独立记录；新增或恶化项必须解决 |
| CHG/文档实质与引用 | 目标CHG、改动文档、模板生成产物 | 全部交付工件 | 必需无占位/死链；历史未改文档结构告警不冒充本次PASS |
| Git双Hook | B08实际预检；G后每批预检 | 所有实际提交及安装后复测 | 必需真实通过，无绕过；作用域变化仅按G05批准合同 |
| Run 执行就绪 | 每个源码 Run 创建前执行真实控制面快照 | G10、D05复核记录 | 控制面以实际候选返回一致 HEAD、空闲路径事实和无诊断退出；环境差异未定位前不得用本地配置补丁掩盖 |
| 台账 | 当前任务及所属项目 | 发布时全部注册项目 | 缺项/悬空/状态差异都为0；任何异常非零 |
| Release/schema/加载身份 | 相应候选 | D05～D07必跑 | 实际commit/manifest/代码路径/读写兼容一致 |
| 真实E2E与GUI | 对应C/U/V原子 | D05/D08复核 | 无进程PoC、无GUI实演、无PLC静态链任一缺失都不能称交付 |

全库审计不是最终产品“全工作区零债”的承诺。发布必需集合包括全部母体回归、实际交付依赖的静态检查、全部发布台账和所有AC；如果历史诊断落在实际交付依赖内，就必须纳入本范围修复，不能以“历史债”排除。若用户要求全仓所有项目类型错误清零，那是单独的明确扩大目标，不与 pm-flow 可用性混写。

G07 已知失败的闭合归属固定为：Q01 处理候选中 Vartable 真实样例可复现性，Q02 处理 Qt PDF 导出运行环境，Q03 处理 Mypy 模块发现。历史 CHG 格式告警不属于三项，也不作为 G06、Q 或 D05 的通过条件。每项必须保留原始失败指纹和新的命令证据；不得通过扩大忽略规则、删断言或把失败改标记为历史而获得绿灯。

### 8.3 可直接使用的现有命令

以下命令本轮已由现有源码/帮助确认；不在真实环境执行带修复参数的命令来验证产品。

~~~powershell
# 工作区根，只读恢复；默认多任务时由主控明确选择。
& .\.venv\Scripts\python.exe -B -I .\main.py pm resume SW-2026-008 --json
& .\.venv\Scripts\python.exe -B -I .\main.py pm resume SW-2026-008 --work-id <已选Work> --run-id <已选Run> --json

# 工作区根，只读台账；此命令不会纠正差异。
& .\.venv\Scripts\python.exe -B -I .\main.py ledger reconcile SW-2026-008

# 在研发候选 D 工作目录，用工作区 .venv 解释器运行216目标回归。
& <工作区Python绝对路径> -B -m pytest tests/change/test_ledger_updater.py -q -p no:cacheprovider -o addopts=
& <工作区Python绝对路径> -B -m ruff check --no-cache auto_pm/domain/change/ledger_updater.py tests/change/test_ledger_updater.py
& <工作区Python绝对路径> -B -m mypy --no-incremental auto_pm/domain/change/ledger_updater.py
~~~

占位符由系统从所选 Work 和 workspace context 代入，不交给用户手填。实际执行命令必须记录完整 argv/cwd/被测hash；秘密不进入 argv。pytest 日志/缓存/覆盖率写专用目录或禁用，禁止污染 release exact-tree。

D02 的 pmf_build.py、G06 增强预检、P11 的新目标参数、U07 的 Cockpit SDK 是拟建接口。它们须先完成对应原子和帮助/行为测试，才能作为后续派工的实际命令。活动1.3.3不提供 settle-expired；H 的恢复不能复制该命令到现行 root 后期待成功。

## 9. 附件

### 9.1 依据

- [用户指定的历史需求蓝图](archive/G1-20260909/Cockpit_OS_大一统集成与超级特种兵架构方案_WBS.md)：读取产品需求，不执行其中旧入口/技能指令。
- [26 治理基线](26_SW-2026-008_治理恢复与连续性重基线总计划_PM.md)：真源及权限边界。
- [36 日常操作手册](36_驾驶舱与双技术栈日常迭代操作手册_PM.md)：领域交付、Work/Run及分范围验证。
- [38 既有恢复证据](38_Cockpit_OS_工作区恢复与单主线收口报告_REP.md)：历史工作树和恢复依据。
- [归档37](archive/PMF-20260912/37_Cockpit_OS_超级特种兵大一统目标架构与迁移总方案_PM.md)：已有资产复用，不重开旧排期。
- [39 V1.0.0 历史快照](archive/PMF-20260912/39_PM-Flow_恢复与可用化总方案_WBS_PM_V1.0.0.md)：仅用于比较本次修订。
- O/01_项目管理域/02_规划阶段/027_迭代项目计划模板_PM.md：沿用九节结构。
- O/01_项目管理域/02_规划阶段/033_功能模块迭代流程标准_PM.md：真实验证、源码基线、授权、发布。
- O/01_项目管理域/04_变更管理/042_通用变更管理流程规范_PM.md §3.7：CHG/Decision与Work/Run边界。
- [OpenAI模型定位](https://developers.openai.com/api/docs/models)、[模型指导](https://developers.openai.com/api/docs/guides/latest-model)：本会话已实际打开；具体WBS分配由本计划承担。

### 9.2 本轮修改范围和可验证状态

本轮 V2.5.0 仅修订主工作区本39文件中的真实进度、C09 收敛门槛、依赖和版本记录。V1.0.0 历史快照及隔离候选 V2.4.8 保留原样；未改产品源码、Continuity 数据库、Hook、release 指针、CHG/Decision/Work/Run 状态或隔离候选。`SW-2026-009` 的未提交 `CHG-SCPT-2026-012` 原样保留，其 approved 状态和未完成验证结论分别陈列，不能以文档修订代替业务验收。

V2.5.1 只同步本轮新核实的 V04-R0、R3B 和旧 `app.db` 事实及 §4.8/V 批次启动门槛；保留原备份、未提交候选、FAILED Run 与 `CHG-SCPT-2026-012`，不据此改动 canonical 状态或宣告任何业务验收。缺失的 JSON 处置回执与未建立的独立验收均明列为未通过，不通过文档补记为已完成。

V2.5.2 只将本轮单目标 FENCE 验收结果写回 WBS 当前投影；保留 FIX、R3B、R3C、原业务及旧 `app.db` 证据门的独立状态，不从台账的共用“已关闭”标签推断 CHG 已 `closed`。本 WBS 修订不授权其它状态流转。

V2.5.3 只将 FIX 子 Work 的独立验收写回 WBS 当前投影；原 V04-R0 Work、CHG-309 整体、R3B/R3C、原业务与旧 `app.db` 证据门不随之关闭。候选源码和测试仍未提交，不把 Work 验收解释为提交、合并或发布授权。

V2.6.2 仅同步唯一 M1 不可变候选的真实质量证据，并新增 G10-R1 生命周期/Resume 收敛任务。它不新建或流转 canonical 治理对象，不改历史 Checkpoint、P2/CHG-323、release 指针或稳定部署，不授权批量处置历史 BLOCKED Work，也不把候选 PASS 写成 M1 正式完成。V2.6.3 随后以独立 CHG/Decision、当前字节治理证据链、可重复 release、回退演练和根入口身份验证完成 M1 收口；该收口仍不授权 main 合并、P2 历史清理或 M2 执行。

复核项：95 个原子编号唯一；补齐既有 P08-R 的任务行，C09-R3B/R3C 位于 C09 前且不逆转原业务 Run 的历史；G10-R1 位于 G10 后并成为 M1 正式治理验收前置；所有依赖均指向存在的编号且无环；所有 REQ/AC 有责任任务；PlanningDraft 与 Mission 的安全边界、G06 的输入合同、G10 集成边界和 Q01～Q03 的最终门禁归属明确。文档校验只证明计划结构完整，不代替产品验收。

### 9.3 版本修订记录

| 版本 | 日期 | 改动 |
|---|---|---|
| V1.0.0 | 2026-09-12 | 初始25工作包，恢复前置过长、粒度不均、真实提交入口验证过晚 |
| V2.0.0 | 2026-09-12 | 纠正当前事实与Hook因果；80原子、4产品里程碑、限定bootstrap、显式对象选择、门禁合同、历史旁路和完整需求验收映射 |
| V2.1.0 | 2026-09-13 | 按实际 G06 启动演练补充真实执行就绪门；把 G06 的同一 index 快照合同扩至 enforcer；新增 G10 候选集成与 Q01～Q03 已冻结基线失败收敛；更新当前执行入口 |
| V2.1.1 | 2026-09-14 | 修正 G10 的 Run/Checkpoint 顺序：不可变提交先装配为最终、洁净的非活动候选，Run 再以该 HEAD 启动；保留首次 G10 基线漂移阻断作为审计证据，不改产品源码、来源候选或 release。 |
| V2.2.0 | 2026-09-14 | 修正 P02 先建 DRAFT Mission 与既有强授权 Mission 合同的矛盾；新增独立、不可执行、可幂等持久化的 PlanningDraft，将真实 CHG、规范、范围卡、Decision、Mission、Work 重排为 P02～P11，并同步全部下游依赖与验收映射。 |
| V2.3.0 | 2026-09-14 | 根据 P08-R 的闭合证据补全强授权 Mission 的子 Work 类型契约：仅允许 WBS，明确拒绝其它类型；将 P08-R 设为 P09 的唯一新增门禁，并更新主线与当前推进投影。 |
| V2.4.0 | 2026-09-14 | 根据 P11 冷启动重放失败的根因证据，将 Facade 及其回归测试纳入 P11 四路径范围；要求 CHG 离开 DRAFT 后仍能以相同 request_id 与输入恢复同一范围卡和唯一授权链，不在 CLI 建立旁路。 |
| V2.4.1 | 2026-09-19 | B01～P11 只读审计后同步执行投影：P01～P11 已验收并以 `50a929c` 固定 P 链隔离提交锚点；保留 B02～B09 汇总 Work 仍为 VERIFYING 的事实，不修改原子合同、产品源码或运行态。 |
| V2.4.2 | 2026-09-21 | 根据 C09 候选实演的运行身份与单一 Store 复核，新增 C09-R1 双根绑定前置；不改变 M1 范围、里程碑顺序或发布边界。 |
| V2.4.3 | 2026-09-21 | 根据实际外部隔离工作树 Run 创建失败、旧意图无 Run 与新文件投影合同，新增 C09-R2 并明确 C09 依赖；保留 R1/R1a 历史验收与旧意图，修正原子任务计数。 |
| V2.4.4 | 2026-09-21 | 根据 C09/Q03 的执行准备与长租约失败，新增 C09-R3A：计划持久化先于 Run/lease、有界可配置租约及启动前失败无残留；新增 V04-R1：受控撤销、进程证明与 fencing 的独立系统级验收。不改旧 Run、数据库、产品源码、release 或部署。 |
| V2.4.5 | 2026-09-23 | 根据真实 24 小时 C09 租约阻断，将租约生命周期、Recovery 撤销和 epoch fencing 前置为 V04-R0；C09-R3A 可经 V04-R0 的无 Popen 证明恢复。V04-R1 保留真实进程回收演练。不改历史事件，不以系统时间或直改数据库绕过。 |
| V2.5.0 | 2026-09-23 | 只读对照主工作区、C09 隔离候选和 canonical 数据库后，将原业务 VERIFYING/未验收、两条辅助 Run FAILED、R3B/R3C 未闭合及 V04-R0 未闭合写入当前投影；将跨项目证据、租约、越界脏路径差异、原 Run 验收权限和 CHG/台账设为 C09 联合收敛门槛。本轮只修订 WBS。 |
| V2.5.1 | 2026-09-24 | 重核 V04-R0 原 Run CANCELLED、FIX/FENCE 的 SUCCEEDED Run 与同头 Checkpoint、两个 VERIFYING Work 和待独立验收，以及两次 FAILED Recovery；核实旧 `app.db` 原字节备份哈希和当前 HEAD blob 一致，但处置 JSON 回执缺失、C09FE/FINISH Runs FAILED；明确 V01～V08/M2 未整体启动，保留 C09 联合收敛阻断。仅更新 WBS 事实。 |
| V2.5.2 | 2026-09-24 | 用户仅验收 `CHG-SAFE-2026-012` 的单目标 FENCE；受控流转使对应 Work 为 ACCEPTED、CHG 为 completed（非 closed），台账对账 0 差异。FIX、R3B、V04-R0 整体、原 C09 与 M1/M2 未因该验收通过。 |
| V2.5.3 | 2026-09-24 | 对 V04-R0 FIX 独立核验：当前候选字节与同头 Checkpoint 一致，补做 10 个相关定向用例及 FAILED/CANCELLED 临时隔离验证；仅 `WORK-SW008-PMF-V04R0FIX-001` 流转 ACCEPTED，`CHG-SCPT-2026-309` 为 implementing，原 V04-R0 Work 与 C09/M1/M2 均未验收。 |
| V2.5.4 | 2026-09-24 | 对原业务候选旧 `app.db` 的备份、原会话输出、Decision 范围与当前/HEAD 字节作限定补充证据裁决；原始 JSON 回执仍缺失，不追认失败 Run 或 C09 验收。 |
| V2.5.5 | 2026-09-24 | 独立复核 R3B：既有 SW008 Checkpoint/Decision 不覆盖 SW009；原业务候选 SW009 strict Mypy exit 1（201 项），故联合门继续阻断。 |
| V2.5.6 | 2026-09-24 | 在新隔离候选完成 SW009 12 文件 strict Mypy 修复并独立核验自动 Checkpoint、Run/lease、Work、CHG 与台账；保留原业务候选的旧字节、R3B 跨工作树联合门和 R3C/C09/M1 阻断，更新根 launcher 的真实 active 加载事实。 |
| V2.5.7 | 2026-09-24 | 将 SW008 15 与 SW009 12 个已验收差异机械组合到同头隔离候选；同一候选两项目六项真实门禁、自动当前字节 Checkpoint 与额外 SW009 测试文件 strict Mypy 均通过；联合质量 Work ACCEPTED、Run SUCCEEDED/lease RELEASED、CHG-317 completed、SW008 台账零差异。旧 R3B 总 Work 与 V04-R0 原 Work 未闭合，原业务候选/Run、R3C、C09/M1 均不外推。 |
| V2.5.8 | 2026-09-24 | 在原 V04-R0 Work/Decision 范围内补同候选验证 Run/自动当前字节 Checkpoint，完整核心 129 passed、Ruff/Mypy exit 0，原 Work ACCEPTED、CHG-309 completed；原取消 Run 与失败 Recovery 均保留。结合已通过的 SW008＋SW009 联合质量证据，旧 R3B Work 的 Checkpoint 重核 current=true 后独立 ACCEPTED。CHG-310 仍 implementing，原业务候选字节、R3C/C09/M1、合并/发布边界均未改变。 |
| V2.5.9 | 2026-09-25 | 独立只读审计与物理验证：确认稳定部署回退加载 1.3.2 且 1.3.2 上下文存在 release_id 谎报（归独立基础设施线 Track A）；完成 c09-final-e2e 与 c09-r3b-joint-20260924 字节比对与 diff 矩阵，证实 FE 独有 test_pmf_python.py 在 JT 环境实测 exit 0；定性 09-25 凌晨旁路测试候选；确立受控推进方案。 |
| V2.6.0 | 2026-09-25 | C09 业务端到端闭环与 M1 正式达成：专用 Decision DEC-20260925-C09R3C01 恢复原业务 Run 验收租约，清洗 c09-final-e2e 候选至 3 owned paths，五门全绿；记录 Checkpoint CP-SW009-PMF-C09-FINAL-001，经用户明确批准；通过 PmFacadeService.accept 与 PmClosureService 闭环流程，CHG-SCPT-2026-012 完成实质注入；RUN-PLAN-F767C11087531180 终态 SUCCEEDED（租约 RELEASED），WORK-MSN-F0564CAF05D18E0B 与 MISSION-0648162FF0602FDD 终态 CLOSED；SW-2026-009/008 台账 0 差异；M1 标记 COMPLETED / ACCEPTED。 |
| V2.6.1 | 2026-09-27 | 独立复验校准：保留 V2.6.0 业务状态机及用户批准历史，但纠正“五门全绿”的覆盖口径；原 CP 的 SW009 Mypy 使用 `--follow-imports=skip` 且漏检测试，原候选 strict 双文件复测 Exit 1；M1 当前质量 `FAIL`，M0 当前完整复验 `UNVERIFIED`。P2 五文件本轮因九条历史活动 Work 路径冲突、NOSKIP 旧 Run/租约未安全处置而停在创建新 Work 前；没有新 Run、Checkpoint 或 177 项全套测试。 |
| V2.6.2 | 2026-09-27 | 从已验收 G10 隔离集成链重建唯一 M1 不可变候选 `a1c5d94`：SW008 扩展核心 203 passed，6 文件 Ruff/normal-import strict Mypy Exit 0；SW009 8 passed（9 subtests）及 Ruff/Mypy Exit 0；C09 E2E pytest/Ruff/Mypy Exit 0；候选洁净、临时产物已清除。新增 G10-R1 固定 ACCEPTED 非活动、BLOCKED 仍活动、显式 Resume 与多活动 Fail-Closed 合同。保留原 Checkpoint 局限，不创建治理终态，不合并、部署或切换 release。 |
| V2.6.3 | 2026-09-27 | G10-R1 六路径当前字节治理链完成，最终洁净提交 `8b02de55` 已推送至 `origin/codex/g10-r1-lifecycle`，未合并 main；CHG-328/329 completed，Run SUCCEEDED/lease RELEASED、Work CLOSED。由该提交可重复构建并注册 release `1.3.3-8b02de5`，active/previous exact-tree、隔离前切换/回退与根入口身份均通过，SW008 台账 0/0/0。M1 标记 COMPLETED / ACCEPTED；M0 当前重验、原 C09 Checkpoint 局限、P2/CHG-323 阻断和 M2 未启动事实不变。 |
| V3.0.1 | 2026-09-27 | U01 五状态演示原型在独立隔离候选提交 `d88eedd5` 固化；静态原型测试 2 passed、Ruff/Mypy/diff-check 均为 Exit 0。`CP-SW008-U01-001`、Run SUCCEEDED/lease RELEASED、Work CLOSED 与 `CHG-HMI-2026-001` completed 形成当前验收链，SW008 台账 0/0/0。M2 标记 IN_PROGRESS；U02～U08、P2、合并、部署和 release 切换均未由此启动。 |
| V3.0.2 | 2026-09-28 | Batch C 全量资产与 M2 准入审计闭合；新增原子任务 `M2-GOV-IC01` 及实施卡 015，只规划实施卡合同与自动化工作流。 |
| V3.0.3 | 2026-09-28 | 启动 `M2-BL01`，从运行身份修复基线机械引入 U01 两文件，形成 M2 唯一不可变集成基线。 |
| V3.0.4 | 2026-09-28 | `M2-BL01` 验收闭环：候选 `4851fce4`、Checkpoint、Run/Work、CHG 与台账证据齐备。 |
| V3.0.5 | 2026-09-28 | `M2-GOV-IC01` 八文件技术门禁通过并形成 Checkpoint，但首次提交因 CHG/台账未进入同一暂存快照而被正常门禁拒绝；历史如实保留，唯一纠正链改为八个产品路径加两个提交证据路径，禁止第十一路径。 |
| V3.0.6 | 2026-09-28 | `M2-GOV-IC01` 有界纠正闭合：八产品路径与两提交证据路径分层建模，33 项测试及 Ruff/Mypy/diff-check 全绿，当前十路径 Checkpoint `CP-SW008-M2-GOV-IC01-003` 与正常 hook 提交 `b7bb9357` 成立，Run/Work/Mission/CHG 均达合法终态；下一项为 U02 只读预检。 |
| V3.0.7 | 2026-09-28 | U02 开工前校准：确认现有 QML 接线与测试需要五条产品路径；`PlanningDraft` 无确定范围字段，界面只能如实标示“范围待规划”，不得提前创建 Mission。实施卡 016 已建，本次不宣称 U02 产品或治理验收。 |
| V3.0.8 | 2026-09-28 | U02 五产品路径已在 `m2-u02-planning-draft` 隔离候选实现，定向 QML/Cockpit 11 项、Facade 27 项、Ruff/Mypy/diff-check 均 Exit 0；`CP-SW008-M2-U02-001` 绑定 `b7bb9357` 与七条授权路径。正常 Git Hook 因候选旧基线 CHG 集合与现行台账不一致（120 孤儿、3 状态差异）拒绝提交；Run/Work 如实置 `BLOCKED`，CHG-339 保持 `implementing`。未提交、未验收，不改变 M0/M1 或 release。 |
| V3.0.9 | 2026-09-28 | U02 有界纠正闭环：确认首次阻断源于把 canonical 294 条完整台账复制到历史候选；恢复 `b7bb9357` 的 173 条分支本地快照并仅增量加入 CHG-339 后，候选达到 174/174、0/0/0。完整复跑 38 项测试及 Ruff/Mypy/diff-check，`CP-SW008-M2-U02-002` 与正常 Hook 提交 `74493c37` 成立；Run SUCCEEDED、lease RELEASED、Work/Mission CLOSED、CHG-339 completed，canonical 台账 0/0/0。旧 `CP-SW008-M2-U02-001` 仅保留为失败尝试历史证据。 |

当前产品状态（2026-09-28）：原 C09 业务 Run `SUCCEEDED`、租约 `RELEASED`，原 Work/Mission `CLOSED`，CHG-012 `completed`，双项目台账 0 差异，历史事件和批准均保留。原 Checkpoint 的 SW009 类型检查范围不足、原候选 strict 复验 Exit 1 的历史结论不改写；新统一不可变候选最终提交 `8b02de55` 已完成完整技术复验、G10-R1 治理闭环并由稳定 release `1.3.3-8b02de5` 消费，根入口不再 fallback，故 M1 为 `COMPLETED / ACCEPTED`。M0 历史完成保留、当前完整复验 `UNVERIFIED`。P2/CHG-323 仍因历史 `BLOCKED` Work 与 NOSKIP 进程/租约证据未闭合而 `BLOCKED`，不得宣称五文件真实验收完成，也不作为撤销 M1 的依据。U01、U02 已按各自依赖独立验收，M2 为 `IN_PROGRESS`；下一产品任务为 U03，只读预检前仍须核对候选祖先链与路径占用。main 尚未合并，后续源码集成与 D 阶段发布仍是独立边界。
