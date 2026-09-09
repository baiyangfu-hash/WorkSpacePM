# G6 Resume V2 与 PM_SESSION 投影验收报告

> 日期：2026-09-09
> 状态：`DEV_ACCEPTED / RUNTIME_NOT_EFFECTIVE`
> 基线：`0d3cc9b3`

## 1. 结论

G6 已在研发母体完成。Resume v2 只组合 Workspace Context v2 与 Continuity Store；PM_SESSION 被实现为项目摘要投影，不再承载 Work/Run 执行队列。现场 PM_SESSION 已有其他 owner 的未提交修改，本包未改写该文件。

## 2. 关键语义

- 返回 `subject/control/development/runtime/release` 身份和可选的 `work/run/checkpoint/lease`。
- Continuity Store 不存在时只返回身份，Work/Run/Checkpoint/lease 与下一动作均明确为空，且读取不会创建数据库。
- 同时存在多个活动 Work 或 Run 时返回 conflict，不选择“最新项”。
- 过期 lease 返回 `LEASE_EXPIRED` conflict 并抑制下一动作。
- 有 Run、无 Checkpoint 时返回 `CONTINUE_RUN`；只有存在恢复点时才允许 `CONTINUE_FROM_CHECKPOINT`。
- 指定 Work/Run 时校验 subject 与父链，不允许跨项目或跨 Work 拼接。
- PM_SESSION 投影只包含项目身份、控制面、研发/运行根、release 和 evidence_id；不写入 Work ID、Run ID、current_focus 或 next action。
- 损坏的 Continuity Store 失败关闭，不回退到旧 PM_SESSION 叙述猜测。

## 3. 验证证据

| 门禁 | 结果 |
|---|---|
| G3–G6 定向测试 | `40 passed`，Exit 0 |
| 空 Store / 多活 / 过期 lease / 损坏 DB | 全部符合失败关闭预期 |
| PM_SESSION 投影越界写入 | 拒绝 |
| Ruff | All checks passed，Exit 0 |
| Mypy | Success，Exit 0 |
| 研发母体全量 pytest | `1839 passed, 14 skipped, 60 warnings`，Exit 0 |

60 个 warning 为既有 Copier 弃用告警，本包未扩大范围处理。

## 4. 精确交付文件

- `auto_pm/contracts/continuity_resume.py`
- `auto_pm/infrastructure/continuity_store.py`
- `auto_pm/application/core/continuity_resume_service.py`
- `auto_pm/application/core/pm_session_projection_service.py`
- `tests/core/test_continuity_resume_service.py`
- 本报告及治理总计划状态更新

## 5. 后续

下一合法动作是 G7。G7 必须先把 v2 能力接入不持有状态的 adapter，再从已提交母体构建候选 release 并做 inactive 验证；未完成真实双 Agent Dogfood 前不得修改 Obsidian 正式规范。
