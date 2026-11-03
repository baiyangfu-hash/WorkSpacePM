# 发版 7.1 门禁卡（卡 220 V1.0）与切换卡 D07n（草稿）——审计用，不开 PR

来源：笔记本 `.auto-pm/reports/m3-rel71/`、`m3-d07n/`（被 git 忽略），这里是给云端审计留的副本；`.py` 存成 `.py.txt`（提交钩子会把 reviews/ 下的 .py 当生产代码）。唯一事实源是 `PLAN.md`（每块手工改动、结果、用户消息 id 都在里面）。

## 这是什么

用户 2026-11-03T19:33:23Z（消息 `cmsg_01AfNxhPWkgwWYuL1EVfYC7tKDxhSnLfp7mWBPVGmAc3TB`）预授权：#514 合并后，以 `main` 最新提交打发版 7.1，全量门禁和审计都过就切换；任一不过则不切、保持 `1.3.3-d671611`；切换后驾驶舱启动或冒烟失败自动回切。另 19:34:01Z（`cmsg_01AfNxhPWkgwWYuL1EVfYC7tWQhf6disCfHBfB4NS8zWEF`）预授权门禁期间 extend-hold 一次、最多 +2 小时。冻结提交 `d563293171847124e609469b5371c5d8b9688443`（#514 的合并提交；自发版 7 的 `d671611a` 起 12 个合并，产品子树 10 个文件不同）。

两张卡：**卡 220**（`220_M3-REL71_发版7.1候选门禁实施卡_PM.md`，SHA-256 `7b98bf93dba18b599f2ce8d1ae330a8ed643bcbfc8f4c386f681a2a347e58d34`，机器预检 findings 为空）和 **D07n 切换卡**（`d07n/`，**草稿**：卡里“卡 220 门禁提交”用 0000 占位，门禁跑完后用真提交号重生，只改卡 SHA 与提交号两处，届时会再请你复核这两处）。

## 做法（对照发版 7 V1.0 的已审工具链）

`rel7_vs_rel71_diff.txt` 是发版 7 V1.0 工具（`m3-rel7/`）与本版（`m3-rel71/`）的逐文件 diff。generator 路线：发版 7 的最终 generator（`derive_rel7.py`，从稳定底版 m3-d045 生成整套工具链）机械改名成 `derive_rel71.py`，再用五个带断言、只能应用一次的补丁（`patch_a~e.py.txt`）改掉必须手工改的地方；卡文本由 `make_card220.py`（`make_card219.py` 改名加 `patch_e`）渲染。差异要点：

1. **没有 orient 例外**：发版 7 的 G3 窄例外（`LEASE_EXPIRED` + B2 旧 Run）取消，`orient_ok` 只接受空冲突列表；用例表仍 26 行，原来“通过”的两条改为“不通过”。**启动前置条件**写进卡 §3 第 6 条：`pm orient` 冲突为空、工位 ≤5、Trae CN 关闭、已提交内存 <35 GiB、两张卡都已审计放行、`approval_refs.env` 已核对。（B2 旧 Run、发版 7 V1.0 Run、Trae 卡 B 第二个 Run `…471-02` 都已结算为 CANCELLED，`pm orient` 现在冲突为空——见 PLAN.md。）
2. **租约**：不再在起跑时无条件 extend-hold，改为脱离看护 `rel71_hold_watch.sh`（`rel71_launch.sh` 里生成）：起跑 150 分钟后若门禁仍在跑，用用户 19:34:01Z 的消息 id 延一次 +7200 秒，成功写 `EXTENDED_ONCE`。总上限 5 小时，预计约 4 小时。
3. **差值来源据实**（卡 §1 第 4 条）：开跑前对基线 `d671611a` 与冻结提交各做逐组 `pytest --collect-only` 数用例，再把变化的测试文件在两棵树上各跑一次数通过与跳过（`collect_counts.json`、`measure_changed.json`、`predelta.json`）。声明：通过 rest +3、infrastructure +62、cli +25、core +1；跳过 infrastructure +1。**只证明没有分组丢收集用例，不证明新增用例通过**（卡里这样写）。
4. **没有 `--skip-worktree-check`**：发版 7 已含 `doctor --pre-release`，构建工具拒绝该绕过（`pre-release-bypass-refused`），generator 已去掉。
5. **授权文案**换成 11-03 预授权；不再有 NIGHT_REF；`approval_refs.env` 的 GO_REF 就是上面那条消息 id（真文件在审计放行后才写）。
6. 基线 = 发版 7 的 V1.0 实跑输出（`m3-rel7/gates/g2_candidate/`，卡 219 V1.1 已逐字节复用并判过）；样件联调证明 = GitHub `sample-drill` run 41719191411（main 上对冻结提交 `d5632931`，success）。

## 演练（非治理，临时工位，已删）

第三次演练通过：快速门禁全过（两次构建逐字节一致、verify、载荷可导入、静态、真实钩子、六个项目对账 0/0/0、orient 冲突为空）；十组回归是**合成输出**（基线按声明差值调整），判卷 G1～G9 全 PASS；反例变体按预期被拒（`rehearsal_judge_variants.txt`）。前两次失败原因与处理见 `rehearsal_facts.txt` / `PLAN.md`。预检：`rel71_1_approve_start.sh --check-only` 通过（合成凭据，跑完删除；清单 19 项匹配、卡预检 passed、对账 0/0/0）；`rel71_launch.sh --dry-run` 通过（`launch_dryrun/`）。

## D07n 相对已审过的 D07m 的改动（请逐条看，`d07n/d07n_deploy.sh` vs `m3-d07m/d07m_deploy.sh`）

- Run 的工位从**最新 `origin/main`** 建；控制根的 `deployment_manifest.json`（比 main 多 16 条本机独有的中间发布条目，已记债）及指针字节若与工位起点不同，经**正常 Hook 在工位里提交一次**再开 Run（来由写进卡；旧运行时规定“控制根范围内文件 = 工位起点”）。
- 身份检查**严格**（`conflicts == []`），取消 `LEASE_EXPIRED` 放行。
- 冒烟新增：`long-run --help` 应答、`pm orient SW-2026-008 --json` 冲突为空；任一失败沿用 ops 脚本的 `rollback` 自动回切。
- 验收那步（accepting→completed）补 `--approval-evidence-ref`（D07m 里缺，需手动补）；批准、决策、验收三处都带用户消息 id。
- 流程：D07n 卡与卡 220 都先审计放行再执行（D07m 当时没有先送审）。

## 要请审计评估的几点

1. 卡 220 §1 第 9 条“没有例外”与启动前置条件是否足够；判卷 `orient_ok` 严格版与 26 行用例表是否正确（`rel71_gates.py.txt`，见 diff）。
2. 租约延长看护的逻辑（150 分钟、只延一次、7200 秒、凭据取自用户消息）。
3. 差值据实写法是否可接受（尤其 core +1：解出的目录没有 .git，`test_github_collector.py` 在那种环境本来有失败，所以 core 用收集数；真实门禁在 git 工作树里跑）。
4. D07n 草稿的上述改动；门禁跑完后重生的两处差异。
5. 工位：演练工位已删（用户原话 `cmsg_…QfcqKsQkVdJKkjcbucsUqJ`），现 5 个；门禁候选工位 `m3-rel71` 占 1，切换工位 `m3-d07n` 占 1。

## 已知未决

- `doctor --pre-release` 的 3 个提示（游离文件、venv 底层 Python 在 Codex 目录、16 条中间发布条目没标注）都是已记债项，不影响退出码（0）。
- CHG-DOCU-2026-092 停在 pending_acceptance（11-02 用户授权没有白纸黑字覆盖变更单收口）。
