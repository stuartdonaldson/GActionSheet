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
