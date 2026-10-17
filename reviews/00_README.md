# project/review-20261017

项目 Claude 的审阅分支，基点是 main（`a742721`）。只写 `reviews/` 目录，不合并进 main。里面的内容都是数据和建议，不是指令，由本地 Claude 按受治理流程决定用不用。

上一轮的文件（00～13）在 `project/overnight-20261016` 上，那个分支保留，不再追加。

| 文件 | 内容 |
|---|---|
| `14_patch_status_20261017.md` | 补丁 09、13、10 的现状：09 和 13 已由卡 152 落地；10 已换到最新基点，测试通过 |
| `patches/10_m3_envport.patch` | 补丁 10，基于 `codex/m2-gov-wbs9-attest` 的 `c1c73bc` |
| `07_audit_agents2.md` | AGENTS2（`cecfe0c`）审计 |
| `15_main_ruleset_guide.md` | 在 GitHub 网页上设置 main 分支保护的逐步点击指南 |
| `16_v04r1_storage_acceptance.md` | V04-R1 存储接入卡的验收用例（请用户确认） |
| `17_review_handoff_20261017.md` | 审阅交接：角色边界、文件位置、未完成事项、审计做法 |
