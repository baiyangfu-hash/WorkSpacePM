# D07p：切换到发版 7.2 候选（供独立审计）

- 卡 `D07p_card.md`（SHA-256 `987d40264e047cc35e1fa90f99bc90a984c52233c8dcb6dc7bfb80e657842a1f`），脚本 `d07p_deploy.sh`（SHA-256 `1539d0e5ea24c6b4fb815cda3f2984cdab0a1e97e16c16a5f0bafa06930f7f9f`，内嵌卡 SHA）。生成器 `derive_d07p.py.txt` 不是被执行的工具。
- 来源：发版 7.1 的 D07n（已审计、已用过）。`d07n_deploy.sh.reference`、`D07n_card.md.reference` 是它的原件；`d07p_deploy_vs_d07n_deploy.diff` 是把 d07n/D07n 统一改名后的逐行差异（只看这个就能审）。
- 与 D07n 的差别：
  1. 门禁判据：`gate_verdict.json` 必须是 `card=CARD-SW008-M3-REL72 V1.1`、`base=dd8b192f…`、`run_id=RUN-SW008-M3-REL72-003`、九项全 PASS（D07n 有一个 G2 例外，这里没有）；且该 Run 在账本里必须 SUCCEEDED。
  2. 授权：用户 2026-11-05T04:04:33Z 的常设授权“不过不切换，过了自己切换。门禁已经授权了。”不点名本卡 SHA，所以 D07n 的“确认文件里有本卡 SHA”一行换成“确认文件里有 USER_TEXT 一行”，并新增必须存在且非空的 `switch_audit_ref.txt`（审计放行的引用）——没有它脚本不切换。
  3. 工位数守卫：`.auto-pm/worktrees` 已有 7 个目录时不启动（发版体检上限 7，本卡工位是第 8 个）。
  4. 指针常量（`OLD_ACTIVE_SHA` 等）取自现在的控制根文件；候选 `1.3.3-dd8b192`，active := 它，previous := `1.3.3-d563293`，更早的 `1.3.3-d671611` 仍保留并校验。
  5. 冒烟清单增加 `pm state-backup`、`pm triage`；站点提交那一步（控制根清单字节入工位）通常无内容可提交，因为步骤 M 之后控制根清单与指针等于 main。
  6. 不在本卡：发版 PR（把发布目录、三个指针、只多一项的清单入库，同 #528 做法）和 `pm state-backup push`（外发动作）。
- 状态：`--check-only` 现在会在缺 `gate_verdict.json` 处正确拒绝（门禁还在跑）；脚本从未实跑，也没有演练。回退用 D06 演练过的同一份 `pmf_release_ops.sh`（SHA 在卡里）。
