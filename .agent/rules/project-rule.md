---
description: "跨 AI 协作统一入口（Antigravity / Codex / Trae / Cursor）— 指向 .trae 单一真源"
alwaysApply: true
---

# 工作空间 AI 统一协作准则（引用入口）

> **治理冻结**：`pm-workflow` 当前为 `QUARANTINED`，不得读取或调用。治理任务唯一入口为 `SYS-2026-001_WorkspaceGovernance/01_项目文档/26_SW-2026-008_治理恢复与连续性重基线总计划_PM.md`；旧计划与 PM_SESSION 仅作证据输入。

本工作空间由多个 AI 协作开发（Antigravity、Codex、Trae、Cursor）。**所有 AI 严格遵循同一套真源，禁止重复维护规则内容**。

## 单一真源索引

| 用途 | 绝对路径 |
|:---|:---|
| **全局开发规则** | `.trae/rules/project-rule.md` |
| **跨技能公共契约** | `.trae/skills/shared/refs/skill_coordination.md` |
| **治理冻结期主计划** | `SYS-2026-001_WorkspaceGovernance/01_项目文档/26_SW-2026-008_治理恢复与连续性重基线总计划_PM.md` |
| **隔离对象（禁止使用）** | `.trae/skills/pm-workflow/SKILL.md` |
| **PLC 电气工程** | `.trae/skills/plc-electrical-engineer/SKILL.md` |
| **全栈高级语言** | `.trae/skills/fullstack-engineer/SKILL.md` |
| **Obsidian 规范注册表** | `00_Obsidian_Base全局规范文件仓库/spec_registry.json` |
| **全局协作入口** | `AGENTS.md` |

## 规则优先级

冲突时：项目级 > 技术栈规则 > 全局规则。

> 本文件是**引用入口**。治理冻结条款优先于旧 PM 路由；`.trae/` 保持只读，待治理验收后再决定是否恢复或替换 PM 技能。
