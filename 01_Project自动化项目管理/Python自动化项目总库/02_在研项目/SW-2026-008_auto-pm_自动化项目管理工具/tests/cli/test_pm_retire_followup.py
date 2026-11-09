"""D-141 (part 2): the renamed JSON fields of ``pm retire`` (``mission_ids`` / ``mission_states``) are lists, in all three places."""

from __future__ import annotations

import json
from pathlib import Path

from tests.cli.test_pm_retire import PROJECT, _run, root  # noqa: F401  (``root`` is a fixture)
from tests.core.test_retire_service import _mission


def _json(output: str) -> dict[str, object]:
    payload: dict[str, object] = json.loads(output[output.index("{") : output.rindex("}") + 1])
    return payload


def test_preview_apply_result_and_trace_all_list_every_mission(root: Path) -> None:  # noqa: F811
    first = _mission(root, "WORK-OLD", suffix="-A")
    second = _mission(root, "WORK-OLD", suffix="-B", activate=False)
    both = sorted([first, second])

    preview = _json(_run(root, "--stale").output)
    leftover = preview["leftovers"][0]  # type: ignore[index]
    assert leftover["work_id"] == "WORK-OLD"
    assert sorted(leftover["mission_ids"]) == both
    assert len(leftover["mission_states"]) == 2 and set(leftover["mission_states"]) == {"ACTIVE", "AWAITING_APPROVAL"}

    applied = _json(_run(root, "--stale", "--apply").output)
    result = applied["results"][0]  # type: ignore[index]
    assert isinstance(result["mission_ids"], list) and sorted(result["mission_ids"]) == both
    recorded = json.loads(Path(str(applied["trace"])).read_text(encoding="utf-8"))
    assert sorted(recorded["results"][0]["mission_ids"]) == both
    assert PROJECT in json.dumps(recorded)
