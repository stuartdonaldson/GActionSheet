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
  1. Batch syncAll sheetWin flush           -> retired, see below
  2. Batch syncAll new-assign flush         -> retired, see below
  3. Batch syncAll duplicate-reconciliation -> retired, see below
  4. Batch syncAll missing-status flush     -> retired, see below
  5. Interactive status-tap (preview card)  -> test_ep5_preview_card_status_flush
  6. Interactive status-tap (sidebar)       -> test_ep6_sidebar_status_flush
  7. _syncSheetRowToDoc (onEdit trigger)    -> retired, see below (KNOWN GAP, not fixed)

Entry points 1-4 and 7 retired gts-crae (staged plan
docdata-litter-apt-speed.md, stage `flush-lane-retire`) — each is now run
through tests/test_apt_flush_lane.py's batched lane (one composed doc
instead of five) via tests/fixtures/flush-lane-*.apt.txt. Formatting
contract (bold field name, tab after colon) and the write->read round trip
are re-proven implicitly by the golden `diff_apt` comparison: a field line
that stopped being recognized on rescan would re-encode as prose and the
diff would go red. Entry points 5 and 6 stay here — they exercise call
sites (preview-card tap, sidebar tap) run_lane has no mutation kind for.

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


def _paras_containing(scn, needle):
    return [
        p for p in paragraph_texts_with_breaks(load_doc(download_docx(scn.doc_id)))
        if needle in p
    ]


# ---------------------------------------------------------------------------
# Entry points 1, 2, 3, 4 — batch syncAll sheetWin / new-assign /
# duplicate-reconciliation / missing-status flush
#
# Retired gts-crae/flush-lane-retire (staged plan docdata-litter-apt-
# speed.md, stage `flush-lane-retire`) WITHOUT a new corpus — each was
# already covered by tests/fixtures/flush-lane-sheetwin.apt.txt (EP1),
# flush-lane-new-assign.apt.txt (EP2), flush-lane-duplicate.apt.txt (EP3)
# and flush-lane-missing-status.apt.txt (EP4), run via
# tests/test_apt_flush_lane.py's batched lane (batch "apt-lanes-flush"),
# one composed doc instead of four separate ones. Formatting contract
# (bold field name, tab-after-colon) and the write->read round trip are
# reproven implicitly by that lane's golden diff_apt comparison.
# ---------------------------------------------------------------------------


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
#
# Retired gts-crae/flush-lane-retire (staged plan docdata-litter-apt-
# speed.md, stage `flush-lane-retire`) WITHOUT a new corpus — already
# covered by tests/fixtures/flush-lane-onedit-trigger.apt.txt, run via
# tests/test_apt_flush_lane.py's batched lane (batch "apt-lanes-flush").
# That golden encodes the SAME known gap this test used to mark directly
# (SyncManager.js's own comment: the onEdit-trigger flush has no
# customFields source, so the field line is dropped, not preserved) — the
# expected doc has no `Target:` line. The lane's golden will start
# failing, in a good way, the day entry point 7 gains its own customFields
# source, at which point the corpus (not this file) should be rewritten.
# ---------------------------------------------------------------------------
