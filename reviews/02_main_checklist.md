# 02 M3-MAIN 前提核对与可执行清单（项目 Claude，2026-10-17）

基于远端只读核对：`origin/main` = `e83c117d6fba5a6beaaf6318a79eb4dc7f652979`；`codex/m2-gov-wbs9-attest` 尖端 `23e841b258910172e23229664189ef6a032c8ad4`；`codex/c09-recovery-governance` = `6f759fce9cfe7d7eefb3bfc1710596047b9cf6b3`（与 main 的分叉点 `d81903a2`，领先 main 59 个提交）。本文是建议，不是指令。

## 结论

**同意按“补齐 c09 记录 → CIMAIN → CI 通过的 X → 草稿 PR → 快进推送”执行。** 要点：

1. **c09 上只有它自己有的文件是 64 个，不是 57 个**（51 个 Decision + 13 个文档）。此前评估把 7 个 SW-2026-009 变更单按文件名算成了“m2 已有”，其实它们是同号不同项目的另一份记录（见第 3 节 B）。严重度：中。
2. **X 不能早于 HYG-MIN 入库提交和 CIMAIN 提交。** `c38c469b` 不符合。严重度：高。
3. **此前评估第 3 节方案 A 第 4 步写的“删除分支”作废**，与用户“绝不删除”的裁决冲突。改为只打归档标签、分支保留。严重度：中。
4. **不要用 GitHub 的 “Rebase and merge” 或 “Squash”**：两者都会改写提交号，使已经绑定提交号的 Decision 和 CHG 追溯失效。只用本地 `git push X:refs/heads/main` 做快进。严重度：高。

## 1. X 的选取条件（全部满足）

| # | 条件 | 核对命令 |
|---|---|---|
| 1 | X 是 `e83c117d` 的后代（纯快进） | `git merge-base --is-ancestor e83c117d6fba X && echo FF_OK` |
| 2 | X 包含 HYG-MIN 入库提交（含第 3 节的 64 个文件）和 CIMAIN 提交 | `git merge-base --is-ancestor <入库提交> X`、`git merge-base --is-ancestor <CIMAIN提交> X` |
| 3 | `sw008-ci` 在 X 本身上是 success（不是 X 的父提交） | GitHub Actions 中该运行的 `head_sha == X` |
| 4 | 范围内没有新增的密钥格式行 | 在 X 上执行 `python -I <PROJ>/tests/tools/sw008_ci/secret_scan.py e83c117d6fba`，退出码 0 |
| 5 | 范围内没有**新增或修改的**超过 5MB 文件 | 见下方命令。注意：仓库里本来就有 8 个超过 5MB 的历史文件（SW-2026-004 的 exe、dll 等），它们不在本次范围内，只检查全树会误报 |
| 6 | X 上没有标签，且本机没有未推送的提交 | `git tag --points-at X` 为空；`git log origin/codex/m2-gov-wbs9-attest..codex/m2-gov-wbs9-attest` 为空 |

条件 5 的命令：

```bash
git diff --name-only --diff-filter=AM e83c117d6fba X > /tmp/chg.txt
git ls-tree -r -l X | awk '$4>5242880' | cut -f2 | grep -xFf /tmp/chg.txt   # 应无输出
```

云端在 `23e841b` 上的实测：534 个文件变化，没有新增或修改的超过 5MB 的文件。

## 2. 命令顺序

```bash
# 0. 准备
git fetch origin
git status --porcelain                         # 必须为空
X=<满足第 1 节的提交号（40 位）>

# 1. 指针分支 + 草稿 PR（只新增，不删除）
git push origin X:refs/heads/codex/main-ff-candidate
#    在 GitHub 上开草稿 PR：base=main，head=codex/main-ff-candidate
#    等待 pull_request 触发的 sw008-ci 跑完且为 success（同时验证 CIMAIN 的 PR 路径）

# 2. 快进推送（不带 --force；不是快进时服务器会拒绝，这本身就是保险）
git push origin X:refs/heads/main

# 3. 核验
git ls-remote origin refs/heads/main           # 输出必须等于 X
#    GitHub 上草稿 PR 应自动显示为 Merged
#    main 上应出现一次 push 触发的 sw008-ci，before = e83c117d，结果 success

# 4. 归档（只新增标签，不删除分支）
git push origin refs/remotes/origin/codex/c09-recovery-governance:refs/tags/archive/c09-recovery-governance-20261017
```

说明：指针分支用 `codex/` 前缀，是本地 Claude 的地盘；它固定在 X，本地继续往 m2 提交也不会让 PR 内容漂移。

## 3. 回退

前提：main 当时**没有**开启分支保护（现在没有；分支保护放到确认不再回退之后）。

```bash
git push --force-with-lease=refs/heads/main:X origin e83c117d6fba5a6beaaf6318a79eb4dc7f652979:refs/heads/main
```

`--force-with-lease=refs/heads/main:X` 只在远端 main 仍然等于 X 时才回退。如果期间有人往 main 推了别的提交，回退会被拒绝，不会把那个提交丢掉。回退后，CIMAIN 的扫描基线 `before` = X（`fetch-depth: 0` 下仍可取到），`X..e83c117d` 为空，CI 不会误报。

## 4. c09 的 64 个“仅 c09”文件逐个处置

核对方法：`git diff --name-only --diff-filter=AM d81903a2 6f759fce` 共 107 个文件，与 `23e841b` 按路径和内容比对：35 个完全相同，8 个同路径不同内容，64 个只在 c09 上。

### A. 51 个 Decision（`.auto-pm/decisions/*.json`）：建议全部入库，字节保持与 c09 一致

**被 m2 引用的 15 个**（m2 尖端 `git grep` 结果，不含 decisions 目录本身）：

| Decision | 引用位置（相对 `02_在研项目/` 或仓库根） |
|---|---|
| DEC-20260929-BL02CODE | SW-2026-008 CHG-SCPT-2026-356、-357；SYS-2026-001 `39_…WBS_PM.md` |
| DEC-20260923-4E4C5345 | CHG-SAFE-2026-011；CHG-SCPT-2026-309 |
| DEC-20260924-6BAAB080 | CHG-SCPT-2026-311、-327 |
| DEC-20260921-D2DB1A6D | CHG-SCPT-2026-304 |
| DEC-20260923-Q03R0002 | CHG-SCPT-2026-305 |
| DEC-20260924-6404A011 | CHG-SAFE-2026-012 |
| DEC-20260924-94F97EA2 | CHG-SAFE-2026-012 |
| DEC-20260927-DBB26950 | CHG-SCPT-2026-328 |
| DEC-20260928-331AD001 | CHG-SCPT-2026-331 |
| DEC-20260928-331C0001 | CHG-SCPT-2026-331 |
| DEC-20260928-336INT01 | CHG-SCPT-2026-336 |
| DEC-20260928-336REL01 | CHG-SCPT-2026-336 |
| DEC-20260928-M2IC0102 | CHG-SCPT-2026-338 |
| DEC-20260929-U04BR1R1 | `tests/cli/test_continuity.py:1240`（只是字符串，CI 不读这个文件） |
| DEC-20260930-BL02RSET | SYS-2026-001 `39_…WBS_PM.md` |

**未被 m2 引用的 36 个**（属于 H03、C09、Q03、H11B、A03、A04、M2U02 等收口过程，同样是治理证据，建议一并入库）：
DEC-20260920-H03SAFE0 DEC-20260921-62760183 DEC-20260921-H03R0001 DEC-20260921-H03R0002 DEC-20260921-H03R0003 DEC-20260922-C09R0001 DEC-20260923-57C74C50 DEC-20260923-5D0E95FC DEC-20260923-C09ART01 DEC-20260923-C09DONE1 DEC-20260923-C09LEG01 DEC-20260923-C09R3C04 DEC-20260923-C09R3CR1 DEC-20260923-C09R3CR2 DEC-20260923-C09R3CR3 DEC-20260923-C09R3CR4 DEC-20260923-C09REC01 DEC-20260923-C09REC02 DEC-20260923-Q03LEG01 DEC-20260927-3A8E013B DEC-20260927-7B5C013A DEC-20260927-8B177C43 DEC-20260928-13FA4027 DEC-20260928-3320A1F1 DEC-20260928-334A0001 DEC-20260928-335A0001 DEC-20260928-406D7018 DEC-20260928-4B1DCC33 DEC-20260928-9B2734D4 DEC-20260928-A03A0002 DEC-20260928-A03B0002 DEC-20260928-A04B0001 DEC-20260928-FEECDFD7 DEC-20260928-M2U02001 DEC-20260929-0ADBC79D DEC-20260929-H11BSETL

**入库前必须先核对本机磁盘版本与 c09 版本是否字节一致**（UNVERIFIED：云端看不到本机磁盘）。Decision 的 Git 绑定校验比的是字节（`continuity_store.py` 中的 `decision_git_binding_issues` 和 `_control_root_decision_binding`），两边不一致时不能随便挑一份：

```bash
C=origin/codex/c09-recovery-governance
git diff --name-only --diff-filter=A d81903a2 $C -- .auto-pm/decisions/ | while read f; do
  [ -f "$f" ] || { echo "MISSING-LOCAL $f"; continue; }
  [ "$(git hash-object "$f")" = "$(git rev-parse "$C:$f")" ] || echo "DIFFERS $f"
done
```

- 无输出：直接用本机文件入库（与 c09 字节相同）。
- `MISSING-LOCAL`：从 c09 取回，`git checkout $C -- <path>`。
- `DIFFERS`：停下，逐个列出差异再决定，不覆盖本机文件。

另外：m2 上已跟踪 115 个 Decision，c09 上 162 个，本机待入库 366 个。51 个 c09 独有的应当是 366 的子集；建议入库清单里显式标出这 51 个，便于审计。

### B. 7 个 SW-2026-009 变更单：建议入库，并作为编号撞号的证据记录

`02_在研项目/SW-2026-009_英语学习助手/04_监控/01_变更管理/01_变更单/` 下的 CHG-SAFE-2026-001、-002，CHG-SCPT-2026-005～009。m2 上有同名文件，但属于**别的项目**：例如 c09 的 CHG-SCPT-2026-005 写的是“项目编号 SW-2026-009，2026-09-21，PM Facade”，m2 上 `SYS-2026-001_…/CHG-SCPT-2026-005.md` 写的是“SYS-2026-001，2026-09-04，Codex”。路径不同，入库不会冲突；但这说明变更单编号按“类型+年+序号”在全局并不唯一，是 06（M3-COLLAB A，编号新格式）的直接证据。

### C. 6 个 SW-2026-008 和 SYS 文档：建议入库

- `02_规划/014_M2前置知识与工作区治理收敛实施卡_PM.md`
- `02_规划/015_实施卡合同与自动化工作流实施卡_PM.md`
- `02_规划/018_U04_真实事件进度与失败时间线实施卡_PM.md`
- `02_规划/022_GitHook候选快照与控制根治理真源分离实施卡_PM.md`
- `04_监控/02_整改项/控制面事故登记台账.md`
- `SYS-2026-001_WorkspaceGovernance/01_项目文档/archive/PMF-20260927/V2.6.3_ARCHIVE_POINTER.md`

都是新文件，与 m2 不冲突。

### D. 8 个同路径不同内容的文件：保留 m2 版本，不从 c09 取

`active_release.json`、`deployment_manifest.json`、`previous_release.json`、017 实施卡、两本 `01_版本变更台账.md`、`活动技术债台账.md`、`39_…WBS_PM.md`。m2 是后来的演进版本；尤其三个 release 指针文件一旦取 c09 版本，会让启动器指向旧发布。

### 取回命令（只取路径，不合并 c09 历史）

```bash
C=origin/codex/c09-recovery-governance
git diff --name-only --diff-filter=A d81903a2 $C > /tmp/c09_added.txt
# 只保留 HEAD 上不存在的路径（即上面 A+B+C 的 64 个）
while read f; do git cat-file -e "HEAD:$f" 2>/dev/null || echo "$f"; done < /tmp/c09_added.txt > /tmp/c09_only.txt
wc -l /tmp/c09_only.txt                        # 期望 64
git checkout $C --pathspec-from-file=/tmp/c09_only.txt   # Decision 若已按 A 核对为本机版本，可跳过它们
```

注意：`--diff-filter=A` 只取新增；c09 上被修改过的已有文件都属于 D 类，不取。核对数时如果不是 64，先停下比较差异。

## 5. 其他分支（都不删除）

| 分支 | 状态 | 建议 |
|---|---|---|
| `codex/g10-r1-lifecycle` | 已完全包含在 m2 | 保留；可以打归档标签 |
| `claude/cloud-docs-refresh` | 1 个候选提交 `66424dc`，未治理，与 m2 的 README 有 1 处冲突 | 保留，不混进这次快进，以后单独评审 |
| `codex/c09-recovery-governance` | 文件经第 4 节取回后，内容已全部在主线上 | 打标签 `archive/c09-recovery-governance-20261017`，分支保留 |
| `project/overnight-20261016`、`claude/*` | 审阅数据通道 | 不合进 main |
