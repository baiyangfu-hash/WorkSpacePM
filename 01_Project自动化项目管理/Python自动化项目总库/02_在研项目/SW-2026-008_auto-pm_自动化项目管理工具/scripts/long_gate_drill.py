"""长门禁主机的“中途杀会话”演练（Windows 上可复现 10-23 的故障，并证明新做法躲得开）

不碰账本、不碰真门禁：用一个假续租脚本和三段假“组”，全部放在临时目录。约 2 分钟。

    python -B scripts/long_gate_drill.py            # 打印每一项 PASS/FAIL，全过退出 0

它做五件事：
1. 旧做法对照：在一个“假会话”进程里用后台方式起一个长任务，然后整棵杀掉“假会话”；
   长任务跟着没了（Windows 上这就是 10-23 的现象；Linux 上 nohup 本来就能躲开，只记录不判）。
2. 新做法：在另一个“假会话”里运行 `long_gate.py launch`（Windows 上登记计划任务），整棵杀掉“假会话”；
   门禁进程还活着、续租还在继续、防休眠在位（Windows），它的父进程不是“假会话”。
3. 把门禁进程本身强杀在第 2 组中间：第 2 组的子进程跟着死，不留孤儿继续写文件。
4. 再 `launch` 一次：第 1 组不重跑，第 2 组从头重跑、半截输出留档，第 3 组跑完，结果 DONE。
5. 门禁拿到最终结果后自己删掉那个一次性计划任务（Windows 上核对）；演练收尾时兜底再删一次本演练建的那一个。
"""

# ruff: noqa: T201
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
GATE = HERE / "long_gate.py"
PY = sys.executable
WIN = os.name == "nt"

RENEW = r"""
import datetime as dt, json, sys
from pathlib import Path
d = Path(sys.argv[1])
n = int((d / "renew_count").read_text()) + 1 if (d / "renew_count").exists() else 1
(d / "renew_count").write_text(str(n))
exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
print(json.dumps({"version": n + 1, "expires_at": exp.isoformat()}))
"""

STEP = r"""
import sys, time
from pathlib import Path
d, name, wait = Path(sys.argv[1]), sys.argv[2], float(sys.argv[3])
with open(d / f"runs_{name}.log", "a") as f: f.write("run\n")
print(f"group {name} output", flush=True)
end = time.time() + wait
while time.time() < end and not (d / f"release_{name}").exists():
    time.sleep(0.2)
"""

LEGACY = r"""
import sys, time
from pathlib import Path
p = Path(sys.argv[1])
for _ in range(600):
    p.write_text(str(time.time()))
    time.sleep(0.5)
"""

results: list[tuple[bool, str]] = []


def check(ok: bool, what: str) -> bool:
    results.append((ok, what))
    print(f"{'PASS' if ok else 'FAIL'}  {what}", flush=True)
    return ok


def wait_for(pred: Any, timeout: float) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        try:
            if pred():
                return True
        except (OSError, ValueError):
            pass
        time.sleep(0.5)
    return False


def alive(pid: int) -> bool:
    if WIN:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"], capture_output=True,
                             text=True, check=False).stdout
        return f'"{pid}"' in out
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    try:
        return Path(f"/proc/{pid}/stat").read_text().split()[2] != "Z"
    except OSError:
        return True


def parent_name(pid: int) -> str:
    if WIN:
        ps = (f"$p=(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').ParentProcessId;"
              "(Get-CimInstance Win32_Process -Filter \"ProcessId=$p\").Name")
        return subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True,
                              check=False).stdout.strip() or "(parent gone)"
    try:
        ppid = int(Path(f"/proc/{pid}/stat").read_text().split()[3])
        return Path(f"/proc/{ppid}/comm").read_text().strip()
    except OSError:
        return "?"


# Windows: the stand-in session puts itself in a kill-on-close Job Object, then runs the command and stays up.
# Killing it closes the job, which kills everything started under it, detached or not: the way a session host
# can reap a session's work (a plain tree kill misses a process whose parent has already exited).
SESSION_WRAPPER = r"""
import ctypes, subprocess, sys, time
sys.path.insert(0, sys.argv[1])
import long_gate
job = long_gate._win_job()
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
k32.GetCurrentProcess.restype = ctypes.c_void_p
if not k32.AssignProcessToJobObject(job, ctypes.c_void_p(k32.GetCurrentProcess())):
    sys.exit(f"stand-in session could not join its job (error {ctypes.get_last_error()})")
subprocess.call(sys.argv[2:])
time.sleep(600)
"""


def session(argv: list[str]) -> subprocess.Popen[bytes]:
    """A stand-in for the AI session whose whole tree (Windows: whole job) we kill."""

    if WIN:
        return subprocess.Popen([PY, "-c", SESSION_WRAPPER, str(HERE), *argv],
                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return subprocess.Popen(argv, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def kill_tree(p: subprocess.Popen[bytes]) -> None:
    if WIN:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, check=False)
    else:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    p.wait(timeout=30)


def kill(pid: int) -> None:
    if WIN:
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=False)
    else:
        os.kill(pid, signal.SIGKILL)


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="long_gate_drill_"))
    tools, out, wt = work / "tools", work / "out", work / "candidate"
    tools.mkdir()
    (tools / "renew.py").write_text(RENEW, encoding="utf-8")
    (tools / "step.py").write_text(STEP, encoding="utf-8")
    (tools / "legacy.py").write_text(LEGACY, encoding="utf-8")
    wt.mkdir()
    genv = dict(os.environ, GIT_AUTHOR_NAME="d", GIT_AUTHOR_EMAIL="d@x", GIT_COMMITTER_NAME="d", GIT_COMMITTER_EMAIL="d@x")
    subprocess.run(["git", "init", "-q", str(wt)], check=True, env=genv)
    (wt / "frozen.txt").write_text("frozen candidate\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(wt), "add", "."], check=True, env=genv)
    subprocess.run(["git", "-C", str(wt), "commit", "-qm", "candidate"], check=True, env=genv)
    print(f"drill folder: {work}")

    def step(name: str, wait: float) -> dict[str, Any]:
        return {"name": name, "argv": ["{python}", str(tools / "step.py"), str(tools), name, str(wait)], "cwd": str(wt)}

    name = f"drill-{os.getpid()}"
    cfg = {
        "name": name, "python": PY, "out_dir": str(out), "poll_s": 2,
        "lease": {"mode": "command", "argv": [PY, str(tools / "renew.py"), str(tools)], "renew_interval_s": 5},
        "fingerprint": {"git_worktree": str(wt)},
        "markers": {"done": {"DONE": "done\n"}, "failed": {"FAILED": "failed\n"}},
        "steps": [step("rest", 300), step("core", 300), step("judge", 0)],
    }
    cfg_path = work / "drill.json"
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    launch = [PY, "-B", str(GATE), "launch", "--config", str(cfg_path), "--wait", "90"]

    def runs(n: str) -> int:
        p = tools / f"runs_{n}.log"
        return len(p.read_text().splitlines()) if p.exists() else 0

    def status() -> dict[str, Any]:
        return json.loads((out / "long_gate_status.json").read_text(encoding="utf-8"))

    try:
        # 1. the old way, for comparison
        beat = tools / "legacy_beat.txt"
        if WIN:
            legacy = session(["cmd", "/c", "start", "/b", PY, str(tools / "legacy.py"), str(beat)])
        else:
            legacy = session(["sh", "-c", f"nohup '{PY}' '{tools / 'legacy.py'}' '{beat}' >/dev/null 2>&1 &  sleep 600"])
        wait_for(beat.exists, 30)
        kill_tree(legacy)
        last = beat.stat().st_mtime
        time.sleep(5)
        still = beat.stat().st_mtime > last
        check(not still, "old way: a background job started from the session dies when the session's process tree "
              "is killed (the 10-23 fault; nohup does not help)")

        # 2. the new way: launch from a session, kill the session's whole tree
        s1 = session(launch)
        ok = wait_for(lambda: runs("rest") == 1 and status()["current_step"] == "rest", 120)
        check(ok, "launch started the runner and group 1 is running")
        if not ok:
            return 1
        runner = int(status()["pid"])
        kill_tree(s1)
        time.sleep(3)
        check(alive(runner), f"session killed: the runner (pid {runner}) is still alive")
        parent = parent_name(runner)
        if WIN:
            check(parent.lower() in ("svchost.exe", "taskeng.exe", "taskhostw.exe"),
                  f"the runner's parent is the Task Scheduler service, not the session (parent: {parent})")
        else:
            print(f"INFO  runner parent process: {parent}")
        n0 = int((tools / "renew_count").read_text())
        check(wait_for(lambda: int((tools / "renew_count").read_text()) >= n0 + 2, 30),
              "session killed: lease renewals continue inside the runner")
        if WIN:
            check(status()["keep_awake"] == "on", "keep-awake is held by the runner itself")
        (tools / "release_rest").write_text("")
        check(wait_for(lambda: runs("core") == 1, 60), "group 1 finished on its own, group 2 started")

        # 3. kill the runner itself in the middle of group 2
        state = json.loads((out / "long_gate_state.json").read_text(encoding="utf-8"))
        child = int(state["steps"]["core"]["child_pid"])
        kill(runner)
        check(wait_for(lambda: not alive(child), 30), "runner killed: its group-2 child died with it (no orphan)")

        # 4. resume from another session, which is killed again
        s2 = session(launch)
        check(wait_for(lambda: runs("core") == 2, 120), "relaunch: group 2 runs again from the start")
        kill_tree(s2)
        (tools / "release_core").write_text("")
        check(wait_for(lambda: (out / "DONE").exists(), 120), "relaunch: the round reaches DONE")
        check(runs("rest") == 1, "group 1 was not re-run")
        check((out / "core.interrupted.1.txt").exists(), "the half-run group 2 output is kept as core.interrupted.1.txt")
        check((out / "judge.exit").read_text() == "0\n", "group 3 ran once with its result written")
        if WIN:
            gone = wait_for(lambda: subprocess.run(["schtasks", "/Query", "/TN", f"WSPM-LongGate-{name}"],
                                                   capture_output=True, check=False).returncode != 0, 30)
            check(gone, "the one-off scheduled task deleted itself after the final result")
    finally:
        if WIN:
            subprocess.run(["schtasks", "/Delete", "/TN", f"WSPM-LongGate-{name}", "/F"], capture_output=True, check=False)
        (out / "STOP").write_text("drill cleanup") if out.exists() else None

    failed = [w for ok, w in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} PASS" + ("" if not failed else f"; FAILED: {failed}"))
    print(f"drill folder kept for the record: {work}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
