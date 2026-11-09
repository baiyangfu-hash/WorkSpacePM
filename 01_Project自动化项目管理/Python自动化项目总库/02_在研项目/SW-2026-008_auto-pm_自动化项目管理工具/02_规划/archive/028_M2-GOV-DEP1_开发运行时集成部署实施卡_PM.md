# M2-GOV-DEP1｜开发运行时集成部署实施卡

> 卡片编号：`CARD-SW008-M2-GOV-DEP1`
> 阶段：整改阶段 5（见 024 号总览）
> 版本：`V0.3`（2026-09-30，Gate A 完成后定稿的最终执行卡：回填整合提交、精确 release 身份与 Gate B 绑定对象）
> 状态：`GATE_A_COMPLETED / GATE_B_READY`
> 授权：用户于 2026-09-30 授权 Claude 全权推进 M2 里程碑（原话：“M2里程碑的任务都给你授权推进”“不要每次脚本都要我来实施”）。本卡 V0.2 中“由用户批准/由用户运行”的动作改为**委托执行**：签字模式 `DELEGATED`，审批身份仍记为 `fubai / baiyang`，每一步写回执。GPT 整改要求原文写的是“不部署、不切换 release”，本卡是对该约束的有意偏差（见 024 §1.1），已由用户确认纳入整改
> 隔离基线：`a808fa8a43335ceb5705d7384d2afbb0a12e412c`
> 治理任务真源：WBS 候选提交 `a385452cde480090d27175f1b4d2ccfe358a4cec`；WBS SHA-256 `AEBB2AE678D483A19E499C3A3706FD5C880643EF3EB689B2B4093D0665045EC6`
> 路径根：`.`
> 执行模型：`claude-opus-5-5`
> 禁用能力：`pm-workflow`
> 性质：**开发运行时**切换，不等同于 WBS D07 的正式稳定交付

> V0.3 治理说明：V0.2 是准备卡，其 Gate A 已在 CHG-SCPT-2026-360 下完成（整合提交、两次确定性构建、临时 exact-tree 与切换/回退演练，见 §8）。本版把隔离基线回填为整合提交，把 §2.1 第 4 行替换为精确 release 路径，并在 §8 列出 Gate B 必须绑定的全部对象。V0.3 必须先通过卡 027 的机器预检（以整合提交的代码运行），Gate B Approval Receipt 另行绑定本卡 SHA-256；卡片不写入自身 SHA-256。

## 1. 为什么需要这一步（申请部署的理由）

1. 当前 active release `1.3.3-0b72499` 是“`f4626947` 加三个补丁”的侧血统，**不含 M2 产品代码**（U01～U04B 的驾驶舱能力、实施卡工具等），与任何一条产品分支都不等价。
2. 整改 B（裁决绑定 Git）、C（`--target-work-id`）、D（开工前预检）只有部署后才在生产运行时生效；否则整改只是候选提交。
3. 后续 U05～U08 与验收会用到 M2 运行时能力。
4. 集中一次切换，比每张卡各切一次的风险与次数更小；所有切换均有 CHG、exact-tree 校验、演练与回退。

## 2. 前置条件（全部满足才可启动）

1. 阶段 1（WBS 修订 1）、阶段 2（BL02）、阶段 3（R1）、阶段 4（R2）均已达 024 §2 的完成判据。BL02 的 G1 为 `PASS_WITH_BASELINE_EXCEPTION`（例外均有源码复现）；其中 E-G1-1 已被 R2 修复，整合提交的并集回归为 `PASS`（0 失败、无例外，见 §8），以整合提交的结论满足“BL02 结论为 PASS”的意图。
2. R1 与 R2 是各自从 BL02 起步的两个独立候选；已形成**一个包含二者的整合提交**（见 §8）。
3. 用户已授权本卡（含部署范围与回退方案），按委托执行。
4. 没有持有未过期 lease 的 Run；`pm resume SW-2026-008` 无活动冲突（Gate B 脚本在切换前重新核验）。
5. 真实切换前，V0.3 最终执行卡、Gate B Approval Receipt、整合提交、release ID、manifest 条目 SHA-256、切换脚本 SHA-256 与回退指针哈希必须全部相互绑定（本卡 §8 绑定除自身与 Gate B 脚本外的全部对象；Gate B 脚本绑定本卡 SHA-256；回执绑定全部）。

## 2.1 受治理的对象路径（本卡无产品源码 owned paths；下表是 Decision 需要覆盖的部署对象）

| # | 路径 | 基线状态 |
|---|---|---|
| 1 | `00_Infrastructure/auto_pm/deployment_manifest.json` | 存在 |
| 2 | `00_Infrastructure/auto_pm/active_release.json` | 存在 |
| 3 | `00_Infrastructure/auto_pm/previous_release.json` | 存在 |
| 4 | `00_Infrastructure/auto_pm/releases/1.3.3-a808fa8` | 计划新增 |

这四条路径是部署 Decision 与写入型 Work 的完整 scope。

## 3. 双级实施授权签字门与 GUI 合同

### 3.1 当前签字状态

| 字段 | Gate A：准备与演练 | Gate B：真实切换 |
|---|---|---|
| 卡片版本 | `V0.2` | `V0.3` |
| 当前状态 | `COMPLETED`（CHG-SCPT-2026-360 已完成） | `READY`（由 Gate B 脚本按委托执行） |
| 允许动作 | 临时整合、两次构建、exact-tree、临时切换/回退演练 | 写入新 release、manifest 与两个真实指针 |
| 禁止动作 | 真实基础设施写入、切换 release、部署收口 | 范围外写入、数据库回档、main 合并、推送 |
| 审批人 | `fubai / baiyang`（委托签署） | `fubai / baiyang`（委托签署） |
| 执行模型 | `claude-opus-5-5` | `claude-opus-5-5`；指针切换由 Gate B 脚本按委托执行 |

Gate A Approval Receipt（`.auto-pm/reports/m2-gov-dep1/gate_a_approval_receipt.txt`）绑定 V0.2 卡片 SHA-256、三个前置阶段的不可变提交、WBS 真源、允许/禁止动作与审批身份。Gate B Approval Receipt 另行绑定 V0.3 卡片 SHA-256、最终整合提交、精确 release ID/路径、manifest 条目、切换脚本、旧指针哈希、回退条件与审批身份。卡片不得写入自身 SHA-256。

### 3.2 授权成立与失效

1. Gate A 不授权真实容器写入；Gate B 只在 Gate A 证据、V0.3 最终卡和精确四路径齐备后出现。
2. 任一卡片、提交、release ID、manifest、脚本、旧指针或审批身份漂移，对应 Gate 立即失效（Gate B 脚本在任何写入前逐项核验）。
3. 切换与最终验收是 Gate B 脚本中相互独立的步骤：切换后核验任一失败即自动回退并停止，不进入收口；执行代理不得跳过核验直接收口。
4. GUI 必须分别展示 Gate A/Gate B 状态、卡片哈希、精确 release 路径、manifest 差异、回退指针与互斥的批准/拒绝/要求修订动作，并通过高层服务生成回执（后续迭代，不阻断本卡）。

## 4. 执行步骤

**步骤 1｜只读预检与冻结**（Gate A 已完成）
- 记录 BL02、R1、R2 的不可变提交 SHA 与 §2 的前置核验；
- 对 `.auto-pm/continuity.db` 做带 SHA-256 的**只读副本**；
- 备份 `active_release.json`、`previous_release.json`、`deployment_manifest.json` 并记录 SHA-256；
- 核验命令存在：`main.py pm resume`、`main.py ledger reconcile`、`main.py change show`、`main.py continuity work adjudication-evidence`、`main.py continuity run legacy-terminal-evidence`、`main.py decision create`、`main.py implementation-card precheck`（后者在整合提交上验证）。

**步骤 2｜生成整合提交（不新增任何产品内容）**（Gate A 已完成）
- 在全新隔离工作树中，从 BL02 起步，以一次 `--no-ff` 合并依次并入 R1、R2 的不可变提交（父提交顺序 BL02、R1、R2）；两者路径不相交、无冲突；
- 对整合结果重跑并集回归（BL02 卡 §6 G1 的同一集合，加 R1 与 R2 各自新增测试），与 BL02 基线相比新增失败为 0；
- 对整合结果再次执行 BL02 卡 §6 G3（数据库副本兼容演练），确认新增合同没有引入读取误拒。

**步骤 3｜构建 release（不写入真实容器）**（Gate A 已完成）
- 复用卡 023 的 G5 确定性合同：仅以 `git archive` 从整合提交导出 `auto_pm/` 与 `templates/`，生成 `release_meta.json` 与逐文件 SHA-256 manifest；`built_at` 取提交时间以保证可复现；构建、校验、切换、回退、身份核验集中在 `.auto-pm/reports/dep1_release_ops.sh`（SHA-256 见 §8）；
- 同一提交连续构建两次到两个临时容器，逐文件 SHA-256、manifest 条目与整个 manifest 文件完全一致；
- 在临时容器完成 exact-tree 校验，并用同一脚本演练“切换 → 回退”各一次，均做根入口身份校验。

**步骤 4｜真实切换（Gate B，委托执行）**
- Gate B 脚本 `.auto-pm/reports/dep1_b_deploy.sh`：核验本卡 SHA-256、`dep1_release_ops.sh` SHA-256、Gate A 收口回执与旧指针哈希；以整合提交的代码对本卡执行机器预检；创建并批准部署 CHG 与 Decision（精确四路径）；在控制根上建立写入型 Work 与 Run；
- 以同一构建脚本把 release 写入真实容器，manifest 条目 SHA-256 必须等于 §8 的值；备份指针与 manifest；原子写指针（previous 指向旧 active，active 指向新版）。

**步骤 5｜切换后核验（只读；任一失败立即自动回退）**
- `pm resume` 的 configured 与 effective 均为新 release，无 fallback、无冲突；
- 新增命令均可用（含 `implementation-card precheck`、`decision create --target-work-id`、`continuity work create --card-file`），并用新运行时对本卡执行 `main.py implementation-card precheck --card-file`；
- SW008 与 SYS-2026-001 台账 0/0/0；
- 用真实库做只读核验：`adjudication-evidence`、`legacy-terminal-evidence` 均无误拒；事件链 0 断裂；
- 最近三次 release（新 active、previous `1.3.3-0b72499` 与更早的 `1.3.3-e648e0b`）的 exact-tree 均通过。

**步骤 6｜收口与回写**
- 核验全部通过后，Gate B 脚本创建 Checkpoint、完成 Run/Work 并收口部署 CHG（委托签署）；Agent 回写 024 §2 并报告。

## 5. 回退触发条件与方案

任一情况立即回退：exact-tree 失败；出现 fallback；`pm resume` 出现新的冲突；台账非 0/0/0；步骤 5 任一读取核验失败；关键命令缺失。

回退方法：`dep1_release_ops.sh rollback` 把切换前备份的两个指针文件复制回容器并核验运行时身份回到 `1.3.3-0b72499`（必要时同时还原 manifest 备份）；随后重复步骤 5 的核验。**不回滚数据库**：事件日志是追加的，不用旧备份覆盖切换后的新事务；数据库副本仅用于演练与取证。

## 6. 硬停止条件

- 前置条件未满足；
- 整合提交出现产品代码冲突，或并集回归、数据库副本演练失败；
- 两次构建不可复现，或 exact-tree 失败；
- 需要修改历史 release、历史事件、Checkpoint 或真实数据库；
- 需要合并到 main、推送；
- V0.2 准备卡被用于真实写入，或 V0.3/Gate B Receipt 未绑定精确 release ID、manifest、脚本与旧指针哈希。

## 7. 交付物

1. 三个来源提交与整合提交 SHA、构建脚本 SHA-256、两次构建的清单对照；
2. 新 release ID、相对上一 release 的文件差异清单；
3. 数据库副本的 SHA-256 与演练结果；
4. CHG / Decision ID；
5. 切换输出与切换后核验的原始输出；
6. 回退演练记录与回退方案；
7. 声明：这是开发运行时切换，D07 的正式稳定交付仍是独立任务；
8. Gate A 与 Gate B 两份 Approval Receipt、V0.2/V0.3 卡片 SHA-256、卡 027 预检结果与实施/验收签字状态。

## 8. Gate A 结果与 Gate B 绑定对象

| 对象 | 值 |
|---|---|
| Gate A CHG / Decision | `CHG-SCPT-2026-360` / `DEC-20260930-DEP1INTG`（Work/Run `…-M2-GOV-DEP1-001`） |
| 整合提交 | `a808fa8a43335ceb5705d7384d2afbb0a12e412c`（分支 `codex/m2-gov-dep1-integration`；父提交 BL02 `7cfe227e`、R1 `d876cf98`、R2 `e6529115`） |
| 整合纯度 | 20 个路径（R1 9 + R2 11，不相交），逐字节等于各自来源提交 |
| 并集回归 | 1458 个用例逐一有结果：1455 passed、3 skipped、0 failed；无访问冲突；相对 BL02 集合无删减，新增 94 个均属整合的测试文件（判卷 A1） |
| 数据库副本演练 | 事件 2633 条 0 断裂；运行活动 303/303；裁决/遗留证据命令 19/19 exit 0；E-G3-1 与稳定版一致（基线例外，已源码复现）；副本未改动 |
| release ID | `1.3.3-a808fa8` |
| release 路径 | `00_Infrastructure/auto_pm/releases/1.3.3-a808fa8` |
| release 文件数与差异 | 502 个文件；相对 `1.3.3-0b72499`：files 502 vs 497; added 5, removed 0, changed 18（清单 `.auto-pm/reports/m2-gov-dep1/gates/g5/diff_vs_old_release.txt`） |
| manifest 条目 SHA-256（规范化 JSON） | `2adbaaeb8c0778915a9808bc9dc6b6150921492ce2d19e6e292ce51d295db94d` |
| 两次构建 | 逐文件 SHA-256、manifest 条目与 manifest 文件完全一致 |
| `dep1_release_ops.sh` SHA-256 | `c022486676a801c328310acc8880e26b601976fbc81575051b2c1f11e57cf0b7` |
| 切换前 `active_release.json` SHA-256 | `d1b8221311db4eabed15bdc2cc836fd8cf2d670e6a84d57d841808f10a44deb8`（指向 `1.3.3-0b72499`） |
| 切换前 `previous_release.json` SHA-256 | `360be142c90d1b150b70c48314f094f4713ccbf526a78c8e17ad9844891c1159`（指向 `1.3.3-e648e0b`） |
| 切换前 `deployment_manifest.json` SHA-256 | `05f553320416183c1f334c1b2d106bf6dc7b32e50eb29f414c4018fd2088289a` |
| 临时切换/回退演练 | 新旧 release exact-tree 通过；切换后 configured=effective=`1.3.3-a808fa8`、无 fallback、无冲突、新命令可用；回退后恢复 `1.3.3-0b72499`；真实容器未改动 |
| Gate A 判卷 | A1（提交前）SHA-256 `d3f17fae7dd451eaf754f5ddff9a42637d84e1feee5f89f0c4ee26a71bbe67ad`；A2（构建、演练与本卡预检）反向绑定本卡 SHA-256，见 Gate A 收口回执 |
