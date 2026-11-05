# rel72 工具派生：已冻结状态（2026-11-04，冻结点 dd8b192f2e0a）

本文件描述卡 221 的冻结工具是怎么来的、和 7.1 的差别、哪些事已经核实、哪些没有。

## 来源与重新生成

- `derive_rel72.py` 以发版 7.1 最终审计过的工具（`m3-rel71b/`）为底做改写，不是在旧派生链上重新生成（旧链里有补丁脚本，单靠旧脚本复现不出最终版）。
- 重新生成命令（冻结点、差值、跳过差值、sample-drill 证据文字、卡 SHA 五个参数）：
  `.\.venv\Scripts\python.exe -B .auto-pm\reports\m3-rel72\derive_rel72.py <冻结提交> "<差值json>" "<跳过差值json>" "<证据文字>" <卡SHA-256>`
  不给第五个参数时，`rel72_1_approve_start.sh` 里的 `CARD_SHA` 保持占位 `__CARD_SHA__`，脚本会拒绝启动。
- 它还会执行 `git branch -f m3-rel72-base <冻结提交>`（只建本地分支）。

## 和 7.1 最终工具的差别

1. **所有用户原话和消息 id 全部删除**（11-03 的两条预授权不出现在任何产物里）。7.2 的批准文字、消息 id、时间由 `approval_refs.env` 在运行时提供：`GO_SHA`、`GO_REF`、`GO_AT`、`GO_TEXT`；延长授权只读 `HOLD_REF.txt`，没有就不延长。
2. 十组整跑；删掉 7.1 V1.1 的九组复用块和复用硬核；保留心跳、电源证据、提交钉住三项检查。
3. 提交钉住放宽：`origin/main` 在运行期间前进时，没有载荷改动（`auto_pm`、`templates`、`scripts`）就通过，有载荷改动判不过。演练 `v72_checks_test.py` 11 个用例全部符合预期（含两对真实提交）。
4. 基线用发版 7 的受治理输出（`baseline_g2/`，RUN-SW008-M3-REL7-001，产品 d671611a，逐字节复制）。不用 7.1 的输出：7.1 的 core 组失败过一次，靠例外放行切换，7.1 的 V1.1 重判从未启动。
5. 编号：Work/Run 取 `-002`（脚本沿用 7.1 V1.1 的编号规则，实际创建的就是 -002），账本里没有 `-001`。配置、延长授权的幂等键、状态文件都以 -002 为准。
6. `rel72_1_approve_start.sh` 内嵌卡的 SHA，所以不在清单里（否则卡与清单互相依赖），靠带外锚点：`rel72_launch.sh` 拿它和审计分支上同名文件比对哈希。清单按 LF 字节计算。
7. 一个已修的生成器缺陷：早期版本的改名顺序错了，导致 `rel72_1_approve_start.sh` 里卡的文件名与卡 SHA 还是 7.1 的。现在长字符串先于通用替换，已用 `--check-only` 实跑验证。

## 已核实

- 所有生成的脚本 `bash -n` 与 Python 解析通过；`v72_checks_test.py` 11 个用例按预期。
- `rel72_1_approve_start.sh --check-only` 实跑退出码 0（`CHECK_ONLY_OK`，没有写入任何治理记录），输出在 `evidence/dryrun_check_only.txt`。**注意**：check-only 之前要求 `approval_refs.env` 存在，所以我临时放了一个明确标注“DRY-RUN ONLY，不是用户消息”的假文件，跑完立刻改名移走（`approval_refs.env.DRYRUN-NOT-A-USER-APPROVAL.2`），真正起跑时这个文件必须由用户的批准之后才写。第一次 check-only 失败（卡 §5.1 的 SHA 不是表格，脚本解析不了），修卡后第二次通过；第一次的输出被第二次覆盖，原因记在这里。
- 冻结点上整组 `tests/cli` 在真实检出里后台方式复跑：1014 passed, 3 skipped, 0 failed（`evidence/final_cli_full.txt`）。

## 没做 / 请审计评估

1. 整条脚本链路没有在合成输出上彩排（`rel72_rehearse.sh` 已派生，但要建临时工位，工位数在上限）。
2. 账本里两个遗留 Work（`WORK-SW008-M3-REL7-001`、`WORK-SW008-M3-REL71-001`）仍是 IN_PROGRESS，不挡启动，发版收口后另开带 Decision 的结算卡。
3. 新测试目录 `tests/contract/`（单数）不在十组里，不影响本卡判定。
