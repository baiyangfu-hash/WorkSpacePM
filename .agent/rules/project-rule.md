---
description: "跨 AI 协作统一入口（Antigravity / Codex / Trae / Cursor）— 指向 .trae 单一真源"
alwaysApply: true
---

# 工作空间 AI 统一协作准则（引用入口）

> **退役隔离**：`pm-workflow` 为 `QUARANTINED / DECOMMISSIONED`，未注册为可用技能，不得读取或调用。PM 作为治理角色通过 CHG、Decision 与 Continuity v2 工作；旧计划、PM_SESSION 与 handoff.v1 仅作证据输入。

本工作空间由多个 AI 协作开发（Antigravity、Codex、Trae、Cursor）。**所有 AI 严格遵循同一套真源，禁止重复维护规则内容**。

## 单一真源索引

| 用途 | 绝对路径 |
|:---|:---|
| **全局开发规则** | `.trae/rules/project-rule.md` |
| **跨技能公共契约** | `roles/shared/refs/skill_coordination.md` |
| **治理基线** | `SYS-2026-001_WorkspaceGovernance/01_项目文档/26_SW-2026-008_治理恢复与连续性重基线总计划_PM.md` |
| **当前计划与状态投影** | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/驾驶舱开发基线_20261114/02_里程碑与WBS.md`（以其“当前排序”一节为准；39 号计划是历史依据） |
| **PLC 电气工程** | `roles/plc-electrical-engineer/SKILL.md` |
| **全栈高级语言** | `roles/fullstack-engineer/SKILL.md` |
| **Obsidian 规范注册表** | `00_Obsidian_Base全局规范文件仓库/spec_registry.json` |
| **全局协作入口** | `AGENTS.md` |
| **工位与控制根规则** | `AGENTS.md`“多 agent 工位与控制根规则 (WS-001)”：每台电脑 1 个控制根，每个对话一个工位 `.auto-pm/worktrees/<基名>-<会话ID前6位>`（名字规则见该节） |
| **运行驾驶舱命令的身份声明** | 没有自带身份标记的 agent 一律用 `00_Infrastructure/bin/pm-as-agent.ps1 <基名> <命令参数>`（只在单条命令内设置 `AUTO_PM_AGENT`），否则会被当成用户本人；口令类命令（`pm approve`、`pm accept`、`pm sign-risk`）不要用它运行 |
| **独立审计（审 PR 时）** | `AGENTS.md`“独立审计 (AUD-001)” |

## 规则优先级

冲突时：项目级 > 技术栈规则 > 全局规则。

> 本文件是**引用入口**。退役隔离条款优先于旧 PM 路由；执行技能只消费已授权 Work/Run，不拥有治理状态。
