"""看板从 pythonw 启动时，起子命令要换成同目录的 python.exe（卡 281）。

用户双击 ``双击打开驾驶舱看板.bat`` 起的是 pythonw.exe。看板原来用 ``sys.executable`` 起 ``main.py``，
pythonw 一层层往下起的子进程输出到不了看板接的管道：退出码 0、输出 0 字节，每一页都成了
“只有启动提示，没有结果”（2026-11-16 用户电脑实测）。测试和 CI 一直用 python.exe 跑，所以没抓到。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cockpit_board import actions, tool_actions  # noqa: E402


def _fake_python_dir(tmp_path: Path, *, with_console: bool) -> Path:
    folder = tmp_path / "Scripts"
    folder.mkdir()
    (folder / "pythonw.exe").write_bytes(b"")
    if with_console:
        (folder / "python.exe").write_bytes(b"")
    return folder


def test_pythonw_is_swapped_for_the_console_python_next_to_it(tmp_path: Path) -> None:
    folder = _fake_python_dir(tmp_path, with_console=True)
    assert actions.child_python(str(folder / "pythonw.exe")) == str(folder / "python.exe")
    assert actions.child_python(str(folder / "PYTHONW.EXE")) == str(folder / "python.exe")


def test_pythonw_without_a_console_python_is_kept(tmp_path: Path) -> None:
    folder = _fake_python_dir(tmp_path, with_console=False)
    assert actions.child_python(str(folder / "pythonw.exe")) == str(folder / "pythonw.exe")


def test_a_console_python_is_left_alone(tmp_path: Path) -> None:
    folder = _fake_python_dir(tmp_path, with_console=True)
    assert actions.child_python(str(folder / "python.exe")) == str(folder / "python.exe")


def test_every_board_command_uses_the_swapped_interpreter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """读数、检查、工具、新终端窗口四条起子进程的路，都不能再直接用 pythonw。"""
    folder = _fake_python_dir(tmp_path, with_console=True)
    monkeypatch.setattr(sys, "executable", str(folder / "pythonw.exe"))
    console = str(folder / "python.exe")
    root = tmp_path / "root"

    assert actions.cli_command(root, ["worktree", "list"])[0] == console
    assert tool_actions.full_command(root, ["change", "list"])[0] == console

    seen: list[list[str]] = []

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        seen.append(list(command))
        return subprocess.CompletedProcess(command, 0, "", "")

    actions.run_check(root, root, "SW-2026-008", "plc_check", runner=runner)
    assert seen[-1][0] == console

    opened: list[list[str]] = []
    monkeypatch.setattr(actions, "console_flag", lambda: 1)
    actions.open_console(root, "x", ["worktree", "list"], opener=lambda command, **_: opened.append(list(command)))
    assert opened[-1][0] == console


@pytest.mark.skipif(os.name != "nt", reason="pythonw.exe 只在 Windows 上有")
def test_on_windows_the_swapped_interpreter_really_returns_output(tmp_path: Path) -> None:
    """按双击的路子真跑一次：pythonw 起的子进程照看板的读法（接管道、不弹窗）要拿得到输出。"""
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.is_file():
        pytest.skip("这个 Python 旁边没有 pythonw.exe")
    script = tmp_path / "child.py"
    script.write_text(
        "import subprocess, sys\n"
        "sys.path.insert(0, sys.argv[1])\n"
        "from cockpit_board import actions\n"
        # 和 main.py 一样再起一层孙进程、不指定输出（继承）：输出要一路回到看板接的管道
        "grandchild = 'import subprocess, sys; subprocess.run([sys.executable, \"-c\", \"print(1 + 1)\"])'\n"
        "inner = [actions.child_python(), '-c', grandchild]\n"
        "r = subprocess.run(inner, capture_output=True, text=True, stdin=subprocess.DEVNULL, **actions.quiet())\n"
        "open(sys.argv[2], 'w', encoding='utf-8').write(r.stdout)\n",
        encoding="utf-8",
    )
    result_file = tmp_path / "result.txt"
    scripts_dir = Path(actions.__file__).resolve().parent.parent
    subprocess.run([str(pythonw), str(script), str(scripts_dir), str(result_file)], check=True, timeout=120,
                   stdin=subprocess.DEVNULL)
    assert result_file.read_text(encoding="utf-8").strip() == "2"
