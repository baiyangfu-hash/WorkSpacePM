"""
间隔重复算法引擎 (FSRS-4 简化版)
基于 py-fsrs 的简化实现，不依赖外部库
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from typing import TypedDict


class FSRSParameters(TypedDict):
    w: list[float]
    request_retention: float
    maximum_interval: int


class FSRSState:
    """FSRS 单词状态"""
    def __init__(self) -> None:
        self.due = datetime.now().isoformat()
        self.stability = 0.0      # 记忆稳定性
        self.difficulty = 0.0     # 难度
        self.elapsed_days = 0     # 已过去天数
        self.scheduled_days = 0   # 计划间隔天数
        self.reps = 0             # 重复次数
        self.lapses = 0           # 遗忘次数
        self.state = 0            # 0=新词, 1=学习中, 2=复习, 3=重新学习

    def to_json(self) -> str:
        return json.dumps(self.__dict__)

    @classmethod
    def from_json(cls, json_str: str | None) -> FSRSState:
        if not json_str:
            return cls()
        obj = cls()
        data: object = json.loads(json_str)
        if not isinstance(data, dict):
            return obj
        for key in ("due",):
            value = data.get(key)
            if isinstance(value, str):
                setattr(obj, key, value)
        for key in ("stability", "difficulty"):
            value = data.get(key)
            if isinstance(value, (int, float)):
                setattr(obj, key, float(value))
        for key in ("elapsed_days", "scheduled_days", "reps", "lapses", "state"):
            value = data.get(key)
            if isinstance(value, int):
                setattr(obj, key, value)
        return obj

class FSRSEngine:
    """FSRS 间隔重复引擎"""

    # FSRS-4 默认参数
    PARAMS: FSRSParameters = {
        'w': [0.4, 0.6, 2.4, 5.8, 4.93, 0.94, 0.86, 0.01, 1.49, 0.14, 0.94, 2.18, 0.05, 0.34, 1.26, 0.29, 2.61],
        'request_retention': 0.9,
        'maximum_interval': 365,
    }

    # 评分: 1=重来, 2=困难, 3=一般, 4=简单
    RATING_MAP = {
        'again': 1,
        'hard': 2,
        'good': 3,
        'easy': 4
    }

    def __init__(self) -> None:
        self.w = self.PARAMS['w']
        self.request_retention = self.PARAMS['request_retention']
        self.maximum_interval = self.PARAMS['maximum_interval']

    def init_difficulty(self, rating: int) -> float:
        """初始化难度"""
        return self.w[4] - math.exp(self.w[5] * (rating - 1)) + 1

    def init_stability(self, rating: int) -> float:
        """初始化稳定性"""
        # w[0]=again, w[1]=hard, w[2]=good, w[3]=easy
        # 确保 easy > good > hard > again
        base = max(0.1, self.w[rating - 1])
        if rating == 4:  # easy: 在 good 基础上增加 50%
            good_base = max(0.1, self.w[2])
            return good_base * 1.5
        return base

    def next_difficulty(self, difficulty: float, rating: int) -> float:
        """计算下一个难度"""
        return difficulty - self.w[6] * (rating - 3)

    def next_stability(self, state: int, stability: float, difficulty: float, rating: int) -> float:
        """计算下一个稳定性"""
        stability = max(0.1, float(stability))
        difficulty = max(1.0, min(10.0, float(difficulty)))
        if rating == 1:  # 重来
            return self.w[11] * math.pow(difficulty, -self.w[12]) * (math.pow(stability + 1, self.w[13]) - 1) * math.exp((1 - rating) * self.w[14])

        return stability * (1 + math.exp(self.w[8]) * (11 - difficulty) * math.pow(stability, -self.w[9]) * (math.exp((1 - rating) * self.w[10]) - 1))

    def next_interval(self, stability: float) -> int:
        """计算下一个间隔天数"""
        interval = stability / math.log(self.request_retention) * math.log(0.9)
        interval = max(1, min(round(interval), self.maximum_interval))
        return interval

    def review(self, state: FSRSState, rating: str) -> tuple[FSRSState, datetime]:
        """
        执行一次复习评分
        state: FSRSState 对象
        rating: 'again'|'hard'|'good'|'easy'
        返回: (new_state, due_date)
        """
        rating_val = self.RATING_MAP.get(rating, 3)

        new_state = FSRSState()
        new_state.reps = state.reps + 1
        new_state.lapses = state.lapses
        new_state.elapsed_days = state.scheduled_days

        if state.state == 0:  # 新词
            new_state.stability = self.init_stability(rating_val)
            new_state.difficulty = self.init_difficulty(rating_val)
            new_state.state = 1 if rating_val > 1 else 0
            # 根据评分设置不同的初始间隔
            if rating_val == 1:
                new_state.scheduled_days = 0
            elif rating_val == 2:
                new_state.scheduled_days = 1
            elif rating_val == 3:
                new_state.scheduled_days = 3
            else:  # easy
                new_state.scheduled_days = 5

        elif state.state == 1 or state.state == 3:  # 学习中或重新学习
            if rating_val == 1:  # 重来
                new_state.stability = self.init_stability(rating_val)
                new_state.difficulty = self.next_difficulty(state.difficulty, rating_val)
                new_state.state = 3
                new_state.lapses += 1
                new_state.scheduled_days = 1
            else:
                new_state.stability = self.next_stability(state.state, state.stability, state.difficulty, rating_val)
                new_state.difficulty = self.next_difficulty(state.difficulty, rating_val)
                new_state.state = 2
                new_state.scheduled_days = self.next_interval(new_state.stability)

        else:  # 复习状态
            if rating_val == 1:  # 重来
                new_state.stability = self.init_stability(rating_val)
                new_state.difficulty = self.next_difficulty(state.difficulty, rating_val)
                new_state.state = 3
                new_state.lapses += 1
                new_state.scheduled_days = 1
            else:
                new_state.stability = self.next_stability(state.state, state.stability, state.difficulty, rating_val)
                new_state.difficulty = self.next_difficulty(state.difficulty, rating_val)
                new_state.state = 2
                new_state.scheduled_days = self.next_interval(new_state.stability)

        # 计算到期时间
        due = datetime.now() + timedelta(days=new_state.scheduled_days)
        new_state.due = due.isoformat()

        return new_state, due

    def get_rating_intervals(self, state: FSRSState) -> dict[str, int]:
        """
        获取各个评分对应的预计间隔天数
        用于显示在按钮上
        """
        intervals: dict[str, int] = {}
        for rating_name in self.RATING_MAP:
            temp_state = FSRSState()
            temp_state.__dict__.update(state.__dict__)
            temp_state.state = state.state
            new_state, _ = self.review(temp_state, rating_name)
            intervals[rating_name] = new_state.scheduled_days
        return intervals
