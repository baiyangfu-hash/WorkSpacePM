# python-tool Copier 模板

用于生成符合 210 编程规范的 Python CLI 工具项目骨架。

## 使用方式

```bash
# 在工作空间根目录执行
copier copy path/to/templates/python-tool ./目标目录
```

Copier 会依次询问以下问题：

| 字段 | 说明 | 示例 | 默认值 |
|------|------|------|--------|
| `project_id` | 项目编号（字母-年份-序号） | `SW-2026-009` | 无（必填） |
| `project_name` | 项目名称 | `数据分析工具` | 无（必填） |
| `package_name` | Python 包名（小写+下划线） | `data_tool` | 由 project_name 派生 |
| `cli_command` | CLI 命令名 | `data-tool` | 由 package_name 派生 |
| `description` | 项目描述 | `数据分析工具` | 同 project_name |
| `author` | 作者名 | `fubai` | `fubai` |
| `version` | 初始版本 | `0.1.0` | `0.1.0` |

## 生成的项目结构

```
<project_id>_<project_name>/
├── <package_name>/              # Python 包（flat layout）
│   ├── cli/                     # Click CLI 入口
│   ├── core/                    # 核心业务层
│   ├── config/                  # pydantic-settings 配置
│   ├── logging/                 # 统一日志
│   └── utils/                   # 通用工具
├── tests/                       # pytest 测试
├── 00_项目基础信息/              # PRD 等文档
├── pyproject.toml               # hatchling 构建 + 标准化依赖
├── .ruff.toml                   # 210 规范对齐
├── .pre-commit-config.yaml      # ruff + ruff-format
├── PM_SESSION_<project_id>.md   # PM 会话骨架
└── .copier-answers.yml          # Copier 答案记录
```

## 设计原则

1. **对齐 auto-pm 实践**：模板生成的项目与 auto-pm 自身结构一致
2. **flat layout**：包目录直接在根目录，pythonpath 配置简单
3. **开箱即用**：生成的项目立即可 `pytest` + `ruff check` + `mypy` 通过
4. **PM_SESSION 骨架**：生成项目即含 PM_SESSION，支持 pm-workflow 技能立即接入

## 增量更新

模板升级后，老项目可通过 `copier update` 增量同步：

```bash
cd <已生成的项目>
copier update
```

冲突时 Copier 会提示用户选择保留版本。
