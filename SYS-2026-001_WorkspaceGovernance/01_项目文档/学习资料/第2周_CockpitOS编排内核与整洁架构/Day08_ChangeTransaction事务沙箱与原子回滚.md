---
version: "V2.0.0"
status: "正式发布"
created: "2026-09-07"
updated: "2026-09-07"
spec_id: "GUIDE_W2_D08"
project_id: "SW-2026-008"
title: "Day 08：ChangeTransaction 事务沙箱与原子回滚"
---

# Day 08：ChangeTransaction 事务沙箱与原子回滚

> 🎯 **今日目标**：理解 Cockpit OS 的变更事务管理器（ChangeTransactionManager），掌握沙箱快照、异常自动回滚与原子提交机制。  
> ⏱️ **预计耗时**：50 分钟  
> 🛠️ **前置准备**：查看 `auto_pm/domain/workflow/transaction.py`。

---

## 💡 一、工控视角看事务沙箱：伺服定位运动的“故障急停与自动复位”

在多轴协同装配机械手运行中，机械手抓取工件需要执行连续 5 个动作：
1. Z 轴下压到目标高度；
2. 气爪闭合抱紧；
3. 检测压力传感器到位信号；
4. Z 轴提升回安全位置；
5. X 轴平移送料。

如果在第 3 步“压力检测超时”，系统绝不能“停在半空或者继续平移（那样会撞机）”，必须执行**原子急停与原路复位补偿（Rollback）**：立刻张开气爪、Z 轴升起回零位，确保机械不损坏。

`ChangeTransactionManager` 就是代码世界的**“多动作原子事务控制器”**：
- 在修改一批文件前，自动给每一个目标文件拍下**内存快照（Snapshot）**；
- 如果中间任何一步报错或单测失败，立刻执行 **100% 自动回滚**，将所有文件瞬间还原；
- 只有全部步骤 100% 绿灯，才执行 **原子提交（Commit）**！

```text
with ChangeTransaction(project_root) as tx:
    tx.record_file(file_a)   # 自动保存旧快照
    modify_file(file_a)
    tx.record_file(file_b)   # 自动保存旧快照
    modify_file(file_b)
    # 若此时抛出异常 -> 触发 __exit__ -> 自动全部还原为修改前字节！
    # 若无异常 -> 自动持久化并释放沙箱锁
```

---

## ⚙️ 二、事务沙箱的三大防线

1. **快照备份隔离**：在修改任何文件前，原样字节存入临时沙箱缓冲区；
2. **新建文件追踪**：如果事务中新建了文件，回滚时会自动清理新建的垃圾文件；
3. **异常即时熔断**：任何未捕获的异常都会在毫秒级触发物理还原，不给系统留下半成品脏状态。

---

## 🧪 三、5 分钟动手实操实验

### 步骤 1：查看变更事务沙箱测试用例
```powershell
$env:PYTHONPATH = "00_Infrastructure/auto_pm"
python -m pytest tests/workflow/test_transaction.py -v
```
*预期输出*：19 项事务沙箱单测用例 100% passed，涵盖普通回滚、新建清理、嵌套事务等场景。

---

## 🛡️ 四、改崩恢复法与今日自测打卡

### 🚑 事务死锁排查
若由于外部进程锁死文件导致事务提交失败：
系统会自动将备份文件还原。可查看控制台打印的 `[ROLLBACK]` 日志确认哪些文件已成功恢复。

### 📝 今日自测思考题
1. 工业现场为什么要坚持“全成功或全回滚（All or Nothing）”的原子性？
2. 事务沙箱如何处理“在事务中新建的文件”？
3. Python 上下文管理器 `with` 在事务回滚中起到了什么关键作用？
