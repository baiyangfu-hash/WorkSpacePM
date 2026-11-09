"""Scan every line ADDED by the commits in <base_ref>..HEAD for provider-shaped secrets.

usage: secret_scan.py <base_ref>

Walks the commits one by one (`git log -p`), so a secret that was added and removed again
inside the range is still found.  Prints only "[pattern] path @commit xN"; values are never
printed or logged.  Strict provider patterns only: generic "password = ..." assignments are
not scanned here because they produce false positives in lease-token code.
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from typing import NoReturn


def _cannot_load(path: Path, why: str) -> NoReturn:
    """Exit 2: the scan did not run.  (``SystemExit("text")`` would exit 1, which reads as "secrets found".)"""
    print(f"cannot load the shared secret rules from {path}: {why}", file=sys.stderr)
    sys.exit(2)


def _shared_patterns() -> dict[str, re.Pattern[str]]:
    """The commit hook's rules (``auto_pm/domain/secret_patterns.py``), loaded by path: one list, not two (D-70).

    That file is pure stdlib with no I/O, so it loads without the rest of the package.  Before this, the CI list
    had ``{30,}`` / ``{40,}`` length floors and no ``sk-`` / ``AIza`` rules while the hook had the opposite gaps.
    """
    path = Path(__file__).resolve().parents[3] / "auto_pm" / "domain" / "secret_patterns.py"
    spec = importlib.util.spec_from_file_location("sw008_secret_patterns", path)
    if spec is None or spec.loader is None:
        _cannot_load(path, "no import spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # the dataclass in that file looks its own module up here
    try:
        spec.loader.exec_module(module)
    except Exception as error:  # noqa: BLE001 - any load failure is "scan could not run" (exit 2), never "secrets found" (exit 1)
        _cannot_load(path, f"{type(error).__name__}: {error}")
    return dict(module.SECRET_PATTERNS)


# CI-only extra: credentials inside a URL.  The commit hook leaves it out (false positives in lease-token code).
PATTERNS = {
    **_shared_patterns(),
    "url-credentials": re.compile(r"https?://[^/@\s:]+:[^/@\s]+@"),
}


def main(base: str) -> int:
    out = subprocess.run(
        ["git", "-c", "core.quotepath=off", "log", "-p", "--unified=0", "--no-color",
         "--format=@@commit %h", f"{base}..HEAD"],
        capture_output=True, encoding="utf-8", errors="replace", check=True,
    ).stdout
    hits: dict[tuple[str, str, str], int] = {}
    commit, path = "?", "?"
    for line in out.splitlines():
        if line.startswith("@@commit "):
            commit = line[9:]
        elif line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else line[4:]
        elif line.startswith("+") and not line.startswith("+++"):
            for name, pat in PATTERNS.items():
                if pat.search(line):
                    key = (name, path, commit)
                    hits[key] = hits.get(key, 0) + 1
    for (name, path, commit), n in sorted(hits.items()):
        print(f"SECRET-SHAPED [{name}] {path} @{commit} x{n}")
    print(f"secret scan: {len(hits)} location(s) flagged in {base}..HEAD")
    return 1 if hits else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
