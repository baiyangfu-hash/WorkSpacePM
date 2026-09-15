# PM-Flow 恢复与可用化总方案

> 文档版本：V2.5.0；修订日期：2026-09-14；状态：REVISED_FOR_EXECUTION。
> 项目：SW-2026-008；治理：SYS-2026-001；规划标识：PMF-20260912。
> 修订依据：用户要求“重新修订方案，原子级拆解，最终需求必须达成”。本轮直接修订既有计划；不再设置一个等待批准的“先盘点再规划”项目。
> 本文件给出 4 个产品里程碑、86 个原子任务及 1 条主线；其中 Q01～Q03 是已冻结基线失败的独立收敛队列。任务属于批次内部步骤，不等于 86 次用户审批。
> 当前批准涵盖方案修订；既有 216 的实施、验收、隔离提交批准继续保留。新增恢复写入、Hook 安装、发布等按下文明确的批次范围执行，不能从旧 216 授权外推。
> 沿用原文件已经生成的 PM-027 九节结构，直接修订正文。V1.0.0 留存在 archive/PMF-20260912，退出当前派工入口。
> V2.1.0 依据实际 G06 启动演练修订：不把一次环境诊断包装成候选工作树补丁；先固定真实执行就绪门、G06 输入合同和候选集成点，再进入源码执行。
> V2.1.1 依据 G10 的真实 Checkpoint 合同修订：不可变提交的非活动候选装配必须发生在 G10 Run 之前；Run 只在最终、洁净的集成 HEAD 上启动，避免把受控组合误报为基线漂移。
> V2.2.0 依据 P01 后的代码合同复核修订：前授权计划草稿与强授权 Mission 分层；禁止用空授权或伪造 CHG/Decision 提前创建 Mission，并把 P 链及下游依赖重排为可执行顺序。
> V2.3.0 依据 P08-R 的实际闭合修订：强授权 Mission 还必须显式、最小化地声明允许派生的子 Work 类型；P08-R 的不可变提交与 Checkpoint 是 P09 的唯一新增前置，P09 不得自行补写或扩大 Mission 授权。
> V2.4.0 依据 P11 首次 CLI 冷启动重放实演修订：P10 的内存 card 重试不能代替进程重启后的 request_id 恢复；P11 同票根治 Facade 在 CHG 离开 DRAFT 后的幂等范围卡重建，禁止在 CLI 中绕过服务真源。
> V2.5.0 依据 E02 启动前持久调度的根因核验修订：原三路径没有把 ExecutionIntent 纳入 Continuity 单一真源，无法合法兑现“持久化后启动、同 operation_id 不重复派发”。E02 扩为契约、服务、持久化层及两类测试的五路径原子；禁止创建文件/JSON 旁路账本或把 PREPARED 误报为已启动。

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
9. 批次授权：本版将 86 个原子作为 4 个里程碑内的步骤；对旧文档“逐包审批”的粒度解释在批次 Decision 中明写，不静默改 O 或 .trae 法典。

## 4. 迭代计划

### 4.1 原子任务的定义与推进规则

每个原子交付一个独立可判断的行为，包含该行为的测试，不把“全部实现”与“以后补测试”拆成两票。源码增量以 1～3 个主文件加对应测试为常态；跨文件的单一事务必须整体验证。

每行含依赖、产出位置、机器判定和执行/复核模型。依赖完成、当前批次授权有效、目标 lease/基线无冲突即自动进入下一行。单项预计一个 15～60 分钟专注窗口；这是拆分预算，不是完成时间保证。两次同因失败后由主控在本票内复盘并改方案；超出路径/风险范围才提交一个合并后的决策点。

每张源码 Run 在创建前或重新进入前必须通过一次真实执行就绪门：以将实际使用的控制面、解释器、候选 worktree 和 Git 子进程采集 `HEAD`、工作树脏路径、工作树身份及目标 Work/Decision。检查必须无写入，记录执行环境、完整命令、候选 HEAD 和退出码。任何诊断先在同一调用链复现，并与隔离环境对照；未证明为稳定产品问题时，不得写 Git 配置、停止守护进程、替换 PATH 或修改源码。已有 READY Work 不豁免此门，只有通过后才能创建新的 Run。

“同一快照”专指 Git index 的不可变 `StagedSnapshot`；提交信息文件与工作树内容是显式的实时输入，预检必须记录其路径和读取阶段。预检的成功只描述该次输入，不能保证未来 Git commit 前的文件仍未变化。实现不得复制 `.git/index`、篡改 `GIT_INDEX_FILE` 或以 monkeypatch 冒充真实 Hook；应让同一 `StagedSnapshot` 直接进入实际 `pre-commit` 与 `commit-msg` 的公共检查函数。

“完成”先记行为证据；实现、验收、提交、部署各自有状态。表中所有尚未产生新证据的行均为 PLANNED，只有 B01/B02 可消费本轮已存在的事实；不把它们宣称为已经完成的运行操作。

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

G01、G03～G10 在研发候选实现，G02 是明确批准的 Hook 安装动作。G02 的新模板可以先调用现有有效 root runtime；新领域门禁代码只有随管理候选明示调用或 D07 正式部署后才生效。每份预检回执记录实际代码身份，不能把模板安装当作所有门禁实现已上线。P/E/C 只以 G10 通过的集成候选作为源码基线，不能从独立已验收 Work 推断它们已组合可用。

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
| P08 | 物化强授权 Mission | P07 | CORE/pm_facade_service.py、CORE/mission_service.py、INFRA/continuity_store.py、T/core/test_pm_facade_service.py | 仅以真实 change_id、decision_id、CHG_DECISION 构造 AuthorityEnvelope 并创建唯一 Mission；无占位 ID、无空授权；仅显式允许 `WorkKind.WBS` 子 Work，BUG/TEST/DEBT/GOVERNANCE 等仍拒绝；重放返回同一 Mission | A/G |
| P09 | 从强授权 Mission 派生可选定 Work | P08 + P08-R 闭合 | CORE/work_registry_service.py、CORE/pm_facade_service.py、T/core/test_work_registry_service.py | 仅接受已允许 `WorkKind.WBS` 的有效 Mission；Work 路径不超 Decision；与其它 owner 冲突精确拒绝；用户不填 ID；无 Mission 或无 WBS 子 Work 授权不得建 Work | T/G |
| P10 | 全授权链中断可重试 | P09 | CORE/pm_facade_service.py、INFRA/continuity_store.py、T/core/test_pm_facade_service.py | PlanningDraft/CHG/Decision/Mission/Work 每一持久化边界故障注入后重试均只有一条链；不留下虚假 READY 或无授权 Mission | A/G |
| P11 | CLI 接通新需求 plan | P06、P10 | CLI/pm.py、CORE/pm_facade_service.py、T/cli/test_pm_facade.py、T/core/test_pm_facade_service.py | 新需求参数真实创建/恢复 PlanningDraft 与范围卡；批准后沿同链到唯一 Work；CHG 离开 DRAFT 后，CLI 冷启动仍可按相同 request_id+输入恢复同一 PlanningScopeCard 及授权链；保留原 Mission 调用兼容；未来参数以实现后的 --help 为准 | A/G |

### 4.5 E：真正执行、监督和接棒（E01～E08）

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| E01 | 真实本地执行器最小实演 | G10；执行器使用已批准 | 拟新增 INFRA/local_executor.py、T/core/test_local_executor.py；独立微任务夹具 | 真实模型进程完成一项允许的文件改动；记录 actual model/session/exit；mock 只能作单测；认证失败明确阻断本后端 | T/G |
| E02 | 持久调度意图 | P09、E01 | CONTRACT/execution_adapter.py、CORE/execution_adapter_service.py、INFRA/continuity_store.py、T/contracts/test_execution_adapter.py、T/core/test_execution_adapter_service.py | `ExecutionIntent` 以唯一 `operation_id` 写入 Continuity 单一真源后，才允许 materialize worktree、创建 Run 或启动模型进程；同 ID 同载荷返回同一 intent/receipt，同 ID 异载荷精确拒绝；持久化失败必须零副作用；`PREPARED` 明确表示尚未启动。禁止文件/JSON/内存旁路账本；真实 PID/session 与已启动状态只由 E03 映射 | A/G |
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
| C09 | 第一条 Python 新需求闭环实演 | C08、E08、G10 | 拟新增 T/e2e/test_pmf_python.py；批准的真实 Python 演练工程 | 新目标→范围批准→真实改动→门禁→用户验收→CHG/台账一致；0 次手工治理 JSON；含一次实际提交预检 | T/A |

C09 是 M1 的可用能力验收。CLI 可用于实际任务，不必等所有 QML 页面和历史工作树归档。演练不能预先手造全套 Mission/Work 来绕过 P 入口。

### 4.7 U：用户界面与 SDK（U01～U08）

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| U01 | 五状态可点击界面原型 | P06、E03、C07 | 拟新增 S/01_项目文档/prototypes/pm-flow-v2.html | 新目标、确认、执行、失败/恢复、验收五场景可达；标明演示数据；按钮/函数/导航无死链 | T/G |
| U02 | QML 输入目标生成真实草稿 | U01、P11 | QML/bridges/pm_cockpit_bridge.py、QML/views/BossCockpitView.qml、T/qml/test_pm_cockpit_bridge.py | Bridge→Facade 实际建 PlanningDraft；显示项目/范围/验收，不让用户填内部 ID；批准前不展示为 Mission | T/G |
| U03 | 一次确认启动真实任务 | U02、E08 | QML/bridges/pm_cockpit_bridge.py、QML/components/PmConfirmationCard.qml、T/qml/test_pm_cockpit_bridge.py | 连点只启动一次；实际 session 未确认时不显示执行中 | T/G |
| U04 | QML 进度和失败来自真实事件 | U03 | CORE/pm_cockpit_service.py、QML/components/ActivityTimeline.qml、T/core/test_pm_cockpit_service.py | QRunnable/Signal 更新；主线程不阻塞；无伪百分比，失败原因能定位步骤 | T/G |
| U05 | 恢复同一任务与证据抽屉 | U04、E06、C03 | QML/bridges/pm_cockpit_bridge.py、QML/components/EvidenceDrawer.qml、T/qml/test_pm_cockpit_bridge.py | 关闭重开后同 Work/Run；证据匹配当前内容；恢复动作受服务资格限制 | T/G |
| U06 | GUI 验收与待同步状态 | U05、C07 | QML/bridges/pm_cockpit_bridge.py、QML/views/BossCockpitView.qml、T/qml/test_boss_cockpit_view.py | 验收→投影失败→重试→完成可观测；缺必要证据不能点成“已完成” | T/G |
| U07 | 薄 Cockpit SDK | C09 | 拟新增 D/auto_pm/api.py、T/core/test_cockpit_api.py；D/auto_pm/__init__.py | SDK经统一运行身份/Facade从新目标到批准、真实execute、验收落账完整实演；生产初始化不落到editable/母体；不只验import/查询 | T/G |
| U08 | 旧 workflow 接口兼容 | U07 | CLI/workflow.py、拟新增 T/cli/test_workflow_compat.py | 现有命令保留；新 workflow 别名只委托 pm；不能恢复旧写入状态机；未知旧动作明确拒绝 | T/G |

U01 是在现有 PySide6/QML 方案上的交互原型，不换 Web 技术栈。界面核心信息固定为：目标、当前阶段、实际执行器、下一可行动作、证据、验收；复杂内部对象默认折叠。

### 4.8 V：双领域、恢复和模板（V01～V08）

| ID | 单一交付 | 依赖 | 精确产出/改动边界 | 验收与失败出口 | 模型 |
|---|---|---|---|---|---|
| V01 | PLC 静态质量门插件 | C01、C03 | CORE/evidence_collection_service.py、T/core/test_evidence_collection_service.py | 复用现行 PLC checker；违规 SCL 确实失败；.plc.json/SCL/INT/VAR 证据同基线 | T/G |
| V02 | PLC 新需求静态闭环 | V01、C09 | 拟新增 T/e2e/test_pmf_plc.py；批准的 PLC 演练工程 | 新目标到真实 SCL 变化、静态门禁、验收落账；上机编译/下发单列未执行，不虚报工业运行成功 | T/A |
| V03 | 真实更换 Agent 续跑 | E07、C09 | 拟新增 T/e2e/test_pmf_handoff.py；R 下本场景证据 | 第二 Agent 接同一 Work，旧 owner 后续写入拒绝；无需用户搬 JSON/token | T/A |
| V04 | 进程中断/lease 到期恢复实演 | E06、V03 | 拟新增 T/e2e/test_pmf_recovery.py | 杀执行进程、主控重启各实演；到期不冒记成功；取消/续跑有合法证据与幂等事件 | A/G |
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
| M0 交付通道恢复 | B01～B10、G01～G10 | 216 可提交；后续任务知道用什么代码、检什么范围、在哪执行 | 当前阻塞解除，实际双 Hook 通过；新门禁与运行身份在同一集成候选验证，安装/运行身份分别记清 |
| M1 第一条可用 PM-Flow 候选 | P01～P11、E01～E08、C01～C09 | CLI在候选环境完成真实Python新任务；内部对象和证据由系统生成 | C09端到端通过；E07可在C03后完成；外部成本/执行器可用性有实证 |
| M2 驾驶舱与双领域候选 | U01～U08、V01～V08 | GUI、SDK、PLC、跨Agent、故障恢复在候选中走同一条链 | V05/V06真实正反验收；模板源于实演基准 |
| M3 稳定使用 | Q01～Q03、D01～D09 | 根入口稳定运行，三次真实任务可重复交付 | 全部 AC、制品一致性、兼容回退、全量门禁与 D08 均有证据 |

主依赖：
~~~text
B01 -> B02 -> B03 -> B04 -----> B06 -> B07 -> B08 -> B09 -> B10
               \-> B05 ------/
B09 -> G01 -> G02
        \-> G03 -> G04 -> G05 -> G06
B09 -> G07 -> G08/G09
G06 + G08 + G09 -> G10
G10 -> P01 -> P02 -> P03 -> P04 -> P05 -> P06 -> P07 -> P08 -> P08-R -> P09 -> P10 -> P11
G10 -> E01; P09 + E01 -> E02 -> E03 -> E04/E05 -> E06
E05 -> C01 -> C02 -> C03 -> C04 -> C05 -> C06 -> C07 -> C08
C03 + E06 -> E07; E05 + P11 -> E08
C08 + E08 + G10 -> C09 -> U/V -> D
G07 -> Q01/Q02/Q03 -> D03 -> D04 -> D05
~~~

V2.0 的第一张执行卡为 B 批次；其历史输入、输出和批准边界保留如下，不能作为 2026-09-13 的当前启动指令：

- 输入：当前 HEAD、216 暂存两文件及已验收证据、SAFE-007 单个差异、当前双 Hook。
- 输出：限定投影修复证据、真实双 Hook 通过、216 两源码隔离提交、独立治理记录集合。
- 批次需要新增声明：允许固定哈希非活动管理候选；允许本次 SAFE-007 投影单元格写入；允许补齐216治理正文；这些不属于之前两代码文件的实施 scope。
- 机器对象：由主控使用现有服务生成恢复 CHG/Decision/Work/Run，明确选定 Work/Run，内部持有有效 lease；不需要先完成 H。
- 原子顺序：B01～B10，内部常规检查/克隆/重试不再逐项问用户。
- 当前推进：G10、P01～P11 与 E01 均已完成受控验收和隔离提交；E01 的不可变提交为 `d013ccfd39b031311f6f05e03d6a8b088e3bab33`。下一原子是 V2.5 的 E02：只能基于 E01 与已闭合 P09 建立候选，并严格执行本行五路径和零副作用合同；本次文档修订验收前不得创建 E02 产品执行对象。Q01～Q03 独立推进，D03/D05 前必须闭合。

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

本轮 V2.5 只修订本39文件；V1.0.0 历史快照继续保留，不重新生成临时 Copier 脚手架，不新增第二份活动方案。本次修订未改产品源码、Continuity 数据库、Hook、release 指针或 E02 执行对象。E01 的不可变源码提交 `d013ccfd39b031311f6f05e03d6a8b088e3bab33` 是本次根因复核输入，不属于 V2.5 文档修订写入。

复核项：86 个原子编号唯一；所有依赖均指向存在的编号且无环；所有 REQ/AC 有责任任务；PlanningDraft 与 Mission 的安全边界、G06 的输入合同、G10 集成边界和 Q01～Q03 的最终门禁归属明确；现有模块路径与“拟新增”区分。文档校验通过只证明计划结构完整，不代替产品验收。

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
| V2.5.0 | 2026-09-14 | 根据 E02 根因核验，将持久化层和契约测试补入 E02 的最小充分五路径；固化 ExecutionIntent 的 operation_id 幂等、异载荷拒绝、持久化失败零副作用及 PREPARED 未启动合同，并将真实 PID/session 映射明确留给 E03。 |

当前产品状态：G06、G08、G09 均已有不可变隔离提交；G10 已验收并形成不可变隔离提交 `d87fd3d`；P01～P11 已沿授权链闭合，E01 已验收并形成不可变隔离提交 `d013ccfd39b031311f6f05e03d6a8b088e3bab33`。下一步只能在本 V2.5 文档验收后，基于 P09 与 E01 的不可变输入启动 E02；不得在 E02 建立旁路账本、抢先登记 PID/session，或绕过真实 Continuity 持久化。pm-flow 端到端需求尚未达成，Q01～Q03 仍须在 D03/D05 前完成。
