# M2-GOV-CIBASE｜CI 基线刷新实施卡

> 卡片编号：`CARD-SW008-M2-CIBASE`
> 版本：`V1.0`（2026-10-11；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-11 说“先做CI基线小卡，做完再推送”，并已预授权当日排期、要求“替我收口验收”；本卡 SHA 先在聊天报出再启动；条件见 §7）
> 档次：**测试档**（规则文档 §3：只改测试目录下的一个数据文件；相关完整组 `rest`；不改任何产品或测试代码）
> 依赖：卡 105（M2-GOV-TD12）的 Run/Work 已达技术终态且 CHG-DOCU-2026-039 已收口（由启动脚本核验）
> 隔离基线：`741ed045123caf5357349c2e33a48cd7edc6dcdb`（卡 105 的提交，本地分支 `codex/m2-td12-flip`）
> 路径根：`.`
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-11）

1. **为什么**：Linux CI（卡 098）把 35 个已知失败登记在 `tests/tools/sw008_ci/baseline.linux.json`，其中 14 个属于类别 `Q01`（真实样例缺失）。卡 101 把样例入库之后，这 14 个测试在干净检出里通过。比较脚本 `compare_baseline.py` 的规则是“基线里的条目意外通过 = 判 FAIL（基线过期），而不是悄悄放过”，所以如果不刷新基线，推送之后触发的那次 CI 会判 FAIL。用户 2026-10-11 要求先做本卡再推送。
2. **做什么**（只改这一个数据文件）：去掉 `categories` 里的 `Q01`、`ids` 里的 14 个 Q01 id、`id_category` 里对应的 14 项；其余 21 个 id 与 `schema`、`platform`、`recorded_on`、`measured_on` 全部原样；新增 `refreshed_on` 与 `refresh_note` 两个字段（比较脚本只读 `ids`）。被去掉的 14 个 id：
   - `tests/vartable/test_autoshop_parser.py::TestAutoshopParserRealSample::test_autoshop_parse_real_sample_comment_extraction`
   - `tests/vartable/test_autoshop_parser.py::TestAutoshopParserRealSample::test_autoshop_parse_real_sample_data_types`
   - `tests/vartable/test_autoshop_parser.py::TestAutoshopParserRealSample::test_autoshop_parse_real_sample_entries_count`
   - `tests/vartable/test_autoshop_parser.py::TestAutoshopParserRealSample::test_autoshop_parse_real_sample_gbk`
   - `tests/vartable/test_autoshop_parser.py::TestAutoshopParserRealSample::test_autoshop_parse_real_sample_i_start`
   - `tests/vartable/test_autoshop_parser.py::TestAutoshopParserRealSample::test_autoshop_parse_real_sample_in_scope`
   - `tests/vartable/test_format_detector.py::TestDetectFormatRealSamples::test_detect_format_real_autoshop_sample_gbk`
   - `tests/vartable/test_format_detector.py::TestDetectFormatRealSamples::test_detect_format_real_work3_sample_utf16_le`
   - `tests/vartable/test_work3_parser.py::TestWork3ParserRealSample::test_work3_parse_real_sample_address_no_quotes`
   - `tests/vartable/test_work3_parser.py::TestWork3ParserRealSample::test_work3_parse_real_sample_data_types`
   - `tests/vartable/test_work3_parser.py::TestWork3ParserRealSample::test_work3_parse_real_sample_entries_count`
   - `tests/vartable/test_work3_parser.py::TestWork3ParserRealSample::test_work3_parse_real_sample_fb_name_metadata`
   - `tests/vartable/test_work3_parser.py::TestWork3ParserRealSample::test_work3_parse_real_sample_utf16_le`
   - `tests/vartable/test_work3_parser.py::TestWork3ParserRealSample::test_work3_parse_real_sample_var_input_scope`
3. **没有任何测试读这个文件**：它只被 CI 工作流的比较步骤读取；CI 的自检脚本（`selftest.py`）用临时基线，不读它。所以 rest 组结果应与卡 101 的受治理输出完全相同（1 failed / 854 passed / 13 skipped）。
4. **一个必须说明的局限**：这是对 Linux 行为的**预测**——14 个测试在 Linux 干净检出里是否确实通过，只有 CI 的下一次运行才能证明。如果 CI 报出新的失败，用其日志再校准（本卡之后的事）。基线原来的 `measured_on` 是云端容器（Python 3.13）的实测，CI 首次运行（Python 3.12，2026-10-10）与它一致（PASS_KNOWN_BASELINE）。
5. **检查**：独立检查脚本核对：文件字节等于冻结值、标准 JSON 格式（`indent=2`、末尾换行）；`ids` 恰为旧 `ids` 去掉 14 个 Q01；`id_category` 键与 `ids` 一致、引用的类别都存在、`Q01` 不再出现；其余顶层字段不变；无密钥格式的值。并**真实运行随仓库交付的 `compare_baseline.py`**：新的 21 个失败集合 → `PASS_KNOWN_BASELINE`（exit 0）；旧的 35 个集合 → `FAIL`；少一个 id → `FAIL`（过期）。8 个反例（byte_drift、secret_injected、crlf_flip、q01_id_left_in、non_q01_id_dropped、category_map_out_of_sync、q01_category_kept、measured_on_changed）各被对应断言拒绝。**它不证明 Linux 行为**，见上一条。
6. 我在隔离演练树上完整跑了一遍（非受治理执行，不能复用为正式门禁；输出在 `.auto-pm/reports/m2-cibase/gates_rehearsal/`）：G1–G9 全部 PASS，共用判卷脚本接受判卷文件；rest 组 `1 failed, 854 passed, 13 skipped`（23 分 37 秒），与卡 101 的受治理输出逐项相同；基线文件由 9997 字节减为 6829 字节，id 35 → 21；随仓库交付的 `compare_baseline.py` 的真实行为符合预期（新集合 PASS_KNOWN_BASELINE、旧 35 个集合 FAIL、少一个 id FAIL）；真实 `pre-commit` 钩子对暂存的该文件退出 0；8 个反例各被对应断言拒绝、冻结文件被接受。演练一次通过，没有需要修正的地方。
7. **不做什么**：不改任何测试、产品、工作流或比较脚本；不重测 Linux；不推送（推送是本卡之后的独立动作，按用户授权执行）。

## 2. 单一目标与完成定义

基线文件与卡 101 之后的事实一致。技术完成 = 全部门禁通过且提交字节等于冻结清单；变更单收口按用户委托在 G1～G9 全 PASS 且提交字节等于冻结清单后代为执行。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线分支仍在基线、基线文件的基线 blob 等于冻结哈希（`d97655404b71db5c47a0c42004be37614f5e8a19d13f0beeb5a6109533be9357`）、卡 105 的 Run/Work 为 SUCCEEDED/CLOSED、CHG-DOCU-2026-039 completed。启动脚本有只读的 `--check-only`。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有 `first renewal ok`。

## 4. 精确 Owned Paths（1）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/tools/sw008_ci/baseline.linux.json` | 存在 | Linux CI 的已知基线：去掉 `Q01` 类别与 14 个 id（余 21 个 id），其余字段原样，加刷新说明 |

出现第 2 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m2-cibase/`、本卡文件、演练工作树）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

最终 SHA-256；基线（`741ed045` 上的）blob SHA-256 为 `d97655404b71db5c47a0c42004be37614f5e8a19d13f0beeb5a6109533be9357`。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/tools/sw008_ci/baseline.linux.json` | 存在 | `c117fc973c3462dc372fc3a46d0cc8e0e0b5571987805af981d383455b622443` |

### 5.2 冻结工具

工具与脚本在 `.auto-pm/reports/m2-cibase/`；清单文件 `reference_manifest.json` 的 SHA-256 为 `8a92b1b9d066c999d40fc6123534f287945a94dd2265618e967e7cfee998f09e`。G2 的基线取卡 101 受治理执行的 rest 组真实输出（`.auto-pm/reports/m2-q01/gates/g2_candidate/rest.txt`，其 SHA-256 冻结在 `cibase_config.json`）。

| 工具 | SHA-256 |
|---|---|
| `cibase_config.json` | `356d47447307f2874406d9a926401a4eb7abc834899187f079d0de105f4ed77f` |
| `cibase_gates.py` | `23be8cdb25c66a0064b19ce1d3d3d6fe0f69c42968250bfd3cfe6837d5a5863d` |
| `cibase_gates_all.sh` | `91bdde4981c3f241838a8d383c526d59bc57eea316a4e028b628718839eff8c3` |
| `commit_msg.template.txt` | `0891cc0fe9f71a632363415e0f40a4a15d253e1845784ef7eca0b818d45bcdcd` |
| `install_files.py` | `876627305996f8dd37fc29b46cb6cd16dce3df56231b9228f2150ddcd085d6ca` |
| `run_g2.sh` | `10b906ffd3424a7f94faf4100f85ba1d32319e650a3e7d61aa9c08656872508a` |

## 6. 门禁矩阵

测试档。顺序：基线测量 → 安装冻结文件 → 快速门禁 → rest 组回归（G2）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 夹具健康、冒烟、导入测试 | 候选与基线完全相同（既存失败仅 TD-SW008-042 一个） |
| G2 | rest 组回归（含 tests/e2e、tests/vartable） | 与卡 101 的真实输出逐项相同：失败集合、通过数、skip 数相同，无 ERROR |
| G3 | 基线文件合同与比较脚本的真实行为 | 文件合同无问题（21 个 id、无 Q01、键一致、其余字段不变、标准格式）；`compare_baseline.py`：新集合 exit 0 且 PASS_KNOWN_BASELINE，旧 35 个集合 exit 1，少一个 id exit 1 |
| G4 | Git 语义 | 文件未被忽略；Git 存储的 blob 等于原始字节 |
| G5 | 范围与字节 | 变更集恰为 1 个路径、字节等于 §5.1；HEAD 为基线；安装前工作树干净 |
| G6 | 既有内容不变 | auto_pm 与 templates 树与基线逐字节相同；tests 树只差这一个文件 |
| G7 | 隔离与钩子 | 真实 .git/hooks 前后字节相同；无遗留 python 进程；真实 pre-commit 钩子对暂存的该文件退出 0（临时索引） |
| G8 | 负向对照（8 项反例与 1 个正例） | byte_drift、secret_injected、crlf_flip、q01_id_left_in、non_q01_id_dropped、category_map_out_of_sync、q01_category_kept、measured_on_changed 各被对应断言拒绝；冻结文件被接受 |
| G9 | 最终范围与字节 | 全部门禁之后字节与变更集不变 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-11 说“先做CI基线小卡，做完再推送”，并已预授权当日排期、要求“替我收口验收”（原话记入 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾）；**本卡 SHA 报给用户后，由用户在聊天中回复批准**才启动。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 在聊天报告最终卡 SHA 与摘要，随即启动（预授权范围内）。
2. 创建 SW-2026-008 SCPT/DEF 变更单、匹配 Decision（`DEC-<当天>-CIBASE01`）、Work `WORK-SW008-M2-CIBASE-001`、Run `RUN-SW008-M2-CIBASE-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认第一次续租成功**）；实际创建前验证未被占用。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m2-cibase`，分支 `codex/m2-cibase-refresh`。
4. 安装冻结字节并完整重跑门禁（`cibase_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；按委托收口变更单。

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；需要改这个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；不做任何真实模型调用。全量测试对机器负载敏感（TD-SW008-095，另见 TD-SW008-120）：正式门禁期间不并发其他重任务；若 G2 因 TD-SW008-120 的竞态测试失败，本卡**没有**容忍规则，按上条停下，由用户裁决。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结文件与工具；演练原始门禁（非治理）与真实钩子干跑；正式独立门禁与证据；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；委托收口记录。

## 11. 限制与后续

提交在本地分支 `codex/m2-cibase-refresh`（卡 105 的提交之上）。本卡之后按用户“做完再推送”的授权：重做只读核对、快进推送单分支（不带 tag、不推 main），然后读 CI 的结果并在需要时再校准基线。
