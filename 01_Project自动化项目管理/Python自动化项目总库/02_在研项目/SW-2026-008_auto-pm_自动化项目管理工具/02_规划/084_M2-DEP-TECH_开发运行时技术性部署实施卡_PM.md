# M2-DEP-TECH｜开发运行时技术性部署实施卡

> 卡片编号：`CARD-SW008-M2-DEPTECH`
> 版本：`V1.1`（2026-10-09；V1.0 的 SHA-256 为 `21135b702d18ef6664de27a934eae3bc3bd8fe3fb674ae8681e5dedce073c4a9`，其 Gate B 第一轮在切换后核验“根入口身份无冲突”处失败并已自动回退，见 §6.1；V1.1 只把这一条判据改为“冲突集合与切换前相同、无新增”，其余字节不变；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`GATE_A_COMPLETED / GATE_B_ROUND1_ROLLED_BACK / GATE_B_ROUND2_READY`
> 授权：用户 2026-10-09 傍晚与夜间（对话原话，逐字；第二轮“同意，出 V1.1 重跑”）：“gpt不再复审了，今天还有两个任务，技术部署和推送。整个M2就结束了。给你授权，准备技术部署，至于合并，你判断是否合适。”记录在 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾。签字模式 `DELEGATED`，审批身份记为 `fubai / baiyang`。条件：卡 SHA 先在聊天报出；Gate A 全过；任一切换后核验失败即自动回退
> 隔离基线：`4b5c6307e814cd6bf17337f31ccd8c7e533553e1`（M2 线尖端，分支 `codex/m2-gov-wbs9-attest`；产品子树等于已证明的最终提交 `1d0be4af46423b46b8521884aaca98c42943f8a8`）
> 治理任务真源：WBS V3.0.25（§4.7.9、§4.7.10、§4.11 冻结条款）
> 路径根：`.`
> 执行模型：`claude-sonnet-5-5`
> 禁用能力：`pm-workflow`
> 性质：**开发运行时**切换，不等同于 WBS D07 的正式稳定交付

## 1. 为什么需要这一步

M2 的全部代码（U05 至 F02、V05-C，以及 ADJ/IC02 合并）只存在于隔离分支上，开发运行时仍是 `1.3.3-a808fa8`，不含 M2 代码（N2-0 已验证）。本卡把 M2 提交 `4b5c6307` 的确定性构建 `1.3.3-4b5c630` 部署为开发运行时，previous 为 `1.3.3-a808fa8`，切换和回退都按 DEP1 已验收的同一份操作脚本执行。

## 2. 已核实事实（Gate A，临时根上，真实容器零改动）

1. 提交 `4b5c6307e814cd6bf17337f31ccd8c7e533553e1` 的父提交是已证明的最终提交 `1d0be4af`，`auto_pm` 与 `templates` 子树与它的完全相同（树 `14c0d313…`、`15a75e65…`），所以构建内容就是 §4.7.10 证明的 20 个文件所在的那棵树。
2. 两次确定性构建到两个临时容器：逐文件 SHA-256、manifest 条目、整份 manifest 文件完全一致（513 个文件）；manifest 条目 SHA-256 `f8cecee8d79ffd40c58d2fa577bf7f9f277b4152c50dbc1ef435f0544a79613e`；# 1.3.3-4b5c630 vs 1.3.3-a808fa8: files 513 vs 502; added 11, removed 0, changed 37。
3. 临时根上做了：三个 release（新、`1.3.3-a808fa8`、`1.3.3-0b72499`）exact-tree 校验通过；切换后根入口身份核对（configured 与 effective 均为 `1.3.3-4b5c630`、无 fallback、无冲突）；新命令可用（`implementation-card precheck`、`decision create --target-work-id`、`continuity work create --card-file`、M2 的 `pm orient`、`pm resume` 带 query 块）；回退后身份恢复。
4. 数据库演练：用新 release 自己的代码读真实库的副本，与现行 release 读同一副本的结果逐项相同（事件 3622 条、链断裂 0、Run 376 个全部可读、Work 274 个）；一个历史 Mission 的读取校验错误在两个版本里完全相同（既有历史，非回归）；演练后副本 `quick_check` 为 ok。
5. 数据库的 schema 版本常量两版均为 `continuity-store.v7`；M2 多出的 `planning_scope_cards`、`intake_items`、`planning_draft_intake_bindings` 三张表是首次使用时才创建的追加表（GPT 预备审计项 2），不删不改旧表；回退到旧版时旧版忽略这些表。
6. Gate A 证据：`.auto-pm/reports/m2-dep-tech/gate_a/`（`GATE_A_RESULT.txt` SHA-256 `7c70335ef4e465b053bac34c5affde0366105cd440a6be8535a05c5917d95c78`、`gate_a_log.txt` SHA-256 `1eff70e87e05651a4284d4ad42060a8e8637bb7c9311e45f2b6446606ee967c4`）；真实指针与 manifest 的备份在 `.auto-pm/reports/m2-dep-tech/preflight/`。

## 3. 前置条件（全部满足才启动 Gate B）

1. 卡字节与已向用户报告的 SHA 一致；`dep1_release_ops.sh` SHA-256 为 `c022486676a801c328310acc8880e26b601976fbc81575051b2c1f11e57cf0b7`。
2. 真实 active 为 `1.3.3-a808fa8`、previous 为 `1.3.3-0b72499`，三个文件的 SHA-256 等于 §4 的值（无漂移）。
3. 没有测试、驾驶舱或续租进程在运行，`HEAVY_GATES_RUNNING` 不存在（TD-SW008-105 要求切换时没有并发写入）；真实库在切换前用 SQLite 备份接口做带 SHA-256 的副本。
4. SW-2026-008 与 SYS-2026-001 台账 0/0/0。

## 4. 受治理的对象路径与指纹

本卡无产品源码 owned paths；下表是 Decision 需要覆盖的部署对象。

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `00_Infrastructure/auto_pm/deployment_manifest.json` | 存在 | 追加 release 条目（条目 SHA-256 `f8cecee8d79ffd40c58d2fa577bf7f9f277b4152c50dbc1ef435f0544a79613e`） |
| 2 | `00_Infrastructure/auto_pm/active_release.json` | 存在 | 原子改指针：active 指向 `1.3.3-4b5c630` |
| 3 | `00_Infrastructure/auto_pm/previous_release.json` | 存在 | 原子改指针：previous 指向 `1.3.3-a808fa8` |
| 4 | `00_Infrastructure/auto_pm/releases/1.3.3-4b5c630` | 计划新增 | 新 release 目录（`release_meta.json` 的 `source_commit` 为 `4b5c6307e814cd6bf17337f31ccd8c7e533553e1`） |

切换前指针与 manifest 的 SHA-256：`active_release.json` `f95ddd95888ef44659d14cfb5fd1a3d228fa762dcc86053eafb4da07d041cbb1`；`previous_release.json` `bcd350a966baa5b00becfd1cc985b22c82e1dea255e3d2f680b7aa09cd4b90af`；`deployment_manifest.json` `95eba220791e45e69f5040a2e6d121ba34713dbf4935fb2f62a4a535ebd8d0f9`。

## 5. 执行步骤（Gate B 脚本 `.auto-pm/reports/m2-dep-tech/dtech_gate_b.sh`，可续跑）

1. 核验本卡 SHA、操作脚本 SHA、Gate A 结果、`4b5c6307` 仍是 M2 线尖端、产品子树等于已证明的提交、旧指针哈希；对本卡执行机器预检；台账 0/0/0。
2. 无并发写入核对；数据库备份（SQLite 备份接口）；记录切换前旧运行时的身份与冲突集合（V1.1）。
3. 创建（第二轮复用 CHG-SCPT-2026-400 与其 Decision）并批准部署变更单与 Decision（精确四路径）；在控制根上建立写入型 Work 与 Run（`-002`，租约，已声明的既有脏路径，带本卡为实施卡）。
4. 以同一构建脚本把 release 写入真实容器，manifest 条目 SHA-256 必须等于 §4 的值；备份指针与 manifest；原子写指针。
5. 切换后核验（只读，任一失败立即自动回退）：`pm resume` 的 configured 与 effective 均为新 release，无 fallback，**冲突集合与切换前（旧运行时）相同、无新增冲突**（V1.1）；新命令可用（含 `pm orient` 与 resume 的 query 块）；用新运行时对本卡执行预检；两项目台账 0/0/0；真实库只读核验（裁决与遗留证据命令、事件链 0 断裂）；最近三次 release 的 exact-tree 通过。
6. 创建 Checkpoint，完成 Run 与 Work，收口部署变更单（委托签署），写回执。

## 6. 回退

触发：步骤 5 任一核验失败，或切换后根入口身份不是新 release。方案：用切换前备份的两个指针原子还原（`dep1_release_ops.sh rollback`），回退后再做身份核对；**不回滚数据库**（只做追加，旧版忽略新表）。切换前的数据库备份副本保留用于取证，不是回退手段。

## 6.1 第一轮记录（V1.0，2026-10-09 夜）

Gate B 第一轮：切换成功，其余核验全部通过（身份为 `1.3.3-4b5c630`、无 fallback；resume 带 query 块；新命令可用；卡预检通过；两项目台账 0/0/0；真实库 19 条只读证据命令 exit 0；事件链 3627 条 0 断裂；三个 release exact-tree 通过），唯独“根入口身份核对要求冲突为空”失败：冲突为 `MULTIPLE_ACTIVE_WORKS`。回退后用旧运行时查，**同一冲突仍在**：它来自 5 个历史失败尝试遗留的未终结 Work（F02-001、P1-AUDITFIX-001、TD3-001、V05B2-001、V05B3-001），不是新版本带来的。自动回退成功，指针哈希与切换前相同；该轮 Run 记 FAILED、Work 记 CANCELLED；V1.0 另有一处脚本缺陷（写入型 Work 缺 `--card-file`）已修。V1.1 的改动只有判据：用“与切换前相同、无新增”代替“为空”，因为那 5 个 Work 是用户要求原样保留的失败记录，本卡不处置它们。证据：`.auto-pm/reports/m2-dep-tech/gate_b_round1/`。

## 7. 硬停止

卡、脚本、指针、manifest 或 Gate A 结果任一漂移；有并发写入；预检失败；构建的 manifest 条目与 Gate A 不一致；切换后核验失败（先自动回退，再停止，保留现场，不重试）。止损：同一问题最多 2 轮；不做真实模型调用。

## 8. 合并与推送（用户把合并交给我判断，推送是今天的第二项任务）

- **合并 main：不合并。** 理由：WBS 与 M2 冻结条款写明“合并 main 等到 M3 的 D03”；控制根所在分支是 `codex/c09-recovery-governance`，与 M2 线不是同一条线，合并会同时引入历史整改线与 M2 线的差异，超出本任务范围；技术部署不需要合并（release 是由 git 提交确定性导出的）。
- **推送**：部署成功后，把 M2 隔离候选分支 `codex/m2-gov-wbs9-attest`（尖端 `4b5c6307`，内含整个 M2 线）原样推送到 `origin`，不改写历史、不推 main、不强推；推送前在聊天写明目标。部署失败则不推送。

## 9. 交付物

Gate A 证据与日志；Gate B 的预检、数据库备份、变更单/Decision/Work/Run/Checkpoint、切换与核验日志、回执；部署后的指针与 manifest 的 SHA-256。

## 10. 限制

这是开发运行时切换；不改产品源码；不合并 main；D07 正式稳定交付另行进行；不处置任何历史失败对象。
