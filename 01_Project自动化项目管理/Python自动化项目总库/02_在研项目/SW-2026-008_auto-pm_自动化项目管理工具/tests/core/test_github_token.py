"""总控屏读 GitHub 复用本机 gh 登录（审计 538）：取令牌、令牌生命周期、只发 GET、只发给 api.github.com、令牌不泄漏。

不碰真凭据、不连外网：gh 用假运行器，GitHub 用假 fetch。
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import inspect
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from tests.core import test_github_collector as base

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import github_collector as gh  # noqa: E402
from cockpit_board import actions  # noqa: E402
from cockpit_board import app as app_module  # noqa: E402
from cockpit_board import viewmodel as vm  # noqa: E402

SENTINEL = "gho_" + "SentinelTokenDoNotLeak0123456789abcdef"[:36]
OTHER = "gho_" + "AnotherSentinelToken0123456789abcdef"[:36]
GH_EXE = str(Path(tempfile.gettempdir()) / "bin" / "gh")  # 任何系统上都是绝对路径（Windows 上 /usr/... 不算绝对）
API = base.API
REPO = base.REPO


# ---------------------------------------------------------------- 取令牌（gh auth token）


class FakeRun:
    """假的 subprocess.run：记下每次调用，按设定回话。"""

    def __init__(self, stdout: str = SENTINEL + "\n", rc: int = 0, error: Exception | None = None) -> None:
        self.stdout, self.rc, self.error = stdout, rc, error
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        self.calls.append((list(command), dict(kwargs)))
        if self.error is not None:
            raise self.error
        return subprocess.CompletedProcess(command, self.rc, self.stdout, "")


def _resolve(run: FakeRun, which: str | None = GH_EXE) -> str:
    return str(actions.resolve_github_token(runner=run, which=lambda _name: which))


def test_good_token_comes_back_and_the_command_is_pinned() -> None:
    run = FakeRun()
    assert _resolve(run) == SENTINEL
    command, kwargs = run.calls[0]
    assert command == [GH_EXE, "auth", "token", "--hostname", "github.com"]  # 绝对路径 + 固定命令，不拼用户输入
    assert kwargs["stdin"] == subprocess.DEVNULL and kwargs["timeout"] == actions.GH_TOKEN_TIMEOUT == 5
    assert kwargs["capture_output"] is True and not kwargs.get("shell")
    assert kwargs["env"]["GH_PROMPT_DISABLED"] == "1"  # 没登录时直接失败，不停下来等人输入
    assert kwargs["cwd"] in (str(Path.home()), tempfile.gettempdir())  # 不在仓库里跑


def test_no_gh_or_relative_path_means_no_token_and_nothing_is_run() -> None:
    for which in (None, "", "gh", "./gh", "bin/gh"):
        run = FakeRun()
        assert _resolve(run, which) == ""
        assert run.calls == []  # 解析不出绝对路径就不执行：当前目录里的同名程序不能顶替


@pytest.mark.parametrize(
    "run",
    [
        FakeRun(rc=1),
        FakeRun(error=FileNotFoundError("gh")),
        FakeRun(error=subprocess.TimeoutExpired("gh", 5)),
        FakeRun(stdout="gh: not logged in, run gh auth login\n"),
        FakeRun(stdout=""),
        FakeRun(stdout=SENTINEL + "\nsecond line"),  # 带换行的不是令牌：不能把它塞进请求头
        FakeRun(stdout="ghp_short"),
    ],
)
def test_every_failure_is_just_no_token(run: FakeRun) -> None:
    assert _resolve(run) == ""


def test_token_shapes() -> None:
    for good in (SENTINEL, "ghp_" + "a" * 36, "github_pat_" + "A1_" * 20, "0123456789abcdef" * 2 + "01234567"):
        assert gh.valid_token(good), good
    for bad in ("", "x", "ghp_" + "a" * 5, SENTINEL + " x", "Bearer " + SENTINEL, "gho_" + "a" * 36 + "\n"):
        assert not gh.valid_token(bad), bad


def test_resolver_never_goes_through_run_cli() -> None:
    """取令牌的子进程不能走 run_cli：run_cli 会把输出放进回执，令牌就进了界面。"""
    tree = ast.parse(textwrap.dedent(inspect.getsource(actions.resolve_github_token)))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not names & {"run_cli", "Receipt", "open_console"}


# ---------------------------------------------------------------- 令牌小仓库：内存里、线程安全、被拒就丢


def test_cache_asks_gh_only_once_even_from_many_threads() -> None:
    calls: list[int] = []

    def resolver() -> str:
        calls.append(1)
        return SENTINEL

    cache = actions.GithubTokenCache(resolver)
    results: list[str] = []
    threads = [threading.Thread(target=lambda: results.append(cache.get())) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [SENTINEL] * 12 and len(calls) == 1


def test_rejected_token_is_dropped_and_asked_again_but_only_a_bounded_number_of_times() -> None:
    answers = iter([SENTINEL, OTHER, "should-never-be-asked"])
    asked: list[int] = []

    def resolver() -> str:
        asked.append(1)
        return next(answers)

    cache = actions.GithubTokenCache(resolver)
    assert cache.get() == SENTINEL
    cache.rejected()
    assert cache.get() == OTHER and len(asked) == 2  # 被拒一次：丢掉，再问一次
    cache.rejected()
    assert cache.get() == "" and cache.get() == "" and len(asked) == 2  # 连续被拒到上限：不再问 gh，游客读
    cache.accepted()  # 成功一次，计数清零（但上面已经锁成游客，直到重启）
    assert cache.MAX_REJECTIONS == 2


def test_accepted_resets_the_streak() -> None:
    cache = actions.GithubTokenCache(lambda: SENTINEL)
    cache.get()
    cache.rejected()
    cache.get()
    cache.accepted()
    cache.rejected()  # 清零后又被拒一次，不到上限，仍会再问
    assert cache.get() == SENTINEL


def test_cache_repr_hides_the_token() -> None:
    cache = actions.GithubTokenCache(lambda: SENTINEL)
    cache.get()
    assert SENTINEL not in repr(cache) and SENTINEL not in str(cache)


# ---------------------------------------------------------------- 采集器：显式令牌、401 改游客、只发 api.github.com


def _collect(tmp_path: Path, fake: base.FakeGitHub, **kw: Any) -> Any:
    root = tmp_path / "repo" if (tmp_path / "repo").is_dir() else base._repo(tmp_path)
    return gh.collect(REPO, root, [root / "reviews"], tmp_path / "cache" / "github.json", base.NOW,
                      fetch=fake, env={}, **kw)


def test_explicit_token_is_used_without_touching_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    fake = base.FakeGitHub(base.routes())
    snap = _collect(tmp_path, fake, token=SENTINEL)
    assert snap.authenticated and all(h.get("Authorization") == f"Bearer {SENTINEL}" for _u, h in fake.calls)
    import os

    assert SENTINEL not in os.environ.values()  # 没有把令牌塞进进程环境


def test_explicit_empty_token_means_anonymous_even_if_env_has_one(tmp_path: Path) -> None:
    fake = base.FakeGitHub(base.routes())
    root = base._repo(tmp_path)
    snap = gh.collect(REPO, root, [root / "reviews"], None, base.NOW, fetch=fake, env={"GITHUB_TOKEN": OTHER}, token="")
    assert not snap.authenticated and all("Authorization" not in h for _u, h in fake.calls)


class RejectingGitHub(base.FakeGitHub):
    """带 Authorization 就回 401，游客读照常回。"""

    def __call__(self, url: str, headers: dict[str, str]) -> Any:
        if "Authorization" in headers:
            self.calls.append((url, dict(headers)))
            return 401, {}, b'{"message":"Bad credentials"}'
        return super().__call__(url, headers)


def test_rejected_token_falls_back_to_anonymous_in_the_same_collection(tmp_path: Path) -> None:
    fake = RejectingGitHub(base.routes())
    snap = _collect(tmp_path, fake, token=SENTINEL)
    assert snap.token_rejected and not snap.authenticated
    assert snap.state == "partial" and snap.fresh and len(snap.pulls) == 2  # 游客读成功，数据是新的
    assert any("登录凭据被 GitHub 拒绝" in e for e in snap.errors)
    authed = [u for u, h in fake.calls if "Authorization" in h]
    assert len(authed) == 1  # 带令牌的只试了一次，不循环
    assert all("Authorization" not in h for _u, h in fake.calls[1:])


def test_token_rejected_twice_stops_and_is_reported(tmp_path: Path) -> None:
    class AlwaysReject(base.FakeGitHub):
        def __call__(self, url: str, headers: dict[str, str]) -> Any:
            self.calls.append((url, dict(headers)))
            return 401, {}, b"{}"

    fake = AlwaysReject({})
    snap = _collect(tmp_path, fake, token=SENTINEL)
    assert snap.state == "auth" and snap.token_rejected and not snap.fresh
    assert len(fake.calls) == 2  # 带令牌一次 + 游客一次，到此为止


def test_api_refuses_every_address_that_is_not_api_github_com() -> None:
    seen: list[str] = []

    def fetch(url: str, headers: dict[str, str]) -> Any:
        seen.append(url)
        return 200, {}, b"[]"

    api = gh.Api(fetch, SENTINEL, {})
    for bad in ("https://evil.example/x", "http://api.github.com/x", "https://api.github.com.evil.example/x",
                "https://api.github.com@evil.example/x", "file:///etc/passwd", "ftp://api.github.com/x", "x"):
        with pytest.raises(gh.ApiError):
            api.get(bad)
    assert seen == []  # 一个字节都没发
    assert api.get("/repos/o/r/pulls") == [] and seen == [API.split("/repos")[0] + "/repos/o/r/pulls"]
    assert api.get("https://api.github.com/repos/o/r/pulls") == []


def test_urllib_fetch_itself_refuses_other_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gh._OPENER, "open", lambda *a, **k: pytest.fail("不该发请求"))
    with pytest.raises(gh.ApiError):
        gh.urllib_fetch("https://evil.example/x", {"Authorization": "Bearer x"})


def test_redirects_only_stay_on_api_github_com() -> None:
    handler = gh._ApiOnlyRedirects()
    request = urllib.request.Request(gh.API + "/a", headers={"Authorization": f"Bearer {SENTINEL}"}, method="GET")
    for target in ("https://evil.example/steal", "http://api.github.com/a", "https://github.com/login", "https://api.github.com.evil.example/"):
        assert handler.redirect_request(request, None, 302, "Found", {}, target) is None, target
    followed = handler.redirect_request(request, None, 302, "Found", {}, gh.API + "/b")
    assert followed is not None and followed.full_url == gh.API + "/b"


def test_only_get_at_the_lowest_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """urllib 的最底层（OpenerDirector.open）收到的永远是 GET、没有请求体。"""
    seen: list[tuple[str, object, str]] = []

    class Response:
        status = 200
        headers: dict[str, str] = {}

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_a: object) -> None:
            return None

        def read(self) -> bytes:
            return b"{}"

    def fake_open(request: urllib.request.Request, timeout: float | None = None) -> Response:
        seen.append((request.get_method(), request.data, request.full_url))
        return Response()

    monkeypatch.setattr(gh._OPENER, "open", fake_open)
    gh.urllib_fetch(gh.API + "/repos/o/r/pulls", {"Authorization": "Bearer x"})
    assert seen == [("GET", None, gh.API + "/repos/o/r/pulls")]


def test_source_scan_only_one_request_object_and_no_write_verbs() -> None:
    source = (SCRIPTS / "github_collector.py").read_text(encoding="utf-8")
    assert len(re.findall(r"urllib\.request\.Request\(", source)) == 1
    assert len(re.findall(r"\.open\(", source)) == 1 and "urlopen" not in source.replace("# noqa", "")
    tree = ast.parse(source)
    request_calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "Request"]
    assert len(request_calls) == 1 and not [k for k in request_calls[0].keywords if k.arg in ("data", "json")]
    assert ".add_data" not in source and "set_proxy" not in source
    assert re.findall(r"method\s*=\s*\"(\w+)\"", source) == ["GET"]
    assert "subprocess" not in source  # 起子进程只在 cockpit_board/actions.py


# ---------------------------------------------------------------- 令牌不泄漏


def _fresh_snapshot(tmp_path: Path) -> tuple[Any, Path]:
    fake = base.FakeGitHub(base.routes())
    snap = _collect(tmp_path, fake, token=SENTINEL)
    return snap, tmp_path / "cache" / "github.json"


def test_token_is_nowhere_in_snapshot_cache_or_reprs(tmp_path: Path) -> None:
    snap, cache = _fresh_snapshot(tmp_path)
    assert snap.authenticated
    assert SENTINEL not in json.dumps(dataclasses.asdict(snap), default=str, ensure_ascii=False)
    assert SENTINEL not in repr(snap) and SENTINEL not in cache.read_text(encoding="utf-8")
    api = gh.Api(base.FakeGitHub(base.routes()), SENTINEL, {})
    assert SENTINEL not in repr(api) and SENTINEL not in str(api) and "authenticated=True" in repr(api)
    github_vm = vm.github_vm(snap, base.NOW, base.OFFSET)
    assert SENTINEL not in repr(github_vm)


def test_token_is_not_in_options_repr_logs_or_the_crash_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    root = base._repo(tmp_path)
    cache = actions.GithubTokenCache(lambda: SENTINEL)
    options = argparse.Namespace(
        no_github=False, no_net=False, github_repo=REPO, root=root, reviews_dirs=[root / "reviews"],
        github_cache=tmp_path / "c.json", now=base.NOW, github_token_cache=cache,
    )

    def exploding_fetch(url: str, headers: dict[str, str]) -> Any:
        raise RuntimeError("读管道炸了")  # collect 只吞 GitHub 类异常；这种会一路抛出去，像真崩溃

    options.github_fetch = exploding_fetch
    with caplog.at_level(logging.DEBUG), pytest.raises(RuntimeError):
        app_module.load_github(options)
    assert cache.get() == SENTINEL  # 令牌确实取到了、用上了
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    try:
        app_module.load_github(options)
    except RuntimeError:
        app_module._crash_report()
    report = (tmp_path / "驾驶舱总控屏_启动错误.txt").read_text(encoding="utf-8")
    assert SENTINEL not in report and SENTINEL not in repr(options) and SENTINEL not in str(vars(options).keys())
    assert SENTINEL not in caplog.text


# ---------------------------------------------------------------- 接线：load_github


def _options(tmp_path: Path, cache: actions.GithubTokenCache | None, fake: base.FakeGitHub, **extra: Any) -> argparse.Namespace:
    root = base._repo(tmp_path)
    options = argparse.Namespace(
        no_github=False, no_net=False, github_repo=REPO, root=root, reviews_dirs=[root / "reviews"],
        github_cache=tmp_path / "c.json", now=datetime(2026, 10, 22, 12, 0, tzinfo=UTC), github_fetch=fake,
        github_token_cache=cache,
    )
    for key, value in extra.items():
        setattr(options, key, value)
    return options


def _counting(asked: list[int]) -> Callable[[], str]:
    def resolver() -> str:
        asked.append(1)
        return SENTINEL

    return resolver


def test_load_github_uses_the_cached_login_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    fake = base.FakeGitHub(base.routes())
    snap = app_module.load_github(_options(tmp_path, actions.GithubTokenCache(lambda: SENTINEL), fake))
    assert snap is not None and snap.authenticated
    assert all(h.get("Authorization") == f"Bearer {SENTINEL}" for _u, h in fake.calls)


def test_environment_token_wins_and_gh_is_not_asked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", OTHER)
    asked: list[int] = []
    cache = actions.GithubTokenCache(_counting(asked))
    fake = base.FakeGitHub(base.routes())
    app_module.load_github(_options(tmp_path, cache, fake))
    assert asked == [] and all(h.get("Authorization") == f"Bearer {OTHER}" for _u, h in fake.calls)


def test_offline_option_never_asks_gh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    asked: list[int] = []
    cache = actions.GithubTokenCache(_counting(asked))
    app_module.load_github(_options(tmp_path, cache, base.FakeGitHub(base.routes()), no_net=True))
    assert asked == []


def test_load_github_drops_a_rejected_token_and_asks_again_next_round(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    answers = iter([SENTINEL, OTHER])
    cache = actions.GithubTokenCache(lambda: next(answers))
    options = _options(tmp_path, cache, RejectingGitHub(base.routes()))
    first = app_module.load_github(options)
    assert first is not None and first.token_rejected
    good = base.FakeGitHub(base.routes())
    options.github_fetch = good
    second = app_module.load_github(options)
    assert second is not None and second.authenticated and not second.token_rejected
    assert all(h.get("Authorization") == f"Bearer {OTHER}" for _u, h in good.calls)  # 换了新令牌


# ---------------------------------------------------------------- 页面怎么说


def test_page_says_which_credentials_were_used_or_why_anonymous(tmp_path: Path) -> None:
    snap, _cache = _fresh_snapshot(tmp_path)
    notes = vm.github_vm(snap, base.NOW, base.OFFSET).notes
    assert any("已用 GitHub 登录凭据" in n for n in notes) and not any("没给令牌" in n for n in notes)
    root = base._repo(tmp_path / "anon")
    anonymous = gh.collect(REPO, root, [root / "reviews"], None, base.NOW, fetch=base.FakeGitHub(base.routes()), env={}, token="")
    notes = vm.github_vm(anonymous, base.NOW, base.OFFSET).notes
    assert any("没给令牌" in n and "gh auth login" in n for n in notes)


# ---------------------------------------------------------------- 找 gh：不能让当前目录里的同名程序顶替（审计 541）


def _touch(path: Path, executable: bool = True) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a real gh")
    path.chmod(0o755 if executable else 0o644)
    return str(path)


def test_find_on_path_windows_skips_cwd_relative_and_empty_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows 语义（注入 windows=True，Linux 也能跑）：当前目录、相对项、空项里的 gh.exe 一律不选。"""
    monkeypatch.chdir(tmp_path)  # 让相对项 "rel" 真的指到放了假 gh.exe 的 rel/ 目录
    cwd, real = tmp_path / "repo", tmp_path / "tools"
    _touch(cwd / "gh.exe")
    _touch(tmp_path / "rel" / "gh.exe")
    entries = ["", ".", "rel", str(cwd), f'"{cwd}"', str(tmp_path / "empty")]
    where = actions.find_on_path("gh", path=";".join(entries), windows=True, cwd=str(cwd))
    assert where is None  # 只有被跳过的项：宁可没找到，也不执行仓库里的程序
    chosen = _touch(real / "gh.exe")
    where = actions.find_on_path("gh", path=";".join([*entries, str(real)]), windows=True, cwd=str(cwd))
    assert where == chosen and os.path.isabs(where)


def test_find_on_path_windows_only_accepts_exe(tmp_path: Path) -> None:
    for suffix in (".bat", ".cmd", ".com", ".ps1", ""):
        _touch(tmp_path / "bin" / f"gh{suffix}")
    assert actions.find_on_path("gh", path=str(tmp_path / "bin"), windows=True, cwd=str(tmp_path / "elsewhere")) is None
    _touch(tmp_path / "bin" / "gh.exe")
    assert actions.find_on_path("gh", path=str(tmp_path / "bin"), windows=True, cwd=str(tmp_path / "elsewhere")) \
        == str(tmp_path / "bin" / "gh.exe")


@pytest.mark.skipif(os.name == "nt", reason="POSIX 语义：冒号分隔、看执行权限")
def test_find_on_path_posix_skips_empty_entry_and_needs_execute_bit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cwd = tmp_path / "repo"
    _touch(cwd / "gh")
    monkeypatch.chdir(cwd)
    assert shutil.which("gh", path=":/nonexistent") == "gh"  # 基线：标准库会把空项当当前目录
    assert actions.find_on_path("gh", path=":/nonexistent:.", cwd=str(cwd)) is None
    _touch(tmp_path / "plain" / "gh", executable=False)
    assert actions.find_on_path("gh", path=str(tmp_path / "plain"), cwd=str(cwd)) is None  # 没有执行权限不算
    good = _touch(tmp_path / "tools" / "gh")
    assert actions.find_on_path("gh", path=f"{tmp_path / 'plain'}:{tmp_path / 'tools'}", cwd=str(cwd)) == good


def test_the_token_resolver_defaults_to_our_own_lookup_not_the_standard_library_one() -> None:
    default = inspect.signature(actions.resolve_github_token).parameters["which"].default
    assert default is actions.find_on_path


def test_default_lookup_never_runs_a_gh_planted_in_the_current_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """用真实的默认查找（不注入）：cwd 里放假 gh，PATH 里没有真 gh，就必须是“没找到、没执行”。

    在 Windows 的 CI 上这是审计 541 要的那条：标准库 which 在那里默认先搜当前目录。
    """
    cwd, empty = tmp_path / "repo", tmp_path / "empty"
    empty.mkdir()
    _touch(cwd / ("gh.exe" if os.name == "nt" else "gh"))
    monkeypatch.chdir(cwd)
    monkeypatch.delenv("NoDefaultCurrentDirectoryInExePath", raising=False)
    monkeypatch.setenv("PATH", str(empty) + (os.pathsep if os.name != "nt" else ""))
    if os.name == "nt":
        assert shutil.which("gh") is not None  # 基线：标准库会选中当前目录里的假 gh
    run = FakeRun()
    assert actions.resolve_github_token(runner=run) == ""
    assert run.calls == []


# ---------------------------------------------------------------- 环境变量里的令牌也验形状；连续被拒的提示（审计 541）


BAD_ENV_TOKEN = "my token with spaces\nsecond line"


def test_bad_shaped_environment_token_is_ignored_with_a_reason(tmp_path: Path) -> None:
    fake = base.FakeGitHub(base.routes())
    root = base._repo(tmp_path)
    snap = gh.collect(REPO, root, [root / "reviews"], None, base.NOW, fetch=fake, env={"GITHUB_TOKEN": BAD_ENV_TOKEN})
    assert not snap.authenticated and snap.fresh
    assert all("Authorization" not in h for _u, h in fake.calls)  # 不合格的串根本不发出去
    assert "GITHUB_TOKEN" in snap.env_token_problem and "已忽略" in snap.env_token_problem
    assert "spaces" not in snap.env_token_problem and "spaces" not in repr(snap)  # 原因里不带令牌本身
    notes = vm.github_vm(snap, base.NOW, base.OFFSET).notes
    assert any(snap.env_token_problem == n for n in notes)


def test_well_shaped_environment_token_is_still_used_even_with_whitespace(tmp_path: Path) -> None:
    fake = base.FakeGitHub(base.routes())
    root = base._repo(tmp_path)
    snap = gh.collect(REPO, root, [root / "reviews"], None, base.NOW, fetch=fake, env={"GH_TOKEN": f"  {OTHER}\n"})
    assert snap.authenticated and snap.env_token_problem == ""
    assert all(h.get("Authorization") == f"Bearer {OTHER}" for _u, h in fake.calls)


def test_offline_with_bad_environment_token_still_says_why(tmp_path: Path) -> None:
    root = base._repo(tmp_path)
    snap = gh.collect(REPO, root, [root / "reviews"], None, base.NOW, offline=True, env={"GITHUB_TOKEN": BAD_ENV_TOKEN})
    assert not snap.authenticated and snap.env_token_problem


def test_bad_environment_token_lets_the_local_login_take_over(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", BAD_ENV_TOKEN)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    fake = base.FakeGitHub(base.routes())
    snap = app_module.load_github(_options(tmp_path, actions.GithubTokenCache(lambda: SENTINEL), fake))
    assert snap is not None and snap.authenticated and "GITHUB_TOKEN" in snap.env_token_problem
    assert all(h.get("Authorization") == f"Bearer {SENTINEL}" for _u, h in fake.calls)


def test_page_says_login_refused_only_after_the_second_rejection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    cache = actions.GithubTokenCache(lambda: SENTINEL)
    options = _options(tmp_path, cache, RejectingGitHub(base.routes()))
    wording = "登录被拒，暂用游客读取，重启后重试"

    def notes() -> tuple[list[str], Any]:
        snap = app_module.load_github(options)
        assert snap is not None
        return vm.github_vm(snap, base.NOW, base.OFFSET).notes, snap

    first, snap1 = notes()
    assert not snap1.login_refused and not any(wording in n for n in first)  # 被拒一次：还会再试
    second, snap2 = notes()
    assert snap2.login_refused and any(wording in n for n in second)  # 被拒两次：不再问 gh
    assert not any("没给令牌" in n for n in second)
    third, snap3 = notes()  # 之后每一轮都是游客读，仍然这句话
    assert snap3.login_refused and not snap3.authenticated and any(wording in n for n in third)
    assert SENTINEL not in json.dumps(dataclasses.asdict(snap3), default=str, ensure_ascii=False)


def test_login_refused_wording_is_not_shown_when_there_is_simply_no_login(tmp_path: Path) -> None:
    root = base._repo(tmp_path)
    snap = gh.collect(REPO, root, [root / "reviews"], None, base.NOW, fetch=base.FakeGitHub(base.routes()), env={}, token="")
    notes = vm.github_vm(snap, base.NOW, base.OFFSET).notes
    assert any("没给令牌" in n for n in notes) and not any("登录被拒" in n for n in notes)
