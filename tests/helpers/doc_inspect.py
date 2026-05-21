"""python-docx helpers for asserting tracked-actions table and floating-action content."""
import io
import re
import docx

_SECTION_HEADING = "=== Tracked Actions ==="
_FLOATING_RE = re.compile(r"^AI-(\d+)\s+")


def load_doc(docx_bytes: bytes) -> docx.Document:
    return docx.Document(io.BytesIO(docx_bytes))


def floating_actions(document: docx.Document) -> list[dict]:
    """Return all floating-action paragraphs as parsed dicts."""
    result = []
    for para in document.paragraphs:
        text = para.text.strip()
        if not text.startswith("AI-"):
            continue
        parts = text.split(" | ")
        prefix = parts[0]
        m = re.match(r"^AI-(\d+)\s+(.*)", prefix)
        if not m:
            continue
        result.append({
            "id": int(m.group(1)),
            "assignee_token": m.group(2).strip(),
            "action": parts[1].strip() if len(parts) > 1 else None,
            "status": parts[2].strip() if len(parts) > 2 else None,
            "date_created": parts[3].strip() if len(parts) > 3 else None,
            "date_modified": parts[4].strip() if len(parts) > 4 else None,
            "_para_style": para.style.name,
            "_raw": text,
        })
    return result


def tracked_actions_table(document: docx.Document) -> list[dict] | None:
    """Return tracked-actions table rows as dicts, or None if section not found."""
    in_section = False
    for block in _iter_block_items(document):
        if hasattr(block, "text"):
            if block.text.strip() == _SECTION_HEADING:
                in_section = True
                continue
            if in_section and block.style.name.startswith("Heading"):
                break
        elif in_section and hasattr(block, "rows"):
            return _table_to_dicts(block)
    return None


def _table_to_dicts(table) -> list[dict]:
    headers = [cell.text.strip() for cell in table.rows[0].cells]
    result = []
    for row in table.rows[1:]:
        values = [cell.text.strip() for cell in row.cells]
        if all(v == "" for v in values):
            continue
        result.append(dict(zip(headers, values)))
    return result


def _iter_block_items(document):
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    body = document.element.body
    for child in body:
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def find_table_row(document: docx.Document, action_id: int) -> dict | None:
    rows = tracked_actions_table(document)
    if rows is None:
        return None
    for row in rows:
        raw_id = re.sub(r'^AI-', '', str(row.get("ID", "")))
        if raw_id == str(action_id):
            return row
    return None
