"""D-03: a gate whose lease hold cannot cover the round plus the closing is refused at launch; the closing runs by the gate itself.

Card 225 item 6.  The 2026-11-04 round ran 4 h 57 min under a 5 h hold, the closing window was 3 minutes, nobody closed it overnight and the
lease ran out at 02:24.  Real runner processes, a real (small) ledger file for the hold cap, fake renewals.
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from auto_pm.infrastructure.continuity_store import LEASE_HOLD_CAP_SECONDS
from tests.e2e import test_long_gate as _base
from tests.e2e.test_long_gate import PY, _config, _module, _run, _state

lab = _base.lab  # the same candidate-worktree fixture the other long-gate tests use
RUN_ID = "RUN-SW008-X-001"
FAKE_MAIN = (
    "import datetime as dt, json, sys\n"
    "exp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat()\n"
    "print(json.dumps({'version': 8, 'expires_at': exp}))\n"
)


def _ledger(root: Path, *, run_age_s: float, extended_s: int = 0) -> None:
    (root / ".auto-pm").mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(root / ".auto-pm" / "continuity.db")
    con.execute("create table execution_leases (run_id text, version integer)")
    con.execute("insert into execution_leases values (?, 7)", (RUN_ID,))
    con.execute("create table run_items (run_id text, created_at text)")
    created = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=run_age_s)
    con.execute("insert into run_items values (?, ?)", (RUN_ID, created.isoformat()))
    con.execute(
        "create table events (aggregate_type text, aggregate_id text, event_type text, payload_json text)"
    )
    if extended_s:
        con.execute(
            "insert into events values ('run', ?, 'LEASE_HOLD_EXTENDED', ?)",
            (RUN_ID, json.dumps({"extra_seconds": extended_s})),
        )
    con.commit()
    con.close()


def _gate(
    lab: dict[str, Path],
    *,
    run_age_s: float,
    extended_s: int = 0,
    extra: dict[str, Any] | None = None,
    lease_extra: dict[str, Any] | None = None,
) -> Path:
    root = lab["root"] / "control"
    _ledger(root, run_age_s=run_age_s, extended_s=extended_s)
    (root / "main.py").write_text(FAKE_MAIN, encoding="utf-8")
    (lab["root"] / "token.txt").write_text("tok\n", encoding="utf-8")
    path = _config(lab, [{"name": "ok", "argv": ["{python}", "-c", "print(1)"]}])
    cfg = json.loads(path.read_text(encoding="utf-8"))
    cfg["root"] = str(root)
    cfg["lease"] = {
        "mode": "auto_pm",
        "run_id": RUN_ID,
        "owner": "o",
        "token_file": str(lab["root"] / "token.txt"),
        "renew_interval_s": 1200,
        **(lease_extra or {}),
    }
    cfg.update(extra or {})
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


def test_the_mirrored_hold_cap_is_the_ledgers_hold_cap() -> None:
    assert _module().LEASE_HOLD_CAP_S == LEASE_HOLD_CAP_SECONDS


def test_a_round_that_leaves_no_room_to_close_is_refused_before_any_step(
    lab: dict[str, Path],
) -> None:
    # Run is 2 h 50 min old: 10 min of hold left.  A 4 h round (with no approved extension) cannot be closed.
    cfg = _gate(lab, run_age_s=2 * 3600 + 3000, extra={"expected_duration_s": 4 * 3600})
    r = _run(cfg, "run")
    assert r.returncode == 4, r.stdout + r.stderr
    assert "lease hold ends" in r.stderr
    assert not (lab["out"] / "ok.exit").exists()
    assert _state(lab)["refusals"]


def test_the_refusal_comes_with_launch_too_and_starts_nothing(
    lab: dict[str, Path], capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _gate(lab, run_age_s=2 * 3600 + 3000, extra={"expected_duration_s": 4 * 3600})
    module = _module()
    monkeypatch.setattr(module, "_memory_preflight_refusal", lambda: "")
    monkeypatch.setattr(module, "_launch_windows", lambda *a: pytest.fail("must not start"))
    monkeypatch.setattr(module, "_launch_posix", lambda *a: pytest.fail("must not start"))
    assert module.cmd_launch(cfg, 1) == 4
    assert "REFUSED: the lease hold ends" in capsys.readouterr().out


def test_the_planned_extension_counts_toward_the_margin(lab: dict[str, Path]) -> None:
    cfg = _gate(
        lab,
        run_age_s=2 * 3600 + 3000,
        extra={"expected_duration_s": 4 * 3600},
        lease_extra={"dispatch_approval_ref": "user-confirmation:msg-42"},
    )
    module = _module()
    loaded, _ = module.load_config(cfg)
    assert (
        module.hold_margin_refusal(loaded) == ""
    )  # 10 min + 10 h planned extension covers 4 h + closing + 30 min


def test_an_extension_already_in_the_ledger_is_not_counted_twice(lab: dict[str, Path]) -> None:
    cfg = _gate(
        lab,
        run_age_s=2 * 3600 + 3000,
        extended_s=10 * 3600,
        extra={"expected_duration_s": 11 * 3600},
        lease_extra={"dispatch_approval_ref": "user-confirmation:msg-42"},
    )
    module = _module()
    loaded, _ = module.load_config(cfg)
    assert "lease hold ends" in module.hold_margin_refusal(loaded)  # 10 min + 10 h only, not +20 h


def test_without_an_expected_duration_nothing_is_judged_and_the_log_says_so(
    lab: dict[str, Path],
) -> None:
    cfg = _gate(lab, run_age_s=2 * 3600 + 3000)
    assert _run(cfg, "run").returncode == 0
    assert "close-window margin was not checked" in (lab["out"] / "long_gate.log").read_text(
        encoding="utf-8"
    )


def test_an_unreadable_hold_cap_is_a_refusal_not_a_pass(lab: dict[str, Path]) -> None:
    cfg = _gate(lab, run_age_s=60, extra={"expected_duration_s": 600})
    (lab["root"] / "control" / ".auto-pm" / "continuity.db").unlink()
    r = _run(cfg, "run")
    assert r.returncode == 4
    assert "cannot read the Run's lease hold cap" in r.stderr


@pytest.mark.parametrize(
    "bad",
    [
        {"expected_duration_s": 5},
        {"expected_duration_s": True},
        {"closing_estimate_s": -1},
        {"closing": {"argv": []}},
        {"closing": {"argv": ["x"], "timeout_s": 1}},
    ],
)
def test_bad_close_window_settings_are_refused_at_load(
    lab: dict[str, Path], bad: dict[str, Any]
) -> None:
    cfg = _gate(lab, run_age_s=60, extra=bad)
    module = _module()
    with pytest.raises(module.GateError):
        module.load_config(cfg)


def test_the_gate_runs_the_closing_itself_after_the_verdict(lab: dict[str, Path]) -> None:
    marker = lab["root"] / "closed.marker"
    closing = {"argv": [PY, "-c", f"open({str(marker)!r}, 'w').write('x')"]}
    cfg = _gate(
        lab,
        run_age_s=60,
        extra={"closing": closing},
        lease_extra={"hold_until_marker": str(marker)},
    )
    assert _run(cfg, "run").returncode == 0
    assert marker.exists()
    state = _state(lab)
    assert (
        state["result"] == "DONE"
        and state["closing"]["status"] == "done"
        and state["closing"]["exit"] == 0
    )
    status = json.loads((lab["out"] / "long_gate_status.json").read_text(encoding="utf-8"))
    assert status["closing"]["status"] == "done"


def test_a_failed_closing_keeps_the_scene_and_does_not_change_the_verdict(
    lab: dict[str, Path],
) -> None:
    closing = {"argv": [PY, "-c", "import sys; print('boom'); sys.exit(3)"]}
    cfg = _gate(lab, run_age_s=60, extra={"closing": closing})
    assert _run(cfg, "run").returncode == 0
    state = _state(lab)
    assert (
        state["result"] == "DONE"
        and state["closing"]["status"] == "failed"
        and state["closing"]["exit"] == 3
    )
    assert "boom" in (lab["out"] / "closing.txt").read_text(encoding="utf-8")
    assert "scene kept" in (lab["out"] / "long_gate.log").read_text(encoding="utf-8")
    assert (lab["out"] / "ok.exit").exists()  # the group results are untouched


def test_a_closing_that_hangs_is_cut_off_and_reported(lab: dict[str, Path]) -> None:
    closing = {"argv": [PY, "-c", "import time; time.sleep(60)"], "timeout_s": 10}
    cfg = _gate(lab, run_age_s=60, extra={"closing": closing})
    assert _run(cfg, "run", timeout=90).returncode == 0
    assert _state(lab)["closing"]["status"] == "timeout"


def test_a_short_hold_at_the_end_is_flagged_close_window_low(lab: dict[str, Path]) -> None:
    cfg = _gate(
        lab, run_age_s=3 * 3600 - 20 * 60
    )  # 20 min of hold left when the (instant) round ends
    assert _run(cfg, "run").returncode == 0
    state = _state(lab)
    assert state["warning"] == "CLOSE_WINDOW_LOW"
    assert (
        json.loads((lab["out"] / "long_gate_status.json").read_text(encoding="utf-8"))["warning"]
        == "CLOSE_WINDOW_LOW"
    )


def test_a_comfortable_hold_is_not_flagged(lab: dict[str, Path]) -> None:
    cfg = _gate(lab, run_age_s=60)
    assert _run(cfg, "run").returncode == 0
    assert _state(lab).get("warning") is None
