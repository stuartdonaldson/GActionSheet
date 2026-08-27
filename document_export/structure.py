"""Structure pass: units, blocks, runs, tables, numbering (contract §1, §8;
stage docx-structure, gts-pmga).

Mirrors src/Procedure-Exporter.js's structural-walk region one-for-one per
the contract's "Standing constraint: architectural alignment for back-port" —
GOVERNANCE_UNIT_PATTERNS / HEADING_FALLBACK_BASE_RANK / SEMANTIC_STATE_PATTERNS
are the same rules, unchanged, moved here rather than reinvented.
processStructuralContent_/processParagraph_/processTable_/createUnit_/
createBlock_/pushUnitOntoStack_ all have a same-shape counterpart below.

Deliberately NOT ported (per the bead's own DESIGN section and ADR-0026
Decision 5): associateCommentsToBlocks_'s tuning constants and four-tier
matcher (stage docx-comments), makeAutoTextRun_/mergeAdjacentRuns_'s
Docs-API-field-code shapes (OOXML represents generated page numbers as
w:fldSimple/w:instrText, an unrelated mechanism).

Revision classification (w:ins/w:del -> run.revision.state/change) is stage
docx-revisions' (gts-9c8k) and lives in document_export.revisions --
_iter_run_elements below discovers each run's w:ins/w:del ancestor chain
during the same traversal that already finds hyperlinks/fields, and
_build_runs calls revisions.classify_revision(...) to turn that chain into
the run's `revision` object. text is always extracted (both w:t and
w:delText, per contract §3.1) so no source text is silently lost (§17
principle 1) regardless of tracked-change nesting.
"""
from __future__ import annotations

import re

from document_export import images, revisions
from document_export.package import NS
from document_export.schema import (
    SEGMENT_MAIN,
    drop_if_empty,
    make_block_id,
    make_citation_hint,
    make_location,
    make_unit_id,
    normalize_line,
)

_W = NS["w"]
_R = NS["r"]


def _wtag(local: str) -> str:
    return f"{{{_W}}}{local}"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


# ============================================================================
# TEXT-PATTERN INFERENCE RULES -- ported verbatim from
# src/Procedure-Exporter.js's bannered region (docs/procedure-exporter.md
# §7.4). Tune in BOTH places together; do not let this drift from the GAS
# source without recording why (contract "Standing constraint").
# ============================================================================

GOVERNANCE_UNIT_PATTERNS = [
    {
        "name": "policy_numbered", "kind": "policy", "rank": 2,
        "re": re.compile(
            r"^(Church|Cabinet|Board(?: Meeting| Leader| Committee| Safety)?|"
            r"Communications Committee|Facilities Committee|Finance Committee|"
            r"Governance Committee|HRC|Human Resources Committee|Nominating Committee)"
            r"\s+Policy\s+\d+\s*:", re.IGNORECASE,
        ),
    },
    {
        "name": "procedure_numbered", "kind": "procedure", "rank": 3,
        "re": re.compile(
            r"^(Church|Cabinet|Board(?: Meeting| Leader| Committees?| Safety)?|"
            r"CC|FAC|FIC|GC|HRC|NC)\s+Procedure(?:s)?\s+\d+(?:[-:]\d+)?\s*:",
            re.IGNORECASE,
        ),
    },
    {"name": "charter_suffix", "kind": "charter", "rank": 1,
     "re": re.compile(r"\bCHARTER\s*$", re.IGNORECASE)},
    {"name": "article_prefix", "kind": "article", "rank": 1,
     "re": re.compile(r"^ARTICLE\s+(?:[A-Z]+|\w+)\b", re.IGNORECASE)},
    {"name": "exhibit_prefix", "kind": "exhibit", "rank": 1,
     "re": re.compile(r"^EXHIBIT\s+[A-Z0-9]+\b", re.IGNORECASE)},
    {"name": "standing_rules_prefix", "kind": "standing_rules", "rank": 1,
     "re": re.compile(r"^STANDING RULES\b", re.IGNORECASE)},
    {"name": "organizational_chart_mention", "kind": "organizational_chart", "rank": 1,
     "re": re.compile(r"ORGANIZATIONAL CHART", re.IGNORECASE)},
    {"name": "glossary_mention", "kind": "glossary", "rank": 1,
     "re": re.compile(r"GLOSSARY", re.IGNORECASE)},
    {"name": "numbered_section_prefix", "kind": "section", "rank": 2,
     "re": re.compile(r"^\d+\s*[-–—]\s+.+")},
]

HEADING_FALLBACK_BASE_RANK = 3

SEMANTIC_STATE_PATTERNS = [
    {"name": "old_paren_prefix", "state": "historical", "re": re.compile(r"^\(OLD\)", re.IGNORECASE)},
    {"name": "old_dash_prefix", "state": "historical", "re": re.compile(r"^OLD\s*[-:]", re.IGNORECASE)},
    {"name": "end_prefix", "state": "editorial", "re": re.compile(r"^END\s*[-:]", re.IGNORECASE)},
    {"name": "fyi_prefix", "state": "editorial", "re": re.compile(r"^FYI\s*[-:]", re.IGNORECASE)},
    {"name": "tbd_marker", "state": "editorial", "re": re.compile(r"\bTBD\b", re.IGNORECASE)},
    {"name": "question_marks_marker", "state": "editorial", "re": re.compile(r"\?\?\?+")},
    {"name": "link_placeholder_marker", "state": "editorial", "re": re.compile(r"\blink\?\?", re.IGNORECASE)},
    {"name": "placeholder_word_marker", "state": "editorial", "re": re.compile(r"\bplaceholder\b", re.IGNORECASE)},
]

# Leading semantic-state markers stripped before GOVERNANCE_UNIT_PATTERNS
# matching only (title/semantic-state detection still run against the full,
# unstripped text) -- only patterns anchored at string-start are eligible,
# mirroring KIND_MATCH_STRIP_PATTERNS' `source.startsWith('^')` filter.
_KIND_MATCH_STRIP_PATTERNS = [p for p in SEMANTIC_STATE_PATTERNS if p["re"].pattern.startswith("^")]

LABEL_MAX_LEN = 80
LABEL_SCAN_MAX_LEN = 100

_HIGHLIGHT_HEX = {
    "black": "#000000", "blue": "#0000FF", "cyan": "#00FFFF", "darkBlue": "#00008B",
    "darkCyan": "#008B8B", "darkGray": "#A9A9A9", "darkGreen": "#006400",
    "darkMagenta": "#8B008B", "darkRed": "#8B0000", "darkYellow": "#808000",
    "green": "#00FF00", "lightGray": "#D3D3D3", "magenta": "#FF00FF",
    "red": "#FF0000", "white": "#FFFFFF", "yellow": "#FFFF00",
}

_UNORDERED_NUM_FORMATS = {"bullet"}
_UNRESOLVED_NUM_FORMATS = {"none"}


def _strip_leading_state_marker(t: str) -> str:
    for pattern in _KIND_MATCH_STRIP_PATTERNS:
        m = pattern["re"].match(t)
        if m and m.start() == 0:
            return t[m.end():].strip()
    return t


def _detect_semantic_state(text: str) -> dict:
    t = normalize_line(text)
    for pattern in SEMANTIC_STATE_PATTERNS:
        if pattern["re"].search(t):
            return {"state": pattern["state"], "evidence": [{"type": "text_pattern", "rule": pattern["name"]}]}
    return {"state": "baseline", "evidence": []}


def _detect_governance_unit(text: str, heading_level: int | None, has_image: bool = False) -> dict | None:
    t = normalize_line(text)
    kind_match_text = _strip_leading_state_marker(t)

    for pattern in GOVERNANCE_UNIT_PATTERNS:
        if pattern["re"].search(kind_match_text):
            semantic = _detect_semantic_state(t)
            return {
                "kind": pattern["kind"],
                "title": t,
                "rank": pattern["rank"],
                "kind_evidence": [{"type": "text_pattern", "rule": pattern["name"]}],
                "semantic_state": semantic["state"],
                "semantic_state_evidence": semantic["evidence"],
            }

    # gts-pczo.1 AC #3: a heading-styled paragraph with neither text nor an
    # image is authoring noise (a stray Enter-after-heading leaving an empty
    # Heading-styled line), not a structural boundary -- do not open a unit
    # for it. `has_image` keeps the documented, intentional exception: a
    # heading paragraph whose entire content is an image still opens its own
    # unit (mirrors GAS's own detectSemanticUnit_(allText, ...) behavior,
    # unchanged since before stage docx-images).
    if heading_level and (t or has_image) and len(t) < 180:
        semantic = _detect_semantic_state(t)
        return {
            "kind": "section",
            "title": t,
            "rank": HEADING_FALLBACK_BASE_RANK + heading_level,
            "kind_evidence": [{"type": "style_pattern", "rule": "heading_style", "named_style": f"HEADING_{heading_level}"}],
            "semantic_state": semantic["state"],
            "semantic_state_evidence": semantic["evidence"],
        }

    return None


def _detect_bold_colon_label(raw_runs: list[dict]) -> dict | None:
    """Mirrors detectBoldColonLabel_: a paragraph opening with bold text up to
    a colon is a labeled_paragraph. `raw_runs` are pre-merge {"text", "bold"}
    dicts in document order (non-text runs already filtered out)."""
    collected = ""
    saw_bold = False

    for run in raw_runs:
        text = run["text"]
        bold = run["bold"]

        if not collected and not bold:
            return None
        if bold:
            saw_bold = True
        if not bold and ":" not in collected:
            return None

        collected += text
        colon = collected.find(":")
        if colon >= 0:
            label = collected[:colon].strip()
            if saw_bold and label and len(label) <= LABEL_MAX_LEN and "\n" not in label and "\r" not in label:
                return {"text": label, "normalized": re.sub(r"\s+", " ", label.lower())}
            return None

        if len(collected) > LABEL_SCAN_MAX_LEN:
            return None

    return None


def _classify_block(heading_level: int | None, has_bullet: bool, label: dict | None, semantic_state: str) -> str:
    if semantic_state == "historical":
        return "historical_note"
    if semantic_state == "editorial":
        return "editorial_note"
    if heading_level:
        return "heading"
    if has_bullet:
        return "list_item"
    if label:
        return "historical_note" if label["normalized"] == "historical note" else "labeled_paragraph"
    return "paragraph"


# ============================================================================
# STYLES / NUMBERING RESOLUTION
# ============================================================================

def _load_heading_levels(pkg) -> dict[str, int]:
    """styleId -> heading level (1-6), from word/styles.xml. Prefers
    w:pPr/w:outlineLvl (0-based -> +1); falls back to a `heading N` style
    name for a style that carries no explicit outlineLvl."""
    styles_root = pkg.xml("styles")
    levels: dict[str, int] = {}
    if styles_root is None:
        return levels

    for style in styles_root.findall("w:style", NS):
        if style.get(_wtag("type")) != "paragraph":
            continue
        style_id = style.get(_wtag("styleId"))
        if not style_id:
            continue

        ppr = style.find("w:pPr", NS)
        outline = ppr.find("w:outlineLvl", NS) if ppr is not None else None
        if outline is not None:
            val = outline.get(_wtag("val"))
            if val is not None:
                levels[style_id] = int(val) + 1
                continue

        name_el = style.find("w:name", NS)
        name_val = (name_el.get(_wtag("val")) if name_el is not None else None) or ""
        m = re.match(r"^heading\s*(\d)$", name_val.strip(), re.IGNORECASE)
        if m:
            levels[style_id] = int(m.group(1))

    return levels


def _load_numbering(pkg):
    """(numId -> abstractNumId, abstractNumId -> {ilvl: numFmt}) from
    word/numbering.xml. Both dicts empty when the part is absent."""
    root = pkg.xml("numbering")
    num_to_abstract: dict[str, str] = {}
    abstract_fmt: dict[str, dict[str, str | None]] = {}
    if root is None:
        return num_to_abstract, abstract_fmt

    for num in root.findall("w:num", NS):
        num_id = num.get(_wtag("numId"))
        abs_el = num.find("w:abstractNumId", NS)
        if num_id is not None and abs_el is not None:
            num_to_abstract[num_id] = abs_el.get(_wtag("val"))

    for abstract_num in root.findall("w:abstractNum", NS):
        abs_id = abstract_num.get(_wtag("abstractNumId"))
        lvl_map: dict[str, str | None] = {}
        for lvl in abstract_num.findall("w:lvl", NS):
            ilvl = lvl.get(_wtag("ilvl"))
            fmt_el = lvl.find("w:numFmt", NS)
            fmt = fmt_el.get(_wtag("val")) if fmt_el is not None else None
            if ilvl is not None:
                lvl_map[ilvl] = fmt
        if abs_id is not None:
            abstract_fmt[abs_id] = lvl_map

    return num_to_abstract, abstract_fmt


def _is_ordered(num_fmt: str | None) -> bool | None:
    """Contract §1/AC #2: a real answer read off numbering.xml, replacing
    inferOrderedList_'s deliberate `return null`. None means "could not be
    determined" (no numbering.xml, unresolved numId, or an explicit
    `numFmt="none"`) -- still a legitimate value, never invented."""
    if num_fmt is None:
        return None
    if num_fmt in _UNORDERED_NUM_FORMATS:
        return False
    if num_fmt in _UNRESOLVED_NUM_FORMATS:
        return None
    return True


def _resolve_list(num_pr, num_to_abstract, abstract_fmt) -> dict | None:
    num_id_el = num_pr.find("w:numId", NS)
    ilvl_el = num_pr.find("w:ilvl", NS)
    num_id = num_id_el.get(_wtag("val")) if num_id_el is not None else None
    ilvl = int(ilvl_el.get(_wtag("val"))) if ilvl_el is not None else 0

    if num_id is None or num_id == "0":
        # numId 0 is OOXML's own "remove numbering inherited from style" —
        # not a list.
        return None

    abs_id = num_to_abstract.get(num_id)
    fmt = abstract_fmt.get(abs_id, {}).get(str(ilvl)) if abs_id is not None else None
    return {"list_id": num_id, "nesting_level": ilvl, "ordered": _is_ordered(fmt)}


# ============================================================================
# RUNS
# ============================================================================

def _run_format(rpr, link: str | None) -> dict:
    def flag(name: str) -> bool:
        el = rpr.find(f"w:{name}", NS) if rpr is not None else None
        if el is None:
            return False
        val = el.get(_wtag("val"))
        return val not in ("0", "false", "none") if val is not None else True

    underline = False
    if rpr is not None:
        u_el = rpr.find("w:u", NS)
        if u_el is not None:
            underline = u_el.get(_wtag("val")) not in (None, "none")

    foreground = None
    background = None
    if rpr is not None:
        color_el = rpr.find("w:color", NS)
        if color_el is not None:
            val = color_el.get(_wtag("val"))
            if val and val.lower() != "auto":
                foreground = f"#{val.upper()}"

        highlight_el = rpr.find("w:highlight", NS)
        if highlight_el is not None:
            hval = highlight_el.get(_wtag("val"))
            background = _HIGHLIGHT_HEX.get(hval or "", None)
        if background is None:
            shd_el = rpr.find("w:shd", NS)
            if shd_el is not None:
                fill = shd_el.get(_wtag("fill"))
                if fill and fill.lower() not in ("auto", "none"):
                    background = f"#{fill.upper()}"

    return {
        "bold": flag("b"),
        "italic": flag("i"),
        "underline": underline,
        "strikethrough": flag("strike"),
        "foreground_color": foreground,
        "background_color": background,
        "link": link,
    }


def _iter_run_elements(elements, rels: dict | None = None, link=None, tracked: tuple = ()):
    """DFS over a paragraph's children, yielding (run_element, link, tracked)
    for every w:r found -- including ones nested inside w:ins/w:del/
    w:hyperlink/w:fldSimple/w:smartTag, so tracked-change and field-wrapped
    text is not silently skipped (contract §3.1, §17 principle 1). `link`
    threads a w:hyperlink ancestor's resolved URL down to the runs it wraps.
    `tracked` threads a run's w:ins/w:del ancestor chain, outer-to-inner, as
    `{"tag", "author", "date"}` dicts -- contract §3.1's revision
    classification input (document_export.revisions.classify_revision).
    `rels` is only needed to resolve a w:hyperlink's own r:id -- callers
    with no hyperlink to resolve (e.g. label detection, which only reads
    text/bold) may omit it."""
    for el in elements:
        tag = _local(el.tag)
        if tag == "r":
            yield el, link, tracked
        elif tag == "hyperlink":
            nested_link = _resolve_hyperlink(el, rels) if rels else None
            yield from _iter_run_elements(
                list(el), rels=rels, link=nested_link or link, tracked=tracked,
            )
        elif tag in ("ins", "del"):
            entry = {
                "tag": tag,
                "author": el.get(_wtag("author")),
                "date": el.get(_wtag("date")),
            }
            yield from _iter_run_elements(
                list(el), rels=rels, link=link, tracked=tracked + (entry,),
            )
        elif tag in ("fldSimple", "smartTag", "sdt", "sdtContent"):
            yield from _iter_run_elements(list(el), rels=rels, link=link, tracked=tracked)


def _run_text_and_breaks(run_el) -> tuple[str, int]:
    """Concatenates a run's text-bearing children in document order. w:t and
    w:delText (contract §3.1: "both are read as run text") contribute their
    text; w:tab -> '\\t'; w:noBreakHyphen -> U+2011; a soft w:br (no type, or
    type="textWrapping"/"column") -> '\\n', surviving rather than being
    dropped (AC #5). Returns (text, page_break_count) -- a `w:br
    w:type="page"` contributes to the count instead of the text, matching
    contract §5's "counted from w:br w:type=page only"."""
    text_parts: list[str] = []
    page_breaks = 0
    for child in run_el:
        tag = _local(child.tag)
        if tag in ("t", "delText"):
            text_parts.append(child.text or "")
        elif tag == "tab":
            text_parts.append("\t")
        elif tag == "noBreakHyphen":
            text_parts.append("‑")
        elif tag == "br":
            if child.get(_wtag("type")) == "page":
                page_breaks += 1
            else:
                text_parts.append("\n")
        # w:lastRenderedPageBreak, w:cr and anything else: ignored (contract
        # §5 -- Word's cached pagination is not a source of truth).
    return "".join(text_parts), page_breaks


def paragraph_all_text(p_el) -> str:
    """Public seam for stage docx-comments (gts-nxx3): the same emptiness
    test _process_paragraph uses to decide whether a paragraph produces a
    block, exposed so comments.py's independent document-order walk can
    line a paragraph up with the block it produced (or None) without
    duplicating _iter_run_elements/_run_text_and_breaks. No page-break
    bookkeeping — callers that need that use _build_runs directly."""
    text_parts = []
    for run_el, _link, _tracked in _iter_run_elements(list(p_el)):
        text, _pb = _run_text_and_breaks(run_el)
        text_parts.append(text)
    return "".join(text_parts)


def _resolve_hyperlink(hyperlink_el, rels: dict) -> str | None:
    rid = hyperlink_el.get(f"{{{_R}}}id")
    if not rid:
        return None
    rel = rels.get(rid)
    return rel["target"] if rel else None


def _build_runs(paragraph_el, rels: dict, ctx) -> tuple[list[dict], str]:
    """Builds this paragraph's run objects (contract run shape, real
    revision classification per contract §3) and its concatenated text.
    Also advances ctx's page counters for any page-type w:br encountered."""
    runs: list[dict] = []

    for run_el, link, tracked in _iter_run_elements(list(paragraph_el), rels=rels):
        text, page_breaks = _run_text_and_breaks(run_el)
        if page_breaks:
            ctx.current_page += page_breaks
            ctx.explicit_breaks_so_far += page_breaks
            ctx.diagnostics["explicit_page_breaks"] += page_breaks
        if text == "":
            continue
        rpr = run_el.find("w:rPr", NS)
        fmt = _run_format(rpr, link)
        runs.append({
            "kind": "text",
            "text": text,
            "revision": revisions.classify_revision(tracked),
            "format": fmt,
        })

    merged = _merge_adjacent_runs(runs)
    all_text = "".join(r["text"] for r in merged if r["kind"] == "text")
    return merged, all_text


def _merge_adjacent_runs(runs: list[dict]) -> list[dict]:
    out: list[dict] = []
    for run in runs:
        prev = out[-1] if out else None
        if prev and prev["revision"] == run["revision"] and prev["format"] == run["format"]:
            prev["text"] += run["text"]
        else:
            out.append(dict(run))
    return out


# ============================================================================
# CONTEXT / TRAVERSAL
# ============================================================================

class _Ctx:
    def __init__(self, diagnostics: dict):
        self.next_ordinal = 0
        self.unit_stack: list[tuple[dict, int]] = []
        self.current_unit: dict | None = None
        self.units: list[dict] = []
        self.all_blocks: list[dict] = []
        self.diagnostics = diagnostics
        self.current_page = 0
        self.explicit_breaks_so_far = 0
        self.heading_levels: dict[str, int] = {}
        self.num_to_abstract: dict[str, str] = {}
        self.abstract_fmt: dict[str, dict] = {}
        self.rels: dict[str, dict] = {}
        # Stage docx-images (gts-8uo6):
        self.pkg = None
        self.include_images = True
        self.document_images: list[dict] = []


def _push_unit_onto_stack(unit: dict, rank: int, ctx: _Ctx) -> None:
    while ctx.unit_stack and ctx.unit_stack[-1][1] >= rank:
        ctx.unit_stack.pop()
    parent = ctx.unit_stack[-1][0] if ctx.unit_stack else None
    unit["parent_unit_id"] = parent["id"] if parent else None
    ctx.unit_stack.append((unit, rank))


def _make_location(ctx: _Ctx, ordinal: int) -> dict:
    """Thin ctx-shaped wrapper over schema.make_location (moved there in
    stage docx-images, gts-8uo6, so document_export.images can build an
    image block's location the same way, without a structure.py<->images.py
    import cycle)."""
    return make_location(ordinal, ctx.current_page, ctx.explicit_breaks_so_far == 0)


def _create_unit(info: dict, ctx: _Ctx) -> dict:
    ordinal = ctx.next_ordinal
    unit = {
        "id": make_unit_id(SEGMENT_MAIN, info["kind"], info["title"], ordinal),
        "kind": info["kind"],
        "title": info["title"],
        "parent_unit_id": None,
        "kind_evidence": info["kind_evidence"],
        "semantic_state": info["semantic_state"],
        "semantic_state_evidence": info["semantic_state_evidence"],
        "source_order": ordinal,
        "location": _make_location(ctx, ordinal),
        "citation_hint": None,
        "color_signals": [],
        "comment_ids": [],
        "blocks": [],
    }
    _push_unit_onto_stack(unit, info["rank"], ctx)
    return unit


def _create_synthetic_root_unit(ctx: _Ctx) -> dict:
    ordinal = ctx.next_ordinal
    unit = {
        "id": make_unit_id(SEGMENT_MAIN, "document_part", "Document", ordinal),
        "kind": "document_part",
        "title": "Document",
        "parent_unit_id": None,
        "kind_evidence": [],
        "semantic_state": "baseline",
        "semantic_state_evidence": [],
        "source_order": ordinal,
        "location": _make_location(ctx, ordinal),
        "citation_hint": None,
        "color_signals": [],
        "comment_ids": [],
        "blocks": [],
    }
    _push_unit_onto_stack(unit, -1, ctx)
    return unit


def _process_paragraph(p_el, ctx: _Ctx) -> None:
    ppr = p_el.find("w:pPr", NS)
    style_id = None
    num_pr = None
    if ppr is not None:
        pstyle = ppr.find("w:pStyle", NS)
        style_id = pstyle.get(_wtag("val")) if pstyle is not None else None
        num_pr = ppr.find("w:numPr", NS)

    heading_level = ctx.heading_levels.get(style_id) if style_id else None
    runs, all_text = _build_runs(p_el, ctx.rels, ctx)

    # A peek, not an extraction -- just "does this paragraph carry a
    # drawing at all", so the heading-fallback branch below can tell an
    # image-only heading (opens a unit) from a truly blank one (does not).
    # The real extraction (ordinal consumption included) still happens
    # below, in its original GAS-mirroring position.
    has_image = images.has_drawing(p_el)

    # Unit detection runs against allText unconditionally -- including an
    # empty string, which no GOVERNANCE_UNIT_PATTERNS entry matches and
    # which only reaches the heading-fallback branch for a heading-styled
    # paragraph that is otherwise empty of text, and then only when it
    # carries an image (mirrors GAS's own detectSemanticUnit_(allText, ...)
    # -> allText.trim() ordering, unchanged since before stage docx-images;
    # gts-pczo.1 AC #3 narrowed this further -- see _detect_governance_unit).
    unit_info = _detect_governance_unit(all_text, heading_level, has_image)
    opened_unit_this_paragraph = False
    if unit_info:
        ctx.current_unit = _create_unit(unit_info, ctx)
        ctx.units.append(ctx.current_unit)
        ctx.diagnostics["units"] += 1
        opened_unit_this_paragraph = True
    elif ctx.current_unit is None:
        ctx.current_unit = _create_synthetic_root_unit(ctx)
        ctx.units.append(ctx.current_unit)
        ctx.diagnostics["units"] += 1
        opened_unit_this_paragraph = True

    # Images are extracted before the text-block emptiness check (stage
    # docx-images, gts-8uo6) -- mirrors GAS's processInlineImages_ ->
    # allText.trim() ordering: an image-only paragraph produces no text
    # block, only the image block(s) below, attached to the unit just
    # resolved above.
    if ctx.include_images:
        images.process_inline_images(p_el, ctx.pkg, ctx.rels, ctx)

    if not all_text.strip():
        # gts-pczo.1 AC #2: a unit opened above (_create_unit/
        # _create_synthetic_root_unit) stamps its id from ctx.next_ordinal
        # without incrementing it -- by design, so a unit and the text block
        # that opens it share one ordinal (contract: "a unit id and its
        # first block id agree on their tail number"). But when this
        # paragraph produces no text block (this branch), that ordinal is
        # never claimed by anything else and must be consumed here, or the
        # next unit/block to ask for one collides with it (duplicate ids).
        # Any image(s) above already consumed their own, separate ordinals.
        if opened_unit_this_paragraph:
            ctx.next_ordinal += 1
        return  # image-only or wholly-empty paragraph -- no text block.

    ordinal = ctx.next_ordinal
    ctx.next_ordinal += 1

    label = _detect_bold_colon_label(_raw_runs_for_label(p_el, ctx.rels))
    semantic = _detect_semantic_state(all_text)
    list_info = _resolve_list(num_pr, ctx.num_to_abstract, ctx.abstract_fmt) if num_pr is not None else None
    kind = _classify_block(heading_level, num_pr is not None, label, semantic["state"])
    named_style = f"HEADING_{heading_level}" if heading_level else "NORMAL_TEXT"

    revision_summary = revisions.summarize_revision(runs)

    block = {
        "id": make_block_id(SEGMENT_MAIN, ordinal),
        "unit_id": ctx.current_unit["id"],
        "kind": kind,
        "semantic_state": semantic["state"],
        "semantic_state_evidence": semantic["evidence"],
        "label": label["text"] if label else None,
        "named_style": named_style,
        "heading_level": heading_level,
        "source_order": ordinal,
        "location": _make_location(ctx, ordinal),
        "list": list_info,
        "runs": runs,
        "revision_summary": revision_summary,
        "comment_ids": [],
    }
    # §13.3: unchanged blocks get a single canonical `text` field; blocks
    # with any revision activity get the all_text/baseline_text/
    # proposed_text trio instead -- never both (contract §3.2, gts-e7ca's
    # inherited invariant).
    if revision_summary == "unchanged":
        block["text"] = revisions.build_view_text(runs, "all", semantic["state"])
    else:
        block["all_text"] = revisions.build_view_text(runs, "all", semantic["state"])
        block["baseline_text"] = revisions.build_view_text(runs, "baseline", semantic["state"])
        block["proposed_text"] = revisions.build_view_text(runs, "proposed", semantic["state"])
    block["citation_hint"] = make_citation_hint(ctx.current_unit, block)

    ctx.current_unit["blocks"].append(block)
    ctx.all_blocks.append(block)
    ctx.diagnostics["blocks"] += 1
    ctx.diagnostics["runs"] += len(runs)
    for run in runs:
        if run["kind"] != "text":
            continue
        change = run["revision"]["change"]
        if change == "inserted":
            ctx.diagnostics["proposed_insertions"] += 1
        elif change == "deleted":
            ctx.diagnostics["suggested_deletions"] += 1


def _raw_runs_for_label(p_el, rels) -> list[dict]:
    """Rebuilds the {"text", "bold"} sequence _detect_bold_colon_label needs,
    from the paragraph's raw run elements (same traversal as _build_runs, but
    label detection must see runs in their pre-merge, pre-empty-filtered
    form -- mirroring detectBoldColonLabel_ operating on paragraph.elements
    directly rather than on the already-merged run objects)."""
    out = []
    for run_el, _link, _tracked in _iter_run_elements(list(p_el)):
        text, _pb = _run_text_and_breaks(run_el)
        rpr = run_el.find("w:rPr", NS)
        bold = False
        if rpr is not None:
            b_el = rpr.find("w:b", NS)
            if b_el is not None:
                val = b_el.get(_wtag("val"))
                bold = val not in ("0", "false", "none") if val is not None else True
        out.append({"text": text, "bold": bold})
    return out


def _process_content(elements, ctx: _Ctx) -> None:
    for el in elements:
        tag = _local(el.tag)
        if tag == "p":
            _process_paragraph(el, ctx)
        elif tag == "tbl":
            _process_table(el, ctx)
        elif tag == "sdt":
            # gts-pczo.1 AC #1: a body-level w:sdt (Google Docs' own export
            # artifact -- observed as a goog_rdk_* tag wrapping a single
            # paragraph) is not structural content itself, but its
            # w:sdtContent can hold a real w:p/w:tbl that must still be
            # walked -- otherwise the whole paragraph (and any unit heading
            # it opens) silently vanishes. Mirrors _iter_run_elements's own
            # sdt/sdtContent passthrough for the run-level walk.
            sdt_content = el.find("w:sdtContent", NS)
            if sdt_content is not None:
                _process_content(list(sdt_content), ctx)
        # sectPr and anything else at this level: not structural content.


def _process_table(tbl_el, ctx: _Ctx) -> None:
    row_index = 0
    for row in tbl_el.findall("w:tr", NS):
        col_index = 0
        for cell in row.findall("w:tc", NS):
            before = len(ctx.all_blocks)
            _process_content(list(cell), ctx)
            after = len(ctx.all_blocks)
            for i in range(before, after):
                # Snapshot-based tagging (not ctx.current_unit.blocks, which
                # may point at a different unit by the time the cell
                # finishes) -- ctx.all_blocks is stable across unit switches,
                # so this preserves {row, column} even after a mid-cell unit
                # switch (gts-qjkj invariant, AC #3).
                ctx.all_blocks[i]["table"] = {"row": row_index, "column": col_index}
            col_index += 1
        row_index += 1


def _finalize_units(units: list[dict]) -> list[dict]:
    """§13.4: omit kind_evidence/semantic_state_evidence/color_signals/
    runs[].revision.evidence entirely when empty (AC #4). `comment_ids` is
    deliberately NOT finalized here: stage docx-comments (gts-nxx3) attaches
    it after this pass returns, by mutating these same unit/block dicts —
    finalizing it here would drop the key before comments.py ever gets to
    populate it. comments.resolve_comments finalizes comment_ids itself,
    once comment resolution is done."""
    for unit in units:
        drop_if_empty(unit, "kind_evidence")
        drop_if_empty(unit, "semantic_state_evidence")
        drop_if_empty(unit, "color_signals")
        for block in unit["blocks"]:
            drop_if_empty(block, "semantic_state_evidence")
            for run in block.get("runs", []):
                if run.get("kind") == "text":
                    drop_if_empty(run["revision"], "evidence")

    return units


def walk_structure(pkg, diagnostics: dict, include_images: bool = True) -> tuple[list[dict], list[dict]]:
    """Contract §7.1 entry point for this module. Walks word/document.xml's
    body and returns (units[], document.images[]) -- units each with their
    blocks[], §13.4's empty-array omission already applied; document_images
    is the mirrored `document.images[]` array images.py accumulates on ctx
    as it runs interleaved with the same traversal (stage docx-images,
    gts-8uo6) -- there is no separate image pass, matching GAS's own
    processInlineImages_ call from inside processParagraph_. `include_images`
    False skips image extraction entirely: no image blocks, no ordinals
    consumed for drawings, document_images stays []. Mutates `diagnostics`
    in place (units/blocks/runs/images/explicit_page_breaks counts) -- the
    same contract build.py's other passes (stage 2's tabs_detected) already
    use."""
    ctx = _Ctx(diagnostics)
    ctx.heading_levels = _load_heading_levels(pkg)
    ctx.num_to_abstract, ctx.abstract_fmt = _load_numbering(pkg)
    ctx.rels = pkg.document_rels()
    ctx.pkg = pkg
    ctx.include_images = include_images

    document_root = pkg.xml("document")
    body = document_root.find("w:body", NS) if document_root is not None else None
    if body is not None:
        _process_content(list(body), ctx)

    return _finalize_units(ctx.units), ctx.document_images
