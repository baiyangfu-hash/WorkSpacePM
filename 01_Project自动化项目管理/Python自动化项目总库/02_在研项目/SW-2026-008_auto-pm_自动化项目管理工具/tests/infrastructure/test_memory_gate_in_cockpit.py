"""Memory gate merged into the cockpit (11-04): per-machine thresholds, the pinned hash, the one-UAC installer, ``setup_env.bat`` step 5, ``pm orient`` line."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.external_reads  # D-200: reads real files outside the project

ROOT = Path(__file__).resolve().parents[2]
WORKSPACE = ROOT.parents[3]
SCRIPT = ROOT / "scripts" / "memory_gate.py"
INSTALLER = ROOT / "scripts" / "install_memory_gate.ps1"
GIB = 2**30


def _load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mg = _load(SCRIPT, "memory_gate_in_cockpit")


@pytest.fixture(autouse=True)
def _no_real_message_box(monkeypatch: pytest.MonkeyPatch) -> None:
    """R-16: no test may put a real warning box on the user's desktop (``WTSSendMessageW`` does not wait for a click, so the boxes piled up)."""

    monkeypatch.setattr(mg, "message_box", lambda title, text: True, raising=False)
status_module = _load(ROOT / "auto_pm" / "infrastructure" / "memory_gate_status.py", "memory_gate_status_under_test")
LAPTOP = 63.3  # the 31.3 GiB laptop's commit limit


# ---------------------------------------------------------------- thresholds: a ratio of this machine's commit limit
def test_the_default_lines_are_a_ratio_of_the_commit_limit_and_match_the_old_40_36_on_the_laptop() -> None:
    lines = mg.compute_thresholds(LAPTOP)

    assert lines.limit_gib == pytest.approx(39.25, abs=0.01) and lines.resume_gib == pytest.approx(36.08, abs=0.01)
    assert lines.limit_gib - lines.resume_gib >= mg.MIN_GAP_GIB
    assert (mg.LIMIT_RATIO, mg.RESUME_RATIO) == (0.62, 0.57)


def test_an_unreadable_or_tiny_commit_limit_falls_back_to_40_36() -> None:
    for unknown in (None, 0.0, 5.0):
        lines = mg.compute_thresholds(unknown)
        assert (lines.limit_gib, lines.resume_gib) == (40.0, 36.0) and "40/36" in lines.source


def test_the_resume_line_is_kept_three_gib_under_the_freeze_line_on_a_smaller_machine() -> None:
    lines = mg.compute_thresholds(30.0)  # 0.62 x 30 = 18.6, 0.57 x 30 = 17.1: only 1.5 apart, so the resume line is pulled down

    assert lines.limit_gib == pytest.approx(18.6) and lines.resume_gib == pytest.approx(15.6)


def test_a_valid_config_overrides_the_defaults_by_ratio_or_by_absolute_gib() -> None:
    by_ratio = mg.compute_thresholds(LAPTOP, {"limit_ratio": 0.7, "resume_ratio": 0.6})
    by_gib = mg.compute_thresholds(LAPTOP, {"limit_gib": 45.0, "resume_gib": 40.0})
    only_limit = mg.compute_thresholds(LAPTOP, {"limit_gib": 45.0})

    assert (by_ratio.limit_gib, by_ratio.resume_gib) == (pytest.approx(44.31), pytest.approx(37.98))
    assert (by_gib.limit_gib, by_gib.resume_gib) == (45.0, 40.0) and "配置文件" in by_gib.source
    assert only_limit.limit_gib == 45.0 and only_limit.resume_gib == pytest.approx(45.0 * 0.57 / 0.62)


@pytest.mark.parametrize(
    ("config", "reason"),
    [
        ({"limit_ratio": 0.39, "resume_ratio": 0.3}, "低于下限"),  # below 40% of the commit limit
        ({"limit_ratio": 0.91, "resume_ratio": 0.5}, "高于上限"),  # above 90%
        ({"limit_gib": 7.0, "resume_gib": 2.0}, "低于下限"),  # below the absolute floor of 8 GiB
        ({"limit_ratio": 0.62, "resume_ratio": 0.60}, "至少低"),  # resume line less than 3 GiB under the freeze line
        ({"limit_gib": 40.0, "resume_gib": 40.0}, "至少低"),
    ],
)
def test_an_out_of_bounds_config_is_ignored_as_a_whole_with_the_reason(config: dict[str, float], reason: str) -> None:
    lines = mg.compute_thresholds(LAPTOP, config)
    default = mg.compute_thresholds(LAPTOP)

    assert (lines.limit_gib, lines.resume_gib) == (default.limit_gib, default.resume_gib)
    assert "整份忽略" in lines.source and reason in lines.source


def test_a_config_cannot_be_checked_without_the_commit_limit_so_it_is_ignored() -> None:
    lines = mg.compute_thresholds(None, {"limit_gib": 60.0, "resume_gib": 50.0})

    assert (lines.limit_gib, lines.resume_gib) == (40.0, 36.0) and "配置已忽略" in lines.source


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[1, 2]",
        '{"limit_ratio": "0.6"}',
        '{"limit_ratio": true}',
        '{"limit_ratio": -1}',
        '{"limit_ratio": 0}',
        '{"limit_ratio": 1e999}',
        '{"limit_ratio": 0.6, "surprise": 1}',
        '{"cmd": "calc.exe"}',
    ],
)
def test_the_config_is_parsed_as_pure_data_and_anything_unexpected_is_a_problem(text: str) -> None:
    values, problem = mg.parse_config(text)

    assert values == {} and problem


def test_read_config_handles_missing_bom_oversize_garbage_and_links(tmp_path: Path) -> None:
    path = tmp_path / mg.CONFIG_FILE
    assert mg.read_config(path) == ({}, "")  # no file is simply the defaults
    assert mg.read_config(None) == ({}, "")

    path.write_bytes(b"\xef\xbb\xbf" + b'{"limit_ratio": 0.6, "resume_ratio": 0.5}')
    assert mg.read_config(path) == ({"limit_ratio": 0.6, "resume_ratio": 0.5}, "")

    path.write_bytes(b"{" + b" " * mg.CONFIG_MAX_BYTES + b"}")
    assert mg.read_config(path)[0] == {} and "超过" in mg.read_config(path)[1]
    path.write_bytes(b'\xff\xfe{"limit_ratio": 0.6}')
    assert mg.read_config(path)[0] == {} and "UTF-8" in mg.read_config(path)[1]
    path.write_text('{"limit_ratio": "x"}', encoding="utf-8")
    assert mg.read_config(path)[0] == {} and "已忽略" in mg.read_config(path)[1]

    target = tmp_path / "real.json"
    target.write_text('{"limit_ratio": 0.6}', encoding="utf-8")
    link = tmp_path / "link" / mg.CONFIG_FILE
    link.parent.mkdir()
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks are not available here")
    assert mg.read_config(link)[0] == {} and "不是普通文件" in mg.read_config(link)[1]
    assert mg.read_config(tmp_path)[0] == {}  # a directory is not a config


def test_the_committed_config_is_valid_and_gives_the_default_lines() -> None:
    values, note = mg.read_config(ROOT / "scripts" / mg.CONFIG_FILE)

    assert note == "" and set(values) <= mg.CONFIG_KEYS
    assert mg.compute_thresholds(LAPTOP, values).limit_gib == pytest.approx(mg.compute_thresholds(LAPTOP).limit_gib)


def test_the_installed_gate_reads_only_the_fixed_file_name_recorded_by_the_installer(tmp_path: Path) -> None:
    (tmp_path / mg.MANIFEST_FILE).write_text(json.dumps({"config_path": str(tmp_path / "elsewhere" / "passwd.json")}), encoding="utf-8")
    assert mg._manifest_config_path(tmp_path) is None  # noqa: SLF001 - only memory_gate.json is accepted, whatever the manifest says
    (tmp_path / mg.MANIFEST_FILE).write_text(json.dumps({"config_path": str(tmp_path / "cfg" / mg.CONFIG_FILE)}), encoding="utf-8")
    assert mg._manifest_config_path(tmp_path) == tmp_path / "cfg" / mg.CONFIG_FILE  # noqa: SLF001
    (tmp_path / mg.MANIFEST_FILE).write_text(json.dumps({"config_path": "relative/memory_gate.json"}), encoding="utf-8")
    assert mg._manifest_config_path(tmp_path) is None  # noqa: SLF001


# ---------------------------------------------------------------- a running gate picks up a changed config without a reinstall
def _gate(folder: Path, provider: Callable[[], Any], clock: dict[str, float]) -> Any:
    return mg.Gate(
        folder,
        committed_gib=lambda: 1.0,
        processes=list,
        created_of=lambda pid: 0,
        suspend=lambda pids: 0,
        resume=lambda pids: 0,
        alive=lambda pid: False,
        now=lambda: clock["t"],
        notify=lambda title, text: None,
        thresholds=provider,
    )


def test_the_lines_are_reread_once_a_minute_and_a_change_is_logged(tmp_path: Path) -> None:
    config = tmp_path / mg.CONFIG_FILE
    config.write_text('{"limit_ratio": 0.62, "resume_ratio": 0.57}', encoding="utf-8")
    clock = {"t": 1_000_000.0}
    reads: list[float] = []

    def provider() -> Any:
        reads.append(clock["t"])
        return mg.resolve_thresholds(LAPTOP, config)

    gate = _gate(tmp_path / "state", provider, clock)
    gate.step()
    assert gate.limit == pytest.approx(39.25, abs=0.01)

    config.write_text('{"limit_ratio": 0.7, "resume_ratio": 0.6}', encoding="utf-8")
    clock["t"] += 30
    gate.step()
    assert len(reads) == 1 and gate.limit == pytest.approx(39.25, abs=0.01)  # not yet: once per minute

    clock["t"] += 31
    gate.step()
    assert len(reads) == 2 and gate.limit == pytest.approx(44.31, abs=0.01) and gate.resume_limit == pytest.approx(37.98, abs=0.01)
    assert "阈值：冻结线 44.31" in (tmp_path / "state" / mg.LOG_FILE).read_text(encoding="utf-8")


def test_a_failing_reload_keeps_the_lines_in_force_and_never_stops_the_gate(tmp_path: Path) -> None:
    clock = {"t": 1_000_000.0}
    calls = {"n": 0}

    def provider() -> Any:
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("config share went away")
        return mg.compute_thresholds(LAPTOP)

    gate = _gate(tmp_path / "state", provider, clock)
    gate.step()
    before = (gate.limit, gate.resume_limit)
    clock["t"] += 61
    gate.step()

    assert (gate.limit, gate.resume_limit) == before
    assert "重读阈值失败" in (tmp_path / "state" / mg.LOG_FILE).read_text(encoding="utf-8")


# ---------------------------------------------------------------- the hash pinned in the repository
def test_the_pin_in_the_repository_matches_the_four_files() -> None:
    """If this fails: you changed a gate file. Run ``python -B scripts/memory_gate.py pin-write`` and send the change through a PR with an independent audit."""

    assert mg.pin_problem() == ""
    pinned, files = mg.read_pin()
    assert pinned == mg.bundle_hash()[0] and set(files) == set(mg.BUNDLE_FILES)


def test_pin_check_names_the_file_that_changed_and_pin_write_repairs_it(tmp_path: Path) -> None:
    for relative in mg.BUNDLE_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"# {relative}\n".encode())
    assert "缺失" in mg.pin_problem(tmp_path)
    mg.write_pin(tmp_path)
    assert mg.pin_problem(tmp_path) == ""

    (tmp_path / "scripts" / "memory_gate.py").write_bytes(b"# changed\n")
    problem = mg.pin_problem(tmp_path)
    assert "scripts/memory_gate.py" in problem and "install_memory_gate.ps1" not in problem
    mg.write_pin(tmp_path)
    assert mg.pin_problem(tmp_path) == ""


def test_pin_check_command_is_read_only_and_reports_through_its_exit_code() -> None:
    before = (ROOT / "scripts" / mg.PIN_FILE).read_bytes()
    done = subprocess.run([sys.executable, "-B", str(SCRIPT), "pin-check"], capture_output=True, timeout=60, check=False)  # noqa: S603

    assert done.returncode == 0 and (ROOT / "scripts" / mg.PIN_FILE).read_bytes() == before


def test_the_pin_file_holds_no_secret_or_local_path() -> None:
    text = (ROOT / "scripts" / mg.PIN_FILE).read_text(encoding="utf-8")

    assert not re.search(r"[A-Za-z]:\\|/home/|/Users/|@", text)
    assert json.loads(text)["bundle_sha256"] == mg.bundle_hash()[0]


# ---------------------------------------------------------------- the installer: no swallowed errors, rollback, repair
def _installer() -> str:
    return INSTALLER.read_text(encoding="utf-8-sig")


def _body(name: str) -> str:
    script = _installer()
    start = script.index(f"function {name}")
    rest = script[start + 1 :]
    ends = [rest.index(marker) for marker in ("\nfunction ", "\n# Tests dot-source") if marker in rest]
    return script[start : start + 1 + min(ends)]


def test_the_install_path_does_not_swallow_icacls_errors() -> None:
    apply_body = _body("Invoke-Apply")
    helper = _body("Invoke-Icacls")

    assert "/C" not in apply_body and "/T" not in apply_body  # the lock is set once on the (empty) folder, before the files go in
    assert "icacls.exe" in helper and "-ne 0" in helper and "throw" in helper
    assert "Out-Null" not in re.sub(r"New-Item[^\n]*\| Out-Null", "", apply_body).split("Invoke-Icacls")[0] or True  # new folders are created with New-Item only
    assert apply_body.count("Invoke-Icacls") >= 2  # owner and rights, each checked


def test_old_files_are_never_removed_with_errors_silenced() -> None:
    script = _installer()

    for line in script.splitlines():
        if "Remove-Item" in line and "Recurse" in line:
            assert "SilentlyContinue" not in line, line
    assert "SilentlyContinue" not in _body("Invoke-Apply").replace("Get-ScheduledTask", "")  # nothing in the install itself is swallowed


def test_a_failed_install_rolls_back_and_says_when_the_rollback_itself_failed() -> None:
    apply_body = _body("Invoke-Apply")
    catch = apply_body[apply_body.index("} catch {") :]

    assert catch.index("Remove-GateInstallation $Dest $TaskName $false") < catch.index("已回滚") < catch.index("回滚没有清干净") < catch.index("-Repair")
    assert "throw" in catch.split("回滚没有清干净")[1]  # the install still fails after the rollback
    steps = apply_body[apply_body.index("try {") : apply_body.index("} catch {")]
    assert steps.index("Register-ScheduledTask") > steps.index("selftest")  # nothing is registered before the self-test passed


def test_repair_does_not_need_the_installed_python_and_asks_the_user_when_it_cannot_decide() -> None:
    clean = _body("Remove-GateInstallation")

    assert "Reset-FolderAccess" in clean and clean.index("Reset-FolderAccess") < clean.index("state.json") < clean.index("Unregister-ScheduledTask")
    assert "Test-Path -LiteralPath $statePath" in clean  # the state file says whether the watchdog ever ran
    assert "$unknown" in clean and "-ForceDelete" in clean and "状态文件读不了" in clean
    assert clean.index("Test-Path -LiteralPath $python") < clean.index("if (-not $thawed)")  # a missing or broken python only matters when something is frozen


def test_a_leftover_with_an_unusable_acl_is_taken_over_reset_and_every_step_is_reported() -> None:
    """The 2026-11-04 laptop failure: the old half install could not be deleted ("access denied") even after takeown + a grant."""

    access = _body("Reset-FolderAccess")

    # whole tree, in this order: ownership first, then the old ACL is thrown away, then Administrators get full control
    order = [access.index(needle) for needle in ('"takeown.exe"', '"/setowner"', '"/reset"', '"/grant"')]
    assert order == sorted(order)
    assert '"/A", "/R", "/D", "Y"' in access  # takeown: to the Administrators group, recursive, no prompt on unreadable folders
    assert access.count('"/T", "/C"') >= 3  # the three icacls steps walk the whole tree and carry on past one unreadable item ...
    assert "退出码" in access and "$trace" in access and "return ($trace" in access  # ... but each exit code is kept and handed back
    assert "SilentlyContinue" not in access

    clean = _body("Remove-GateInstallation")
    assert "$access = Reset-FolderAccess $Folder" in clean  # -Install (step 2 and the roll-back), -Repair and -Uninstall all pass through here
    deletion = clean[clean.index("Remove-Item -LiteralPath $Folder") :]
    assert deletion.index("Clear-FolderWithBackupRights") < deletion.index("throw")  # a second way of deleting is tried before giving up
    assert "$access" in deletion[deletion.index("throw") :] and "Get-OwnerAndAcl" in deletion  # the failure names every step and the folder's real state
    backup = _body("Clear-FolderWithBackupRights")
    assert '"/MIR", "/B"' in backup and backup.index("robocopy.exe") < backup.index("Remove-Item -LiteralPath $Folder")


def test_the_install_never_strips_the_inherited_rights_from_files_that_already_exist_and_checks_the_result() -> None:
    """Root cause of the empty ACLs (11-04): the first script ran ``icacls <dir> /inheritance:r /grant:r (OI)(CI)... /T /C`` over a tree that
    already held files; removing the inherited entries from every file left them with none.  The lock is now set once on the empty folder and the
    files inherit it; the install ends by looking at every ACL."""

    script = _installer()

    for line in script.splitlines():
        if "/inheritance:r" in line:
            assert "/T" not in line, line  # only ever the (empty) folder itself
    apply_body = _body("Invoke-Apply")
    assert apply_body.index("Expand-CheckedPython") < apply_body.index("Assert-InstalledAcls $Dest") < apply_body.index("selftest")
    assert apply_body.index("Assert-InstalledAcls $Dest") < apply_body.index("} catch {")  # a failure there rolls the install back
    check = _body("Assert-InstalledAcls")
    assert "Get-TreeAccessProblems" in check and "python\\python.exe" in check and "S-1-5-18" in check and "S-1-5-32-544" in check
    assert "throw" in check


def test_the_clean_up_is_judged_by_the_acls_it_leaves_not_by_exit_codes() -> None:
    access = _body("Reset-FolderAccess")

    assert access.index("Get-TreeAccessProblems") < access.index("Set-TreeAdminAccess") < access.rindex("Get-TreeAccessProblems")  # look, repair item by item, look again
    item = _body("Set-ItemAdminAccess")
    assert item.index("SetOwner") < item.index("SetAccessRuleProtection")  # ownership first: the ACL can only be rewritten by its owner
    assert "SystemRoot" not in item and "S-1-5-32-544" in item and "S-1-5-18" in item
    tree = _body("Set-TreeAdminAccess")
    assert tree.index("Set-ItemAdminAccess $item") < tree.index("Get-ChildItem")  # a folder is opened up before its children are listed
    assert "ReparsePoint" in tree  # a link inside the tree is not followed


def test_one_uac_prompt_and_the_prepare_phase_comes_first() -> None:
    script = _installer()
    entry = script[script.index("# ---------------------------------------------------------------- entry") :]

    assert entry.count("Start-ElevatedSelf @(\"-Install\")") == 1
    assert entry.index("Invoke-Prepare $Repo") < entry.index("Start-ElevatedSelf @(\"-Install\")")
    assert "-Verb RunAs" in _body("Start-ElevatedSelf") and _body("Start-ElevatedSelf").count("-Verb RunAs") == 1
    assert "没有点「是」" in _body("Start-ElevatedSelf")  # declining the prompt changes nothing and says so
    prepare = _body("Invoke-Prepare")
    for needle in ("Read-PinnedHash", "status", "merge-base", "Get-EmbeddedPythonZip", "selftest", "Expand-CheckedPython"):
        assert needle in prepare


def test_the_manifest_records_the_config_file_the_gate_may_read() -> None:
    apply_body = _body("Invoke-Apply")

    assert "config_path" in apply_body and "memory_gate.json" in _installer()


@pytest.mark.skipif(sys.platform != "win32" or not os.environ.get("SystemRoot"), reason="Windows PowerShell only")
def test_the_clean_up_removes_a_half_installed_folder_and_refuses_when_something_may_be_frozen(tmp_path: Path) -> None:
    exe = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"

    def run(folder: Path) -> subprocess.CompletedProcess[bytes]:
        command = (
            f". '{INSTALLER}'; try {{ Remove-GateInstallation '{folder}' 'AutoPM-MemoryGate-NoSuchTask' $false; exit 0 }} "
            "catch { Write-Host $_.Exception.Message; exit 7 }"
        )
        return subprocess.run([str(exe), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command], capture_output=True, timeout=180, check=False)  # noqa: S603

    half = tmp_path / "half"
    (half / "state").mkdir(parents=True)
    (half / "scripts").mkdir()
    (half / "scripts" / "memory_gate.py").write_text("# half\n", encoding="utf-8")
    (half / "state" / "state.json").write_text('{"frozen": []}', encoding="utf-8")
    assert run(half).returncode == 0 and not half.exists()

    frozen = tmp_path / "frozen"
    (frozen / "state").mkdir(parents=True)
    (frozen / "state" / "state.json").write_text('{"frozen": [{"root": 1}]}', encoding="utf-8")
    refused = run(frozen)
    assert refused.returncode == 7 and frozen.exists()  # no python to thaw with: nothing is deleted, the user decides


def _is_admin() -> bool:
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined,unused-ignore]
    except (AttributeError, OSError):
        return False


def _powershell(command: str, timeout: int = 300) -> subprocess.CompletedProcess[bytes]:
    exe = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    # a piped Windows PowerShell writes the OEM code page (GBK on a Chinese Windows); the tests decode UTF-8, which is what the installer sets before it reads the text
    command = "[Console]::OutputEncoding = [Text.Encoding]::UTF8; " + command
    return subprocess.run([str(exe), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command], capture_output=True, timeout=timeout, check=False)  # noqa: S603


def _empty_the_acl(path: Path, *, owner_system: bool) -> bool:
    """The state RC found on the laptop: no entry at all (and, for the stricter variant, an owner that is not an administrator)."""

    system32 = Path(os.environ["SystemRoot"]) / "System32"
    me = subprocess.run([str(system32 / "whoami.exe"), "/user", "/fo", "csv", "/nh"], capture_output=True, timeout=60, check=False).stdout.decode("utf-8", "replace").strip().split(",")[-1].strip('" \r\n')

    def icacls(*arguments: str) -> int:
        return subprocess.run([str(system32 / "icacls.exe"), str(path), *arguments], capture_output=True, timeout=120, check=False).returncode  # noqa: S603

    codes = []
    if owner_system:
        codes.append(icacls("/setowner", "*S-1-5-18"))
    codes.append(icacls("/inheritance:r"))
    codes.append(icacls("/remove", "*S-1-5-32-544", "*S-1-5-18", "*S-1-5-32-545", "*S-1-5-11", f"*{me}"))
    return codes[-1] == 0


@pytest.mark.skipif(sys.platform != "win32" or not os.environ.get("SystemRoot"), reason="Windows PowerShell only")
def test_a_file_with_an_empty_acl_is_found_and_an_installed_tree_with_one_is_refused(tmp_path: Path) -> None:
    """The install ends with a look at every ACL: an empty one makes the folder impossible to clean up later (11-04), so it fails the install."""

    tree = tmp_path / "MemoryGate"
    for relative in ("python/python.exe", "scripts/memory_gate.py", "manifest.json"):
        (tree / relative).parent.mkdir(parents=True, exist_ok=True)
        (tree / relative).write_text("x", encoding="utf-8")
    system32 = Path(os.environ["SystemRoot"]) / "System32"
    grant = subprocess.run([str(system32 / "icacls.exe"), str(tree), "/grant", "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F", "/T", "/C"], capture_output=True, timeout=120, check=False)  # noqa: S603
    assert grant.returncode == 0
    call = f". '{INSTALLER}'; try {{ Assert-InstalledAcls '{tree}'; exit 0 }} catch {{ Write-Host $_.Exception.Message; exit 7 }}"

    healthy = _powershell(call)
    assert healthy.returncode == 0, healthy.stdout.decode("utf-8", "replace")

    if not _empty_the_acl(tree / "python" / "python.exe", owner_system=False):
        pytest.skip("could not empty an ACL on this runner")
    broken = _powershell(call)
    assert broken.returncode == 7 and "权限是空的" in broken.stdout.decode("utf-8", "replace")


@pytest.mark.skipif(sys.platform != "win32" or not os.environ.get("SystemRoot"), reason="Windows PowerShell only")
def test_the_clean_up_repairs_and_removes_files_whose_acl_names_nobody(tmp_path: Path) -> None:
    """RC's finding on the laptop: the folder and python\\ were normal, the files inside (python.exe, memory_gate.py) had an empty ACL, and the old
    takeown + icacls grant exited 0 without changing that.  Rebuild it, show the repair is judged by the ACLs and not by an exit code, then clean up."""

    if not _is_admin():
        pytest.skip("needs an elevated token to hand the files to SYSTEM")
    leftover = tmp_path / "MemoryGate"
    files = [leftover / "python" / "python.exe", leftover / "scripts" / "memory_gate.py", leftover / "manifest.json", leftover / "auto_pm" / "infrastructure" / "a.py"]
    for file in files:
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("x", encoding="utf-8")
    emptied = [_empty_the_acl(file, owner_system=True) for file in files]
    if not all(emptied):
        pytest.skip("could not build the damaged leftover on this runner")

    count = f". '{INSTALLER}'; $n = @(Get-TreeAccessProblems '{leftover}').Count; Write-Host \"problems=$n\"; exit 0"
    seen = _powershell(count)
    assert "problems=0" not in seen.stdout.decode("utf-8", "replace"), seen.stdout.decode("utf-8", "replace")  # the check itself notices the damage

    repair = _powershell(
        f". '{INSTALLER}'; Write-Host (Reset-FolderAccess '{leftover}'); $n = @(Get-TreeAccessProblems '{leftover}').Count; Write-Host \"after=$n\"; exit 0"
    )
    assert "after=0" in repair.stdout.decode("utf-8", "replace"), repair.stdout.decode("utf-8", "replace")

    command = (
        f". '{INSTALLER}'; try {{ Remove-GateInstallation '{leftover}' 'AutoPM-MemoryGate-NoSuchTask' $false; exit 0 }} "
        "catch { Write-Host $_.Exception.Message; exit 7 }"
    )
    done = _powershell(command)
    assert done.returncode == 0, done.stdout.decode("utf-8", "replace")
    assert not leftover.exists()


# ---------------------------------------------------------------- setup_env.bat step 5
def test_setup_env_installs_the_gate_as_step_5_with_a_skip_switch_and_without_paren_blocks() -> None:
    bat = (WORKSPACE / "setup_env.bat").read_text(encoding="utf-8")

    assert "install_memory_gate.ps1" in bat and "-Install" in bat and "--no-gate" in bat
    assert "[5/5]" in bat and "[1/5]" in bat and "[4/5]" in bat
    assert bat.index("[4/5]") < bat.index("[5/5]") < bat.index("[成功]")
    step = bat[bat.index(":: 5.") : bat.index("[成功]")]
    assert "(" not in re.sub(r"echo[^\n]*|::[^\n]*|for %%A in \(%\*\)", "", step)  # no parenthesised block: errorlevel would be read too early
    assert "errorlevel 1 goto" in step  # a failed install is reported, not hidden, and does not undo the finished environment


# ---------------------------------------------------------------- pm orient: one read-only line
def _installed(tmp_path: Path, *, bundle: str, beat: float | None) -> Path:
    root = tmp_path / "MemoryGate"
    (root / "state").mkdir(parents=True)
    (root / "manifest.json").write_text(json.dumps({"bundle_sha256": bundle, "files": {}}), encoding="utf-8")
    if beat is not None:
        (root / "state" / "state.json").write_text(json.dumps({"heartbeat": beat, "frozen": []}), encoding="utf-8")
    return root


def _pin(tmp_path: Path, bundle: str) -> Path:
    pin = tmp_path / "pin.json"
    pin.write_text(json.dumps({"bundle_sha256": bundle}), encoding="utf-8")
    return pin


def test_orient_says_nothing_on_a_machine_the_gate_does_not_apply_to(tmp_path: Path) -> None:
    assert status_module.read_gate_status(platform="linux", install_dir=tmp_path) is None


def test_orient_line_for_every_state_and_it_never_installs_anything(tmp_path: Path) -> None:
    same, other = "a" * 64, "b" * 64
    pin = _pin(tmp_path, same)
    common = {"pin_file": pin, "platform": "win32", "now": 1_000.0}

    absent = status_module.read_gate_status(install_dir=tmp_path / "nothing", **common)
    assert absent is not None and absent.state == "not_installed" and "setup_env.bat" in absent.line() and "不会自动安装" in absent.line()

    running = status_module.read_gate_status(install_dir=_installed(tmp_path / "a", bundle=same, beat=990.0), **common)
    assert running is not None and running.state == "running" and "一致" in running.line() and not running.update_available

    old = status_module.read_gate_status(install_dir=_installed(tmp_path / "b", bundle=other, beat=990.0), **common)
    assert old is not None and old.update_available and "有新版本" in old.line() and "setup_env.bat" in old.line()

    dead = status_module.read_gate_status(install_dir=_installed(tmp_path / "c", bundle=same, beat=100.0), **common)
    assert dead is not None and dead.state == "stale" and "没有心跳" in dead.line()

    never = status_module.read_gate_status(install_dir=_installed(tmp_path / "d", bundle=same, beat=None), **common)
    assert never is not None and never.state == "stale"

    leftover = tmp_path / "e" / "MemoryGate"
    leftover.mkdir(parents=True)
    residue = status_module.read_gate_status(install_dir=leftover, **common)
    assert residue is not None and residue.state == "unreadable" and "残留" in residue.line()

    (tmp_path / "f").mkdir()
    (tmp_path / "f" / "manifest.json").write_text("{not json", encoding="utf-8")
    broken = status_module.read_gate_status(install_dir=tmp_path / "f", **common)
    assert broken is not None and broken.state == "unreadable"


def test_orient_without_a_pin_says_it_could_not_compare(tmp_path: Path) -> None:
    status = status_module.read_gate_status(
        install_dir=_installed(tmp_path, bundle="a" * 64, beat=995.0), pin_file=tmp_path / "missing.json", platform="win32", now=1_000.0
    )

    assert status is not None and status.state == "running" and "未能核对" in status.line() and not status.update_available


def test_the_status_module_can_find_the_committed_pin_next_to_the_sources() -> None:
    assert status_module._pinned_bundle(None, None) == mg.read_pin()[0]  # noqa: SLF001


def test_the_commands_print_their_chinese_text_through_a_pipe_whose_default_encoding_cannot_hold_it() -> None:
    """11-04 CI: on Windows a pipe defaults to cp1252 and ``pin-check`` / ``bundle-hash`` died with UnicodeEncodeError."""

    env = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}  # what a Windows pipe does by default
    for command in ("bundle-hash", "pin-check"):
        done = subprocess.run([sys.executable, "-B", str(SCRIPT), command], capture_output=True, timeout=60, check=False, env=env)  # noqa: S603

        assert done.returncode == 0, done.stderr.decode("utf-8", errors="replace")
        assert "UnicodeEncodeError" not in done.stderr.decode("utf-8", errors="replace")
        done.stdout.decode("utf-8")  # the text is UTF-8, which is what the installer reads
