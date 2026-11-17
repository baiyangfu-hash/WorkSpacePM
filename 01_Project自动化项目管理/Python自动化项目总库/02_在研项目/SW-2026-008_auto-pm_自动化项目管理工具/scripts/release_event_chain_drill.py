"""Event-chain drill for a release candidate (release deploy self-check, D-146 card 4; moved into the repo by CHG-SCPT-2026-706).

Called by ``release deploy`` / ``release ship`` as ``python -B -I <this file> <candidate release dir> <scratch root>``: reads a copy of
the canonical continuity database with the candidate's own code and prints one JSON object (events_total, chain_breaks,
run_activity_fail, ...).  Read-only on the copy.  Same logic as the original .auto-pm/reports/m2-gov-dep1/tools/drill.py (card 023
V0.4 §6, G3 drill), only reformatted.
"""

from __future__ import annotations

import collections
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any


def main(candidate: str, root: str) -> dict[str, Any]:
    sys.path.insert(0, candidate)
    from auto_pm.infrastructure.continuity_store import ContinuityStore

    db = Path(root) / ".auto-pm" / "continuity.db"
    res: dict[str, Any] = {}
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT rowid,* FROM events ORDER BY rowid").fetchall()
    prev = ""
    breaks = 0
    census: collections.Counter[str] = collections.Counter()
    schemas: dict[str, set[str]] = collections.defaultdict(set)
    for r in rows:
        payload = json.loads(r["payload_json"])
        canon = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(
            f"{prev}|{r['aggregate_id']}|{r['event_type']}|{canon}|{r['created_at']}".encode()
        ).hexdigest()
        if r["previous_hash"] != prev or r["event_hash"] != digest:
            breaks += 1
        prev = r["event_hash"]
        census[r["event_type"]] += 1
        schemas[r["event_type"]].add(str(payload.get("schema_version")))
    runs = [r["run_id"] for r in conn.execute("SELECT run_id FROM run_items ORDER BY rowid")]
    conn.close()
    for suffix in ("-wal", "-shm"):
        side = str(db) + suffix
        if os.path.exists(side):
            os.remove(side)
    res["events_total"] = len(rows)
    res["chain_breaks"] = breaks
    res["census"] = {k: {"count": census[k], "schemas": sorted(schemas[k])} for k in sorted(census)}
    store = ContinuityStore(root, db)
    ok = 0
    fails: list[tuple[str, str, str]] = []
    for run_id in runs:
        try:
            store.list_run_activities(run_id)
            ok += 1
        except Exception as error:  # recorded, never swallowed silently
            fails.append((run_id, type(error).__name__, str(error)))
    res["runs_total"] = len(runs)
    res["run_activity_ok"] = ok
    res["run_activity_fail"] = fails
    try:
        works = store.list_works("SW-2026-008", include_terminal=True)
        res["works_read"] = len(works)
        res["works_by_state"] = dict(collections.Counter(w.state.value for w in works))
        res["runs_read_via_works"] = sum(
            len(store.list_runs(w.work_id, include_terminal=True)) for w in works
        )
    except Exception as error:
        res["work_run_read_error"] = f"{type(error).__name__}: {error}"
    try:
        res["missions_read"] = len(store.list_missions("SW-2026-008", include_terminal=True))
    except Exception as error:
        lines = str(error).splitlines()
        res["mission_read_error"] = (
            f"{type(error).__name__}: {lines[0] if lines else ''} | {lines[1] if len(lines) > 1 else ''}"
        )
    return res


if __name__ == "__main__":
    print(json.dumps(main(sys.argv[1], sys.argv[2]), ensure_ascii=False, indent=2, default=str))
