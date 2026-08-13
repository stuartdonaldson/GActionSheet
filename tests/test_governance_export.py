"""
test_governance_export.py — gts-2glm, [TST] twin of gts-ipoy (governance
JSON exporter, src/Procedure-Exporter.js).

Entry point: WebApp.js's 'export_governance_json' route -> exportGovernance_()
via the options.docId testability seam this bead added (exportGovernance_
otherwise only resolves DocumentApp.getActiveDocument(), which is add-on-UI-
session-only and has no headless call-site). Production entry points
(onGovernanceExportMenu/onGovernanceExportAndPdfMenu/onExportGovernanceJson/
onExportGovernanceJsonAndPdf, all in Procedure-Exporter.js) never pass docId
and are unaffected by the seam.

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
tests/test_governance_export_pure.js for the pure-function track that
covers those two ACs against hand-built Docs-API-shaped fixture objects.
Also out of scope this session: table mid-cell unit-switch tagging, and the
prefix/cross-paragraph/fuzzy comment-match tiers beyond exact — flagged as
open follow-up in gts-2glm rather than silently skipped.
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


def _export(scn: ScenarioSession, export_pdf: bool = False) -> dict:
    resp = scn._post_route("export_governance_json", {"docId": scn.doc_id, "exportPdf": export_pdf})
    assert resp.get("ok"), resp
    return resp["json"]


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

def test_export_governance_entry_point_basic_shape(settings, request):
    """Call-site coverage for exportGovernance_() via export_governance_json
    (WebApp.js) — the entry point itself is the call-site, per this project's
    entry-point coverage invariant."""
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_heading(scn, "Board Policy 1: Test Governance Policy", level=1)
    _insert_text(scn, "This is baseline body text.\n")

    doc = _export(scn)

    assert doc["schema_version"] == "2.1"
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

def test_export_governance_parent_unit_id_hierarchy(settings, request):
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

    body_block = next(b for b in procedure["blocks"] if b["all_text"].startswith("Procedure body"))
    assert body_block["unit_id"] == procedure["id"]


# ---------------------------------------------------------------------------
# location.page_approximate under explicit page breaks
# ---------------------------------------------------------------------------

def test_export_governance_page_approximate_transitions_on_explicit_break(settings, request):
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_text(scn, "Before any explicit page break.\n")
    _insert_page_break(scn)
    _insert_text(scn, "After the explicit page break.\n")

    doc = _export(scn)
    blocks = _all_blocks(doc)
    before = next(b for b in blocks if b["all_text"].startswith("Before any"))
    after = next(b for b in blocks if b["all_text"].startswith("After the"))

    assert before["location"]["page_approximate"] is True
    assert after["location"]["page_approximate"] is False
    assert after["location"]["page"] > before["location"]["page"]
    assert doc["diagnostics"]["explicit_page_breaks"] == 1


# ---------------------------------------------------------------------------
# text_pattern / style_pattern evidence emission
# ---------------------------------------------------------------------------

def test_export_governance_semantic_state_text_pattern_evidence(settings, request):
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


def test_export_governance_bold_colon_label_style_pattern(settings, request):
    """A bold `Intent:` prefix is detected via detectBoldColonLabel_ and
    surfaces as block.label / kind 'labeled_paragraph'."""
    scn = ScenarioSession.new_doc(settings, request=request)
    _insert_bold_label(scn, "Intent", "State the purpose of this policy.")

    doc = _export(scn)
    block = next(b for b in _all_blocks(doc) if b["label"] == "Intent")
    assert block["kind"] == "labeled_paragraph"
    assert block["all_text"].startswith("Intent: State the purpose")


# ---------------------------------------------------------------------------
# unit.color_signals scoping (no cross-unit leakage)
# ---------------------------------------------------------------------------

def test_export_governance_color_signals_scoped_per_unit(settings, request):
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
    assert unit_b["color_signals"] == []

    assert any("Manual highlight colors" in w for w in doc["diagnostics"]["warnings"])


# ---------------------------------------------------------------------------
# Comment-to-document traceability (associateCommentsToBlocks_)
# ---------------------------------------------------------------------------

def test_export_governance_comment_association_exact_match(settings, request):
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


def test_export_governance_comment_association_unmatched(settings, request):
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
