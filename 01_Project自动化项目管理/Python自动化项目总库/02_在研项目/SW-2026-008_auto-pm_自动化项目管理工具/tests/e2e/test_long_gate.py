"""scripts/long_gate.py with real processes: decoupled launch, in-process renewal, resume by step.

Every runner here is a real separate Python process; the "AI session" is a real parent process that is killed.
"""

from __future__ import annotations

import importlib.util
import json
import os
import signal
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "long_gate.py"
PY = sys.executable

FAKE_RENEW = r"""
import datetime as dt, json, sys
from pathlib import Path
d = Path(sys.argv[1])
if (d / "renew_fail").exists():
    print("lease is gone", file=sys.stderr); sys.exit(1)
n = int((d / "renew_count").read_text()) + 1 if (d / "renew_count").exists() else 1
(d / "renew_count").write_text(str(n))
left = 300 if (d / "renew_short").exists() else 3600
exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=left)
print(json.dumps({"run_id": "RUN-X", "owner_id": "o", "version": n + 1, "expires_at": exp.isoformat()}))
"""

# A step that appends one line per start to a counter file, then sleeps until a release file exists (or N s).
STEP = r"""
import sys, time
from pathlib import Path
d, name, wait = Path(sys.argv[1]), sys.argv[2], float(sys.argv[3])
with open(d / f"runs_{name}.log", "a") as f: f.write("run\n")
print(f"step {name} output")
end = time.time() + wait
while time.time() < end and not (d / f"release_{name}").exists():
    time.sleep(0.1)
sys.exit(int(sys.argv[4]) if len(sys.argv) > 4 else 0)
"""


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("long_gate_under_test", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def lab(tmp_path: Path) -> dict[str, Path]:
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "renew.py").write_text(FAKE_RENEW, encoding="utf-8")
    (tools / "step.py").write_text(STEP, encoding="utf-8")
    wt = tmp_path / "candidate"
    wt.mkdir()
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@x", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@x")
    subprocess.run(["git", "init", "-q", str(wt)], check=True, env=env)
    (wt / "a.txt").write_text("frozen\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(wt), "add", "."], check=True, env=env)
    subprocess.run(["git", "-C", str(wt), "commit", "-qm", "base"], check=True, env=env)
    return {"root": tmp_path, "tools": tools, "wt": wt, "out": tmp_path / "out"}


def _config(lab: dict[str, Path], steps: list[dict[str, Any]], *, interval: int = 1, name: str = "drill") -> Path:
    cfg = {
        "name": name,
        "python": PY,
        "out_dir": str(lab["out"]),
        "poll_s": 1,
        "lease": {"mode": "command", "argv": [PY, str(lab["tools"] / "renew.py"), str(lab["tools"])],
                  "renew_interval_s": interval},
        "fingerprint": {"git_worktree": str(lab["wt"])},
        "markers": {"done": {"DONE": "done\n", "gates_all.exit": "{exit}\n"},
                    "failed": {"FAILED": "failed\n", "gates_all.exit": "{exit}\n"}},
        "steps": steps,
    }
    path = lab["root"] / "gate.json"
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return path


def _step(lab: dict[str, Path], name: str, wait: float = 0.0, code: int = 0, **extra: Any) -> dict[str, Any]:
    return {"name": name, "argv": ["{python}", str(lab["tools"] / "step.py"), str(lab["tools"]), name, str(wait), str(code)],
            "cwd": str(lab["wt"]), **extra}


def _run(cfg: Path, *args: str, timeout: int = 120, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([PY, "-B", str(SCRIPT), *args, "--config", str(cfg)], capture_output=True, text=True,
                          timeout=timeout, check=False, env=env)


def _start(cfg: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen([PY, "-B", str(SCRIPT), "run", "--config", str(cfg)], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=(os.name != "nt"))


def _wait_for(pred: Any, timeout: float = 60) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return
        time.sleep(0.2)
    raise AssertionError("condition not reached in time")


def _state(lab: dict[str, Path]) -> dict[str, Any]:
    return json.loads((lab["out"] / "long_gate_state.json").read_text(encoding="utf-8"))


def _runs(lab: dict[str, Path], name: str) -> int:
    p = lab["tools"] / f"runs_{name}.log"
    return len(p.read_text().splitlines()) if p.exists() else 0


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:  # a zombie is dead for our purpose
        return "Z" not in Path(f"/proc/{pid}/stat").read_text().split()[2]
    except OSError:
        return True


def _kill(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=False)
    else:
        os.kill(pid, signal.SIGKILL)


def test_full_round_writes_the_run_g2_layout_and_renews_first(lab: dict[str, Path]) -> None:
    cfg = _config(lab, [_step(lab, "rest"), _step(lab, "cli", code=1, dir="g2"),
                        {"name": "ALL_DONE", "write": "done\n", "dir": "g2"}])
    r = _run(cfg, "run")
    assert r.returncode == 0, r.stderr
    out = lab["out"]
    assert (out / "rest.exit").read_text() == "0\n"
    assert (out / "g2" / "cli.exit").read_text() == "1\n"  # a failed group is a result for the judge, not a stop
    assert "step cli output" in (out / "g2" / "cli.txt").read_text()
    for suffix in ("started", "finished"):
        assert len((out / f"rest.{suffix}").read_text().strip()) == 19
    assert (out / "DONE").exists() and (out / "gates_all.exit").read_text() == "0\n"
    log = (out / "long_gate.log").read_text()
    assert log.index("first renewal ok") < log.index("step rest start")
    assert _state(lab)["result"] == "DONE"


def test_session_killed_runner_keeps_going(lab: dict[str, Path]) -> None:
    """The 10-23 failure: the session's process tree is torn down. `launch` must leave nothing in that tree."""

    cfg = _config(lab, [_step(lab, "rest", wait=60), _step(lab, "core")], interval=2)
    session = subprocess.Popen([PY, "-B", str(SCRIPT), "launch", "--config", str(cfg), "--wait", "60"],
                               stdout=subprocess.PIPE, text=True, start_new_session=(os.name != "nt"))
    _wait_for(lambda: _runs(lab, "rest") == 1)
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(session.pid)], capture_output=True, check=False)
    else:
        os.killpg(session.pid, signal.SIGKILL)  # the whole "session" process group
    session.wait(timeout=30)
    count = int((lab["tools"] / "renew_count").read_text())
    _wait_for(lambda: int((lab["tools"] / "renew_count").read_text()) >= count + 2, timeout=30)  # renewals go on
    (lab["tools"] / "release_rest").write_text("")
    _wait_for(lambda: (lab["out"] / "DONE").exists())
    assert _state(lab)["result"] == "DONE"
    assert _runs(lab, "rest") == 1 and _runs(lab, "core") == 1


def test_runner_killed_mid_step_resumes_only_the_unfinished_step(lab: dict[str, Path]) -> None:
    cfg = _config(lab, [_step(lab, "rest"), _step(lab, "core", wait=120), _step(lab, "judge", stop_on_fail=True)])
    runner = _start(cfg)
    _wait_for(lambda: _runs(lab, "core") == 1)
    rest_started = (lab["out"] / "rest.started").read_text()
    child = _state(lab)["steps"]["core"]["child_pid"]
    _kill(runner.pid)
    runner.wait(timeout=30)
    _wait_for(lambda: not _pid_alive(child), timeout=30)  # the group dies with its runner; no orphan writes on
    (lab["tools"] / "release_core").write_text("")
    r = _run(cfg, "run")
    assert r.returncode == 0, r.stderr
    st = _state(lab)
    assert st["resumes"] == 1 and st["result"] == "DONE"
    assert _runs(lab, "rest") == 1 and _runs(lab, "core") == 2 and _runs(lab, "judge") == 1
    assert (lab["out"] / "rest.started").read_text() == rest_started
    assert (lab["out"] / "core.interrupted.1.txt").exists()
    assert st["steps"]["core"]["interruptions"][0]["kept_as"] == "core.interrupted.1.txt"


def test_resume_refused_when_candidate_bytes_changed(lab: dict[str, Path]) -> None:
    cfg = _config(lab, [_step(lab, "rest"), _step(lab, "core", wait=120)])
    runner = _start(cfg)
    _wait_for(lambda: _runs(lab, "core") == 1)
    _kill(runner.pid)
    runner.wait(timeout=30)
    (lab["wt"] / "a.txt").write_text("edited after the group ran\n", encoding="utf-8")
    r = _run(cfg, "run")
    assert r.returncode == 4
    assert "bytes differ" in r.stderr
    time.sleep(0.5)
    assert _runs(lab, "core") == 1


def test_resume_refused_when_config_changed(lab: dict[str, Path]) -> None:
    cfg = _config(lab, [_step(lab, "rest"), _step(lab, "core", wait=120)])
    runner = _start(cfg)
    _wait_for(lambda: _runs(lab, "core") == 1)
    _kill(runner.pid)
    runner.wait(timeout=30)
    _config(lab, [_step(lab, "rest"), _step(lab, "core", wait=1)])
    r = _run(cfg, "run")
    assert r.returncode == 4 and "config changed" in r.stderr


def test_first_renewal_must_succeed(lab: dict[str, Path]) -> None:
    (lab["tools"] / "renew_fail").write_text("")
    cfg = _config(lab, [_step(lab, "rest")])
    r = _run(cfg, "run")
    assert r.returncode == 5
    assert _runs(lab, "rest") == 0
    assert (lab["out"] / "FAILED").exists() and (lab["out"] / "gates_all.exit").read_text() == "5\n"
    assert _run(cfg, "run").returncode == 5 and _runs(lab, "rest") == 0  # final: never re-run


def test_renewal_failure_mid_run_is_a_final_hard_stop(lab: dict[str, Path]) -> None:
    cfg = _config(lab, [_step(lab, "rest", wait=120), _step(lab, "core")], interval=1)
    runner = _start(cfg)
    _wait_for(lambda: _runs(lab, "rest") == 1)
    child = _state(lab)["steps"]["rest"]["child_pid"]
    (lab["tools"] / "renew_fail").write_text("")
    assert runner.wait(timeout=60) == 6
    _wait_for(lambda: not _pid_alive(child), timeout=30)
    st = _state(lab)
    assert st["result"] == "HARD_STOP_LEASE" and "renewal failed" in st["reason"]
    assert not (lab["out"] / "rest.exit").exists()
    (lab["tools"] / "renew_fail").unlink()
    assert _run(cfg, "run").returncode == 6 and _runs(lab, "rest") == 1 and _runs(lab, "core") == 0


def test_lease_below_ten_minutes_is_a_hard_stop(lab: dict[str, Path]) -> None:
    (lab["tools"] / "renew_short").write_text("")
    cfg = _config(lab, [_step(lab, "rest", wait=120)], interval=600)
    runner = _start(cfg)
    assert runner.wait(timeout=60) == 6
    assert "s left" in _state(lab)["reason"]


def test_stop_file_stops_and_the_round_resumes(lab: dict[str, Path]) -> None:
    cfg = _config(lab, [_step(lab, "rest"), _step(lab, "core", wait=120)])
    runner = _start(cfg)
    _wait_for(lambda: _runs(lab, "core") == 1)
    assert _run(cfg, "stop").returncode == 0
    assert runner.wait(timeout=60) == 7
    (lab["tools"] / "release_core").write_text("")
    assert _run(cfg, "run").returncode == 0
    assert _runs(lab, "rest") == 1 and _runs(lab, "core") == 2


def test_failed_stop_on_fail_step_is_final(lab: dict[str, Path]) -> None:
    cfg = _config(lab, [_step(lab, "fast", code=3, stop_on_fail=True), _step(lab, "rest")])
    assert _run(cfg, "run").returncode == 1
    assert _run(cfg, "run").returncode == 1
    assert _runs(lab, "fast") == 1 and _runs(lab, "rest") == 0
    assert (lab["out"] / "FAILED").exists()


def test_second_runner_on_the_same_round_is_refused(lab: dict[str, Path]) -> None:
    cfg = _config(lab, [_step(lab, "rest", wait=120)])
    runner = _start(cfg)
    _wait_for(lambda: _runs(lab, "rest") == 1)
    assert _run(cfg, "run").returncode == 3
    assert "ALREADY RUNNING" in _run(cfg, "launch").stdout
    status = json.loads(_run(cfg, "status").stdout)
    assert status["runner_alive"] is True and status["current_step"] == "rest"
    assert status["lease"]["version"] >= 2
    _kill(runner.pid)
    runner.wait(timeout=30)


def test_auto_pm_renewal_never_writes_the_token(lab: dict[str, Path]) -> None:
    import sqlite3

    root = lab["root"] / "control"
    (root / ".auto-pm").mkdir(parents=True)
    con = sqlite3.connect(root / ".auto-pm" / "continuity.db")
    con.execute("create table execution_leases (run_id text, version integer)")
    con.execute("insert into execution_leases values ('RUN-SW008-X-001', 7)")
    con.commit()
    con.close()
    token = "tok-SECRET-0123456789abcdef"
    (lab["root"] / "token.txt").write_text(token + "\n", encoding="utf-8")
    # A fake main.py that checks what the real CLI is given, then tries to leak the token on both streams.
    (root / "main.py").write_text(
        "import datetime as dt, json, os, sys\n"
        "a = sys.argv[1:]\n"
        "assert a[:3] == ['continuity', 'lease', 'renew'], a\n"
        "assert a[a.index('--expected-version') + 1] == '7'\n"
        "assert a[a.index('--idempotency-key') + 1] == 'run-sw008-x-001-renew-v7'\n"
        "assert os.environ[a[a.index('--lease-token-env') + 1]] == open('../token.txt').read().strip()\n"
        "assert not any('SECRET' in x for x in a)\n"
        "print('token=' + os.environ['LONG_GATE_LEASE_TOKEN'], file=sys.stderr)\n"
        "exp = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat()\n"
        "print(json.dumps({'run_id': 'RUN-SW008-X-001', 'owner_id': 'o', 'version': 8, 'expires_at': exp,"
        " 'note': os.environ['LONG_GATE_LEASE_TOKEN']}))\n",
        encoding="utf-8",
    )
    cfg_path = _config(lab, [{"name": "env", "argv": ["{python}", "-c",
                              "import os; print('LONG_GATE_LEASE_TOKEN' in os.environ)"]}])
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["root"] = str(root)
    cfg["lease"] = {"mode": "auto_pm", "run_id": "RUN-SW008-X-001", "owner": "o",
                    "token_file": str(lab["root"] / "token.txt"), "renew_interval_s": 1200}
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    # Even a token already in the runner's own environment must not reach a group.
    r = _run(cfg_path, "run", env=dict(os.environ, LONG_GATE_LEASE_TOKEN=token))
    assert r.returncode == 0, (lab["out"] / "long_gate.log").read_text()
    assert (lab["out"] / "env.txt").read_text().strip() == "False"  # steps never inherit the token
    for f in lab["out"].iterdir():
        if f.is_file():
            assert token not in f.read_text(encoding="utf-8", errors="replace"), f.name
    assert "renewal ok version=8" in (lab["out"] / "long_gate.log").read_text()


def test_task_xml_runs_on_battery_at_normal_priority_without_trigger() -> None:
    mod = _module()
    xml = mod.task_xml(r"C:\WS\.venv\Scripts\pythonw.exe", '-B "C:\\a b\\long_gate.py" run --config "C:\\中文\\g.json"',
                       r"C:\WS\out", r"PC\fubai")
    root = ET.fromstring(xml.split("?>", 1)[1])
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    get = lambda path: root.find(path, ns).text  # noqa: E731
    assert get("t:Settings/t:DisallowStartIfOnBatteries") == "false"
    assert get("t:Settings/t:StopIfGoingOnBatteries") == "false"
    assert get("t:Settings/t:Priority") == "4"
    assert get("t:Settings/t:ExecutionTimeLimit") == "PT12H"
    assert get("t:Principals/t:Principal/t:LogonType") == "InteractiveToken"
    assert root.find("t:Triggers", ns) is None
    assert "中文" in get("t:Actions/t:Exec/t:Arguments")


def test_config_validation_rejects_relative_out_dir(tmp_path: Path) -> None:
    mod = _module()
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"name": "x", "out_dir": "rel", "steps": [{"name": "a", "argv": ["x"]}]}), encoding="utf-8")
    with pytest.raises(mod.GateError):
        mod.load_config(p)
