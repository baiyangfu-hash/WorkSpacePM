---
spec_id: DEV-220
title: Python项目打包规范
version: V2.4.1
domain: python
lifecycle: stable
canonical_path: "00_Obsidian_Base全局规范文件仓库/02_Python开发域/220_Python项目打包规范_DEV.md"
aliases: ["CODE-220"]
---




# Python项目打包规范



## 1. 文档基础信息



**文档标题**：Python项目打包规范
**文档版本**：V2.4.1
**编制日期**：2026-07-18
**编制人**：技术团队

**审核人**：[审核人姓名]



## 2. 版本变更记录



| 版本号 | 变更内容 | 变更人 | 变更日期 | 详细说明 |
|--------|----------|--------|----------|----------|
| V2.4.1 | 附录A构建脚本标为已退役 | auto-pm | 2026-11-14 | 1)附录A标题与说明改为“已退役”，打包一律用 auto-pm delivery 命令 2)A.1、A.5 中指向脚本的两处改为历史说明；正文其余内容不变 |
| V2.4.0 | 新增旧版归档机制 + auto-pm delivery CLI | auto-pm | 2026-07-18 | 1)新增§18旧版归档机制（archive/子目录+archive_info.md） 2)新增§19 auto-pm delivery CLI命令参考 3)更新§16两阶段流程增加归档步骤 4)附录A标注build_delivery.py为兼容保留，推荐使用CLI |
| V2.3.0 | 补充hatchling打包模式 | auto-pm | 2026-06-21 | 1)新增hatchling+pyproject.toml打包模式 2)PyInstaller模式降级为可选方案 3)补充pip install -e .开发模式和hatch build构建流程 |
| V2.2.0 | 规范缺陷修复+构建脚本强制化 | AI Assistant | 2026-04-15 | 1)D1:消除L526 Compress-Archive矛盾 2)D2:目录结构对齐实际项目 3)D3:ZIP阈值更新至150-170MB 4)D4:新增附录A(标准构建脚本build_delivery.py) |

| V2.1.0 | AI打包风险控制+强制验证机制+两阶段流程标准化 | AI Assistant | 2026-04-15 | 1)新增第15节AI辅助打包风险控制 2)新增第16节两阶段交付标准流程 3)强化第17节打包后验证为强制性检查 4)新增关键文件阈值校验(文件数/大小/核心程序) 5)补充AI打包遗漏真实案例 |

| V2.0.0 | 全面升级：完整交付物归档+命名标准统一 | AI Assistant | 2026-04-12 | 1)统一命名格式为{系统名称}_V{版本号}_{日期}.zip 2)新增第11节完整交付物归档章节 3)定义8大目录归档结构 4)对齐通用交付规范 |

| V1.0.0 | 初始版本 | 文档专家 | 2026-01-15 | 定义Python项目打包的基本规范 |

| V1.1.0 | 更新为exe打包规范，移除PyPI相关内容 | 文档专家 | 2026-03-10 | 优化打包流程和最佳实践 |

| V1.2.0 | 简化为纯exe交付规范，无需安装步骤 | 技术团队 | 2026-03-17 | 只交付exe文件，无需任何安装配置 |



## 3. 范围



本规范适用于所有Python项目的打包和发布过程，涵盖两种打包模式：

1. **hatchling + pyproject.toml 模式**（推荐）：适用于库和CLI工具，通过 pip 安装使用
2. **PyInstaller exe 模式**（可选）：适用于桌面 GUI 应用，打包为独立可执行文件

**核心原则**：
- 库/CLI工具优先使用 hatchling 打包，通过 pip 安装分发
- 桌面 GUI 应用使用 PyInstaller 打包为 exe，用户双击即可运行
- 无需配置Python环境，无需安装任何依赖库



## 4. 术语定义



| 术语 | 定义 |

|------|------|

| exe打包 | 将Python项目打包成Windows可执行文件（.exe） |
| hatchling打包 | 使用hatchling构建后端打包为sdist/wheel |
| 无需安装 | 用户无需安装Python环境即可直接运行exe文件 |
| 单文件打包 | 将所有内容打包成一个exe文件，包含Python解释器和所有依赖 |
| 绿色版 | 无需安装，解压后双击即可运行 |
| 便携版 | 可以将整个应用放入U盘中随身携带使用 |
| 开发模式 | pip install -e . 以可编辑模式安装，代码修改即时生效 |
| 生产模式 | pip install . 安装到Python环境，适合正式使用 |



## 5. 打包工具

### 5.1 hatchling（推荐）

hatchling 是现代化的 Python 构建后端，配合 pyproject.toml 使用，是 PEP 517/518 标准的实现。

**特点**：
- 符合 PEP 517/518 标准
- 配置集中在 pyproject.toml
- 支持 sdist/wheel 构建
- 开发模式安装（pip install -e .）
- 社区活跃，Hatch 生态完善

### 5.2 PyInstaller（可选，用于桌面应用）

PyInstaller是最流行的Python打包工具，支持将Python程序打包成独立的可执行文件。

**特点**：
- 支持Windows、Linux、macOS
- 支持单文件和目录打包
- 自动分析依赖关系
- 支持图标和版本信息
- 适用于 PySide6/PyQt GUI 应用打包



### 5.3 cx_Freeze



cx_Freeze是另一个流行的Python打包工具，支持跨平台打包。



**特点**：

- 支持Windows、Linux、macOS

- 配置灵活

- 支持服务打包

- 社区活跃



### 5.4 Nuitka



Nuitka是一个Python编译器，可以将Python代码编译成C代码，然后生成可执行文件。



**特点**：

- 性能更好

- 代码保护更强

- 支持C扩展

- 编译时间较长



### 5.5 PyOxidizer



PyOxidizer是一个现代化的Python打包工具，使用Rust实现。



**特点**：

- 性能优异

- 安全性好

- 配置简单

- 支持嵌入式Python



## 6. 打包流程

### 6.0 模式选择

| 项目类型 | 推荐模式 | 安装方式 |
|----------|----------|----------|
| CLI 工具（如 auto-pm、其他 Click CLI 工具） | hatchling + pyproject.toml | `pip install .` 或 `pip install -e .` |
| 库/SDK | hatchling + pyproject.toml | `pip install .` 或 `pip install -e .` |
| 桌面 GUI 应用（PySide6/PyQt） | PyInstaller exe | 双击 exe 运行 |

### 6.1 hatchling + pyproject.toml 打包（推荐）

#### 6.1.1 pyproject.toml 配置

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "auto-pm"
version = "2.0.0"
description = "自动化项目管理工具"
readme = "README.md"
requires-python = ">=3.10"
license = "MIT"
dependencies = [
    "click>=8.0",
    "rich>=13.0",
]

[project.scripts]
auto-pm = "auto_pm.cli.__main__:cli"
my-tool = "my_tool.cli.__main__:cli"

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-qt>=4.0",
]
```

#### 6.1.2 开发模式安装

```bash
# 开发模式：代码修改即时生效，无需重新安装
pip install -e .

# 带开发依赖
pip install -e ".[dev]"
```

**适用场景**：
- 日常开发调试
- 代码修改后立即测试
- 多项目联调

#### 6.1.3 生产模式安装

```bash
# 生产模式：安装到 Python 环境
pip install .

# 从 PyPI 安装（发布后）
pip install auto-pm
```

**适用场景**：
- 正式环境部署
- 用户安装使用

#### 6.1.4 构建 sdist/wheel

```bash
# 安装 hatch
pip install hatch

# 构建 sdist 和 wheel
hatch build

# 输出位置: dist/
#   dist/auto_pm-2.0.0.tar.gz  (sdist)
#   dist/auto_pm-2.0.0-py3-none-any.whl  (wheel)
```

#### 6.1.5 验证构建产物

```bash
# 检查 wheel 内容
python -m zipfile -l dist/auto_pm-2.0.0-py3-none-any.whl

# 在干净环境中测试安装
pip install dist/auto_pm-2.0.0-py3-none-any.whl
auto-pm --help
```

### 6.2 准备工作



1. **项目结构**：确保项目结构清晰，入口文件明确

2. **依赖管理**：使用requirements.txt或pyproject.toml管理依赖

3. **资源文件**：确保资源文件（图片、配置等）路径正确

4. **测试验证**：确保项目在开发环境中运行正常



### 6.3 安装打包工具

#### 6.3.1 安装hatchling

```bash
pip install hatchling
```

#### 6.3.2 安装PyInstaller



```bash

pip install pyinstaller

```



#### 6.3.3 安装cx_Freeze



```bash

pip install cx_Freeze

```



#### 6.2.3 安装Nuitka



```bash

pip install nuitka

```



### 6.4 PyInstaller打包（可选，用于桌面应用）

#### 6.4.1 基本打包命令



```bash

# 单文件打包

pyinstaller --onefile main.py



# 目录打包

pyinstaller --onedir main.py



# 指定输出目录

pyinstaller --distpath ./output main.py

```



#### 6.4.2 常用参数



| 参数 | 说明 |

|------|------|

| `--onefile` | 打包成单个exe文件 |

| `--onedir` | 打包成目录（默认） |

| `--name` | 指定exe文件名 |

| `--icon` | 指定图标文件 |

| `--windowed` | 无控制台窗口（GUI程序） |

| `--console` | 显示控制台窗口（CLI程序） |

| `--add-data` | 添加数据文件 |

| `--hidden-import` | 添加隐藏导入 |

| `--exclude-module` | 排除模块 |

| `--clean` | 清理缓存 |

| `--noconfirm` | 不询问确认 |



#### 6.4.3 完整打包示例



```bash

pyinstaller ^

  --onefile ^

  --name "MyApp" ^

  --icon "assets/icon.ico" ^

  --windowed ^

  --add-data "assets;assets" ^

  --hidden-import "pkg_resources" ^

  --clean ^

  main.py

```



#### 6.3.4 使用spec文件



spec文件是PyInstaller的配置文件，可以保存打包配置。



**生成spec文件**：

```bash

pyinstaller --onefile main.py

```



**编辑spec文件**：

```python

# -*- mode: python ; coding: utf-8 -*-



block_cipher = None



a = Analysis(

    ['main.py'],

    pathex=[],

    binaries=[],

    datas=[('assets/*', 'assets')],

    hiddenimports=['pkg_resources'],

    hookspath=[],

    hooksconfig={},

    runtime_hooks=[],

    excludes=[],

    win_no_prefer_redirects=False,

    win_private_assemblies=False,

    cipher=block_cipher,

    noarchive=False,

)



pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)



exe = EXE(

    pyz,

    a.scripts,

    a.binaries,

    a.zipfiles,

    a.datas,

    [],

    name='MyApp',

    debug=False,

    bootloader_ignore_signals=False,

    strip=False,

    upx=True,

    upx_exclude=[],

    runtime_tmpdir=None,

    console=False,

    disable_windowed_traceback=False,

    argv_emulation=False,

    target_arch=None,

    codesign_identity=None,

    entitlements_file=None,

    icon='assets/icon.ico'

)

```



**使用spec文件打包**：

```bash

pyinstaller MyApp.spec

```



### 6.5 cx_Freeze打包

#### 6.5.1 创建setup.py



```python

import sys

from cx_Freeze import setup, Executable



build_exe_options = {

    "packages": ["os"],

    "excludes": ["tkinter"],

    "include_files": ["assets/"]

}



base = None

if sys.platform == "win32":

    base = "Win32GUI"



setup(

    name="MyApp",

    version="1.0",

    description="My Application",

    options={"build_exe": build_exe_options},

    executables=[Executable("main.py", base=base, icon="assets/icon.ico")]

)

```



#### 6.5.2 打包命令



```bash

python setup.py build

```



### 6.6 Nuitka打包

#### 6.6.1 基本打包命令



```bash

nuitka --standalone --onefile --enable-plugin=pyqt5 main.py

```



#### 6.6.2 常用参数



| 参数 | 说明 |

|------|------|

| `--standalone` | 独立打包 |

| `--onefile` | 单文件打包 |

| `--enable-plugin` | 启用插件（如pyqt5） |

| `--windows-disable-console` | 禁用控制台 |

| `--icon` | 指定图标 |

| `--include-data-dir` | 包含数据目录 |



#### 6.5.3 完整打包示例



```bash

nuitka ^

  --standalone ^

  --onefile ^

  --enable-plugin=pyqt5 ^

  --windows-disable-console ^

  --icon=assets/icon.ico ^

  --include-data-dir=assets=assets ^

  main.py

```



## 7. 打包优化



### 7.1 减小文件体积



1. **排除不必要的模块**：

   ```bash

   pyinstaller --exclude-module tkinter --exclude-module matplotlib main.py

   ```



2. **使用UPX压缩**：

   ```bash

   pyinstaller --upx-dir path/to/upx main.py

   ```



3. **选择合适的打包方式**：

   - 单文件：体积大，分发方便

   - 目录：体积小，启动快



### 7.2 提高启动速度



1. **使用目录打包**：目录打包比单文件打包启动更快

2. **减少依赖**：减少不必要的依赖库

3. **优化代码**：优化导入和初始化代码



### 7.3 资源文件处理



1. **使用相对路径**：使用`sys._MEIPASS`获取资源路径

   ```python

   import sys

   import os



   def resource_path(relative_path):

       if hasattr(sys, '_MEIPASS'):

           return os.path.join(sys._MEIPASS, relative_path)

       return os.path.join(os.path.abspath("."), relative_path)

   ```



2. **添加数据文件**：

   ```bash

   pyinstaller --add-data "assets;assets" main.py

   ```



## 8. 版本信息



### 8.1 添加版本信息



创建version_info.txt文件：

```txt

VSVersionInfo(

  ffi=FixedFileInfo(

    filevers=(1, 0, 0, 0),

    prodvers=(1, 0, 0, 0),

    mask=0x3f,

    flags=0x0,

    OS=0x40004,

    fileType=0x1,

    subtype=0x0,

    date=(0, 0)

  ),

  kids=[

    StringFileInfo(

      [

      StringTable(

        u'040904B0',

        [StringStruct(u'CompanyName', u'My Company'),

        StringStruct(u'FileDescription', u'My Application'),

        StringStruct(u'FileVersion', u'1.0.0.0'),

        StringStruct(u'InternalName', u'MyApp'),

        StringStruct(u'LegalCopyright', u'Copyright 2026'),

        StringStruct(u'OriginalFilename', u'MyApp.exe'),

        StringStruct(u'ProductName', u'My Application'),

        StringStruct(u'ProductVersion', u'1.0.0.0')])

      ]), 

    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])

  ]

)

```



### 8.2 使用版本信息



```bash

pyinstaller --version-file version_info.txt main.py

```



## 9. 测试验证



### 9.1 功能测试



1. 在干净环境中测试exe文件

2. 验证所有功能正常工作

3. 检查资源文件是否正确加载



### 9.2 兼容性测试



1. 在不同Windows版本上测试

2. 在不同硬件配置上测试

3. 测试是否有依赖冲突



### 9.3 性能测试



1. 测试启动时间

2. 测试内存占用

3. 测试运行性能



## 10. 发布流程



### 10.1 打包发布



1. **清理环境**：确保打包环境干净

2. **执行打包**：使用配置好的命令打包

3. **测试验证**：在干净环境中测试exe文件

4. **准备发布**：准备发布说明和安装指南



### 10.2 版本管理



遵循语义化版本规范：

```

MAJOR.MINOR.PATCH

```



- **MAJOR**：重大功能变更或架构调整

- **MINOR**：新增功能或改进

- **PATCH**：bug修复或小改进



### 10.3 发布说明



发布说明应包含：

- 版本号

- 新增功能

- 改进内容

- 修复问题

- 已知问题

- 系统要求



### 10.4 交付物清单



**最终交付物清单**：



| 编号 | 文件名 | 类型 | 说明 | 要求 |

|------|--------|------|------|------|

| 1 | `{项目名称}.exe` | 可执行文件 | 主程序可执行文件 | 必须包含，文件名应包含版本号 |

| 2 | `version_info.txt` | 配置文件 | 包含版本号、构建日期等信息 | 必须包含 |

| 3 | `RELEASE.md` | 文档 | 版本变更、新增功能等发布说明 | 必须包含 |

| 4 | `README.md` | 文档 | 快速上手指南和使用说明 | 必须包含 |

| 5 | `{项目名称}.spec` | 配置文件 | PyInstaller打包配置文件 | 建议包含 |



### 10.5 最终交付格式



**交付格式**：ZIP压缩包（完整归档版）

**命名规范**：`{系统名称}_V{版本号}_{日期}.zip`

**示例**：`Python自动化项目管理系统_V2.2.0_20260412.zip`

**归档位置**：项目根目录下的 `06_交付物打包/` 目录



**压缩包内部结构（本项目实际版 - V2.2.0更新）**：

```

{系统名称}_V{版本号}_{日期}.zip/

├── 01_可执行文件/              # 必须: exe + _internal/ + config/

│   ├── {程序名}.exe            # PyInstaller编译产物

│   ├── _internal/              # Python运行时依赖 (onedir模式)

│   └── config/                 # 4个JSON配置文件

├── 02_发布说明/                # 必须: 更新说明 + 交付清单

├── 02_配置文件/                # 可选: config副本

├── 03_测试文件/                # 可选: 测试脚本

├── 04_文档/                    # 可选: README等

├── 05_数据库/                  # 可选: db备份

├── data/                       # 必须: project_manager.db

├── *.md                        # 散落文档(README,已知问题等)

└── *.ps1                       # 散落脚本(如有)

```



> **注意**: 以上为Python项目管理工具(SW-2026-004)的实际目录结构。

> 不同项目的目录结构可能不同，应根据实际情况调整。



### 10.6 打包流程优化



1. **准备阶段**：

   - 确认项目功能正常

   - 整理依赖和资源文件

   - 创建版本信息文件

   - 编写发布说明和使用说明



2. **打包阶段**：

   - 使用 PyInstaller 单文件打包

   - 添加版本信息和图标

   - 测试打包结果



3. **验证阶段**：

   - 在干净环境测试

   - 验证功能完整性

   - 检查启动速度和内存占用



4. **交付阶段**：

   - 生成发布说明

   - 打包成带版本的压缩包

   - 验证压缩包内容完整

   - 确认所有必要文件都已包含



## 11. 完整交付物归档（V2.0.0新增）



### 11.1 归档目的



除了第10节的基础交付（仅exe+少量文件），本规范定义**完整交付物归档**标准，

用于项目的正式归档、审计追溯和知识沉淀。



### 11.2 归档触发条件



满足以下任一条件时应生成完整归档包：

- 项目里程碑节点（如V1.0发布、重大迭代完成）

- 外部交付（向客户/第三方交付完整项目）

- 内部归档（季度/年度项目资产盘点）

- 验收交付（项目验收时提交全部材料）



### 11.3 归档内容清单



| 编号 | 目录 | 必需内容 | 可选内容 |

|------|------|----------|----------|

| 1 | 01_源代码/ | src/ 全部源码 | .gitignore, .env.example |

| 2 | 02_可执行文件/ | .exe 文件 | version_info.txt |

| 3 | 03_配置文件/ | *.json 配置 | .env.example |

| 4 | 04_脚本与工具/ | build.py, requirements.txt | 迁移脚本, CI配置 |

| 5 | 05_数据库与数据/ | project_manager.db | 示例数据, SQL迁移脚本 |

| 6 | 06_测试报告/ | 综合测试报告 | 单元测试报告, 覆盖率报告 |

| 7 | 07_项目文档/ | 5大过程全部文档 | 设计草图, 会议纪要 |

| 8 | 08_交付清单/ | 交付清单md | 验收确认书 |



### 11.4 归档操作流程



1. **准备阶段**: 创建 `06_交付物打包/archive_temp/` 临时目录

2. **复制阶段**: 按上述8个目录逐一复制对应内容

3. **校验阶段**: 检查每个目录的内容完整性

4. **打包阶段**: 使用 Python zipfile.ZIP_DEFLATED 生成 ZIP

                    （详见第15.2.2节技术栈推荐，**禁止使用PowerShell Compress-Archive**）

5. **验证阶段**: 解压验证ZIP完整性

6. **清理阶段**: 删除 archive_temp 临时目录



### 11.5 命名规范



```

{系统名称}_V{版本号}_{日期}.zip

```



- **系统名称**: 产品化后的系统全称（如"Python自动化项目管理系统"）

- **版本号**: 语义化版本号，前缀V（如"V2.2.0"）

- **日期**: 打包日期，格式 YYYYMMDD（如"20260412"）



### 11.6 与旧版规范的兼容性



旧版命名 `{项目名称}_{版本号}_交付物.zip` 仍可用于简易交付场景。

完整归档场景必须使用新命名格式。



## 12. 最佳实践



1. **使用虚拟环境**：在干净的虚拟环境中打包，避免依赖冲突

2. **版本控制**：将spec文件和打包脚本纳入版本控制

3. **自动化打包**：使用CI/CD工具自动化打包流程

4. **测试充分**：在多个环境中充分测试

5. **文档完善**：提供详细的使用说明和故障排除指南

6. **定期更新**：定期更新打包工具和依赖库

7. **安全考虑**：对exe文件进行数字签名，提高可信度

8. **打包清单管理**：

   - 维护详细的打包清单，确保所有必要文件都已包含

   - 定期检查打包清单，确保与项目需求一致

   - 在打包前验证清单内容的完整性

9. **压缩包管理**：

   - 使用统一的命名规范，包含项目名称和版本号

   - 验证压缩包的完整性和正确性

   - 保存不同版本的压缩包，便于回滚和对比



## 13. 常见问题



### 12.1 打包后无法运行



**问题**：exe文件双击无法运行或立即退出



**解决方案**：

- 使用控制台模式查看错误信息

- 检查是否缺少依赖

- 使用`--debug`参数调试

- 检查资源文件路径是否正确



### 12.2 依赖缺失



**问题**：运行时提示缺少某个模块



**解决方案**：

- 使用`--hidden-import`参数添加隐藏导入

- 检查spec文件中的hiddenimports配置

- 使用`--collect-all`参数收集所有子模块



### 12.3 文件体积过大



**问题**：exe文件体积过大



**解决方案**：

- 排除不必要的模块

- 使用UPX压缩

- 考虑使用目录打包

- 优化依赖，减少不必要的库



### 12.4 资源文件找不到



**问题**：打包后找不到资源文件



**解决方案**：

- 使用`sys._MEIPASS`获取资源路径

- 确保使用`--add-data`参数添加资源文件

- 检查资源文件路径分隔符（Windows使用`;`，Linux使用`:`）



### 12.5 启动速度慢



**问题**：exe文件启动速度慢



**解决方案**：

- 使用目录打包代替单文件打包

- 减少依赖库

- 优化代码，减少启动时的初始化工作

- 使用Nuitka编译提高性能



### 12.6 压缩包相关问题



**问题1**：压缩包解压后缺少文件



**解决方案**：

- 检查打包清单，确保所有必要文件都已包含

- 验证压缩包的完整性

- 在打包过程中添加文件存在性检查



**问题2**：压缩包命名不规范



**解决方案**：

- 使用统一的命名规范：`{项目名称}_{版本号}_交付物.zip`

- 确保版本号与实际内容一致

- 在自动化脚本中实现标准化命名



**问题3**：压缩包过大



**解决方案**：

- 优化exe文件体积（排除不必要的模块、使用UPX压缩）

- 只包含必要的文件，避免冗余内容

- 考虑使用分卷压缩（如果文件特别大）



### 12.6 压缩包相关问题



**问题1**：压缩包解压后缺少文件



**解决方案**：

- 检查打包清单，确保所有必要文件都已包含

- 验证压缩包的完整性

- 在打包过程中添加文件存在性检查



**问题2**：压缩包命名不规范



**解决方案**：

- 使用统一的命名规范：`{项目名称}_{版本号}_交付物.zip`

- 确保版本号与实际内容一致

- 在自动化脚本中实现标准化命名



**问题3**：压缩包过大



**解决方案**：

- 优化exe文件体积（排除不必要的模块、使用UPX压缩）

- 只包含必要的文件，避免冗余内容

- 考虑使用分卷压缩（如果文件特别大）



### 12.7 AI辅助打包遗漏（真实案例）



> **严重程度**: 🔴 P0（致命）

> **发生时间**: 2026-04-15

> **涉及版本**: V2.4.1（豆包模型首次打包）



**问题描述**：

使用AI大语言模型（豆包）执行打包操作时，生成的zip压缩包仅21KB，

仅包含7个文档文件（README.md、更新说明、测试报告等），

**完全缺失核心程序目录**（01_可执行文件/ 约100MB，含exe + _internal/运行时依赖）。



**根因分析**：



| 因素 | 说明 |

|------|------|

| 路径理解偏差 | AI对中文路径（`06_交付物/01_可执行文件/`）解析不准确 |

| 文件遍历遗漏 | AI在执行文件复制/打包时跳过了大型二进制目录 |

| 无验证机制 | 打包后未执行完整性校验就直接输出结果 |

| 大小阈值未设 | 21KB的异常大小未触发告警 |



**影响范围**：

- 用户收到无法使用的空壳交付物

- 需要完全重新打包，浪费时间和信任

- 项目发布延迟



**解决方案（已实施并纳入本规范）**：



1. **强制两阶段流程**（见第16节）：先更新交付物目录 → 再打包

2. **自动化验证脚本**（见第17节）：打包后必须运行校验

3. **关键指标阈值**：文件数 < 50 或 zip < 1MB 时自动拦截

4. **人工复核**：AI生成的打包命令需人工确认后再执行



**预防措施**：

- ✅ 使用Python脚本替代PowerShell处理中文路径（避免编码问题）

- ✅ 打包前打印完整文件清单供确认

- ✅ 与历史版本（V2.4.0 = 107MB）对比大小差异

- ✅ 核心程序（exe + _internal）单独验证存在性



---



## 15. AI辅助打包风险控制（V2.1.0新增）



### 15.1 风险概述



当使用AI大语言模型（如豆包、ChatGPT、Claude等）辅助执行打包任务时，

存在以下特有风险：



| 风险类型 | 发生概率 | 影响程度 | 典型表现 |

|----------|:--------:|:--------:|----------|

| **核心文件遗漏** | 高 | 🔴 致命 | exe/_internal等大目录被跳过 |

| **路径解析错误** | 高 | 🟠 严重 | 中文路径编码问题导致文件找不到 |

| **命令执行失败** | 中 | 🟡 一般 | PowerShell语法错误（变量$被吞掉） |

| **编码混乱** | 中 | 🟡 一般 | UTF-8/BOM混用导致脚本无法运行 |

| **逻辑简化过度** | 低 | 🟠 严重 | AI"优化"掉关键步骤 |



### 15.2 安全使用指南



#### 15.2.1 必须遵守的原则



```

原则1: AI生成代码不直接执行 → 先审查再运行

原则2: 打包操作必须分阶段 → 先准备后打包

原则3: 结果必须自动验证 → 不依赖AI自我报告

原则4: 异常值必须告警 → 大小/数量偏离历史数据时拦截

```



#### 15.2.2 推荐的技术栈



| 操作类型 | 推荐工具 | 避免使用 | 原因 |

|----------|----------|----------|------|

| 文件复制/打包 | Python (os/shutil/zipfile) | PowerShell | 中文路径兼容性差 |

| 路径拼接 | `os.path.join()` | 字符串拼接 | 自动处理分隔符 |

| 编码处理 | UTF-8 BOM=False | 系统默认编码 | 跨平台一致 |

| 大文件操作 | 分块读取 | 一次性读入 | 内存溢出风险 |



#### 15.2.3 禁止行为清单



- ❌ **禁止**让AI直接在终端执行打包命令（应先生成脚本文件）

- ❌ **禁止**信任AI输出的"打包完成"信息（必须自行验证）

- ❌ **禁止**使用PowerShell处理含中文的复杂路径

- ❌ **禁止**跳过验证步骤直接发布AI生成的zip

- ❌ **禁止**在无历史数据对比的情况下首次打包新版本



### 15.3 应急预案



当发现AI打包结果异常时：



```python

# 立即执行的诊断步骤

1. 对比上一版本zip大小（差异 > 50% 则可疑）

2. 列出zip内顶层目录（应包含 01_可执行文件/）

3. 检查exe文件是否存在且 > 10MB

4. 统计总文件数（PyInstaller项目通常 > 500个）

5. 如有异常，立即删除错误zip，重新按第16节流程执行

```



---



## 16. 两阶段交付标准流程（V2.1.0新增）



### 16.1 流程定义



基于本次V2.4.1事件教训，定义**两阶段交付流程**为强制性标准：



```
┌─────────────────────────────────────────────────────────────┐
│                    两阶段交付标准流程                         │
├──────────────────────┬──────────────────────────────────────┤
│   阶段1: 更新交付物    │        阶段2: 打包归档               │
│   06_交付物/          │     06_交付物打包/                   │
├──────────────────────┼──────────────────────────────────────┤
│ ① 归档旧版交付物      │ ⑤ 归档旧 ZIP                        │
│    → archive/子目录   │    → archive/子目录                  │
│ ② 清理旧版本文档      │ ⑥ 创建临时归档目录                   │
│ ③ 复制最新exe+config │ ⑦ 复制06_交付物全部内容              │
│ ④ 复制发布说明文档    │ ⑧ 执行zip压缩                        │
│ ⑤ 创建README.md      │ ⑨ 运行强制验证脚本                   │
│                      │ ⑩ 输出验证报告                       │
└──────────────────────┴──────────────────────────────────────┘
         ↓                           ↓
   [阶段1完成标志]            [阶段2完成标志]
   交付物目录结构正确          zip通过所有检查项
   旧版已归档到archive/        旧ZIP已归档到archive/
```



### 16.2 目录职责分离



| 目录 | 用途 | 内容 | 更新频率 |

|------|------|------|----------|

| `06_交付物/` | **工作目录** | 实时维护的最新交付物 | 每次版本更新 |

| `06_交付物打包/` | **归档目录** | 历史版本的最终zip包 | 仅打包时写入 |



**关键规则**：

- `06_交付物/` 是**唯一的数据源**，打包时从此处读取

- `06_交付物打包/` 只存放**不可变的归档包**

- 两者物理隔离，避免误操作覆盖



### 16.3 阶段1详细步骤：更新交付物目录



```python

# _stage1_update_delivery.py (标准模板)

import os, shutil

from datetime import datetime



# === 配置区 ===

BASE_DIR = r"{项目根目录}"

DELIVERY_DIR = os.path.join(BASE_DIR, "06_交付物")

SRC_CODE_DIR = os.path.join(BASE_DIR, "03_主程序", "01_主程序核心代码")

RELEASE_NOTES_DIR = os.path.join(BASE_DIR, "02_发布说明")

VERSION = "V{x.y.z}"

DATE_STR = "{YYYYMMDD}"



# Step 1: 清理旧版本文档（保留01_可执行文件/不变）

old_docs = ["01_交付清单_DEL-V{旧版}.md", ...]

for f in old_docs:

    target = os.path.join(DELIVERY_DIR, f)

    if os.path.exists(target):

        os.remove(target)



# Step 2: 复制最新编译产物

src_exe = os.path.join(SRC_CODE_DIR, "dist", "{程序名}.exe")

dst_exe = os.path.join(DELIVERY_DIR, "01_可执行文件", "{程序名}.exe")

shutil.copy2(src_exe, dst_exe)

assert os.path.getsize(dst_exe) > 10 * 1024 * 1024, "exe太小，可能有问题"



# Step 3: 复制配置文件

config_files = ["app_config.json", "api_config.json", ...]

for cf in config_files:

    shutil.copy2(os.path.join(SRC_CODE_DIR, "config", cf),

                 os.path.join(DELIVERY_DIR, "01_可执行文件", "config", cf))



# Step 4: 复制发布文档 + README

# ... (详见模板)



print("[DONE] Stage 1 complete")

```



### 16.4 阶段2详细步骤：打包归档



```python

# _stage2_create_package.py (标准模板)

import zipfile

import os



DELIVERY_DIR = "{06_交付物完整路径}"

PACKAGE_DIR = "{06_交付物打包完整路径}"

VERSION = "V{x.y.z}"

DATE = "{YYYYMMDD}"

PACKAGE_NAME = f"Python自动化项目管理系统_{VERSION}_{DATE}"

ZIP_PATH = os.path.join(PACKAGE_DIR, f"{PACKAGE_NAME}.zip")



# Step 5-7: 创建zip（从06_交付物读取）

with zipfile.ZipFile(ZIP_PATH, 'w', zipfile.ZIP_DEFLATED) as zf:

    for root, dirs, files in os.walk(DELIVERY_DIR):

        for fn in files:

            fp = os.path.join(root, fn)

            arcname = os.path.join(PACKAGE_NAME,

                os.path.relpath(fp, DELIVERY_DIR)).replace('\\', '/')

            zf.write(fp, arcname)



# Step 8: 强制验证（见第17节）

run_verification(ZIP_PATH)



print(f"[DONE] Stage 2: {ZIP_PATH}")

```



### 16.5 流程检查清单



| 步骤 | 检查项 | 通过条件 | 执行人 |

|------|--------|----------|--------|

| 1.1 | 旧版本文档已清理 | V{旧版}*.md不存在 | AI/人工 |

| 1.2 | exe文件已更新 | 大小 > 10MB 且日期为今日 | 脚本 |

| 1.3 | 配置文件已同步 | 4个json文件均存在 | 脚本 |

| 1.4 | 发布文档已复制 | 6个文档文件齐全 | 脚本 |

| 1.5 | README已创建 | 包含版本号和日期 | 脚本 |

| 2.1 | 临时目录已创建 | 空目录存在 | 脚本 |

| 2.2 | 交付物已完整复制 | 文件数与06_交付物一致 | 脚本 |

| 2.3 | zip已生成 | 文件存在且 > 1MB | 脚本 |

| 2.4 | 验证脚本已通过 | 所有CHK项OK | 脚本 |

| 2.5 | 验证报告已输出 | 报告文件存在 | 脚本 |



---



## 17. 打包后强制验证机制（V2.1.0新增）



> **强制性要求**：每次打包完成后**必须**执行本节验证，未通过不得发布！



### 17.1 验证等级定义



| 等级 | 触发条件 | 处理方式 |

|------|----------|----------|

| 🟢 PASS | 全部检查通过 | 可以发布 |

| 🟠 WARN | 有非致命警告 | 记录日志，可发布（需确认） |

| 🔴 FAIL | 有致命错误 | **禁止发布**，立即修复 |



### 17.2 关键指标阈值



基于本项目历史数据（V2.2.0~V2.4.0）统计：



| 指标 | 最小阈值 | 正常范围 | 最大阈值 | 告警级别 |

|------|:--------:|----------|:--------:|----------|

| **ZIP文件大小** | 80 MB | 150-170 MB | 200 MB | <80MB或>200MB: 🔴 |

> (PyInstaller onedir模式含_internal依赖，实际约160MB。onefile模式可能更小)

| **解压后总文件数** | 500 | 900-1000 | 1500 | <500或>1500: 🔴 |

| **exe文件大小** | 10 MB | 55-65 MB | 100 MB | <10MB: 🔴 |

| **_internal/文件数** | 400 | 800-900 | 1200 | <400: 🔴 |

| **文档文件数** | 6 | 6-10 | 20 | <6: 🟠 |

| **配置文件数** | 4 | 4 | 4 | ≠4: 🔴 |



### 17.3 自动化验证脚本（标准实现）



```python

# _verify_package.py (必选附件)

import zipfile

import os

import sys



def verify_package(zip_path):

    """执行完整的打包验证"""

    results = {'pass': [], 'warn': [], 'fail': []}



    # 基础检查

    if not os.path.exists(zip_path):

        results['fail'].append(f"ZIP文件不存在: {zip_path}")

        return results



    with zipfile.ZipFile(zip_path, 'r') as zf:

        all_files = zf.namelist()



        # CHK-001: 总文件数

        total = len(all_files)

        if total < 500:

            results['fail'].append(f"[CHK-001] 文件数过少: {total} (<500)")

        elif total > 1500:

            results['fail'].append(f"[CHK-001] 文件数过多: {total} (>1500)")

        else:

            results['pass'].append(f"[CHK-001] 文件数正常: {total}")



        # CHK-002: ZIP大小

        zip_size = os.path.getsize(zip_path) / (1024*1024)

        if zip_size < 80:

            results['fail'].append(f"[CHK-002] ZIP过小: {zip_size:.1f}MB (<80MB)")

        elif zip_size > 200:

            results['fail'].append(f"[CHK-002] ZIP过大: {zip_size:.1f}MB (>200MB)")

        else:

            results['pass'].append(f"[CHK-002] ZIP大小正常: {zip_size:.1f}MB")



        # CHK-003: 核心程序存在性

        exe_files = [f for f in all_files if f.endswith('.exe') and '可执行文件' in f]

        if not exe_files:

            results['fail'].append("[CHK-003] 缺少exe文件！")

        else:

            exe_info = zf.getinfo(exe_files[0])

            exe_mb = exe_info.file_size / (1024*1024)

            if exe_mb < 10:

                results['fail'].append(f"[CHK-003] exe过小: {exe_mb:.1f}MB (<10MB)")

            else:

                results['pass'].append(f"[CHK-003] exe正常: {exe_mb:.1f}MB")



        # CHK-004: _internal依赖目录

        internal_count = len([f for f in all_files if '_internal/' in f])

        if internal_count < 400:

            results['fail'].append(f"[CHK-004] _internal文件过少: {internal_count}")

        else:

            results['pass'].append(f"[CHK-004] _internal正常: {internal_count}文件")



        # CHK-005: 关键文档

        key_docs = ['README.md', '交付清单', '更新说明', '测试报告', '已知问题']

        for doc in key_docs:

            found = [f for f in all_files if doc in f]

            if not found:

                results['warn'].append(f"[CHK-005] 缺少文档: {doc}")



        # CHK-006: 配置文件

        configs = ['app_config.json', 'api_config.json', 'database_config.json']

        for cfg in configs:

            found = [f for f in all_files if cfg in f and 'config' in f]

            if not found:

                results['fail'].append(f"[CHK-006] 缺少配置: {cfg}")



        # CHK-007: 目录结构完整性

        top_dirs = set()

        for f in all_files:

            parts = f.split('/')

            if len(parts) >= 2:

                top_dirs.add(parts[1])

        expected_dirs = {'01_可执行文件'}

        for d in expected_dirs:

            if d not in top_dirs:

                results['fail'].append(f"[CHK-007] 缺少顶级目录: {d}/")



    # 输出结果

    print("\n" + "="*60)

    print("PACKAGE VERIFICATION REPORT")

    print("="*60)

    print(f"\n[✓] PASS ({len(results['pass'])}):")

    for r in results['pass']: print(f"  {r}")

    print(f"\n[⚠] WARN ({len(results['warn'])}):")

    for r in results['warn']: print(f"  {r}")

    print(f"\n[✗] FAIL ({len(results['fail'])}):")

    for r in results['fail']: print(f"  {r}")



    status = "🔴 FAIL" if results['fail'] else ("🟠 WARN" if results['warn'] else "🟢 PASS")

    print(f"\n>>> Final Status: {status}")

    print("="*60)



    return results



if __name__ == "__main__":

    zip_file = sys.argv[1] if len(sys.argv) > 1 else "package.zip"

    results = verify_package(zip_file)

    sys.exit(1 if results['fail'] else 0)

```



### 17.4 验证报告格式



每次验证必须输出如下格式的报告：



```

============================================================

PACKAGE VERIFICATION REPORT - V2.4.1_20260415

============================================================



[✓] PASS (6):

  [CHK-001] 文件数正常: 945

  [CHK-002] ZIP大小正常: 102.2MB

  [CHK-003] exe正常: 58.35MB

  [CHK-004] _internal正常: 851文件

  [CHK-005] 配置文件齐全: 4/4

  [CHK-006] 顶级目录完整: 01_可执行文件/



[⚠] WARN (0):



[✗] FAIL (0):



>>> Final Status: 🟢 PASS

============================================================

Release APPROVED ✓

```



### 17.5 异常处理流程



```

检测到 🔴 FAIL

    ↓

立即停止发布流程

    ↓

分析失败原因（查看具体CHK编号）

    ↓

┌─ CHK-001/002 (大小/数量异常) → 可能是AI遗漏核心目录 → 按16节重新执行

├─ CHK-003 (exe缺失) → 检查dist/目录是否有编译产物 → 重新编译

├─ CHK-004 (_internal缺失) → PyInstaller打包不完整 → 重新执行pyinstaller

├─ CHK-005 (文档缺失) → 02_发布说明/目录文件不全 → 补充文档

└─ CHK-006/007 (结构异常) → 06_交付物/目录损坏 → 从git恢复

    ↓

修复后重新运行验证

    ↓

直到 🟢 PASS 或 🟠 WARN(确认)

    ↓

方可发布

```



---
## 18. 旧版归档机制（V2.4.0新增）

> **核心原则**：`06_交付物/` 和 `06_交付物打包/` 各自只保留一份最新"正式文件"，旧版本归档到 `archive/` 子目录，每个旧版附带归档说明。

### 18.1 目录结构

#### 06_交付物/ — 仅保留最新 + 旧版归档

```
06_交付物/
├── 01_可执行文件/                  # 最新正式 exe
│   ├── {程序名}.exe
│   └── _internal/                  # PyInstaller 运行时依赖
├── 02_发布说明/                    # 最新发布说明
├── README.md                       # 最新使用文档
├── CHANGELOG.md
└── archive/                        # 旧版归档
    ├── V1.0.0_20260716/
    │   ├── archive_info.md         # 归档说明
    │   ├── 01_可执行文件/
    │   ├── 02_发布说明/
    │   ├── README.md
    │   └── CHANGELOG.md
    └── V1.0.1_20260720/
        └── ...
```

#### 06_交付物打包/ — 仅保留最新 ZIP + 旧版归档

```
06_交付物打包/
├── {系统名称}_V{最新版本}_{日期}.zip  # 最新正式 ZIP
└── archive/                            # 旧版 ZIP 归档
    ├── archive_manifest.md             # 归档总清单
    └── {系统名称}_V{旧版本}_{日期}.zip
```

### 18.2 归档说明格式 (archive_info.md)

每次归档操作自动生成 `archive_info.md`，记录归档元数据：

```markdown
# 归档信息

| 字段 | 内容 |
|------|------|
| 版本号 | V1.0.0 |
| 归档日期 | 2026-07-18 |
| 原始文件大小 | 156.3 MB |
| 变更摘要 | 初始版本交付，包含基础项目管理功能 |
| 被替代版本 | V1.0.1 |
| 操作人 | auto-pm delivery build |
```

### 18.3 归档触发条件

| 触发场景 | 操作 | 归档内容 |
|----------|------|----------|
| `delivery build` | 构建新交付物前 | 将当前 `06_交付物/` 根目录内容 → `archive/V{旧版本}_{日期}/` |
| `delivery package` | 打包新 ZIP 前 | 将当前 `06_交付物打包/` 根目录 ZIP → `archive/` |
| `delivery build --auto-package` | 一键完成 | 先归档交付物，再归档旧 ZIP，最后生成新 ZIP |

### 18.4 保留策略

- 默认保留最近 **5** 个归档版本
- 通过 `auto-pm delivery archive clean --keep N` 清理旧归档
- 支持 `--dry-run` 预览模式

### 18.5 恢复机制

- `ArchiveManager.restore_delivery(version)` 可将指定归档版本恢复到 `06_交付物/` 根目录
- 恢复前会自动归档当前最新版本，确保不丢失数据

---

## 19. auto-pm delivery CLI（V2.4.0新增）

> **替代旧版 `scripts/build_delivery.py`**，将交付物管理工作流集成到 auto-pm CLI。

### 19.1 命令树

```
auto-pm delivery
├── build       # 构建交付物（编译 + 归档旧版 + 复制新版）
├── package     # 打包 ZIP（归档旧 ZIP + 创建新 ZIP + 验证）
├── archive     # 归档管理
│   ├── list    # 列出归档版本
│   └── clean   # 清理旧归档（保留最近 N 个）
└── status      # 查看当前交付物状态
```

### 19.2 命令参考

#### delivery build — 构建交付物

```bash
auto-pm delivery build --version V1.0.1 [--skip-pyinstaller] [--auto-package]
```

流程:
1. 归档旧版交付物 → `06_交付物/archive/`
2. 复制新 exe + _internal → `06_交付物/01_可执行文件/`
3. 复制发布文档 → `06_交付物/02_发布说明/`
4. 执行 D-checks 校验
5. `--auto-package` 自动触发打包

#### delivery package — 打包 ZIP

```bash
auto-pm delivery package --version V1.0.1 [--verify-only]
```

流程:
1. 归档旧 ZIP → `06_交付物打包/archive/`
2. 从 `06_交付物/` 创建新 ZIP（Python zipfile.ZIP_DEFLATED）
3. 执行 CHK-checks 验证
4. 输出验证报告

#### delivery archive list — 列出归档

```bash
auto-pm delivery archive list [--type delivery|package]
```

#### delivery archive clean — 清理旧归档

```bash
auto-pm delivery archive clean --keep 5 [--dry-run]
```

#### delivery status — 查看状态

```bash
auto-pm delivery status
```

### 19.3 一键工作流

```bash
# 构建 + 自动打包（推荐）
auto-pm delivery build --version V1.0.1 --skip-pyinstaller --auto-package

# 仅打包（已有交付物）
auto-pm delivery package --version V1.0.1

# 查看状态
auto-pm delivery status

# 查看归档历史
auto-pm delivery archive list
```

### 19.4 与旧脚本的关系

| 旧方式 | 新方式 |
|--------|--------|
| `python scripts/build_delivery.py --version V1.0.1` | `auto-pm delivery build --version V1.0.1` |
| 手动归档 | 自动归档到 `archive/` + 生成 `archive_info.md` |
| 无状态查询 | `auto-pm delivery status` |
| 无归档管理 | `auto-pm delivery archive list/clean` |

---

## 14. 版本详细变更说明

<a name="v230"></a>
### V2.3.0 版本详细变更
1. 新增 hatchling + pyproject.toml 打包模式（§6.1），作为推荐模式
2. PyInstaller exe 打包模式降级为可选方案（§6.4），仅用于桌面 GUI 应用
3. 新增模式选择指引（§6.0）
4. 新增术语定义：hatchling打包、开发模式、生产模式
5. 更新打包工具章节，hatchling 列为首选

[↑ 返回版本变更记录](#2-版本变更记录)

<a name="v210"></a>

### V2.1.0 版本详细变更

1. 新增第15节：AI辅助打包风险控制（基于2026-04-15 V2.4.1豆包打包遗漏事件）

2. 新增第16节：两阶段交付标准流程（06_交付物 → 06_交付物打包）

3. 新增第17节：打包后强制验证机制（7项CHK检查 + 阈值告警 + 自动化脚本）

4. 新增第12.7节：AI辅助打包遗漏真实案例分析

5. 更新第12节最佳实践，补充AI安全使用指南

6. 定义关键指标阈值（ZIP大小/文件数/exe大小等）作为强制校验标准

7. 提供标准Python脚本模板（替代PowerShell解决中文路径问题）



[↑ 返回版本变更记录](#2-版本变更记录)



<a name="v200"></a>

### V1.0.0 版本详细变更

1. 初始版本创建

2. 定义Python项目打包的基本规范

3. 提供详细的打包工具使用指南



[↑ 返回版本变更记录](#2-版本变更记录)



<a name="v110"></a>

### V1.1.0 版本详细变更

1. 更新为exe打包规范，移除PyPI相关内容

2. 优化打包流程和最佳实践

3. 完善常见问题和解决方案



[↑ 返回版本变更记录](#2-版本变更记录)



<a name="v120"></a>

### V1.2.0 版本详细变更

1. 简化为纯exe交付规范，无需安装步骤

2. 强调只交付exe文件，用户双击即可运行

3. 明确无需配置Python环境和安装依赖库

4. 突出绿色便携特性，可在任意Windows系统运行---



## 附录A: 标准构建脚本 build_delivery.py（V2.2.0新增，V2.4.0标记为兼容保留，V2.4.1标记为已退役）

> **⚠️ 已退役（V2.4.1，2026-11-14）**：本脚本不再使用，也不再维护。打包一律使用 `auto-pm delivery` CLI 命令，详见 §19。
> 本附录以下内容是退役前的原文，只作历史参考。
>
> **强制性要求**：所有打包操作必须通过 `auto-pm delivery` CLI 命令执行，**禁止临时手写脚本替代**。

>

> 本附录提供完整可运行的构建脚本源码，作为本规范的**代码级强制执行工具**。

> 脚本文件原位置（已退役，仅历史参考）：`03_主程序/01_主程序核心代码/scripts/build_delivery.py`



### A.1 脚本功能概览



```

历史用法（已退役，现用 auto-pm delivery build）: python build_delivery.py --version V{x.y.z} [--skip-build] [--verify-only]



流程 (6步):

  [1] 编译检查(PyInstaller) → [2] 更新06_交付物/

  → [3] 校验交付物完整性   → [4] 打包zip(Python zipfile)

  → [5] 校验zip(7项CHK)     → [6] 输出报告

```



### A.2 核心设计原则



| 原则 | 实现方式 |

|------|---------|

| **禁止PowerShell** | 全程使用Python标准库(os/shutil/zipfile) |

| **强制验证** | Step 3(6项D-check) + Step 5(7项CHK)，任何FAIL终止流程 |

| **阈值告警** | 文件数/大小偏离历史数据时自动拦截 |

| **可追溯** | 彩色终端报告 + Final Status明确PASS/FAIL |



### A.3 验证检查清单



**Step 3 — 交付物目录校验 (D-checks)**:



| 编号 | 检查项 | 阈值 | 失败处理 |

|:----:|--------|------|---------|

| D1 | exe存在且大小 | >50MB | ❌ 终止 |

| D2 | _internal文件数 | ≥400 (⚠️onefile可为0) | ⚠️ 继续 |

| D3 | config/json文件数 | =4 | ⚠️ 继续 |

| D4 | db存在 | 存在 | ⚠️ 继续 |

| D5 | 发布文档数 | ≥2 | ⚠️ 继续 |

| D6 | 总文件数 | ≥900 | ❌ 终止 |



**Step 5 — ZIP校验 (CHK-checks)**:



| 编号 | 检查项 | 最小 | 正常范围 | 最大 | 级别 |

|:----:|--------|:----:|----------|:----:|:----:|

| CHK-001 | 总文件数 | 500 | 940-960 | 1500 | 🔴 |

| CHK-002 | ZIP大小(MB) | 80 | 155-165 | 200 | 🔴 |

| CHK-003 | exe大小(MB) | 10 | 55-62 | 100 | 🔴 |

| CHK-004 | _internal文件数 | 0 | 850-900 | 1200 | ⚠️ |

| CHK-005 | 关键文档类 | 3 | 5-10 | 20 | ⚠️ |

| CHK-006 | 配置文件数 | 4 | 4 | 4 | 🔴 |

| CHK-007 | 一级目录完整性 | - | 含01_可执行文件 | - | 🔴 |



### A.4 输出报告示例



```

============================================================

🟢 DELIVERY BUILD REPORT - V2.4.3_20260415

============================================================

  Step 1 [编译]:  ✅ PASS

  Step 2 [更新]:  ✅ PASS

  Step 3 [校验]:  ✅ PASS (6/6)

  Step 4 [打包]:  ✅ PASS (951 files, 160.13 MB)

  Step 5 [验证]:  ✅ PASS (🟢 7/7 CHK)

>>> Final Status: 🟢 RELEASE APPROVED

============================================================

```



### A.5 脚本源码



> 完整源码原在项目路径 `scripts/build_delivery.py` (约350行)，脚本已退役；需要查看时到项目归档目录或 Git 历史中找。

> 本规范不在此嵌入完整源码以避免冗余，请以项目中实际文件为准。



---



## 15. 附录



### 15.1 参考资料

| 资料名称 | 版本 | 来源 |

|----------|------|------|

| PyInstaller官方文档 | [版本] | [来源] |

| cx_Freeze官方文档 | [版本] | [来源] |

| Nuitka官方文档 | [版本] | [来源] |

| PyOxidizer官方文档 | [版本] | [来源] |



### 15.2 联系方式

| 角色 | 姓名 | 邮箱 | 电话 |

|------|------|------|------|

| 文档负责人 | [姓名] | [邮箱] | [电话] |

| 技术负责人 | [姓名] | [邮箱] | [电话] |



---



**文档版本**: V2.4.1
**编制日期**: 2026-07-18
**编制人**: 技术团队
**审核人**: [审核人姓名]

