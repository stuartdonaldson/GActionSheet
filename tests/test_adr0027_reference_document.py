"""
test_adr0027_reference_document.py — gts-colw AC#5.

The consolidated regression suite for ADR-0027, seeded from the canonical
reference doc (docs/interfaces/action-portable-text.md, gts-colw) instead of
each bead separately hand-constructing its own paragraphs via
TestFixtures.js. The reference doc's checked-in portable-text source is
tests/fixtures/action-reference.apt.txt — reviewable/extendable as plain
text, and regenerable from (or into) the permanent canonical Doc via the
encode_reference_document / decode_reference_document fixtures
(src/PortableText.js).

Seeded ONCE per test session (module-scoped `reference` fixture below), not
once per test — decode + a single sync against a live GAS backend is
expensive; every test in this file reads the SAME synced state.

This file is the closing artifact for the doc-content-representable cases
from five open [TST] beads:
  - gts-ucdz  grammar accept/reject matrix              (TestGrammarMatrix)
  - gts-thwh  unparseable paragraph reported, not skipped (TestUnparseableReporting)
  - gts-tz5x  hyperlink round trip                       (TestHyperlinkRoundTrip)
  - gts-82s2  continuation-line field parsing            (TestFieldContinuation)
  - gts-nrxn  dual-prefix read / shared N namespace       (TestDualPrefix)

Each bead also lists cases that are BEHAVIORAL, not doc content — a second
no-op sync's idempotency, an entry-point audit across menu/WebApp/sweep call
sites, a create-action flow, a negative "no link key" default. Those stay
each bead's own scope and are not duplicated here; each section's docstring
says which of its bead's numbered cases this file covers.
"""
import pathlib

import pytest

from scn.session import ScenarioSession

_APT_PATH = pathlib.Path(__file__).parent / "fixtures" / "action-reference.apt.txt"


@pytest.fixture(scope="module")
def reference(settings):
    """Decodes the checked-in reference doc into a fresh doc, syncs once, and
    hands every test in this module (scn, rows) — rows keyed by the token
    portion of globalId (e.g. 'ACT-1', 'AI-10')."""
    scn = ScenarioSession.new_doc(settings)
    apt = _APT_PATH.read_text()
    resp = scn._post_fixture("decode_reference_document", {"apt": apt})
    assert (resp.get("data") or {}).get("ok"), f"decode_reference_document failed: {resp}"
    scn.sync()
    rows = {r.global_id.split("/")[-1]: r for r in scn.find_sheet_actions()}
    yield scn, rows
    scn.close()


def _row(rows, token):
    assert token in rows, f"{token} missing from synced rows; got {sorted(rows)}"
    return rows[token]


def _debug_runs(scn, doc_id, n):
    resp = scn._post_fixture("debug_action_runs", {"docId": doc_id, "n": n})
    return resp.get("data") or {}


# ---------------------------------------------------------------------------
# gts-ucdz — grammar accept/reject matrix (docs/CONTEXT.md §Action Format /
# ADR-0027). Case 11's malformed-line counterpart lives in
# TestUnparseableReporting below (it is that bead's own case 1).
# ---------------------------------------------------------------------------

class TestGrammarMatrix:

    def test_case1_at_sigil_email(self, reference):
        _, rows = reference
        r = _row(rows, "ACT-3")
        assert r.assignee == "jane@example.com"
        assert r.action == "finish the report"
        assert r.status == "Open"

    def test_case2_bare_email_identical_output_to_sigil(self, reference):
        _, rows = reference
        r3, r4 = rows["ACT-3"], rows["ACT-4"]
        assert r3.assignee == r4.assignee == "jane@example.com"
        assert r3.action == r4.action == "finish the report"
        assert r3.status == r4.status == "Open"

    def test_case3_person_chip_identity_wins(self, reference):
        _, rows = reference
        r = _row(rows, "ACT-5")
        assert r.assignee == "jane@example.com"
        assert r.assignee_name, "a PERSON chip must carry a display name, not just an email"

    def test_case4_literal_pipe_in_action_text(self, reference):
        _, rows = reference
        r = _row(rows, "ACT-6")
        assert r.action == "approve the design doc, please | thanks"

    def test_case5_status_with_trailing_text_preserved(self, reference):
        _, rows = reference
        r = _row(rows, "ACT-7")
        assert r.status == "Open"
        assert r.action == "ship it - done"

    def test_case6_no_status_detected_parens_literal(self, reference):
        _, rows = reference
        r = _row(rows, "ACT-8")
        assert r.status == "Open"  # default -- not read from "(draft)"
        assert r.action == "(draft) proposal"

    def test_case7_bare_token_empty_action_text(self, reference):
        _, rows = reference
        r = _row(rows, "ACT-9")
        assert r.action == ""
        assert not r.assignee

    def test_case8_legacy_ai_prefix_accepted(self, reference):
        _, rows = reference
        r = _row(rows, "AI-10")
        assert r.action == "legacy spelling still works"
        assert r.status == "Open"

    def test_case9_header_status_detected_with_continuation_present(self, reference):
        _, rows = reference
        r = _row(rows, "ACT-11")
        assert r.status == "In Progress"

    def test_case10_continuation_line_parens_not_read_as_status(self, reference):
        # Same row as case 9: the Notes field value ends "...(blocked)" — the
        # header-line status must win, not this trailing paren group.
        _, rows = reference
        r = _row(rows, "ACT-11")
        assert r.status == "In Progress"

    def test_case11_plain_prose_paragraph_not_an_action(self, reference):
        _, rows = reference
        texts = [r.action for r in rows.values()]
        assert "This document tracks Q3 deliverables for the design team." not in texts

    def test_strict_superset_every_row_present(self, reference):
        """Every one of the 21 well-formed action paragraphs in the
        reference doc produced exactly one row -- nothing the grammar
        accepts today was silently dropped."""
        _, rows = reference
        expected = {"ACT-%d" % n for n in list(range(1, 10)) + list(range(11, 22))} | {"AI-10"}
        assert expected <= set(rows), f"missing rows: {expected - set(rows)}"


# ---------------------------------------------------------------------------
# gts-thwh — unparseable paragraph is reported, not skipped (ADR-0027 rule
# 6). Case 1 only -- cases 2/3 (well-formed action / prose not reported) are
# gts-ucdz's cases 1-10 and 11 respectively, already asserted above. Cases 4
# (persists across sync-then-verify) and 5 (entry-point audit) are
# behavioral and stay gts-thwh's own scope.
# ---------------------------------------------------------------------------

class TestUnparseableReporting:

    def test_case1_malformed_token_reported_not_synced(self, reference):
        scn, rows = reference
        texts = [r.action for r in rows.values()]
        assert not any("someone" in t for t in texts), (
            "'ACT-77 | someone | do the thing' (no colon after the token "
            "digits) must not have synced a row"
        )
        data = (scn._post_fixture("verify_consistency").get("data")) or {}
        issues = data.get("issues") or []
        matches = [i for i in issues if "does not parse" in i]
        assert matches, f"expected an unparseable-action-paragraph issue, got: {issues!r}"
        assert "ACT-77 | someone | do the thing" in matches[0]
        assert data.get("counts", {}).get("unparseable") == 1


# ---------------------------------------------------------------------------
# gts-tz5x — hyperlink round trip (ADR-0027 rules 10-15). Cases 1-3 are doc
# content; case 4 (chip link on the token unchanged) is asserted here too
# since every row in this doc already carries a token chip link. Cases 5
# (idempotency) and 6 (no-link-key negative) are behavioral / read-side
# defaults and stay gts-tz5x's own scope.
# ---------------------------------------------------------------------------

class TestHyperlinkRoundTrip:

    def test_case1_link_mid_action_survives(self, reference):
        scn, rows = reference
        r = _row(rows, "ACT-19")
        runs = _debug_runs(scn, r.doc_id, 19)
        link_runs = [x for x in (runs.get("scanRuns") or []) if x.get("link")]
        assert link_runs, f"no linked run found for ACT-19: {runs}"
        assert link_runs[0]["link"].startswith("https://example.com/docs")
        assert runs.get("scanActionText") == "Please see the Q3 deck for context"

    def test_case2_link_only_action_survives_hasformatting_gate(self, reference):
        scn, rows = reference
        r = _row(rows, "ACT-20")
        runs = _debug_runs(scn, r.doc_id, 20)
        scan_runs = runs.get("scanRuns") or []
        assert scan_runs, "a link-only action must not report empty scanRuns (rule 12)"
        assert any(x.get("link") for x in scan_runs)
        assert not any(x.get("bold") or x.get("italic") for x in scan_runs)

    def test_case3_encodable_url_round_trips(self, reference):
        scn, rows = reference
        r = _row(rows, "ACT-19")
        runs = _debug_runs(scn, r.doc_id, 19)
        link_runs = [x for x in (runs.get("scanRuns") or []) if x.get("link")]
        assert link_runs
        assert "x=1" in link_runs[0]["link"] and "y=2" in link_runs[0]["link"]

    def test_case4_chip_link_on_token_unchanged(self, reference):
        """Every row's token carries a chip link independent of any run
        link this file's actions may also carry -- spot-check the
        link-bearing rows plus a plain one."""
        _, rows = reference
        for token in ("ACT-3", "ACT-19", "ACT-20"):
            r = _row(rows, token)
            assert r.global_id, f"{token} missing a globalId (token chip link derives from it)"


# ---------------------------------------------------------------------------
# gts-82s2 — continuation-line field parsing and prose disambiguation
# (ADR-0027 rules 5/5a/9). Case 7 (idempotency) is behavioral and stays
# gts-82s2's own scope.
# ---------------------------------------------------------------------------

class TestFieldContinuation:

    def test_case1_context_md_worked_example(self, reference):
        scn, rows = reference
        r = _row(rows, "ACT-2")
        assert "Draft the Q4 board deck and circulate" in r.action
        assert "- pull last year's actuals" in r.action
        assert r.status == "In Progress"
        runs = _debug_runs(scn, r.doc_id, 2)
        fields = runs.get("scanCustomFields") or {}
        assert fields.get("Target", {}).get("text") == "September 12 board meeting"
        assert fields.get("Progress", {}).get("text") == "outline done, needs the revenue section"
        assert fields.get("Consult With", {}).get("text") == "\n- Stuart\n- John"
        assert "a|b" in (fields.get("Notes", {}).get("text") or "")

    def test_case2_lowercase_colon_line_stays_prose(self, reference):
        scn, rows = reference
        r = _row(rows, "ACT-13")
        assert "then he said: we should ship it" in r.action
        runs = _debug_runs(scn, r.doc_id, 13)
        fields = runs.get("scanCustomFields") or {}
        assert not fields, f"'then he said:' must not parse as a field: {fields}"

    def test_case3_adjacent_action_paragraphs_not_merged(self, reference):
        _, rows = reference
        r14, r15 = _row(rows, "ACT-14"), _row(rows, "ACT-15")
        assert r14.action == "wrap up the sprint"
        assert r15.action == "kick off the next one"

    def test_case4_prose_before_first_field_goes_to_action_text(self, reference):
        scn, rows = reference
        r = _row(rows, "ACT-12")
        assert "just a continuation sentence, no colon" in r.action
        runs = _debug_runs(scn, r.doc_id, 12)
        fields = runs.get("scanCustomFields") or {}
        assert fields.get("Target", {}).get("text") == "next week"
        assert "just a continuation sentence" not in (fields.get("Target", {}).get("text") or "")

    def test_case5_field_value_ending_in_parens_not_status(self, reference):
        _, rows = reference
        r = _row(rows, "ACT-11")
        assert r.status == "In Progress"

    def test_case6_field_value_hyperlink_survives(self, reference):
        scn, rows = reference
        r = _row(rows, "ACT-18")
        runs = _debug_runs(scn, r.doc_id, 18)
        fields = runs.get("scanCustomFields") or {}
        notes = fields.get("Notes") or {}
        assert "Q3 deck" in (notes.get("text") or "")
        link_runs = [x for x in (notes.get("runs") or []) if x.get("link")]
        assert link_runs, f"Notes field lost its hyperlink: {notes}"
        assert "docs.google.com" in link_runs[0]["link"]

    def test_case8_overlong_field_name_degrades_to_prose(self, reference):
        scn, rows = reference
        r = _row(rows, "ACT-16")
        assert "This Is A Really Very Long Field Name Indeed Here" in r.action
        runs = _debug_runs(scn, r.doc_id, 16)
        fields = runs.get("scanCustomFields") or {}
        assert not any(k.startswith("This Is A Really") for k in fields), (
            f"a 51-char field name must degrade to prose, not become a field: {fields}"
        )

    def test_case9_block_scoping_worked_example(self, reference):
        scn, rows = reference
        r = _row(rows, "ACT-1")
        runs = _debug_runs(scn, r.doc_id, 1)
        fields = runs.get("scanCustomFields") or {}
        assert fields.get("Consult With", {}).get("text") == "\n- Stuart\n- John"
        assert fields.get("Due", {}).get("text") == "Tuesday"
        assert "- Stuart" not in r.action and "- John" not in r.action

    def test_case10_bare_field_line_empty_inline_value(self, reference):
        scn, rows = reference
        r = _row(rows, "ACT-1")
        runs = _debug_runs(scn, r.doc_id, 1)
        fields = runs.get("scanCustomFields") or {}
        consult = fields.get("Consult With") or {}
        assert consult.get("text", "").startswith("\n"), (
            "a bare 'Consult With:' line's own inline value is empty -- the "
            "value's text must start with the next line's leading \\n"
        )

    def test_case11_repeated_field_name_appends(self, reference):
        scn, rows = reference
        r = _row(rows, "ACT-17")
        runs = _debug_runs(scn, r.doc_id, 17)
        fields = runs.get("scanCustomFields") or {}
        assert fields.get("Due", {}).get("text") == "Monday\nTuesday", (
            f"repeated 'Due:' lines must append in document order, not "
            f"overwrite: {fields.get('Due')}"
        )
        assert fields.get("Notes", {}).get("text") == "first note"


# ---------------------------------------------------------------------------
# gts-nrxn — dual-prefix read, ACT-N canonical write, shared N namespace
# (ADR-0023). Case 1 (legacy AI-N read) and the read-side half of case 4
# (shared N namespace across spellings) are doc content. Cases 2, 3, 5, 6
# need a live create/flush flow this static reference doc cannot exercise
# and stay gts-nrxn's own scope.
# ---------------------------------------------------------------------------

class TestDualPrefix:

    def test_case1_legacy_ai_n_reads_unrewritten(self, reference):
        _, rows = reference
        r = _row(rows, "AI-10")
        assert r.global_id.endswith("/AI-10"), (
            f"a legacy AI-N globalId must not be rewritten to ACT-N on read: {r.global_id}"
        )

    def test_case4_n_namespace_shared_across_spellings(self, reference):
        """AI-10 sits between ACT-9 and ACT-11 in document order and got
        N=10 -- the counter is one shared sequence across both token
        spellings, not a separate one per prefix."""
        _, rows = reference
        assert _row(rows, "ACT-9").global_id.endswith("/ACT-9")
        assert _row(rows, "AI-10").global_id.endswith("/AI-10")
        assert _row(rows, "ACT-11").global_id.endswith("/ACT-11")
