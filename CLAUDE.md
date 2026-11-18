# Claude Code 入口（薄入口）

本文件只指路，不含规则；规则真源是根目录 `AGENTS.md`，下面一行把它整篇引入。

@AGENTS.md

1. **新会话第一件事**：照 `AGENTS.md`“进门”一节做：在控制根跑 `pm_flows.py entry <项目编号>`，读完它列出的文件，再用中文向用户报告当前焦点、下一步合法动作和冲突；确认控制根、项目编号、脚本用不了时怎么手敲，见 `.trae/skills/cockpit-entry/SKILL.md`。
2. **“要你点头”那一类（见 `AGENTS.md` FLOW-001）在变更单被用户批准之前，只做只读命令、建变更单和领卡号，此外不改仓库里的文件**；其余改动直接做、事后告诉用户；控制根的 `main` 只由 `pm_merge.py merge` 改（见 `AGENTS.md` FLOW-002“本机收口”、GH-001）；Work/Run/租约只在看板一键流和命令本身要求时才要；命令输出里建议的修复命令（如 `--fix`、`doc sync`）不要运行。
3. **本机 Claude Code 的工位和分支前缀**：见 `AGENTS.md` 的“多 agent 工位与控制根规则 (WS-001)”（基名 `claude`，分支 `claude/`；工位目录名用别名 `claude-<会话ID前6位>`，名字规则见附录 `roles/shared/refs/agents_附录/03_工位细则.md`）。
4. **不得使用**已隔离的 `pm-workflow`；`PM_SESSION` 和聊天文字都不是授权。
