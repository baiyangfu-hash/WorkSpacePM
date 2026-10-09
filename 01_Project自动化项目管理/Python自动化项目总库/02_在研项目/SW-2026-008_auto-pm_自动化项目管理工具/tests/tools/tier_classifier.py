"""Machine tier classifier for governed cards (rule document "M2 gate tiers and card size", sections 1, 3, 4 and 11).

The rule document says the tier is taken from the highest-risk path of the real change, is never chosen by the executor, and that an unknown or unclassifiable path is
refused a tier and reviewed as core. This module is that check as code. It only RECOMMENDS: it can keep or raise the tier a card declares, and a card that declares a lower
tier than the computed one is refused. It never lowers a tier (section 11).

* ``tier_core_list.json`` (next to this file, versioned, hashed into every result) holds the rules: path prefixes, exact files and base names, each with a tier and a reason.
  Several rules can match one path; the HIGHEST tier among them wins, so a more specific core rule can never be shadowed by a broader product rule.
* A path that no rule matches gets the unknown tier (core) and is listed under ``unknown``.
* Under a docs folder a file with a behaviour suffix (script, configuration, template, query) is not plain documentation and is raised to product.
* Paths are normalised before matching (separators, case, ``./``); absolute paths and parent traversal are refused.
* The changed paths can come from ``git diff --name-status --no-renames`` (a rename counts as the removal of the old path and the addition of the new one) and, on request, from untracked files.

Usage: python -B tier_classifier.py (--paths PATH [PATH ...] | --diff BASE [HEAD]) [--repo DIR] [--untracked] [--declared TIER] [--rules FILE]
Exit codes: 0 = classified (and the declared tier, if given, is not lower), 2 = the declared tier is lower than the computed one or unknown, 3 = bad input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = "m2-tier-rules.v1"
TIERS = ("docs", "tests", "product", "core")
MATCH_KINDS = ("prefix", "exact", "basename", "basename_prefix")
RULES_FILE = Path(__file__).with_name("tier_core_list.json")

# What each tier must run, in words that match the rule document (sections 2 to 4). A higher tier never runs less than a lower one where they overlap.
GATES: dict[str, tuple[str, ...]] = {
    "docs": ("document-structure-and-links", "ledger-integrity", "old-content-preserved", "scope-and-byte-fingerprints", "light-negative-controls"),
    "tests": ("relevant-complete-group", "test-health", "types-and-static", "mutation-check-of-new-assertions", "product-bytes-unchanged"),
    "product": ("nine-regression-groups", "related-static-and-scenario-gates", "mutation-check", "scope-and-byte-fingerprints"),
    "core": (
        "nine-regression-groups",
        "related-static-and-scenario-gates",
        "mutation-check",
        "scope-and-byte-fingerprints",
        "real-process-concurrency-or-state-boundary-coverage",
    ),
}


class TierError(ValueError):
    """The input cannot be classified (bad path, empty change set, invalid rules); the caller must not guess a tier."""


@dataclass(frozen=True)
class Rule:
    rule_id: str
    tier: str
    kind: str
    pattern: str
    reason: str


@dataclass(frozen=True)
class Rules:
    version: str
    sha256: str
    project_prefix: str
    behavior_suffixes: tuple[str, ...]
    unknown_tier: str
    rules: tuple[Rule, ...]


@dataclass(frozen=True)
class PathVerdict:
    path: str
    normalized: str
    tier: str
    rule_ids: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Classification:
    tier: str
    verdicts: tuple[PathVerdict, ...]
    unknown: tuple[str, ...]
    rules_version: str
    rules_sha256: str
    gates: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier,
            "rules_version": self.rules_version,
            "rules_sha256": self.rules_sha256,
            "unknown": list(self.unknown),
            "gates": list(self.gates),
            "paths": [
                {"path": v.path, "normalized": v.normalized, "tier": v.tier, "rules": list(v.rule_ids), "reasons": list(v.reasons)} for v in self.verdicts
            ],
        }


def _rank(tier: str) -> int:
    return TIERS.index(tier)


def load_rules(path: Path | None = None) -> Rules:
    """Read and validate the versioned rules file; any defect is refused instead of being worked around."""

    source = path or RULES_FILE
    try:
        raw = source.read_bytes()
        data = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError) as error:
        raise TierError(f"rules file unreadable: {error}") from error
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise TierError(f"rules file schema is not {SCHEMA}")
    if data.get("tiers") != list(TIERS):
        raise TierError("rules file tiers differ from the four tiers of the rule document")
    if data.get("unknown_tier") != "core":
        raise TierError("an unknown path must be reviewed as core")
    version = data.get("version")
    prefix = data.get("project_prefix")
    suffixes = data.get("behavior_suffixes")
    entries = data.get("rules")
    if not isinstance(version, str) or not version or not isinstance(prefix, str) or not isinstance(suffixes, list) or not isinstance(entries, list) or not entries:
        raise TierError("rules file misses version, project_prefix, behavior_suffixes or rules")
    if not all(isinstance(item, str) and item.startswith(".") and item == item.lower() for item in suffixes):
        raise TierError("behavior_suffixes must be lower-case suffixes starting with a dot")
    rules: list[Rule] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise TierError("a rule is not an object")
        rule_id, tier, kind, pattern, reason = (entry.get(key) for key in ("id", "tier", "kind", "pattern", "reason"))
        if not all(isinstance(item, str) and item for item in (rule_id, tier, kind, pattern, reason)):
            raise TierError(f"rule {rule_id!r} misses a field")
        assert isinstance(rule_id, str) and isinstance(tier, str) and isinstance(kind, str) and isinstance(pattern, str) and isinstance(reason, str)
        if rule_id in seen:
            raise TierError(f"duplicate rule id {rule_id}")
        seen.add(rule_id)
        if tier not in TIERS:
            raise TierError(f"rule {rule_id} has an unknown tier {tier!r}")
        if kind not in MATCH_KINDS:
            raise TierError(f"rule {rule_id} has an unknown match kind {kind!r}")
        if "\\" in pattern or pattern.startswith("/"):
            raise TierError(f"rule {rule_id} pattern must be a relative path with forward slashes")
        rules.append(Rule(rule_id, tier, kind, pattern, reason))
    return Rules(version, hashlib.sha256(raw).hexdigest(), prefix, tuple(suffixes), "core", tuple(rules))


def normalize_path(raw: str, project_prefix: str = "") -> str:
    """Make one changed path comparable: forward slashes, no ``./``, no duplicate separators, project prefix removed. Absolute paths and ``..`` are refused."""

    if not isinstance(raw, str) or not raw.strip() or "\x00" in raw:
        raise TierError(f"empty or invalid path: {raw!r}")
    text = raw.strip().replace("\\", "/")
    if text.startswith("/") or (len(text) > 1 and text[1] == ":"):
        raise TierError(f"absolute path is not a repository-relative change: {raw!r}")
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise TierError(f"parent traversal in path: {raw!r}")
    if not parts:
        raise TierError(f"empty path: {raw!r}")
    result = "/".join(parts)
    if project_prefix and result.casefold().startswith(project_prefix.casefold()):
        result = result[len(project_prefix) :]
        if not result:
            raise TierError(f"path names only the project folder: {raw!r}")
    return result


def _matches(rule: Rule, normalized: str) -> bool:
    folded, pattern = normalized.casefold(), rule.pattern.casefold()
    base = folded.rsplit("/", 1)[-1]
    if rule.kind == "prefix":
        return folded.startswith(pattern)
    if rule.kind == "exact":
        return folded == pattern
    if rule.kind == "basename":
        return base == pattern
    return base.startswith(pattern)


def classify_path(raw: str, rules: Rules) -> PathVerdict:
    normalized = normalize_path(raw, rules.project_prefix)
    matched = [rule for rule in rules.rules if _matches(rule, normalized)]
    if not matched:
        return PathVerdict(raw, normalized, rules.unknown_tier, ("UNKNOWN_PATH",), ("no rule matches this path; it is reviewed as core",))
    tier = max((rule.tier for rule in matched), key=_rank)
    top = [rule for rule in matched if rule.tier == tier]
    rule_ids = tuple(rule.rule_id for rule in top)
    reasons = tuple(rule.reason for rule in top)
    suffix = "." + normalized.rsplit(".", 1)[-1].casefold() if "." in normalized.rsplit("/", 1)[-1] else ""
    if tier == "docs" and suffix in rules.behavior_suffixes:
        return PathVerdict(raw, normalized, "product", rule_ids + ("BEHAVIOR_SUFFIX_IN_DOCS",), reasons + (f"a {suffix} file can change behavior, so it is not plain documentation",))
    return PathVerdict(raw, normalized, tier, rule_ids, reasons)


def classify_paths(paths: list[str], rules: Rules) -> Classification:
    """The tier of a change is the highest tier among its paths. An empty change set is refused (nothing to classify is not 'docs')."""

    if not paths:
        raise TierError("empty change set: there is nothing to classify")
    seen: set[str] = set()
    verdicts: list[PathVerdict] = []
    for raw in paths:
        verdict = classify_path(raw, rules)
        if verdict.normalized.casefold() in seen:
            continue
        seen.add(verdict.normalized.casefold())
        verdicts.append(verdict)
    tier = max((verdict.tier for verdict in verdicts), key=_rank)
    unknown = tuple(verdict.normalized for verdict in verdicts if "UNKNOWN_PATH" in verdict.rule_ids)
    return Classification(tier, tuple(verdicts), unknown, rules.version, rules.sha256, GATES[tier])


def check_declared(declared: str, classification: Classification) -> list[str]:
    """Problems with the tier a card declares: it may equal or exceed the computed tier, never undercut it (rule document section 11)."""

    if declared not in TIERS:
        return [f"declared tier {declared!r} is not one of {', '.join(TIERS)}"]
    if _rank(declared) < _rank(classification.tier):
        suffix = f"; unknown paths: {', '.join(classification.unknown)}" if classification.unknown else ""
        return [f"declared tier {declared} is lower than the computed tier {classification.tier}{suffix}"]
    return []


def required_gates(tier: str) -> tuple[str, ...]:
    if tier not in GATES:
        raise TierError(f"unknown tier {tier!r}")
    return GATES[tier]


def changed_paths_from_git(repo: Path, base: str, head: str | None = "HEAD", include_untracked: bool = False) -> list[str]:
    """Paths changed between ``base`` and ``head`` (or the working tree when ``head`` is None). Renames are reported as the old path removed and the new path added."""

    command = ["git", "-C", str(repo), "-c", "core.quotePath=false", "diff", "--name-status", "-z", "--no-renames", base]
    if head is not None:
        command.append(head)
    done = subprocess.run(command, capture_output=True, check=False)
    if done.returncode != 0:
        raise TierError(f"git diff failed: {done.stderr.decode('utf-8', errors='replace').strip()}")
    tokens = done.stdout.decode("utf-8", errors="strict").split("\x00")
    paths: list[str] = []
    index = 0
    while index + 1 < len(tokens) and tokens[index]:
        paths.append(tokens[index + 1])
        index += 2
    if include_untracked:
        other = subprocess.run(
            ["git", "-C", str(repo), "-c", "core.quotePath=false", "ls-files", "--others", "--exclude-standard", "-z"], capture_output=True, check=False
        )
        if other.returncode != 0:
            raise TierError(f"git ls-files failed: {other.stderr.decode('utf-8', errors='replace').strip()}")
        paths.extend(item for item in other.stdout.decode("utf-8", errors="strict").split("\x00") if item)
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify the tier of a change from its real paths.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--paths", nargs="+", help="changed paths, relative to the project or the control root")
    source.add_argument("--diff", nargs="+", metavar=("BASE", "HEAD"), help="classify git diff BASE HEAD (HEAD defaults to the working tree when omitted)")
    parser.add_argument("--repo", type=Path, default=Path("."), help="repository for --diff")
    parser.add_argument("--untracked", action="store_true", help="include untracked files with --diff")
    parser.add_argument("--declared", help="the tier the card declares; refused if lower than the computed tier")
    parser.add_argument("--rules", type=Path, default=None, help="rules file (default: tier_core_list.json next to this module)")
    args = parser.parse_args(argv)
    try:
        rules = load_rules(args.rules)
        if args.paths is not None:
            paths = list(args.paths)
        else:
            base = args.diff[0]
            head = args.diff[1] if len(args.diff) > 1 else None
            paths = changed_paths_from_git(args.repo, base, head, args.untracked)
        result = classify_paths(paths, rules)
    except TierError as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 3
    problems = check_declared(args.declared, result) if args.declared else []
    output = result.to_dict()
    output["declared"] = args.declared
    output["problems"] = problems
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 2 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
