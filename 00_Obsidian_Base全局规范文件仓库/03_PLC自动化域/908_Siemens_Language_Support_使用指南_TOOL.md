---
spec_id: TOOL-908
title: "Siemens Language Support插件使用指南"
version: "V1.0.1"
domain: plc
lifecycle: stable
canonical_path: "00_Obsidian_Base全局规范文件仓库/03_PLC自动化域/908_Siemens_Language_Support_使用指南_TOOL.md"
tags: ["Siemens", "LSP", "工具", "使用指南"]
---

# Siemens Language Support 插件使用指南

## 一、插件概述

**Dynamic Siemens Language Support** 是一款专为西门子 PLC 开发者设计的 VS Code 扩展插件，提供完整的 SCL（Structured Text）语言支持。

### 主要功能

| 功能类别 | 功能描述 |
|---------|---------|
| **语法支持** | SCL/ST 语法高亮、注释切换、括号配对 |
| **智能编辑** | 代码补全、悬停提示、跳转定义 |
| **诊断检查** | 类型检查、错误提示、语法验证 |
| **专用编辑器** | FBD 预览、标签表编辑、S7DCL 支持 |
| **项目管理** | PLC 作用域配置、库引用管理 |
| **测试框架** | 单元测试、集成测试、测试报告 |

---

## 二、安装与配置

### 2.1 安装插件

1. 打开 VS Code
2. 进入扩展市场（`Ctrl+Shift+X`）
3. 搜索 **"Siemens Language Support"**
4. 点击安装按钮

### 2.2 项目配置

#### 2.2.1 创建 `.plc.json` 配置文件

在 PLC 项目根目录创建 `.plc.json` 文件：

```json
{
    "name": "DJ-2026-005 边框缓存机 PLC",
    "description": "边框缓存机控制系统",
    "libraries": [
        "./主控",
        "./公共服务",
        "./四层输送机",
        "./取放料机构",
        "./打胶机送料机构",
        "./外部设备交互"
    ]
}
```

**配置说明：**

| 字段 | 说明 |
|------|------|
| `name` | PLC 项目名称 |
| `description` | 项目描述 |
| `libraries` | 库目录列表，插件会自动扫描这些目录 |

#### 2.2.2 文件关联

插件自动关联以下文件类型：

| 文件扩展名 | 文件类型 | 说明 |
|-----------|---------|------|
| `.scl` | Structured Text | 结构化文本源文件 |
| `.st` | Structured Text | 结构化文本源文件 |
| `.s7dcl` | S7DCL Definition | FBD 功能块定义文件 |
| `.s7res` | S7 Resource | 资源文件 |
| `.udt` | User Data Type | 用户自定义类型 |
| `.db` | Data Block | 数据块 |
| `.awl` | AWL Language | AWL 语言文件 |

注：上表只是 VS Code 插件按扩展名认文件类型的对照表，**不是 TIA 导入规则**。TIA V19 实测：DB 和结构体（UDT）用 `.scl` 源文件都能导入（DJ-2026-011 的 DB 文件是 `.scl`；2026-11-11 驾驶舱 3 工位样例 10 个结构体用 `.scl`，全部重建 0 错误）。

---

## 三、核心功能使用

### 3.1 语法高亮

插件自动为 SCL/ST 代码提供语法高亮：

- **关键字**: `FUNCTION_BLOCK`, `VAR`, `IF`, `CASE`, `END_VAR` 等
- **数据类型**: `BOOL`, `INT`, `REAL`, `ARRAY` 等
- **注释**: 行注释 `//` 和块注释 `(* ... *)`
- **字符串**: 单引号和双引号字符串

### 3.2 智能编辑功能

#### 3.2.1 代码补全

按下 `Ctrl+Space` 触发代码补全：

```st
FUNCTION_BLOCK FB_1004_GlueMachine
VAR_INPUT
    i_b|  // 输入 i_b 后按 Ctrl+Space
END_VAR
```

补全内容包括：
- 变量名
- 功能块名
- 关键字
- 数据类型

#### 3.2.2 悬停提示

将鼠标悬停在变量或功能块上，显示详细信息：

```st
VAR
    fbGlue : FB_1004_GlueMachineFeeder_BufferFraming;
END_VAR
```

悬停显示：
- 变量类型
- 功能块定义位置
- 注释说明

#### 3.2.3 跳转定义

在变量或功能块上按下 `F12`，跳转到定义位置：

```st
fbGlueMachineFeeder(  // 在此处按 F12
    i_b使能 := TRUE
);
```

#### 3.2.4 查找引用

选中变量或功能块，按下 `Shift+F12`，查找所有引用位置。

### 3.3 诊断检查

插件提供实时诊断检查：

| 诊断类型 | 说明 | 示例 |
|---------|------|------|
| **未定义变量** | 使用未声明的变量 | `Unknown identifier 'x'` |
| **类型不匹配** | 赋值类型不兼容 | `Type mismatch: expected BOOL, got INT` |
| **重复定义** | 变量重复声明 | `Duplicate declaration` |
| **语法错误** | 语法不符合规范 | `Syntax error` |

### 3.4 FBD 块预览

打开 `.s7dcl` 文件，插件自动渲染 FBD 功能块接口预览：

```
输入参数          输出参数
┌─────────┐      ┌─────────┐
│i_b使能  │      │o_b运行中│
│i_b自动模式│     │o_b故障  │
│i_b启动  │      │o_i状态  │
└─────────┘      └─────────┘
     │               │
     └──────┬────────┘
            ▼
   ┌─────────────────┐
   │ FB_1003_PickPlace│
   └─────────────────┘
```

---

## 四、功能块开发规范

### 4.1 功能块声明

```st
FUNCTION_BLOCK FB_1004_GlueMachineFeeder_BufferFraming
    VAR_INPUT
        i_b使能 : BOOL;           // 输入变量: i_ 前缀
        i_b自动模式 : BOOL;
    END_VAR
    
    VAR_OUTPUT
        o_b运行中 : BOOL;         // 输出变量: o_ 前缀
        o_b故障 : BOOL;
    END_VAR
    
    VAR
        s_i步序 : INT;            // 内部变量: s_ 前缀
        s_b运行中 : BOOL;
    END_VAR
    
    VAR CONSTANT
        STP_空闲 : INT := 0;      // 常量定义
    END_VAR
END_FUNCTION_BLOCK
```

### 4.2 功能块实例化与调用

```st
PROGRAM PRG_MainControl
    VAR
        // 实例化功能块
        fbGlueMachine : FB_1004_GlueMachineFeeder_BufferFraming;
    END_VAR
    
    // 调用功能块
    fbGlueMachine(
        i_b使能 := TRUE,
        i_b自动模式 := stHMI_In.bAutoMode,
        o_b运行中 => stHMI_Out.bFeederRunning,
        o_b故障 => stCoordination.bFeederFault
    );
END_PROGRAM
```

### 4.3 命名规范

| 变量类型 | 前缀 | 示例 |
|---------|------|------|
| 输入变量 | `i_` | `i_b使能`, `i_r速度` |
| 输出变量 | `o_` | `o_b运行中`, `o_i状态` |
| 内部变量 | `s_` | `s_i步序`, `s_b运行中` |
| 定时器 | `t_` | `t动作定时器`, `t超时定时器` |

---

## 五、测试框架使用

### 5.1 创建测试文件

创建 `.scltest` 文件：

```st
// ============================================================================
// 测试文件说明注释
// ============================================================================

TEST_CASE "初始化流程测试"
    // 测试功能块初始化流程
    
    SET GlobalVars.stFeeder.i_bAutoMode := TRUE;
    SET GlobalVars.stFeeder.i_bManualMode := FALSE;
    
    WAIT_CYCLES 2;
    
    ASSERT GlobalVars.stFeeder.q_bRunning = FALSE;
    ASSERT GlobalVars.stFeeder.q_iCurrentState = 0;
END_TEST_CASE

TEST_CASE "伺服故障报警测试"
    // 测试伺服故障检测
    
    SET GlobalVars.stFeeder.i_bAutoMode := TRUE;
    SET GlobalVars.stFeeder.i_bManualMode := FALSE;
    
    WAIT_CYCLES 2;
    
    SET GlobalVars.stGlobal.i_bX2ServoFault := TRUE;
    WAIT_CYCLES 1;
    
    ASSERT GlobalVars.stGlobal.q_wCurrentAlarmCode = 12;
END_TEST_CASE
```

**测试语法说明：**

| 关键字 | 语法 | 说明 |
|--------|------|------|
| `TEST_CASE` | `TEST_CASE "用例名称"` | 定义测试用例开始 |
| `END_TEST_CASE` | `END_TEST_CASE` | 定义测试用例结束 |
| `SET` | `SET 变量 := 值;` | 设置变量值 |
| `WAIT_CYCLES` | `WAIT_CYCLES 周期数;` | 等待指定扫描周期数 |
| `ASSERT` | `ASSERT 条件;` | 断言验证条件 |

**注意：不支持 `TESTSUITE`、`DESCRIPTION`、`VAR`/`END_VAR` 等关键字**

### 5.2 运行测试

1. 打开 VS Code 测试资源管理器（侧边栏测试图标）
2. 选择要运行的测试套件或测试用例
3. 点击运行按钮

### 5.3 测试报告

测试结果会显示在输出面板：

```
测试套件: FB_1004_GlueMachineFeeder_BufferFraming
  ✅ 初始化流程测试
  ✅ 伺服故障报警测试
  ✅ 安全区信号测试
  
测试完成: 3/3 通过
```

---

## 六、快捷键参考

| 快捷键 | 功能 |
|--------|------|
| `Ctrl+Space` | 代码补全 |
| `F12` | 跳转到定义 |
| `Shift+F12` | 查找引用 |
| `Ctrl+K Ctrl+I` | 显示悬停信息 |
| `Ctrl+/` | 注释切换 |
| `Ctrl+Shift+P` | 打开命令面板 |

---

## 七、项目配置示例

### 7.1 项目结构

```
DJ-2026-005_边框缓存机/
├── 02_PLC程序/
│   └── 通用ST程序及变量表/
│       ├── .plc.json                    # PLC配置文件
│       ├── 主控/                        # 主控制程序
│       │   ├── PRG_MainControl.scl
│       │   ├── PRG_StationCoordinator.scl
│       │   └── TypeDefinitions.scl
│       ├── 四层输送机/                  # 输送机功能块
│       │   ├── FB_1001_Conveyor4Layer.scl
│       │   └── FB_1002_SingleLayer.scl
│       ├── 取放料机构/                  # 取放料功能块
│       │   ├── FB_1003_PickPlace.s7dcl
│       │   └── FB_1003_PickPlace.scl
│       ├── 打胶机送料机构/              # 送料机构功能块
│       │   ├── FB_1004_GlueMachine.scl
│       │   └── FB_1004_GlueMachine.scltest
│       └── 公共服务/                    # 公共服务功能块
│           └── FB_2001_CommonAlarm.scl
```

### 7.2 完整 `.plc.json` 配置

```json
{
    "name": "DJ-2026-005 边框缓存机 PLC",
    "description": "边框缓存机控制系统 - 四层输送机 + 取放料机构 + 打胶机送料机构",
    "libraries": [
        "./主控",
        "./公共服务",
        "./四层输送机",
        "./取放料机构",
        "./打胶机送料机构",
        "./外部设备交互"
    ]
}
```

---

## 八、故障排除

### 8.1 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| **语法高亮不生效** | 文件未关联 | 确保文件扩展名正确（.scl, .st） |
| **诊断报错"未定义"** | 功能块未找到 | 检查 `.plc.json` 库路径 |
| **跳转定义失效** | 功能块定义不存在 | 确保功能块已正确声明 |
| **测试无法运行** | 测试语法错误 | 检查 `END_TESTSUITE` 是否存在 |

### 8.2 日志查看

1. 打开命令面板（`Ctrl+Shift+P`）
2. 输入 **"Siemens: Show Language Server Log"**
3. 查看日志定位问题

---

## 九、版本信息

| 项目 | 说明 |
|------|------|
| 插件名称 | Dynamic Siemens Language Support |
| 版本 | 2.5.0 |
| 作者 | DynamicEngineering |
| 发布平台 | VS Marketplace, Open-VSX |

---

**文档版本**: V1.0.1  
**创建日期**: 2026-04-28  
**适用项目**: DJ-2026-005 边框缓存机
