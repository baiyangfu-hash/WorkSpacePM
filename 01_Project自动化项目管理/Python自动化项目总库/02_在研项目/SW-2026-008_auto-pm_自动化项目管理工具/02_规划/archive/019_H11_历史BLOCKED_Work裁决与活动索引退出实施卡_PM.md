# H11｜历史 BLOCKED Work 裁决与活动索引退出实施卡

> 卡片编号：`CARD-SW008-H11`
> 对应 WBS：`H11`
> 版本：`V0.1`（2026-09-28）
> 状态：`READ_ONLY_PREPARED / NOT_AUTHORIZED`
> 控制根：`C:\Users\fubai\Documents\My_Workspace`
> 准备基线：根工作区 `4166b9afb8e9c1628d3c1fd21f91b42ea89619cd`
> 依据：PM-033、PM-042、Continuity v2 追加事件与 fail-closed 合同

## 1. 用户故事与完成定义

作为驾驶舱和后续执行任务的使用者，我需要历史辅助 Work 永久保留其 Run、Checkpoint
和事件证据，但不再被默认 Resume 或活动任务查询误认为当前待执行工作。

H11 只有在下列条件全部成立时才算完成：

1. 14 条目标 Work 均逐项获得带当前 version、Run、lease、Checkpoint 和进程证据的裁决；
2. 原 Work/Run/Checkpoint/事件不删除、不覆盖、不伪造成功；
3. 所有可写 token 已通过合法结算或受控 reconcile 明确失效；
4. 目标 Work 经高层服务进入与事实一致的终态并退出活动查询；
5. 默认 Resume 不再因这 14 条历史对象产生多活动冲突；
6. canonical 事件链连续，SW008 台账仍为 0 缺失、0 孤儿、0 不一致；
7. 历史工作树是否归档另行裁决，不作为隐藏控制面未结算对象的手段。

## 2. 只读事实基线

2026-09-28 对 `.auto-pm/continuity.db` 以只读连接复核，目标共 14 条，当前均为
`BLOCKED`。其中 11 条可进入常规前向处置预检，另外 3 条必须分离处理。

| Work | 当前版本 | Run / lease / Checkpoint 摘要 | 准备裁决 |
|---|---:|---|---|
| `WORK-SW008-PMF-C09-CLOSURE-001` | 4 | 3 FAILED；lease 均 RELEASED；无 CP | H11A：被后继 C09 收口替代，拟 CANCELLED |
| `WORK-SW008-PMF-C09CONV-001` | 4 | 1 FAILED；lease RELEASED；有 `CP-SW008-PMF-C09CONV-001` | H11A：Checkpoint 不改变 Run FAILED，拟 CANCELLED |
| `WORK-SW008-PMF-C09P2-REMEDY-ISSUER-001` | 4 | 1 CANCELLED；lease RELEASED；有 CP；存在 blocked_by 关系 | H11A：拟 CANCELLED，保留关系和 CP |
| `WORK-SW008-PMF-C09R3C-001` | 4 | 1 CANCELLED；lease RELEASED；关联 Mission 已 CANCELLED | H11A：拟 CANCELLED |
| `WORK-SW008-PMF-C09R3C-EXACT-001` | 4 | 1 FAILED；lease RELEASED；无 CP | H11A：拟 CANCELLED |
| `WORK-SW008-PMF-C09R3C-INTEG-001` | 4 | 1 FAILED；lease RELEASED；无 CP | H11A：拟 CANCELLED |
| `WORK-SW008-PMF-C09R3C-REC-001` | 4 | 1 CANCELLED；lease RELEASED；无 CP | H11A：拟 CANCELLED |
| `WORK-SW008-PMF-C09R3C-ROOT-001` | 7 | 2 FAILED；lease 均 RELEASED；无 CP | H11A：拟 CANCELLED |
| `WORK-SW008-PMF-V04R0REC-001` | 4 | 2 FAILED；lease 均 RELEASED；无 CP | H11A：拟 CANCELLED |
| `WORK-SW008-ROOT-BINDING-001` | 4 | 无 Run；CHG-332 仍 implementing | H11A：确认后继根绑定成果后拟 CANCELLED |
| `WORK-SW008-ROOT-BINDING-SNAPSHOT-001` | 4 | 无 Run；CHG-332 仍 implementing | H11A：确认后继证据固化后拟 CANCELLED |
| `WORK-SW008-PMF-C09R3C-NOSKIP-001` | 7 | 1 BLOCKED；lease v1 已过期且未 RELEASED；无 CP | H11B：先证明无进程并以 `settle_expired_run` 单目标结算，再拟 CANCELLED |
| `WORK-SW008-PMF-C09R3C-002` | 4 | 6 个终态 Run；其中 002、005 的过期 lease 未 RELEASED；无 CP | H11C：旧终态租约兼容裁决后拟 CANCELLED |
| `WORK-SW008-PMF-C09R3C-QG-001` | 14 | FAILED×1、SUCCEEDED×2；三条过期 lease 均未 RELEASED；两个成功 CP | H11C：先 reconcile 三条 lease；成功 CP 作为辅助质量事实永久保留，Work 拟按“被最终 C09 替代”取消，不冒充原 C09 验收 |

### 2.1 与原 WBS 假设的差异

原 WBS 只记录 NOSKIP 一条未释放 lease。当前物理复核证明共有 6 条：NOSKIP 一条
非终态 Run，以及 `C09R3C-002` 下两条、`C09R3C-QG-001` 下三条终态 Run。

五条旧终态 Run 的事件不满足 U04B-R1 的精确前置合同：部分终态事件仅含旧版
`{"state": ...}`，`RUN-SW008-PMF-C09R3C-002` 甚至没有可绑定的终态
`RUN_TRANSITIONED`。因此不得直接调用 `reconcile_terminal_lease`，也不得手改 token。

### 2.2 工作树证据

目标对象当前引用下列仍含独有现场的工作树：

- `c09-convergence`：HEAD `d89b1269`，25 条脏路径；
- `c09-r3c-root-clean`：HEAD `638fed60`，1 条脏路径；
- `c09-p2-effective`：HEAD `f9455e2d`，3 条脏路径。

H11 不删除、清理或归档这些工作树。只有控制面全部终态化、进程为零、独有资产已形成
可恢复快照后，才能转交工作树卫生治理卡通过托管归档处理。

## 3. 根因裁决

历史记录本身不是错误；错误是当前活动查询仅按 `state NOT IN (CLOSED, CANCELLED)`
判断，缺少“历史裁决/被替代”这一受权机器合同。现有
`WorkRegistryService.transition` 虽允许 `BLOCKED → CANCELLED`，但只沿用目标 Work
的旧 `authorization_ref`，不能证明本次 H11 的新行政裁决；现有 runtime Decision 又只
能精确绑定 target Run，不能绑定 target Work。

因此 H11 必须先补齐机器合同，再处理数据。不能依靠 Prompt、批量脚本或数据库 SQL。

## 4. 三批实施方案

### 4.1 H11A｜精确 Work 行政裁决合同与 11 条常规退出

先建立独立 CHG 和 Decision，只允许以下动作：

- `adjudicate_blocked_work`；
- 精确 `target_work_ids`；
- 目标结果只能为 `CANCELLED`；
- 每条目标必须匹配当前 Work version、原 Decision SHA-256、Run 集合摘要和 lease 摘要；
- 不允许存在非终态 Run或未释放 lease；
- 在同一事务追加裁决事件并执行 `BLOCKED → CANCELLED`，重放必须幂等。

建议 owned paths（执行前须再次只读确认）：

1. `auto_pm/contracts/decision_package.py`
2. `auto_pm/application/core/work_registry_service.py`
3. `auto_pm/infrastructure/continuity_store.py`
4. `auto_pm/ui/cli/continuity.py`
5. `tests/contracts/test_decision_package.py`
6. `tests/core/test_work_registry_service.py`
7. `tests/infrastructure/test_continuity_store.py`
8. `tests/cli/test_continuity.py`

合同候选通过定向 Pytest、Ruff、strict Mypy、diff-check 和当前字节 Checkpoint 后，才允许
用一次精确 runtime Decision 处理 §2 中 11 条 H11A 对象。ROOT-BINDING 两条在后继成果
证明不足时自动退出本批，不影响其余十/九条继续；不得为了凑数量降低条件。

### 4.2 H11B｜NOSKIP 单目标过期 Run 结算

仅处理 `RUN-SW008-PMF-C09R3C-NOSKIP-001`：

1. 复核 Run/Work/lease version 未漂移；
2. 从事件和操作系统双向证明无匹配进程、session 或 retained handle；
3. 使用独立 CHG、无条件 runtime Decision、恢复 Work/Run 和有界 lease；
4. 通过现有 `settle_expired_run` 将目标 Run 前向结算为 `CANCELLED`；
5. 恢复链自身合法终态后，再通过 H11A 合同取消 NOSKIP Work。

任一进程证据不明时，Run 保持 `BLOCKED`，不得继续 H11C，也不得制造 Checkpoint。

### 4.3 H11C｜五条旧终态未释放 lease 的兼容裁决

这是独立缺口，不复用 U04B-R1。先设计并验证仅适用于旧终态证据的 fail-closed 合同：

- 目标 Run 已是 `SUCCEEDED`、`FAILED` 或 `CANCELLED` 且版本不变；
- lease 已过期，token 未 RELEASED，CAS version 精确匹配；
- 目标 Run 的完整事件摘要、Checkpoint 摘要和最终投影状态必须由 Decision 固化；
- 对缺少终态事件的对象必须额外绑定事故裁决，不得根据投影行反推历史事件；
- 只允许 token fencing / RELEASED 和追加新裁决事件，不修改 Run 状态、版本、CP 或旧事件；
- 一条目标失败即该目标回滚，但不得回滚此前已成功且可证明的独立目标。

五条 lease 均结算后，再通过 H11A 合同分别取消 `C09R3C-002` 与 QG Work。QG 两个
SUCCEEDED Run 和 Checkpoint 永久保留并明确标注“辅助质量证据，不等于原 C09 验收”。

## 5. 门禁与验证命令

源码合同阶段至少执行：

```powershell
python -m pytest -o addopts= --no-cov -p no:cacheprovider `
  tests/contracts/test_decision_package.py `
  tests/core/test_work_registry_service.py `
  tests/infrastructure/test_continuity_store.py `
  tests/cli/test_continuity.py
python -m ruff check --no-cache <本阶段全部 Python owned paths>
python -m mypy --strict --no-incremental <本阶段全部 Python owned paths>
git diff --check
```

运行态每批结束后必须只读核验：

1. 目标 Work 当前 state/version；
2. 目标 Run、lease、Checkpoint 与原事件字节未被覆盖；
3. 新事件数量、幂等键和哈希链连续；
4. `main.py pm resume SW-2026-008 --json` 不再返回这些已处置对象；
5. `main.py ledger reconcile SW-2026-008` 为 0/0/0；
6. 与 H11 无关的当前 Mission/Work/Run 完全不变。

## 6. 停止条件

以下任一情况立即停止当前批次并保留现场：

- 14 条目标之一的 state、version、Decision、Run 或 lease 与本卡不一致；
- 检测到匹配的在运行进程、session 或 retained handle；
- 需要第九个源码路径、修改 U05、改写旧事件或直接 SQL 才能继续；
- 成功 Checkpoint 的当前性或候选字节无法证明；
- 工作树清理/归档成为执行前提；
- 任何门禁非零、Checkpoint 非当前字节或新事件链不连续。

每批最多一个主 Run 和一个完全落在原 owned paths 内的有界纠正 Run。不得因一条对象
失败而自动创建第二条补偿链，不得把 H11 扩展成 CHG-161～164 格式修复、旧 release
清理、远端同步、合并、推送、部署或 release 切换。

## 7. 当前授权边界与下一审批点

本卡仅完成只读准备和 WBS 校准。当前未授权：

- 创建 H11 CHG、Decision、Mission、Work 或 Run；
- 修改 §4.1 的八个源码/测试路径；
- 改变 14 条历史 Work、任一 Run/lease、Checkpoint 或 canonical 数据库；
- 清理、提交或归档历史工作树。

下一次审批只建议授权 **H11A 合同实现与隔离验证**；H11B、H11C 和 14 条对象的
canonical 执行继续保持独立审批边界。
