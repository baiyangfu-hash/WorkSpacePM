"""Static AST extractor for PLC gatekeeper checker methods."""

import ast
from pathlib import Path

from auto_pm.domain.doc.models import GateRuleDTO


class GateAstExtractor:
    """Extracts PlcChecker gate rules statically."""

    @staticmethod
    def extract_from_checker(checker_file: Path) -> list[GateRuleDTO]:
        rules: list[GateRuleDTO] = []
        if not checker_file.exists():
            return rules

        try:
            content = checker_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content, filename=str(checker_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name.startswith("check_"):
                    rule_name = node.name.replace("check_", "")
                    doc = ast.get_docstring(node) or f"Check {rule_name}"
                    first_line_doc = doc.strip().split("\n")[0]
                    rules.append(
                        GateRuleDTO(
                            rule_id=f"GATE-{rule_name.upper()}",
                            rule_name=rule_name,
                            category="PLC_GATE",
                            doc=first_line_doc,
                        )
                    )
        except Exception:
            pass
        return rules
