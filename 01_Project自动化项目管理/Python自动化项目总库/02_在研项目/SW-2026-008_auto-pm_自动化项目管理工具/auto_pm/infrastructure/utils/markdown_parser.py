"""Markdown 结构化解析器 (Structural Markdown Parser)

将 Markdown 文本解析为结构化的 JSON Block 块，用于 QML 端的动态委托渲染。
"""

from typing import Any

import markdown


def parse_markdown_to_blocks(content: str) -> list[dict[str, Any]]:
    if not content:
        return []

    lines = content.splitlines()
    blocks = []

    in_code_block = False
    code_lang = ""
    code_lines: list[str] = []

    in_table = False
    table_lines: list[str] = []

    in_quote = False
    quote_type = "quote"
    quote_lines: list[str] = []

    current_paragraph: list[str] = []

    def flush_paragraph() -> None:
        nonlocal current_paragraph
        if current_paragraph:
            text = "\n".join(current_paragraph).strip()
            if text:
                # 将段落内部 Markdown 转换为 HTML 富文本，以便 QML 渲染链接、粗体、小列表等
                html = markdown.markdown(text, extensions=["extra"])
                blocks.append({"type": "paragraph", "html": html})
            current_paragraph = []

    def flush_table() -> None:
        nonlocal in_table, table_lines
        if in_table and table_lines:
            table_md = "\n".join(table_lines)
            html = markdown.markdown(table_md, extensions=["extra"])
            blocks.append({"type": "table", "html": html})
            table_lines = []
            in_table = False

    def flush_quote() -> None:
        nonlocal in_quote, quote_lines, quote_type
        if in_quote and quote_lines:
            text = "\n".join(quote_lines).strip()
            if text:
                html = markdown.markdown(text, extensions=["extra"])
                if quote_type != "quote":
                    blocks.append({"type": "alert", "alert_type": quote_type, "html": html})
                else:
                    blocks.append({"type": "blockquote", "html": html})
            quote_lines = []
            in_quote = False
            quote_type = "quote"

    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]

        # 1. Code block handling
        if line.strip().startswith("```"):
            if in_code_block:
                code_text = "\n".join(code_lines)
                blocks.append({"type": "code", "lang": code_lang or "text", "code": code_text})
                code_lines = []
                in_code_block = False
            else:
                flush_paragraph()
                flush_table()
                flush_quote()
                in_code_block = True
                code_lang = line.strip()[3:].strip()
            i += 1
            continue

        if in_code_block:
            code_lines.append(line)
            i += 1
            continue

        # 2. Table handling
        is_table_line = line.strip().startswith("|") or (
            line.strip()
            and "|" in line
            and (i + 1 < n and ("---" in lines[i + 1] or ":" in lines[i + 1]))
        )
        if is_table_line:
            if not in_table:
                flush_paragraph()
                flush_quote()
                in_table = True
            table_lines.append(line)
            i += 1
            continue
        elif in_table:
            flush_table()

        # 3. Blockquotes / Alerts
        if line.strip().startswith(">"):
            if not in_quote:
                flush_paragraph()
                flush_table()
                in_quote = True
                match_line = line.strip().lstrip(">").strip()
                if match_line.startswith("[!") and match_line.endswith("]"):
                    alert_tag = match_line[2:-1].lower()
                    if alert_tag in ("note", "tip", "important", "warning", "caution"):
                        quote_type = alert_tag
                    else:
                        quote_type = "quote"
                        quote_lines.append(line.lstrip("> ").strip())
                else:
                    quote_type = "quote"
                    quote_lines.append(line.lstrip("> ").strip())
            else:
                quote_lines.append(line.lstrip("> ").strip())
            i += 1
            continue
        elif in_quote:
            flush_quote()

        # 4. Headers
        if line.strip().startswith("#"):
            flush_paragraph()
            flush_table()
            flush_quote()

            stripped = line.strip()
            level = 0
            while level < len(stripped) and stripped[level] == "#":
                level += 1

            title_text = stripped[level:].strip()
            if 1 <= level <= 6:
                blocks.append(
                    {
                        "type": f"h{level}",
                        "text": title_text,
                        "anchor": title_text.lower()
                        .replace(" ", "-")
                        .replace("/", "")
                        .replace("(", "")
                        .replace(")", ""),
                    }
                )
            else:
                current_paragraph.append(line)
            i += 1
            continue

        # 5. Empty lines
        if not line.strip():
            flush_paragraph()
            flush_table()
            flush_quote()
            i += 1
            continue

        # 6. Paragraph lines
        current_paragraph.append(line)
        i += 1

    flush_paragraph()
    flush_table()
    flush_quote()

    return blocks
