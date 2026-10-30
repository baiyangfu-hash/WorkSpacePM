from __future__ import annotations

import json
from pathlib import Path

from auto_pm.domain.spec.core.registry import SpecInfo, SpecRegistry


class TestSpecRegistryLoad:
    def test_load_success(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        assert reg.load() is True

    def test_load_missing_file(self, workspace: Path) -> None:
        reg = SpecRegistry(workspace)
        assert reg.load() is False

    def test_load_invalid_json(self, registry_dir: Path, workspace: Path) -> None:
        (registry_dir / "spec_registry.json").write_text("{invalid json", encoding="utf-8")
        reg = SpecRegistry(workspace)
        assert reg.load() is False

    def test_load_empty_file(self, registry_dir: Path, workspace: Path) -> None:
        (registry_dir / "spec_registry.json").write_text("", encoding="utf-8")
        reg = SpecRegistry(workspace)
        assert reg.load() is False

    def test_load_specs_parsed(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        assert len(reg._specs) == 4
        assert "PM-2026-001" in reg._specs
        assert "PLC-2026-001" in reg._specs
        assert "CODE-210" in reg._specs
        assert "PM-2026-002" in reg._specs


class TestSpecRegistryGetSpec:
    def test_get_existing_spec(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        spec = reg.get_spec("PM-2026-001")
        assert spec is not None
        assert spec.title == "项目管理规范"
        assert spec.version == "V1.0.0"
        assert spec.domain == "pm"
        assert spec.lifecycle == "stable"

    def test_get_nonexistent_spec(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        assert reg.get_spec("NONEXISTENT-000") is None


class TestSpecRegistryListSpecs:
    def test_list_all(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        all_specs = reg.list_specs()
        assert len(all_specs) == 4

    def test_list_by_domain(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        pm_specs = reg.list_specs(domain="pm")
        assert len(pm_specs) == 2
        assert all(s.domain == "pm" for s in pm_specs)

    def test_list_by_lifecycle(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        stable = reg.list_specs(lifecycle="stable")
        assert len(stable) == 3
        deprecated = reg.list_specs(lifecycle="deprecated")
        assert len(deprecated) == 1


class TestSpecRegistryAddUpdate:
    def test_add_spec(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        new_spec = SpecInfo(
            spec_id="PY-2026-099",
            title="测试规范",
            number="PY-099",
            version="V1.0.0",
            domain="python",
            lifecycle="stable",
        )
        reg.add_spec("PY-2026-099", new_spec)
        spec = reg.get_spec("PY-2026-099")
        assert spec is not None
        assert spec.title == "测试规范"

    def test_update_spec(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        updated = SpecInfo(
            spec_id="PM-2026-001",
            title="更新后的项目管理规范",
            number="PM-001",
            version="V2.0.0",
            domain="pm",
            lifecycle="stable",
        )
        reg.update_spec("PM-2026-001", updated)
        spec = reg.get_spec("PM-2026-001")
        assert spec is not None
        assert spec.title == "更新后的项目管理规范"
        assert spec.version == "V2.0.0"

    def test_update_nonexistent_does_nothing(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        updated = SpecInfo(spec_id="NONEXISTENT", title="x")
        reg.update_spec("NONEXISTENT", updated)
        assert reg.get_spec("NONEXISTENT") is None


class TestSpecRegistrySave:
    def test_save_and_reload(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        new_spec = SpecInfo(
            spec_id="PY-2026-099",
            title="测试保存",
            number="PY-099",
            version="V1.0.0",
            domain="python",
            lifecycle="stable",
        )
        reg.add_spec("PY-2026-099", new_spec)
        reg.save()

        reg2 = SpecRegistry(populated_workspace)
        reg2.load()
        spec2 = reg2.get_spec("PY-2026-099")
        assert spec2 is not None
        assert spec2.title == "测试保存"

    def test_save_preserves_raw_fields(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        reg.save()

        reg2 = SpecRegistry(populated_workspace)
        reg2.load()
        assert "project_copies" in reg2.raw
        assert reg2.raw["version"] == "1.0.0"


class TestSpecRegistryDeprecated:
    def test_get_deprecated(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        deprecated = reg.get_deprecated()
        assert len(deprecated) == 1
        assert deprecated[0].spec_id == "PM-2026-002"


class TestSpecRegistryReplacementChain:
    def test_replacement_chain(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        chain = reg.get_replacement_chain("PM-2026-002")
        assert chain == ["PM-2026-002", "PM-2026-001"]

    def test_replacement_chain_no_replacement(self, populated_workspace: Path) -> None:
        reg = SpecRegistry(populated_workspace)
        reg.load()
        chain = reg.get_replacement_chain("PM-2026-001")
        assert chain == ["PM-2026-001"]


class TestSpecRegistryHandlesExtraFields:
    def test_load_with_extra_fields(self, registry_dir: Path, workspace: Path) -> None:
        data = {
            "version": "1.0.0",
            "specs": {
                "PM-2026-001": {
                    "title": "测试",
                    "number": "PM-001",
                    "canonical_path": "a.md",
                    "version": "V1.0.0",
                    "type_prefix": "PM",
                    "domain": "pm",
                    "lifecycle": "stable",
                    "sub_domain": "",
                    "tags": [],
                    "replaces": [],
                    "replaced_by": [],
                    "drift_warning": True,
                    "classification_issue": False,
                    "project_local_copy": "xxx",
                    "note": "额外字段",
                },
            },
        }
        (registry_dir / "spec_registry.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        reg = SpecRegistry(workspace)
        assert reg.load() is True
        spec = reg.get_spec("PM-2026-001")
        assert spec is not None
        assert spec.title == "测试"

    def test_load_with_string_list_fields(self, registry_dir: Path, workspace: Path) -> None:
        data = {
            "version": "1.0.0",
            "specs": {
                "PM-2026-001": {
                    "title": "测试",
                    "number": "PM-001",
                    "canonical_path": "a.md",
                    "version": "V1.0.0",
                    "type_prefix": "PM",
                    "domain": "pm",
                    "lifecycle": "stable",
                    "sub_domain": "",
                    "tags": "a, b, c",
                    "replaces": "x",
                    "replaced_by": "y",
                },
            },
        }
        (registry_dir / "spec_registry.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        reg = SpecRegistry(workspace)
        reg.load()
        spec = reg.get_spec("PM-2026-001")
        assert spec is not None
        assert spec.tags == ["a", "b", "c"]
        assert spec.replaces == ["x"]
        assert spec.replaced_by == ["y"]
