---
version: "V2.0.0"
status: "正式发布"
created: "2026-09-07"
updated: "2026-09-07"
spec_id: "GUIDE_W1_D03"
project_id: "SW-2026-008"
title: "Day 03：GUI 深色驾驶舱与 Headless 双模启动"
---

# Day 03：GUI 深色驾驶舱与 Headless 双模启动

> 🎯 **今日目标**：掌握 auto-pm 工业深色驾驶舱（PySide6/QML）与 Headless CLI 的双模启动机制与环境探针原理。  
> ⏱️ **预计耗时**：45 分钟  
> 🛠️ **前置准备**：熟悉桌面快捷启动脚本与终端命令。

---

## 💡 一、工控视角看双模架构：触摸屏 HMI 与 远程终端 SCADA

在现代自动化工厂中，同一套生产线通常具备两种监控操作方式：
1. **现场触摸屏（HMI）**：直观的深色磨砂工业界面、动态按钮、设备状态拓扑图、报警弹出卡片——对应 `auto-pm` 的 **PySide6 / QML GUI 驾驶舱**；
2. **后台命令行 / API（SCADA/MES）**：无界面的轻量脚本通道，供服务器轮询、定时任务、批处理执行——对应 `auto-pm` 的 **Headless CLI 模式**。

二者共享底层完全一致的业务逻辑（Domain Layer），界面无论怎么换，业务规则绝不重复编写！

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🚀 auto-pm 混合接入层                                                        │
├──────────────────────────────────────┬──────────────────────────────────────┤
│ 🖥️ 工业深色驾驶舱 (GUI 模式)          │ ⌨️ Headless 命令行 (CLI 模式)        │
│ • PySide6 + QML 现代化工业界面        │ • Click 驱动的 40 组命令矩阵         │
│ • 70% 暗场磨砂遮罩，消灭文字穿透      │ • Exit Code 严苛返回 (0=PASS, 1=FAIL)│
│ • 8 大业务大厅 + 5 大工站 Tab 面板   │ • 支持 --json 格式化输出供脚本集成   │
└──────────────────────────────────────┴──────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 🧠 统一领域核心层 (Project / PLC / Spec / Change / VarTable)                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## ⚙️ 二、双模启动机制深度剖析

### 1. 桌面 GUI 一键启动：`双击启动驾驶舱.bat`
桌面启动批处理文件位于工作空间根目录，它包含两项工业级防污染防护：
```bat
set PYTHONDONTWRITEBYTECODE=1
python 00_Infrastructure/auto_pm/launcher/bootstrap.py
```
- **禁写字节码**：杜绝 Python 自动在生产目录生成 `__pycache__` 导致 manifest 校验破坏；
- **Fail-Closed Bootstrap**：启动器会先探测环境完整性与指针有效性，若环境受损则返回明确错误码退出，杜绝半死不活假死运行。

### 2. Headless CLI 启动：`python -m auto_pm`
在无桌面环境或由自动化流水线调用时，使用 CLI 模式：
```powershell
$env:PYTHONPATH = "00_Infrastructure/auto_pm"
python -m auto_pm -w "c:\Users\fubai\Documents\My_Workspace" <子命令>
```

---

## 🧪 三、5 分钟动手实操实验

### 步骤 1：使用 CLI 探针检查系统版本与全局帮助
```powershell
$env:PYTHONPATH = "00_Infrastructure/auto_pm"
python -m auto_pm --help
```
*预期输出*：控制台打印规整的 CLI 命令大厅，展示 22 个以上命令分组（project, plc, change, spec, workflow, handoff 等）。

### 步骤 2：启动 GUI 驾驶舱（体验后可正常关闭）
```powershell
python 00_Infrastructure/auto_pm/launcher/bootstrap.py --resolve-only
```
*预期输出*：返回 `Exit 0`，打印当前成功解析出的 Python 解释器、active release 路径与 manifest 验证通过证据。

---

## 🛡️ 四、改崩恢复法与今日自测打卡

### 🚑 GUI 启动报模块找不到或窗口闪退
1. 检查环境变量：确保未混入旧版全局 pip 安装的 auto-pm；
2. 运行自检：执行 `python -m auto_pm doc check --strict` 确认文件一致性。

### 📝 今日自测思考题
1. 为什么说“把 UI 当成 HMI，把业务层当成 PLC 逻辑”是优秀的工业架构？
2. `--resolve-only` 选项的作用是什么？
3. QML 弹窗为什么必须使用实底面板与 70% 暗场遮罩？
