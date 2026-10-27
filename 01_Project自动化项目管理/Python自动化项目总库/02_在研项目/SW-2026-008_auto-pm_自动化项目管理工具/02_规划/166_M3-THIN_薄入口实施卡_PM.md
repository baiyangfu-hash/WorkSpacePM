# M3-THIN｜薄入口实施卡（三个路径）

> 卡片编号：`CARD-SW008-M3-THIN`
> 版本：`V1.0`（2026-10-18；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-18 说“先出薄入口卡”；2026-10-17 对 `.trae/` 写权限“我签字”、“多agent是同一台电脑”；云端审阅 25～27 的薄入口设计；本卡 SHA 先在聊天报出再启动；条件见 §7）
> 档次：**核心档**（分档器：`.trae/rules/`、`.trae/skills/` 与 `.agents/skills.json` 都不在已知规则内，按“未知路径按核心档复核”；不得降级）
> 依赖：上一张卡 RUN-SYS001-M3-WBS29-002 已达技术终态且 CHG-DOCU-2026-053 已收口（由启动脚本核验）
> 隔离基线：`391ffc19c00968e5ebefe61aa2fee8eca12e8d75`（卡 165 V1.1 的提交，本地分支 `codex/m3-wbs29b-projection`（`main` 在 PR #8 的合并提交上与它字节一致））
> 路径根：`.`
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-16 夜）

1. **为什么**：用户 2026-10-17、2026-10-18 的裁决——多 agent 限同一台电脑，不同 IDE 里的 agent 经薄入口进入同一项目并互相接棒，Trae CN 首选、Codex 备选，`.trae/` 的写权限用户已签字（限薄入口文件）。2026-10-18 用户在 Trae CN 里实测：它的 Default 模式 agent 自己在终端执行命令，没有等用户点运行（`pm orient` 与 `pm inbox list` 当时因缺项目编号退出 1 和 2，是提示词的问题）。没有这个入口，每个新会话都要用户手抄口令与上下文（TD-SW008-067）。
2. **做什么**（三个路径，全部事实在构建时读自 git 并断言）：
   - **新规则** `.trae/rules/cockpit-entry.md`（常驻）与**新技能** `.trae/skills/cockpit-entry/SKILL.md`：入口只做“进门定位”。四步：用 `git rev-parse --git-dir --git-common-dir` 确认当前是控制根（两行相同才是；隔离工作树里两行不同，就停下）；确定项目编号（用户说了用用户的，没说就 `project list` 后问用户，**不硬编码任何编号**）；运行只读的 `pm orient <项目编号> --json`；用中文报告焦点、正在做的 Work/Run、下一步合法动作，`conflicts` 不为空就原文告诉用户并停下。没有已授权的 Work 之前只能用只读命令，新需求用 `pm inbox add` 入箱（唯一允许的写，不授权任何事）；要写代码或文档，必须有用户批准的卡，并转到 `fullstack-engineer` 或 `plc-electrical-engineer`；不使用已隔离的 `pm-workflow`；换 agent 的一条命令交接由 `M3-HANDOFF` 提供，在那之前不自己造口令。
   - **登记表** `.agents/skills.json`：在最前面加一条指向新技能，Codex 经注册表读到同一个技能（`AGENTS.md` 本身不改）。
2. **做什么**（3 个文件；全部事实在构建时读自 git 并断言）：

3. **不做什么**：不改 `AGENTS.md`、不改 `.trae/skills/README.md`（它仍把已隔离的 `pm-workflow` 列为推荐入口，已过时，另卡处理）、不改现有的 `project-rule.md`、`fullstack-engineer`、`plc-electrical-engineer` 与 `pm-workflow`、不改任何产品代码；不实现换 agent 命令（`M3-HANDOFF`）；不推送由本卡完成（走 PR）。
4. **为什么是核心档**：分档器不认识这个路径，按“未知路径按核心档复核”的规则声明为核心档，跑九组回归并要求与上一张卡的受治理输出逐项相同。
5. **本卡带来的、用户应当知道的事**：入口只含文字，不改任何运行路径；回退办法是还原这 3 个路径的提交。**两件事你应当知道**：（1）入口里的报告步骤会读到 `conflicts`。我 2026-10-18 实测 `pm orient` 对 SW-2026-008 返回 `MULTIPLE_ACTIVE_WORKS`：有 8 个历史 Work 停在 BLOCKED 或 READY（M2-F02、P1-AUDITFIX、TD3、V05B2、V05B3、PLUGIN-001、PLUGIN-003、V04D-001），它们是失败版本或被取代的卡遗留的，没有任何 Run 在跑。技能里已写明“BLOCKED 的是历史遗留”，但冲突标志仍在；要让入口干净，需要另一张只改运行态的处置卡，我会单独报批，这张卡不碰它们。（2）Trae CN 的 Default 模式不经确认就执行终端命令，所以入口规则写死“没有已授权 Work 之前只读”；真正的最后防线仍是提交钩子与租约，不是提示词。
6. **容忍规则**：沿用 M3-RACE 的同一条具名规则（事先声明）：rest 组里若恰有 r09 一个失败且同字节隔离重跑 3/3 通过则放行并记偏差；此前所有受治理卡均严格全绿（未使用）。
7. **演练事实（非治理，草稿工作树，不是正式证据）**：2026-10-18 在基线（卡 165 V1.1 的提交）的临时工作树里跑了一遍快速门禁与判卷（原始输出在 `.auto-pm/reports/m3-thin1/gates_rehearsal/`）：三个路径安装后恰等于冻结字节（登记表 155→214 字节，新规则 1280 字节，新技能 2975 字节，LF、无 BOM）；入口里命令的真实输出在安装前后逐字节相同且退出码 0（项目列表、`pm orient` 与 `pm inbox add` 与 `context resolve` 的帮助、`pm inbox list`、`pm orient <编号> --json` 的键集合含 `conflicts` 与 `next_legal_action`）；控制根判断（`git-dir` 等于 `git-common-dir`）在主工作区说“相同”、在隔离工作树说“不同”；冒烟与导入测试通过、静态检查干净；真实 pre-commit 钩子对暂存的 3 个路径（临时索引）退出 0；9 道门禁在合成输出集上全部通过；9 个反例各按预期原因被拒绝、3 个冻结文件被接受；四个负向判卷变体按预期处理。九组真实回归没有在演练里跑，由正式运行执行。

## 2. 单一目标与完成定义

冻结的 3 个文件的字节被提交，且九组回归与上一张卡的输出逐项相同；技术完成 = 全部门禁通过且提交字节等于冻结清单；变更单收口按用户委托在 G1～G9 全 PASS 且提交字节等于冻结清单后代为执行。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线分支仍在基线、冻结文件的基线 blob 等于冻结哈希。启动脚本有只读的 `--check-only`。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **机器负载**：启动前核对前台无游戏/启动器，近 10 秒 CPU 低；Windows 更新已由用户暂停至 2026-11-18。
4. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有续租成功。
5. **正式门禁期间不并发其他重任务**（TD-SW008-095）；整次运行预计约 2 小时 30 分钟。

## 4. 精确 Owned Paths（3）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `.agents/skills.json` | 存在 | 技能注册表：在最前面加一条 `../.trae/skills/cockpit-entry`（Codex 经注册表读到同一个技能；原有两条原样保留） |
| 2 | `.trae/rules/cockpit-entry.md` | 计划新增 | 新文件：Trae CN 的常驻规则（`alwaysApply: true`），6 条，只指路：先读技能、没有已授权 Work 只读、新需求入箱、写代码要卡、不用 `pm-workflow`、有冲突停下 |
| 3 | `.trae/skills/cockpit-entry/SKILL.md` | 计划新增 | 新文件：薄技能，进门四步（确认控制根、确定项目编号、`pm orient`、中文报告）、只读命令清单、入箱、要写时的门槛、换 agent、不要做的事 |

出现第 4 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m3-thin1/`、本卡文件、演练工作树与临时目录）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

最终 SHA-256；冻结文件的基线（`391ffc19` 上的）blob SHA-256 在 `thin1_config.json` 与启动脚本里冻结。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `.agents/skills.json` | 存在 | `f02925fac0a1abf89c85c833127f37c7e50b91cf503a89d263c516bdd191f457` |
| 2 | `.trae/rules/cockpit-entry.md` | 计划新增 | `b5f998ee858fe9da2e3499626eb7e8feb576bbcc40c75995dc8b1c968a393112` |
| 3 | `.trae/skills/cockpit-entry/SKILL.md` | 计划新增 | `0ee4917f4d32688bd296c4a9f2b1774264d18527cecffba68de9a70ed53ebc44` |

### 5.2 冻结工具

工具与脚本在 `.auto-pm/reports/m3-thin1/`；清单文件 `reference_manifest.json` 的 SHA-256 为 `82a1a37d0bdef7de81a10d9c493d5c6aa46b683e8a2d437f56ec605560d6199a`。

| 工具 | SHA-256 |
|---|---|
| `adjust_counts.py` | `3be71108779dd23bcc742186b5048c82e6a0c29de6998e80318d5587dcda595f` |
| `commit_msg.template.txt` | `33438abbd32344f9ec1f050bd6a50b9b489a356e18fa00cfd46e6a7ad0586708` |
| `gen_project.py` | `eac50737f52b35b23b3c9b23583ac819940a042f71109f9cc96ceaa435e06565` |
| `install_files.py` | `6aedee90c5e09232666de6288b65a37f0c39b185c0ae3209b03bceccd2b771fa` |
| `run_g2.sh` | `6956748a33added47bde7bca81e837230d6e461e746f48da7a0770499cd578fc` |
| `thin1_config.json` | `fc462069a9d93e134b7b163f046db86b8fe7fbfff4a2d207577323bb5e285080` |
| `thin1_gates.py` | `3e5642e819c5d33a97ff7cf3cf6886337cab819773e3db95c9923f5ffc95aeb9` |
| `thin1_gates_all.sh` | `f61b102453340a24036230037f71a0a33fd061c9dd560aa50f7f137912e878f0` |
| `thin1_lib.py` | `5ed8da5a3d6d8fe24e938bd957ecd861266eb9b9d19bc7f4fa789ccb8b912dbb` |

## 6. 门禁矩阵

核心档。顺序：基线测量 → 安装冻结文件 → 快速门禁 → 九组回归（G2，十个输出）→ 瞬时竞态测试的三次隔离重跑（仅在其于组跑里失败时才被判卷采用）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份与健康测试 | HEAD 为基线、工作树干净、冻结文件为基线字节；夹具健康、冒烟、导入测试在基线与候选都全部通过且数目相同 |
| G2 | 九组回归（rest、application、plc、change、contracts、infrastructure、qml_debounce_alone、cli、qml、core） | 与上一张卡的受治理输出相比：失败集合为空、无 ERROR，各组通过数与 skip 数不变（本卡不加测试）。唯一容忍规则见 §1 第 6 条 |
| G3 | 内容合同 | 三个路径各等于冻结字节且满足内容合同（LF、无 BOM、没有硬编码的项目编号、没有死链、不引用已隔离的 `pm-workflow`、规则常驻、登记表是原有两条加新的一条且每条都有 SKILL.md）；入口里命令的输出在安装前后相同且退出码 0（`pm orient <编号> --json` 的键集合含 `conflicts` 与 `next_legal_action`）；控制根判断在主工作区说相同、在隔离工作树说不同；冒烟与导入测试通过；插件二进制 SHA-256 前后相同 |
| G4 | 静态 | `ruff check auto_pm tests` 干净；`mypy --platform win32 auto_pm` 干净；`git diff --check` 无问题 |
| G5 | 范围与字节 | 变更集恰为 3 个路径、字节等于 §5.1；HEAD 为基线；安装前工作树干净；无残留文件 |
| G6 | 产品字节不变 | `auto_pm`、`templates`、`tests`、`scripts` 四棵树与基线逐字节相同 |
| G7 | 隔离与钩子 | 真实 .git/hooks 前后字节相同；无遗留 python 进程；真实 pre-commit 钩子对暂存的 3 个文件退出 0（临时索引） |
| G8 | 负向对照与正例 | 9 个反例（硬编码项目编号、死链、缺控制根判断、引用已隔离的技能、规则不常驻、丢掉登记表原有条目、登记表指向不存在的技能、CRLF、把 PM_SESSION 当授权来源）各按指定原因被内容合同拒绝；3 个冻结文件各被接受 |
| G9 | 最终范围与字节 | 全部门禁之后字节与变更集不变 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-18 说“先出薄入口卡”（原话记入 `.auto-pm/reports/PREAUTH_M2_20261008.txt` 末尾）；本卡内容验收不委托，须用户阅读后确认；**本卡 SHA 报给用户后，由用户在聊天中回复批准**才启动。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

0. 启动前核对本机负载：无游戏/启动器在前台，近 10 秒 CPU 占用低；有则等待，不启动。
1. 在聊天报告最终卡 SHA 与摘要，随即启动（预授权范围内）。
2. 创建 SW-2026-008 的 SCPT/OPT 变更单、匹配 Decision（`DEC-<当天>-M3THIN01`）、Work `WORK-SW008-M3-THIN-001`、Run `RUN-SW008-M3-THIN-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认续租成功**）。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m3-thin1`，分支 `codex/m3-thin-entry`。
4. 安装冻结字节并完整重跑门禁（`thin1_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；按委托收口变更单。

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败（§1 第 6 条那一条容忍规则之外）；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；插件缺失或版本不符；需要改这 3 个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；同一问题两次未解就通知用户（用户切 Opus 诊断）；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结文件与工具；演练原始输出（非治理）；正式独立门禁与证据；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；委托收口记录。

## 11. 限制与后续

提交在本地分支 `codex/m3-thin-entry`。之后：走 PR 同步到 main；用户在 Codex 里跑一次同样的只读提示词；`M3-HANDOFF`（换 agent 命令）与运态处置卡另行报批。
