# M3-ENVPORT｜新电脑一键可用实施卡（七个文件）

> 卡片编号：`CARD-SW008-M3-ENVPORT`
> 版本：`V1.0`（2026-10-16；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-17 转述咨询 Claude 的裁决并回答“可以”（先做补丁 10，再做存储接入卡，最后跨电脑共享状态）；2026-10-16 说“你的其他建议全部批准”；本卡 SHA 先在聊天报出再启动；条件见 §7）
> 档次：**核心档**（分档器：`requirements.txt` 与 `setup_env.bat` 不在已知规则内，按“未知路径按核心档复核”；不得降级）
> 依赖：上一张卡 RUN-SW008-M3-TD25-001 已达技术终态且 CHG-DOCU-2026-055 已收口（由启动脚本核验）
> 隔离基线：`c1c73bc0ccab65b8a617b95ca07665f70dfb4222`（上一张受治理卡的提交，本地分支 `codex/m3-td25-ledger`，是已推送线的尖端）
> 路径根：`.`
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-16 夜）

1. **为什么**：用户 2026-10-17 要求换电脑、换 agent 都能进行。项目 Claude 的审阅 05（`git grep` 实测，我已在开发树上核对补丁）指出：产品源码里没有写死的用户路径，真正挡住“新电脑一键可用”的是依赖——`setup_env.bat` 装的是根目录过时的 `requirements.txt`（缺 pydantic、copier、markdown，版本不锁），装完启动器会因缺包失败；另有 2 个脚本与 2 个测试写死了已失效的 `Desktop\My_Workspace` 路径，其中两个测试在别的电脑上永远被跳过。用户同意的顺序：先做这张小卡，再做 V04-R1 存储接入卡，最后跨电脑共享状态。**补丁里的启动器依赖探测（`launch.py` 及其测试）不在本卡**：演练时真实 pre-commit 钩子拒绝“不属于任何已登记项目的生产文件”（`00_Infrastructure/auto_pm/launcher/launch.py`），启动器属于部署路径，需另议。
2. **做什么**（7 个文件；全部事实在构建时读自 git 并断言）：
   - **`setup_env.bat`**：只接受 Python 3.12（锁定文件只覆盖 3.12），按 `requirements-lock-py312-win.txt` 以 `--no-deps` 精确安装并跑 `pip check`；已有 `.venv` 不是 3.12 时停下；
   - **根目录 `requirements.txt`**：不再列依赖，改为指向锁定文件与 `setup_env.bat`；
   - **`pyproject.toml`**：只改开发依赖的 4 行上限（与锁定版本对齐，`uv sync` 与 CI 用同一套规则）；
   - **2 个脚本与 2 个测试**：写死的 Desktop 路径改为相对路径；两个 vartable 测试此前在别的电脑上被跳过，之后在任何电脑上运行（rest 组预期 897 passed、13 skipped 变为 899 passed、11 skipped）。
3. **不做什么**：不碰产品源码 `auto_pm/`、启动器与部署清单、锁定文件与 `environment_record.json`、不改 `python_bridge` 的钉点（它钉在不在 GitHub 上的提交，另卡）、不改 `.devcontainer/` 与 `plc-tool-ci.yml`；不推送由本卡完成。
4. **为什么是核心档**：分档器不认识这个路径，按“未知路径按核心档复核”的规则声明为核心档，跑九组回归并要求与上一张卡的受治理输出逐项相同。
5. **本卡带来的、用户应当知道的事**：改动面小、不碰任何运行路径：只影响新电脑的一键安装与打包脚本，以及让两个原本被跳过的测试在本机运行（本机实测通过）。`setup_env.bat` 只在新电脑上运行，这里无法替你在第二台电脑上实跑，需你在那台电脑上验证一次。回退办法是还原这 7 个文件的提交。
6. **容忍规则**：沿用 M3-RACE 的同一条具名规则（事先声明）：rest 组里若恰有 r09 一个失败且同字节隔离重跑 3/3 通过则放行并记偏差；此前所有受治理卡均严格全绿（未使用）。
7. **演练事实（非治理，草稿工作树，不是正式证据）**：2026-10-17 在基线（卡 157 的提交）的临时工作树里跑了一遍本卡的快速门禁与判卷（原始输出在 `.auto-pm/reports/m3-envport/gates_rehearsal/`）：7 个文件各等于冻结字节且具备预期性质、两个 vartable 测试 16 个通过且 0 跳过、冒烟与导入测试、静态检查、9 个反例各被内容合同拒绝、7 个冻结文件各被接受、真实 pre-commit 钩子对暂存的 7 个文件退出 0；九组回归用合成输出（上一张受治理卡的输出，rest 组按期望调整为 899 passed、11 skipped）判卷，G1–G9 全 PASS，4 个反例变体判卷结果符合预期。演练中还发现：补丁里的启动器部分（`launch.py` 与其测试）被真实钩子拒绝（“暂存生产文件归属未知或不唯一”），因此本卡不含启动器。演练不是正式证据，正式 Run 完整重跑。

## 2. 单一目标与完成定义

冻结的 7 个文件的字节被提交，且九组回归与上一张卡的输出逐项相同；技术完成 = 全部门禁通过且提交字节等于冻结清单；变更单收口按用户委托在 G1～G9 全 PASS 且提交字节等于冻结清单后代为执行。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线分支仍在基线、冻结文件的基线 blob 等于冻结哈希。启动脚本有只读的 `--check-only`。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **机器负载**：启动前核对前台无游戏/启动器，近 10 秒 CPU 低；Windows 更新已由用户暂停至 2026-11-18。
4. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有续租成功。
5. **正式门禁期间不并发其他重任务**（TD-SW008-095）；整次运行预计约 1 小时 30 分钟。

## 4. 精确 Owned Paths（7）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/pyproject.toml` | 存在 | 开发依赖上限与锁定版本对齐：mypy <3、pytest <10、pytest-cov <8、ruff <0.17（只改这 4 行） |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/build_delivery.py` | 存在 | 写死的已失效 Desktop 路径改为 scripts/ 的上一级（项目根） |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/verify_m7_gui.py` | 存在 | 同上：写死的 Desktop 路径改为项目根 |
| 4 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/vartable/test_communications_parser.py` | 存在 | 真实 DJ-2026-005 样例路径改为相对工作区根（parents[6]），使该测试在任何电脑上不再被跳过 |
| 5 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/vartable/test_program_blocks_parser.py` | 存在 | 同上 |
| 6 | `requirements.txt` | 存在 | 根目录依赖清单迁移：不再列依赖（缺 pydantic、copier、markdown，且与 pyproject 矛盾），改为指向锁定文件与 setup_env.bat |
| 7 | `setup_env.bat` | 存在 | 新电脑一键安装：只接受 Python 3.12，按锁定文件 --no-deps 精确安装并跑 pip check；已有 .venv 不是 3.12 时停下并提示 |

出现第 8 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m3-envport/`、本卡文件、演练工作树与临时目录）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

最终 SHA-256；冻结文件的基线（`c1c73bc0` 上的）blob SHA-256 在 `envport_config.json` 与启动脚本里冻结。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/pyproject.toml` | 存在 | `4aefdf95812bcbfb2a816416325af282be6d7aa51c1dc78555d85c611366162d` |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/build_delivery.py` | 存在 | `99fe36975f19ce00561ffbd70c176a19b64290af98f1fb5e06a6eab95f7b2600` |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/verify_m7_gui.py` | 存在 | `44f8c6995025bfd3f13afe16977bd0921df88930df814b91719ea82f9a01a050` |
| 4 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/vartable/test_communications_parser.py` | 存在 | `989e1b07ae63da2885bfe4d538902d5db497f704b8fcff4aacb181e73546ec64` |
| 5 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/vartable/test_program_blocks_parser.py` | 存在 | `81fa774cf6d28acfcf6a575d4e43edc29f888aa6974d9e1d9d9a5f9bc455ab9f` |
| 6 | `requirements.txt` | 存在 | `e85cf8a1b5f969916986fb84b0209d04011ffaeeb6bded278373c87d34621415` |
| 7 | `setup_env.bat` | 存在 | `863f72eea8d0ad932fa9d872d01126b9cbd03cf7eff3a6f44dc8745362dffedb` |

### 5.2 冻结工具

工具与脚本在 `.auto-pm/reports/m3-envport/`；清单文件 `reference_manifest.json` 的 SHA-256 为 `9b38e775e45f0143d3c888070b08da83f982dc7bf7341138b48e102da6a06a05`。

| 工具 | SHA-256 |
|---|---|
| `adjust_counts.py` | `dfe7291e51ddc9d57c3abc9d792556a76a9f1d64c60cb616ea2889ddbf4e62ca` |
| `commit_msg.template.txt` | `7b53cb5dcdc5c17ba2ddc2f5347b30e1aa132d8c6bb913bb219bf7c8f5b6e740` |
| `envport_config.json` | `44340c84948d379cf59e5d40f29ef55389c4dd27ea4ca42d3c38445dad6acfa5` |
| `envport_gates.py` | `926d7270897fa1be8c9ad47fcc9841a65304421c58d82e2aa7580dd8541a1dfc` |
| `envport_gates_all.sh` | `f31ea580cc39bf6a62de0ec94b7b85ed9bb8aea4563e19e392d2caa1292bdaec` |
| `envport_lib.py` | `14f1a5e5fc327b272a9b20612c49b5478b4649a46a720f4d30e877f618867e08` |
| `gen_project.py` | `eac50737f52b35b23b3c9b23583ac819940a042f71109f9cc96ceaa435e06565` |
| `install_files.py` | `368e3ada8a4105a6072ca3d935bd6d67a98b1c6f88c62efdc062207f1d18ba10` |
| `run_g2.sh` | `6956748a33added47bde7bca81e837230d6e461e746f48da7a0770499cd578fc` |

## 6. 门禁矩阵

核心档。顺序：基线测量 → 安装冻结文件 → 快速门禁 → 九组回归（G2，十个输出）→ 瞬时竞态测试的三次隔离重跑（仅在其于组跑里失败时才被判卷采用）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份与健康测试 | HEAD 为基线、工作树干净、冻结文件为基线字节；夹具健康、冒烟、导入测试在基线与候选都全部通过且数目相同 |
| G2 | 九组回归（rest、application、plc、change、contracts、infrastructure、qml_debounce_alone、cli、qml、core） | 与上一张卡的受治理输出相比：失败集合为空、无 ERROR，各组通过数与 skip 数不变（本卡不加测试）。唯一容忍规则见 §1 第 6 条 |
| G3 | 内容合同 | 7 个文件各等于冻结字节且具备预期性质（setup_env.bat 的 3.12 检查、`--no-deps` 锁定安装与 `pip check`；requirements.txt 迁移；pyproject 上限对齐；两个脚本与两个测试里不再有 Desktop 路径）；两个 vartable 测试 16 个通过且 0 跳过；冒烟与导入测试通过；插件二进制 SHA-256 前后相同 |
| G4 | 静态 | `ruff check auto_pm tests` 干净；`mypy --platform win32 auto_pm` 干净；`git diff --check` 无问题 |
| G5 | 范围与字节 | 变更集恰为 7 个路径、字节等于 §5.1；HEAD 为基线；安装前工作树干净；无残留文件 |
| G6 | 产品字节不变 | `auto_pm`、`templates`、`tests`、`scripts` 四棵树与基线逐字节相同 |
| G7 | 隔离与钩子 | 真实 .git/hooks 前后字节相同；无遗留 python 进程；真实 pre-commit 钩子对暂存的 7 个文件退出 0（临时索引） |
| G8 | 负向对照与正例 | 9 个反例（脚本或测试里旧 Desktop 路径、旧 ruff 上限、旧安装命令、依赖重新列出、setup 接受别的 Python、CRLF、路径层数改动）各被内容合同拒绝；7 个冻结文件各被接受 |
| G9 | 最终范围与字节 | 全部门禁之后字节与变更集不变 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-17 转述咨询 Claude 的裁决并回答“可以”，2026-10-16 说“你的其他建议全部批准”（原话记入 `.auto-pm/reports/PREAUTH_M2_20261008.txt`）；**本卡 SHA 报给用户后，由用户在聊天中回复批准**才启动。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

0. 启动前核对本机负载：无游戏/启动器在前台，近 10 秒 CPU 占用低；有则等待，不启动。
1. 在聊天报告最终卡 SHA 与摘要，随即启动（预授权范围内）。
2. 创建 SW-2026-008 的 SCPT/OPT 变更单、匹配 Decision（`DEC-<当天>-M3ENVP01`）、Work `WORK-SW008-M3-ENVPORT-001`、Run `RUN-SW008-M3-ENVPORT-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认续租成功**）。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m3-envport`，分支 `codex/m3-envport`。
4. 安装冻结字节并完整重跑门禁（`envport_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；按委托收口变更单。

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败（§1 第 6 条那一条容忍规则之外）；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；插件缺失或版本不符；需要改这 7 个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；同一问题两次未解就通知用户（用户切 Opus 诊断）；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结文件与工具；演练原始输出（非治理）；正式独立门禁与证据；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；委托收口记录。

## 11. 限制与后续

提交在本地分支 `codex/m3-envport`。之后：推送并读 CI；台账与 WBS 回写（TD-SW008-144 的相应项偿还；启动器依赖探测另立一条债；`python_bridge` 钉点另卡）。
