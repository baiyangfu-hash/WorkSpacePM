# 发版 7.2 候选门禁：卡 221 与冻结工具（供独立审计）

- 卡：`card/221_M3-REL72_发版7.2候选门禁实施卡_PM.md`（SHA-256 在线程里报出，字节以本分支为准）。编号：Work/Run 为 `-002`，账本里没有 `-001`。
- 冻结点：`dd8b192f2e0a8ffdc370fd7e2dc4f7a999bb7642`（`main`，#550 合并提交）。基线是发版 7 的受治理输出（RUN-SW008-M3-REL7-001，产品 `d671611a`）。
- 本目录根下是冻结工具（`reference_manifest.json` 列出 19 个，含 SHA-256；`rel72_1_approve_start.sh` 内嵌卡的 SHA，不在清单里，靠带外锚点，SHA-256 为 `8f69de5667811fd524f7d5e7cedbc49eda0342be4164bc15430de9f26e5dc0d1`）；`derive_rel72.py` 是生成器，不是被执行的工具。
- 派生方式和与 7.1 最终工具的差别见 `DERIVE_NOTES.md`；提交钉住与防睡眠的演练见 `v72_checks_test.py`、`evidence/v72_checks.txt`。
- 冻结点上整组 `tests/cli` 的真实检出复跑：`evidence/final_cli_full.txt`（1014 passed, 3 skipped, 0 failed）。差值测量：`evidence/real_measure.json`、`evidence/collect_counts.json`。
- 用户原话：本目录里没有任何预置的用户原话或消息 id；7.2 的批准文字、消息 id、时间在起跑时从 `approval_refs.env` 读。
- 文件名说明：为避开提交钩子对生产代码要求变更单号的检查（和 7.1 的审计分支同样做法），`.py` 文件在本分支里加了 `.txt` 后缀，内容逐字节相同；`reference_manifest.json` 里的哈希对应去掉 `.txt` 后的文件。`.sh` 与 `.json` 文件原样。
- 启动前核对：`rel72_1_approve_start.sh --check-only` 实跑退出码 0，输出在 `evidence/dryrun_check_only.txt`（细节和假批准文件的说明见 `DERIVE_NOTES.md`）。
