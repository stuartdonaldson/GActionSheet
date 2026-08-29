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
"""
import pytest

from scn.session import ScenarioSession


def _debug_runs(scn, n: int = 1) -> dict:
    resp = scn._post_fixture("debug_action_runs", {"n": n})
    return resp.get("data") or {}


def _expected_runs_for_link(text: str, link_word: str, url: str) -> list[dict]:
    """Computes the exact expected run list for `text` with `url` applied
    to the single occurrence of `link_word`, mirroring _extractInlineRuns'
    coalescing (adjacent same-styled characters merge into one run; a
    plain prefix/suffix is only present if non-empty) — this is the
    specifiable oracle, derived from the seed's own reported text/word,
    not a hand-counted offset guess."""
    start = text.index(link_word)
    end = start + len(link_word)
    runs = []
    if start > 0:
        runs.append({"start": 0, "end": start, "bold": False, "italic": False, "link": None})
    runs.append({"start": start, "end": end, "bold": False, "italic": False, "link": url})
    if end < len(text):
        runs.append({"start": end, "end": len(text), "bold": False, "italic": False, "link": url if False else None})
    return runs


def test_link_survives_scan_store_flush_rescan(settings, request):
    """[gts-tz5x case 1] A hyperlink over one phrase in the action text
    survives: doc scan -> Actions sheet (RichTextValue) -> flush back to
    the doc (materializing the missing status token) -> a fresh rescan.
    Both views (post-flush doc rescan and the sheet cell) must show the
    identical URL over the identical range — not dropped, not shifted."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        seed = scn._post_fixture("seed_link_action", {"n": 1})
        seed_data = seed.get("data") or {}
        assert seed_data.get("ok"), f"seed_link_action failed: {seed}"
        text = seed_data["text"]
        link_word = seed_data["linkWord"]
        url = seed_data["url"]
        expected = _expected_runs_for_link(text, link_word, url)

        scn.sync()

        result = _debug_runs(scn, 1)
        assert result.get("ok"), f"debug_action_runs failed: {result}"
        assert result.get("scanActionText") == text
        assert result.get("sheetActionText") == text
        assert result.get("scanRuns") == expected, (
            "post-flush doc rescan runs did not match the seeded link span "
            "— the hyperlink was dropped, shifted, or merged incorrectly "
            "by the flush's delete+reinsert"
        )
        assert result.get("sheetRuns") == expected, (
            "Actions sheet RichTextValue runs did not match the seeded "
            "link span — the STORE step did not preserve the scanned link"
        )
    finally:
        scn.close()


def test_link_only_action_survives_hasformatting_gate(settings, request):
    """[gts-tz5x case 2 / ADR-0027 rule 12] An action whose ONLY formatting
    is a hyperlink (no bold, no italic anywhere) must not be treated as
    unformatted: _extractInlineRuns' hasFormatting test has to fire on
    `link` alone, or the run list collapses to [] and the link is lost —
    the exact bug rules 10-15 exist to fix."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        seed = scn._post_fixture("seed_link_action", {"n": 1})
        seed_data = seed.get("data") or {}
        assert seed_data.get("ok"), f"seed_link_action failed: {seed}"

        scn.sync()

        result = _debug_runs(scn, 1)
        assert result.get("scanRuns"), (
            "a link-only action reported empty scanRuns — the "
            "hasFormatting gate did not fire on link alone (rule 12)"
        )
        assert any(r.get("link") for r in result["scanRuns"]), (
            "scanRuns is non-empty but no run actually carries the link URL"
        )
        assert not any(r.get("bold") or r.get("italic") for r in result["scanRuns"]), (
            "precondition violated: this fixture must not also apply "
            "bold/italic, or it no longer isolates the hasFormatting-on-"
            "link-alone case"
        )
    finally:
        scn.close()


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
