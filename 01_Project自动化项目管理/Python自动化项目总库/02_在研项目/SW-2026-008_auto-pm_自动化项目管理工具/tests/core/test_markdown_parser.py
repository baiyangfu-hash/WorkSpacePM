"""单元测试：Markdown 结构化解析器 (markdown_parser)"""
from __future__ import annotations

from auto_pm.infrastructure.utils.markdown_parser import parse_markdown_to_blocks


def test_parse_headers() -> None:
    content = """
# Heading 1
## Heading 2
### Heading 3
    """
    blocks = parse_markdown_to_blocks(content)
    assert len(blocks) == 3
    assert blocks[0] == {"type": "h1", "text": "Heading 1", "anchor": "heading-1"}
    assert blocks[1] == {"type": "h2", "text": "Heading 2", "anchor": "heading-2"}
    assert blocks[2] == {"type": "h3", "text": "Heading 3", "anchor": "heading-3"}

def test_parse_paragraphs() -> None:
    content = """
Hello World.
This is a paragraph.

Another paragraph.
    """
    blocks = parse_markdown_to_blocks(content)
    assert len(blocks) == 2
    assert blocks[0]["type"] == "paragraph"
    assert "<p>Hello World.\nThis is a paragraph.</p>" in blocks[0]["html"]
    assert blocks[1]["type"] == "paragraph"
    assert "<p>Another paragraph.</p>" in blocks[1]["html"]

def test_parse_code_blocks() -> None:
    content = """
```python
def test() -> None:
    pass
```
    """
    blocks = parse_markdown_to_blocks(content)
    assert len(blocks) == 1
    assert blocks[0] == {
        "type": "code",
        "lang": "python",
        "code": "def test() -> None:\n    pass"
    }

def test_parse_alerts() -> None:
    content = """
> [!NOTE]
> This is a note alert.

> [!WARNING]
> Warning content.
    """
    blocks = parse_markdown_to_blocks(content)
    assert len(blocks) == 2
    assert blocks[0]["type"] == "alert"
    assert blocks[0]["alert_type"] == "note"
    assert "This is a note alert." in blocks[0]["html"]

    assert blocks[1]["type"] == "alert"
    assert blocks[1]["alert_type"] == "warning"
    assert "Warning content." in blocks[1]["html"]

def test_parse_tables() -> None:
    content = """
| Col A | Col B |
|---|---|
| A1 | B1 |
    """
    blocks = parse_markdown_to_blocks(content)
    assert len(blocks) == 1
    assert blocks[0]["type"] == "table"
    assert "<table>" in blocks[0]["html"]
    assert "<th>Col A</th>" in blocks[0]["html"]
    assert "<td>A1</td>" in blocks[0]["html"]
