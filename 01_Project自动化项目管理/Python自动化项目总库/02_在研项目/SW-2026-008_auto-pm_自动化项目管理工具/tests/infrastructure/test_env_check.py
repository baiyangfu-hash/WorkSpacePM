"""D-156 卡②：环境自检 env_check.py（只用标准库，.venv 没装好时也能跑）。"""

from __future__ import annotations

import ast
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.external_reads  # D-200: reads real files outside the project

WORKSPACE = Path(__file__).resolve().parents[6]
ENV_DIR = WORKSPACE / "00_Infrastructure" / "auto_pm" / "environment"
SCRIPT = ENV_DIR / "env_check.py"
WRAPPER = ENV_DIR / "cloud_selfcheck.sh"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("env_check_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclass 解析注解时要在 sys.modules 里找到本模块
    spec.loader.exec_module(module)
    return module


env_check = _load()


def _venv(root: Path, *, windows: bool) -> None:
    python = env_check.venv_python(root, windows=windows)
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")


class Probes:
    """按命令的特征回答，并记下每次被问到什么。"""

    def __init__(
        self,
        *,
        version: str = "3.12",
        missing: tuple[str, ...] = (),
        qt_ok: bool = True,
        shallow: str | None = "false",
        import_fails: bool = False,
    ) -> None:
        self.version, self.missing, self.qt_ok, self.shallow, self.import_fails = (
            version,
            missing,
            qt_ok,
            shallow,
            import_fails,
        )
        self.asked: list[list[str]] = []

    def __call__(self, command: object, env: dict[str, str] | None) -> tuple[int, str]:
        words = list(command)  # type: ignore[call-overload]
        self.asked.append(words)
        if words[0] == "git":
            return (0, f"{self.shallow}\n") if self.shallow is not None else (128, "")
        code = words[2]
        if "sys.version_info" in code:
            return 0, self.version + "\n"
        if "import_module" in code:
            return (
                (1, "") if self.import_fails else (0, "".join(f"{name}\n" for name in self.missing))
            )
        assert "QApplication" in code and env is not None and env["QT_QPA_PLATFORM"] == "offscreen"
        return (0 if self.qt_ok else 1), ""


@pytest.mark.parametrize("windows", [False, True])
def test_without_a_venv_the_check_fails_with_the_setup_command_and_skips_the_venv_probes(
    tmp_path: Path, windows: bool
) -> None:
    probes = Probes()

    checks = env_check.run_checks(tmp_path, windows=windows, probe=probes)

    first = checks[0]
    assert not first.ok and "没有 .venv" in first.name
    assert first.fix == (
        "双击根目录的 setup_env.bat"
        if windows
        else "sh 00_Infrastructure/auto_pm/environment/setup_env.sh"
    )
    assert [words[0] for words in probes.asked] == ["git"], (
        "没有 .venv 时不该再去问 .venv 里的 Python"
    )


def test_the_venv_python_path_differs_by_platform(tmp_path: Path) -> None:
    assert env_check.venv_python(tmp_path, windows=False) == tmp_path / ".venv" / "bin" / "python"
    assert (
        env_check.venv_python(tmp_path, windows=True)
        == tmp_path / ".venv" / "Scripts" / "python.exe"
    )


def test_a_healthy_environment_passes_every_check(tmp_path: Path) -> None:
    _venv(tmp_path, windows=False)

    checks = env_check.run_checks(tmp_path, windows=False, probe=Probes())

    assert all(check.ok for check in checks) and len(checks) == 4
    assert "[失败]" not in env_check.format_report(checks)


def test_a_venv_with_another_python_version_names_the_version_and_the_way_out(
    tmp_path: Path,
) -> None:
    _venv(tmp_path, windows=False)

    checks = env_check.run_checks(tmp_path, windows=False, probe=Probes(version="3.13"))

    bad = [check for check in checks if not check.ok]
    assert len(bad) == 1 and "3.13" in bad[0].name and "3.12" in bad[0].name
    assert bad[0].fix.startswith("mv .venv .venv.old && sh ")


def test_missing_modules_are_named(tmp_path: Path) -> None:
    _venv(tmp_path, windows=False)

    checks = env_check.run_checks(
        tmp_path, windows=False, probe=Probes(missing=("pytest_cov", "xdist"))
    )

    bad = [check for check in checks if not check.ok]
    assert len(bad) == 1 and "pytest_cov、xdist" in bad[0].name


def test_an_import_probe_that_cannot_run_counts_every_module_as_missing(tmp_path: Path) -> None:
    _venv(tmp_path, windows=False)

    checks = env_check.run_checks(tmp_path, windows=False, probe=Probes(import_fails=True))

    bad = [check for check in checks if not check.ok]
    assert len(bad) == 1 and all(name in bad[0].name for name in env_check.REQUIRED_MODULES)


def test_qt_failure_gets_the_apt_line_on_linux_and_the_setup_line_on_windows(
    tmp_path: Path,
) -> None:
    _venv(tmp_path, windows=False)
    linux = [
        c
        for c in env_check.run_checks(tmp_path, windows=False, probe=Probes(qt_ok=False))
        if not c.ok
    ]
    other = tmp_path / "w"
    other.mkdir()
    _venv(other, windows=True)
    windows = [
        c for c in env_check.run_checks(other, windows=True, probe=Probes(qt_ok=False)) if not c.ok
    ]

    assert len(linux) == 1 and "apt-get install" in linux[0].fix and "libegl1" in linux[0].fix
    assert (
        len(windows) == 1 and "apt-get" not in windows[0].fix and "setup_env.bat" in windows[0].fix
    )


def test_a_shallow_clone_or_missing_git_is_reported(tmp_path: Path) -> None:
    _venv(tmp_path, windows=False)

    shallow = [
        c
        for c in env_check.run_checks(tmp_path, windows=False, probe=Probes(shallow="true"))
        if not c.ok
    ]
    nogit = [
        c
        for c in env_check.run_checks(tmp_path, windows=False, probe=Probes(shallow=None))
        if not c.ok
    ]

    assert len(shallow) == 1 and shallow[0].fix == "git fetch --unshallow origin"
    assert len(nogit) == 1 and "git" in nogit[0].name


def test_the_report_puts_the_fix_under_each_failure() -> None:
    report = env_check.format_report(
        [env_check.Check("好的", True), env_check.Check("坏的", False, "做这个")]
    )

    assert report.splitlines() == ["[通过] 好的", "[失败] 坏的", "       补救：做这个"]


def test_run_probe_returns_output_and_treats_a_missing_program_as_failure() -> None:
    code, out = env_check.run_probe([sys.executable, "-c", "print('hi')"])
    missing_code, missing_out = env_check.run_probe(["definitely-not-a-program-d156"])

    assert (code, out.strip()) == (0, "hi")
    assert (missing_code, missing_out) == (127, "")


def _copy_script_into_a_bare_tree(tmp_path: Path) -> Path:
    """一棵只有脚本的假工作空间：没有 .venv、不是 Git 仓库、Python 也没装 auto_pm。"""

    folder = tmp_path / "00_Infrastructure" / "auto_pm" / "environment"
    folder.mkdir(parents=True)
    shutil.copy(SCRIPT, folder / "env_check.py")
    shutil.copy(WRAPPER, folder / "cloud_selfcheck.sh")
    return folder


def test_the_script_runs_alone_with_a_bare_python_and_exits_1_with_a_remedy(tmp_path: Path) -> None:
    folder = _copy_script_into_a_bare_tree(tmp_path)

    # 管道里的输出固定是 UTF-8，哪怕解释器的默认输出编码打不出中文（Windows 的 ANSI 代码页，#672 的 CI 上发生过）
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    done = subprocess.run(
        [sys.executable, str(folder / "env_check.py")],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert done.returncode == 1
    assert "[失败] 没有 .venv" in done.stdout and "补救：" in done.stdout
    assert "退出码非 0 不要开工" in done.stderr


@pytest.mark.skipif(shutil.which("sh") is None, reason="需要 sh")
def test_the_shell_wrapper_only_hands_over_to_the_script(tmp_path: Path) -> None:
    text = WRAPPER.read_text(encoding="utf-8")
    assert "env_check.py" in text and "[ -x" not in text, "检查逻辑不要再留在 shell 里"
    folder = _copy_script_into_a_bare_tree(tmp_path)

    done = subprocess.run(
        ["sh", str(folder / "cloud_selfcheck.sh")],
        env={**os.environ, "PYTHONIOENCODING": "cp1252"},
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert done.returncode == 1 and "[失败] 没有 .venv" in done.stdout


@pytest.mark.skipif(shutil.which("sh") is None, reason="需要 sh")
def test_the_shell_wrapper_skips_a_python3_stub_that_cannot_run(tmp_path: Path) -> None:
    """D-198：Windows 应用商店的 python3 占位桩 command -v 找得到、一运行就退出 49；壳必须跳过它去用下一个真 Python。"""

    folder = _copy_script_into_a_bare_tree(tmp_path)
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    fake = stubs / "python3"
    fake.write_text("#!/bin/sh\nexit 49\n", encoding="utf-8", newline="\n")
    real = stubs / "python"
    real.write_text(f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "$@"\n', encoding="utf-8", newline="\n")
    for stub in (fake, real):
        stub.chmod(0o755)

    done = subprocess.run(
        ["sh", str(folder / "cloud_selfcheck.sh")],
        env={**os.environ, "PATH": os.pathsep.join([str(stubs), os.environ.get("PATH", "")]), "PYTHONIOENCODING": "cp1252"},
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert done.returncode == 1 and "[失败] 没有 .venv" in done.stdout, done.stdout + done.stderr


def _runtime_nodes(tree: ast.Module) -> list[ast.AST]:
    """模块里会在导入时真正求值的节点：跳过 TYPE_CHECKING 块和各种注解（有 __future__ annotations 时它们是字符串）。"""

    skipped: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and "TYPE_CHECKING" in ast.dump(node.test):
            skipped.update(id(n) for n in ast.walk(node))
        annotations: list[ast.AST | None] = []
        if isinstance(node, ast.AnnAssign):
            annotations.append(node.annotation)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            annotations.append(node.returns)
            args = node.args
            all_args = [*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg]
            annotations.extend(a.annotation for a in all_args if a is not None)
        for annotation in annotations:
            if annotation is not None:
                skipped.update(id(n) for n in ast.walk(annotation))
    return [n for n in ast.walk(tree) if id(n) not in skipped]


def _unsafe_for_py39(source: str) -> list[str]:
    nodes = _runtime_nodes(ast.parse(source))
    found = [
        f"第 {n.lineno} 行：运行时 `X | Y`"
        for n in nodes
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr)
    ]
    builtins_generic = {"dict", "list", "tuple", "set", "frozenset", "type"}
    found += [
        f"第 {n.lineno} 行：运行时 `{n.value.id}[...]`"
        for n in nodes
        if isinstance(n, ast.Subscript)
        and isinstance(n.value, ast.Name)
        and n.value.id in builtins_generic
    ]
    return found


def test_d156_no_module_level_expression_that_crashes_on_python_39() -> None:
    """env_check.py 要在任何旧系统 Python 上先跑起来：不能有导入时求值的 `X | Y`、`dict[...]`（≤3.9 会 TypeError）。"""

    assert _unsafe_for_py39(SCRIPT.read_text(encoding="utf-8")) == []


def test_d156_the_py39_scan_catches_the_old_alias() -> None:
    old = "from collections.abc import Callable, Sequence\nProbe = Callable[[Sequence[str], dict[str, str] | None], tuple[int, str]]\n"
    assert len(_unsafe_for_py39(old)) == 3
    guarded = "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    Probe = dict[str, str] | None\ndef f(x: dict[str, str] | None) -> list[int]: ...\n"
    assert _unsafe_for_py39(guarded) == []
