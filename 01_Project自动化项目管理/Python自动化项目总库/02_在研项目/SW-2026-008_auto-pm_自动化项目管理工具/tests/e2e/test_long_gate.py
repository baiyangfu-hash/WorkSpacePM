"""scripts/long_gate.py with real processes: decoupled launch, in-process renewal, resume by step.

Every runner here is a real separate Python process; the "AI session" is a real parent process that is killed.
"""

from __future__ import annotations

import importlib.util
import json
import locale
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
import datetime as dt, json, sys, time
from pathlib import Path
d = Path(sys.argv[1])
if (d / "renew_fail").exists():
    print("lease is gone", file=sys.stderr); sys.exit(1)
n = int((d / "renew_count").read_text()) + 1 if (d / "renew_count").exists() else 1
tmp = d / "renew_count.tmp"
tmp.write_text(str(n))
for _ in range(50):  # atomic: a reader never sees the file truncated mid-write
    try:
        tmp.replace(d / "renew_count")
        break
    except PermissionError:  # Windows: the target is open in the reader at this instant
        time.sleep(0.02)
else:
    tmp.replace(d / "renew_count")
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


def _drill() -> ModuleType:
    spec = importlib.util.spec_from_file_location("long_gate_drill_under_test", SCRIPT.with_name("long_gate_drill.py"))
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_console_tool_output_in_the_console_code_page_is_read_not_dropped(monkeypatch: pytest.MonkeyPatch) -> None:
    # 2026-10-24: on a Chinese Windows with PYTHONUTF8=1, text=True could not decode tasklist's GBK output, stdout came
    # back as None and the liveness check raised TypeError. The bytes below are what such a tasklist prints.
    drill = _drill()
    gbk = '"映像名称","PID","会话名"\r\n"python.exe","1234","Console"\r\n'.encode("gbk")
    monkeypatch.setattr(drill.locale, "getencoding", lambda: "gbk")
    monkeypatch.setattr(drill.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=gbk, stderr=b""))
    text = drill.console_text(["tasklist"])
    assert '"1234"' in text
    assert "映像名称" in text  # a utf-8 decode would turn the GBK header into replacement characters
    monkeypatch.setattr(drill, "WIN", True)
    assert drill.alive(1234)
    assert not drill.alive(4321)
    # Undecodable bytes are replaced, never an exception or a None.
    monkeypatch.setattr(drill.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=b"\xd0\xff\xfe 99", stderr=b""))
    assert "99" in drill.console_text(["tasklist"])
    monkeypatch.setattr(drill.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 1, stdout=None, stderr=b""))
    assert drill.console_text(["tasklist"]) == ""


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


def _config(
    lab: dict[str, Path], steps: list[dict[str, Any]], *, interval: int = 1, name: str = "drill", remove: list[str] | None = None
) -> Path:
    cfg = {
        "name": name,
        "python": PY,
        "out_dir": str(lab["out"]),
        **({"root": str(lab["root"])} if remove else {}),
        "poll_s": 1,
        "lease": {"mode": "command", "argv": [PY, str(lab["tools"] / "renew.py"), str(lab["tools"])],
                  "renew_interval_s": interval},
        "fingerprint": {"git_worktree": str(lab["wt"])},
        "markers": {"done": {"DONE": "done\n", "gates_all.exit": "{exit}\n"},
                    "failed": {"FAILED": "failed\n", "gates_all.exit": "{exit}\n"}, **({"remove": remove} if remove else {})},
        "steps": steps,
    }
    path = lab["root"] / "gate.json"
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return path


def _step(lab: dict[str, Path], name: str, wait: float = 0.0, code: int = 0, **extra: Any) -> dict[str, Any]:
    return {"name": name, "argv": ["{python}", str(lab["tools"] / "step.py"), str(lab["tools"]), name, str(wait), str(code)],
            "cwd": str(lab["wt"]), **extra}


def _run(cfg: Path, *args: str, timeout: int = 120, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([PY, "-B", str(SCRIPT), *args, "--config", str(cfg)], capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, check=False, env=env)


def _start(cfg: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen([PY, "-B", str(SCRIPT), "run", "--config", str(cfg)], stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=(os.name != "nt"))


def _wait_for(pred: Any, timeout: float = 60) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            if pred():
                return
        except (OSError, ValueError):  # a counter file being replaced reads as missing/empty for an instant
            pass
        time.sleep(0.2)
    raise AssertionError("condition not reached in time")


def _state(lab: dict[str, Path]) -> dict[str, Any]:
    return json.loads((lab["out"] / "long_gate_state.json").read_text(encoding="utf-8"))


def _runs(lab: dict[str, Path], name: str) -> int:
    p = lab["tools"] / f"runs_{name}.log"
    return len(p.read_text().splitlines()) if p.exists() else 0


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        # Bytes, then the console code page: text=True under PYTHONUTF8=1 cannot decode GBK and returns None.
        raw = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True).stdout or b""
        return str(pid) in raw.decode(locale.getencoding(), errors="replace")
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
                               stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", start_new_session=(os.name != "nt"))
    _wait_for(lambda: _runs(lab, "rest") == 1)
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(session.pid)], capture_output=True, check=False)
    else:
        os.killpg(session.pid, signal.SIGKILL)  # the whole "session" process group
    session.wait(timeout=30)
    counts: list[int] = []
    _wait_for(lambda: counts.append(int((lab["tools"] / "renew_count").read_text())) or True)
    count = counts[0]
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


def test_interval_must_leave_the_ten_minute_floor(tmp_path: Path) -> None:
    mod = _module()
    p = tmp_path / "c.json"
    base = {"name": "x", "out_dir": str(tmp_path / "o"), "steps": [{"name": "a", "argv": ["x"]}],
            "fingerprint": {"git_worktree": str(tmp_path)},
            "lease": {"mode": "command", "argv": ["x"], "lease_seconds": 3600, "renew_interval_s": 3000}}
    p.write_text(json.dumps(base), encoding="utf-8")
    with pytest.raises(mod.GateError, match="floor"):
        mod.load_config(p)
    base["lease"]["renew_interval_s"] = 2940
    p.write_text(json.dumps(base), encoding="utf-8")
    mod.load_config(p)


def test_a_due_renewal_runs_before_the_floor_is_judged(tmp_path: Path) -> None:
    import datetime as dt
    import threading

    mod = _module()

    class FakeLease:
        cfg = {"renew_interval_s": 1}

        def __init__(self) -> None:
            self.expires_at = mod.utc_now() + dt.timedelta(seconds=590)  # below the floor, renewal due

        def remaining_s(self) -> float:
            return (self.expires_at - mod.utc_now()).total_seconds()

        def renew(self) -> None:
            self.expires_at = mod.utc_now() + dt.timedelta(seconds=3600)

    hard, stop = threading.Event(), threading.Event()
    keeper = mod.LeaseKeeper(FakeLease(), hard, stop, mod.Log(tmp_path / "log"))
    keeper.start()
    time.sleep(3)
    stop.set()
    keeper.join(timeout=5)
    assert not hard.is_set(), keeper.reason


def test_concurrent_status_writes_do_not_crash(tmp_path: Path) -> None:
    import threading

    mod = _module()
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"name": "x", "out_dir": str(tmp_path / "o"), "steps": [{"name": "a", "argv": ["x"]}],
                             "fingerprint": {"git_worktree": str(tmp_path)}}), encoding="utf-8")
    cfg, sha = mod.load_config(p)
    runner = mod.Runner(cfg, sha)
    runner.out.mkdir(parents=True)
    errors: list[BaseException] = []

    def hammer() -> None:
        try:
            for _ in range(200):
                runner.write_status()
        except BaseException as error:  # noqa: BLE001
            errors.append(error)

    threads = [threading.Thread(target=hammer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert json.loads((runner.out / "long_gate_status.json").read_text(encoding="utf-8"))["name"] == "x"


def test_fingerprint_is_required(tmp_path: Path) -> None:
    mod = _module()
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"name": "x", "out_dir": str(tmp_path / "o"), "steps": [{"name": "a", "argv": ["x"]}]}),
                 encoding="utf-8")
    with pytest.raises(mod.GateError, match="fingerprint"):
        mod.load_config(p)


def test_a_failed_group_is_not_rerun_on_resume(lab: dict[str, Path]) -> None:
    cfg = _config(lab, [_step(lab, "plc", code=1), _step(lab, "core", wait=120)])
    runner = _start(cfg)
    _wait_for(lambda: _runs(lab, "core") == 1)
    _kill(runner.pid)
    runner.wait(timeout=30)
    (lab["tools"] / "release_core").write_text("")
    assert _run(cfg, "run").returncode == 0
    assert _runs(lab, "plc") == 1 and _runs(lab, "core") == 2
    assert (lab["out"] / "plc.exit").read_text() == "1\n"
    assert json.loads(_run(cfg, "status").stdout)["failed_steps"] == ["plc"]


def test_a_hung_group_times_out_as_a_failed_group(lab: dict[str, Path]) -> None:
    cfg = _config(lab, [_step(lab, "core", wait=3600, timeout_s=3), _step(lab, "judge")])
    r = _run(cfg, "run")
    assert r.returncode == 0  # the round goes on; the judge sees the failure
    st = _state(lab)
    assert st["steps"]["core"]["exit"] == 124 and st["steps"]["core"]["timed_out"] is True
    assert (lab["out"] / "core.exit").read_text() == "124\n"
    assert _runs(lab, "judge") == 1
    assert _run(cfg, "run").returncode == 0 and _runs(lab, "core") == 1  # never re-run as if unfinished


def test_the_round_has_a_total_time_limit(lab: dict[str, Path]) -> None:
    cfg_path = _config(lab, [_step(lab, "core", wait=3600), _step(lab, "judge")])
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["round_timeout_s"] = 10
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    start = time.time()
    r = _run(cfg_path, "run", timeout=180)
    assert r.returncode == 8 and time.time() - start < 60
    assert _state(lab)["result"] == "ROUND_TIMEOUT" and (lab["out"] / "FAILED").exists()
    assert _runs(lab, "judge") == 0
    assert _run(cfg_path, "run").returncode == 8 and _runs(lab, "core") == 1  # final


@pytest.mark.skipif(os.name == "nt", reason="uses a fake schtasks on PATH; the Windows drill deletes the real task")
def test_the_task_is_deleted_once_the_round_is_final(lab: dict[str, Path]) -> None:
    bindir = lab["root"] / "bin"
    bindir.mkdir()
    fake = bindir / "schtasks"
    fake.write_text(f"#!/bin/sh\necho \"$@\" >> '{lab['tools'] / 'schtasks.log'}'\n", encoding="utf-8")
    fake.chmod(0o755)
    cfg = _config(lab, [_step(lab, "rest")])
    env = dict(os.environ, PATH=f"{bindir}{os.pathsep}{os.environ['PATH']}")
    r = subprocess.run([PY, "-B", str(SCRIPT), "run", "--config", str(cfg), "--task-name", "WSPM-LongGate-drill"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=120, check=False)
    assert r.returncode == 0
    assert (lab["tools"] / "schtasks.log").read_text().split() == ["/Delete", "/TN", "WSPM-LongGate-drill", "/F"]
    assert "scheduled task WSPM-LongGate-drill deleted" in (lab["out"] / "long_gate.log").read_text()


def test_partial_output_held_open_is_copied_aside(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows: a killed grandchild can still hold the output for a moment; a rename that keeps failing becomes a copy."""

    mod = _module()
    src, dst = tmp_path / "core.txt", tmp_path / "core.interrupted.1.txt"
    src.write_text("half a group\n", encoding="utf-8")

    def refuse(self: Path, target: Path) -> Path:
        raise PermissionError("held open")

    monkeypatch.setattr(Path, "rename", refuse)
    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    mod._keep_partial(src, dst, mod.Log(tmp_path / "log"))
    assert dst.read_text(encoding="utf-8") == "half a group\n"
    assert "copied to core.interrupted.1.txt" in (tmp_path / "log").read_text(encoding="utf-8")


@pytest.mark.parametrize("code", [0, 1])
def test_a_heavy_round_marker_is_removed_when_the_round_ends_whatever_the_verdict(lab: dict[str, Path], code: int) -> None:
    """TD-SW008-205：启动脚本留下的 HEAVY_GATES_RUNNING 一类标记，由结束的这一轮清掉（有组失败也清）。"""
    marker = lab["root"] / "HEAVY_GATES_RUNNING"
    marker.write_text("run=RUN-X\n", encoding="utf-8")
    cfg = _config(lab, [_step(lab, "s", code=code)], remove=[str(marker)])

    _run(cfg, "run")

    assert not marker.exists()
    assert "removed leftover marker" in (lab["out"] / "long_gate.log").read_text(encoding="utf-8")


def test_the_marker_stays_while_the_round_is_still_running_and_a_missing_one_is_fine(lab: dict[str, Path]) -> None:
    marker = lab["root"] / "HEAVY_RUNNING"
    cfg = _config(lab, [_step(lab, "slow", wait=3.0)], remove=[str(marker), str(lab["root"] / "never_existed")])
    marker.write_text("run=RUN-X\n", encoding="utf-8")
    proc = _start(cfg)
    try:
        _wait_for(lambda: (lab["out"] / "slow.started").exists())
        assert marker.exists()
        assert proc.wait(timeout=60) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
    assert not marker.exists()


@pytest.mark.parametrize("bad", ["relative/marker", "../escape", "/etc/passwd"])
def test_markers_remove_refuses_paths_outside_the_workspace(lab: dict[str, Path], bad: str) -> None:
    cfg = _config(lab, [_step(lab, "s")], remove=[bad])
    result = _run(cfg, "run")
    assert result.returncode != 0 and "markers.remove" in (result.stdout + result.stderr)


def _symlink_or_skip(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("this machine cannot create symbolic links")


def test_markers_remove_refuses_dotdot_inside_an_absolute_path(lab: dict[str, Path]) -> None:
    cfg = _config(lab, [_step(lab, "s")], remove=[str(lab["root"] / "sub" / ".." / "HEAVY_GATES_RUNNING")])
    result = _run(cfg, "run")
    assert result.returncode != 0 and "markers.remove" in (result.stdout + result.stderr)


def test_markers_remove_refuses_a_link_that_points_outside_the_workspace(lab: dict[str, Path], tmp_path_factory: pytest.TempPathFactory) -> None:
    outside = tmp_path_factory.mktemp("outside") / "precious.txt"
    outside.write_text("keep\n", encoding="utf-8")
    _symlink_or_skip(lab["root"] / "HEAVY_GATES_RUNNING", outside)
    cfg = _config(lab, [_step(lab, "s")], remove=[str(lab["root"] / "HEAVY_GATES_RUNNING")])

    result = _run(cfg, "run")

    assert result.returncode != 0 and "markers.remove" in (result.stdout + result.stderr)
    assert outside.read_text(encoding="utf-8") == "keep\n"


def test_a_link_planted_after_the_config_check_never_deletes_outside_files(lab: dict[str, Path], tmp_path_factory: pytest.TempPathFactory) -> None:
    outside = tmp_path_factory.mktemp("outside") / "precious.txt"
    outside.write_text("keep\n", encoding="utf-8")
    marker = lab["root"] / "HEAVY_GATES_RUNNING"
    cfg = _config(lab, [_step(lab, "slow", wait=3.0)], remove=[str(marker)])
    proc = _start(cfg)
    try:
        _wait_for(lambda: (lab["out"] / "slow.started").exists())
        _symlink_or_skip(marker, outside)
        assert proc.wait(timeout=60) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
    assert outside.read_text(encoding="utf-8") == "keep\n"
    assert "resolves outside the workspace" in (lab["out"] / "long_gate.log").read_text(encoding="utf-8")


def test_the_marker_stays_when_the_round_is_only_stopped(lab: dict[str, Path]) -> None:
    marker = lab["root"] / "HEAVY_GATES_RUNNING"
    marker.write_text("run=RUN-X\n", encoding="utf-8")
    cfg = _config(lab, [_step(lab, "core", wait=120)], remove=[str(marker)])
    runner = _start(cfg)
    _wait_for(lambda: _runs(lab, "core") == 1)
    assert _run(cfg, "stop").returncode == 0
    assert runner.wait(timeout=60) == 7
    assert marker.exists()


def test_a_directory_is_never_removed(lab: dict[str, Path]) -> None:
    folder = lab["root"] / "HEAVY_DIR"
    folder.mkdir()
    (folder / "keep.txt").write_text("x", encoding="utf-8")
    cfg = _config(lab, [_step(lab, "s")], remove=[str(folder)])
    assert _run(cfg, "run").returncode == 0
    assert (folder / "keep.txt").exists()


def test_a_marker_that_cannot_be_deleted_is_only_logged(lab: dict[str, Path]) -> None:
    # A read-only parent makes the unlink fail on POSIX; elsewhere (Windows, root) there is no cheap way to force it.
    if os.name == "nt" or os.geteuid() == 0:
        pytest.skip("cannot make a delete fail on this machine without an open handle")
    stuck = lab["root"] / "locked" / "HEAVY_STUCK"
    stuck.parent.mkdir()
    stuck.write_text("x", encoding="utf-8")
    cfg = _config(lab, [_step(lab, "s")], remove=[str(stuck)])
    stuck.parent.chmod(0o500)
    try:
        result = _run(cfg, "run")
    finally:
        stuck.parent.chmod(0o700)
    assert result.returncode == 0 and stuck.exists()
    assert "not removed" in (lab["out"] / "long_gate.log").read_text(encoding="utf-8")
