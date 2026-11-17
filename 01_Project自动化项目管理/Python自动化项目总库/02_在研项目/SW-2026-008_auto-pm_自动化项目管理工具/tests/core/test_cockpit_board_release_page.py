"""发版页的“同意切换”（CHG-SCPT-2026-707）：候选版本从哪来、按钮什么时候能点、点了以后先写批准记录再跑哪条命令、结果怎么显示。

``release ship`` 用假的运行器，不碰真账本、不真换版本；输出格式按接口约定（CHG-SCPT-2026-706，
/mnt/project-files/release_ship_接口约定_20261117.md）。命令自己的护栏由 706 的测试管，这里只管看板这一侧。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton  # noqa: E402

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from cockpit_board import decisions, policy, release_ship  # noqa: E402
from cockpit_board.release_controller import (  # noqa: E402
    NO_APPROVER,
    NOT_ALLOWED,
    ReleaseController,
)
from cockpit_board.release_ship import Candidate, Check  # noqa: E402
from cockpit_board.widgets import release  # noqa: E402
from cockpit_board.widgets.release import ReleaseDialog, ReleasePage  # noqa: E402

from auto_pm.contracts.user_evidence import user_evidence_problem  # noqa: E402
from tests.core import test_pm_dashboard as base  # noqa: E402 - 复用假工作空间
from tests.core import test_pm_dashboard_gui as gui_tests  # noqa: E402 - 复用窗口工厂

NOW = datetime(2026, 11, 17, 2, 13, 3, tzinfo=UTC)
SESSION = "0123456789ab"
COMMIT = "abcdef0" + "1" * 33
RELEASE_ID = "1.3.3-abcdef0"
CANDIDATE = Candidate(RELEASE_ID, "abcdef0")


def _ship(**changes: Any) -> dict[str, Any]:
    """接口约定里只看模式的一份“能切”的输出；changes 改其中几格。"""
    data: dict[str, Any] = {
        "commit": COMMIT, "release_id": RELEASE_ID, "active_release": "1.3.3-1111111",
        "gate": {"state": "pass", "run_id": 1000001, "run_url": "https://github.com/o/r/actions/runs/1000001",
                 "verdict_path": f".auto-pm/release-candidates/{RELEASE_ID}/gate_verdict.json", "verdict_sha256": "ab" * 32,
                 "detail": ""},
        "audit": {"state": "present", "path": f".auto-pm/release-candidates/{RELEASE_ID}/audit_signoff.md", "detail": ""},
        "preflight": {"ok": True, "checks": [{"name": "控制根停在 main", "ok": True, "detail": ""},
                                             {"name": "没有开着的 Run", "ok": True, "detail": ""}]},
        "changes": [{"pr": 855, "title": "plc check 按用户实测补 5 条报红"}, {"pr": 849, "title": "工位止血"}],
        "can_switch": True, "deployed": False, "result": None,
    }
    data.update(changes)
    return data


def _check(**changes: Any) -> Check:
    return release_ship.parse_check(CANDIDATE, 0, json.dumps(_ship(**changes), ensure_ascii=False))


# ---- 纯函数 ------------------------------------------------------------------------------------------------


def test_candidates_are_release_id_folders_newest_first(tmp_path: Path) -> None:
    folder = tmp_path / release_ship.CANDIDATE_DIR
    for index, name in enumerate(("1.3.3-1234567", "1.3.3-abcdef0", "notes", "1.3.3-ABCDEF0", "1.3.3-abc")):
        (folder / name).mkdir(parents=True)
        stamp = NOW.timestamp() + index
        os.utime(folder / name, (stamp, stamp))
    (folder / "1.3.3-7654321").write_text("不是文件夹", encoding="utf-8")
    assert release_ship.list_candidates(tmp_path) == [Candidate("1.3.3-abcdef0", "abcdef0"), Candidate("1.3.3-1234567", "1234567")]
    assert release_ship.list_candidates(tmp_path / "没有") == [] and release_ship.list_candidates(None) == []


def test_the_page_runs_only_the_two_registered_shapes() -> None:
    ref = release_ship.confirm_ref(NOW, SESSION)
    check, switch = release_ship.check_args("ABCDEF0"), release_ship.switch_args(COMMIT, ref, "白")
    assert check == ("release", "ship", "abcdef0", "--json")
    assert switch == ("release", "ship", COMMIT, "--no-check-only", "--confirm-ref", ref, "--approver", "白", "--json")
    assert release_ship.allowed_command(check) and release_ship.allowed_command(switch)
    shapes = {len(shape): shape for shape in policy.RELEASE_COMMANDS}
    for args in (check, switch):  # 和 policy 登记的形状逐格对得上（尖括号那几格是变量）
        assert all(want.startswith("<") or want == got for want, got in zip(shapes[len(args)], args, strict=True))
    bad = [
        ("release", "ship", "abcdef0"),
        ("release", "ship", "abcdef0", "--json", "--force"),
        ("release", "deploy", "abcdef0", "--json"),
        ("release", "ship", "zzz", "--json"),
        (*switch[:5], "user-confirmation:gui-click-20261117", *switch[6:]),
        (*switch[:7], "--force", "--json"),
        (*switch[:7], " ", "--json"),
        (*switch[:3], "--check-only", *switch[4:]),
    ]
    for args in bad:
        assert not release_ship.allowed_command(args), args
    with pytest.raises(ValueError):
        release_ship.check_args("abc; rm")


def test_the_click_reference_has_the_contract_form_and_passes_the_user_evidence_check() -> None:
    ref = release_ship.confirm_ref(NOW, SESSION)
    assert ref == "user-confirmation:board-click:2026-11-17T02:13:03Z:0123456789ab"
    assert release_ship.is_confirm_ref(ref) and user_evidence_problem(ref) == ""
    phoenix = timezone(timedelta(hours=-7))  # 用户在凤凰城：本机时间换成 UTC 再写
    assert release_ship.confirm_ref(NOW.astimezone(phoenix), SESSION) == ref
    for wrong in ("user-confirmation:board-click:2026-11-17T02:13:03Z:xyz", "user-confirmation:board-click:昨天:0123456789ab",
                  "board-click:2026-11-17T02:13:03Z:0123456789ab"):
        assert not release_ship.is_confirm_ref(wrong), wrong
    with pytest.raises(ValueError):
        release_ship.confirm_ref(NOW, "claude")


def test_output_it_cannot_read_is_named_not_guessed() -> None:
    for stdout in ("", "这不是 JSON", "[1, 2]", json.dumps({"release_id": RELEASE_ID, "gate": {}}),
                   json.dumps(_ship(release_id="1.3.3-9999999"))):
        check = release_ship.parse_check(CANDIDATE, 0, stdout)
        assert check.problem and not check.can_switch, stdout
        assert release_ship.blocked_reason(check).startswith("检查结论没读懂："), stdout
    check = _check()
    assert not check.problem and check.can_switch and check.commit == COMMIT
    assert release_ship.change_lines(check) == ["#855 plc check 按用户实测补 5 条报红", "#849 工位止血"]
    assert release_ship.gate_text(check) == "判决 PASS · 运行 1000001"


def test_the_button_is_grey_for_the_first_missing_condition_in_order() -> None:
    assert release_ship.blocked_reason(_check()) == ""
    assert release_ship.blocked_reason(_check(), human_block="带 AI 标记") == "带 AI 标记"
    assert release_ship.blocked_reason(_check(), busy=True).startswith("上一次切换还在跑")
    assert release_ship.blocked_reason(None).startswith("还没读到")
    cases: dict[str, list[dict[str, Any]]] = {
        "已经是现在生效的版本": [{"deployed": True}, {"active_release": RELEASE_ID}],
        "门禁没有 PASS 判决：判决 FAIL": [{"gate": {"state": "fail"}}],
        "门禁没有 PASS 判决：没有判决": [{"gate": {"state": "missing"}}],
        "门禁没有 PASS 判决：（没写）": [{"gate": {}}],
        "门禁没有 PASS 判决：门禁还在跑": [{"gate": {"state": "running"}}],
        "审计还没放行：还没有审计放行记录": [{"audit": {"state": "missing"}}],
        "预检没过：没有开着的 Run": [{"preflight": {"ok": False, "checks": [{"name": "控制根停在 main", "ok": True},
                                                                           {"name": "没有开着的 Run", "ok": False}]}}],
        "预检没过：命令没说是哪一项": [{"preflight": {}}],
        "release ship 说现在不能切": [{"can_switch": False}, {"can_switch": "true"}],
        "命令没给出完整的提交号": [{"commit": "abc"}, {"commit": ""}],
        "命令说的提交号": [{"commit": "1234567" + "0" * 33}],
    }
    for want, variants in cases.items():
        for change in variants:
            assert release_ship.blocked_reason(_check(**change)).startswith(want), (want, change)
    # 门禁没过时，就算审计也没放行，先说门禁（只说差的第一条）
    assert release_ship.blocked_reason(_check(gate={"state": "fail"}, audit={"state": "missing"})).startswith("门禁")


def test_result_says_switched_rolled_back_or_needs_a_person() -> None:
    assert release_ship.result_text({"ok": True, "message": "已换成 1.3.3-abcdef0"}, 0) == ("切换成了：已换成 1.3.3-abcdef0", "ok")
    assert release_ship.result_text({"ok": False, "rolled_back": True}, 3) == ("没切成，已自动退回旧版本", "risk")
    text, sev = release_ship.result_text({"ok": False, "rolled_back": False, "message": "指针写坏"}, 4)
    assert sev == "block" and "要人处理" in text and "指针写坏" in text and "退出码 4" in text
    assert release_ship.result_text(None, 1)[1] == "block"
    # 命令自己再判一遍没过（退出码 2，deployed false）：版本没动，不说成“没能退回”
    refused = {"ok": False, "rolled_back": False, "message": "预检没过，什么都没写"}
    assert release_ship.result_text(refused, 2, deployed=False) == ("没切成，命令再判一遍没过，版本没动：预检没过，什么都没写", "risk")


def test_policy_names_why_this_page_may_say_agree_and_switch() -> None:
    """PM_FORBIDDEN_WORDS 里有“同意”“切换”：这一页是唯一例外，来由和护栏写在 policy.py，按钮字也不出现 NEVER 里的词。"""
    source = (SCRIPTS / "cockpit_board" / "policy.py").read_text(encoding="utf-8")
    assert "同意" in policy.PM_FORBIDDEN_WORDS and "切换" in policy.PM_FORBIDDEN_WORDS
    assert "RELEASE_BUTTONS" in source and "唯一例外" in source and "CHG-SCPT-2026-707" in source
    for guard in ("AI 标记", "检查结果", "RELEASE_COMMANDS", "批准记录", "回执"):
        assert guard in source, guard
    for text in (*policy.RELEASE_BUTTONS, policy.RELEASE_BUTTON_PREFIX + RELEASE_ID):
        assert not any(word in text for word in policy.NEVER), text
    assert release_ship.SWITCH_PREFIX == policy.RELEASE_BUTTON_PREFIX


def test_the_command_map_says_ship_is_user_only() -> None:
    """release ship 和 release deploy 一样是 user_only：只在用户本人打开的看板跑（命令登记由 706 做，项目经理 2026-11-17 定）。"""
    commands = json.loads((SCRIPTS / "cockpit_board" / "flow" / "commands_map.json").read_text(encoding="utf-8"))["commands"]
    assert commands["release ship"]["class"] == "user_only" == commands["release deploy"]["class"]


def test_only_the_agree_button_can_carry_the_switch_flag_the_reference_and_the_approver() -> None:
    """整个看板里，带 --no-check-only、--confirm-ref、--approver 的 release ship 只有一处能拼出来（release_ship.switch_args），
    只有 release_controller.switch 调它，而那里先查 AI 标记、再判 blocked_reason、再写批准记录。"""
    check, switch = policy.RELEASE_COMMANDS
    assert not {"--no-check-only", "--confirm-ref", "--approver"} & set(check)
    assert {"--no-check-only", "--confirm-ref", "--approver"} <= set(switch)
    package = SCRIPTS / "cockpit_board"
    for path in package.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if path.name not in ("release_ship.py", "policy.py"):
            assert "--no-check-only" not in source and "--confirm-ref" not in source, path.name
        if path.name not in ("release_ship.py", "release_controller.py", "release.py"):
            assert "switch_args(" not in source, path.name
    controller = (package / "release_controller.py").read_text(encoding="utf-8")
    assert controller.count("switch_args(") == 1
    body = controller.split("def switch(", 1)[1].split("\n    def ", 1)[0]
    order = [body.index(word) for word in ("human_only_block", "blocked_reason", "switch_args(", "allowed_command",
                                          "record_board_approval", "run_cli")]
    assert order == sorted(order)
    page = (package / "widgets" / "release.py").read_text(encoding="utf-8")
    assert "REF_PLACEHOLDER" in page.split("switch_args(", 1)[1].split("\n", 1)[0]  # 页上只拼带占位的“等价命令”给人看


def test_the_approval_line_names_who_when_and_what_they_saw(tmp_path: Path) -> None:
    ref = release_ship.confirm_ref(NOW, SESSION)
    record = release_ship.approval_record(_check(), ref, "白", NOW, SESSION)
    assert record == {"kind": "release_ship_switch", "confirm_ref": ref, "approver": "白", "clicked_at": "2026-11-17T02:13:03Z",
                      "session": SESSION, "release_id": RELEASE_ID, "commit": COMMIT, "active_release": "1.3.3-1111111",
                      "gate_state": "pass", "gate_run_id": 1000001, "verdict_sha256": "ab" * 32, "audit_state": "present",
                      "audit_path": f".auto-pm/release-candidates/{RELEASE_ID}/audit_signoff.md"}
    from cockpit_board import actions

    path = actions.record_board_approval(tmp_path, release_ship.APPROVAL_RECORD, record)
    path.write_bytes(path.read_bytes().rstrip(b"\n"))  # 上一行没有换行结尾：追加时先补一个
    actions.record_board_approval(tmp_path, release_ship.APPROVAL_RECORD, {**record, "approver": "黑"})
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["approver"] for line in lines] == ["白", "黑"]
    assert release_ship.APPROVAL_RECORD.parts[:2] == (".auto-pm", "reports")  # .auto-pm/reports/ 已被忽略，不会被误提交


# ---- 页面和控制器 -------------------------------------------------------------------------------------------


class FakeShip:
    """假的 subprocess.run：只看模式回 ``_ship()``；真发版回 ``switch_out``，并记下那一刻批准记录里有几行。"""

    def __init__(self, root: Path, switch_rc: int = 0, switch_result: dict[str, Any] | None = None) -> None:
        self.root, self.switch_rc = root, switch_rc
        self.switch_result = switch_result if switch_result is not None else {"ok": True, "rolled_back": False, "message": ""}
        self.calls: list[list[str]] = []
        self.record_at_switch: list[str] = []
        self.check_out = _ship()

    def __call__(self, command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        args = command[3:]  # [python, -B, main.py, ...]
        self.calls.append(args)
        if "--no-check-only" in args:
            path = self.root / release_ship.APPROVAL_RECORD
            self.record_at_switch = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
            out = {**_ship(), "deployed": self.switch_rc != 2, "result": self.switch_result}
            return subprocess.CompletedProcess(command, self.switch_rc, json.dumps(out, ensure_ascii=False), "")
        return subprocess.CompletedProcess(command, 0, json.dumps(self.check_out, ensure_ascii=False), "")


def _root(tmp_path: Path) -> Path:
    (tmp_path / release_ship.CANDIDATE_DIR / RELEASE_ID).mkdir(parents=True)
    return tmp_path


def _wait(controller: ReleaseController, qapp: QApplication) -> None:
    for _ in range(200):
        for job in list(controller._jobs):
            job.wait(2000)
        qapp.processEvents()
        if not controller._jobs:
            break
    qapp.processEvents()


def _setup(qapp: QApplication, tmp_path: Path, markers: tuple[str, ...] | None = (), **fake: Any
           ) -> tuple[ReleasePage, ReleaseController, FakeShip]:
    root = _root(tmp_path)
    ship = FakeShip(root, **fake)
    page = ReleasePage(root, lambda: markers, lambda _text: None, lambda: "白")
    controller = ReleaseController(page, root, ship, now=lambda: NOW, markers=lambda: markers, session=SESSION)
    controller.refresh()
    _wait(controller, qapp)
    return page, controller, ship


def _switch_button(page: ReleasePage) -> QPushButton:
    found: QPushButton = next(b for b in page.findChildren(QPushButton) if b.property("release_action") == "switch")
    return found


def _labels(page: Any) -> list[str]:
    return [label.text() for label in page.findChildren(QLabel)]


def test_without_candidates_or_root_there_is_no_button(qapp: QApplication, tmp_path: Path) -> None:
    assert not ReleasePage().findChildren(QPushButton)
    page = ReleasePage(tmp_path, lambda: (), lambda _text: None)
    controller = ReleaseController(page, tmp_path, FakeShip(tmp_path), markers=lambda: ())
    controller.refresh()
    assert not controller._jobs and not page.findChildren(QPushButton)
    assert release.NO_CANDIDATES in _labels(page)


def test_a_passing_candidate_shows_what_changed_and_the_switch_button(qapp: QApplication, tmp_path: Path) -> None:
    page, _controller, ship = _setup(qapp, tmp_path)
    assert ship.calls == [["release", "ship", "abcdef0", "--json"]]
    button = _switch_button(page)
    assert button.isEnabled() and button.text() == "同意切换到 " + RELEASE_ID
    texts = _labels(page)
    for want in ("判决 PASS · 运行 1000001", "审计已放行（有放行记录）", "1.3.3-1111111", "✓ 没有开着的 Run"):
        assert want in texts, want
    assert any("#855 plc check 按用户实测补 5 条报红" in text for text in texts)
    for item in page.findChildren(QPushButton):
        assert item.text() in policy.RELEASE_BUTTONS or item.text().startswith(policy.RELEASE_BUTTON_PREFIX), item.text()
        assert not any(word in (item.text() + item.toolTip()) for word in policy.NEVER), item.text()


def test_no_verdict_or_no_audit_greys_the_button_and_says_why(qapp: QApplication, tmp_path: Path) -> None:
    root = _root(tmp_path)
    for change, want in (({"gate": {"state": "missing"}}, "门禁没有 PASS 判决：没有判决"),
                         ({"audit": {"state": "missing"}}, "审计还没放行：还没有审计放行记录")):
        ship = FakeShip(root)
        ship.check_out = _ship(**change)
        page = ReleasePage(root, lambda: (), lambda _text: None, lambda: "白")
        controller = ReleaseController(page, root, ship, now=lambda: NOW, markers=lambda: (), session=SESSION)
        controller.refresh()
        _wait(controller, qapp)
        assert not _switch_button(page).isEnabled()
        reasons = [label.text() for label in page.findChildren(QLabel) if label.property("blocked_reason") == RELEASE_ID]
        assert reasons == [want]
        controller.switch(RELEASE_ID, "白")  # 绕过按钮直接调进来：照样不运行
        _wait(controller, qapp)
        assert all("--no-check-only" not in call for call in ship.calls)
        assert not (root / release_ship.APPROVAL_RECORD).exists()


@pytest.mark.parametrize("markers", [("CLAUDECODE",), None])
def test_with_an_ai_marker_or_unknown_the_button_is_grey_and_nothing_runs(qapp: QApplication, tmp_path: Path,
                                                                          markers: tuple[str, ...] | None) -> None:
    page, controller, ship = _setup(qapp, tmp_path, markers)
    assert ship.calls == []  # release ship 是 user_only：带标记的看板连只看那条也不跑
    assert "没跑 release ship（只看那条也只许你本人打开的看板跑）" in _labels(page)
    assert not _switch_button(page).isEnabled()
    reasons = [label.text() for label in page.findChildren(QLabel) if label.property("blocked_reason") == RELEASE_ID]
    assert reasons == [decisions.human_only_block(markers)]
    page.checks[RELEASE_ID] = _check()  # 就算结论是从别处塞进来的：按钮、确认框、运行入口照样都拦
    page.render_ship()
    assert not _switch_button(page).isEnabled()
    dialog = page.open_dialog(RELEASE_ID, run=False)  # 就算从别处直接打开确认框：确认键也灰着
    assert isinstance(dialog, ReleaseDialog) and dialog.blocked and not dialog.run_button.isEnabled()
    controller.switch(RELEASE_ID, "白")
    _wait(controller, qapp)
    assert ship.calls == []
    assert not (tmp_path / release_ship.APPROVAL_RECORD).exists()
    assert "未运行" in page.receipts[-1].command and page.receipts[-1].output == decisions.human_only_block(markers)


def test_the_dialog_shows_the_facts_the_approver_and_the_command(qapp: QApplication, tmp_path: Path) -> None:
    page, _controller, _ship = _setup(qapp, tmp_path)
    dialog = page.open_dialog(RELEASE_ID, run=False)
    assert isinstance(dialog, ReleaseDialog) and dialog.run_button.isEnabled() and dialog.approver() == "白"
    texts = " ".join(_labels(dialog))
    assert RELEASE_ID in texts and COMMIT in texts and "判决 PASS" in texts and "#849 工位止血" in texts
    assert dialog.command_text == release_ship.shown_command(
        ("release", "ship", COMMIT, "--no-check-only", "--confirm-ref", release_ship.REF_PLACEHOLDER, "--approver", "白", "--json"))
    dialog.approver_input.setText("  ")
    assert not dialog.run_button.isEnabled() and "<批准人>" in dialog.command_text
    dialog.approver_input.setText("黑")
    assert dialog.run_button.isEnabled() and dialog.command_text.endswith("--approver 黑 --json")


def test_a_click_records_first_shows_a_running_receipt_then_the_result(qapp: QApplication, tmp_path: Path) -> None:
    page, controller, ship = _setup(qapp, tmp_path)
    page.switch_requested.emit(RELEASE_ID, "白")
    # 点下去马上有回音（#851 同样的修法）：命令还没跑完，页上已经有“正在运行”的回执，按钮也灰了
    assert page.receipts[-1].rc is None and page.receipts[-1].output == release.RUNNING
    assert release.RUNNING in _labels(page) and not _switch_button(page).isEnabled()
    _wait(controller, qapp)
    ref = release_ship.confirm_ref(NOW, SESSION)
    switch = ["release", "ship", COMMIT, "--no-check-only", "--confirm-ref", ref, "--approver", "白", "--json"]
    assert ship.calls == [["release", "ship", "abcdef0", "--json"], switch, ["release", "ship", "abcdef0", "--json"]]
    assert [json.loads(line)["confirm_ref"] for line in ship.record_at_switch] == [ref]  # 运行那一刻批准记录已经写好
    assert page.results_text[RELEASE_ID] == ("切换成了", "ok")
    bars = [frame for frame in page.findChildren(QLabel) if frame.text() == "切换成了"]
    assert bars, "切换结果没画在页上"


def test_a_rolled_back_switch_says_so_on_the_page(qapp: QApplication, tmp_path: Path) -> None:
    page, controller, _ship = _setup(qapp, tmp_path, switch_rc=3,
                                     switch_result={"ok": False, "rolled_back": True, "message": "演练没过"})
    controller.switch(RELEASE_ID, "白")
    _wait(controller, qapp)
    assert page.results_text[RELEASE_ID] == ("没切成，已自动退回旧版本：演练没过", "risk")
    assert "没切成，已自动退回旧版本：演练没过" in _labels(page)
    assert page.receipts[-1].rc == 3


def test_if_the_approval_record_cannot_be_written_nothing_runs(qapp: QApplication, tmp_path: Path) -> None:
    page, controller, ship = _setup(qapp, tmp_path)
    (tmp_path / release_ship.APPROVAL_RECORD.parent.parent).mkdir(parents=True)
    (tmp_path / release_ship.APPROVAL_RECORD.parent).write_text("挡路的文件", encoding="utf-8")  # 记录的文件夹建不出来
    controller.switch(RELEASE_ID, "白")
    _wait(controller, qapp)
    assert all("--no-check-only" not in call for call in ship.calls)
    assert page.receipts[-1].output.startswith("批准记录没写成，不运行") and "未运行" in page.receipts[-1].command


def test_a_missing_or_unsafe_approver_or_an_unlisted_shape_does_not_run(qapp: QApplication, tmp_path: Path,
                                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    page, controller, ship = _setup(qapp, tmp_path)
    for approver, want in (("", NO_APPROVER), ("白\n--force", "不能用的字符"), ("-x", NOT_ALLOWED)):
        controller.switch(RELEASE_ID, approver)
        _wait(controller, qapp)
        assert want in page.receipts[-1].output, approver
    assert all("--no-check-only" not in call for call in ship.calls)
    assert not (tmp_path / release_ship.APPROVAL_RECORD).exists()


def test_a_recheck_asked_while_checking_is_not_dropped(qapp: QApplication, tmp_path: Path) -> None:
    page, controller, ship = _setup(qapp, tmp_path)
    controller.refresh()
    controller.refresh()  # 上一轮还没查完：记下，查完再查一次
    _wait(controller, qapp)
    _wait(controller, qapp)
    assert ship.calls.count(["release", "ship", "abcdef0", "--json"]) == 3
    assert not page.checking


def test_the_window_checks_candidates_when_the_release_page_opens(qapp: QApplication, tmp_path: Path) -> None:
    root, db = base._workspace(tmp_path, [("DJ-2026-101", "ACTIVE", "写通讯层", 0.1)])
    _root(root)
    ship = FakeShip(root)

    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if command[3:5] == ["release", "ship"]:
            return ship(command, **kwargs)
        return subprocess.CompletedProcess(command, 0, json.dumps({"tasks": []}), "")

    window = gui_tests._window(qapp, root, db, read_runner=runner)
    window.release_actions.markers = lambda: ()
    window.release.markers = lambda: ()
    window.decisions.page.approver_input.setText("白")
    window.goto("release")
    _wait(window.release_actions, qapp)
    for thread in list(window._threads):
        thread.wait(5000)
    qapp.processEvents()
    assert ship.calls == [["release", "ship", "abcdef0", "--json"]]
    button = _switch_button(window.release)
    assert button.isEnabled()
    dialog = window.release.open_dialog(RELEASE_ID, run=False)
    assert dialog is not None and dialog.approver() == "白"  # 批准人默认取“决定”页填的名字
    window.close()
