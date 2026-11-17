---
version: "V2.0.0"
status: "正式发布"
created: "2026-09-07"
updated: "2026-09-07"
spec_id: "GUIDE_W1_D02"
project_id: "SW-2026-008"
title: "Day 02：Release 双槽稳定部署与不可变制品"
---

# Day 02：Release 双槽稳定部署与不可变制品

> 🎯 **今日目标**：理解工业级 SRE 双槽稳定部署架构（Active / Previous），掌握不可变 release 制品与 manifest 防篡改机制。  
> ⏱️ **预计耗时**：50 分钟  
> 🛠️ **前置准备**：查看 `00_Infrastructure/auto_pm/releases/` 目录。

---

## 💡 一、工控视角看双槽部署：PLC 双 CPU 冗余与 A/B 系统切换

在高端工控机（如西门子 IPC、倍福 CX 系列）或手机 OTA 升级时，工业系统从来不会“直接在正在运行的程序里修改代码”，而是采用 **A/B 双槽（Dual-Slot）冗余机制**：
- **A 槽（Active）**：正在运行的生产程序，处于只读锁定状态，绝不允许外部随意改动；
- **B 槽（Inactive）**：新固件的准备与烧录区，烧录完毕后进行完整性离线校验；
- **原子指针翻转**：确认新版本无误后，瞬间将引导指针从 A 槽翻转到 B 槽。一旦新版本崩溃，硬件看门狗会瞬间把指针翻回 A 槽实现秒级回滚！

`auto-pm` 彻底淘汰了传统的“源码平铺就地运行”，全面拥抱该架构：

```text
00_Infrastructure/auto_pm/
├── active_release.json        # 【当前活动槽指针】 -> 指向 releases/1.2.4-6699a5b
├── previous_release.json      # 【备用回滚槽指针】 -> 指向 releases/1.2.3-f950525 (或 null)
└── releases/
    ├── 1.2.3-f950525/         # 历史不可变槽位 (冻结归档)
    └── 1.2.4-6699a5b/         # 当前生产活动槽位 (不可变只读)
        ├── manifest.json      # 465 文件 SHA-256 哈希清单 (防篡改捕兽夹)
        └── auto_pm/           # 生产二进制与纯净运行时
```

---

## ⚙️ 二、不可变制品与 Manifest 465 文件硬锁

### 1. 为什么禁止在 `releases/` 目录下直接改代码？
`1.2.4-6699a5b` 槽位中的每一个 `.py` 文件，在发布时都生成了唯一的 SHA-256 指纹，记录在 `manifest.json` 中。
系统在启动或执行严格门禁时，会自动计算该目录下 465 个文件的哈希：
- 只要有人偷偷改动了一个字符，或生成了一个 `__pycache__` 垃圾文件，哈希立刻失配，系统判定为“槽位受污染”并拒绝启动！

### 2. 研发母体 vs 稳定部署位
- **研发母体**：`01_Project.../SW-2026-008_...` 是唯一的开发与源码演进基地；
- **稳定运行位**：`00_Infrastructure/auto_pm` 纯粹作为不可变部署容器，只读不写。

---

## 🧪 三、5 分钟动手实操实验

### 步骤 1：查看当前生产活动指针
```powershell
Get-Content "00_Infrastructure/auto_pm/active_release.json"
```
*预期输出*：
```json
{
  "schema_version": "release_pointer.v1",
  "slot": "active_release.json",
  "release_id": "1.2.4-6699a5b",
  "release_path": "1.2.4-6699a5b"
}
```

### 步骤 2：查看发布槽位清单与不可变制品
```powershell
Get-ChildItem "00_Infrastructure/auto_pm/releases"
```
*预期输出*：清晰展示 `1.2.3-f950525` 与 `1.2.4-6699a5b` 两个不可变槽位。

---

## 🛡️ 四、改崩恢复法与今日自测打卡

### 🚑 误改生产槽位的抢救
若不小心手滑修改了 `00_Infrastructure/auto_pm/releases/` 下的某个文件导致 manifest 报错：
```powershell
git checkout HEAD -- 00_Infrastructure/auto_pm/releases/
```
一秒恢复与 Git 仓库完全一致的不可变哈希状态。

### 📝 今日自测思考题
1. 为什么 auto-pm 要求在启动脚本中加入 `PYTHONDONTWRITEBYTECODE=1`？
2. `active_release.json` 与 `previous_release.json` 的双槽机制解决了什么生产风险？
3. 如果需要开发新功能，应该修改 `00_Infrastructure` 还是 `SW-2026-008` 母体？
