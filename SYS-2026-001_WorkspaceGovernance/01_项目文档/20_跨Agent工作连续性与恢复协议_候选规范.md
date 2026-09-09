# 跨 Agent 工作连续性与恢复协议（候选）

**状态**：候选；仅供评审与后续 Dogfood，非 Obsidian 正式规范，尚未生效。
**变更单**：CHG-SPEC-2026-010
**适用边界**：My_Workspace 内的项目上下文恢复、执行工作项和 Agent 交接；不改变 PLC、SRE 或业务交付规则。

## 1. 目的与不变项

本协议消除“从文本猜测当前项目”的恢复方式。它定义可验证的 Project、Work、Run、Checkpoint 和 Handoff 边界，并要求缺少身份或证据时失败关闭。

它不授予变更授权、不替代 CHG 审批、不把平台 Adapter 变成核心状态库，也不在本候选阶段修改任何 Obsidian 文件、注册表或索引。

## 2. 真源与职责

| 对象 | 真源 | 写入者 | 用途 |
|---|---|---|---|
| Project State | 项目 PM_SESSION | PM | 项目级目标、边界和已批准的决策摘要 |
| Work | 待建设的工作注册表 | PM / 调度器 | 一个可委派、可归属的工作单元 |
| Run | 待建设的运行记录 | 执行器 | Work 的一次实际执行 |
| Checkpoint | 待建设的检查点记录 | 执行器、PM 确认 | 可恢复状态和证据锚点 |
| Handoff | 现有 handoff 记录 | 派发方/执行方 | 交接、lease、回执；不写 Project State |
| CHG | 变更单及审批历史 | PM / 审批者 | 授权范围、条件和关闭结论 |
| 规范法典 | Obsidian 正式规范 | 获批发布流程 | 对外生效的规则 |
| 索引数据库 | `index.db` | 索引器 | 可再建投影，非以上对象真源 |

`subject_project_id` 是被操作项目；`control_project_id` 仅在明确映射时表示治理控制面。两者不得以同名、文本包含或默认值推断。

## 3. Context Resolve 最小契约

成功结果至少含：`schema_version`、`subject_project_id`、`control_project_id`（可空）、`development_root`、`runtime_root`、`release_id`、`resolution_source`、`read_set`、`evidence` 与 `conflicts`。每项路径必须为工作区内的规范化相对路径；每项读取证据应含路径和内容指纹。

解析优先级固定为：

1. 用户显式传入的项目标识；
2. 调用目录向上逐层寻找唯一项目锚点；
3. 已验证的项目—控制面映射。

不得递归扫描整个工作区、不得用 PM_SESSION 文本包含关系选择控制面、不得把 `ai_context.json` 当默认项目。无锚点、多候选、映射冲突、运行槽位不完整或指纹不匹配均返回结构化失败，要求显式选择。

## 4. Work、Run、Checkpoint 与 Handoff

Work 是授权范围内的逻辑工作单元，必须有 `work_id`、`subject_project_id`、owner、生命周期和关联 CHG。Run 是 Work 的一次执行，必须有 `run_id`、开始/结束时间、执行环境、源/目标 Git 基线与结果。Checkpoint 是可恢复事实，必须有 `checkpoint_id`、所属 Work/Run、状态、证据和下一合法动作。Handoff 传递 Work/Run/Checkpoint 的引用和 lease；它不能通过自由文本改写范围或 PM_SESSION。

所有对象使用不可变事件追加和显式状态迁移；结果提交必须验证 owner/lease、基线、所需证据和 schema 版本。冲突、过期 lease、dirty tree 未声明、未知 schema 均失败关闭。

## 5. 运行与 Git 约束

`development_root` 与 `runtime_root` 必须分别记录。Adapter 只能调用经解析的工作区启动入口；规范表达语义命令，不硬编码全局解释器、Trae 目录或某 IDE。执行前记录 Git `HEAD`、dirty 状态和允许路径；共享脏树只允许读取或经 CHG 明确批准的单一 owner 写入。并行写入或隔离需求使用工作树，归并前重新验证基线。

## 6. 兼容、发布与生效

本协议的候选版本不具强制力。后续实现先以 capability/version 声明与 v1 handoff 兼容；旧对象缺少新字段时仅可只读展示或由明确迁移记录补全，不得猜测。

正式发布的原子单元必须同时包含：获批规范正文、PM-033/042/046 和 PM-004/010 的获批差异、注册表/索引更新、实现版本、Dogfood 证据、回退指针。任一项缺失则不发布，旧规范继续生效。
