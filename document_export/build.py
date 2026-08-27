"""build_export(...) — the offline seam (contract §7.2).

Pure: no network, no filesystem writes. Takes .docx bytes, returns a dict.
This is what makes stages 3-6 testable against a checked-in fixture with no
Google auth, and what lets acquisition tiers (contract §7.3) be swapped
without touching parsing code.

Stage 2 (gts-28hx) scope was a structurally valid but near-empty artifact —
document metadata, schema_version, diagnostics, no blocks. Stage 3
(docx-structure, gts-pmga) adds real units/blocks/runs/tables/numbering via
document_export.structure.walk_structure. Stage 4 (docx-comments, gts-nxx3)
adds comment anchoring via document_export.comments.resolve_comments. Stage 5
(docx-revisions, gts-9c8k) adds real revision classification -- structure.py
now classifies each run's w:ins/w:del state inline (document_export.revisions
.classify_revision), and this module adds document.suggestion_groups
(document_export.revisions.build_suggestion_groups) and the top-level
views.* (document_export.revisions.build_document_views). Stage 6
(docx-images, gts-8uo6) adds image extraction -- document_export.structure's
own paragraph walk calls document_export.images.process_inline_images
interleaved with text-block emission (mirrors GAS's own
processInlineImages_ call from inside processParagraph_), so this module's
own change is just threading the includeImages option through and adding
document.images[] to the output.
"""
from __future__ import annotations

import datetime as _dt

from document_export.comments import resolve_comments
from document_export.package import DocxPackage
from document_export.revisions import build_document_views, build_suggestion_groups
from document_export.schema import PRODUCER, SCHEMA_VERSION
from document_export.structure import walk_structure

# Contract §7.5 / ADR-0026 Consequences: emitted whenever tabs cannot be
# counted, which today is unconditional (cookie auth cannot reach the Docs
# API — package.tabs_detected() always returns None). Text must instruct the
# reader to verify what was actually downloaded, not merely note the
# condition (contract §7.5).
_TABS_UNKNOWN_WARNING = (
    "Tab count could not be determined: this pipeline authenticates via a "
    "cookie session, which cannot reach the Docs API to count tabs "
    "(ADR-0026 Consequences; deferred by gts-11rq). If the source document "
    "may have multiple Google Docs tabs, verify what was actually "
    "downloaded — Google's .docx converter's tab behavior (concatenate, "
    "drop, or otherwise alter tab content) is unverified and this pipeline "
    "cannot detect it."
)


def _empty_diagnostics() -> dict:
    return {
        "units": 0,
        "blocks": 0,
        "runs": 0,
        "proposed_insertions": 0,
        "suggested_deletions": 0,
        "comments": 0,
        "unresolved_comments": 0,
        # contract §5: unanchored_comments replaces unmatched_comments.
        "unanchored_comments": 0,
        "explicit_page_breaks": 0,
        "distinct_suggestion_ids": 0,
        "toc_entries": 0,
        "images": 0,
        # contract §5: null means "could not determine", never "zero".
        "tabs_detected": None,
        "warnings": [],
    }


def build_export(
    docx_bytes: bytes,
    *,
    doc_id: str | None = None,
    title: str | None = None,
    options: dict | None = None,
) -> dict:
    """Contract §7.2. `options` accepts `includeWholeDocumentViews` (default
    False) and `includeImages` (default True) — both are validated here and
    threaded through unused until stages 4/6 add the passes that consume
    them, so the CLI's flags have somewhere real to land today."""
    opts = dict(options or {})
    include_whole_document_views = bool(opts.get("includeWholeDocumentViews", False))
    include_images = bool(opts.get("includeImages", True))

    pkg = DocxPackage(docx_bytes)  # raises PackageError if word/document.xml is missing

    resolved_title = title or doc_id or "document"
    source_url = (
        f"https://docs.google.com/document/d/{doc_id}/edit" if doc_id else None
    )

    diagnostics = _empty_diagnostics()
    diagnostics["tabs_detected"] = pkg.tabs_detected()
    if diagnostics["tabs_detected"] is None:
        diagnostics["warnings"].append(_TABS_UNKNOWN_WARNING)

    units, document_images = walk_structure(pkg, diagnostics, include_images)
    comments = resolve_comments(pkg, units, diagnostics)
    suggestion_groups = build_suggestion_groups(units)
    diagnostics["distinct_suggestion_ids"] = len(suggestion_groups)

    out: dict = {
        "schema_version": SCHEMA_VERSION,
        "producer": PRODUCER,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "document": {
            "id": doc_id,
            "title": resolved_title,
            # No OOXML/Drive-API equivalent reachable over the cookie
            # session this pipeline uses (contract does not name this field
            # in its §5 degradation table — recorded as a contract gap in
            # this stage's handoff, not silently resolved here).
            "revision_id": None,
            "source_url": source_url,
            "suggestion_groups": suggestion_groups,
            "toc": [],
        },
        "semantics": {
            "baseline": "Text against which proposed revisions are evaluated.",
            "proposed": "Unchanged baseline plus proposed insertions, excluding deletions.",
            "historical": "Old or superseded material retained for reference.",
            "editorial": "Drafting/reviewer material not intended as governance text.",
        },
        "page_numbering": {
            "exact_rendered_page_map_available": False,
            "default_basis": "explicit_page_break_count",
            "warning": (
                "Word does not expose a universal body-text range to final "
                "rendered page mapping. Page values are best effort unless "
                "the source uses explicit page breaks (w:br w:type=\"page\"; "
                "w:lastRenderedPageBreak is ignored — contract §5)."
            ),
        },
        # contract §3.3 — a fact of this pipeline (w:ins/w:del carry
        # w:author/w:date directly), not data-dependent, so it is fixed here
        # rather than computed per-document.
        "suggestion_authorship": {
            "resolvable": True,
            "basis": "ooxml_w_ins_w_del_author",
        },
        "units": units,
        "comments": comments,
        "views": build_document_views(units, include_whole_document_views),
        "diagnostics": diagnostics,
    }
    # contract §7.5: document.toc is omitted entirely (not []) when empty.
    # Stage docx-structure does not populate it (TOC diversion is not this
    # stage's scope -- see handoff); applying the omission rule now keeps
    # today's always-empty toc list schema-correct regardless.
    if not out["document"]["toc"]:
        del out["document"]["toc"]
    # contract §4 / §13.4: document.images[] is omitted entirely (key
    # absent, not []) when the document has no (extractable) images, or when
    # includeImages=False suppressed extraction.
    if document_images:
        out["document"]["images"] = document_images
    return out
