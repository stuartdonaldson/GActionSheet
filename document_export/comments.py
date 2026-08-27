"""Comment anchoring from w:commentRangeStart/End (contract §2; stage
docx-comments, gts-nxx3).

Retires, does not port: the four-tier quoted-text matcher, its tuning
constants, the `association_basis` field, and the `unmatched` bucket
(ADR-0026 Decision 5, contract §2.1/§2.3). No fuzzy or text-similarity
matching appears anywhere in this module.

Mirrors src/Procedure-Exporter.js's comment shape one-for-one per the
contract's "Standing constraint" (id/author/created_at/modified_at/
resolved/content/quoted_text/associated_block_ids/associated_unit_ids/
section_path/citation_hint/replies) except where the contract names a
deviation: `anchor_basis` replaces `association_basis` (§2.3), and
`quoted_mime_type`/`drive_anchor` (Drive-only concepts) have no OOXML
source. This stage's own unlisted-field gaps (comment `id` scheme,
`modified_at`) are recorded in the stage handoff, following the same
disposition stage docx-harness used for `document.revision_id`.
"""
from __future__ import annotations

from document_export.package import NS
from document_export.revisions import block_text
from document_export.schema import drop_if_empty, normalize_line
from document_export.structure import paragraph_all_text

_W = NS["w"]
_W14 = "http://schemas.microsoft.com/office/word/2010/wordml"
_W15 = NS["w15"]


def _wtag(local: str) -> str:
    return f"{{{_W}}}{local}"


def _w14tag(local: str) -> str:
    return f"{{{_W14}}}{local}"


def _w15tag(local: str) -> str:
    return f"{{{_W15}}}{local}"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


# ============================================================================
# comments.xml / commentsExtended.xml
# ============================================================================

def _parse_raw_comments(comments_root) -> dict[str, dict]:
    """id -> {author, date, para_id, text}. `para_id` is the comment's own
    w14:paraId (its w:p's, not the range markers) -- commentsExtended.xml
    threads on this, not on w:id."""
    raw: dict[str, dict] = {}
    if comments_root is None:
        return raw
    for c in comments_root.findall("w:comment", NS):
        cid = c.get(_wtag("id"))
        if cid is None:
            continue
        para_id = None
        text_parts: list[str] = []
        for p in c.findall("w:p", NS):
            if para_id is None:
                para_id = p.get(_w14tag("paraId"))
            for t in p.iter(_wtag("t")):
                text_parts.append(t.text or "")
        raw[cid] = {
            "id": cid,
            "author": c.get(_wtag("author")),
            "created_at": c.get(_wtag("date")),
            "para_id": para_id,
            "content": "".join(text_parts),
        }
    return raw


def _parse_extended(ext_root) -> dict[str, dict]:
    """comment paraId -> {done, parent_para_id}. Absent commentsExtended.xml
    (contract §2.6) yields an empty map -- every comment then resolves
    `resolved: null`."""
    out: dict[str, dict] = {}
    if ext_root is None:
        return out
    for ce in ext_root.findall("w15:commentEx", NS):
        para_id = ce.get(_w15tag("paraId"))
        if para_id is None:
            continue
        out[para_id] = {
            "done": ce.get(_w15tag("done")),
            "parent_para_id": ce.get(_w15tag("paraIdParent")),
        }
    return out


def _resolved_value(ext_entry: dict | None) -> bool | None:
    """Contract §2.6: null means "unknown" (no commentsExtended.xml, or no
    entry for this comment), never "not resolved"."""
    if ext_entry is None:
        return None
    return ext_entry["done"] == "1"


# ============================================================================
# document.xml -- paragraph/block alignment (mirrors structure.py's own
# traversal so paragraph N here lines up with the Nth non-empty paragraph's
# block in units[], without re-deriving structure.py's text extraction).
# ============================================================================

def _iter_paragraphs(elements):
    """Yields every w:p in document order, descending into w:tbl/w:tr/w:tc
    exactly as structure._process_table does. Mirrors structure._process_content's
    traversal shape rather than duplicating it -- only w:p/w:tbl are
    structural at this level, same as there."""
    for el in elements:
        tag = _local(el.tag)
        if tag == "p":
            yield el
        elif tag == "tbl":
            for row in el.findall("w:tr", NS):
                for cell in row.findall("w:tc", NS):
                    yield from _iter_paragraphs(list(cell))


def _flatten_blocks_in_order(units: list[dict]) -> list[dict]:
    """source_order is assigned once per non-empty-text paragraph, strictly
    increasing in document traversal order (structure._process_paragraph) --
    sorting recovers the exact document-order sequence of *text* blocks
    regardless of which unit ended up owning each one.

    `image`-kind blocks (stage docx-images, gts-8uo6) are excluded here --
    they consume their own ordinal but are not the "did this paragraph
    produce a block" answer `_paragraph_block_pairs` is testing for (an
    image-only paragraph has no text, `paragraph_all_text` reports it
    empty, and no `commentRangeStart/End` can anchor inside a `w:drawing`).
    Including them would desync this 1-paragraph-with-text : 1-block
    invariant every text paragraph after an image-only one relies on --
    each image block would be handed to the *next* real text paragraph
    instead. Comment-to-image association is out of this module's scope."""
    return sorted(
        (b for u in units for b in u["blocks"] if b.get("kind") != "image"),
        key=lambda b: b["source_order"],
    )


def _paragraph_block_pairs(document_root, units: list[dict]) -> list[tuple]:
    """[(p_el, block_or_None), ...] in document order. A paragraph gets a
    block iff structure.py's own emptiness test (paragraph_all_text) said
    so -- same test, so this pairing stays correct even if that test's
    rules change later."""
    body = document_root.find("w:body", NS) if document_root is not None else None
    if body is None:
        return []
    blocks = iter(_flatten_blocks_in_order(units))
    pairs = []
    for p_el in _iter_paragraphs(list(body)):
        has_text = bool(paragraph_all_text(p_el).strip())
        block = next(blocks, None) if has_text else None
        pairs.append((p_el, block))
    return pairs


def _paragraph_events(p_el):
    """Yields (kind, comment_id, token) in document order for one paragraph,
    kind in 'start'/'end'/'text'. `token` is a dense per-paragraph index
    used only to test whether any real text token falls between a comment's
    start and end event (range_empty, contract §2.3) -- not a document-wide
    position."""
    token = 0
    for el in p_el.iter():
        tag = _local(el.tag)
        if tag == "commentRangeStart":
            yield "start", el.get(_wtag("id")), token
            token += 1
        elif tag == "commentRangeEnd":
            yield "end", el.get(_wtag("id")), token
            token += 1
        elif tag in ("t", "delText") and (el.text or ""):
            yield "text", None, token
            token += 1


def _nearest_block_index(pos: int, block, pairs: list[tuple], block_index: dict, *, forward: bool):
    """Resolves a marker to a block-sequence index. If the marker's own
    paragraph produced a block, that block is the answer. Otherwise (the
    marker sits in a structurally-empty paragraph -- not exercised by the
    golden fixture) search outward: forward from a start marker's paragraph,
    backward from an end marker's, for the nearest paragraph that did
    produce one. Returns None only if no block exists on that side at all."""
    if block is not None:
        return block_index[id(block)]
    step = 1 if forward else -1
    i = pos
    while 0 <= i < len(pairs):
        _, b = pairs[i]
        if b is not None:
            return block_index[id(b)]
        i += step
    return None


def _resolve_ranges(document_root, units: list[dict]) -> dict[str, dict]:
    """comment id -> {anchor_basis, associated_block_ids (block dicts, not
    just ids), quoted_text}, for every comment id that has at least a start
    marker somewhere in the body. A comment id with no entry here is
    `no_range` (contract §2.3's fifth row)."""
    pairs = _paragraph_block_pairs(document_root, units)
    block_seq = _flatten_blocks_in_order(units)
    block_index = {id(b): i for i, b in enumerate(block_seq)}

    starts: dict[str, tuple] = {}
    ends: dict[str, tuple] = {}
    empty_ranges: set[str] = set()

    for pos, (p_el, _block) in enumerate(pairs):
        events = list(_paragraph_events(p_el))
        open_start_token: dict[str, int] = {}
        for kind, cid, tok in events:
            if kind == "start":
                open_start_token[cid] = tok
                if cid not in starts:
                    starts[cid] = (pos, pairs[pos][1])
            elif kind == "end":
                ends[cid] = (pos, pairs[pos][1])
                start_tok = open_start_token.pop(cid, None)
                if start_tok is not None:
                    has_text = any(k == "text" and start_tok < t < tok for k, _c, t in events)
                    if not has_text:
                        empty_ranges.add(cid)

    resolved: dict[str, dict] = {}
    for cid, (start_pos, start_block) in starts.items():
        start_idx = _nearest_block_index(start_pos, start_block, pairs, block_index, forward=True)
        end = ends.get(cid)

        if end is None:
            if start_idx is None:
                continue  # no block anywhere after the start marker -- leave as no_range.
            blocks = [block_seq[start_idx]]
            resolved[cid] = {
                "anchor_basis": "range_unterminated",
                "blocks": blocks,
                "quoted_text": normalize_line(" ".join(block_text(b) for b in blocks)),
                "warning": True,
            }
            continue

        end_pos, end_block = end
        end_idx = _nearest_block_index(end_pos, end_block, pairs, block_index, forward=False)

        if start_idx is None or end_idx is None or end_idx < start_idx:
            continue  # degenerate placement -- leave as no_range rather than invent an order.

        if cid in empty_ranges and start_idx == end_idx:
            resolved[cid] = {
                "anchor_basis": "range_empty",
                "blocks": [block_seq[start_idx]],
                "quoted_text": "",
                "warning": False,
            }
            continue

        blocks = block_seq[start_idx:end_idx + 1]
        resolved[cid] = {
            "anchor_basis": "range_exact" if start_idx == end_idx else "range_multiblock",
            "blocks": blocks,
            "quoted_text": normalize_line(" ".join(block_text(b) for b in blocks)),
            "warning": False,
        }

    return resolved


# ============================================================================
# assembly
# ============================================================================

_NO_RANGE_WARNING = (
    "{count} comment(s) could not be anchored to a block (anchor_basis "
    "\"no_range\" or \"range_unterminated\") -- their commentRangeStart/End "
    "markers are missing or incomplete in the source .docx. "
    "associated_block_ids/associated_unit_ids/section_path are empty for "
    "these comments; this is not a matching-tier failure (contract §2.3), "
    "no fuzzy fallback is attempted."
)


def _ordered_dedup(items):
    seen = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def _build_comment_record(cid: str, raw: dict, resolution: dict | None, unit_by_id: dict) -> dict:
    if resolution is None:
        return {
            "id": raw["id"],
            "author": raw["author"],
            "created_at": raw["created_at"],
            # No OOXML equivalent of Drive's separate modifiedTime -- a
            # w:comment carries one w:date only. Recorded as a contract gap
            # in this stage's handoff, same disposition as revision_id
            # (stage docx-harness).
            "modified_at": None,
            "resolved": None,  # filled in by the caller once threading is known
            "content": raw["content"],
            "quoted_text": None,
            # Drive-only concepts; no OOXML source (same disposition as
            # modified_at, above).
            "quoted_mime_type": None,
            "drive_anchor": None,
            "anchor_basis": "no_range",
            "associated_block_ids": [],
            "associated_unit_ids": [],
            "section_path": [],
            "citation_hint": None,
            "replies": [],
        }

    blocks = resolution["blocks"]
    associated_unit_ids = _ordered_dedup(b["unit_id"] for b in blocks)
    primary_block = blocks[0]
    primary_unit = unit_by_id.get(primary_block["unit_id"])
    section_path = _unit_ancestry_path(primary_unit, unit_by_id) if primary_unit else []

    return {
        "id": raw["id"],
        "author": raw["author"],
        "created_at": raw["created_at"],
        "modified_at": None,
        "resolved": None,
        "content": raw["content"],
        "quoted_text": resolution["quoted_text"],
        "quoted_mime_type": None,
        "drive_anchor": None,
        "anchor_basis": resolution["anchor_basis"],
        "associated_block_ids": [b["id"] for b in blocks],
        "associated_unit_ids": associated_unit_ids,
        "section_path": section_path,
        "citation_hint": primary_block.get("citation_hint"),
        "replies": [],
    }


def _unit_ancestry_path(unit: dict, unit_by_id: dict) -> list[dict]:
    """Root -> leaf breadcrumb of ancestor units for `unit`, mirroring
    unitAncestryPath_ (src/Procedure-Exporter.js)."""
    chain = []
    current = unit
    while current is not None:
        chain.append({"id": current["id"], "kind": current["kind"], "title": current["title"]})
        current = unit_by_id.get(current.get("parent_unit_id"))
    chain.reverse()
    return chain


def resolve_comments(pkg, units: list[dict], diagnostics: dict) -> list[dict]:
    """Contract §7.1 entry point for this module. Attaches `comment_ids` to
    the blocks/units already built by structure.walk_structure (mutated in
    place, then finalized here per §13.4 -- see structure._finalize_units'
    docstring for why that omission is deferred to this module) and returns
    the top-level comments[] array (roots only; threaded replies nest under
    `replies[]`, contract §2.6). Mutates `diagnostics` in place, same
    contract as walk_structure's own counters."""
    comments_root = pkg.xml("comments")
    raw = _parse_raw_comments(comments_root)
    if not raw:
        return []

    ext_by_para_id = _parse_extended(pkg.xml("comments_extended"))
    document_root = pkg.xml("document")
    resolutions = _resolve_ranges(document_root, units)
    unit_by_id = {u["id"]: u for u in units}

    # Threading: a comment is a reply iff its own paraId is named as some
    # other comment's paraIdParent (contract §2.6). Resolve parent-by-paraId
    # to the comment id that owns that paraId, not by w:id.
    para_id_to_cid = {r["para_id"]: cid for cid, r in raw.items() if r["para_id"]}
    parent_cid_of: dict[str, str] = {}
    for cid, r in raw.items():
        ext = ext_by_para_id.get(r["para_id"])
        if ext and ext["parent_para_id"]:
            parent_cid = para_id_to_cid.get(ext["parent_para_id"])
            if parent_cid:
                parent_cid_of[cid] = parent_cid

    records: dict[str, dict] = {}
    for cid, r in raw.items():
        record = _build_comment_record(cid, r, resolutions.get(cid), unit_by_id)
        record["resolved"] = _resolved_value(ext_by_para_id.get(r["para_id"]))
        records[cid] = record

    roots: list[dict] = []
    for cid, record in records.items():
        parent_cid = parent_cid_of.get(cid)
        if parent_cid and parent_cid in records:
            reply = {
                "id": record["id"],
                "author": record["author"],
                "created_at": record["created_at"],
                "modified_at": record["modified_at"],
                "content": record["content"],
            }
            records[parent_cid]["replies"].append(reply)
        else:
            roots.append(record)

    # comment_ids: attach to every associated block, then aggregate onto
    # each block's unit (mirrors associateCommentsToBlocks_'s two passes).
    unanchored = 0
    for cid, record in records.items():
        if parent_cid_of.get(cid):
            continue  # replies do not carry their own anchor.
        resolution = resolutions.get(cid)
        if resolution is not None:
            for block in resolution["blocks"]:
                block["comment_ids"].append(record["id"])
        if record["anchor_basis"] in ("no_range", "range_unterminated"):
            unanchored += 1

    for unit in units:
        ids = _ordered_dedup(cid for block in unit["blocks"] for cid in block.get("comment_ids", []))
        unit["comment_ids"] = ids
        drop_if_empty(unit, "comment_ids")
        for block in unit["blocks"]:
            drop_if_empty(block, "comment_ids")

    diagnostics["comments"] = len(roots)
    diagnostics["unresolved_comments"] = sum(1 for r in roots if r["resolved"] is not True)
    diagnostics["unanchored_comments"] = unanchored
    if unanchored:
        diagnostics["warnings"].append(_NO_RANGE_WARNING.format(count=unanchored))

    return roots
