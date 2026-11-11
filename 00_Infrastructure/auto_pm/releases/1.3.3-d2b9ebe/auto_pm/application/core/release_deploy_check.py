"""``release deploy <commit> --check-only`` and ``release status``: the read-only half of the one-command release (D-146, card 1).

Nothing here writes a file, a pointer, a manifest entry or the ledger.  The preflight answers one question: *may this commit be deployed
now?*  Every check says PASS, FAIL or UNVERIFIED (the check could not run here); the verdict is ``ok`` only when nothing failed **and**
nothing is unverified, so a missing input never reads as a pass.  What this card does **not** cover is listed in ``NOT_COVERED``
and printed with every report, so a green preflight is never mistaken for a complete one.

The release id is computed the way ``pmf_release_ops.sh build`` computes it: ``<pyproject version>-<first 7 hex of the commit>``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from auto_pm.application.core.release_consistency import check_release_consistency
from auto_pm.infrastructure.process_probe import windows_command_lines

PROJECT_DIR = "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具"
CONTAINER = Path("00_Infrastructure") / "auto_pm"
EVIDENCE_PREFIX = "release-deploy-"  # the deploy writes <reports>/<prefix><release id>/receipt.json; ``release status`` reads the same name (D-188)
PASS, FAIL, UNVERIFIED = "PASS", "FAIL", "UNVERIFIED"
GIT_TIMEOUT_SECONDS = 30
EXACT_TREE_TIMEOUT_SECONDS = 120
MIN_FREE_BYTES = 2 * 1024**3
PROCESS_LIST_TIMEOUT_SECONDS = 30
BUSY_PROCESS_MARKERS = ("pytest", "boss_main", "main.py gui")
HEAVY_GATES_MARKER = Path(".auto-pm") / "reports" / "HEAVY_GATES_RUNNING"
# Part of the one-command release that later cards add; printed so a green preflight is not read as the whole safety net.
NOT_COVERED = (
    "四个项目的台账对账 0/0/0（卡3，需要账本）",
    "真实 pre-commit 钩子干跑（卡4，在切换后的新运行时下才有意义）",
    "数据库副本上的事件链演练（卡4）",
    "用户确认引用与批准口令（真部署才需要，卡4）",
)

_VERSION = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


@dataclass
class Preflight:
    commit: str = ""
    release_id: str = ""
    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str) -> None:
        self.checks.append(Check(name, status, detail))

    @property
    def ok(self) -> bool:
        return all(check.status == PASS for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "commit": self.commit,
            "release_id": self.release_id,
            "checks": [{"name": c.name, "status": c.status, "detail": c.detail} for c in self.checks],
            "not_covered": list(NOT_COVERED),
        }

    def render(self) -> list[str]:
        lines = [f"发布预检：提交 {self.commit[:12] or '?'} → 发布号 {self.release_id or '?'}：{'可以部署' if self.ok else '不能部署'}"]
        lines.extend(f"  [{c.status}] {c.name}：{c.detail}" for c in self.checks)
        lines.append("  本预检没覆盖：" + "；".join(NOT_COVERED))
        return lines


def _git(root: Path, *args: str) -> str | None:
    try:
        done = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",  # lenient-decode: git 输出只用来判断和展示，坏字节不该让只读预检崩溃
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def _json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def release_id_for(root: Path, commit: str) -> str:
    """``<pyproject version>-<commit[:7]>``, the id ``pmf_release_ops.sh build`` gives the release; empty when the version cannot be read."""

    text = _git(root, "show", f"{commit}:{PROJECT_DIR}/pyproject.toml")
    found = _VERSION.search(text or "")
    return f"{found.group(1)}-{commit[:7]}" if found else ""


def _check_commit(root: Path, spec: str, report: Preflight) -> None:
    full = _git(root, "rev-parse", "--verify", "--quiet", f"{spec}^{{commit}}")
    if not full or not _FULL_SHA.match(full):
        report.add("提交存在", FAIL, f"{spec} 不是本仓库里的提交")
        return
    report.commit = full
    report.add("提交存在", PASS, full)
    parents = (_git(root, "rev-list", "--parents", "-n", "1", full) or "").split()[1:]
    report.add(
        "是合并提交", PASS if len(parents) >= 2 else FAIL,
        "合并提交" if len(parents) >= 2 else f"只有 {len(parents)} 个父提交；本仓库只用 Merge commit 合并，发布点必须是合并提交",
    )
    for branch in ("origin/main", "main"):
        if _git(root, "rev-parse", "--verify", "--quiet", f"{branch}^{{commit}}"):
            inside = subprocess.run(  # noqa: S603 - fixed argv, no shell
                ["git", "-C", str(root), "merge-base", "--is-ancestor", full, branch],
                capture_output=True, timeout=GIT_TIMEOUT_SECONDS, check=False,
            ).returncode == 0
            report.add("已在主线上", PASS if inside else FAIL, f"在 {branch} 上" if inside else f"不在 {branch} 上")
            return
    report.add("已在主线上", UNVERIFIED, "找不到 origin/main 或 main，没法判断")


def _check_slot(base: Path, report: Preflight) -> None:
    manifest = _json(base / "deployment_manifest.json")
    if manifest is None or not isinstance(manifest.get("releases"), dict):
        report.add("发布槽位空闲", FAIL, "读不出 deployment_manifest.json（不是控制根或清单坏了）")
        return
    if not report.release_id:
        report.add("发布槽位空闲", FAIL, "读不出该提交的 pyproject 版本，算不出发布号")
        return
    taken = report.release_id in manifest["releases"] or (base / "releases" / report.release_id).exists()
    report.add("发布槽位空闲", FAIL if taken else PASS, f"{report.release_id} 已存在（清单或目录），build 会拒绝重装" if taken else report.release_id)


def _check_pointers(base: Path, report: Preflight) -> list[str]:
    """Record both pointers (id and file SHA-256); returns the release ids that must stay intact."""

    ids: list[str] = []
    notes: list[str] = []
    for name in ("active_release.json", "previous_release.json"):
        data = _json(base / name)
        release = str((data or {}).get("release_id", ""))
        if not release:
            report.add(f"指针 {name}", FAIL, "读不出或没有 release_id")
            continue
        ids.append(release)
        notes.append(f"{name.split('_')[0]}={release} sha256={_sha256(base / name)[:16]}")
    if len(ids) == 2:
        report.add("指针已记录", PASS, "；".join(notes))
    return ids


def _check_consistency(root: Path, report: Preflight) -> None:
    result = check_release_consistency(str(root))
    status = {"ok": PASS, "warn": PASS, "info": FAIL, "fail": FAIL}.get(str(result.get("status")), UNVERIFIED)
    problems = result.get("failures") or []
    detail = "；".join(problems[:3]) if problems else f"{result.get('status')}（警告 {len(result.get('warnings') or [])} 条）"
    report.add("发布记录互相一致", status, detail)


def _check_gate(path: Path | None, commit: str, report: Preflight) -> None:
    if path is None:
        report.add("门禁判决", FAIL, "没给 --gate-verdict；部署必须有这个提交的全量门禁判决")
        return
    verdict = _json(path)
    if verdict is None:
        report.add("门禁判决", FAIL, f"读不出 {path}")
        return
    named = str(verdict.get("commit", "")).lower()
    result = str(verdict.get("verdict", ""))
    if not commit or not named or not (commit.startswith(named) or named.startswith(commit)) or len(named) < 12:
        report.add("门禁判决", FAIL, f"判决里的提交 {named[:12] or '空'} 不是待发布提交 {commit[:12]}")
    elif not result.startswith("PASS"):
        report.add("门禁判决", FAIL, f"判决不是 PASS：{result[:80]}")
    else:
        report.add("门禁判决", PASS, f"{result[:80]}")


AUDIT_LINE = re.compile(r"^audit:AUD-001 independent-audit (?P<token>\S+) (?P<run>\S+) (?P<commit>[0-9a-f]{40}) verdict-sha256=(?P<sha>[0-9a-f]{16})(?:\s|$)", re.MULTILINE)


def _check_audit(path: Path | None, commit: str, gate_path: Path | None, report: Preflight) -> None:
    """Only the machine-readable audit line counts: the token must be exactly ``PASS``, name this commit, and carry the first 16 hex
    digits of the SHA-256 of the gate verdict file given to this command.  Prose (\"放行\", \"不放行\", \"PASS 了 3 项\") is never read."""

    name = "独立审计签字"
    if path is None:
        report.add(name, FAIL, "没给 --audit-signoff；部署必须有独立审计的放行记录")
        return
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        report.add(name, FAIL, f"读不出 {path}")
        return
    lines = list(AUDIT_LINE.finditer(text))
    if not lines:
        report.add(name, FAIL, "签字文件里没有机器可读的审计行（audit:AUD-001 independent-audit <PASS|PASS-with-notes> <Run> <40位提交> verdict-sha256=<16位> …）")
        return
    line = lines[-1]  # the last line is the audit's final word
    if not commit or line["commit"] != commit.lower():
        report.add(name, FAIL, f"审计行里的提交 {line['commit'][:12]} 不是待发布提交 {commit[:12] or '空'}")
    elif line["token"] == "PASS-with-notes":
        report.add(name, FAIL, "审计是 PASS-with-notes（放行但有保留项）：不允许一键继续，需要用户确认引用点名每一条保留项（裁决 11-08）")
    elif line["token"] != "PASS":
        report.add(name, FAIL, f"审计结论是 {line['token']}，不是 PASS")
    elif gate_path is None or not gate_path.is_file() or _sha256(gate_path)[:16] != line["sha"]:
        report.add(name, FAIL, "审计行里的 verdict-sha256 和传入的门禁判决文件对不上（审的不是这份判决）")
    else:
        report.add(name, PASS, f"{line['run']} {path.name}")


def _list_processes() -> tuple[list[tuple[int, int, str]] | None, str]:
    """(pid, parent pid, command line) of every running process, and why not when it cannot be listed: ``(None, reason)``.

    Windows reads the kernel's process snapshot in-process (D-234: the PowerShell query it replaces took 20 to 27 seconds of its 30
    inside the gate's white-listed environment); elsewhere ``ps`` is asked.
    """

    if sys.platform == "win32":
        return windows_command_lines()
    else:
        return _ps_processes()


def _ps_processes() -> tuple[list[tuple[int, int, str]] | None, str]:
    command = ["ps", "-eo", "pid=,ppid=,args="]
    try:
        done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",  # lenient-decode: 进程命令行只用来匹配关键字
                              timeout=PROCESS_LIST_TIMEOUT_SECONDS, check=False)  # noqa: S603 - fixed argv, no shell
    except subprocess.TimeoutExpired:
        return None, f"ps 超过 {PROCESS_LIST_TIMEOUT_SECONDS} 秒没返回"
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"ps 起不来：{type(exc).__name__}: {exc}"
    if done.returncode != 0:
        return None, f"ps 退出码 {done.returncode}：{(done.stderr or '').strip()[:200] or '没有错误输出'}"
    rows: list[tuple[int, int, str]] = []
    for raw in done.stdout.splitlines():
        parts = raw.strip().split(None, 2)
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            rows.append((int(parts[0]), int(parts[1]), parts[2] if len(parts) > 2 else ""))
    return (rows, "") if rows else (None, f"ps 的输出里没有一行进程（共 {len(done.stdout.splitlines())} 行）")


_PYTHON_EXE = re.compile(r"python(\d+(\.\d+)*)?w?(\.exe)?", re.IGNORECASE)


def _runs_python(command_line: str) -> bool:
    """True when the process *is* a Python interpreter: argv[0]'s base name, not any ``python`` further along the line.

    A ``bash -c "...python -m pytest..."`` wrapper mentions both words but is a shell, and is finished when its child is.
    """

    text = command_line.strip()
    if text.startswith('"'):
        end = text.find('"', 1)
        first = text[1:end] if end > 0 else text[1:]
    else:
        first = text.split(maxsplit=1)[0] if text else ""
    return _PYTHON_EXE.fullmatch(first.replace("\\", "/").rsplit("/", 1)[-1]) is not None


def _busy_processes(rows: list[tuple[int, int, str]]) -> list[str]:
    parents = {pid: parent for pid, parent, _line in rows}
    mine: set[int] = set()
    pid = os.getpid()
    while pid and pid not in mine:  # this command and whatever launched it are not "busy"
        mine.add(pid)
        pid = parents.get(pid, 0)
    return [str(pid) for pid, _parent, line in rows if pid not in mine and _runs_python(line) and any(m in line for m in BUSY_PROCESS_MARKERS)]


def _check_busy(root: Path, report: Preflight) -> None:
    if (root / HEAVY_GATES_MARKER).exists():
        report.add("没有重型门禁在跑", FAIL, f"{HEAVY_GATES_MARKER.as_posix()} 存在")
        return
    rows, why = _list_processes()
    if rows is None:
        report.add("没有测试或驾驶舱进程在跑", UNVERIFIED, f"系统进程列表读不出来，没法确认（{why}）")
        return
    busy = _busy_processes(rows)
    report.add("没有测试或驾驶舱进程在跑", FAIL if busy else PASS, f"在跑的进程：{','.join(busy[:5])}" if busy else "无")


def _check_disk(root: Path, report: Preflight) -> None:
    free = shutil.disk_usage(root).free
    report.add("磁盘余量", PASS if free >= MIN_FREE_BYTES else FAIL, f"剩 {free // 1024**2} MiB（至少 {MIN_FREE_BYTES // 1024**2} MiB）")


def exact_tree_ok(base: Path, release_id: str) -> tuple[bool, str]:
    """The launcher's own exact-tree check of one installed release (the same call ``pmf_release_ops.sh verify`` makes)."""

    launcher = base / "launcher" / "bootstrap.py"
    if not launcher.is_file():
        return False, "没有 launcher/bootstrap.py"
    code = (
        "import sys\nfrom pathlib import Path\nc=Path(sys.argv[1]); sys.path.insert(0,str(c/'launcher'))\n"
        "import bootstrap as b\nb._resolve_slot(c,'verify',sys.argv[2])\nprint('exact-tree OK',sys.argv[2])\n"
    )
    try:
        done = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, "-B", "-c", code, str(base), release_id],
            capture_output=True, text=True, encoding="utf-8", errors="replace",  # lenient-decode: 子进程输出只用来展示失败原因
            timeout=EXACT_TREE_TIMEOUT_SECONDS, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return False, str(error)
    if done.returncode == 0:
        return True, done.stdout.strip()
    return False, (done.stderr.strip().splitlines() or [""])[-1]


def _check_exact_trees(base: Path, ids: list[str], report: Preflight) -> None:
    if not (base / "launcher" / "bootstrap.py").is_file():
        report.add("已装发布逐文件校验", UNVERIFIED, "没有 launcher/bootstrap.py，没法校验")
        return
    for release in dict.fromkeys(ids):
        good, detail = exact_tree_ok(base, release)
        report.add(f"发布 {release} 逐文件校验", PASS if good else FAIL, detail)


def preflight(
    root: Path, commit_spec: str, *, gate_verdict: Path | None = None, audit_signoff: Path | None = None
) -> Preflight:
    """Every read-only check that decides whether ``commit_spec`` may be deployed from control root ``root``."""

    root = Path(root)
    base = root / CONTAINER
    report = Preflight()
    _check_commit(root, commit_spec, report)
    if report.commit:
        report.release_id = release_id_for(root, report.commit)
    _check_slot(base, report)
    ids = _check_pointers(base, report)
    _check_consistency(root, report)
    _check_exact_trees(base, ids, report)
    _check_gate(gate_verdict, report.commit, report)
    _check_audit(audit_signoff, report.commit, gate_verdict, report)
    _check_busy(root, report)
    _check_disk(root, report)
    return report


def status(root: Path) -> dict[str, Any]:
    """``release status``: what is configured, what is installed, and the latest deploy receipt on disk.  Read-only."""

    root = Path(root)
    base = root / CONTAINER
    pointers: dict[str, Any] = {}
    for name in ("active_release.json", "previous_release.json"):
        data = _json(base / name)
        pointers[name.split("_")[0]] = {"release_id": (data or {}).get("release_id"), "updated_at": (data or {}).get("updated_at")}
    manifest = _json(base / "deployment_manifest.json")
    releases = sorted((manifest or {}).get("releases", {})) if manifest else []
    receipts = sorted((root / ".auto-pm" / "reports").glob(f"{EVIDENCE_PREFIX}*/receipt.json"), key=lambda p: p.stat().st_mtime) if (root / ".auto-pm" / "reports").is_dir() else []
    consistency = check_release_consistency(str(root))
    return {
        "pointers": pointers,
        "installed_releases": releases,
        "consistency": {"status": consistency.get("status"), "failures": consistency.get("failures", [])},
        "last_receipt": str(receipts[-1]) if receipts else None,
    }
