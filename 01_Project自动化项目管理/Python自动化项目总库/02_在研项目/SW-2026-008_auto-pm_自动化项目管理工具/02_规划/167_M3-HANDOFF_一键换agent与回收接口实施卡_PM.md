# M3-HANDOFF｜一键换 agent 与回收接口实施卡（合卡，十五个路径）

> 卡片编号：`CARD-SW008-M3-HANDOFF`
> 版本：`V1.0`（2026-10-18；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-18 回复“合卡”并预授权自行收口推送；本卡 SHA 先在线程里报出再启动；条件见 §7）
> 档次：**核心档**（连续性存储、服务与命令行都是核心文件；不得降级）
> 依赖：上一张卡 RUN-SW008-M3-THIN-001 已达技术终态且 CHG-SCPT-2026-430 已收口（由启动脚本核验）
> 隔离基线：`ea024f27642c055818b80d6d8bbbfae3410251da`（`main` 上 PR #10 的合并提交，本地分支 `codex/m3-main-ea024f27`）
> 路径根：`.`
> 执行模型：Claude；独立审计由项目另开的云端会话做
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-18）

1. **为什么**：M3 要求同一台电脑上不同 IDE 的 agent 能接棒，执行进程被杀后别的 agent 能安全接手（真实进程演练与 D08 的前提）。今天项目管理层没有换 agent 的入口，用户只能手工走底层命令并自己搬口令（TD-SW008-063）；多数命令把口令放在命令行参数里，会留在进程列表与 shell 历史（TD-SW008-064）；V04-R1 的回收接口没有实现，断电后没有合法办法接手（存储验收用例 1、3，用户 2026-10-17 回答“都要、接受风险只能用户本人签、宽限期 120 秒”）。用户 2026-10-18 回复“合卡”，把 `M3-HANDOFF` 与 `M3-V04R1E` 合成一张卡，九组门禁只跑一次。
2. **做什么**（15 个路径：9 个新文件、6 个修改；全部事实在构建时读自 git 并断言）：
   - **一条命令换 agent**（下文新命令都省去根入口前缀：它们要到部署后才进入根入口，机器预检按当前发布版核对命令）：当前持有者运行 `pm handoff --run-id <Run> --to <接手方>`，命令记检查点并生成发给接手方的交接；接手方运行 `pm takeover --handoff-id <交接> --as <自己>`，先只读定位（`pm orient` 同一份查询，定位失败就不接手），再用自己生成的口令接手，口令写进本机钱包 `.auto-pm/cache/lease-wallet/`（被 Git 忽略）；之后的写命令加 `--lease-wallet`，用户与 agent 都不经手口令。旧持有者的口令随接手失效。
   - **口令来源**：`run start`、`run transition`、`run settle-expired`、`dispatch prepare`、`checkpoint create`、`handoff create`、`handoff accept` 都可用 `--lease-token-env` 一类的环境变量选项（读后即清除），能定位 Run 的命令还可用 `--lease-wallet`；旧的命令行口令选项保留并标弃用，交互终端里打印弃用警告（脚本与测试的输出不变）。
   - **回收接口**：`continuity run reclaim --run-id <Run> --claimant <接手方> --reason <原因>`。租约还有效（含 120 秒宽限）时拒绝并写明还要等多久；租约失效且原持有者记录的进程已证明消失（进程不在、或 pid 已被别的进程占用）时接手，lease version 加一即新 epoch，事件里记下由谁、因为什么回收；原持有者进程仍在时拒绝；无法判断（没有记录进程、读不到进程表、别的主机）时为 PENDING，什么都不写，出路是用户本人在自己的交互终端运行 `pm sign-risk --run-id <Run> --claimant <接手方>`，输入 Run 编号与“接受风险”四个字；签字绑定接手方、持有者、epoch 与租约版本，任一变化即失效。agent 会话（带 `CLAUDECODE`、`CODEX_SANDBOX`、`AUTO_PM_AGENT` 等标记）与非交互会话一律不能签。存储在写入事务里再判一遍租约失效、持有者与版本未变、签字仍有效，所以“判定之后有人续租或移交”抢不进来。持有者进程由 `run start --lease-wallet`、`pm takeover` 自动记录（调用命令的 shell 或 IDE），也可用 `continuity lease record-holder --holder-pid <pid>` 记录续租循环一类的长驻进程。
   - **用例 1**：同一张卡已有 Run 时，第二个 agent 被拒，提示写明谁持有、租约到几点（本机时间）、该怎么办；被拒的申请不留下任何东西；两个 agent 同一瞬间申请只有一个成功（存储事务内判，已有）。旧持有者带旧口令或旧 epoch 来写，被拒并写明当前持有者。
   - **TD-SW008-065 最小子集**：按用户 2026-10-10 的书面裁决接受单用户本机信任模型，规则写入 WBS 短投影 §5 第 7 条；测试证明数据库与钱包都被 Git 忽略。改存哈希不做。
   - **回写**：台账（TD-SW008-063、064、065、067 已偿还，登记 152、153，§3 追加 CHG-SCPT-2026-430、431）与 WBS 短投影 V4.0.1（卡 166、清理卡与本卡，Codex 挂起，§5 第 7、8 条）。按“零张独立记账卡”的规则，回写是本卡的最后一部分，分档取最高一档。
3. **不做什么**：不改表结构、不改事件哈希链、不改既有的移交与 settle-expired 语义；不做“强制回收活租约”（不在用例里）；不做编排器微任务仓库的中途换执行器（登记为 TD-SW008-152）；不改 `.trae/` 入口文字（措辞问题登记为 TD-SW008-153，另一张文档卡做）；不部署、不切换发布版本——命令要到 D06/D07 部署后才在根入口生效，在那之前根入口仍是 `1.3.3-4b5c630`。
4. **为什么是核心档**：连续性存储、服务与命令行都是分档器的核心文件，跑九组回归并要求与上一张卡的受治理输出逐项相同（只多出新测试）。
5. **你应当知道的事**：（1）“只有用户本人能签”在单用户本机上是程序上的护栏，不是密码学保证：agent 能读控制根的一切，规则禁止它签，命令拒绝 agent 会话与非交互会话，测试证明这几条都生效；这与 TD-SW008-065 的信任模型一致。（2）Windows 上能读到进程的启动时间与命令行，所以“进程还在”判得出来；进程被杀后判“已消失”。（3）回退办法是还原本卡的提交；本卡没有数据迁移，旧的命令写法照常可用。
6. **旧测试的影响**：两处报错信息加了持有者与到期时间，前缀不变，既有测试用前缀匹配，不受影响（构建时已检索）。
7. **容忍规则**：沿用 M3-RACE 的同一条具名规则（事先声明）：rest 组里若恰有 r09 一个失败且同字节隔离重跑 3/3 通过则放行并记偏差。
8. **演练事实（非治理，临时工作树，不是正式证据）**：2026-10-18 在基线 `ea024f27` 的临时工作树里跑了两遍快速门禁与判卷（原始输出在 `.auto-pm/reports/m3-handoff1/gates_rehearsal/`）。第 1 遍 G4 的 `git diff --check` 抓到台账 4 行列错位（多出一列、行尾空格），改正后重新冻结；第 2 遍：58 个新测试全过且无跳过、新入口可导入、`doc check` 与基线同退出码、两份文档满足逐行合同、`ruff` 与 `mypy` 全包干净、13 个真实变异全部被抓住并按字节还原、真实 pre-commit 钩子对 15 个暂存文件退出 0；九组回归用合成输出判卷，G1–G9 全 PASS，4 个反例变体的判卷结果符合预期。演练不是正式证据，正式 Run 完整重跑。

## 2. 单一目标与完成定义

冻结的 15 个文件的字节被提交，九组回归只多出本卡的新测试；技术完成 = 全部门禁通过且提交字节等于冻结清单；变更单收口按用户委托在 G1～G9 全 PASS 且提交字节等于冻结清单后代为执行；之后开 PR，由用户在网页上合并。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线分支仍在基线、6 个修改文件的基线 blob 等于冻结哈希、9 个新文件在基线不存在。启动脚本有只读的 `--check-only`。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **机器负载**：启动前核对前台无游戏/启动器，近 10 秒 CPU 低；用户还在用这台电脑，跑重载门禁前先在线程里告诉用户。
4. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有续租成功。
5. **正式门禁期间不并发其他重任务**（TD-SW008-095）；整次运行预计约 2 小时 30 分钟到 3 小时。

## 4. 精确 Owned Paths（15）

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/continuity_execution_service.py` | 存在 | 被拒时写明持有者与租约到期（本机时间）：同一 Work 已有 Run 时（用例 1）、口令不匹配时 |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/infrastructure/continuity_store.py` | 存在 | 回收 `reclaim_lease`（事务内再判租约失效、持有者与版本未变、无法判断时必须有用户签字）、持有者进程记录、风险签字记录；epoch 也认回收事件；拒绝信息带持有者与到期 |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/ui/cli/continuity.py` | 存在 | 口令来源：环境变量或本机钱包（旧的命令行口令选项保留并标弃用）；新命令 `run reclaim`、`lease record-holder`；`run start --lease-wallet` |
| 4 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/ui/cli/pm.py` | 存在 | 在 `pm` 下登记三条新命令（文件末尾 7 行） |
| 5 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/lease_handover_service.py` | 计划新增 | 新文件：交接、接手、回收与签字的服务层（只编排存储原语与进程观察） |
| 6 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/infrastructure/lease_wallet.py` | 计划新增 | 新文件：本机口令钱包（`.auto-pm/cache/lease-wallet/`，被 Git 忽略），原子写入，只把口令交给它的持有者 |
| 7 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/infrastructure/process_probe.py` | 计划新增 | 新文件：只读观察持有者进程（Windows 与 Linux）；读不到一律算“无法判断”，从不算“已死” |
| 8 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/ui/cli/pm_handoff.py` | 计划新增 | 新文件：`pm handoff`、`pm takeover`、`pm sign-risk` |
| 9 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_pm_handoff.py` | 计划新增 | 新测试 15 条：命令接线、口令来源、钱包、交接与接手、回收命令、签字只认用户、数据库与钱包被 Git 忽略 |
| 10 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_lease_handover_service.py` | 计划新增 | 新测试 28 条：用例 1、用例 3 的全部分支、存储事务内复判、精确重放、交接与接手 |
| 11 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_reclaim.py` | 计划新增 | 新测试 1 条：真实进程——执行进程被杀后另一个 agent 接手、旧进程回来被拒 |
| 12 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/infrastructure/test_lease_wallet.py` | 计划新增 | 新测试 7 条：钱包 |
| 13 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/infrastructure/test_process_probe.py` | 计划新增 | 新测试 7 条：真实进程的存活与被杀、别的主机算无法判断 |
| 14 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/02_整改项/活动技术债台账.md` | 存在 | 台账回写：TD-SW008-063、064、065（最小子集）、067 已偿还；登记 152、153；§3 追加 CHG-SCPT-2026-430、431 |
| 15 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md` | 存在 | WBS 短投影回写 V4.0.1：卡 166、清理卡与本卡；Codex 挂起；§5 新增口令信任模型与委托范围两条 |

出现第 16 条候选变更即停止。准备和证据落点（`.auto-pm/reports/m3-handoff1/`、本卡文件、演练工作树与临时目录）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

最终 SHA-256；6 个修改文件的基线（`ea024f27` 上的）blob SHA-256 在 `handoff1_config.json` 与启动脚本里冻结。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/continuity_execution_service.py` | 存在 | `efa8be4da33610076e54281d88466071583fdc282b4bdde5689293f6e6dafac7` |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/infrastructure/continuity_store.py` | 存在 | `d0f80111f1590762e983f0fab941c0939fa03d1b32a6bc56095c0d19881a7046` |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/ui/cli/continuity.py` | 存在 | `6a4bad51a21f08336ac608de6efc2ff08755cf99fd9628929de9f666446a4b06` |
| 4 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/ui/cli/pm.py` | 存在 | `aa731839b600a0bab57d67ed776c607bf11f30f0af79853d2c073a766fa2730c` |
| 5 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/application/core/lease_handover_service.py` | 计划新增 | `093e4db68a9c7241b376537b9335a6926d4e2f388ca811e3948db1382a567845` |
| 6 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/infrastructure/lease_wallet.py` | 计划新增 | `08ade27daf9951247da10ed3e6c40795b53bf6144f5bbadde1ecd0d056666be2` |
| 7 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/infrastructure/process_probe.py` | 计划新增 | `ebd62f0b39e62e6f9d758872364cb1df8c824fdac9b3760512e59406cecd6537` |
| 8 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/auto_pm/ui/cli/pm_handoff.py` | 计划新增 | `43c587b1e82d6a5a4e8284e4664c45b318042fb201feeef6265231b24e5191ad` |
| 9 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/cli/test_pm_handoff.py` | 计划新增 | `25d87bd447ca5005391312becb8a3fdae34f9ba3b2367e8c56ad0d8712401cdf` |
| 10 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/core/test_lease_handover_service.py` | 计划新增 | `670d5846134be09960fcc4a8aa692ed117080ddf55b6b302329d47fdb826338a` |
| 11 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/e2e/test_pmf_reclaim.py` | 计划新增 | `64e6e073ad0349ba6a441791e16ef6ce7d8f62546e2596a48f383d25256503e3` |
| 12 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/infrastructure/test_lease_wallet.py` | 计划新增 | `de9e402be3ce5a28c2dc215e40e2b79f6f08d9992905fdabe43d87351067faff` |
| 13 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/tests/infrastructure/test_process_probe.py` | 计划新增 | `6d8b9b4e03d132afc09acbb914656252fbfe9a615bbf0d270b201b0faae8540a` |
| 14 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/02_整改项/活动技术债台账.md` | 存在 | `3ae77472c004e05c3e5cea9d6f9faa5a8b8abc27c26ddcec8b934a6689fdaa72` |
| 15 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/39_PM-Flow_恢复与可用化总方案_WBS_PM.md` | 存在 | `c89c25e6c7490e18677772544192f578526609c255c7da02a3b279a70057745e` |

### 5.2 冻结工具

工具与脚本在 `.auto-pm/reports/m3-handoff1/`；清单文件 `reference_manifest.json` 的 SHA-256 为 `2d1e1755b04a0dfb95a8e4d53c334957692aa2786eae46a3ee8e4775b96fc6c9`。

| 工具 | SHA-256 |
|---|---|
| `adjust_counts.py` | `b0662948d52b927db2ba88232b20550616efeb572bdbd129472bb79cbee3ca1d` |
| `commit_msg.template.txt` | `95baf316d98fc2206c2e873ccfcaf0660c6ea1b1bf8d79c5100d588d0b8636b5` |
| `gen_project.py` | `eac50737f52b35b23b3c9b23583ac819940a042f71109f9cc96ceaa435e06565` |
| `handoff1_config.json` | `4b8d8ad941eec02010535bda526d8677ee1a8be34469f39160c50e7b31be308b` |
| `handoff1_gates.py` | `edff56fe9220a618fad558950df1651aef305fa9392e58d5c79fffb46c01e18b` |
| `handoff1_gates_all.sh` | `c1c1eedf78402d424c23dca2a57dbeff42b23c06776810efdea12df94b6d24f0` |
| `install_files.py` | `eb7bc37a83c6231467b4ad2890702c3a96547b17e43a3232e8282f20e92e25cd` |
| `run_g2.sh` | `6956748a33added47bde7bca81e837230d6e461e746f48da7a0770499cd578fc` |

## 6. 门禁矩阵

核心档。顺序：基线测量 → 安装冻结文件 → 快速门禁 → 九组回归（G2，十个输出）→ 瞬时竞态测试的三次隔离重跑（仅在其于组跑里失败时才被判卷采用）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份与健康测试 | HEAD 为基线、工作树干净、6 个修改文件为基线字节、9 个新文件不存在；夹具健康、冒烟、导入测试在基线与候选都全部通过且数目相同 |
| G2 | 九组回归（rest、application、plc、change、contracts、infrastructure、qml_debounce_alone、cli、qml、core） | 与上一张卡的受治理输出相比：失败集合为空、无 ERROR，新增测试数恰为 core +28、cli +15、infrastructure +14、rest +1，其余各组通过数与 skip 数不变。唯一容忍规则见 §1 第 7 条 |
| G3 | 内容合同 | 5 个新测试文件 58 条全部通过且无跳过（用例 1、用例 3 各分支、事务内复判、交接与接手、口令来源、真实进程）；新入口可导入；`doc check` 退出码与基线相同；台账与 WBS 两份文档满足冻结的逐行合同（只删冻结的那些行、其余行顺序不变、新增行带指定标记、LF、无 BOM、无控制字符、无密钥样式）；插件二进制前后相同 |
| G4 | 静态 | `ruff check auto_pm tests` 干净；`mypy --platform win32 auto_pm` 干净；`git diff --check` 无问题 |
| G5 | 范围与字节 | 变更集恰为 15 个路径、字节等于 §5.1；HEAD 为基线；安装前工作树干净；无残留文件 |
| G6 | 产品树只差冻结文件 | `auto_pm`、`templates`、`tests`、`scripts` 四棵树相对基线恰好只差本卡的 13 个产品与测试文件（两份文档由 G3、G5 判） |
| G7 | 隔离与钩子 | 真实 .git/hooks 前后字节相同；无遗留 python 进程；真实 pre-commit 钩子对暂存的 15 个文件退出 0（临时索引） |
| G8 | 真实变异 | 13 个变异（存储回收活租约、回收不抬 epoch、服务层不拒活租约、持有者总被当成已死、agent 会话或非交互会话可以签字、签字不绑定接手方、存储在无法判断时不要签字、用例 1 的拒绝不写持有者、钱包把口令给别人、已结束的进程被当成还在、环境变量口令不被读取、接手不先定位）各让指定测试失败，并按字节还原 |
| G9 | 最终范围与字节 | 全部门禁之后字节与变更集不变 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-18 在本线程回复“合卡”，并在项目聊天里预授权“自行收口推送，其他按照你的经验来”（普通核心卡不再逐卡报批，跑重载门禁前先告诉用户）；**本卡 SHA 在线程里报出、并在跑重载门禁前告诉用户后**启动。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | 按用户 2026-10-18 的预授权委托：G1～G9 全 PASS 且提交字节等于冻结清单后由 Claude 收口；合并进 `main` 仍由用户在网页上做 |
| 审批人 | fubai |
| 执行模型 | Claude |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

0. 启动前核对本机负载，并在线程里告诉用户要跑约 2.5～3 小时的门禁。
1. 在线程里报告最终卡 SHA 与摘要，随即启动（预授权范围内）。
2. 创建 SW-2026-008 的 SCPT/OPT 变更单、匹配 Decision（`DEC-<当天>-M3HANDO1`）、Work `WORK-SW008-M3-HANDOFF-001`、Run `RUN-SW008-M3-HANDOFF-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认续租成功**）。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m3-handoff1`，分支 `codex/m3-handoff-reclaim`。
4. 安装冻结字节并完整重跑门禁（`handoff1_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；按委托收口变更单；推送 PR 分支并开 PR，由用户在网页上合并；独立审计由项目另开的云端会话做。

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败（§1 第 7 条那一条容忍规则之外）；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；插件缺失或版本不符；需要改这 15 个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮；同一问题两次未解就通知用户；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结文件与工具；演练原始输出（非治理）；正式独立门禁与证据；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；委托收口记录；PR。

## 11. 限制与后续

提交在本地分支 `codex/m3-handoff-reclaim`，之后推送为 PR 分支。命令在 D06/D07 部署后才在根入口生效。之后：真实进程演练 `M3-DRILL`（Trae CN 到本机 Claude Code 接棒，加执行进程被杀后的回收）；薄入口措辞文档卡（TD-SW008-153）。
