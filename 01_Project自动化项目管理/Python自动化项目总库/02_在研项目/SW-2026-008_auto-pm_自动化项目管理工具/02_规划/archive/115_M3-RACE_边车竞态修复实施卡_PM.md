# M3-RACE｜连续性存储边车竞态修复实施卡

> 卡片编号：`CARD-SW008-M3-RACE`
> 版本：`V1.0`（2026-10-12；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-12 说“批准，截止17:00，推送一并授权，A4先出方案”，授权含当天排期里的 B；本卡 SHA 先在聊天报出再启动；条件见 §7；**不含推送**）
> 档次：**核心档**（分档器：`auto_pm/infrastructure/continuity_store.py` 属核心清单；测试文件属测试档；取最高档，不得降）
> 依赖：卡 114（M3-WBS15）的 Run/Work 已达技术终态且 CHG-DOCU-2026-039（SYS-2026-001）已收口，CHG-DOCU-2026-042 completed（由启动脚本核验）；**控制根对齐（A4）的执行已完成或明确推迟**（重门禁运行期间不得切换控制根）
> 隔离基线：`ba0ef3e976d12f1e9465b5fbbf52b571b3ba3882`（卡 114 的提交，已推送的远端尖端）
> 路径根：`.`
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计（**本卡建议引入独立审计**，见 §1 第 7 条）
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-12，只读勘测）

1. **症状**：`tests/e2e/test_pmf_recovery.py::test_r09_a_reader_never_fails_because_another_process_has_a_transaction_open` 偶发失败（读者子进程报“Continuity Store 路径必须是唯一链接的普通文件: continuity.db-wal”）；它让卡 100 V1.0 的受治理运行作废一次（TD-SW008-120），也迫使卡 100 V1.1 与卡 107 各带一条具名容忍规则；同家族 TD-SW008-077。
2. **根因（读自代码）**：严格只读读取在取快照前调用 `ContinuityStore._file_inventory`（`continuity_store.py` 约第 1065 行）清点数据库及 `-wal`、`-shm`、`-journal`。SQLite 在别的进程开着事务时会创建、截断、删除这些边车文件；清点在某个瞬间看到的不是“链接数为 1 的普通文件”时，**直接抛出硬错误**（第 1078 行的消息就是失败信息）。同一个检查在 `_validated_db_path`（约第 465～507 行）里早已有有界重试（V04 的 sc01～sc08，`_SIDECAR_ATTEMPTS=6`），清点这一处是漏掉的第二处：只对“读文件时被占用的权限错误”做了重试（`transient=True` 与 sc06/sc07），对链接数与类型异常没有。
3. **修法（只改清点这一处，最小）**：新增内部异常类 `_ReadSnapshotAnomalyError`（`_ReadSnapshotDriftError` 的子类）；`_file_inventory` 在 `transient`（边车）下遇到链接数或类型异常时抛它，数据库文件本身（`transient=False`）仍直接硬拒绝；`_stable_read_snapshot` 的有界重试循环把它当漂移重试，若**最后一次尝试**仍是该异常则以原消息（“路径必须是唯一链接的普通文件”）拒绝，不是泛泛的 BUSY；之后出现的普通漂移会清除这条记忆。真正的异常（持久的硬链接或非普通文件）因此仍被拒绝，只是不再被一个瞬间误杀。
4. **新增 5 个确定性测试**（`tests/infrastructure/test_continuity_store_sidecars.py`，sc09～sc12，不依赖真实竞态）：sc09（两个参数）清点把边车的错误链接数当重试信号、把数据库的当拒绝；sc10 边车瞬间不是普通文件时被重试；sc11 严格读取容忍两次清点异常；sc12 持久异常以原消息拒绝且不是 BUSY、尝试次数与睡眠次数有界。**勘测中的实测**（草稿工作树，非治理）：新测试在旧代码上，sc09（两个参数）、sc10、sc12 失败，sc11 通过——sc11 只记录“重试循环已能重试漂移”这一既有行为，不是判别性的，已在卡里如实说明；修后整个文件 13 个全过。
5. **这个竞态是概率性的，修复靠确定性测试证明，不靠真实进程反复跑**：门禁里的 r09 单独重复 20 次与九组回归里 rest 组的一次运行，只能说明“没有再见到失败”，不能证明“不会再发生”。这一点在判卷与台账里如实记录。
6. **范围边界**：不改 `_validated_db_path`、不改事务路径的检查、不改数据库文件的处理、不放宽任何拒绝条件；不碰租约、Decision、治理库的任何语义；不删除卡 100 V1.1 与卡 107 的容忍规则文字（历史记录），但**本卡自己仍带同一条具名容忍规则**（事先声明，沿用已验收做法）：rest 组里若恰有 r09 一个失败且同字节隔离重跑 3/3 通过，则放行并在判卷里记偏差，且偏差在判卷里标明“本卡的目的就是消除它，出现即说明未消除”；WBS 验收条件“具名容忍规则不再被需要”以“该规则在本卡运行中未被使用”为证据。
7. **为什么建议独立审计**：这是核心档里的并发与状态边界代码，修复的是“让一个安全检查在瞬间异常时重试”，放宽一类拒绝条件天然需要第二双眼睛；建议在你验收前由另一位审计者只读复核 §1 第 3 条与 sc09～sc12 的覆盖是否把“持久异常仍被拒”与“数据库文件从不重试”守住。
8. **演练事实（非治理，草稿工作树，不是正式证据）**：2026-10-12 在基线 `ba0ef3e9` 的临时工作树里跑了快速门禁与判卷脚本（九组用合成输出：取卡 107 的真实输出，infrastructure 组按“+5”改写；原始输出在 `.auto-pm/reports/m3-race/gates_rehearsal/`）：基线上边车测试文件 8 passed，装入冻结字节后 13 passed；r09 在候选里隔离重复 20 次全部 1 passed（只能说明“没再见到失败”，见 §1 第 5 条）；`mypy --platform win32 auto_pm` 为 “Success: no issues found in 244 source files”；真实 pre-commit 钩子对暂存的 2 个文件退出 0；三个真实变异均被杀死并按字节还原（M1 杀死 sc09、sc10；M2 杀死 sc09；M3 杀死 sc12）；判卷脚本在合成输入上判得 G1–G9 全 PASS，再用 5 个反例各判一次：rest 多一个无关失败、rest 通过数不对、竞态测试重跑失败、core 组通过数被改均判 FAIL，只有“竞态测试单独失败且三次重跑都过”按规则通过并记偏差。**演练不能证明九组真实结果**，那只有正式 Run 才有。

## 2. 单一目标与完成定义

严格只读读取的清点不再因边车文件的瞬间异常而硬失败，且持久异常与数据库文件异常仍被原样拒绝。技术完成 = 全部门禁通过且提交字节等于冻结清单；变更单收口按用户委托在 G1～G9 全 PASS 且提交字节等于冻结清单后代为执行。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线分支仍在基线、两个文件的基线 blob 等于冻结哈希、卡 114 的 Run/Work 为 SUCCEEDED/CLOSED、CHG-DOCU-2026-042 completed。启动脚本有只读的 `--check-only`。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有 `first renewal ok`。
4. **正式门禁期间不并发其他重任务，也不切换控制根**（TD-SW008-095）；整次运行预计约 2 小时 40 分钟。

## 4. 精确 Owned Paths（2）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/infrastructure/continuity_store.py` | 存在 | 连续性存储：清点边车文件遇到链接数/类型异常时改为可重试的漂移信号（新增一个内部异常类，改清点与取快照循环，约 19 行新增、4 行删除） |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/infrastructure/test_continuity_store_sidecars.py` | 存在 | 边车测试文件：新增 sc09～sc12 共 5 个确定性测试（约 80 行新增） |

出现第 3 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m3-race/`、本卡文件、演练工作树）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

最终 SHA-256；基线（`ba0ef3e9` 上的）blob SHA-256 在 `race_config.json` 与启动脚本里冻结。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/infrastructure/continuity_store.py` | 存在 | `a758586ed82745d18f1778ab04bdcf4f0d5af62a38a1972cf17f95a2d6b5e9a7` |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/infrastructure/test_continuity_store_sidecars.py` | 存在 | `cbde4b4e04601a1b4119067775836affe7ee073e5a38ce16d08d79f1f39aee54` |

### 5.2 冻结工具

工具与脚本在 `.auto-pm/reports/m3-race/`；清单文件 `reference_manifest.json` 的 SHA-256 为 `77cbdaa8b3036f33568eb2501039f94521cca27dd2d6d014bee3ccac92be26f2`。G2 的基线取卡 107 受治理执行的九组真实输出（`.auto-pm/reports/m3-a1/gates/g2_candidate/`）。

| 工具 | SHA-256 |
|---|---|
| `commit_msg.template.txt` | `b7c1fa26e76f0c1e03c0dbdd630eeb59a6eed3abbe50b15a46daa2417214f73c` |
| `install_files.py` | `f3b679ac99db8bb8bd8cfaf1d2506a8aa95e5c9612b339772b301784a169cb07` |
| `race_config.json` | `ee5936f37782038e0d29f32b2d64e01e34368a15353f92c82c69a7c2879469fb` |
| `race_gates.py` | `ea40f1b6166403740f3c5d06c597175b5aef7e5abeddc4f06705d01981a4d245` |
| `race_gates_all.sh` | `1f29aafbcc9b3347d822f45fb734f94c132119adef6522888c797e056cf26e4a` |
| `run_g2.sh` | `6956748a33added47bde7bca81e837230d6e461e746f48da7a0770499cd578fc` |

## 6. 门禁矩阵

核心档。顺序：基线测量 → 安装冻结文件 → 快速门禁（含 r09 隔离重复 20 次与三个真实变异）→ 九组回归（G2，十个输出）→ 瞬时竞态测试的三次隔离重跑（仅在其于组跑里失败时才被判卷采用）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 夹具健康、冒烟、导入测试 | 基线与候选都全部通过且数目相同 |
| G2 | 九组回归（rest、application、plc、change、contracts、infrastructure、qml_debounce_alone、cli、qml、core） | 与卡 107 的受治理输出逐项相同（失败集合、skip 数、无 ERROR）；infrastructure 组通过数恰好 +5（五个新测试），其余各组通过数不变。唯一容忍规则见 §1 第 6 条 |
| G3 | 边车测试文件与真实进程压力测试 | 边车测试文件候选全部通过且通过数 = 基线 + 5；r09 在候选里隔离重复 20 次，每次 1 passed |
| G4 | 静态检查 | 两个改动文件 ruff 无问题；`mypy --platform win32 auto_pm` 为 “Success: no issues found”；`git diff --check` 无问题 |
| G5 | 范围与字节 | 变更集恰为 2 个路径、字节等于 §5.1；HEAD 为基线；安装前工作树干净；无残留文件 |
| G6 | 既有内容不变 | `auto_pm` 树与基线只差 `infrastructure/continuity_store.py`；`tests` 树只差边车测试文件；`templates` 树不变 |
| G7 | 隔离与钩子 | 真实 .git/hooks 前后字节相同；无遗留 python 进程；真实 pre-commit 钩子对暂存的 2 个文件退出 0（临时索引） |
| G8 | 真实变异（3 个） | M1 把“边车异常抛可重试信号”改回立即拒绝：sc09、sc10 必须失败；M2 让数据库文件也走重试：sc09 必须失败；M3 让持久异常忘记原消息：sc12 必须失败；每个变异后文件按字节还原 |
| G9 | 最终范围与字节 | 全部门禁之后字节与变更集不变 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-12 说“批准，截止17:00，推送一并授权，A4先出方案”（含当天排期里的 B：M3-RACE），并已要求“替我收口验收”（原话记入 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾）；**本卡 SHA 报给用户后，由用户在聊天中回复批准**才启动。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 在聊天报告最终卡 SHA 与摘要，随即启动（预授权范围内，且在 17:00 之前能完成）。
2. 创建 SW-2026-008 SCPT/DEF 变更单、匹配 Decision（`DEC-<当天>-M3RACE01`）、Work `WORK-SW008-M3-RACE-001`、Run `RUN-SW008-M3-RACE-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认第一次续租成功**）。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m3-race`，分支 `codex/m3-race-sidecar`。
4. 安装冻结字节并完整重跑门禁（`race_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；按委托收口变更单。

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败（§1 第 6 条那一条容忍规则之外）；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；需要改这两个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；不做任何真实模型调用。**17:00 之后不启动任何新卡**；若启动时离 17:00 不足 3 小时，则不启动、改次日。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结文件与工具；演练原始输出（非治理）；勘测中新旧代码对比的原始输出；正式独立门禁与证据；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；委托收口记录。

## 11. 限制与后续

提交在本地分支 `codex/m3-race-sidecar`（卡 114 的提交之上）；推送需要用户另行授权。之后：台账回写（TD-SW008-120、077 的状态与证据）与 WBS 记录；`M2-B1`。
