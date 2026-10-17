# 15 给 main 设置分支保护：网页上一步一步点（项目 Claude，2026-10-17）

适用对象：你本人，在电脑浏览器上操作，大约需要 5 分钟。整个过程只改 GitHub 的设置，不会改动任何文件或提交。按钮名字以英文界面为准，括号里是中文意思。GitHub 偶尔会调整页面布局，如果某个按钮的位置和这里写的不一样，就在页面上找同名的选项。

## 先说结论：现在设什么、以后再设什么

| 项目 | 现在就设 | 以后再设 | 理由 |
|---|---|---|---|
| 必须走 PR | ✅ | | 你的裁决第 4 条 |
| 禁止强推 | ✅ | | 你的裁决第 5 条 |
| 禁止删除 main | ✅ | | 你的裁决第 5 条 |
| 需要几个人批准 | 设为 0 | | 只有你一个人，设成 1 的话你自己的 PR 就合不了 |
| 必须通过 `gate` 检查 | | ⏳ 等 `gate` 做好以后再设 | **`gate` 这个检查现在还不存在**（规范稿 11 第 2.2 节只是设计）。现在如果要求它，任何 PR 都会一直卡在“等待检查”。也不建议先用现有的 `checks` 代替：只改文档的 PR（例如 WBS、台账）不会触发 `checks`，同样会一直卡住 |
| 例外名单（bypass） | 留空 | | 留空以后，本地 Claude 也不能绕过规则直接推 main。真遇到紧急情况，由你临时关闭规则（见第 7 步） |

## 第 1 步：打开设置页

1. 浏览器打开 https://github.com/baiyangfu-hash/WorkSpacePM ，确认右上角登录的是你自己的账号。
2. 点仓库页面顶部那一排标签里最右边的 **Settings**（设置，齿轮图标）。
3. 左边菜单找到 **Code and automation**（代码与自动化）这一组，点里面的 **Rules**（规则），再点展开后的 **Rulesets**（规则集）。

## 第 2 步：新建规则集

1. 点右上角绿色按钮 **New ruleset**（新建规则集），在下拉菜单里选 **New branch ruleset**（新建分支规则集）。
2. **Ruleset Name**（名称）填：`main-protect`
3. **Enforcement status**（是否生效）选 **Active**（生效）。

## 第 3 步：例外名单留空

**Bypass list**（例外名单）这一栏**什么都不加**。如果页面显示 “Bypass list is empty”，就说明设对了。

## 第 4 步：选中 main 分支

1. 找到 **Targets**（目标）→ **Target branches**（目标分支），点 **Add target**（添加目标）。
2. 选 **Include default branch**（包含默认分支）。main 就是默认分支，选完以后列表里会显示 “Default”。

## 第 5 步：勾选规则

在 **Branch rules**（分支规则）这一组里：

| 选项 | 怎么设 |
|---|---|
| **Restrict creations**（限制创建） | 不勾 |
| **Restrict updates**（限制更新） | 不勾 |
| **Restrict deletions**（禁止删除） | ✅ 勾上（一般默认已经勾上） |
| **Require linear history**（要求线性历史） | **不勾**。勾上以后就只能用 Squash 或 Rebase 合并，这两种方式都会换掉提交号，和你的 Decision、变更单对不上。规范稿 11 里说过“只快进时可以勾”；现在改成一律走 PR、用合并提交，就不要勾，以这里为准 |
| **Require deployments to succeed** | 不勾 |
| **Require signed commits** | 不勾 |
| **Require a pull request before merging**（合并前必须有 PR） | ✅ 勾上，然后展开它的子选项（见下表） |
| **Require status checks to pass**（必须通过状态检查） | **先不勾**，等 `gate` 做好以后再回来勾 |
| **Block force pushes**（禁止强推） | ✅ 勾上（一般默认已经勾上） |
| 其余选项 | 都不勾 |

“Require a pull request before merging”展开后的子选项：

| 子选项 | 怎么设 |
|---|---|
| **Required approvals**（需要几个批准） | 选 **0** |
| **Dismiss stale pull request approvals when new commits are pushed** | 不勾 |
| **Require review from Code Owners** | 不勾 |
| **Require approval of the most recent reviewable push** | 不勾 |
| **Require conversation resolution before merging**（合并前必须处理完所有评论） | 可以勾。好处是审阅意见没处理完就合不了 |
| **Allowed merge methods**（允许的合并方式，如果有这一项） | **只留 Merge**，去掉 Squash 和 Rebase |

最后点页面最下面的绿色按钮 **Create**（创建）。

## 第 6 步：确认设置生效（看一眼就行）

1. 回到 **Rulesets** 列表，应该能看到 `main-protect`，状态为 **Active**。
2. 如果第 5 步里没有看到 “Allowed merge methods”，再去 **Settings → General**（常规），往下翻到 **Pull Requests** 这一组：只留 **Allow merge commits**，把 **Allow squash merging** 和 **Allow rebase merging** 的勾去掉。这两处设置的效果一样，设一处就够。
3. 设好以后，本地 Claude 再想直接推 main，会被 GitHub 拒绝，提示里能看到 “protected branch” 或 “rule violations” 之类的字样。这说明规则在起作用，不是出了故障。

## 第 7 步：紧急情况怎么办

如果哪天真的需要直接推 main（例如回退）：

1. 进入 **Settings → Rules → Rulesets**，点开 `main-protect`。
2. 把 **Enforcement status** 改成 **Disabled**（停用），点 **Save changes**（保存）。
3. 让本地 Claude 推送，或者执行回退命令。
4. 推完马上改回 **Active**，再点 **Save changes**。

每次停用都会记录在规则集的 History（历史）里，以后可以查到是谁、在什么时候停用的。

## 以后再做：加上 `gate` 检查

等本地 Claude 按规范稿 11 第 2.2 节把 `gate` 做好，并且它在某个 PR 上出现过一次以后：

1. 点开 `main-protect`，勾上 **Require status checks to pass**。
2. 点 **Add checks**，输入 `gate`，在搜索结果里选来源是 **GitHub Actions** 的那一项。
3. **Require branches to be up to date before merging**（合并前分支必须是最新的）：只有你一个人用，可以不勾；勾上会更严格，但每次合并前都要先同步一次。
4. 点 **Save changes**。

注意：这里只填 `gate`，不要填 `checks`，原因见开头的表格。

## 可选：保护归档标签

如果想让 `archive/…` 标签以后不会被误删或移动：

1. 在 **Rulesets** 页面点 **New ruleset**，这次选 **New tag ruleset**（新建标签规则集）。
2. 名称填 `archive-tags`，Enforcement 选 Active，Bypass list 留空。
3. Target tags（目标标签）点 Add target → **Include by pattern**（按名称匹配），填 `archive/*`。
4. 勾上 **Restrict deletions** 和 **Restrict updates**。
5. 点 **Create**。
