# G7 发布适配与真实 Dogfood 验收报告

> 日期：2026-09-09  
> 结论：`ACCEPTED / RUNTIME_EFFECTIVE`  
> 生效版本：`1.3.1-a7dae04`  
> 回退版本：`1.2.4-6699a5b`

## 1. 验收结论

G3～G7 的平台中立连续性能力已进入 active release。标准入口、候选精确树、纯 Git checkout、真实 Continuity Store、Work/Run/Checkpoint/Handoff、双适配器冷启动和回退链均已验证。`pm-workflow` 保持 `QUARANTINED / DO_NOT_USE`，不再是 PM owner、路由入口或状态落账 owner。

## 2. 生效对象

- active：`00_Infrastructure/auto_pm/releases/1.3.1-a7dae04`
- previous：`00_Infrastructure/auto_pm/releases/1.2.4-6699a5b`
- source commit：`a7dae04a64e9eb5d91bba67ee3769651a100545c`
- release commit：`638a6d3d5aabb16ec4b108ffe034b383a9ee11c6`
- 运行事实源：`.auto-pm/continuity.db`
- Dogfood：`WORK-G7-DOGFOOD-20260909` / `RUN-G7-DOGFOOD-20260909` / `CP-G7-DOGFOOD-20260909`

## 3. 实测证据

| 验证项 | 结果 |
|---|---|
| 母体全量 pytest | `1842 passed, 14 skipped, 60 warnings`，Exit 0 |
| Ruff / Mypy | 目标文件 Exit 0 |
| inactive exact-tree | 468 个 payload 文件全部匹配 manifest，Exit 0 |
| detached worktree | HEAD `638a6d3d`，dirty 0，exact-tree Exit 0，临时 worktree 已移除 |
| 标准入口 | `main.py --resolve-only` 命中 active `1.3.1-a7dae04`，Exit 0 |
| 真实交接 | lease `codex → cursor` 原子转移；旧 owner 失权 |
| 双适配器冷启动 | 独立 Codex/Cursor 进程 payload 字节级一致，SHA-256 `4236caa79480a883cf7c56056a6387cfdecd1cdc9e8b020ed8e316a897f6e8ae` |
| 执行闭环 | Work=`CLOSED`，Run=`SUCCEEDED`，next action 为空 |
| 权限隔离 | Resume 使用 `lease-view.v1`，不返回 `lease_token` |
| 回退 | 首次切流失败时 active/previous 已恢复；launcher 自动命中 previous，证明回退链有效 |

## 4. Dogfood 发现及处置

1. PowerShell `-c` 注入中文 scope 产生转码污染。失败数据库未删除，已归档为 `.auto-pm/reports/g7_rejected_dogfood_encoding_20260909.db`；正式 Dogfood 改用稳定 ASCII 治理路径。
2. 直接导入候选产生 `__pycache__`，exact-tree 正确拒绝。临时缓存已精确清理；候选执行统一禁用字节码写入。
3. 两个 `GlobalVars.db` 模板被通用 `*.db` 忽略，导致纯 worktree 缺文件。已通过提交 `465a615a` 精确纳入发布快照，运行态 `continuity.db` 仍保持忽略。
4. Resume 曾暴露 lease capability token。1.3.0 被拒绝，不再激活；1.3.1 引入只读 `LeaseView` 和防泄漏回归测试。

## 5. 状态裁决

- G3 Context v2：`RUNTIME_EFFECTIVE`
- G4 Work Registry：`RUNTIME_EFFECTIVE`
- G5 Run/Checkpoint/Handoff v2：`RUNTIME_EFFECTIVE`
- G6 Resume v2 / PM_SESSION 项目投影：`RUNTIME_EFFECTIVE`
- G7：`ACCEPTED / RUNTIME_EFFECTIVE`
- `pm-workflow`：继续隔离，不解除、不调用、不作为 G8 工具

## 6. 下一合法动作

进入 G8，只对连续性协议、PM-033、PM-042、PM-046 及其必要注册表/索引做后置生效整改。DEV-300、PLC/LSP、PM-043/045 和全库冷热清洗不在范围内。
