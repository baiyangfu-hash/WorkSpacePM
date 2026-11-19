---
spec_id: PM-056
title: 跨 Agent 工作连续性与恢复协议
version: V2.0.0
domain: pm
lifecycle: stable
type: PM
status: active
created: 2026-09-09
updated: 2026-11-19
author: Codex（架构师/PM）
canonical_path: "00_Obsidian_Base全局规范文件仓库/01_项目管理域/00_元规则与治理/056_跨Agent工作连续性与恢复协议_PM.md"
tags: [连续性, Resume, Handoff, Work, Run, Checkpoint, Agent, local-handoff]
related:
  - "[[033_功能模块迭代流程标准_PM]]"
  - "[[042_通用变更管理流程规范_PM]]"
  - "[[046_通用任务派发契约模板_PM]]"
---

# 跨 Agent 工作连续性与恢复协议

## 1. 目的与适用范围

本协议定义不同 AI、IDE、CLI 和人工执行者之间可验证、可恢复、可回退的工作连续性边界。它是平台中立的上位协议；具体平台只提供 Adapter，不得成为核心状态真源。

适用于需要跨会话、跨 Agent、跨工作树或跨运行版本继续执行的项目管理、软件开发和工程交付。单次纯问答不强制创建执行对象。

本协议采用**双轨分工**，按协作形态选用对应轨道，不得混用或互相冒充授权：

- **轨道 A（重轨：Work / Run / Checkpoint / Lease，第 4～12 节）**：适用于看板“确认开工”一键流、多机并发或需要强租约互斥的受控写入任务，权威源在 Continuity Store 事务表。
- **轨道 B（轻轨：本机交接契约 `local-handoff.v1`，第 13 节）**：适用于单机日常迭代、跨对话换班接手（GitHub 处于“关”或“备份”档，不走 Run/Lease 也不依赖远程 `claims/*` 分支），以项目内结构化双表承载机器查不到的阶段目标、优先级与断点上下文。

## 2. 对象边界

| 对象 | 唯一职责 | 禁止承载 |
|---|---|---|
| Project | 长期业务身份与项目元数据 | 当前执行队列 |
| Governance / CHG / Decision | 范围、风险和变更授权 | 执行进度、lease |
| Work | 一个可独立授权、验收和关闭的逻辑工作单元 | 某次进程细节 |
| Run | Work 的一次执行尝试 | 跨 Run 共享状态 |
| Checkpoint | Run 的不可变恢复点 | 原位覆盖的 current state |
| Handoff（轨道 A） | 对指定 checkpoint 的交接快照 | 自由文本授权 |
| Local Handoff（轨道 B） | 项目单机交接交换区（`focus.json` + `journal.jsonl`），承载阶段目标、优先级与断点 | 授权凭据、手写完成态、长篇日志 |
| Release | 已登记、可验证、可回退的运行制品 | 研发母体 dirty 内容 |

对象必须通过 `project_id / work_id / run_id / checkpoint_id / handoff_id / release_id` 显式关联，不得用标题、更新时间或自然语言猜测关联。

## 3. 一事实一真源

| 事实 | 权威源 |
|---|---|
| subject/control/development/runtime 映射 | Workspace Registry |
| Work/Run/Checkpoint/Handoff/lease | Continuity Store 的事务表 |
| 变更授权 | CHG 与不可变 Decision 证据 |
| 代码事实 | Git commit、dirty 声明、worktree |
| 运行版本 | manifest 与 active/previous 指针 |
| 项目当前阶段焦点与交接事件（单机轻轨） | 项目交接交换区 `focus.json` 与 `journal.jsonl`（受第 13 节硬约束） |
| PM_SESSION | 已退役历史文件，不是执行队列或授权源 |

Adapter、聊天上下文、PM_SESSION、轨道 A/B 的 handoff 文本和“已完成”口头回执均不得覆盖上述权威源，亦不得替代授权。

## 4. Context Resolve

Context 必须返回：schema version、workspace root、subject project、control project、development root、runtime root、release ID、resolution source、带 SHA-256 的 read set、evidence ID 和 conflicts。

解析优先级为显式 `project_id`，其次为调用目录的局部锚点。无锚点、多候选、路径越界、映射冲突、指纹漂移或 release 指针不可读时必须结构化失败，禁止按最近更新时间猜测项目。

Context 只解决身份，不查询 Work/Run，也不生成下一动作。

## 5. Work

Work 必须包含：`work_id`、subject project、kind、title、owner、scope paths、source fingerprint、authorization reference、read-only 标志、状态、版本和时间戳。

写入型 Work 必须在 CHG/Decision 明确批准后进入 READY；只读 Grooming 可用 `READ_ONLY` 授权。scope 必须是工作空间内规范化相对路径，执行 owned paths 必须是 scope 子集。

Work 关系只允许显式类型，例如 `blocks / blocked_by / parent / child / discovered_from / duplicates`。发现的新问题必须新建 Work 或 CHG，不得暗中扩大原 Work。

## 6. Run、ownership 与 lease

每个 Run 必须绑定一个 Work、executor、adapter、owned paths、Git HEAD、worktree、声明的 dirty paths、状态和幂等键。

同一 owned path 同时只允许一个有效写 lease。lease 必须有 owner、到期时间和乐观并发版本。错误 owner、错误 token、过期 lease、owned path 越界或未声明 dirty 均失败关闭。

lease token 是执行能力凭证，不是可共享状态。Resume、日志、报告和通用 Handoff 不得返回或记录 token；接收方通过受控 accept 操作提交新的私密 token。

## 7. Checkpoint 与 Handoff

Checkpoint 只追加、不原位更新，必须绑定 Run、sequence、Git baseline、dirty paths、摘要、evidence 和时间戳。无 evidence 的 checkpoint 不可用于恢复。

Handoff 必须绑定确定的 Work、Run 和 Checkpoint，并携带 from/to owner、owned paths、Git/worktree、授权引用、约束、验收标准、能力集、schema version 和快照 hash。accept 必须原子转移 lease；转移后旧 owner 立即失权。

## 8. Resume

Resume 必须先消费成功的 Context，再按显式 Work/Run 查询。未显式指定时，只能在当前 subject 下唯一可判定时选择；零个明确返回空，多个返回 conflict，禁止选择 latest。

输出必须分离 context、work、run、checkpoint、只读 lease view、conflicts、read set、evidence ID 和 next legal action。任何过期 lease、Git 漂移、未知 dirty、scope 冲突、损坏 Store 或未知 schema 都必须抑制下一动作。

## 9. dirty tree 与 worktree

执行前必须记录 Git HEAD，并把 dirty 文件分为 owned、declared external、unknown。unknown dirty 一律阻断写入。不得为获得绿灯而 reset、clean、stash、覆盖或并入其他 owner 的改动。

并行写入、发布构建、基线复现或高风险验证应使用独立 worktree。worktree 必须由明确 commit 创建；不得把主工作树未提交内容伪装成可复现基线。

## 10. Adapter 与入口

平台 Adapter 只做输入规范化、调用和结果呈现，不保存核心状态，不改写状态机，不根据 provider 身份改变事实 payload。不同 Adapter 对同一显式 Work/Run 必须得到同一 canonical payload。

所有运行命令必须通过工作空间声明的 release launcher 或等价稳定入口；禁止把某个 IDE、技能目录、editable install 或 `python -m auto_pm` 写成跨项目强制入口。

## 11. 版本兼容与失败关闭

schema 必须显式版本化。旧 Handoff 可保留只读兼容，但缺少 Work/Run/Checkpoint/lease/Git 事实时不得用于新的写入执行。未知主版本、字段缺失、快照 hash 不符和能力不兼容均拒绝执行，不得静默降级。

## 12. 发布、验证与回退

连续性能力必须依次通过：母体测试、inactive release 精确树、隔离 checkout、真实 Store Dogfood、至少两个独立 Adapter 冷启动、active 切流和 previous 回退验证。窄测、模拟 payload 或稳定槽旧代码不能代替母体和真实运行验证。

验证证据必须记录命令语义、cwd、入口、版本、exit code、Git commit、制品 hash 和实际结论。发现失败时先回退指针或停止写入，再修复母体并构建新 release，禁止原地篡改已发布制品。

## 13. 本机轻轨交接契约（`local-handoff.v1`）

本节规范单机日常开发与跨对话换班的轻轨交接协议。它像单机设备与 HMI 之间的固定通讯数据表：字段名、长度、类型和读写边界全部写死，避免新对话靠猜或靠散文文档接手。

### 13.1 适用边界与目录约定

1. **适用场景**：单机本地优先工作流（GitHub 档位为“关”或“备份”），以及需要给任意新对话提供项目级焦点摘要的场合；处于“多机”档时，本交换区可与远程占位表（`claims/*`）并行展示，互不替代。
2. **跨项目零冲突目录规则**（由 `workspace_registry.json` 解析 `project_root`，使用无编号子目录 `交接交换区/` 避免与已有编号目录冲突）：
   - Python / 治理类项目（`project_root` 不在 `0100_PLC自动化/` 下，如 `SW-*`、`SYS-*`）：`<project_root>/04_监控/交接交换区/`
   - PLC 工程项目（`project_root` 在 `0100_PLC自动化/` 下，如 `DJ-*`）：`<project_root>/11_监控/交接交换区/`
3. **版本控制与写入边界**：交接交换区文件随工位分支经 `pm_merge.py merge` 合入 `main`；工具默认禁止直接在控制根覆写已跟踪的交接文件，防止制造未提交脏树阻断合并。

### 13.2 双表结构定义

每个项目的 `交接交换区/` 固定只包含两张 UTF-8 编码结构化数据表：

#### 表 1：`focus.json`（当前焦点投影，覆盖写）

| 字段 | 类型 | 必填 | 约束 | 语义 |
|---|---|---|---|---|
| `schema` | string | 是 | 固定 `"local-handoff-focus.v1"` | 协议版本号（未知版本失败关闭） |
| `project_id` | string | 是 | 必须与查询项目号一致 | 所属项目编号 |
| `updated_at` | string | 是 | UTC ISO-8601（如 `2026-11-19T22:00:00Z`） | 最后更新时间（用于陈旧检测） |
| `updated_by` | string | 是 | 非空，≤40 字符 | 更新者标识（如 `antigravity`/`claude`/`user`） |
| `stage_goal` | string | 是 | 非空，≤120 字符 | 当前阶段唯一核心目标 |
| `priorities` | array | 是 | 最多 5 项；每项含 `rank`（1..5 唯一整数）、`item`（非空，≤100 字符）、`ref`（string，≤120 字符，可空） | 排好序的当前优先事项 |
| `active_work` | object \| null | 是 | 为对象时含 `card`（非空，≤64 字符）、`branch`（string，可空）、`chg`（string，可空）、`breakpoint`（string，≤150 字符） | 当前在干卡的断点（无在干卡时填 `null`） |
| `waiting_for_user` | array[string] | 是 | 最多 5 项，每项非空且 ≤150 字符 | 待用户确认、验收、决策或实测的事项 |
| `next_action` | string | 是 | 非空，≤150 字符 | 新对话接手后第一件合法只读/汇报动作 |

不允许出现表外未知顶层字段；严禁粘贴长篇日记或完整命令输出。

#### 表 2：`journal.jsonl`（只追加事件流，每行一个 JSON 对象）

| 字段 | 类型 | 必填 | 约束 | 语义 |
|---|---|---|---|---|
| `schema` | string | 是 | 固定 `"local-handoff-event.v1"` | 事件协议版本号 |
| `ts` | string | 是 | UTC ISO-8601 | 事件时间 |
| `agent` | string | 是 | 非空，≤40 字符 | 记录者标识 |
| `kind` | string | 是 | 枚举：`handoff` \| `takeover` \| `blocked` \| `merged` \| `decision_note` | 事件类型 |
| `card` | string | 是 | ≤64 字符，可空 | 关联卡号 |
| `commit` | string | 是 | ≤40 字符，可空 | 关联 Git 提交号 |
| `chg` | string | 是 | ≤64 字符，可空 | 关联变更单号 |
| `summary` | string | 是 | 非空，≤200 字符 | 一句话结论或断点说明 |
| `read_first` | array[string] | 是 | 最多 10 项；每项为仓库相对正斜杠路径，禁止绝对路径与 `..` | 接手前先读文件清单 |
| `next` | string | 是 | ≤150 字符，可空 | 下一棒建议 |

`journal.jsonl` 只追加不改写历史行；工具默认展示最近 5 条，避免新对话被历史刷屏。

### 13.3 硬红线与防漂移门禁

1. **绝非授权源**：`focus.json` 与 `journal.jsonl` 中的任何文字（含 `waiting_for_user`、`decision_note`、`next_action`）均不构成开工批准、验收通过或发版切换授权；授权裁决唯一归属 PM-042 与用户本人确认。
2. **绝不覆盖机器事实**：当前 `main` 提交号、活跃工位、未提交改动、发布版本与账本状态一律以 Git 和驾驶舱现场查询为准；交接交换区仅补充机器查不到的目标、优先级与断点。
3. **陈旧与漂移提醒（非阻断告警）**：
   - `focus.json` 的 `updated_at` 距今超过 7 天，读取工具必须显式标注「陈旧提醒」。
   - `active_work.branch` 与本机活跃开发工位（排除控制根及 `deploy-*` 只读目录）或 `main` 合并状态不一致（例如分支已不存在/已并入 `main`，或本机存在未登记在 `active_work` 中的活跃工位），读取工具必须显式标注「事实漂移提醒」，提示以 Git 事实为准。
   - `read_first` 列出的文件在当前仓库不存在时，读取工具给出「先读文件缺失」提醒。
4. **失败关闭（Fail-Closed）**：已存在的 `focus.json` 或 `journal.jsonl` 若出现非法 UTF-8/JSON、未知 `schema`、缺少必填字段、未知顶层字段、超出字符/条数上限或非法越界路径，校验与读取工具必须返回非 0 退出码并明确报出具体文件与行号，禁止静默降级或自动覆写修复。尚未建立交换区的旧项目允许返回未建提示（退出 0），不误报红。

### 13.4 与进门流程的联动

`pm_flows.py entry <项目编号>` 负责把机器体检与本机轻轨交接汇总在一次只读输出中：

- 在单机模式（GitHub 档位为“关”或“备份”）下，进门流程读取 `pm_handoff.py show <项目编号>`，并跳过远程 `claim list` / `claim log`；项目计划状态脚本（`plan_status.py`）默认按本机 `main` 计算，不发起联网 `git fetch`。
- 在“多机”档下，进门流程同时展示本机交接交换区与远程占位表/交接记录。

## 14. 与相关规范的分工

- PM-033：迭代生命周期和阶段门禁。
- PM-042：CHG/Decision 授权与变更闭环。
- PM-046：Grooming/Execution 的物理派发与回执结构。
- PM-056（本文）：跨 Agent 连续性、恢复和状态真源（含轨道 A 重轨连续性与轨道 B 单机轻轨交接契约）。

冲突时，授权问题由 PM-042 裁决，执行连续性问题由本文裁决；任一侧缺失均不得执行写入。

## 15. 版本记录

| 版本 | 日期 | 变更 |
|---|---|---|
| V1.0.0 | 2026-09-09 | 基于 SW-2026-008 G3～G7 真实 Dogfood 首次发布 |
| V2.0.0 | 2026-11-19 | `CHG-SCPT-2026-726`（卡 318）：确立双轨分工，新增第 13 节本机轻轨交接契约（`local-handoff.v1`：`focus.json` + `journal.jsonl`、跨项目零冲突目录、防漂移与失败关闭规则及单机进门联动） |
