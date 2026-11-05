# auto-pm 架构文档化方案 Spec

## Why

用户是电气工程师，精通 PLC/HMI 体系。现有 auto-pm 的 Service/Facade/Bridge 命名对电气工程师不直观，但架构本身并不复杂。目标：**零代码改动，仅通过注释和文档建立 PLC/HMI 概念映射**，让用户用自己的知识体系理解现有代码。

## 核心思想：概念映射，不动代码

现有架构本身是合理的，只需要换个视角看：

| 现有代码 | 实际做的事 | PLC/HMI 对应概念 |
|----------|-----------|-----------------|
| `ui/registry.py` FacadeRegistry | 初始化所有模块，注入 QML 上下文 | **OB1 组织块**：上电初始化 |
| `ui/qml/bridges/` Bridge 类 | QML 可调用的方法列表，Signal 通知数据变化 | **HMI 变量表**：画面能读写的接口 |
| `application/` Facade 类 | 封装业务逻辑，聚合多个 Service | **FB 功能块**：封装一个完整功能 |
| `core/` Service 类 | 底层数据操作（文件读写、DB查询） | **库函数 SFB/SFC**：底层工具 |
| `models/` 数据类 | 数据结构定义 | **UDT 自定义数据类型** |
| `ui/contracts/dto/` DTO | 传给 QML 的数据格式 | **HMI 画面的数据结构** |
| QML Signal | 数据变了自动通知 QML | **HMI 变量变化事件** |
| QML @Slot | QML 调用的方法 | **HMI 按钮触发的脚本** |

## What Changes

### 零代码改动

- 不改任何 `.py` 逻辑
- 不改任何 `.qml` 逻辑
- 不移动任何文件
- 不删除任何模块

### 只做三件事

1. **给关键文件加块注释**：在文件头部用 PLC 术语解释该文件的作用
2. **画一张架构对照图**：放在项目根目录，一眼看懂
3. **更新 PM_SESSION**：记录这次认知重构

### 注释示例

**`auto_pm/ui/registry.py`**（当前 OB1 组织块）：
```python
"""PLC-HMI 概念映射：OB1 组织块（初始化扫描）

像 PLC 上电的第一个扫描周期，负责：
1. 初始化所有 DB（数据块/Service）
2. 装配所有 FB（功能块/Facade）
3. 注入 HMI 上下文（让画面能访问 FB）
"""
```

**`auto_pm/application/workbench_facade.py`**（当前 FB_Workbench）：
```python
"""PLC-HMI 概念映射：FB_Workbench 功能块

对应 PLC 的 FB，封装"工作台"域的完整业务逻辑。
- 输入引脚：__init__ 参数（project_service, dashboard_service 等）
- 输出引脚：返回 QueryResult/CommandResult（写回 HMI 变量表）
- 内部调用：SFB 库函数（core/ 下的 Service）
"""
```

**`auto_pm/ui/qml/bridges/workbench_bridge.py`**（当前 HMI 变量表）：
```python
"""PLC-HMI 概念映射：HMI 变量表接口

像 HMI 触摸屏的变量表，定义了 QML 画面能访问的所有变量和方法：
- @Slot 方法 = HMI 按钮触发的脚本
- Signal = HMI 变量变化事件（数据变了自动刷新画面）
- Property = HMI 只读变量（画面直接绑定显示）
"""
```

## Impact

- **零风险**：不改任何代码，1352 个测试全部不受影响
- **零回归**：不需要重新测试
- **即时生效**：改完注释就可以用新视角看代码
- **CLI 不受影响**：本来就不涉及

## 实施清单

1. 在以下文件头部加 PLC 概念注释：
   - `auto_pm/ui/registry.py` → OB1 组织块
   - `auto_pm/application/*.py`（5 个 Facade）→ FB 功能块
   - `auto_pm/ui/qml/bridges/*.py`（5 个 Bridge）→ HMI 变量表
   - `auto_pm/core/project_service.py` → SFB 库函数（示例）
   - `auto_pm/models/` → UDT 数据类型
   - `auto_pm/ui/qml_main_window.py` → 主程序入口

2. 在项目根目录创建 `ARCHITECTURE.md`（架构对照图）

3. 更新 PM_SESSION 记录本次认知重构