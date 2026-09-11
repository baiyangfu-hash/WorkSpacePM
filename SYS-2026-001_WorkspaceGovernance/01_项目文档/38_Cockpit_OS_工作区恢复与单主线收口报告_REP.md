# Cockpit OS 工作区恢复与单主线收口报告

> 报告状态：`REC_GIT_VERIFIED / A2_DEFERRED`
> 核验时间：2026-09-11
> 治理变更：`CHG-SAFE-2026-001`、`CHG-SAFE-2026-002`
> 执行真源：`DEC-20260911-EC983850`、`DEC-20260911-7733A527`、Continuity v2、Git
> 发布边界：未构建候选、未部署、未切换 `active_release.json` 或 `previous_release.json`

## 1. 收口结论

本轮已把原先分散的本地 Git 现场收敛到一个持久产品主线 `main`。根工作树干净，旧分支和辅助 worktree 已在可恢复证据成立后退出活动面；旧 A2 因仍有三条过期 lease 的非终态 Run，专用分支与 worktree 暂时保留，等待独立的前向运行态结算变更。

没有把未知内容直接丢弃，没有使用 `git reset --hard`、`git clean`、强制 checkout、fetch、push 或发布切换。五个无法取得 ACL 所有权的 `.pytest_cache` 目录已移入显式隔离区并剥离全部可访问内容；它们是公开记录的缓存例外，不计作“已彻底删除”。

## 2. 当前事实

| 维度 | 核验结果 |
|---|---|
| 根 Git | `main@2af4aac5dccad718f286e2bc645098ca48d67e9a`；`git status --short --branch` 仅显示 `main...origin/main [ahead 235]`，无工作树差异 |
| 本地分支 | 2 条：`main`；临时保留的 `codex/a2-pm-facade@06782f4d21317a0107abf5dcdedba742a5625d1b` |
| Git worktree | 2 个：工作区根；旧 A2 专用 `.auto-pm/worktrees/codex-a2-pm-facade`，两者均干净 |
| Git 完整性 | `git fsck --full --strict --no-dangling` Exit 0 |
| 远端关系 | `main` 相对本地缓存的 `origin/main@e9c6dd05` ahead 235；本变更禁止 fetch/push，因此不把缓存的远端状态表述为已同步 |
| 活动发布 | `1.3.3-d8f7c8b`；根启动器仍解析到该不可变槽 |
| 上一发布 | `1.3.2-9d3c920` |
| 发布指针 SHA-256 | active `5D3579D24B3D9BFAA62592D3039E55B03D77384DDCEEB612746CDB5EADAF09C1`；previous `24BC03E008B0B1E8CF7FF3144B549B6A50307A321492AF8465FE1F2C26E80514` |
| 部署清单 SHA-256 | `3948C404E7C2341BDE39A74FC85B20EDAF3E84B4D5CA46385EDB4F3FFC89AEFF`，与 REC-0 冻结值一致 |

## 3. Git 拓扑收敛

| 项目 | 收敛前 | 收敛后 | 处置 |
|---|---:|---:|---|
| 本地分支 | 16 | 2 | 已合并且无保留价值的旧分支删除；两条独有提交先转为 annotated archive tag |
| worktree | 12 | 2 | 干净 worktree 正常移除；含独有/忽略资产者先归档；ACL 受阻者整体移入隔离区后 prune 登记 |
| 根工作树状态项 | 557 | 0 | 修改、删除、未跟踪内容分别以 patch、ZIP、SHA-256 冻结后精确恢复/纳入正式治理提交 |
| 持久产品主线 | 多入口 | `main` | 原研发母体提交链及已验收恢复提交统一落入 `main` |

独有提交的恢复锚点：

- `archive/rec-20260911/preserve-mother-pre-mainline` → `a042d01c9ae0fc0c3d8939ca11225684079a5bae`
- `archive/rec-20260911/wpf-poc` → `da69a92e05832635cbd7faf0be8ada266d7bc7ce`

旧 A2 分支/worktree 不属于残留平行主线。它只为运行态结算保留；三条旧 Run 安全终结并核验后必须移除，最终目标仍是仅保留根 `main`。

### 3.1 REC-GIT Run 事实链

| Run | 结果 | Checkpoint / 说明 |
|---|---|---|
| `RUN-SW008-REC-GIT-002-01` | `FAILED` | `CP-SW008-REC-GIT-002-01-01`；旧根清理未满足门禁，失败原样保留 |
| `RUN-SW008-REC-GIT-002-02` | `SUCCEEDED` | `CP-SW008-REC-GIT-002-02-01`；主线恢复基础完成 |
| `RUN-SW008-REC-GIT-002-03` | `FAILED` | 切换中的 worktree/基线条件不满足，未伪造 Checkpoint |
| `RUN-SW008-REC-GIT-002-04` | `FAILED` | 运行时生成未声明的 SQLite sidecar，Checkpoint 正确拒绝 |
| `RUN-SW008-REC-GIT-002-05` | `SUCCEEDED` | `CP-SW008-REC-GIT-002-05-01`；治理记录正式纳入并提交 `2af4aac5` |
| `RUN-SW008-REC-GIT-002-06` | `SUCCEEDED` | `CP-SW008-REC-GIT-002-06-02`；worktree/branch 退役与 ACL 隔离完成 |
| `RUN-SW008-REC-GIT-002-07` | `FAILED` | 活动版 1.3.3 拒绝启动后新产生、但未在启动时声明的 dirty paths；失败原样保留 |
| `RUN-SW008-REC-GIT-002-08` | `SUCCEEDED` | 精确声明并接管三项现有差异，生成最终 Checkpoint、报告与闭环提交 |

失败 Run 是门禁发挥作用的审计证据，不删除、不改写、不用后续成功记录覆盖。

## 4. 可恢复证据

主要恢复介质位于 `.auto-pm/backups/REC-SW008-20260911`：

| 介质 | SHA-256 | 用途 |
|---|---|---|
| `workspace-rec-git-004-pre-prune.bundle` | `8CA09CB0C712B85D07BE0233EE1FF515314043109658F7BFD8C4A2B0D53F70DB` | worktree/branch 裁剪前完整 Git 历史 |
| `workspace-all-refs.bundle` | `8B2246990F59A68B6141B80A83AE7981E7CF78B66DAF1CF91EAF286333F41B17` | REC-0 全 refs 冗余 |
| `workspace-rec-git-002-run02.bundle` | `16A614B9BFE7D9406580A3DED218DB097C710698156C07D294500DA7606A3873` | Run02 主线恢复快照；不声称覆盖外部候选 `f950525` |
| `root-governance-intake-precanonical.zip` | `CD1022128B2B1EE00A357ADD6B800C425C7CB534014C6FD5C9EE0C84F768D6D9` | 14 项治理记录纳入 Git 前原件 |
| `retired-internal-worktrees-ignored-20260911.zip` | `1A3FDAB10C2B6D13C7C857B84D6A9AD9A7ABF68785A67B36DF513812F084FB9E` | 2,271 个内部 worktree 忽略文件 |
| `external-candidate-accessible-ignored-20260911.zip` | `3350474E0A81DA4F8DF9696FC87E1B42FA2C7E21E3B2F57ABD6F5F7791A38555` | 472 个外部候选可访问忽略文件 |
| `b0-accessible-ignored-20260911.zip` | `93DEBDCA50882CC5212C9E7ACC787517A7DD03405BFDDABEAC5D5CC18AB415EF` | 252 个 B0 可访问忽略文件 |
| `continuity.db.backup` | `797EB49DFA9164D1DB5B694B19BCD4A8BD6515F5E3F820FAD3835D057B391A3C` | REC-0 连续性库一致性备份 |
| `continuity.db.rec-git-002-pre-clean.backup` | `A490D63E5EF15F2D547577A197EB011D47E895130254AC5F25B9891B8800C9C0` | Git 清场前连续性库增量备份 |
| `index.db.backup` | `D0554A64CC5F4776A8C7D682B2BAAE8D78D7753080742CBA8EA10D2A835CEDCF` | 索引投影备份 |

各 ZIP 在移除源文件前均按“路径 + SHA-256 + 条目数”核验；Git bundle 已执行 verify。恢复时先复制备份到独立临时目录核验哈希，不得直接覆盖当前工作区或运行库。

## 5. ACL 隔离例外

以下目录现位于 `.auto-pm/backups/REC-SW008-20260911/acl-quarantine/worktrees`：

- `a5-execution-adapters`
- `a6-dual-target-continued`
- `a6r-project-generation-repair`
- `b0-mainline-integration`
- `external-candidate-f950525`

每个隔离树的可访问文件数和可访问字节数均为 0；仅剩一个 Windows ACL 拒绝访问的 `.pytest_cache` 目录链。普通权限和 `takeown` 均返回 Access Denied，因此本轮没有继续破坏性尝试。它们不再是 Git worktree，不承载源码、运行数据库或发布槽；后续可由真正提升的 Windows 管理员权限执行精确删除，删除前仍须逐一解析并确认目标位于上述隔离根内。

## 6. 尚未完成的运行态收口

当前 `pm resume SW-2026-008 --json` 先报 `MULTIPLE_ACTIVE_WORKS`：

- `WORK-SW008-A2-201-R2`：`ACCEPTED`
- `WORK-SW008-REC-001`：`IN_PROGRESS`
- `WORK-SW008-REC-GIT-002`：`IN_PROGRESS`

两项 REC Work 的执行 Run 已成功，应按正式状态机验收并关闭。之后旧 A2 会暴露三条 lease 已过期但 Run 未终结的历史冲突：

| Run | 当前状态 | 父 Work | 最近 Checkpoint |
|---|---|---|---|
| `RUN-SW008-A2-201-01` | `BLOCKED` | 已 `CANCELLED` 的 `WORK-SW008-A2-201` | `CP-SW008-A2-201-01` |
| `RUN-SW008-A2-201-03` | `RUNNING` | `WORK-SW008-A2-201-R2` | `CP-SW008-A2-201-03` |
| `RUN-SW008-A2-201-04` | `VERIFYING` | `WORK-SW008-A2-201-R2` | `CP-SW008-A2-201-04` |

禁止直接修改 SQLite、复用过期 token 或把旧测试证据伪造成新的完成记录。下一阶段必须用独立 SCPT CHG、类型化 Decision 能力、恢复 Work/Run 和有效恢复 lease，实现带 CAS、目标 lease 过期校验、严格幂等与原子审计事件的 `settle_expired_run`，将三条旧 Run 前向结算为 `CANCELLED`。结算成功后关闭 A2 Work，并移除最后一个临时分支/worktree。

## 7. 后续阶段边界

1. **REC-2 / A2 运行态结算**：先实现和验证安全结算能力，再使用固定源码提交对根运行库执行一次受控前向结算。
2. **REC-3 / 文档真源对齐**：校准 26、36、37 的当前状态；19～24 保持归档，仅作历史证据。
3. **A7-0.2 / 非活动候选**：从干净 `main` 的固定提交构建不可变候选，运行全量回归、清单哈希和非活动槽验证；禁止改发布指针。
4. **A7-1 / 正式切换**：必须重新取得 User 明确批准后才允许切换 active/previous，并完成回滚演练。
5. **A8 / GUI 整理**：独立阶段，不能混入 A7 发布治理。

## 8. REC-GIT 验收标准

- 根工作树无跟踪或未跟踪差异；
- 仅保留 `main` 和为 A2 结算临时保留的分支/worktree；
- 所有退役对象具有 bundle、patch、ZIP、哈希或 archive tag 恢复入口；
- ACL 残留被显式隔离并准确披露；
- Git 连通性检查 Exit 0；
- active、previous、deployment manifest 哈希与 REC-0 一致；
- 未执行 fetch、push、构建、部署或发布指针切换。

以上标准已经满足。A2 临时分支/worktree 的最终移除属于下一阶段的收尾条件，不伪装为本阶段已完成事项。
