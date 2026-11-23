"""Unified L1/L2/L3 gate tiering policy shared by precheck, local merge, and CI."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, Literal

from auto_pm.application.core.gate_run_service import GROUPS

TierName = Literal["L1", "L2", "L3"]

L1_MAX_PRODUCT_PY = 3
L1_MAX_TEST_ONLY_FILES = 6
ALL_GATE_GROUPS: tuple[str, ...] = tuple(group.name for group in GROUPS)
_VALID_GROUP_SET = frozenset(ALL_GATE_GROUPS)

_M2_SCHEMA = "m2-tier-rules.v1"
_M2_TIERS = ("docs", "tests", "product", "core")
_M2_MATCH_KINDS = ("prefix", "exact", "basename", "basename_prefix")
_DOC_EXTENSIONS = (".md", ".rst")

_GLOBAL_L3_EXACT = frozenset({"tests/conftest.py", "pyproject.toml", "requirements.txt"})
_MANDATORY_L3_EXACT = frozenset(
    {
        "scripts/pm_merge.py",
        "scripts/pm_release.py",
        "scripts/long_gate.py",
        "auto_pm/infrastructure/git_hook_enforcer.py",
        "auto_pm/infrastructure/change_status_guard.py",
        "auto_pm/domain/change/change_service.py",
        "auto_pm/domain/change/status_journal.py",
        "auto_pm/domain/change/guard_checker.py",
        "auto_pm/ui/cli/change.py",
    }
)
_MANDATORY_L3_PREFIXES = (
    "auto_pm/application/core/gate_",
    "auto_pm/application/core/release_",
    "auto_pm/domain/plc/",
    "auto_pm/application/plc/",
    "auto_pm/infrastructure/plc/",
    "auto_pm/ui/cli/plc/",
    "auto_pm/ui/qml/",
    "tests/plc/",
    "tests/qml/",
    "tests/tools/",
)
_MANDATORY_L3_SUFFIXES = (".qml", ".scl", ".st")
_BOARD_L2_PREFIXES = ("scripts/cockpit_board/",)
_BOARD_L2_EXACT = frozenset({"scripts/pm_dashboard_gui.py"})
_HEAVY_GUI_TEST_PREFIXES = ("test_cockpit_board", "test_pm_dashboard_gui")
# 一期先仅对已核实样板与纯文档开放 L1；其余非核心路径统一保守入 L2，经二期核算后再扩表。
L1_VERIFIED_PILOT_PATHS: frozenset[str] = frozenset(
    {
        "scripts/command_catalog.py",
        "tests/infrastructure/test_command_catalog.py",
    }
)

_GROUP_PREFIX_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("auto_pm/contracts/", ("contracts",)),
    ("tests/contracts/", ("contracts",)),
    ("tests/contract/", ("contracts",)),
    ("auto_pm/domain/change/", ("change",)),
    ("auto_pm/application/change", ("change",)),
    ("tests/change/", ("change",)),
    ("auto_pm/domain/plc/", ("plc",)),
    ("auto_pm/application/plc/", ("plc",)),
    ("auto_pm/infrastructure/plc/", ("plc",)),
    ("auto_pm/ui/cli/plc/", ("plc",)),
    ("tests/plc/", ("plc",)),
    ("auto_pm/ui/qml/", ("qml", "qml_debounce_alone")),
    ("tests/qml/", ("qml", "qml_debounce_alone")),
    ("auto_pm/ui/cli/", ("cli",)),
    ("tests/cli/", ("cli",)),
    ("auto_pm/infrastructure/", ("infrastructure",)),
    ("tests/infrastructure/", ("infrastructure",)),
    ("auto_pm/application/", ("application",)),
    ("tests/application/", ("application",)),
    ("auto_pm/domain/", ("core",)),
    ("auto_pm/core/", ("core",)),
    ("tests/core/", ("core",)),
    ("scripts/cockpit_board/", ("core",)),
    ("scripts/pm_dashboard_gui.py", ("core",)),
    ("main.py", ("cli", "core")),
    ("scripts/", ("rest",)),
    ("tests/", ("rest",)),
)


@dataclass(frozen=True)
class GateTierDecision:
    """Machine classification outcome for one candidate change set."""

    tier: TierName
    m2_tier: str
    recommended_groups: tuple[str, ...]
    require_plugin: bool
    full_forced: bool
    reasons: tuple[str, ...]
    rules_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable summary of this tier decision."""
        return {
            "tier": self.tier,
            "m2_tier": self.m2_tier,
            "recommended_groups": list(self.recommended_groups),
            "require_plugin": self.require_plugin,
            "full_forced": self.full_forced,
            "reasons": list(self.reasons),
            "rules_sha256": self.rules_sha256,
        }


@dataclass(frozen=True)
class _M2Rule:
    rule_id: str
    tier: str
    kind: str
    pattern: str
    reason: str


@dataclass(frozen=True)
class _M2Rules:
    sha256: str
    project_prefix: str
    behavior_suffixes: tuple[str, ...]
    unknown_tier: str
    rules: tuple[_M2Rule, ...]


def _m2_rank(tier: str) -> int:
    return _M2_TIERS.index(tier)


def _fail_closed(reason: str, *, rules_sha256: str = "") -> GateTierDecision:
    return GateTierDecision(
        tier="L3",
        m2_tier="core",
        recommended_groups=ALL_GATE_GROUPS,
        require_plugin=True,
        full_forced=True,
        reasons=(reason,),
        rules_sha256=rules_sha256,
    )


def _default_rules_file(project: Path | None, rules_path: Path | None) -> Path:
    if rules_path is not None:
        return rules_path
    if project is not None:
        return project / "tests" / "tools" / "tier_core_list.json"
    return Path(__file__).resolve().parents[3] / "tests" / "tools" / "tier_core_list.json"


def _load_m2_rules(source: Path) -> _M2Rules:
    raw = source.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict) or data.get("schema") != _M2_SCHEMA:
        raise ValueError(f"rules schema is not {_M2_SCHEMA}")
    if data.get("tiers") != list(_M2_TIERS):
        raise ValueError("rules tiers differ from m2 schema")
    if data.get("unknown_tier") != "core":
        raise ValueError("unknown_tier must be core")
    prefix = data.get("project_prefix")
    suffixes = data.get("behavior_suffixes")
    entries = data.get("rules")
    if (
        not isinstance(prefix, str)
        or not isinstance(suffixes, list)
        or not isinstance(entries, list)
        or not entries
    ):
        raise ValueError("rules file misses project_prefix, behavior_suffixes or rules")
    if not all(isinstance(item, str) and item.startswith(".") and item == item.lower() for item in suffixes):
        raise ValueError("invalid behavior_suffixes")

    parsed: list[_M2Rule] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("rule entry must be an object")
        rule_id = entry.get("id")
        tier = entry.get("tier")
        kind = entry.get("kind")
        pattern = entry.get("pattern")
        reason = entry.get("reason")
        if not all(isinstance(v, str) and v for v in (rule_id, tier, kind, pattern, reason)):
            raise ValueError(f"rule {rule_id!r} misses required string fields")
        assert (
            isinstance(rule_id, str)
            and isinstance(tier, str)
            and isinstance(kind, str)
            and isinstance(pattern, str)
            and isinstance(reason, str)
        )
        if rule_id in seen:
            raise ValueError(f"duplicate rule id {rule_id}")
        seen.add(rule_id)
        if tier not in _M2_TIERS or kind not in _M2_MATCH_KINDS:
            raise ValueError(f"invalid tier or match kind in {rule_id}")
        if "\\" in pattern or pattern.startswith("/"):
            raise ValueError(f"invalid pattern in {rule_id}")
        parsed.append(_M2Rule(rule_id=rule_id, tier=tier, kind=kind, pattern=pattern, reason=reason))

    return _M2Rules(
        sha256=hashlib.sha256(raw).hexdigest(),
        project_prefix=prefix,
        behavior_suffixes=tuple(suffixes),
        unknown_tier="core",
        rules=tuple(parsed),
    )


def _normalize_raw_posix(raw: str) -> str:
    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        raise ValueError(f"空路径或非法字符：{raw!r}")
    text = raw.strip().replace("\\", "/")
    if text.startswith("/") or (len(text) > 1 and text[1] == ":"):
        raise ValueError(f"绝对路径不允许进入分档：{raw!r}")
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts) or not parts:
        raise ValueError(f"越界或空路径：{raw!r}")
    return "/".join(parts)


def _strip_project_prefix(posix_path: str, project_prefix: str) -> str:
    if project_prefix and posix_path.casefold().startswith(project_prefix.casefold()):
        trimmed = posix_path[len(project_prefix) :]
        if not trimmed:
            raise ValueError(f"路径只指向项目根目录：{posix_path!r}")
        return trimmed
    return posix_path


def _m2_matches(rule: _M2Rule, normalized: str) -> bool:
    folded = normalized.casefold()
    pattern = rule.pattern.casefold()
    base = folded.rsplit("/", 1)[-1]
    if rule.kind == "prefix":
        return folded.startswith(pattern)
    if rule.kind == "exact":
        return folded == pattern
    if rule.kind == "basename":
        return base == pattern
    return base.startswith(pattern)


def _classify_m2(normalized: str, rules: _M2Rules) -> tuple[str, tuple[str, ...]]:
    matched = [rule for rule in rules.rules if _m2_matches(rule, normalized)]
    if not matched:
        return rules.unknown_tier, (f"未知路径未命中 M2 规则：{normalized}",)
    tier = max((rule.tier for rule in matched), key=_m2_rank)
    top_reasons = tuple(rule.reason for rule in matched if rule.tier == tier)
    base = normalized.rsplit("/", 1)[-1]
    suffix = "." + base.rsplit(".", 1)[-1].casefold() if "." in base else ""
    if tier == "docs" and suffix in rules.behavior_suffixes:
        return "product", (*top_reasons, f"文档目录下的行为文件 {suffix} 升级为 product")
    return tier, top_reasons


def _matches_protected_pattern(candidates: Sequence[str], patterns: Sequence[str]) -> str | None:
    for pattern in patterns:
        folded_pat = pattern.strip().replace("\\", "/").casefold()
        if not folded_pat:
            continue
        for candidate in candidates:
            if fnmatchcase(candidate.casefold(), folded_pat):
                return pattern
    return None


def _groups_for_path(normalized: str) -> tuple[str, ...]:
    folded = normalized.casefold()
    for prefix, groups in _GROUP_PREFIX_RULES:
        if prefix.endswith("/") and folded.startswith(prefix):
            return tuple(g for g in groups if g in _VALID_GROUP_SET)
        if not prefix.endswith("/") and folded == prefix:
            return tuple(g for g in groups if g in _VALID_GROUP_SET)
    return ("rest",) if "rest" in _VALID_GROUP_SET else ()


def _order_groups(group_names: set[str]) -> tuple[str, ...]:
    return tuple(name for name in ALL_GATE_GROUPS if name in group_names)


def _dedupe_reasons(reasons: Sequence[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    for item in reasons:
        if item and item not in ordered:
            ordered.append(item)
    return tuple(ordered)


def classify_gate_tier(
    changed_paths: Sequence[str],
    *,
    project: Path | None = None,
    rules_path: Path | None = None,
    outside_changes: Sequence[str] = (),
    extra_protected_patterns: Sequence[str] = (),
) -> GateTierDecision:
    """Classify changed paths into L1 / L2 / L3 with fail-closed protection for core and unknown paths."""
    source = _default_rules_file(project, rules_path)
    try:
        rules = _load_m2_rules(source)
    except (OSError, ValueError) as exc:
        return _fail_closed(f"tier_core_list.json 读取或校验失败（{exc}），按 L3 全量执行")

    if not changed_paths and not outside_changes:
        return _fail_closed("改动列表为空，fail-closed 走 L3 全量门禁", rules_sha256=rules.sha256)

    if outside_changes:
        for outside_raw in outside_changes:
            try:
                outside_posix = _normalize_raw_posix(outside_raw)
            except ValueError as exc:
                return _fail_closed(f"项目外非法路径（{exc}），按 L3 全量执行", rules_sha256=rules.sha256)
            matched_pat = _matches_protected_pattern((outside_raw, outside_posix), extra_protected_patterns)
            if matched_pat:
                return _fail_closed(
                    f"命中受保护路径规则 {matched_pat}：{outside_posix}，强制 L3 全量门禁",
                    rules_sha256=rules.sha256,
                )
        sample = ", ".join(str(p) for p in outside_changes[:3])
        return _fail_closed(
            f"包含项目目录外改动（{sample}），强制 L3 全量门禁",
            rules_sha256=rules.sha256,
        )

    l3_reasons: list[str] = []
    l2_reasons: list[str] = []
    m2_levels: list[str] = []
    affected_groups: set[str] = set()
    product_py_paths: list[str] = []
    test_py_paths: list[str] = []

    for raw in changed_paths:
        try:
            raw_posix = _normalize_raw_posix(raw)
            normalized = _strip_project_prefix(raw_posix, rules.project_prefix)
        except ValueError as exc:
            return _fail_closed(str(exc), rules_sha256=rules.sha256)

        matched_pat = _matches_protected_pattern((raw, raw_posix, normalized), extra_protected_patterns)
        if matched_pat:
            l3_reasons.append(f"命中额外受保护规则 {matched_pat}：{normalized}")

        folded = normalized.casefold()
        base_name = Path(normalized).name
        is_doc = any(folded.endswith(ext) for ext in _DOC_EXTENSIONS)

        if folded in _GLOBAL_L3_EXACT:
            l3_reasons.append(f"全局测试/构建配置改动：{normalized}")
        if folded in _MANDATORY_L3_EXACT or any(folded.startswith(pref) for pref in _MANDATORY_L3_PREFIXES):
            l3_reasons.append(f"核心门禁/发版/PLC/QML/工具目录改动：{normalized}")
        if any(folded.endswith(ext) for ext in _MANDATORY_L3_SUFFIXES):
            l3_reasons.append(f"受保护扩展名文件改动：{normalized}")

        m2_tier, m2_path_reasons = _classify_m2(normalized, rules)
        m2_levels.append(m2_tier)
        if m2_tier == "core":
            l3_reasons.extend(m2_path_reasons)

        if not is_doc and not folded.endswith(".py"):
            l3_reasons.append(f"非 Python 运行或配置资产改动：{normalized}")

        if not is_doc:
            affected_groups.update(_groups_for_path(normalized))
            if folded.startswith("tests/"):
                test_py_paths.append(normalized)
                if base_name == "conftest.py" and folded != "tests/conftest.py":
                    l2_reasons.append(f"子目录 conftest 影响整组测试：{normalized}")
                if Path(normalized).stem.startswith(_HEAVY_GUI_TEST_PREFIXES):
                    l2_reasons.append(f"涉及总控屏/GUI 重型测试：{normalized}")
            elif folded.endswith(".py"):
                product_py_paths.append(normalized)
                if any(folded.startswith(pref) for pref in _BOARD_L2_PREFIXES):
                    l2_reasons.append(f"涉及总控屏脚本目录：{normalized}")
                elif folded in _BOARD_L2_EXACT:
                    l2_reasons.append(f"涉及总控屏入口脚本：{normalized}")
            if folded.endswith(".py") and folded not in L1_VERIFIED_PILOT_PATHS:
                l2_reasons.append(f"尚未纳入一期 L1 已核实白名单：{normalized}")

    overall_m2 = max(m2_levels, key=_m2_rank) if m2_levels else "docs"

    if l3_reasons:
        return GateTierDecision(
            tier="L3",
            m2_tier=overall_m2,
            recommended_groups=ALL_GATE_GROUPS,
            require_plugin=True,
            full_forced=True,
            reasons=_dedupe_reasons(l3_reasons),
            rules_sha256=rules.sha256,
        )

    if len(product_py_paths) > L1_MAX_PRODUCT_PY:
        l2_reasons.append(
            f"受影响产品 Python 文件共 {len(product_py_paths)} 个，超过 L1 上限 {L1_MAX_PRODUCT_PY}"
        )
    if len(test_py_paths) > L1_MAX_TEST_ONLY_FILES:
        l2_reasons.append(
            f"受影响测试文件共 {len(test_py_paths)} 个，超过 L1 上限 {L1_MAX_TEST_ONLY_FILES}"
        )

    ordered_groups = _order_groups(affected_groups)

    if l2_reasons:
        return GateTierDecision(
            tier="L2",
            m2_tier=overall_m2,
            recommended_groups=ordered_groups,
            require_plugin=False,
            full_forced=False,
            reasons=_dedupe_reasons(l2_reasons),
            rules_sha256=rules.sha256,
        )

    l1_reason = (
        "仅文档改动（.md/.rst），执行 L1 轻量预检"
        if not product_py_paths and not test_py_paths
        else f"命中一期 L1 已核实白名单（产品 py {len(product_py_paths)} 个，测试 py {len(test_py_paths)} 个），满足 L1 本地闭环"
    )
    return GateTierDecision(
        tier="L1",
        m2_tier=overall_m2,
        recommended_groups=ordered_groups,
        require_plugin=False,
        full_forced=False,
        reasons=(l1_reason,),
        rules_sha256=rules.sha256,
    )
