"""Read-only status line of the memory gate (the system-level watchdog) for ``pm orient``.

The gate is installed once by ``setup_env.bat`` (step 5, one UAC prompt) under ``%ProgramFiles%\\AutoPM\\MemoryGate``.  This module only *reads*
what the installer and the watchdog wrote there (``manifest.json`` and ``state\\state.json``, readable by ordinary users) and the hash pinned in the
repository (``config/memory_gate.pin.json``).  It never installs, repairs, starts or stops anything and never runs the installed Python.

Standard library only; every location can be replaced by the caller (tests).  Nothing is read at import time.
"""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

HEARTBEAT_STALE_SECONDS = 30.0  # the same limit memory_gate.py status uses
_PIN_RELATIVE = Path("config") / "memory_gate.pin.json"
_PROJECT_RELATIVE = Path("01_Project自动化项目管理") / "Python自动化项目总库" / "02_在研项目" / "SW-2026-008_auto-pm_自动化项目管理工具"
_MAX_BYTES = 64 * 1024


@dataclass(frozen=True)
class GateStatus:
    """``state`` is one of running, stale, not_installed, unreadable."""

    state: str
    installed_bundle: str = ""
    pinned_bundle: str = ""
    heartbeat_age: float | None = None
    detail: str = ""

    @property
    def update_available(self) -> bool:
        return bool(self.installed_bundle and self.pinned_bundle and self.installed_bundle != self.pinned_bundle)

    def line(self) -> str:
        if self.state == "not_installed":
            return "总闸: 未安装。想装请运行 setup_env.bat 的第 5 步（用户点一次 Windows 的“是”）；本命令只读，不会自动安装。"
        if self.state == "unreadable":
            return f"总闸: 已安装，但状态读不出（{self.detail}）。排查: powershell -File scripts\\install_memory_gate.ps1 -Status；残留用 -Repair。"
        if self.state == "stale":
            age = "未知" if self.heartbeat_age is None else f"{self.heartbeat_age:.0f}"
            return f"总闸: 已安装但看门狗没有心跳（{age} 秒前）。排查: powershell -File scripts\\install_memory_gate.ps1 -Status；残留用 -Repair。{self._version_note()}"
        return f"总闸: 运行中。{self._version_note()}"

    def _version_note(self) -> str:
        if not self.pinned_bundle:
            return "未能核对已装版本是否等于仓库钉住的版本（没找到 config/memory_gate.pin.json）。"
        if not self.installed_bundle:
            return "已装版本记录读不出，无法核对。"
        if self.update_available:
            return "已装版本不等于仓库钉住的版本: 有新版本，请重跑 setup_env.bat（用户点一次 UAC，不会自动更新）。"
        return "已装版本与仓库钉住的一致。"


def default_install_dir() -> Path:
    return Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "AutoPM" / "MemoryGate"


def _read_json(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    if len(raw) > _MAX_BYTES:
        raise ValueError("文件过大")
    data = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("不是 JSON 对象")
    return data


def _pinned_bundle(pin_file: Path | None, workspace_root: Path | None) -> str:
    candidates = [pin_file] if pin_file is not None else [
        Path(__file__).resolve().parents[2] / _PIN_RELATIVE,
        *([workspace_root / _PROJECT_RELATIVE / _PIN_RELATIVE] if workspace_root is not None else []),
    ]
    for candidate in candidates:
        try:
            value = _read_json(candidate).get("bundle_sha256", "")
        except (OSError, ValueError):
            continue
        if isinstance(value, str) and len(value) == 64:
            return value.lower()
    return ""


def read_gate_status(
    *,
    install_dir: Path | None = None,
    pin_file: Path | None = None,
    workspace_root: Path | None = None,
    now: float | None = None,
    platform: str = sys.platform,
) -> GateStatus | None:
    """The gate's status, or ``None`` on a machine the gate does not apply to (it is a Windows-only watchdog)."""

    if platform != "win32":
        return None
    root = install_dir if install_dir is not None else default_install_dir()
    pinned = _pinned_bundle(pin_file, workspace_root)
    try:
        has_manifest = (root / "manifest.json").exists()
        has_dir = root.exists()
    except OSError as error:
        return GateStatus("unreadable", pinned_bundle=pinned, detail=type(error).__name__)
    if not has_dir:
        return GateStatus("not_installed", pinned_bundle=pinned)
    if not has_manifest:
        return GateStatus("unreadable", pinned_bundle=pinned, detail="目录在但没有 manifest.json，像是装了一半或残留")
    try:
        installed = str(_read_json(root / "manifest.json").get("bundle_sha256", "")).lower()
        state = _read_json(root / "state" / "state.json")
    except FileNotFoundError:
        # manifest present but the watchdog never wrote a state: it is not running
        return GateStatus("stale", installed_bundle=_installed_only(root), pinned_bundle=pinned, detail="还没有状态文件")
    except (OSError, ValueError) as error:
        return GateStatus("unreadable", pinned_bundle=pinned, detail=f"{type(error).__name__}")
    beat = state.get("heartbeat")
    if not isinstance(beat, (int, float)) or isinstance(beat, bool) or beat <= 0:
        return GateStatus("stale", installed_bundle=installed, pinned_bundle=pinned)
    age = (time.time() if now is None else now) - float(beat)
    return GateStatus("running" if age <= HEARTBEAT_STALE_SECONDS else "stale", installed_bundle=installed, pinned_bundle=pinned, heartbeat_age=age)


def _installed_only(root: Path) -> str:
    try:
        return str(_read_json(root / "manifest.json").get("bundle_sha256", "")).lower()
    except (OSError, ValueError):
        return ""
