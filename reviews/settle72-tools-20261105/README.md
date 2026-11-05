# SETTLE72（结算 10 条 Run）与 D07p V1.1（重新切换）：供独立审计

背景：D07p V1.0 在 2026-11-05 06:27 MST 切到 `1.3.3-dd8b192`，切换后核验只有一项不过（7.2 运行时新增的互锁 `LIVE_RUN_UNDER_FINISHED_WORK`），脚本自动回退，现行仍是 `1.3.3-d563293`。要先结掉触发这条互锁的旧 Run，再重新切换。**两个包都没有执行过**。

## 包一：`settle72-tools-20261105/`（结算卡）
- 卡 `SETTLE72_recovery_card.md`（SHA-256 `ec4bc4a5116a1e7088ce4b16246b8244ad37268334ff60e9ebba400eebc849ad`），恢复脚本 `settle72_1_recovery.sh`（`c42e4e41523d6ab5e9d23620bce6a2f390b642903d176d091708c1e7270ca67c`，内嵌卡 SHA），收口脚本 `settle72_2_chg_close.sh`（`48b682e7420db76a65f1021b4a736697136ebbadbd0b7c6b3019d778b0212b5a`），生成器 `derive_settle72.py.txt`（不是被执行的工具）。
- 目标 10 条：SW-2026-008 的 8 条（A2-201-01/03/04、PMF-C03REC-002、PMF-E01-001、PMF-G10-001，以及失败尝试留下的 M3-REL72-002、M3-D07P-001）和 SYS-2026-001 的 2 条（PMF-WBS24-001、PMF-WBS25-001）。前 6+2 条是 7.2 运行时自己的扫描（`ContinuityStore.list_live_runs_under_finished_work`）在账本 sqlite 备份副本上只读得出的，原始输出 `evidence/scan_7_2_runtime_on_ledger_copy.txt`；注意我最初凭查询写的 5 条名单是错的，已纠正。
- 做法：与 `m3-settle10`（已审计、用过）同一条恢复链，改成多目标：每个项目一张恢复变更单（SW 用 SCPT 域、SYS 用 DOCU 域）、每个项目一份恢复 Decision（`--target-run-id` 逐条列出）、一个提交绑定 Decision 文件、每条目标各起恢复 Work/Run、`settle-expired` 到 CANCELLED、目标 Work 仍在 IN_PROGRESS/BLOCKED 的转 CANCELLED（已 ACCEPTED/CANCELLED 的不动，这是相对 settle10 的差别之一）、旧口令探测只对有口令文件的 2 条做。逐行差异：`evidence/settle72_vs_settle10.diff`（先把 settle10/SETTLE10 统一改名再 diff）。
- **请重点审**：(1) 目标清单与状态是否属实（对照扫描输出和脚本里的 `T_*` 数组）；(2) 一个 Decision 列多个目标、多个恢复 Work 共用它授权，运行时是否允许（`continuity_execution_service.py:1039` 起的逐项校验：目标 Work 绑定 canonical Decision、scope 在原 Decision 批准文件内、租约已过期、恢复链与目标独立）；(3) 第 9 条 `RUN-SW008-M3-D07P-001` 租约 07:26 MST 才到期，脚本遇到未到期的目标会停下并可原处续跑；(4) 提交 Decision 文件那一步在控制根 `main` 上（`main` 落后 `origin/main`，先例的做法是推 PR 分支再 Merge commit 合并）；(5) 恢复链**没有演练过**（先例 settle10 有 `SETTLE_ROOT` 演练根，本脚本没有，只在真实账本上跑了只读预检）。
- 预检证据：`evidence/settle72_checkonly_output.txt` 是 `--check-only` 在一个只去掉“回执文件”一行的临时副本上的输出（此时没有用户批准回执，没有伪造）；真实脚本现在会在回执处拒绝。

## 包二：`d07p2-switch-tools-20261105/`（切换卡 V1.1）
- 卡 `D07p_card.md`（`6ea633dbed9a99fb08f7f01ba9899d094ff8e533ed6286005a1cdd5f7490e401`），脚本 `d07p_deploy.sh`（`620e8251bb89ebe977a9bf268dbcbc16b0b129bd19ade641524c5a5400f45837`，内嵌卡 SHA），生成器 `derive_d07p2.py.txt`；V1.0 的脚本与失败证据在 `evidence/`；逐行差异 `evidence/d07p2_vs_d07p.diff`。
- 与 V1.0 的差别：新编号（Work/Run/Checkpoint `-002`、Decision `M3D07P02`、owner `claude:m3d07p2`、幂等键 `d07p2-`、证据目录 `m3-d07p2`）；沿用变更单 CHG-SCPT-2026-479；新前置条件（SETTLE72 已完成、V1.0 的 Run 与 REL72-002 已 CANCELLED、两个项目都没有挂在已结束 Work 下的 Run）；切换后多核 `pm orient SYS-2026-001` 冲突为空；**审计引用需要对 V1.1 另行放行，不沿用 V1.0 的**；用户的常设授权记录（04:04:33Z 原话）原样沿用。
- 注意风险：V1.0 装好的发布目录 `1.3.3-dd8b192` 仍在 `releases/` 并在清单里登记（未入库的改动），V1.1 的 Run 启动时这些路径是“已声明脏”的，是否被运行时接受要到启动时才知道；被拒就停下，不绕过。
- `--check-only` 现在会在缺 `switch_audit_ref.txt` 处拒绝（其前面的指针、清单、已装版本核验都通过，说明 V1.0 的回退把指针字节原样还原了）。
