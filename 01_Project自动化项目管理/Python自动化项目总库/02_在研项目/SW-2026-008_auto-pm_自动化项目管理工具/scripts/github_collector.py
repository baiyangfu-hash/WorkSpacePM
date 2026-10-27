"""总控屏的 GitHub 采集（只读）——数据层，和 pm_dashboard.py 并列；cockpit_board 包本身不碰网络。

采什么：
    - 开着的 PR：改到哪些项目（按路径里的项目编号）、头提交、作者。
    - 每个 PR 的 CI：按 .github/workflows/*.yml 的 pull_request 路径过滤推出“应该跑哪几个”，
      再和 GitHub Actions 上这个头提交实际跑的比（sw008-ci、plc-ci，以后合进来的 safety-gate 自动算上）。
    - main 上每个工作流最近一次的结论。
    - PR 描述里的“安全回路: 是/否”、PR 评论里的“安全签字 <头提交号>”（规则照抄 reviews/tools/safety_zone_check.py，
      这里只显示，不当裁判；裁判是 safety-gate）。
    - 审计结论：读 reviews/ 目录（仓库里的 + 可另给目录，例如共享文件夹的 reviews/）里 “编号_*.md” 的结论段。

只读保证：
    - 只发 GET，没有任何写 GitHub 的请求；令牌只从环境变量 GITHUB_TOKEN / GH_TOKEN 读，不写进缓存、不打印。
    - 用 ETag 条件请求，内容没变时 GitHub 回 304，用缓存里的正文（有令牌时 304 不占限额）。
    - 唯一写的文件是本机缓存（用户缓存目录下一个 JSON，不在工作空间里），带“数据截至”时间戳。

读不到怎么办（用户 10-22 18:21 定：没检查显示没检查，不显示 0、不显示绿）：
    - 断网 → state = offline；限流 → rate_limited；令牌无效 → auth；其他 → error。
      此时若有缓存，带上缓存里的旧数据并标 from_cache，画面一律按“未知”显示，旧值只作小字参考。
    - 单个 PR 的某一项读失败 → 只那一项标 unknown，整份 state = partial，其余照常。
    - 限流发生在半路 → 后面的请求不再发，没读到的全标 unknown。
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from fnmatch import fnmatchcase
from pathlib import Path

API = "https://api.github.com"
DEFAULT_REPO = "baiyangfu-hash/WorkSpacePM"
TIMEOUT = 8
PER_PAGE = 100
CACHE_VERSION = 1
TOKEN_ENV = ("GITHUB_TOKEN", "GH_TOKEN")

PROJECT_SEGMENT = re.compile(r"^((?:DJ|SW|SYS)-\d{4}-\d{3})(?:_|$)")
SHARED = "仓库公共"
PLC_ROOT = "0100_PLC自动化/"

# 读不到工作流文件时的兜底（和 main 上 .github/workflows 一致，2026-10-22）。
DEFAULT_WORKFLOWS: dict[str, tuple[str, ...] | None] = {
    "sw008-ci": (
        "01_Project自动化项目管理/Python自动化项目总库/02_在研项目/SW-2026-008_auto-pm_自动化项目管理工具/**",
        "00_Infrastructure/auto_pm/environment/**",
        ".github/workflows/sw008-ci.yml",
    ),
    "plc-ci": (
        "0100_PLC自动化/**",
        ".github/workflows/plc-ci.yml",
        "reviews/tools/plc_ci.py",
        "reviews/tools/test_plc_ci.py",
    ),
}

# 安全签字规则照抄 reviews/tools/safety_zone_check.py（claude/safety-signoff-check-v2 058e21dc）。
SIGNERS = {"baiyangfu-hash": 246858089}
PLAN_LINE = re.compile(r"^\s*(?:\*\*)?(?:④\s*)?(?:是否涉及)?安全回路(?:\*\*)?\s*[:：]\s*(.*?)\s*$")
PLAN_CHOICES = ("是", "否")
SIGN_LINE = re.compile(r"^\s*安全签字\s*[:：]?\s*`?([0-9a-fA-F]{7,40})`?(?:\s.*|[，。；：！、）】」』,;.!)\]].*)?$")

AUDIT_FILE = re.compile(r"^(\d+)_.*\.md$")
AUDIT_PR_LINE = re.compile(r"^\s*(?:#\s.*?|-\s*(?:PR|对象)\s*[：:]\s*)PR\s*#?\s*(\d+)|^\s*-\s*PR\s*[：:]\s*#?\s*(\d+)")
AUDIT_HEAD = re.compile(r"头(?:部)?\s*[：:]?\s*`?([0-9a-f]{7,40})`?")
AUDIT_BRANCH = re.compile(r"分支\s*[：:]?\s*`?((?:claude|codex|manual|feature|fix)/[\w./-]+?)`?(?=[\s，,（(；;]|$)")
AUDIT_HEADING = re.compile(r"^##\s*((?:结论|复核).*)$")


class OfflineError(Exception):
    """连不上 GitHub（断网、DNS、超时、代理拒绝）。"""


class RateLimitedError(Exception):
    def __init__(self, reset_at: datetime | None) -> None:
        super().__init__("GitHub 限流")
        self.reset_at = reset_at


class AuthFailedError(Exception):
    """令牌无效或没权限（401；私有仓库没令牌时 404 也算）。"""


class ApiError(Exception):
    pass


# ---------------------------------------------------------------- 数据


@dataclass(frozen=True)
class CiState:
    workflow: str
    state: str  # pass / fail / running / notrun / na / unknown
    detail: str = ""
    url: str = ""


@dataclass(frozen=True)
class Safety:
    state: str  # signed / waiting / declared_no / undeclared / na / unknown
    plan: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class Audit:
    number: int
    file: str
    verdict: str  # pass / fail / conditional / unknown
    summary: str
    pr: int | None = None
    branch: str = ""
    head: str = ""


@dataclass
class PullInfo:
    number: int
    title: str
    url: str
    author: str
    head_sha: str
    head_ref: str
    draft: bool
    updated_at: str
    projects: list[str] = field(default_factory=list)
    plc: bool = False
    ci: list[CiState] = field(default_factory=list)
    safety: Safety = field(default_factory=lambda: Safety("unknown"))
    audit: Audit | None = None
    audit_stale: bool = False  # 审计时的头提交和现在的头不是同一个
    errors: list[str] = field(default_factory=list)

    @property
    def gate(self) -> str:
        """这个 PR 的门禁合起来看：fail / unknown / running / pass / notrun。"""
        states = [c.state for c in self.ci if c.state != "na"]
        if not states:
            return "unknown" if any(c.state == "unknown" for c in self.ci) else "notrun"
        for verdict in ("fail", "unknown", "running", "notrun"):
            if verdict in states:
                return verdict
        return "pass"


@dataclass
class Snapshot:
    repo: str
    state: str  # ok / partial / offline / rate_limited / auth / error / disabled
    checked_at: datetime  # 这一次尝试读的时刻
    fetched_at: datetime | None  # 数据截至：上次成功从 GitHub 读到的时刻；从没读到过为 None
    from_cache: bool = False
    pulls: list[PullInfo] = field(default_factory=list)
    main_ci: list[CiState] = field(default_factory=list)
    audits: list[Audit] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    reset_at: datetime | None = None
    authenticated: bool = False

    @property
    def fresh(self) -> bool:
        """这次真的从 GitHub 读到了（全部或部分）。False 时画面一律按未知显示。"""
        return self.state in ("ok", "partial") and not self.from_cache


# ---------------------------------------------------------------- 本地：工作流路径、审计结论、仓库名


def _workflow_paths(text: str) -> tuple[bool, tuple[str, ...] | None]:
    """从工作流 YAML 里取 pull_request 触发和它的 paths。返回（PR 会不会触发，paths；None = 不按路径过滤）。

    只认本仓库工作流的写法（缩进列表），不是通用 YAML 解析器；认不出就当“PR 都会触发”，宁可说该跑没跑。
    """
    lines = text.splitlines()
    in_on = False
    on_indent = -1
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if re.match(r"^['\"]?on['\"]?\s*:", stripped) and indent == 0:
            if stripped.split(":", 1)[1].strip():
                inline = stripped.split(":", 1)[1]
                return "pull_request" in inline, None
            in_on, on_indent = True, indent
            continue
        if in_on and indent <= on_indent:
            in_on = False
        if not in_on or not re.match(r"^pull_request\s*:", stripped):
            continue
        pr_indent = indent
        paths: list[str] | None = None
        cursor = index + 1
        while cursor < len(lines):
            sub = lines[cursor]
            sub_stripped = sub.strip()
            sub_indent = len(sub) - len(sub.lstrip())
            if sub_stripped and not sub_stripped.startswith("#") and sub_indent <= pr_indent:
                break
            if re.match(r"^paths\s*:", sub_stripped):
                paths = []
                key_indent = sub_indent
                cursor += 1
                while cursor < len(lines):
                    item = lines[cursor]
                    item_stripped = item.strip()
                    if item_stripped and len(item) - len(item.lstrip()) <= key_indent and not item_stripped.startswith("-"):
                        break
                    if item_stripped.startswith("-"):
                        paths.append(item_stripped[1:].strip().strip("'\""))
                    elif item_stripped and not item_stripped.startswith("#"):
                        break
                    cursor += 1
                continue
            cursor += 1
        return True, tuple(paths) if paths is not None else None
    return False, None


def read_workflows(repo_root: Path) -> dict[str, tuple[str, ...] | None]:
    """{工作流名: PR 路径过滤（None = 所有 PR 都跑）}；只收会被 pull_request 触发的。"""
    folder = repo_root / ".github" / "workflows"
    found: dict[str, tuple[str, ...] | None] = {}
    if not folder.is_dir():
        return dict(DEFAULT_WORKFLOWS)
    for path in sorted(folder.glob("*.y*ml")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        name_match = re.search(r"^name\s*:\s*['\"]?(.+?)['\"]?\s*$", text, re.MULTILINE)
        name = name_match.group(1) if name_match else path.stem
        triggered, paths = _workflow_paths(text)
        if triggered:
            found[name] = paths
    return found or dict(DEFAULT_WORKFLOWS)


def path_matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-2])
    return fnmatchcase(path, pattern) if any(ch in pattern for ch in "*?[") else path == pattern


def expected_workflows(paths: Iterable[str], workflows: Mapping[str, tuple[str, ...] | None]) -> set[str]:
    paths = list(paths)
    return {
        name
        for name, patterns in workflows.items()
        if patterns is None or any(path_matches(p, pattern) for p in paths for pattern in patterns)
    }


def projects_of(paths: Iterable[str]) -> list[str]:
    found: list[str] = []
    for path in paths:
        pid = next((m.group(1) for m in (PROJECT_SEGMENT.match(part) for part in path.split("/")) if m), SHARED)
        if pid not in found:
            found.append(pid)
    return sorted(found, key=lambda p: (p == SHARED, p))


def repo_from_git_config(repo_root: Path) -> str:
    """从 .git/config 的 origin 读 owner/name；读不到用 DEFAULT_REPO。只读文件，不起子进程。"""
    config = repo_root / ".git" / "config"
    try:
        text = config.read_text(encoding="utf-8")
    except OSError:
        return DEFAULT_REPO
    section = re.search(r'\[remote "origin"\](.*?)(?=^\[|\Z)', text, re.DOTALL | re.MULTILINE)
    url = re.search(r"^\s*url\s*=\s*(\S+)", section.group(1), re.MULTILINE) if section else None
    match = re.search(r"github\.com[:/]([\w.-]+)/([\w.-]+?)(?:\.git)?/?$", url.group(1)) if url else None
    return f"{match.group(1)}/{match.group(2)}" if match else DEFAULT_REPO


def _verdict(text: str) -> str:
    head = text.strip().lstrip("：: ")
    bold = re.match(r"^\*\*(.+?)\*\*", head)
    first = bold.group(1) if bold else re.split(r"[。；;\n]", head, maxsplit=1)[0]
    if re.search(r"不通过|不过|不同意|驳回|退回", first):
        return "fail"
    if "有条件" in first:
        return "conditional"
    if re.search(r"通过|^过|预审过|复核过|同意合并", first):
        return "pass"
    return "unknown"


def _audit_pr(name: str, top: list[str]) -> int | None:
    """PR 号只认三处：文件名里的 PR35、标题行里的 PR #35、“- PR：#35 / - 对象：PR #35”行。正文里顺带提到的不算。"""
    in_name = re.search(r"PR(\d+)", name)
    if in_name:
        return int(in_name.group(1))
    for line in top:
        match = AUDIT_PR_LINE.match(line)
        if match:
            return int(match.group(1) or match.group(2))
    return None


def parse_audit(path: Path) -> Audit | None:
    match = AUDIT_FILE.match(path.name)
    if not match:
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return Audit(int(match.group(1)), path.name, "unknown", "读不出这份文件")
    lines = text.splitlines()
    top = "\n".join(lines[:20])
    pr_number = _audit_pr(path.name, lines[:20])
    head = AUDIT_HEAD.search(top)
    branch = AUDIT_BRANCH.search(top)
    verdict, summary = "unknown", "没找到“结论”段"
    for index, line in enumerate(lines):
        heading = AUDIT_HEADING.match(line.strip())
        if not heading:
            continue
        title = heading.group(1)
        tail = re.split(r"[：:]", title, maxsplit=1)
        body = next((x.strip() for x in lines[index + 1:index + 8] if x.strip()), "")
        candidate = _verdict(tail[1]) if len(tail) > 1 and tail[1].strip() else "unknown"
        if candidate == "unknown":
            candidate = _verdict(body)
        if candidate != "unknown" or verdict == "unknown":
            verdict = candidate
            summary = (title if title.startswith("复核") else (body or title)).strip("* ")
            if title.startswith("复核"):
                sha = re.search(r"[0-9a-f]{7,40}", title)
                if sha:
                    head = sha
    return Audit(
        number=int(match.group(1)),
        file=path.name,
        verdict=verdict,
        summary=summary[:120],
        pr=pr_number,
        branch=branch.group(1) if branch else "",
        head=(head.group(1) if head and head.groups() else head.group(0) if head else "").lower(),
    )


def read_audits(dirs: Iterable[Path]) -> list[Audit]:
    out: list[Audit] = []
    for folder in dirs:
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.md")):
            audit = parse_audit(path)
            if audit is not None:
                out.append(audit)
    return sorted(out, key=lambda a: (a.number, a.file))


def audit_for(pull: PullInfo, audits: list[Audit]) -> Audit | None:
    """这个 PR 最新的一份审计：按 PR 号对，或按分支名对（预做分支预审）。编号大的算新。"""
    hits = [a for a in audits if a.pr == pull.number or (a.branch and a.branch == pull.head_ref)]
    return max(hits, key=lambda a: (a.number, a.file), default=None)


# ---------------------------------------------------------------- 安全回路与签字（只显示）


def plan_declaration(body: str | None) -> tuple[str | None, str]:
    values: list[str] = []
    fenced = False
    for line in (body or "").splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        match = None if fenced else PLAN_LINE.match(line)
        if match:
            values.append(match.group(1).strip("`*_ "))
    if not values:
        return None, ""
    bad = sorted({v for v in values if v not in PLAN_CHOICES})
    if bad:
        return None, f"“安全回路”只能写 是 或 否，现在写的是：{'、'.join(bad)}"
    if len(set(values)) > 1:
        return None, "“安全回路”写了多行且不一致"
    return values[0], ""


def find_signature(comments: list[dict], head_sha: str) -> tuple[str | None, str]:
    """返回（签到的提交号，没签上的原因）。只认指定签字人本人手写、签的是当前头提交的。"""
    notes: list[str] = []
    for comment in comments:
        body = str(comment.get("body") or "")
        shas = [m.group(1).lower() for m in (SIGN_LINE.match(line) for line in body.splitlines()) if m]
        if not shas:
            continue
        user = comment.get("user") or {}
        login, uid = user.get("login"), user.get("id")
        if login not in SIGNERS or SIGNERS[login] != uid:
            notes.append(f"{login} 不是指定签字人")
            continue
        if comment.get("performed_via_github_app"):
            notes.append("经由 App 发出，不算")
            continue
        if not any(head_sha.startswith(sha) for sha in shas):
            notes.append(f"签的是 {shas[0][:8]}，现在的头是 {head_sha[:8]}，要重签")
            continue
        return head_sha[:8], ""
    return None, "；".join(notes)


def safety_of(body: str | None, comments: list[dict] | None, head_sha: str, plc: bool) -> Safety:
    plan, problem = plan_declaration(body)
    if problem:
        return Safety("undeclared", None, problem)
    if comments is None:
        return Safety("unknown", plan, "PR 评论没读到")
    signed, why = find_signature(comments, head_sha)
    if signed:
        return Safety("signed", plan, f"已签 {signed}")
    if plan == "是":
        return Safety("waiting", plan, why or f"填了“安全回路: 是”，等你仿真后签 {head_sha[:8]}")
    if plan == "否":
        return Safety("declared_no", plan, "填了“否”；碰没碰安全区由 safety-gate 判（合进 main 后）")
    if plc:
        return Safety("undeclared", None, "改了 PLC 却没写“安全回路: 是/否”一行")
    return Safety("na", None, "不涉及 PLC")


# ---------------------------------------------------------------- CI


def _run_state(run: dict) -> tuple[str, str]:
    status, conclusion = run.get("status"), run.get("conclusion")
    if status != "completed":
        return "running", "在跑"
    if conclusion == "success":
        return "pass", "过"
    if conclusion in ("failure", "timed_out", "startup_failure", "action_required"):
        return "fail", "红"
    if conclusion == "cancelled":
        return "fail", "被取消（不算过）"
    return "notrun", f"没跑（{conclusion or '无结论'}）"


def latest_runs(runs: list[dict]) -> dict[str, dict]:
    """每个工作流名取最新的一次（run_number 大的、建得晚的）。"""
    out: dict[str, dict] = {}
    for run in runs:
        name = str(run.get("name") or "")
        key = (str(run.get("created_at") or ""), int(run.get("run_number") or 0))
        old = out.get(name)
        if old is None or key > (str(old.get("created_at") or ""), int(old.get("run_number") or 0)):
            out[name] = run
    return out


def ci_states(runs: list[dict] | None, expected: set[str], known: Iterable[str]) -> list[CiState]:
    names = sorted(set(known) | expected | set(latest_runs(runs or [])))
    if runs is None:
        return [CiState(n, "unknown", "没读到") if n in expected else CiState(n, "na", "路径没碰到") for n in names]
    latest = latest_runs(runs)
    out = []
    for name in names:
        run = latest.get(name)
        if run is not None:
            state, text = _run_state(run)
            out.append(CiState(name, state, text, str(run.get("html_url") or "")))
        elif name in expected:
            out.append(CiState(name, "notrun", "应跑没跑"))
        else:
            out.append(CiState(name, "na", "路径没碰到，不跑"))
    return out


# ---------------------------------------------------------------- 网络（只 GET）


Fetch = Callable[[str, dict[str, str]], tuple[int, Mapping[str, str], bytes]]


def urllib_fetch(url: str, headers: dict[str, str]) -> tuple[int, Mapping[str, str], bytes]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 - 只连 api.github.com
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers or {}), error.read() or b""
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise OfflineError(str(getattr(error, "reason", error))) from error


def _header(headers: Mapping[str, str], name: str) -> str:
    lowered = {k.lower(): v for k, v in headers.items()}
    return str(lowered.get(name.lower(), ""))


class Api:
    def __init__(self, fetch: Fetch, token: str, etags: dict[str, list]) -> None:
        self.fetch = fetch
        self.token = token
        self.etags = etags  # {url: [etag, 正文 JSON]}；不含令牌
        self.calls = 0

    def get(self, path: str) -> object:
        url = path if path.startswith("http") else API + path
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "WorkSpacePM-cockpit-readonly",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        cached = self.etags.get(url)
        if cached and cached[0]:
            headers["If-None-Match"] = cached[0]
        self.calls += 1
        status, response_headers, body = self.fetch(url, headers)
        if status == 304 and cached:
            return cached[1]
        if status in (403, 429) and (
            _header(response_headers, "x-ratelimit-remaining") == "0" or _header(response_headers, "retry-after")
            or b"rate limit" in body.lower()
        ):
            reset = _header(response_headers, "x-ratelimit-reset")
            raise RateLimitedError(datetime.fromtimestamp(int(reset), UTC) if reset.isdigit() else None)
        if status == 401 or (status == 404 and not self.token and "/pulls?" in url):
            raise AuthFailedError("令牌无效，或私有仓库没给令牌" if status == 401 or self.token else "没给令牌（私有仓库要令牌）")
        if status != 200:
            raise ApiError(f"HTTP {status}")
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise ApiError("回的不是 JSON") from error
        etag = _header(response_headers, "etag")
        if etag:
            self.etags[url] = [etag, data]
        return data


def read_token(env: Mapping[str, str]) -> str:
    return next((env[name].strip() for name in TOKEN_ENV if env.get(name, "").strip()), "")


# ---------------------------------------------------------------- 缓存


def default_cache_path(repo: str, env: Mapping[str, str] = os.environ) -> Path:
    base = env.get("LOCALAPPDATA") or env.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "WorkSpacePM" / "cockpit" / f"github_{repo.replace('/', '_')}.json"


def _audit_from(raw: dict) -> Audit:
    return Audit(**raw)


def _pull_from(raw: dict) -> PullInfo:
    raw = dict(raw)
    raw["ci"] = [CiState(**c) for c in raw.get("ci", [])]
    raw["safety"] = Safety(**raw["safety"])
    raw["audit"] = _audit_from(raw["audit"]) if raw.get("audit") else None
    return PullInfo(**raw)


def load_cache(path: Path) -> tuple[dict[str, list], Snapshot | None]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}, None
    if not isinstance(raw, dict) or raw.get("version") != CACHE_VERSION:
        return {}, None
    etags = raw.get("etags") if isinstance(raw.get("etags"), dict) else {}
    snap = raw.get("snapshot")
    try:
        snapshot = Snapshot(
            repo=snap["repo"],
            state=snap["state"],
            checked_at=datetime.fromisoformat(snap["checked_at"]),
            fetched_at=datetime.fromisoformat(snap["fetched_at"]) if snap.get("fetched_at") else None,
            pulls=[_pull_from(p) for p in snap.get("pulls", [])],
            main_ci=[CiState(**c) for c in snap.get("main_ci", [])],
            errors=list(snap.get("errors", [])),
            authenticated=bool(snap.get("authenticated")),
        )
    except (KeyError, TypeError, ValueError):
        return etags, None
    return etags, snapshot


def save_cache(path: Path, etags: dict[str, list], snapshot: Snapshot) -> None:
    """写缓存：先写临时文件再替换，写一半断电也不坏。令牌不进缓存。审计结论每次现读，也不进缓存。"""
    snap = asdict(snapshot)
    snap.pop("audits", None)
    snap["checked_at"] = snapshot.checked_at.isoformat()
    snap["fetched_at"] = snapshot.fetched_at.isoformat() if snapshot.fetched_at else None
    snap["reset_at"] = None
    payload = {"version": CACHE_VERSION, "repo": snapshot.repo, "etags": etags, "snapshot": snap}
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


# ---------------------------------------------------------------- 采集


def _fallback(
    repo: str, state: str, now: datetime, cached: Snapshot | None, audits: list[Audit], error: str,
    reset_at: datetime | None = None, authenticated: bool = False,
) -> Snapshot:
    """读不到：带上缓存里的旧数据（标 from_cache），没有缓存就空着。画面按未知显示。"""
    if cached is None:
        return Snapshot(repo, state, now, None, False, [], [], audits, [error], reset_at, authenticated)
    for pull in cached.pulls:
        pull.audit = audit_for(pull, audits)
        pull.audit_stale = bool(pull.audit and pull.audit.head and not pull.head_sha.startswith(pull.audit.head))
    return Snapshot(repo, state, now, cached.fetched_at, True, cached.pulls, cached.main_ci, audits, [error],
                    reset_at, authenticated)


def _describe(error: Exception) -> tuple[str, str, datetime | None]:
    if isinstance(error, OfflineError):
        return "offline", f"断网：{error}", None
    if isinstance(error, RateLimitedError):
        when = error.reset_at.strftime("%H:%M UTC") if error.reset_at else "稍后"
        return "rate_limited", f"GitHub 限流，{when} 恢复", error.reset_at
    if isinstance(error, AuthFailedError):
        return "auth", f"令牌：{error}", None
    return "error", f"读失败：{error}", None


def collect(
    repo: str,
    repo_root: Path,
    reviews_dirs: Iterable[Path],
    cache_path: Path | None,
    now: datetime,
    fetch: Fetch | None = None,
    env: Mapping[str, str] = os.environ,
    offline: bool = False,
) -> Snapshot:
    """读一轮。任何异常都不往外抛（画面不挂），一律变成 Snapshot.state + errors。"""
    audits = read_audits(reviews_dirs)
    etags, cached = load_cache(cache_path) if cache_path else ({}, None)
    if cached is not None and cached.repo != repo:
        etags, cached = {}, None
    if offline:
        return _fallback(repo, "offline", now, cached, audits, "按离线处理，没去读 GitHub",
                         authenticated=bool(read_token(env)))
    token = read_token(env)
    api = Api(fetch or urllib_fetch, token, etags)
    workflows = read_workflows(repo_root)
    try:
        raw_pulls = api.get(f"/repos/{repo}/pulls?state=open&per_page={PER_PAGE}")
        if not isinstance(raw_pulls, list):
            raise ApiError("PR 列表格式不对")
    except (OfflineError, RateLimitedError, AuthFailedError, ApiError) as error:
        state, text, reset = _describe(error)
        return _fallback(repo, state, now, cached, audits, text, reset, bool(token))

    errors: list[str] = []
    stopped: str = ""  # 半路限流后不再发请求

    def guarded(what: str, path: str) -> object | None:
        nonlocal stopped
        if stopped:
            errors.append(f"{what}：没读（{stopped}）")
            return None
        try:
            return api.get(path)
        except RateLimitedError as error:
            stopped = _describe(error)[1]
            errors.append(f"{what}：{stopped}")
        except (OfflineError, AuthFailedError, ApiError) as error:
            errors.append(f"{what}：{_describe(error)[1]}")
        return None

    main_raw = guarded("main 上的 CI", f"/repos/{repo}/actions/runs?branch=main&event=push&per_page=50")
    main_runs = main_raw.get("workflow_runs") if isinstance(main_raw, dict) else None
    main_ci = [
        c if c.state != "na" else CiState(c.workflow, "notrun", "main 上最近 50 次推送里没跑")
        for c in ci_states(main_runs, set(workflows), workflows)
    ] if main_runs is not None else [CiState(n, "unknown", "没读到") for n in sorted(workflows)]

    pulls: list[PullInfo] = []
    for raw in raw_pulls:
        number = int(raw.get("number"))
        head = raw.get("head") or {}
        pull = PullInfo(
            number=number,
            title=str(raw.get("title") or ""),
            url=str(raw.get("html_url") or ""),
            author=str((raw.get("user") or {}).get("login") or ""),
            head_sha=str(head.get("sha") or ""),
            head_ref=str(head.get("ref") or ""),
            draft=bool(raw.get("draft")),
            updated_at=str(raw.get("updated_at") or ""),
        )
        before = len(errors)
        files = guarded(f"PR #{number} 改动文件", f"/repos/{repo}/pulls/{number}/files?per_page={PER_PAGE}")
        paths = [str(f.get("filename") or "") for f in files] if isinstance(files, list) else None
        if paths is not None:
            pull.projects = projects_of(paths)
            pull.plc = any(p.startswith(PLC_ROOT) for p in paths)
        runs_raw = guarded(f"PR #{number} CI", f"/repos/{repo}/actions/runs?head_sha={pull.head_sha}&per_page=50")
        runs = runs_raw.get("workflow_runs") if isinstance(runs_raw, dict) else None
        if paths is None:
            # 不知道改了哪些文件，就推不出该跑哪几个：一律未知，不说“不适用”
            pull.ci = [CiState(n, "unknown", "改动文件没读到") for n in sorted(workflows)]
        else:
            pull.ci = ci_states(runs, expected_workflows(paths, workflows), workflows)
        comments = guarded(f"PR #{number} 评论", f"/repos/{repo}/issues/{number}/comments?per_page={PER_PAGE}")
        pull.safety = safety_of(
            str(raw.get("body") or ""), comments if isinstance(comments, list) else None, pull.head_sha,
            pull.plc if paths is not None else True,
        )
        if paths is None and pull.safety.state in ("na", "undeclared") and pull.safety.plan is None:
            pull.safety = Safety("unknown", None, "改动文件没读到，判断不了要不要声明安全回路")
        pull.audit = audit_for(pull, audits)
        pull.audit_stale = bool(pull.audit and pull.audit.head and not pull.head_sha.startswith(pull.audit.head))
        pull.errors = errors[before:]
        pulls.append(pull)

    state = "partial" if errors else "ok"
    snapshot = Snapshot(repo, state, now, now, False, sorted(pulls, key=lambda p: p.number), main_ci, audits,
                        errors, None, bool(token))
    if cache_path is not None:
        try:
            save_cache(cache_path, api.etags, snapshot)
        except OSError as error:
            snapshot.errors.append(f"本机缓存没写成：{error}")
    return snapshot
