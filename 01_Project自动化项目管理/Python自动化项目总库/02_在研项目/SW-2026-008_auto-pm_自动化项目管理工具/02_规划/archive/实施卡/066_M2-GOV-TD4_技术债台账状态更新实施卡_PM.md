# M2-GOV-TD4｜技术债台账状态更新实施卡

> 卡片编号：`CARD-SW008-M2-TD4`
> 版本：`V1.0`（2026-10-08；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / NOT_AUTHORIZED`（用户已有条件预授权，见 §7；条件满足前不开工）
> 档次：文档档；只改三条既有债务行的状态与进展，不新增债务行，不处置历史失败对象
> 隔离基线：`4d0b33ac39e0653941dbae9e52e6b6b5e894de32`（V05-B3，CHG-SCPT-2026-389 completed）
> 路径根：`01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具`
> 治理任务基线：WBS V3.0.22，提交 `0b56b2f4de2b35effea7e100ab2c56bc1cec0bc7`；WBS SHA-256 `41469091baa836807b5d8913e5a0678a3e38f043253b008f72cd00e1bab522d6`
> 对应 WBS：TD4 无独立任务行；本卡只让台账状态跟上已验收的提交，不在本卡修改 WBS
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033，以及基线提交中的《M2 门禁分档与单卡规模规则》（文档档：不需要 pytest 全量）。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-08）

1. 台账维护规则 2：关联 CHG 状态改变时必须同步本表。V04-T（提交 `715713bb`，CHG-SCPT-2026-388 completed）与 V05-B3（提交 `4d0b33ac`，CHG-SCPT-2026-389 completed）已验收，但台账里 TD-SW008-081、091、092 仍写“待执行”、关联 CHG 仍是“待立”。
2. 基线台账原字节 SHA-256 为 `78c20df206e3255fab77a0783c2e04119740460feed19271fa468e338c190223`（即 TD3R 提交后的字节，编号最高 094）。本卡只改 081、091、092 三行，其余全部原字节不变。
3. **逐条核对了各行自己的验收条件**（不是看卡名就改）：
   - 081（测试漏检）：条件四项——修正前提与准确拒因、断言租约完整值不变、进程探测分存活/已退出/未知三态且查询失败不当作已退出、真实失败变异。已在基线源码中核对：`tests/e2e/test_pmf_handoff.py` 的 q05 断言整条租约不变；`tests/e2e/test_pmf_recovery.py` 含三态探测与对应测试；变异由 V04-T 的 G8 门禁杀死。四项均满足，依据提交 `715713bb`。
   - 091（关闭后最终验收仍先写入）：条件——关闭后用真实可验收的 Mission 证明不改 Mission、Work、Run、事件、不排队收尾，去掉检查的变异被点名断言抓住。`tests/qml/test_pm_cockpit_closing_guards.py` 的第一个测试正是如此（关闭与窗口销毁两条路径），变异由 V05-B3 的 G8 门禁杀死。满足，依据提交 `4d0b33ac`。
   - 092（启动任务迟到信号）：条件要求对启动、收尾、批准、快照、证据五类 worker 分别证明“有未完成项、有界等待、迟到信号静默”。V05-B3 只证明了启动类（迟到结果丢弃、关闭时停启动计时器），快照类由 V05-B2 覆盖；收尾、批准、证据三类没有各自的证明。**不满足，所以不写已偿还**：状态由“待执行”改“活动”（已确认、未满足验收条件），关联 CHG 写 CHG-SCPT-2026-389，事实证据末尾写明已做与未做。
4. 状态定义（台账 §1）：已偿还要求关联 CHG 的实现、专项验证、回归、台账和 PM 收口均完成；两个关联 CHG 均为 completed，G1–G9 与 Checkpoint 绑定均已核验。GPT 对这两张卡的独立审计仍在排队；若审计发现问题，另行用新卡改回，不在本卡处理。
5. 我在隔离演练树上完整跑了一遍（2026-10-08，非受治理执行，不能复用为正式门禁）：基线、安装、候选三步原始退出码均 0；G1–G9 全部 PASS；16 项内存负向对照都改变了目标输入并被指定断言拒绝；共用判卷器退出 0；`gate_verdict` SHA-256 `0e5dffa05db29272a758e4f9c40a0ce2ae42a86699aa4189e58dd041498070a5`，`DONE` SHA-256 `33d3a0774c23d79b4780feba6f4a32ff3321ba6d02217388c44eb4924069eb10`；证据目录 `.auto-pm/reports/m2-td4/gates_rehearsal/`。
6. 不在本卡范围（需用户另行批准）：新增债务行（例如判卷器 `verdict_check.py` 不在 Git、负载下偶发失败的 Git/子进程类测试、机器上残留的 fsmonitor 与 node 进程）；处置 CHG-381、CHG-386、CHG-DOCU-2026-018、CHG-SCPT-2026-389 首次失败对象等历史失败记录；TD-SW008-086、089 的状态。

## 2. 单一目标与完成定义

让台账三条既有债务行与已验收事实一致；只修改一个文件，产品、测试、模板均零改动。

| 编号 | 改动 | 依据提交 | 关联 CHG | 新状态 |
|---|---|---|---|---|
| TD-SW008-081 | 事实证据末尾追加处置说明；关联 CHG 由“待立”改为 CHG-SCPT-2026-388 | `715713bb` | CHG-SCPT-2026-388 | 已偿还 |
| TD-SW008-091 | 事实证据末尾追加处置说明；关联 CHG 改为 CHG-SCPT-2026-389 | `4d0b33ac` | CHG-SCPT-2026-389 | 已偿还 |
| TD-SW008-092 | 事实证据末尾追加“部分处置”和未满足项；关联 CHG 改为 CHG-SCPT-2026-389 | `4d0b33ac` | CHG-SCPT-2026-389 | 活动 |

每行的编号、问题、负责人、优先级、验收条件、后续 WBS 六列一字不改；事实证据只许追加（旧内容是新内容的前缀）。

## 3. 实施前预检

1. 核对卡字节与已向用户报告的 SHA 一致、基线、WBS、唯一 owned path 及最终字节。没有这些，不创建 CHG/Decision/Work/Run。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空；预检仅读，不代表获批。
3. 核对前置 CHG-SCPT-2026-389 completed；核对失败记录（CHG-381、386、018 及其 Work/Run/Decision）仍在原状态且本卡不触碰。
4. 正式执行显式选择本卡新 Work/Run，不借用任何旧授权；新候选 HEAD 等于基线且 clean、index 为空、基线台账 SHA 一致；WBS 源 Git 字节与 SHA 一致；工具、配置、负向计划及原始证据引用均匹配冻结指纹。

## 4. 精确 Owned Paths（1）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `04_监控/02_整改项/活动技术债台账.md` | 存在 | 只改 TD-SW008-081、091、092 三行；其余原字节不变 |

出现第二条候选变更即停止。准备和证据落点（`.auto-pm/reports/m2-td4/`、本卡文件、演练工作树）不是额外产品 owned paths，不进本卡产品提交。CHG/Decision/Work/Run 等治理对象只在批准条件满足后通过根 CLI 落账，不直接写数据库。

## 5. 字节合同

唯一最终文件 SHA-256：`4087a8e010fb6f330a12ba309369ffde55b15cf47c8ab6f3378766a7e86995e6`。UTF-8、LF、无 BOM。冻结的最终台账与三行文本保存在 `.auto-pm/reports/m2-td4/`（`proto/`、`updated_rows.md`）；安装器只在明确安装阶段核对基线后写入，判卷器不得调用安装或生成。

1. 除三行外全部基线原字节不变；三行中编号、问题、负责人、优先级、验收条件、后续 WBS 不变，事实证据只追加，关联 CHG 与状态等于 §2。
2. 状态取值只能是已偿还、活动、待执行之一；写已偿还的行，其关联 CHG 的变更状态必须为 completed 或 closed（判卷器从受控根读取该变更单）；每行的依据提交必须出现在追加文字中，且是候选 HEAD 的祖先（git 自己判定）。
3. 追加文字里反引号包围的文件引用必须真实存在：仓库内文件在候选树中存在，`.auto-pm/` 下的证据文件匹配冻结 SHA。
4. 验证只读，负向对照仅修改内存中的输入；每个样本必须改变目标输入并被对应目标断言拒绝。
5. 工具与配置的 manifest 已冻结，SHA-256 为 `f7512b5de46856c0ace34560364af8d2c5a13bc60648f9ecc9a3e4e9d12091df`；实际运行必须由外部传入该期望值。共享判卷器 SHA-256 为 `0fcbd53020b909b123f3819dcf0774d1f8d93dbc4354dcc5f3c1f72dd56f2188`。
6. 门禁前后逐一记录最终文件 SHA，全部相同且等于本卡。无门禁跨 Run 复用。

冻结工具（`.auto-pm/reports/m2-td4/`；运行器与安装器沿用 TD3R 已演练代码，仅改名；判卷器是为本卡新写的，因为 TD3R 的判卷器规定“旧行一律不许改”）：

| 工具 | SHA-256 |
|---|---|
| `td4_runner.py` | `1338df429d965b9f235ccb32ea2148e1348e4a503a082a22b409d42de52d056b` |
| `td4_check.py` | `72be65031d5f9a62caea4b46ee2bfd8794beafbf13d3af864a2d6b3953c27d7c` |
| `install_candidate.py` | `cfea35059577e7a625bb53a9af0dfb297c1bd3afefee509ec70103698f4d30c3` |
| `prepare_td4.py` | `0b3cec046f760b3e655665b26f5e30a91c5c1f0d1a39848345c3720b7fa581c9` |
| `td4_config.json` | `01962a694b71e70c22a45dcff9db21b8a0fad896ec91178be57cdd6067aaf637` |
| `updated_rows.md` | `6998607e14cfefa8192b434e7646eeda7a4f552693d177df8b4c9afe27705c10` |
| `base_ledger.md` | `78c20df206e3255fab77a0783c2e04119740460feed19271fa468e338c190223` |

## 6. 门禁矩阵

顺序：基线测量 → 显式安装 → 最终候选测量和判卷。任一非零或环境异常立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份、工作树与初始 hook | HEAD 为基线、clean、index 空，台账为原字节；真实 hook 指纹非空 |
| G2 | 基线文档检查 | 根入口 `main.py doc check` 显式传控制根与候选根，原始 exit 0 |
| G3 | 安装前治理台账 | 根入口 `main.py ledger reconcile SW-2026-008`，无 fix，exit 0 且 0/0/0 |
| G4 | 最终候选文档检查 | 同根入口，原始 exit 0；受检前后字节均等于冻结值 |
| G5 | 安装后治理台账 | 同只读对账，原始 exit 0 且 0/0/0 |
| G6 | 台账语义、三行外字节、关联 CHG、依据提交、引用 | §5 全部成立 |
| G7 | 真实 hook 保全 | 运行前后全部真实 hook 字节相同 |
| G8 | 轻量负向对照（16 项） | modify_other_row、delete_row、revert_one_update、change_priority、change_acceptance、replace_evidence、illegal_status、overclaim_repaid、repaid_with_open_chg、chg_unbound、basis_missing、not_ancestor、dead_reference、out_of_scope、tampered_bytes、crlf，各由对应断言拒绝 |
| G9 | 最终范围、HEAD、index、diff | 实测变更仅唯一 owned 文件、HEAD 仍基线、index 空、无未跟踪残留；完整 diff 及前后 SHA 绑定 |

判卷另由冻结的 `m2-tools/verdict_check.py` 核对完整 G1–G9、card/base/run、报告映射及文件 SHA；空集合、缺报告、错误身份均拒绝。越界负向是变更路径清单输入的内存测试，不宣称已完成物理 Git 越界集成测试；测量器输出 `is_governed_evidence=false`，正式外层须由 Checkpoint 绑定测量。测量与安装分离，任何 STOP 禁止再次运行该证据目录。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户的有条件预授权（原话 `.auto-pm/reports/PREAUTH_M2_20261007.txt`）：卡 SHA 已先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径；任一不满足则不开工 |
| 最终验收 | 已委托：G1–G9 全部通过且提交与 Checkpoint 一致时由 claude-sonnet-5-5 代为验收并收口 CHG；用户可复核并推翻 |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。外部回执绑定卡 SHA、工具 manifest SHA、基线/WBS、owned 与最终文件 SHA、允许禁止动作、审批人与真实时间。卡、基线、范围或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 向用户在聊天报告最终卡 SHA 与三行改动摘要。
2. 创建独立 SW-2026-008 DOCU/OPT 变更单、匹配 Decision（`DEC-<当天>-TD4DOCS0`）、Work `WORK-SW008-M2-TD4-001`、Run `RUN-SW008-M2-TD4-001`（租约不超过 3600 秒）；实际创建前验证未被占用，不复用幂等键或旧 token。
3. 从代码基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m2-td4`，分支 `codex/m2-td4-docs`，绑定精确 owned、owner 与 lease。
4. 安装最终字节并完整重跑门禁（`td4_gates_all.sh`）；测量报告本身不能替代治理授权或 Checkpoint。
5. 先创建当前字节 Checkpoint，再正常 Hook 提交唯一 owned 文件，绝不 no-verify。核对提交父、范围及 blob 与 Checkpoint 完全一致。
6. 依法推进 Run/Work 技术终态，对账 0/0/0；条件满足后代为验收并收口 CHG。

## 9. 硬停止

基线、工具/卡/Decision 指纹、owner/scope、lease 或 hook 漂移；新增范围；任何门禁失败；负向目标未命中；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；需要变更三行以外的台账内容、新增债务行、CHG、WBS、产品、模板、Obsidian 或安全设置：均停止，保留现场，不靠重跑、改字节或放宽判据变绿；不处置任何历史失败对象。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结工具、台账与三行；演练原始门禁（非治理）；批准条件满足后的独立正式门禁、CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；代验收记录；GPT 对提交的独立审计。

## 11. 限制与后续

本卡只让三行状态与已验收事实一致，不修任何代码、不新增债务、不处置失败记录。“已偿还”依据的是各行自己的验收条件逐项核对和两张卡的受治理门禁；GPT 的独立审计尚未回来，若审计推翻，用新卡改回。092 的余下部分（收尾、批准、证据三类 worker 的关闭语义证明）仍待后续测试补卡，建议值，未排期。无合并、推送、部署或 release 切换授权。
