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

    When Google Docs exports a PERSON chip to .docx it becomes a hyperlink whose
    display text is the person's display name and whose URL contains the email
    (mailto: or ?email= param).  Building action_text from para.text would include
    that display name, so we exclude chip-hyperlink text and collect only the
    non-chip runs when building action_text for chip-led paragraphs.

    Returns list of dicts with keys: assignee_email, assignee_name, action,
    status, has_explicit_status.
    """
    import urllib.parse as _urlparse

    _R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'

    # Build map: rId -> email for all email-containing hyperlink relationships
    email_by_rid: dict[str, str] = {}
    try:
        for rel in document.part.rels.values():
            if 'hyperlink' not in rel.reltype:
                continue
            url = rel.target_ref or ''
            m = re.match(r'mailto:([^\?&]+)', url, re.IGNORECASE)
            if m:
                email_by_rid[rel.rId] = m.group(1).strip()
                continue
            m = re.search(r'[?&]email=([^&]+)', url, re.IGNORECASE)
            if m:
                email_by_rid[rel.rId] = _urlparse.unquote(m.group(1)).strip()
    except Exception:
        pass

    result = []
    for para in document.paragraphs:
        # w:numPr is nested inside w:pPr, not a direct child of w:p.
        if para._element.find('.//' + qn('w:numPr')) is None:
            continue  # not a list paragraph

        # Find the first person-chip hyperlink in this paragraph
        assignee_email = ''
        chip_rid = ''
        for hl in para._element.findall(qn('w:hyperlink')):
            r_id = hl.get(f'{{{_R_NS}}}id', '')
            if r_id in email_by_rid:
                assignee_email = email_by_rid[r_id]
                chip_rid = r_id
                break

        if assignee_email:
            # Chip-led: collect text from all direct children except the chip hyperlink.
            # This excludes the chip's display name from action_text.
            parts = []
            for child in para._element:
                local = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if local == 'hyperlink' and child.get(f'{{{_R_NS}}}id', '') == chip_rid:
                    continue  # skip chip display text
                for t_el in child.iter(qn('w:t')):
                    if t_el.text:
                        parts.append(t_el.text)
            raw_text = ''.join(parts).strip()
        else:
            # No chip hyperlink: fall back to email-at-start in full paragraph text
            raw_text = para.text.strip()
            if not raw_text:
                continue
            em = _EMAIL_RE.match(raw_text)
            if em:
                assignee_email = em.group(0)
                raw_text = raw_text[len(em.group(0)):].strip()
            else:
                continue

        if not assignee_email:
            continue  # can't identify assignee — not a trackable floating action

        # Parse trailing (Status) token
        sm = _STATUS_RE.search(raw_text)
        has_explicit_status = bool(sm)
        if sm:
            status = sm.group(1).strip() or 'Open'
            action_text = raw_text[:sm.start()].strip()
        else:
            status = 'Open'
            action_text = raw_text

        result.append({
            'assignee_email': assignee_email,
            'assignee_name':  '',
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


def verify_doc_chip_integrity(doc_id: str, settings: dict) -> list[dict]:
    """POST verify_chip_integrity to the GAS WebApp; return violations list.

    Each violation is a dict with 'paragraph' (e.g. 'AI-3') and 'issue' keys.
    Empty list means all AI-N: chips have a brand-NUTS status icon, a valid
    globalId link, and a consistent (Status) token.
    Raises RuntimeError on network or GAS errors.
    """
    import json as _json
    import pathlib as _pathlib
    import urllib.request as _req
    import urllib.error as _uerr

    url   = settings.get("webappTestUrl") or ""
    token = settings.get("testToken") or ""
    if not url:
        raise RuntimeError("webappTestUrl not set in local.settings.json")

    payload = _json.dumps({
        "action":    "verify_chip_integrity",
        "testToken": token,
        "docId":     doc_id,
    }).encode("utf-8")

    headers: dict = {"Content-Type": "application/json"}
    if url.endswith("/dev"):
        _auth = _pathlib.Path(__file__).parent.parent.parent / ".auth" / "user.json"
        if _auth.exists():
            _state = _json.loads(_auth.read_text())
            _domains = {"script.google.com", ".google.com", "accounts.google.com"}
            _parts = [
                f"{c['name']}={c['value']}"
                for c in _state.get("cookies", [])
                if any(c.get("domain", "") == d or c.get("domain", "").endswith(d)
                       for d in _domains)
            ]
            if _parts:
                headers["Cookie"] = "; ".join(_parts)

    request = _req.Request(url, data=payload, headers=headers, method="POST")
    try:
        with _req.urlopen(request, timeout=90) as resp:
            raw = resp.read().decode("utf-8")
    except _uerr.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from verify_chip_integrity: {raw!r}") from exc
    except _uerr.URLError as exc:
        raise RuntimeError(f"Network error calling verify_chip_integrity: {exc.reason}") from exc

    if raw in ("test-token-unauthorized", "test-token-expired"):
        raise RuntimeError(f"GAS rejected test token for verify_chip_integrity: {raw}")

    result = _json.loads(raw)
    if "error" in result:
        raise RuntimeError(f"GAS verify_chip_integrity error: {result['error']}")
    return result.get("violations", [])
