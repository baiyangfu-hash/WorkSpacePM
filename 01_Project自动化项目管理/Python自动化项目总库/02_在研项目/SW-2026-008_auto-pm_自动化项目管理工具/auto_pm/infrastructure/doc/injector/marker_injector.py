"""Non-destructive marker-based Markdown injector."""
import re
from pathlib import Path


class MarkdownMarkerInjector:
    """Injects dynamic content between <!-- AUTO_DOC_START: <TAG> --> and <!-- AUTO_DOC_END: <TAG> -->."""

    @staticmethod
    def inject(file_path: Path, tag: str, new_content: str) -> tuple[bool, str]:
        if not file_path.exists():
            return False, f"Target file not found: {file_path}"

        text = file_path.read_text(encoding="utf-8")
        escaped_tag = re.escape(tag)
        start_pattern = rf"<!--\s*AUTO_DOC_START:\s*{escaped_tag}\s*-->"
        end_pattern = rf"<!--\s*AUTO_DOC_END:\s*{escaped_tag}\s*-->"

        full_pattern = rf"({start_pattern})(.*?)({end_pattern})"
        match = re.search(full_pattern, text, flags=re.DOTALL)

        if not match:
            return False, f"Marker tag '{tag}' not found in {file_path.name}"

        replacement = rf"\g<1>\n{new_content.strip()}\n\g<3>"
        updated_text = re.sub(full_pattern, replacement, text, flags=re.DOTALL)

        if updated_text != text:
            file_path.write_text(updated_text, encoding="utf-8")
            return True, f"Successfully injected '{tag}' into {file_path.name}"
        return True, f"Content unchanged for '{tag}' in {file_path.name}"
