---
spec_id: PM-056
title: 跨 Agent 工作连续性与恢复协议
version: V1.0.0
domain: pm
lifecycle: stable
type: PM
status: active
created: 2026-09-09
updated: 2026-09-09
author: Codex（架构师/PM）
canonical_path: "00_Obsidian_Base全局规范文件仓库/01_项目管理域/00_元规则与治理/056_跨Agent工作连续性与恢复协议_PM.md"
tags: [连续性, Resume, Handoff, Work, Run, Checkpoint, Agent]
parent: "[[010_通用项目管理规范_PM|010_通用项目管理规范]]"
related:
  - "[[033_功能模块迭代流程标准_PM]]"
  - "[[042_通用变更管理流程规范_PM]]"
  - "[[046_通用任务派发契约模板_PM]]"
---

# 跨 Agent 工作连续性与恢复协议

## 1. 目的与适用范围

本协议定义不同 AI、IDE、CLI 和人工执行者之间可验证、可恢复、可回退的工作连续性边界。它是平台中立的上位协议；具体平台只提供 Adapter，不得成为核心状态真源。

适用于需要跨会话、跨 Agent、跨工作树或跨运行版本继续执行的项目管理、软件开发和工程交付。单次纯问答不强制创建执行对象。

## 2. 对象边界

| 对象 | 唯一职责 | 禁止承载 |
|---|---|---|
| Project | 长期业务身份与项目元数据 | 当前执行队列 |
| Governance / CHG / Decision | 范围、风险和变更授权 | 执行进度、lease |
| Work | 一个可独立授权、验收和关闭的逻辑工作单元 | 某次进程细节 |
| Run | Work 的一次执行尝试 | 跨 Run 共享状态 |
| Checkpoint | Run 的不可变恢复点 | 原位覆盖的 current state |
| Handoff | 对指定 checkpoint 的交接快照 | 自由文本授权 |
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
| PM_SESSION | 项目摘要投影，不是执行队列或授权源 |

Adapter、聊天上下文、PM_SESSION、handoff 文本和“已完成”口头回执均不得覆盖上述权威源。

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

## 13. 与相关规范的分工

- PM-033：迭代生命周期和阶段门禁。
- PM-042：CHG/Decision 授权与变更闭环。
- PM-046：Grooming/Execution 的物理派发与回执结构。
- PM-056（本文）：跨 Agent 连续性、恢复和状态真源。

冲突时，授权问题由 PM-042 裁决，执行连续性问题由本文裁决；任一侧缺失均不得执行写入。

## 14. 版本记录

| 版本 | 日期 | 变更 |
|---|---|---|
| V1.0.0 | 2026-09-09 | 基于 SW-2026-008 G3～G7 真实 Dogfood 首次发布 |
