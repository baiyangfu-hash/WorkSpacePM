# G5 Run / Checkpoint / Handoff V2 验收报告

> 日期：2026-09-09
> 状态：`DEV_ACCEPTED / RUNTIME_NOT_EFFECTIVE`
> 基线：`0a0a4276`

## 1. 结论

G5 已在 SW-2026-008 研发母体完成并通过故障注入与全量回归。能力尚未构建到稳定运行槽，真实 handoff、PM_SESSION、Continuity Store 和 release 指针均未写入。

## 2. 已闭环能力

- Run 绑定 `work_id`、executor、adapter、`owned_paths`、声明 dirty 范围、Git HEAD 和 worktree 路径。
- 每个 Run 建立排他、带 token、版本号和到期时间的 lease；错误 owner、错误 token、过期 lease 和并发版本冲突均失败关闭。
- Checkpoint 是不可变、递增序号且包含摘要、Git 基线、dirty paths 和 evidence 的恢复点。
- Handoff V2 只引用已从事务真源回读的 Work/Run/Checkpoint，快照带 SHA-256 指纹。
- 接收 Handoff 时原子转移 lease；转移后旧 owner 立即失权。
- `handoff.v1` 只读兼容，不导入可变真源；未知 schema 拒绝。
- 新表与 Work Registry 共用 `.auto-pm/continuity.db` 事务边界，不复用 `index.db`。

## 3. 故障注入与门禁

| 场景/门禁 | 结果 |
|---|---|
| 未声明 dirty path、越界 owned path | 拒绝 |
| 错误/过期 lease | 拒绝 |
| Git baseline drift | 拒绝 |
| 未知 handoff schema | 拒绝 |
| 终态 Run 重开 | 拒绝 |
| Handoff 接收后旧 owner 续租 | 拒绝 |
| G4+G5 定向测试 | `20 passed`，Exit 0 |
| Ruff | All checks passed，Exit 0 |
| Mypy | Success，Exit 0 |
| 研发母体全量 pytest | `1832 passed, 14 skipped, 60 warnings`，Exit 0 |

60 个 warning 仍为既有 Copier 弃用告警，不属于本包范围。

## 4. 精确交付文件

- `auto_pm/contracts/continuity.py`
- `auto_pm/infrastructure/continuity_store.py`
- `auto_pm/application/core/continuity_execution_service.py`
- `tests/core/test_continuity_execution_service.py`
- 本报告及治理总计划状态更新

## 5. 回退与后续

本包没有真实运行态数据，回退只需撤销本包提交。下一合法动作是 G6：新增 Resume v2 编译器和 PM_SESSION 项目摘要投影器，并以临时数据库验证空 Work/Run、有效链、冲突链和旧 v1 降级路径。
