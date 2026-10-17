# 03 V04-R1 第 2 张卡（存储接入）设计草案（项目 Claude，2026-10-17）

基于 `23e841b`：`auto_pm/infrastructure/continuity_store.py`（下称 store）、`auto_pm/application/core/continuity_execution_service.py`（下称 service）、`auto_pm/contracts/lease_reclaim.py`（第 1 张卡）。行号均为 `23e841b` 上的行号。本文是建议，不是指令。

## 结论

**第 2 张卡可以做，不改 schema、不改哈希链机制。但第 1 张卡已经推送的契约与“续租不增加 epoch”相矛盾，需要先修正。**

| # | 发现 | 严重度 |
|---|---|---|
| 1 | `lease_reclaim.py` 第 5 行写“epoch = lease version……授予、**续租**、移交时增加”，`next_epoch()` 的文档也写“grant, **renewal** or transfer”。store 的续租确实会 `version=version+1`（store:5905）。照这个契约接线，持有者每续租一次，自己在途的写入就会被 `check_write_epoch` 判成 `STALE` | **高** |
| 2 | `create_checkpoint`（store:6026）事务内**完全不查租约**；service 的 `checkpoint()`（service:303-338）先读租约、在事务外判断，再另开事务写入，是“先查后写”的竞态 | 高 |
| 3 | `transition_run`（store:3988）事务内只做 Run 版本的比较并发控制，不查租约。`transfer_lease` 不改 Run 版本，所以旧持有者“查完租约 → 移交发生 → 写入”这一窗口内，旧持有者的状态推进会成功 | 高 |
| 4 | `append_verified_checkpoint`（service:342）在检查租约和真正写入之间要跑质量门禁，耗时可达数分钟，期间必然发生续租。这正是“续租期间在途写入”的真实场景，第 3 张演练卡应该用它做回归 | 信息 |
| 5 | 其他写入路径已经在事务内校验 owner/token/过期，只缺 epoch：`record_run_started`（store:4357 起，约 4410-4416）、`create_handoff`（store:6055 起，约 6108-6110）、`renew_lease`（store:5809 起，约 5895-5905）、`transfer_lease`（store:5935 起，约 5985-5998）、恢复类路径中对恢复租约的 version/owner/token 校验（store:5251-5254 等） | 信息 |

## 1. epoch 的定义（修正第 1 张卡）

**epoch = 当前 token 被授予时的 lease version（下称“授予版本”）。** 只有安装新 token 的动作才会改变它：创建 Run（version 1）、移交（`transfer_lease`）、将来的回收。续租只把 `version` 加 1 并延长 `expires_at`，epoch 不变。

不改 schema 的取法：在同一事务里取该 Run 最近一次“安装 token”的事件，读出其中的 version。

```sql
SELECT event_type, payload_json FROM events
WHERE aggregate_id = ? AND event_type IN ('RUN_CREATED', 'LEASE_TRANSFERRED', /* 将来 */ 'RUN_LEASE_RECLAIMED')
ORDER BY rowid DESC LIMIT 1
```

（已有 `idx_events_aggregate` 索引，store:328。）`RUN_CREATED` 的 epoch 取 1；`LEASE_TRANSFERRED` 取其载荷里移交后的 version。实现时先核对这两个事件载荷里 version 字段的确切键名；如果某个版本的载荷里没有 version，就按“1 + 之前的移交次数”计算，两种取法在现有数据上应当一致，写一个对账测试证明这一点。

为什么不直接用 `version`：store 里的 `version` 同时承担续租的比较并发控制（`renew_lease` 的 `expected_version`），一旦把它当围栏号，就无法区分“别人接管了”和“我自己刚续租了”。

**第 1 张卡要改的地方**（产品档小修，可并入第 2 张卡的第一个提交）：
- 第 5 行文档改为“授予、移交、回收时增加；续租不增加”；
- `next_epoch()` 文档去掉 renewal；
- 增加测试：`check_write_epoch(current=E, presented=E)` 在任意次续租之后仍为 `OK`（契约层用“授予版本不随续租变化”的模型表达）。

## 2. 事务内租约校验：一个辅助函数，所有变更路径共用

```python
def _require_lease_in_tx(
    self, conn, *, run_id, owner_id, lease_token, expected_epoch: int | None,
    write_key: str, now: datetime,
) -> LeaseItem:
    lease = self._get_lease(conn, run_id)                      # 同一个 BEGIN IMMEDIATE 事务（store:1030）
    if lease.owner_id != owner_id or lease.lease_token != lease_token:
        raise ContinuityStoreError("lease ownership 不匹配")
    if self._aware_timestamp(lease.expires_at, "lease") <= now:
        raise ContinuityStoreError("lease 已过期")
    current = self._grant_epoch(conn, run_id)                   # 第 1 节
    verdict = check_write_epoch(current, expected_epoch, compatibility_period=LEASE_EPOCH_COMPAT)
    if not verdict.accepted:
        raise ContinuityStoreError(f"lease epoch 拒绝: {verdict.reason}")
    if verdict.verdict is EpochVerdict.OK_WITH_WARNING:
        self._append_event(conn, run_id, "LEASE_EPOCH_MISSING", {...}, f"{write_key}:epoch-missing", now.isoformat(), aggregate_type="run")
    return lease
```

因为 `_transaction()` 用的是 `BEGIN IMMEDIATE`，读租约与随后的写入之间不会插入别的写事务，竞态在存储层就被消除了。service 层现有的 `_require_active_lease`（service:1337）保留，作为提前失败、给出友好报错的快速检查，但不再是唯一防线。

### 各写入路径的改动

| 路径 | store 方法 | 现状（事务内） | 改动 |
|---|---|---|---|
| 普通 Checkpoint、自动 Checkpoint | `create_checkpoint` | **无租约校验** | 新增必填关键字参数 `owner_id`、`lease_token`，可选 `expected_epoch`；在 `_event_by_key` 幂等重放判断之后、插入之前调用辅助函数 |
| Run 状态推进 | `transition_run` | 只有 Run 版本 CAS | 同上；这个 store 方法在产品代码里只有 service:724 一个调用方（`git grep` 结果），改签名的影响面小 |
| 启动证据 | `record_run_started` | owner/token/过期已在事务内 | 只加 `expected_epoch` |
| 续租 | `renew_lease` | owner/token/过期 + version CAS | 加 `expected_epoch`；**续租不改变授予版本** |
| Handoff | `create_handoff` | owner/token/过期已在事务内 | 只加 `expected_epoch` |
| 移交 | `transfer_lease` | 源 owner/过期/version | 移交成功后新的授予版本 = 移交后的 version；`LEASE_TRANSFERRED` 载荷里要有这个值 |
| 恢复类（`settle_expired_run`、`fence_terminal_lease`、`reconcile_terminal_lease`） | 同名 | 恢复租约的 version/owner/token 已在事务内 | 恢复租约补 `expected_epoch`；被回收的目标租约不需要 epoch（它的持有者不是调用方） |

### 幂等重放

现在每个路径都先 `_event_by_key` 判断重放。租约校验放在**重放判断之后**：同一个 idempotency_key 的精确重放应当返回原结果，哪怕租约已经移交或过期，否则重试会把已经成功的写入报成失败。这和现有 `create_checkpoint` 先重放再查 Run 的顺序一致。

### 兼容期（缺 `expected_epoch` 只警告）

- 常量 `LEASE_EPOCH_COMPAT = True` 放在契约模块；结束条件写进卡里，建议为“第 3 张演练卡通过、并且 `LEASE_EPOCH_MISSING` 事件在一周内只来自已知调用方”。
- 警告写成**单独的新事件类型** `LEASE_EPOCH_MISSING`，不往现有事件载荷里加字段。原因：现有重放校验会比较载荷键集合是否完全一致（例如 store:5868-5872 的 `!= {"schema_version", "request", "expires_at", "version"}`），往旧载荷加键会让旧事件的重放校验失败，或者需要给每种事件升级 schema_version。新增事件类型只是往哈希链上追加记录，不改链的机制。
- 将来新增的回收接口从第一天起要求 `expected_epoch`，不走兼容期。

## 3. 需要补的测试

均放在 `tests/infrastructure/test_continuity_store.py` 或新文件 `tests/infrastructure/test_continuity_store_lease_fence.py`，按现有风格写，使用真实 SQLite 文件，不用 mock。

1. **续租期间在途写入不被误拒**：取得 epoch E → 续租 3 次 → 用 E 写 Checkpoint、推进状态，均成功；同时断言 `version` 已经从 E 变成 E+3。
2. **移交后旧持有者被拒**：A 持有，取得 E → 移交给 B → A 用旧 token 写入被拒（ownership）；A 伪造 B 的 token 但带 E 被拒（STALE）。
3. **先查后写的竞态被消除**：在 service 的 `_require_active_lease` 之后、store 写入之前注入一次移交（用 store 方法真实执行，不用 mock 替换），断言写入失败、Checkpoint 表无新行、事件链无新事件。
4. **过期在事务内判断**：把 `now` 推进到 `expires_at` 之后（store 有 `_utc_now`，用现有的可注入时钟），写入被拒。
5. **FUTURE epoch 被拒**：带 E+1 写入被拒。
6. **兼容期警告**：不带 epoch 写入成功，并产生且只产生一条 `LEASE_EPOCH_MISSING` 事件；同一 key 重放不再产生第二条。
7. **兼容期关闭**：`compatibility_period=False` 时不带 epoch 被拒，且没有任何写入。
8. **幂等重放不受移交影响**：写入成功 → 移交 → 用同一 key 重放，返回原 Checkpoint。
9. **授予版本对账**：对现有测试库里所有 Run，事件推导出的授予版本与“1 + 移交次数”一致。
10. **变异检查**：去掉辅助函数里任意一个条件（owner、token、过期、epoch），至少有一个上述测试失败。

## 4. 不做的事

- 不改 `execution_leases` 表结构、不新增列、不迁移数据；
- 不改事件哈希链的计算方式；
- 不改 `settle-expired` 的现有行为（Run -004 这类已过期 Run 的处理路径不变）；
- 不在本卡里接入进程指纹（那是第 3 张卡与回收接口的事）。
