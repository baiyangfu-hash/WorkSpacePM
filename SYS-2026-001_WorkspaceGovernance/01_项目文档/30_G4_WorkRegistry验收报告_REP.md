# G4 Work Registry 验收报告

> 日期：2026-09-09
> 状态：`DEV_ACCEPTED / RUNTIME_NOT_EFFECTIVE`
> 基线：`141dec37`

## 1. 结论

G4 已在 SW-2026-008 研发母体完成并通过验收。新增能力仅存在于研发母体，尚未构建或切换稳定运行槽，因此不得表述为运行时已生效。

## 2. 实现边界

- 新增平台中立 `WorkItem`、`WorkKind`、`WorkState` 契约。
- 新增独立 SQLite Continuity Store，默认目标为工作空间根 `.auto-pm/continuity.db`。
- 使用 WAL、外键、`BEGIN IMMEDIATE`、乐观版本号、幂等键和追加式哈希链事件。
- Work 写入型任务先进入 `PLANNED`；只有经 Decision Package 的项目与文件范围校验后才可进入 `READY`。
- 只读 Work 可用 `READ_ONLY` 授权直接进入 `READY`。
- Work 关系采用受限类型并持久化，禁止自关联和跨 Work 复用幂等键。
- 未读取、改写或双写既有 `index.db`；未迁移 PM_SESSION、旧 handoff 或真实历史状态。

## 3. 验证证据

| 门禁 | 结果 |
|---|---|
| G4 定向测试 | `12 passed`，Exit 0 |
| Ruff（4 个 G4 文件） | All checks passed，Exit 0 |
| Mypy（3 个 G4 源文件） | Success，Exit 0 |
| 研发母体全量 pytest | `1824 passed, 14 skipped, 60 warnings`，Exit 0 |
| 真实 `.auto-pm/continuity.db` | `ABSENT`，验证未污染真实运行状态 |

全量测试中的 60 个 warning 均为既有 Copier `now`/`utcnow` 弃用告警；本包未将其误报为通过的静态债务，也未扩大范围处理。

## 4. 精确交付文件

- `auto_pm/contracts/continuity.py`
- `auto_pm/infrastructure/continuity_store.py`
- `auto_pm/application/core/work_registry_service.py`
- `tests/core/test_work_registry_service.py`
- 本报告及治理总计划状态更新

## 5. 回退与后续

本包不触碰运行指针和真实数据库。回退仅需撤销本包提交，不涉及数据回滚。下一合法动作是 G5：在同一事务真源上增加 Run、Checkpoint、lease、owned paths、Git 基线、evidence 和 Handoff V2，并继续使用临时工作空间做故障注入。
