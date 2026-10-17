# 12 远端分支与 main 的关系及清理建议（项目 Claude，2026-10-17，只读）

数据取自 `git fetch origin` 之后的远端状态（2026-10-17，main 仍在 `e83c117`，M3-MAIN 尚未执行）。按“绝不删除”的裁决，下表只给出“保留”或“打归档标签后保留”两种建议，不建议删除任何分支。本文是建议，不是指令。

| 分支 | 尖端 | 相对 main（领先/落后） | 不在 m2 中的提交 | 关系 | 建议 |
|---|---|---|---|---|---|
| `main` | `e83c117` 2026-09-21 | — | — | 将被快进到 X | M3-MAIN |
| `codex/m2-gov-wbs9-attest` | `23e841b` 2026-10-16 | +143 / −0 | — | 活跃主线，main 的后代 | 保留；M3-MAIN 之后仍是本地 Claude 的工作分支 |
| `codex/g10-r1-lifecycle` | `8b02de5` 2026-09-27 | +11 / −0 | 0 | **已完全包含**在 m2 中 | 打标签 `archive/g10-r1-lifecycle-20261017`，分支保留 |
| `codex/c09-recovery-governance` | `6f759fc` 2026-09-30 | +59 / −41（**分叉**） | 59 个提交，其中 57 个在 m2 中没有等价补丁（`git cherry`：57 个 `+`、2 个 `-`） | 分叉；其中 64 个文件只存在于 c09 上（见 02 第 4 节） | 先按 02 把 64 个文件取回主线，再打标签 `archive/c09-recovery-governance-20261017`，分支保留。不要合并 c09 的历史（与 m2 有 5 处台账冲突） |
| `claude/cloud-docs-refresh` | `66424dc` 2026-10-11 | +93 / −0 | 1 个（`66424dc`，提交说明自注 “CANDIDATE, not a governed commit”） | m2 的祖先线上多了 1 个未治理的候选提交 | 保留，不打归档标签：它是一份待评审的候选内容。以后作为单独 PR（`claude/cloud-docs-refresh` → main）评审，或者由本地 Claude 决定作废，作废时再打标签 |
| `project/overnight-20261016` | 持续更新 | m2 尖端 `23e841b` + 只改 `reviews/` 的提交 | 只含 `reviews/**` | 审阅数据通道 | 保留；不合进 main。M3-MAIN 之后，建议审阅改在以 main 为基点的新分支（例如 `project/reviews-<日期>`）上继续，这样 PR 的差异只显示审阅文件 |

## 核对命令（可复现）

```bash
git fetch origin
for b in $(git branch -r --format='%(refname:short)' | grep -v HEAD); do
  echo "$b +$(git rev-list --count origin/main..$b) -$(git rev-list --count $b..origin/main)"
done
git cherry origin/codex/m2-gov-wbs9-attest origin/codex/c09-recovery-governance | cut -c1 | sort | uniq -c
git merge-base --is-ancestor origin/codex/g10-r1-lifecycle origin/codex/m2-gov-wbs9-attest && echo g10_contained
```

## 标签命令（建议在 M3-MAIN 之后执行，只新增、不删除）

```bash
git push origin refs/remotes/origin/codex/g10-r1-lifecycle:refs/tags/archive/g10-r1-lifecycle-20261017
git push origin refs/remotes/origin/codex/c09-recovery-governance:refs/tags/archive/c09-recovery-governance-20261017
```

打标签后，按 11 第 2.3 节开启 `archive-tags` 规则集（禁止删除、禁止更新），归档标签就不会再被移动。

## 本机分支（UNVERIFIED）

云端只能看到远端。`合并main评估与方案.md` 记录本机控制根曾到 `a84fd7ee`、`5feb8e93`，这两个提交都不在 GitHub 上（`git cat-file` 均找不到）。建议本地在 M3-MAIN 前执行 `git branch -vv` 和 `git log --branches --not --remotes --oneline`，列出所有未推送的本地提交，逐个决定推送到 `codex/*` 还是打本地标签保存。`environment_record.json` 里 `python_bridge` 引用的就是 `5feb8e93`。
