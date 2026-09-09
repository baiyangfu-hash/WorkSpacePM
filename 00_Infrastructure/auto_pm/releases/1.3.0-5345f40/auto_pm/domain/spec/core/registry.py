"""PLC-HMI 概念映射：SFB 库函数（规范注册表（规范元数据存储/查询））

像 PLC 的 SFB/SFC 系统函数，被 FB 功能块（application/*_facade.py）调用，
不直接暴露给 HMI 画面。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SpecInfo:
    spec_id: str = ""
    title: str = ""
    number: str = ""
    canonical_path: str = ""
    version: str = ""
    type_prefix: str = ""
    domain: str = ""
    lifecycle: str = "active"
    sub_domain: str = ""
    tags: list[str] = field(default_factory=list)
    replaces: list[str] = field(default_factory=list)
    replaced_by: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)


class SpecRegistry:
    def __init__(self, workspace: Path, registry_path: str | None = None) -> None:
        self.workspace = workspace
        self._registry_path = registry_path
        self._specs: dict[str, SpecInfo] = {}
        self._raw: dict[str, Any] = {}

    @property
    def path(self) -> Path:
        if self._registry_path is not None:
            return self.workspace / self._registry_path
        from .config import DEFAULT_REGISTRY_PATH
        return self.workspace / DEFAULT_REGISTRY_PATH

    @property
    def raw(self) -> dict[str, Any]:
        return self._raw

    def load(self) -> bool:
        if not self.path.exists():
            return False
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self._raw = data
            self._specs = {}
            specs_data = data.get("specs", {})
            for spec_id, info in specs_data.items():
                if not isinstance(info, dict):
                    continue
                clean = dict(info)
                for key in ("drift_warning", "classification_issue", "project_local_copy", "project", "note"):
                    clean.pop(key, None)
                for list_key in ("replaces", "replaced_by", "tags", "aliases"):
                    if list_key in clean and isinstance(clean[list_key], str):
                        clean[list_key] = [s.strip() for s in clean[list_key].split(",") if s.strip()]
                if "spec_id" not in clean:
                    clean["spec_id"] = spec_id
                self._specs[spec_id] = SpecInfo(
                    **{k: v for k, v in clean.items() if k in SpecInfo.__dataclass_fields__}
                )
            return True
        except (json.JSONDecodeError, OSError, TypeError):
            return False

    def save(self) -> None:
        self._sync_specs_to_raw()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._raw, f, ensure_ascii=False, indent=2)

    def _sync_specs_to_raw(self) -> None:
        specs_raw = self._raw.setdefault("specs", {})
        for spec_id, spec_info in self._specs.items():
            specs_raw[spec_id] = asdict(spec_info)

    def get_spec(self, spec_id: str) -> SpecInfo | None:
        return self._specs.get(spec_id)

    def list_specs(
        self,
        domain: str | None = None,
        lifecycle: str | None = None,
    ) -> list[SpecInfo]:
        results = list(self._specs.values())
        if domain is not None:
            results = [s for s in results if s.domain == domain]
        if lifecycle is not None:
            results = [s for s in results if s.lifecycle == lifecycle]
        return results

    def add_spec(self, spec_id: str, info: SpecInfo) -> None:
        info.spec_id = spec_id
        self._specs[spec_id] = info

    def update_spec(self, spec_id: str, info: SpecInfo) -> None:
        if spec_id in self._specs:
            info.spec_id = spec_id
            self._specs[spec_id] = info

    def get_deprecated(self) -> list[SpecInfo]:
        return [s for s in self._specs.values() if s.lifecycle in ("deprecated", "archived")]

    def get_replacement_chain(self, spec_id: str) -> list[str]:
        chain: list[str] = []
        current_ids = [spec_id]
        visited: set[str] = set()
        while current_ids:
            next_ids = []
            for cid in current_ids:
                if cid in visited:
                    continue
                visited.add(cid)
                chain.append(cid)
                spec = self._specs.get(cid)
                if spec and spec.replaced_by:
                    next_ids.extend(spec.replaced_by)
            current_ids = next_ids
        return chain
