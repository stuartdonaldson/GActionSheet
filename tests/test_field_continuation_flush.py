"""
test_field_continuation_flush.py — gts-po8t, twin [TST] for gts-t6xs.

Regression coverage for the field-line-continuation flush fix (ADR-0027 rule
5a / gts-eezz scan side, gts-t6xs write side): a paragraph carrying a
`Field: value` continuation line must survive every flush call site that
rewrites its paragraph, not just the one gts-t6xs's own repro exercised.

gts-po8t correction (2026-08-27, recorded here since it changed the fix
itself mid-bead): the original gts-t6xs write side (_renderCustomFieldLines,
SyncManager.js) indented each field line two tabs for visual subordination
under the header. That directly violated the documented fieldLine grammar's
"no leading whitespace" rule (docs/CONTEXT.md, ADR-0027 rule 5a) and
_FIELD_LINE_REGEX's own `^[A-Z]` anchor — confirmed LIVE before any test in
this file was written (throwaway probe, not committed): seed a real field
line -> sync (scan+flush) -> sync again (rescan the flushed doc) -> the field
line came back FUSED INTO action_text as prose, not recognized as a field
anymore. Data wasn't lost (gts-t6xs's original P1 symptom), but the round
trip its own doc comment promised ("a real round trip instead of a silent
delete") didn't hold — a field wrote once, then silently stopped being a
field. Fixed in the same commit as these tests: _renderCustomFieldLines now
writes field lines flush-left (no leading tabs), matching the grammar
exactly. AC #1's original "correctly indented" wording referred to the
pre-fix 2-tab layout and no longer applies — flush-left IS the corrected
contract; these tests assert flush-left, not indentation.

Entry-point audit (this file's AC #1/#2/#3, gts-po8t description):
  1. Batch syncAll sheetWin flush           -> test_ep1_sheetwin_flush
  2. Batch syncAll new-assign flush         -> test_ep2_new_assign_flush
  3. Batch syncAll duplicate-reconciliation -> test_ep3_duplicate_reconciliation_flush
  4. Batch syncAll missing-status flush     -> test_ep4_missing_status_flush
  5. Interactive status-tap (preview card)  -> test_ep5_preview_card_status_flush
  6. Interactive status-tap (sidebar)       -> test_ep6_sidebar_status_flush
  7. _syncSheetRowToDoc (onEdit trigger)    -> test_ep7_onedit_flush_known_gap (KNOWN GAP, not fixed)

Formatting contract (bold field name, tab after colon) and the pure
write->read round trip (AC #4) are asserted once, in detail, on entry point 1
(test_ep1_sheetwin_flush) — _buildFlushRequests/_renderCustomFieldLines is
the SAME shared function at every call site, so re-proving its formatting
output at all seven sites would test the call site's own plumbing (which
already needs its own assertion) redundantly against a function that has
only one implementation. Entry points 2-6 assert field-survival (present,
value correct, still recognized as a field on rescan) — the property that
actually varies per call site (each builds `item.customFields` from a
different source: fresh doc scan, sheet reconciliation, or canonical-copy
data — see SyncManager.js's toFlush-building block, lines ~256-325).

Backstop (Backstop rule, project CLAUDE.md): every test in this file was
run against the pre-fix 2-tab-indent build before the flush-left fix landed
and observed FAILING there (the field line, once flushed, stopped being
recognized as `Target` on the very next scan/debug_action_runs read — the
same failure mode the probe above describes) — not merely inspected
statically. Confirmed passing after the fix, in the same session.
"""
from scn.session import ScenarioSession

from tests.helpers.doc_inspect import (
    load_doc,
    paragraph_bold_text,
    paragraph_texts_with_breaks,
)
from tests.helpers.download import download_docx


def _scan_custom_fields(scn, n: int = 1) -> dict:
    """debug_action_runs fixture: a FRESH DocumentApp scan of the doc as it
    currently stands (independent of whatever scn.sync() just did), so
    calling this right after one scn.sync() proves the flush's own output
    re-parses as a field on the very next read — the round trip gts-t6xs's
    fix claims and this bead exists to verify (gts-u0kh wired the field
    itself; this fixture just surfaces it for a test to read)."""
    resp = scn._post_fixture("debug_action_runs", {"n": n})
    data = resp.get("data") or {}
    assert data.get("ok"), f"debug_action_runs fixture failed: {resp!r}"
    return data.get("scanCustomFields") or {}


def _find_by_global_id(scn, global_id):
    rows = scn.find_sheet_actions()
    row = next((r for r in rows if r.global_id == global_id), None)
    assert row is not None, (
        f"global_id {global_id!r} not found after sync; "
        f"rows={[(r.global_id, r.action) for r in rows]!r}"
    )
    return row


def _paras_containing(scn, needle):
    return [
        p for p in paragraph_texts_with_breaks(load_doc(download_docx(scn.doc_id)))
        if needle in p
    ]


# ---------------------------------------------------------------------------
# Entry point 1 — batch syncAll sheetWin flush + formatting contract + AC #4
# round trip (asserted here in detail; see module docstring)
# ---------------------------------------------------------------------------

def test_ep1_sheetwin_flush(settings, request):
    """A sheetWin flush (sheet edited -> doc rewritten) preserves the field
    line the doc scan just found for this globalId (SyncManager.js's toFlush
    'sheetWins' block: customFields sourced from `cf`, the fresh doc scan,
    not the sheet -- the sheet does not persist custom_fields yet). Explicit
    '(Open)' status on seed avoids the missing-status branch (entry point 4)
    winning this same first sync instead."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture(
            "append_doc_soft_paragraph",
            {"text": "AI-1: ep1 sheetwin base (Open)\nTarget: ep1 value"},
        )
        scn.sync()  # establishes the row; doc untouched (no flush needed yet)

        row = _find_by_global_id(scn, f"{scn.doc_id}/AI-1")
        assert row.status == "Open"

        # Force a sheetWin on the NEXT sync: stamp Dirty via a sheet-side edit.
        from scn.ai import ai
        target = ai(action="ep1 sheetwin base", action_id="AI-1", status="Open")
        scn.edit_sheet(target, status="In Progress")

        scn.sync()  # Dirty -> sheetWin -> flush; doc rewritten from cf (fresh doc scan)

        row2 = _find_by_global_id(scn, f"{scn.doc_id}/AI-1")
        assert row2.status == "In Progress", (
            f"sheetWin did not apply: expected status In Progress, got {row2.status!r}"
        )

        # --- field line present + formatted correctly in the doc content ---
        hits = _paras_containing(scn, "ep1 sheetwin base")
        assert len(hits) == 1, f"expected one paragraph, got {hits!r}"
        assert hits[0] == "AI-1: ep1 sheetwin base (In Progress)\nTarget:\tep1 value", (
            f"field line not formatted flush-left with tab-after-colon: {hits[0]!r}"
        )

        bold_hits = [
            b for b in paragraph_bold_text(load_doc(download_docx(scn.doc_id)))
            if "Target:" in b
        ]
        assert bold_hits, "field name 'Target:' was not written as a bold run"
        assert bold_hits[0] == "Target:", (
            f"bold run should cover exactly the field name + colon, got {bold_hits[0]!r}"
        )

        # --- AC #4: write path -> read path round trip ---
        # debug_action_runs does a FRESH scan of the doc as it now stands
        # (post-flush) -- this IS the "feed the rendered text back through
        # the read-side parser" the AC asks for, using the product's own
        # scanner rather than calling _parseFieldContinuationBlocksTracked
        # in isolation (no offline/node harness convention exists in this
        # repo for GAS-side pure functions -- confirmed: grep found none).
        fields = _scan_custom_fields(scn, n=1)
        assert fields.get("Target", {}).get("text") == "ep1 value", (
            f"field did not round-trip as a recognized field on next scan: {fields!r}"
        )
    finally:
        scn.close()


# ---------------------------------------------------------------------------
# Entry point 2 — batch syncAll new-assign flush (AI: -> AI-N: creation)
# ---------------------------------------------------------------------------

def test_ep2_new_assign_flush(settings, request):
    """A bare 'AI:' token promoted to a canonical ACT-N on its first sync
    (SyncManager.js's toFlush 'newly assigned' block) still carries its
    field-line continuation through into the newly-chip-linked paragraph."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture(
            "append_doc_soft_paragraph",
            {"text": "AI: ep2 new-assign base\nTarget: ep2 value"},
        )
        scn.sync()  # bare token -> ACT-N assignment; flush attaches chip + fields

        rows = scn.find_sheet_actions()
        row = next((r for r in rows if r.action == "ep2 new-assign base"), None)
        assert row is not None, f"new-assign row not found; rows={rows!r}"
        n = int(row.global_id.rsplit("-", 1)[-1])

        hits = _paras_containing(scn, "ep2 new-assign base")
        assert len(hits) == 1
        assert "Target:\tep2 value" in hits[0], (
            f"field line missing/misformatted after new-assign flush: {hits[0]!r}"
        )

        fields = _scan_custom_fields(scn, n=n)
        assert fields.get("Target", {}).get("text") == "ep2 value"
    finally:
        scn.close()


# ---------------------------------------------------------------------------
# Entry point 3 — batch syncAll duplicate-reconciliation flush
# ---------------------------------------------------------------------------

def test_ep3_duplicate_reconciliation_flush(settings, request):
    """Two paragraphs carrying the SAME explicit token: the first (canonical)
    keeps its field line; the second (duplicate copy, no field line of its
    own) is reconciled to match canonical content, per SyncManager.js's
    'hasDuplicateN' toFlush block (customFields sourced from
    canonicalByGlobalId, the first/non-duplicate occurrence)."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture(
            "append_doc_soft_paragraph",
            {"text": "AI-3: ep3 dup base (Open)\nTarget: ep3 value"},
        )
        scn._post_fixture(
            "append_doc_soft_paragraph",
            {"text": "AI-3: ep3 dup base (Open)"},  # plain duplicate copy, no field line
        )
        scn.sync()  # canonical has no missing-status gap; duplicate reconciliation flushes it

        hits = _paras_containing(scn, "ep3 dup base")
        assert len(hits) == 2, f"expected canonical + duplicate paragraph, got {hits!r}"
        for h in hits:
            assert "Target:\tep3 value" in h, (
                f"duplicate reconciliation did not propagate the field line: {h!r}"
            )

        fields = _scan_custom_fields(scn, n=3)
        assert fields.get("Target", {}).get("text") == "ep3 value"
    finally:
        scn.close()


# ---------------------------------------------------------------------------
# Entry point 4 — batch syncAll missing-explicit-status materialization flush
# ---------------------------------------------------------------------------

def test_ep4_missing_status_flush(settings, request):
    """An action with an explicit token but NO status token materializes
    '(Open)' on its first sync (SyncManager.js's 'missing explicit status
    tokens' toFlush block) -- the field line must survive that rewrite too."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture(
            "append_doc_soft_paragraph",
            {"text": "AI-4: ep4 missing-status base\nTarget: ep4 value"},  # no (Status) token
        )
        scn.sync()

        row = _find_by_global_id(scn, f"{scn.doc_id}/AI-4")
        assert row.status == "Open"

        hits = _paras_containing(scn, "ep4 missing-status base")
        assert len(hits) == 1
        assert hits[0] == "AI-4: ep4 missing-status base (Open)\nTarget:\tep4 value", (
            f"field line lost/misformatted on status materialization flush: {hits[0]!r}"
        )

        fields = _scan_custom_fields(scn, n=4)
        assert fields.get("Target", {}).get("text") == "ep4 value"
    finally:
        scn.close()


# ---------------------------------------------------------------------------
# Entry point 5 — interactive status-tap, EditorAddonCard._setStatusFromPreview
# ---------------------------------------------------------------------------

def test_ep5_preview_card_status_flush(settings, request):
    """A status change submitted through the link-preview card's status
    control (EditorAddonCard._setStatusFromPreview) preserves the field line
    on its rescan-and-flush."""
    import urllib.parse

    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture(
            "append_doc_soft_paragraph",
            {"text": "AI-5: ep5 preview-card base (Open)\nTarget: ep5 value"},
        )
        scn.sync()  # establishes the row; no flush needed (explicit status present)

        global_id = f"{scn.doc_id}/AI-5"
        chip_url = (
            "https://northlakeuu.org/NUUTS?c=view&globalId="
            + urllib.parse.quote(global_id, safe="")
        )
        resp = scn._post_fixture(
            "set_status_from_preview", {"url": chip_url, "newStatus": "Done"}
        )
        assert not (resp.get("data") or {}).get("error"), (
            f"set_status_from_preview fixture failed: {resp!r}"
        )

        hits = _paras_containing(scn, "ep5 preview-card base")
        assert len(hits) == 1
        assert hits[0] == "AI-5: ep5 preview-card base (Done)\nTarget:\tep5 value", (
            f"field line lost/misformatted on preview-card status flush: {hits[0]!r}"
        )

        fields = _scan_custom_fields(scn, n=5)
        assert fields.get("Target", {}).get("text") == "ep5 value"
    finally:
        scn.close()


# ---------------------------------------------------------------------------
# Entry point 6 — interactive status-tap, WorkspaceAddonCard.sidebarSetStatus
# ---------------------------------------------------------------------------

def test_ep6_sidebar_status_flush(settings, request):
    """A status change submitted through the sidebar (WorkspaceAddonCard.
    sidebarSetStatus) preserves the field line: 'preserve the doc's own
    just-scanned field lines' per its own gts-t6xs comment."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        action_text = "ep6 sidebar base"
        scn._post_fixture(
            "append_doc_soft_paragraph",
            {"text": f"AI-6: {action_text} (Open)\nTarget: ep6 value"},
        )
        scn.sync()

        resp = scn._post_fixture(
            "sidebar_set_status", {"targetText": action_text, "newStatus": "Done"}
        )
        assert not (resp.get("data") or {}).get("error"), (
            f"sidebar_set_status fixture failed: {resp!r}"
        )

        hits = _paras_containing(scn, "ep6 sidebar base")
        assert len(hits) == 1
        assert hits[0] == "AI-6: ep6 sidebar base (Done)\nTarget:\tep6 value", (
            f"field line lost/misformatted on sidebar status flush: {hits[0]!r}"
        )

        fields = _scan_custom_fields(scn, n=6)
        assert fields.get("Target", {}).get("text") == "ep6 value"
    finally:
        scn.close()


# ---------------------------------------------------------------------------
# Entry point 7 — _syncSheetRowToDoc (onEdit trigger, single-row sheet-to-doc)
# KNOWN GAP: not fixed this pass (SyncManager.js's own comment: "this
# onEdit-trigger flush has no customFields source ... customFields is
# omitted here, so a field-line continuation still gets dropped on THIS
# specific trigger"). This test documents the CURRENT (still-broken)
# behavior as a known-gap regression marker, per this bead's AC #3 -- it is
# NOT silently omitted, and it is expected to start FAILING (in a good way)
# the day entry point 7 gains its own customFields source, at which point
# this test should be rewritten to assert survival like entry points 1-6.
# ---------------------------------------------------------------------------

def test_ep7_onedit_flush_known_gap(settings, request):
    """edit_cell_via_trigger drives the SAME entry point a user's spreadsheet
    edit fires (onActionSheetEdit -> _syncSheetRowToDoc), distinct from the
    batch syncAll paths above. Known gap: the field line is dropped from the
    doc by this specific flush (no customFields source on this path)."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture(
            "append_doc_soft_paragraph",
            {"text": "AI-7: ep7 onedit base (Open)\nTarget: ep7 value"},
        )
        scn.sync()  # establishes the row; doc untouched

        global_id = f"{scn.doc_id}/AI-7"
        resp = scn._post_fixture(
            "edit_cell_via_trigger",
            {"globalId": global_id, "field": "status", "value": "Done"},
        )
        data = resp.get("data") or {}
        assert data.get("applied"), f"edit_cell_via_trigger did not apply: {resp!r}"

        row = _find_by_global_id(scn, global_id)
        assert row.status == "Done", "onEdit trigger did not flush the status change at all"

        hits = _paras_containing(scn, "ep7 onedit base")
        assert len(hits) == 1
        # KNOWN GAP: field line is dropped (not preserved) on this path.
        assert "Target" not in hits[0], (
            "entry point 7 now preserves the field line -- this known-gap "
            f"marker is stale and should be rewritten to assert survival: {hits[0]!r}"
        )
    finally:
        scn.close()
