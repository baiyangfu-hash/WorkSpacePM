# M2-GOV-RTOOL｜工具链冻结实施卡

> 卡片编号：`CARD-SW008-M2-RTOOL`
> 版本：`V1.0`（2026-10-10；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-10 预授权当日排期，原话见 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾；条件见 §7）
> 档次：文档档（两个新增文件，不改 `pyproject.toml`、不改 `.venv`）
> 隔离基线：`5c157f7308de14a3fd96d760663b5782e6016cb8`（卡 091 的提交，本地分支 `codex/m2-rann-notes`）
> 路径根：`.`
> 治理任务基线：WBS V3.0.26；台账 TD-SW008-114（本卡的验收条件来自该条）
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-10）

1. **为什么**：`pyproject.toml` 的开发约束（ruff `>=0.5,<0.6`、mypy `>=1,<2`、pytest `>=8,<9`、pytest-cov `>=5,<6`）与实际环境不一致，且没有任何锁文件；运行依赖的 `.venv` 不在版本库里，换机器无法复现今天通过的结果。用户的要求是“新机器可复现当前稳定版本”，不是追逐最新版，也不是降级回旧约束。
2. **怎么做**：不动 `pyproject.toml`。新增两个文件：①**锁文件** `00_Infrastructure/auto_pm/environment/requirements-lock-py312-win.txt`——控制根 `.venv` 当前安装的 108 个包的精确版本（`pip freeze --all`，可编辑安装不在内）；②**环境记录** `00_Infrastructure/auto_pm/environment/environment_record.json`——解释器事实、`pyproject.toml` 声明约束与实际版本的对照、可编辑安装清单、验证方法与结果、已知局限。
3. **关键事实**（环境记录里的内容）：
   - 解释器：3.12.14；`.venv` 的 `pyvenv.cfg` 指向用户配置目录下 codex 运行时缓存里的解释器（仓库之外），且该工具会原地更新它（`pyvenv.cfg` 记 3.12.13，现为 3.12.14）——这是环境脆弱点，已写入记录；
   - 一个可编辑安装的包 `python_bridge`（来自 `WorkSpacePM` 仓库的 DJ-2026-009 项目子目录，固定在提交 `5feb8e93`）不在锁文件里，单独列出；
   - 声明与实际对照：

| 包 | 声明 | 实际 | 在声明内 |
|---|---|---|---|
| `commitizen` | `<4,>=3` | 3.31.0 | 是 |
| `copier` | `<10,>=9.7.1` | 9.17.1 | 是 |
| `faker` | `<31,>=30` | 30.10.0 | 是 |
| `mypy` | `<2,>=1` | 2.3.1 | **否** |
| `polyfactory` | `<3,>=2` | 2.22.5 | 是 |
| `pre-commit` | `<4,>=3` | 3.8.0 | 是 |
| `pytest` | `<9,>=8` | 9.1.1 | **否** |
| `pytest-cov` | `<6,>=5` | 7.1.0 | **否** |
| `pytest-datadir` | `<2,>=1` | 1.8.0 | 是 |
| `pytest-env` | `<2,>=1` | 1.7.0 | 是 |
| `pytest-qt` | `<5,>=4.4` | 4.5.0 | 是 |
| `pytest-xdist` | `<4,>=3` | 3.8.0 | 是 |
| `ruff` | `<0.6,>=0.5` | 0.16.4 | **否** |
| `safety` | `<4,>=3.2.9` | 3.8.1 | 是 |
| `toml-sort` | `<0.25,>=0.24.2` | 0.24.4 | 是 |
| `types-PyYAML` | `<7,>=6` | 6.0.12.20260815 | 是 |

4. **隔离环境验证**（演练已做，正式 Run 在门禁前再做一次并由检查器比对）：用同一解释器新建临时 venv，`pip install --no-deps` 精确安装锁文件，然后 `pip check`、导入关键模块、跑 7 个测试、对基线提交的导出做整包类型检查；结果：创建 ok、安装 ok、`pip check`：No broken requirements found.、版本与锁一致 ok、导入 ok、测试 7 passed、类型检查：Success: no issues found in 244 source files。
5. **检查**：独立检查器核对：锁文件与控制根 `.venv` 当前的 `pip freeze --all` 逐包相同；锁文件无可编辑安装、无重复、按名排序；记录里的锁哈希与包数、声明对照与重新计算相同；记录里的验证结果等于本次 Run 重新做的验证结果（含全部通过与锁哈希）；字节等于冻结值；8 个反例（lock_missing_package、lock_version_changed、editable_in_lock、record_lock_hash_wrong、declared_flag_flipped、verification_failed、verification_other_lock、byte_drift）各被对应断言拒绝。**它不证明这套版本就是你想要的**，这由你验收。
6. 我在隔离演练树上完整跑了一遍（非受治理执行，不能复用为正式门禁）：基线、安装、候选三步原始退出码均 0；G1–G9 全部 PASS；8 项反例全部被拒绝；`gate_verdict` SHA-256 `b137ea21ec1414610c1c501852c72c3b4e3d389e07cbb85328e2354b13767841`，`DONE` SHA-256 `a3dc79c3d31bec1ebfe961de4cfc2ca67762d065209af613dd5cd70e5b3f96a4`；证据目录 `.auto-pm/reports/m2-rtool/gates_rehearsal/`。
7. 不在本卡范围：修改 `pyproject.toml` 的版本范围（等你看完记录再决定，另立卡）；升级或降级任何包；改 `.venv`；推送、打 tag、处置任何债务或失败记录。

## 2. 单一目标与完成定义

把锁文件与环境记录提交到本地分支。技术完成 = 提交通过全部门禁、提交字节等于冻结清单；**验收 = 用户阅读环境记录后确认**，变更单收口不委托。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线、两个新增文件在基线里不存在、冻结副本字节等于配置、工具字节等于冻结清单、卡 091 的 Run/Work 已达技术终态。启动脚本有只读的 `--check-only`，预检只用它。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **续租**：先用绝对路径启动续租循环并确认日志里有 `first renewal ok`（隔离环境验证在门禁脚本里先跑，约几分钟）。

## 4. 精确 Owned Paths（2）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `00_Infrastructure/auto_pm/environment/environment_record.json` | 计划新增 | 新增：环境记录（解释器、声明与实际对照、验证结果、局限） |
| 2 | `00_Infrastructure/auto_pm/environment/requirements-lock-py312-win.txt` | 计划新增 | 新增：已验证环境的精确版本锁文件 |

出现第三条候选变更即停止。准备和证据落点（`.auto-pm/reports/m2-rtool/`、本卡文件、演练工作树）不是额外 owned paths。

## 5. 字节合同

1. 冻结文件清单（路径与 SHA-256）在 `.auto-pm/reports/m2-rtool/files_manifest.json`，SHA-256 为 `b9b90a8772c769baf8b05c545a889f46f58313d9769df54b898314c1a0d5bfac`；冻结副本在 `.auto-pm/reports/m2-rtool/proto/` 下同一相对路径，由 `prepare_rtool.py` 从控制根 `.venv`、基线 `pyproject.toml` 与隔离环境验证结果确定性生成。变更集恰为这两个新增文件。
2. 工具与配置的 manifest 已冻结，SHA-256 为 `2e9f33a913212b58acb00179f4e8eabeca7379d12b3565b0ffe55cf5072922d1`；实际运行由启动脚本逐文件核对。共享判卷器 SHA-256 为 `0fcbd53020b909b123f3819dcf0774d1f8d93dbc4354dcc5f3c1f72dd56f2188`。
3. 提交：只含冻结文件；父提交为基线；经正常钩子，绝不绕过；提交 blob 与 git 对冻结字节算出的 blob id 相同。
4. Checkpoint 在提交之前创建，证据里写明冻结清单的路径与 SHA-256。

冻结工具（`.auto-pm/reports/m2-rtool/`；运行器、安装器沿用卡 091 的已验收代码，仅改名；检查器的判断部分与隔离环境验证为本卡新写）：

| 工具 | SHA-256 |
|---|---|
| `rtool_runner.py` | `cbd06ac5bcccf8c86befa13869f30b97937156c3e2bdc28255a8ab6bb2cd4d15` |
| `rtool_check.py` | `c0396f5567a73a93493e4a56a31bf93f7e6055675acdfe5433b7e32ad818597a` |
| `rtool_verify.py` | `92516c7fbb3f6e32d7fee444f441994953d3edaa26030b9eb6eb564cc06a0370` |
| `install_candidate.py` | `94201f64f4c0ea34acfa5565e8370578a4aa826d3ba2b314c36e5603ee2de1df` |
| `prepare_rtool.py` | `58f51866a8fccfd056c8c1001424b8431048fbf512a01981de0a329fe1015a1c` |
| `rtool_config.json` | `4eeb18192b7612f9c714eb978381365e608717582ca2bbfb97c22bb3f8ca6569` |
| `files_manifest.json` | `b9b90a8772c769baf8b05c545a889f46f58313d9769df54b898314c1a0d5bfac` |

## 6. 门禁矩阵

在门禁之前先运行隔离环境验证（失败即停止，不进入门禁）。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份、工作树与初始 hook | HEAD 为基线、clean；新增文件不存在；真实 hook 指纹非空 |
| G2 | 基线文档检查 | 根入口 `main.py doc check` 显式传控制根与候选根，原始 exit 0 |
| G3 | 安装前治理台账 | `ledger reconcile` 对 SW-2026-008 与 SYS-2026-001 无 fix，exit 0 且 0/0/0 |
| G4 | 最终候选文档检查 | 同根入口，原始 exit 0；受检前后字节均等于冻结值 |
| G5 | 安装后治理台账 | 同只读对账，两个项目均 exit 0 且 0/0/0 |
| G6 | 环境记录语义 | §1.5 全部成立（含本次 Run 的隔离环境验证全部通过且锁哈希相同） |
| G7 | 真实 hook 保全 | 运行前后全部真实 hook 字节相同 |
| G8 | 轻量负向对照（8 项） | lock_missing_package、lock_version_changed、editable_in_lock、record_lock_hash_wrong、declared_flag_flipped、verification_failed、verification_other_lock、byte_drift，各由对应断言拒绝 |
| G9 | 最终范围与字节 | 实测变更恰为冻结文件、HEAD 仍基线、index 空；完整改动清单及前后 SHA 绑定 |

判卷另由冻结的 `m2-tools/verdict_check.py` 核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-10 预授权当日排期（原话见 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾）：卡 SHA 先在汇报里报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读环境记录后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

1. 创建独立 SW-2026-008 DOCU/OPT 变更单、匹配 Decision（`DEC-<当天>-RTOOLFRZ`）、Work `WORK-SW008-M2-RTOOL-001`、Run `RUN-SW008-M2-RTOOL-001`（租约不超过 3600 秒）。
2. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m2-rtool`，分支 `codex/m2-rtool-lock`。
3. 运行门禁脚本（`rtool_gates_all.sh`：先隔离环境验证，再基线、安装、候选与判卷）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob id。
4. 依法推进 Run/Work 技术终态，对账 0/0/0；**变更单停在“实施中”，等用户阅读后验收再收口。**

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease 或 hook 漂移；隔离环境验证失败；任何门禁失败；负向目标未命中；Checkpoint 不能绑定清单哈希；提交 Hook 拒绝；需要改清单之外的任何文件：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结工具、文件清单与冻结副本；隔离环境验证结果；演练原始门禁（非治理）；正式门禁、CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；用户阅读验收的记录。

## 11. 限制与后续

锁文件只钉版本，不钉哈希；隔离验证用的是同一解释器二进制，换解释器或换机器不在覆盖范围；`pyproject.toml` 的声明范围仍与实际不符（环境记录里逐项列出），怎么改（放宽范围、改成实际版本的兼容范围，或同时引入 uv 锁文件）等你看完记录再定，另立卡。提交在本地分支 `codex/m2-rtool-lock`，**不推送、不合并**。
