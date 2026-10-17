# 11 main 之后的流程规范稿（项目 Claude，2026-10-17）

本文是规范草案，供本地 Claude 按受治理流程落账；不是指令。第 1、3 节在 `06_collab_A_design.md` 第 1、4 节的基础上写成可以直接采用的条文；第 2 节是新内容。

## 1. 外部 PR 的固定描述与合并后补登

### 1.1 适用范围

凡是不由台账主机（本地 Claude，`codex/*`）直接提交的改动，都走 PR，例如 `project/*`、`claude/*`，以及以后的协作者。台账主机自己的提交可以照旧直接推送，也可以走 PR。

### 1.2 PR 描述模板（放仓库根目录 `.github/pull_request_template.md`）

```markdown
## 来源
- 写入者：<project | cloud | local | 人名>
- 分支：<prefix>/<name>
- 基点：<base 提交，40 位>

## 内容
<一段话：读者会看到什么变化>

## 治理登记建议（合并后由台账主机补登）
- 档次：<docs | product | core>
- 变更单：CHG-PENDING-<短主题>
- 涉及路径：<逐条列出>
- 需要的 Decision：<无 | 理由>
- 关联任务：<WBS 任务号，如 M3-ENVPORT>

## 自检
- [ ] 只改了本分支前缀允许的路径
- [ ] 本地检查：<命令> → 退出码 <n>
- [ ] 没有本机路径、令牌、个人信息
```

### 1.3 合并后补登（台账主机执行，最少六步）

1. **核对**：PR 的 `sw008-gate` 为绿；文件集合等于“涉及路径”；没有越界。
2. **取号**：用现有入口为该项目取变更单号（第 3 节方案一），写变更单。
3. **授权**：创建 Work 和 Decision，`approved_files` = PR 的文件集合。
4. **合并**：用“Create a merge commit”或本地快进，不用 Squash，也不用 Rebase and merge，二者都会换掉提交号。
5. **绑定**：Decision 的 `git_head` 取合并后的提交；追加台账行；在 PR 上评论回填变更单号和 Decision 号。
6. **对账**：`main.py ledger reconcile <PID>`，退出码 0 才算闭环。

先合并、后补登不会让 Decision 指向一个不存在的提交：Decision 绑定的就是合并后的那个提交。

## 2. 分支保护（规则集）设置清单与“永远运行的汇总检查”

### 2.1 问题

`sw008-ci` 有 `paths` 过滤。如果把它设为 main 的必需检查，凡是不碰这些路径的 PR（只改 `reviews/`、WBS、规范库），检查永远不会出现，PR 会一直停在“等待必需检查”，无法合并。

### 2.2 方案：工作流不设 `paths`，改在 job 里判断；必需检查只设一个汇总 job

GitHub 的规则是：被 `if:` 跳过的 job，在必需检查里算通过。所以做法是：

```yaml
# .github/workflows/sw008-ci.yml（只列出与现在不同的部分）
on:
  push:
  pull_request:
    branches: [main]
  workflow_dispatch:

jobs:
  changes:
    runs-on: ubuntu-24.04
    outputs:
      sw008: ${{ steps.diff.outputs.sw008 }}
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0, persist-credentials: false }
      - id: diff
        env:
          EVENT: ${{ github.event_name }}
          REF: ${{ github.ref }}
          BEFORE: ${{ github.event.before }}
          PR_BASE: ${{ github.event.pull_request.base.sha }}
        run: |
          base=origin/main
          if [ "$EVENT" = pull_request ]; then base="$PR_BASE"
          elif [ "$EVENT" = push ] && [ "$REF" = refs/heads/main ]; then base="$BEFORE"; fi
          if [ "$EVENT" = workflow_dispatch ] || ! git cat-file -e "$base^{commit}" 2>/dev/null; then
            echo "sw008=true" >> "$GITHUB_OUTPUT"; exit 0      # 拿不准就跑全量
          fi
          if git diff --name-only "$base" HEAD | grep -qE \
             '^(01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/|00_Infrastructure/auto_pm/environment/|\.github/workflows/sw008-ci\.yml$)'; then
            echo "sw008=true" >> "$GITHUB_OUTPUT"
          else
            echo "sw008=false" >> "$GITHUB_OUTPUT"
          fi

  checks:
    needs: changes
    if: needs.changes.outputs.sw008 == 'true'
    # …原有 checks job 的全部步骤，原样保留…

  territory:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0, persist-credentials: false }
      - run: python -I .github/tools/territory_check.py   # 按分支前缀检查越界，见 06 第 5 节

  gate:
    # 唯一的必需检查。永远运行，汇总前面的结果。
    needs: [changes, checks, territory]
    if: always()
    runs-on: ubuntu-24.04
    steps:
      - env:
          RESULTS: ${{ join(needs.*.result, ' ') }}
        run: |
          echo "upstream results: $RESULTS"
          for r in $RESULTS; do
            case "$r" in success|skipped) ;; *) echo "::error::a required job ended as $r"; exit 1 ;; esac
          done
```

说明：

- `gate` 用 `if: always()`，所以 `checks` 被跳过或失败时它都会运行；只有上游都是 `success` 或 `skipped` 时它才通过。`changes` 自己失败（结果为 `failure`）时，`gate` 也会失败，不会因为 `checks` 被连带跳过而误判为通过。
- 秘密扫描的基线取法与 01 相同；`checks` 里的秘密扫描步骤沿用 01 的写法，不要改成 `changes` 的基线变量，否则普通分支会失去全段扫描。
- `territory_check.py` 和地盘表（`.github/territory.json`）是新文件，按 06 第 5 节写，属于核心档。
- 这样 `reviews/` 这类只改文档的推送，也会产生一个绿色的 `gate`，同时完成越界检查。

### 2.3 规则集设置清单（GitHub → Settings → Rules → Rulesets，由你点）

**时机**：M3-MAIN 完成，并且你确认不再需要回退（回退要强推 main）之后再开。

| 规则集 | 目标 | 规则 | 例外（bypass） |
|---|---|---|---|
| `main-protect` | 分支 `main` | 禁止删除；禁止强推；要求线性历史（与“只快进或合并提交”一致，如果以后要用合并提交，就不要勾这一项）；要求状态检查 `gate`，并勾选“要求分支为最新” | Repository admin（就是你）。本地 Claude 用你的身份做快进推送，需要这个例外；不想让它绕过时，把“要求 PR”打开并去掉例外 |
| `codex-keep` | 分支 `codex/*` | 禁止删除 | 无 |
| `archive-tags` | 标签 `archive/*` | 禁止删除；禁止更新（归档标签不可移动） | 无 |
| `review-branches`（可选） | 分支 `project/*`、`claude/*` | 禁止删除 | 无 |

注意：

- 必需检查只填 `gate`，**不要**填 `checks`。`checks` 被跳过时，GitHub 显示的名称和状态与 `gate` 不同；把它设为必需检查，又会回到 2.1 的问题。
- 规则集里检查名称的来源要选 “GitHub Actions”，避免别的应用伪造同名状态。
- 开启“禁止强推”之后，`02_main_checklist.md` 第 3 节的回退命令会失效。这是开启时机必须放在回退窗口之后的原因。

## 3. 变更单编号不撞号的规范草案

### 3.1 现状（证据见 02 第 4 节 B、06 第 1 节）

- 编号格式 `CHG-<DOMAIN>-<YYYY>-<NNN>`，按项目目录扫描取下一个号（`<SW008>/auto_pm/domain/change/change_service.py:157`，`<SW008>` 的含义同 05）。
- 两个写入者同时取号会拿到同一个号；不同项目本来就会出现相同编号（例如 `CHG-SCPT-2026-005` 同时属于 SYS-2026-001 和 SW-2026-009）。

### 3.2 规范条文（建议）

1. **唯一键**：变更单的唯一键是“项目编号 + 变更单编号”。任何按编号查找变更单的代码都必须限定在项目内。只凭编号做跨项目查找属于缺陷。
2. **唯一取号者**：只有台账主机取号。其他写入者在 PR 和建议文件里写 `CHG-PENDING-<短主题>`，`<短主题>` 只用小写字母、数字和连字符。`CHG-PENDING-` 前缀永远不会被取号器分配，现有的正则（`CHG-[A-Z]+-\d{4}-\d{3}`）也不会把它识别成正式编号。
3. **旧编号不改写**：所有已经存在的编号保持原样，包括已知的跨项目同号。
4. **取号原子性**：台账主机内部如果有多个并行会话，取号与创建变更单文件应当放在同一个文件锁内完成（例如用 `O_CREAT|O_EXCL` 创建变更单文件，失败就取下一个号）。这样单机上的并行会话也不会撞号。
5. **扩展预留（多人以后启用）**：需要多个取号者时，启用后缀格式 `CHG-<DOMAIN>-<YYYY>-<NNN>-<W4>`，`<W4>` 为写入者登记码（`[A-Z0-9]{4}`，登记在 AGENTS.md 的地盘表里）。启用前必须先把所有识别编号的正则改为接受可选后缀 `(?:-[A-Z0-9]{4})?`，并补测试证明新旧格式并存、互不混淆。已知位置：`contracts/intake.py:89,92`、`contracts/decision_package.py:19`、`application/core/pm_resume_service.py:176`、`application/core/ai_handoff_service.py:1022`。

### 3.3 落地顺序

先做条文 2、3（只改 AGENTS.md 和 PR 模板，不改代码）；再做条文 4（产品档小改，加一个并发取号测试）；条文 1 先写只读检查，列出所有跨项目同号的编号和按编号查找的位置，再决定改哪些；条文 5 等真正需要时再做。
