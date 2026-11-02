"""总控屏联网探测：超时、网络不通、认证失败、地址错误、没有 origin 分别写明，不都写成“3 秒超时”。

用户去中国后 GitHub 时通时不通，这几种读不到的处理办法不一样（等一等 / 重新登录 / 改地址），所以要分开说。
全部用假运行器，不连外网。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from tests.core import test_cockpit_board as board_tests  # noqa: E402
from tests.core import test_pm_dashboard as base  # noqa: E402
from tests.core import test_pm_dashboard_gui as gui_tests  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cockpit_board import actions  # noqa: E402
from cockpit_board import viewmodel as vm  # noqa: E402

# 真实 git 的报错文字（LC_ALL=C 下），按我们要区分的几种各取一条
STDERR = {
    "no_origin": "fatal: 'origin' does not appear to be a git repository\nfatal: Could not read from remote repository.\n",
    "auth": "remote: Invalid username or password.\nfatal: Authentication failed for 'https://github.com/x/y.git/'\n",
    "auth_prompt_off": "fatal: could not read Username for 'https://github.com': terminal prompts disabled\n",
    "auth_ssh": "git@github.com: Permission denied (publickey).\nfatal: Could not read from remote repository.\n",
    "auth_403": "fatal: unable to access 'https://github.com/x/y.git/': The requested URL returned error: 403\n",
    "bad_url": "remote: Repository not found.\nfatal: repository 'https://github.com/x/nope.git/' not found\n",
    "bad_url_404": "fatal: unable to access 'https://github.com/x/y.git/': The requested URL returned error: 404\n",
    "bad_url_path": "fatal: '/no/such/dir' does not appear to be a git repository\n",
    "network_dns": "fatal: unable to access 'https://github.com/x/y.git/': Could not resolve host: github.com\n",
    "network_refused": "fatal: unable to access 'https://github.com/x/y.git/': Failed to connect to github.com port 443: Connection refused\n",
    "network_timeout": "fatal: unable to access 'https://github.com/x/y.git/': Failed to connect to github.com port 443 after 21000 ms: Timed out\n",
    "network_tls": "fatal: unable to access 'https://github.com/x/y.git/': schannel: failed to receive handshake, SSL/TLS connection failed\n",
}
EXPECTED = {
    "no_origin": "no_origin", "auth": "auth", "auth_prompt_off": "auth", "auth_ssh": "auth", "auth_403": "auth",
    "bad_url": "bad_url", "bad_url_404": "bad_url", "bad_url_path": "bad_url",
    "network_dns": "network", "network_refused": "network", "network_timeout": "network", "network_tls": "network",
}


class Runner:
    """假的 subprocess.run。"""

    def __init__(self, rc: int = 0, stderr: str = "", error: Exception | None = None) -> None:
        self.rc, self.stderr, self.error = rc, stderr, error
        self.kwargs: dict[str, Any] = {}

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return subprocess.CompletedProcess(command, self.rc, "", self.stderr)


@pytest.mark.parametrize("name", sorted(STDERR))
def test_each_failure_text_lands_in_its_own_kind(tmp_path: Path, name: str) -> None:
    probe = actions.probe_origin(tmp_path, runner=Runner(128, STDERR[name]))
    assert probe.kind == EXPECTED[name] and not probe.online, name


def test_non_zero_exit_code_means_not_online(tmp_path: Path) -> None:
    """协调者要求的那一条：任何非 0 退出码，probe_online 都是 False（含认识和不认识的报错）。"""
    for rc, stderr in ((128, ""), (128, "fatal: something new\n"), (1, STDERR["auth"]), (2, ""), (255, STDERR["network_dns"])):
        assert actions.probe_online(tmp_path, runner=Runner(rc, stderr)) is False, (rc, stderr)
    assert actions.probe_online(tmp_path, runner=Runner(0)) is True


def test_zero_exit_is_online_and_says_so(tmp_path: Path) -> None:
    probe = actions.probe_origin(tmp_path, runner=Runner(0))
    assert probe.kind == "online" and probe.online and probe.text == "在线"


def test_timeout_is_its_own_kind_and_says_how_long(tmp_path: Path) -> None:
    probe = actions.probe_origin(tmp_path, runner=Runner(error=subprocess.TimeoutExpired("git", actions.PROBE_TIMEOUT)))
    assert probe.kind == "timeout" and not probe.online
    assert "超时" in probe.text and str(actions.PROBE_TIMEOUT) in probe.text


def test_only_the_timeout_text_mentions_the_timeout_limit(tmp_path: Path) -> None:
    """认证失败、地址错误、没有 origin 都不能写成“3 秒超时”。"""
    for name in ("auth", "bad_url", "no_origin", "network_dns"):
        text = actions.probe_origin(tmp_path, runner=Runner(128, STDERR[name])).text
        assert "秒" not in text and "超时" not in text, (name, text)


def test_texts_tell_the_user_what_to_do(tmp_path: Path) -> None:
    texts = {k: actions.PROBE_TEXT[k] for k in actions.PROBE_TEXT}
    assert "gh auth login" in texts["auth"]
    assert "git remote -v" in texts["bad_url"] and "git remote -v" in texts["no_origin"]
    assert len(set(texts.values())) == len(texts)  # 每一种说法都不一样


def test_git_missing_and_other_os_errors(tmp_path: Path) -> None:
    assert actions.probe_origin(tmp_path, runner=Runner(error=FileNotFoundError("git"))).kind == "no_git"
    other = actions.probe_origin(tmp_path, runner=Runner(error=PermissionError("denied")))
    assert other.kind == "other" and not other.online


def test_empty_remote_is_reached_but_not_online(tmp_path: Path) -> None:
    probe = actions.probe_origin(tmp_path, runner=Runner(2, ""))
    assert probe.kind == "empty" and not probe.online and "HEAD" in probe.text


def test_unknown_failure_shows_the_first_line_without_credentials(tmp_path: Path) -> None:
    secret = "ghp_" + "SecretTokenDoNotShow0123456789abcd"
    stderr = f"\nfatal: strange failure at https://bob:{secret}@example.com/x.git/ now\nsecond line\n"
    probe = actions.probe_origin(tmp_path, runner=Runner(128, stderr))
    assert probe.kind == "other" and "rc 128" in probe.text and "strange failure" in probe.text
    assert secret not in probe.text and secret not in probe.detail and "bob" not in probe.text and "***@" in probe.text
    err = actions.probe_origin(tmp_path, runner=Runner(error=OSError(f"bad https://bob:{secret}@h/x")))
    assert secret not in err.text


def test_probe_asks_git_for_english_messages_and_never_prompts(tmp_path: Path) -> None:
    runner = Runner(0)
    actions.probe_origin(tmp_path, runner=runner)
    env = runner.kwargs["env"]
    assert env["LC_ALL"] == "C" and env["GIT_TERMINAL_PROMPT"] == "0" and env["GCM_INTERACTIVE"] == "never"
    assert runner.kwargs["timeout"] == actions.PROBE_TIMEOUT and runner.kwargs["capture_output"] is True


# ---------------------------------------------------------------- 画面上怎么说


@pytest.mark.parametrize("kind", ["timeout", "network", "auth", "bad_url", "no_origin"])
def test_window_station_page_names_the_reason(qapp: QApplication, tmp_path: Path, kind: str) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACCEPTANCE_PENDING", "握手断线", 1)])
    window = gui_tests._window(qapp, root, db)
    window._on_probed(actions.OriginProbe(kind))
    qapp.processEvents()
    texts = gui_tests._texts(window.station)
    line = next(t for t in texts if t.startswith("网络 "))
    assert line == "网络 " + actions.PROBE_TEXT[kind]
    if kind != "timeout":
        assert "3 秒超时" not in line
    window.close()


def test_window_online_and_manual_offline_wording(qapp: QApplication, tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACCEPTANCE_PENDING", "握手断线", 1)])
    window = gui_tests._window(qapp, root, db)
    window._on_probed(actions.OriginProbe("online"))
    qapp.processEvents()
    assert "网络 在线" in gui_tests._texts(window.station)
    window.set_net("off")
    qapp.processEvents()
    assert any(t.startswith("网络 手动切到离线") for t in gui_tests._texts(window.station))
    window.close()


def test_station_vm_greys_push_buttons_with_the_specific_reason(tmp_path: Path) -> None:
    board = board_tests._board(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    home = vm.home_vm(board, board_tests.OFFSET, online=False, use_git=False)
    cards = home.hot + home.rest
    identity = {"source": "a", "effective": "a"}

    def reasons(station: Any) -> list[str]:
        return [reason for step in station.steps for _t, key, _e, reason in step.buttons if key in ("push", "open_pr")]

    specific = vm.station_vm(board, cards, False, identity, "manual/x", [], False, actions.PROBE_TEXT["auth"])
    assert reasons(specific) and all("认证失败" in r and r.startswith("离线") for r in reasons(specific))
    timeout = vm.station_vm(board, cards, False, identity, "manual/x", [], False, actions.PROBE_TEXT["timeout"])
    assert all(r == actions.PROBE_TEXT["timeout"] for r in reasons(timeout))
    plain = vm.station_vm(board, cards, False, identity, "manual/x", [], False)  # 没给原因：沿用旧说法
    assert all(r == "离线：读不到 origin" for r in reasons(plain))
    online = vm.station_vm(board, cards, True, identity, "manual/x", [], False, "在线")
    assert all("离线" not in r for r in reasons(online))


# ---------------------------------------------------------------- 抹掉网址里的账号口令（审计 545）


def _leaks(text: str, secret: str, size: int = 8) -> bool:
    return any(secret[i:i + size] in text for i in range(len(secret) - size + 1))


@pytest.mark.parametrize(
    "url",
    [
        "https://user:ghp_ABCDEFGH12345678@host.example/x.git",
        "https://user:p@ss@host.example/x.git",  # 口令里有原样的 @
        "https://user:p@ss:w@rd@host.example/x.git",
        "https://TOKENONLY12345678@host.example/x.git",
        "ssh://git:tok1234567@host.example:22/x.git",
    ],
)
def test_credentials_in_urls_are_masked_up_to_the_last_at_sign(url: str) -> None:
    masked = actions._scrub(f"fatal: unable to access '{url}': boom")
    assert "***@host.example" in masked
    for secret in ("ghp_ABCDEFGH12345678", "ss@host", "p@ss", "ss:w", "rd@", "TOKENONLY12345678", "tok1234567"):
        assert secret not in masked, (url, masked)


def test_urls_without_credentials_and_plain_at_signs_are_left_alone() -> None:
    text = "fatal: unable to access 'https://github.com/x/y.git/': mail me at a@b.example about https://host/path@x"
    assert actions._scrub(text) == text  # 没有 :// 后紧跟 user@ 的，原样不动
    assert actions._scrub("https://github.com/x/y.git") == "https://github.com/x/y.git"


def test_masking_happens_before_truncating_to_80_characters(tmp_path: Path) -> None:
    """令牌正好跨在第 80 个字之前：先截再抹会把令牌前半截留在页面上；必须先抹再截。"""
    secret = "ghp_" + "Zq8WxVn3Lk5Tm9RbHd2Fs7Yc4Jp6Ga1E"
    head = "fatal: odd failure at '" + "https://bob:"  # 用不会被归进已知类别的措辞，才会走到“其他”
    prefix = head.replace("fatal: ", "fatal: " + "z" * (70 - len(head)), 1)  # 补字，让网址头正好占满前 70 个字
    assert len(prefix) == 70
    line = prefix + secret + "@example.com/some/long/path/x.git/': boom"
    assert len(prefix) < 80 < len(prefix + secret)  # 第 80 个字落在令牌中间：先截后抹就会漏出令牌前半截
    probe = actions.probe_origin(tmp_path, runner=Runner(128, line + "\nsecond line\n"))
    assert probe.kind == "other" and not _leaks(probe.text, secret) and not _leaks(probe.detail, secret)
    assert "***@" in probe.text or "***" in probe.detail
    err = actions.probe_origin(tmp_path, runner=Runner(error=OSError(line)))
    assert not _leaks(err.text, secret) and not _leaks(err.detail, secret)


def test_repository_not_found_text_also_says_it_may_be_a_permission_problem() -> None:
    """GitHub 对没有访问权限的私有库也回 Repository not found，所以不能只说“地址不对”。"""
    text = actions.PROBE_TEXT["bad_url"]
    assert "地址不对" in text and "仓库不存在" in text and "没有访问权限" in text
