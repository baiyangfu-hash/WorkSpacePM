"""Find an executable on ``PATH`` without letting the current directory (or anything relative) stand in for it.

``shutil.which`` is the wrong tool for launching programs from a repository: on Windows it searches the process's current
directory *first*, and on POSIX an empty ``PATH`` entry also means the current directory, so a ``gh.exe`` or ``git.exe``
dropped into the repository would be executed instead of the real one.  :func:`find_on_path` looks only at ``PATH``
entries written as absolute directories, and on Windows by default accepts only ``<name>.exe``: ``.bat``/``.cmd`` files are
handed to ``cmd.exe``, which interprets the arguments a second time.

``scripts/cockpit_board/actions.py`` keeps its own copy of the same function (the scripts run without the ``auto_pm``
package on their path); ``tests/infrastructure/test_executable_lookup.py`` pins the two to the same answers.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence

__all__ = ["find_on_path", "windows_path_extensions"]

_WINDOWS_DEFAULT_EXTENSIONS = (".exe",)


def windows_path_extensions() -> tuple[str, ...]:
    """The extensions Windows would try for a bare command name (``PATHEXT``), lower-cased."""

    raw = os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD")
    return tuple(item.lower() for item in raw.split(";") if item)


def find_on_path(
    name: str,
    *,
    path: str | None = None,
    windows: bool | None = None,
    cwd: str | None = None,
    is_file: Callable[[str], bool] | None = None,
    extensions: Sequence[str] | None = None,
) -> str | None:
    """The absolute path of ``name`` found in ``PATH``, or ``None``.

    - Empty entries, ``.``, any relative entry and the entry equal to the current directory are skipped.
    - On Windows only ``<name><ext>`` for ``ext`` in ``extensions`` (default: just ``.exe``) counts; elsewhere a file with the
      execute bit.  A caller that must keep launching npm-style ``.cmd`` shims passes ``windows_path_extensions()``.
    - ``windows`` / ``cwd`` / ``path`` / ``is_file`` exist so tests can inject them.
    """

    is_windows = os.name == "nt" if windows is None else windows
    raw_path = os.environ.get("PATH", "") if path is None else path
    here = os.path.normcase(os.path.realpath(os.getcwd() if cwd is None else cwd))
    exists = is_file or (lambda p: os.path.isfile(p) and (is_windows or os.access(p, os.X_OK)))
    if is_windows:
        allowed = tuple(item.lower() for item in (extensions or _WINDOWS_DEFAULT_EXTENSIONS))
        suffix = os.path.splitext(name)[1].lower()
        file_names = [name] if suffix and suffix in allowed else [f"{name}{ext}" for ext in allowed]
    else:
        file_names = [name]
    for entry in raw_path.split(";" if is_windows else ":"):
        entry = entry.strip().strip('"')
        if not entry or not os.path.isabs(entry):
            continue
        if os.path.normcase(os.path.realpath(entry)) == here:
            continue
        for file_name in file_names:
            candidate = os.path.join(entry, file_name)
            if exists(candidate):
                return candidate
    return None
