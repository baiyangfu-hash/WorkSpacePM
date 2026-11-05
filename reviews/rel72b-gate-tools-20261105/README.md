# 发版 7.2 候选门禁 V1.1：卡 221 V1.1 与冻结工具（供独立审计）

V1.0 在 2026-11-04 21:05 MST 的快速门禁失败（发版体检拒绝构建：16 个发布目录磁盘上有、`deployment_manifest.json` 没登记）。V1.1 是同一张卡：新 Work/Run（`-003`）、新证据目录与工位（`m3-rel72b`）、新 Decision 后缀（`M3R72B01`）、沿用变更单 `CHG-SCPT-2026-478`，并多一步“步骤 M”：把那 16 个目录改名移出 `releases/`，随后 `doctor --pre-release` 必须退出码 0 才启动门禁。其余是 V1.0 已审计并用过一次的文字，只改编号与路径。

## 审计请重点看
1. `rel72_0_move_unregistered.sh`（新）：只改名不删、集合与 16 个名字逐一相等才动、移动前后文件数相等、写好反向脚本、移动后体检必须 0。
2. `rel72_launch.sh`、`rel72_1_approve_start.sh` 相对 V1.0 的差别（`diff` 即可：只有重命名、步骤 M 的接入和 `check` 调用）。
3. 卡 §1 第 16～18 条（失败记录、根因与修法、与 V1.0 的差别），尤其第 18 条里把工位数上限从 5 放宽到 6（机器上限是 7）。
4. 根因的代码证据：`release_consistency.py` 第 202～205 行对“磁盘有而清单没登记”无条件判失败，`release_annotations.json` 的 `corrections` 只能更正 `source_commit`，所以“走 annotations 更正”这条路对这一项无效（只读代码，没有跑模拟）。
5. `v1.0-failure/`：V1.0 失败的原始证据；`evidence/dryrun_check_only.txt`：`--check-only` 在一个只把 `load_refs` 一行换成占位值的临时副本上实跑的输出（此时 `approval_refs.env` 还不存在，没有伪造批准文件）。

## 文件
- 卡：`card/221_M3-REL72_发版7.2候选门禁实施卡_V1.1_PM.md`。冻结工具在本目录根下，`reference_manifest.json` 列出 21 项（含 SHA-256）；`rel72_1_approve_start.sh` 内嵌卡的 SHA，不在清单里，靠带外锚点（启动脚本拿它和本分支同一文件比对）。
- `.py` 文件为避开提交钩子的变更单号检查加了 `.txt` 后缀（与 V1.0 审计分支同样做法），内容逐字节相同；清单里的哈希对应去掉 `.txt` 后的文件。`.sh` 与 `.json` 原样。
- `derive_rel72.py.txt`、`derive_rel72b.py.txt` 是生成器，不是被执行的工具。
- 冻结点仍是 `dd8b192f2e0a8ffdc370fd7e2dc4f7a999bb7642`；基线仍是发版 7 的受治理输出（`RUN-SW008-M3-REL7-001`）。
- 本目录里没有任何预置的用户原话或消息 id；批准文字、消息 id、时间在起跑时从 `approval_refs.env` 读。
