"""Copy the active release to a scratch folder so it can be tried without touching ``releases/`` (D-05, handoff 11 item 10).

Until now the only quick way to reproduce a problem of the deployed code was to run it inside ``00_Infrastructure/auto_pm/releases/<id>``,
which leaves bytecode caches there (D-04) and the launcher then refuses that release.  This service makes the safe way one command:
the copy lives in the system temp folder (never in the workspace), carries no ``__pycache__``, and the report says how to run it with
``python -B``.  It reads the release pointer and copies; it writes no ledger, no pointer and nothing under the workspace, and it never
deletes anything -- the user removes the copy when done.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

POINTER_RELATIVE = Path("00_Infrastructure") / "auto_pm" / "active_release.json"
RELEASES_RELATIVE = Path("00_Infrastructure") / "auto_pm" / "releases"
_SKIP_NAMES = ("__pycache__", "*.pyc", "*.pyo")


class ReleaseTrialError(Exception):
    """The release could not be located or copied; the message says why and what to do."""


@dataclass(frozen=True)
class TrialCopy:
    release_id: str
    source: Path
    destination: Path
    files: int

    @property
    def run_hint(self) -> str:
        return f'PYTHONPATH="{self.destination}" python -B -m auto_pm --help'

    def to_dict(self) -> dict[str, object]:
        return {
            "release_id": self.release_id,
            "source": str(self.source),
            "destination": str(self.destination),
            "files": self.files,
            "run_hint": self.run_hint,
        }


class ReleaseTrialService:
    def __init__(self, control_root: str | Path) -> None:
        self._root = Path(control_root).resolve()

    def active_release_dir(self) -> tuple[str, Path]:
        pointer = self._root / POINTER_RELATIVE
        try:
            data = json.loads(pointer.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ReleaseTrialError(f"读不出生效发布的指针 {pointer}：{error}") from error
        release_id = data.get("release_id") if isinstance(data, dict) else None
        relative = data.get("release_path") if isinstance(data, dict) else None
        if not isinstance(release_id, str) or not isinstance(relative, str) or not release_id or not relative:
            raise ReleaseTrialError(f"{pointer} 里没有可用的 release_id / release_path")
        if relative != Path(relative).name or relative in {".", ".."}:
            raise ReleaseTrialError(f"release_path 必须是 releases/ 下的单层目录名：{relative}")
        releases = self._root / RELEASES_RELATIVE
        source = releases / relative
        if source.is_symlink() or not source.is_dir():
            raise ReleaseTrialError(f"生效发布的目录不存在或是链接：{source}")
        return release_id, source

    def make_copy(self, parent: str | Path | None = None) -> TrialCopy:
        release_id, source = self.active_release_dir()
        base = Path(parent).resolve() if parent is not None else Path(tempfile.gettempdir()).resolve()
        if base == self._root or self._root in base.parents:
            raise ReleaseTrialError(f"试验副本不能放在工作区里面（{base}）；请换一个工作区外的目录")
        if not base.is_dir():
            raise ReleaseTrialError(f"目录不存在：{base}")
        destination = Path(tempfile.mkdtemp(prefix=f"auto-pm-trial-{release_id}-", dir=base))
        target = destination / "release"
        try:
            shutil.copytree(source, target, ignore=shutil.ignore_patterns(*_SKIP_NAMES), symlinks=False)
        except OSError as error:
            raise ReleaseTrialError(f"复制失败：{error}；已创建的 {destination} 请自行删除") from error
        files = sum(1 for item in target.rglob("*") if item.is_file())
        return TrialCopy(release_id, source, target, files)
