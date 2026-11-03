# 发版 7.1 门禁卡与切换卡：起草计划（M3 主执行，11-03 12:40 MST）

依据：用户 2026-11-03T19:33:23Z 预授权（cmsg_01AfNxhPWkgwWYuL1EVfYC7tKDxhSnLfp7mWBPVGmAc3TB）；协调者 19:33:44Z 指令：先起草门禁卡和切换卡，送审计放行，冻结提交待 #514 合并后填。

## 来源与做法
- 源：发版 7 的 V1.0 全量工具链 `.auto-pm/reports/m3-rel7/`（完整门禁：基线→安装→快速→十组回归→瞬时三次重跑→判卷）+ 判卷 `rel7_gates.py`（G3 窄例外要**去掉**：B2 已结算，orient 现在冲突为空，G3 恢复“必须无冲突”）+ 卡生成 `m2-batch1/make_card219.py`（改名 make_card220.py）+ 切换卡生成 `m3-d07m/gen_d07m.py`（改名 gen_d07n.py）。
- 每一版的做法是对上一版文本做定点替换（derive_relN.py），不手写新逻辑；本版同样，输出到 `.auto-pm/reports/m3-rel71/`。

## 要改的点（逐项，不漏）
1. 编号：卡 220（`CARD-SW008-M3-REL71`），前缀 `rel71`，证据目录 `m3-rel71`，Work/Run/Ckpt `…-M3-REL71-001`，决策后缀 `M3REL7101`，分支 `claude/m3-rel71`，owner `claude:m3rel71`，基线分支 `m3-rel71-base`。
2. 基线（对照）：发版 7 的受治理输出（RUN-SW008-M3-REL7-001 十组输出，由 V1.1 逐字节复用并判过）；现行有效版本 `1.3.3-d671611`；声明差值先留 `@@DELTAS@@`，由 `pregate`/首个冻结提交上的实测定（V1.0 教训：差值不能留空；V1.1 教训：差值来源必须据实写）。
3. 冻结提交：占位 `@@FROZEN@@`，#514 合并后由协调者给出 main 最新提交；`cardkit`/spec.json 的 `base`、`rel71_config.json` 的 `frozen_commit` 填入后才能算卡 SHA。
4. 租约：核心组上次 2:53，总上限 3 小时不够（V1.0 教训）：门禁卡按“预计 4 小时”写，**启动脚本里的 extend-hold 只在用户有 extend-hold 原话（消息 id）时才执行**，没有就在 3 小时前拆成两段 Run（分组：快速+前七组为段 A，core+qml 为段 B，段 B 复用 A 的基线），否则不开跑；这条要在卡 §7 写明。
5. 内存：门禁全部走 detach_run+mem_guard（已有）；开跑前加 #513 的预检（`run_preflight` 未合并前用 typeperf 手工检查已提交内存 < 35 GiB）；Trae 必须关闭（卡 §7 前置条件）。
6. Run 工作树：旧运行时（现行 1.3.3-d671611 已含 #496/#418 的限制）不让控制根当 Run 工作树；门禁 Run 本来就在 `m3-rel71` 候选工位，沿用；**D07n 切换卡的 Run 用工位 `m3-d07n`**（不再手动补清单提交，开工前先按“控制根范围内文件=工位起点”要求把 manifest/pointers 提交或让它们落在同一指针 PR 里——此项要先问协调者：现在控制根的 deployment_manifest.json 与两个指针是未提交改动，#507 因 CI 把清单撤出了）。
7. 切换卡 D07n：后核验在 D07m 基础上加“驾驶舱启动 + 冒烟”（`main.py pm orient` / `pm handoff --help` 之外增加一次 `gui --help` 与一次 `doctor --pre-release`？以审计意见为准）+ **自动回切**（任一失败调用 `pmf_release_ops.sh rollback`，已有；此处改成在冒烟失败时同样触发并写回执），冲突列表恢复“必须为空”（不再放行 LEASE_EXPIRED）；`--approval-evidence-ref` 在批准、决策、验收三处都带用户消息 id（来自 cmsg_…KDxhSnLfp7mWBPVGmAc3TB）。
8. 授权文字：卡的 DELEG/sign-off 写 11-03T19:33:23Z 的预授权原话；“当场确认”类措辞全部不用。
9. 审计：门禁卡与切换卡都先送审计放行，再跑（协调者记的流程缺口）；卡字节不随用户消息 id 变（id 写进 approval_refs.env，同 V1.1 做法）。
10. 其它沿用 V1.1 的教训：commit 说明里不写模型名以外的…（按 Co-Authored-By 规则）；README 不写“预计”类不实时间；`.py` 工具存 `.py.txt`；`.gitignore *.log` 的陷阱用 `.txt`。

## 需要的外部输入（等）
- #514 合并后的 main 最新提交号；
- 用户 extend-hold 带条件原话（协调者在要）；
- 控制根未提交的 manifest/pointers 怎么处理的裁决（见 6）。

## 产物清单
`derive_rel71.py`、`rel71_config.json`、`spec.json`、`rel71_{1_approve_start,2_close_commit,3_chg_close,4_close_worktree}.sh`、`rel71_gates{.py,_all.sh,_wrap.sh}`、`rel71_launch.sh`、`rel71_rehearse*.sh`、卡 `220_M3-REL71_…_PM.md`、`gen_d07n.py`、`D07n_card.md`、`d07n_deploy.sh`；全部先在演练根跑通（rehearsal），再送审计。

---
## 进展与已定做法（11-03 14:40 MST）
- 冻结提交：d563293171847124e609469b5371c5d8b9688443（#514 合并提交；自 d671611a 起 12 个合并 #497 #498 #499 #503 #506 #507 #509 #511 #512 #513 #514 #517）。基线（对照）= 发版 7 的 V1.0 实跑输出 `.auto-pm/reports/m3-rel7/gates/g2_candidate/`（十组 .txt/.exit，已由 V1.1 逐字节复用并判过）。
- 开跑前计数已完成：predelta.json —— 声明差值（通过数）rest +3、infrastructure +62（跳过 +1）、cli +25、core +1，其余 0。
- 底版选择：**m3-rel7（V1.0 全量版）的文件就是 7.1 的底版**——它和 rel7b（V1.1）差别很小（approve_start 56 行都是编号/文案；launch 里多一段 extend-hold，7.1 需要它，条件是用户原话 cmsg_01AfNxhPWkgwWYuL1EVfYC7tWQhf6disCfHBfB4NS8zWEF，最多 +2 小时一次）。rel7_gates_all.sh 用 m3-rel7 的全量版（V1.1 的是复用版）。
- 替换表（对 m3-rel7 的文本文件，按此顺序）：rel7-gate-tools-20261102→rel71-gate-tools-20261103；m3-rel7-base→m3-rel71-base；m3-rel7→m3-rel71；rel7_→rel71_；M3REL701→M3REL7101；REL7-001→REL71-001；CARD-SW008-M3-REL7→CARD-SW008-M3-REL71；M3-REL7→M3-REL71；claude:m3rel7→claude:m3rel71；219→220；d671611a13bc15536047769fdb0498666c414044→d563293171847124e609469b5371c5d8b9688443；d671611→d563293；卡文件名→220_M3-REL71_发版7.1候选门禁实施卡_PM.md；REP→016_M3_发版7.1候选构建与全量门禁_REP.md（先核 05_收尾 现有编号）；上一张卡的描述（card 218 V1.1 / RUN-SW008-M3-REL6-002 / 1.3.3-6a9f127）→（card 219 / RUN-SW008-M3-REL7-001 / 1.3.3-d671611）。
- 必改逻辑：rel71_gates.py 的 orient_ok 改成**只接受空冲突列表**（去掉 LEASE_EXPIRED 窄例外和 KNOWN_STUCK_*），orient_cases 表按新规则重算（≥26 行，含“空冲突=通过”“任何冲突=不通过”“已知旧例外对象现在也不通过”）；G3 文案同步；spec/config 的 expected_deltas、expected_skips、baseline_g2、frozen_commit、card 版本、run id、docs 报告路径与必含词（新冻结提交号）换成 7.1 的。
- 切换卡 D07n：以 m3-d07m/gen_d07m.py 为底，改：冲突必须空；冒烟（pm orient + gui --help + doctor 不带 --pre-release 的退出码）；冒烟失败自动回切并写回执；Run 用工位 m3-d07n（先用“控制根范围内文件=工位起点”：manifest/指针已随 #517 与 main 同形，清单本机多 16 条的问题要在 D07n 卡里用“清单字节对齐的小提交”写明并送审）。
- 前置：工位目录 9→≤6（等用户删除原话）；Trae 关闭；#519 的内存总闸若装好则可用。
- 还没做：以上全部的实际文件生成与演练。下一步：写 derive_rel71.py（读 m3-rel7 文件→替换→写 m3-rel71），跑，grep 残留 rel7/219/d671611，再 rehearsal。

---
## 状态（11-03 15:10 MST）：generator 已机械改名，还剩手工改动清单
`derive_rel71.py` 已由 `m3-rel6/derive_rel7.py`（它从稳定底版 m3-d045 生成整套工具链，是 rel7 的最终 generator）机械改名生成（rel7→rel71、REL7-001→REL71-001、卡号 CARD-SW008-M3-REL7→…REL71、冻结提交→d5632931）。**仍需手工改的位置（行号为 derive_rel71.py 当前行号，用 grep 对应原文）**：
1. L1 docstring 的卡号说明；L53-54 `ACTIVE_FROZEN` 改成 d671611a13bc15536047769fdb0498666c414044，注释里 1.3.3-6a9f127→1.3.3-d671611。
2. L59 `REPORT` 改成 `…/05_收尾/016_M3_发版7.1候选构建与全量门禁_REP.md`；L66-100 报告正文：标题/“第七次”→“发版 7.1”、卡号、上一张卡描述（card 218 V1.1/RUN-SW008-M3-REL6-002/1.3.3-6a9f127 → card 219/RUN-SW008-M3-REL7-001/1.3.3-d671611，且“差值”来源写据实：开跑前收集数差 + 变化测试文件在两棵树上的跑数，只证明零丢收集用例）、“差值由 release-pregate…”整句要换；第 3 节“D07 同款脚本在用户当场确认后做”改为“按用户 11-03 的预授权，门禁与审计全过后做”。
3. L107、L120、L237、L288、L291 的卡号/上一张卡描述；L133 `KNOWN_CARD` 保留但 **FUNC 块（约 L130-245）里 KNOWN_STUCK_RUN/WORK 与 orient_ok/orient_cases 要改成“只接受空冲突”并重算 26+ 行用例表**。
4. L326-327 extend-hold 块：`--run-id RUN-SW008-M3-REL71-001`，凭据改为 cmsg_01AfNxhPWkgwWYuL1EVfYC7tWQhf6disCfHBfB4NS8zWEF，`--extra-seconds 7200` 只许一次（≤2 小时），注释里写原话；并加“只在某组接近总持有上限时才执行”——脚本里改成由 gates 包装器在第 150 分钟时检查再延（不是起跑就延）。
5. L351 `DELEG`、L379 `REF`、L420/L443 的 `DELEG` 文案：授权依据改成用户 2026-11-03T19:33:23Z（cmsg_01AfNxhPWkgwWYuL1EVfYC7tKDxhSnLfp7mWBPVGmAc3TB）预授权；起跑时间用户 11-02 的话不再适用，去掉 NIGHT_REF/NIGHT_TEXT（approval_refs 解析里改为可选）。
6. L355-368 spec 字段：card_no 220、card_file `220_M3-REL71_发版7.1候选门禁实施卡_PM.md`、label_short M3-REL71、approval_tag M3-REL71、title、background、commit_msg（“seventh”→“7.1”）。
7. 运行参数：`python -B derive_rel71.py d563293171847124e609469b5371c5d8b9688443 CHG-SCPT-2026-472 RUN-SW008-M3-REL7-001 .auto-pm/reports/m3-rel7/gates/g2_candidate '{"rest":3,"infrastructure":62,"cli":25,"core":1}' '{"infrastructure":1}' "<MEASURED_FROM 据实>" "<sample-drill 对 d5632931 的运行号，需要先在 GitHub 上跑或查>"`。
8. 卡文本：由 `m2-batch1/make_card219.py` 复制成 `make_card220.py` 并同样改（文字、差值句、上一张卡、授权句）；产出 `220_M3-REL71_…_PM.md`，机器预检；再演练 `rel71_rehearse.sh`；再写切换卡 D07n（`gen_d07m.py` 为底）。
9. 样件联调 CI 证明：需要 `sample-drill` 工作流对 d5632931 的运行（查 `gh run list --workflow sample-drill`），没有就先触发。
- sample-drill 对冻结提交 d5632931 的证明已有：GitHub Actions 运行 41719191411（main 上的 push，headSha d5632931，completed success，2026-11-03 查得）——DRILL_CI 参数用它。
- [x] 块 1/2（ACTIVE_FROZEN、REPORT 路径 016、报告正文：标题、上一张卡、差值来源据实、第 3 节授权措辞）已由 patch_a.py 应用到 derive_rel71.py（11-03 15:20 MST）。
- [x] 块 3（门禁文本的上一张卡描述、orient 只接受空冲突：orient_ok 改严格，两条原“通过”用例改为 False，用例表仍 ≥26 行）已由 patch_b.py 应用（11-03 15:30 MST）。注意：rel71_gates.py 其余处（约 L483-488 的 orient_line 文案“orient exception”）措辞可在审计时再润色，不影响判据。
- [x] 块 4/5/6（工具源目录名修正为 rel7_tools_src；launcher 改卡号 220，**无条件 extend-hold 换成“150 分钟后仍在跑才延一次 +7200 秒”的脱离看护 rel71_hold_watch.sh，凭据 cmsg_…WQhf6…**；DELEG/REF 换成 11-03 的预授权 cmsg_…KDxhSn…；spec 的 pfx/card_no/card_file/label/approval_tag/background/necessity/title/commit_msg）已由 patch_c.py 应用（11-03 15:45 MST）。
- [x] 块 5 续（approve_start/close 里的授权措辞换成 11-03 预授权，`_lit` 改为 KDxhSn… 的 ref，approval_refs 模板写 7.1 预授权原文，NIGHT_* 不用）已由 patch_d.py 应用（11-03 16:00 MST）。
- [ ] 下一步：跑 `python -B derive_rel71.py d563293171847124e609469b5371c5d8b9688443 CHG-SCPT-2026-472 RUN-SW008-M3-REL7-001 m3-rel7 '{"rest":3,"infrastructure":62,"cli":25,"core":1}' '{"infrastructure":1}' "<MEASURED_FROM>" "<DRILL_CI>"`（BASE_G2_FROM 是相对 reports 的目录名，脚本取 `R/BASE_G2_FROM/gates/g2_candidate`）；DRILL_CI=“运行 41719191411，main 上对冻结提交 d5632931 的推送运行，结论 success，已核实”；MEASURED_FROM=“.auto-pm/reports/m3-rel71/predelta.json”。
- 注：dec_suffix 必须 8 位 A-Z0-9（cardkit 规则），7.1 用 M3R71A01（决策号 DEC-<日期>-M3R71A01）；已改 derive_rel71.py。
- [x] derive_rel71.py 已跑通（'REL71 toolkit derived; frozen d5632931 merges 12 product files 10'），产出 rel71_* 脚本、spec.json、rel71_config.json、reference_manifest.json、proto/…016…REP.md（11-03 16:10 MST）。下一步：核对残留 → 卡 220 → 演练 → D07n。
- 生成命令（可重复）：.venv/Scripts/python.exe -B derive_rel71.py d563293171847124e609469b5371c5d8b9688443 CHG-SCPT-2026-472 RUN-SW008-M3-REL7-002 m3-rel7 '{"rest":3,"infrastructure":62,"cli":25,"core":1}' '{"infrastructure":1}' ".auto-pm/reports/m3-rel71/predelta.json" "运行 41719191411，main 上对冻结提交 d5632931 的推送运行，结论 success，已核实"（必须用 venv 的 Python 3.12，cardkit 用了 3.12 的 f-string 语法）。
- [x] 块 8a: patch_e.py 已应用到 make_card220.py（卡 220 文本：名称、基线、G2/G3/G8 表、授权、§1 第 1/3/4/5/7/9/10/11/12 条、§3 第 3/4/5/6 条）（11-03 16:40 MST）。下一步：运行 make_card220.py 生成卡并机器预检；再演练；再 D07n。
- [x] 切换卡 D07n 草稿已生成（gen_d07n.py，底版 m3-d07m/d07m_deploy.sh；`python -B gen_d07n.py d563293171847124e609469b5371c5d8b9688443 DRAFT`，产物 ../m3-d07n/D07n_card.md、d07n_deploy.sh；DRAFT 卡 SHA 970ab14f…，卡里的“卡 220 门禁提交”用 0000… 占位，门禁跑完后用真提交号重生并再送审，只会改 SHA 与提交号两处）。D07n 相对 D07m 的改动：工位从 origin/main 建 + 控制根清单/指针字节经 Hook 提交；身份检查严格（冲突必须 []）；冒烟加 `long-run` 入口与 `pm orient --json` 冲突为空；验收那步带 `--approval-evidence-ref`；批准/决策/验收三处都带用户消息 id。（11-03 17:05 MST）
- [ ] 待办（按顺序）：①处理 Trae 卡 B 的 471-02（用户原话待）→ pm orient 无冲突；②跑演练 `bash rel71_rehearse.sh`（后台，约 10~15 分钟；会建临时工位 m3-rel71-rehearse，现有工位 5 个，演练后要收：需用户原话）→ 得 rehearsal_facts.txt；③`make_card220.py` 出卡 220、`implementation-card precheck` 过；④卡 220 与 D07n 草稿送审计；⑤审计放行后启动：approval_refs.env（GO_SHA=卡 220 SHA，GO_REF=KDxhSn…，GO_TEXT=原话）→ `rel71_launch.sh`。
- 排队事项（排在 7.1 两张卡之后，不插队；7.1 门禁跑的时候不装）：#519 头 2c0e3967（债线报：PR CI 36 项通过，手动 sw008-ci run 1878 通过）。bundle 哈希 dced3e54b4e505cff710130b49bb9e92c39a9c5d832b197410de783974f1e90d，脚本 CRLF 哈希 0611424b1e0fbfb8dc2853a7480a90523b716fe3eefa17ddee3739e63e1b3a13（都没变）。轮到时：先本地核对两个哈希，再把“管理员 -Install 一行命令 + 严格自检步骤”发协调者，由协调者转用户在管理员 PowerShell 粘贴。
- [x] ① 完成（11-03 15:20 MST）：用户 22:11:10Z“同意”（cmsg_01AfNxhPWkgwWYuL1EVfYC7tCZAiuqsUG2DkLSovGvqkrV，回答我“请回：同意结算 …471-02 为 CANCELLED，Work 保持进行中”的请求）→ 恢复链 CHG-DOCU-2026-094、决策 DEC-20261103-SETLB2B1、恢复 Run/Work 在控制根；471-02 已 CANCELLED，Work WORK-MSN-415BA3D417866398 仍 IN_PROGRESS，`pm orient` 冲突 []，对账 0/0/0。控制根 main 本地多一个提交（决策绑定，f3badfd1 为起点）；待写回卡一并 PR。
- 修正：发版 7 已含 doctor --pre-release，构建工具拒绝 --skip-worktree-check（pre-release-bypass-refused）→ derive_rel71.py 里去掉该绕过（new_b = old_b）；演练第一次因此失败（G3_build_a.txt），第一次的演练工位 m3-rel71-rehearse 留着待用户原话删除；第二次演练用 m3-rel71-rehearse2（rel71_rehearse.sh 经 sed 改名，未写进 generator）。
- 用户预授权（cmsg_01AfNxhPWkgwWYuL1EVfYC7tPe7TpS9CYhGNhgAuJoSo1X，2026-11-03T22:16:32Z）：“发版 7.1 演练完成后删除临时工位 m3-rel71-rehearse，不带 --force，有未提交内容就不删”。范围只含 m3-rel71-rehearse；第二次演练用的 m3-rel71-rehearse2 不在其内，需另请示。
- 阻塞（等协调者 A/B）：演练里 `doctor --pre-release` 因 CHG-DOCU-2026-092 / CHG-SCPT-2026-471 的状态没有流转记录而红（钩子也拦提交）；方案 A = 用 `change transition` 正常走流转写记录。
- 卡 220 草稿已渲染（演练事实占位 @@REHEARSAL_FACTS_MISSING@@；草稿 SHA 685d99a7…，待演练后重渲染）。
