# 本地技能入口说明

规则真源是根目录 `AGENTS.md`。可用技能以 `.agents/skills.json` 的登记为准（`cockpit-entry`、`fullstack-engineer`、`plc-electrical-engineer`）；另有未登记的维护技能 `find-skills`。

## 第一入口

### `cockpit-entry`（驾驶舱薄入口）

任何 IDE 或 agent 进入本工作区，第一件事都走它：确认在控制根、确认项目编号、运行只读定位命令 `pm orient <项目编号> --json`，再向用户报告当前焦点和下一步合法动作。没有已授权的 Work 之前只跑只读命令。详见 `cockpit-entry/SKILL.md`。

## 执行技能（有已授权的 Work 之后）

### `fullstack-engineer`

Python / 上位机 / 前后端的实现、联调、修复与验证。

### `plc-electrical-engineer`

PLC / HMI / 电气交付项目的程序与技术文档。

## 维护入口

### `find-skills`

查找外部技能、评估是否需要安装新技能。

## 已隔离，禁止使用

- `pm-workflow`：自 2026-09-09 起为 `QUARANTINED / DECOMMISSIONED`，不得调用。目录已于 2026-10-25 按用户决定删除（历史内容见 Git 历史与既有 Decision，不作当前指令）。PM 是治理角色，通过 CHG、Decision 与 Continuity v2 工作。
- `PM_SESSION_<项目编号>.md` 与 handoff.v1 已退役（2026-10-10 裁决），不再回写，仅作历史证据；当前状态以 `pm orient` / `pm resume` 输出为准。

## 不再作为主入口的旧技能

以下技能已归档到 `.trae/skills_archive/`：

- `breakdown-plan`
- `github-project-management`
- `prd`
- `product-requirements`
- `wireframe-design`
- `wireframe-prototyping`

## 选择原则

- 刚进工作区、不知道现在该做什么：`cockpit-entry`
- 有已授权的 Work，做软件实现、调试、联调：`fullstack-engineer`
- 有已授权的 Work，做 PLC / 电气程序与文档：`plc-electrical-engineer`
- 新需求、缺陷或想法：按 `cockpit-entry` 用用户原话入收件箱（`pm inbox add`），不要直接动手
- 需要扩展新能力：`find-skills`
