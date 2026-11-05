# M3 发版 7.2｜发版候选构建与全量门禁（合同与结论）

> 报告冻结日期：2026-11-04（本文件字节在门禁前冻结，提交日期以 Git 提交为准）；实施卡 `CARD-SW008-M3-REL72 V1.0`；门禁合同与卡 220 相同。
> **本报告的结论由提交本身证明**：本文件只在下表每一项都通过之后才被提交；任何一项不过，卡停在原地、不提交，本文件不会出现在 `main` 上。原始证据在控制根 `.auto-pm/reports/m3-rel72/gates/`。

## 1. 冻结的合并提交

`dd8b192f2e0a8ffdc370fd7e2dc4f7a999bb7642`（`main` 上的 Merge pull request #550）。十组回归的基线是发版 7 的受治理输出（产品等于 `1.3.3-d671611`，冻结提交 `d671611a`）；两者之间合进 `main` 的提交如下（第一父链）：

| 合并提交 | 说明 |
|---|---|
| `dd8b192f` | Merge pull request #550 from baiyangfu-hash/claude/tests-record-holder-pid-20261104 |
| `5bc30c9a` | Merge pull request #549 from baiyangfu-hash/claude/project-thread-49uqw5-agents-ptr |
| `0288a30c` | Merge pull request #547 from baiyangfu-hash/claude/project-thread-49uqw5-m3v10 |
| `76ddb5ee` | Merge pull request #548 from baiyangfu-hash/claude/tests-popup-and-gbk-20261104 |
| `ee763a14` | Merge pull request #546 from baiyangfu-hash/claude/project-thread-49uqw5 |
| `00d0353e` | Merge pull request #545 from baiyangfu-hash/claude/project-thread-49uqw5-banners |
| `4324c036` | Merge pull request #543 from baiyangfu-hash/claude/project-thread-49uqw5-docs-refresh |
| `ac61b58c` | Merge pull request #544 from baiyangfu-hash/claude/project-thread-49uqw5-agents-md |
| `d8280ed8` | Merge pull request #541 from baiyangfu-hash/claude/project-thread-q77wsy |
| `133a163e` | Merge pull request #540 from baiyangfu-hash/claude/holder-pid-skip-shells |
| `5421d432` | Merge pull request #542 from baiyangfu-hash/claude/project-thread-49uqw5 |
| `84f4245f` | Merge pull request #521 from baiyangfu-hash/claude/project-thread-u0qdo3 |
| `6b72a620` | Merge pull request #537 from baiyangfu-hash/claude/project-thread-49uqw5 |
| `26157a48` | Merge pull request #538 from baiyangfu-hash/claude/project-thread-49uqw5-empty-test-folder |
| `2fd3894e` | Merge pull request #536 from baiyangfu-hash/claude/gitignore-untracked-runtime-20261104 |
| `4101cb7e` | Merge pull request #535 from baiyangfu-hash/claude/handover-29-refresh |
| `ac44fa9c` | Merge pull request #534 from baiyangfu-hash/claude/project-thread-6ucs3k-state-backup-config |
| `33ca4610` | Merge pull request #533 from baiyangfu-hash/claude/project-thread-6ucs3k-state-backup-2 |
| `c2ac1741` | Merge pull request #531 from baiyangfu-hash/claude/project-thread-6ucs3k |
| `04dfb0ce` | Merge pull request #530 from baiyangfu-hash/claude/project-thread-6ucs3k |
| `92b64fc5` | Merge pull request #527 from baiyangfu-hash/claude/prA2-dec-setlb2b1 |
| `66eed287` | Merge pull request #529 from baiyangfu-hash/claude/handover-prd-20261104 |
| `50929e07` | Merge pull request #528 from baiyangfu-hash/claude/handover-prc-20261104 |
| `9067d6f6` | Merge pull request #526 from baiyangfu-hash/claude/handover-prb-20261104 |
| `3121e093` | Merge pull request #525 from baiyangfu-hash/claude/project-thread-ljkxr2 |
| `d5fc81df` | Merge pull request #522 from baiyangfu-hash/claude/project-thread-491ykm |
| `ff17c232` | Merge pull request #523 from baiyangfu-hash/claude/ps1-parse-guard |
| `5491f803` | Merge pull request #519 from baiyangfu-hash/claude/memory-gate |
| `bba07fa1` | Merge pull request #520 from baiyangfu-hash/claude/project-thread-0vm0po |
| `98f95235` | Merge pull request #510 from baiyangfu-hash/claude/rules-approval-board |
| `63ae3246` | Merge pull request #518 from baiyangfu-hash/claude/long-run-evidence |
| `d5632931` | Merge pull request #514 from baiyangfu-hash/claude/long-run |
| `e4cfc99f` | Merge pull request #517 from baiyangfu-hash/claude/ptr-d671611-integrated |
| `cf8e8d7f` | Merge pull request #513 from baiyangfu-hash/claude/memory-preflight |
| `51368334` | Merge pull request #512 from baiyangfu-hash/claude/lease-wallet-diagnostics |
| `c07449c9` | Merge pull request #511 from baiyangfu-hash/claude/safety-sign-12 |
| `2c0c0de2` | Merge pull request #509 from baiyangfu-hash/claude/project-thread-0nrp1r |
| `7df4f16b` | Merge pull request #507 from baiyangfu-hash/claude/rel7-switch-evidence-20261103 |
| `8db3befb` | Merge pull request #499 from baiyangfu-hash/claude/project-thread-0rmx1t |
| `b86c917e` | Merge pull request #506 from baiyangfu-hash/claude/b2-settlement-decisions-20261103 |
| `2dd6bff9` | Merge pull request #498 from baiyangfu-hash/claude/project-thread-0nrp1r |
| `a6335657` | Merge pull request #503 from baiyangfu-hash/claude/project-thread-ov14bq |
| `c7224288` | Merge pull request #497 from baiyangfu-hash/claude/project-thread-0nrp1r |

产品子树（`auto_pm`、`templates`、`scripts`）共有 49 个文件不同。事先声明的通过数差值：rest +12、infrastructure +217、cli +43、core +101；跳过数差值：infrastructure +5。样件联调的 4 个测试文件不在本卡跑，证据：GitHub 上 sample-drill 工作流在 main 的推送运行 41916531376（提交 d8280ed8f175，结论 success）；该提交到冻结点之间 auto_pm、templates、scripts 与 tests/e2e 没有任何文件变化（仅三个非样件联调的测试文件不同），证据有效

## 2. 门禁合同与对应检查

| 门禁 | 本卡怎么检查 | 通过标准 |
|---|---|---|
| 构建入口自身的测试 | `tests/core/test_pmf_build.py` | 退出码 0，无跳过 |
| 母体全量 pytest | 十组回归，在冻结提交的隔离工作树里跑 | 每组无失败、无 ERROR，通过数与跳过数等于基线加事先声明的差值 |
| Ruff/Mypy | `ruff check auto_pm tests`、`mypy --platform win32 auto_pm` | 退出码 0 |
| 全库 Ruff/Mypy 审计 | `ruff check .`、`mypy auto_pm tests` | 原始结果如实记录，不写“全绿” |
| 文档检查与本报告 | `doc check`；本报告的逐行合同 | 退出码与基线相同；合同满足 |
| Git 双 Hook | 真实 pre-commit 钩子对本卡暂存的文件干跑；提交时正常经过钩子 | 退出码 0，无绕过 |
| Run 执行就绪 | 控制根 `pm orient SW-2026-008 --json` | 冲突列表为空 |
| 台账 | 全部注册项目（SYS-2026-001、SW-2026-008、SW-2026-009、DJ-2026-005、SW-2026-010、DJ-2026-011）的 `ledger reconcile` | 每个项目 0/0/0 |
| 可复现构建与加载身份 | 同一提交构建两次，两份载荷逐字节相同、`release_meta.json` 除构建机信息外相同，两份都通过 `verify`；从载荷导入 `auto_pm` 并运行命令行 | 全部成立 |
| 提交钉住与防睡眠 | 门禁前后工作树 HEAD 都等于冻结提交；心跳无超过 120 秒的缺口；电源证据在 | 全部成立 |

## 3. 不做什么

不切换有效发布版本、不改发布指针（切换另走切换卡，须门禁与独立审计全部通过，且用户亲口说“切换”）；WBS 与台账的回写不在本卡。
