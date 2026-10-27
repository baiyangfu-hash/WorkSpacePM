# M3-HYGIN1｜控制根治理记录入库实施卡（产品档；M3-HYG-MIN 的入库部分）

> 卡片编号：`CARD-SW008-M3-HYGIN1`
> 版本：`V1.0`（2026-10-16；最终字节报 SHA 后冻结，执行期间不得修改）
> 状态：`PLANNED / PRE-AUTHORIZED`（用户 2026-10-16 说“你的其他建议全部批准”“允许夜里推”“允许夜里执行”“今天晚上继续作业”；HYG-MIN 的 14 类处置在其中；本卡 SHA 先在聊天报出再启动；条件见 §7）
> 档次：**产品档**（分档器：变更单与 Decision 所在目录命中规则——它们是治理工具运行时读写的数据；不得降级）
> 依赖：卡 148（M3-V04R1B）的 Run/Work 已达技术终态且 CHG-SCPT-2026-422 已收口（由启动脚本核验）
> 隔离基线：`d25a98161c52a8dd0ca2be1bd5ae4d6196666c28`（卡 148 的提交，本地分支 `codex/m3-v04r1b-fix`）
> 路径根：`.`
> 执行模型：`claude-sonnet-5-5`；GPT 只做审计
> 禁用能力：`pm-workflow`（含不得读取其内容作为当前指令）

依据 PM-042、PM-033。无 UI 改动，HTML 原型不适用。

## 1. 背景与已核实事实（2026-10-16 夜）

1. **为什么**：控制根里有大量受治理记录从未入库（TD-SW008-141）：Decision 记录、实施卡文、变更单正文、旧方案归档，以及只存在于分支 `codex/c09-recovery-governance` 上的治理文件。换电脑或本机损坏就丢失，版本库也无法证明这些变更为什么发生；更重要的是，**合并 main 之前必须入库**——main 如果只含代码、不含这些记录，别人（朋友、云端、项目 Claude）克隆到的是治理记录残缺的仓库，而产品里有“Decision 绑定 Git HEAD”的校验。用户 2026-10-16 批准了 `M3-HYG-MIN` 的处置原则（绝不删除、已改文件先备份、逐类）与全部 14 类建议；已备份的 18 个已修改文件在 `.auto-pm/reports/hyg-min-backup-20261016/`。
2. **做什么**（构建时读自控制根磁盘与 git 并断言；565 个路径：561 个新增、4 个修改）：
   - **370 个 Decision 记录**、**135 张实施卡文**、**44 个变更单**（SW-2026-008、SYS-2026-001、SW-2026-009）、**11 个旧方案归档文件**、**1 个**只有 c09 分支持有而本机没有的治理文件：全部原样入库（换行统一为 LF，与提交时 git 的规范化结果逐字节一致）；
   - **4 个活变更台账**（SW-2026-008、SYS-2026-001、SW-2026-009、DJ-2026-005）改为控制根的版本：构建时断言只新增行、基线的行一个不丢；
   - **c09 分支独有的 64 个治理文件**（项目 Claude 的评审 `reviews/02_main_checklist.md` 核对）：本机已有其中 63 个且字节与 c09 一致，其余 1 个从 c09 取回；两个 SW-2026-009 变更单 c09 上是较早的状态（approved），控制根上是后来的状态（completed），**取控制根的字节**并在此记录。
3. **不做什么**：不删除任何东西；不碰发布载荷（`00_Infrastructure/auto_pm/releases/`）、部署指针与部署记录（`active_release.json`、`previous_release.json`、`deployment_manifest.json`）、`.trae/`、`.vscode/`、规范库（规范库 033 的空格对齐改动备份后另行还原）、项目 Claude 的方案文档与云端分支文档、4 个 Decision JSON 的末尾换行改动、学习资料的版本号改动（来源不明，不碰）；不改任何产品字节；本卡不推送（夜间推送由我收口后按用户允许另行完成并读 CI）。
4. **为什么是产品档、跑九组回归**：分档器把变更单与 Decision 目录列为产品档（治理工具运行时读写）。入库新的字节理论上可能被扫描这些目录的测试看到，所以按规则跑完整九组，并要求与基线九组输出（同一产品字节）逐项相同。
5. **安全核对**（构建时）：全部冻结文件无密钥格式的值（含 `secret_scan.py` 的 URL 凭据模式，因为 M3-CIMAIN 之后 main 上的 CI 会扫描这些提交）、每个文件不超过 5MB、Decision 全部是合法 JSON。
6. **容忍规则**：沿用 M3-RACE 的同一条具名规则（事先声明）：rest 组里若恰有 r09 一个失败且同字节隔离重跑 3/3 通过则放行并记偏差；此前所有受治理卡均严格全绿（未使用）。
7. **演练事实（非治理，草稿工作树，不是正式证据）**：2026-10-16 在基线（卡 148 的提交）的临时工作树里跑了一遍本卡的快速门禁与判卷（原始输出在 `.auto-pm/reports/m3-hygin1/gates_rehearsal/`）：基线与候选的 `doc check`、两个项目的 `ledger reconcile`（0/0/0）、565 个文件的内容合同（LF、UTF-8、无密钥格式的值、Decision 全是合法 JSON、基线台账行一个不丢）、10 个负向对照全部被拒、四棵产品树逐字节相同、真实 pre-commit 钩子对暂存的 565 个文件退出 0；九组回归用合成输出（卡 148 的受治理输出）判卷，G1–G9 全 PASS，4 个反例变体判卷结果符合预期。演练中发现并修正了一个门禁脚本问题：565 个文件名放进一条 `git add` 命令行会超出 Windows 的命令行长度上限，改为用标准输入传路径。演练不是正式证据，正式 Run 完整重跑。

## 2. 单一目标与完成定义

控制根里受治理记录在版本库里与磁盘事实一致，且不丢、不删、不改任何其他东西。技术完成 = 全部门禁通过且提交字节等于冻结清单；变更单收口按用户委托在 G1～G9 全 PASS 且提交字节等于冻结清单后代为执行。

## 3. 实施前预检

1. 核对卡字节与已报告的 SHA 一致、基线分支仍在基线、4 个台账的基线 blob 等于冻结哈希、561 个计划新增路径在基线上不存在、卡 148 的 Run/Work 为 SUCCEEDED/CLOSED、CHG-SCPT-2026-422 completed。启动脚本有只读的 `--check-only`。
2. `main.py implementation-card precheck` 对本卡返回 0 且 findings 为空。
3. **机器负载**：启动前核对前台无游戏/启动器，近 10 秒 CPU 低；Windows 更新已由用户暂停至 2026-11-18。
4. **续租**：门禁启动前先用绝对路径启动续租循环并确认日志里有续租成功。
5. **正式门禁期间不并发其他重任务**（TD-SW008-095）；整次运行预计约 1 小时 30 分钟。

## 4. Owned Paths（11 个范围，覆盖 565 个冻结文件）

产品的 Decision、Work 与 Run 把范围放在命令行上（上限约 3.2 万字符），565 个精确路径放不下，所以 owned paths 用**目录或文件范围**；**精确文件清单与 SHA-256 在 §5.1（565 行）**，门禁 G4、G5、G9 逐个核对，变更集必须恰好等于该清单。

| # | 路径 | 基线状态 | 用途 |
|---|---|---|---|
| 1 | `.auto-pm/decisions` | 存在 | 新增文件的目录范围（精确文件清单与 SHA-256 见 §5.1；门禁 G4、G5、G9 逐个核对，不在 §5.1 的文件一律失败） |
| 2 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划` | 存在 | 新增文件的目录范围（精确文件清单与 SHA-256 见 §5.1；门禁 G4、G5、G9 逐个核对，不在 §5.1 的文件一律失败） |
| 3 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单` | 存在 | 新增文件的目录范围（精确文件清单与 SHA-256 见 §5.1；门禁 G4、G5、G9 逐个核对，不在 §5.1 的文件一律失败） |
| 4 | `SYS-2026-001_WorkspaceGovernance/04_监控/01_变更管理/01_变更单` | 存在 | 新增文件的目录范围（精确文件清单与 SHA-256 见 §5.1；门禁 G4、G5、G9 逐个核对，不在 §5.1 的文件一律失败） |
| 5 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-009_英语学习助手/04_监控/01_变更管理/01_变更单` | 存在 | 新增文件的目录范围（精确文件清单与 SHA-256 见 §5.1；门禁 G4、G5、G9 逐个核对，不在 §5.1 的文件一律失败） |
| 6 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/archive` | 存在 | 新增文件的目录范围（精确文件清单与 SHA-256 见 §5.1；门禁 G4、G5、G9 逐个核对，不在 §5.1 的文件一律失败） |
| 7 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/02_变更记录/01_版本变更台账.md` | 存在 | 修改：变更台账（只新增行，不丢基线行） |
| 8 | `SYS-2026-001_WorkspaceGovernance/04_监控/01_变更管理/02_变更记录/01_版本变更台账.md` | 存在 | 修改：变更台账（只新增行，不丢基线行） |
| 9 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-009_英语学习助手/04_监控/01_变更管理/02_变更记录/01_版本变更台账.md` | 存在 | 修改：变更台账（只新增行，不丢基线行） |
| 10 | `0100_PLC自动化/DJ-2026-005/11_监控/01_变更管理/02_变更记录/01_版本变更台账.md` | 存在 | 修改：变更台账（只新增行，不丢基线行） |
| 11 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/02_整改项/控制面事故登记台账.md` | 计划新增 | 新增：仅 c09 分支持有的治理文档（1 个文件） |

出现不在 §5.1 的候选变更即停止。准备和证据落点（`.auto-pm/reports/m3-hygin1/`、本卡文件、演练工作树与临时目录）不是额外 owned paths。

## 5. 字节合同

### 5.1 参考字节指纹

最终 SHA-256；4 个台账的基线（`d25a9816` 上的）blob SHA-256 在 `hygin1_config.json` 与启动脚本里冻结，561 个新增路径无基线。

| # | 路径 | 基线状态 | SHA-256 |
|---|---|---|---|
| 1 | `.auto-pm/decisions/DEC-20260912-00D5A8C2.json` | 计划新增 | `8fb946d71fc9c7af8e762b6dd59013a149abcdb434d021e470ad1e918fca8b2e` |
| 2 | `.auto-pm/decisions/DEC-20260912-488F0A16.json` | 计划新增 | `52c34de1bb499e26259fe2c0521cb33c7622c80049029f48dedc69e752834654` |
| 3 | `.auto-pm/decisions/DEC-20260912-94734A5A.json` | 计划新增 | `7aa27422adbd16d8d6f716265717bdaec241df795074a4a615b2c12d9b7f7aee` |
| 4 | `.auto-pm/decisions/DEC-20260912-B5DE7168.json` | 计划新增 | `8d9017b62f33908cfa1f718cbe6b07b08a36af64d8f237d37342f64801e9dbed` |
| 5 | `.auto-pm/decisions/DEC-20260913-0B527D7B.json` | 计划新增 | `b1a4a9b9b59d11f4129aa13a33fe183459fd721db00178caa110c3eedb135237` |
| 6 | `.auto-pm/decisions/DEC-20260913-1A2BE7E8.json` | 计划新增 | `04f28e672f1d8037e529ceefc5fac92c2690556aabd04231e1bbb4ef374fbeb5` |
| 7 | `.auto-pm/decisions/DEC-20260913-398F83E9.json` | 计划新增 | `42aa63adf2737ea79c7cae6e50f4afcfc1fece2f4cac483559b77d31bc29f23c` |
| 8 | `.auto-pm/decisions/DEC-20260913-3D9D721F.json` | 计划新增 | `644ea40a8922cdb536c923804b77bc9c5964c2ea12c9b012f1966408794be0d8` |
| 9 | `.auto-pm/decisions/DEC-20260913-57479172.json` | 计划新增 | `db358a50fbba3725b4cd4f84ef553aa8b1c4718bce32b24d9a775ea18d468915` |
| 10 | `.auto-pm/decisions/DEC-20260913-6E1773AD.json` | 计划新增 | `c108e4e84fe1c4c7ef875c3676a05f9da129f5fd7367722533909882f3faadaa` |
| 11 | `.auto-pm/decisions/DEC-20260913-71698720.json` | 计划新增 | `be3c5ae5d17718719b006a9b5e44d6eb1e89ace0121f48ff49440af4738c2bb3` |
| 12 | `.auto-pm/decisions/DEC-20260913-895E71AE.json` | 计划新增 | `6df138592ce29a89ae88f7159f0847fd3063d3a1488be3afdf37af3c3735faac` |
| 13 | `.auto-pm/decisions/DEC-20260913-A7A422F8.json` | 计划新增 | `de97ace01b710d6992688fd5d216efb996bab77527fd4d5dc4ba04c25137eb40` |
| 14 | `.auto-pm/decisions/DEC-20260913-A9A5F99B.json` | 计划新增 | `b8fa85354d8e2e19ee8137134b20f3291b98033501a907d355cb23b950197419` |
| 15 | `.auto-pm/decisions/DEC-20260913-BCAEACD2.json` | 计划新增 | `365596016adc6d91984465f42597804abb6e79337ee4743528c1e04b8baba7d5` |
| 16 | `.auto-pm/decisions/DEC-20260913-C0C653BF.json` | 计划新增 | `eded1af56234db93368a38af0ad3b23b5d1cd3a7a35399db92d6e5769de4ebbe` |
| 17 | `.auto-pm/decisions/DEC-20260913-E020B75C.json` | 计划新增 | `b4f9c25aa7ecc12a39275822ba804281110922b7c5c5a9779e9756aedf021f42` |
| 18 | `.auto-pm/decisions/DEC-20260914-190A22F3.json` | 计划新增 | `64376a9184ee5a95bf4fafb328c8e7a36f34f39a20c363ebc821dd29f0c47b3c` |
| 19 | `.auto-pm/decisions/DEC-20260914-26950AE2.json` | 计划新增 | `a1743716a1a02aea6a8a583ab3d2c613d2a543cc41e1b5890ea2c37db5be9903` |
| 20 | `.auto-pm/decisions/DEC-20260914-2CF755A1.json` | 计划新增 | `fc4aab7fe9145db106923639c4682b89f436ccd03517865db61302b0addb9364` |
| 21 | `.auto-pm/decisions/DEC-20260914-31369489.json` | 计划新增 | `09db2d361577cceb7c6ea57b189d8ea6d3821988364826e683631a1e17f377d2` |
| 22 | `.auto-pm/decisions/DEC-20260914-469209F1.json` | 计划新增 | `e751e073050fbc4eba5b5f36bcc61ff5032a44d1d4fe1a48d1e7c955374abd73` |
| 23 | `.auto-pm/decisions/DEC-20260914-5A7739A2.json` | 计划新增 | `97f204d29c41afc66fd62179a796388dc0e0227cc427f1fe2fc17cdc7bfd7b27` |
| 24 | `.auto-pm/decisions/DEC-20260914-6D31D623.json` | 计划新增 | `8b3a2836410ef4d7a5541661d1145afd90d65403d8cc6d7c89f196ef5e188381` |
| 25 | `.auto-pm/decisions/DEC-20260914-6F2DA44A.json` | 计划新增 | `9297c9b59d874bb5a516870e7088a64cb3c9f4b0317a04833a01b2f8a397ec17` |
| 26 | `.auto-pm/decisions/DEC-20260914-8867A731.json` | 计划新增 | `cb2d1d90b397a30130edd77168135be4f73c7703cab44b54667d56c6a41b3484` |
| 27 | `.auto-pm/decisions/DEC-20260914-95F03E6A.json` | 计划新增 | `af7652b50be7a3fd224f00a7e843ef9061753e0ff96b3118e532834bcb1130cb` |
| 28 | `.auto-pm/decisions/DEC-20260914-9E491E53.json` | 计划新增 | `da76dd0f2c7cceed17e15a59b10fdd03e9dfc59060d1d1a7e91c3c4d63c417b0` |
| 29 | `.auto-pm/decisions/DEC-20260914-AF2B899D.json` | 计划新增 | `75c302892808e0babe764257f578e055febeb1f1e8dc168f696f2f9ce77a73b1` |
| 30 | `.auto-pm/decisions/DEC-20260914-B4EA7300.json` | 计划新增 | `c1a16035e4501ad433e152973f28c5b617a08cc06236258d2958086de2892cc6` |
| 31 | `.auto-pm/decisions/DEC-20260914-B81DA099.json` | 计划新增 | `2a5725f8277f2df29faaddc9de985e43e8b13dffd899da07c3d65d1ad526b140` |
| 32 | `.auto-pm/decisions/DEC-20260914-CB787A31.json` | 计划新增 | `04c1655262723281b347124c9ec005cfc3f244dcef57cf032093bb1b9a526985` |
| 33 | `.auto-pm/decisions/DEC-20260914-FA85DD64.json` | 计划新增 | `1b80cc597a08d102f1e5f8335f756af0cc06fec9a3020a6a1a0c5ce1d9f1aaaa` |
| 34 | `.auto-pm/decisions/DEC-20260914-FB35F02D.json` | 计划新增 | `6f198a7d03226fb60e3f36ace592eb721c73f124e6daa0ba9b60ef2d83ac0509` |
| 35 | `.auto-pm/decisions/DEC-20260914-FBDAC832.json` | 计划新增 | `97e407a0db4eabe2f920724f4f3dcce64dd7d449ca59ec1907d5290eaa80ad90` |
| 36 | `.auto-pm/decisions/DEC-20260914-FE6F4E97.json` | 计划新增 | `a19c89666162ed6bfebb99e2169414d41f562705848c4e38ccacc21c4e1b6477` |
| 37 | `.auto-pm/decisions/DEC-20260915-0DB160C5.json` | 计划新增 | `f08ef13ed13f3d7c57fde5118d74bdc73bf31be2e353730a1e7968bd70ed2fb5` |
| 38 | `.auto-pm/decisions/DEC-20260915-1C6FD9E9.json` | 计划新增 | `dd77996b2ab7f1067fbf0adedaa2078031e520dc63a3864bbf34ba1e96d14e2f` |
| 39 | `.auto-pm/decisions/DEC-20260915-2F4E76FB.json` | 计划新增 | `1eb624a676e79d97827c1732da109235bd15a0f49b19acb438648ed52e365ed6` |
| 40 | `.auto-pm/decisions/DEC-20260915-42511897.json` | 计划新增 | `a2b9d0c94cbcf1174e1889770ff567ded85ed276f4b27caf0e756382e51dc106` |
| 41 | `.auto-pm/decisions/DEC-20260915-53746F27.json` | 计划新增 | `8b2a1dac6aa555de355bcfb32ec269729d205f7009cc2aaaae86c82e24cf5c67` |
| 42 | `.auto-pm/decisions/DEC-20260915-A5D0A37E.json` | 计划新增 | `86856d7420c5f22212fabfd095455bd048cc3148a474500e1fb98a04c18793cd` |
| 43 | `.auto-pm/decisions/DEC-20260915-E7797850.json` | 计划新增 | `21bf9fddfcda9077eb5d59c13feebeeb8599a47f86e7b7c42f4ce7469f5533b9` |
| 44 | `.auto-pm/decisions/DEC-20260915-EC1C560D.json` | 计划新增 | `5675e6b25c55b5142fbc2cfa4e9bd0c3dc90f6d0dd05d8b748a03eb6feec64dc` |
| 45 | `.auto-pm/decisions/DEC-20260915-F79AE948.json` | 计划新增 | `aaab3929264e9dbd5e8fb0f9074ee3c494577b6183cd342bf8705f6adb8f74d0` |
| 46 | `.auto-pm/decisions/DEC-20260919-1B6BBE97.json` | 计划新增 | `1dcd898b36617b4c77321bca5f465e39c67351542a96c51deeb8d3c43fc8059b` |
| 47 | `.auto-pm/decisions/DEC-20260919-1E7416E9.json` | 计划新增 | `26d10d0525de6b683ce0c4402529bf5e1348dfa6555cb7bc2b02fd277b9bf24a` |
| 48 | `.auto-pm/decisions/DEC-20260919-209898A1.json` | 计划新增 | `c610fb276194a485469c7afe01344e7304b9707f4c47a48314b590793a48b0c6` |
| 49 | `.auto-pm/decisions/DEC-20260919-259B6927.json` | 计划新增 | `a848688b64e776c4d58dae1f49ec52ed49bf3aa0f156f5df872b306599f89cf6` |
| 50 | `.auto-pm/decisions/DEC-20260919-299C2474.json` | 计划新增 | `a7efe045c34edb6aae04295728a362f98cdb2c5d9c44c8b936329205d8a6aab4` |
| 51 | `.auto-pm/decisions/DEC-20260919-40844A15.json` | 计划新增 | `dbc42a2bdd422db825d9d03d5f31e7ed08d3e413c188c6c94dea774c05753ce5` |
| 52 | `.auto-pm/decisions/DEC-20260919-4147B7D4.json` | 计划新增 | `ea7d3aa5bd65b042b35eff7d1bc056ea710d139dfe9113a7b66c515e15aafc23` |
| 53 | `.auto-pm/decisions/DEC-20260919-8B521F39.json` | 计划新增 | `122eb6bc13745e2127131cb38f02d75d43df868a1d244ae985963a0803cb83e1` |
| 54 | `.auto-pm/decisions/DEC-20260919-985E63A2.json` | 计划新增 | `4754702716f4e17df1a340f05aa26a313188763236141784354f6f3e0e650f71` |
| 55 | `.auto-pm/decisions/DEC-20260919-A1512A5E.json` | 计划新增 | `a641845abb43c0700555065a55706ba8d82e5bbc6b35b089325b7d31e9eabad3` |
| 56 | `.auto-pm/decisions/DEC-20260919-B238B8A8.json` | 计划新增 | `03b1d869682ef3d0df32c5fc9ce51a3aebafb8d229d8e5ea1212efb5772b0198` |
| 57 | `.auto-pm/decisions/DEC-20260919-C04C0261.json` | 计划新增 | `aa57086fda50da00e4f9482f8adcdc472c39bc3977ef05b4ab20a911773146b9` |
| 58 | `.auto-pm/decisions/DEC-20260919-C1796A60.json` | 计划新增 | `47c4071f5949730733921c803ee9d1cd58aad2600418ab8b46e0e507d8823a80` |
| 59 | `.auto-pm/decisions/DEC-20260919-C4518F63.json` | 计划新增 | `541eae76290573083c64096aa17c10df1a74a244b98bfe71fc2796eea5dd8641` |
| 60 | `.auto-pm/decisions/DEC-20260919-E07C0262.json` | 计划新增 | `0999d70e716bd8bc746cbe2acb414e99d80bff5ef3383973217338564c22449e` |
| 61 | `.auto-pm/decisions/DEC-20260919-WBS21001.json` | 计划新增 | `5505cdc52c7676cec3415e1466f4667a2134fe3950721aca90799bbb644a3c96` |
| 62 | `.auto-pm/decisions/DEC-20260919-WBS21201.json` | 计划新增 | `d8cbd8e785232271c8fc2ba9e05027e9d584cb3a01eba0bfad54bdec2941e431` |
| 63 | `.auto-pm/decisions/DEC-20260919-WBS29001.json` | 计划新增 | `1ce6ad63d092a42768a9cdcdafe51de15fb502905f9fda71e76959b6fe53d376` |
| 64 | `.auto-pm/decisions/DEC-20260920-0701DD43.json` | 计划新增 | `eacc5d2cc9830fb60ab8e33126f0b1f83cb8f368d110046246960633e536c775` |
| 65 | `.auto-pm/decisions/DEC-20260920-0B066310.json` | 计划新增 | `42433829b31d6c19af25c7146577a7745447e35ac1f3241c74c0f64a30d29ac7` |
| 66 | `.auto-pm/decisions/DEC-20260920-0D84CCE1.json` | 计划新增 | `d8ec6ac00c4c9c02791ff2cedcd02f95800c442981b8568b04532cca1dd7de27` |
| 67 | `.auto-pm/decisions/DEC-20260920-15D983A0.json` | 计划新增 | `6c9cabad2ecad5581144c5dc324446a6ddf7d11c51866aefc3029180d83906bc` |
| 68 | `.auto-pm/decisions/DEC-20260920-18569966.json` | 计划新增 | `52fc73edae9d90699902ec3867553d20f5749595da673bdd06a069ea049adac3` |
| 69 | `.auto-pm/decisions/DEC-20260920-26062ED2.json` | 计划新增 | `c6ee14102303c6ccb1e82159add307e1b5a86b519d9ed8121c9130b9b4cb4fe7` |
| 70 | `.auto-pm/decisions/DEC-20260920-35CF805E.json` | 计划新增 | `e06dfe93c42b13b6d094998680a194a0163aa6488279548585e6d06f51715234` |
| 71 | `.auto-pm/decisions/DEC-20260920-495AEDBA.json` | 计划新增 | `168cbaaac8d90e7d3153077840dc0348ffcebf496213a4bda3241546dfe986cd` |
| 72 | `.auto-pm/decisions/DEC-20260920-4BAC1FE5.json` | 计划新增 | `380e4be5ae65aaab5e634abbd393dedab14645fd6b4a8ce579d19fcbc796e6c1` |
| 73 | `.auto-pm/decisions/DEC-20260920-53286204.json` | 计划新增 | `c9c48c733d67d7db76a2537fcf9882b6d78cf2c3c17813f00490cb0437e6e555` |
| 74 | `.auto-pm/decisions/DEC-20260920-58463FE9.json` | 计划新增 | `92efab19d908acc02087c5f922c88db5c43ab24006e798eee6fa7300a976bc2c` |
| 75 | `.auto-pm/decisions/DEC-20260920-5A441F8D.json` | 计划新增 | `ceca74e7c027528290de2daf680ba71022f53ab8ba866ff6bd86797b918acb3a` |
| 76 | `.auto-pm/decisions/DEC-20260920-638CE7CD.json` | 计划新增 | `5a9ae2a3b6282ad7cedf6bbeb2aa88f1d4464718527b4041dabcbac0bfe63634` |
| 77 | `.auto-pm/decisions/DEC-20260920-6B2D26B9.json` | 计划新增 | `dc45ed96f313eab8715a510f5f22ab4ceba838f0742ad2f42d042eb1f2ab849c` |
| 78 | `.auto-pm/decisions/DEC-20260920-6C43E498.json` | 计划新增 | `51c20d173df31207226601cdd38b2e94f6981474e124a8e4c4f522f7d2446bdd` |
| 79 | `.auto-pm/decisions/DEC-20260920-7753334D.json` | 计划新增 | `ab4e9e0116a84990a94dc62d6c3dfc154a80fd484eb835a349c6bbca1c58690f` |
| 80 | `.auto-pm/decisions/DEC-20260920-83AF9E52.json` | 计划新增 | `6b1f6b3461e84efdb744a8a28f586882caae11bdcf65cb27f8515963ab45f709` |
| 81 | `.auto-pm/decisions/DEC-20260920-971F217E.json` | 计划新增 | `1ce72d3e82a453989a72e87aece830e49db89516ab68f767b11e3505c37e0ebf` |
| 82 | `.auto-pm/decisions/DEC-20260920-9A6AEA22.json` | 计划新增 | `f1ed899476778eac1a46f5ab8c8eed73c0cb617f49097fed9ae568c730c56268` |
| 83 | `.auto-pm/decisions/DEC-20260920-9AD04286.json` | 计划新增 | `97da4ac86eae6a7211d0834827a03ac3f570d337f112c34fc442b83381acbf71` |
| 84 | `.auto-pm/decisions/DEC-20260920-9D900CEE.json` | 计划新增 | `5e8a8fdd9f96caf1a476d91ff583acacd684de194f957bfe35ca5f79fcdd60e9` |
| 85 | `.auto-pm/decisions/DEC-20260920-BB762435.json` | 计划新增 | `67121ef9d93c68cca09930568b45004cd98710be99a144df24c3e81b1bcae715` |
| 86 | `.auto-pm/decisions/DEC-20260920-C72A63FC.json` | 计划新增 | `83d56ad32009c3ac8d348cf6d9f049c5c59deb27f8bd961a2f3a7557a063140b` |
| 87 | `.auto-pm/decisions/DEC-20260920-D10D4AAB.json` | 计划新增 | `498c5b613b1f82cbbf99357b7f0f5c1afd4a8b6badd65fcfc513d70d9927d303` |
| 88 | `.auto-pm/decisions/DEC-20260920-D30DBD65.json` | 计划新增 | `e4d74b9c0665f219c098427654dbbee2556bc9bfb7b06cac7376d4eb0d4ff555` |
| 89 | `.auto-pm/decisions/DEC-20260920-D805E754.json` | 计划新增 | `02131f5e9b0bb0df8f1c269b322b64536d3817004297647453bc44006f1ccf0f` |
| 90 | `.auto-pm/decisions/DEC-20260920-E08A0001.json` | 计划新增 | `d9a0c06104344c2812d6ca42b73a6f3a6a19dd01eec8d0b5c341af4473e3d9b7` |
| 91 | `.auto-pm/decisions/DEC-20260920-E903FAE6.json` | 计划新增 | `7089ffdde4d94c165f1fb5f007beb9dfe94665e96b744e2ba8d11d5eacd13076` |
| 92 | `.auto-pm/decisions/DEC-20260920-F51725B7.json` | 计划新增 | `0abd297c6ec927a3f40682185bf42f6deb0c9e6571ad487d0fbd10e68befaa45` |
| 93 | `.auto-pm/decisions/DEC-20260920-FB987510.json` | 计划新增 | `f6aee5fad08a4ff1c7e80fc33672cd634364a49c74d331bc7c1493cd31a7ae45` |
| 94 | `.auto-pm/decisions/DEC-20260920-G15INT01.json` | 计划新增 | `dd306a0693f8ec4e476678e6b923532c95d639b14be1670ea168aa4b5cd72812` |
| 95 | `.auto-pm/decisions/DEC-20260920-H03SAFE0.json` | 计划新增 | `1ab7edf3099a91566d69a14ae629ba7b12c5305beca44661562c5e8b04a70793` |
| 96 | `.auto-pm/decisions/DEC-20260920-H12VAL01.json` | 计划新增 | `9b35969aad3437707f4fed48b8dd8bec3d10cb2b5ea0d6b5fab0c131c972239b` |
| 97 | `.auto-pm/decisions/DEC-20260921-3D4F1F21.json` | 计划新增 | `5d71fc4d384a3c0eb5fcb7551d18b8a439c8a12c454a859f7de4ab52375d6afc` |
| 98 | `.auto-pm/decisions/DEC-20260921-4E4F0551.json` | 计划新增 | `4d25a68b2563c17feacca1c3037ea253018cdf4fbd21960a586134a030b97830` |
| 99 | `.auto-pm/decisions/DEC-20260921-545A8B22.json` | 计划新增 | `34c7953a66ff5efcfffd2508deab0d66a2c1692a2090296d34ffe68bc1205803` |
| 100 | `.auto-pm/decisions/DEC-20260921-62760183.json` | 计划新增 | `2090eff77839c5cb9c5020703db359d20e24f797cc4c1f52c7c8683f14d08e51` |
| 101 | `.auto-pm/decisions/DEC-20260921-63605F4C.json` | 计划新增 | `918f5a1d1a0fd6aa0fa462c9ce29e9134d232b0cb474f2b9e2d97ef5b9fdf710` |
| 102 | `.auto-pm/decisions/DEC-20260921-91EBFAEF.json` | 计划新增 | `467ecab0902582c8093cf94191d57e1d57a270495c36ca19a73ee22565fba3c3` |
| 103 | `.auto-pm/decisions/DEC-20260921-A0AD9EE7.json` | 计划新增 | `20a056c31c05da398402daf977df15e1c5ed98bcd91039b4717b5ec5b572ea9b` |
| 104 | `.auto-pm/decisions/DEC-20260921-D2DB1A6D.json` | 计划新增 | `dbb2a72f247e988b816c1753341b6316392660804107dc8a2fae04ebd6a16c05` |
| 105 | `.auto-pm/decisions/DEC-20260921-D5DDFE83.json` | 计划新增 | `19734e6db6b149c8f4bf94de4941e53c547292df63f9c7e1167a951405e26280` |
| 106 | `.auto-pm/decisions/DEC-20260921-DCBF5F4F.json` | 计划新增 | `fa61b6a542a1f19d54380e28c4d410f938e83fdfdfa8595f7c6602030435244b` |
| 107 | `.auto-pm/decisions/DEC-20260921-DF7809B2.json` | 计划新增 | `de21929eff3d17709a9dfee741306bc0450ee8aff23d9db251aa0e3c099af3a3` |
| 108 | `.auto-pm/decisions/DEC-20260921-F04E318A.json` | 计划新增 | `404a6bfe71f20d5cc4671012762bb06f4207db929115df8875082de9bc426e1d` |
| 109 | `.auto-pm/decisions/DEC-20260921-H03R0001.json` | 计划新增 | `2e5f8a68877396842b294facca3a61b038ffa6a01aa190bf75e1f28a7766722f` |
| 110 | `.auto-pm/decisions/DEC-20260921-H03R0002.json` | 计划新增 | `e12b7341dcf1d382289d0cbc8322079b9e2c0842f8c9d4f6bcc3c09e7cea8298` |
| 111 | `.auto-pm/decisions/DEC-20260921-H03R0003.json` | 计划新增 | `a2ab42570e39ca40c487ec002c93f8377402ac81b283f59196a9c7585a9697c9` |
| 112 | `.auto-pm/decisions/DEC-20260921-HWC70001.json` | 计划新增 | `e3d01195442440a704861d6cfa33a2c77407ac64da979a250ddda7fb7f0d2751` |
| 113 | `.auto-pm/decisions/DEC-20260922-A901C903.json` | 计划新增 | `0ca9ef45fe8cda8c7a32531c783b5fea0a2ec437296d207e7300e1aef9357b0b` |
| 114 | `.auto-pm/decisions/DEC-20260922-C09R0001.json` | 计划新增 | `c3c184a0aac0fe3673d7c938165eddc4f8162bc03e740a6d3c5a3e4614eccafb` |
| 115 | `.auto-pm/decisions/DEC-20260922-C09R3B01.json` | 计划新增 | `cc06948921fada1b6ab45f4618c481a683a11fb96624b229df535bfbf95cc328` |
| 116 | `.auto-pm/decisions/DEC-20260922-Q03R0001.json` | 计划新增 | `8d5cd1b25663b13fadfc1a81549f490c35c940544cd8dcf4156f6997fd77bc51` |
| 117 | `.auto-pm/decisions/DEC-20260923-4E4C5345.json` | 计划新增 | `85287d3a5f95f78dd13b61651b651a28a9e8eae102d252cf091e480f2bfe58b1` |
| 118 | `.auto-pm/decisions/DEC-20260923-57C74C50.json` | 计划新增 | `52c2cea269f7da7271af8e7fb2f571b74252bb60c791e36863402c61a82c6fc5` |
| 119 | `.auto-pm/decisions/DEC-20260923-5D0E95FC.json` | 计划新增 | `42f7e38fa317c5a6750849a06d6dfe54da547218682a5c123682390762eeff85` |
| 120 | `.auto-pm/decisions/DEC-20260923-637498D5.json` | 计划新增 | `96e2e3020c5ae9a613ec5cee925e4d7cb6fd4c0745fc66cc1e69706811027082` |
| 121 | `.auto-pm/decisions/DEC-20260923-8E28B4C7.json` | 计划新增 | `8071e98195652f713903106384e745eba0080c97604faa0056cf28d8fce7f1ab` |
| 122 | `.auto-pm/decisions/DEC-20260923-A5FD056A.json` | 计划新增 | `e9875ed4c0f108cf9a4f8a8e8528563a4cff323a09f12c35ee9f292b610149ad` |
| 123 | `.auto-pm/decisions/DEC-20260923-C09ART01.json` | 计划新增 | `c7f224f0bb5243509d39ab52e1c51b0039f34439848de2f1f66c31857b474575` |
| 124 | `.auto-pm/decisions/DEC-20260923-C09C0001.json` | 计划新增 | `63ccbf873d76f524076a22a0dd8a37924cef52fc07ee32d807683270e0232638` |
| 125 | `.auto-pm/decisions/DEC-20260923-C09DONE1.json` | 计划新增 | `f9abf025383a455500d24ae58c58eb3368f0ac3895e01b45cfd36e547fe569f6` |
| 126 | `.auto-pm/decisions/DEC-20260923-C09DONE2.json` | 计划新增 | `da6c64c1556b5f91bb016a2600b2fcebbcd3670b6722f8d60346e1134177b4c2` |
| 127 | `.auto-pm/decisions/DEC-20260923-C09DONE3.json` | 计划新增 | `4d93a5182074304ba4a6ac1b5c0387672527b39463c454ddb04cff049fdbb29e` |
| 128 | `.auto-pm/decisions/DEC-20260923-C09FE001.json` | 计划新增 | `17c4121cf8f30fbdbc56fc019f38b089e6aa1f65e5248499d6f925b41cd75ea8` |
| 129 | `.auto-pm/decisions/DEC-20260923-C09FE002.json` | 计划新增 | `93bdfb3d886c8e1654187baf3aa8eb725b198f349c3108b651ca88084fb2adf4` |
| 130 | `.auto-pm/decisions/DEC-20260923-C09FE003.json` | 计划新增 | `1b50c3b391f0be576c82fc1f5fe7f3e3d725a57d72b48dfb089a01f4267e04fc` |
| 131 | `.auto-pm/decisions/DEC-20260923-C09LEG01.json` | 计划新增 | `858e57d3c03ba121eda782887a6ffb41c3bfe30d1e9e97409549fecbcffe5218` |
| 132 | `.auto-pm/decisions/DEC-20260923-C09R0001.json` | 计划新增 | `49a6b90a690e516ac7f5d6f5e17d0613b610d98e7a382836fede82503e2638c6` |
| 133 | `.auto-pm/decisions/DEC-20260923-C09R3C01.json` | 计划新增 | `ebe436c13817974d117a865a44725b394378214f54443b08903ce5d2253811ef` |
| 134 | `.auto-pm/decisions/DEC-20260923-C09R3C02.json` | 计划新增 | `712bf9c8fc5609a423571630b231a25871542a46119eb05f4da992bb6a6291c3` |
| 135 | `.auto-pm/decisions/DEC-20260923-C09R3C03.json` | 计划新增 | `60d9af0604b138b11c27e1a3d29dacd7a090b3fc1341e27a5b3db0e0b1cabc4a` |
| 136 | `.auto-pm/decisions/DEC-20260923-C09R3C04.json` | 计划新增 | `00b675497aefdf9cf007dd15c3a1b698034e03c8fce69853f9aed2a1c70dcfac` |
| 137 | `.auto-pm/decisions/DEC-20260923-C09R3CR1.json` | 计划新增 | `d40ee10e9e9b8a6aaee81aef2c9da0e2b64bcd7ad0565e53c43be030d7569510` |
| 138 | `.auto-pm/decisions/DEC-20260923-C09R3CR2.json` | 计划新增 | `114225269cd9cda81b760f61e103f002847326d5586de0cfd51b60faf0fae1dc` |
| 139 | `.auto-pm/decisions/DEC-20260923-C09R3CR3.json` | 计划新增 | `48b7999a3534f951b05b6c46e4d8ee96075772f7897bf07dc47dec367661846c` |
| 140 | `.auto-pm/decisions/DEC-20260923-C09R3CR4.json` | 计划新增 | `898f8d928722cf66cbe7ea6825496afa43a1b4b5c0d5b8d5b5b4f0c6972b5376` |
| 141 | `.auto-pm/decisions/DEC-20260923-C09REC01.json` | 计划新增 | `433264406f1aa54d824e4a6eb07dfab6a1305b4f4ea071bb294533754a5f92db` |
| 142 | `.auto-pm/decisions/DEC-20260923-C09REC02.json` | 计划新增 | `4ff66e68b2e6159041562b2dd58b33312f1e1a721c1f6e06e6ae9285e37c73e1` |
| 143 | `.auto-pm/decisions/DEC-20260923-Q03LEG01.json` | 计划新增 | `488692604e4698e15a2fc4724c8064ed5af2146343bfe1e6e2d3b5574a7b4b79` |
| 144 | `.auto-pm/decisions/DEC-20260923-Q03R0002.json` | 计划新增 | `bfd264f891a99763e4db9d32a9932893621dd6a1c79e6c7aa0dc4a423b34510b` |
| 145 | `.auto-pm/decisions/DEC-20260924-051B85A8.json` | 计划新增 | `54a1e89cb7b453c019f10ed76a7fa058e119fd285545fd502045b60a9e2a6af5` |
| 146 | `.auto-pm/decisions/DEC-20260924-6404A011.json` | 计划新增 | `638381fff2ecd972bb2cf5ec89294cbf7b7701d3fdf98ab86c80a01d5fb033a8` |
| 147 | `.auto-pm/decisions/DEC-20260924-6BAAB080.json` | 计划新增 | `f932b0583bff19d494cb13decb883e63dd36d0434dc71438a48e26176bad95d2` |
| 148 | `.auto-pm/decisions/DEC-20260924-94F97EA2.json` | 计划新增 | `e242e710e8913075450b4d891c4b7aa01716b0e417df4f2fd4cc24bb9ad2c763` |
| 149 | `.auto-pm/decisions/DEC-20260924-D4C2E911.json` | 计划新增 | `afbaff3fad7f8717b3942f3514baaf6fceaa62ffce1cd1803639f09cb3a57eed` |
| 150 | `.auto-pm/decisions/DEC-20260924-F7689947.json` | 计划新增 | `7561b5bcb92b355a9952477cd1763dbfb49633877ce0521c2a33917855d40938` |
| 151 | `.auto-pm/decisions/DEC-20260925-C09P2001.json` | 计划新增 | `e05815fcd52f4d1f58600a7e278a00315b0e0fdb5ee3876725e6be8777c0e558` |
| 152 | `.auto-pm/decisions/DEC-20260925-C09R3C01.json` | 计划新增 | `d05f6d0d7c922c3e873b6be0def7e2827860ad38352205293c70247975d49ab6` |
| 153 | `.auto-pm/decisions/DEC-20260926-0DEF6ADE.json` | 计划新增 | `f20bbc9acff0db739a07011a7d941dc405035a84ca40f8a3aa85b3d8eccb1852` |
| 154 | `.auto-pm/decisions/DEC-20260926-C09P2324.json` | 计划新增 | `29c040b46cf03f361f4b5128c4be11cd404eaa641e75975fc06d2c09b57ca577` |
| 155 | `.auto-pm/decisions/DEC-20260927-1E58FA8F.json` | 计划新增 | `f5954e8d68fd21003b52265822ff5440d0c2b7cedfef98922e0779369d8f2da5` |
| 156 | `.auto-pm/decisions/DEC-20260927-2243C496.json` | 计划新增 | `882881d299522228088751fa79f959b35464f4d66ec68e16fa7037b5f11203f8` |
| 157 | `.auto-pm/decisions/DEC-20260927-329RVK01.json` | 计划新增 | `e61acf21db51ce2b5e8f00bcde522e7a32e271b5a9490d0ba6131335f9a376d6` |
| 158 | `.auto-pm/decisions/DEC-20260927-3A8E013B.json` | 计划新增 | `e61d2cd154eef0b7a0e94c2ec988ca2c7930fbf78ee4abee61f7ba567546deb1` |
| 159 | `.auto-pm/decisions/DEC-20260927-4F70BE88.json` | 计划新增 | `d0a73af3adba679a9d11552d07eaee298c3a769351edd3e1953beb00cd688d46` |
| 160 | `.auto-pm/decisions/DEC-20260927-4F76EE3D.json` | 计划新增 | `95f8c74843a989bb03f882af0787a2974be83fa2d34806bbdf397f246dede107` |
| 161 | `.auto-pm/decisions/DEC-20260927-6DBB0D77.json` | 计划新增 | `04deb1a32b61e169826f7ca838c64e2c6051a6f31b65ab331d310de8dd0ba265` |
| 162 | `.auto-pm/decisions/DEC-20260927-7B5C013A.json` | 计划新增 | `466966444df060048084dd56a0113f89426ddaa9f08c5388779ffa98ca7dbd38` |
| 163 | `.auto-pm/decisions/DEC-20260927-7D7E84B3.json` | 计划新增 | `92836c7b855ee2eb38712a9f4f7d4f97a4c66f267fb694a9bcfd2192eefa65f0` |
| 164 | `.auto-pm/decisions/DEC-20260927-871B343F.json` | 计划新增 | `c9dc988525ca6eea200e5e6e20a75f0e12df4606b91c3abba711058160d0f42e` |
| 165 | `.auto-pm/decisions/DEC-20260927-8B177C43.json` | 计划新增 | `680a87ce7b572caa2a1fb4e7e022646c46c308ff9ed1bb1543762932f437a083` |
| 166 | `.auto-pm/decisions/DEC-20260927-C09F1A32.json` | 计划新增 | `1d573d4854ae606f0e189daeb7adc3208646b08cb4ead0db9447b9e629b7e903` |
| 167 | `.auto-pm/decisions/DEC-20260927-C09P2ADJ.json` | 计划新增 | `9e537590cdc0d43a3899f6725d1ff450589cb903b2d315d616e65d17e2ba190e` |
| 168 | `.auto-pm/decisions/DEC-20260927-C09P2R01.json` | 计划新增 | `409ae1e1cab909d9d63d38c68c15b394e1844f95e50d81a4baefc6ad55f13804` |
| 169 | `.auto-pm/decisions/DEC-20260927-DBB26950.json` | 计划新增 | `8491f4620d20c8d029e6776fc7c749892f5577a303bd91b451cd68d65d7e37f2` |
| 170 | `.auto-pm/decisions/DEC-20260927-G10R1001.json` | 计划新增 | `2daf047afecef7d607b78eb60556ac8c2ce6396897b97f1b02ee8e2b5c690f72` |
| 171 | `.auto-pm/decisions/DEC-20260928-05BC73A2.json` | 计划新增 | `da1af359b5b4eb3aa9b1112a9e087c043a26b595162f1f9da68d494659101e11` |
| 172 | `.auto-pm/decisions/DEC-20260928-0B54A4B6.json` | 计划新增 | `1aa48bb35a18afaef8d2410f7fe88290fec7cf8d54eb0c64580d45aff2542270` |
| 173 | `.auto-pm/decisions/DEC-20260928-13FA4027.json` | 计划新增 | `d5417697ea558aec1bea99fa918d19c2028596f8843abaa57c28533bd3d19254` |
| 174 | `.auto-pm/decisions/DEC-20260928-331AD001.json` | 计划新增 | `c397c577ccf68abb40b1196b0e43a7ffaf3dfb8fae062f8f1251c4ee60a18515` |
| 175 | `.auto-pm/decisions/DEC-20260928-331C0001.json` | 计划新增 | `60d6bf0ad8025d08a350f9261605c6a8ca697910527a0bddd6f386cbf2a19a73` |
| 176 | `.auto-pm/decisions/DEC-20260928-3320A1F1.json` | 计划新增 | `b6e5e88bd8240cf9a08593a058126a7f7714963f0f8a7f2c37ca87fd214e1351` |
| 177 | `.auto-pm/decisions/DEC-20260928-334A0001.json` | 计划新增 | `340fffe921535f2328bba0c5ee0c973c0affd1d0b962a9dc8f094d5e3c53070d` |
| 178 | `.auto-pm/decisions/DEC-20260928-335A0001.json` | 计划新增 | `7e63f688131165be657e5c02986fa17ed952f7a1aefd1bae0994d082699fd577` |
| 179 | `.auto-pm/decisions/DEC-20260928-336INT01.json` | 计划新增 | `9cfbce658a193239d5ccb264b2926f99f06103dd272527b8bd23162252cde904` |
| 180 | `.auto-pm/decisions/DEC-20260928-336REL01.json` | 计划新增 | `16b4ff367f02a2175d698bd14f75ea513c5ecf4c959f6484b5830ee12c7ec758` |
| 181 | `.auto-pm/decisions/DEC-20260928-406D7018.json` | 计划新增 | `e8c6ed85e610150659bbbc780de0771c7803c5ba7686fdfb6aed279c9324aa66` |
| 182 | `.auto-pm/decisions/DEC-20260928-4B1DCC33.json` | 计划新增 | `134361a0e3c57af2bc03999081a9747ba0b4abf0d68a6a74f755e6621be56fb2` |
| 183 | `.auto-pm/decisions/DEC-20260928-792FDFDA.json` | 计划新增 | `a352206f1f5cc2893797da2cb1acbaac0ca59f8554878695f39e8b16d27f0c11` |
| 184 | `.auto-pm/decisions/DEC-20260928-796A3BBB.json` | 计划新增 | `a911a7d1463cfeec563ba8f8eaca88051a4357f3573be65d961b87c75f1ec656` |
| 185 | `.auto-pm/decisions/DEC-20260928-7ADA8EFE.json` | 计划新增 | `0061ad0dc397917fa2bd02c124d289d5500c98344ef7396b09a6c18e2a033124` |
| 186 | `.auto-pm/decisions/DEC-20260928-7E4C2A11.json` | 计划新增 | `4d0dcc9ed6f6703919254278a66570b4225014d632ee5f9c5e48a6991ad703cd` |
| 187 | `.auto-pm/decisions/DEC-20260928-8454F57F.json` | 计划新增 | `98169c873d5a974979dc66b1ee3b907c945faf7e33555387d449815f83abf0d6` |
| 188 | `.auto-pm/decisions/DEC-20260928-8D72B667.json` | 计划新增 | `aa82aa7f776d07c556728913e0f675071e7b4818d9568ded71645028ea88519a` |
| 189 | `.auto-pm/decisions/DEC-20260928-9B2734D4.json` | 计划新增 | `db1d3f0465f88f543c8166c06e89da1e98b9845b5b86418cdba00e506d0e455b` |
| 190 | `.auto-pm/decisions/DEC-20260928-A03A0001.json` | 计划新增 | `0f4013b5e97e5e913bf00eb4a67bdaa200b3296364272ad7d87eca03aa20da10` |
| 191 | `.auto-pm/decisions/DEC-20260928-A03A0002.json` | 计划新增 | `496534c3438539d76858d9c9688642b0b9110a7b4522ce462dbf12391e6275ae` |
| 192 | `.auto-pm/decisions/DEC-20260928-A03B0002.json` | 计划新增 | `6b8f204368b208f0cc4f6b4a800b6c8ccd4ac1c5312d819bcb9bc4f38cff9f0f` |
| 193 | `.auto-pm/decisions/DEC-20260928-A04A0001.json` | 计划新增 | `973f1ba307589f875da3583e46c4fecc546cc6897f22b54c0e33e9769a8f11e3` |
| 194 | `.auto-pm/decisions/DEC-20260928-A04B0001.json` | 计划新增 | `179f216ed3b6714743df7dfc80937267ae071582422fc1aa7ed5cf3a63783ec9` |
| 195 | `.auto-pm/decisions/DEC-20260928-A1F4C332.json` | 计划新增 | `a64216c73515815006787941b9345116314abb7a572f3442611d5b1ef617e2b3` |
| 196 | `.auto-pm/decisions/DEC-20260928-E848E7E9.json` | 计划新增 | `a47ddf4baf1809bae72921ee59e3093c3b0484792e741aa699f6ba12620d7456` |
| 197 | `.auto-pm/decisions/DEC-20260928-FEECDFD7.json` | 计划新增 | `3320da52ec5725cc48a4519ca1c346f29ef1fd14a1dc1d1d8884d61cb767f259` |
| 198 | `.auto-pm/decisions/DEC-20260928-M2BL0101.json` | 计划新增 | `0bed6427fa5ec82973d00ce637c0ac7d4589b5f1e2f0136bd3315f9fd753b80f` |
| 199 | `.auto-pm/decisions/DEC-20260928-M2IC0102.json` | 计划新增 | `d646abb2cce1ff76ab845577c87aac5fa602a2720362aeea9e2a76e3fd6f1b9f` |
| 200 | `.auto-pm/decisions/DEC-20260928-M2U02001.json` | 计划新增 | `1282b241373ac38bc509930590b1465cf13a27e511abad6ef21ed24e2181d07d` |
| 201 | `.auto-pm/decisions/DEC-20260928-U04A0001.json` | 计划新增 | `1c17558b3f0e0ffc12491bc736e49481a53f9e6a715a4bf97d80a93dfce0a167` |
| 202 | `.auto-pm/decisions/DEC-20260929-0ADBC79D.json` | 计划新增 | `f347ac18d7e37c5d1e40325f48bafb0511886497d890474607b01186f9e37d42` |
| 203 | `.auto-pm/decisions/DEC-20260929-3FE5E138.json` | 计划新增 | `c7f008dd4b2cc806b4adc125470604906a83c9f1bd024a13bdad6bac0a0c8639` |
| 204 | `.auto-pm/decisions/DEC-20260929-5130FE99.json` | 计划新增 | `68f0b5a84a19f83c4920d69c5c043b6ea64a5cc7a60d5dcc9b613ef6536f61fd` |
| 205 | `.auto-pm/decisions/DEC-20260929-59BD0F3C.json` | 计划新增 | `b36bceb46a10cce398e1beaa3b57273adf976b72f0b2b58016e233b47eca58d9` |
| 206 | `.auto-pm/decisions/DEC-20260929-5F9DAE1B.json` | 计划新增 | `36f32688b1f1af3045bc96b6c1c25fe3f5bff41bcb2414d3d91e4de254e68ffa` |
| 207 | `.auto-pm/decisions/DEC-20260929-78D8B61C.json` | 计划新增 | `a63feb1277502174d43a94859f9f8fa5af0c7571a4f1b63b250e4140463b6b99` |
| 208 | `.auto-pm/decisions/DEC-20260929-B84378C5.json` | 计划新增 | `8b5fae7696aeda50885d2982cd1616799263f4442118f589ae2f9cef1a7edc00` |
| 209 | `.auto-pm/decisions/DEC-20260929-BL02CODE.json` | 计划新增 | `2bb64ae303c13435e0989b24184032896c3b4ab69bd21d029ebbf0fbdf1646df` |
| 210 | `.auto-pm/decisions/DEC-20260929-DEPLOYH2.json` | 计划新增 | `fa3e7003de540ed7f993b26c5a1dbbd9730994e9fe0c421f5c121591d839fd71` |
| 211 | `.auto-pm/decisions/DEC-20260929-DEPLOYH3.json` | 计划新增 | `8a045a524c41cc68d13445e009440a6ed574e19af49939cbb1c9c92520a0fd80` |
| 212 | `.auto-pm/decisions/DEC-20260929-DEPLOYHK.json` | 计划新增 | `983801441399bb5b6bf2950d28df9a8eeaba711565c46a3dde958dd5544c4989` |
| 213 | `.auto-pm/decisions/DEC-20260929-H11ACODE.json` | 计划新增 | `2066bd7125f8de74d7d65a645318328df97ff4f9d50b545e1b80fbce3dbe5f5a` |
| 214 | `.auto-pm/decisions/DEC-20260929-H11AEXEC.json` | 计划新增 | `7f598634cd2108663325c5be53e26e9258fd4ccf3cfbac0fb179e7c96bc9bee4` |
| 215 | `.auto-pm/decisions/DEC-20260929-H11BADJD.json` | 计划新增 | `82806067d5a9151397d00e82aebdaac6ceb17b5915fa4605bf2393b747f70193` |
| 216 | `.auto-pm/decisions/DEC-20260929-H11BSETL.json` | 计划新增 | `aeb45f45c67f7cbe7cd9018c947f15d520f660e541871648bfa5f0eae3ce79b8` |
| 217 | `.auto-pm/decisions/DEC-20260929-H11CADJD.json` | 计划新增 | `983b5effe8dd7f17a412a93e64bebac6269d9e5c465da380da8e0dc615177c0a` |
| 218 | `.auto-pm/decisions/DEC-20260929-H11CCODE.json` | 计划新增 | `5dbabec951b5ab3535569eddf8258240bbf1ac99bffa653ac35d1d35e0f64e47` |
| 219 | `.auto-pm/decisions/DEC-20260929-H11CFENC.json` | 计划新增 | `537da95ec73ae9487a7c30758bab3c91d7b1e8ec19ef7b8b35b4ba509b047d40` |
| 220 | `.auto-pm/decisions/DEC-20260929-HOOKCTX2.json` | 计划新增 | `dedad2ff524d78832450184613e06ebba2a1c2de61d86408943a81bcc6ab0e48` |
| 221 | `.auto-pm/decisions/DEC-20260929-U04BR1R1.json` | 计划新增 | `46c26d1ae7be72ab2e88954e0128c1b0609e1f144b5afeaf27c2e07358a35678` |
| 222 | `.auto-pm/decisions/DEC-20260929-WBS10001.json` | 计划新增 | `01a619eed0a999a7df181a2cd13e211cc418fed8ed7c3d5e1a08d98747cac297` |
| 223 | `.auto-pm/decisions/DEC-20260930-ADJCODE0.json` | 计划新增 | `31a9d4affc89839405b2c5bbf76b973edc961edd9b55703a14ae0df260a66a85` |
| 224 | `.auto-pm/decisions/DEC-20260930-BL02RSET.json` | 计划新增 | `218542282555d8855b8aaea12127b8fe05676b35397f164f979d6227bc376633` |
| 225 | `.auto-pm/decisions/DEC-20260930-DEP1DPLY.json` | 计划新增 | `8fdafd72068e8836d81e9218e40b5ea328298febec0510e2b1c0f03d48f68dcc` |
| 226 | `.auto-pm/decisions/DEC-20260930-DEP1INTG.json` | 计划新增 | `af5e319144cdcfd3b4ea0942739718e0075b79cfed640c27176976ed61461a56` |
| 227 | `.auto-pm/decisions/DEC-20260930-IC02CODE.json` | 计划新增 | `6fe444733b11babe415144818f907d136b9de9651adad9dd29addaf4d00a3791` |
| 228 | `.auto-pm/decisions/DEC-20260930-U05CODE0.json` | 计划新增 | `7577e5109462abd848327deea46dc2d0d39318587b31111a17282ff89d8ebca1` |
| 229 | `.auto-pm/decisions/DEC-20260930-U06CODE0.json` | 计划新增 | `03b990a7e37880ad589f4f13c53569b08560c9521c93fbadfe478b824c6e4774` |
| 230 | `.auto-pm/decisions/DEC-20260930-U07ACODE.json` | 计划新增 | `90ebe58e416613682acedc7425a6ca5ca56fbb21224fc502bafb993b2bdd5e54` |
| 231 | `.auto-pm/decisions/DEC-20260930-WBS2CAND.json` | 计划新增 | `9f99f71742c1146c610ce9ab7191522171efe3892ab97c92494341b2666a023f` |
| 232 | `.auto-pm/decisions/DEC-20261001-U07ARSET.json` | 计划新增 | `e3fb6823978ad2070736c281c8d897c54d5507c3ff8efc8f1e0b7748ed1e0c92` |
| 233 | `.auto-pm/decisions/DEC-20261001-U07BCODE.json` | 计划新增 | `d11aa0f7c625afa44692dd3f8e4a130ec9c89a8e5c7c8baa119e09b8acd9b12b` |
| 234 | `.auto-pm/decisions/DEC-20261001-U07CCODE.json` | 计划新增 | `8af066a0c4aa7621fc6487dee370a1d4d212d2bc566a2150dea5062e5d6d5036` |
| 235 | `.auto-pm/decisions/DEC-20261001-U07DCODE.json` | 计划新增 | `12bb5c2b67b68b806f59bce14d8c97a9a69d71e7a5ecae1910737a0fa5213091` |
| 236 | `.auto-pm/decisions/DEC-20261001-U08CODE0.json` | 计划新增 | `8f7c1973a36fb31ba9767cb3fd509a960b5e082f02f1adfd951688a47374b1c8` |
| 237 | `.auto-pm/decisions/DEC-20261001-U09ACODE.json` | 计划新增 | `8c9a18387628a8dbba59815b07c74aedf88229929ba87a07e2a1dc7ecdb8cda1` |
| 238 | `.auto-pm/decisions/DEC-20261001-U09BCODE.json` | 计划新增 | `e2bdb8430afea9c4412ccb60501b8fbcced614d1d3e93dff417c4ac12a02dc42` |
| 239 | `.auto-pm/decisions/DEC-20261001-U09CCODE.json` | 计划新增 | `11105ea4fd5ca18c98b4a4db1c491b265eb49465e88767e4c1de187a2f241b5b` |
| 240 | `.auto-pm/decisions/DEC-20261001-WBS3CAND.json` | 计划新增 | `10dd49b083f7a48f0ae9ac3508e9356b9896d8af51c48a44539be1108b216342` |
| 241 | `.auto-pm/decisions/DEC-20261002-QMLLIFE1.json` | 计划新增 | `205fb8899493aa39d038f12a69be93c823948145e1c04c3bb69e4a0e654ae23f` |
| 242 | `.auto-pm/decisions/DEC-20261002-QMLLIFE2.json` | 计划新增 | `921a5f28023405338185d4d4964267426cbcf8fc9b3f7c8d75b3fcefd86846d0` |
| 243 | `.auto-pm/decisions/DEC-20261002-QMLLIFE3.json` | 计划新增 | `ee2dd7190da6946d68ded5ed88da5116574ad3381cbf70ce4e2fce7d9a141652` |
| 244 | `.auto-pm/decisions/DEC-20261002-QMLLIFE4.json` | 计划新增 | `116afe208cfafa8c25b4c3feb8da2273259dfd2520f36540a31928d9f45b5f96` |
| 245 | `.auto-pm/decisions/DEC-20261002-U09CFIN3.json` | 计划新增 | `b06dcc22c037c90af6dc87855c94b293f3052e8268d52ac15c6d830f3e09d8db` |
| 246 | `.auto-pm/decisions/DEC-20261002-U09CROOT.json` | 计划新增 | `edfb4cc32f2570e98eb115544808330243ffdec4d5c6d03bac9f3710017811b7` |
| 247 | `.auto-pm/decisions/DEC-20261002-U09CRUN4.json` | 计划新增 | `1065078ce46c003a09ac640b2aa39e5f94975b9490e9d5d6bdbd2463169014b6` |
| 248 | `.auto-pm/decisions/DEC-20261003-V01BDOCS.json` | 计划新增 | `73862fe4003f36316985711be6dc2244ae705875faceb1394a501297d26239ec` |
| 249 | `.auto-pm/decisions/DEC-20261003-V01CHEAL.json` | 计划新增 | `b486b6e6b11059aab3403aee248908436089729b01043dd09d4446b2a3d252d6` |
| 250 | `.auto-pm/decisions/DEC-20261003-V01DHOOK.json` | 计划新增 | `14cae51ef83fcfee61bbcbf9b9ba574fcbac70156b8c7415c3f25e4fe74e46fa` |
| 251 | `.auto-pm/decisions/DEC-20261003-V01PLCQG.json` | 计划新增 | `25c40d22acb2518e1a9c40d69d4c5d343eac3df9b89ff22ffd0c94d9cf47c25f` |
| 252 | `.auto-pm/decisions/DEC-20261003-WBS4CAND.json` | 计划新增 | `4cb94dd92746620e21f05f8661e847cdba8fc7e6e14d51e1217de55111c2320a` |
| 253 | `.auto-pm/decisions/DEC-20261003-WBS5CAND.json` | 计划新增 | `b3b3979ec93c0c299e587d9675fb7c63b968d274b682dc925905a481682bf1cb` |
| 254 | `.auto-pm/decisions/DEC-20261004-TD1LEDGR.json` | 计划新增 | `870f40b2f331e2144d08a3d8b29a9542f2cbabd1ece6182260a8b5d568521cba` |
| 255 | `.auto-pm/decisions/DEC-20261004-V02PLCFX.json` | 计划新增 | `809ab781d1406ba0d86ed78660840d815e86ec0bfa229eb1ab2b94e531e93a69` |
| 256 | `.auto-pm/decisions/DEC-20261004-V03HNDOF.json` | 计划新增 | `a06780ea77e2335da172c4a3e89045f56b5afee529eeb1950a38dbfcf3d71254` |
| 257 | `.auto-pm/decisions/DEC-20261005-P1AUDIT1.json` | 计划新增 | `991afce34a31bd135fa163ad5a0f4bd2db0b45ae96ac22541ab70ed2a211dc31` |
| 258 | `.auto-pm/decisions/DEC-20261005-P1INTAKE.json` | 计划新增 | `8ab8591ac9f3a517bd817b6f9126e6dbf73202a80c3cedf890e842e7efd08725` |
| 259 | `.auto-pm/decisions/DEC-20261005-V04RECVY.json` | 计划新增 | `6319c45aa1887bd5a6062dcb4692743df3b144f552d4569e6d3b2df6c50afe42` |
| 260 | `.auto-pm/decisions/DEC-20261006-F01AGUAR.json` | 计划新增 | `1d9b1fb091a5680e8ff7e5a7da09a0a1d8aebba6b303c3ef12b1136046fd9b2d` |
| 261 | `.auto-pm/decisions/DEC-20261006-P1FIXAUD.json` | 计划新增 | `473e2980e5cf0e1df40642d2d880e3a95345157b1952aa605d26d21d69a1eba2` |
| 262 | `.auto-pm/decisions/DEC-20261006-TD2DOCS0.json` | 计划新增 | `13e1e646af67be32d23ae4ee9a0403cf889fecdc76dc083fc4c86e6ea862e8c9` |
| 263 | `.auto-pm/decisions/DEC-20261006-V05AQUER.json` | 计划新增 | `7316b11ff933a45711de1ed3abaa38942e987516cb0a04f901ba2510dd924934` |
| 264 | `.auto-pm/decisions/DEC-20261006-WBS6CAND.json` | 计划新增 | `ea383ba49519ced18e8e7c445d720ebfc33f6bf91708aef4f4e46af21397e97c` |
| 265 | `.auto-pm/decisions/DEC-20261007-TD3DOCS0.json` | 计划新增 | `016b118265ffd01f9c2011f799396be973d98e2b580fd01347e54aa9a774320c` |
| 266 | `.auto-pm/decisions/DEC-20261007-TD3RDOCS.json` | 计划新增 | `5964e30e1ecd20c1c24712035b8e205aa13278b16bfd554a67131052192d2359` |
| 267 | `.auto-pm/decisions/DEC-20261007-V04TTEST.json` | 计划新增 | `8d815dbc2c86f45459bcc144f8767c7cf4e232f34f2d4559ae9c1fdeac3614dd` |
| 268 | `.auto-pm/decisions/DEC-20261007-V05B2R02.json` | 计划新增 | `e2326d3264a93d416c69ef152b03aa17811f8f2600721e810ea7ff896f3a4537` |
| 269 | `.auto-pm/decisions/DEC-20261007-V05B2WIN.json` | 计划新增 | `38292bad5dd8ede35d293d3d2dc5c634a96d1af83b13361a46a979a28363faac` |
| 270 | `.auto-pm/decisions/DEC-20261007-V05B3GRD.json` | 计划新增 | `ba62675bd8156eb31649d238ac87b6e0f2815f7f4527e9c9ae45111bf3bc77a2` |
| 271 | `.auto-pm/decisions/DEC-20261007-V05BDUAL.json` | 计划新增 | `1d5b96838fdd9dbd60e6e9dba03d6308e02166c2ba52ebef97619ad2f9be93a6` |
| 272 | `.auto-pm/decisions/DEC-20261007-V06HOOKS.json` | 计划新增 | `eb4a8a28de6e287cd43e927c7395bdde2755e310b5c981d804425285557e839b` |
| 273 | `.auto-pm/decisions/DEC-20261008-F011SEAL.json` | 计划新增 | `c65a894ec7ee6f11eb2a7d06f7abf97bd93c13dc8748720fa26d416c70c261c2` |
| 274 | `.auto-pm/decisions/DEC-20261008-F02QUER2.json` | 计划新增 | `462722ced530762d7f86ca89f43d89075e2312f932cf97906313fbba5b0f7b1f` |
| 275 | `.auto-pm/decisions/DEC-20261008-F02QUERY.json` | 计划新增 | `709b75929819d59b77a6bef57257163935d9f8c39994e19f27c196e7985a3c51` |
| 276 | `.auto-pm/decisions/DEC-20261008-TD4DOCS0.json` | 计划新增 | `5dbd0860708bba6986cab3827432eff67add68c8b5d2d4d58c7192334cf8cd6e` |
| 277 | `.auto-pm/decisions/DEC-20261008-TD5DOCS0.json` | 计划新增 | `570cdec8e8cd1b051bf783c84cac9f3fe8c98073ecc970327325d8c6745dbb82` |
| 278 | `.auto-pm/decisions/DEC-20261008-TD6DOCS0.json` | 计划新增 | `9e89c8dbea04eeb845ded38fc4712f3d3fd4e1623e8b912c00430d9c59abb3e7` |
| 279 | `.auto-pm/decisions/DEC-20261008-V05B3R02.json` | 计划新增 | `553947606e0fc3fd562fe66552e7331e2780034fb70611240fa0a82b4e916bb7` |
| 280 | `.auto-pm/decisions/DEC-20261008-V06BJUDG.json` | 计划新增 | `f898437d7f9ba2fecc40bb9ead1c558d7520e03c68c9af54221c87b7b986a2c7` |
| 281 | `.auto-pm/decisions/DEC-20261008-V06CJUDG.json` | 计划新增 | `c82872a6a1197b97b4a5287ca6cbae817690b97e0dbbf38babd3753eccc74c1c` |
| 282 | `.auto-pm/decisions/DEC-20261008-V06DHOOK.json` | 计划新增 | `2c9d3d94d94c106806365a7d57d5d918d58533c1af0db39d38a41a75f4a60a9f` |
| 283 | `.auto-pm/decisions/DEC-20261008-WBS7CAND.json` | 计划新增 | `6bb38b1d6834834bfe50795d5d3084f247b9ce730b9fb1a56762975b7ba9ba48` |
| 284 | `.auto-pm/decisions/DEC-20261008-WBS7CND2.json` | 计划新增 | `86debdf08000a0b7206890a21c27249f08f659f3d6dcf4ea33255caadba7c5a7` |
| 285 | `.auto-pm/decisions/DEC-20261009-DINTADJ1.json` | 计划新增 | `4db5e484edc34dfd15f91cc729d474c8451e4e4121eba741bef03c2e31614f4e` |
| 286 | `.auto-pm/decisions/DEC-20261009-DTECHDPL.json` | 计划新增 | `553c2807869e0be26c9946581519a4c3d19e59615972f4397b3c71ea8f24b24f` |
| 287 | `.auto-pm/decisions/DEC-20261009-N1ADOCS0.json` | 计划新增 | `18699ce8ffe6346029b722f781a2b7f3e1b26ee75aab254cd988e1d50ce279c5` |
| 288 | `.auto-pm/decisions/DEC-20261009-N1ADOCS1.json` | 计划新增 | `3e2e77f1a5255739f0facc6f78c192003f1256acd679d1f6455749970c81cfb7` |
| 289 | `.auto-pm/decisions/DEC-20261009-N20SURVY.json` | 计划新增 | `09b285813f6b66db1c5f5a14cc836b7de2bf0fe64ccb55e820f361a63af7df68` |
| 290 | `.auto-pm/decisions/DEC-20261009-RULEDOCS.json` | 计划新增 | `6f763f2f2c003ab2f09ad299294aff92ef6a99f672ee79ef14fbee47d85f7852` |
| 291 | `.auto-pm/decisions/DEC-20261009-SETLV05C.json` | 计划新增 | `8b4981693fe400fbb2a79474cc584cc3d305b40e9ac448e56dbde3af92a87c11` |
| 292 | `.auto-pm/decisions/DEC-20261009-SETLWBS7.json` | 计划新增 | `a82c23be4806b05b75f32e944c07eb2cf5bb8801394ed8726dd61e8559fd1de1` |
| 293 | `.auto-pm/decisions/DEC-20261009-TD7DOCS0.json` | 计划新增 | `77e51ffd6dba06f343ca12b5acbf7d0bebc3af48aaf23bfb4806c9bc3f998252` |
| 294 | `.auto-pm/decisions/DEC-20261009-TIERCLAS.json` | 计划新增 | `2d151d7dad6fb1ac46fe2c5c28ab3b76045d0a188f75018c810873cf4099f63f` |
| 295 | `.auto-pm/decisions/DEC-20261009-V05CGUI2.json` | 计划新增 | `14804a1a3b5521b2f9e4dde02e3e087ba40e9c174c6a964666602cd2090d3013` |
| 296 | `.auto-pm/decisions/DEC-20261009-V05CGUIR.json` | 计划新增 | `4d37f0f6ea5f29818e9ada6b25d3657ebd227bdb838009e6b8270c8db0a6057e` |
| 297 | `.auto-pm/decisions/DEC-20261009-WBS10WRT.json` | 计划新增 | `2beb5780326c2d5f5e43401dd91809c2258362e1bede176092aba85222e7ee20` |
| 298 | `.auto-pm/decisions/DEC-20261009-WBS8FRZE.json` | 计划新增 | `311ec0baf2f1ed817e8737a4c7b1cfab59ba65e04b0bf7119204b56b89b3fa51` |
| 299 | `.auto-pm/decisions/DEC-20261009-WBS9ATTE.json` | 计划新增 | `3a7b2f58579fb4f8d4f30e4352b4950b3ba93fa1dca6cf94ecb59d22bef52f72` |
| 300 | `.auto-pm/decisions/DEC-20261010-CHGIMPRT.json` | 计划新增 | `1ad088280b5ed48a270b95bcb2abf409a53188d97db84ed36847e562105d819c` |
| 301 | `.auto-pm/decisions/DEC-20261010-CHGSYNCR.json` | 计划新增 | `c038f01b79fd02aafb393ed94beb862dc410ccff0be8a946b131f047dd20f09b` |
| 302 | `.auto-pm/decisions/DEC-20261010-CICDLAN2.json` | 计划新增 | `5a727e892224bf547ed02d8a45862739349905b88990a8e392bfd40cf5586cfd` |
| 303 | `.auto-pm/decisions/DEC-20261010-CICDLAND.json` | 计划新增 | `28fd3522827d16e9b8b48c15a4e1ec306d87cba8868b6e8e66dc914db32cd749` |
| 304 | `.auto-pm/decisions/DEC-20261010-GIGNRULE.json` | 计划新增 | `bad94a1b3e6f8996c6b668108663b5ccfa7508b3c4d454d70eefe6624b1ddd98` |
| 305 | `.auto-pm/decisions/DEC-20261010-MRGSIBLG.json` | 计划新增 | `0fc76f4eae4fde9bfddb683afd0b9c17041120b11a12af23f96ddfc482f60653` |
| 306 | `.auto-pm/decisions/DEC-20261010-PLCCHGIM.json` | 计划新增 | `77f8539b86535bca9bd9d3887f69269442e63ad9e29f6626c2d6446b0ff7aa3e` |
| 307 | `.auto-pm/decisions/DEC-20261010-RANNRECD.json` | 计划新增 | `e6c1aef88c1d0ec8eaa43d05f14e7ca6cb3a47b9a364ee8b0ac6d32cb1bc3764` |
| 308 | `.auto-pm/decisions/DEC-20261010-RGOV0INV.json` | 计划新增 | `cd3afa144caefe8f8adbf4e3b6b863d9805013914edfbb35e339280e595944ae` |
| 309 | `.auto-pm/decisions/DEC-20261010-RTAGLOCL.json` | 计划新增 | `bcd4b3c6d7d9b289d9b3076d4c5b6f32af5bc91ae74b6721afb5e9cef4534b5b` |
| 310 | `.auto-pm/decisions/DEC-20261010-RTOOLFRZ.json` | 计划新增 | `578412c902fc3e7ec1d77a23ee8d68f89bef387b60e3ae5bdb615384b6820151` |
| 311 | `.auto-pm/decisions/DEC-20261010-TD10DOCS.json` | 计划新增 | `a365fed59c7a0c31d1461d3a92da5b74ec10a84c58ffee46df2a6f0e2e23a1c2` |
| 312 | `.auto-pm/decisions/DEC-20261010-TD8DOCS0.json` | 计划新增 | `49272a4fe1ad7472ba6086038bfeafcec95d3863c62d334710ea0748c0147da2` |
| 313 | `.auto-pm/decisions/DEC-20261010-TD9DOCS0.json` | 计划新增 | `2c5a4ead0ea7d83b233176505ce97d985ab6a14addea811a7c69e286aa9ab6f3` |
| 314 | `.auto-pm/decisions/DEC-20261010-TRKCHECK.json` | 计划新增 | `c54d2fb179f3acaa4e8c1e467caa474c1485744d8ada42d53a0144821df15c46` |
| 315 | `.auto-pm/decisions/DEC-20261010-WBS11WRT.json` | 计划新增 | `ff140221ab3620f433ac8d4039edc4d02519c757acffe3323ffe0f3f75a3f8b2` |
| 316 | `.auto-pm/decisions/DEC-20261011-CIBASE01.json` | 计划新增 | `b36e0b7540b9b29b743233d36372fcb4755996e3a68a921ecb3dd1e14f5f01a1` |
| 317 | `.auto-pm/decisions/DEC-20261011-CIBASE02.json` | 计划新增 | `14d36f1067ce5f2b2374690fafe555e84bdba163b5a1c33bd844b20fe717b963` |
| 318 | `.auto-pm/decisions/DEC-20261011-ERRA0195.json` | 计划新增 | `1c3e1c5aa7bb1cf81ff7c0006233127dc153a81c5cff37691f737676f63cd211` |
| 319 | `.auto-pm/decisions/DEC-20261011-M3A10001.json` | 计划新增 | `66b37ea43576625cf7f8e16aedc366a21f477ca782c0eca07b19eb210926b5e9` |
| 320 | `.auto-pm/decisions/DEC-20261011-M3DOCS01.json` | 计划新增 | `74a0032991f97dabd5234a445a309873ffdf6eb8c34c4a3e23e316084f122ba3` |
| 321 | `.auto-pm/decisions/DEC-20261011-M3TD1301.json` | 计划新增 | `10dfc6d900abc6fab8b17704fdf2e33f8fb0a9bbd9dfd16154e20fde6d7dc95a` |
| 322 | `.auto-pm/decisions/DEC-20261011-M3WBS130.json` | 计划新增 | `57f7ecf5a8728b5b34250c888043d3ac3cb6cf9257f1819d711c5d2c90fafd0d` |
| 323 | `.auto-pm/decisions/DEC-20261011-M3WBS140.json` | 计划新增 | `6b6159592b703478cd5d500d6f0ccd3949ec58b51f18f310638129e2f37d4bb4` |
| 324 | `.auto-pm/decisions/DEC-20261011-MRGSIBL2.json` | 计划新增 | `ae6fa2244995052238cc2ff432f021f148cc9c87a1697ea97d368009406f1813` |
| 325 | `.auto-pm/decisions/DEC-20261011-Q01SAMPL.json` | 计划新增 | `f74664292e81048a2e9b003699d05159fdcb1fa0e9671a3c71048daaa807fb5a` |
| 326 | `.auto-pm/decisions/DEC-20261011-TD11SYNC.json` | 计划新增 | `3067e0b3459f153e3e25c2dc76d702cb2a8e530be023511784b9a9231c209789` |
| 327 | `.auto-pm/decisions/DEC-20261011-TD12FLIP.json` | 计划新增 | `8bc2458208ad0e137368361989aaadea17317799504c0323e0638689c895735b` |
| 328 | `.auto-pm/decisions/DEC-20261011-WBS12V28.json` | 计划新增 | `053b4c163e070f0673ad05d7d3aa9da4fbd211455442ced49e27fd24b9bbf39c` |
| 329 | `.auto-pm/decisions/DEC-20261012-M3B10001.json` | 计划新增 | `1c0479af27e4eb2b465934a11393d8eeabf4599942568e280a7d4e5cded95c9e` |
| 330 | `.auto-pm/decisions/DEC-20261012-M3CS2001.json` | 计划新增 | `9edb828b2065a8105b55a84c6e07497ba0fa2db81f3fa19db34512d7079e4c15` |
| 331 | `.auto-pm/decisions/DEC-20261012-M3RACE01.json` | 计划新增 | `5cdc0f2b8eda185d33a71a1bdf2a397c819049cf034933eaddb823f954401f42` |
| 332 | `.auto-pm/decisions/DEC-20261012-M3TD1401.json` | 计划新增 | `659580d851c01461758e377ce62a4aa170cdf77d2e05e74f384992d62a442a4e` |
| 333 | `.auto-pm/decisions/DEC-20261012-M3TD1501.json` | 计划新增 | `51853c5b773cf1334f6f7877759a3595d78a8d8e80fe1ac967251968ee33691e` |
| 334 | `.auto-pm/decisions/DEC-20261012-M3TD1601.json` | 计划新增 | `9e9ede0e711f89b6755752ec331ff5c4b5613d33715251cf0bb7b30a26bcf1df` |
| 335 | `.auto-pm/decisions/DEC-20261012-M3V07001.json` | 计划新增 | `1cb4a55f99f5d2f2badf67fff8c5245df983fb82db0bc5d652218f16ee2acc72` |
| 336 | `.auto-pm/decisions/DEC-20261012-M3V08001.json` | 计划新增 | `48b0b451a1b620e6caf114d3083cde11f68c92842528939f35142ce1fbcdaabd` |
| 337 | `.auto-pm/decisions/DEC-20261012-M3WBS150.json` | 计划新增 | `b8b943bea4fbe4c819c8a64510b9cdbd85522c653aa8dc55a144ff5902aa1d8e` |
| 338 | `.auto-pm/decisions/DEC-20261012-M3WBS160.json` | 计划新增 | `da3afd2d2fbed8345c53ad3d12f9230f06770120441bd1c2b844d06887879e70` |
| 339 | `.auto-pm/decisions/DEC-20261012-M3WBS170.json` | 计划新增 | `8776fdcd9f06a806c88155d987eaf681315f3b8445acc20d82afee25a98a45db` |
| 340 | `.auto-pm/decisions/DEC-20261013-M3PLUG01.json` | 计划新增 | `1ba703b27cab446710653a1dcaa0432f535ef08a53343168f7e98df8f0db0d1f` |
| 341 | `.auto-pm/decisions/DEC-20261013-M3PLUG02.json` | 计划新增 | `c2b2116174530fa2fbf417c4aa72419deb57ba06668c69a4ba61c266f2ca785a` |
| 342 | `.auto-pm/decisions/DEC-20261013-M3PLUG03.json` | 计划新增 | `8ce07347220b2d5dde2ae63755169f293233c89d81c8afda80f8aa20fe97fc8c` |
| 343 | `.auto-pm/decisions/DEC-20261013-M3PLUG04.json` | 计划新增 | `8d4deb399e088455f27cc7a45a09c85daf5d7380d4beb8a4bb036139af25fe6c` |
| 344 | `.auto-pm/decisions/DEC-20261013-M3TD1701.json` | 计划新增 | `ffcee693dd153b7244e11474eba7d456e0a9b4931fbf11fa83e497d17253989e` |
| 345 | `.auto-pm/decisions/DEC-20261013-M3TPL101.json` | 计划新增 | `bf02bdd42ff0c2b75c8afff80e8ce132c457eaec00d2195f0eebb8b23d03ec21` |
| 346 | `.auto-pm/decisions/DEC-20261013-M3WBS180.json` | 计划新增 | `5849ee727386947133bad5b9b928bd24829a3e37961f31439510dfedf869161c` |
| 347 | `.auto-pm/decisions/DEC-20261014-M3AGNT01.json` | 计划新增 | `4d5a24488c82456581eb7edcb17730983eb30eba8da6b76d40a58d0a0135cc33` |
| 348 | `.auto-pm/decisions/DEC-20261014-M3D02001.json` | 计划新增 | `1cd4be23fda4095400807c9584127dd11850e1af7567723ce0ac5704423d3974` |
| 349 | `.auto-pm/decisions/DEC-20261014-M3PLUG05.json` | 计划新增 | `a18e49ac6d483ce5e623de1b8178cb6ad0609fa36944ed1721f63af16d8fe76b` |
| 350 | `.auto-pm/decisions/DEC-20261014-M3PRDL01.json` | 计划新增 | `e316b56c2c83661e186fd115f1361392d874ff4a2cbbe8ff9393b8c1f75e5139` |
| 351 | `.auto-pm/decisions/DEC-20261014-M3SMALL1.json` | 计划新增 | `d073578361e5d21ba2f4a4897caae8f82ab95ccffe1a651df3fdc420c3622713` |
| 352 | `.auto-pm/decisions/DEC-20261014-M3TD1801.json` | 计划新增 | `d4cccb7646790f0c2ea486be2194ca2850c679cb69490fc46bd991399d7f05ab` |
| 353 | `.auto-pm/decisions/DEC-20261014-M3TD1901.json` | 计划新增 | `7fed08ab6e76a4e8f5dcf9951e126f9e394e8677fad14db18e3b69c64cb54d9b` |
| 354 | `.auto-pm/decisions/DEC-20261014-M3TD2001.json` | 计划新增 | `e94e74bccba26fa1628dfc4c349775e8f8f68179e6bc063e6e7a44e0e06605fa` |
| 355 | `.auto-pm/decisions/DEC-20261014-M3TD2101.json` | 计划新增 | `0e69a4643371dd75bbd5a2898a6fbc96ae720ad952dbda1b977ec9ab407a1cf6` |
| 356 | `.auto-pm/decisions/DEC-20261014-M3WBS190.json` | 计划新增 | `e35efb59a28c53bfd69528c2e5b95c03f864afb7148664e91afe709734d8d852` |
| 357 | `.auto-pm/decisions/DEC-20261014-M3WBS200.json` | 计划新增 | `122a6463bdcd9ab7fb2111c7ede69d28c68a67c70d5b4852d15e6108b6fcc1f7` |
| 358 | `.auto-pm/decisions/DEC-20261014-M3WBS210.json` | 计划新增 | `91748580e9b8fafcced83507c8b6abf8fb61cac2504c318515f85fdf1f6ef29d` |
| 359 | `.auto-pm/decisions/DEC-20261014-M3WBS220.json` | 计划新增 | `4d35d8402dcdbc8bb308ebbab07686fb30804f73c5f22815f42901c228771839` |
| 360 | `.auto-pm/decisions/DEC-20261015-M3D02B01.json` | 计划新增 | `ff5223ce7a9356d6912c247ade783c945bb57eced93f54fa1f6debfdc5e2a5ee` |
| 361 | `.auto-pm/decisions/DEC-20261015-M3PRDL02.json` | 计划新增 | `b05ccaddf129ae100406b95b9f556d2f52426139ad4199f62044409e8c8ab7e1` |
| 362 | `.auto-pm/decisions/DEC-20261015-M3TD2201.json` | 计划新增 | `74aab4abc9102f6ed54af0a44b30f24ad0d0ff17935c21f53024942d7bd89cb8` |
| 363 | `.auto-pm/decisions/DEC-20261015-M3WBS230.json` | 计划新增 | `8a64dccdbcaa94679611defc31d672bba3a237e9365db23da65038101ff070c7` |
| 364 | `.auto-pm/decisions/DEC-20261016-M3D02C01.json` | 计划新增 | `22f0533405093f4c837e1d0ad941620483edf6a0a4e91a7d4f94dd90cdefd2e4` |
| 365 | `.auto-pm/decisions/DEC-20261016-M3TD2301.json` | 计划新增 | `c071153e8b13145de41bb70024a9eb57265188ed911da1070a2e214faf0aa6e1` |
| 366 | `.auto-pm/decisions/DEC-20261016-M3V04A01.json` | 计划新增 | `24f98fe99e67979c86d53692a5b879390a073969c5a557ce19e432a8ba6cdaee` |
| 367 | `.auto-pm/decisions/DEC-20261016-M3V04B01.json` | 计划新增 | `7032d98c9ca7f50053e9dfa7b9cb2d3099898266fe2d0ef379bc5f81981c2702` |
| 368 | `.auto-pm/decisions/DEC-20261016-M3WBS240.json` | 计划新增 | `d1ee306b5db484fdc192aa7ae8ec7602c51317039fd0c2157884d63ac06223df` |
| 369 | `.auto-pm/decisions/dispositions/20260913/DEC-20260913-D41E4565.json` | 计划新增 | `badd92e04e9755d1e887cdd918fefdee3c1bf57a7c89edbf50658c0ed037e867` |
| 370 | `.auto-pm/decisions/dispositions/DISP-20260914-FA85DD64-01.json` | 计划新增 | `07851c1c6d3f566254c3d7a788a61deba633fb504d55bce94c21f0a020038fa9` |
| 371 | `0100_PLC自动化/DJ-2026-005/11_监控/01_变更管理/02_变更记录/01_版本变更台账.md` | 存在 | `a5d840ab9dab2a35310b3d1de93c42294592356b1492dcaf05244096e4b7303d` |
| 372 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/012_运行身份一致性收口实施卡_PM.md` | 计划新增 | `13623bf061246c4b3f533b11f77c8abf130862f2f29f17a7dbb19305b0d6c9af` |
| 373 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/013_工作区与历史工作树卫生治理实施卡_PM.md` | 计划新增 | `af6fbe002864d0e81efd111264906d19c79f678b81b1ba19bdc1c242fefd76d7` |
| 374 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/014_M2前置知识与工作区治理收敛实施卡_PM.md` | 计划新增 | `db278d7a240674d0407eaae4d31aa5d34454f4c5163eb19c9e4f6bf832062bf7` |
| 375 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/015_实施卡合同与自动化工作流实施卡_PM.md` | 计划新增 | `11288b74730dc6177cda0efc249abd2a49c518a2631b97fdc04dad4770e1f41a` |
| 376 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/018_U04_真实事件进度与失败时间线实施卡_PM.md` | 计划新增 | `37f355e9ed4a5492a66148b04e8d4514e1ec7f648b581074475baedc740f85ae` |
| 377 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/019_H11_历史BLOCKED_Work裁决与活动索引退出实施卡_PM.md` | 计划新增 | `81d1545ecb57e1211e59ea957b9351572a1c242c751137334d280cade1733334` |
| 378 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/020_U04S01_异步一次启动与Canonical活动投影规范沉淀实施卡_PM.md` | 计划新增 | `981cca8cb45ac5d83064ee32591ef4e1a4114cdb71fb278ed95ec3bce72e6610` |
| 379 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/021_控制根与隔离候选运行时上下文合同修复实施卡_PM.md` | 计划新增 | `439031faf44c485028ae633d176c2679d6635f5ab52715fa297c9a50093e66fb` |
| 380 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/022_GitHook候选快照与控制根治理真源分离实施卡_PM.md` | 计划新增 | `3e008f914ce01d88cbe680cede094c1a3cce8efd16a1810c4264c7f8b93e432e` |
| 381 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/023_M2-GOV-BL02_统一基线整合与事件兼容演练实施卡_PM.md` | 计划新增 | `8e61e0ad8e0b71c397d1ddb20efd270274ba960c84a5d1c1caefc0a7cefa9a7d` |
| 382 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/024_治理整改总览与WBS修订1方案_PM.md` | 计划新增 | `a595c82c7ea5f9f99905ad7847e713e734f0582b5f8ef3759a1db60b7f1a715b` |
| 383 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/025_M2-GOV-WBS1_WBS修订1实施卡_PM.md` | 计划新增 | `9f423446a5b71512685906e740ad9a8b9addbd9073dd31b04891679db65c9a47` |
| 384 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/026_M2-GOV-ADJ_裁决合同绑定Git与Decision正式CLI实施卡_PM.md` | 计划新增 | `5367f66cfc57a3022e3d5e42fa937a94f4cc83351bb3e9dcebec300d8d5db476` |
| 385 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/027_M2-GOV-IC02_实施卡开工前预检实施卡_PM.md` | 计划新增 | `6cee8b7c5bea22b2d59ac0c21f954981b62ae49eb94fe6579749a9caaa202880` |
| 386 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/028_M2-GOV-DEP1_开发运行时集成部署实施卡_PM.md` | 计划新增 | `5255537ecdd999852775b26e80c21345614410527a3762bc5ef9e64cb640f121` |
| 387 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/029_M2-GOV-WBS2_WBS修订2与整改交付实施卡_PM.md` | 计划新增 | `d66baf846cf2f8327b93498a8b8fece6bcd5dab5f66fa5baccb50d9b59792910` |
| 388 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/030_U05_恢复同一任务与证据抽屉实施卡_PM.md` | 计划新增 | `269c0093be1c2ce7fc7c4a36548ff5d006e5c1cc67881c0f5948410aa033a31e` |
| 389 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/031_U06_GUI验收与待同步状态实施卡_PM.md` | 计划新增 | `30781b0ac7d2d6e412d9d563adf4c2bbbdacc814af80b6d04a2bb8a81396713d` |
| 390 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/032_U07A_验证与验收门接线实施卡_PM.md` | 计划新增 | `81b08a50f35504ed2a91c7717d35f9cc7dd3d6b57bfd105d8bb9f078a794b99e` |
| 391 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/033_U07B_收尾实质接线实施卡_PM.md` | 计划新增 | `03d05c11f862abc6ed812fad4bf1ac24b9a03e41879a1200d061eaa2bccfe03f` |
| 392 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/034_U07C_薄CockpitSDK与运行身份守卫实施卡_PM.md` | 计划新增 | `039853bba8e2800cb23cb3b5032696a241d06add18387c046378fdab89cc8296` |
| 393 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/035_U07D_GUI开工接线实施卡_PM.md` | 计划新增 | `4d284a5005b65c0a2a2842e6291df601e7b2789775f5b7496fe2bcd24cd573b6` |
| 394 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/036_U08_旧workflow接口兼容实施卡_PM.md` | 计划新增 | `d2788e3cf2a913be02f53746eb45be30fa51a54f1f72a330c9854828b34bb8c0` |
| 395 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/037_U09A_范围卡持久化与按哈希批准实施卡_PM.md` | 计划新增 | `a8b5475a2e02c6d15d5a65722b8a55c8c1e30e39781b252bf094e8362f02cb4d` |
| 396 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/038_M2-GOV-WBS3_WBS修订3实施卡_PM.md` | 计划新增 | `4e68893925fe1b9cf2041aa933335940d4cf21bc286c9bf324312fb8b8f9db47` |
| 397 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/039_U09B_CLI列出草稿与范围卡持久化实施卡_PM.md` | 计划新增 | `df6de8d03816c523667b83baf80712e457cff8ad0afc32a67bc7351ab5858ead` |
| 398 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/040_U09C_驾驶舱批准范围并开始实施卡_PM.md` | 计划新增 | `5c4cd040e6248942fa09e8333ea8f02ffa6eddc18a9a82153bddc0755bdcad63` |
| 399 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/041_M2-GOV-WBS4_WBS修订4实施卡_PM.md` | 计划新增 | `e1d1ba20bc626cc9deeaa344099c8bd0acff12917bede3eef93541de2c5f1302` |
| 400 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/042_V01_PLC静态质量门实施卡_PM.md` | 计划新增 | `dbb04f532449f60f3b157a96d5e11d261f74d70fee06d4e097be43a7a28a1803` |
| 401 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/043_PLC文档与代码一致性核对与自动补全需求说明_PM.md` | 计划新增 | `3fee21e69adfb97f41101e521a8fd291dd75ce23a05a55677e737f8965e7be8e` |
| 402 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/044_M2-GOV-WBS5_WBS修订5实施卡_PM.md` | 计划新增 | `eac33d26168e708c62fcce91f9d76b42c14a9256a4c2097c4792ebb6d7718a32` |
| 403 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/045_V01B_PLC文档与代码一致性核对与自动补全实施卡_PM.md` | 计划新增 | `ed93c8fb9cd014bc64ba9918fbdf5bf8d2aaf7369d5aa7e085753b50b03fd38b` |
| 404 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/046_V01C_基准治愈与升基准实施卡_PM.md` | 计划新增 | `5a53a7f0354033edec2c5ae9893bede10700d3e2f02948243521d0c6800251b2` |
| 405 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/047_V01D_提交拦截钩子与阶段门实施卡_PM.md` | 计划新增 | `241d98a3700af12ad20e0e4e0e25b554b149a14f30974e48f53c5df961f2dcb0` |
| 406 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/048_V02_PLC新需求静态闭环实施卡_PM.md` | 计划新增 | `67ab5cfa24b6dae6609adb57e2ffa08fecbcab5522dddfc114d9e73020f537ca` |
| 407 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/049_M2-GOV-TD1_技术债台账回写实施卡_PM.md` | 计划新增 | `4659e65deb94edb696734e0bcd9e9207a0d38e2762bcdf790920cf79872d9708` |
| 408 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/050_V03_真实更换Agent续跑实施卡_PM.md` | 计划新增 | `fbd566e422095a2054a3f5f6738199ff27311135e69b714e2be9c1711336a1f5` |
| 409 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/051_P1_入口分类与分诊收件箱第一期实施卡_PM.md` | 计划新增 | `1e6fe9796da5b30cd663112bb26a9688a39bb8fd197e406b687518a2dcf1bfe3` |
| 410 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/052_V04_进程中断与租约到期恢复实演实施卡_PM.md` | 计划新增 | `131edf48c03a62e9ff21a41b4e183e6a88c86023dc543deb6b95842b5d36d495` |
| 411 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/053_P1_规划事务与分类证据合同修复实施卡_PM.md` | 计划新增 | `d34b31fd681fda8b53f2b0e0d0ace7f11918bc82b01e75cf9c3d2086905e32d8` |
| 412 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/054_P1_审计缺陷修复实施卡_PM.md` | 计划新增 | `2f6e5de221b350ebf7b3651c8f03a739e4cf7a2d9a2478854237484ca82b26ea` |
| 413 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/055_M2-GOV-TD2_台账归档与规则落库实施卡_PM.md` | 计划新增 | `24751227f6b4cef5bcc8ca864ea30b5144a56ae57afa3b4b8547e32a05166b95` |
| 414 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/056_M2-GOV-WBS6_WBS修订6实施卡_PM.md` | 计划新增 | `ff023e2b3763c8f873923213e4d973bd333e66528368d7937208fc6ecd9dd378` |
| 415 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/057_F01-a_PLC工程标记删除失败关闭实施卡_PM.md` | 计划新增 | `a4f4445c09b2d0b428875198f15e1b4c126314147526a270f57c97a84dd7ceee` |
| 416 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/058_V05-A_共用版本能力查询实施卡_PM.md` | 计划新增 | `a2f53542f5defedba7052fb03bc5494c2c029c452838572752b13099dae5b126` |
| 417 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/059_V05-B_GUI双根与生产线程池接线实施卡_PM.md` | 计划新增 | `40f6423895fd9c87c6a834eda00605a5a4fe7eb25f21cd3bcc92cff555aa58f3` |
| 418 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/060_V05-B2_GUI能力提示与有序关闭实施卡_PM.md` | 计划新增 | `bbe507302d964f4974e3b5a27dc38106880912d888505a1154fa70e095f7d167` |
| 419 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/061_M2-GOV-TD3_技术债台账登记实施卡_PM.md` | 计划新增 | `b440b2dc9fcaad75f33d8934eb60db3e7acbe3e7b3250412d0528f4cd41e154b` |
| 420 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/062_M2-GOV-TD3R_技术债台账登记重启实施卡_PM.md` | 计划新增 | `4637d6a4c43a69d8c15762d6c681e6a5824943d97712bb514eabb8b3541eeb96` |
| 421 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/063_V04-T_e2e测试证明补强实施卡_PM.md` | 计划新增 | `e68ccf2b0541edc0fb2dbf078b3b9e62eb9a3eb4357943f4d9052cb36a422bff` |
| 422 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/064_V05-B3_关闭防护修复实施卡_PM.md` | 计划新增 | `855732043626aa16e6565e04e40e88c7104e6a4e3b16d25aeac8a02366f019e4` |
| 423 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/065_V06_双Hook真实拒绝实施卡_PM.md` | 计划新增 | `a4d675aac4ce8f0e8710fc0a85bc55c5378b4de039cc9db88cecf162aff52434` |
| 424 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/066_M2-GOV-TD4_技术债台账状态更新实施卡_PM.md` | 计划新增 | `5f21aa5e680fdcf566761f3377af9e2f44517941bcd9cd725946d5e1eb19c12e` |
| 425 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/067_M2-GOV-TD5_技术债台账追加三条实施卡_PM.md` | 计划新增 | `b0aa03e8645feadde100015508cf5a1e2d6f8ec10915139f280692aa653f1a2c` |
| 426 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/068_V06B_判卷器入库与反例实施卡_PM.md` | 计划新增 | `7b2132bdd79f71427b68a062e9e09199693e760c2be89badeaafa3bc9f684f35` |
| 427 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/069_M2-GOV-TD6_技术债台账同步实施卡_PM.md` | 计划新增 | `1b57f96742a96c2302f2c367e7e191872a7f0051730f695c743de4eeb5ded50a` |
| 428 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/070_V06C_判卷器例外合同收紧实施卡_PM.md` | 计划新增 | `6f6f7a1df57aa13513413d20a9d08f4194827f533ea6cf370b262c6973a50360` |
| 429 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/071_V06D_钩子测试补强实施卡_PM.md` | 计划新增 | `26d712fd41b2a9b24f4d6ec454de99731e55693ac935b207b82e7f1902a5c98e` |
| 430 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/072_F01-1_关闭封口实施卡_PM.md` | 计划新增 | `35529109574313b3d8d1d15376651fb85ca1e6a7b28d650625f3d2e5cfbff78c` |
| 431 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/073_M2-GOV-WBS7_WBS修订7实施卡_PM.md` | 计划新增 | `7026dd16d8af0d90f325a4f84ae13492e7fdbdf035389d70730eea03baedd9a7` |
| 432 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/074_F02_查询版本字段必填与消费者重验实施卡_PM.md` | 计划新增 | `0045da34359763073185eecf1c8591b3de6834aa13413038c3a9efb90ee3dc20` |
| 433 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/075_V05-C_真实双领域GUI联验实施卡_PM.md` | 计划新增 | `604f3f9f1f6b1e9a629f20fff476c0e5a95efbac188fe0d022e36d735b4d5ab8` |
| 434 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/076_M2-GOV-TD7_技术债台账同步实施卡_PM.md` | 计划新增 | `863daef6881aa2147c0be7ba276e745989b22a8fd581956c8ae77dbaf3309828` |
| 435 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/077_M2-GOV-RULE_门禁分档规则修订实施卡_PM.md` | 计划新增 | `1ac7d8a4dbde32cf7d107b7ca6b277fe64289520bc73f676e465e11ebd3e5044` |
| 436 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/078_M2-TOOL-TIER_分档器实施卡_PM.md` | 计划新增 | `f7f89abc2708b56af4b2f773db72d83dd8629c6bd27c16b01a37fa7e99649a65` |
| 437 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/079_M2-N1A_驾驶舱角色与边界说明文档实施卡_PM.md` | 计划新增 | `8c4c83787f566cc7d9ed270da3012952baf566a881cd10f9d4831aa9575c9736` |
| 438 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/080_M2-N2-0_只读勘测实施卡_PM.md` | 计划新增 | `911c0c9f0c99087a9cfc190b9a2aabfa1a15c8999d5758296c3242144f983cf1` |
| 439 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/081_M2-GOV-WBS8_WBS第8次修订冻结实施卡_PM.md` | 计划新增 | `5644c54fc95d27d022a87a9d4794adfcaf1f4eb5e84450d166c6e4ba20ba56ad` |
| 440 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/082_M2-DEP-INT_ADJ与IC02整合实施卡_PM.md` | 计划新增 | `a183be0e65eea8042b1de4d312ff26ebc54dc3ba3fd94a09f841db4db2d47c0c` |
| 441 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/083_M2-GOV-WBS9_最终提交证明与状态写回实施卡_PM.md` | 计划新增 | `037cc8707f60081199a68bcc2d563dfbab3eca0ae941d219d1629798033b23ad` |
| 442 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/084_M2-DEP-TECH_开发运行时技术性部署实施卡_PM.md` | 计划新增 | `c4201956a4dd68db04be61a02f23888478d4fa20a961645d825d2d8f51e19024` |
| 443 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/085_M2-GOV-WBS10_部署与推送状态写回实施卡_PM.md` | 计划新增 | `32100f627f0f856f20ae3b420c07c49b373978877400edd4a75d00fd35b2a1c5` |
| 444 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/086_M2-GOV-TD8_发布治理债务登记实施卡_PM.md` | 计划新增 | `98f08b5b2877aca088d7607eafc9b615bfc2e9fa7ce5f174dce5f380ccfaa19d` |
| 445 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/087_M2-RGOV-0_发布资产盘点实施卡_PM.md` | 计划新增 | `d00570821a7ec8fcccb997a7e77995f6e594cb7383227354b88e459dc9550198` |
| 446 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/088_M2-GOV-CHGIMP_治理记录入库实施卡_PM.md` | 计划新增 | `55d38d1d05aa67aa37f24397986ff78de5a75e2d95d3cb79a2ae2269724e79b9` |
| 447 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/089_M2-GOV-TD9_发布治理债务更新实施卡_PM.md` | 计划新增 | `d4aef3a4216a3096f31a0b750f4ea8d515fd62f5a75bb46e90d2b78a5baf0b9a` |
| 448 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/090_M2-RGOV-1_本地只读release源码tag实施卡_PM.md` | 计划新增 | `67d33e57f27e5617e57308205d213429fbc41b1b5eee164dbc2ec826173aa522` |
| 449 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/091_M2-GOV-RANN_release更正与标注记录实施卡_PM.md` | 计划新增 | `a43f5d4e31c2c10ef349e9a9408f66d7cfdf7b5ea9af4dd4e1317f42c3db93e0` |
| 450 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/092_M2-GOV-RTOOL_工具链冻结实施卡_PM.md` | 计划新增 | `468d818826de2d63ede2bf7533e22dac76462678b9d0fd21d9c9bb4e2afa0a4e` |
| 451 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/093_M2-GOV-TRK_变更单入库检查实施卡_PM.md` | 计划新增 | `49153529228692b80a716895011b5a15731b5726981e59b850bf1dfa2b6b2448` |
| 452 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/094_M2-GOV-GIGN_忽略规则补洞实施卡_PM.md` | 计划新增 | `86e1b84e0c588e8eafd86c8838392b8fedb4ed1f5835a2bc6ca140f930c783c6` |
| 453 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/095_M2-GOV-WBS11_发布治理批次状态写回实施卡_PM.md` | 计划新增 | `560075dcc5d6bd2f2289b02a4615e4c94a210c131e244e6597423ef29ad6b3a4` |
| 454 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/096_M2-GOV-PLCCHG_PLC变更单入库实施卡_PM.md` | 计划新增 | `373f22122b0aa1b62121a68eaeaf74f45d6199cd423f8cc86014deff80b85492` |
| 455 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/097_M2-GOV-TD10_技术债分诊同步实施卡_PM.md` | 计划新增 | `720144634518d59205c0653718c1fae568c2cb808c7904f1a47fa889516de784` |
| 456 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/098_M2-GOV-CICD1_CI最小版落地实施卡_PM.md` | 计划新增 | `32165e9ed623bb29a079558dd476c65c8c469e0567fe53dfd93cb8d5ad6d6702` |
| 457 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/099_M2-GOV-CHGSYNC_变更单补入库实施卡_PM.md` | 计划新增 | `3b7880cc58daa8edd857198dbd032f359d75dffb024d9481e04710eba94fc05c` |
| 458 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/100_M2-GOV-MRG1_兄弟分支合并实施卡_PM.md` | 计划新增 | `523917dc88e9624cdcfca849af1f9817d3bf1855bb66b1c84bf4bbec72d42829` |
| 459 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/101_M2-GOV-Q01_vartable真实样例入库实施卡_PM.md` | 计划新增 | `97e46aff9cb554bacb841019dc854ef0866a4ba7fe129073831ee4ae6adf46f0` |
| 460 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/102_M2-GOV-ERRA_CHG195勘误实施卡_PM.md` | 计划新增 | `4688b21084e525e21a65db9b67404190d3f691f7d2bbf82fa7a5f58e949be3df` |
| 461 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/103_M2-GOV-TD11_技术债台账同步实施卡_PM.md` | 计划新增 | `2d38e1fe5c38b793532b0e3cf3f0f4ce0c0fe15497a704f4c7350cb923674c39` |
| 462 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/104_M2-GOV-WBS12_WBS修订12实施卡_PM.md` | 计划新增 | `b20b4316de557eb7d3a9d732663671fbeb364c7c97c174132df8a16b0c73c79c` |
| 463 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/105_M2-GOV-TD12_台账状态翻转实施卡_PM.md` | 计划新增 | `50482eb8b080212cd30424fc3b310997453d9d74a9a11e9bdd4536c06d2fb022` |
| 464 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/106_M2-GOV-CIBASE_CI基线刷新实施卡_PM.md` | 计划新增 | `30c838bf43af35fb2deb662664eabee474ec70665f8ac9fa53a0e3f31d22844c` |
| 465 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/107_M3-A1_指引修正与夹具健康及mypy修复实施卡_PM.md` | 计划新增 | `96a818ba1e19b45524ecfdef107b735e64038d0e3680e03087c4bd76adef425a` |
| 466 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/108_M3-DOCS_文档草案采纳实施卡_PM.md` | 计划新增 | `4168609401c06b9fed63feb12b1e025ff3c58b878e554605ed368ff78800fa93` |
| 467 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/109_M3-TD13_技术债台账回写实施卡_PM.md` | 计划新增 | `9a9c1bd0c0fe3dd41ad75b5f0fef94d28275fba0bb428c786c185135bf406cf2` |
| 468 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/110_M3-WBS13_WBS修订13实施卡_PM.md` | 计划新增 | `8974417bca471f030cf3b3c9e3a2a4e0b5cf41898059c4f75f639aa9a725f29e` |
| 469 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/111_M3-CIBASE2_CI基线再刷新实施卡_PM.md` | 计划新增 | `a4bbe5756f9c7dad6d550a738407164495c942fdaa808fa90e3dd75fed84e840` |
| 470 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/112_M3-WBS14_WBS修订14实施卡_PM.md` | 计划新增 | `c65a71aeba32d781abb3dbab3b6d67b1ef3884bd74456f1af393d0356b574b89` |
| 471 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/113_M3-TD14_技术债台账回写实施卡_PM.md` | 计划新增 | `94123b21a2324a947cd573ff02dc5a454f44f46f8ca7e53b83498ad1be25279b` |
| 472 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/114_M3-WBS15_WBS修订15实施卡_PM.md` | 计划新增 | `792ab125757cd537d20deff08cfd3a17da58708a89036e186d49d8a97b951c0c` |
| 473 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/115_M3-RACE_边车竞态修复实施卡_PM.md` | 计划新增 | `9cd2cea6ce9cb1954fe564699245f301635021cf1abaaccfc1d3ef561b070c58` |
| 474 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/116_M3-B1_存储哈希函数提取实施卡_PM.md` | 计划新增 | `80ee4602bac599779355a950e6f78d1ad277cc571237b5f30a17d8ea5a42b73b` |
| 475 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/117_M3-TD15_技术债台账回写实施卡_PM.md` | 计划新增 | `3a6cd1a9f51e94f5ccd76681b05645013a5994e1765e0ed96bb54d273a8c0a35` |
| 476 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/118_M3-WBS16_WBS修订16实施卡_PM.md` | 计划新增 | `505c2148d64e23331002718d4c2accacb944b17357975b17a39cbba2d70e0b50` |
| 477 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/119_M3-CS2_变更单补入库实施卡_PM.md` | 计划新增 | `1ce7bf93589242ed1ed6651ddea72a60235c16aa7e4a6e34b7e8bc54437d5455` |
| 478 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/120_M3-V07_Python模板验证实施卡_PM.md` | 计划新增 | `f8e271fc6c71b8091da48f8efba42382f34e2f2101bb64c878c330e7911b1f13` |
| 479 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/121_M3-TD16_技术债台账回写实施卡_PM.md` | 计划新增 | `41efcf63fef37304cf83b4a622c07ec43766fdf3a890a09881f095f57e1b2bcf` |
| 480 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/122_M3-WBS17_WBS修订17实施卡_PM.md` | 计划新增 | `b02215e590852390d5d4513a2a0b9ac52c62ca3047dcd13e3fc917e6348e7bf8` |
| 481 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/123_M3-V08_PLC模板验证实施卡_PM.md` | 计划新增 | `61935f217a47afe65b4acc801b1b827f749ee8838ae3615aafd049a9e4271df3` |
| 482 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/124_M3-TPL1_PLC模板修复实施卡_PM.md` | 计划新增 | `e7768a094dab09fc2659dd35daf00ac69dee151eec385bc010c82616c8bb9377` |
| 483 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/125_M3-TD17_技术债台账回写实施卡_PM.md` | 计划新增 | `56557a3b6def2c46de8945499076d1f0052bb60e0eec3353f7ae5499c61b61b4` |
| 484 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/126_M3-WBS18_WBS修订18实施卡_PM.md` | 计划新增 | `edbc1e3d870f3e88eb3050a6a301c25e4ad4a000817c8da540ee6ff93fea7df0` |
| 485 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/127_M3-PLUGIN_插件命令行接入门禁实施卡_PM.md` | 计划新增 | `2fccf1699462c86d134c703c72c33587f955c3be2b4f9f9f4ed8d7e87bb064bd` |
| 486 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/128_M3-TD18_技术债台账回写实施卡_PM.md` | 计划新增 | `5e9cc92316627590e0f16752bf18f60f11eab5afab296c7cbaec99615ad9c2d0` |
| 487 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/129_M3-WBS19_WBS修订19实施卡_PM.md` | 计划新增 | `9ef6fb0c2e385e52e54c36cc5e99a8e503b6a81ce7c23f55f54b82c2d377ba03` |
| 488 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/130_M3-SMALL1_检查项标签台账字形小修实施卡_PM.md` | 计划新增 | `b5403101c78179b7cf2d835ec5eca1a16f3e37531696e0b3ad2d42f412df5a8f` |
| 489 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/131_M3-AGENTS1_AGENTS措辞更正实施卡_PM.md` | 计划新增 | `1f48f21ebb4c124fa4b6b88d31679dbc973f39d6637dfd32c03c8aa0f35bbfe5` |
| 490 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/132_M3-TD19_技术债台账回写实施卡_PM.md` | 计划新增 | `587255f52f15d6479652b8692d276f6cdb213c40ce425bd20accdbcdf248f75f` |
| 491 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/133_M3-WBS20_WBS修订20实施卡_PM.md` | 计划新增 | `f67cf8a7f1e19eb19bf7d7b6bcaad0030f14539582280107cade832626badd5f` |
| 492 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/134_M3-TD20_技术债台账更正实施卡_PM.md` | 计划新增 | `cdd998deae373630b161da8ab3de1ec8b9bf6294d783c60ecb4b62dcaf3ebffb` |
| 493 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/135_M3-WBS21_WBS修订21实施卡_PM.md` | 计划新增 | `27675b33655859cd0c1dc0e6ee23d3ab8abd2bbe6999b7f3a84bb013a7f3af33` |
| 494 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/136_M3-D02_可复现构建入口实施卡_PM.md` | 计划新增 | `4ab6219ecc31ea38372ea99f1715697a60a42ed8288aaa0b0fc1246914f9ca63` |
| 495 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/137_M3-TD21_技术债台账回写实施卡_PM.md` | 计划新增 | `a26d2fcc1052dea0015f3896adde60936858ba712e82b99f6782f0e3e275e634` |
| 496 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/138_M3-WBS22_WBS修订22实施卡_PM.md` | 计划新增 | `b3fb06c08118ac55db52f406505357f4e97b9b6375aaea892629e329e1575fdd` |
| 497 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/139_M3-PRDLAYOUT1_PLC模板接口文档三层分工实施卡_PM.md` | 计划新增 | `86e65436e5e56c6785ff03acfbb4673fc789b1362fc3b0a51cb3dc4997739552` |
| 498 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/140_M3-TD22_技术债台账回写实施卡_PM.md` | 计划新增 | `86a131d851f7e3f1c0dc930fdaa00b77c8634ab73361c86ef2879a682b8e3dba` |
| 499 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/141_M3-WBS23_WBS修订23实施卡_PM.md` | 计划新增 | `3ad7cb19bee2c8f754c4681a85595a0980b7b70c504373b103798a1fdf899847` |
| 500 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/142_M3-PRDLAYOUT2_驾驶舱接口文档对照与修复器实施卡_PM.md` | 计划新增 | `a91bc2c04ca5a074c21017f469a9539b06e29db9cec22edb890ec229809f44bf` |
| 501 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/143_M3-D02B_构建入口收尾实施卡_PM.md` | 计划新增 | `b64e49dab05b49779ba426014e3e710120f92aa783ccb59780ef1d87d1dd822a` |
| 502 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/144_M3-D02C_审计发现修复实施卡_PM.md` | 计划新增 | `f37549f253f4c020aaf232d77953c0463b1c59b5908b6513183e2068637619c6` |
| 503 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/145_M3-TD23_技术债台账回写实施卡_PM.md` | 计划新增 | `8dedcbb34380ce13d70ccfd8928878b6617fffcb5c999a790551b3466523ae2c` |
| 504 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/146_M3-WBS24_WBS修订24实施卡_PM.md` | 计划新增 | `2854a3c31853ce7750a8c1c55d124f9db29354f597b7ac71b7c032abb8cccb92` |
| 505 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/147_M3-V04R1A_租约回收与写入epoch契约实施卡_PM.md` | 计划新增 | `41df4926e0513400e35edac61a51324dad1f2f9c7f9c4a4029d984bf38d86ff4` |
| 506 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/148_M3-V04R1B_契约更正实施卡_PM.md` | 计划新增 | `673402ee4716bf300dfca8e1372945957a8bd049aa4084cfc84a25e28d8bb158` |
| 507 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-044.md` | 计划新增 | `7ff810d4113c759b338b62c8bfaeb72c767938929e5c6277d10ad0845c640183` |
| 508 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-045.md` | 计划新增 | `1b7438757859e239d151e004f33435c803805015e6f4e1a240d04e4e384150e9` |
| 509 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-046.md` | 计划新增 | `524547f70348ee5cd68943b96287598721bb0e6d5e2867a47a408fb6ee9d48c0` |
| 510 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-047.md` | 计划新增 | `78a0be6eb41a068771528b820c4db16825e714280a81af1a4d7313212e944010` |
| 511 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-048.md` | 计划新增 | `62d88f47c2c0db7c63678ce6dc60006b765df331ca3f301df28fbc01a085c977` |
| 512 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-049.md` | 计划新增 | `800d937bd5a6d72a629d70b3fceb4bbb5fe2850956e9e3fbb822dfca471ab0d4` |
| 513 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-050.md` | 计划新增 | `314ac90d18e8bd066402709b3931c39061ed378e40dcfe99ccf2ab969491f39e` |
| 514 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-051.md` | 计划新增 | `5a8ddb984c7212c40d1df4d50beaf0919992f58e1626784dde58d6ef6296cbcb` |
| 515 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-052.md` | 计划新增 | `2cabed15c4b435e68c8bab175d87c4e63c4687ac69ab2466e087f2ae58488a6a` |
| 516 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-411.md` | 计划新增 | `2d48d44cdb54a21bae98eb5851963c19b9962731a2257438d9e00850c328ebde` |
| 517 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-412.md` | 计划新增 | `816b2d2f831fce8e8cc87a334fb7c3ced3eb822e6ea7fa55d3fcb6730c5a60ed` |
| 518 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-413.md` | 计划新增 | `526d6588c06f55dc7b84bbdfdb36838b0a1f1a1ccb4dda6d4b86c2e19dd628d0` |
| 519 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-414.md` | 计划新增 | `930e7bc2e637322319b0fbea924139b10acd62849c9d9c9b5e611ad597297910` |
| 520 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-415.md` | 计划新增 | `25b9be388d364a491b9c4ca38c6e02c8a3d3f6562f0e2343b9e2e15a16cb4203` |
| 521 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-416.md` | 计划新增 | `4d781b6d267cc7343de7ca8fcb9e731c0c6e726a66c564e2b17a9610d1bb1b00` |
| 522 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-417.md` | 计划新增 | `abecc623a2e9ff7b7048efa7e285cc0dfe815da43f5302a5137c72b2057fa76d` |
| 523 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-418.md` | 计划新增 | `561474c8473fca5b674649b8b45295a2956ed48bdff8ece05c9073316ca9abf8` |
| 524 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-419.md` | 计划新增 | `30f56f64336d25e1393bf89c8a27df87b4e1e0f4f906c366bb20c12cf77c15e8` |
| 525 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-420.md` | 计划新增 | `ad45cbed82348876f17b75b393690cb826413d680c23aff4e14265b79cca8536` |
| 526 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-421.md` | 计划新增 | `3f098d074cf46e899b39c6366c2e0a5679913a81b49cfb2e4c7fda1a5d618426` |
| 527 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-422.md` | 计划新增 | `0474946aaa6373f3f7889cebfa9c838e7178126b67214da47c69b2388042184e` |
| 528 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/01_变更管理/02_变更记录/01_版本变更台账.md` | 存在 | `1c643caae8c6aeb960b679f35b683c8e115ef04db4fc14753dec5dcbee0127ab` |
| 529 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/04_监控/02_整改项/控制面事故登记台账.md` | 计划新增 | `8ed89687ce5cc7694fac1a1ce811d5ab9eee57be8dde1d8874e2f0aba7b8232a` |
| 530 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-009_英语学习助手/04_监控/01_变更管理/01_变更单/CHG-SAFE/CHG-SAFE-2026-001.md` | 计划新增 | `2108b281eef1e4c4c257ef716dc978d5f91dcbec611745284fa92d05ffaa72eb` |
| 531 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-009_英语学习助手/04_监控/01_变更管理/01_变更单/CHG-SAFE/CHG-SAFE-2026-002.md` | 计划新增 | `544b9331e258a320dd613c1e393f0bedf26455d8257315e0eeca7c9fb0a5fde6` |
| 532 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-009_英语学习助手/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-004.md` | 计划新增 | `07723362e9d63a48a45e6e0d6165189aedf2fb1e48d896a4c2794f49f947a862` |
| 533 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-009_英语学习助手/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-005.md` | 计划新增 | `bd2096795e2598c7fcedb6fbf9747ea3fdac9e133322d13cd333cc3a7226e2e3` |
| 534 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-009_英语学习助手/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-006.md` | 计划新增 | `69f4f01b8a86bd12e39a7fd041ab4bc19a4dd6ca43d465032ebb39edff5421f2` |
| 535 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-009_英语学习助手/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-007.md` | 计划新增 | `d1c6ba92c04993736af6a60363915affc9a9c984b8486d72aa2f8aab3b7160d6` |
| 536 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-009_英语学习助手/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-008.md` | 计划新增 | `625b3d6cedaf77e9d8294552392ed7f7e7368dcdac704038b28fed1abfab1f2b` |
| 537 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-009_英语学习助手/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-009.md` | 计划新增 | `b0bf63e34b89a9bbfa582f56f92c9ca13bc27c831db6723a4dd633c76b42c2a0` |
| 538 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-009_英语学习助手/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-010.md` | 计划新增 | `3c543bc68d505de545b2b28e978303fdb7067057e0822df4b87d508bddcbf61f` |
| 539 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-009_英语学习助手/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-011.md` | 计划新增 | `ac137e785e4fc9af38be4933992ee181c4ca40c6dd9ec1f15922c9fc96c74f56` |
| 540 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-009_英语学习助手/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-012.md` | 计划新增 | `52a7b458cbfc02c7e41484666445871fb4947caae23351f2c89ebcb4adfcdac9` |
| 541 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-009_英语学习助手/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-013.md` | 计划新增 | `1e9bac8f72606fcc2d70f70000a8ca7f6add4e29dde1a37e6916ee1d2235ede9` |
| 542 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-009_英语学习助手/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-014.md` | 计划新增 | `a247f0f4993556afa5790c53629c2d4535f80855a923dcc4f422cad08a16471f` |
| 543 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-009_英语学习助手/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-015.md` | 计划新增 | `e78e8f47b1fbfd7a73c7e90d2c7beda1181ed81fad1d9242ee3e5e657ffecd96` |
| 544 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-009_英语学习助手/04_监控/01_变更管理/01_变更单/CHG-SCPT/CHG-SCPT-2026-016.md` | 计划新增 | `bdd46134c1107cb7c4fcd19c91f8b260ca61866c25e3c53569803b9a8a004f4c` |
| 545 | `01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-009_英语学习助手/04_监控/01_变更管理/02_变更记录/01_版本变更台账.md` | 存在 | `86c71d5a75efe6f1371c146c6c0e96ea101141926c4429484eefc00ae61ef775` |
| 546 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/archive/PMF-20260912/03_分阶段整改路线图_PM.md` | 计划新增 | `2dad6fc641c620eaf08e83091c05c829be857b8bba9240eb47409bba9e275438` |
| 547 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/archive/PMF-20260912/07_SW-2026-008_驾驶舱Dogfooding迭代方案与WBS_PM.md` | 计划新增 | `9dc6eab5c8c50bca8f4618718185e5a852d3fbcfd4ce1caa852d2d3d973665ed` |
| 548 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/archive/PMF-20260912/12_SW-2026-008_PM驾驶舱强制闭环_对话交接_PM.md` | 计划新增 | `299fa6296d4d8434a87f054b7a507ed8ea395a3287c668bb4baeb351cbdaeec7` |
| 549 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/archive/PMF-20260912/15_SW-2026-008_驾驶舱强制闭环_后续WBS校准_PM.md` | 计划新增 | `6e23c8651ac555e33816b9eea863a175821f9b22eea1d9e1763b1151e8d00635` |
| 550 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/archive/PMF-20260912/17_SW-2026-008_研发母体稳定部署_重制实施方案_PM.md` | 计划新增 | `ae3ab851f3ec5007805adbb125e9b00c16d93139e8933e2e4f44139a4f8a0f4f` |
| 551 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/archive/PMF-20260912/18_SW-2026-008_切流回退与问题移交_GEMINI.md` | 计划新增 | `9bc908ea90026f820f96f434c3c91a3b8f20110cb974466d2e41aad614c29e8e` |
| 552 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/archive/PMF-20260912/18_SW-2026-008_旧方案历史治理索引_PM.md` | 计划新增 | `acfcb73f87159267986e4207f9c86013d7230169656cb331d3968b5612adaa57` |
| 553 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/archive/PMF-20260912/37_Cockpit_OS_超级特种兵大一统目标架构与迁移总方案_PM.md` | 计划新增 | `99bef693f25af3b8deda6c20ebf8a77af79913eeb57612c903af5d733c380a53` |
| 554 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/archive/PMF-20260912/39_PM-Flow_恢复与可用化总方案_WBS_PM_V1.0.0.md` | 计划新增 | `f89ae4bf6f96915f4c85b5581c48bac80090f52f7687f9b2fd368cc78f682d6f` |
| 555 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/archive/PMF-20260912/PMF-20260912_文档归档台账_REP.md` | 计划新增 | `e5be2d3901d84730935a5617064935c3b9cd42bfaaa999991c0fec7dac0eefdd` |
| 556 | `SYS-2026-001_WorkspaceGovernance/01_项目文档/archive/PMF-20260927/V2.6.3_ARCHIVE_POINTER.md` | 计划新增 | `8012ccc908f784d3c45381ff5ff94d0ddf9afd6ca867a6ef8bae35ba90a44306` |
| 557 | `SYS-2026-001_WorkspaceGovernance/04_监控/01_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-041.md` | 计划新增 | `1858eec8da9acec24a50ea0aab4ca537acbab160e51b41ca45dcab7b20231b08` |
| 558 | `SYS-2026-001_WorkspaceGovernance/04_监控/01_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-042.md` | 计划新增 | `2f194cf4db4bfe935420a8292a3ceb3e7a6c2fb417381310379a0154857f1b84` |
| 559 | `SYS-2026-001_WorkspaceGovernance/04_监控/01_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-043.md` | 计划新增 | `ec216a43ab5c1444dff456ce9ef56de9e081c3c60970466c2c1ab070bb1e8d43` |
| 560 | `SYS-2026-001_WorkspaceGovernance/04_监控/01_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-044.md` | 计划新增 | `671a908583b0f75dd156b88a024524f7b81eaa955b94d8b3585a1adfa11ee878` |
| 561 | `SYS-2026-001_WorkspaceGovernance/04_监控/01_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-045.md` | 计划新增 | `626d034aade6061cab1310a06717410176b58cdd530b623fd3731b2670e87579` |
| 562 | `SYS-2026-001_WorkspaceGovernance/04_监控/01_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-046.md` | 计划新增 | `1ea12d16d30bee9b7b33291d935dacf66769ef56bccb190349d10f5c16e86800` |
| 563 | `SYS-2026-001_WorkspaceGovernance/04_监控/01_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-047.md` | 计划新增 | `9d7c69d1751ec9bb2350977ad34c12eda33a9d7b7098463cc9dba78ab3e8374a` |
| 564 | `SYS-2026-001_WorkspaceGovernance/04_监控/01_变更管理/01_变更单/CHG-DOCU/CHG-DOCU-2026-048.md` | 计划新增 | `e9448fdece24f52dbf08bef816239ba1f33e4def1ddf124033921e831d71ff69` |
| 565 | `SYS-2026-001_WorkspaceGovernance/04_监控/01_变更管理/02_变更记录/01_版本变更台账.md` | 存在 | `36133ab63a9c285f4ca27b3692176f63f79b2b3aadb43015476aa1a19ca0adff` |

### 5.2 冻结工具

工具与脚本在 `.auto-pm/reports/m3-hygin1/`；清单文件 `reference_manifest.json` 的 SHA-256 为 `de33490871c8fa10d879b9056f22f75666dce91a33f320f6e26d23874cb9f8dc`。G2 的基线是卡 148（M3-V04R1B）受治理执行的九组真实输出（`.auto-pm/reports/m3-hygin1/baseline_g2/`，同一产品字节）；期望：每一组与基线逐项相同。

| 工具 | SHA-256 |
|---|---|
| `adjust_counts.py` | `b0662948d52b927db2ba88232b20550616efeb572bdbd129472bb79cbee3ca1d` |
| `check_bytes.py` | `c6317beda165ea955ad769e639c0ec2160e5e935c144c3c2e0e397081dbe28e7` |
| `commit_msg.template.txt` | `e62209a90295bd4e6395fa2875274f6803a6100a52bf9c733673a92a7cd617cf` |
| `gen_project.py` | `eac50737f52b35b23b3c9b23583ac819940a042f71109f9cc96ceaa435e06565` |
| `hygin1_config.json` | `332ec809ae53cf4f8e96d8874a6e4e427397c197a59c59ed3f40e0ee059112de` |
| `hygin1_gates.py` | `08d858b1fdf6d4751e4b99175838f65d3baff11e6dfe94a4017729938afec983` |
| `hygin1_gates_all.sh` | `1575cb428a82f09916bbc4272058e1b9aa38f1fa547ad8564ae64395680819e4` |
| `install_files.py` | `c59264b22842f7e4c0a2f1a2a2c421ca7d56b04bbc8764652ca29eb8d6da69a8` |
| `run_g2.sh` | `6956748a33added47bde7bca81e837230d6e461e746f48da7a0770499cd578fc` |

## 6. 门禁矩阵

产品档。顺序：基线测量（身份、文档检查、台账对账、健康测试）→ 安装冻结文件 → 快速门禁（候选文档检查与对账、健康测试、内容合同、负向对照、四棵产品树、真实 pre-commit 钩子干跑）→ 九组回归（G2，十个输出）→ 瞬时竞态测试的三次隔离重跑（仅在其于组跑里失败时才被判卷采用）→ 判卷。任一非零立即停止并保留原始证据；正式 Run 完整重跑，不采用演练结果。

| 门禁 | 内容 | 通过标准 |
|---|---|---|
| G1 | 基线身份与健康测试 | HEAD 为基线、工作树干净、新增路径不存在、4 个台账为基线字节；夹具健康、冒烟、导入测试在基线与候选都全部通过且数目相同 |
| G2 | 九组回归（rest、application、plc、change、contracts、infrastructure、qml_debounce_alone、cli、qml、core） | 与基线九组输出（卡 148）逐项相同（失败集合、通过数、skip 数、无 ERROR）；产品字节未变，所以任何一组的差异都是失败。唯一容忍规则见 §1 第 6 条 |
| G3 | 文档检查与台账对账 | `doc check`（根入口，显式传控制根与候选根）在基线与候选都 exit 0；SW-2026-008 与 SYS-2026-001 的 `ledger reconcile` 在安装前后都 exit 0 且 0/0/0 |
| G4 | 内容合同 | 变更集恰为冻结的 565 个路径、字节等于 §5.1、LF、无 BOM、UTF-8、无密钥格式的值；每个 Decision 是合法 JSON；基线台账行 ID 一个不丢；台账里没有无文件的行；每个新增变更单在其台账里有行 |
| G5 | 范围与字节 | 变更集恰为 565 个路径、字节等于 §5.1；HEAD 为基线；安装前工作树干净；无残留文件 |
| G6 | 产品字节不变 | `auto_pm`、`templates`、`tests`、`scripts` 四棵树与基线逐字节相同 |
| G7 | 隔离与钩子 | 真实 .git/hooks 前后字节相同；无遗留 python 进程；真实 pre-commit 钩子对暂存的 565 个文件退出 0（临时索引） |
| G8 | 负向对照（10 个） | extra_file、missing_file、byte_drift、ledger_orphan_row、secret_injected、ledger_base_row_deleted、wrong_kind、file_not_in_ledger、crlf_flip、decision_not_json 各被其目标断言拒绝 |
| G9 | 最终范围与字节 | 全部门禁之后字节与变更集不变 |

判卷由共用判卷脚本再核对完整 G1–G9、card/base/run、报告映射及文件 SHA。

## 7. 实施授权签字门

| 字段 | 当前值 |
|---|---|
| 实施批准 | 用户 2026-10-16 说“你的其他建议全部批准”“允许夜里推”“允许夜里执行”“今天晚上继续作业”，2026-10-13 说“替我收口验收”（原话记入 `.auto-pm/reports/PREAUTH_M2_20261008.txt`）；**本卡 SHA 报给用户后，由用户在聊天中回复批准**才启动。条件：卡 SHA 先在聊天报出、卡字节等于该 SHA、机器预检通过、范围不超出本卡路径、任一门禁失败即停下保留现场、不开第二轮；止损照旧 |
| **内容验收** | **用户阅读后确认；不委托。变更单收口脚本只在用户确认之后运行** |
| 审批人 | fubai |
| 执行模型 | claude-sonnet-5-5 |

本卡不包含自身 SHA。卡、基线、范围、冻结文件或工具变化均须重报 SHA，不沿用批准。

## 8. 治理顺序

0. 启动前核对本机负载：无游戏/启动器在前台，近 10 秒 CPU 占用低；有则等待，不启动。
1. 在聊天报告最终卡 SHA 与摘要，随即启动（预授权范围内）。
2. 创建 SW-2026-008 DOCU/OPT 变更单、匹配 Decision（`DEC-<当天>-M3HYGI01`）、Work `WORK-SW008-M3-HYGIN1-001`、Run `RUN-SW008-M3-HYGIN1-001`（租约不超过 3600 秒，续租循环**用绝对路径启动并确认续租成功**）。
3. 从基线建立全新正式候选：控制根下 `.auto-pm/worktrees/m3-hygin1`，分支 `codex/m3-hygin1-records`。
4. 安装冻结字节并完整重跑门禁（`hygin1_gates_all.sh`）；先创建 Checkpoint，再正常 Hook 提交，绝不 no-verify；核对提交父、范围与 blob。
5. 依法推进 Run/Work 技术终态，对账 0/0/0；按委托收口变更单。

## 9. 硬停止

基线、工具/卡/Decision 指纹、冻结文件字节、owner/scope、lease（含续租失败）或 hook 漂移；新增范围；任何门禁失败（§1 第 6 条那一条容忍规则之外）；Checkpoint 不能绑定当前字节；提交 Hook 拒绝；需要改这 565 个文件以外的任何内容、或为让检查变绿而放宽判据：均停止，保留现场，不靠重跑、改字节或放宽判据变绿，不开第二轮。止损：同一问题最多修 2 轮，连续 2 张卡失败整体停下；同一问题两次未解就通知用户（用户切 Opus 诊断）；不做任何真实模型调用。

## 10. 交付物

基线 SHA 与预检事实表；卡与预检；冻结文件与工具；演练原始输出（非治理）；正式独立门禁与证据；CHG/Decision/Work/Run/Checkpoint、正常 Hook 提交、blob 核对和对账；委托收口记录。

## 11. 限制与后续

提交在本地分支 `codex/m3-hygin1-records`（卡 148 的提交之上）。之后：推送并读 CI；M3-CIMAIN；台账与 WBS 回写；M3-MAIN（把 main 快进）。
