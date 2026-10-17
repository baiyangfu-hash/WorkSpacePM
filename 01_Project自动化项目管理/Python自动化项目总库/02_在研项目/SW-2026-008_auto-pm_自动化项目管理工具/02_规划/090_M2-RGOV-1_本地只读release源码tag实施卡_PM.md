# M2-RGOV-1｜本地只读 release 源码 tag 实施卡

> 卡片编号：`CARD-SW008-M2-RTAG`
> 版本：`V1.0`（2026-10-10；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-10 预授权当日排期，原话见 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾；条件见 §7）
> 档次：文档档（本地引用写入，成果是两个新增输出文件，不改仓库里的任何已有文件）
> 隔离基线：`6e2508425a1efcd13f643a9eed7d85a9faf40748`（卡 089 的提交，本地分支 `codex/m2-td9-docs`）；操作对象是控制根仓库的 `refs/tags/release-src/*`
> 路径根：`.`
> 治理任务基线：WBS V3.0.26；台账 TD-SW008-109、111（本卡的验收条件来自这些条目）
> 执行模型：`claude-sonnet-5-5`；结果由用户读后验收
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-10）

1. **为什么**：`deployment_manifest.json` 登记了 15 个 release；盘点卡 087 查实其中 6 个的源码提交不在任何远端分支上（3 个只剩本机 reflog 与游离的工作树 HEAD），清理工作树就会丢；另有 1 个的登记值写错。载荷本身不必入库：盘点重建结果显示 12 个 release 能从源码提交重建出与载荷逐文件相同的内容。所以保住**源码提交**就保住了发布来源。
2. **做什么**：为每个已登记的 release 在其源码提交上创建一个**本地带注释 tag** `release-src/<release-id>`（共 15 个，下表）；tag 说明里写明登记值、重建比对与校验结果。`1.2.4-6699a5b` 的登记值 `6699a5b746d0…` 不存在，按 release 编号后缀唯一对应的存在对象 `6699a5b831d9…` 更正（该对象在远端分支上，提交说明是“重命名台帐…”，时间 2026-09-07，与该 release 的部署日一致）。
3. **不做什么**：不推送任何东西（包括 tag；仓库公开，推送另行授权）；不移动任何已有 tag；不改任何分支、manifest、指针、载荷与文件。
4. **检查**：独立检查器核对每个 tag 存在、类型为带注释 tag、指向冻结清单里的提交；运行前后指纹相比只多出预期的 15 个 `release-src/*` tag，分支、远端跟踪引用、其他 tag、跟踪改动、未跟踪文件与发布指针逐字节不变；报告数字等于 tag 文件；8 个反例（wrong_target、missing_tag、unexpected_new_tag、other_ref_moved、lightweight_tag、report_mismatch、readonly_changed、tag_moved）各被对应断言拒绝。**它不证明冻结清单里的提交就是该 release 的真源码**（来自 manifest 与盘点；一处更正已在上面说明）。
5. 我在一次性本地克隆上完整演练了一遍（非受治理执行，不能复用为正式证据）：创建 15 个 tag、检查器退出 0、8 个反例全部被拒绝；演练输出与检查结果在 `.auto-pm/reports/m2-rtag/rehearsal/`。真实仓库在演练前后没有 `release-src/*` tag。
6. 不在本卡范围：推送 tag、入库任何文件、标注旧 release、改 manifest、转私有、处置任何债务或失败记录。

### 冻结的 tag → 提交清单

| tag | 提交 | 来源 | 从源码重建与载荷对比（卡 087） |
|---|---|---|---|
| `release-src/1.2.3-d41eb38` | `d41eb38c773c0b5f175b3231cb6c30f4c90b60aa` | 登记值 | identical |
| `release-src/1.2.3-813105c` | `813105c3238aa21d506fc8d16a22a293735e033a` | 登记值 | different |
| `release-src/1.2.3-f950525` | `f95052537392eae53143e20a5b5e1a9a3d271f11` | 登记值 | identical |
| `release-src/1.2.4-6699a5b` | `6699a5b831d9df6bc11800a5f3a320fd6b5ec82d` | 更正：登记值不存在 | n/a |
| `release-src/1.3.0-5345f40` | `5345f403d96e7a13a9eba2ed73d32502f8cb5dc8` | 登记值 | identical |
| `release-src/1.3.1-a7dae04` | `a7dae04a64e9eb5d91bba67ee3769651a100545c` | 登记值 | identical |
| `release-src/1.3.2-9d3c920` | `9d3c92057a5dcdadbf1f1f693030ef9bc3c102a3` | 登记值 | identical |
| `release-src/1.3.3-d8f7c8b` | `d8f7c8b84b1bcffb68d079f108ffe182b0e1db27` | 登记值 | different |
| `release-src/1.3.3-8b02de5` | `8b02de55f011df31591601464e0eebf4db5e4f23` | 登记值 | identical |
| `release-src/1.3.3-f462694` | `f46269475542d8407416fbec84c1b0b0b4542804` | 登记值 | identical |
| `release-src/1.3.3-8f08c1a` | `8f08c1a59fb43bd156586d8afeec43af96edabdb` | 登记值 | identical |
| `release-src/1.3.3-e648e0b` | `e648e0b4a07adadae418a7bbf7bfb60494666b5c` | 登记值 | identical |
| `release-src/1.3.3-0b72499` | `0b7249972a51b64a9e78e98213f37d38263d2502` | 登记值 | identical |
| `release-src/1.3.3-a808fa8` | `a808fa8a43335ceb5705d7384d2afbb0a12e412c` | 登记值 | identical |
| `release-src/1.3.3-4b5c630` | `4b5c6307e814cd6bf17337f31ccd8c7e533553e1` | 登记值 | identical |

## 2. 单一目标与完成定义

创建 15 个本地 tag 并让检查器全过、只读证明成立。技术完成 = Run SUCCEEDED、Work CLOSED；**验收 = 用户阅读 tag 报告后确认**，变更单收口不委托。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线、两个输出路径均不存在、工具字节等于冻结清单、卡 089 的 Run/Work 已达技术终态。启动脚本有只读的 `--check-only`，预检只用它。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **续租**：先用绝对路径启动续租循环并确认日志里有 `first renewal ok`。

## 4. 精确 Owned Paths（2）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `.auto-pm/reports/m2-rtag/out/RTAG_REPORT.md` | 计划新增 | 新增：tag 报告（人读） |
| 2 | `.auto-pm/reports/m2-rtag/out/tags.json` | 计划新增 | 新增：15 个 tag 的对象、提交与类型（机读） |

另有 15 个本地 tag（引用，不是文件）受 Decision 条件约束，名称与指向见 §1。出现第三条候选变更或清单之外的任何引用变化即停止。准备和证据落点（`.auto-pm/reports/m2-rtag/` 下的工具、快照、门禁证据、演练输出）不是额外 owned paths。

## 5. 字节合同

1. 变更集恰为这两个新增文件与 15 个预期 tag；其余仓库字节、引用、release 载荷与指针不变（运行前后指纹相比只多出预期 tag）。
2. 工具的 manifest 已冻结，SHA-256 为 `30829315ef592b7bfb5c8e0bb2ad771c4292003636d4c472fa121d7ecd2df7c2`；实际运行由启动脚本逐文件核对。
3. tag 为带注释 tag，名称 `release-src/<release-id>`，指向 §1 清单里的提交。

冻结工具（`.auto-pm/reports/m2-rtag/`）：

| 工具 | SHA-256 |
|---|---|
| `build_rtag.py` | `39d4832c4f8b2450223ce39b568066d7d7ef065a04289a833eb195c79209a687` |
| `prepare_rtag.py` | `2caf4c1b1a3e3228a522e196b1d491a9fe438c4b48fd9642de18f9d0662ec83d` |
| `rtag_apply.py` | `1df82e9b316406b79f8c50d6babd17071d9ed6d5bcdc8c4f4bbd101930aed8df` |
| `rtag_card.py` | `4dee31206f82bebf8af0ebcd1d5ee478300d4e034866b4898adc48538be54bc0` |
| `rtag_check.py` | `1c38522ecf48fcf7e9331707f8f0a83d8db842f7cb127f8491ea90107c34f37a` |
| `rtag_config.json` | `50bbb6021db18622667640e670dede72a74ac0ade8b8b8ecbce408f958bc5874` |
| `rtag_snapshot.py` | `ebff7870bf182013271dfa9fb2208023c3fb640392f0cf244f62e62d2b2aab82` |

## 6. 门禁矩阵

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| R1 | 前置 | 卡字节、工具字节、卡 089 终态、输出文件不存在 |
| R2 | 指纹 | 运行前后相比只多出预期的 15 个 tag |
| R3 | 检查器 | 退出 0，`assertions_failed` 为空 |
| R4 | 反例（8 项） | wrong_target、missing_tag、unexpected_new_tag、other_ref_moved、lightweight_tag、report_mismatch、readonly_changed、tag_moved，各由对应断言拒绝 |
| R5 | 治理终态 | Run SUCCEEDED、Work CLOSED、台账对账 0/0/0；变更单停在实施中 |

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-10 预授权当日排期（原话见 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾）：卡 SHA 先在汇报里报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读 tag 报告后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 创建独立 SW-2026-008 DOCU/OPT 变更单、匹配 Decision（`DEC-<当天>-RTAGLOCL`）、Work `WORK-SW008-M2-RTAG-001`、Run `RUN-SW008-M2-RTAG-001`（控制根，无工作树，租约不超过 3600 秒）；启动脚本取运行前指纹。
2. 运行 `rtag_2_run.sh`（创建 tag，一次）；运行 `rtag_3_close.sh`（运行后指纹、检查器、Run/Work 终态）。
3. **变更单停在“实施中”，等用户阅读后验收再收口。**

## 9. 硬停止

卡/工具指纹漂移；输出文件已存在；已有 tag 指向别处；运行前后指纹出现预期之外的变化；检查器任一断言失败；lease 失败；需要写任何 owned 之外的文件或推送：均停止，保留现场，不靠重跑或放宽判据变绿。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；不做任何真实模型调用。

## 10. 交付物

卡与预检；冻结工具与 tag 清单；演练输出（非治理）；两个输出文件；运行前后指纹、检查器结果与反例、证据哈希、验收回执；用户阅读验收的记录。

## 11. 限制与后续

本卡只在本机创建 tag。tag 只保住“源码提交的名字”，**不会让它们到达远端**：推送另行授权，且仓库公开（TD-SW008-112、116），推送前要用盘点卡 087 的扫描结论逐次确认；转私有等待办做完再说（用户 2026-10-10）。
