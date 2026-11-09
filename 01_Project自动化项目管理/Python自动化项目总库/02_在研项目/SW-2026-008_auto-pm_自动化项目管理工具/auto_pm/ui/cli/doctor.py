"""Doctor 环境与依赖自检 CLI 命令 (CHG-SCPT-2026-155 纯净度防守升级)"""

from __future__ import annotations

import importlib.util
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from auto_pm.application.core.agent_worktree_service import (
    MAX_STATIONS,
    RELEASE_FREE_PLACES,
    AgentWorktreeError,
    AgentWorktreeService,
)
from auto_pm.application.core.governance_service import GovernanceService
from auto_pm.application.core.release_consistency import check_release_consistency
from auto_pm.ui.cli.caller_path import CallerPath

console = Console()


def resolve_workspace(workspace_root: str | None = None) -> str:
    if workspace_root:
        return os.path.abspath(workspace_root)
    from auto_pm.app_context import AppContext
    return AppContext().workspace_root


EXTERNAL_RUNTIME_MARKERS = (".cache/codex-runtimes", "/codex-runtimes/")


def _same_version(recorded: str, running: str) -> bool:
    """Compare version numbers part by part (3.12.1 is not 3.12.14); a short record such as 3.12 matches any 3.12.x."""

    wanted = recorded.split(".")[:3]
    return running.split(".")[: len(wanted)] == wanted


def check_venv_base(
    prefix: str | None = None,
    base_prefix: str | None = None,
    running_version: str | None = None,
) -> dict[str, Any]:
    """The virtual environment's base interpreter: is it still there, is it ours, is it the version recorded (TD pool 31).

    A ``.venv`` keeps working only while the Python it was made from stays put.  When that Python lives in another tool's
    cache (an AI tool's runtime folder) an update or a clean-up of that tool breaks the cockpit and the gates together,
    so the check says so while everything still works.  Read-only; ``status`` is ok / warn / info.
    """

    prefix = sys.prefix if prefix is None else prefix
    base_prefix = sys.base_prefix if base_prefix is None else base_prefix
    running = platform.python_version() if running_version is None else running_version
    if os.path.normcase(os.path.abspath(prefix)) == os.path.normcase(os.path.abspath(base_prefix)):
        return {"status": "info", "reasons": ["没有在虚拟环境里运行"], "home": ""}
    reasons: list[str] = []
    home = ""
    recorded = ""
    cfg = Path(prefix) / "pyvenv.cfg"
    try:
        for line in cfg.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            key, value = key.strip().lower(), value.strip()
            if key == "home":
                home = value
            elif key in ("version", "version_info"):
                recorded = value
    except OSError:
        reasons.append(f"读不到 {cfg}，无法核对底层 Python")
    except UnicodeDecodeError:
        reasons.append(f"{cfg} 不是合法 UTF-8，无法核对底层 Python")
    if home:
        if not Path(home).is_dir():
            reasons.append(f"底层 Python 目录已不存在：{home}；.venv 马上就不能用了，需要重建")
        normalized = home.replace("\\", "/").lower()
        if any(marker in normalized for marker in EXTERNAL_RUNTIME_MARKERS):
            reasons.append(
                f"底层 Python 在 Codex 的运行时缓存目录里（目前只认这一种工具缓存）：{home}；那个工具更新或清理后驾驶舱和门禁会一起坏，建议用固定安装的 Python 重建 .venv"
            )
    if recorded and not _same_version(recorded, running):
        reasons.append(
            f".venv 记录的版本是 {recorded}，现在实际是 {running}：底层 Python 被换过，建议重建 .venv"
        )
    return {"status": "warn" if reasons else "ok", "reasons": reasons, "home": home}


POINTER_DIR = "00_Infrastructure/auto_pm"
POINTER_FILES = ("active_release.json", "previous_release.json", "deployment_manifest.json")


def _git_show(root: str, ref: str, relative: str) -> str | None:
    """File content at a Git ref, or None when the ref or the file is not there.  Strict UTF-8: a bad byte is a failure, not a guess."""

    try:
        result = subprocess.run(
            ["git", "-C", root, "show", f"{ref}:{relative}"],
            capture_output=True,
            timeout=30,
            check=False,
        )
        return result.stdout.decode("utf-8") if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError, UnicodeDecodeError):
        return None


def _pointers_changed_by_head(root: str, base_ref: str) -> bool:
    """Does the checked-out commit change a pointer file relative to where it branched off ``base_ref``?

    Three dots, so only what THIS branch did counts: a branch that is merely behind a main that moved the pointers on has not
    changed them.  Any Git failure (no common ancestor, a shallow clone) answers False, which leaves the strict comparison
    against ``base_ref`` in force -- the check never gets laxer because Git could not answer.
    """

    paths = [f"{POINTER_DIR}/{name}" for name in POINTER_FILES]
    try:
        result = subprocess.run(
            ["git", "-C", root, "diff", "--name-only", f"{base_ref}...HEAD", "--", *paths],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def _pull_request_ci_base(root: str, ref: str) -> str:
    """In a GitHub ``pull_request`` run, the commit the merge ref was built on; otherwise (or on any Git failure) ``ref``.

    CI checks out ``refs/pull/N/merge``: the PR head merged into the main tip *at the time the merge ref was built*.  A PR
    deploys nothing, so asking "does the machine match the newest main?" turns every pointer check-in on main red for all
    PRs that were opened before it.  The merge base is the main the PR was built on; a later main changes nothing.  Outside
    that CI event (a control root on a laptop) the comparison stays exactly against ``ref``.
    """

    if os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("GITHUB_EVENT_NAME") != "pull_request":
        return ref
    try:
        result = subprocess.run(
            ["git", "-C", root, "merge-base", ref, "HEAD"],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ref
    base = result.stdout.decode("utf-8", errors="replace").strip() if result.returncode == 0 else ""  # lenient-decode: a Git object id is ASCII
    return base or ref


def _json_object(text: str | None) -> dict[str, Any] | None:
    if text is None:
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def check_release_pointers(root: str, ref: str | None = None) -> dict[str, Any]:
    """Do the three release pointer files on main match the release deployed on this machine (TD-244)?

    After a release switch the pointers change on this machine, and nothing carries them into Git until someone commits
    them.  Fresh clones then read an old release.  Read-only.  ``status`` is ok / fail / info; a release id that contains
    ``.test.`` is a test build and never counts as the deployed release.

    When the checked-out branch itself changes a pointer file (the release PR), the comparison is against that branch's own
    commit (``ref`` is ``HEAD``, ``pr_head`` is True) instead of ``origin/main``; with no pointer change in the branch the
    comparison is against ``origin/main`` exactly as before.  An explicit ``ref`` is always honoured.
    """

    base = Path(root) / POINTER_DIR
    if not (base / "active_release.json").exists():
        return {"status": "info", "reasons": ["本机没有 active_release.json（不是控制根或还没部署）"], "ref": ""}
    local = {name: _json_object(_read_local(base / name)) for name in POINTER_FILES}
    unreadable = [name for name in POINTER_FILES if local[name] is None and (base / name).exists()]
    active = local["active_release.json"]
    if unreadable or active is None:
        return {
            "status": "fail",
            "reasons": [f"本机 {name} 读不出来（不是有效的 JSON 或含坏字节），不能判断部署的是哪个版本" for name in unreadable]
            or ["本机 active_release.json 读不出来"],
            "ref": "",
        }
    pr_head = False
    base_ref = ""
    if ref is None:
        ref = "origin/main" if _git_show(root, "origin/main", f"{POINTER_DIR}/active_release.json") is not None else "HEAD"
        if ref != "HEAD":
            ref = _pull_request_ci_base(root, ref)
        if ref != "HEAD" and _pointers_changed_by_head(root, ref):
            # A branch that itself moves the pointers (the release PR) can never equal main before it merges, so comparing it
            # with main would be red by construction.  Compare with the branch's own commit instead: the machine must still match
            # what is committed, and the committed manifest must still list the deployed release.
            base_ref, ref, pr_head = ref, "HEAD", True
    reasons: list[str] = []
    deployed = active.get("release_id")
    if not isinstance(deployed, str) or not deployed:
        return {"status": "fail", "reasons": ["本机 active_release.json 缺少 release_id"], "ref": ref}
    if ".test." in deployed:
        reasons.append(f"本机已部署的版本 {deployed} 是测试构建（版本号含 .test.），不能当作已部署版本")
    committed = {name: _json_object(_git_show(root, ref, f"{POINTER_DIR}/{name}")) for name in POINTER_FILES}
    for name in ("active_release.json", "previous_release.json"):
        mine, theirs = local[name], committed[name]
        if mine is None:
            continue
        if theirs is None:
            reasons.append(f"{ref} 上读不到 {name}")
        elif theirs.get("release_id") != mine.get("release_id"):
            reasons.append(f"{name}：{ref} 上是 {theirs.get('release_id')}，本机是 {mine.get('release_id')}；发版后的指针还没入库")
    if pr_head:
        # Self-consistency is not exemption: a release PR must also say which release it replaced.  If it switches the active
        # pointer, previous_release.json has to name the release main had as active.
        before = _json_object(_git_show(root, base_ref, f"{POINTER_DIR}/active_release.json"))
        now_active, now_previous = committed["active_release.json"], committed["previous_release.json"]
        if before is not None and now_active is not None and now_active.get("release_id") != before.get("release_id"):
            replaced = before.get("release_id")
            recorded = now_previous.get("release_id") if now_previous is not None else None
            if recorded != replaced:
                reasons.append(
                    f"previous_release.json：本分支把 active_release.json 从 {replaced} 换成 {now_active.get('release_id')}，"
                    f"previous 应指向被替换的上一版 {replaced}，现在是 {recorded}"
                )
    manifest = committed["deployment_manifest.json"]
    if manifest is None:
        reasons.append(f"{ref} 上读不到 deployment_manifest.json")
    else:
        releases = manifest.get("releases")
        if not isinstance(releases, dict) or deployed not in releases:
            reasons.append(f"deployment_manifest.json：{ref} 上没有本机已部署的版本 {deployed}")
    return {"status": "fail" if reasons else "ok", "reasons": reasons, "ref": ref, "pr_head": pr_head}


def check_change_status_history(root: str) -> dict[str, Any]:
    """Is every change-order status edit in the working tree backed by the approval history?  Read-only.

    ``status`` is ok / fail / info (info: Git could not answer, so nothing was checked).  The same rule the commit hook applies
    to a staged edit, applied before the commit: a hand-written approved state shows up here at once.
    """

    from auto_pm.application.core.change_status_check import pending_change_status_problems

    problems = pending_change_status_problems(root)
    if problems is None:
        return {"status": "info", "reasons": ["Git 读不出改动（不是仓库或还没有提交），没有核对变更单状态"]}
    return {"status": "fail" if problems else "ok", "reasons": problems}


def check_worktree_floor(root: str, *, pre_release: bool = False) -> dict[str, Any]:
    """Before a release: at most ``MAX_STATIONS - RELEASE_FREE_PLACES`` directories under ``.auto-pm/worktrees``.

    The count is ``AgentWorktreeService.count()`` -- the number ``worktree open`` refuses on -- so the two can never
    disagree.  Read-only.  ``status``: ok; warn (too many, but this is the everyday check); fail (too many and
    ``pre_release``, i.e. ``doctor --pre-release``); info (not a control root or Git cannot be asked, nothing to judge).
    A day-to-day ``doctor`` and the settings page must not turn red for this, only the release pre-check may.
    """

    limit = MAX_STATIONS - RELEASE_FREE_PLACES
    try:
        count = AgentWorktreeService(root, measure_size=False).count()
    except (AgentWorktreeError, OSError) as error:
        return {"status": "info", "count": 0, "limit": limit, "reasons": [f"不是控制根或读不了工位目录：{error}"]}
    if count <= limit:
        return {"status": "ok", "count": count, "limit": limit, "reasons": []}
    return {
        "status": "fail" if pre_release else "warn",
        "count": count,
        "limit": limit,
        "reasons": [
            f".auto-pm/worktrees 下有 {count} 个目录，发版前最多 {limit} 个"
            f"（上限 {MAX_STATIONS}，发版自己要占 {RELEASE_FREE_PLACES} 个）；先 `worktree list --deep` 看哪些做完了，"
            "再 `worktree close` / `worktree sweep`"
        ],
    }


def _read_local(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def run_doctor_check(workspace_root: str | None = None, *, pre_release: bool = False) -> dict[str, Any]:
    """执行综合环境健康诊断

    Args:
        pre_release: 发版前置检查（``doctor --pre-release``）；只有它才把“工位目录太多”判为失败，日常体检只提示。

    Returns:
        包含诊断结果的字典
    """
    root = resolve_workspace(workspace_root)

    # 1. Python 版本检查
    py_ver = sys.version.split()[0]
    py_ok = sys.version_info >= (3, 11)

    # 2. 核心依赖检查
    dependencies = ["rich", "click", "pydantic", "PySide6", "copier", "yaml", "ruff", "pytest", "mypy"]
    dep_results: dict[str, bool] = {}
    for dep in dependencies:
        spec = importlib.util.find_spec(dep)
        dep_results[dep] = spec is not None

    # 3. pyproject.toml 版本
    pyproject_path = Path(root) / "pyproject.toml"
    version_str = "1.1.0"
    if pyproject_path.exists():
        try:
            import tomli as tomllib
        except ImportError:
            import tomllib
        try:
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
                version_str = data.get("project", {}).get("version", "1.1.0")
        except Exception:
            pass

    # 4. Git 工作区检查
    git_dir = Path(root) / ".git"
    git_ok = git_dir.exists()

    # 5. 工作空间纯净度守卫
    gov_service = GovernanceService(workspace_root=root)
    sanitation_report = gov_service.inspect_sanitation()

    # 6. GitHub 命令行（`main.py pr open` 要用；只提示，不计入 all_passed）
    from auto_pm.application.core.pr_open_service import gh_status

    gh_installed, gh_logged_in = gh_status()

    venv_base = check_venv_base()
    release_pointers = check_release_pointers(root)
    release_consistency = check_release_consistency(root)
    change_status = check_change_status_history(root)
    worktree_floor = check_worktree_floor(root, pre_release=pre_release)

    all_passed = (
        py_ok
        and git_ok
        and sanitation_report.is_pure
        and all(dep_results.values())
        and release_pointers["status"] != "fail"
        and release_consistency["status"] != "fail"
        and change_status["status"] != "fail"
        and worktree_floor["status"] != "fail"
    )

    return {
        "workspace_root": str(root),
        "python_version": py_ver,
        "python_ok": py_ok,
        "dependencies": dep_results,
        "project_version": version_str,
        "git_found": git_ok,
        "sanitation_pure": sanitation_report.is_pure,
        "sanitation_issues": sanitation_report.total_issues,
        "gh_installed": gh_installed,
        "gh_logged_in": gh_logged_in,
        "venv_base": venv_base,
        "release_pointers": release_pointers,
        "release_consistency": release_consistency,
        "change_status": change_status,
        "worktree_floor": worktree_floor,
        "all_passed": all_passed,
    }


@click.command("doctor")
@click.option("-w", "--workspace", type=CallerPath(exists=True), help="工作空间根目录")
@click.option("--pre-release", "pre_release", is_flag=True, help="发版前置检查：工位目录超过 7 个判为失败（默认只提示）")
def doctor_command(workspace: str | None, pre_release: bool) -> None:
    """执行 auto-pm 环境与依赖健康诊断"""
    console.print(Panel.fit("[bold blue]auto-pm 环境与依赖健康诊断[/bold blue]", border_style="blue"))

    res = run_doctor_check(workspace, pre_release=pre_release)

    table = Table(title="诊断明细", show_header=True, header_style="bold magenta")
    table.add_column("检查项", style="cyan")
    table.add_column("状态", style="bold")
    table.add_column("说明", style="dim")

    # Python
    py_status = "[green]✅ PASS[/green]" if res["python_ok"] else "[red]❌ FAIL[/red]"
    table.add_row("Python 版本", py_status, f"{res['python_version']} (要求 >= 3.11)")

    # 版本
    table.add_row("源码版本号", "[blue]ℹ INFO[/blue]", f"pyproject.toml version: {res['project_version']}")

    # 依赖项
    for dep, ok in res["dependencies"].items():
        dep_status = "[green]✅ 已安装[/green]" if ok else "[yellow]⚠️ 未找到[/yellow]"
        table.add_row(f"依赖: {dep}", dep_status, "可用" if ok else "开发环境建议安装")

    # 工作空间
    table.add_row("工作空间根目录", "[blue]ℹ INFO[/blue]", res["workspace_root"])
    git_status = "[green]✅ PASS[/green]" if res["git_found"] else "[yellow]⚠️ 未找到[/yellow]"
    table.add_row("Git 仓库", git_status, "已检测到 .git" if res["git_found"] else "未检测到 .git")

    # 根目录纯净度守卫
    sani_status = "[green]✅ 根目录纯净[/green]" if res["sanitation_pure"] else f"[bold yellow]⚠️ 存在 {res['sanitation_issues']} 个游离文件[/bold yellow]"
    sani_msg = "符合根目录白名单规范" if res["sanitation_pure"] else "建议运行 'auto-pm clean' 进行自动清扫"
    table.add_row("工作空间纯净度守卫", sani_status, sani_msg)

    if not res["gh_installed"]:
        gh_row = ("[yellow]⚠️ 未安装[/yellow]", "`main.py pr open` 要用 gh；没装就把分支交给用户在网页上开 PR")
    elif not res["gh_logged_in"]:
        gh_row = ("[yellow]⚠️ 未登录[/yellow]", "运行 `gh auth login`")
    else:
        gh_row = ("[green]✅ 已登录[/green]", "可用 `main.py pr open`")
    table.add_row("GitHub 命令行 gh", *gh_row)

    venv = res["venv_base"]
    if venv["status"] == "warn":
        table.add_row("虚拟环境底层 Python", "[yellow]⚠️ 注意[/yellow]", "；".join(venv["reasons"]))
    elif venv["status"] == "ok":
        table.add_row("虚拟环境底层 Python", "[green]✅ PASS[/green]", venv["home"])

    pointers = res["release_pointers"]
    if pointers["status"] == "fail":
        table.add_row("发布指针与本机部署", "[bold red]❌ FAIL[/bold red]", "；".join(pointers["reasons"]))
    elif pointers["status"] == "ok":
        table.add_row("发布指针与本机部署", "[green]✅ PASS[/green]", f"{pointers['ref']} 上的三个指针与本机一致" + ("（本分支改了发布指针，按分支头比）" if pointers.get("pr_head") else ""))

    consistency = res["release_consistency"]
    if consistency["status"] == "fail":
        table.add_row("发布记录互相核对", "[bold red]❌ FAIL[/bold red]", "；".join(consistency["failures"]))
    elif consistency["status"] == "warn":
        table.add_row("发布记录互相核对", "[yellow]⚠️ 注意[/yellow]", "；".join(consistency["warnings"]))
    elif consistency["status"] == "ok":
        table.add_row("发布记录互相核对", "[green]✅ PASS[/green]", "manifest、载荷目录、release_meta、标注记录、Git 提交互相一致")

    chg_status = res["change_status"]
    if chg_status["status"] == "fail":
        table.add_row("变更单状态与流转记录", "[bold red]❌ FAIL[/bold red]", "；".join(chg_status["reasons"]))
    elif chg_status["status"] == "ok":
        table.add_row("变更单状态与流转记录", "[green]✅ PASS[/green]", "工作区里新改的变更单批准态都有对应的流转记录")
    else:
        table.add_row("变更单状态与流转记录", "[yellow]⚠️ 未核对[/yellow]", "；".join(chg_status["reasons"]))
    floor = res["worktree_floor"]
    if floor["status"] == "fail":
        table.add_row("工位目录数（发版前置）", "[bold red]❌ FAIL[/bold red]", "；".join(floor["reasons"]))
    elif floor["status"] == "warn":
        table.add_row("工位目录数（发版前置）", "[yellow]⚠️ 注意[/yellow]", "；".join(floor["reasons"]) + "（发版前用 --pre-release 复查）")
    elif floor["status"] == "ok":
        table.add_row("工位目录数（发版前置）", "[green]✅ PASS[/green]", f"{floor['count']} 个，发版前最多 {floor['limit']} 个")

    console.print(table)

    if chg_status["status"] == "fail":
        console.print("\n[bold red]变更单状态被手改过，没有流转记录作依据：把状态改回去，再用 `main.py change transition` 走流转。[/bold red]\n")
        raise SystemExit(1)

    if pointers["status"] == "fail":
        console.print("\n[bold red]发布指针落后于本机部署：把三个指针文件走变更单提交进 main，再重跑 doctor。[/bold red]\n")
        raise SystemExit(1)

    if consistency["status"] == "fail":
        console.print("\n[bold red]发布记录自相矛盾：不要靠改 manifest 或载荷字节消除，走变更单在 release_annotations.json 里更正。[/bold red]\n")
        raise SystemExit(1)

    if floor["status"] == "fail":
        console.print("\n[bold red]工位目录太多，先回收再发版（删除只认用户亲口说“收”）。[/bold red]\n")
        raise SystemExit(1)

    if res["all_passed"]:
        console.print("\n[bold green]🎉 恭喜！当前环境一切正常，可顺畅运行与开发 auto-pm！[/bold green]\n")
    else:
        console.print("\n[bold yellow]⚠️ 注意：存在非标准或缺失依赖，请参考表项修复建议。[/bold yellow]\n")
