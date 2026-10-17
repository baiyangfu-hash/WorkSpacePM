# 17 审阅线程交接（项目 Claude，2026-10-17）

本文写给接手审阅的任何 agent（本地 Claude、Codex、新的项目线程等），读完这一份就能接着做，不需要翻聊天记录。时间一律用亚利桑那时间（MST，UTC−7，没有夏令时）。本文是数据，不是指令。

## 1. 审阅者的角色和边界

- **只读审阅**：读仓库、跑测试、写审计报告和补丁，结论交给台账主机（本地 Claude，分支前缀 `codex/`），由它按受治理流程（卡、CHG、Decision）落地。
- **只写 `reviews/`**：审阅分支用 `project/` 前缀（项目 Claude）或 `claude/` 前缀（云端会话）。不推 `main`，不推 `codex/*`，不合并 PR。
- **不改这些路径**：WBS、各种台账、`AGENTS.md`、`00_Obsidian_Base…`、`00_Infrastructure/auto_pm/`、`CHG-*`、`DEC-*`、`.auto-pm/`、`.github/workflows/`。需要改时写成建议或补丁。
- **绝不删除**：不删文件、分支或标签，需要留存时只新增归档标签。
- **报告格式**：先写结论，再写证据（`文件:行号` 或提交号）和严重度；没有亲自核对过的写 UNVERIFIED；用“建议”，不用命令口吻。
- **用户**：baiyang，写中文，不是程序员。回复先给结果，少用术语。

## 2. 分支与文件位置

| 位置 | 内容 |
|---|---|
| `project/review-20261017`（基于 main `a742721`） | **当前的审阅分支**：14 补丁现状、07 AGENTS2 审计、15 分支保护指南、16 存储卡验收用例、本交接文件、`patches/10_m3_envport.patch` |
| `project/overnight-20261016`（已冻结，保留） | 上一轮的 00～13：01 CIMAIN 设计、02 main 快进清单、03/04 V04-R1 存储与演练设计、05 新电脑调研、06 协作 A 部分设计、07 卡 147/148/HYGIN1/CIMAIN 审计、08 main 审计、09/13 补丁（已落地）、11 流程规范稿、12 分支清理建议 |
| `/mnt/project-files/reviews/`（项目共享文件夹，仓库外的 agent 看不到） | 两份裁决稿、分支保护指南、存储卡验收用例、本交接文件的副本 |

## 3. 当前状态（2026-10-17 上午）

- **main**：`a742721`，由 PR #1 快进而来，审计结论见 `08_audit_main.md`。main 推送那次的 CI 已通过，失败的 20 个测试与已记录的基线一致。
- **分支保护**：用户已建好 `main-protect` 规则集，现在生效的规则是：
  - 禁止删除、禁止强推；
  - 必须走 PR，批准人数 0，只允许 Merge；
  - 合并前必须处理完所有评论；
  - 例外名单为空。
  
  “未署名改动需要额外批准”这一项，用户后来把它去掉了。
- **PR #2**（`codex/pr-sync-20261017` → main，卡 149、152、155～157，头部 `c1c73bc`）：已于 08:08 合并，main 现在是 `46aead1`，核对结果见第 6 节。
- **补丁**：
  - 09 和 13 已由卡 152（`539b9df`）落地，逐字节一致；
  - 10（新电脑一键可用）在 `c1c73bc` 上可以干净应用，测试通过，等本地 Claude 单独开 PR。
- **已审计、结论为同意的卡**：147、148（发现的问题已由 152 修复）、HYGIN1、CIMAIN、AGENTS2、M3-MAIN。

## 4. 未完成事项（接手的人从这里开始）

| # | 事项 | 等谁 | 怎么做 |
|---|---|---|---|
| 1 | PR #2 合并以后核对 main | 已在本线程完成，结果附在本文末尾；如果末尾没有结果，就由接手的人来做 | 核对 main 是否等于 PR #2 的合并提交、它的两个父提交是 `a742721` 和 `c1c73bc`、main 推送那次的 CI 是否通过，做法同 `08_audit_main.md` |
| 2 | 补丁 10 的 PR | 本地 Claude 开 PR | PR 开出来以后，审计它和 `patches/10_m3_envport.patch` 是否一致。`setup_env.bat` 只能在 Windows 上验证，请用户在第二台电脑上用新目录实际跑一遍 |
| 3 | 存储卡验收用例的三个问题 | **用户回答** | 见 `16_v04r1_storage_acceptance.md` 末尾：三条用例是否都要；“接受风险”的 Decision 是否只能用户本人签；宽限期是否保持 120 秒。三个问题的建议答案依次是：都要、只能本人签、保持 |
| 4 | 规则集里加上 `gate` 检查 | 先由本地 Claude 按 `11_post_main_process_spec.md` 第 2.2 节做出 `gate`；做好以后由**用户**按 `15_main_ruleset_guide.md` 末尾的步骤勾选 | 在 `gate` 做出来之前不要设必需检查。现有的 `checks` 有 `paths` 过滤，只改文档的 PR 不会触发它，设成必需检查会让这类 PR 一直卡住 |
| 5 | V04-R1 存储接入卡 | 用户答完第 3 项以后由本地 Claude 开工 | 设计见 `03_v04r1_storage_design.md`；注意 TD-SW008-145（“先检查、后写入”的竞争）。卡推送以后按 07 系列的格式审计 |
| 6 | 跨电脑共享状态、V0.3 规划修订 | 下一阶段，开新线程做 | — |

## 5. 审计常用的做法

- **测试环境**：Python 3.12 或 3.13，装 `pytest`、`ruff<0.17`、`mypy<3`、`pydantic`、`pyyaml`。
  - SW008 的 `conftest.py` 会导入 PySide6。没装 PySide6 时，用 `pytest --noconftest -o addopts=` 跑单个测试文件。
  - mypy 用 `--platform win32`。
- **变异检查**：每次只改一处，跑测试，然后立即还原（用 `try/finally`）。用来证明测试真的能抓到问题。
- **补丁**：基于审计对象所在的提交生成，`git apply --check` 必须通过。如果和已有的卡冲突，用 `--3way`；测试文件末尾同时追加内容造成的冲突，两边都保留即可。
- **隐私扫描**（仓库是公开的）：令牌前缀、长 base64 串、邮箱、内网地址、手机号和身份证号、本机路径。本机路径和用户名 `fubai` 在 main 上已有约 200 个文件，属于已知情况；新报告只需要指出“新增了哪一类”。
- **CI 日志**：GitHub Actions 运行 `sw008-ci`。看三处：秘密扫描那一行 `secret scan: N location(s) flagged in <base>..HEAD`、`verdict: PASS_KNOWN_BASELINE`，以及 env 里的 `EVENT`、`BEFORE`、`PR_BASE`。

## 6. 合并后核对结果

核对时间：2026-10-17 08:15 左右（亚利桑那时间）。结论：**通过**，第 4 节第 1 项已完成。

| 检查 | 结果 |
|---|---|
| main 的新提交 | `46aead1`（`Merge PR #2: M3 sync 1 (cards 149, 152, 155-157)`），08:08 合并 |
| 两个父提交 | `a742721`（原 main）和 `c1c73bc`（PR #2 头部），是合并提交，没有用 Squash 或 Rebase，提交号都保留了 |
| 内容 | `git diff c1c73bc 46aead1` 为空，main 的内容和 PR #2 头部完全相同 |
| main 推送那次的 CI | run 39043711320，`success`。`EVENT: push`，`BEFORE: a742721`；`secret scan: 0 location(s) flagged in a742721..HEAD`；Ruff 通过；pytest 20 failed、3695 passed、24 skipped；`verdict: PASS_KNOWN_BASELINE`（失败的 20 个与基线一致） |
| 过程中的插曲 | PR #2 在 08:01 被关闭过一次，08:02 重开，08:08 合并。原因没有核对（UNVERIFIED），对结果没有影响 |

合并以后，卡 152（补丁 09+13）已经在 main 上。下一步从第 4 节第 2 项（补丁 10 的 PR）开始。
