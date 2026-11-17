# Day 16：真实工业变更单流转实战

> 🎯 **今日目标**：结合真实电气工程场景，走通一次完整的“工业变更单 9 步闭环流转”。
> ⏱️ **预计耗时**：50 分钟
> 🛠️ **前置准备**：完成第 3 周全部内容。

---

## 📋 一、工业变更 9 步闭环生命周期

现场最怕“私改程序不留底”。`auto-pm` 强制实施标准化变更闭环：

```
1. 建立草稿 ──> 2. 方案评审 ──> 3. 正式审批 ──> 4. 编码实施 ──> 5. 门禁验证 ──> 6. 关闭归档
(draft)        (review)        (approved)      (applied)       (verified)      (closed)
```

---

## 🛠️ 二、实操：发起并流转一张变更单

### 步骤 1：创建变更单草稿
```powershell
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" change create DJ-2026-005 "新增传感器消抖算法"
```

### 步骤 2：查看变更单状态与 12 章节向导
```powershell
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" change list
```

### 步骤 3：状态流转到下一个阶段
```powershell
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" change transition CHG-PLC-2026-001 approved
```

---

## 📝 今日打卡小结

1. 变更单是工业软件和 PLC 改动的唯一合法凭据。
2. 变更单状态不可跳级流转，保证质量与溯源闭环。
