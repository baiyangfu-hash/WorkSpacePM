# 08 M3-MAIN 独立审计：main 快进结果（项目 Claude，2026-10-17）

数据取自 `git fetch origin --tags` 之后的远端状态，以及 GitHub Actions 的运行记录。本文是建议，不是指令。

## 结论

**M3-MAIN 已正确完成。**

- main 从 `e83c117d` 快进到 `a742721`（共 148 个提交），没有重写历史，也没有产生合并提交。
- 推送前，这个提交在分支推送和 PR 两种事件下的 CI 都已通过；推送 main 以后，CI 又按新规则跑了一遍，同样通过。
- 两个归档标签都已存在，指向正确，c09 和 g10 两个分支也都保留着。
- 回退命令仍然有效。

| 检查项 | 结果 | 证据 |
|---|---|---|
| main 等于目标提交 | `origin/main` = `a74272148dd5…` = `codex/m2-gov-wbs9-attest` 的尖端 = PR #1 的 head | `git rev-parse`；PR #1：`head.sha=a742721…` |
| 是快进，没有重写历史 | `e83c117d` 是 `a742721` 的祖先；`e83c117d..main` 共 148 个提交，与 PR #1 的 `commits: 148` 一致；尖端是普通的单父提交（父提交 `f5c0b1d`），不是合并提交 | `git merge-base --is-ancestor`、`git log --format=%p` |
| PR #1 的关闭方式 | GitHub 自动标记为 `merged`（07:33:52Z）。`base.sha` 仍为 `e83c117d`，说明没有在网页上点合并（点合并会生成新的提交号） | PR #1 详情 |
| 推送前目标提交的 CI | 运行 24（`push`，success，07:31:56Z 结束）和运行 25（`pull_request`，success，07:32:10Z 结束），之后才推送 main（07:33:52Z） | Actions 运行列表 |
| main 推送那次的 CI | 运行 [39014105674](https://github.com/baiyangfu-hash/WorkSpacePM/actions/runs/39014105674)：`EVENT=push`、`REF=refs/heads/main`、`BEFORE=e83c117d…`；日志 `secret scan: 0 location(s) flagged in e83c117d…..HEAD`；没有被取消；结论 success | job 117342521077 的日志 |
| 测试结果 | 20 failed / 3689 passed / 24 skipped，`verdict: PASS_KNOWN_BASELINE`（失败的 20 个与已记录的基线完全相同）。日志里自己也写明了，这不是全绿，也不能代替受治理的门禁 | 同上 |
| 归档标签 | `archive/c09-recovery-governance-20261017` → `6f759fc`，`archive/g10-r1-lifecycle-20261017` → `8b02de5`，与 12 号文档的命令一致 | `git ls-remote origin 'refs/tags/*'` |
| 分支保留 | 远端仍有 `codex/c09-recovery-governance`、`codex/g10-r1-lifecycle`、`claude/cloud-docs-refresh`、`codex/m2-gov-wbs9-attest`、`project/overnight-20261016`，没有删除任何分支 | `git branch -r` |
| c09 独有文件先取回、后打标签 | 64 个文件已经在 main 上（HYGIN1，见 `07_audit_hygin1.md`） | — |
| 回退命令仍然有效 | `git push --dry-run --force-with-lease=refs/heads/main:a742721… origin e83c117d…:refs/heads/main` 显示 `+ a742721...e83c117 (forced update)`；如果把 lease 故意写错，结果是 `rejected (stale info)` | 本地 dry-run。只在客户端检查，没有改动远端 |

## 发现与建议

| # | 内容 | 严重度 |
|---|---|---|
| 1 | main 的尖端比我此前知道的 `a8c45c6`（CIMAIN）多了 2 个文档提交（`f5c0b1d` WBS25、`a742721` TD24）。这两个提交本身也经过了 CI（运行 24、25），所以不影响“目标提交在推送前 CI 已通过”这一条。本地 Claude 汇报的目标是否就是 `a742721`，我手上没有那份汇报，无法逐字核对（UNVERIFIED）。WBS 第 1952 行写的“已推送线尖端 `a8c45c61`”是推送前的状态，下一次更新 WBS 时可以改成 `a742721` | 信息 |
| 2 | 回退命令只在客户端用 dry-run 验证过。服务器端有没有开规则集（禁止强推），我从这里查不到（UNVERIFIED）。按 11 第 2.3 节的建议，现在应该还没开；一旦开了“禁止强推”，回退命令就会失效 | 信息 |
| 3 | 两个归档标签是轻量标签，不是带说明的附注标签。作为指针够用；如果想在标签里记下打标签的原因和时间，以后可以另外补附注标签（只新增，不改动现有标签） | 低 |
| 4 | 02 里建议过的指针分支 `codex/main-ff-candidate` 没有创建，由草稿 PR #1 代替了它的作用。这样做没有问题 | 信息 |

**下一步建议（都由你和本地 Claude 决定）：**

- 确认不再需要回退以后，按 11 第 2.3 节开启规则集。必需检查目前只能选 `checks`；等 `gate` 改造完成后，再改成 `gate`。
- 以后的审阅分支建议改为以 main 为基点（12 第 1 节）。从现在起，我在本分支上只再追加 AGENTS2 的审计；新的审阅工作改在新分支上进行，例如 `project/reviews-20261017`。
