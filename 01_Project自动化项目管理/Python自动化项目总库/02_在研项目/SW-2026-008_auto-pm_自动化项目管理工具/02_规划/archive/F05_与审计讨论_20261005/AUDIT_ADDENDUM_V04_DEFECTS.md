# 审计补充：V04 真实进程演练发现的两个缺陷（事实，供只读审计参考）

> 日期：2026-10-05。性质：事实说明，不是新的任务指令；原审计提示词的范围、只读边界与报告位置不变。
> 状态：修复**尚未提交**，只存在于卡 052（V1.0，SHA-256 `131edf48c03a62e9ff21a41b4e183e6a88c86023dc543deb6b95842b5d36d495`）的草案与演练证据里，等用户批准；审计对象的提交仍是 `4e165cf4`（第 1 期，CHG-SCPT-2026-379 待用户验收）。

## 缺陷一：E06 重启对账在真实派发路径上认不出原 session

- 位置：`ContinuityExecutionService.resolve_started_run`（`auto_pm/application/core/continuity_execution_service.py`，基线 `4e165cf4`）。
- 事实：它把 Run 的 `executor_id` 与派发回执的 `executor_id` 比较；真实派发创建的 Run 记的是“适配器:执行者”（回执的 `owner_id`，例如 `codex:agent-a`），回执的 `executor_id` 是裸的 `agent-a`。所以真实路径上 `ExecutionSupervisorService.recover_started_session` 总是报运行身份不可恢复。
- 为什么 M1 阶段的测试没发现：`tests/core/test_continuity_execution_service.py::test_service_reconciles_operation_receipt_run_and_started_identity` 用手造对象，让两边都等于 `agent-a`。
- 发现方式：V04 的真实进程演练 r02（杀主控后由新进程在服务层调用对账）。
- 建议审计时顺带看：其他用手造身份数据的单元测试是否掩盖了同类问题（已登记为拟新增的 `TD-SW008-075`）。

## 缺陷二：存储路径校验对 WAL 边车文件的瞬时状态误报

- 位置：`ContinuityStore._validated_db_path`（`auto_pm/infrastructure/continuity_store.py`，基线 `4e165cf4`）。每次事务与只读前都会校验 `-wal`、`-shm`、`-journal` 三个边车“解析后仍在工作空间内”且“是唯一链接的普通文件”。
- 事实：别的进程使用库时 SQLite 会反复创建、删除边车，校验遇到半建或待删除状态就拒绝。第 1 期的 `tests/e2e/test_pmf_intake.py` 并发入箱测试（4 个进程同时 `inbox add`）在 V04 演练的九组回归里失败一次（`DB/sidecar 必须是唯一链接的普通文件: continuity.db-shm`，归档于 `gates_rehearsal/judge_dry/g2_candidate/rest.txt`）。更正：此前写的“空闲机器上重复 12 次又失败 1 次、修复后 24 次通过”没有逐轮日志，不作证据；现在有逐轮日志的重复（`.auto-pm/reports/m2-v04/e04_repeat/`）是修复前字节 24/24 通过、候选 24/24 通过，说明该缺陷只在负载下偶发，该测试区分不了修复前后。
- 拟议修复（在卡 052 里，未提交）：只对边车的校验异常做最多 6 次、间隔 25 毫秒的重试；数据库文件本身的异常从不重试；持续异常仍拒绝。
- 仍未覆盖：严格只读快照读取路径（`_file_inventory`、`_stable_read_snapshot`）有同类盲点（拟登记为 `TD-SW008-077`）。
- 影响面：多个 Agent 与 `pm` 命令同时使用存储时可能偶发失败；P1 门禁里这个并发测试此前可能是侥幸通过。

## 证据位置（只读）

- 卡与演练：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/052_V04_进程中断与租约到期恢复实演实施卡_PM.md`；`.auto-pm/reports/m2-v04/`（`proto/` 为拟议的 6 个文件字节，`gates_rehearsal2/` 为最终字节的演练输出与判卷预演，`SURVEY_NOTES_20261005.md` 为勘测笔记）。
- 说明：`m2-v04/` 下的材料是**草案阶段**的证据，不是已批准或已提交的成果。
