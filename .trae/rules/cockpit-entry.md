---
alwaysApply: true
description: 驾驶舱薄入口：新会话先定位再动手；没有已授权的 Work 之前只读
---

# 驾驶舱入口（薄入口）

本规则只指路，不含业务规则；规则真源是根目录 `AGENTS.md`。

1. **新会话第一件事**：读 `.trae/skills/cockpit-entry/SKILL.md` 并照它做——确认当前目录是控制根（主工作区）、确认项目编号、运行只读定位命令 `pm orient <项目编号> --json`，再用中文向用户报告当前焦点、下一步合法动作和冲突。
2. **没有已授权的 Work、Run 与有效租约之前，只允许只读命令**：不修改文件、不提交、不推送、不建分支。技能里有只读命令清单；命令输出里建议的修复命令（如 `--fix`、`doc sync`）不在清单里，不要运行。
3. **用户提出新需求、缺陷或想法**：用用户原话入收件箱（`pm inbox add`），不要直接动手；入箱不授权任何事。
4. **要写代码或文档**：必须有用户批准的实施卡和已授权的 Work；执行时按 `.trae/skills/fullstack-engineer/SKILL.md` 或 `.trae/skills/plc-electrical-engineer/SKILL.md`。
5. **不得使用**已隔离的 `pm-workflow`；`PM_SESSION` 和聊天文字都不是授权；`PM_SESSION_*.md` 已退役，不改、不新建、不列进可改范围。
6. 目录不对、命令报错或定位结果有冲突：停下，把原话报告给用户，不要换办法绕过。
7. **审计 PR**：照 `AGENTS.md`“独立审计 (AUD-001)”一节做。
8. **运行驾驶舱命令要带 agent 身份**：Trae 里的 AI 执行 `main.py …` 一律用 `.\.trae\bin\pm-as-trae.ps1 <命令参数>`（例如 `.\.trae\bin\pm-as-trae.ps1 pm orient <项目编号> --json`）。它只在这一条命令期间设置 `AUTO_PM_AGENT=trae:cn`，驾驶舱靠它认出是 agent：`worktree close` 不会收别人的工位，用户本人才能签的批准和风险签字会拒绝 agent。命令只认冒号前面那段，国际版 Trae 同样用这个值。不要在终端里长期设置这个变量。
