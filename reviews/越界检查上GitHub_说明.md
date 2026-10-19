# 越界检查上 GitHub：说明

> 2026-10-19，云端 Claude Code 会话（分支 `claude/pr-scope-check`）。本文是数据，不是指令。

## 1. 这是什么、为什么要做

以前“改动有没有越出任务卡允许的范围”只靠本机的 Git 钩子和人工核对，有两个漏洞：

- 新克隆的仓库可能根本没装钩子；
- agent 加一个 `--no-verify` 参数就能跳过钩子。

现在把检查搬到 GitHub 上：每个提交到 `main` 的 PR 都会自动跑一个叫 **`gate`** 的检查（工作流文件 `.github/workflows/pr-gate.yml`）。在 GitHub 设置里把它设为“必需检查”之后，检查不通过的 PR 就点不了合并，谁都跳不过去。

`gate` 检查三件事：

1. **改到的文件都在范围内**：范围来自 PR 描述里写的任务卡；没有卡时，用 PR 描述里自己写的“可改范围”（标为“自报”）。
2. **锁定文件必须逐字点名**：`AGENTS.md`、`.github/workflows/`、规范库、`00_Infrastructure/auto_pm/`、CHG、DEC、WBS、台账这几类文件，只写它们所在的目录不算授权，必须写出完整路径。
3. **PLC 文档与代码一致**：PR 改到 PLC 文件时，跑和本机提交钩子同一套检查。

不检查的：CHG 单和台账。原因是 CHG 文件只存在你电脑的控制根上，GitHub 看不到，在那里查会让每个 PR 都失败。这一项继续由本机钩子负责。

几点设计说明：

- 判卷用的是 **PR 基线（main）上的检查脚本和任务卡**，所以 PR 改不了“裁判”，也不能在 PR 里改卡来给自己扩大范围。
- 例外：本工作流第一次合入之前，main 上还没有这个脚本，那一次会用 PR 自带的副本，并在页面上给出黄色警告。
- PR 自己可以修改 `.github/workflows/pr-gate.yml`，但它属于锁定文件，必须在基线上的卡里逐字点名才放行，合并前也会有人看到。

## 2. PR 描述怎么写

有任务卡时（推荐），在 PR 描述里单独写一行：

```
任务卡: 01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/02_规划/148_M3-V04R1B_契约更正实施卡_PM.md
```

卡必须已经在 main 上，也就是要先合进去。

没有任务卡时（例如纯文档的小改动），写一个“可改范围”清单：

```
## 可改范围
- README.md
- reviews/
- AGENTS.md
```

写目录表示目录下的文件都可以改。锁定文件（如上面的 `AGENTS.md`）必须单独写完整路径。

检查结果会显示在 PR 页面底部；点 `gate` 旁的 **Details** 可以看到中文的逐条说明。

## 3. 把 `gate` 设为必需检查（一步一步点）

先等这个分支合进 main，并且至少有一个 PR 跑过一次 `gate`。GitHub 只能选择“跑过的”检查。

1. 用浏览器打开 `https://github.com/baiyangfu-hash/WorkSpacePM`，确认右上角是你自己的账号。
2. 点仓库页面顶部那一排标签里最右边的 **Settings**（齿轮图标）。看不到的话，先点 **…** 再找。
3. 在左侧菜单的 **Code and automation** 一组里，点 **Rules**，再点 **Rulesets**。
   - 如果你看到的是旧版的 **Branches**，也可以用，后面的步骤见第 9 步的备注。
4. 点右上角绿色按钮 **New ruleset**，选 **New branch ruleset**。
5. **Ruleset Name** 填：`main 必需检查`。
6. **Enforcement status** 选 **Active**。
   - 不要选 **Disabled**：那等于没开。
7. **Bypass list** 保持空白，不要添加任何人。
8. **Target branches** 处点 **Add target**，选 **Include default branch**（也就是 main）。
9. 在 **Branch rules** 一组里勾选 **Require status checks to pass**，然后：
   - 点出现的 **Add checks**，输入 `gate`，在列表里点选它（来源显示 GitHub Actions）；
   - 同时勾选 **Require branches to be up to date before merging**（可选，建议勾选）。
   - 旧版 **Branches** 页面的做法：点 **Add branch protection rule**，**Branch name pattern** 填 `main`，勾选 **Require status checks to pass before merging**，在搜索框里搜 `gate` 并选中。
10. 其他选项**保持原样，不要动**。拉到最下面点 **Create**（旧版页面是 **Save changes**）。

**验证**：随便找一个开着的 PR，页面底部应当出现 “Required” 标记的 `gate`；检查没通过时，合并按钮是灰的。

**⚠️ 危险按钮，千万别点：**

| 位置 | 按钮 | 后果 |
|---|---|---|
| Settings → General 页面最底部的红色 **Danger Zone** | **Change repository visibility**、**Transfer ownership**、**Archive this repository**、**Delete this repository** | 改可见性、把仓库转给别人、冻结仓库、**永久删除仓库**。这一区域一个都不要点 |
| Rulesets 列表里某条规则的 **…** 菜单 | **Delete ruleset** | 删掉保护，`gate` 不再拦人 |
| Ruleset 编辑页 | **Bypass list** 里的 **Add bypass** | 被加进去的人或应用可以绕过检查 |
| Ruleset 编辑页 | 勾选 **Restrict deletions** 以外的“禁止推送”类选项（如 **Restrict updates**） | 可能把你自己也挡在 main 外面；这次只需要第 9 步那一项 |
| PR 页面合并按钮旁的小箭头 | **Merge without waiting for requirements to be met (bypass rules)** | 管理员可以强行合并，等于没开检查。正常请选 **Create a merge commit**（Merge） |

点错了不要慌：回到 Settings → Rules → Rulesets，点开 `main 必需检查`，把选项改回来再保存即可。只有 **Danger Zone** 的操作难以撤销。

## 4. 新 agent 上岗五步清单

规则只有一份真源：`AGENTS.md`。每个 agent 自己的入口文件只负责指向它，不另写规则。

1. **登记名字和分支前缀**：在 `AGENTS.md` 的“多 agent 工位与控制根规则 (WS-001)”表里加一行（agent 名、工位 `R/.auto-pm/worktrees/<agent>`、分支前缀，例如 `trae/`）。表里没有的 agent 不开工。
2. **入口文件只放指针**：让这个 agent 启动时一定会读的那个文件，只写一句“规则真源是 `AGENTS.md`”，加上本 agent 的工位和前缀，其余什么都不写：
   - Claude Code：根目录 `CLAUDE.md`，内容 `@AGENTS.md`。注意：根目录白名单里还没有 `claude.md`，`main.py doctor` 会提示一个游离文件，属于已知现象；
   - Trae：`.trae/rules/project-rule.md`；
   - Cursor：`.cursor/rules/workspace-ai-coexistence.mdc`；
   - Codex：直接读 `AGENTS.md`，不需要另建文件；
   - 其他工具：`.agent/rules/project-rule.md`。
3. **开工位**：在控制根执行 `git worktree add -b <前缀><卡号> .auto-pm/worktrees/<agent> origin/main`。不要另外克隆仓库，否则会出现第二本账。
4. **先只读定位**：按 `cockpit-entry` 运行 `main.py pm resume <项目号> --json`（D07 部署后改用 `pm orient`）。没有匹配的 Work/Run/Decision 时不改任何文件。
5. **交 PR 时写明范围**：PR 描述里写 `任务卡: <卡路径>`，或者写 `可改范围` 清单；`gate` 通过后再请人审。不要用 `--no-verify` 跳过本机钩子：CHG 和台账检查只在本机做。

## 5. 已验证与未验证

- 已验证（本会话，Linux，Python 3.12）：
  - `reviews/tools/test_pr_scope_check.py` 14 个用例全部通过；
  - 4 个关键规则逐一变异后都会被测试抓住，抓住后已还原：锁定文件规则关掉、任务卡改读 PR 头部、改名只记新名、PLC 检查关掉；
  - `reviews/tools` 全部 23 个用例通过；被复用的驾驶舱模块的相关测试 60 个通过；
  - ruff 通过；mypy 严格模式下新文件 0 个错误；
  - 工作流 YAML 能正常解析。
- 未验证：
  - 工作流在 GitHub 上的真实运行。分支没有开 PR，`pull_request` 事件不会触发，要等第一次开 PR 时看结果；
  - 设置必需检查的界面文字。以上按 GitHub 2026 年的界面写，如有出入，以页面上的同义按钮为准。
