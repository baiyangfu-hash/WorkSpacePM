"""Self-test of the CI tools, run as the first CI step (stdlib only, < 5 s).

Proves that the checks can actually fail: a bad baseline, a stale baseline, a crashed pytest
run and a secret-shaped string must each be rejected, and a clean case must pass.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
COMPARE = HERE / "compare_baseline.py"
SCAN = HERE / "secret_scan.py"
FAILS: list[str] = []


def run(*args: str, cwd: Path | None = None) -> int:
    return subprocess.run([sys.executable, "-I", *args], cwd=cwd, capture_output=True).returncode


def check(name: str, got: int, want: int) -> None:
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {name}: exit {got}, expected {want}")
    if not ok:
        FAILS.append(name)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        log_fail = d / "fail.log"
        log_fail.write_text("FAILED tests/a.py::t1\nFAILED tests/b.py::t2\n2 failed, 8 passed in 1.00s\n", encoding="utf-8")
        log_clean = d / "clean.log"
        log_clean.write_text("10 passed in 1.00s\n", encoding="utf-8")

        def baseline(name: str, ids: list[str]) -> str:
            p = d / name
            p.write_text(json.dumps({"ids": ids}), encoding="utf-8")
            return str(p)

        both = baseline("both.json", ["tests/a.py::t1", "tests/b.py::t2"])
        check("failures equal baseline -> PASS_KNOWN_BASELINE", run(str(COMPARE), str(log_fail), both, "1"), 0)
        check("failure missing from baseline -> FAIL",
              run(str(COMPARE), str(log_fail), baseline("one.json", ["tests/a.py::t1"]), "1"), 1)
        check("baseline item unexpectedly passes -> FAIL (stale)",
              run(str(COMPARE), str(log_fail), baseline("extra.json", ["tests/a.py::t1", "tests/b.py::t2", "tests/c.py::t3"]), "1"), 1)
        check("pytest crashed (exit 2) -> FAIL", run(str(COMPARE), str(log_fail), both, "2"), 1)
        check("clean run but non-empty baseline -> FAIL (stale)", run(str(COMPARE), str(log_clean), both, "0"), 1)
        check("clean run, empty baseline -> PASS", run(str(COMPARE), str(log_clean), baseline("empty.json", []), "0"), 0)

        repo = d / "repo"
        repo.mkdir()
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "ci@example.invalid")
        git(repo, "config", "user.name", "ci")
        (repo / "a.txt").write_text("base\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "base")
        git(repo, "branch", "-M", "main")
        git(repo, "checkout", "-q", "-b", "feature")
        (repo / "ok.txt").write_text("token = a_long_value_that_is_not_provider_shaped\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "clean")
        check("clean addition -> scan passes", run(str(SCAN), "main", cwd=repo), 0)
        # Built at run time so that this file itself never contains a token-shaped literal.
        (repo / "leak.txt").write_text("k = " + "ghp_" + "Z" * 36 + "\n", encoding="utf-8")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "leak")
        check("token-shaped addition -> scan fails", run(str(SCAN), "main", cwd=repo), 1)
        (repo / "leak.txt").unlink()
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", "remove the leak again")
        check("added then removed inside the range -> scan still fails", run(str(SCAN), "main", cwd=repo), 1)

    print("self-test:", "FAILED " + ", ".join(FAILS) if FAILS else "all checks behaved as expected")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
