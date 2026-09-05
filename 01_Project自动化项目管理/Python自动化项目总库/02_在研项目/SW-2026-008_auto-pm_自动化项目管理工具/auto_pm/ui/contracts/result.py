"""PLC-HMI 概念映射：HMI 画面数据结构（统一结果类型（QueryResult/CommandResult 返回值包装））

像 HMI 触摸屏的画面变量结构，定义 QML 画面能显示的数据格式。

--- 原始注释 ---

Command / Query 基础结果封装"""

from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class CommandResult(Generic[T]):
    """命令/操作执行结果"""

    success: bool
    message: str
    payload: T | None = None
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class QueryResult(Generic[T]):
    """查询执行结果 (供需要明确标识失败的查询使用)"""

    success: bool
    message: str
    payload: T | None = None
    errors: list[str] = field(default_factory=list)
