# 驾驶舱A6Python验证套件

> 项目编号: SW-2026-010
> 版本: {{ version }}
> 作者: {{ author }}

{{ description }}

## 安装

```bash
# 开发模式安装
pip install -e .

# 或使用 uv
uv pip install -e .
```

## 使用

```bash
# 查看帮助
sw-2026-010 --help

# 示例命令
sw-2026-010 hello
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 代码检查
ruff check .
mypy sw_2026_010

# 代码格式化
ruff format .

# 安装 pre-commit hooks
pre-commit install
```

## 项目结构

```
sw_2026_010/        # Python 包
├── cli/                   # Click CLI 入口
├── core/                  # 核心业务层
├── config/                # pydantic-settings 配置
├── logging/               # 统一日志
└── utils/                 # 通用工具
tests/                     # pytest 测试
```

## 规范

- 遵循 210_Python编程规范
- 遵循 211_Python代码审查规范
- 遵循 220_Python项目打包规范

## 许可证

MIT
