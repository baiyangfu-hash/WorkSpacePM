"""Split the Windows "core" test group into shards that run in parallel (one CI job each).

usage: core_shards.py <shard>      print the pytest arguments of that shard (space separated)
       core_shards.py --check      verify the split itself (used by the CI self-test)

Why: the single windows-cli-core job took 36 to 58 minutes against a 60-minute timeout.  The shards are
built so that no test can be left out by accident:

* ``drill`` and the explicit lists below name files that are known to be slow, measured as seconds of test time
  on Linux.  Weights are for balancing only.
* ``rest`` is computed, not listed: every ``tests/core/test_*.py`` that no explicit shard names, so a new test
  file lands in ``rest`` automatically and an explicit file that was renamed or deleted is an error (exit 1),
  never a silently smaller run.
Stdlib only; run from the project root (the directory that holds ``tests/``).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# name -> test files (relative to the project root, forward slashes)
EXPLICIT: dict[str, tuple[str, ...]] = {
    # ~520 s: the two sample drills (the long-gate drill script runs in the same job, see the workflow)
    "drill": (
        "tests/e2e/test_closure_drill.py",
        "tests/e2e/test_closure_drill_agent_misconduct.py",
    ),
    # ~480 s
    "heavy": (
        "tests/core/test_continuity_execution_service.py",
        "tests/core/test_pm_run_e2e.py",
        "tests/e2e/test_long_gate.py",
        "tests/core/test_pr_open_service.py",
        "tests/core/test_continuity_resume_service.py",
    ),
    # ~460 s
    "mid": (
        "tests/core/test_docs_checkpoint_chain.py",
        "tests/core/test_work_registry_service.py",
        "tests/core/test_cockpit_api.py",
        "tests/core/test_pm_facade_service.py",
        "tests/core/test_legacy_terminal_lease_fence.py",
        "tests/core/test_pm_cockpit_service.py",
        "tests/core/test_agent_worktree_service.py",
        "tests/core/test_plc_checkpoint_chain.py",
        "tests/core/test_mission_switch_service.py",
        "tests/core/test_mission_park_store.py",
        "tests/core/test_evidence_collection_service.py",
    ),
}
REST = "rest"
SHARDS = (*EXPLICIT, REST)


def core_test_files(root: Path = ROOT) -> list[str]:
    """Every test file under tests/core, as forward-slash paths relative to ``root``."""
    return sorted(p.relative_to(root).as_posix() for p in (root / "tests" / "core").rglob("test_*.py"))


def problems(root: Path = ROOT) -> list[str]:
    """What is wrong with the split; an empty list means every core test runs in exactly one shard."""
    found: list[str] = []
    seen: dict[str, str] = {}
    for shard, files in EXPLICIT.items():
        for name in files:
            if not (root / name).is_file():
                found.append(f"{shard}: {name} does not exist (renamed or deleted: fix the list in core_shards.py)")
            if name in seen:
                found.append(f"{name} is listed in both {seen[name]} and {shard}")
            seen[name] = shard
    leftover = [n for n in core_test_files(root) if n not in seen]
    if not leftover:
        found.append("the rest shard would be empty")
    return found


def arguments(shard: str) -> list[str]:
    """The pytest arguments of one shard."""
    if shard in EXPLICIT:
        return list(EXPLICIT[shard])
    if shard == REST:
        named = {n for files in EXPLICIT.values() for n in files}
        return ["tests/core", *(f"--ignore={n}" for n in sorted(named) if n.startswith("tests/core/"))]
    raise KeyError(shard)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    wanted = argv[0]
    bad = problems()
    if bad:
        print("core shard split is broken:\n  " + "\n  ".join(bad), file=sys.stderr)
        return 1
    if wanted == "--check":
        print("core shards ok:", ", ".join(f"{s}={len(arguments(s))}" for s in SHARDS))
        return 0
    if wanted not in SHARDS:
        print(f"unknown shard {wanted!r}; one of {', '.join(SHARDS)}", file=sys.stderr)
        return 2
    print(" ".join(arguments(wanted)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
