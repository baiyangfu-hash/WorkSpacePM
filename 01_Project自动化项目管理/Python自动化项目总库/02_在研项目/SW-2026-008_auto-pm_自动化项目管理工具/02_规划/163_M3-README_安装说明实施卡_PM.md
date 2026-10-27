# M3-README｜README 安装说明实施卡（一个文件）

> 卡片编号：`CARD-SW008-M3-README`
> 版本：`V1.0`（2026-10-16；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-17 说“先做 README 小卡，并行做 HYG-MIN；结束后有序停止，我有问题和你讨论”；2026-10-16 说“你的其他建议全部批准”；本卡 SHA 先在聊天报出再启动；条件见 §7）
> 档次：**核心档**（分档器：`README.md` 不在已知规则内，按“未知路径按核心档复核”；不得降级）
> 依赖：上一张卡 RUN-SW008-M3-TD26-001 已达技术终态且 CHG-DOCU-2026-056 已收口（由启动脚本核验）
> 隔离基线：`d9b582f791c443878c9b8885303902052619b42e`（上一张受治理卡的提交，本地分支 `codex/m3-td26-ledger`）
> 路径根：`.`
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-16 夜）

1. **为什么**：TD-SW008-151。卡 158 把根目录 `requirements.txt` 改成只指向锁定文件后，根目录 `README.md` 的安装说明没有同步：仍写“脚本检测 Python 3.11+”，并让 Linux/macOS 用户执行 `pip install -r requirements.txt`，结果得到一个空环境。评审机器人在 PR #3 指出（P1，只影响非 Windows）；用户 2026-10-17 说“先做 README 小卡，并行做 HYG-MIN；结束后有序停止”。
2. **做什么**（1 个文件；全部事实在构建时读自 git 并断言）：
   - **`README.md`** 的“一键安装”段落只改两处文字：Windows 向导说明改为只接受 Python 3.12、已有 `.venv` 不是 3.12 时停下不删除、按锁定文件以 `--no-deps` 精确安装并运行 `pip check`；Linux/macOS 命令改为 `python3.12 -m venv .venv`、安装锁定文件、`pip check`，并注明锁定文件冻结于 Windows 与 Python 3.12、CI 在 Linux 安装同一份、其他系统与版本没有完整验证。
3. **不做什么**：不改 `setup_env.bat`（其错误级别问题是 TD-SW008-150，另卡）、不改 `requirements.txt` 与锁定文件、不改 README 的其他任何一行；不推送由本卡完成（走 PR）。
4. **为什么是核心档**：分档器不认识这个路径，按“未知路径按核心档复核”的规则声明为核心档，跑九组回归并要求与上一张卡的受治理输出逐项相同。
5. **本卡带来的、用户应当知道的事**：只改一个文档文件里的两处安装说明，不碰任何运行路径。回退办法是还原这 1 个文件的提交。
6. **容忍规则**：沿用 M3-RACE 的同一条具名规则（事先声明）：rest 组里若恰有 r09 一个失败且同字节隔离重跑 3/3 通过则放行并记偏差；此前所有受治理卡均严格全绿（未使用）。
7. **演练事实（非治理，草稿工作树，不是正式证据）**：2026-10-17 在基线（卡 162 的提交）的临时工作树里跑了一遍快速门禁与判卷（原始输出在 `.auto-pm/reports/m3-readme1/gates_rehearsal/`）：README.md 安装后恰等于冻结字节（6593 字节变 7151 字节，LF、无 BOM）；`spec check`、`spec lint`、`spec frontmatter` 在安装前后输出与退出码逐字节相同；冒烟与导入测试通过、静态检查干净；真实 pre-commit 钩子对暂存的 1 个文件（临时索引）退出 0；9 道门禁在合成输出集上全部通过；5 个变异（旧 Python 说法、旧 Linux 命令、缺 `pip check`、别处改动、CRLF）各被内容合同拒绝，冻结文件被接受；四个负向判卷变体（核心组数目变化、rest 一个失败、rest 暂态重跑失败）按预期拒绝，rest 暂态容忍变体按预期放行。九组真实回归没有在演练里跑，由正式运行执行。

## 2. 单一目标与完成定义

冻结的 1 个文件的字节被提交，且九组回归与上一张卡的输出逐项相同；技术完成 = 全部门禁通过且提交字节等于冻结清单；变更单收口按用户委托在 G1～G9 全 PASS 且提交字节等于冻结清单后代为执行。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线分支仍在基线、冻结文件的基线 blob 等于冻结哈希。启动脚本有只读的 `--check-only`。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **机器负载**：启动前核对前台无游戏/启动器，近 10 秒 CPU 低；Windows 更新已由用户暂停至 2026-11-18。
4. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有续租成功。
5. **正式门禁期间不并发其他重任务**（TD-SW008-095）；整次运行预计约 1 小时 30 分钟。

## 4. 精确 Owned Paths（1）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `README.md` | 存在 | 安装说明两处文字：Windows 向导说明改为 Python 3.12、按锁定文件 `--no-deps` 安装并 `pip check`；Linux/macOS 命令改为安装锁定文件（根目录 `requirements.txt` 已不再列依赖） |

出现第 2 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m3-readme1/`、本卡文件、演练工作树与临时目录）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

最终 SHA-256；冻结文件的基线（`d9b582f7` 上的）blob SHA-256 在 `readme1_config.json` 与启动脚本里冻结。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `README.md` | 存在 | `eb85bad883aba5df57c40bbd8cf21b28aee2e43a676c3949c0e2a775ff367a2f` |

### 5.2 冻结工具

工具与脚本在 `.auto-pm/reports/m3-readme1/`；清单文件 `reference_manifest.json` 的 SHA-256 为 `4a2d6b39bddebfa6fd58655e1ba4fd54483be53b08825ff5ea44d88f016e60ac`。

| 工具 | SHA-256 |
|---|---|
| `adjust_counts.py` | `3be71108779dd23bcc742186b5048c82e6a0c29de6998e80318d5587dcda595f` |
| `commit_msg.template.txt` | `b1c6ab3ddfc43ad214c1d2c395bd71180b7041de27b09daabf986388dfb65067` |
| `gen_project.py` | `eac50737f52b35b23b3c9b23583ac819940a042f71109f9cc96ceaa435e06565` |
| `install_files.py` | `afe2d03cce239ffa80e5155f8a0e8a7652aa09c8440a7dfec733894d51fcd745` |
| `readme1_config.json` | `0006356dbc1127ef35dccb97674933f62fabfb0f0b570a17fa89399af26d56af` |
| `readme1_gates.py` | `d5e184fc864b9a59c821102fa02a910dc48c13e4d2c63d3784d5046a41a3de6b` |
| `readme1_gates_all.sh` | `f7c5a7441a74ba882c2c91f28d308240fa6c89bdd8dc7ebdcf71d1756716c9fc` |
| `readme1_lib.py` | `542363b9ac30ba811ade92d45827a507261faa8bccc183f3cef203abc8eae091` |
| `run_g2.sh` | `6956748a33added47bde7bca81e837230d6e461e746f48da7a0770499cd578fc` |

## 6. 门禁矩阵

核心档。顺序：基线测量 → 安装冻结文件 → 快速门禁 → 九组回归（G2，十个输出）→ 瞬时竞态测试的三次隔离重跑（仅在其于组跑里失败时才被判卷采用）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份与健康测试 | HEAD 为基线、工作树干净、冻结文件为基线字节；夹具健康、冒烟、导入测试在基线与候选都全部通过且数目相同 |
| G2 | 九组回归（rest、application、plc、change、contracts、infrastructure、qml_debounce_alone、cli、qml、core） | 与上一张卡的受治理输出相比：失败集合为空、无 ERROR，各组通过数与 skip 数不变（本卡不加测试）。唯一容忍规则见 §1 第 6 条 |
| G3 | 内容合同 | README.md 恰等于基线字节加两处冻结替换（LF、无 BOM）；旧说法（Python 3.11+、`pip install -r requirements.txt`）消失，新说法（Python 3.12、`--no-deps`、`pip check`、锁定文件名）出现；`spec check`、`spec lint`、`spec frontmatter` 在安装前后输出与退出码逐字节相同；冒烟与导入测试通过；插件二进制 SHA-256 前后相同 |
| G4 | 静态 | `ruff check auto_pm tests` 干净；`mypy --platform win32 auto_pm` 干净；`git diff --check` 无问题 |
| G5 | 范围与字节 | 变更集恰为 1 个路径、字节等于 §5.1；HEAD 为基线；安装前工作树干净；无残留文件 |
| G6 | 产品字节不变 | `auto_pm`、`templates`、`tests`、`scripts` 四棵树与基线逐字节相同 |
| G7 | 隔离与钩子 | 真实 .git/hooks 前后字节相同；无遗留 python 进程；真实 pre-commit 钩子对暂存的 1 个文件退出 0（临时索引） |
| G8 | 负向对照与正例 | 5 个反例（旧 Python 说法回来、旧 Linux 命令回来、缺 `pip check`、别处被改、CRLF 注入）各被内容合同拒绝；冻结文件被接受 |
| G9 | 最终范围与字节 | 全部门禁之后字节与变更集不变 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-17 说“先做 README 小卡，并行做 HYG-MIN；结束后有序停止”，2026-10-16 说“你的其他建议全部批准”（原话记入 `.auto-pm/reports/PREAUTH_M2_20261008.txt`）；**本卡 SHA 报给用户后，由用户在聊天中回复批准**才启动。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

0. 启动前核对本机负载：无游戏/启动器在前台，近 10 秒 CPU 占用低；有则等待，不启动。
1. 在聊天报告最终卡 SHA 与摘要，随即启动（预授权范围内）。
2. 创建 SW-2026-008 的 SCPT/OPT 变更单、匹配 Decision（`DEC-<当天>-M3READ01`）、Work `WORK-SW008-M3-README-001`、Run `RUN-SW008-M3-README-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认续租成功**）。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m3-readme1`，分支 `codex/m3-readme-install`。
4. 安装冻结字节并完整重跑门禁（`readme1_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；按委托收口变更单。

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败（§1 第 6 条那一条容忍规则之外）；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；插件缺失或版本不符；需要改这 1 个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；同一问题两次未解就通知用户（用户切 Opus 诊断）；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结文件与工具；演练原始输出（非治理）；正式独立门禁与证据；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；委托收口记录。

## 11. 限制与后续

提交在本地分支 `codex/m3-readme-install`。之后：走 PR 同步到 main；TD-SW008-151 偿还并回写台账。
