"""PLC 检查“只拦新增失败”：把一次检查的失败项展开成逐条的键，再和开工基线逐条比。

口径与 PLC 项目 CI（``reviews/tools/plc_ci.py`` 的 ``failure_keys``）相同：

* 一般检查项：项目名 + 说明，说明里的数字抹平（行数、计数会变，问题本身没变）；
* “SCL 代码规范”只给总数和前 3 条，这里用同一个 ``SclLinter`` 逐条展开（文件 + 规则 + 说明 + **违规处的代码文字**，不含行号）；
* “文档一致性 [...]”逐条展开成 ``plc docs check`` 的明细；
* Siemens 语言服务 check/test 逐条展开成插件命令行的诊断行（行号、列号抹平，同样带上那一行的代码文字）。

为什么键里要有代码文字：规范错误的说明大多不带变量名（CASE 缺 ELSE、GOTO、TIME 字面量……），只比“文件 + 规则 + 说明”，
同一个文件里“补上一处、新写一处”会被当成同一条老问题放行（审计 125）。“违规处的代码文字”= 违规那一行加上它前面最多
2 行非空、非纯注释的代码（CASE 缺 ELSE 报在 ``END_CASE;`` 上，只看那一行两个 CASE 长得一样，要连着前面的 ``CASE xxx OF`` 一起看）。
只是整体挪了行号、或前面插了注释的错仍是同一条；违规处及其紧挨着的前两行被改动，就算新增（宁可多拦，不漏拦）。
同样的算法在 ``reviews/tools/plc_ci.py`` 里有一份，测试 b12 锁两边一致。

同一个键出现的次数也算数：基线 2 条、现在 3 条，多出的 1 条就是新增。展开不出明细时退回用检查项本身的说明当键，宁可多拦不漏拦。

本模块只做纯数据比对，不起子进程；取基线文件（Git）的事在应用层做。
"""

from __future__ import annotations

import os
import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from auto_pm.domain.models.plc import CheckResult
from auto_pm.domain.plc.language_service import LanguageService, LanguageServiceResult
from auto_pm.domain.plc.scl_linter import SclLinter

_DIGITS = re.compile(r"\d+")
_LOCATION = re.compile(r":\d+(?::\d+)?")
_DIAGNOSTIC = re.compile(r"^(?:\[(?P<scope>[^\]]*)\]\s*)?(?:\./)?(?P<file>[^:\n]+?):(?P<line>\d+)(?::\d+)?:")
MAX_CODE_TEXT = 300
CONTEXT_LINES = 2
SCL_ITEM = "SCL 代码规范"
DOC_ITEM_PREFIX = "文档一致性"
LANGUAGE_ITEMS = {"Siemens 语言服务 check": "check", "Siemens 语言服务 test": "test"}


@dataclass(frozen=True)
class FailureDiff:
    """现在的失败项和基线逐条比的结果。"""

    new: tuple[str, ...]
    known: tuple[str, ...]
    fixed: tuple[str, ...]
    baseline_note: str = ""

    @property
    def passed(self) -> bool:
        """没有新增失败（基线已有的老问题不算本单）。"""
        return not self.new

    def render(self, title: str) -> list[str]:
        """电气工程师看得懂的比对段落：先结论，再逐条。"""
        lines = [
            f"{title}：新增失败 {len(self.new)} 条（拦），基线已有失败 {len(self.known)} 条（不算本单，仍需另行修复），"
            f"本单修好 {len(self.fixed)} 条"
        ]
        if self.baseline_note:
            lines.append(f"基线说明：{self.baseline_note}")
        lines.extend(f"new | {key}" for key in self.new)
        lines.extend(f"known | {key}" for key in self.known)
        lines.extend(f"fixed | {key}" for key in self.fixed)
        return lines


def diff_failures(now: Counter[str], base: Counter[str] | None, *, baseline_note: str = "") -> FailureDiff:
    """逐条比：现在有、基线没有（或次数变多）的是新增；基线有、现在没了的是本单修好。``base`` 为 None 时全部算新增。"""

    base = base or Counter()
    new: list[str] = []
    known: list[str] = []
    for key, count in sorted(now.items()):
        old = min(count, base.get(key, 0))
        known.extend([key] * old)
        new.extend([key] * (count - old))
    fixed: list[str] = []
    for key, count in sorted(base.items()):
        fixed.extend([key] * max(0, count - now.get(key, 0)))
    return FailureDiff(tuple(new), tuple(known), tuple(fixed), baseline_note)


def _plain(text: str, project_path: str) -> str:
    for variant in {project_path, os.path.abspath(project_path)}:
        text = text.replace(variant + os.sep, "").replace(variant, ".")
    return text.replace("\\", "/")


def code_context(source: Sequence[str], line_number: int) -> str:
    """违规处的代码文字：第 ``line_number`` 行（从 1 数）加上它前面最多 ``CONTEXT_LINES`` 行非空、非纯注释的代码。"""

    index = line_number - 1
    if not 0 <= index < len(source):
        return ""
    picked = [source[index].strip()]
    previous = index - 1
    while previous >= 0 and len(picked) <= CONTEXT_LINES:
        text = source[previous].strip()
        if text and not text.startswith("//"):
            picked.append(text)
        previous -= 1
    return " / ".join(reversed(picked))


def _context_in_file(path: Path | str, line_number: int, fallback: str = "") -> str:
    try:
        source = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return fallback
    return code_context(source, line_number) or fallback


def code_suffix(code: str) -> str:
    """键尾巴：违规那一行的代码文字（去掉首尾空白，数字不抹平）；取不到就不加。"""

    text = " ".join(code.split())[:MAX_CODE_TEXT]
    return f" | 代码: {text}" if text else ""


def _source_line(project_path: str, diagnostic: str) -> str:
    """插件诊断行 ``[范围] 文件:行:列: …`` 指向的那一行源码；读不到返回空串。"""

    found = _DIAGNOSTIC.match(diagnostic)
    if found is None:
        return ""
    base = Path(project_path)
    scope = found.group("scope")
    if scope and scope != ".":
        base = base / scope
    return _context_in_file(base / found.group("file"), int(found.group("line")))


def scl_failure_keys(project_path: str) -> Counter[str]:
    """工程里全部 .scl（及 .db / .udt 的数组下界）的规范错误，逐条（与 ``PlcChecker`` 的“SCL 代码规范”一项扫同一批文件）。"""

    keys: Counter[str] = Counter()
    for root, _, files in os.walk(project_path):
        for name in sorted(files):
            if not SclLinter.is_lintable(name):  # .scl 全查，.db / .udt 只查数组下界
                continue
            path = os.path.join(root, name)
            relative = os.path.relpath(path, project_path).replace(os.sep, "/")
            for violation in SclLinter.lint_file(path).violations:
                if violation.severity == "ERROR":
                    context = _context_in_file(path, violation.line_number, violation.code_snippet)
                    keys[
                        f"SCL 规范 · {relative} [{violation.rule_id}] {violation.message}{code_suffix(context)}"
                    ] += 1
    return keys


def lint_failure_keys(files: Iterable[tuple[str, Path]]) -> Counter[str]:
    """指定文件（相对名, 路径）的规范错误逐条键；验收门的 scl-lint 只看 Run 名下的文件。"""

    keys: Counter[str] = Counter()
    for relative, path in files:
        for violation in SclLinter.lint_file(str(path)).violations:
            if violation.severity == "ERROR":
                context = _context_in_file(path, violation.line_number, violation.code_snippet)
                keys[f"{relative} [{violation.rule_id}] {violation.message}{code_suffix(context)}"] += 1
    return keys


def doc_failure_keys(project_path: str) -> Counter[str]:
    from auto_pm.domain.plc.doc_consistency import analyze_project

    keys: Counter[str] = Counter()
    for finding in analyze_project(project_path).findings:
        if finding.severity == "fail":
            who = f"{finding.obj}.{finding.variable}" if finding.variable else finding.obj
            keys[f"文档一致性 · {who}：{finding.message}"] += 1
    return keys


def failure_keys(
    result: CheckResult,
    project_path: str,
    language: Mapping[str, Sequence[str]] | None = None,
) -> Counter[str]:
    """一次 ``PlcChecker.check_project`` 的失败项展开成逐条的键。``language``：插件命令行每条诊断（按 check/test 分）。"""

    keys: Counter[str] = Counter()
    scl_fallback: list[str] = []
    doc_fallback: list[str] = []
    for item in result.items:
        if item.status != "fail":
            continue
        message = _plain(item.message, project_path)
        plain_key = f"plc check · {item.item}：{_DIGITS.sub('#', message)}"
        if item.item == SCL_ITEM:
            scl_fallback.append(plain_key)
        elif item.item.startswith(DOC_ITEM_PREFIX):
            doc_fallback.append(plain_key)
        elif item.item in LANGUAGE_ITEMS:
            command = LANGUAGE_ITEMS[item.item]
            lines = (language or {}).get(command, ())
            if lines:
                for line in lines:
                    shown = _LOCATION.sub(":#", _plain(line, project_path))
                    keys[f"Siemens 语言服务 {command} · {shown}{code_suffix(_source_line(project_path, line))}"] += 1
            else:
                keys[plain_key] += 1
        else:
            keys[plain_key] += 1
    for fallback, expand in ((scl_fallback, scl_failure_keys), (doc_fallback, doc_failure_keys)):
        if not fallback:
            continue
        expanded = expand(project_path)
        if expanded:
            keys += expanded
        else:
            keys.update(fallback)
    return keys


@dataclass
class RecordingLanguageService:
    """把插件命令行的每条诊断都记下来（检查器自己只留前几条），一次运行同时供判卷和逐条比对用。"""

    inner: LanguageService
    project_root: Path
    diagnostics: dict[str, list[str]] = field(default_factory=dict)
    # 插件命令行没跑完（超时、起不来）：这一次检查不算数，验收门按出错处理，不拿去和基线比
    incomplete: bool = False

    @property
    def available(self) -> bool:
        return self.inner.available

    def check(self, root: Path) -> LanguageServiceResult:
        return self._record(root, self.inner.check(root))

    def test(self, root: Path) -> LanguageServiceResult:
        return self._record(root, self.inner.test(root))

    def _record(self, root: Path, result: LanguageServiceResult) -> LanguageServiceResult:
        try:
            tag = root.relative_to(self.project_root).as_posix()
        except ValueError:
            tag = root.name
        if result.available and result.exit_code in (-1, None):
            self.incomplete = True
        lines = result.diagnostics or result.messages
        bucket = self.diagnostics.setdefault(result.command, [])
        bucket.extend(f"[{tag}] {line}" for line in lines if result.available and not result.passed)
        return result


__all__ = [
    "FailureDiff",
    "RecordingLanguageService",
    "diff_failures",
    "doc_failure_keys",
    "failure_keys",
    "lint_failure_keys",
    "scl_failure_keys",
]
