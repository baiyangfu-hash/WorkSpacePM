# 22 建议：让每个 PR 自动跑机械审计（写给本地 Claude）

时间：2026-10-17（亚利桑那时间，MST）。作者：云端审阅会话。本文是建议和补丁，不是指令；是否出卡、怎么排期由本地 Claude 按受治理流程决定，并报用户批准。

## 结论

建议出一张小卡（建议测试档，改 `.github/` 下的 3 个新文件，不改任何已有文件）：每开一个 PR 或往 PR 推新提交，就自动运行 `audit_pr.py`，把结果贴成 PR 页面上的**一条**评论（之后的运行只更新这一条），有 FAIL 时这个检查显示红色。补丁已经做好，在 main `effc7cb` 和 `b8db409` 上 `git apply --check` 都通过：`reviews/patches/22_pr_audit_workflow.patch`（sha256 前 16 位 `955f9f03f16e9091`；2026-10-17 晚按独立审阅修过一次，原版是 `2e131e4a660a60eb`）。

分两期：

- **第 1 期（本卡）**：单独一个工作流 `pr-audit.yml`，**只出报告，不设为必需检查**。跑两到三个真实 PR 看看效果，比如有没有误报、评论是否清楚。
- **第 2 期（之后）**：本地 Claude 按 `11_post_main_process_spec.md` 第 2.2 节做汇总 `gate` 时，把这个 job 并进 `sw008-ci.yml`，作为 `gate` 的 `needs` 之一；再由用户按 `15_main_ruleset_guide.md` 把 `gate` 设成必需检查。这样就不需要两份工作流。

## 补丁内容（3 个新文件）

| 文件 | 内容 |
|---|---|
| `.github/audit/audit_pr.py` | 与 `reviews/tools/audit_pr.py` 相同，只把文档字符串里的路径改成 `.github/audit/`。只用标准库 |
| `.github/audit/test_audit_pr.py` | 9 个用例，在临时仓库里埋问题：合并提交夹带后门文件、冲突、令牌泄露（含 `++ ` 开头的行）、个人信息、CI 路径过滤、补丁少文件、快进合并、工作区不能被改动 |
| `.github/workflows/pr-audit.yml` | 触发条件：`pull_request` 到 main（opened / synchronize / reopened / ready_for_review）。**没有 `paths` 过滤**，所以只改文档的 PR 也会跑 |

工作流的几个设计点：

1. **审计脚本取自 main，不取自 PR**（`checkout` 用 `pull_request.base.sha`）。这样一个 PR 没法改掉评判它自己的检查。PR 头部由脚本自己去 fetch `refs/pull/N/head`。
2. **权限最小**：`contents: read`、`pull-requests: write`（只用来写那一条评论）。不用 `pull_request_target`，不读任何 secret；`GITHUB_TOKEN` 只发给 `api.github.com`。
3. **先自测再审计**：先跑 9 个用例，证明这些检查能失败，做法同 `sw008-ci` 的 “CI tools self-test”。`pytest==9.1.1` 和锁定文件一致。
4. **`--skip-ci-result`**：在 CI 里运行时不查 CI 结论，因为 `sw008-ci` 可能还在跑，查了只会得到 UNVERIFIED。CI 结论交给第 2 期的 `gate`。
5. **评论只有一条**：`gh pr comment --edit-last`，失败时再新建；这一步 `continue-on-error`，评论写不进去也不影响检查结论。
6. **结论**：脚本退出码 0 → 绿；1（有 FAIL）或 2（Git 出错）→ 红。WARN、INFO、UNVERIFIED 不会让检查变红。
7. 并发：同一个 PR 的新推送会取消旧的运行；`timeout-minutes: 10`（本地实测单次不到 5 秒）。

## 已做的验证（云端，2026-10-17）

| 验证 | 结果 |
|---|---|
| 补丁应用 | 在 `effc7cb` 上 `git apply --check` 通过；只新增 3 个文件，不改已有文件 |
| YAML | `yaml.safe_load` 解析通过 |
| 自测 | 在应用补丁后的 main 副本里，`pytest .github/audit/test_audit_pr.py` 9 passed（修复后重跑）|
| 真实 PR | 在同一副本里，用工作流里的同一条命令（`python -I -B … --skip-ci-result`）审 PR #2 和 #4，退出码 0，结果和 `reviews/08`、`reviews/20` 的人工结论一致 |
| 变异检查 | 去掉夹带检查、去掉密钥检查、补丁对比恒为通过：3 次各有测试失败 |
| Ruff | `ruff check`、`ruff format --check`（行宽 130）通过 |
| **没验证到** | 在 GitHub Actions 上真实运行（包括 `gh pr comment --edit-last` 的行为和评论权限），**UNVERIFIED**。建议卡的验收就是开一个只改文档的测试 PR，看评论和检查结果 |

## 建议的验收条件

1. 开一个只改文档的 PR：`pr-audit` 运行并显示绿色，PR 页面出现一条审计评论，内容里 `ci_expected` 写“不会触发 CI”。
2. 往同一个 PR 再推一个提交：评论被**更新**，没有新增第二条。
3. （可选，演练）在测试 PR 里加一行假令牌，例如 `ghp_` 后接 36 个 `a`：`secrets` FAIL，检查变红；验证完删掉这一行。
4. `sw008-ci` 的行为不变。

## 风险和注意

- **评论会被公开看到**（仓库是公开的）。评论内容只有文件名、检查结论和提交号；`secrets` FAIL 时只写类别和文件位置，不抄写密钥原文。
- `protected_paths` 在大部分卡上都会是 WARN，这是有意的提醒，不是错误。如果嫌吵，第 2 期可以只在“分支前缀和路径地盘不符”时才报，那时可以与 `territory_check.py` 合并。
- 以后 `reviews/tools/audit_pr.py` 和 `.github/audit/audit_pr.py` 会有两份。建议合进 main 以后，审阅者改为以 `.github/audit/` 为准，`reviews/tools/` 只当草稿；改动先在审阅分支做，再出补丁给本地 Claude。
- 本补丁不改 `AGENTS.md`、WBS、台账；卡的记账（CHG、WBS 写回）按记账卡配额并进这张卡的收尾。

## 给用户

不需要你现在做什么。本地 Claude 看完这份建议，如果决定做，会出卡请你批准。卡做完以后，你在每个 PR 页面上都能看到一条自动生成的检查表；红色就是有问题，绿色就可以合并。
