"""Read-only facts about a lease holder's process on this host (V04-R1 reclaim interface, M3-HANDOFF card).

The probe only observes; ``lease_reclaim.judge_process`` decides.  Every failure to observe returns ``None`` (or ``None`` fields), which the contract
turns into ``UNKNOWN``: a process nobody could identify is never reported as dead.

- Windows: ``OpenProcess`` with the limited query right; error 87 (no such process) proves absence, error 5 (access denied) proves presence with an
  unknown start time; the start time is the creation ``FILETIME`` as a decimal tick count; image and command line are hashed, never stored.
- Linux: ``/proc/<pid>/stat`` field 22 (start time in clock ticks since boot), ``/proc/<pid>/exe`` and ``/proc/<pid>/cmdline``.
- Other platforms: nothing can be observed (``None``).

The host identity is a hash of the machine id (``MachineGuid`` on Windows, ``/etc/machine-id`` on Linux); the raw id is never stored.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from auto_pm.contracts.lease_reclaim import ProcessFingerprint, ProcessObservation

# Images skipped when looking for the long-lived process behind a CLI call (M3 drill 2026-10-19):
# - the root entry and the launcher are two short-lived Python parents of every governed command;
# - agent hosts (Trae CN, Claude Code, Codex, Cursor) run every command in a fresh shell that exits with it, so recording that shell made
#   every reclaim see PROVEN_DEAD while the agent was still working.  The holder is the first ancestor past both kinds: the agent's host.
# - per-command sandboxes: Trae CN (user's laptop, 2026-10-23) starts each command as python -> powershell -> trae-sandbox.exe ->
#   agent-tool-host.exe -> Trae CN utility -> Trae CN; the sandbox exits with the command, the tool host stays.  A sandbox is skipped like
#   a shell but never kept as the fallback holder, since it never outlives its command.
# A person typing in a terminal has no host above the shell, only the terminal window or the desktop; when the walk reaches one of those
# session roots, the shell nearest to it (the one the person keeps open) is the holder.
_LAUNCHER_IMAGES = frozenset({"python.exe", "pythonw.exe", "python3.exe", "py.exe", "python", "python3"})
_SHELL_IMAGES = frozenset(
    {
        "cmd.exe", "powershell.exe", "pwsh.exe", "bash.exe", "sh.exe", "zsh.exe", "dash.exe", "fish.exe", "wsl.exe",
        "bash", "sh", "zsh", "dash", "fish", "ksh", "pwsh", "sudo", "env", "timeout", "nohup",
    }
)
_SANDBOX_IMAGES = frozenset({"trae-sandbox.exe", "trae-sandbox"})
_SESSION_ROOT_IMAGES = frozenset(
    {
        "explorer.exe", "windowsterminal.exe", "openconsole.exe", "conhost.exe", "wininit.exe", "winlogon.exe", "services.exe",
        "svchost.exe", "userinit.exe", "sihost.exe", "sshd.exe", "systemd", "init", "launchd", "sshd", "login", "su",
        "tmux: server", "screen", "gnome-terminal-", "konsole", "xterm", "alacritty", "kitty", "wezterm-gui",
    }
)
_VERSIONED_PYTHON = re.compile(r"pythonw?[0-9.]*(\.exe)?")
_MAX_ANCESTORS = 12


def _is_launcher(image_name: str) -> bool:
    # Linux shows the interpreter as its versioned name ("python3.12"), Windows as an image ("python.exe")
    return image_name in _LAUNCHER_IMAGES or _VERSIONED_PYTHON.fullmatch(image_name) is not None


@dataclass(frozen=True)
class ProcessEntry:
    """One row of the process table: the parent pid and the image base name (lower case)."""

    pid: int
    parent_pid: int
    image_name: str


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def local_host_id() -> str:
    """A stable, hashed identity of this machine; empty when it cannot be read (the contract then answers UNKNOWN)."""

    raw = ""
    if sys.platform == "win32":
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
            ) as key:
                value, _kind = winreg.QueryValueEx(key, "MachineGuid")
                raw = str(value).strip()
        except OSError:
            raw = ""
    else:
        for candidate in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
            try:
                raw = Path(candidate).read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                continue
            if raw:
                break
    return "host:" + _sha256_text(raw)[:32] if raw else ""


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _NTDLL = ctypes.WinDLL("ntdll")
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _STILL_ACTIVE = 259
    _ERROR_ACCESS_DENIED = 5
    _ERROR_INVALID_PARAMETER = 87
    _TH32CS_SNAPPROCESS = 0x00000002
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    _PROCESS_COMMAND_LINE_INFORMATION = 60

    class _FileTime(ctypes.Structure):
        _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

    class _ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    class _UnicodeString(ctypes.Structure):
        _fields_ = [
            ("Length", wintypes.USHORT),
            ("MaximumLength", wintypes.USHORT),
            ("Buffer", ctypes.c_void_p),
        ]

    _KERNEL32.OpenProcess.restype = wintypes.HANDLE
    _KERNEL32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _KERNEL32.CloseHandle.argtypes = [wintypes.HANDLE]
    _KERNEL32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    _KERNEL32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(_FileTime)] * 4
    _KERNEL32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _KERNEL32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _KERNEL32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _KERNEL32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32W)]
    _KERNEL32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_ProcessEntry32W)]
    _NTDLL.NtQueryInformationProcess.restype = ctypes.c_long
    _NTDLL.NtQueryInformationProcess.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.ULONG,
        ctypes.POINTER(wintypes.ULONG),
    ]

    def _windows_command_line(handle: int) -> str | None:
        needed = wintypes.ULONG(0)
        _NTDLL.NtQueryInformationProcess(handle, _PROCESS_COMMAND_LINE_INFORMATION, None, 0, ctypes.byref(needed))
        if needed.value == 0 or needed.value > 1 << 20:
            return None
        buffer = ctypes.create_string_buffer(needed.value)
        status = _NTDLL.NtQueryInformationProcess(
            handle, _PROCESS_COMMAND_LINE_INFORMATION, buffer, needed, ctypes.byref(needed)
        )
        if status != 0:
            return None
        text = _UnicodeString.from_buffer(buffer)
        if not text.Buffer or text.Length == 0:
            return None
        return ctypes.wstring_at(text.Buffer, text.Length // 2)

    def _windows_observe(pid: int) -> tuple[ProcessObservation, str | None] | None:
        handle = _KERNEL32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            error = ctypes.get_last_error()
            if error == _ERROR_INVALID_PARAMETER:
                return ProcessObservation(pid_exists=False), None
            if error == _ERROR_ACCESS_DENIED:
                return ProcessObservation(pid_exists=True), None
            return None
        try:
            code = wintypes.DWORD(0)
            if not _KERNEL32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return None
            if code.value != _STILL_ACTIVE:
                return ProcessObservation(pid_exists=False), None
            created, exited, kernel, user = _FileTime(), _FileTime(), _FileTime(), _FileTime()
            start: str | None = None
            if _KERNEL32.GetProcessTimes(
                handle, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)
            ):
                start = str((created.high << 32) | created.low)
            size = wintypes.DWORD(32768)
            path_buffer = ctypes.create_unicode_buffer(size.value)
            image: str | None = None
            if _KERNEL32.QueryFullProcessImageNameW(handle, 0, path_buffer, ctypes.byref(size)):
                image = path_buffer.value
            command = _windows_command_line(handle)
            return (
                ProcessObservation(
                    pid_exists=True,
                    start_time=start,
                    image_sha256=_sha256_text(image.casefold()) if image else None,
                    cmdline_sha256=_sha256_text(command) if command else None,
                ),
                Path(image).name.casefold() if image else None,
            )
        finally:
            _KERNEL32.CloseHandle(handle)

    def _windows_process_table() -> dict[int, ProcessEntry] | None:
        snapshot = _KERNEL32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
        if not snapshot or snapshot == _INVALID_HANDLE_VALUE:
            return None
        try:
            entry = _ProcessEntry32W()
            entry.dwSize = ctypes.sizeof(_ProcessEntry32W)
            table: dict[int, ProcessEntry] = {}
            ok = _KERNEL32.Process32FirstW(snapshot, ctypes.byref(entry))
            while ok:
                pid = int(entry.th32ProcessID)
                table[pid] = ProcessEntry(pid, int(entry.th32ParentProcessID), entry.szExeFile.casefold())
                ok = _KERNEL32.Process32NextW(snapshot, ctypes.byref(entry))
            return table
        finally:
            _KERNEL32.CloseHandle(snapshot)


def _linux_observe(pid: int) -> tuple[ProcessObservation, str | None] | None:
    base = Path("/proc") / str(pid)
    try:
        stat = (base / "stat").read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ProcessObservation(pid_exists=False), None
    except OSError:
        return None
    closing = stat.rfind(")")
    fields = stat[closing + 2 :].split() if closing != -1 else []
    # after "pid (comm) " the fields start at "state" (field 3), so field 22 (starttime) is index 19
    start = fields[19] if len(fields) > 19 and fields[19].isdigit() else None
    if len(fields) > 0 and fields[0] == "Z":
        return ProcessObservation(pid_exists=False), None
    image: str | None
    try:
        image = os.readlink(base / "exe")
    except OSError:
        image = None
    try:
        command = (base / "cmdline").read_bytes().decode("utf-8", errors="replace")
    except OSError:
        command = ""
    name = stat[stat.find("(") + 1 : closing].casefold() if closing != -1 else None
    return (
        ProcessObservation(
            pid_exists=True,
            start_time=start,
            image_sha256=_sha256_text(image) if image else None,
            cmdline_sha256=_sha256_text(command) if command else None,
        ),
        name,
    )


def _observe_with_name(pid: int) -> tuple[ProcessObservation, str | None] | None:
    if type(pid) is not int or pid <= 0:
        return None
    if sys.platform == "win32":
        return _windows_observe(pid)
    elif sys.platform.startswith("linux"):
        return _linux_observe(pid)
    else:
        return None


def observe(pid: int) -> ProcessObservation | None:
    """What this host shows now for ``pid``; ``None`` when the process table could not be read."""

    observed = _observe_with_name(pid)
    return observed[0] if observed is not None else None


def fingerprint(pid: int) -> ProcessFingerprint | None:
    """The fingerprint to record for a live holder process; ``None`` when it is not running or cannot be read with a start time."""

    host = local_host_id()
    observed = observe(pid)
    if not host or observed is None or not observed.pid_exists or observed.start_time is None:
        return None
    return ProcessFingerprint(
        host_id=host,
        pid=pid,
        start_time=observed.start_time,
        image_sha256=observed.image_sha256,
        cmdline_sha256=observed.cmdline_sha256,
    )


def _parent_pid(pid: int) -> tuple[int, str] | None:
    if sys.platform == "win32":
        table = _windows_process_table()
        if table is None or pid not in table:
            return None
        entry = table[pid]
        parent = table.get(entry.parent_pid)
        return entry.parent_pid, parent.image_name if parent is not None else ""
    elif sys.platform.startswith("linux"):
        try:
            stat = (Path("/proc") / str(pid) / "stat").read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        closing = stat.rfind(")")
        fields = stat[closing + 2 :].split() if closing != -1 else []
        if len(fields) < 2 or not fields[1].isdigit():
            return None
        parent_pid = int(fields[1])
        observed = _observe_with_name(parent_pid)
        return parent_pid, (observed[1] or "") if observed is not None else ""
    else:
        return None


def holder_process_pid(
    start_pid: int | None = None, parent_of: Callable[[int], tuple[int, str] | None] | None = None
) -> int | None:
    """The long-lived process behind this CLI call: the agent host above the per-command shells, or the person's own shell.

    Walks up from ``start_pid`` past Python launchers, shells and per-command sandboxes.  The first other ancestor is the holder, unless it is a session root
    (terminal window, desktop, init), in which case the nearest shell below it is.  ``None`` when the ancestry cannot be read: a later
    reclaim then sees UNKNOWN, never PROVEN_DEAD.
    """

    lookup = _parent_pid if parent_of is None else parent_of
    current = os.getpid() if start_pid is None else start_pid
    nearest_shell: int | None = None
    for _ in range(_MAX_ANCESTORS):
        parent = lookup(current)
        if parent is None:
            return nearest_shell
        parent_pid, image_name = parent
        if parent_pid <= 0 or parent_pid == current or not image_name:
            return nearest_shell
        if image_name in _SESSION_ROOT_IMAGES or parent_pid == 1:
            return nearest_shell if nearest_shell is not None else (None if parent_pid == 1 else parent_pid)
        if image_name in _SHELL_IMAGES:
            nearest_shell = parent_pid
        elif image_name in _SANDBOX_IMAGES:
            pass
        elif not _is_launcher(image_name):
            return parent_pid
        current = parent_pid
    return nearest_shell
