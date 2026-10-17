# 01 M3-CIMAIN 工作流只读审阅（云端 Claude，2026-10-17）

审阅对象：`.github/workflows/sw008-ci.yml` @ `23e841b`，以及任务单里描述的计划改动。只读，本文不是指令，只是建议。

## 结论

**同意（附 4 项修改）。** 计划的三处改动方向正确：去掉 `branches-ignore`、新增 `pull_request`、秘密扫描基线按事件选取。但照原样实施会出 4 个问题：

| # | 问题 | 严重度 |
|---|---|---|
| A | 普通分支的推送如果也改用 `github.event.before`，被 `cancel-in-progress` 取消的那次推送里的提交就再也不会被扫描 | 高 |
| B | `before` 在仓库里不存在（强推、浅历史）时，`git log before..HEAD` 直接报错，CI 变红但原因不明 | 中 |
| C | main 上 `cancel-in-progress: true`：连续两次推送 main，前一个提交永远拿不到 CI 结论，而 M3-MAIN 的条件恰好是“在 CI 通过的提交上” | 中 |
| D | `${{ }}` 直接拼进 `run:` 存在脚本注入面，事件字段应走 `env:` | 低（目前字段都是 SHA，按惯例收紧） |

## 证据

- 推送触发与排除：`sw008-ci.yml:7-13`（`branches-ignore: [main]`、`paths`、`workflow_dispatch`）。
- 并发：`sw008-ci.yml:20-22`，`group: sw008-ci-${{ github.ref }}`，`cancel-in-progress: true`。
- 检出：`sw008-ci.yml:41`，`fetch-depth: 0`，所以 `origin/main`、PR 的 base SHA 和推送的 `before` 通常都在本地。
- 扫描：`sw008-ci.yml:62` 调用 `secret_scan.py origin/main`；`tests/tools/sw008_ci/secret_scan.py` 执行 `git log -p <base>..HEAD`，`check=True`。基线不存在时抛 `CalledProcessError`，表现为红灯，而不是“扫描不可用”。

## 建议的完整 diff

```diff
 on:
   push:
-    branches-ignore: [main]
     paths:
       - "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/**"
       - "00_Infrastructure/auto_pm/environment/**"
       - ".github/workflows/sw008-ci.yml"
+  pull_request:
+    branches: [main]
+    paths:
+      - "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/**"
+      - "00_Infrastructure/auto_pm/environment/**"
+      - ".github/workflows/sw008-ci.yml"
   workflow_dispatch:

 concurrency:
   group: sw008-ci-${{ github.ref }}
-  cancel-in-progress: true
+  # main 上的每个提交都要有结论（M3-MAIN 以“CI 通过的提交”为条件），所以 main 不取消。
+  cancel-in-progress: ${{ github.ref != 'refs/heads/main' }}
```

```diff
-      - name: Secret scan (lines added since main)
-        run: python -I "$PROJ/tests/tools/sw008_ci/secret_scan.py" origin/main
+      - name: Secret scan (lines added by this change)
+        env:
+          EVENT: ${{ github.event_name }}
+          REF: ${{ github.ref }}
+          BEFORE: ${{ github.event.before }}
+          PR_BASE: ${{ github.event.pull_request.base.sha }}
+        run: |
+          # 普通分支（push、workflow_dispatch）：仍然扫描 origin/main..HEAD 全段，
+          # 这样被并发取消的推送里的提交下一次也会被扫到。
+          base=origin/main
+          if [ "$EVENT" = pull_request ]; then
+            base="$PR_BASE"
+          elif [ "$EVENT" = push ] && [ "$REF" = refs/heads/main ]; then
+            base="$BEFORE"
+          fi
+          if [ -z "$base" ] || [ "$base" = 0000000000000000000000000000000000000000 ] \
+             || ! git cat-file -e "$base^{commit}" 2>/dev/null; then
+            echo "::error::secret scan base '$base' is not available in this checkout; scan refused (fail closed)"
+            exit 1
+          fi
+          python -I "$PROJ/tests/tools/sw008_ci/secret_scan.py" "$base"
```

说明：

1. **A 的处理方式**：只有推送 main 时才用 `before`，普通分支保持 `origin/main` 全段扫描，和现在一样。原因是普通分支开着 `cancel-in-progress`，如果改用 `before`，被取消那次推送里新增的行会永远漏扫。main 不取消（见 C），所以在 main 上用 `before` 是安全的。
2. **B 的处理方式**：基线拿不到时明确失败（fail closed），并给出一行原因，而不是抛出 Python 栈。main 上 `before` 全零只会出现在第一次创建 main 时，现在不会发生，所以全零也按失败处理，不需要回退到 `origin/main`（在 main 上回退到 `origin/main` 就是空扫）。
3. **M3-MAIN 回退场景**：`--force-with-lease` 把 main 退回 `e83c117d` 时，`before` 是 X。因为 `fetch-depth: 0` 会带上 `codex/m2-gov-wbs9-attest`，X 仍然存在；`X..e83c117d` 为空，扫描通过，符合预期。
4. **PR 场景**：`actions/checkout` 检出的是 `refs/pull/N/merge`。`base.sha..HEAD` 覆盖分支上的每个提交；合并提交在 `git log -p` 下默认不出 diff，所以不会重复计数。

## 其他风险（不需要现在改，建议记录）

- **`pull_request` 与 fork**：fork 来的 PR 拿到的是只读 token、没有密钥。本工作流 `permissions: contents: read` 且不用密钥，不受影响。不要改成 `pull_request_target`，否则会以仓库权限运行 fork 的代码。（严重度：信息）
- **重复运行**：分支推送一次、它的 PR 再跑一次，两者的 `github.ref` 不同（`refs/heads/x` 与 `refs/pull/N/merge`），不会互相取消，同一个提交会跑两遍。可以接受；不建议把 group 合并，否则分支推送会取消 PR 的检查。（低）
- **`paths` 与将来的必需检查**：M3-COLLAB 如果把 `sw008-ci` 设为必需检查，不碰这些路径的 PR（例如只改 `reviews/`、WBS 文档）会一直停在“等待检查”，无法合并。到时需要一个永远运行、只做汇总的 job，或者改用规则集。（中，属于 M3-COLLAB）
- **`workflow_dispatch` 在 main 上**：基线是 `origin/main`，即空扫。手动在 main 上触发时扫描没有意义，其余检查照常。（低，记录即可）
- **草稿 PR**：`pull_request` 默认类型（opened、synchronize、reopened）对草稿 PR 也会触发，所以“X → main 草稿 PR 先跑 CI，再快进推送”这一方案可行。快进推送后 GitHub 会把 PR 标为已合并。（信息）
- **快进推送 main 那一次**：`before` = `e83c117d`，`e83c117d..X` 是全部 142+ 个提交，和此前普通分支上 `origin/main..HEAD` 的范围相同，耗时可接受。（信息）

## 验证建议

- 改完先在分支上推一次，确认 GitHub 接受语法、普通分支的扫描仍是 `origin/main..HEAD`（日志里打印的范围可以证明）。
- B 的失败分支可以本地模拟：`base=deadbeef` 跑这段脚本，应该看到 `::error::` 那行并退出 1。
- `pull_request` 和 main 推送两条路径，用 M3-MAIN 的草稿 PR 和随后的快进推送各验证一次。
