---
version: "V2.0.0"
status: "正式发布"
created: "2026-09-07"
updated: "2026-09-07"
spec_id: "GUIDE_W4_D18"
project_id: "SW-2026-008"
title: "Day 18：双槽无感切流与日常运维 CheckList"
---

# Day 18：双槽无感切流与日常运维 CheckList

> 🎯 **今日目标**：掌握 Release 生产槽位的无感原子切流（Switchover），熟悉系统日常健康体检 CheckList，完成系统接管结项。  
> ⏱️ **预计耗时**：50 分钟  
> 🛠️ **前置准备**：查看 `00_Infrastructure/auto_pm/` 运行容器。

---

## 💡 一、工控视角看生产切流：上位机双机热备与无扰切换

在水厂、电厂或大型化工厂中，主控上位机系统如果要升级新版本：
- 绝对禁止“让产线停机 2 小时，在主机上卸载旧软件、安装新软件”；
- 必须采用**无扰切换（Bumpless Transfer）**：
  1. 备机在后台离线部署好新版本，运行 100 项模拟单测，确认数据流完全正常；
  2. 运维人员按下“切流按钮”；
  3. 网络路由器瞬间把数据采集流重定向至备机，主机降为备用，用户界面甚至感觉不到一帧的卡顿！

`auto-pm` 的 **单向发布链与双槽无感切流** 正是基于此工业思想落地：

```text
① 母体研发测试全绿 ──> ② 构建候选槽位 1.2.4-xxxx ──> ③ 离线 465 文件 manifest 校验
                                                                   │
                                                                   ▼
⑥ 生产系统平稳运行 <── ⑤ 原子修改指针 (active_release.json) <── ④ 架构师正式批准切流
```

---

## ⚙️ 二、日常运维体检 CheckList（接管必背）

作为接管系统的电气总工兼 PM，每天上班启动系统或提交新改动前，只需按顺序运行以下 **四门禁健康体检套餐**：

```powershell
# 1. 语法与门禁：PLC 53 项体检（确保下位机无死锁与缺项）
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" plc check --all

# 2. 文档与死链：严格文档一致性门禁（确保无死链、版本锁定）
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" doc check --strict

# 3. 会话与健康：PM_SESSION 结构与字段自检
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" pm-session check SW-2026-008

# 4. 台账与审计：生产台账一致性对账（确保 0 缺失 0 孤儿）
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" ledger reconcile SW-2026-008
```

只要这四条指令全部返回 **Exit 0（全绿灯）**，就可以放心地给现场交付、闭环结项！

---

## 🧪 三、5 分钟动手实操实验

### 步骤 1：完整执行一次四门禁体检大连跑
```powershell
$env:PYTHONPATH = "00_Infrastructure/auto_pm"
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" doc check --strict
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" ledger reconcile SW-2026-008
```
*预期输出*：全绿通过，0 报警，0 差异。

### 步骤 2：查看发布部署证据清单
```powershell
Get-Content "00_Infrastructure/auto_pm/releases/1.2.4-6699a5b/deployment_manifest.json" | Select-String "file_count"
```
*预期输出*：显示不可变发布包中 465 个文件的精确受控证据。

---

## 🛡️ 四、改崩恢复法与今日自测打卡

### 🚑 生产切流后的紧急回滚
若新版本切流上线后发现不可预期的重大异常，只需修改 `active_release.json`，将指针重新指回 `previous_release.json` 记录的历史稳定版本，即可在 1 秒内完成生产回退！

### 📝 结项结语与接管确认
恭喜你！通过这 4 周 18 天的系统学习与实战演练，你已经完全掌握了 `auto-pm` 的底层安全防线、双槽部署机制、Cockpit OS 编排内核、多 Agent 契约协同以及 40 组 CLI 命令实战。
你已经成功实现了从“单纯画图写程序的电气工程师”向“具备工业 SRE 架构思维的一人全栈超级个体”的华丽转身！
