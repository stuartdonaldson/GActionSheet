"""
test_inline_formatting.py — gts-zocq twin [TST]

Regression coverage for gts-zocq (inline bold/italic round-trip in action
text), authored against the frozen composition-rule/transit/identity/
rendering decisions recorded in plan-fix.md Session 9 Result and
ADR-0022 — not against the implementation diff (no-shared-context
convention, plan-context.md).

Frozen decisions this test exercises:
  1. Composition rule (ADR-0022): Config's uniform action-text style no
     longer asserts bold/italic; inline runs own those two attributes.
  2. Transit: docState rows may carry an additive, optional
     `runs: [{start,end,bold,italic}]` field (ContractSchema.js).
  3. Row identity/consistency: a bolded word changing does not orphan the
     row or force extra work — covered here by asserting a second,
     no-op sync produces the SAME runs with no additional Actions-sheet
     row.
  4. SCAN -> STORE -> FLUSH -> RESCAN round trip is idempotent.

Uses the project's TestFixtures.js run_fixture cases (`seed_formatted_action`,
`debug_action_runs`) rather than driving the doc UI directly — same class of
test-support entry point as gts-1pk's `config_format`/`debug_action_text_style`
fixtures (plan-fix.md Session 8).

Backstop (per this bead's own AC: "each new formatting assertion is
demonstrated failing against a build that flattens the formatting"): verified
live during Session 9 by temporarily disabling _buildFlushRequests' per-run
updateTextStyle block (SyncManager.js) — with it disabled, a rescan of the
doc after sync showed EMPTY runs (formatting flattened by the flush's plain
delete+reinsert) while the identical assertion passed cleanly with the block
restored. See plan-fix.md Session 9 Result for the full transcript; not
re-run as part of this file (doing so here would require the harness to
redeploy a known-broken build against shared TEST, which Session 1
established the deploy tooling itself refuses to do).
"""
import pytest

from scn.session import ScenarioSession

_EXPECTED_RUNS = [
    {"start": 0, "end": 7, "bold": False, "italic": False},
    {"start": 7, "end": 16, "bold": True, "italic": False},
    {"start": 16, "end": 21, "bold": False, "italic": False},
    {"start": 21, "end": 32, "bold": False, "italic": True},
    {"start": 32, "end": 38, "bold": False, "italic": False},
]
_EXPECTED_TEXT = "Please bold this and italic that today"


def _debug_runs(scn, n: int = 1) -> dict:
    resp = scn._post_fixture("debug_action_runs", {"n": n})
    return resp.get("data") or {}


def test_inline_bold_italic_round_trips_scan_store_flush_rescan(settings, request):
    """[gts-zocq AC1/AC2/AC3] A bold span and a separate italic span inside
    one action's text survive: doc scan -> Actions sheet (RichTextValue) ->
    flush back to the doc (materializing the missing status token) -> a
    fresh rescan of the doc. All three views (scan-at-sync-time via the
    sheet, and post-flush rescan) must show the identical run spans — not
    merged, not dropped, not uniformly reapplied over the whole range."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        seed = scn._post_fixture("seed_formatted_action", {"n": 1})
        seed_data = seed.get("data") or {}
        assert seed_data.get("ok"), f"seed_formatted_action failed: {seed}"
        assert seed_data.get("boldWord") == "bold this"
        assert seed_data.get("italicWord") == "italic that"

        scn.sync()

        result = _debug_runs(scn, 1)
        assert result.get("ok"), f"debug_action_runs failed: {result}"
        assert result.get("scanActionText") == _EXPECTED_TEXT
        assert result.get("sheetActionText") == _EXPECTED_TEXT
        assert result.get("scanRuns") == _EXPECTED_RUNS, (
            "post-flush doc rescan runs did not match the seeded spans — "
            "inline formatting was flattened, merged, or shifted by the "
            "flush's delete+reinsert (the exact defect gts-zocq fixes)"
        )
        assert result.get("sheetRuns") == _EXPECTED_RUNS, (
            "Actions sheet RichTextValue runs did not match the seeded "
            "spans — the STORE step did not preserve scanned formatting"
        )

        # Idempotency (AC3): a second sync with nothing changed must not
        # alter the spans (re-flush of the same, already-correct content).
        scn.sync()
        result2 = _debug_runs(scn, 1)
        assert result2.get("scanRuns") == _EXPECTED_RUNS
        assert result2.get("sheetRuns") == _EXPECTED_RUNS

        rows = scn.find_sheet_actions()
        matching = [r for r in rows if r.action_id == "AI-1"]
        assert len(matching) == 1, (
            "a formatting-only re-sync must not orphan the row or create a "
            "duplicate — row identity is plain-text only (gts-zocq AC4)"
        )
    finally:
        scn.close()


def test_plain_action_text_has_no_runs(settings, request):
    """[gts-zocq — common-case cost/negative check] An action with no bold/
    italic anywhere reports an empty runs[] at both scan and sheet layers —
    the additive `runs` field must not appear/cost anything for the
    overwhelmingly common unformatted case."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn.append_paragraph("AI-1: nothing but plain text here")
        scn.sync()

        result = _debug_runs(scn, 1)
        assert result.get("ok"), f"debug_action_runs failed: {result}"
        assert result.get("scanRuns") == []
        assert result.get("sheetRuns") == []
    finally:
        scn.close()


def test_plain_edit_clears_prior_italic_formatting(settings, request):
    """[gts-a8yh.2 — durable invariant] Once an action's text has ever
    carried bold/italic, a later doc-side edit that removes ALL formatting
    must make the sheet report an empty runs[] too — not leak the previous
    occupant's RichTextValue styling forward. This is the WebApp.js
    doc-authoritative "update existing row" branch: _buildRichTextValueForActionText
    returns null for the new (plain) runs, so the write must actively clear
    any rich-text formatting already on the cell rather than relying on
    setValue() to do so (it does not — see gts-a8yh.2 / TD-PLAN-21-08 §3.3)."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        seed = scn._post_fixture("seed_formatted_action", {"n": 1})
        seed_data = seed.get("data") or {}
        assert seed_data.get("ok"), f"seed_formatted_action failed: {seed}"

        scn.sync()

        before = _debug_runs(scn, 1)
        assert before.get("sheetRuns"), (
            "precondition: the cell must actually carry rich-text runs "
            "before we test that a plain edit clears them"
        )

        replace = scn._post_fixture("replace_action_plain_text", {"n": 1})
        replace_data = replace.get("data") or {}
        assert replace_data.get("ok"), f"replace_action_plain_text failed: {replace}"

        scn.sync()

        after = _debug_runs(scn, 1)
        assert after.get("ok"), f"debug_action_runs failed: {after}"
        assert after.get("scanRuns") == [], (
            "doc-side scan should already show no formatting after the "
            "plain-text replace"
        )
        assert after.get("sheetRuns") == [], (
            "Actions sheet cell still reports a rich-text run after the "
            "action was rewritten as plain text — stale RichTextValue "
            "formatting was left on the cell by the update write"
        )
    finally:
        scn.close()


def test_archived_row_reuse_does_not_leak_italic_into_new_plain_action(settings, request):
    """[gts-a8yh.2 — durable invariant, root-cause repro] Reproduces the
    actual gas-test6.log mechanism: an Actions-sheet row that once carried
    an italic run gets archived (ArchiveManager._archiveActionsRows
    compacts the sheet via clearContent()+setValues(), and clearContent()
    explicitly preserves per-cell/per-character formatting), freeing its
    physical row for reuse by a later, unrelated, plain-text action. That
    row must not inherit the archived occupant's stale italic run.

    Only meaningful run in isolation (no concurrent writers to the shared
    TEST Actions sheet) — the row-freed-by-archive must be this test's own
    seeded row and nothing else's, or the "next append lands in the freed
    slot" assumption below does not hold. Do not run this test with -n>1
    or interleaved against other Actions-sheet writers."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        seed = scn._post_fixture("seed_formatted_action", {"n": 1})
        seed_data = seed.get("data") or {}
        assert seed_data.get("ok"), f"seed_formatted_action failed: {seed}"

        scn.sync()

        before = _debug_runs(scn, 1)
        assert before.get("sheetRuns"), (
            "precondition: the row must actually carry a rich-text run "
            "before we test that archiving+reuse doesn't leak it forward"
        )

        global_id = f"{scn.doc_id}/AI-1"
        backdate = scn._post_fixture(
            "backdate_action_row", {"globalId": global_id, "daysAgo": 35, "status": "Closed"}
        )
        assert (backdate.get("data") or {}).get("globalId") == global_id, backdate

        sweep = scn._post_fixture("archive_sweep")
        sweep_data = sweep.get("data") or {}
        assert sweep_data.get("ok") and sweep_data.get("archived", 0) >= 1, (
            f"archive_sweep did not archive the backdated row: {sweep}"
        )

        scn.append_paragraph("AI-2: brand new plain action, no formatting")
        scn.sync()

        after = _debug_runs(scn, 2)
        assert after.get("ok"), f"debug_action_runs failed: {after}"
        assert after.get("scanRuns") == []
        assert after.get("sheetRuns") == [], (
            "a brand-new plain action's sheet cell reports a rich-text run "
            "— it landed on a physical row recycled from the archived "
            "italic action and inherited that row's stale RichTextValue "
            "formatting (gts-a8yh.2 root cause: ArchiveManager's "
            "clearContent()+setValues() compaction preserves format)"
        )
    finally:
        scn.close()
