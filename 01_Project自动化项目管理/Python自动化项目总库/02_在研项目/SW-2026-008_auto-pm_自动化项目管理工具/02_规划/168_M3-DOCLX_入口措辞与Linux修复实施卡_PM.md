# M3-DOCLX｜入口措辞与 Linux 修复实施卡（合卡，十六个路径）

> 卡片编号：`CARD-SW008-M3-DOCLX`
> 版本：`V1.0`（2026-10-18；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-18 预授权自行收口推送与合并；本卡 SHA 先在线程里报出；重载门禁 21:00 以后跑；条件见 §7）
> 档次：**核心档**（`.trae/` 路径分档器不认识按核心档复核，且改了产品代码；不得降级）
> 依赖：上一张卡 RUN-SW008-M3-HANDOFF-001 已达技术终态且 CHG-SCPT-2026-432 已收口（由启动脚本核验）
> 隔离基线：`43b1088e0f40d43732a4d1180895293d4f5b78d9`（`main` 上 PR #11 的合并提交，本地分支 `codex/m3-main-43b1088`）
> 路径根：`.`
> 执行模型：Claude；两包改动由云端会话备卡，独立审计 32、33 由另外的云端会话做
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令；本卡只改它的描述与加一行隔离提示，正文不动）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-18）

1. **为什么**：PR #10 的独立审计指出薄入口三处措辞会把 agent 带偏（TD-SW008-153）：只读命令出错时会提示去跑会写文件的修复命令；在子文件夹里判断控制根会误判；“BLOCKED 都是历史遗留”在清理卡之后已过时。用户在 Trae CN 的技能列表里仍看到已隔离的 `pm-workflow` 被当作主入口。另外，云端会话把驾驶舱在 Linux 上跑通了：Linux CI 原有一批登记为“已知失败”的测试（含原 `M3-R01` 那条），根因是钩子没有执行位、Linux 镜像只有 python3、项目扫描只认本机分隔符、两处测试的平台假设。两包改动都由云端会话备卡、另外的云端会话独立审计通过（审计 32、33）。合成一张卡，九组门禁只跑一次。
2. **做什么**（16 个路径：1 个新文件、15 个修改；全部事实在构建时读自 git 并断言）：入口规则与技能的措辞；技能说明、根 README、PLC 联锁指南与 `pm-workflow` 技能描述标明隔离、第一入口是 `cockpit-entry`；两个产品文件的 Linux 修复与对应测试；Linux CI 已知失败基线清空；新的 Linux 安装脚本；台账与 WBS 短投影回写。两条审计的低严重度建议已一并落地（技能说明里 `find-skills` 未登记的说法、联锁指南里两处 PM_SESSION 标注已退役、`pm-workflow` 正文前加一行隔离提示）。
3. **不做什么**：不改 `AGENTS.md`、`.agents/skills.json`、规范库；不删、不搬 `pm-workflow` 目录，正文不动；不改 CI 工作流；不部署、不切换发布版本。
4. **为什么是核心档**：`.trae/` 路径分档器不认识，按“未知路径按核心档复核”；且改了产品代码（项目扫描与钩子安装）。
5. **你应当知道的事**：（1）Windows 上 Git 不记录执行位，Linux 安装脚本入库后没有执行位，Linux 上用 `bash setup_env.sh` 运行（登记 TD-SW008-154）。（2）执行位那条新测试只在 Linux 上跑，Windows 上按平台跳过；Linux 上由 CI 覆盖。（3）回退办法是还原本卡的提交。
6. **容忍规则**：沿用 M3-RACE 的同一条具名规则（事先声明）：rest 组里若恰有 r09 一个失败且同字节隔离重跑 3/3 通过则放行并记偏差。
7. **演练事实（非治理，临时工作树，不是正式证据）**：2026-10-18 在基线 `43b1088e` 的临时工作树里跑了两遍快速门禁与判卷（原始输出在 `.auto-pm/reports/m3-doclx1/gates_rehearsal/`）。第 1 遍 G3 的逐行合同把整篇重写的 `.trae/skills/README.md` 判为“保留行顺序变了”，这是合同对整篇重写的文件不适用；改为该文件不判行序（删除行集合与关键词照判）后重新冻结。第 2 遍：4 个改动的测试文件 84 条通过、1 条按平台跳过，`bash -n` 接受 Linux 安装脚本，`doc check` 与基线同退出码，8 份文档满足合同，`ruff` 与 `mypy` 全包干净，2 个代码变异与 2 个文档反例全部被抓住，真实 pre-commit 钩子对 16 个暂存文件退出 0；九组回归用合成输出判卷，G1–G9 全 PASS，4 个反例变体的判卷结果符合预期。演练不是正式证据，正式 Run 完整重跑。

## 2. 单一目标与完成定义

冻结的 16 个文件的字节被提交，九组回归只多出本卡的新测试；技术完成 = 全部门禁通过且提交字节等于冻结清单；变更单收口按用户委托在 G1～G9 全 PASS 且提交字节等于冻结清单后代为执行；之后开 PR，独立审计通过且 CI 全绿后由 Claude 按用户授权合并。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线分支仍在基线、15 个修改文件的基线 blob 等于冻结哈希、新文件在基线不存在。启动脚本有只读的 `--check-only`。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **机器负载**：启动前核对前台无游戏/启动器，近 10 秒 CPU 低；重载门禁只在 21:00（亚利桑那时间）以后跑。
4. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有续租成功。
5. **正式门禁期间不并发其他重任务**（TD-SW008-095）；整次运行预计约 2 小时 30 分钟到 3 小时。

## 4. 精确 Owned Paths（16）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `.trae/rules/cockpit-entry.md` | 存在 | 常驻规则：只读命令出错时不要照提示去跑会写文件的修复命令 |
| 2 | `.trae/skills/cockpit-entry/SKILL.md` | 存在 | 薄技能：控制根判断改用绝对路径（子文件夹不误判）；`context resolve --path` 识别项目；BLOCKED 原样报告；修复命令不在只读清单里 |
| 3 | `.trae/skills/README.md` | 存在 | 技能说明重写：`cockpit-entry` 是第一入口；`pm-workflow` 列入“已隔离，禁止使用”；删去 PM_SESSION 回写与旧启动脚本 |
| 4 | `.trae/skills/plc-electrical-engineer/refs/interlock-and-handoff-guide.md` | 存在 | PLC 联锁指南：`pm-workflow` 改为“PM 治理角色”；两处 PM_SESSION 标注已退役 |
| 5 | `.trae/skills/pm-workflow/SKILL.md` | 存在 | 隔离技能本身：描述改为“已隔离，禁止使用”，正文前加一行“以下仅作历史证据，不要执行”（正文不动） |
| 6 | `README.md` | 存在 | 根 README：框图与技能清单把 `cockpit-entry` 列为入口，`pm-workflow` 标为已隔离 |
| 7 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/project_scanner.py` | 存在 | 项目扫描：两种分隔符都统一为 `/`，Windows 写下的反斜杠路径在 Linux 上也能推断技术栈 |
| 8 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/ui/cli/git_hook.py` | 存在 | 安装的两个钩子：Linux 上只有 python3 时回退到 python3；安装后加执行位（POSIX 上 Git 会跳过没有执行位的钩子） |
| 9 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_git_hook.py` | 存在 | 新测试 2 条（执行位，只在 POSIX 上跑；python3 回退）；钩子测试的 shell 调用分平台 |
| 10 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_git_hook_plc_docs.py` | 存在 | 测试修正：接受文档的提交带上真实改动（Linux 上原来没有可提交的差异） |
| 11 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_project_scanner.py` | 存在 | 新测试 1 条：反斜杠路径 |
| 12 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_recovery.py` | 存在 | 测试修正：被终止进程的失败码在 Windows 是 NONZERO_EXIT、在 POSIX 是 TERMINATED |
| 13 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/tools/sw008_ci/baseline.linux.json` | 存在 | Linux CI 已知失败基线清空（原 M3-R01 的那条也在内） |
| 14 | `00_Infrastructure/auto_pm/environment/setup_env.sh` | 计划新增 | 新文件：Linux 安装脚本，对应 `setup_env.bat`（入库时没有执行位，见 TD-SW008-154） |
| 15 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/02_整改项/活动技术债台账.md` | 存在 | 台账回写：TD-SW008-153 已偿还；登记 154；§3 追加 CHG-SCPT-2026-432 |
| 16 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md` | 存在 | WBS 短投影回写 V4.0.2：卡 167 合并、本卡、演练时段、合并 main 的授权与 21:00 规则 |

出现第 17 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m3-doclx1/`、本卡文件、演练工作树与临时目录）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

最终 SHA-256；15 个修改文件的基线（`43b1088e` 上的）blob SHA-256 在 `doclx1_config.json` 与启动脚本里冻结。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `.trae/rules/cockpit-entry.md` | 存在 | `f69fd2dfa3c6b33fc6df70134361cd380e6cca517dd259748570a4f24864edea` |
| 2 | `.trae/skills/cockpit-entry/SKILL.md` | 存在 | `3cf2504e2467d065786de3901081a0879562967ca8052ccb629917b3fd09f8d8` |
| 3 | `.trae/skills/README.md` | 存在 | `a95227a06d662e67beae16dad5659be5c063fff102759e79ccb92633c9ce6ece` |
| 4 | `.trae/skills/plc-electrical-engineer/refs/interlock-and-handoff-guide.md` | 存在 | `046a4e34206c030cc2f96ba91a11fbdbc798da62f08fd9a25ecfa7ebd8ad7df7` |
| 5 | `.trae/skills/pm-workflow/SKILL.md` | 存在 | `66019ad1bef4f877ab22bb31114918b985ecc70acca899331501ff721b446b70` |
| 6 | `README.md` | 存在 | `c5255c176be67737021189c6bb2f1eb7d320dfbfae0d06b89cb0e090dd81fa3b` |
| 7 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/project_scanner.py` | 存在 | `04fd4815a91d858fd616a1159181379f93d4d7ff86cc9e4ae5d58aa1964f81bc` |
| 8 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/ui/cli/git_hook.py` | 存在 | `7e67ecd53da465c62cefe93499379fb7facffd5797e4533615665336bf421ddf` |
| 9 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_git_hook.py` | 存在 | `cd66955c95bdaa1d3f43e0b4462aeb23ba82c41ab4fb5e4d3f60c08177ef9006` |
| 10 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_git_hook_plc_docs.py` | 存在 | `55ea619336def9300395460450e2696e11037cbe690a44799c07fba816d81479` |
| 11 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_project_scanner.py` | 存在 | `c26c64f0e970b0178a00ad4366f21da3cffbbdd39fe309f4d57b56f7a2b2c5b5` |
| 12 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_recovery.py` | 存在 | `4cd859ced2c2d7bc25c6af07fd8b7a5bab5961ca9075fc262d2002e21c2cc5af` |
| 13 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/tools/sw008_ci/baseline.linux.json` | 存在 | `1e048f9530f060bd2784c71bfb54247394b14b4325f8c6c3d0cbef05d06ddae6` |
| 14 | `00_Infrastructure/auto_pm/environment/setup_env.sh` | 计划新增 | `917dd736be1abece0e8a7cebe237bb5a1487832d76cdb9f7ba2f90240f5fc5cd` |
| 15 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/02_整改项/活动技术债台账.md` | 存在 | `1ee59fb29c8e319bc8002c91d6db6b2c6b2d0bd5ccc8b97be7c7dfd08d28117f` |
| 16 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md` | 存在 | `0e737644140253690ac7a9c1f1e0da15dc6190247ad46f85f14e24eda06374cc` |

### 5.2 冻结工具

工具与脚本在 `.auto-pm/reports/m3-doclx1/`；清单文件 `reference_manifest.json` 的 SHA-256 为 `ddd90cc415447dbafeaeab358323d8a56cd1c9ebb0554d208be8b42d8bd8746e`。

| 工具 | SHA-256 |
|---|---|
| `adjust_counts.py` | `b0662948d52b927db2ba88232b20550616efeb572bdbd129472bb79cbee3ca1d` |
| `commit_msg.template.txt` | `da5317bbe4abebd437f1849c4ec9032ea42cb5c0a4dbd2cc2136eab8006875a9` |
| `doclx1_config.json` | `f6d8c1f9d87bd884af3f708a4e999ea1858d1f01edfe6667319a84dce9eba4b8` |
| `doclx1_gates.py` | `2a4ca048bbe8e6f1e883669332fe9064c2816ae6d648bb0f20941e4638364530` |
| `doclx1_gates_all.sh` | `07ee862008f7e02f8fabd0b2df6ff6dddbdb6a3d944ef42291c24c1aa3f8e161` |
| `gen_project.py` | `eac50737f52b35b23b3c9b23583ac819940a042f71109f9cc96ceaa435e06565` |
| `install_files.py` | `ea7f7b36ce39df58ad1498eea32f27ca2dc28a3a636bf1138d080c11805aabf4` |
| `run_g2.sh` | `6956748a33added47bde7bca81e837230d6e461e746f48da7a0770499cd578fc` |

## 6. 门禁矩阵

核心档。顺序：基线测量 → 安装冻结文件 → 快速门禁 → 九组回归（G2，十个输出）→ 瞬时竞态测试的三次隔离重跑（仅在其于组跑里失败时才被判卷采用）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份与健康测试 | HEAD 为基线、工作树干净、15 个修改文件为基线字节、新文件不存在；夹具健康、冒烟、导入测试在基线与候选都全部通过且数目相同 |
| G2 | 九组回归（rest、application、plc、change、contracts、infrastructure、qml_debounce_alone、cli、qml、core） | 与上一张卡（卡 167）的受治理输出相比：失败集合为空、无 ERROR，新增恰为 cli 通过 +1、跳过 +1（执行位测试只在 POSIX 上跑）、core +1，其余各组不变。唯一容忍规则见 §1 第 6 条 |
| G3 | 内容合同 | 4 个改动的测试文件 84 条通过、1 条按平台跳过；`bash -n` 接受新的 Linux 安装脚本；`doc check` 退出码与基线相同；8 份文档（6 份入口与隔离说明、台账、WBS）满足冻结的逐行合同；插件二进制前后相同 |
| G4 | 静态 | `ruff check auto_pm tests` 干净；`mypy --platform win32 auto_pm` 干净；`git diff --check` 无问题 |
| G5 | 范围与字节 | 变更集恰为 16 个路径、字节等于 §5.1；HEAD 为基线；安装前工作树干净；无残留文件 |
| G6 | 产品树只差冻结文件 | `auto_pm`、`templates`、`tests`、`scripts` 四棵树相对基线恰好只差本卡的 7 个产品与测试文件 |
| G7 | 隔离与钩子 | 真实 .git/hooks 前后字节相同；无遗留 python 进程；真实 pre-commit 钩子对暂存的 16 个文件退出 0（临时索引） |
| G8 | 真实变异与文档反例 | 2 个代码变异（项目扫描不统一反斜杠、commit-msg 钩子没有 python3 回退）各让指定测试失败并按字节还原；2 个文档反例（入口规则丢掉只读那句、WBS 丢掉一条无关的行）被逐行合同拒绝 |
| G9 | 最终范围与字节 | 全部门禁之后字节与变更集不变 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-18 在项目聊天里预授权“自行收口推送，其他按照你的经验来…你现在负责全局”，并授权 Claude 合并 main；`.trae/` 改动在独立审计 32 通过后落地，Linux 修复经独立审计 33；**本卡 SHA 在线程里报出后**于 21:00 以后启动。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | 按用户 2026-10-18 的预授权委托：G1～G9 全 PASS 且提交字节等于冻结清单后由 Claude 收口；独立审计通过且 CI 全绿后由 Claude 合并 |
| 审批人 | fubai |
| 执行模型 | Claude |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

0. 启动前核对本机负载；只在 21:00 以后启动。
1. 在线程里报告最终卡 SHA 与摘要，随即启动（预授权范围内）。
2. 创建 SW-2026-008 的 SCPT/OPT 变更单、匹配 Decision（`DEC-<当天>-M3DOCLX1`）、Work `WORK-SW008-M3-DOCLX-001`、Run `RUN-SW008-M3-DOCLX-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认续租成功**）。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m3-doclx1`，分支 `codex/m3-doclx`。
4. 安装冻结字节并完整重跑门禁（`doclx1_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；按委托收口变更单；推送 PR 分支并开 PR；独立审计由项目另开的云端会话做，通过且 CI 全绿后按用户授权合并。

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败（§1 第 7 条那一条容忍规则之外）；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；插件缺失或版本不符；需要改这 16 个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮；同一问题两次未解就通知用户；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结文件与工具；演练原始输出（非治理）；正式独立门禁与证据；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；委托收口记录；PR。

## 11. 限制与后续

提交在本地分支 `codex/m3-doclx`，之后推送为 PR 分支。之后：真实进程演练 `M3-DRILL`（10-19 上午）；D03 冻结。
