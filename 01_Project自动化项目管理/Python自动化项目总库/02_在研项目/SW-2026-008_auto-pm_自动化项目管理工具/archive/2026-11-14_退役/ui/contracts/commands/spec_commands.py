"""PLC-HMI 概念映射：HMI 画面数据结构（规范命令定义（检查/索引/Frontmatter 的参数））

像 HMI 触摸屏的画面变量结构，定义 QML 画面能显示的数据格式。

--- 原始注释 ---

Spec 相关 Command 定义"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RunSpecCheckCommand:
    target_path: str
    auto_fix: bool
    scope: str
