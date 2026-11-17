"""One command for a release: ``release ship <commit>`` (CHG-SCPT-2026-706).

``release deploy`` already does preflight → books → build → switch → self-checks → automatic rollback, but it needs six arguments and
the person running it had to fetch the cloud gate verdict by hand, find the audit signoff, and know where the event-chain drill script
and the precheck card live.  ``ship`` gathers all of that for one commit and hands it to the same preflight and the same real deploy:

* the gate verdict is downloaded from the cloud ``gate-full`` run of that exact commit (artifact ``gate-verdict-<sha12>``, or the older
  ``gate-verdict``) into ``.auto-pm/release-candidates/<release id>/gate_verdict.json``;
* the audit signoff is read from ``.auto-pm/release-candidates/<release id>/audit_signoff.md`` (the audit puts it there);
* the drill script is a fixed file in the repository; the intake card is generated for this release by the real deploy
  (``release_card``: ``.auto-pm/release-candidates/<release id>/release_card.md``, CHG-SCPT-2026-709).

Without ``confirm_ref`` the releases, pointers and ledger are not touched (only the verdict is cached in the candidate folder): a look
the dashboard's release page can show.  The output dictionary is the contract in ``.auto-pm/reports/release_ship_接口约定_20261117.md``.
Opening the release-intake pull requests stays a separate step (``release_intake`` plans the slices; its git/GitHub adapter is a later card).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from auto_pm.application.core import release_deploy_check as check
from auto_pm.application.core import release_ops as ops

CANDIDATES_DIR = Path(".auto-pm") / "release-candidates"
DRILL_SCRIPT = Path(check.PROJECT_DIR) / "scripts" / "release_event_chain_drill.py"
GATE_WORKFLOW = "gate-full.yml"
_MERGE_PR = re.compile(r"^Merge pull request #(\d+) from \S+\s*(.*)$")


class GitHubPort(Protocol):
    def gate_runs(self, commit: str) -> list[dict[str, Any]]: ...

    def download_verdict(self, run_id: int, commit: str, dest: Path) -> Path | None: ...


@dataclass
class ShipReport:
    commit: str
    release_id: str
    active_release: str
    gate: dict[str, Any]
    audit: dict[str, Any]
    preflight: dict[str, Any]
    changes: list[dict[str, Any]] = field(default_factory=list)
    deployed: bool = False
    result: dict[str, Any] | None = None

    @property
    def can_switch(self) -> bool:
        return (
            bool(self.preflight.get("ok"))
            and self.gate.get("state") == "pass"
            and self.audit.get("state") == "present"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "commit": self.commit,
            "release_id": self.release_id,
            "active_release": self.active_release,
            "gate": self.gate,
            "audit": self.audit,
            "preflight": self.preflight,
            "changes": self.changes,
            "can_switch": self.can_switch,
            "deployed": self.deployed,
            "result": self.result,
        }


def candidate_dir(root: Path, release_id: str) -> Path:
    return Path(root) / CANDIDATES_DIR / release_id


def _gate(
    root: Path, commit: str, release_id: str, github: GitHubPort
) -> tuple[dict[str, Any], Path | None]:
    target = candidate_dir(root, release_id) / "gate_verdict.json"
    try:
        runs = github.gate_runs(commit)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        if target.is_file():
            note = target.with_name("gate_verdict.run")
            cached = note.read_text(encoding="utf-8").strip() if note.is_file() else ""
            return _verdict_info(
                target,
                int(cached) if cached.isdigit() else None,
                "",
                "拿不到 GitHub 上的运行记录，用的是上次下载的判决（可能不是最新一轮）",
            ), target
        return {
            "state": "error",
            "run_id": None,
            "run_url": "",
            "verdict_path": "",
            "verdict_sha256": "",
            "detail": f"拿不到 GitHub 上的运行记录：{error}",
        }, None
    if not runs:
        return {
            "state": "missing",
            "run_id": None,
            "run_url": "",
            "verdict_path": "",
            "verdict_sha256": "",
            "detail": f"提交 {commit[:12]} 还没跑过云端 gate-full",
        }, None
    run = runs[0]  # newest first
    run_id, url = int(run["id"]), str(run.get("url", ""))
    if run.get("status") != "completed":
        return {
            "state": "running",
            "run_id": run_id,
            "run_url": url,
            "verdict_path": "",
            "verdict_sha256": "",
            "detail": "云端 gate-full 还在跑",
        }, None
    run_note = target.with_name("gate_verdict.run")
    cached_run = run_note.read_text(encoding="utf-8").strip() if run_note.is_file() else ""
    if target.is_file() and cached_run != str(run_id):
        target.unlink()  # a newer gate run of the same commit: the cached verdict belongs to another run
    if not target.is_file():
        downloaded = github.download_verdict(run_id, commit, target.parent)
        if downloaded is None:
            return {
                "state": "error",
                "run_id": run_id,
                "run_url": url,
                "verdict_path": "",
                "verdict_sha256": "",
                "detail": "运行结束了，但下载不到判决产物",
            }, None
        if downloaded != target:
            shutil.copyfile(downloaded, target)
        run_note.write_text(str(run_id), encoding="utf-8")
    return _verdict_info(target, run_id, url, ""), target


def _verdict_info(path: Path, run_id: int | None, url: str, note: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {
            "state": "error",
            "run_id": run_id,
            "run_url": url,
            "verdict_path": str(path),
            "verdict_sha256": "",
            "detail": "判决文件读不出",
        }
    verdict = str(data.get("verdict", ""))
    return {
        "state": "pass" if verdict.startswith("PASS") else "fail",
        "run_id": run_id,
        "run_url": url,
        "verdict_path": str(path),
        "verdict_sha256": check._sha256(path),  # noqa: SLF001 - the same digest the audit line carries
        "detail": note or f"判决 {verdict[:60]}",
    }


def _audit(root: Path, release_id: str) -> tuple[dict[str, Any], Path | None]:
    path = candidate_dir(root, release_id) / "audit_signoff.md"
    if path.is_file():
        return {
            "state": "present",
            "path": str(path),
            "detail": "审计签字在，内容由预检逐字核",
        }, path
    return {
        "state": "missing",
        "path": str(path),
        "detail": "还没有审计签字（审计把放行记录放到这个位置）",
    }, None


def _changes(root: Path, active_release: str, commit: str) -> list[dict[str, Any]]:
    base = active_release.rsplit("-", 1)[-1] if active_release else ""
    if not base or not commit:
        return []
    out = check._git(
        root, "log", "--first-parent", "--merges", "--format=%s%x09%b", f"{base}..{commit}"
    )  # noqa: SLF001
    changes: list[dict[str, Any]] = []
    for line in (out or "").splitlines():
        subject, _, body = line.partition("\t")
        found = _MERGE_PR.match(subject)
        if found:
            changes.append(
                {"pr": int(found.group(1)), "title": body.strip() or found.group(2).strip()}
            )
    return changes


def ship(
    root: Path,
    commit_spec: str,
    *,
    github: GitHubPort,
    confirm_ref: str = "",
    approver: str = "",
    deploy: Callable[..., Any] | None = None,
) -> ShipReport:
    """Gather the verdict and the signoff for ``commit_spec`` and run the preflight; with ``confirm_ref`` also run the real deploy."""

    root = Path(root)
    first = check.preflight(root, commit_spec)  # only to resolve the commit and the release id
    commit, release_id = first.commit, first.release_id
    active = ops.pointer_release(ops.container_of(root), "active_release.json")
    gate, verdict_path = (
        _gate(root, commit, release_id, github)
        if commit and release_id
        else (
            {
                "state": "missing",
                "run_id": None,
                "run_url": "",
                "verdict_path": "",
                "verdict_sha256": "",
                "detail": "提交认不出",
            },
            None,
        )
    )
    audit, signoff_path = (
        _audit(root, release_id)
        if release_id
        else ({"state": "missing", "path": "", "detail": "发布号认不出"}, None)
    )
    report = check.preflight(
        root, commit_spec, gate_verdict=verdict_path, audit_signoff=signoff_path
    )
    ship_report = ShipReport(
        commit=commit,
        release_id=release_id,
        active_release=active,
        gate=gate,
        audit=audit,
        preflight={
            "ok": report.ok,
            "checks": [
                {"name": c.name, "ok": c.status == check.PASS, "detail": c.detail}
                for c in report.checks
            ],
        },
        changes=_changes(root, active, commit),
    )
    if not confirm_ref:
        return ship_report
    if not ship_report.can_switch:
        ship_report.result = {
            "ok": False,
            "rolled_back": False,
            "receipt": "",
            "backup": "",
            "change_id": "",
            "message": "预检没过，什么都没写",
        }
        return ship_report
    from auto_pm.application.core import release_wiring as wiring
    from auto_pm.application.core.release_deploy import DeployError

    run_deploy = deploy or wiring.real_deploy
    ship_report.deployed = True
    try:
        done = run_deploy(
            root,
            report,
            approver=approver,
            confirm_ref=confirm_ref,
            card_file=None,  # the deploy writes this release's own intake card (CHG-SCPT-2026-709)
            drill_script=root / DRILL_SCRIPT,
        )
    except DeployError as error:
        ship_report.result = {
            "ok": False,
            "rolled_back": error.rolled_back,
            "receipt": "",
            "backup": "",
            "change_id": "",
            "message": str(error),
        }
        return ship_report
    ship_report.result = {
        "ok": True,
        "rolled_back": False,
        "receipt": str(done.receipt),
        "backup": str(done.backup),
        "change_id": done.change_id,
        "message": f"已部署 {done.release_id}；发布记录（指针、清单、发布目录）还要开入账 PR",
    }
    return ship_report


class GhCli:
    """The real :class:`GitHubPort`: the ``gh`` command line, which the control root already uses for pull requests."""

    def __init__(
        self, root: Path, run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run
    ) -> None:
        self._root = Path(root)
        self._run = run

    def _gh(self, *args: str) -> str:
        done = self._run(
            ["gh", *args],
            cwd=self._root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )  # lenient-decode: gh 输出只用来解析 JSON 和路径
        if done.returncode != 0:
            raise OSError((done.stderr or done.stdout or "gh 出错").strip()[-200:])
        return done.stdout

    def gate_runs(self, commit: str) -> list[dict[str, Any]]:
        data = json.loads(
            self._gh(
                "run",
                "list",
                "--workflow",
                GATE_WORKFLOW,
                "--commit",
                commit,
                "--limit",
                "5",
                "--json",
                "databaseId,status,conclusion,url,createdAt",
            )
        )
        runs = sorted(data, key=lambda r: str(r.get("createdAt", "")), reverse=True)
        return [
            {
                "id": r["databaseId"],
                "status": r.get("status"),
                "conclusion": r.get("conclusion"),
                "url": r.get("url", ""),
            }
            for r in runs
        ]

    def download_verdict(self, run_id: int, commit: str, dest: Path) -> Path | None:
        dest.mkdir(parents=True, exist_ok=True)
        for name in (f"gate-verdict-{commit[:12]}", "gate-verdict"):
            scratch = dest / f"_download_{name}"
            try:
                self._gh("run", "download", str(run_id), "-n", name, "-D", str(scratch))
            except OSError:
                continue
            summary = scratch / "gate_summary.json"
            if summary.is_file():
                target = dest / "gate_verdict.json"
                shutil.copyfile(summary, target)
                shutil.rmtree(scratch, ignore_errors=True)
                return target
            shutil.rmtree(scratch, ignore_errors=True)
        return None
