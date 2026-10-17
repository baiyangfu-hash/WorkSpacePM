# M2-DEP-INT｜把发布线的 ADJ 与 IC02 整合进 M2 代码线实施卡

> 卡片编号：`CARD-SW008-M2-DEPINT`
> 对应 WBS：`M2-DEP-INT`（V3.0.24 §4.7.1，由 `M2-GOV-WBS8` 新增；WBS 卡提交 `f06c5aac`）；依据 N2-0 勘测报告 `.auto-pm/reports/m2-n20/N2-0_SURVEY_REPORT.md`
> 版本：`V1.0`（2026-10-09；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-09 约 11:15 的开工信号预授权本卡，原话见 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾；条件见 §7）
> 档次：**核心档**。分档器（卡 078）对本卡 20 个路径的计算结果：核心档，命中规则 `CORE-CONTINUITY-SERVICES`、`CORE-CONTINUITY-STORE`、`CORE-CONTRACTS`、`CORE-IMPLEMENTATION-CARD`、`CORE-WORK-REGISTRY`、`PRODUCT-PACKAGE`、`TESTS-TREE`，规则表版本 1.0，无未知路径，声明“核心档”无冲突；跑全量九组、相关静态与范围门禁
> 依赖：`M2-GOV-WBS8`（卡 081，提交 `f06c5aac`，CHG-DOCU-2026-032 用户已验收 completed，由启动脚本核验）
> 隔离基线：`f06c5aac08a90a3e089142f9d16cafdfead75452`（WBS 卡提交，分支 `codex/m2-gov-wbs8-freeze`）；第二个父提交：`a808fa8a43335ceb5705d7384d2afbb0a12e412c`（发布 `1.3.3-a808fa8` 的源提交）
> 治理任务真源：WBS V3.0.24（基线提交中的 WBS 文件）
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

## 1. 背景与已核实事实（2026-10-09，基线 `f06c5aac`）

1. **为什么**：N2-0 勘测发现，已部署的发布 `1.3.3-a808fa8`（源提交 `a808fa8a`）与 M2 代码线从 `7cfe227e` 分叉：发布线比分叉点多 3 个提交（ADJ `d876cf98`、IC02 `e6529115` 与它们的整合提交 `a808fa8a`），M2 线多 45 个提交，且 M2 线没有 `implementation_card_precheck.py`、`decision.py` 里没有 `adjudicate_blocked_work`。不整合就部署，会丢掉这两个已验收的功能。用户 2026-10-09 决定把它作为 M2 的剩余任务，并预授权本卡。它是部署前提任务，不是债务偿还。
2. **做什么**：把发布源提交 `a808fa8a` 合并进 M2 线（`git merge --no-commit --no-ff`），提交是第二个父提交为 `a808fa8a` 的合并提交。我已在隔离树上演过：合并**没有任何文本冲突**，结果恰为 20 个路径（18 个既有文件被修改、2 个新增：实施卡预检模块与它的测试），+2284/−31 行。内容就是 git 的合并结果，**不手改任何一行**。
3. **ADJ**（`decision create --target-work-id` 与 `adjudicate_blocked_work`，按 Git Decision 字节绑定的裁决合同）与 **IC02**（实施卡创建 Work 前的只读预检，强制接入 `continuity work create`）都是已在发布线验收闭环的功能（CHG-SCPT-2026-358、359；整合 CHG-SCPT-2026-360 completed）。本卡只做整合，不改它们的行为。
4. **测试数据**：合并使被改动的 10 个测试文件的收集节点从 235 增到 329（新增 94、减少 0）：`core` +48（其中预检新文件 29）、`cli` +34、`contracts` +6、`infrastructure` +6；其余组不变。
5. **静态检查**（在隔离树上跑过）：19 个 Python 文件 `ruff` 零问题、`mypy --strict` 零问题，`git diff --cached --check` 通过。
6. **九组回归的基线**：沿用已治理的原始输出，不重测：八组取卡 074（F02，核心档，九组全跑）的输出，`rest` 组取卡 078（分档器）的输出；自那两张卡以来，这些组的代码没有变化。基线与我的演练结果如下（演练是在隔离树上对合并结果跑的九组，非受治理执行）：
   - rest：基线 15 failed, 831 passed, 13 skipped in 1279.41s (0:21:19)；演练 15 failed, 831 passed, 13 skipped in 1619.54s (0:26:59)
   - application：基线 174 passed in 4.05s；演练 174 passed in 3.50s
   - plc：基线 144 passed, 24 warnings in 52.34s；演练 144 passed, 24 warnings in 79.24s (0:01:19)
   - change：基线 230 passed in 11.62s；演练 230 passed in 14.05s
   - contracts：基线 210 passed, 1 skipped in 36.00s；演练 216 passed, 1 skipped in 43.18s
   - infrastructure：基线 68 passed in 123.40s (0:02:03)；演练 74 passed in 192.44s (0:03:12)
   - cli：基线 359 passed, 1 skipped, 48 warnings in 656.20s (0:10:56)；演练 393 passed, 1 skipped, 48 warnings in 736.74s (0:12:16)
   - qml：基线 305 passed, 1 deselected in 704.31s (0:11:44)；演练 305 passed, 1 deselected in 644.81s (0:10:44)
   - core：基线 3 failed, 1091 passed, 1 skipped in 6487.56s (1:48:07)；演练 1142 passed, 1 skipped in 5369.02s (1:29:29)
7. **演练**：在隔离演练树上对合并结果完整跑了一遍（非受治理执行，不能复用为正式门禁）：九组回归、与卡内相同的快速门禁、判卷器；G1–G9 全部 PASS；`gate_verdict` SHA-256 `751ed7e2697a97038a77cb2b41f1dfb9d03485c5ef37306810d4bc1f42043208`；证据目录 `.auto-pm/reports/m2-depint/gates_rehearsal/`。G8（合并重现）演练结果：候选树与重现树相同（`644c5732219f`）。按用户的时间限定，本卡只演练这一次。
8. **与已有卡的差别**：本卡没有“变异检查”（F02 的 G8）——整合的是两条已各自验收的提交，没有新写的逻辑可变异；改为 G8“合并可重现”：用同一条合并命令在一次性工作树里再合并一次，要求树完全相同，从而证明候选里没有手写的改动。
9. 不在本卡范围：任何 §4 之外的文件；WBS、台账、规则、模板、`.trae`；合并 main、推送、部署、切换 release；处置任何债务或失败记录；M3 的任何事项；真实模型调用。

## 2. 单一目标与完成定义

把发布线的 ADJ 与 IC02 合并进 M2 线，只改这 20 个路径，内容等于 git 合并结果。技术完成 = 提交通过全部门禁（G1–G9）、提交等于 Checkpoint、Run 与 Work 到终态。**验收已委托**：G1–G9 全部通过且提交与 Checkpoint 一致时，由 claude-sonnet-5-5 代为收口变更单；用户可复核并推翻。

## 3. 实施前预检

1. 核对卡字节与已向用户报告的 SHA 一致、基线、20 个 owned path 的基线状态与冻结的合并结果字节指纹、工具字节等于 manifest。没有这些，不创建 CHG/Decision/Work/Run。启动脚本有只读的 `--check-only`，预检只用它。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空；预检仅读，不代表获批。
3. 核对前置 WBS 卡（CHG-DOCU-2026-032，用户 2026-10-09 已验收）为 completed 且其 Run SUCCEEDED、Work CLOSED；历史失败记录仍在原状态且本卡不触碰。
4. 新候选 HEAD 等于基线且 clean、不在合并中；工具、配置均匹配冻结指纹。
5. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有 `first renewal ok`，门禁期间每次检查先看续租日志；门禁用后台等待，不反复轮询。
6. **时限**：用户要求本卡的门禁最晚 18:30 前正式开始，否则今天不做；22:00 硬截止，不开第二轮。

## 4. 精确 Owned Paths（20）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `auto_pm/application/core/continuity_execution_service.py` | 存在 | 修改：与发布线 ADJ/IC02 合并（git 合并结果，不手改） |
| 2 | `auto_pm/application/core/implementation_card_precheck.py` | 计划新增 | 新增：实施卡启动前只读预检（IC02，417 行） |
| 3 | `auto_pm/application/core/implementation_card_service.py` | 存在 | 修改：与发布线 ADJ/IC02 合并（git 合并结果，不手改） |
| 4 | `auto_pm/application/core/work_registry_service.py` | 存在 | 修改：与发布线 ADJ/IC02 合并（git 合并结果，不手改） |
| 5 | `auto_pm/contracts/implementation_card.py` | 存在 | 修改：与发布线 ADJ/IC02 合并（git 合并结果，不手改） |
| 6 | `auto_pm/infrastructure/continuity_store.py` | 存在 | 修改：与发布线 ADJ/IC02 合并（git 合并结果，不手改） |
| 7 | `auto_pm/templates/governance/implementation_card.md.jinja` | 存在 | 修改：与发布线 ADJ/IC02 合并（git 合并结果，不手改） |
| 8 | `auto_pm/ui/cli/continuity.py` | 存在 | 修改：与发布线 ADJ/IC02 合并（git 合并结果，不手改） |
| 9 | `auto_pm/ui/cli/decision.py` | 存在 | 修改：与发布线 ADJ/IC02 合并（git 合并结果，不手改） |
| 10 | `auto_pm/ui/cli/implementation_card.py` | 存在 | 修改：与发布线 ADJ/IC02 合并（git 合并结果，不手改） |
| 11 | `tests/cli/test_continuity.py` | 存在 | 修改：与发布线 ADJ/IC02 合并（git 合并结果，不手改） |
| 12 | `tests/cli/test_decision.py` | 存在 | 修改：与发布线 ADJ/IC02 合并（git 合并结果，不手改） |
| 13 | `tests/cli/test_implementation_card.py` | 存在 | 修改：与发布线 ADJ/IC02 合并（git 合并结果，不手改） |
| 14 | `tests/contracts/test_decision_package.py` | 存在 | 修改：与发布线 ADJ/IC02 合并（git 合并结果，不手改） |
| 15 | `tests/contracts/test_implementation_card.py` | 存在 | 修改：与发布线 ADJ/IC02 合并（git 合并结果，不手改） |
| 16 | `tests/core/test_implementation_card_precheck.py` | 计划新增 | 新增：预检的 29 个测试节点 |
| 17 | `tests/core/test_implementation_card_service.py` | 存在 | 修改：与发布线 ADJ/IC02 合并（git 合并结果，不手改） |
| 18 | `tests/core/test_legacy_terminal_lease_fence.py` | 存在 | 修改：与发布线 ADJ/IC02 合并（git 合并结果，不手改） |
| 19 | `tests/core/test_work_registry_service.py` | 存在 | 修改：与发布线 ADJ/IC02 合并（git 合并结果，不手改） |
| 20 | `tests/infrastructure/test_continuity_store.py` | 存在 | 修改：与发布线 ADJ/IC02 合并（git 合并结果，不手改） |

出现第 21 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m2-depint/`、本卡文件、演练工作树）不是额外产品 owned paths，不进本卡产品提交。

## 5. 字节合同

### 5.1 参考字节指纹

20 个文件的最终 SHA-256（UTF-8、LF、无 BOM），即 `git merge --no-commit --no-ff a808fa8a` 在基线上的结果；冻结文件保存在 `.auto-pm/reports/m2-depint/proto/`。安装步骤只在候选位于基线、clean、不在合并中时执行合并，然后核对：MERGE_HEAD 等于发布源提交、无未合并路径、暂存变更集恰为这 20 个路径且工作树等于索引、每个文件的字节等于下表和 `proto/` 副本、无冲突标记。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `auto_pm/application/core/continuity_execution_service.py` | 存在 | `e96463fd1767e5132dce4c0662dd3a3f71d3546c6dca73d978bb8aea2c4bb09b` |
| 2 | `auto_pm/application/core/implementation_card_precheck.py` | 计划新增 | `2b92e7f1a06ee4b9ed18117ca51bf6671a9051dc88d6cf9d9387f87d0402f297` |
| 3 | `auto_pm/application/core/implementation_card_service.py` | 存在 | `32e110e6acebfd549ce6afa41dccb353e837739ff70c5b3a5e5f672d2f6102ff` |
| 4 | `auto_pm/application/core/work_registry_service.py` | 存在 | `74c066bbd8cb4d35f9c5e38e29e61d85abdf25bd0cc67f02de19dd7109d5c753` |
| 5 | `auto_pm/contracts/implementation_card.py` | 存在 | `b3b04730dfe4283a0f90b1c5215448f6614c128da64511bd93eb525cdfa72269` |
| 6 | `auto_pm/infrastructure/continuity_store.py` | 存在 | `3e3ae1bddaa87588ad2069ce226a0a5d040d9d84a021e2ea638a011cf869f983` |
| 7 | `auto_pm/templates/governance/implementation_card.md.jinja` | 存在 | `561b218fa48c3c69baf19707540c0f7aad3cfd432298ab016ec77410f937013f` |
| 8 | `auto_pm/ui/cli/continuity.py` | 存在 | `8c5b02980670d94bd2836287f7753dfc976065b5a109686b759365e92ab1b087` |
| 9 | `auto_pm/ui/cli/decision.py` | 存在 | `e2c0255a9db923cbadf5a36272ebd0faaa080059e38cba7173d844f45894cfd4` |
| 10 | `auto_pm/ui/cli/implementation_card.py` | 存在 | `61aa2faff4c36214dd6cd2d9dac9357d33f54708b67cd9cd21ef3eaccaff2d09` |
| 11 | `tests/cli/test_continuity.py` | 存在 | `1e4795db8b23b3d5877f0da422dd902b8b808da8a21656d63c3c6cc18d63b106` |
| 12 | `tests/cli/test_decision.py` | 存在 | `98281a31fbd900c87af0e671e1d71573fad66e5de5e8a20757e52dc0874cf44d` |
| 13 | `tests/cli/test_implementation_card.py` | 存在 | `4fef11cc8fbb54865dbf7707fca3343afb09027e12103ae3f3805124d006ed8b` |
| 14 | `tests/contracts/test_decision_package.py` | 存在 | `6c4f201dc6a0c2b907d9cb4a002b24d986b56e29605a14410b4d1fad56f825e0` |
| 15 | `tests/contracts/test_implementation_card.py` | 存在 | `0ee63e6d2fdba62a16eaa6f8a7308218b712f790daf3079850192ca27112757c` |
| 16 | `tests/core/test_implementation_card_precheck.py` | 计划新增 | `b980eecbc55d61eefde9ea7e62cdf93c9b2a236763bb5017e9b26b32784d0b4e` |
| 17 | `tests/core/test_implementation_card_service.py` | 存在 | `65a5598a7103d448991cfbc1e4b69513adf7ca306684f7ab86938ec4bb5c0fbb` |
| 18 | `tests/core/test_legacy_terminal_lease_fence.py` | 存在 | `bd7959dc285bbd6f2ceb52c59628944a6c41f9dc784d7f56dc73d2fce6188394` |
| 19 | `tests/core/test_work_registry_service.py` | 存在 | `4c4379b5328ca71a1e4c7e4b0fa8ebcb80a7e61821b0e9f01b6189eaddfc245c` |
| 20 | `tests/infrastructure/test_continuity_store.py` | 存在 | `82674491ba625de454c2523b3c3d39eb750f2247ec77142a6bc99982c4ac2e1a` |

### 5.2 冻结工具

工具与脚本由卡 074（F02，核心档）与卡 081 的已演练工具派生；共用判卷脚本仍是控制根下的外部副本。manifest（含上表与下表）的 SHA-256 为 `995560830741b7631324098fa3d7d08eb6205618e6d11b8b89d45e03851d4845`，门禁脚本启动时核对该值。

| 工具 | SHA-256 |
|---|---|
| `dint_install.py` | `9ddffa699187ec345a558e696043251890881ba8f136b75618d4731cbbd2b8ba` |
| `run_gates_dint.py` | `0a1c241adb84bd08c94fb7bfdbc88eb0cfc1e101db81edf6d5febeeeb27318e3` |
| `run_gates_fast.sh` | `89a2687b8306d7f3756fcfee8cd8ccece3b048733ef3ac3d2f5dd71a747f6f05` |
| `run_gates_g2.sh` | `2d9f5d7137a1f338e9ed3eee65e0094c4519a2a966fec80e1762ac79a50f3edd` |
| `run_g2.sh` | `d0c29cbce6ab813186b9390425e59336e7ac64c500af106ad64453f0bfea5b00` |
| `g6_check.py` | `5a1ee10ac43c07946eb3d85191a23d4efe6e0927cbdaa6f9842ed6e390140059` |
| `g8_merge_repro.py` | `c90d4ec65397700cb67764d2496a055c675ac5148f78d0a6a9077c0c5a86da32` |
| `dint_group_check.py` | `4527b3a1d360ae0a867f7e9d52ad861f289da28f40a9339135effcb75f4163fb` |
| `new_nodes.json` | `315626f9d6bdde9dbb091623b8fd5ddc69d7c62a3c7309d642183da06f110074` |
| `dint_config.json` | `e0c7924cf0ad7391999126b5651c1330bdbad670376fbef93280f65d3088b2b2` |
| `m2-tools/verdict_check.py` | `0fcbd53020b909b123f3819dcf0774d1f8d93dbc4354dcc5f3c1f72dd56f2188` |

## 6. 门禁矩阵

核心档。顺序：基线测量 → 合并（安装）→ 快速门禁（G1、G3、G4、G6、G8、G9）→ 九组回归（G2）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 夹具健康、冒烟、导入测试 | 与合并前在同一候选里测得的结果完全相同（同样的失败、同样的通过数、同样的 skip） |
| G2 | 九组回归（十份输出） | 每组失败集合与基线相同、`core` 组通过数恰增 48、`cli` 组恰增 34、`contracts` 与 `infrastructure` 各恰增 6、其余组通过数不变、无新增 skip 与 ERROR |
| G3 | 新测试节点 | 十个测试文件收集到的恰为基线节点加冻结的 94 个节点，没有基线节点消失 |
| G4 | 静态检查 | 19 个 Python 文件 `ruff`、`mypy --strict` 零问题，`git diff --cached --check`，字节扫描，没有发布线以外的新抑制注释 |
| G5 | 范围 | 变更集恰为 20 个 owned path，字节等于 §5.1，HEAD 为基线、MERGE_HEAD 为发布源提交（门禁前后不变），无残留 |
| G6 | 既有内容不变 | `templates`、`auto_pm`、`tests` 树除这 20 个文件外与基线逐字节相同 |
| G7 | 隔离 | 合并没有引入发布线以外的对真实控制根的引用；真实 `.git/hooks` 前后字节相同；门禁不遗留 python 进程 |
| G8 | 合并可重现 | 一次性工作树里同一条合并得到相同的树；MERGE_HEAD 是发布源提交且基线不含它；无未合并路径、无冲突标记 |
| G9 | 目标测试整文件 | 十个测试文件全部通过，0 failed，通过数加 skip 数等于收集数，skip 数等于冻结值 1 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-09 约 11:15 的预授权（原话 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾）：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、止损照旧；时限：准备最晚 16:30 完成，门禁最晚 18:30 前正式开始，22:00 硬截止、不开第二轮 |
| 最终验收 | 已委托：G1–G9 全部通过且提交与 Checkpoint 一致时，由 claude-sonnet-5-5 代为验收并收口 CHG；用户可复核并推翻 |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

卡、基线、范围或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 在聊天报告最终卡 SHA 与改动摘要。
2. 新建 SW-2026-008 SCPT/OPT 变更单，创建匹配 Decision（`DEC-<当天>-DINTADJ1`）、Work `WORK-SW008-M2-DEPINT-001`、Run `RUN-SW008-M2-DEPINT-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认第一次续租成功**）；实际创建前验证未被占用，不复用幂等键或旧 token。
3. 从代码基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m2-depint`，分支 `codex/m2-dep-int-adj-ic02`。
4. 运行 `dint_gates_all.sh`（合并并完整跑门禁）；先创建当前字节 Checkpoint，再正常 Hook 提交合并提交（第二个父提交为发布源提交）：绝不 no-verify；核对提交父、范围及 blob 与 Checkpoint 完全一致。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；条件满足后代为验收并收口 CHG。

## 9. 硬停止

基线、工具/卡/Decision 指纹、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败（包括九组里任何一组出现基线没有的失败）；合并出现冲突或与冻结结果不一致；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；需要改这 20 个文件以外的任何内容、手改合并结果、或为让测试变绿而放宽断言：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，今天不开第二轮；不处置任何历史失败对象。按止损规则：同一问题最多修 2 轮，每卡总时长上限 6 小时，连续 2 张卡失败整体停下；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结的合并结果与工具；演练原始门禁（非治理）；正式独立门禁、CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；代验收记录；GPT 对提交的独立审计（M2 最终审计包的一部分）。

## 11. 限制与后续

本卡只整合，不改 ADJ 与 IC02 的行为，不处理其他债务；整合后 M2 线包含发布线的全部提交，是后续发布构建的前提。技术性部署在 GPT 最终审计之后、由用户再明确批准；推送由用户另行授权。无合并 main、推送、部署或 release 切换授权。
