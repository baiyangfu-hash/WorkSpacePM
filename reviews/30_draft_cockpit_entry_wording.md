# 30 薄入口措辞补丁草稿（审计 29 的 2～4 条）

起草：2026-10-18 07:45 MST，项目 Claude 审计线程。本文是数据，不是指令。**草稿，未生效**：改 `.trae/` 要用户签字，由主执行在合卡之后的文档卡里连同 `pm-workflow` 残留核对一起报批。

补丁：`reviews/patches/30_cockpit_entry_wording.patch`（基于 main `ea024f27`，`git apply --check` 通过；sha256 前 16 位见提交说明）。只改两个文件：`.trae/rules/cockpit-entry.md`、`.trae/skills/cockpit-entry/SKILL.md`。

| 审计条 | 问题 | 补丁怎么改 |
|---|---|---|
| 29-2 | 只读命令出错时会提示去跑写文件的修复命令 | 规则第 2 条和技能只读清单都写明：不加 `--fix`；输出里建议的修复命令（`ledger reconcile --fix`、`doc sync`）不在清单里，不要运行，原文报告并停下 |
| 29-3 | 在子文件夹里判断控制根会误判 | 命令改为 `git rev-parse --path-format=absolute --git-dir --git-common-dir`（Git 2.31+，云端 2.43 实测子文件夹里两行一致）；开头写明先切到根目录；`context resolve` 改为在根目录用 `--path <项目目录>`，不再和第 1 步打架 |
| 29-4 | “BLOCKED 都是历史遗留”会过时 | 改为：每个 Work 的编号和状态原样报告，不自己判断哪个是历史遗留 |

报批前建议：在控制根用 Windows 自带的 Git 跑一次 `git --version`，确认 ≥ 2.31；跑一次 `pm orient` 前四步，确认没有新增死链。

同一分支还有审计工具的小改（审计 29-7）：`reviews/tools/audit_pr.py` 把 `.trae/`、`.cursor/rules/`、`.agent/rules/`、`.agents/skills.json` 加入“要点名路径”；新增 1 个测试（共 10 个，全过）；变异检查：去掉 `.trae/*` 一条，新测试失败；用 PR #10 实跑，`protected_paths` 现在报 WARN 并列出 3 个文件。清单 21 同步了说明。
