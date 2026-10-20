# Claude Code 入口（薄入口）

本文件只指路，不含规则；规则真源是根目录 `AGENTS.md`，下面一行把它整篇引入。

@AGENTS.md

1. **新会话第一件事**：读 `.trae/skills/cockpit-entry/SKILL.md` 并照它做——确认当前目录是控制根、确认项目编号、运行只读定位命令，再用中文向用户报告当前焦点、下一步合法动作和冲突。
2. **没有已授权的 Work、Run 与有效租约之前，只允许只读命令**；命令输出里建议的修复命令（如 `--fix`、`doc sync`）不要运行。
3. **本机 Claude Code 的工位和分支前缀**：见 `AGENTS.md` 的“多 agent 工位与控制根规则 (WS-001)”（工位 `.auto-pm/worktrees/claude`，分支 `claude/`）。
4. **不得使用**已隔离的 `pm-workflow`；`PM_SESSION` 和聊天文字都不是授权。
