"""总控屏“工具”页：命令白名单、拼装、回执、IO 查重、页面行为，以及“只有 actions.py / tool_actions.py 起子进程”。

界面是命令行的另一层皮：这里每个按钮对应的命令，参数取值都和真实命令的选项对账，不凭记忆写死。
"""

from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import (  # noqa: E402
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDial,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QSlider,
    QTextEdit,
    QWidget,
)

TOOL_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = TOOL_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cockpit_board import decisions, iocheck, policy, tool_actions, tool_policy  # noqa: E402
from cockpit_board.actions import Receipt  # noqa: E402
from cockpit_board.widgets.tools import ToolsPage  # noqa: E402

from auto_pm.contracts.intake import (  # noqa: E402
    EVIDENCE_KINDS,
    ChangeAction,
    Disposition,
    IntakeKind,
    UrgentCriterion,
)
from auto_pm.domain.change.constants import STATUS_FLOW, STATUS_LABELS  # noqa: E402

ERR = tool_actions.ToolError


def _create(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "pid": "DJ-2026-009", "domain": "PLC", "nature": "REQ", "scope": ["LOCAL", "MODULE"], "applicant": "张工（客户设备科）",
        "background": "上料节拍太慢", "necessity": "客户要提产", "urgency": "normal", "references": "",
    }
    values.update(changes)
    return values


def _inbox(**changes: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "pid": "DJ-2026-009", "request_id": "board-20261112T210000Z", "title": "上料节拍太慢", "kind": "iteration",
        "original_words": "上料那段  太慢了，\n客户要提产", "affects": "上料工位 OB1", "duplicate_check": "查过收件箱和台账，没有同类",
        "evidence": "file:说明书.md\ncmd:main.py pm inbox list --project-id DJ-2026-009", "disposition": "after_current",
        "rationale": "不挡手上的卡", "alternatives": "先改定时器\n换气缸", "cost_risk": "半天；低风险",
    }
    values.update(changes)
    return values


# ---------------------------------------------------------------- 取值和真实命令对账


def _cli() -> Any:
    from auto_pm.ui.cli.__main__ import cli

    return cli


def _choices(command: Any, name: str) -> tuple[str, ...]:
    return tuple(next(p for p in command.params if p.name == name).type.choices)


def test_choices_match_the_real_change_create_options() -> None:
    create = _cli().commands["change"].commands["create"]
    assert tool_actions.CHANGE_DOMAINS == _choices(create, "domain")
    assert tool_actions.CHANGE_NATURES == _choices(create, "business_nature")
    assert tool_actions.CHANGE_SCOPES == _choices(create, "impact_scope")
    assert tool_actions.CHANGE_URGENCIES == _choices(create, "urgency")


def test_inbox_choices_match_the_real_inbox_add_options_and_the_contract() -> None:
    add = _cli().commands["pm"].commands["inbox"].commands["add"]
    assert tool_actions.INBOX_KINDS == _choices(add, "kind") == tuple(k.value.lower() for k in IntakeKind)
    assert tool_actions.INBOX_ACTIONS == _choices(add, "change_action") == tuple(a.value.lower() for a in ChangeAction)
    assert tool_actions.INBOX_DISPOSITIONS == _choices(add, "disposition") == tuple(d.value.lower() for d in Disposition)
    assert tool_actions.INBOX_CRITERIA == _choices(add, "urgent_criterion") == tuple(u.value.lower() for u in UrgentCriterion)
    assert tool_actions.INBOX_EVIDENCE_KINDS == EVIDENCE_KINDS


def test_status_lists_match_the_real_change_states() -> None:
    transition = _cli().commands["change"].commands["transition"]
    real = set(_choices(transition, "new_status"))
    assert real == set(STATUS_FLOW) == set(tool_actions.CHANGE_STATUSES)
    assert set(tool_actions.CHANGE_TARGETS) | set(tool_actions.USER_ONLY_TARGETS) == real
    assert not set(tool_actions.CHANGE_TARGETS) & set(tool_actions.USER_ONLY_TARGETS)
    assert tool_actions.STATUS_LABELS_ZH == STATUS_LABELS


def test_every_tool_command_exists_with_the_options_we_pass() -> None:
    cli = _cli()
    needs = {
        "change list": {"--status", "--full"}, "change show": {"--pid"},
        "change create": {"--pid", "--domain", "--nature", "--scope", "--applicant", "--background", "--necessity", "--urgency", "--references"},
        "change transition": {"--to", "--pid", "--comment", "--approver", "--verification-conclusion"},
        "decision list": {"--pid", "--change-id"}, "decision show": set(), "vartable parse": {"--output-format"},
        "pm inbox add": {
            "--project-id", "--request-id", "--title", "--kind", "--change-action", "--domain", "--impact-scope", "--original-words",
            "--affects", "--duplicate-check", "--duplicate-of", "--evidence", "--urgent-criterion", "--disposition", "--rationale",
            "--alternative", "--cost-risk", "--ask", "--proposed-by",
        },
    }
    for label, flags in needs.items():
        command = cli
        for word in label.split():
            command = command.commands[word]
        have = {opt for p in command.params for opt in getattr(p, "opts", [])}
        assert flags <= have, (label, flags - have)


# ---------------------------------------------------------------- 拼命令


def test_build_command_exact_argv() -> None:
    b = tool_actions.build_command
    assert b("change_list", {"pid": "DJ-1"}) == ["change", "list", "DJ-1", "--full"]
    assert b("change_list", {"pid": "DJ-1", "status": "draft"}) == ["change", "list", "DJ-1", "--full", "--status", "draft"]
    assert b("change_show", {"pid": "DJ-1", "number": "CHG-X-1"}) == ["change", "show", "CHG-X-1", "--pid", "DJ-1"]
    assert b("change_create", _create(references="图纸 A3")) == [
        "change", "create", "--pid", "DJ-2026-009", "--domain", "PLC", "--nature", "REQ", "--scope", "LOCAL", "--scope", "MODULE",
        "--applicant", "张工（客户设备科）", "--background", "上料节拍太慢", "--necessity", "客户要提产", "--urgency", "normal",
        "--references", "图纸 A3"]
    assert b("change_transition", {"pid": "DJ-1", "number": "CHG-X-1", "to": "submitted"}) == [
        "change", "transition", "CHG-X-1", "--to", "submitted", "--pid", "DJ-1"]
    assert b("decision_list", {}) == ["decision", "list"]
    assert b("decision_list", {"pid": "DJ-1", "change_id": "CHG-X-1"}) == ["decision", "list", "--pid", "DJ-1", "--change-id", "CHG-X-1"]
    assert b("decision_show", {"decision_id": "DEC-1"}) == ["decision", "show", "DEC-1"]
    assert b("vartable_parse", {"file": "/x/io_points.csv"}) == ["vartable", "parse", "/x/io_points.csv", "--output-format", "json"]


def test_inbox_add_exact_argv_keeps_the_original_words_as_typed() -> None:
    assert tool_actions.build_command("inbox_add", _inbox()) == [
        "pm", "inbox", "add", "--project-id", "DJ-2026-009", "--request-id", "board-20261112T210000Z", "--title", "上料节拍太慢",
        "--kind", "iteration", "--original-words", "上料那段  太慢了，\n客户要提产", "--affects", "上料工位 OB1",
        "--duplicate-check", "查过收件箱和台账，没有同类", "--evidence", "file:说明书.md",
        "--evidence", "cmd:main.py pm inbox list --project-id DJ-2026-009", "--disposition", "after_current", "--rationale", "不挡手上的卡",
        "--alternative", "先改定时器", "--alternative", "换气缸", "--cost-risk", "半天；低风险", "--proposed-by", "cockpit-board"]
    full = tool_actions.build_command("inbox_add", _inbox(
        kind="change", change_action="modify", domain="PLC", impact_scope=["LOCAL", "SAFE"], duplicate_of="TD-SW008-001\n",
        urgent_criterion="safety", asks="要不要停线改"))
    assert full[full.index("--change-action") + 1] == "modify" and full[full.index("--domain") + 1] == "PLC"
    assert [full[i + 1] for i, a in enumerate(full) if a == "--impact-scope"] == ["LOCAL", "SAFE"]
    assert full[full.index("--duplicate-of") + 1] == "TD-SW008-001" and full[full.index("--urgent-criterion") + 1] == "safety"
    assert full[full.index("--ask") + 1] == "要不要停线改" and full[-2:] == ["--proposed-by", "cockpit-board"]


def test_board_request_id_is_utc_time() -> None:
    from datetime import UTC, datetime, timedelta, timezone

    moment = datetime(2026, 11, 12, 14, 0, 5, tzinfo=timezone(timedelta(hours=-7)))
    assert tool_actions.board_request_id(moment) == "board-20261112T210005Z"
    assert tool_actions.board_request_id().startswith("board-" + datetime.now(UTC).strftime("%Y%m%d"))


def test_default_urgency_is_normal_and_scope_may_be_a_single_string() -> None:
    args = tool_actions.build_command("change_create", _create(urgency="", scope="SAFE"))
    assert args[args.index("--urgency") + 1] == "normal" and args.count("--scope") == 1


@pytest.mark.parametrize("target", ["approved", "conditionally_approved"])
def test_approval_states_are_refused_with_the_terminal_hint(target: str) -> None:
    with pytest.raises(ERR, match="只在终端里由你本人做"):
        tool_actions.build_command("change_transition", {"pid": "DJ-1", "number": "CHG-X-1", "to": target})


def test_every_other_target_is_allowed_given_its_required_fields() -> None:
    for target in tool_actions.CHANGE_TARGETS:
        params = {"pid": "DJ-1", "number": "CHG-X-1", "to": target, "comment": "原因", "verification_conclusion": "通过"}
        assert tool_actions.build_command("change_transition", params)[4] == target


@pytest.mark.parametrize(("key", "params", "needle"), [
    ("nope", {}, "没有这个工具"),
    ("change_list", {}, "还没填"),
    ("change_list", {"pid": "DJ-1", "status": "weird"}, "状态只能是"),
    ("change_show", {"pid": "DJ-1"}, "还没填"),
    ("change_create", _create(domain=""), "技术领域只能是"),
    ("change_create", _create(nature="X"), "业务性质只能是"),
    ("change_create", _create(scope=[]), "影响范围至少选一个"),
    ("change_create", _create(scope=["GALAXY"]), "影响范围只能是"),
    ("change_create", _create(urgency="whenever"), "紧急程度只能是"),
    ("change_create", _create(applicant=""), "还没填"),
    ("change_create", _create(background="--pid evil"), "不能以 - 开头"),
    ("change_transition", {"pid": "DJ-1", "number": "CHG-X-1", "to": "abandoned"}, "还没填：comment"),
    ("change_transition", {"pid": "DJ-1", "number": "CHG-X-1", "to": "completed"}, "还没填：verification_conclusion"),
    ("change_transition", {"pid": "DJ-1", "number": "CHG-X-1", "to": "nonsense"}, "目标状态只能是"),
    ("change_transition", {"pid": "DJ-1", "number": "--to", "to": "draft"}, "不能以 - 开头"),
    ("decision_show", {}, "还没填"),
    ("decision_show", {"decision_id": "-h"}, "不能以 - 开头"),
    ("vartable_parse", {}, "还没填"),
    ("vartable_parse", {"file": "--format x"}, "不能以 - 开头"),
    ("inbox_add", _inbox(original_words=""), "还没填：original_words"),
    ("inbox_add", _inbox(original_words="  \n "), "还没填：original_words"),
    ("inbox_add", _inbox(original_words="--project-id X"), "不能以 - 开头"),
    ("inbox_add", _inbox(title=""), "还没填：title"),
    ("inbox_add", _inbox(affects=""), "还没填：affects"),
    ("inbox_add", _inbox(duplicate_check=""), "还没填：duplicate_check"),
    ("inbox_add", _inbox(rationale=""), "还没填：rationale"),
    ("inbox_add", _inbox(cost_risk=""), "还没填：cost_risk"),
    ("inbox_add", _inbox(pid=""), "还没填：pid"),
    ("inbox_add", _inbox(request_id=""), "还没填：request_id"),
    ("inbox_add", _inbox(evidence=""), "取证（至少一条）"),
    ("inbox_add", _inbox(evidence="\n\n"), "取证（至少一条）"),
    ("inbox_add", _inbox(alternatives=""), "备选方案（至少一个）"),
    ("inbox_add", _inbox(evidence="说明书.md"), "取证每行要写成"),
    ("inbox_add", _inbox(evidence="url:http://x"), "取证每行要写成"),
    ("inbox_add", _inbox(evidence="file:a\nfile:a"), "有重复的行"),
    ("inbox_add", _inbox(alternatives="A\nA"), "有重复的行"),
    ("inbox_add", _inbox(kind=""), "类别只能是"),
    ("inbox_add", _inbox(kind="feature"), "类别只能是"),
    ("inbox_add", _inbox(kind="change"), "变更动作只能是"),
    ("inbox_add", _inbox(change_action="add"), "只有类别是“变更”"),
    ("inbox_add", _inbox(disposition=""), "建议处置只能是"),
    ("inbox_add", _inbox(urgent_criterion="soon"), "紧急判据只能是"),
    ("inbox_add", _inbox(domain="XX"), "技术领域只能是"),
    ("inbox_add", _inbox(impact_scope=["GALAXY"]), "影响范围只能是"),
    ("inbox_add", _inbox(rationale="--kind bug"), "不能以 - 开头"),
])
def test_bad_input_is_refused_before_any_command_runs(key: str, params: dict[str, Any], needle: str) -> None:
    with pytest.raises(ERR, match=needle):
        tool_actions.build_command(key, params)


def test_whitelist_has_no_dangerous_verbs() -> None:
    for spec in tool_actions.TOOLS.values():
        assert not any(word in spec.label for word in ("merge", "delete", "approve", "sign", "release", "codex"))
    assert {k for k, s in tool_actions.TOOLS.items() if s.writes} == {"change_create", "change_transition", "inbox_add"}


# ---------------------------------------------------------------- 跑


class _Fake:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "", error: Exception | None = None) -> None:
        self.returncode, self.stdout, self.stderr, self.error = returncode, stdout, stderr, error
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> Any:
        self.calls.append((command, kwargs))
        if self.error:
            raise self.error
        return subprocess.CompletedProcess(command, self.returncode, self.stdout, self.stderr)


def test_run_tool_runs_in_the_control_root_with_the_same_command_a_person_would_type(tmp_path: Path) -> None:
    fake = _Fake(0, "列表", "")
    result = tool_actions.run_tool(tmp_path, "change_list", {"pid": "DJ-1"}, runner=fake)
    command, kwargs = fake.calls[0]
    assert command[:5] == [sys.executable, "-B", str(tmp_path / "main.py"), "-w", str(tmp_path)]
    assert command[5:] == ["change", "list", "DJ-1", "--full"]
    assert kwargs["cwd"] == str(tmp_path) and kwargs["timeout"] == tool_actions.TOOL_TIMEOUT and kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace" and kwargs["env"]["COLUMNS"] == "200" and kwargs["env"]["PYTHONUTF8"] == "1"
    receipt = result.receipt
    assert receipt.rc == 0 and receipt.rc_text == "rc 0" and receipt.command == "main.py change list DJ-1 --full" and receipt.output == "列表"


def test_run_tool_does_not_hide_failures_or_stderr(tmp_path: Path) -> None:
    result = tool_actions.run_tool(tmp_path, "decision_list", {}, runner=_Fake(1, "", "错误: 决策包列表包含无效文件"))
    assert result.receipt.rc == 1 and "无效文件" in result.receipt.output


def test_run_tool_turns_os_and_timeout_errors_into_an_unverified_receipt(tmp_path: Path) -> None:
    for error in (OSError("no python"), subprocess.TimeoutExpired("x", 1)):
        receipt = tool_actions.run_tool(tmp_path, "decision_list", {}, runner=_Fake(error=error)).receipt
        assert receipt.rc is None and receipt.rc_text == "未验证" and type(error).__name__ in receipt.output


def test_run_tool_refuses_without_running_anything(tmp_path: Path) -> None:
    fake = _Fake()
    with pytest.raises(ERR):
        tool_actions.run_tool(tmp_path, "change_transition", {"pid": "P", "number": "C", "to": "approved"}, runner=fake)
    assert fake.calls == []


def test_long_output_is_clipped_and_says_so(tmp_path: Path) -> None:
    receipt = tool_actions.run_tool(tmp_path, "decision_list", {}, runner=_Fake(0, "x" * (tool_actions.OUTPUT_LIMIT + 500))).receipt
    assert len(receipt.output) < tool_actions.OUTPUT_LIMIT + 200 and "只留前" in receipt.output


def test_open_workbench_starts_gui_advanced_detached_and_reports_failure(tmp_path: Path) -> None:
    started: list[Any] = []

    def opener(command: list[str], **kwargs: Any) -> None:
        started.append((command, kwargs))

    receipt = tool_actions.open_workbench(tmp_path, opener=opener)
    assert started[0][0][-2:] == ["gui", "--advanced"] and receipt.rc == 0
    assert started[0][1]["stdin"] == subprocess.DEVNULL and started[0][1]["cwd"] == str(tmp_path)

    def broken(*_a: Any, **_k: Any) -> None:
        raise OSError("denied")

    failed = tool_actions.open_workbench(tmp_path, opener=broken)
    assert failed.rc is None and "denied" in failed.output


def test_find_io_tables_is_read_only_and_skips_git(tmp_path: Path) -> None:
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / ".git").mkdir()
    (tmp_path / "a" / "b" / "io_points.csv").write_text("x", encoding="utf-8")
    (tmp_path / ".git" / "io_points.csv").write_text("x", encoding="utf-8")
    assert tool_actions.find_io_tables(tmp_path) == [tmp_path / "a" / "b" / "io_points.csv"]
    assert tool_actions.find_io_tables(tmp_path / "nope") == []


# ---------------------------------------------------------------- 只有两个文件起子进程


def test_only_actions_and_tool_actions_touch_subprocesses_or_write_files() -> None:
    allowed = {"actions.py", "tool_actions.py"}
    for path in (SCRIPTS / "cockpit_board").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if path.name not in allowed:
            assert not re.search(r"\bsubprocess\b|os\.system|os\.popen|QProcess", text), path.name
    text = (SCRIPTS / "cockpit_board" / "tool_actions.py").read_text(encoding="utf-8")
    assert not re.search(r"write_text|write_bytes|\.unlink|rmtree|shutil\.|open\([^)]*[\"'][wax]", text)  # 工具命令自己不写文件
    page = (SCRIPTS / "cockpit_board" / "widgets" / "tools.py").read_text(encoding="utf-8")
    assert not re.search(r"write_text|write_bytes|\.unlink|rmtree|shutil\.", page)


# ---------------------------------------------------------------- 查重


def _entry(address: str, tag: str, line: int, station: str = "S1") -> dict[str, Any]:
    return {"station": station, "address": address, "tag": tag, "signal_name": tag, "line_number": line}


def test_duplicate_address_and_name_are_found_with_line_numbers() -> None:
    report = iocheck.find_duplicates([_entry("%I0.0", "Start", 2), _entry("I0.1", "Stop", 3), _entry("i0.0 ", "Estop", 4), _entry("%Q0.0", "start", 5)])
    assert report.total == 4 and not report.clean
    assert [(d.key, d.lines, d.names) for d in report.duplicate_addresses] == [("I0.0", (2, 4), ("Start", "Estop"))]
    assert [(d.key, d.lines) for d in report.duplicate_names] == [("Start", (2, 5))]
    text = iocheck.render_report(report)
    assert "重复地址 1 组" in text and "第 2 行、第 4 行" in text and "Start" in text


def test_clean_table_says_so_and_other_stations_do_not_clash() -> None:
    report = iocheck.find_duplicates([_entry("%I0.0", "A", 2, "PLC1"), _entry("%I0.0", "A", 2, "PLC2")])
    assert report.clean and "重复地址：无" in iocheck.render_report(report)


def test_missing_address_or_name_is_counted_not_flagged() -> None:
    report = iocheck.find_duplicates([_entry("", "A", 2), _entry("", "B", 3), _entry("%I0.0", "", 4), _entry("%I0.1", "", 5)])
    assert report.clean and report.missing_address == 2 and report.missing_name == 2 and "2 条没写地址" in report.summary()


def test_extract_entries_tolerates_log_lines_before_the_json_and_refuses_non_tables() -> None:
    document = json.dumps({"success": True, "var_table": {"entries": [_entry("%I0.0", "A", 2)]}})
    assert iocheck.extract_entries("2026 [WARNING] x\n" + document)[0]["tag"] == "A"
    for bad in ("no json at all", "{broken", json.dumps({"success": False}), json.dumps({"success": True, "block_table": {}})):
        with pytest.raises(iocheck.IoCheckError):
            iocheck.extract_entries(bad)
    failed = json.dumps({"success": False, "errors": [{"message": "缺少必需列: station"}]})
    with pytest.raises(iocheck.IoCheckError, match="缺少必需列"):  # 解析失败的原因带出来，不只说“没成功”
        iocheck.extract_entries(failed)


def test_real_cli_output_feeds_the_duplicate_check(tmp_path: Path) -> None:
    """端到端：真的跑一次 vartable parse，再对输出查重（命令输出的字段名变了，这里会红）。"""
    csv = tmp_path / "io_points.csv"
    csv.write_text(
        "station,signal_type,address,tag,signal_name,device,comment\n"
        "S1,BOOL,%I0.0,Start_PB,Start_PB,,启动\nS1,BOOL,%I0.1,Stop_PB,Stop_PB,,停止\nS1,BOOL,%I0.0,Estop,Estop,,急停\n",
        encoding="utf-8",
    )
    result = tool_actions.run_tool(TOOL_ROOT, "vartable_parse", {"file": str(csv)})
    assert result.receipt.rc == 0, result.receipt.output
    report = iocheck.find_duplicates(iocheck.extract_entries(result.stdout))
    assert report.total == 3 and [d.key for d in report.duplicate_addresses] == ["I0.0"] and not report.duplicate_names


# ---------------------------------------------------------------- 页面


def _page(tmp_path: Path, runner: Any = None) -> ToolsPage:
    page = ToolsPage(tmp_path, runner=runner or tool_actions.run_tool, opener=lambda root: Receipt("10:00", "打开高级工作台", "main.py gui --advanced", 0), threaded=False)
    page.set_projects([("DJ-1", "proj/DJ-1"), ("SW-1", "proj/SW-1")])
    return page


def _fill_create(page: ToolsPage) -> None:
    page.inputs["domain"].setCurrentIndex(page.inputs["domain"].findData("PLC"))
    page.inputs["nature"].setCurrentIndex(page.inputs["nature"].findData("REQ"))
    page.scope_boxes["LOCAL"].setChecked(True)
    for key, text in (("applicant", "张工"), ("background", "背景"), ("necessity", "必要")):
        page.inputs[key].setText(text)


def test_page_buttons_are_all_in_the_whitelist_and_none_is_forbidden(qapp: QApplication, tmp_path: Path) -> None:
    page = _page(tmp_path)
    texts = {b.text() for b in page.findChildren(QPushButton)}
    assert texts == tool_policy.TOOL_BUTTONS
    for text in texts:
        assert not any(word in text for word in tool_policy.TOOL_FORBIDDEN_WORDS), text
    assert policy.NEVER and set(policy.NEVER) <= set(tool_policy.TOOL_FORBIDDEN_WORDS)


# 工具页里能输入、能选的控件，一个不多一个不少（审计往页里塞一个游离输入框，这条要红）。
# 加字段是有意的改动：在 tool_actions.build_command 里加参数，同时改这份名单。
EXPECTED_CONTROLS = {
    # 看变更单、建变更单、转状态
    "tool_project", "tool_status", "tool_show_number",
    "tool_domain", "tool_nature", "tool_urgency", "tool_applicant", "tool_background", "tool_necessity", "tool_references",
    "tool_scope_LOCAL", "tool_scope_MODULE", "tool_scope_SYSTEM", "tool_scope_CROSS", "tool_scope_SAFE",
    "tool_number", "tool_to", "tool_comment", "tool_approver", "tool_verification_conclusion",
    # 看决策、变量表查重
    "tool_decision_change", "tool_decision_id", "tool_vartable_file",
    # 入箱（CHG-SCPT-2026-648）
    "tool_inbox_title", "tool_inbox_kind", "tool_inbox_change_action", "tool_inbox_original_words", "tool_inbox_affects",
    "tool_inbox_duplicate_check", "tool_inbox_duplicate_of", "tool_inbox_evidence", "tool_inbox_disposition",
    "tool_inbox_urgent_criterion", "tool_inbox_rationale", "tool_inbox_alternatives", "tool_inbox_cost_risk", "tool_inbox_asks",
    "tool_inbox_domain",
    "tool_inbox_scope_LOCAL", "tool_inbox_scope_MODULE", "tool_inbox_scope_SYSTEM", "tool_inbox_scope_CROSS", "tool_inbox_scope_SAFE",
    # 输出框（只读）
    "tool_output",
}
CONTROL_KINDS = (QLineEdit, QComboBox, QPlainTextEdit, QTextEdit, QAbstractSpinBox, QSlider, QDial, QCheckBox, QRadioButton)


def _controls(page: QWidget) -> list[QWidget]:
    found: list[QWidget] = []
    for kind in CONTROL_KINDS:
        found += page.findChildren(kind)
    return found


def _inside(widget: QWidget, name: str) -> bool:
    parent = widget.parentWidget()
    while parent is not None and parent.objectName() != name:
        parent = parent.parentWidget()
    return parent is not None


def test_page_controls_are_exactly_the_expected_list_and_all_in_forms(qapp: QApplication, tmp_path: Path) -> None:
    page = _page(tmp_path)
    controls = _controls(page)
    names = [w.objectName() for w in controls]
    assert sorted(names) == sorted(EXPECTED_CONTROLS), set(names) ^ EXPECTED_CONTROLS  # 多一个、少一个、重名都红
    for widget in controls:
        if widget is page.output:
            assert isinstance(widget, QPlainTextEdit) and widget.isReadOnly()  # 输出框只读，不是输入口
        else:
            assert _inside(widget, "tool_form"), widget.objectName()  # 其余全在 tool_form 框里（深色模式靠它着色）
    # 每个输入口都登记在页面里：能读到值的只有这几个，没有“看不见、读不到”的旁路
    registered = {id(w) for w in page.inputs.values()} | {id(w) for w in page.scope_boxes.values()} | {id(page.project_box), id(page.output)}
    registered |= {id(w) for w in page.inbox_scope_boxes.values()}
    assert {id(w) for w in controls} == registered


def test_transition_dropdown_never_offers_approval(qapp: QApplication, tmp_path: Path) -> None:
    box = _page(tmp_path).inputs["to"]
    assert isinstance(box, QComboBox)
    offered = {box.itemData(i) for i in range(box.count())}
    assert offered == set(tool_actions.CHANGE_TARGETS) and not offered & set(tool_actions.USER_ONLY_TARGETS)


def test_write_needs_a_preview_and_any_edit_voids_it(qapp: QApplication, tmp_path: Path) -> None:
    page = _page(tmp_path, runner=_Fake(0, "ok"))
    button = page.write_buttons["change_create"]
    assert not button.isEnabled()
    page.preview_command("change_create", page._create_params())  # 没填好：不开放
    assert not button.isEnabled() and "没法预览" in page.note.text()
    _fill_create(page)
    page.preview_command("change_create", page._create_params())
    assert button.isEnabled() and "main.py change create --pid DJ-1" in page.output.toPlainText()
    page.inputs["background"].setText("背景改了")
    assert not button.isEnabled() and page.preview is None


def test_previewed_write_runs_exactly_once(qapp: QApplication, tmp_path: Path) -> None:
    fake = _Fake(0, "已创建 CHG-DJ-2026-099")
    page = _page(tmp_path, runner=tool_actions.run_tool)
    # 换成假的子进程：run_tool 默认 runner 参数在定义时绑死了 subprocess.run，所以直接换页面的 runner
    page.runner = lambda root, key, params: tool_actions.run_tool(root, key, params, runner=fake)
    _fill_create(page)
    page.preview_command("change_create", page._create_params())
    page.run_preview()
    page.run_preview()  # 连点第二下：预览已用掉，不再写
    assert len(fake.calls) == 1 and fake.calls[0][0][5:7] == ["change", "create"]
    assert "已创建 CHG-DJ-2026-099" in page.output.toPlainText() and page.receipts[0].rc == 0


def test_failure_is_shown_not_swallowed(qapp: QApplication, tmp_path: Path) -> None:
    fake = _Fake(1, "", "错误: 决策包列表包含无效文件")
    page = _page(tmp_path)
    page.runner = lambda root, key, params: tool_actions.run_tool(root, key, params, runner=fake)
    page._dispatch(lambda: page.runner(tmp_path, "decision_list", {}), "decision_list")
    assert "无效文件" in page.output.toPlainText() and "rc 1" in page.output.toPlainText() and page.receipts[0].rc == 1


def test_missing_fields_show_a_note_and_start_nothing(qapp: QApplication, tmp_path: Path) -> None:
    fake = _Fake()
    page = _page(tmp_path)
    page.runner = lambda root, key, params: tool_actions.run_tool(root, key, params, runner=fake)
    page.run("change_show", {"pid": "DJ-1", "number": ""})
    assert "还没填" in page.note.text() and fake.calls == [] and page.receipts == []


def test_vartable_tool_shows_the_duplicate_report_above_the_raw_output(qapp: QApplication, tmp_path: Path) -> None:
    stdout = json.dumps({"success": True, "var_table": {"entries": [_entry("%I0.0", "A", 2), _entry("%I0.0", "B", 3)]}})
    fake = _Fake(0, stdout)
    page = _page(tmp_path)
    page.runner = lambda root, key, params: tool_actions.run_tool(root, key, params, runner=fake)
    page.inputs["vartable_file"].setText("/x/io_points.csv")
    page.check_duplicates()
    text = page.output.toPlainText()
    assert text.index("重复地址 1 组") < text.index("命令原样输出") and "vartable parse /x/io_points.csv" in text


def test_vartable_parse_failure_gives_no_report(qapp: QApplication, tmp_path: Path) -> None:
    fake = _Fake(2, "", "Error: File not found")
    page = _page(tmp_path)
    page.runner = lambda root, key, params: tool_actions.run_tool(root, key, params, runner=fake)
    page.inputs["vartable_file"].setText("/nope.csv")
    page.check_duplicates()
    assert "重复地址" not in page.output.toPlainText() and "File not found" in page.output.toPlainText()


def test_find_in_project_fills_the_path(qapp: QApplication, tmp_path: Path) -> None:
    (tmp_path / "proj" / "DJ-1" / "sub").mkdir(parents=True)
    table = tmp_path / "proj" / "DJ-1" / "sub" / "io_points.csv"
    table.write_text("x", encoding="utf-8")
    page = _page(tmp_path)
    page.find_in_project()
    assert page.inputs["vartable_file"].text() == str(table)
    page.project_box.setCurrentIndex(1)
    page.find_in_project()
    assert "没找到" in page.note.text()


def test_workbench_button_uses_the_opener_and_logs_a_receipt(qapp: QApplication, tmp_path: Path) -> None:
    page = _page(tmp_path)
    page.workbench_button.click()
    assert page.receipts[0].action == "打开高级工作台" and page.receipts[0].rc == 0


def test_project_choice_survives_a_refresh_and_empty_projects_are_handled(qapp: QApplication, tmp_path: Path) -> None:
    page = _page(tmp_path)
    page.project_box.setCurrentIndex(1)
    page.set_projects([("DJ-1", "a"), ("SW-1", "b")])
    assert page.pid() == "SW-1"
    page.set_projects([])
    assert page.pid() == ""
    page.run("change_list", {"pid": page.pid()})
    assert "还没填" in page.note.text()


def test_tabs_show_one_page_at_a_time(qapp: QApplication, tmp_path: Path) -> None:
    page = _page(tmp_path)
    page.show()
    for key in ("decision", "vartable", "inbox", "change"):
        page.select_tab(key)
        assert [name for name, widget in page.pages.items() if widget.isVisible()] == [key]


# ---------------------------------------------------------------- 入箱页签（CHG-SCPT-2026-648）


def _pick(box: Any, value: str) -> None:
    box.setCurrentIndex(box.findData(value))


def _fill_inbox(page: ToolsPage, words: str = "上料那段太慢了") -> None:
    for key, text in (("inbox_title", "上料节拍太慢"), ("inbox_affects", "上料工位"), ("inbox_duplicate_check", "查过，没有同类"),
                      ("inbox_rationale", "不挡手上的卡"), ("inbox_cost_risk", "半天")):
        page.inputs[key].setText(text)
    for key, text in (("inbox_original_words", words), ("inbox_evidence", "file:README.md"), ("inbox_alternatives", "先改定时器")):
        page.inputs[key].setPlainText(text)
    _pick(page.inputs["inbox_kind"], "iteration")
    _pick(page.inputs["inbox_disposition"], "after_current")


def test_inbox_dropdowns_offer_exactly_the_real_choices(qapp: QApplication, tmp_path: Path) -> None:
    page = _page(tmp_path)
    for key, allowed in (("inbox_kind", tool_actions.INBOX_KINDS), ("inbox_change_action", tool_actions.INBOX_ACTIONS),
                         ("inbox_disposition", tool_actions.INBOX_DISPOSITIONS), ("inbox_urgent_criterion", tool_actions.INBOX_CRITERIA),
                         ("inbox_domain", tool_actions.CHANGE_DOMAINS)):
        box = page.inputs[key]
        assert isinstance(box, QComboBox)
        assert [box.itemData(i) for i in range(box.count())] == ["", *allowed], key  # 第一项是空：不替你选
    assert set(page.inbox_scope_boxes) == set(tool_actions.CHANGE_SCOPES)


def test_the_board_never_fills_the_original_words(qapp: QApplication, tmp_path: Path) -> None:
    """“用户原话”只能由人亲手填（审计裁定）：页面打开、切项目、切页签、刷新项目、预览都不往里写字。"""
    page = _page(tmp_path, runner=_Fake(0, "ok"))
    words = page.inputs["inbox_original_words"]
    assert isinstance(words, QPlainTextEdit) and words.toPlainText() == ""
    page.select_tab("inbox")
    page.project_box.setCurrentIndex(1)
    page.set_projects([("DJ-1", "a"), ("SW-1", "b")])
    page.preview_command("inbox_add", page._inbox_params())
    assert words.toPlainText() == "" and page.preview is None and "还没填" in page.note.text()
    for key in ("inbox_evidence", "inbox_alternatives"):  # 取证、备选方案也不替你塞
        assert page.inputs[key].toPlainText() == ""
    typed = "  原话 里有两个空格\n第二行  "
    _fill_inbox(page, typed)
    assert page._inbox_params()["original_words"] == typed  # 原样交给命令


def test_inbox_preview_then_record_runs_once_and_edits_void_the_preview(qapp: QApplication, tmp_path: Path) -> None:
    fake = _Fake(0, '{"created": true}')
    page = _page(tmp_path)
    page.runner = lambda root, key, params: tool_actions.run_tool(root, key, params, runner=fake)
    stamps = iter(f"board-20261112T21{n:02d}00Z" for n in range(10))
    page.clock = lambda: next(stamps)
    button = page.write_buttons["inbox_add"]
    page.preview_command("inbox_add", page._inbox_params())  # 空表：不开放、不起进程
    assert not button.isEnabled() and fake.calls == []
    _fill_inbox(page)
    page.preview_command("inbox_add", page._inbox_params())
    assert button.isEnabled() and "main.py pm inbox add --project-id DJ-1 --request-id board-20261112T210100Z" in page.output.toPlainText()
    page.inputs["inbox_original_words"].setPlainText("改了一个字")
    assert not button.isEnabled() and page.preview is None
    page.preview_command("inbox_add", page._inbox_params())
    page.run_preview()
    page.run_preview()  # 连点：预览已用掉
    assert len(fake.calls) == 1
    argv = fake.calls[0][0][5:]
    assert argv[:3] == ["pm", "inbox", "add"] and argv[argv.index("--request-id") + 1] == "board-20261112T210200Z"
    assert argv[argv.index("--original-words") + 1] == "改了一个字" and page.receipts[0].rc == 0


def test_inbox_failure_shows_the_exit_code_and_output(qapp: QApplication, tmp_path: Path) -> None:
    fake = _Fake(1, "", "Error: 参数不合格")
    page = _page(tmp_path)
    page.runner = lambda root, key, params: tool_actions.run_tool(root, key, params, runner=fake)
    _fill_inbox(page)
    page.preview_command("inbox_add", page._inbox_params())
    page.run_preview()
    assert "rc 1" in page.output.toPlainText() and "参数不合格" in page.output.toPlainText() and page.receipts[0].rc == 1


@pytest.mark.usefixtures("identity_guard_off")
def test_inbox_add_really_records_a_proposed_item_the_decisions_page_can_read(qapp: QApplication, tmp_path: Path) -> None:
    """在临时账本上真跑一次看板拼出的整条命令（进程内跑真的命令行），条目是 PROPOSED，“决定”页的解析能读到它。"""
    from click.testing import CliRunner

    importlib.import_module("tests.cli.test_pm_facade")._setup_planning(tmp_path)
    cli = _cli()

    def in_process(command: list[str], **_kwargs: Any) -> Any:
        assert command[:5] == [sys.executable, "-B", str(tmp_path / "main.py"), "-w", str(tmp_path)]
        result = CliRunner().invoke(cli, command[3:])
        return subprocess.CompletedProcess(command, result.exit_code, result.output, "")

    page = _page(tmp_path)
    page.set_projects([("SW-TEST-001", "SW-TEST-001")])
    page.runner = lambda root, key, params: tool_actions.run_tool(root, key, params, runner=in_process)
    _fill_inbox(page, "登录页有时候是白的，刷新才好")
    _pick(page.inputs["inbox_domain"], "SCPT")  # 临时项目没有技术栈，命令要求写明领域
    page.preview_command("inbox_add", page._inbox_params())
    page.run_preview()
    assert page.receipts[0].rc == 0, page.output.toPlainText()
    listed = CliRunner().invoke(cli, ["-w", str(tmp_path), "pm", "inbox", "list", "--project-id", "SW-TEST-001"])
    items = json.loads(listed.output)["items"]
    assert [(i["status"], i["proposed_by"], i["ticket"]["original_words"]) for i in items] == [
        ("PROPOSED", "cockpit-board", "登录页有时候是白的，刷新才好")]
    targets = decisions.parse_inbox(listed.output, "SW-TEST-001")
    assert [t.item_id for t in targets] == [items[0]["item_id"]]
