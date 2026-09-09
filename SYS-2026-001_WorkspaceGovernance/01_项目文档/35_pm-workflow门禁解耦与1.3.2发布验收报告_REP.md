# pm-workflow 门禁解耦与 1.3.2 发布验收报告

> 日期：2026-09-09  
> 变更：`CHG-SCPT-2026-027`  
> 结论：`ACCEPTED / RUNTIME_EFFECTIVE`

## 1. 最终结果

SHC-017 已不再读取或要求维护被冻结、弃用的 `pm-workflow`。活动 skill contract 只保留 fullstack 工程门禁检查；PM 连续性与授权规则分别由 PM-056、PM-042 和事务服务承担，不再形成技能副本真源。

## 2. 发布状态

| 项目 | 结果 |
|---|---|
| active | `1.3.2-9d3c920` |
| previous | `1.3.1-a7dae04` |
| source commit | `9d3c9205` |
| release commit | `abae03a2`，manifest 哈希修正 `9e4fa230` |
| cutover commit | `f182191a` |
| payload | 468 个文件，exact-tree 通过 |

## 3. 验证

- 定向：5 passed；Ruff、Mypy Exit 0。
- 全量：1841 passed、14 skipped、60 warnings，Exit 0。
- detached Git checkout：exact-tree Exit 0，dirty 0；临时 worktree 已移除。
- 标准入口：active 解析 Exit 0。
- SHC-017：0 项错误，Exit 0。
- 完整 spec check：SHC-017 已消失；仅余 3 项既有 SHC-011 投影版本债务，Exit 1。

## 4. 边界与回退

未读取或修改 `.trae/skills/pm-workflow`，未修改 PM_SESSION、DEV-300、PLC/LSP 或用户脏文件。若需回退，将 active 指针恢复到 `1.3.1-a7dae04`；不得恢复 pm-workflow owner 身份。
