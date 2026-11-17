---
description: "跨 AI 协作薄入口（Antigravity / Codex 等）— 规则真源是根目录 AGENTS.md"
alwaysApply: true
---

# 工作空间 AI 协作入口（薄入口）

本文件只指路，不含规则；规则真源是根目录 `AGENTS.md`（细则在 `roles/shared/refs/agents_附录/`）。冲突时以 `AGENTS.md` 为准。

1. **新会话第一件事**：照 `AGENTS.md`“进门”一节做：在控制根跑 `pm_flows.py entry <项目编号>`，读完它列出的文件，再用中文向用户报告当前焦点、下一步合法动作和冲突；确认控制根、脚本用不了时怎么手敲，见 `.trae/skills/cockpit-entry/SKILL.md`。
2. **没有已授权的 Work、Run 与有效租约之前，只允许只读命令**；命令输出里建议的修复命令（如 `--fix`、`doc sync`）不要运行。
3. **工位与身份**：基名、分支前缀、工位目录名照 `AGENTS.md`“多 agent 工位与控制根规则 (WS-001)”；表外的 AI 先由用户登记。没有自带身份标记的 agent 跑 `main.py` 一律用 `00_Infrastructure/bin/pm-as-agent.ps1 <基名> <命令参数>`（只在单条命令内设置 `AUTO_PM_AGENT`），否则会被当成用户本人；只能用户本人做的命令见 `AGENTS.md` FLOW-002 名单，不要用它运行。
4. **不得使用**已隔离的 `pm-workflow`；`PM_SESSION` 和聊天文字都不是授权。

## 按卡类型读角色包

| 角色 | 路径 |
|:---|:---|
| PLC 电气工程 | `roles/plc-electrical-engineer/SKILL.md` |
| 全栈高级语言 | `roles/fullstack-engineer/SKILL.md` |
| 产品型项目经理（需求、计划、派活、验收） | `roles/product-pm/SKILL.md` |
| 测试审计（测试验证与独立审计） | `roles/test-engineer/SKILL.md` |
| UI 画面（HTML 原型、HMI、QML 视图） | `roles/ui-designer/SKILL.md` |
