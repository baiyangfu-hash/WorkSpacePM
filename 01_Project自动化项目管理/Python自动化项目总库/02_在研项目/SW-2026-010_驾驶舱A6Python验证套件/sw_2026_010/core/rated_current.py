"""三相电机额定电流计算"""

from __future__ import annotations

import math

_SQRT3 = math.sqrt(3.0)


def calculate_rated_current(
    power_kw: float,
    voltage_v: float,
    power_factor: float,
    efficiency: float,
) -> float:
    """按 I = P×1000 / (√3 × U × cosφ × η) 计算三相电机额定电流（A）。

    任一输入为 0 或负数时抛出 ValueError，消息为中文。
    """
    _require_positive("额定功率(kW)", power_kw)
    _require_positive("线电压(V)", voltage_v)
    _require_positive("功率因数", power_factor)
    _require_positive("效率", efficiency)
    return power_kw * 1000.0 / (_SQRT3 * voltage_v * power_factor * efficiency)


def _require_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name}必须大于 0，当前值为 {value}")
