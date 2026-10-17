# U04S01｜异步一次启动与 Canonical 活动投影规范沉淀实施卡

> 卡片编号：`CARD-SW008-M2-GOV-U04S01`
> 对应 WBS：`M2-GOV-U04S01`
> 版本：`V0.1`（2026-09-28）
> 状态：`ACCEPTED`（提交 `14650723`；`CP-SW008-M2-GOV-U04S01-001`；CHG-SPEC-2026-017 completed；规范门禁以 `spec check/lint/frontmatter` 执行，原 `doc check --strict` 不存在，与基线逐字一致）
> 控制根：`C:\Users\fubai\Documents\My_Workspace`
> 建议隔离候选：`.auto-pm/worktrees/m2-gov-u04s01-spec`
> 隔离起点：`4166b9afb8e9c1628d3c1fd21f91b42ea89619cd`
> 前置验收：U04A `d59120c7`、U04B `d200eb9b`、U04B-R1 `e05fafa1`
> 治理属性：Obsidian CCB 独立规范变更；本卡不赋予实施权限

## 1. 用户故事与完成定义

作为后续项目和执行 Agent，我需要从全局规范直接获得已经被 U03/U04 实测证明的
异步启动、后台刷新、canonical 活动投影和安全失败降级合同，避免每个项目再次依赖
聊天提示、局部实现经验或事故复盘来重建同一套边界。

U04S01 只有在以下事实全部成立时才能关闭：

1. DEV-216 与 DEV-300 仅增加跨项目稳定合同，不写入 SW008、U04、CHG、Run 或事故编号；
2. `spec_registry.json` 与两份规范的版本、路径、生命周期保持一致；
3. 规范完整性、死链、注册表和差异门禁全部通过；
4. 三个目标路径在独立隔离候选中形成正常 Hook 的不可变本地提交；
5. 对应 CHG、Decision、Work、Run、Checkpoint 与台账合法闭环；
6. 合并、推送、部署和 release 切换仍保持独立边界。

## 2. 为什么需要扩充原 WBS 定义

WBS 只登记了“一次启动、canonical 重载、后台 Signal、真实事件进度和失败降级”五类
主题。U04 的实际实施还证明了以下边界必须一并进入实施卡，否则规范沉淀会不完整：

1. **单飞而非仅异步**：后台化不等于安全；同一用途同一时刻最多一个任务，重叠触发
   必须跳过或合并，不能排队堆积。
2. **结果时效性**：页面或 Bridge 销毁后，晚到 Signal 不得更新失效对象；刷新结果必须
   绑定发起时的 generation/owner 身份。
3. **最后可信快照**：读取失败时保留最后一份已验证快照并显示明确错误，不能清空成
   “无活动”，也不能以写库重试掩盖读取失败。
4. **投影隔离**：默认活动视图只允许当前 Mission、根 Work 和当前/最近 Run；历史
   `BLOCKED`、恢复辅助对象或其他 Mission 不得污染当前卡片。
5. **事件语义而非伪进度**：进度必须来自 append-only canonical 事件的离散阶段与持久化
   时间，不得根据 wall-clock、stdout、聊天文本或客户端内存伪造百分比。
6. **安全失败 DTO**：面向 UI 的失败原因必须是白名单化结构字段；异常堆栈、环境变量、
   argv、token、stdout/stderr 只进入受控诊断面，不进入普通活动卡片。
7. **Legacy 与损坏数据**：旧事件缺少字段时显式显示未知；未知版本、哈希不一致或损坏
   结构必须 fail-closed，不能猜测为成功。
8. **执行入口身份**：生成证据和收尾时必须使用与候选字节匹配的受控 runtime；不得从
   脏主工作区或旧 release 加载服务实现后再给新候选落账。

第 8 项只沉淀为通用的证据身份原则；U04B-R1 的具体租约事故和恢复 API 继续保留在
项目实施卡、CHG 与事件链中，不写入全局规范正文。

## 3. 证据来源与知识分层

### 3.1 可进入全局规范的稳定合同

| 经验证事实 | 规范落点 | 抽象后的合同 |
|---|---|---|
| U03 一次启动与防重复触发 | DEV-216 | 单飞 Worker、按钮/入口防重入、真实启动确认后才改变 UI 状态 |
| U04B 后台持续刷新 | DEV-216 | 有界周期、重叠 tick 跳过、Signal 回主线程、销毁后拒绝晚到结果 |
| 当前 Mission 活动隔离 | DEV-216、DEV-300 | 查询必须绑定当前 owner 范围；历史与辅助对象不得进入当前视图 |
| U04A 离散阶段与安全失败原因 | DEV-300 | canonical 事件、持久化时间、白名单失败 DTO、legacy unknown |
| 读取失败时保留可信快照 | DEV-216、DEV-300 | stale-but-verified + 显式 degraded 状态；禁止清空或静默成功 |
| U04B-R1 暴露的运行身份风险 | DEV-300 | 候选字节、执行 runtime 与证据生成器身份必须一致，否则 fail-closed |

### 3.2 只留在项目历史、禁止进入全局规范

- U04A/U04B/R1 的 CHG、Decision、Mission、Work、Run、Checkpoint 与事件 ID；
- `d59120c7`、`d200eb9b`、`e05fafa1` 等项目提交号；
- C09/P2/H11、NOSKIP、历史 `BLOCKED` Work 的具体对象与处置过程；
- 某次 Agent、模型、聊天内容、额度消耗或人为失误；
- U04B-R1 单次事故的精确恢复参数、token、租约版本或数据库行。

## 4. 精确 owned paths（3）

1. `00_Obsidian_Base全局规范文件仓库/02_Python开发域/216_PySide6_GUI开发规范_DEV.md`
2. `00_Obsidian_Base全局规范文件仓库/04_驾驶舱与全栈域/300_高级语言与工业上位机系统_Google_SRE工程可靠性规范_DEV.md`
3. `00_Obsidian_Base全局规范文件仓库/spec_registry.json`

出现第 4 条脏路径即停止，不得现场扩大 CCB Decision。生成索引或报告若会修改其他文件，
本任务只运行检查模式；需要同步生成物时必须修订本卡并重新报批。

### 4.1 控制根治理证据层（不属于候选 dirty paths）

本卡的三路径限制适用于隔离候选中的**规范内容与 Checkpoint dirty paths**。为满足 CCB
治理和 Continuity v2 的根绑定要求，高层服务还会仅在主控制根生成下列证据对象：

1. `SYS-2026-001_WorkspaceGovernance/04_监控/01_变更管理/01_变更单/CHG-SPEC/CHG-SPEC-2026-017.md`；
2. `SYS-2026-001_WorkspaceGovernance/04_监控/01_变更管理/02_变更记录/01_版本变更台账.md`；
3. `.auto-pm/decisions/<本次新生成 Decision>.json` 与 canonical Continuity v2 追加事件。

这些对象必须由 `main.py change`、`main.py decision` 与 `main.py continuity` 的高层入口在
主控制根创建；它们不得被复制到候选、不得计入候选 Run 的 `owned_paths` 或 dirty paths，
也不得成为编辑 Obsidian 正文的授权理由。除上述两份可跟踪治理文档外，任何新增工作区
文件均触发停止条件。

## 5. 拟实施内容

### 5.1 DEV-216｜PySide6/QML 异步 UI 合同

在现有“QThreadPool + QRunnable”章节下新增可机器测试的工程合同：

1. **Single-flight**：同一 Bridge/用途最多一个 in-flight Worker；重复触发必须跳过、合并
   或返回已有任务，不得无界排队。
2. **主线程边界**：SQLite、文件、网络与重解析只在 Worker 执行；QML 属性只能由 Signal
   回到对象所属线程后更新。
3. **生命周期 fencing**：Worker 结果携带 generation/owner 标识；对象销毁、页面切换或
   generation 变化后，晚到结果必须被丢弃。
4. **有界刷新**：刷新间隔显式、可测试、可停止；关闭页面或应用时停止调度并释放引用。
5. **失败呈现**：保留最后可信快照，另行发布 `degraded/error`；不得把失败清空为无数据。
6. **一次启动 UI**：按钮锁定不代表启动成功；只有 canonical 启动确认或等价受控回执后
   才允许展示运行态，失败后必须恢复可重试状态。

建议 DEV-216 由 `V2.0.0` 升为 `V2.1.0`，属于向后兼容的新增工程合同。

### 5.2 DEV-300｜Canonical 投影与证据身份合同

在可观测性、故障隔离和边界保护章节补充：

1. 活动状态、阶段、时间与失败类别以 canonical append-only 事件及其当前投影为真源；
2. 只投影当前 owner 范围，默认不得将历史、恢复或辅助对象混入当前业务视图；
3. 不计算没有物理依据的完成百分比；离散阶段只说明“已发生”，不预测“完成度”；
4. 面向 UI 的失败原因使用稳定枚举和无秘密短说明；原始异常仅进入受控诊断日志；
5. legacy 缺失字段显式为 unknown；未知版本、哈希不一致和损坏数据 fail-closed；
6. 候选源码身份、实际加载 runtime 与证据生成器必须可证明一致；不一致时禁止验收、
   Checkpoint 或终态落账，不允许静默 fallback；
7. 读取故障采用 stale-but-verified 降级，不触发隐式写入或自动“修复” canonical 数据。

建议 DEV-300 由 `V1.0.0` 升为 `V1.1.0`，属于跨语言可复用的可靠性合同扩充。

### 5.3 spec_registry.json

只同步 DEV-216、DEV-300 的版本与必要标签；不改变 canonical path、spec ID、生命周期或
其他规范条目。建议新增标签仅限能被正文直接证明的稳定术语，例如：

- DEV-216：`SingleFlight`、`LifecycleFencing`；
- DEV-300：`CanonicalProjection`、`FailClosed`。

标签是否落地以实施时注册表 schema 和现有命名风格复核为准；若 schema 不接受新增标签，
仅同步版本，不为标签修改 schema。

## 6. 治理与隔离执行顺序

1. 从 `4166b9afb8e9c1628d3c1fd21f91b42ea89619cd` 创建独立隔离候选；不得使用当前脏主工作区
   直接编辑三份规范。
2. 只读确认三个目标文件在该基线的 SHA-256、版本、注册表记录和 Git 跟踪状态。
3. 在 SYS-2026-001 规范治理域建立独立 CCB CHG；通过 Decision 精确授权 §4 三路径。
4. 建立单一 Work、单一主 Run 与有界 lease；不得复用 U04 产品 Run 或 H11 治理对象。
5. 仅修改三路径，运行 §7 门禁并生成当前字节 Checkpoint。
6. 用户验收后形成正常 Hook 的不可变本地提交，再闭合 Run、Work、CHG 和台账。
7. 验收完成后再更新 WBS 投影为 `ACCEPTED`；不得提前把建卡视为规范已生效。

本卡不硬编码尚未分配的 CHG、Decision、Work、Run 编号。实施前必须通过当前注册表和
canonical 数据库确认编号未占用后，由高层服务生成，禁止手写 SQL。

## 7. 门禁矩阵

所有命令从隔离候选根目录运行，使用工作区 `.venv` 解释器和 `-B`；不得调用已退役的
`pm-workflow`。

```powershell
$wsRoot = 'C:\Users\fubai\Documents\My_Workspace'
$python = "$wsRoot\.venv\Scripts\python.exe"

# JSON 与目标条目一致性
& $python -B -c "import json; from pathlib import Path; p=Path('00_Obsidian_Base全局规范文件仓库/spec_registry.json'); d=json.loads(p.read_text(encoding='utf-8', errors='replace')); assert d['specs']['DEV-216']['version']=='V2.1.0'; assert d['specs']['DEV-300']['version']=='V1.1.0'; print('registry target versions: PASS')"

# 规范完整性、索引与死链门禁；只检查，不自动同步或覆写
& $python -B main.py doc check --strict

# 三路径边界与 Markdown/JSON 基础差异检查
git status --short
git diff --check -- `
  '00_Obsidian_Base全局规范文件仓库/02_Python开发域/216_PySide6_GUI开发规范_DEV.md' `
  '00_Obsidian_Base全局规范文件仓库/04_驾驶舱与全栈域/300_高级语言与工业上位机系统_Google_SRE工程可靠性规范_DEV.md' `
  '00_Obsidian_Base全局规范文件仓库/spec_registry.json'
```

若 `main.py doc check --strict` 因既存、与三路径无关的基线债失败，必须同时提供：

1. 隔离基线上的同命令结果；
2. 当前候选结果；
3. 证明本次没有新增诊断的差异报告。

既存基线债只能标记为 `BASELINE_EXCEPTION`，不能冒记全绿；若本次新增任何诊断则 FAIL。

实施时还必须执行只读语义检查，证明：

- 两份规范 frontmatter 与注册表版本完全一致；
- 正文不含 SW008、U04、C09、P2、H11、CHG、Decision、Run、Checkpoint 或提交号；
- 正文不存在 token、PID、数据库行、Agent/模型名称或事故叙事；
- 三个目标文件以外没有脏路径。

## 8. 验收与提交条件

1. 三路径内容符合 §5，且稳定合同具备明确 MUST/MUST NOT 语义；
2. `spec_registry.json` 可解析，DEV-216/DEV-300 的路径、版本与 lifecycle 对齐；
3. 所有新增诊断为 0，或仅保留经基线对照证明的既存 `BASELINE_EXCEPTION`；
4. Checkpoint 绑定当前候选 HEAD、三条 dirty paths、当前 SHA-256 与真实命令；
5. 正常 Git Hook 形成一个不可变本地提交，不得使用 `--no-verify`；
6. Run `SUCCEEDED` 且 lease `RELEASED`，Work `CLOSED`，CCB CHG `completed`；
7. SYS-2026-001 对应台账 reconcile 为 0 缺失、0 孤儿、0 不一致；
8. WBS 更新只记录最终验收事实，不改写 U03/U04 的历史记录；
9. 合并、推送、部署和 release 切换均不在本卡授权范围。

## 9. 有界修复与停止条件

本任务最多一个主 Run 和一个有界纠正 Run。纠正只能处理三个 owned paths 内稳定复现的
文档、frontmatter 或注册表一致性问题；不得修改检查器、索引生成器、源码或第四个文件。

以下任一情况立即停止并保留现场：

- 隔离起点、目标文件 SHA-256 或 U04 验收事实与本卡不符；
- CCB Decision、owned paths、候选身份或 lease 不一致；
- `doc check` 要求写入额外索引、README 或生成报告才能通过；
- 需要修改规范检查器、模板、产品源码或 canonical 数据库；
- 规范内容必须依赖项目 ID、事故编号或尚未验收的实现才能成立；
- 出现第 4 条脏路径、Git Hook 被绕过或 Checkpoint 不是当前字节；
- 任何命令需要手改数据库、合并、推送、部署或切换 release。

## 10. 与 H11、U05 的顺序

U04S01 是 U03/U04 已验收经验的规范沉淀，应在继续 U05 产品开发前完成，避免后续 Agent
再次依赖上下文记忆。它不处理历史控制面对象，也不以“规范更新”替代 H11：

1. 先独立验收 U04S01；
2. 再按实施卡 019 推进 H11A/H11B/H11C；
3. H11 达到其准入条件后，再准备 U05。

若 H11 因独立控制面问题延期，U04S01 的规范提交仍可单独验收；两者不得共享 CHG、
Decision、Work、Run 或 Checkpoint。

## 11. 当前裁决

本卡已建立，状态保持 `PLANNED / NOT_AUTHORIZED`。它完整吸收了 U04 长周期实施中可跨项目
复用的知识，同时明确排除了事故细节和项目专属恢复步骤。下一步需要单独批准 Obsidian CCB
实施；在该批准到来前，不修改三个目标规范、不创建执行治理对象、不更新 WBS 完成状态。
