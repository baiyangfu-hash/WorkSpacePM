from auto_pm.infrastructure.doc.extractors.bridge_ast_extractor import BridgeAstExtractor
from auto_pm.infrastructure.doc.extractors.cli_ast_extractor import CliAstExtractor
from auto_pm.infrastructure.doc.extractors.gate_ast_extractor import GateAstExtractor
from auto_pm.infrastructure.doc.injector.marker_injector import MarkdownMarkerInjector


def test_cli_ast_extractor(tmp_path):
    cli_file = tmp_path / "test_cmd.py"
    cli_file.write_text('''
def cmd_run(arg1, arg2):
    """Run test command description."""
    pass
''', encoding="utf-8")
    cmds = CliAstExtractor.extract_from_directory(tmp_path)
    assert len(cmds) >= 1
    assert cmds[0].group == "test_cmd"
    assert "Run test command description" in cmds[0].doc

def test_bridge_ast_extractor(tmp_path):
    bridge_file = tmp_path / "system_bridge.py"
    bridge_file.write_text('''
class SystemBridge:
    def on_refresh(self, name):
        """Refresh system state."""
        pass
''', encoding="utf-8")
    methods = BridgeAstExtractor.extract_from_directory(tmp_path)
    assert len(methods) >= 1
    assert methods[0].bridge_name == "system_bridge"
    assert methods[0].method_name == "on_refresh"

def test_gate_ast_extractor(tmp_path):
    checker_file = tmp_path / "checker.py"
    checker_file.write_text('''
class Checker:
    def check_prds(self):
        """Check all PRD docs."""
        pass
''', encoding="utf-8")
    rules = GateAstExtractor.extract_from_checker(checker_file)
    assert len(rules) == 1
    assert rules[0].rule_id == "GATE-PRDS"

def test_marker_injector(tmp_path):
    doc_file = tmp_path / "test_doc.md"
    doc_file.write_text('''# Doc
<!-- AUTO_DOC_START: TEST_TAG -->
old content
<!-- AUTO_DOC_END: TEST_TAG -->
Footer
''', encoding="utf-8")
    ok, msg = MarkdownMarkerInjector.inject(doc_file, "TEST_TAG", "new injected table")
    assert ok is True
    content = doc_file.read_text(encoding="utf-8")
    assert "new injected table" in content
    assert "old content" not in content
    assert "Footer" in content
