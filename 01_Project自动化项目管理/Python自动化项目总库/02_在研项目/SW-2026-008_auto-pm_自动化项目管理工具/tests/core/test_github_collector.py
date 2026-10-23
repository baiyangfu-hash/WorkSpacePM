"""总控屏 GitHub 采集（scripts/github_collector.py）与它在视图模型里的显示。不连外网：全部用假的 fetch。

重点三种读不到的情况（协调者 10-22 要求）：离线、限流、部分失败；规矩是“没检查显示没检查 / 未知，不显示 0、不显示绿”。
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from tests.core import test_pm_dashboard as base

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import github_collector as gh  # noqa: E402
from cockpit_board import policy  # noqa: E402
from cockpit_board import viewmodel as vm  # noqa: E402

pd = base.pd
NOW = base.NOW
OFFSET = timezone(timedelta(hours=-7))
REPO = "baiyangfu-hash/WorkSpacePM"
API = gh.API + f"/repos/{REPO}"
TOKEN = "ghp_test_token_do_not_store"
SHA1 = "1111111aaaaaaa1111111aaaaaaa1111111aaaaa"
SHA2 = "2222222bbbbbbb2222222bbbbbbb2222222bbbbb"
PLC_FILE = "0100_PLC自动化/DJ-2026-009_某线/03_执行/OB1.scl"
SW8_FILE = (
    "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/scripts/a.py"
)
SW8_CI = """name: sw008-ci
on:
  push:
    paths:
      - "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/**"
  pull_request:
    branches: [main]
    paths:
      - "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/**"
      - ".github/workflows/sw008-ci.yml"
  workflow_dispatch:
"""
PLC_CI = """name: plc-ci
on:
  pull_request:
    branches: [main]
    paths:
      - "0100_PLC自动化/**"
  push:
    branches: [main]
"""
NIGHTLY = """name: nightly
on:
  schedule:
    - cron: "0 3 * * *"
"""


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "sw008-ci.yml").write_text(SW8_CI, encoding="utf-8")
    (workflows / "plc-ci.yml").write_text(PLC_CI, encoding="utf-8")
    (workflows / "nightly.yml").write_text(NIGHTLY, encoding="utf-8")
    reviews = root / "reviews"
    reviews.mkdir()
    (reviews / "79_PR2_某审计_20261022.md").write_text(
        "# 审计 79：PR #2\n\n- PR：#2，分支 claude/x，头 2222222b\n\n## 结论\n\n**首审不通过，只差一条测试。** 不过别的都好。\n\n"
        "## 复核 1（头 2222222b）：通过\n\n补上了。\n",
        encoding="utf-8",
    )
    (reviews / "80_预做分支预审_20261022.md").write_text(
        "# 审计 80：预做分支\n\n- 分支：claude/plc-safety，头 0000000c（旧）\n\n## 结论\n\n**预审通过。** 顺带提到 PR #2。\n",
        encoding="utf-8",
    )
    return root


def _run(name: str, sha: str, conclusion: str | None, number: int = 1) -> dict:
    return {
        "name": name, "head_sha": sha, "status": "completed" if conclusion else "in_progress",
        "conclusion": conclusion, "run_number": number, "created_at": f"2026-10-22T10:0{number}:00Z",
        "html_url": f"https://github.com/{REPO}/actions/runs/{number}",
    }


def _signature(sha: str, login: str = "baiyangfu-hash", uid: int = 246858089, app: bool = False) -> dict:
    return {"body": f"仿真过了\n安全签字 {sha[:8]}", "user": {"login": login, "id": uid},
            "performed_via_github_app": {"slug": "bot"} if app else None, "html_url": "c"}


def routes(**override: object) -> dict[str, object]:
    """两个开着的 PR：#1 改 PLC（DJ-2026-009），描述“安全回路: 是”、没签；#2 改 SW-008，sw008-ci 红。"""
    table: dict[str, object] = {
        f"{API}/pulls?state=open&per_page=100": [
            {"number": 1, "title": "OB1 加急停复位", "html_url": "u1", "user": {"login": "baiyangfu-hash"},
             "head": {"sha": SHA1, "ref": "claude/plc-safety"}, "draft": False, "updated_at": "2026-10-22T09:00:00Z",
             "body": "说明\n\n安全回路: 是\n"},
            {"number": 2, "title": "看板改字", "html_url": "u2", "user": {"login": "baiyangfu-hash"},
             "head": {"sha": SHA2, "ref": "claude/x"}, "draft": False, "updated_at": "2026-10-22T08:00:00Z",
             "body": "```\n安全回路: 是\n```\n只是示例"},
        ],
        f"{API}/actions/runs?branch=main&event=push&per_page=50": {
            "workflow_runs": [_run("sw008-ci", "m", "success", 3), _run("sw008-ci", "m", "failure", 2),
                              _run("plc-ci", "m", "success", 1)]},
        f"{API}/pulls/1/files?per_page=100": [{"filename": PLC_FILE}],
        f"{API}/actions/runs?head_sha={SHA1}&per_page=50": {"workflow_runs": [_run("plc-ci", SHA1, "success")]},
        f"{API}/issues/1/comments?per_page=100": [_signature(SHA2), _signature(SHA1, login="someone", uid=1),
                                                  _signature(SHA1, app=True)],
        f"{API}/pulls/2/files?per_page=100": [{"filename": SW8_FILE}],
        f"{API}/actions/runs?head_sha={SHA2}&per_page=50": {"workflow_runs": [_run("sw008-ci", SHA2, "failure")]},
        f"{API}/issues/2/comments?per_page=100": [],
    }
    table.update(override)
    return table


class FakeGitHub:
    """按 URL 回 JSON；值可以是 (状态码, 头, 正文) 或一个异常。记下每次请求的 URL 和头。"""

    def __init__(self, table: dict[str, object]) -> None:
        self.table = table
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: dict[str, str]):  # noqa: ANN204
        self.calls.append((url, dict(headers)))
        value = self.table.get(url, (404, {}, b"{}"))
        if isinstance(value, Exception):
            raise value
        if isinstance(value, tuple):
            return value
        etag = f'W/"{abs(hash(url))}"'
        if headers.get("If-None-Match") == etag:
            return 304, {"ETag": etag}, b""
        return 200, {"ETag": etag}, json.dumps(value).encode("utf-8")


def _collect(tmp_path: Path, fake: FakeGitHub | None, when: datetime = NOW, token: bool = True, **kw: object):
    root = tmp_path / "repo" if (tmp_path / "repo").is_dir() else _repo(tmp_path)
    env = {"GITHUB_TOKEN": TOKEN} if token else {}
    return gh.collect(REPO, root, [root / "reviews"], tmp_path / "cache" / "github.json", when,
                      fetch=fake, env=env, **kw)


def _home(tmp_path: Path, snapshot: gh.Snapshot | None, online: bool | None = True) -> vm.HomeVM:
    root, db = base._workspace(tmp_path / "ws", [])
    board = pd.build_board(root, db, NOW, use_git=False, use_legacy=False)
    return vm.home_vm(board, OFFSET, online, False, snapshot)


def _no_green(github: vm.GithubVM) -> None:
    cells = [cell for row in github.rows for cell in (row.gate, row.safety, row.audit, *(c for _n, c in row.ci))]
    cells += [c for _n, c in github.main_ci]
    assert all(cell.sev == "na" for cell in cells), [c for c in cells if c.sev != "na"]
    assert all(cell.text in ("未知", "没审计记录") or "通过" in cell.text or "看不出" in cell.text for cell in cells)


# ---------------------------------------------------------------- 全读到


def test_full_read_pulls_ci_safety_audit(tmp_path: Path) -> None:
    fake = FakeGitHub(routes())
    snap = _collect(tmp_path, fake)
    assert snap.state == "ok" and snap.fresh and snap.fetched_at == NOW and snap.authenticated
    one, two = snap.pulls
    assert one.projects == ["DJ-2026-009"] and one.plc
    assert {c.workflow: c.state for c in one.ci} == {"plc-ci": "pass", "sw008-ci": "na"}  # nightly 不是 PR 触发
    assert one.gate == "pass"
    # 签了旧头、不是指定签字人、经由 App 的都不算
    assert one.safety.state == "waiting" and "要重签" in one.safety.detail
    assert two.projects == ["SW-2026-008"] and two.gate == "fail"
    assert two.safety.state == "na"  # 代码块里的“安全回路: 是”是示例，不算声明
    # 审计：复核结论盖过首审；按 PR 号对上；80 正文里顺带提到 PR #2 不算
    assert two.audit is not None and two.audit.number == 79 and two.audit.verdict == "pass" and not two.audit_stale
    assert one.audit is not None and one.audit.number == 80 and one.audit_stale  # 审的是旧头
    assert {c.workflow: c.state for c in snap.main_ci} == {"plc-ci": "pass", "sw008-ci": "pass"}  # 取最新一次

    home = _home(tmp_path, snap)
    checks = {c.key: c for c in home.checks}
    assert checks["gate_red"].state == "number" and checks["gate_red"].value == 1
    assert checks["safety_unsigned"].state == "number" and checks["safety_unsigned"].value == 1
    assert any(d.ask == "PR #1 等你安全签字" and d.reply.endswith(SHA1[:8]) for d in home.decisions)
    assert home.github is not None and home.github.as_of.startswith("数据截至 ")
    gates = {r.number: r.gate for r in home.github.rows}
    assert gates[2].text == "红" and gates[2].sev == "block" and gates[1].sev == "ok"
    audits = {r.number: r.audit for r in home.github.rows}
    assert audits[1].sev == "risk" and "旧头" in audits[1].text


def test_cache_has_timestamp_and_no_token_and_etag_is_reused(tmp_path: Path) -> None:
    fake = FakeGitHub(routes())
    _collect(tmp_path, fake)
    cache = tmp_path / "cache" / "github.json"
    text = cache.read_text(encoding="utf-8")
    assert TOKEN not in text and "Authorization" not in text
    raw = json.loads(text)
    assert raw["snapshot"]["fetched_at"] == NOW.isoformat()
    assert all(h.get("Authorization") == f"Bearer {TOKEN}" for _u, h in fake.calls)
    # 第二轮：全部带 If-None-Match，GitHub 回 304，结果和第一轮一样，数据截至更新为这一轮
    later = NOW + timedelta(minutes=5)
    fake2 = FakeGitHub(routes())
    snap = _collect(tmp_path, fake2, when=later)
    assert all("If-None-Match" in h for _u, h in fake2.calls)
    assert snap.state == "ok" and snap.fetched_at == later and [p.gate for p in snap.pulls] == ["pass", "fail"]


def test_only_get_requests_in_source() -> None:
    source = (SCRIPTS / "github_collector.py").read_text(encoding="utf-8")
    assert re.findall(r"method\s*=\s*\"(\w+)\"", source) == ["GET"]
    for verb in ("POST", "PATCH", "PUT", "DELETE"):
        assert f'"{verb}"' not in source, verb
    assert "subprocess" not in source  # 仓库名从 .git/config 读，不起 git


# ---------------------------------------------------------------- 离线


def test_offline_without_cache_shows_unknown_never_zero(tmp_path: Path) -> None:
    fake = FakeGitHub({f"{API}/pulls?state=open&per_page=100": gh.OfflineError("Name or service not known")})
    snap = _collect(tmp_path, fake)
    assert snap.state == "offline" and not snap.fresh and snap.fetched_at is None and snap.pulls == []
    assert snap.audits  # 审计是本机文件，断网照读
    home = _home(tmp_path, snap, online=False)
    checks = {c.key: c for c in home.checks}
    for key in ("gate_red", "safety_unsigned"):
        assert checks[key].state == "offline" and checks[key].text == "断网未知" and checks[key].sev == "na"
    assert home.github is not None and home.github.as_of == "数据截至：从没读到过"
    assert "断网" in home.github.headline
    assert not any("PR #" in d.ask for d in home.decisions)


def test_offline_with_cache_keeps_old_rows_but_all_unknown(tmp_path: Path) -> None:
    _collect(tmp_path, FakeGitHub(routes()))
    later = NOW + timedelta(hours=2)
    snap = _collect(tmp_path, FakeGitHub({f"{API}/pulls?state=open&per_page=100": gh.OfflineError("timed out")}), when=later)
    assert snap.state == "offline" and snap.from_cache and snap.fetched_at == NOW and snap.checked_at == later
    assert [p.number for p in snap.pulls] == [1, 2]
    home = _home(tmp_path, snap, online=None)
    github = home.github
    assert github is not None and not github.fresh
    _no_green(github)  # 旧的“过”也不许显示成绿
    assert "2 小时前" in github.as_of and "旧数据" in github.headline
    assert all(r.note.startswith("上次读到") for r in github.rows)
    checks = {c.key: c for c in home.checks}
    assert checks["gate_red"].text in policy.UNCHECKED_TEXTS and checks["gate_red"].sev == "na"
    assert not any("PR #" in d.ask for d in home.decisions)  # 旧数据不催你签字
    # 项目页证据：门禁、安全签字是“未知”，不是过
    project = next(c for c in home.hot + home.rest if c.project_id == "DJ-2026-101")
    assert project.coverage.github is False


def test_no_net_option_reads_cache_only(tmp_path: Path) -> None:
    _collect(tmp_path, FakeGitHub(routes()))
    fake = FakeGitHub(routes())
    snap = _collect(tmp_path, fake, offline=True)
    assert fake.calls == [] and snap.state == "offline" and snap.from_cache


def test_corrupt_cache_is_ignored(tmp_path: Path) -> None:
    cache = tmp_path / "cache" / "github.json"
    cache.parent.mkdir(parents=True)
    cache.write_text("{不是 JSON", encoding="utf-8")
    snap = _collect(tmp_path, FakeGitHub({f"{API}/pulls?state=open&per_page=100": gh.OfflineError("x")}))
    assert snap.state == "offline" and not snap.from_cache and snap.pulls == []


# ---------------------------------------------------------------- 限流


def test_rate_limited_on_first_call(tmp_path: Path) -> None:
    reset = int((NOW + timedelta(minutes=30)).timestamp())
    limited = (403, {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reset)}, b'{"message":"API rate limit exceeded"}')
    fake = FakeGitHub({f"{API}/pulls?state=open&per_page=100": limited})
    snap = _collect(tmp_path, fake, token=False)
    assert snap.state == "rate_limited" and snap.reset_at == datetime.fromtimestamp(reset, UTC)
    assert len(fake.calls) == 1 and "Authorization" not in fake.calls[0][1]
    home = _home(tmp_path, snap)
    assert home.github is not None and "恢复" in home.github.headline
    assert any("没给令牌" in n for n in home.github.notes)
    checks = {c.key: c for c in home.checks}
    assert checks["gate_red"].state == "unchecked" and checks["safety_unsigned"].state == "unchecked"


def test_rate_limited_half_way_stops_calling_and_marks_rest_unknown(tmp_path: Path) -> None:
    limited = (429, {"Retry-After": "60"}, b"{}")
    fake = FakeGitHub(routes(**{f"{API}/actions/runs?head_sha={SHA1}&per_page=50": limited}))
    snap = _collect(tmp_path, fake)
    assert snap.state == "partial" and snap.fresh
    called = [u for u, _h in fake.calls]
    assert called[-1].endswith(f"head_sha={SHA1}&per_page=50")  # 限流之后一个请求都不再发
    one, two = snap.pulls
    assert one.gate == "unknown" and one.safety.state == "unknown"
    assert two.gate == "unknown" and two.projects == []
    assert any("限流" in e for e in snap.errors)
    home = _home(tmp_path, snap)
    checks = {c.key: c for c in home.checks}
    # 一个红的都没读到，但有没读全的：不许说 0
    assert checks["gate_red"].state == "unchecked" and checks["gate_red"].text == "没检查"
    assert checks["safety_unsigned"].state == "unchecked"
    rows = {r.number: r for r in home.github.rows}  # type: ignore[union-attr]
    assert rows[2].gate.text == "未知" and rows[2].gate.sev == "na" and rows[2].projects == ["未知"]


# ---------------------------------------------------------------- 部分失败


def test_partial_failure_only_marks_the_failed_piece(tmp_path: Path) -> None:
    fake = FakeGitHub(routes(**{
        f"{API}/actions/runs?head_sha={SHA1}&per_page=50": (500, {}, b"oops"),
        f"{API}/actions/runs?branch=main&event=push&per_page=50": gh.OfflineError("reset"),
    }))
    snap = _collect(tmp_path, fake)
    assert snap.state == "partial" and snap.fresh
    one, two = snap.pulls
    assert {c.workflow: c.state for c in one.ci} == {"plc-ci": "unknown", "sw008-ci": "na"}
    assert one.gate == "unknown" and one.errors and "PR #1 CI" in one.errors[0]
    assert one.safety.state == "waiting"  # 评论读到了，照常判
    assert two.gate == "fail" and not two.errors
    assert all(c.state == "unknown" for c in snap.main_ci)
    home = _home(tmp_path, snap)
    checks = {c.key: c for c in home.checks}
    assert checks["gate_red"].state == "number" and checks["gate_red"].value == 1
    assert "1 个没读全" in checks["gate_red"].note
    rows = {r.number: r for r in home.github.rows}  # type: ignore[union-attr]
    assert rows[1].gate.text == "未知" and rows[1].gate.sev == "na" and "PR #1 CI" in rows[1].note
    assert all(cell.text == "未知" and cell.sev == "na" for _n, cell in home.github.main_ci)  # type: ignore[union-attr]


def test_files_unread_means_ci_and_safety_unknown_not_not_applicable(tmp_path: Path) -> None:
    fake = FakeGitHub(routes(**{f"{API}/pulls/2/files?per_page=100": (502, {}, b"")}))
    snap = _collect(tmp_path, fake)
    two = snap.pulls[1]
    assert all(c.state == "unknown" for c in two.ci) and two.gate == "unknown"
    assert two.safety.state == "unknown"


def test_zero_red_with_not_run_is_not_green(tmp_path: Path) -> None:
    table = routes(**{f"{API}/actions/runs?head_sha={SHA2}&per_page=50": {"workflow_runs": []}})
    snap = _collect(tmp_path, FakeGitHub(table))
    assert snap.pulls[1].gate == "notrun"
    gate = next(c for c in _home(tmp_path, snap).checks if c.key == "gate_red")
    assert gate.value == 0 and gate.sev == "na" and "没跑 1 个" in gate.note


def test_unauthorized_token(tmp_path: Path) -> None:
    fake = FakeGitHub({f"{API}/pulls?state=open&per_page=100": (401, {}, b'{"message":"Bad credentials"}')})
    snap = _collect(tmp_path, fake)
    assert snap.state == "auth" and not snap.fresh
    assert "令牌" in vm.github_vm(snap, NOW, OFFSET).headline


def test_disabled_collector_keeps_unchecked(tmp_path: Path) -> None:
    home = _home(tmp_path, None, online=True)
    checks = {c.key: c for c in home.checks}
    assert checks["gate_red"].text == "没检查" and checks["safety_unsigned"].text == "没检查"
    assert home.github is not None and home.github.state == "disabled" and home.github.rows == []


# ---------------------------------------------------------------- 本地解析


def test_workflow_paths_and_project_mapping(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    flows = gh.read_workflows(root)
    assert set(flows) == {"sw008-ci", "plc-ci"}
    assert gh.expected_workflows([PLC_FILE], flows) == {"plc-ci"}
    assert gh.expected_workflows([".github/workflows/sw008-ci.yml"], flows) == {"sw008-ci"}
    assert gh.expected_workflows(["README.md"], flows) == set()
    assert gh.projects_of([PLC_FILE, SW8_FILE, "reviews/x.md"]) == ["DJ-2026-009", "SW-2026-008", gh.SHARED]
    assert gh.read_workflows(tmp_path / "nowhere") == gh.DEFAULT_WORKFLOWS


def test_repo_from_git_config(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text(
        '[core]\n\tbare = false\n[remote "origin"]\n\turl = http://proxy@127.0.0.1:1/git/acme/Line-01\n'
        '[remote "upstream"]\n\turl = git@github.com:x/y.git\n', encoding="utf-8")
    assert gh.repo_from_git_config(tmp_path) == gh.DEFAULT_REPO  # origin 不是 github.com：用默认
    (tmp_path / ".git" / "config").write_text('[remote "origin"]\n\turl = git@github.com:acme/Line-01.git\n', encoding="utf-8")
    assert gh.repo_from_git_config(tmp_path) == "acme/Line-01"


def test_audit_verdicts(tmp_path: Path) -> None:
    cases = {
        "1_a.md": ("## 结论：不过\n\n三条绕过。", "fail"),
        "2_a.md": ("## 结论\n\n**有条件通过：改两句话再合。**", "conditional"),
        "3_a.md": ("## 结论\n\n**同意合并。** 不过有两处措辞。", "pass"),
        "4_a.md": ("## 结论\n\n**过。** 存储层扎实。", "pass"),
        "5_a.md": ("## 结论\n\n1. **只有卡 177 是代码缺陷。**", "unknown"),
        "6_a.md": ("## 结论\n\n**首审不通过。**\n\n## 复核 1（头 abcdef12）：通过\n", "pass"),
        "7_a.md": ("## 结论\n\n**通过。**\n\n## 复核 1（头 abcdef12）：不通过\n", "fail"),
        "notes.md": ("## 结论\n\n通过", None),
    }
    for name, (body, _want) in cases.items():
        (tmp_path / name).write_text("# 审计\n\n" + body, encoding="utf-8")
    found = {a.file: a for a in gh.read_audits([tmp_path, tmp_path / "missing"])}
    for name, (_body, want) in cases.items():
        if want is None:
            assert name not in found
        else:
            assert found[name].verdict == want, name
    assert found["6_a.md"].head == "abcdef12"


def test_project_page_keeps_pr_rows_next_to_card_columns(tmp_path: Path) -> None:
    """项目页按栏排卡时不能把 PR 行冲掉（Codex 评审 #52）：有在干和刚关的卡，PR #2 仍要出现在证据和 PR 列表里。"""
    snap = _collect(tmp_path, FakeGitHub(routes()))
    root, db = base._workspace(
        tmp_path / "ws", [("SW-2026-008", "ACTIVE", "工具卡", 0.1), ("SW-2026-008", "CLOSED", "刚关的", 1)]
    )
    board = pd.build_board(root, db, NOW, use_git=False, use_legacy=False)
    home = vm.home_vm(board, OFFSET, True, False, snap)
    card = next(c for c in home.hot + home.rest if c.project_id == "SW-2026-008")
    page = vm.project_vm(board, card, OFFSET, True, home.github)
    assert [r.number for r in page.prs] == [2]
    gate = next(e for e in page.evidence if e.title == "门禁")
    assert gate.detail.startswith("#2 ") and gate.state == "block"
    columns = {c.name: c.cards for c in page.columns}
    assert [r[1] for r in columns["在干"]] == ["工具卡"] and [r[1] for r in columns["已关"]] == ["刚关的"]
