# Tasks

- [x] Task 1: 给关键 Python 文件加 PLC 概念注释
  - [x] 1.1 `auto_pm/ui/registry.py` → 标注为 OB1 组织块
  - [x] 1.2 `auto_pm/application/workbench_facade.py` → 标注为 FB_Workbench
  - [x] 1.3 `auto_pm/application/change_facade.py` → 标注为 FB_Change
  - [x] 1.4 `auto_pm/application/spec_facade.py` → 标注为 FB_Spec
  - [x] 1.5 `auto_pm/application/delivery_facade.py` → 标注为 FB_Delivery
  - [x] 1.6 `auto_pm/application/system_facade.py` → 标注为 FB_System
  - [x] 1.7 `auto_pm/ui/qml/bridges/workbench_bridge.py` → 标注为 HMI 变量表
  - [x] 1.8 `auto_pm/ui/qml/bridges/change_bridge.py` → 标注为 HMI 变量表
  - [x] 1.9 `auto_pm/ui/qml/bridges/spec_bridge.py` → 标注为 HMI 变量表
  - [x] 1.10 `auto_pm/ui/qml/bridges/delivery_bridge.py` → 标注为 HMI 变量表
  - [x] 1.11 `auto_pm/ui/qml/bridges/system_bridge.py` → 标注为 HMI 变量表
  - [x] 1.12 `auto_pm/core/project_service.py` → 标注为 SFB 库函数
  - [x] 1.13 `auto_pm/models/__init__.py` → 标注为 UDT 数据类型
  - [x] 1.14 `auto_pm/ui/qml_main_window.py` → 标注为主程序入口

- [x] Task 2: 创建架构对照图
  - [x] 2.1 在项目根目录创建 `ARCHITECTURE.md`
  - [x] 2.2 包含：架构层次图（PLC 术语版）、数据流说明、概念对照表
  - [x] 2.3 包含：如何新增一个功能的步骤（用 PLC 思维描述）

- [x] Task 3: 更新 PM_SESSION
  - [x] 3.1 记录本次认知重构的目的和结果
  - [x] 3.2 更新 §2 Current Focus 和 §8 Handoff Notes

# Task Dependencies

- Task 1、Task 2 可并行执行
- Task 3 在 Task 1-2 完成后进行