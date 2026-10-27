"""Role pack check (role-pack card 1): the cockpit keeps the job descriptions, agents only borrow them.

A role pack is a directory under ``auto_pm/roles/<role-id>/``::

    SKILL.md    job description for people and for tools that load skills (Trae, Cursor)
    role.json   machine config: required specs, allowed commands, gates, receipt fields
    refs/       domain notes copied as they were; only needed when the old skill had them

``roles/shared/refs`` holds the common contract that every pack links to with ``../shared/refs``.

The check is read-only and never needs the ledger, so it also runs offline.  Each finding carries a
code so a card or an audit can quote it:

* RP-001 a required file is missing
* RP-002 role.json is not valid or lacks a key
* RP-003 role id is not the directory name or uses a character that breaks Windows paths
* RP-004 SKILL.md front matter name differs from the id, or has no description
* RP-005 a legacy name is claimed by two packs
* RP-006 a required spec id is not in spec_registry.json (UNVERIFIED when the registry is absent)
* RP-007 a relative ``.md`` pointer inside a pack does not resolve
* RP-008 the pack differs from the old skill it replaces, or the old skill cannot be found
  (only ``\"retired\": true`` in role.json skips it; no workspace gives UNVERIFIED)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import auto_pm

ROLE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
SHARED_DIR = "shared"
REQUIRED_KEYS = (
    "schema_version",
    "id",
    "title",
    "kind",
    "legacy_names",
    "required_specs",
    "allowed_commands",
    "gates",
    "receipt_fields",
    "owned_paths_patterns",
    "enforcement",
)
OLD_SKILLS_RELPATH = ".trae/skills"
LEGACY_MODES = frozenset({"body-equal", "section-contained"})
SPEC_REGISTRY_RELPATH = "00_Obsidian_Base全局规范文件仓库/spec_registry.json"
# Only pointers that start like a relative path are followed; bare file names in prose are not.
MD_POINTER = re.compile(r"(?:\.\./|\./|refs/)[\w./\-]+\.md")

FAIL = "FAIL"
UNVERIFIED = "UNVERIFIED"


@dataclass(frozen=True)
class RoleFinding:
    """One problem found in one role pack."""

    code: str
    level: str
    role: str
    message: str


@dataclass
class RoleCheckResult:
    """All findings of one check run; ``ok`` means no FAIL (UNVERIFIED does not fail the run)."""

    roles: list[str] = field(default_factory=list)
    findings: list[RoleFinding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(item.level == FAIL for item in self.findings)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "roles": self.roles,
            "findings": [vars(item) for item in self.findings],
        }


def default_roles_dir() -> Path:
    """Directory that holds the packs shipped inside the cockpit package."""
    return Path(auto_pm.__file__).resolve().parent / "roles"


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Return (front matter key/value pairs, body) of a SKILL.md; no front matter gives ({}, text)."""
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return {}, normalized
    end = normalized.find("\n---\n", 4)
    if end == -1:
        return {}, normalized
    meta: dict[str, str] = {}
    for line in normalized[4:end].split("\n"):
        key, sep, value = line.partition(":")
        if sep:
            meta[key.strip()] = value.strip().strip('"')
    return meta, normalized[end + 5 :]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


class RolePackService:
    """Check the role packs of one cockpit against themselves, the spec registry and the old skills."""

    def __init__(self, roles_dir: Path | None = None, workspace_root: Path | None = None) -> None:
        self.roles_dir = Path(roles_dir) if roles_dir else default_roles_dir()
        self.workspace_root = Path(workspace_root) if workspace_root else None

    def role_dirs(self) -> list[Path]:
        """Pack directories, sorted by name; ``shared`` is not a role."""
        if not self.roles_dir.is_dir():
            return []
        return sorted(
            child for child in self.roles_dir.iterdir() if child.is_dir() and child.name != SHARED_DIR
        )

    def check(self) -> RoleCheckResult:
        """Run every check on every pack and collect the findings."""
        result = RoleCheckResult()
        spec_ids = self._load_spec_ids()
        claimed: dict[str, str] = {}
        for pack in self.role_dirs():
            result.roles.append(pack.name)
            config = self._check_files_and_config(pack, result)
            if config is None:
                continue
            self._check_identity(pack, config, result)
            self._check_legacy_names(pack, config, claimed, result)
            self._check_specs(pack, config, spec_ids, result)
            self._check_pointers(pack, result)
            self._check_equivalence(pack, config, result)
        return result

    def _add(self, result: RoleCheckResult, code: str, role: str, message: str, level: str = FAIL) -> None:
        result.findings.append(RoleFinding(code=code, level=level, role=role, message=message))

    def _check_files_and_config(self, pack: Path, result: RoleCheckResult) -> dict[str, Any] | None:
        """RP-001 and RP-002: files exist, role.json parses and has every key."""
        missing = [name for name in ("SKILL.md", "role.json") if not (pack / name).is_file()]
        for name in missing:
            self._add(result, "RP-001", pack.name, f"缺少 {name}")
        if "role.json" in missing:
            return None
        try:
            config = json.loads(_read(pack / "role.json"))
        except json.JSONDecodeError as error:
            self._add(result, "RP-002", pack.name, f"role.json 不是合法 JSON：{error}")
            return None
        if not isinstance(config, dict):
            self._add(result, "RP-002", pack.name, "role.json 顶层必须是对象")
            return None
        for key in REQUIRED_KEYS:
            if key not in config:
                self._add(result, "RP-002", pack.name, f"role.json 缺少键 {key}")
        return config

    def _check_identity(self, pack: Path, config: dict[str, Any], result: RoleCheckResult) -> None:
        """RP-003 and RP-004: id, directory name and SKILL.md front matter agree."""
        role_id = str(config.get("id", ""))
        if role_id != pack.name:
            self._add(result, "RP-003", pack.name, f"role.json 的 id 是 {role_id!r}，与目录名不一致")
        if not ROLE_ID_PATTERN.match(pack.name):
            self._add(result, "RP-003", pack.name, "角色号只能用小写字母、数字和连字符，不能含冒号（Windows 目录名与 AUTO_PM_AGENT 分段都不允许）")
        if not (pack / "SKILL.md").is_file():
            return
        meta, _ = split_front_matter(_read(pack / "SKILL.md"))
        if meta.get("name") != pack.name:
            self._add(result, "RP-004", pack.name, f"SKILL.md 的 name 是 {meta.get('name')!r}，应为 {pack.name}")
        if not meta.get("description"):
            self._add(result, "RP-004", pack.name, "SKILL.md 缺少 description")

    def _check_legacy_names(
        self, pack: Path, config: dict[str, Any], claimed: dict[str, str], result: RoleCheckResult
    ) -> None:
        """RP-005: an old skill name maps to exactly one role (the alias table card 2 will read)."""
        for name in config.get("legacy_names", []):
            if name in claimed:
                self._add(result, "RP-005", pack.name, f"旧名 {name} 已被 {claimed[name]} 认领")
            else:
                claimed[name] = pack.name

    def _load_spec_ids(self) -> set[str] | None:
        """Spec ids from the registry, or None when the workspace or the registry is not there."""
        if self.workspace_root is None:
            return None
        registry = self.workspace_root / SPEC_REGISTRY_RELPATH
        if not registry.is_file():
            return None
        try:
            specs = json.loads(_read(registry)).get("specs", {})
        except (json.JSONDecodeError, AttributeError):
            return None
        return set(specs) if isinstance(specs, dict) else None

    def _check_specs(
        self, pack: Path, config: dict[str, Any], spec_ids: set[str] | None, result: RoleCheckResult
    ) -> None:
        """RP-006: every spec the pack tells the agent to read exists in the registry."""
        required = config.get("required_specs", [])
        if spec_ids is None:
            if required:
                self._add(result, "RP-006", pack.name, "找不到 spec_registry.json，规范编号未核对", UNVERIFIED)
            return
        for spec_id in required:
            if spec_id not in spec_ids:
                self._add(result, "RP-006", pack.name, f"规范 {spec_id} 不在 spec_registry.json 里")

    def _check_pointers(self, pack: Path, result: RoleCheckResult) -> None:
        """RP-007: relative ``.md`` pointers in SKILL.md and refs/ resolve and stay inside roles/."""
        sources = [pack / "SKILL.md", *sorted((pack / "refs").glob("*.md"))]
        roles_root = self.roles_dir.resolve()
        for source in sources:
            if not source.is_file():
                continue
            for pointer in sorted(set(MD_POINTER.findall(_read(source)))):
                # ``refs/x.md`` is written from the pack root even inside refs/ (the old INDEX.md does so).
                base = pack if pointer.startswith("refs/") else source.parent
                target = (base / pointer).resolve()
                if not target.is_file() or roles_root not in target.parents:
                    self._add(result, "RP-007", pack.name, f"{source.name} 里的指针 {pointer} 找不到")

    def _check_equivalence(self, pack: Path, config: dict[str, Any], result: RoleCheckResult) -> None:
        """RP-008: the pack says what the old skill said.

        A missing old skill is told apart from a retired one: only ``"retired": true`` in role.json
        switches the comparison off, so a mistyped path can never make the check pass silently.
        """
        legacy = config.get("legacy")
        if legacy is None or not (pack / "SKILL.md").is_file():
            return
        if not isinstance(legacy, dict):
            self._add(result, "RP-008", pack.name, "role.json 的 legacy 必须是对象")
            return
        if legacy.get("retired") is True:
            return
        root = self.workspace_root
        if root is None or not (root / OLD_SKILLS_RELPATH).is_dir():
            self._add(result, "RP-008", pack.name, "找不到旧技能目录 .trae/skills，与旧技能的一致性未核对", UNVERIFIED)
            return
        source = root / str(legacy.get("source", ""))
        if not source.is_file():
            self._add(
                result,
                "RP-008",
                pack.name,
                f"旧技能 {legacy.get('source')} 不存在；路径写错请改正，已退役请在 role.json 的 legacy 里写 \"retired\": true",
            )
            return
        mode = legacy.get("mode")
        if mode not in LEGACY_MODES:
            self._add(result, "RP-008", pack.name, f"legacy.mode {mode!r} 不认识，只认 {sorted(LEGACY_MODES)}")
            return
        _, old_body = split_front_matter(_read(source))
        _, new_body = split_front_matter(_read(pack / "SKILL.md"))
        if mode == "body-equal" and old_body != new_body:
            self._add(result, "RP-008", pack.name, f"正文与旧技能 {legacy.get('source')} 不逐字一致")
        elif mode == "section-contained":
            heading = str(legacy.get("from_heading", ""))
            start = old_body.find(heading)
            if start == -1:
                self._add(result, "RP-008", pack.name, f"旧技能里找不到章节 {heading!r}")
            elif old_body[start:] not in new_body:
                self._add(result, "RP-008", pack.name, f"正文没有逐字包含旧技能从 {heading!r} 起的内容")
        refs = legacy.get("refs")
        if refs:
            self._check_refs_equal(pack, root / str(refs), result)

    def _check_refs_equal(self, pack: Path, old_refs: Path, result: RoleCheckResult) -> None:
        """Every file of the old refs/ exists in the pack with the same text."""
        if not old_refs.is_dir():
            self._add(result, "RP-008", pack.name, f"旧技能的 refs 目录 {old_refs.name} 不存在；路径写错请改正，已退役请写 retired")
            return
        for old in sorted(old_refs.rglob("*")):
            if not old.is_file():
                continue
            relative = old.relative_to(old_refs)
            new = pack / "refs" / relative
            if not new.is_file():
                self._add(result, "RP-008", pack.name, f"refs/{relative.as_posix()} 缺失（旧技能里有）")
            elif _read(new).replace("\r\n", "\n") != _read(old).replace("\r\n", "\n"):
                self._add(result, "RP-008", pack.name, f"refs/{relative.as_posix()} 与旧技能不一致")
