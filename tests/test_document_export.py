"""
test_document_export.py — gts-2glm, [TST] twin of gts-ipoy (document
JSON exporter, src/Procedure-Exporter.js).

Entry point: WebApp.js's 'export_document_json' route -> exportDocument_()
via the options.docId testability seam this bead added (exportDocument_
otherwise only resolves DocumentApp.getActiveDocument(), which is add-on-UI-
session-only and has no headless call-site). Production entry points
(onDocumentExportMenu/onDocumentExportAndPdfMenu, the Extensions-menu
universalActions in Procedure-Exporter.js) never pass docId and are
unaffected by the seam. The classic-menu Export dialog's google.script.run
path (runExportForDialog/getExportProgressForDialog, gts-s7ut) is a
separate, not-yet-covered call-site.

Seed content is built via two generic, test-only passthrough routes added
alongside the seam:
  - seed_doc_content: Docs.Documents.batchUpdate() passthrough (headings,
    text, page breaks, highlight colors, bold labels).
  - create_doc_comment: DriveV3.Comments.create() passthrough (real Drive
    comments with quoted_text, driving associateCommentsToBlocks_).
Both are testToken-gated, construct-fixtures-only routes — never called by
production code or by the exporter itself.

Known scope gap (documented in gts-2glm's bd notes, not silently dropped):
suggestion_groups/possible_authors and autoText run preservation are NOT
covered here. The Docs API has no public way to create a Google Docs
Suggested-edit or an autoText page-number field via batchUpdate (read-only
for both), so they cannot be seeded live. See
tests/test_document_export_pure.js for the pure-function track that
covers those two ACs against hand-built Docs-API-shaped fixture objects.
Also out of scope this session: table mid-cell unit-switch tagging, and the
prefix/cross-paragraph/fuzzy comment-match tiers beyond exact — flagged as
open follow-up in gts-2glm rather than silently skipped.

gts-1nw8/gts-crzl scope gap: `document.toc` (§7.5) cannot be covered live —
confirmed by probing `insertTableOfContents` against the real Docs API
batchUpdate endpoint: "Unknown name insertTableOfContents ... Cannot find
field." Table-of-contents insertion is a Docs UI-only feature with no public
API surface, same category as the suggested-edits gap above. TOC parsing
(processTableOfContents_/buildTocEntry_ in Procedure-Exporter.js) was instead
verified live via a one-off manual read against a real customer document that
already had an Insert > Table of contents TOC (docId
1zQkRAczbRjB0iRD2OhpHsqXvHsmskE8VI7VNx8vE5yE, gts-6cq2's sample export) — see
gts-1nw8's close notes for the result. No repeatable pytest coverage exists
for the TOC-entry-shape/link-extraction path; a future fixture-doc with a
pre-baked real TOC (created once by hand via the Docs UI, then reused
read-only across test runs) would close this gap.
"""
import pytest

from scn.session import ScenarioSession


# ---------------------------------------------------------------------------
# Seed-content helpers (Docs API batchUpdate passthrough; test-only)
# ---------------------------------------------------------------------------

def _end_index(scn: ScenarioSession) -> int:
    """Insertion index just before the body's trailing empty paragraph."""
    resp = scn._post_route("dump_doc_paragraphs", {"docId": scn.doc_id})
    elements = resp["elements"]
    return elements[-1]["end"] - 1


def _insert_text(scn: ScenarioSession, text: str) -> tuple[int, int]:
    start = _end_index(scn)
    resp = scn._post_route("seed_doc_content", {
        "docId": scn.doc_id,
        "requests": [{"insertText": {"location": {"index": start}, "text": text}}],
    })
    assert resp.get("ok"), resp
    return start, start + len(text)


def _style_paragraph(scn: ScenarioSession, start: int, end: int, named_style: str) -> None:
    resp = scn._post_route("seed_doc_content", {
        "docId": scn.doc_id,
        "requests": [{"updateParagraphStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "paragraphStyle": {"namedStyleType": named_style},
            "fields": "namedStyleType",
        }}],
    })
    assert resp.get("ok"), resp


def _insert_heading(scn: ScenarioSession, text: str, level: int = 1) -> tuple[int, int]:
    start, end = _insert_text(scn, text + "\n")
    _style_paragraph(scn, start, end - 1, f"HEADING_{level}")
    return start, end


def _insert_bold_label(scn: ScenarioSession, label: str, rest: str) -> tuple[int, int]:
    """A bold `Label:` prefix followed by plain rest-of-paragraph text."""
    prefix = f"{label}:"
    text = f"{prefix} {rest}\n"
    start, end = _insert_text(scn, text)
    resp = scn._post_route("seed_doc_content", {
        "docId": scn.doc_id,
        "requests": [{"updateTextStyle": {
            "range": {"startIndex": start, "endIndex": start + len(prefix)},
            "textStyle": {"bold": True},
            "fields": "bold",
        }}],
    })
    assert resp.get("ok"), resp
    return start, end


def _strikethrough(scn: ScenarioSession, start: int, end: int) -> None:
    """Sets textStyle.strikethrough — the one revision-activity signal that
    Docs' batchUpdate can seed live (suggested insertions/deletions cannot,
    per the module docstring). makeTextRun_ treats a bare strikethrough run
    as change='deleted', which is enough to drive revision_summary into
    'deletions' and exercise the all_text/baseline_text/proposed_text trio
    path (§13.3)."""
    resp = scn._post_route("seed_doc_content", {
        "docId": scn.doc_id,
        "requests": [{"updateTextStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "textStyle": {"strikethrough": True},
            "fields": "strikethrough",
        }}],
    })
    assert resp.get("ok"), resp


def _highlight(scn: ScenarioSession, start: int, end: int, hex_color: str) -> None:
    rgb = {
        "red": int(hex_color[0:2], 16) / 255.0,
        "green": int(hex_color[2:4], 16) / 255.0,
        "blue": int(hex_color[4:6], 16) / 255.0,
    }
    resp = scn._post_route("seed_doc_content", {
        "docId": scn.doc_id,
        "requests": [{"updateTextStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "textStyle": {"backgroundColor": {"color": {"rgbColor": rgb}}},
            "fields": "backgroundColor",
        }}],
    })
    assert resp.get("ok"), resp


def _insert_page_break(scn: ScenarioSession) -> None:
    idx = _end_index(scn)
    resp = scn._post_route("seed_doc_content", {
        "docId": scn.doc_id,
        "requests": [{"insertPageBreak": {"location": {"index": idx}}}],
    })
    assert resp.get("ok"), resp


def _create_comment(scn: ScenarioSession, content: str, quoted_text: str | None = None) -> str:
    payload = {"docId": scn.doc_id, "content": content}
    if quoted_text is not None:
        payload["quotedText"] = quoted_text
    resp = scn._post_route("create_doc_comment", payload)
    assert resp.get("ok"), resp
    return resp["commentId"]


def _export(scn: ScenarioSession, export_pdf: bool = False, include_whole_document_views: bool = False) -> dict:
    resp = scn._post_route("export_document_json", {
        "docId": scn.doc_id,
        "exportPdf": export_pdf,
        "includeWholeDocumentViews": include_whole_document_views,
    })
    assert resp.get("ok"), resp
    return resp["json"]


def _export_raw(scn: ScenarioSession, doc_id: str | None = None) -> dict:
    """Like _export, but returns the full response envelope (exportFolderId,
    jsonFileId) instead of unwrapping to just the JSON payload — gts-es3l's
    export-folder-isolation assertions need the envelope, not the document
    content. doc_id defaults to scn.doc_id; pass explicitly for a second doc
    that isn't scn's own (see test_export_document_folder_isolation_*)."""
    resp = scn._post_route("export_document_json", {"docId": doc_id or scn.doc_id})
    assert resp.get("ok"), resp
    return resp


def _rename(scn: ScenarioSession, doc_id: str, title: str) -> None:
    resp = scn._post_route("rename_doc_for_test", {"docId": doc_id, "title": title})
    assert resp.get("ok"), resp


def _export_index_rows(scn: ScenarioSession, doc_id: str) -> list[dict]:
    resp = scn._post_route("dump_export_index_for_test", {"docId": doc_id})
    assert resp.get("ok"), resp
    return resp["rows"]


def _all_blocks(doc_json: dict) -> list[dict]:
    blocks = []
    for unit in doc_json["units"]:
        blocks.extend(unit["blocks"])
    return blocks


def _unit_by_kind(doc_json: dict, kind: str) -> dict:
    matches = [u for u in doc_json["units"] if u["kind"] == kind]
    assert len(matches) == 1, f"expected exactly one '{kind}' unit, got {len(matches)}: {matches}"
    return matches[0]


# ---------------------------------------------------------------------------
# Entry-point call-site + basic output shape
# ---------------------------------------------------------------------------

def test_export_document_entry_point_basic_shape(settings, request):
    """Call-site coverage for exportDocument_() via export_document_json
    (WebApp.js) — the entry point itself is the call-site, per this project's
    entry-point coverage invariant."""
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_heading(scn, "Board Policy 1: Test Governance Policy", level=1)
    _insert_text(scn, "This is baseline body text.\n")

    doc = _export(scn)

    assert doc["schema_version"] == "2.5"
    assert doc["document"]["id"] == scn.doc_id
    assert doc["diagnostics"]["tabs_processed"] == 1
    assert doc["diagnostics"]["units"] >= 1
    assert doc["diagnostics"]["blocks"] >= 2

    policy = _unit_by_kind(doc, "policy")
    assert policy["kind_evidence"] == [{"type": "text_pattern", "rule": "policy_numbered"}]
    assert policy["title"] == "Board Policy 1: Test Governance Policy"


# ---------------------------------------------------------------------------
# unit.parent_unit_id hierarchy (rank-based containment)
# ---------------------------------------------------------------------------

def test_export_document_parent_unit_id_hierarchy(settings, request):
    """A procedure (rank 3) nested under a policy (rank 2) records the
    policy as its parent; a following plain paragraph belongs to the
    procedure unit (deepest open unit at that point in traversal)."""
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_heading(scn, "Board Policy 2: Parent Policy", level=1)
    _insert_heading(scn, "Board Procedure 2-1: Child Procedure", level=2)
    _insert_text(scn, "Procedure body text.\n")

    doc = _export(scn)

    policy = _unit_by_kind(doc, "policy")
    procedure = _unit_by_kind(doc, "procedure")
    assert procedure["parent_unit_id"] == policy["id"]
    assert policy["parent_unit_id"] is None

    # §13.3: this block has no revision activity, so it carries the
    # canonical `text` field, not all_text/baseline_text/proposed_text.
    body_block = next(b for b in procedure["blocks"] if b["text"].startswith("Procedure body"))
    assert body_block["unit_id"] == procedure["id"]
    assert "all_text" not in body_block
    assert "baseline_text" not in body_block
    assert "proposed_text" not in body_block


# ---------------------------------------------------------------------------
# location.page_approximate under explicit page breaks
# ---------------------------------------------------------------------------

def test_export_document_page_approximate_transitions_on_explicit_break(settings, request):
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_text(scn, "Before any explicit page break.\n")
    _insert_page_break(scn)
    _insert_text(scn, "After the explicit page break.\n")

    doc = _export(scn)
    blocks = _all_blocks(doc)
    before = next(b for b in blocks if b["text"].startswith("Before any"))
    after = next(b for b in blocks if b["text"].startswith("After the"))

    assert before["location"]["page_approximate"] is True
    assert after["location"]["page_approximate"] is False
    assert after["location"]["page"] > before["location"]["page"]
    assert doc["diagnostics"]["explicit_page_breaks"] == 1


# ---------------------------------------------------------------------------
# text_pattern / style_pattern evidence emission
# ---------------------------------------------------------------------------

def test_export_document_semantic_state_text_pattern_evidence(settings, request):
    """SEMANTIC_STATE_PATTERNS ('(OLD)' prefix) is recorded as text_pattern
    evidence on both the unit (heading line) and a plain historical block."""
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_heading(scn, "(OLD) Board Policy 3: Superseded Policy", level=1)
    _insert_text(scn, "OLD - retained for comparison only.\n")

    doc = _export(scn)
    policy = _unit_by_kind(doc, "policy")
    assert policy["semantic_state"] == "historical"
    assert policy["semantic_state_evidence"] == [{"type": "text_pattern", "rule": "old_paren_prefix"}]

    # The heading paragraph is itself also emitted as a block (every paragraph
    # is), and since its semantic_state is 'historical' it too gets kind
    # 'historical_note' — exclude it (heading_level is not None) so this
    # matches the plain "OLD - ..." paragraph, not the unit's own heading.
    historical_block = next(
        b for b in _all_blocks(doc)
        if b["kind"] == "historical_note" and b["heading_level"] is None
    )
    assert historical_block["semantic_state_evidence"] == [{"type": "text_pattern", "rule": "old_dash_prefix"}]
    assert doc["diagnostics"]["historical_blocks"] >= 1


def test_export_document_bold_colon_label_style_pattern(settings, request):
    """A bold `Intent:` prefix is detected via detectBoldColonLabel_ and
    surfaces as block.label / kind 'labeled_paragraph'."""
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_bold_label(scn, "Intent", "State the purpose of this policy.")

    doc = _export(scn)
    block = next(b for b in _all_blocks(doc) if b["label"] == "Intent")
    assert block["kind"] == "labeled_paragraph"
    assert block["text"].startswith("Intent: State the purpose")


# ---------------------------------------------------------------------------
# unit.color_signals scoping (no cross-unit leakage)
# ---------------------------------------------------------------------------

def test_export_document_color_signals_scoped_per_unit(settings, request):
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_heading(scn, "Board Policy 4: Unit A", level=1)
    a_start, a_end = _insert_text(scn, "Highlighted text in unit A.\n")
    _highlight(scn, a_start, a_end - 1, "FFFF00")

    _insert_heading(scn, "Board Policy 5: Unit B", level=1)
    b_start, b_end = _insert_text(scn, "Plain text in unit B, no highlight.\n")

    doc = _export(scn)
    unit_a = next(u for u in doc["units"] if u["title"] == "Board Policy 4: Unit A")
    unit_b = next(u for u in doc["units"] if u["title"] == "Board Policy 5: Unit B")

    assert len(unit_a["color_signals"]) == 1
    assert unit_a["color_signals"][0]["background_color"] == "#FFFF00"
    # §13.4: an empty color_signals array is omitted entirely, not emitted
    # as `[]` — absence has the same meaning (no color signal found).
    assert "color_signals" not in unit_b

    assert any("Manual highlight colors" in w for w in doc["diagnostics"]["warnings"])


# ---------------------------------------------------------------------------
# Comment-to-document traceability (associateCommentsToBlocks_)
# ---------------------------------------------------------------------------

def test_export_document_comment_association_exact_match(settings, request):
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_heading(scn, "Board Policy 6: Commented Policy", level=1)
    _insert_text(scn, "This sentence will be quoted by a review comment.\n")

    _create_comment(
        scn,
        "Please clarify this sentence.",
        quoted_text="This sentence will be quoted by a review comment.",
    )

    doc = _export(scn)
    assert doc["diagnostics"]["comments"] == 1
    comment = doc["comments"][0]
    assert comment["association_basis"] == "quoted_text_exact"
    assert len(comment["associated_block_ids"]) == 1

    policy = _unit_by_kind(doc, "policy")
    assert comment["associated_unit_ids"] == [policy["id"]]
    assert [p["id"] for p in comment["section_path"]] == [policy["id"]]

    block = next(b for b in policy["blocks"] if b["id"] == comment["associated_block_ids"][0])
    assert comment["id"] in block["comment_ids"]
    assert comment["id"] in policy["comment_ids"]


def test_export_document_comment_association_unmatched(settings, request):
    """A comment whose quoted text was subsequently edited/removed from the
    doc gets the first-class 'unmatched' terminal state (proves the miss
    case isn't silently indistinguishable from an empty not-yet-processed
    array — see associateCommentsToBlocks_'s doc comment)."""
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_text(scn, "Some unrelated baseline paragraph.\n")

    _create_comment(
        scn,
        "This quote does not exist anywhere in the document body.",
        quoted_text="This quote does not exist anywhere in the document body.",
    )

    doc = _export(scn)
    comment = doc["comments"][0]
    assert comment["association_basis"] == "unmatched"
    assert comment["associated_block_ids"] == []
    assert comment["associated_unit_ids"] == []
    assert doc["diagnostics"]["unmatched_comments"] == 1
    assert any("could not be associated" in w for w in doc["diagnostics"]["warnings"])


# ---------------------------------------------------------------------------
# §13.3 conditional block-text emission (gts-6cq2)
# ---------------------------------------------------------------------------

def test_export_document_unchanged_block_emits_canonical_text_only(settings, request):
    """revision_summary='unchanged' -> single canonical `text` field; the
    all_text/baseline_text/proposed_text trio is omitted entirely (they
    would be byte-identical copies)."""
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_text(scn, "Plain unchanged paragraph, no edits.\n")

    doc = _export(scn)
    block = next(b for b in _all_blocks(doc) if b["text"].startswith("Plain unchanged"))

    assert block["revision_summary"] == "unchanged"
    assert "all_text" not in block
    assert "baseline_text" not in block
    assert "proposed_text" not in block


def test_export_document_revised_block_emits_view_trio_only(settings, request):
    """A block with revision activity (here: strikethrough, seedable live
    per makeTextRun_'s bare-strikethrough='deleted' rule) emits
    all_text/baseline_text/proposed_text and omits the canonical `text`
    field. baseline_text retains the struck text; proposed_text excludes
    it — same semantics as the pre-existing baseline/proposed view logic,
    just gated on presence rather than always-on."""
    scn = ScenarioSession.new_doc(settings, request=request)
    start, end = _insert_text(scn, "Kept text and struck text.\n")
    struck_start = start + len("Kept text and ")
    struck_end = struck_start + len("struck text.")
    _strikethrough(scn, struck_start, struck_end)

    doc = _export(scn)
    block = next(b for b in _all_blocks(doc) if b.get("all_text", "").startswith("Kept text and"))

    assert block["revision_summary"] == "deletions"
    assert "text" not in block
    assert block["all_text"] == "Kept text and struck text.\n"
    assert "struck text." in block["baseline_text"]
    assert "struck text." not in block["proposed_text"]


def test_export_document_comment_matching_falls_back_to_canonical_text(settings, request):
    """associateCommentsToBlocks_ (quoted-text exact match) reads
    blockAllText_(), which must fall back to `text` on an unchanged block
    that no longer carries `all_text`."""
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_text(scn, "Unchanged sentence quoted by a comment.\n")
    _create_comment(scn, "note", quoted_text="Unchanged sentence quoted by a comment.")

    doc = _export(scn)
    comment = doc["comments"][0]
    assert comment["association_basis"] == "quoted_text_exact"
    assert len(comment["associated_block_ids"]) == 1


def test_export_document_views_fallback_to_canonical_text(settings, request):
    """buildDocumentViews_'s baseline_text/proposed_text reconstructions
    must include unchanged blocks (which only carry `text`) as well as
    revised blocks (which carry the baseline_text/proposed_text trio).
    §13.1/13.2: these views are opt-in (gts-1nw8) — request them explicitly."""
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_text(scn, "Unchanged view line.\n")
    start, end = _insert_text(scn, "Revised view line struck.\n")
    struck_start = start + len("Revised view line ")
    struck_end = struck_start + len("struck.")
    _strikethrough(scn, struck_start, struck_end)

    doc = _export(scn, include_whole_document_views=True)
    assert "Unchanged view line." in doc["views"]["baseline_text"]
    assert "Unchanged view line." in doc["views"]["proposed_text"]
    assert "struck." in doc["views"]["baseline_text"]
    assert "struck." not in doc["views"]["proposed_text"]


def test_export_document_schema_version_is_2_5(settings, request):
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_text(scn, "Version check paragraph.\n")
    doc = _export(scn)
    assert doc["schema_version"] == "2.5"


# ---------------------------------------------------------------------------
# §13.4 structural-field presence (id/kind/... stay present even when null)
# ---------------------------------------------------------------------------

def test_export_document_scalar_structural_fields_stay_present_when_null(settings, request):
    """label/list/parent_unit_id etc. are never omitted, even when null —
    only the five array fields in §13.4 are conditionally dropped."""
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_text(scn, "Plain root-level paragraph.\n")

    doc = _export(scn)
    block = next(b for b in _all_blocks(doc) if b["text"].startswith("Plain root-level"))

    for key in ("id", "kind", "unit_id", "label",
                "named_style", "heading_level", "list", "location"):
        assert key in block, f"{key} must be present even when null"
    assert block["label"] is None
    assert block["list"] is None


# ---------------------------------------------------------------------------
# §7.5 document.toc — insertTableOfContents is not seedable live (see module
# docstring); this covers only the no-TOC-present omission side.
# ---------------------------------------------------------------------------

def test_export_document_toc_omitted_when_no_toc_present(settings, request):
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_heading(scn, "Board Policy 7: No TOC Here", level=1)
    _insert_text(scn, "A document with no table of contents.\n")

    doc = _export(scn)
    assert "toc" not in doc["document"]
    assert doc["diagnostics"]["toc_entries"] == 0


# ---------------------------------------------------------------------------
# §13.5 control-character normalization (derived text only)
# ---------------------------------------------------------------------------

def test_export_document_derived_text_normalizes_nbsp_and_vertical_tab(settings, request):
    """NBSP and vertical-tab (Docs' Shift+Enter soft-break marker) are
    normalized in the derived `text` field but left byte-exact in
    runs[].text."""
    scn = ScenarioSession.new_doc(settings, request=request)
    raw = "Kept textand more.\n"
    _insert_text(scn, raw)

    doc = _export(scn)
    block = next(b for b in _all_blocks(doc) if b["text"].startswith("Kept"))

    assert " " not in block["text"]
    assert "" not in block["text"]
    assert block["text"] == "Kept text\nand more.\n"

    run_text = "".join(r["text"] for r in block["runs"] if r["kind"] == "text")
    assert " " in run_text
    assert "" in run_text


# ---------------------------------------------------------------------------
# §13.1/13.2 includeWholeDocumentViews opt-in
# ---------------------------------------------------------------------------

def test_export_document_whole_document_views_default_omitted(settings, request):
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_text(scn, "Default-export views paragraph.\n")

    doc = _export(scn)
    assert "baseline_text" not in doc["views"]
    assert "proposed_text" not in doc["views"]
    assert "deleted_text" in doc["views"]
    assert "proposed_additions" in doc["views"]


def test_export_document_whole_document_views_opt_in(settings, request):
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_text(scn, "Opted-in views paragraph.\n")

    doc = _export(scn, include_whole_document_views=True)
    assert "Opted-in views paragraph." in doc["views"]["baseline_text"]


# ---------------------------------------------------------------------------
# gts-es3l — export folder isolation (gts-z6j0's getExportFolder_ contract).
# Hardening tests authored against gts-z6j0's frozen pre-code contract only
# (entry point export_document_json / exportFolderId response field / the
# docId-keyed sheetExportIndex row) — see docs/procedure-exporter.md §15.1.
# Skips (not fails) when EXPORT_ROOT_FOLDER_ID isn't configured on the target
# deployment, since isolation is deliberately best-effort/optional (§15.1) —
# a deployment with it unset has nothing to harden here.
# ---------------------------------------------------------------------------

def _require_export_isolation_configured(scn: ScenarioSession) -> None:
    resp = _export_raw(scn)
    if not resp.get("exportFolderId"):
        pytest.skip("EXPORT_ROOT_FOLDER_ID not configured on this deployment — export "
                    "isolation is best-effort (docs/procedure-exporter.md §15.1); nothing to harden.")


def test_export_document_folder_isolation_new_doc_gets_isolated_folder(settings, request):
    """AC(a): a fresh docId's export lands in a folder distinct from the doc's
    own source-folder parent, and that folder is recorded in the index under
    this docId (durable state, not just the response)."""
    scn = ScenarioSession.new_doc(settings, request=request)
    resp = _export_raw(scn)
    if not resp.get("exportFolderId"):
        pytest.skip("EXPORT_ROOT_FOLDER_ID not configured on this deployment.")

    export_folder_id = resp["exportFolderId"]
    assert export_folder_id != scn.sheet_id  # sanity: not accidentally the tracker sheet's own folder

    rows = _export_index_rows(scn, scn.doc_id)
    assert len(rows) == 1, f"expected exactly one index row for a fresh docId, got {rows}"
    assert rows[0]["folderId"] == export_folder_id
    assert rows[0]["docId"] == scn.doc_id


def test_export_document_folder_isolation_repeat_export_is_idempotent(settings, request):
    """AC(b): exporting the same docId twice reuses the same folder and does
    not append a second index row."""
    scn = ScenarioSession.new_doc(settings, request=request)
    _require_export_isolation_configured(scn)

    first = _export_raw(scn)["exportFolderId"]
    second = _export_raw(scn)["exportFolderId"]
    assert first == second, "repeat export of the same docId must reuse the same folder"

    rows = _export_index_rows(scn, scn.doc_id)
    assert len(rows) == 1, f"repeat export must upsert, not append, the index row: {rows}"


def test_export_document_folder_isolation_title_collision_stays_distinct(settings, request):
    """AC(c): two different docIds sharing the same document title still get
    two distinct export folders — the index is keyed by docId, never by
    name, precisely because titles are not unique (this project's docs can
    and do share titles)."""
    scn_a = ScenarioSession.new_doc(settings, request=request)
    scn_b = ScenarioSession.new_doc(settings, request=request)
    _require_export_isolation_configured(scn_a)

    collided_title = "Duplicate Governance Policy Title (gts-es3l)"
    _rename(scn_a, scn_a.doc_id, collided_title)
    _rename(scn_b, scn_b.doc_id, collided_title)

    folder_a = _export_raw(scn_a)["exportFolderId"]
    folder_b = _export_raw(scn_b)["exportFolderId"]
    assert folder_a != folder_b, (
        f"two docs sharing a title must not resolve to the same export folder "
        f"(name-keyed lookup regression): {folder_a!r} == {folder_b!r}"
    )

    rows_a = _export_index_rows(scn_a, scn_a.doc_id)
    rows_b = _export_index_rows(scn_b, scn_b.doc_id)
    assert len(rows_a) == 1 and rows_a[0]["folderId"] == folder_a
    assert len(rows_b) == 1 and rows_b[0]["folderId"] == folder_b


def test_export_document_folder_isolation_falls_back_without_raising_when_unconfigured(settings, request):
    """AC(d): proves the pre-fix fallback contract still holds — this doesn't
    flip EXPORT_ROOT_FOLDER_ID off (that's shared deployment state, not
    something a single test should mutate), it instead proves the *shape* of
    the fallback: when isolation isn't active for this docId (no
    exportFolderId in the response), the export still succeeds and returns a
    real, usable jsonFileId rather than raising or returning an error."""
    scn = ScenarioSession.new_doc(settings, request=request)
    resp = _export_raw(scn)
    assert resp.get("ok") is True
    assert resp.get("jsonFileId"), "export must still produce a Drive file even without export-folder isolation active"
