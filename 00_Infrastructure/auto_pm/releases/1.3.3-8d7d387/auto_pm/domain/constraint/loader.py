"""PLC-HMI 概念映射：SFB 库函数（约束定义 YAML 加载器）

像 PLC 的 SFB/SFC 系统函数，负责从 YAML 文件加载约束定义。
被 FB 功能块（checker.py）调用，不直接暴露给 HMI 画面。

--- 原始注释 ---

约束定义加载器

从 auto_pm/constraint/definitions/ 目录加载 YAML 格式的约束定义文件，
解析为 Constraint 模型对象。

Usage:
    from auto_pm.constraint.loader import ConstraintLoader

    loader = ConstraintLoader(workspace_root)
    constraints = loader.load_all()
    file_cst = loader.load("file_encoding_integrity")
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

from auto_pm.constraint.models import (
    Constraint,
    ConstraintRule,
    ConstraintScope,
)

log = logging.getLogger(__name__)


class ConstraintLoadError(Exception):
    """约束定义加载失败"""


class ConstraintLoader:
    """YAML 约束定义加载器

    从 definitions/ 目录加载约束定义并解析为 Constraint 对象。
    """

    def __init__(self, workspace_root: Path | str) -> None:
        """
        Args:
            workspace_root: 工作空间根目录（用于定位 auto_pm/constraint/definitions/）
        """
        self._workspace_root = Path(workspace_root)
        self._definitions_dir = self._find_definitions_dir()

    def _find_definitions_dir(self) -> Path:
        """查找 definitions/ 目录：优先从包安装路径查找，降级到工作空间内搜索"""
        # 优先：从包安装路径查找（pip install 场景）
        pkg_dir = Path(__file__).resolve().parent / "definitions"
        if pkg_dir.is_dir():
            return pkg_dir

        # 降级：从工作空间内搜索（开发模式场景）
        # 使用 os.walk 兼容 Python 3.11（Path.walk 在 3.12+ 才可用）
        for root_str, dirs, _files in os.walk(str(self._workspace_root)):
            root = Path(root_str)
            if "definitions" in dirs and root.name == "constraint":
                return root / "definitions"

        raise ConstraintLoadError(
            f"未找到 constraint/definitions/ 目录，已搜索: {self._workspace_root}"
        )

    def list_definition_files(self) -> list[Path]:
        """列出所有 YAML 约束定义文件"""
        if not self._definitions_dir.is_dir():
            return []
        return sorted(self._definitions_dir.glob("*.yaml"))

    def load_all(self) -> list[Constraint]:
        """加载所有约束定义"""
        constraints: list[Constraint] = []
        for yaml_file in self.list_definition_files():
            try:
                cst = self._load_file(yaml_file)
                constraints.append(cst)
            except ConstraintLoadError as e:
                log.warning("跳过无效约束定义 %s: %s", yaml_file.name, e)
            except Exception:
                log.exception("加载约束定义 %s 时出错", yaml_file.name)
        return constraints

    def load(self, name: str) -> Constraint | None:
        """按名称加载单个约束定义（不含 .yaml 后缀）"""
        target = self._definitions_dir / f"{name}.yaml"
        if not target.is_file():
            return None
        try:
            return self._load_file(target)
        except ConstraintLoadError as e:
            log.warning("跳过无效约束定义 %s: %s", target.name, e)
            return None
        except Exception:
            log.exception("加载约束定义 %s 时出错", target.name)
            return None

    def _load_file(self, yaml_file: Path) -> Constraint:
        """从单个 YAML 文件加载并解析为 Constraint 对象"""
        if not yaml_file.is_file():
            raise ConstraintLoadError(f"文件不存在: {yaml_file}")

        try:
            with open(yaml_file, encoding="utf-8") as f:
                raw: dict[str, Any] = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConstraintLoadError(f"YAML 解析失败 {yaml_file.name}: {e}") from e
        except OSError as e:
            raise ConstraintLoadError(f"读取文件失败 {yaml_file.name}: {e}") from e

        if raw is None or not isinstance(raw, dict):
            raise ConstraintLoadError(f"{yaml_file.name}: 空文件或非字典内容")

        return self._parse_constraint(raw, yaml_file.name)

    def _parse_constraint(self, raw: dict[str, Any], source: str) -> Constraint:
        """解析 raw dict 为 Constraint 对象"""
        # 必填字段校验
        cst_id = raw.get("id")
        if not cst_id or not isinstance(cst_id, str):
            raise ConstraintLoadError(f"{source}: 缺少有效 id 字段")

        cst_name = raw.get("name")
        if not cst_name or not isinstance(cst_name, str):
            raise ConstraintLoadError(f"{source}: 缺少有效 name 字段")

        # 解析 scope
        scope_raw = raw.get("scope", {})
        if isinstance(scope_raw, dict):
            scope = ConstraintScope(
                patterns=list(scope_raw.get("patterns", [])),
                exclude=list(scope_raw.get("exclude", [])),
            )
        else:
            scope = ConstraintScope()

        # 解析 rules
        rules: list[ConstraintRule] = []
        for rule_raw in raw.get("rules", []):
            if isinstance(rule_raw, dict):
                rules.append(ConstraintRule(
                    type=rule_raw.get("type", ""),
                    description=rule_raw.get("description", ""),
                    check=rule_raw.get("check"),
                    pattern=rule_raw.get("pattern"),
                    cli_command=rule_raw.get("cli_command"),
                    max_count=rule_raw.get("max_count"),
                ))

        return Constraint(
            id=cst_id,
            name=cst_name,
            description=raw.get("description", ""),
            type=raw.get("type", "file_guard"),
            severity=raw.get("severity", "error"),
            scope=scope,
            rules=rules,
            auto_fix=raw.get("auto_fix", False),
            heal_command=raw.get("heal_command", ""),
        )
