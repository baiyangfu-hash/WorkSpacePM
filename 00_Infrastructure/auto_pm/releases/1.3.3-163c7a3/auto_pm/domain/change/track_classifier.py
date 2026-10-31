"""PLC-HMI 概念映射：SFB 库函数（双轨变更通道分类器）

像 PLC 的 SFB/SFC 系统函数，负责自动评估变更请求的技术领域、业务性质、影响范围及变动文件，
判定该变更应该走 Quick Track（轻量通道）还是 Full Track（完整通道）。

--- 原始注释 ---

双轨变更通道分类器 (ChangeTrackClassifier)
设计参考: CHG 流程轻量化改造规范
- Quick Track (轻量通道): 适用于 DEF/OPT/DOCU/CFG 且范围为 LOCAL/MODULE 的局部修改
- Full Track (完整通道): 适用于 REQ/EMRG、跨系统/跨领域影响 SYSTEM/CROSS/SAFE、或触及核心技能/规则的架构变更
"""

from __future__ import annotations

import fnmatch
from collections.abc import Sequence
from enum import Enum
from pathlib import Path


class ChangeTrack(str, Enum):
    QUICK = "Quick"
    FULL = "Full"


# 敏感/核心路径模式（触及这些路径的变更强制走 Full Track）
SENSITIVE_PATH_PATTERNS: list[str] = [
    ".trae/skills/**",
    "auto_pm/constraint/definitions/**",
    "auto_pm/constraint/guard.py",
    "auto_pm/constraint/checker.py",
]


class ChangeTrackClassifier:
    """双轨变更通道分类器"""

    QUICK_NATURES: set[str] = {"DEF", "OPT", "DOCU", "CFG"}
    QUICK_SCOPES: set[str] = {"LOCAL", "MODULE"}

    @classmethod
    def classify(
        cls,
        domain: str = "",
        nature: str = "",
        scope: str | Sequence[str] = "",
        changed_files: Sequence[str | Path] | None = None,
    ) -> ChangeTrack:
        """评估变更请求并返回推荐的 ChangeTrack

        Args:
            domain: 技术领域 (ELEC/MECH/PLC/HMI/SCPT/DOCU/SAFE)
            nature: 业务性质 (REQ/DEF/OPT/CFG/EMRG)
            scope: 影响范围 (LOCAL/MODULE/SYSTEM/CROSS/SAFE)，可以是单个字符串或字符串列表
            changed_files: 修改的文件路径列表 (可选)

        Returns:
            ChangeTrack.QUICK 或 ChangeTrack.FULL
        """
        # 1. 规格性质检查: REQ (需求) 和 EMRG (紧急) 必须走 Full Track
        nature_upper = (nature or "").upper().strip()
        if nature_upper not in cls.QUICK_NATURES:
            return ChangeTrack.FULL

        # 2. 影响范围检查: 包含 SYSTEM/CROSS/SAFE 必须走 Full Track
        scopes: list[str] = []
        if isinstance(scope, str):
            scopes = [s.strip().upper() for s in scope.split(",") if s.strip()]
        else:
            scopes = [str(s).strip().upper() for s in scope if str(s).strip()]

        for s in scopes:
            if s not in cls.QUICK_SCOPES:
                return ChangeTrack.FULL

        # 3. 敏感路径检查: 若修改了技能规则或约束引擎定义，必须走 Full Track
        if changed_files:
            for file_path in changed_files:
                path_str = str(file_path).replace("\\", "/")
                for pattern in SENSITIVE_PATH_PATTERNS:
                    if fnmatch.fnmatch(path_str, pattern) or (
                        pattern.startswith(".trae/") and path_str.startswith(".trae/")
                    ):
                        return ChangeTrack.FULL

        # 4. 符合所有 Quick 条件，归为 Quick Track
        return ChangeTrack.QUICK
