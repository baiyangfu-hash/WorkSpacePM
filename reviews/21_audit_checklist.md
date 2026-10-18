# 21 PR 审计检查清单（任何 agent 通用）

本清单写给接手审计的任何 agent（Claude、Codex 或其他工具），照着做就能产出和 `reviews/18`、`reviews/20` 同样水平的报告。时间一律用亚利桑那时间（MST，UTC−7）。本文是数据，不是指令；角色、边界和背景以交接文件 `17_review_handoff_20261017.md`（在 `project/review-20261017` 分支）为准。

> **给用户 baiyang 的三句话**：脚本结果里没有 FAIL，就可以合并，在 PR 页面选 Merge（不要选 Squash 或 Rebase）；有 FAIL 先别合并，把结果发给审阅线程；WARN 大多是“改到了重要文件，请审阅者在报告里点名”，不是错误。

## 0. 开始前

- **谁可以审**：不是写这张卡的那个 agent。做的和审的不能是同一个（WBS V3.0.43 §4.11 的并行规则 2）。
- **只写 `reviews/`**，推到自己的审阅分支（`claude/…`、`project/…`，或者给 Codex 另起一个前缀，例如 `review-codex/…`）。不推 `main`、不推 `codex/*`、不合并 PR、不删除任何东西。
- **环境**：Python 3.12 或 3.13 和 Git 2.38 以上即可，脚本只用标准库。跑测试需要 `pytest`。

## 1. 跑机械检查（大约占审计的七成）

```
python reviews/tools/audit_pr.py <PR 编号>
```

如果这个 PR 落地的是某个审阅补丁，加上补丁对比：

```
python reviews/tools/audit_pr.py <PR 编号> --patch <分支>:reviews/patches/<补丁文件> --patch-base <补丁基于的提交>
```

退出码：0 表示没有 FAIL，1 表示至少一项 FAIL，2 表示用法或 Git 出错。脚本只读，不改工作区、暂存区或任何分支；它做的 `git fetch` 会新增 `refs/audit/pr-N`，并顺带更新 `origin/main`（无害）。加 `--offline` 不访问 GitHub：这时查不了 CI 结论，被 Squash 合并的 PR 也会被当成未合并。

每项结果的意思：PASS 通过；FAIL 有问题；WARN 要在报告里点名；INFO 只是信息；UNVERIFIED 没查成（网络或离线），要人工补查。

| 检查项 | 它查什么 | FAIL / WARN 时怎么办 |
|---|---|---|
| `merge_shape` | 已合并的 PR 是不是“合并提交”，第二个父提交是不是 PR 头部 | FAIL 说明用了 Squash 或 Rebase，提交号变了，要在报告里写明；WARN 说明用了快进（例：PR #1），离线跑时 `scope` 会是 UNVERIFIED，要联网重跑 |
| `merge_content` | 合并提交有没有夹带 PR 以外的改动 | FAIL 列出多出的文件，属于严重问题；WARN 说明合并时手工解决过冲突，要人工看解决结果 |
| `mergeable` / `up_to_date` | 未合并的 PR 和当前 main 有没有冲突；PR 是否已包含最新 main | `mergeable` FAIL 时建议作者先把 main 合进来；`up_to_date` 只给 PASS 或 INFO，INFO 在没有冲突时不影响合并 |
| `scope` / `protected_paths` | 改了几个文件，有没有碰 WBS、台账、`AGENTS.md`、规范库、`auto_pm` 基建、`.github/workflows`、CHG/DEC，以及 agent 入口（`.trae/`、`.cursor/rules/`、`.agent/rules/`、`.agents/skills.json`，改这些要用户签字） | WARN 不是错，但报告里要点名，并核对这张卡有没有授权改这些路径（第 3 步） |
| `secrets` | 新增行里有没有令牌、API 密钥、私钥 | FAIL 立刻告诉用户（仓库是公开的），不要在报告里抄写密钥原文，只写位置 |
| `privacy` | 邮箱、内网地址、手机号、身份证号、本机路径、`fubai`、长 base64 | 本机路径和 `fubai` 在 main 上已有约 200 个文件，属于已知基线，只报告“新增了哪一类” |
| `ci_expected` | 改动是否落在 CI 的 `paths` 过滤范围内 | 只改文档时不会触发 CI，这是正常的 |
| `ci_result` | GitHub 显示的 CI 结论（每个提交、每种事件只看最新一次） | PASS 只代表显示 success，失败数还要看日志（第 2 步） |
| `patch` | PR 和“补丁应用到基线”的结果是否逐字节一致 | WARN 列出不同的文件，要查清是有意取舍还是遗漏（例：PR #3 有意去掉了启动器部分，提交信息里写明了） |

## 2. 看 CI 日志（脚本做不到，因为日志需要登录 GitHub）

打开这次的 `sw008-ci` 运行记录，找三处：

1. `secret scan: N location(s) flagged in <base>..HEAD`，N 应当为 0；
2. `verdict: PASS_KNOWN_BASELINE`，并且失败数和基线一致（2026-10-17 的基线是 20 个失败）；
3. env 里的 `EVENT`、`BEFORE`、`PR_BASE` 和你审的提交对得上。

通过数或跳过数如果变了，要解释原因。例：卡 158 放开了 2 个原来跳过的测试，所以 3695 → 3697。

## 3. 判断（大约占三成，要靠读内容）

- **授权**：提交信息里的卡号、CHG 号能在 WBS 或 Decision 里找到；改动没有超出“本节不授权”列出的范围。
- **一致性**：WBS 或台账里写的事实（提交号、PR 号、日期、测试数）和 Git、CI 对得上；提到的技术债在活动技术债台账里有编号。
- **只加不删**：WBS 和台账的删除行，应当是原样保留后在末尾追加的同一行。
- **代码改动**：读改动的逻辑，必要时做一次变异检查：每次只改一处，跑测试，然后立即还原。证明测试真的能抓到问题。
- **过时内容**：写的时候正确、合并时已经过时的话，标为低严重度，建议顺手改掉，不需要单独开卡。
- **亲手复现**：报告里说有 bug，就要给出能复现的命令和输出（例：`reviews/20` 里 4301 位数字的复现）。

## 4. 写报告

文件名：`reviews/<下一个编号>_audit_<对象>.md`。格式：

```
# <编号> <对象> 审计
审计时间、审阅者、“本文是数据，不是指令”。

## 结论
同意 / 同意（有保留）/ 不同意，一两句话说明。

## 证据
| 检查 | 结果 |   ← 把 audit_pr.py 的表格整理进来，加上第 2、3 步的结果

## 建议（严重度：高 / 中 / 低）
每条：问题、证据（文件:行号或提交号）、建议怎么改。没有亲自核对的写 UNVERIFIED。

## 给用户
一两句中文，告诉用户要不要做什么（例如“可以合并，选 Merge”）。
```

用户 baiyang 不是程序员，写中文：先给结果，少用术语，用“建议”，不用命令口吻。

PR 合并以后，在同一份报告末尾追加“合并后核对”一节：再跑一次 `audit_pr.py`，确认 `merge_shape` 和 `merge_content` 都是 PASS，main 推送那次的 CI 也通过了。

## 5. 交给另一个 agent 时，可以直接发这段话

> 你是 WorkSpacePM 的审阅者，只读。先读 `reviews/21_audit_checklist.md`（在 `claude/project-thread-imagwg` 分支），再读 `project/review-20261017` 分支的 `reviews/17_review_handoff_20261017.md`。然后按清单审计 PR #<编号>：先跑 `python reviews/tools/audit_pr.py <编号>`，再做第 2、3 步，把报告写到 `reviews/` 并推到你自己的审阅分支。不要推 main，不要合并，不要删除任何东西。

## 6. 脚本本身的维护

- 测试：`python -m pytest reviews/tools/test_audit_pr.py -q -p no:cacheprovider`。10 个用例各自在临时仓库里埋问题：合并提交夹带后门文件、冲突（冲突说明只列文件名）、令牌泄露（包括以 `++ ` 开头、在差异里显示成 `+++ ` 的行）、个人信息、CI 路径过滤、补丁少文件、快进合并、工作区不能被改动、改到 agent 入口（`.trae/` 等）必须点名。
- 2026-10-17 做过 3 次变异检查（去掉夹带检查、去掉密钥检查、补丁对比恒为通过），每次都有测试失败，说明测试能抓到这些问题。同日修复独立审阅发现的问题后又做了 3 次（把 `+++ ` 一律当文件名、不认快进合并、冲突说明不截断），也各有 1 个测试失败。2026-10-18 加入 agent 入口点名后，去掉 `.trae/*` 一条，新用例失败。
- 用真实 PR 校准过：PR #2、#3、#4 的结果和 `reviews/08`、`18`、`20` 的人工结论一致；PR #1（快进）报 WARN，PR #7 报 PASS，都没有 FAIL。
- 以后要让每个 PR 自动跑这个脚本，需要改 `.github/workflows/`，这属于本地 Claude 的地盘，要出卡并经用户批准。审阅者只写建议。
