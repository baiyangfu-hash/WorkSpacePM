"""PLC-HMI 概念映射：HMI 画面数据结构（UI 事件定义（HMI 画面间通信的事件类型））

像 HMI 触摸屏的画面变量结构，定义 QML 画面能显示的数据格式。

--- 原始注释 ---

UI 统一事件契约"""

from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class UiEvent:
    """发往前端的统一事件对象"""
    event_name: str
    level: Literal["info", "warning", "error", "success"]
    source: str
    message: str
    payload: dict[str, Any] | None = None
