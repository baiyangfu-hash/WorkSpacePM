# Day 02：Git 救命三板斧与分支隔离

> 🎯 **今日目标**：掌握代码改崩时的终极自救方法（1 秒回退），掌握利用分支（Branch）进行安全隔离试验。
> ⏱️ **预计耗时**：45 分钟
> 🛠️ **前置准备**：完成 Day 01 学习。

---

## 💡 一、工控视角看“分支”与“回滚”

在工控现场调试时，如果你想试验一个不确定的算法，你通常会：
1. **新建一个测试副本**（不污染正在生产的稳定版本）；
2. 试车成功了，才把改动写进正式程序；
3. 试车失败导致设备报警停机了，**一键“恢复出厂设置”**回到原版。

在 Git 中：
* **`git checkout -b <分支名>`**：就是创建并切换到你的“专属试车程序”；
* **`git restore` / `git reset`**：就是你的**一键回滚“急停出厂还原按钮”**。

---

## 🚨 二、改崩时的“救命三板斧”

维护驾驶舱时，遇到任何代码改错、界面报错打不开的情况，**绝对不要慌**，按以下 3 种场景自救：

```
                    代码改崩时的自救决策树
                              │
               ┌──────────────┴──────────────┐
       还没有 git commit              已经 git commit 了
               │                             │
    想丢弃当前单个文件修改          想彻底回滚到上一个稳定快照
               │                             │
       git restore <file>           git reset --hard HEAD~1
```

### 第一斧：丢弃未提交的修改（恢复单个文件）
如果你改了某个 QML 或 Python 文件，改乱了想彻底不要了：
```powershell
# 放弃对某个文件的修改，瞬间还原到上次 commit 的状态
git restore auto_pm/ui/qml/views/ProjectListView.qml

# 放弃当前工作区所有文件的修改
git restore .
```

### 第二斧：强力回退到历史稳定快照（恢复出厂设置）
如果你已经 commit 提交了，但测试发现有严重 Bug，想彻底撤销这次提交：
```powershell
# 强行回退 1 次提交（所有代码回到上一个快照）
git reset --hard HEAD~1

# 或者回退到指定编号的快照
git reset --hard a1b2c3d
```

### 第三斧：临时抽屉（保存半成品去处理急件）
当你代码写了一半，突然要切换去排查另外一个紧急 Bug：
```powershell
# 1. 把当前写了一半的代码暂存到抽屉
git stash

# 2. 此时工作区变得干干净净，可以放心去修紧急问题...
# 3. 修完紧急问题后，把抽屉里的半成品拿出来继续写
git stash pop
```

---

## 🌿 三、分支隔离铁律：永远在 feature 分支上试验

> [!IMPORTANT]
> **铁律**：严禁在 `main` / `master` 主分支上直接动手改代码！

正确的分支操作流程：
```powershell
# 1. 动手前：基于当前稳定版创建并切换到维护分支
git checkout -b feat/add-new-button

# 2. 在新分支上放肆改代码、做测试...
# 3. 如果改好了，提交快照
git add .
git commit -m "feat(ui): 新增自定义按钮"

# 4. 切换回主分支并合并
git checkout main
git merge feat/add-new-button

# 5. 删除已完成的临时分支
git branch -d feat/add-new-button
```

---

## 🧪 四、5 分钟动手实战实验

### 实验：亲手制造一次“故意破坏”并成功自救

```powershell
# 步骤 1：查看当前状态
git status

# 步骤 2：在根目录新建一个测试文件并写入乱码
Add-Content -Path "test_broken.tmp" -Value "这是一行故意搞乱的测试内容"

# 步骤 3：查看状态，发现多了未跟踪文件
git status

# 步骤 4：执行清理自救
Remove-Item "test_broken.tmp" -Force

# 步骤 5：再次查看状态，确认工作区完全纯净！
git status
```

---

## 📝 今日打卡小结

1. 遇到未提交的改乱，用 `git restore .` 瞬间放弃。
2. 遇到已提交的故障，用 `git reset --hard HEAD~1` 回退到上一个稳定快照。
3. 新增功能永远先建分支：`git checkout -b <分支名>`。
