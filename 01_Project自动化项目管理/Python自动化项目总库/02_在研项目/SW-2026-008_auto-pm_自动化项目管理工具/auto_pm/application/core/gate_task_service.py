"""Identity and lifecycle for the shared full regression gate."""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Protocol

from auto_pm.application.core.gate_run_service import (
    ENV_ALLOW,
    SUMMARY_FILE,
    GateRunError,
    GateRunService,
    child_environment,
    manifest_sha256,
    project_dir_in,
    pytest_counts,
    sha256_file,
)
from auto_pm.application.core.gate_tier_policy import classify_gate_tier
from auto_pm.infrastructure.executable_lookup import find_on_path
from auto_pm.infrastructure.gate_executors import run_command
from auto_pm.infrastructure.gate_task_store import GateAttempt, GateTaskStore

# Increment when execution or receipt semantics change independently of the group manifest.
POLICY = "gate-full-v1"
POLICY_L2 = "gate-l2-v1"
TERMINAL = {"failed", "stopped", "unavailable", "passed"}
LSP_SHA256 = "690f0c692350956416d6b2768f48a1daa119dd6c5b55c6b25bb6fa19f4951985"
WORKFLOW = "gate-full.yml"
LOCK = Path("00_Infrastructure/auto_pm/environment/requirements-lock-py312-win.txt")


def git(path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", str(path), *args],
        capture_output=True, encoding="utf-8", errors="replace",  # lenient-decode: Git diagnostics may use the host code page
        timeout=30, check=False,
    )
    if result.returncode:
        raise GateRunError(f"Git 无法核对候选：{result.stderr.strip()}")
    return result.stdout.strip()


def _trusted_rules_project(root: Path, fallback_project: Path) -> Path:
    """Prefer the control root's tier rules so a candidate branch cannot weaken L2->L3 checks."""
    try:
        root_project = project_dir_in(root)
    except GateRunError:
        return fallback_project
    if (root_project / "tests" / "tools" / "tier_core_list.json").is_file():
        return root_project
    return fallback_project


@dataclass(frozen=True)
class GateCandidate:
    commit: str
    tree: str
    base: str
    manifest: str
    policy: str
    tier: str = "L3"
    groups: tuple[str, ...] = ()

    @classmethod
    def from_worktree(cls, root: Path, worktree: Path, *, full: bool = False) -> GateCandidate:
        if Path(git(worktree, "rev-parse", "--show-toplevel")).resolve() != worktree:
            raise GateRunError("请指定工位的 Git 根目录")
        if Path(git(worktree, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve() != (
            Path(git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
        ):
            raise GateRunError("工位与控制根不属于同一本 Git 仓库")
        if git(worktree, "status", "--porcelain", "--untracked-files=all"):
            raise GateRunError("候选工位有未提交内容")
        project = project_dir_in(worktree)
        commit = git(worktree, "rev-parse", "HEAD")
        base = git(root, "rev-parse", "refs/heads/main")
        if commit == base or git(root, "merge-base", base, commit) != base:
            raise GateRunError("候选必须基于当前 main，且包含待合并提交")
        tree = git(worktree, "rev-parse", f"{commit}^{{tree}}")
        manifest = manifest_sha256()
        if not full:
            raw_diff = git(worktree, "-c", "core.quotepath=false", "diff", "--name-only", "--no-renames", f"{base}..{commit}")
            changed = [line.strip() for line in raw_diff.splitlines() if line.strip()]
            top_resolved = worktree.resolve()
            proj_resolved = project.resolve()
            prefix = (proj_resolved.relative_to(top_resolved).as_posix() + "/") if proj_resolved != top_resolved else ""
            inside = [path[len(prefix) :] for path in changed if not prefix or path.startswith(prefix)]
            outside = [path for path in changed if prefix and not path.startswith(prefix)]
            rules_project = _trusted_rules_project(root, project)
            decision = classify_gate_tier(inside, project=rules_project, outside_changes=outside)
            if decision.tier != "L3" and decision.recommended_groups:
                return cls(commit, tree, base, manifest, POLICY_L2, tier="L2", groups=decision.recommended_groups)
        return cls(commit, tree, base, manifest, POLICY, tier="L3", groups=())

    @classmethod
    def from_key(cls, raw: str) -> GateCandidate:
        data = json.loads(raw)
        return cls(
            commit=str(data["commit"]),
            tree=str(data["tree"]),
            base=str(data["base"]),
            manifest=str(data["manifest"]),
            policy=str(data["policy"]),
            tier=str(data.get("tier") or "L3"),
            groups=tuple(str(g) for g in (data.get("groups") or ()) if str(g)),
        )

    def as_full(self) -> GateCandidate:
        if self.tier == "L3" and not self.groups and self.policy == POLICY:
            return self
        return GateCandidate(self.commit, self.tree, self.base, self.manifest, POLICY, tier="L3", groups=())

    @property
    def key(self) -> str:
        payload: dict[str, Any] = {
            "base": self.base,
            "commit": self.commit,
            "manifest": self.manifest,
            "policy": self.policy,
            "tree": self.tree,
        }
        if self.tier != "L3":
            payload["tier"] = self.tier
            payload["groups"] = list(self.groups)
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class Observation:
    state: str
    handle: str = ""
    detail: str = ""


class Executor(Protocol):
    def launch(self, attempt: GateAttempt, candidate: GateCandidate) -> Observation: ...
    def inspect(self, attempt: GateAttempt, candidate: GateCandidate) -> Observation: ...
    def stop(self, attempt: GateAttempt) -> None: ...


class GateTaskService:
    def __init__(self, store: GateTaskStore, cloud: Executor, local: Executor) -> None:
        self.store = store
        self.executors = {"github": cloud, "local": local}

    def start(self, candidate: GateCandidate) -> GateAttempt:
        if candidate.tier == "L2":
            existing_full = self.store.latest(candidate.as_full().key)
            if existing_full is not None:
                refreshed = self.status(existing_full.id)
                if refreshed.state in {"queued", "running", "passed"}:
                    return refreshed
        attempt, new = self.store.reserve(candidate.key, "github")
        return self._launch(attempt, candidate) if new else self.status(attempt.id)

    def status(self, attempt_id: str) -> GateAttempt:
        attempt = self._get(attempt_id)
        if attempt.state in TERMINAL:
            return attempt
        candidate = GateCandidate.from_key(attempt.key)
        result = self.executors[attempt.backend].inspect(attempt, candidate)
        return self.store.observe(attempt, result.state, result.handle, result.detail)

    def current(self, candidate: GateCandidate) -> GateAttempt | None:
        if candidate.tier == "L2":
            existing_full = self.store.latest(candidate.as_full().key)
            if existing_full is not None:
                refreshed_full = self._refresh_attempt(existing_full, candidate.as_full())
                if refreshed_full.state in {"queued", "running", "passed"}:
                    return refreshed_full
        attempt = self.store.latest(candidate.key)
        if attempt is None:
            return None
        return self._refresh_attempt(attempt, candidate)

    def _refresh_attempt(self, attempt: GateAttempt, candidate: GateCandidate) -> GateAttempt:
        attempt = self.status(attempt.id)
        if attempt.backend == "local" and attempt.state == "passed":
            result = self.executors["local"].inspect(attempt, candidate)
            if result.state != "passed" or result.detail != attempt.detail:
                raise GateRunError("本机门禁的原始日志或摘要无法按原凭证复核")
        return attempt

    def stop(self, attempt_id: str) -> GateAttempt:
        attempt = self.status(attempt_id)
        if attempt.state in TERMINAL:
            return attempt
        if not attempt.handle:
            raise GateRunError("尚无法确认执行端已接单，不能请求停止。请先查状态")
        self.executors[attempt.backend].stop(attempt)
        return self.status(attempt.id)

    def retry(
        self, attempt_id: str, candidate: GateCandidate, *, local: bool = False, approval: str = ""
    ) -> GateAttempt:
        previous = self.status(attempt_id)
        if candidate.key != previous.key:
            raise GateRunError("候选、main 或门禁规则已变更。请用 gate start 登记新任务")
        if local and candidate.tier != "L3":
            raise GateRunError("L2 分组门禁仅支持 GitHub 云端执行；如需切换本机请加 --full")
        if previous.state not in {"failed", "stopped", "unavailable"}:
            raise GateRunError(f"当前状态 {previous.state} 无法重试")
        if local and (
            (previous.state not in {"stopped", "unavailable"}
             and not (previous.backend == "local" and previous.state == "failed"))
            or not re.fullmatch(r"user-confirmation:[^\s]+", approval)
        ):
            raise GateRunError("本机切换需要已确认停止或不可用的执行端，以及用户确认引用")
        attempt, new = self.store.reserve(
            candidate.key, "local" if local else "github", previous_id=previous.id, approval=approval
        )
        return self._launch(attempt, candidate) if new else self.status(attempt.id)

    def _get(self, attempt_id: str) -> GateAttempt:
        attempt = self.store.get(attempt_id)
        if attempt is None:
            raise GateRunError(f"找不到门禁任务 {attempt_id}")
        return attempt

    def _launch(self, attempt: GateAttempt, candidate: GateCandidate) -> GateAttempt:
        result = self.executors[attempt.backend].launch(attempt, candidate)
        # Concurrent status checks may already have learned the execution handle.
        current = self._get(attempt.id)
        if current.state != "unknown" or current.handle:
            return current
        return self.store.observe(current, result.state, result.handle, result.detail)


def _json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _github_unreachable(error: str) -> bool:
    return bool(re.search(
        r"no such host|could not resolve|connection refused|network is unreachable|"
        r"timeout|HTTP (?:429|5[0-9]{2})",
        error,
        re.IGNORECASE,
    ))


class GitHubGateExecutor:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _disabled(self) -> bool:
        path = self.root / ".auto-pm/reports/local_merge/github_mode.json"
        return path.is_file() and _json_file(path).get("mode") == "关"

    def _repo(self) -> str:
        remote = git(self.root, "remote", "get-url", "origin").removesuffix(".git")
        match = re.fullmatch(r"(?:https://github\.com/|git@github\.com:)([\w.-]+/[\w.-]+)", remote)
        if not match:
            raise GateRunError("origin 未指向 github.com 仓库")
        return match[1]

    def _gh(self, *args: str) -> subprocess.CompletedProcess[str]:
        return run_command(self.root, ["gh", *args, "--repo", self._repo()])

    @staticmethod
    def _title(attempt: GateAttempt, candidate: GateCandidate) -> str:
        return f"gate-full {attempt.id} {candidate.commit}"

    @staticmethod
    def _supports_tasks(encoded: str, *, tier: str = "L3") -> bool:
        try:
            workflow = base64.b64decode(encoded).decode("utf-8")
        except ValueError:
            return False
        base_ok = "      task_id:" in workflow and "      candidate_sha:" in workflow and "      base_sha:" in workflow
        if tier == "L2":
            return base_ok and "      requested_tier:" in workflow
        return base_ok

    def launch(self, attempt: GateAttempt, candidate: GateCandidate) -> Observation:
        try:
            if self._disabled():
                return Observation("unavailable", detail="GitHub 档位为关，尚未派发")
            repo = self._repo()
        except (GateRunError, ValueError, OSError, subprocess.TimeoutExpired) as error:
            return Observation("failed", detail=f"GitHub 配置无法核对，尚未派发：{error}")
        try:
            probe = run_command(self.root, ["gh", "api", f"repos/{repo}/branches/main", "--jq", ".commit.sha"])
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return Observation("unavailable", detail="GitHub CLI 不可用或只读探测超时，尚未派发")
        if probe.returncode:
            if _github_unreachable(probe.stderr):
                return Observation("unavailable", detail="GitHub 只读探测确认无法连接，尚未派发")
            return Observation("failed", detail="GitHub 只读探测失败，请检查 gh 登录和仓库权限")
        if probe.stdout.strip() != candidate.base:
            return Observation("failed", detail="远端 main 和候选基线不同，请先核对同步")
        try:
            target = run_command(self.root, ["gh", "api", f"repos/{repo}/git/commits/{candidate.commit}", "--jq", ".tree.sha"])
            workflow = run_command(self.root, [
                "gh", "api", f"repos/{repo}/contents/.github/workflows/{WORKFLOW}?ref={candidate.base}",
                "--jq", ".content",
            ])
        except (OSError, subprocess.TimeoutExpired):
            return Observation("unavailable", detail="只读候选探测失败，尚未派发")
        if any(result.returncode and _github_unreachable(result.stderr) for result in (target, workflow)):
            return Observation("unavailable", detail="GitHub 候选只读探测中断，尚未派发")
        if target.returncode or target.stdout.strip() != candidate.tree:
            return Observation("failed", detail="GitHub 上找不到该候选及其 Git tree，请先推送候选分支")
        if workflow.returncode or not self._supports_tasks(workflow.stdout, tier=candidate.tier):
            if candidate.tier == "L2":
                return Observation(
                    "failed",
                    detail="GitHub main 的 gate-full 尚不支持 L2 分档（请先合入支持 requested_tier 的工作流或加 --full）",
                )
            return Observation("failed", detail="GitHub main 的 gate-full 尚不支持驾驶舱任务号")
        dispatch_args = [
            "workflow", "run", WORKFLOW, "--ref", "main",
            "-f", f"task_id={attempt.id}", "-f", f"candidate_sha={candidate.commit}",
            "-f", f"base_sha={candidate.base}",
        ]
        if candidate.tier == "L2":
            dispatch_args.extend(["-f", "requested_tier=L2"])
        try:
            result = self._gh(*dispatch_args)
        except (OSError, subprocess.TimeoutExpired):
            return Observation("unknown", detail="派发结果未知；按任务号对账后才可以重跑")
        if result.returncode:
            if re.search(r"HTTP (400|401|403|404|422|429)\b", result.stderr):
                return Observation("failed", detail="GitHub 明确拒绝派发，请检查权限、工作流及候选输入")
            return Observation("unknown", detail="派发未获确认；按任务号对账后才可以重跑")
        return Observation("queued", detail="已提交派发，等待匹配运行号")

    def _find(self, attempt: GateAttempt, candidate: GateCandidate) -> dict[str, Any] | None:
        fields = "databaseId,displayTitle,headSha,status,conclusion,url"
        if attempt.handle:
            result = self._gh("run", "view", attempt.handle, "--json", fields)
        else:
            result = self._gh(
                "run", "list", "--workflow", WORKFLOW, "--event", "workflow_dispatch", "--branch", "main",
                "--limit", "100", "--json", fields,
            )
        if result.returncode:
            raise GateRunError("GitHub 暂时无法核对运行状态")
        data = json.loads(result.stdout)
        runs = [data] if attempt.handle else data
        matches = [row for row in runs if row["displayTitle"] == self._title(attempt, candidate)]
        if len(matches) > 1:
            raise GateRunError("任务号匹配多个 GitHub 运行，需要人工核对")
        return matches[0] if matches else None

    def inspect(self, attempt: GateAttempt, candidate: GateCandidate) -> Observation:
        if self._disabled():
            return Observation(attempt.state, detail="GitHub 档位为关，保留现有执行状态")
        try:
            run = self._find(attempt, candidate)
            if run is None:
                return Observation(attempt.state, detail="暂未发现匹配运行，保留现有执行状态")
            handle = str(run["databaseId"])
            if run["headSha"] != candidate.base and run["status"] == "completed":
                return Observation("failed", handle, "运行使用了不同的受信任工作流基线")
            if run["status"] != "completed":
                return Observation("running" if run["status"] == "in_progress" else "queued", handle, run["url"])
            if run["conclusion"] == "cancelled":
                return Observation("stopped", handle, run["url"])
            if run["conclusion"] != "success":
                return Observation("failed", handle, run["url"])
            return self._receipt(handle, candidate, run["url"])
        except (GateRunError, OSError, subprocess.TimeoutExpired, ValueError, KeyError) as error:
            return Observation(attempt.state, detail=str(error))

    def _receipt(self, handle: str, candidate: GateCandidate, url: str) -> Observation:
        artifact = (
            f"gate-verdict-l2-{candidate.commit[:12]}"
            if candidate.tier == "L2"
            else f"gate-verdict-{candidate.commit[:12]}"
        )
        with TemporaryDirectory(prefix="gate-receipt-") as temp:
            result = self._gh("run", "download", handle, "--name", artifact, "--dir", temp)
            if result.returncode:
                raise GateRunError("运行已结束，暂时无法下载判卷产物")
            path = Path(temp) / SUMMARY_FILE
            record = _json_file(path)
            digest = sha256_file(path)
        repo = self._repo()
        response = run_command(
            self.root, ["gh", "api", f"repos/{repo}/commits/{candidate.commit}/statuses", "--paginate", "--slurp"]
        )
        if response.returncode:
            raise GateRunError("暂时无法核对 GitHub 提交状态")
        expected_context = "gate-l2" if candidate.tier == "L2" else "gate-full"
        matches = [
            status for page in json.loads(response.stdout) for status in page
            if status["context"] == expected_context and status["target_url"] == url
            and status.get("creator", {}).get("login") == "github-actions[bot]"
        ]
        if not digest or not matches or matches[0]["state"] != "success":
            return Observation("failed", handle, "GitHub 判卷、插件结果或候选指纹不匹配")
        if candidate.tier == "L2":
            allowed_descriptions = {
                f"PASS: verdict PASS tier L2 sha256 {digest}, plugin skipped",
                f"PASS: verdict PASS tier L2 sha256 {digest}, plugin success",
            }
            raw_results = record.get("results")
            results_ok = (
                isinstance(raw_results, dict)
                and bool(raw_results)
                and set(raw_results) == set(candidate.groups)
                and all(isinstance(v, dict) and v.get("verdict") == "PASS" for v in raw_results.values())
            )
            if (
                matches[0]["description"] in allowed_descriptions
                and record.get("tier") == "L2"
                and record.get("verdict") == "PASS"
                and record.get("commit") == candidate.commit
                and record.get("commit_end") == candidate.commit
                and record.get("complete") is False
                and record.get("manifest_sha256") == candidate.manifest
                and tuple(record.get("expected_groups") or ()) == candidate.groups
                and not record.get("reasons")
                and results_ok
            ):
                return Observation("passed", handle, json.dumps({"url": url, "sha256": digest, "tier": "L2"}))
            return Observation("failed", handle, "GitHub L2 判卷、分组或候选指纹不匹配")
        if (
            matches[0]["description"] == f"PASS: verdict PASS sha256 {digest}, plugin success"
            and record.get("verdict") == "PASS" and record.get("commit") == candidate.commit
            and record.get("commit_end") == candidate.commit and record.get("complete") is True
            and record.get("manifest_sha256") == candidate.manifest
            and record.get("tier", "L3") == "L3"
        ):
            return Observation("passed", handle, json.dumps({"url": url, "sha256": digest}))
        return Observation("failed", handle, "GitHub 判卷、插件结果或候选指纹不匹配")

    def stop(self, attempt: GateAttempt) -> None:
        if self._disabled() or self._gh("run", "cancel", attempt.handle).returncode:
            raise GateRunError("GitHub 未确认停止请求，请查任务状态")


class LocalGateExecutor:
    def __init__(self, root: Path, worktree: Path | None = None, plugin: Path | None = None) -> None:
        self.root = root
        self.worktree = worktree
        self.plugin = plugin

    def _folder(self, attempt: GateAttempt) -> Path:
        return self.root / ".auto-pm/reports/gate-tasks" / attempt.id

    def _runner(self, attempt: GateAttempt, command: str, *args: str) -> subprocess.CompletedProcess[str]:
        script = project_dir_in(self.root) / "scripts/long_gate.py"
        return run_command(self.root, [
            sys.executable, "-B", str(script), command, "--config", str(self._folder(attempt) / "task.json"), *args
        ])

    def _preflight(self) -> str:
        if os.name != "nt":
            return "本机门禁需要 Windows 交互式登录账户"
        if self.plugin is None or sha256_file(self.plugin) != LSP_SHA256:
            return "离线 Siemens LSP 缺失或 SHA-256 不匹配，请给出锁定版本的 --siemens-lsp"
        go = find_on_path("go")
        if go is None or run_command(self.root, [go, "version"]).returncode:
            return "离线 Go 工具链不可用"
        if sys.version_info[:2] != (3, 12):
            return "离线 Python 需要 3.12"
        if self.worktree is None:
            return "缺少候选工位"
        locked = (self.worktree / LOCK).read_text(encoding="utf-8").splitlines()
        expected = {row.lower() for row in locked if row and not row.lstrip().startswith("#")}
        installed = run_command(self.root, [sys.executable, "-m", "pip", "freeze", "--all"])
        if installed.returncode or expected.difference(installed.stdout.lower().splitlines()):
            return "离线 Python 依赖未按候选锁定表安装"
        if run_command(self.root, [sys.executable, "-m", "pip", "check"]).returncode:
            return "离线 Python 依赖一致性检查失败"
        return ""

    def launch(self, attempt: GateAttempt, candidate: GateCandidate) -> Observation:
        if candidate.tier != "L3":
            return Observation("failed", detail="本机执行端仅支持 L3 全量门禁")
        folder = self._folder(attempt)
        worktree, plugin = self.worktree, self.plugin
        try:
            refusal = self._preflight()
            if refusal or worktree is None or plugin is None:
                return Observation("unavailable", detail=refusal)
            if GateCandidate.from_worktree(self.root, worktree, full=True) != candidate:
                return Observation("failed", detail="本机派发前候选已变更")
            folder.mkdir(parents=True)
            project = project_dir_in(worktree)
            evidence = folder / "evidence"
            config = {
                "name": f"gate-full-{attempt.id}",
                "root": str(self.root),
                "out_dir": str(folder / "runner"),
                "env_allow": sorted(ENV_ALLOW),
                "env": child_environment({}),
                "fingerprint": {
                    "git_worktree": str(worktree),
                    "expected_commit": candidate.commit,
                    "plugin": {"path": str(plugin), "sha256": LSP_SHA256},
                },
                "steps": [
                    {
                        "name": "groups",
                        "cwd": str(self.root),
                        "argv": [sys.executable, "-B", str(self.root / "main.py"), "gate", "run",
                                 "--worktree", str(worktree), "--out", str(evidence), "--jobs", "4"],
                        "timeout_s": 36000,
                        "stop_on_fail": True,
                    },
                    {
                        "name": "plugin",
                        "cwd": str(project),
                        "env": {"AUTO_PM_SIEMENS_LSP": str(plugin), "AUTO_PM_REQUIRE_SIEMENS_LSP": "1"},
                        "argv": [sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                 "-o", "addopts=", "--basetemp", str(folder / "plugin-tests"),
                                 "tests/e2e/test_pmf_template_plc.py", "-k", "plugin"],
                    },
                ],
            }
            (folder / "task.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
        except (OSError, ValueError, GateRunError, subprocess.TimeoutExpired) as error:
            return Observation("unavailable", detail=f"本机预检失败，尚未派发：{error}")
        try:
            result = self._runner(attempt, "launch", "--wait", "8")
        except (OSError, subprocess.TimeoutExpired):
            return Observation("unknown", attempt.id, "计划任务派发结果未知")
        if result.returncode == 4:  # long_gate refuses on memory/lease preflight before registering a task
            return Observation("unavailable", detail=result.stdout.strip())
        return Observation("running" if result.returncode == 0 else "unknown", attempt.id, result.stdout.strip())

    def inspect(self, attempt: GateAttempt, candidate: GateCandidate) -> Observation:
        folder = self._folder(attempt)
        if not (folder / "task.json").is_file():
            return Observation(attempt.state, detail="尚无本机执行记录")
        try:
            result = self._runner(attempt, "status")
            if result.returncode:
                raise GateRunError("计划任务状态不可读")
            status = json.loads(result.stdout)
            if status.get("runner_alive"):
                return Observation("running", attempt.id, str(status.get("current_step") or "正在收尾"))
            if status.get("result") == "STOPPED":
                return Observation("stopped", attempt.id, str(status.get("reason") or "已停止"))
            if status.get("result") == "DONE":
                if len(status.get("done", [])) != 2 or status.get("todo") or status.get("failed_steps"):
                    return Observation("failed", attempt.id, "有检查缺失或未通过")
                return self._receipt(attempt, candidate, folder)
            if status.get("result") in {"FAILED", "HARD_STOP_LEASE", "LEASE_FAILED_AT_START", "ROUND_TIMEOUT"}:
                return Observation("failed", attempt.id, str(status.get("reason") or "执行失败"))
            if (
                status.get("scheduler_state") in {"Ready", "Disabled"}
                and status.get("scheduler_exit") not in (None, 0x41303, 0x41301, 0x41305)
                and (status.get("scheduler_started") or status.get("scheduler_exit") != 0)
            ):
                return Observation("failed", attempt.id, f"计划任务退出码 {status['scheduler_exit']}，未生成判卷凭证")
            return Observation("unknown", attempt.id, "计划任务未返回结束凭证")
        except (GateRunError, OSError, subprocess.TimeoutExpired, ValueError) as error:
            return Observation(attempt.state, detail=str(error))

    @staticmethod
    def _receipt(attempt: GateAttempt, candidate: GateCandidate, folder: Path) -> Observation:
        evidence = folder / "evidence"
        summary = GateRunService().judge_dir(evidence)
        plugin_log = folder / "runner/plugin.txt"
        counts = pytest_counts(plugin_log) or {}
        plugin_exit = folder / "runner/plugin.exit"
        artifacts = {
            "sha256": sha256_file(evidence / SUMMARY_FILE),
            "plugin_log_sha256": sha256_file(plugin_log),
            "plugin_exit_sha256": sha256_file(plugin_exit),
            "config_sha256": sha256_file(folder / "task.json"),
        }
        if (
            summary.verdict == "PASS" and summary.commit == candidate.commit
            and summary.manifest_sha256 == candidate.manifest and all(artifacts.values())
            and plugin_exit.read_text(encoding="utf-8").strip() == "0"
            and counts.get("passed", 0) > 0 and not counts.get("skipped", 0)
        ):
            return Observation("passed", attempt.id, json.dumps({**artifacts, "folder": str(folder)}))
        return Observation("failed", attempt.id, "本机判卷、Siemens LSP 插件结果或候选指纹不匹配")

    def stop(self, attempt: GateAttempt) -> None:
        if self._runner(attempt, "stop").returncode:
            raise GateRunError("计划任务未确认停止请求")


def open_gate_task_service(
    root: Path, worktree: Path | None = None, plugin: Path | None = None,
) -> GateTaskService:
    """Compose the ledger and executors at the application boundary."""
    return GateTaskService(
        GateTaskStore(root), GitHubGateExecutor(root), LocalGateExecutor(root, worktree, plugin)
    )


def task_record(attempt: GateAttempt) -> dict[str, Any]:
    record = asdict(attempt)
    record["candidate"] = json.loads(record.pop("key"))
    return record
