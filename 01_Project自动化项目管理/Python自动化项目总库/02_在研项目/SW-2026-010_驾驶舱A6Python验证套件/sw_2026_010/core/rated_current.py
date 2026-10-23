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

    额定功率与线电压必须大于 0；功率因数与效率必须大于 0 且不大于 1。
    任一校验失败时抛出 ValueError，消息为中文。
    """
    _require_positive("额定功率(kW)", power_kw)
    _require_positive("线电压(V)", voltage_v)
    _require_unit_interval("功率因数", power_factor)
    _require_unit_interval("效率", efficiency)
    return power_kw * 1000.0 / (_SQRT3 * voltage_v * power_factor * efficiency)


def _require_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name}必须大于 0，当前值为 {value}")


def _require_unit_interval(name: str, value: float) -> None:
    if value <= 0 or value > 1:
        raise ValueError(f"{name}必须大于 0 且不大于 1，当前值为 {value}")
