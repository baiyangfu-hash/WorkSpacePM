"""Static AST extractor for QML QObject Bridges."""

import ast
from pathlib import Path

from auto_pm.domain.doc.models import BridgeMethodDTO


class BridgeAstExtractor:
    """Extracts PyQt6 QML Bridge slots and signals statically."""

    @staticmethod
    def extract_from_directory(bridges_dir: Path) -> list[BridgeMethodDTO]:
        methods: list[BridgeMethodDTO] = []
        if not bridges_dir.exists():
            return methods

        for file_path in sorted(bridges_dir.glob("*_bridge.py")):
            bridge_name = file_path.stem
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content, filename=str(file_path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        is_slot = False
                        is_signal = False
                        for dec in node.decorator_list:
                            dec_id = ""
                            if isinstance(dec, ast.Name):
                                dec_id = dec.id
                            elif isinstance(dec, ast.Attribute):
                                dec_id = dec.attr
                            elif isinstance(dec, ast.Call):
                                if isinstance(dec.func, ast.Name):
                                    dec_id = dec.func.id
                                elif isinstance(dec.func, ast.Attribute):
                                    dec_id = dec.func.attr
                            if "Slot" in dec_id or "pyqtSlot" in dec_id:
                                is_slot = True
                            elif "Signal" in dec_id or "pyqtSignal" in dec_id:
                                is_signal = True

                        if (
                            is_slot
                            or is_signal
                            or node.name.startswith("on_")
                            or node.name.startswith("get_")
                        ):
                            doc = ast.get_docstring(node) or ""
                            first_line_doc = (
                                doc.strip().split("\n")[0] if doc else f"{node.name} API"
                            )
                            args = [
                                arg.arg for arg in node.args.args if arg.arg not in ("self", "cls")
                            ]
                            methods.append(
                                BridgeMethodDTO(
                                    bridge_name=bridge_name,
                                    method_name=node.name,
                                    args=args,
                                    is_slot=is_slot or not is_signal,
                                    is_signal=is_signal,
                                    doc=first_line_doc,
                                )
                            )
            except Exception:
                continue
        return methods
