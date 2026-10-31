"""PLC-HMI 概念映射：FB_Guard 功能块（文件守护（哈希快照/修改检测））

像 PLC 的 FB，封装"文件修改守护"的完整逻辑。
- 输入引脚：file_path（要守护的文件路径）
- 输出引脚：snapshot / verify_result（快照信息 / 验证结果）
- 内部状态：快照存储（~/.auto-pm/constraint/guard_snapshots.json）

--- 原始注释 ---

文件修改守护

通过 sha256 哈希快照检测文件是否被外部（非 Edit/Write 工具）修改。
提供 BOM 累积检测和自愈能力（CST-FILE-002）。

Usage:
    from auto_pm.constraint.guard import FileGuard

    guard = FileGuard(workspace_root)
    snap = guard.take_snapshot(file_path)
    # ... 使用 Edit/Write 工具修改文件 ...
    result = guard.verify_snapshot(file_path)
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from auto_pm.logging.audit import audit_log

BOM = b"\xef\xbb\xbf"

log = logging.getLogger(__name__)


class FileGuard:
    """文件修改守护：通过哈希快照检测外部修改

    核心职责：
    1. take_snapshot(): 文件操作前登记 sha256 快照
    2. verify_snapshot(): 文件操作后验证快照一致性
    3. check_encoding(): 文件编码完整性检查（BOM 累积）
    4. heal_bom(): 剥离多余 BOM（CST-FILE-002 auto_fix）
    """

    def __init__(self, workspace_root: Path | str) -> None:
        """
        Args:
            workspace_root: 工作空间根目录
        """
        self._workspace_root = Path(workspace_root)
        # 数据目录跟随工作空间（非用户 home），测试传 tmp_path 自动隔离，
        # 生产避免污染用户目录并符合本地化约束
        self._data_dir = self._workspace_root / ".auto-pm" / "constraint"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._snapshot_file = self._data_dir / "guard_snapshots.json"

    # ── 快照管理 ──

    def take_snapshot(self, file_path: Path | str) -> dict[str, Any]:
        """文件操作前登记快照

        Args:
            file_path: 要守护的文件路径

        Returns:
            包含 snapshot_id, sha256, size, mtime, bom_count 的字典

        Raises:
            FileNotFoundError: 文件不存在
        """
        fp = Path(file_path)
        if not fp.is_file():
            raise FileNotFoundError(f"文件不存在: {fp}")

        raw = fp.read_bytes()
        snap = {
            "snapshot_id": hashlib.sha256(
                f"{fp}:{datetime.now().isoformat()}".encode()
            ).hexdigest()[:12],
            "file_path": str(fp),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size": len(raw),
            "mtime": fp.stat().st_mtime,
            "bom_count": self._count_bom(raw),
            "taken_at": datetime.now().isoformat(),
        }
        self._save_snapshot(snap)
        audit_log(
            "constraint_guard",
            file_path=str(fp),
            snapshot_id=snap["snapshot_id"],
            sha256=str(snap["sha256"])[:16],
        )
        return snap

    def verify_snapshot(self, file_path: Path | str) -> dict[str, Any]:
        """文件操作后验证：检测文件是否被外部修改

        Args:
            file_path: 要验证的文件路径

        Returns:
            {
                "verified": bool,
                "snapshot_id": str | None,
                "hash_changed": bool,
                "size_delta": int,
                "bom_delta": int,
                "bom_accumulated": bool,
                "error": str | None,
                "message": str,
            }
        """
        fp = Path(file_path)
        if not fp.is_file():
            return {
                "verified": False,
                "error": "file_not_found",
                "message": f"文件不存在: {fp}",
                "hash_changed": True,
                "size_delta": 0,
                "bom_delta": 0,
                "bom_accumulated": False,
                "snapshot_id": None,
            }

        raw = fp.read_bytes()
        current_hash = hashlib.sha256(raw).hexdigest()
        current_bom = self._count_bom(raw)

        snap = self._find_latest_snapshot(fp)
        if snap is None:
            return {
                "verified": False,
                "error": "no_snapshot",
                "message": "未找到守护快照，文件可能被外部修改",
                "hash_changed": True,
                "size_delta": 0,
                "bom_delta": 0,
                "bom_accumulated": False,
                "snapshot_id": None,
            }

        hash_changed = current_hash != snap["sha256"]
        size_delta = len(raw) - snap["size"]
        bom_delta = current_bom - snap["bom_count"]
        bom_accumulated = current_bom > snap["bom_count"]

        result = {
            "verified": not hash_changed,
            "snapshot_id": snap["snapshot_id"],
            "hash_changed": hash_changed,
            "size_delta": size_delta,
            "bom_delta": bom_delta,
            "bom_accumulated": bom_accumulated,
            "error": None,
            "message": "文件完整" if not hash_changed else "文件已被修改",
        }

        if not result["verified"]:
            audit_log(
                "constraint_violation",
                constraint_id="CST-FILE-001",
                file_path=str(fp),
                hash_changed=hash_changed,
                size_delta=size_delta,
                bom_accumulated=bom_accumulated,
            )

        return result

    def has_snapshot(self, file_path: Path | str) -> bool:
        """检查文件是否有快照记录"""
        return self._find_latest_snapshot(Path(file_path)) is not None

    # ── BOM / 编码检测 ──

    @staticmethod
    def _count_bom(raw: bytes) -> int:
        """统计文件开头的连续 BOM 数量"""
        count = 0
        i = 0
        while i + 3 <= len(raw) and raw[i:i + 3] == BOM:
            count += 1
            i += 3
        return count

    def check_encoding(self, file_path: Path | str) -> dict[str, Any]:
        """检查文件编码完整性（CST-FILE-002）

        Args:
            file_path: 要检查的文件路径

        Returns:
            {
                "file_path": str,
                "bom_count": int,
                "bom_ok": bool,
                "has_null_byte": bool,
                "is_healthy": bool,
            }
        """
        fp = Path(file_path)
        if not fp.is_file():
            return {
                "file_path": str(fp),
                "bom_count": 0,
                "bom_ok": True,
                "has_null_byte": False,
                "is_healthy": True,
                "error": "file_not_found",
            }

        raw = fp.read_bytes()
        bom_count = self._count_bom(raw)
        has_null = b"\x00" in raw

        return {
            "file_path": str(fp),
            "bom_count": bom_count,
            "bom_ok": bom_count <= 1,
            "has_null_byte": has_null,
            "is_healthy": bom_count <= 1 and not has_null,
        }

    def heal_bom(self, file_path: Path | str) -> dict[str, Any]:
        """剥离多余 BOM（CST-FILE-002 auto_fix）

        Args:
            file_path: 要修复的文件路径

        Returns:
            {
                "healed": bool,
                "message": str,
                "bom_before": int,
                "bom_after": int,
                "bytes_removed": int,
            }
        """
        fp = Path(file_path)
        if not fp.is_file():
            return {"healed": False, "message": "文件不存在", "bom_count": 0}

        raw = fp.read_bytes()
        old_count = self._count_bom(raw)

        if old_count <= 1:
            return {"healed": False, "message": "无需修复，BOM 数量正常", "bom_count": old_count}

        # 剥离多余 BOM（保留 0 个，UTF-8 不应有 BOM）
        clean = raw.lstrip(BOM)
        fp.write_bytes(clean)
        new_count = self._count_bom(clean)

        audit_log(
            "constraint_heal",
            constraint_id="CST-FILE-002",
            file_path=str(fp),
            bom_before=old_count,
            bom_after=new_count,
        )

        return {
            "healed": True,
            "message": f"剥离 {old_count - new_count} 个多余 BOM（{old_count}→{new_count}）",
            "bom_before": old_count,
            "bom_after": new_count,
            "bytes_removed": len(raw) - len(clean),
        }

    # ── 内部方法 ──

    def _save_snapshot(self, snap: dict[str, Any]) -> None:
        """将快照追加到快照文件"""
        snapshots = self._load_all_snapshots()
        # 移除同一文件路径的旧快照（只保留最新）
        file_path = snap["file_path"]
        snapshots = [s for s in snapshots if s.get("file_path") != file_path]
        snapshots.append(snap)

        self._snapshot_file.write_text(
            json.dumps(snapshots, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def _load_all_snapshots(self) -> list[dict[str, Any]]:
        """加载所有快照"""
        if not self._snapshot_file.is_file():
            return []
        try:
            raw = self._snapshot_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, OSError) as e:
            log.warning("快照文件损坏，将重新初始化: %s", e)
        return []

    def _find_latest_snapshot(self, file_path: Path) -> dict[str, Any] | None:
        """查找指定文件的最新快照"""
        snapshots = self._load_all_snapshots()
        target = str(file_path)
        matching = [s for s in snapshots if s.get("file_path") == target]
        if not matching:
            return None
        # 按 taken_at 降序，取最新
        matching.sort(key=lambda s: s.get("taken_at", ""), reverse=True)
        return matching[0]
