"""长门禁主机：把一轮长门禁（九组回归等）交给一个与 AI 会话无关的独立进程

为什么：2026-10-23 卡 184 的正式门禁由 AI 会话在后台起（nohup、WMI 都试过），会话被收起时
门禁、续租循环、防休眠三件事一起被带走，租约过期，整轮作废。

本脚本做三件事，判据一条不改：
1. 启动与会话解耦：``launch`` 在 Windows 上登记一个一次性计划任务并立即运行它，门禁进程的
   父进程是计划任务服务，不在 AI 会话的进程树里；会话断开、收起、重启都碰不到它。
2. 续租和防休眠在门禁进程自己里面（两个线程），不靠外部循环。首次续租必须成功才开跑；
   续租失败或租约剩余不足 10 分钟按硬停止处理（停当前组、保留现场、不可续跑）。
3. 按组断点续跑：每组跑完记下结果和跑完时候选工作树的指纹。进程意外没了（断电、重启、
   被误杀）再起时，跑完的组一律不重跑（失败的也不重跑，结果照原样交给判卷），只重跑
   没跑完的那一组，前提是配置逐字节不变、工作树指纹与上一组跑完时相同、同一个租约仍然有效。

输出布局与 run_g2.sh 相同（<组>.txt / .exit / .started / .finished），现有判卷脚本不用改。

用法：
    python -B scripts/long_gate.py launch --config <配置.json>   # 起门禁（Windows：计划任务）
    python -B scripts/long_gate.py status --config <配置.json>   # 看进度（只读）
    python -B scripts/long_gate.py stop   --config <配置.json>   # 请它停下（停当前组，可续跑）
    python -B scripts/long_gate.py run    --config <配置.json>   # 门禁进程本体（launch 调用）
"""

# ruff: noqa: T201
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import hashlib
import json
import os
import re
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

IS_WINDOWS = os.name == "nt"
SCHEMA = 1
STATE_FILE = "long_gate_state.json"
STATUS_FILE = "long_gate_status.json"
LOG_FILE = "long_gate.log"
LOCK_FILE = "long_gate.lock"
STOP_FILE = "STOP"
TOKEN_ENV = "LONG_GATE_LEASE_TOKEN"
MIN_REMAINING_S = 600
NAME_RE = re.compile(r"[A-Za-z0-9_.-]{1,64}")

# Final results are never re-run; the others resume on the next `run`.
FINAL = {"DONE", "FAILED", "HARD_STOP_LEASE", "LEASE_FAILED_AT_START"}
EXIT_CODES = {
    "DONE": 0,
    "FAILED": 1,
    "LOCKED": 3,
    "REFUSED": 4,
    "LEASE_FAILED_AT_START": 5,
    "HARD_STOP_LEASE": 6,
    "STOPPED": 7,
}


class GateError(Exception):
    pass


def _say(msg: str) -> None:
    # Under pythonw (how the scheduled task runs it) there is no console: sys.stderr is None.
    if sys.stderr is not None:
        print(msg, file=sys.stderr)


# ── config ───────────────────────────────────────────────


def load_config(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    cfg = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(cfg, dict):
        raise GateError("config must be a JSON object")
    name = cfg.get("name")
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise GateError("config.name must be 1-64 of A-Z a-z 0-9 _ . -")
    cfg.setdefault("python", sys.executable)
    cfg.setdefault("root", "")
    subst = {"python": str(cfg["python"]), "root": str(cfg["root"])}

    def fill(value: str) -> str:
        return value.replace("{python}", subst["python"]).replace("{root}", subst["root"])

    out_dir = cfg.get("out_dir")
    if not isinstance(out_dir, str) or not Path(fill(out_dir)).is_absolute():
        raise GateError("config.out_dir must be an absolute path")
    cfg["out_dir"] = fill(out_dir)

    steps = cfg.get("steps")
    if not isinstance(steps, list) or not steps:
        raise GateError("config.steps must be a non-empty list")
    seen: set[str] = set()
    for step in steps:
        if not isinstance(step, dict):
            raise GateError("every step must be an object")
        sname = step.get("name")
        if not isinstance(sname, str) or not NAME_RE.fullmatch(sname):
            raise GateError(f"bad step name: {sname!r}")
        key = f"{step.get('dir', '')}/{sname}"
        if key in seen:
            raise GateError(f"duplicate step: {key}")
        seen.add(key)
        if ("argv" in step) == ("write" in step):
            raise GateError(f"step {sname}: give exactly one of argv or write")
        if "argv" in step:
            argv = step["argv"]
            if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
                raise GateError(f"step {sname}: argv must be a non-empty list of strings")
            step["argv"] = [fill(a) for a in argv]
            step["cwd"] = fill(step.get("cwd", cfg["root"] or cfg["out_dir"]))
        else:
            write = step["write"]
            if not isinstance(write, str):
                raise GateError(f"step {sname}: write must be the text to write")
        d = step.get("dir", "")
        if not isinstance(d, str) or Path(d).is_absolute() or ".." in Path(d).parts:
            raise GateError(f"step {sname}: dir must be relative to out_dir")
        step.setdefault("stop_on_fail", False)
        step["env"] = {**cfg.get("env", {}), **step.get("env", {})}
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in step["env"].items()):
            raise GateError(f"step {sname}: env must map strings to strings")
        step["env"] = {k: fill(v) for k, v in step["env"].items()}

    lease = cfg.setdefault("lease", {"mode": "none"})
    mode = lease.get("mode")
    if mode not in {"auto_pm", "command", "none"}:
        raise GateError("lease.mode must be auto_pm, command or none")
    lease.setdefault("lease_seconds", 3600)
    lease.setdefault("renew_interval_s", 1200)
    if not 1 <= int(lease["renew_interval_s"]) <= 3000:
        raise GateError("lease.renew_interval_s must be 1..3000")
    if not 60 <= int(lease["lease_seconds"]) <= 3600:
        raise GateError("lease.lease_seconds must be 60..3600")
    if mode == "auto_pm":
        for k in ("run_id", "owner"):
            if not isinstance(lease.get(k), str) or not lease[k]:
                raise GateError(f"lease.{k} is required for auto_pm")
        if not cfg["root"]:
            raise GateError("config.root is required for lease mode auto_pm")
        if ("token_file" in lease) == bool(lease.get("wallet")):
            raise GateError("lease: give exactly one of token_file or wallet: true")
        if "token_file" in lease:
            lease["token_file"] = fill(lease["token_file"])
    if mode == "command":
        argv = lease.get("argv")
        if not isinstance(argv, list) or not argv:
            raise GateError("lease.argv is required for command mode")
        lease["argv"] = [fill(a) for a in argv]

    fp = cfg.setdefault("fingerprint", {})
    if fp.get("git_worktree"):
        fp["git_worktree"] = fill(fp["git_worktree"])
    for k in ("done", "failed"):
        cfg.setdefault("markers", {}).setdefault(k, {})
    cfg.setdefault("poll_s", 15)
    return cfg, hashlib.sha256(raw).hexdigest()


# ── small helpers ────────────────────────────────────────


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def iso(t: dt.datetime | None) -> str | None:
    return t.isoformat(timespec="seconds") if t else None


def local_stamp() -> str:
    # Same as `date +%FT%T` in run_g2.sh, so the judge reads what it always read.
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    for attempt in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:  # a reader holds the file open on Windows
            time.sleep(0.1 * (attempt + 1))
    os.replace(tmp, path)


class Log:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    def __call__(self, msg: str) -> None:
        line = f"{iso(utc_now())} {msg}\n"
        with self._lock, open(self._path, "a", encoding="utf-8", newline="\n") as f:
            f.write(line)


def git_bytes(wt: Path, *args: str) -> bytes:
    env = dict(os.environ, GIT_LFS_SKIP_SMUDGE="1", GIT_OPTIONAL_LOCKS="0")
    r = subprocess.run(
        ["git", "-c", "core.quotepath=off", "-C", str(wt), *args],
        capture_output=True,
        env=env,
        check=False,
    )
    if r.returncode != 0:
        raise GateError(f"git {' '.join(args)} failed: {r.stderr.decode(errors='replace').strip()[:300]}")
    return r.stdout


def tree_fingerprint(cfg: dict[str, Any]) -> str | None:
    """HEAD + every changed or untracked (non-ignored) file's bytes in the candidate worktree."""

    wt = cfg["fingerprint"].get("git_worktree")
    if not wt:
        return None
    wtp = Path(wt)
    h = hashlib.sha256(git_bytes(wtp, "rev-parse", "HEAD"))
    status = git_bytes(wtp, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    h.update(status)
    entries = status.split(b"\0")
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        if entry[:1] in (b"R", b"C"):
            i += 1  # the next entry is the rename source
        rel = entry[3:].decode("utf-8", errors="surrogateescape")
        p = wtp / rel
        h.update(entry[3:] + b"\0")
        if p.is_file():
            h.update(hashlib.sha256(p.read_bytes()).digest())
        else:
            h.update(b"<absent>")
    return h.hexdigest()


# ── single instance lock (released by the OS when the process dies) ──


def try_lock(path: Path) -> Any:
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, "a+b")  # noqa: SIM115 - held for the process lifetime
    try:
        if IS_WINDOWS:
            import msvcrt

            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def lock_is_held(path: Path) -> bool:
    if not path.exists():
        return False
    f = try_lock(path)
    if f is None:
        return True
    if IS_WINDOWS:
        import msvcrt

        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    f.close()
    return False


# ── child processes: one kill switch for the whole tree ──


class ChildGroup:
    """Windows: a Job Object with KILL_ON_JOB_CLOSE, so if this runner dies its pytest dies with it and
    can never keep writing into a folder a resumed run is using. POSIX: own session + parent-death signal."""

    def __init__(self) -> None:
        self._job = None
        if IS_WINDOWS:
            self._job = _win_job()

    def popen(self, argv: list[str], cwd: str, env: dict[str, str], out: Any) -> subprocess.Popen[bytes]:
        kwargs: dict[str, Any] = {"cwd": cwd, "env": env, "stdout": out, "stderr": subprocess.STDOUT,
                                  "stdin": subprocess.DEVNULL}
        if IS_WINDOWS:
            kwargs["creationflags"] = 0x08000000 | 0x00000200  # CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
            kwargs["preexec_fn"] = _posix_parent_death_kill
        p = subprocess.Popen(argv, **kwargs)
        if self._job is not None:
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
            k32.AssignProcessToJobObject(self._job, ctypes.c_void_p(int(p._handle)))  # type: ignore[attr-defined]
        return p

    def kill(self, p: subprocess.Popen[bytes]) -> None:
        if IS_WINDOWS:
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
            if self._job is not None:
                k32.TerminateJobObject(self._job, 1)
                self._job = _win_job()
            else:
                p.kill()
        else:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            p.kill()


def _posix_parent_death_kill() -> None:
    try:
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        libc.prctl(1, signal.SIGKILL)  # PR_SET_PDEATHSIG
    except OSError:
        pass


def _win_job() -> Any:
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):  # noqa: N801
        _fields_ = [(n, ctypes.c_ulonglong) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class BASIC(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class EXTENDED(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BASIC),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
    k32.CreateJobObjectW.restype = ctypes.c_void_p
    job = k32.CreateJobObjectW(None, None)
    if not job:
        raise GateError(f"CreateJobObject failed: {ctypes.get_last_error()}")  # type: ignore[attr-defined]
    info = EXTENDED()
    info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k32.SetInformationJobObject(ctypes.c_void_p(job), 9, ctypes.byref(info), ctypes.sizeof(info)):
        raise GateError(f"SetInformationJobObject failed: {ctypes.get_last_error()}")  # type: ignore[attr-defined]
    return ctypes.c_void_p(job)


# ── keep awake (inside this process) ─────────────────────


class KeepAwake(threading.Thread):
    """ES_CONTINUOUS | ES_SYSTEM_REQUIRED, refreshed every 60 s by a thread that lives as long as the runner.
    It does not stop the sleep that closing the lid triggers; the guide says to keep the lid open or set it to do nothing."""

    def __init__(self, stop: threading.Event) -> None:
        super().__init__(name="keep-awake", daemon=True)
        self._stop_evt = stop
        self.state = "unsupported" if not IS_WINDOWS else "starting"

    def run(self) -> None:
        if not IS_WINDOWS:
            return
        f = ctypes.windll.kernel32.SetThreadExecutionState  # type: ignore[attr-defined]
        f.restype = ctypes.c_uint
        f.argtypes = [ctypes.c_uint]
        while not self._stop_evt.is_set():
            self.state = "on" if f(0x80000001) else "failed"
            self._stop_evt.wait(60)
        f(0x80000000)
        self.state = "released"


# ── lease renewal (inside this process) ──────────────────


class Lease:
    def __init__(self, cfg: dict[str, Any], log: Log) -> None:
        self.cfg = cfg["lease"]
        self.root = cfg["root"]
        self.python = cfg["python"]
        self.log = log
        self.version: int | None = None
        self.expires_at: dt.datetime | None = None
        self.last_ok: dt.datetime | None = None
        self.renewals = 0

    @property
    def enabled(self) -> bool:
        return self.cfg["mode"] != "none"

    def remaining_s(self) -> float | None:
        if self.expires_at is None:
            return None
        return (self.expires_at - utc_now()).total_seconds()

    def renew(self) -> None:
        mode = self.cfg["mode"]
        if mode == "none":
            return
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        secret = None
        if mode == "auto_pm":
            version = self._current_version()
            run_id, owner = self.cfg["run_id"], self.cfg["owner"]
            argv = [self.python, "-B", "main.py", "continuity", "lease", "renew", "--run-id", run_id,
                    "--owner", owner, "--expected-version", str(version),
                    "--lease-seconds", str(self.cfg["lease_seconds"]),
                    "--idempotency-key", f"{run_id.lower()}-renew-v{version}"]
            if self.cfg.get("wallet"):
                argv.append("--lease-wallet")
            else:
                secret = Path(self.cfg["token_file"]).read_text(encoding="utf-8").strip()
                env[TOKEN_ENV] = secret
                argv += ["--lease-token-env", TOKEN_ENV]
            cwd = self.root
        else:
            argv, cwd = self.cfg["argv"], self.root or None
        r = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, check=False, timeout=300,
                           creationflags=0x08000000 if IS_WINDOWS else 0)
        out = r.stdout.decode("utf-8", errors="replace")
        if r.returncode != 0:
            tail = (r.stderr.decode("utf-8", errors="replace").strip().splitlines() or [""])[-1]
            raise GateError(f"renewal exit {r.returncode}: {_redact(tail, secret)[:300]}")
        try:
            receipt = json.loads(out[out.index("{"): out.rindex("}") + 1])
            version = int(receipt["version"])
            expires = dt.datetime.fromisoformat(str(receipt["expires_at"]).replace("Z", "+00:00"))
        except (ValueError, KeyError, TypeError) as error:
            raise GateError(f"renewal printed no receipt ({type(error).__name__})") from None
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=dt.UTC)
        self.version, self.expires_at, self.last_ok = version, expires, utc_now()
        self.renewals += 1
        # Only these three facts are logged; the receipt is never copied out whole.
        self.log(f"renewal ok version={version} expires_at={iso(expires)}")

    def _current_version(self) -> int:
        db = Path(self.root) / ".auto-pm" / "continuity.db"
        con = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True, timeout=30)
        try:
            row = con.execute("select version from execution_leases where run_id=?", (self.cfg["run_id"],)).fetchone()
        finally:
            con.close()
        if row is None:
            raise GateError(f"no lease for Run {self.cfg['run_id']}")
        return int(row[0])


def _redact(text: str, secret: str | None) -> str:
    return text.replace(secret, "***") if secret else text


class LeaseKeeper(threading.Thread):
    def __init__(self, lease: Lease, hard_stop: threading.Event, stop: threading.Event, log: Log) -> None:
        super().__init__(name="lease", daemon=True)
        self.lease, self.hard_stop, self._stop_evt, self.log = lease, hard_stop, stop, log
        self.reason: str | None = None
        self.next_at: dt.datetime | None = None

    def run(self) -> None:
        interval = int(self.lease.cfg["renew_interval_s"])
        self.next_at = utc_now() + dt.timedelta(seconds=interval)
        while not self._stop_evt.wait(1):
            remaining = self.lease.remaining_s()
            if remaining is not None and remaining < MIN_REMAINING_S:
                self._trip(f"lease has {int(remaining)} s left (< {MIN_REMAINING_S})")
                return
            if utc_now() >= self.next_at:
                try:
                    self.lease.renew()
                except Exception as error:  # noqa: BLE001 - any failure is a hard stop
                    self._trip(f"renewal failed: {error}")
                    return
                self.next_at = utc_now() + dt.timedelta(seconds=interval)

    def _trip(self, reason: str) -> None:
        self.reason = reason
        self.log(f"HARD STOP: {reason}")
        self.hard_stop.set()


# ── the runner ───────────────────────────────────────────


class Runner:
    def __init__(self, cfg: dict[str, Any], sha: str) -> None:
        self.cfg, self.sha = cfg, sha
        self.out = Path(cfg["out_dir"])
        self.log = Log(self.out / LOG_FILE)
        self.stop_all = threading.Event()
        self.hard_stop = threading.Event()
        self.children = ChildGroup()
        self.lease = Lease(cfg, self.log)
        self.keeper: LeaseKeeper | None = None
        self.awake = KeepAwake(self.stop_all)
        self.state: dict[str, Any] = {}
        self.current: str | None = None

    # state
    def _state_path(self) -> Path:
        return self.out / STATE_FILE

    def save(self) -> None:
        atomic_write(self._state_path(), json.dumps(self.state, ensure_ascii=False, indent=2))

    def write_status(self) -> None:
        steps = self.state.get("steps", {})
        status = {
            "schema": SCHEMA,
            "name": self.cfg["name"],
            "pid": os.getpid(),
            "result": self.state.get("result"),
            "reason": self.state.get("reason"),
            "current_step": self.current,
            "done": [k for k, v in steps.items() if v.get("status") == "done"],
            "todo": [s["name"] for s in self.cfg["steps"] if steps.get(_key(s), {}).get("status") != "done"],
            "lease": {
                "mode": self.lease.cfg["mode"],
                "version": self.lease.version,
                "expires_at": iso(self.lease.expires_at),
                "remaining_s": None if self.lease.remaining_s() is None else int(self.lease.remaining_s() or 0),
                "last_renewal_ok": iso(self.lease.last_ok),
                "next_renewal": iso(self.keeper.next_at) if self.keeper else None,
                "renewals": self.lease.renewals,
            },
            "keep_awake": self.awake.state,
            "updated_at": iso(utc_now()),
        }
        atomic_write(self.out / STATUS_FILE, json.dumps(status, ensure_ascii=False, indent=2))

    def finish(self, result: str, reason: str | None = None) -> int:
        self.state["result"], self.state["reason"] = result, reason
        self.state["ended_at"] = iso(utc_now())
        self.save()
        for kind in ("done", "failed"):
            if (kind == "done") == (result == "DONE") and result in FINAL:
                for rel, text in self.cfg["markers"][kind].items():
                    target = Path(rel) if Path(rel).is_absolute() else self.out / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(text.replace("{exit}", str(EXIT_CODES[result])), encoding="utf-8", newline="\n")
        self.log(f"result {result}" + (f": {reason}" if reason else ""))
        self.stop_all.set()
        self.write_status()
        return EXIT_CODES[result]

    def run(self) -> int:
        self.out.mkdir(parents=True, exist_ok=True)
        lock = try_lock(self.out / LOCK_FILE)
        if lock is None:
            _say("another long_gate runner holds this out_dir")
            return EXIT_CODES["LOCKED"]
        try:
            return self._run_locked()
        except Exception as error:  # noqa: BLE001 - the record must say why
            self.log(f"runner crashed: {type(error).__name__}: {error}")
            raise
        finally:
            self.stop_all.set()

    def _run_locked(self) -> int:
        self.log(f"runner start pid={os.getpid()} config_sha256={self.sha}")
        stop = self.out / STOP_FILE
        if stop.exists():
            stop.rename(self.out / f"STOP.consumed.{int(time.time())}")
        sp = self._state_path()
        if sp.exists():
            self.state = json.loads(sp.read_text(encoding="utf-8"))
            if self.state.get("result") in FINAL:
                self.log(f"already finished with {self.state['result']}; nothing re-run")
                self.write_status()
                return EXIT_CODES[self.state["result"]]
            if self.state.get("config_sha256") != self.sha:
                return self._refuse("config changed since this round started; a changed config is a new round in a new out_dir")
            self.state["resumes"] = int(self.state.get("resumes", 0)) + 1
        else:
            self.state = {"schema": SCHEMA, "name": self.cfg["name"], "config_sha256": self.sha,
                          "started_at": iso(utc_now()), "resumes": 0, "steps": {},
                          "bytes_at_start": tree_fingerprint(self.cfg)}
        self.state["result"] = None
        self.state["runner_pid"] = os.getpid()

        expected = self.state.get("bytes_at_start")
        for s in self.cfg["steps"]:
            rec = self.state["steps"].get(_key(s))
            if rec and rec.get("status") == "done":
                expected = rec.get("bytes_after")
            else:
                break
        current = tree_fingerprint(self.cfg)
        if current != expected:
            return self._refuse("candidate worktree bytes differ from the state the last finished step left")

        for s in self.cfg["steps"]:
            rec = self.state["steps"].get(_key(s))
            if rec and rec.get("status") == "running":
                self._park_interrupted(s, rec)
        self.save()

        try:
            self.lease.renew()
        except Exception as error:  # noqa: BLE001
            return self.finish("LEASE_FAILED_AT_START", f"first renewal failed: {error}")
        if self.lease.enabled:
            self.log("first renewal ok")
            self.keeper = LeaseKeeper(self.lease, self.hard_stop, self.stop_all, self.log)
            self.keeper.start()
        self.awake.start()
        beat = threading.Thread(target=self._heartbeat, name="status", daemon=True)
        beat.start()

        for s in self.cfg["steps"]:
            rec = self.state["steps"].get(_key(s))
            if rec and rec.get("status") == "done":
                continue
            outcome = self._run_step(s)
            if outcome == "hard_stop":
                return self.finish("HARD_STOP_LEASE", self.keeper.reason if self.keeper else None)
            if outcome == "stopped":
                return self.finish("STOPPED", "STOP file")
            code = self.state["steps"][_key(s)]["exit"]
            if code != 0 and s["stop_on_fail"]:
                return self.finish("FAILED", f"step {s['name']} exit {code}")
        return self.finish("DONE")

    def _refuse(self, reason: str) -> int:
        self.log(f"REFUSED: {reason}")
        self.state.setdefault("refusals", []).append({"at": iso(utc_now()), "reason": reason})
        if self._state_path().exists():
            self.save()
        _say(f"REFUSED: {reason}")
        return EXIT_CODES["REFUSED"]

    def _paths(self, s: dict[str, Any]) -> dict[str, Path]:
        d = self.out / s.get("dir", "")
        n = s["name"]
        return {k: d / f"{n}.{k}" for k in ("txt", "exit", "started", "finished")}

    def _park_interrupted(self, s: dict[str, Any], rec: dict[str, Any]) -> None:
        p = self._paths(s)
        n = 1
        while (p["txt"].with_name(f"{s['name']}.interrupted.{n}.txt")).exists():
            n += 1
        if p["txt"].exists():
            p["txt"].rename(p["txt"].with_name(f"{s['name']}.interrupted.{n}.txt"))
        rec.setdefault("interruptions", []).append({"started": rec.get("started"), "kept_as": f"{s['name']}.interrupted.{n}.txt"})
        rec["status"] = "interrupted"
        self.log(f"step {_key(s)} had not finished; partial output kept as {s['name']}.interrupted.{n}.txt; it runs again in full")

    def _run_step(self, s: dict[str, Any]) -> str:
        key, p = _key(s), self._paths(s)
        p["txt"].parent.mkdir(parents=True, exist_ok=True)
        rec = self.state["steps"].setdefault(key, {})
        rec.update(status="running", started=local_stamp(), started_utc=iso(utc_now()))
        rec.pop("exit", None)
        self.save()
        self.current = key
        p["started"].write_text(rec["started"] + "\n", encoding="utf-8", newline="\n")
        self.log(f"step {key} start")
        self.write_status()
        if "write" in s:
            p["txt"].write_text(s["write"], encoding="utf-8", newline="\n")
            code = 0
        else:
            env = dict(os.environ)
            # "{PATH}" in a value is the runner's own PATH, so a config can prepend (e.g. Git Bash's usr/bin, as run_g2.sh does).
            env.update({k: v.replace("{PATH}", os.environ.get("PATH", "")) for k, v in s["env"].items()})
            env.pop(TOKEN_ENV, None)
            with open(p["txt"], "wb") as out:
                child = self.children.popen(s["argv"], s["cwd"], env, out)
                rec["child_pid"] = child.pid
                self.save()
                while True:
                    try:
                        code = child.wait(timeout=1)
                        break
                    except subprocess.TimeoutExpired:
                        pass
                    if self.hard_stop.is_set() or (self.out / STOP_FILE).exists():
                        self.children.kill(child)
                        why = "hard_stop" if self.hard_stop.is_set() else "stopped"
                        self.log(f"step {key} killed ({why}); it has no result")
                        self.current = None
                        self._park_interrupted(s, rec)
                        self.save()
                        return why
        p["exit"].write_text(f"{code}\n", encoding="utf-8", newline="\n")
        rec.update(exit=code, finished=local_stamp(), finished_utc=iso(utc_now()))
        p["finished"].write_text(rec["finished"] + "\n", encoding="utf-8", newline="\n")
        rec["bytes_after"] = tree_fingerprint(self.cfg)
        rec["status"] = "done"
        rec.pop("child_pid", None)
        self.save()
        self.current = None
        self.log(f"step {key} finished exit={code}")
        self.write_status()
        return "done"

    def _heartbeat(self) -> None:
        while not self.stop_all.is_set():
            try:
                self.write_status()
            except OSError as error:
                self.log(f"status write failed: {error}")
            self.stop_all.wait(int(self.cfg["poll_s"]))


def _key(s: dict[str, Any]) -> str:
    return f"{s['dir']}/{s['name']}" if s.get("dir") else s["name"]


# ── launch (decoupled from whoever calls it) ─────────────


def task_name(cfg: dict[str, Any]) -> str:
    return f"WSPM-LongGate-{cfg['name']}"


def task_xml(command: str, arguments: str, workdir: str, user: str) -> str:
    """One-off on-demand task: no trigger, runs on battery, normal priority (a task defaults to below normal), 12 h cap."""

    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>WorkSpacePM long gate runner (scripts/long_gate.py). Started on demand; safe to delete after the run.</Description>
  </RegistrationInfo>
  <Principals>
    <Principal id="Author">
      <UserId>{escape(user)}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT12H</ExecutionTimeLimit>
    <Priority>4</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(command)}</Command>
      <Arguments>{escape(arguments)}</Arguments>
      <WorkingDirectory>{escape(workdir)}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _launch_windows(cfg: dict[str, Any], config_path: Path) -> None:
    py = Path(cfg["python"])
    pyw = py.with_name("pythonw.exe")
    command = str(pyw if pyw.exists() else py)
    args = subprocess.list2cmdline(["-B", str(Path(__file__).resolve()), "run", "--config", str(config_path)])
    user = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".lstrip("\\")
    xml_path = Path(cfg["out_dir"]) / "long_gate_task.xml"
    xml_path.write_text(task_xml(command, args, cfg["out_dir"], user), encoding="utf-16")
    name = task_name(cfg)
    for argv in (["schtasks", "/Create", "/TN", name, "/XML", str(xml_path), "/F"], ["schtasks", "/Run", "/TN", name]):
        r = subprocess.run(argv, capture_output=True, check=False)
        if r.returncode != 0:
            msg = (r.stdout + r.stderr).decode("mbcs", errors="replace").strip()
            raise GateError(f"{' '.join(argv[:2])} failed ({r.returncode}): {msg[:400]}")


def _launch_posix(cfg: dict[str, Any], config_path: Path) -> None:
    # Own session, no terminal, stdio on /dev/null: a closed shell or a killed process group cannot reach it.
    subprocess.Popen(
        [cfg["python"], "-B", str(Path(__file__).resolve()), "run", "--config", str(config_path)],
        cwd=cfg["out_dir"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True, close_fds=True,
    )


def cmd_launch(config_path: Path, wait_s: int) -> int:
    cfg, _ = load_config(config_path)
    out = Path(cfg["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    if lock_is_held(out / LOCK_FILE):
        print("ALREADY RUNNING (the runner lock is held); see `status`")
        return EXIT_CODES["LOCKED"]
    sp = out / STATE_FILE
    if sp.exists() and json.loads(sp.read_text(encoding="utf-8")).get("result") in FINAL:
        print("ALREADY FINISHED; see `status`. A new round needs a new out_dir.")
        return 0
    before = time.time()
    (_launch_windows if IS_WINDOWS else _launch_posix)(cfg, config_path.resolve())
    deadline = time.time() + wait_s
    while time.time() < deadline:
        time.sleep(1)
        st = out / STATUS_FILE
        if st.exists() and st.stat().st_mtime >= before - 1 and lock_is_held(out / LOCK_FILE):
            status = json.loads(st.read_text(encoding="utf-8"))
            print(f"STARTED pid={status['pid']} step={status['current_step']} lease_version={status['lease']['version']}")
            return 0
        if sp.exists() and sp.stat().st_mtime >= before - 1:
            state = json.loads(sp.read_text(encoding="utf-8"))
            if state.get("result") in FINAL or state.get("refusals"):
                break
    print("NOT STARTED; last lines of the runner log:")
    log = out / LOG_FILE
    if log.exists():
        print("\n".join(log.read_text(encoding="utf-8").splitlines()[-10:]))
    return 2


def cmd_status(config_path: Path) -> int:
    cfg, _ = load_config(config_path)
    out = Path(cfg["out_dir"])
    alive = lock_is_held(out / LOCK_FILE)
    st = out / STATUS_FILE
    status = json.loads(st.read_text(encoding="utf-8")) if st.exists() else {}
    status["runner_alive"] = alive
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


def cmd_stop(config_path: Path) -> int:
    cfg, _ = load_config(config_path)
    (Path(cfg["out_dir"]) / STOP_FILE).write_text(iso(utc_now()) or "", encoding="utf-8")
    print("STOP requested; the runner stops the current step within a few seconds (it can resume later)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="long gate runner decoupled from the AI session")
    ap.add_argument("command", choices=["run", "launch", "status", "stop"])
    ap.add_argument("--config", required=True, type=Path)
    ap.add_argument("--wait", type=int, default=90, help="launch: seconds to wait for the runner to report")
    a = ap.parse_args(argv)
    config_path = a.config.resolve()
    try:
        if a.command == "run":
            cfg, sha = load_config(config_path)
            return Runner(cfg, sha).run()
        if a.command == "launch":
            return cmd_launch(config_path, a.wait)
        if a.command == "status":
            return cmd_status(config_path)
        return cmd_stop(config_path)
    except GateError as error:
        _say(f"ERROR: {error}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
