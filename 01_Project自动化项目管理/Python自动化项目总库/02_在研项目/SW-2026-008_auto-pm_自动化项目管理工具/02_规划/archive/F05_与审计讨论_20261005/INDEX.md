# F05 与审计讨论归档索引

> 2026-10-06，随卡 055（M2-GOV-TD2）入库。本目录的文件是 2026-10-06 冻结时的**逐字节快照**，原件在不进 Git 的 `.auto-pm/reports/` 下；“历史意见”不改成最后裁决，“有效”只指其作为该事项依据的地位。有冲突时的优先顺序：正式需求说明与分档规则 > 最终决定记录 DECISIONS > 总计划 MASTER_PLAN > 其他。

## 新增的正式文档（不在本目录）

- 需求说明：`02_规划/M2_入口分类与定位交接_需求说明_REQ.md`（SHA-256 `6ea58e0f4fb30a593aa2fb6f5f0afbce8376f12a9d9ea5d0d3b47dbe8d0e747e`）
- 门禁分档与单卡规模规则：`02_规划/M2_门禁分档与单卡规模规则_PM.md`（SHA-256 `8fec2229b931576e49d74ffa82c568ec3a2da8c0b995c34602078c7a02cd6e0c`）

## 归档文件

| 文件 | 原路径 | 内容 | 地位 | SHA-256 | 字节数 |
|---|---|---|---|---|---|
| [DECISION_20261005.md](DECISION_20261005.md) | `.auto-pm/reports/m2-f05-discussion/DECISION_20261005.md` | F05（挂起与唯一索引）分期裁决 | 有效：F05 的裁决依据 | `bbf2e26097e5a049979bc865ee8efd595afe54454394c7327dd530446662aa98` | 3060 |
| [GPT_PROPOSAL.md](GPT_PROPOSAL.md) | `.auto-pm/reports/m2-f05-discussion/GPT_PROPOSAL.md` | GPT 对 F05 的方案（含第 11 节追加） | 历史意见，已被裁决吸收 | `35d5c3de9158f11424e18a058b38038573b0d6924bc8c600e2939806ae3a46af` | 38374 |
| [CLAUDE_PROPOSAL.md](CLAUDE_PROPOSAL.md) | `.auto-pm/reports/m2-f05-discussion/CLAUDE_PROPOSAL.md` | Claude 对 F05 的方案（含第 6、7 节） | 历史意见，已被裁决吸收 | `aacec3595e7e7c2a745a3d300dc91119a3f565f3fb6a5a01fdab4b4594f20420` | 13711 |
| [AUDIT_REPORT_GPT_20261005.md](AUDIT_REPORT_GPT_20261005.md) | `.auto-pm/reports/m2-gpt-audit/AUDIT_REPORT_GPT_20261005.md` | GPT 独立审计报告（F01～F12） | 有效：审计事实来源；处置见本目录 INDEX.md 的映射表 | `5f42d3e9abe20cb29ef195d5a36777562956dc1850c85de08f06fc3bdc0f1299` | 30218 |
| [AUDIT_ADDENDUM_V04_DEFECTS.md](AUDIT_ADDENDUM_V04_DEFECTS.md) | `.auto-pm/reports/m2-gpt-audit/AUDIT_ADDENDUM_V04_DEFECTS.md` | V04 缺陷追加说明 | 有效：审计补充 | `b8d5c64e87df198d1c1cab39f212036b973db1eb3b96dd6ee8ca92759e9c647b` | 3682 |
| [AUDIT_REPORT_GPT_P1_V04_20261005.md](AUDIT_REPORT_GPT_P1_V04_20261005.md) | `.auto-pm/reports/m2-gpt-audit/AUDIT_REPORT_GPT_P1_V04_20261005.md` | GPT 对第 1 期与 V04 的独立审计报告 | 有效：审计事实来源（A-P1、A-V04、A-GATE 编号） | `3420c72d31e6be26f5e581b411692824b192140c093528158b2a6178f20ee62a` | 22344 |
| [ratification_20261005.txt](ratification_20261005.txt) | `.auto-pm/reports/m2-v01/ratification_20261005.txt` | 用户对卡 042 V1.0 最终内容的逐字追认记录 | 有效：追认原文；摘录在 CHG-SCPT-2026-374 §9.1 | `3fa4906638a791d4ddc2f9b5df861833f613161f1272e3f9c250f9fab59f06e4` | 1739 |
| [CLAUDE_REVIEW_OF_GPT_SURVEYS_20261006.md](CLAUDE_REVIEW_OF_GPT_SURVEYS_20261006.md) | `.auto-pm/reports/m2-gpt-audit/CLAUDE_REVIEW_OF_GPT_SURVEYS_20261006.md` | Claude 对 GPT 三份勘测的审阅 | 历史意见；结论已写进 DECISIONS | `ca5b41c816b6a24df9e155b963afaa68d26f31945d86ec159b25793a2f53516c` | 5784 |
| [REQ_DRAFT_入口分类_分诊队列_换Agent_薄入口_需求草案.md](REQ_DRAFT_入口分类_分诊队列_换Agent_薄入口_需求草案.md) | `.auto-pm/reports/m2-req-pm-entry/REQ_DRAFT_入口分类_分诊队列_换Agent_薄入口_需求草案.md` | 入口分类、分诊、换 Agent、薄入口需求草案 v0.3 | 历史草案，已被正式需求说明取代 | `cd9809086f044cfad3648a4c815ea10ac7b0399cf9377305c7200cd4bc3cb906` | 14342 |
| [GATE_TIERS_DRAFT.md](GATE_TIERS_DRAFT.md) | `.auto-pm/reports/m2-gate-tiers/GATE_TIERS_DRAFT.md` | 门禁分档草案 | 历史草案，已被正式规则文档取代 | `8ceeeb4216ffc86b552e91469ed6c6fff9c87ba5b24a25375a1e41fba2b1c19f` | 4861 |
| [MASTER_PLAN_20261006.md](MASTER_PLAN_20261006.md) | `.auto-pm/reports/m2-relay/MASTER_PLAN_20261006.md` | 总计划（分工、顺序、拆卡） | 有效：冻结时的版本；之后的变化以活文件为准 | `322a0d917f5660d8bff5e0b599b36398c92c127835a8efb71c0591c4e2e53638` | 5427 |
| [DECISIONS_20261006.md](DECISIONS_20261006.md) | `.auto-pm/reports/m2-relay/DECISIONS_20261006.md` | 最终决定记录 D-001～D-003 | 有效：冻结时的版本；之后的变化以活文件为准 | `d9c89e4c7d906369207cffeefed68886e548d325e93d370e3a475dc774a74b2b` | 2683 |

## 审计发现的去向

| 审计编号 | 去向 | 状态 |
|---|---|---|
| F01 | TD-SW008-078（F01-a）、079（F01-b） | 待执行；F01-a 在 V05 之前 |
| F02 | TD-SW008-063、064、065（既有，不关闭）；需求说明 N2 | V03 机制已验收，用户流程未交付 |
| F03、F07、F08、A-GATE-01、A-GATE-02 | TD-SW008-080 | V04 与卡 054 起用新工具；旧结果不改称补证 |
| F04、A-V04-01、A-V04-02 | TD-SW008-081 | 测试补卡，V04-R1 前后 |
| F05 | TD-SW008-071（既有）；需求说明 N1.4；DECISION_20261005.md | M2 只交查询合同，完整挂起 M3，运行中插队等 V04-R1 |
| F06 | CHG-SCPT-2026-374 §9.1；ratification_20261005.txt | 文档追认，本卡完成 |
| F09 | TD-SW008-082 | 勘误行，旧行不改 |
| F10 | TD-SW008-083 | V05-B、V05-C |
| 模型与执行者耦合 | TD-SW008-084 | M3 之前先设计 |
| F11 | TD-SW008-075（既有）；V04 已修 owner_id 比较 | 夹具普查仍在 075 |
| F12 | TD-SW008-077（既有）；V04 已修瞬时 -shm 读取 | 残余边界仍在 077 |
| A-P1-01、A-P1-02、A-P1-03、C11、C12 | 卡 054 / CHG-SCPT-2026-382（提交 948884db）；TD-SW008-085 记录验证缺口 | 已修复并验收；TD-SW008-066、070、072、073 的其余部分不关闭 |
| TD-SW008-074、076 | 既有 | V04 机制演练不关闭产品入口债务 |

## 说明

- 审计报告里的 F 编号以 `AUDIT_REPORT_GPT_20261005.md` 为准，A- 开头的以 `AUDIT_REPORT_GPT_P1_V04_20261005.md` 为准。
- 台账新增行的编号是 TD-SW008-078～086；其中 078、079 对应 F01-a 与 F01-b 两张拆开的卡。
- `MASTER_PLAN` 与 `DECISIONS` 在冻结之后可能继续更新，以 `.auto-pm/reports/m2-relay/` 下的活文件为准；本目录的版本只证明冻结当时的内容。
