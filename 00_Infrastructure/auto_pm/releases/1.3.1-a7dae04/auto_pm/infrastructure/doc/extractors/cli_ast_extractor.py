"""Static AST extractor for CLI command modules."""
import ast
from pathlib import Path

from auto_pm.domain.doc.models import CliCommandDTO


class CliAstExtractor:
    """Extracts CLI commands statically via Python AST without importing modules."""

    @staticmethod
    def extract_from_directory(cli_dir: Path) -> list[CliCommandDTO]:
        commands: list[CliCommandDTO] = []
        if not cli_dir.exists():
            return commands

        for file_path in sorted(cli_dir.glob("*.py")):
            if file_path.name.startswith("__"):
                continue
            group_name = file_path.stem
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content, filename=str(file_path))
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        # Detect CLI command functions (e.g., cmd_*, handle_*, or decorated functions)
                        fn_name = node.name
                        if fn_name.startswith("cmd_") or fn_name.startswith("handle_") or fn_name == "main":
                            clean_name = fn_name.replace("cmd_", "").replace("handle_", "")
                            doc = ast.get_docstring(node) or f"{clean_name} command in {group_name}"
                            first_line_doc = doc.strip().split("\n")[0]
                            args = [arg.arg for arg in node.args.args if arg.arg not in ("self", "cls")]
                            commands.append(CliCommandDTO(
                                name=f"{group_name} {clean_name}" if clean_name != "main" else group_name,
                                group=group_name,
                                doc=first_line_doc,
                                args=args,
                                file_source=file_path.name
                            ))
            except Exception:
                continue

        # Fallback if specific cmd_ naming is not used: record the group module itself
        if not commands:
            for file_path in sorted(cli_dir.glob("*.py")):
                if not file_path.name.startswith("__"):
                    commands.append(CliCommandDTO(
                        name=file_path.stem,
                        group=file_path.stem,
                        doc=f"{file_path.stem} CLI operations",
                        file_source=file_path.name
                    ))
        return commands
