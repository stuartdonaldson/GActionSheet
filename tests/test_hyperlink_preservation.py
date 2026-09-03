"""
test_hyperlink_preservation.py — gts-tz5x twin [TST]

Regression coverage for gts-jn8o (ADR-0027 rules 10-15, formerly ADR-0028):
a hyperlink typed into an action's text must survive doc -> Actions sheet
(RichTextValue) -> flush back to the doc -> a fresh rescan, the same
scan/store/flush/rescan round trip test_inline_formatting.py already proves
for bold/italic. Authored against gts-tz5x's frozen pre-code contract only
(no-shared-context convention) — not against the SyncManager.js diff.

Frozen contract (gts-tz5x DESIGN):
  1. Link mid-action survives doc->sheet->doc with URL and range intact.
  2. Link-only action (no bold, no italic) survives — guards rule 12's
     hasFormatting gate (a link-only run must not be misread as
     unformatted and dropped).
  3. A URL with encodable characters (query string, percent-encoding,
     trailing slash) round-trips without becoming a perceived change on a
     second, no-op sync — Sheets' RichTextValue may normalize the URL on
     write, but the normalized form must not itself register as a diff.
  5. Idempotency: a second sync with nothing changed must not alter the
     link's run or the row count.

  Not yet covered here (tracked as follow-up, not blocking): case 4 (chip
  link on the ACT-N:/AI-N: token is unchanged by a flush carrying run
  links) has no existing debug fixture exposing the token's own link, and
  case 6 (a run record with no `link` key produces no spurious diff) is
  a read-side default already exercised indirectly by
  test_inline_formatting.py's pre-link-key assertions.

Uses the seed_link_action / debug_action_runs TestFixtures.js entry
points — same class of test-support fixture as test_inline_formatting.py's
seed_formatted_action / debug_action_runs.

Cases 1 and 2 retired gts-dxz9/act-retire (staged plan
docdata-litter-apt-speed.md, stage `apt-format-migration`) — see the
retirement note inline below. Case 3/5's idempotency assertion is now also
covered generically by the batched runner — gts-5ktl (stage
`lane-idempotency`) made `run_lane` take a second, no-op-sync capture and
diff it against the first, per scenario — so `hyperlink-roundtrip.apt.txt`
asserts idempotency as well as the round trip. This file's own live
assertion stays as the link-specific instance.
"""
import pytest

from scn.session import ScenarioSession


def _debug_runs(scn, n: int = 1) -> dict:
    resp = scn._post_fixture("debug_action_runs", {"n": n})
    return resp.get("data") or {}


# ---------------------------------------------------------------------------
# test_link_survives_scan_store_flush_rescan (case 1: link mid action text
# survives scan->sheet->flush->rescan) and
# test_link_only_action_survives_hasformatting_gate (case 2: a link-only
# action must not be treated as unformatted, ADR-0027 rule 12) retired
# gts-dxz9/act-retire (staged plan docdata-litter-apt-speed.md, stage
# `apt-format-migration`) WITHOUT a new corpus — both were already covered
# by tests/fixtures/hyperlink-roundtrip.apt.txt Case 1 (link mid action text)
# and Case 2 (link-only action) respectively, checked in a stage earlier
# (`apt-corpus-batching`, gts-ph35) for gts-tz5x's own twin-ticket coverage,
# before this stage existed. Run via tests/test_apt_corpus_batch.py's batched
# lane (batch "apt-corpus-batch"), not this stage's own
# tests/test_apt_format_lane.py.
# ---------------------------------------------------------------------------


def test_encodable_url_round_trips_and_is_idempotent(settings, request):
    """[gts-tz5x cases 3 + 5] A URL containing query-string and
    percent-encodable characters must not register as a perceived change
    on a second, no-op sync. Sheets' RichTextValue may normalize the URL
    on write (trailing slash, percent-encoding); what matters is that
    whatever the doc reports immediately after the FIRST flush is stable
    thereafter — a second sync with no user edit must report the identical
    URL, the identical range, and no additional Actions-sheet row. This is
    the round trip a user would experience as "the link disappeared later"
    if normalization drift caused every sync to perceive a change."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        url = "https://example.com/a%20b/?x=1&y=two"
        seed = scn._post_fixture("seed_link_action", {"n": 1, "url": url})
        seed_data = seed.get("data") or {}
        assert seed_data.get("ok"), f"seed_link_action failed: {seed}"
        text = seed_data["text"]
        link_word = seed_data["linkWord"]

        scn.sync()
        first = _debug_runs(scn, 1)
        assert first.get("ok"), f"debug_action_runs failed: {first}"
        first_runs = first.get("scanRuns") or []
        first_link_runs = [r for r in first_runs if r.get("link")]
        assert first_link_runs, (
            f"no run carries a link after the first sync: {first_runs}"
        )
        # gts-mtw0: previously unasserted at this point in the test -- the
        # mismatch (seed's 'text' carried the 'AI-N: ' token prefix,
        # scanActionText never does, since the scanner strips it) was latent
        # until the SECOND sync's equivalent assertion below. Assert it here
        # too, against the FIRST sync, so the fixture-shape contract is
        # checked as soon as it's available rather than only on the no-op
        # idempotency pass.
        assert first.get("scanActionText") == text, (
            f"seed_link_action's 'text' ({text!r}) should already match the "
            f"scanner's prefix-free actionText ({first.get('scanActionText')!r}) "
            f"after the very first sync"
        )
        stable_url = first_link_runs[0]["link"]

        # Second sync, no edits — the durable invariant under test.
        scn.sync()
        second = _debug_runs(scn, 1)
        assert second.get("scanActionText") == text
        assert second.get("scanRuns") == first_runs, (
            "a second, no-op sync changed the doc-rescanned runs — URL "
            "normalization (or offset drift) between the sheet and the "
            "doc is being perceived as a real edit on every sync, which "
            "is exactly the failure mode that would make a link vanish "
            "or shift after enough activity"
        )
        assert second.get("sheetRuns") == first_runs, (
            "a second, no-op sync changed the Actions sheet's own runs — "
            "the stored value is not stable across repeated syncs"
        )
        second_link_runs = [r for r in second.get("scanRuns") or [] if r.get("link")]
        assert second_link_runs and second_link_runs[0]["link"] == stable_url, (
            "the link URL itself changed between the first and second "
            "sync with no user edit in between"
        )

        rows = scn.find_sheet_actions()
        matching = [r for r in rows if r.action_id == "AI-1"]
        assert len(matching) == 1, (
            "a link-only re-sync must not orphan the row or create a "
            "duplicate — row identity is plain-text only, unaffected by runs"
        )
    finally:
        scn.close()
