# 规范与入口去 Claude 绑定：审查结果与改法

对应变更单 CHG-SCPT-2026-483（动态 agent 名）。本文只列规则文字侧的改动；代码侧由本机线程负责。

## 结论

动态别名 `<基名>-<会话ID前6位>` 要求规则文字同步改，否则 Cursor、VS Code、Trae、Codex 照旧写法会出两类问题：工位名对不上，以及没有身份标记的 agent 被当成用户本人。

## 绑死 Claude 的地方与处理

| # | 位置 | 问题 | 处理 |
|---|------|------|------|
| 1 | `AGENTS.md` WS-001 | 工位写死 `worktrees/<agent>`，一个 agent 一个工位，同机多对话装不下 | 本 PR：新增“agent 名字规则”，基名定前缀、别名定工位目录 |
| 2 | `AGENTS.md` WS-001 末段 | 调用方识别只提 `CLAUDECODE`、`CODEX_*` | 本 PR：改为以 `AUTO_PM_AGENT` 为准，其余是额外自动标记 |
| 3 | 身份标记（安全相关） | 只有 Claude、Codex 自带环境变量；Cursor、Copilot 无标记，会被当成用户本人，可跑口令类命令 | 本 PR 写明必须自带 `AUTO_PM_AGENT=<基名>`；机器侧补强见下“后续” |
| 4 | `CLAUDE.md` 第 3 条 | 写死 `.auto-pm/worktrees/claude` | 本 PR：改为基名加别名 |
| 5 | `.trae/skills/cockpit-entry/SKILL.md`、`.trae/rules/cockpit-entry.md`、`.trae/bin/pm-as-trae.ps1` | 身份包装脚本只有 Trae 版，其他 agent 没有同类入口 | 后续：`.trae/` 其他 AI 只读，需用户原话；建议新增通用 `pm-as-agent.ps1 <基名> <参数>`，Trae 版改为调用它 |
| 6 | `.cursor/rules/workspace-ai-coexistence.mdc`、`.agent/rules/project-rule.md` | 工位写成 `worktrees/cursor`；未写身份声明方式 | 后续：改为“基名 cursor，别名由会话ID派生；跑 `main.py` 前带 `AUTO_PM_AGENT=cursor`” |
| 7 | `.claude/hooks/session-start.sh`、`settings.json` | 只有 Claude 云端有开机自检；`SessionEnd` 回收钩子也只能是 Claude 的 | 不改。其他 agent 靠兜底回收和手动 `worktree close`，已写进规则第 4 条 |
| 8 | `docs/handover/01_…`、`24_…`、`25_…`、`90_…` | 多处“Claude 云端”“Claude 一直…”，且 90 号第 2、4 条写明 Claude 退出后无人接主执行 | 后续：随用户对 90 号条目的裁定一并改成角色名（主执行、云端执行、审计） |
| 9 | `agent_worktree_service.py`（`AGENT_ROSTER`、`caller_agent`）、`lease_handover_service.py`（`AGENT_MARKERS`）、`ui/cli` 的 `click.Choice` | 名册写死；见本机线程设计稿 | 代码归本机线程，不在本 PR |

## 与本机线程对齐的约定

- 基名复用现有 `AUTO_PM_AGENT`，不新增 `AUTO_PM_AGENT_BASE`。
- 会话 ID 顺序：`AUTO_PM_SESSION_ID` → `CLAUDE_CODE_SESSION_ID` → 自动生成。
- 别名只能由会话 ID 派生；agent 不得手写别名。
- 回收：Claude 用 `SessionEnd`，其他靠“进程不在且心跳超时且无未过期租约”，默认只列出。

## 后续（需要用户同意）

1. 改 `.trae/`、`.cursor/`、`.agent/` 的第 5、6 项：这几处在受保护清单里，需要用户原话。
2. 机器侧补强：对没有身份标记的会话，口令类命令除了“无标记即用户”，还应要求交互式终端（TTY）。这是否可行，要本机线程在 Windows 上实测，本文未核实。
3. 本 PR 改了 `AGENTS.md`，合并前需要用户在 PR 上评论“规则批准 <头提交号>”（rules-gate）。
