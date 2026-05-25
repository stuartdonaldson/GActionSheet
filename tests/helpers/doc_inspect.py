"""python-docx helpers for asserting tracked-actions table and floating-action content."""
import io
import re
import docx
from docx.oxml.ns import qn

_SECTION_HEADING = "=== Tracked Actions ==="
_STATUS_RE = re.compile(r'\(([^)]*)\)\s*$')
_EMAIL_RE  = re.compile(r'[\w.+\-]+@[\w\-]+(?:\.[a-z]{2,})+', re.IGNORECASE)


def load_doc(docx_bytes: bytes) -> docx.Document:
    return docx.Document(io.BytesIO(docx_bytes))


def floating_actions(document: docx.Document) -> list[dict]:
    """Return all floating-action checklist items as parsed dicts.

    Detection: list/checklist paragraphs (w:numPr present) where the first
    meaningful content resolves to an assignee.

    When Google Docs exports a PERSON chip to .docx it becomes either:
      (a) a hyperlink whose display text is the person's name — the relationship
          target may be a Google profile URL, not mailto:; OR
      (b) a plain-text run with the person's display name or email address.

    Strategy:
      1. Collect all relationship targets (URLs) from the document part for
         hyperlinks that contain an email address (mailto: or ?email= params).
      2. For each list paragraph, extract the full text and any hyperlink URLs.
      3. Try to find an email: first from hyperlink rel targets, then from a
         regex match on the raw text (covers the case where the chip renders as
         the email address itself).
      4. Parse the trailing (Status) token; default status is 'Open'.

    Returns list of dicts with keys: assignee_email, assignee_name, action,
    status, has_explicit_status.
    """
    # Build a map: rId -> target URL for all hyperlink relationships
    hyperlink_urls: dict[str, str] = {}
    try:
        for rel in document.part.rels.values():
            if 'hyperlink' in rel.reltype:
                hyperlink_urls[rel.rId] = rel.target_ref or ''
    except Exception:
        pass

    result = []
    for para in document.paragraphs:
        # w:numPr is nested inside w:pPr, not a direct child of w:p.
        if para._element.find('.//' + qn('w:numPr')) is None:
            continue  # not a list paragraph

        full_text = para.text.strip()
        if not full_text:
            continue

        # Collect hyperlink URLs referenced from this paragraph's XML
        para_emails: list[str] = []
        for hl in para._element.findall(f'.//{qn("w:hyperlink")}'):
            r_id = hl.get(f'{{{hl.nsmap.get("r", "http://schemas.openxmlformats.org/officeDocument/2006/relationships")}}}id', '')
            url = hyperlink_urls.get(r_id, '')
            # mailto: link
            m = re.match(r'mailto:([^\?&]+)', url, re.IGNORECASE)
            if m:
                para_emails.append(m.group(1).strip())
                continue
            # email= query param (Google profile links)
            m = re.search(r'[?&]email=([^&]+)', url, re.IGNORECASE)
            if m:
                import urllib.parse
                para_emails.append(urllib.parse.unquote(m.group(1)).strip())

        # Parse trailing (Status) token
        status = 'Open'
        action_text = full_text
        sm = _STATUS_RE.search(full_text)
        has_explicit_status = bool(sm)
        if sm:
            status = sm.group(1).strip() or 'Open'
            action_text = full_text[:sm.start()].strip()

        # Determine assignee email
        assignee_email = ''
        assignee_name  = ''
        if para_emails:
            assignee_email = para_emails[0]
        else:
            # Try to find email pattern in the raw text (chip rendered as email address)
            em = _EMAIL_RE.match(action_text)
            if em:
                assignee_email = em.group(0)
                action_text = action_text[len(assignee_email):].strip()

        if not assignee_email and not assignee_name:
            continue  # can't identify assignee — not a trackable floating action

        result.append({
            'assignee_email': assignee_email,
            'assignee_name':  assignee_name,
            'action':         action_text,
            'status':         status,
            'has_explicit_status': has_explicit_status,
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
        if str(row.get("ID", "")) == str(action_id):
            return row
    return None
