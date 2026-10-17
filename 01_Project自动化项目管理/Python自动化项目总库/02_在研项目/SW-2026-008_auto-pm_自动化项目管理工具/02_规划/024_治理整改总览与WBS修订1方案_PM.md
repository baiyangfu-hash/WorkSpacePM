# 治理整改总览（阶段索引与恢复入口）

> 编号：`PLAN-SW008-M2-GOV-RECT-001`
> 版本：`V0.3`（2026-09-29）
> 状态：`PLANNED / NOT_AUTHORIZED`
> 性质：总览与索引，本身不授权任何实施；各阶段的实施权限只来自各自的实施卡、CHG 与 Decision
> 用途：**任何新会话或新 Agent 必须先读本文，再读当前阶段的卡**；不得凭聊天记忆推进
> 说明：本文是**索引文件**，不含 owned paths，不作为创建 Work 的依据，因此不适用 027 §5.1 的头部与路径表格式，免预检

## 0. 如何从零恢复（先做这个）

1. 读本文 §1（GPT 原始整改要求，逐字）、§2（阶段表）、§4（全局规则）。
2. **用事实判定当前阶段，不用记忆**：按 §3 的“状态核验命令”逐条执行，对照 §2 的“完成判据”。第一个未满足完成判据的阶段就是当前阶段。
3. 只读取当前阶段对应的卡；执行前先完成该卡 §预检，任一项不符即停止并报告。
4. 每个阶段结束后，把产出的 SHA、CHG/Decision/Work/Run/Checkpoint ID 回写到 §2 的“回写栏”，并向用户报告完成状态。
5. 相关背景事实已沉淀在项目记忆（代码血统、运行规则、审批与汇报偏好）；写卡与执行前也应重新核验，不得引用未核验的结论。

## 1. GPT 原始整改要求（逐字，未经改写）

> 在继续 M2/U05 前，先完成一次独立治理整改，不重新执行 H11，不回档、不修改历史事件或 Checkpoint。
>
> 整改范围：
>
> A. 更新 WBS 当前投影：
> - fubai 与 baiyang 是同一用户的等权署名；
> - H11 标记为 COMPLETED / ACCEPTED；
> - 写入 14 条 Work CANCELLED、5 条 lease 围栏、事件链 2561/0 断裂等当前证据；
> - 保留历史版本，不把历史文字删除。
>
> B. 修复行政裁决授权合同：
> - adjudicate_blocked_work 必须像 settle_expired_run 一样，将原 Decision 和裁决 Decision 的文件字节绑定恢复 Run 的 Git HEAD；
> - Decision 必须已跟踪、相对 HEAD 无脏改、SHA 与 HEAD blob 一致；
> - 补充失败、漂移、未跟踪、HEAD 不一致及正常重放测试。
>
> C. 补齐正式 CLI：
> - decision create 增加 --target-work-id；
> - 与 --target-run-id 建立按 action 的严格互斥/必填合同；
> - adjudicate_blocked_work 只接受精确 target_work_ids；
> - 补齐 CLI 与 DTO 测试，不再使用临时 Python 脚本生成此类 Decision。
>
> D. 修复实施卡开工前预检：
> - 验证卡内命令是否存在；
> - 验证测试路径是否存在，或明确声明为计划新增；
> - baseline 漂移、未知命令、未知既有路径必须在创建 Work/Run 前 fail-closed；
> - 为 doc check --strict 和不存在测试路径两类历史问题添加防复发测试。
>
> 限制：
> - 不重做 H11，不改变其 14 条 Work、5 条围栏事件及历史 Checkpoint；
> - 不清理主工作区；
> - 不合并、不推送、不部署、不切换 release；
> - 不使用 pm-workflow；
> - 所有修改必须使用独立实施卡、精确 owned paths、隔离候选、正常 Hook 和当前字节 Checkpoint。
>
> 完成后自检并交付：
> 1. 精确 diff；
> 2. 测试/Ruff/Mypy 原始命令与 Exit Code；
> 3. 不可变提交；
> 4. Checkpoint 与控制面终态；
> 5. WBS 更新证据；
> 6. 技术债登记；
> 然后停止，交给 GPT 独立裁决，未经裁决不得启动 U05。

### 1.1 与上述要求的已知偏差（须让 GPT 与用户知情）

| 偏差 | 原因 | 处理 |
|---|---|---|
| 增加“统一基线整合”阶段（BL02） | 摸底证明产品线是三条互不包含的线（U04B、R1+Hook 修复、H11 发布线），在任一条上做 B/C/D 都会扩大分叉；D 所扩展的实施卡代码只在 M2 线 | 卡 023 |
| 增加“一次集成部署”阶段 | 整改要求“不部署、不切换 release”，但 B/C/D 只有部署后才在生产生效，且当前运行时不含 U04B 等 M2 代码 | 卡 028；**仅在用户另行批准后执行**，不随任何卡自动授权；GPT 需知情 |
| H11 直接标 `COMPLETED / ACCEPTED` | GPT 已独立只读核验 H11 的 14 条 Work、5 条 lease 围栏、事件链和台账；用户随后确认 `fubai` 与 `baiyang` 为本人等权署名，原署名疑点已解除 | 卡 025、029 不再重复打开或二次验收 H11 |
| WBS 分两次修订（修订 1 与修订 2） | 修订 2 需要写入 B/C/D 与部署的最终证据 | 卡 025、029 |
| D 项范围扩大为“预检命令 + 强制接入 `continuity work create`”（方案 B） | GPT 要求“在创建 Work/Run 前 fail-closed”，只交付可选命令无法满足；方案 C（统一为结构化卡）暂列后续迭代 | 卡 027 V0.2 |
| A 项增加“来源说明” | 等权署名不能掩盖“部分治理记录由 Claude 依据对话授权写入”的事实 | 卡 025、029 |

## 2. 阶段表（顺序不可调换；前一阶段未达完成判据，不得启动后一阶段）

| # | 阶段 | 实施卡 | 覆盖的 GPT 项 | 完成判据（用事实核验） | 回写栏（SHA / ID） |
|---|---|---|---|---|---|
| 0 | 全局摸底（已完成，只读） | 无 | 背景 | 项目记忆与 023 §1 已写入 | 已完成 2026-09-29 |
| 1 | WBS 修订 1 | 025 | A（前半） | 隔离候选提交存在；WBS 新增章节含 §025-4 全部条目；历史文字无删除；台账对账 0/0/0 | 由 GPT 实施；提交 `a385452c`（分支 `codex/m2-gov-wbs1-revision`，父 `58ac6a03`）；CHG-DOCU-2026-022（已关闭）；Claude 只读复查 2026-09-29：基本通过，偏差见下 |
| 2 | M2-GOV-BL02 统一基线 | 023 | 前置 | 统一基线不可变提交存在；G1～G6 PASS；结论 `PASS` | **COMPLETED 2026-09-30**（卡 023 V0.4，SHA-256 `8e61e0ad…9a7d`）：最终候选 `7cfe227e7bf4a7df57d95644a80ea2652ef5a9cc`（分支 `codex/m2-gov-bl02-unified-baseline`，`e8d9b3e5`/`4e08b0dd`/`7cfe227e`）；CHG-SCPT-2026-356、恢复 CHG-SCPT-2026-357 均 completed；Decision `DEC-20260929-BL02CODE`、`DEC-20260930-BL02RSET`（Git 绑定提交 `6f759fce`）；Work `WORK-SW008-M2-GOV-BL02-001` CLOSED；整合 Run 001 CANCELLED（settle-expired），验证 Run 002 SUCCEEDED，`CKPT-SW008-M2-GOV-BL02-002`；G1 `PASS_WITH_BASELINE_EXCEPTION`（例外 E-G1-1/2/3、E-G3-1 均有来源复现）、G2/G4/G5/G6 PASS、G3 `PASS_WITH_BASELINE_EXCEPTION`；判卷文件 SHA-256 `c387bb9b…d18e`；执行方式：用户 2026-09-30 授权 Claude 全权推进 M2，审批/验收为委托执行；证据 `.auto-pm/reports/m2-gov-bl02/` |
| 3 | M2-GOV-ADJ（R1） | 026 | B、C | 在 BL02 基线上的不可变提交；B/C 测试全绿；无临时脚本生成 Decision | **COMPLETED 2026-09-30**（卡 026 V0.3，SHA-256 `5367f66c…b476`）：提交 `d876cf98578de1d5915827d6f24c4ae90f9a12cf`（分支 `codex/m2-gov-adj`，父 `7cfe227e`，9 路径）；CHG-SCPT-2026-358 completed；Decision `DEC-20260930-ADJCODE0`；Work/Run `…-M2-GOV-ADJ-001` CLOSED/SUCCEEDED；`CKPT-SW008-M2-GOV-ADJ-001`（提交前创建，9 个 blob 一致）；G1 `PASS_WITH_BASELINE_EXCEPTION`（1204 passed，仅 E-G1-1），G2～G6 PASS；判卷 `a4e6b9e2…33ce`；偏差：reconcile_terminal_lease 保留 RELEASED（R1 并集）；证据 `.auto-pm/reports/m2-gov-adj/` |
| 4 | M2-GOV-IC02（R2） | 027 | D | 在 BL02 基线上的不可变提交；两类防复发测试通过 | **COMPLETED 2026-09-30**（卡 027 V0.4，SHA-256 `6cee8b7c…2880`）：提交 `e65291151e03bdfbed51b06149414f9aaada75d5`（分支 `codex/m2-gov-ic02`，父 `7cfe227e`，11 路径，含 2 个新增）；CHG-SCPT-2026-359 completed；Decision `DEC-20260930-IC02CODE`；Work/Run `…-M2-GOV-IC02-001` CLOSED/SUCCEEDED；`CKPT-SW008-M2-GOV-IC02-001`（提交前创建，11 个 blob 一致）；G1～G7 全 PASS（1197 passed，0 失败；E-G1-1 的时间炸弹夹具已在 owned 测试文件内修复）；判卷 `8d2711a1…68b9`；证据 `.auto-pm/reports/m2-gov-ic02/` |
| 5 | 开发运行时集成部署 | 028 | 生效条件 | **仅用户批准后**；active 指向集成 release；回退演练通过 | **Gate A COMPLETED 2026-09-30**（CHG-SCPT-2026-360；整合提交 `a808fa8a`，父 7cfe227e/d876cf98/e6529115；并集回归 1458/1458 有结果、0 失败；两次构建一致 release `1.3.3-a808fa8`，manifest 条目 `2adbaaeb…`；临时切换/回退演练通过；卡 028 V0.3 SHA `5255537e…` 预检通过）。**Gate B COMPLETED 2026-09-30**（用户运行 `dep1_b_deploy.sh`，第 3 次重入完成；CHG-SCPT-2026-361 completed；Decision `DEC-20260930-DEP1DPLY`；Work/Run `…-M2-GOV-DEP1-002` CLOSED/SUCCEEDED；`CKPT-SW008-M2-GOV-DEP1-002`；active=`1.3.3-a808fa8`、previous=`1.3.3-0b72499`；切换后核验：identity 无 fallback/冲突、V0.3 预检以新运行时 exit 0、SW008/SYS-2026-001 台账 0/0/0、真实库证据命令 19/19、事件链 2645 事件 0 断裂、三个 release exact-tree OK；post_checks SHA-256 `adc1c84b…1481`；回执与回退命令见 `.auto-pm/reports/m2-gov-dep1/gate_b/acceptance_receipt.txt`；第 1 次因预检相对路径自动回退、第 2 次因备份目录已存在在切换前停止，均已修复；未合并 main、未推送；D07 正式稳定交付仍独立） |
| 6 | WBS 修订 2 与交付 | 029 | A（后半）+ 交付物 1～6 | 交付包齐全；Claude 只读复查与用户验收完成，或用户明确决定直接继续 | **COMPLETED 2026-09-30**（卡 029 V0.4，SHA-256 `d66baf84…2910`）：第一提交 `e07f766280e2a740f57e3b0089e83d273d30f2ac`（父 `a385452c`，V3.0.17，+51/−7）经**用户本人**验收（回执 `.auto-pm/reports/m2-gov-wbs2/first_commit_acceptance_receipt.txt`）；第二提交 `572932a7d7fe23cf799c6f8800d77263aec3c3ee`（父 `e07f7662`，V3.0.18，+8/−3，仅 3 行状态文字改写）；分支 `codex/m2-gov-wbs2`；Decision `DEC-20260930-WBS2CAND`；Checkpoint `CKPT-SYS001-M2-GOV-WBS2-001/002`；Run 001/002 SUCCEEDED（002 为有界纠正 Run，见交付包技术债 18）、Work CLOSED；G1～G5 全 PASS（`gates/`、`gates2/`）；两项目台账 0/0/0；交付包 `.auto-pm/reports/m2-gov-wbs2/M2_GOV_DELIVERY_PACKAGE.md`。阶段 2～5 记 `DELEGATED_ACCEPTED`。**CHG-DOCU-2026-023 最终收口待用户运行** `wbs2_3_chg_close_by_user.sh`。整改闭环，U05 可从 BL02 `7cfe227e` 启动 |
| — | M2 后续执行与最终审计 | 各原子任务独立实施卡 | — | GPT 继续实施 U05 及后续原子任务；Claude 负责阶段复查/异常接管；整个 M2 完成后再做总审计与裁决 | |

## 3. 状态核验命令（恢复时逐条执行，均为只读）

```bash
git -C /c/Users/fubai/Documents/My_Workspace branch -a --list "codex/*bl02*" "codex/*adj*" "codex/*ic02*" "codex/*wbs*"
git -C /c/Users/fubai/Documents/My_Workspace worktree list
grep release_id /c/Users/fubai/Documents/My_Workspace/00_Infrastructure/auto_pm/active_release.json
```

再以 `main.py change show <CHG>` 查看各阶段 CHG 状态；以 `main.py ledger reconcile SW-2026-008` 核验台账；以 `main.py pm resume SW-2026-008 --json` 核验无活动冲突。命令均已在 2026-09-29 于 release `1.3.3-0b72499` 上验证存在。

## 4. 全局规则（所有阶段共同遵守）

1. **审批与收口由用户执行**：CHG 与 Decision 的批准、CHG 最终收口，Agent 只准备脚本（放在 `.auto-pm/reports/`，用户用 Git Bash 运行 `bash <路径>`），不代为批准、不以用户署名代签。Claude Code 的自动模式分类器已两次以“自我批准”拒绝，不得拆分或改写绕过。
2. **每个阶段结束向用户报告完成状态**，含：产出 SHA、门禁结果、控制面终态、遗留问题。
3. **先核验后断言**：涉及分支关系、命令是否存在、路径是否存在、计数的结论，必须由 git/数据库/命令输出支持，并标注“已验证”或“推断”。今天已因未核验而出错多次（M2 尖端、CHG 未关闭数、IC01 能力）。
4. **干净候选**：每个实施阶段用全新隔离工作树、固定 SHA 起点、精确 owned paths、正常 Hook、当前字节 Checkpoint；不得 rebase 或改写既有分支；不得复制主工作区脏文件。唯一例外是卡 025 明确授权的 WBS 单文件输入制品：其 Git 起点固定为 `58ac6a03a886832588e8adc6d81c16453ac8b25a`，输入字节必须绑定 SHA-256 与大小，导入前后逐字节一致，且不得携带任何第二条脏路径。
5. **失败保留历史**：失败尝试保留为历史，不回退、不改写；修复用有界纠正 Run。
6. **主工作区脏状态**是历史债务，不清理，只要不阻断推进；但候选必须从 Git 提交起步，不从脏状态复制。
7. **卡的机器可读格式**（见 027 §5.1）：本组卡的头部含 `隔离基线` 与 `路径根`，路径表含 `基线状态`（存在/计划新增/运行态）。后续阶段的 `隔离基线` 为占位符，前一阶段未回写前预检必失败。
7.1 **命令与路径预检**：每张卡执行前，先验证卡内 `main.py` 命令存在、引用的既有路径在声明基线上存在；这是对整改 D 的手工先行实践。
8. **Windows 注意**：Git Bash 中调用 Windows Python 时路径用 `cygpath -w`；PowerShell 5.1 不支持 `&&`；子进程设置 `PYTHONIOENCODING=utf-8`；完整回归约 30～45 分钟，须后台运行并监视。
9. 不使用 `pm-workflow`；不使用 `--no-verify`；不直接改数据库。
10. **执行角色与有界纠正**：GPT 为 M2 主实施者；Claude 为只读复查与异常接管者。每个原子任务最多一次主 Run 与一次不扩大 owned paths 的纠正 Run；第二次失败、需要扩大边界、额度异常或关键证据不完整时必须停止，不得继续形成补丁链。

## 5. 各阶段一句话摘要

- **025 WBS 修订 1**：在隔离候选里为 WBS 追加新修订章节：新原子任务、三线血统事实、开发运行时切换政策、H11 `COMPLETED / ACCEPTED`、署名与来源说明；不删除历史文字。
- **023 BL02**：三线（U04B、R1+Hook 修复、H11 发布线）整合成一个干净、不可变、可回退的基线候选，并用 canonical 数据库副本证明 M2 读取路径不会误拒新事件。
- **026 R1**：`adjudicate_blocked_work`（建议同强度覆盖 `fence_legacy_terminal_lease`）绑定 Git；`decision create --target-work-id` 与按 action 的互斥合同。
- **027 R2**：实施卡开工前预检（命令存在、路径存在或计划新增、基线漂移）并**强制接入 `continuity work create`**（写入型 Work 必须引用通过预检的卡，scope 不得超出卡的路径表）；定义卡的机器可读格式（头部 `隔离基线`/`路径根`，路径表 `基线状态` ∈ 存在/计划新增/运行态）。
- **028 部署**：一次集成开发运行时部署，仅在用户批准后执行。
- **029 WBS 修订 2 与交付**：写入最终证据、技术债登记并打包交付物；由 Claude 只读复查或用户验收后，GPT 继续 U05，不设置重复的 GPT 中途裁决门。

## 6. 已登记的技术债（随 029 正式入账；数字均为 2026-09-29 已核验）

1. 主工作区大量 CHG、台账、Decision、实施卡未提交（用户确认后期处理）。
2. SW-2026-008 未关闭 CHG 共 **73** 个：approved 38、implementing 16、pending_acceptance 14、draft 5；三项目合计 100 个（精确清单见摸底输出，029 需重新生成）。
3. Markdown 实施卡与结构化实施卡两套并存。**方案 C（以结构化卡为唯一真源、Markdown 卡由其渲染生成、预检与创建流程合并）为后续迭代**；本轮方案 B 只让 `continuity work create`（CLI）强制预检。
3.1 服务层与 Facade 直接调用 `WorkRegistryService.create_work` 的路径、以及 Mission 强授权派生的 Work，未被强制预检。
4. 仓库内缺少正式 release 构建命令，依赖一次性脚本。
5. H11 在较弱合同下执行（未绑定 Git HEAD），既有结果不回溯重验。
6. 旧 Hook 在 GBK 终端输出 emoji 触发 `UnicodeEncodeError`。
7. 主工作区 WBS 与隔离候选中的 WBS 分叉。
8. H 队列中仍有历史非终态 Run（A2 系列、G10、E01 等），不阻断 U05。
9. 119 个工作树中 41 个含独有提交、22 个有未提交改动；`AppData\Local\Temp\codex-pmf-g08-*` 独占 8077 个脏路径。可安全归档的清单尚未整理。
10. 稳定 release 目录（`8b02de5` 之后）未被 Git 跟踪，仅 `deployment_manifest.json` 被跟踪。
11. CHG-SCPT-2026-346 为失败历史（状态机禁止回退）。

## 7. 阶段 1 复查记录（Claude，只读，2026-09-29）

- 已验证：提交 `a385452c` 仅改 WBS 一个文件；版本 V3.0.16；V3.0.13～V3.0.15 保留；新增 BL02、ADJ、IC02、DEP1、WBS2 任务；署名与三线血统已写入；无 TODO 残留；候选工作树洁净；SYS-2026-001 台账 0/0/0。
- 偏差（待用户/GPT 确认）：
  1. ~~H11 写为 `COMPLETED / ACCEPTED`，与卡 025 原定不同~~ **更正（Claude，同日）**：本复查最初对照的是我记忆中的 V0.2；卡 025 已被修订为 V0.3，其中明确要求 H11 标记 `COMPLETED / ACCEPTED`，因此该提交在此点上**符合 V0.3，不是偏差**；
  2. 依赖图中“H11 不阻断 U04A，U04B 必须隔离历史投影”一句被删除，属轻微信息损失；
  3. 另有 9 行当前状态类文字被小幅编辑（版本行、M2 投影行、U05 行、H11 行、U01 段落、依赖图、当前产品状态段），未发现删除历史修订。
- 未验证：`doc check` 与基线的对照、Hook 输出原文、CHG-DOCU-2026-022 的收口是否由用户亲手执行。
- 复查方法局限（Claude 自陈）：本复查在读到 025/023 的 V0.3 之前完成，其中涉及“卡的要求”的判断应以 V0.3 重新核对；其余基于 git 提交内容的事实（提交/父提交/版本行/历史保留/新任务/台账）不受影响。
