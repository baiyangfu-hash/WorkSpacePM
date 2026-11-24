"""Role pack check (role-pack card 1): the cockpit keeps the job descriptions, agents only borrow them.

The library is the tracked, tool-neutral directory ``roles/`` at the workspace root (no IDE and no
cockpit release owns it).  A role pack is a directory ``roles/<role-id>/``::

    SKILL.md    job description for people and for tools that load skills (Trae, Cursor)
    role.json   machine config: required specs, allowed commands, gates, receipt fields
    refs/       domain notes copied as they were; only needed when the old skill had them

``roles/shared/refs`` holds the common contract that every pack links to with ``../shared/refs``.

The check is read-only and never needs the ledger, so it also runs offline.  Each finding carries a
code so a card or an audit can quote it:

* RP-001 the roles/ directory has no pack, or a required file of a pack is missing
* RP-002 role.json is not valid or lacks a key
* RP-003 role id is not the directory name or uses a character that breaks Windows paths
* RP-004 SKILL.md front matter name differs from the id, or has no description
* RP-005 a legacy name is claimed by two packs
* RP-006 a required spec id is not in spec_registry.json (UNVERIFIED when the registry is absent)
* RP-007 a relative ``.md`` pointer inside a pack does not resolve
* RP-008 a pack that points at the one master copy of its procedure (``legacy.mode`` ``pointer``) does
  not name that file, the file or its section heading is gone, or the pack copies the section
  instead of pointing at it; the old copy modes (``body-equal``, ``section-contained``) are refused:
  a second hand-kept copy drifted the day only the master was edited (CHG-SCPT-2026-682).
  Only ``\"retired\": true`` in role.json skips it; no workspace gives UNVERIFIED
* RP-009 a text file of the library is not valid UTF-8 or shows mojibake (U+FFFD, C1 controls,
  UTF-8 read as Latin-1)
* RP-010 the same long line or sentence sits in two packs' SKILL.md, or a pack repeats a line or sentence of
  ``roles/shared/refs`` (sub-folders included) or of a master file (any pack's ``legacy.source``, AGENTS.md,
  CLAUDE.md): what several roles share is written once and each pack points at it.  Lines are cut into
  sentences and both sides compared as a skeleton (no list marker, number in front, space, line break,
  punctuation or symbol), so a copied sentence counts inside other words, wrapped over two lines, with another
  comma, as a heading or in a pack's code block; pointer sentences, headings quoted to point at a section,
  commands with no Chinese and the masters' code blocks do not count
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROLE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
ROLES_DIRNAME = "roles"
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
POINTER_MODE = "pointer"
# Modes that kept a second copy of the master text in the pack and compared the two; refused since 682.
RETIRED_COPY_MODES = frozenset({"body-equal", "section-contained"})
# A copied line or sentence this long is a copy, not a shared phrase (headings like "## 不要做" stay allowed).
COPIED_LINE_MIN_CHARS = 20
# ... and still this long once spaces, bars and punctuation are gone: a table header such as "| agent | 工位 | 分支前缀 |"
# is long on the page but only a few words, and a pack's own sentence may hold them (JB8R on #838, WARN-1).
COPIED_SKELETON_MIN_CHARS = 15
# Copy tricks a whole-line compare missed (JB8R on #834, audit pre-check of the follow-up card): a list marker,
# number, quote mark or bold put in front, one sentence of a long line, a sentence set inside other words, a
# table cell, a line wrapped in two, a space or another comma put in, a sentence made a heading or put in a code
# block.  A unit is cut into sentences first; then both sides are compared as a skeleton (see ``_skeleton``).
LEAD_MARKER = re.compile(r"^(?:>\s*)*(?:[-*+•]\s+|\d+[.)、．]\s*|[（(]\d+[）)]\s*)?(?:\[[ xX]\]\s+)?")
SENTENCE_CUT = re.compile(r"[。；！？;!?|]")
EMPHASIS = re.compile(r"\*\*|__|`")
# A piece with no Chinese outside its <占位> is a command, a path or a name, not a rule; packs may quote those.
PLACEHOLDER = re.compile(r"<[^<>]*>")
CJK = re.compile(r"[\u4e00-\u9fff]")
# Workspace files whose rules a pack may point at but never repeat (RP-010), besides every pack's legacy.source.
MASTER_RELPATHS = ("AGENTS.md", "CLAUDE.md")
SPEC_REGISTRY_RELPATH = "00_Obsidian_Base全局规范文件仓库/spec_registry.json"
# Only pointers that start like a relative path are followed; bare file names in prose are not.
MD_POINTER = re.compile(r"(?:\.\./|\./|refs/)[\w./\-]+\.md")

# Signs of UTF-8 text that was read as Latin-1/CP1252 and saved again, or of bytes lost on the way.
MOJIBAKE = re.compile("\ufffd|[\u0080-\u009f]|[\u00c2\u00c3][\u0080-\u00bf]|\u00e2\u20ac")
TEXT_SUFFIXES = frozenset({".md", ".json"})

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


def _normalise(text: str) -> str:
    """One line or sentence as compared: no list marker, number, quote mark or emphasis in front, spaces collapsed."""
    text = EMPHASIS.sub("", text.strip())
    text = LEAD_MARKER.sub("", text)
    return " ".join(text.split()).strip(" ：:，,、")


def _skeleton(text: str) -> str:
    """What is left to compare once layout is gone: no space, line break, punctuation or symbol, letters in one case.

    Spaces, full- or half-width commas, quote and list marks, emphasis, heading and table marks all drop out, so
    the same words in another layout compare equal; on the pack side the lines are joined with nothing between,
    so a sentence wrapped over two lines is found as well.
    """
    return "".join(char for char in text.casefold() if unicodedata.category(char)[0] not in "PSZC")


def _is_pointer(text: str) -> bool:
    return bool(MD_POINTER.search(text)) or OLD_SKILLS_RELPATH in text or "shared/refs/" in text


def _is_prose(text: str) -> bool:
    return bool(CJK.search(PLACEHOLDER.sub("", text)))


def _copy_units(text: str, *, skip_code: bool = True, skip_pointers: bool = True) -> dict[str, str]:
    """What a copy is looked for in, as {skeleton: line or sentence as shown}: each long prose line and each long
    sentence or table cell of it.

    The whole line stays a unit, so two short sentences copied together are still caught; each sentence is a
    unit too, so one sentence lifted out of a long line, or set inside other words, is caught as well.  A heading
    is a section's name and quoting it is how a pack points at that section, so headings are not units; a rule
    copied into a heading is still found, because the pack side (``_flat_text``) keeps headings.  With
    ``skip_pointers`` a piece that names a shared file (``../shared/refs/x.md``, ``shared/refs/``,
    ``.trae/skills``) is the pointer itself and every pack may say it, and a piece with no Chinese outside its
    ``<占位>`` is a command, path or name that packs may quote; the other sentences of that line are still compared.
    """
    units: dict[str, str] = {}
    fenced = False
    for raw in text.split("\n"):
        stripped = raw.strip()
        if stripped.startswith("```"):
            fenced = not fenced
            continue
        if (fenced and skip_code) or stripped.startswith("#"):
            continue
        for piece in (stripped, *SENTENCE_CUT.split(stripped)):
            unit = _normalise(piece)
            if len(unit) < COPIED_LINE_MIN_CHARS or (skip_pointers and (_is_pointer(unit) or not _is_prose(unit))):
                continue
            key = _skeleton(unit)
            if len(key) < COPIED_SKELETON_MIN_CHARS:
                continue
            units.setdefault(key, unit)
    return units


def _flat_text(text: str) -> str:
    """All of ``text`` (headings and code blocks too) as one skeleton, to find a copied unit inside other words,
    across a line break or in another layout."""
    return "".join(_skeleton(_normalise(raw.strip().lstrip("#"))) for raw in text.split("\n"))


def default_roles_dir(workspace_root: Path) -> Path:
    """The role library of a workspace: ``roles/`` at its root."""
    return Path(workspace_root) / ROLES_DIRNAME


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
    return path.read_text(encoding="utf-8", errors="replace")  # lenient-decode: parsed or shown only; RP-009 fails a file that is not UTF-8


class RolePackService:
    """Check the role packs of one cockpit against themselves, the spec registry and the old skills."""

    def __init__(self, roles_dir: Path | None = None, workspace_root: Path | None = None) -> None:
        self.workspace_root = Path(workspace_root) if workspace_root else None
        if roles_dir:
            self.roles_dir: Path | None = Path(roles_dir)
        else:
            self.roles_dir = default_roles_dir(self.workspace_root) if self.workspace_root else None

    def role_dirs(self) -> list[Path]:
        """Pack directories, sorted by name; ``shared`` is not a role."""
        if self.roles_dir is None or not self.roles_dir.is_dir():
            return []
        return sorted(
            child for child in self.roles_dir.iterdir() if child.is_dir() and child.name != SHARED_DIR
        )

    def check(self) -> RoleCheckResult:
        """Run every check on every pack and collect the findings."""
        result = RoleCheckResult()
        spec_ids = self._load_spec_ids()
        claimed: dict[str, str] = {}
        if not self.role_dirs():
            # An empty library must not pass: that would be the same silent pass as a mistyped path.
            self._add(result, "RP-001", "-", f"找不到角色库或里面没有角色包：{self.roles_dir or '未指定工作区'}")
        for pack in self.role_dirs():
            result.roles.append(pack.name)
            config = self._check_files_and_config(pack, result)
            if config is None:
                continue
            self._check_identity(pack, config, result)
            self._check_legacy_names(pack, config, claimed, result)
            self._check_specs(pack, config, spec_ids, result)
            self._check_pointers(pack, result)
            self._check_encoding(pack, result)
            self._check_pointer_to_master(pack, config, result)
        if self.roles_dir is not None and (self.roles_dir / SHARED_DIR).is_dir():
            self._check_encoding(self.roles_dir / SHARED_DIR, result)
        self._check_no_line_shared_between_packs(result)
        return result

    def _check_no_line_shared_between_packs(self, result: RoleCheckResult) -> None:
        """RP-010: a long line or sentence in two packs' SKILL.md, or in a pack and a shared ref or master file, is a hand-kept copy.

        Lines shared only among the master files and shared refs themselves are not this check's business: it
        reports a line only when a pack's SKILL.md is one of its owners.
        """
        owners: dict[str, list[str]] = {}
        shown: dict[str, str] = {}

        def own(units: dict[str, str], label: str) -> None:
            for key, unit in sorted(units.items()):
                shown.setdefault(key, unit)
                if label not in owners.setdefault(key, []):
                    owners[key].append(label)

        for label, master in self._master_files():
            own(_copy_units(split_front_matter(_read(master))[1]), label)
        shared_refs = self.roles_dir / SHARED_DIR / "refs" if self.roles_dir is not None else None
        if shared_refs is not None and shared_refs.is_dir():
            for ref in sorted(shared_refs.rglob("*.md")):  # sub-folders too: agents_附录/ holds AGENTS.md's long text
                own(_copy_units(_read(ref)), f"shared/refs/{ref.relative_to(shared_refs).as_posix()}")
        pack_texts: dict[str, str] = {}
        for pack in self.role_dirs():
            if not (pack / "SKILL.md").is_file():
                continue
            _, body = split_front_matter(_read(pack / "SKILL.md"))
            pack_texts[pack.name] = _flat_text(body)  # code blocks included: Chinese rules put in a code block are still copies
            own(_copy_units(body), pack.name)
        for key, names in owners.items():
            for name, flat in pack_texts.items():
                if name not in names and key in flat:
                    names.append(name)  # the unit sits inside a longer line or sentence of this pack
        # One finding per group of files that share text: a copied line also shares each of its sentences.
        groups: dict[tuple[str, ...], list[str]] = {}
        for key, names in owners.items():
            if len(names) > 1 and any(name in pack_texts for name in names):
                groups.setdefault(tuple(names), []).append(shown[key])
        for group, units in sorted(groups.items()):
            example = max(units, key=lambda unit: (len(unit), unit))
            copier = [name for name in group if name in pack_texts][-1]
            self._add(
                result,
                "RP-010",
                copier,
                f"{'、'.join(group)} 里抄了同样的话 {len(units)} 处（如 {example[:40]!r}）："
                "正本只留一处，共用的写在 roles/shared/refs，各岗位指路",
            )

    def _master_files(self) -> list[tuple[str, Path]]:
        """AGENTS.md, CLAUDE.md and every file a pack's ``legacy.source`` points at, as (label, path); needs a workspace."""
        root = self.workspace_root
        if root is None:
            return []
        relpaths = list(MASTER_RELPATHS)
        for pack in self.role_dirs():
            try:
                legacy = json.loads(_read(pack / "role.json")).get("legacy")
            except (OSError, ValueError, AttributeError):
                continue  # RP-001/RP-002 report a missing or broken role.json
            if isinstance(legacy, dict) and legacy.get("mode") == POINTER_MODE and legacy.get("source"):
                relpaths.append(str(legacy["source"]))
        found: list[tuple[str, Path]] = []
        for relpath in dict.fromkeys(relpaths):
            path = root / relpath
            if path.is_file():
                found.append((relpath, path))
        return found

    def _check_encoding(self, folder: Path, result: RoleCheckResult) -> None:
        """RP-009: every text file decodes as UTF-8 and shows no mojibake."""
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            relative = path.relative_to(folder).as_posix()
            try:
                text = path.read_bytes().decode("utf-8")
            except UnicodeDecodeError as error:
                self._add(result, "RP-009", folder.name, f"{relative} 不是合法 UTF-8（第 {error.start} 字节处），文件已损坏")
                continue
            hit = MOJIBAKE.search(text)
            if hit:
                line = text.count("\n", 0, hit.start()) + 1
                self._add(result, "RP-009", folder.name, f"{relative} 第 {line} 行有乱码特征 {hit.group()!r}（UTF-8 被当成别的编码存过）")

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
        roles_root = self.roles_dir.resolve() if self.roles_dir else pack.parent.resolve()
        for source in sources:
            if not source.is_file():
                continue
            for pointer in sorted(set(MD_POINTER.findall(_read(source)))):
                # ``refs/x.md`` is written from the pack root even inside refs/ (the old INDEX.md does so).
                base = pack if pointer.startswith("refs/") else source.parent
                target = (base / pointer).resolve()
                if not target.is_file() or roles_root not in target.parents:
                    self._add(result, "RP-007", pack.name, f"{source.name} 里的指针 {pointer} 找不到")

    def _check_pointer_to_master(self, pack: Path, config: dict[str, Any], result: RoleCheckResult) -> None:
        """RP-008: the procedure has one master copy; the pack points at it and does not copy it.

        ``legacy`` is either ``{"retired": true}`` (nothing to point at) or ``{"mode": "pointer", "source": <file>,
        "from_heading": <heading>}``: SKILL.md names ``source``, the heading is still in ``source``, and no heading
        or long line or sentence of the section from that heading on is copied into the pack (compared the way
        RP-010 compares: markers dropped, cut into sentences, found inside other words too).  Editing the master then needs
        no second edit anywhere.
        """
        legacy = config.get("legacy")
        if legacy is None or not (pack / "SKILL.md").is_file():
            return
        if not isinstance(legacy, dict):
            self._add(result, "RP-008", pack.name, "role.json 的 legacy 必须是对象")
            return
        if legacy.get("retired") is True:
            return
        mode = legacy.get("mode")
        if mode in RETIRED_COPY_MODES:
            self._add(
                result,
                "RP-008",
                pack.name,
                f"legacy.mode {mode!r} 已停用：不再在角色包里抄一份正本、再靠检查比对；"
                f"本页改成指路，role.json 写 \"mode\": \"{POINTER_MODE}\"",
            )
            return
        if mode != POINTER_MODE:
            self._add(result, "RP-008", pack.name, f"legacy.mode {mode!r} 不认识，只认 {POINTER_MODE!r}")
            return
        root = self.workspace_root
        if root is None or not (root / OLD_SKILLS_RELPATH).is_dir():
            self._add(result, "RP-008", pack.name, "找不到 .trae/skills，指路是否有效未核对", UNVERIFIED)
            return
        source_text = str(legacy.get("source", ""))
        source = root / source_text
        if not source_text or not source.is_file():
            self._add(
                result,
                "RP-008",
                pack.name,
                f"指路的正本 {legacy.get('source')} 不存在；路径写错请改正，没有正本了请在 role.json 的 legacy 里写 \"retired\": true",
            )
            return
        _, master_body = split_front_matter(_read(source))
        _, pack_body = split_front_matter(_read(pack / "SKILL.md"))
        heading = str(legacy.get("from_heading", ""))
        start = master_body.find(heading) if heading else -1
        if start == -1:
            self._add(result, "RP-008", pack.name, f"正本 {source_text} 里找不到章节 {heading!r}；正本改了标题请同步改 role.json 的 from_heading")
            return
        if source_text not in pack_body:
            self._add(result, "RP-008", pack.name, f"SKILL.md 没有写出指路的正本 {source_text}")
        section = master_body[start:]
        section_headings = {line.strip() for line in section.split("\n") if line.strip().lstrip("#").strip() and line.strip().startswith("#")}
        pack_flat = _flat_text(pack_body)
        copied = sorted(
            {line.strip() for line in pack_body.split("\n")} & section_headings
            | {unit for key, unit in _copy_units(section, skip_code=False, skip_pointers=False).items() if key in pack_flat}
        )
        if copied:
            self._add(
                result,
                "RP-008",
                pack.name,
                f"SKILL.md 抄了正本 {source_text} 的 {len(copied)} 行（如 {copied[0][:40]!r}）：只指路，不抄",
            )
