"""Schema constants and id/normalisation builders (contract §1, §6).

Mirrors src/Procedure-Exporter.js's id/slug helpers one-for-one per the
contract's "Standing constraint: architectural alignment for back-port" —
`make_block_id` <-> `makeBlockId_`, `slugify` <-> `slugify_`, `sanitize_filename`
<-> `sanitizeFilename_`. Names lose the trailing-underscore GAS privacy
convention; nothing else about them changes. See contract §1.3 for why the
tail of each id differs (ordinal vs. Docs startIndex/endIndex).
"""
from __future__ import annotations

import re
import unicodedata

# Schema version for the Python DOCX pipeline. The GAS exporter stays at 2.4
# (GOV_EXPORT_SCHEMA_VERSION, src/Procedure-Exporter.js:42) and is not
# touched (ADR-0026 Decision 7) — contract §6. Bumped to 3.1 by ADR-0029:
# revision.state removed, document.suggestion_groups -> revision_groups,
# semantic_state/semantic_state_evidence/semantics removed document-wide.
SCHEMA_VERSION = "3.1"

# Contract §6: for symmetry the Python artifact carries this so the
# differential oracle (gts-klp8) can distinguish producers without editing
# the frozen GAS side (which carries no such field at all).
PRODUCER = "python-document-export"

# Contract §1.1 — there is no OOXML analogue of a Google Docs tab; every
# block in every document produced by this pipeline carries this constant.
SEGMENT_MAIN = "main"

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_WS_RE = re.compile(r"\s+")
_FILENAME_UNSAFE_RE = re.compile(r'[\\/:*?"<>|]+')
_DASH_RUN_RE = re.compile(r"-+")


def slugify(s: str | None) -> str:
    """NFKD, lower, non-alphanumerics collapsed to '-', trimmed, truncated to
    90 chars. Identical normalisation to slugify_ (src/Procedure-Exporter.js:1905)
    so unit ids stay visually comparable across implementations even though
    their tails (ordinal vs. startIndex) differ (contract §1.3)."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = _NON_ALNUM_RE.sub("-", s)
    s = s.strip("-")
    return s[:90]


def sanitize_filename(s: str | None) -> str:
    """Mirror sanitizeFilename_ (src/Procedure-Exporter.js:1953)."""
    s = str(s or "document").strip()
    s = _FILENAME_UNSAFE_RE.sub("-", s)
    s = _WS_RE.sub("-", s)
    s = _DASH_RUN_RE.sub("-", s)
    s = s.strip("-")
    return s or "document"


def format_ordinal(ordinal: int) -> str:
    """Zero-padded to 6 digits so lexicographic sort of ids equals document
    order (contract §1.2)."""
    return f"{ordinal:06d}"


def make_block_id(segment: str, ordinal: int) -> str:
    """block__<segment>__<ordinal> — contract §1.3. The `block__` prefix is
    retained from GAS's makeBlockId_; only the tail's derivation changes."""
    return f"block__{segment}__{format_ordinal(ordinal)}"


def make_unit_id(segment: str, kind: str, title: str | None, ordinal: int) -> str:
    """<segment>__<kind>__<slug>__<ordinal> — contract §1.3. `ordinal` is the
    ordinal of the block that opened the unit (its heading), so a unit id and
    its first block id agree on their tail number."""
    slug = slugify(title) or kind
    return f"{segment}__{kind}__{slug}__{format_ordinal(ordinal)}"


def make_image_id(segment: str, ordinal: int) -> str:
    """image__<segment>__<ordinal> — contract §1.3."""
    return f"image__{segment}__{format_ordinal(ordinal)}"


def make_image_ref(segment: str, ordinal: int, ext: str) -> str:
    """img-<segment>-<ordinal>.<ext> — contract §1.3."""
    return f"img-{segment}-{format_ordinal(ordinal)}.{ext}"


def make_location(ordinal: int, page: int, page_approximate: bool) -> dict:
    """The `location` shape shared by every unit/block kind on this path —
    text and image blocks alike (contract §1/§5). `page_basis` is always
    `"explicit_page_break_count"` here: only an explicit `w:br
    w:type="page"` counts (contract §5); `w:lastRenderedPageBreak` is
    ignored. Moved here (stage docx-images, gts-8uo6) from structure.py's
    former private `_make_location` so document_export.images can build an
    image block's location the same way structure.py builds a text block's,
    without a structure.py<->images.py import cycle."""
    return {
        "tab_id": None,
        "tab_title": None,
        "start_index": None,
        "end_index": None,
        "ordinal": ordinal,
        "segment": SEGMENT_MAIN,
        "page": page,
        "page_basis": "explicit_page_break_count",
        "page_approximate": page_approximate,
    }


def make_citation_hint(unit: dict | None, block: dict) -> str | None:
    """`"p. <page>, <unit title>, <block label>"`, only the parts that exist
    — shared by structure.py (text blocks) and document_export.images (image
    blocks); moved here for the same reason as `make_location`, above."""
    parts = []
    page = block["location"].get("page")
    if page:
        parts.append(f"p. {page}")
    if unit and unit.get("title"):
        parts.append(unit["title"])
    if block.get("label"):
        parts.append(block["label"])
    return ", ".join(parts) if parts else None


def drop_if_empty(obj: dict, key: str) -> None:
    """Contract §13.4: an array field is omitted entirely, not emitted as
    `[]`, when it would be empty. Shared by structure.py (kind_evidence,
    color_signals, run revision evidence) and comments.py (comment_ids,
    applied after comment resolution mutates blocks/units — must run after,
    not during, the structure pass)."""
    if isinstance(obj.get(key), list) and len(obj[key]) == 0:
        del obj[key]


def normalize_line(s: str | None) -> str:
    """Collapse newlines/whitespace runs to a single space and trim. Mirrors
    normalizeLine_ (src/Procedure-Exporter.js:1914); used for quoted_text and
    other reader-facing text fields (contract §2.5)."""
    s = str(s or "")
    s = re.sub(r"[\r\n]+", " ", s)
    s = _WS_RE.sub(" ", s)
    return s.strip()


_NBSP = "\u00A0"
_VERTICAL_TAB = "\u000B"


def normalize_derived_text(s: str | None) -> str:
    """§13.5: cosmetic normalisation applied ONLY to derived/concatenated
    text (block `text`, the `all_text`/`baseline_text`/`proposed_text` trio,
    `views.*`) — never to `runs[].text`, which stays byte-exact (§17
    principle 1). Mirrors normalizeDerivedText_ (src/Procedure-Exporter.js).
    Non-breaking space -> plain space. Vertical tab has no OOXML producer on
    this path (a soft line break is `w:br`, already turned into `\\n` by
    structure.py's `_run_text_and_breaks`) but the substitution is kept for
    literal contract compliance and in case one ever appears verbatim inside
    `w:t`/`w:delText`."""
    s = str(s or "")
    return s.replace(_NBSP, " ").replace(_VERTICAL_TAB, "\n")
