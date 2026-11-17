# Day 06：Python 面向对象与 5 层整洁架构

> 🎯 **今日目标**：理解 Python 类与 PLC 功能块 (FB) 的深度对应，看清 `auto-pm` 的 5 层整洁架构地图。
> ⏱️ **预计耗时**：50 分钟
> 🛠️ **前置准备**：完成第 1 周全部内容。

---

## 💡 一、工控类比：FB 实例与 Python Class

很多电气工程师觉得 Python 的面向对象（Class）很难懂，其实它和 PLC 的 **FB（功能块）与背景 DB** 是一回事：

```
PLC 的 FB / 背景 DB           Python 的 Class / 对象
─────────────────────────     ──────────────────────────
FB 模板定义                   class 类定义
输入引脚 VAR_INPUT            __init__(self, in_param) 形参
输出引脚 VAR_OUTPUT           def 方法的返回值 (return)
内部静态变量 VAR (背景DB)      self.var_name 内部属性
FB 内部逻辑代码               def method_name(self): 内部方法
OB1 中调用 FB 产生背景 DB     my_instance = MyClass() 实例化
```

### 极简代码对照：

```python
# 就像在西门子博途中写一个 FB_MotorControl
class MotorControl:
    def __init__(self, motor_id: str, max_speed: float):
        # 相当于在背景 DB 里分配变量
        self.motor_id = motor_id
        self.max_speed = max_speed
        self.is_running = False

    def start(self) -> bool:
        # 相当于 FB 内部的启动控制逻辑
        print(f"电机 {self.motor_id} 启动，转速设定为: {self.max_speed}")
        self.is_running = True
        return self.is_running

# 相当于在 OB1 产生背景 DB "DB_Motor1" 并调用
motor1 = MotorControl(motor_id="M101", max_speed=1500.0)
motor1.start()
```

---

## 🗺️ 二、auto-pm 的 5 层整洁架构地图

在修改驾驶舱时，**绝对不要乱翻文件**，只需按图索骥：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. 画面显示层 (QML Views)        auto_pm/ui/qml/views/                     │
│    • 负责：把按钮、表格、曲线画在屏幕上（不负责计算）                      │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2. 通信转换层 (Bridges)          auto_pm/ui/bridges/                       │
│    • 负责：作为 QML 和 Python 之间的“光耦隔离中继”，转发信号和数据          │
├─────────────────────────────────────────────────────────────────────────────┤
│ 3. 门面门禁层 (Facades)          auto_pm/application/facades/              │
│    • 负责：统一调度后台多个服务，把原始数据打包成适合画面的格式            │
├─────────────────────────────────────────────────────────────────────────────┤
│ 4. 核心计算层 (Core Services)    auto_pm/application/core/ & domain/       │
│    • 负责：真正的 Modbus 解析、PLC SCL 语法扫描、项目文件增删改             │
├─────────────────────────────────────────────────────────────────────────────┤
│ 5. 数据结构层 (DTO / Models)     auto_pm/domain/models/                    │
│    • 负责：定义标准点表结构、项目信息结构体（相当于 UDT）                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

> 💡 **改动定位黄金准则**：
> - **只改画面文字/颜色/按钮排版** $\rightarrow$ 去改 **第 1 层 (QML)**
> - **只改底层数学公式/解码规则/扫描逻辑** $\rightarrow$ 去改 **第 4 层 (Service)**
> - **前后端要加一个新的数据传输通道** $\rightarrow$ 去改 **第 2 层 (Bridge)**

---

## 🧪 三、5 分钟动手实战实验

### 步骤 1：查看核心服务文件结构
打开终端，查看 Service 层的真实目录：
```powershell
Get-ChildItem -Path "01_Project自动化项目管理\Python自动化项目总库\02_在研项目\SW-2026-008_auto-pm_自动化项目管理工具\auto_pm\application\core" | Select-Object Name
```

### 步骤 2：体验一次 Python 类调用
```powershell
python -c "from auto_pm.application.core.governance_service import GovernanceService; gs = GovernanceService(); print('Governance Service 实例化成功！')"
```

---

## 📝 今日打卡小结

1. Python 的 `class` 就是 PLC 的 `FB`，`self.xxx` 就是背景 DB 里的变量。
2. auto-pm 遵循 5 层架构，画面（QML）与计算（Service）完全解耦。
