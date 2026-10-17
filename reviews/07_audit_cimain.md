# 07 CIMAIN 独立审计：sw008-ci 覆盖 main 与 PR（项目 Claude，2026-10-17）

审计对象：提交 `a8c45c6`（`ci: [CHG-SCPT-2026-423] … (M3-CIMAIN)`），父提交 `e0d452d`，只改了 `.github/workflows/sw008-ci.yml`（+31/−5）。本文是建议，不是指令。

## 结论

**同意。** 改动与 `01_cimain_workflow.md` 的设计一致，可以随 M3-MAIN 推上 main。

PR #1 本身是草稿 PR，它已经替我们做完了“真实 PR 验证”里的三项观察：

- `pull_request` 事件确实触发了；
- 秘密扫描的基线用的是 `base.sha`；
- 草稿 PR 也会触发。

所以我建议**不再单独开试验 PR**，剩下的“推送 main 时基线取 `before`”这一项，用 M3-MAIN 那次真实推送来观察（放进 08 主线审计）。

| # | 发现 | 证据 | 严重度 |
|---|---|---|---|
| 1 | `pull_request` 触发、草稿 PR 触发、`base.sha` 基线三项都已在真实运行中得到验证 | 运行 [39012658404](https://github.com/baiyangfu-hash/WorkSpacePM/actions/runs/39012658404)：事件 `pull_request`，`REF=refs/pull/1/merge`，`PR_BASE=e83c117d…`，日志 `secret scan: 0 location(s) flagged in e83c117d…..HEAD`，检出的是合并提交 `b03236c0`（a8c45c6 合入 e83c117d），结论 success | 信息（通过） |
| 2 | 同一个提交现在会跑两次：分支推送一次（`push`），PR 同步一次（`pull_request`），两个检查都叫 `checks` | 运行 39012656027（push）和 39012658404（pull_request），head 都是 `a8c45c6` | 低：多花一份 CI 时间。以后在规则集里把 `checks` 设为必需检查时，任意一个通过就会被当作通过；按 11 第 2 节改成汇总 job `gate` 以后，这个问题自然消失 |
| 3 | 在 main 上手动运行（`workflow_dispatch`）时，基线是 `origin/main`，扫描范围 `origin/main..HEAD` 是空的，等于什么都不扫 | 本地复现，见下面“基线逻辑” | 低：手动运行本来就不是门禁，日志也会写明扫描的范围。如果想让它有意义，可以给手动运行加一个输入项来指定基线 |
| 4 | `paths` 过滤仍在：以后如果有一次推送 main 没有碰这三类路径（例如只改 `reviews/` 或 WBS），这次推送就不会有 CI 结论 | `on.push.paths` | 信息：M3-MAIN 这一次一定会碰到这些路径，不受影响。长期方案见 11 第 2 节（工作流不设 `paths`，改用一个永远运行的 `gate`） |

## 核对过程

### 与 01 设计逐条对照

| 01 的要求 | `a8c45c6` | 结果 |
|---|---|---|
| `push` 去掉 `branches-ignore: [main]`，保留 `paths` | 是 | 一致 |
| 增加 `pull_request: branches: [main]`，使用同一组 `paths` | 是 | 一致 |
| `cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}` | 是，并附了注释说明原因 | 一致 |
| 按事件选基线：推送 main 用 `before`，PR 用 `base.sha`，其他用 `origin/main` | 是 | 一致 |
| 拿不到基线就拒绝扫描（fail closed） | 空值、全零、在检出里找不到，三种情况都 `exit 1`，并输出一行 `::error::` | 一致 |
| 事件字段一律经 `env` 传入，不直接拼进脚本 | 是（`EVENT`、`REF`、`BEFORE`、`PR_BASE`） | 一致，没有注入面 |
| `fetch-depth: 0` | 原来就有 | 一致，`before` 和 `base.sha` 都能在检出里找到 |
| 不改检查步骤、测试基线、密钥和分支保护 | `git show --stat` 只有这一个文件；检查步骤没有变化 | 一致 |

YAML 用 PyYAML 解析通过；`on` 和 `concurrency` 解析出的结构与上表相同。

### 基线逻辑（把这一步脚本原样取出，在本地用 8 组输入运行）

| 事件 | ref | before | base.sha | 结果 |
|---|---|---|---|---|
| pull_request | refs/pull/1/merge | — | 空 | 拒绝，exit 1 |
| pull_request | refs/pull/1/merge | — | 全零 | 拒绝，exit 1 |
| push | refs/heads/main | 全零 | — | 拒绝，exit 1 |
| push | refs/heads/main | 不存在的提交 | — | 拒绝，exit 1 |
| push | refs/heads/main | `e83c117d…` | — | 扫描 `e83c117d..HEAD` |
| pull_request | refs/pull/1/merge | — | `e83c117d…` | 扫描 `e83c117d..HEAD` |
| push | refs/heads/project/x | — | — | 扫描 `origin/main..HEAD` |
| workflow_dispatch | refs/heads/main | — | — | 扫描 `origin/main..HEAD`（在 main 上为空，见发现 3） |

### 回退场景

02 第 3 节的回退命令会强推 main 回到 `e83c117d`。那次推送的 `before` 是 X，X 不是新 HEAD 的祖先，所以 `X..HEAD` 是空的，什么也不扫。这是正确的：回退不会引入新内容。另外，X 仍然在 `codex/m2-gov-wbs9-attest` 上，`fetch-depth: 0` 能取到它，不会触发 fail closed。

### CI 结果

- 这两次运行里，测试都是 20 failed / 3689 passed / 24 skipped。经过 `compare_baseline.py` 和 `baseline.linux.json` 对比，这 20 个失败都是已知失败，job 结论为 success。
- 本卡没有改测试基线，所以与之前的运行一致。

## 建议

1. 不单独开试验 PR，理由见结论。M3-MAIN 推送以后，08 主线审计里会检查那次 `push` 运行：`BEFORE` 应为 `e83c117d…`，扫描范围应为 `e83c117d..a8c45c6`（或者最终的 X），并且没有被取消。
2. 发现 2、4 都并入 11 第 2 节的 `gate` 改造，不需要单独开卡。
