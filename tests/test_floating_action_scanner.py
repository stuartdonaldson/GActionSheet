"""
test_floating_action_scanner.py — floating action scanner: tracker-table
exclusion (GTaskSheet-dq6t AC-6) and the two remaining grammar cases with no
specifiable text-diff oracle (sidebar-flush entry point, PERSON-chip
fast-path/soft-return comparison).

Everything else this file used to cover has been retired onto checked-in APT
corpora, run through batched lanes — see the retirement notes inline below
for what moved where and why. AC-1/AC-2/AC-3/AC-5 (structural container
detection) retired gts-45fg/act-retire; AC-4 (table-cell surrounding text),
AC-T1 through AC-T4 (soft-return single-AI-per-paragraph model, GTaskSheet-cn5v),
gts-jxrw, gts-v0py, gts-xvlu and the gts-ogev text-email case retired
gts-oaw1/act-retire (staged plan `docdata-litter-apt-speed.md`, stage
`apt-scanner-migration`) onto `tests/test_apt_scanner_lane.py`.

AC-7/AC-8 (@create mid-cell caret placement, Playwright-driven) need a new
UiDriver capability for placing the caret inside a specific table cell —
split into a follow-up issue (bd comment on GTaskSheet-dq6t) since they
exercise UI precision, not the scanner's detection surface this file covers.

Doc-seeding uses the append_doc_table / append_doc_list_item /
append_doc_soft_paragraph / append_tracker_cell_text / append_doc_soft_paragraph_with_chip
TestFixtures.js cases added alongside these tests.
"""
from scn.engine import CheckpointKind, Surface
from scn.session import ScenarioSession

SHEET = Surface.SHEET
STEP = CheckpointKind.STEP


def _find_action(scn, action_text):
    rows = scn.find_sheet_actions()
    row = next((r for r in rows if r.action == action_text), None)
    assert row is not None, (
        f"action {action_text!r} not found in sheet after sync; "
        f"rows={[r.action for r in rows]!r}"
    )
    return row


def _assert_action_absent(scn, action_text):
    rows = scn.find_sheet_actions()
    assert not any(r.action == action_text for r in rows), (
        f"action {action_text!r} unexpectedly present in sheet: "
        f"{[r.action for r in rows]!r}"
    )


def _find_by_global_id(scn, global_id):
    rows = scn.find_sheet_actions()
    row = next((r for r in rows if r.global_id == global_id), None)
    assert row is not None, (
        f"global_id {global_id!r} not found after sync; "
        f"rows={[(r.global_id, r.action) for r in rows]!r}"
    )
    return row


# ---------------------------------------------------------------------------
# AC-1/AC-2 (bulleted list, body level) and AC-3 (table, multiple cells,
# distinct actionText) retired gts-45fg/act-retire: both are structural
# container detection, now covered by tests/fixtures/list-and-table-
# containers.apt.txt Case 1 (LI) / Case 3 (2x2 TABLE, distinct cells) via
# tests/test_apt_corpus_check.py::TestScenarioRoundTrip — decode into a
# fresh doc, sync, and diff clean against the golden proves the same
# detection this pair asserted, at lower cost per case (gts-83s5's own
# description named these as the retirement target).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# AC-4 (table cell, surrounding text: 'AI: task suffix' suffix case and the
# 'prefix AI: task' not-anchored negative case) retired gts-oaw1/act-retire:
# a specifiable grammar oracle, now covered by
# tests/fixtures/scanner-table-cell.apt.txt (Cases 1/2) via
# tests/test_apt_scanner_lane.py's batched lane.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# AC-5 (bulleted list item inside a table cell) retired gts-45fg/act-retire:
# structural container detection, now covered by tests/fixtures/list-and-
# table-containers.apt.txt Case 3b (<LI> nested inside <CELL>) via
# tests/test_apt_corpus_check.py::TestScenarioRoundTrip — same rationale as
# the AC-1/AC-2/AC-3 pair above.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# AC-6 — tracker table exclusion. NOT migrated: docs/interfaces/action-
# portable-text.md §"List items and table cells (v2)" states this
# explicitly — "Tracker-table exclusion ... is scanner behaviour, not an
# APT concern — APT v2 encodes any table generically; which tables the
# scanner chooses to scan is orthogonal." There is no APT construct for
# "this table is the Action Item Tracker" to round-trip against.
# ---------------------------------------------------------------------------

def test_tracker_table_tokens_excluded(settings, request):
    """AI: tokens inside the Action Item Tracker table are NOT collected by
    the scanner and do NOT produce sheet rows."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        action_text = "dq6t tracker-table excluded action"
        scn.sync()  # creates the doc-level Actions/DocData scaffolding
        scn._post_fixture("insert_tracker_table")
        scn._post_fixture("append_tracker_cell_text", {"text": f"AI: {action_text}"})
        scn.sync()

        _assert_action_absent(scn, action_text)
    finally:
        scn.close()


# ---------------------------------------------------------------------------
# Soft-return paragraphs — one AI: token per paragraph (GTaskSheet-cn5v
# AC-T1 through AC-T4) retired gts-oaw1/act-retire: a specifiable grammar
# oracle, now covered by tests/fixtures/scanner-soft-return.apt.txt via
# tests/test_apt_scanner_lane.py's batched lane.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# gts-dr8j — soft returns survive the sheet -> doc flush (write-back
# direction). NOT migrated: exercises flush entry point 6 (the sidebar
# status-set call site), which docs/interfaces/action-portable-text.md
# §"Batched lanes" explicitly carves out — "Entry points 5 and 6
# (preview-card/sidebar status taps) stay covered by their existing
# UI-driven tests — a sheet edit does not reach those call sites."
# ---------------------------------------------------------------------------

def test_soft_return_survives_sidebar_status_flush(settings, request):
    """gts-dr8j: soft-return continuation lines round-trip through a flush.

    Preserving the line breaks on the way INTO the sheet (formerly the three
    AC-T tests, now tests/fixtures/scanner-soft-return.apt.txt) is only half
    the round trip — the write-back has to reinsert a real soft return, or
    the next flush silently destroys what the scan preserved. The sidebar
    status-set path is the flush call site that matters most here: it
    rescans the LIVE doc and pushes that raw text straight back through the
    Docs REST API's insertText, so it never sees the sheet's normalization
    (gts-kkm7.5).

    Asserts on the durable doc surface, and specifically on the three ways
    this has failed or could fail: lines concatenated with no separator at all
    (\\r stripped by insertText), lines split into separate hard paragraphs
    (\\n), and lines collapsed to spaces (the previous workaround).
    """
    from tests.helpers.doc_inspect import load_doc, paragraph_texts_with_breaks
    from tests.helpers.download import download_docx

    action_text = "dr8j soft flush\nline two\nline three"

    def assert_doc_paragraph(expected, after):
        """The action must occupy exactly ONE paragraph with the given text.

        One entry (not three) is what proves the breaks are soft returns rather
        than hard paragraph breaks; the exact text is what rules out both the
        no-separator and the space-collapsed outcomes.
        """
        paras = paragraph_texts_with_breaks(load_doc(download_docx(scn.doc_id)))
        hits = [p for p in paras if "dr8j soft flush" in p]
        assert len(hits) == 1, (
            f"after {after}: expected the action to stay in ONE paragraph, got "
            f"{hits!r} (all paragraphs: {paras!r})"
        )
        assert hits[0] == expected, (
            f"after {after}: flush did not reproduce the original soft returns: "
            f"{hits[0]!r} != {expected!r}"
        )

    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture("append_doc_soft_paragraph", {"text": f"AI-1: {action_text}"})

        # syncDocument's batch flush — the first of the two _buildFlushRequests
        # call sites this test covers. It rewrites the paragraph to attach the
        # status image and chip link, so the soft returns have to survive here
        # before the sidebar path is even reachable.
        scn.sync()
        assert_doc_paragraph(
            "AI-1: dr8j soft flush (Open)\nline two\nline three", "sync flush"
        )

        row = _find_action(scn, action_text)
        assert row.global_id.endswith("/AI-1")

        # Sidebar status-set — the second call site, and the one gts-kkm7.5 was
        # filed against: it rescans the LIVE doc and pushes that raw text back
        # through insertText without the sheet's normalization in between.
        resp = scn._post_fixture(
            "sidebar_set_status",
            {"targetText": action_text, "newStatus": "Done"},
        )
        assert not (resp.get("data") or {}).get("error"), (
            f"sidebar_set_status fixture failed: {resp!r}"
        )
        assert_doc_paragraph(
            "AI-1: dr8j soft flush (Done)\nline two\nline three", "sidebar flush"
        )

        # And the round trip closes: rescanning the flushed doc yields the same
        # action text it started with, so a further sync/flush is stable.
        scn.sync()
        row = _find_action(scn, action_text)
        assert row.status == "Done"
        assert_doc_paragraph(
            "AI-1: dr8j soft flush (Done)\nline two\nline three", "resync flush"
        )
    finally:
        scn.close()


# ---------------------------------------------------------------------------
# gts-jxrw — bare "AI-N: " token must not absorb a following soft-return
# continuation line into action_text (twin [TST]: gts-jav4). Both cases
# retired gts-oaw1/act-retire onto tests/fixtures/scanner-jxrw.apt.txt via
# tests/test_apt_scanner_lane.py's batched lane. That migration found the
# continuation line is not merely excluded from action_text — the flush
# rewrite drops the physical continuation line from the DOCUMENT entirely
# for the bare-token case, something this file's tests never checked (they
# only asserted the sheet-side absence). See scanner-jxrw-expected.apt.txt's
# Case 1 for the observed behavior; not investigated further here (no src/
# change made — this migration only proves what the scanner already does).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# gts-v0py — status token followed by trailing user text (twin [TST]:
# gts-jav4). Both cases retired gts-oaw1/act-retire onto
# tests/fixtures/scanner-jxrw.apt.txt Case 3 (folded into the jxrw corpus
# rather than a standalone one — a single already-established record with no
# other content in its own corpus would trip the degenerate-scenario lint,
# gts-5st5) via tests/test_apt_scanner_lane.py's batched lane.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ADR-0027 rule 6 / gts-xvlu — unparseable-action-paragraph is reported, not
# silently skipped. Retired gts-oaw1/act-retire: the round-trip corpus
# already existed (tests/fixtures/unparseable-reporting.apt.txt Case 1,
# gts-thwh) but only proved the paragraph's TEXT survives untouched, not
# that verify_consistency actually REPORTS it — extended with Cases 2/3 and
# reused under tests/test_apt_scanner_lane.py's own batch tag
# (unparseable-reporting-verify.scenario.json) so a live verify_consistency
# call could be asserted on the same open ScenarioSession.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# gts-ogev — PERSON-chip parity between the single-token fast path
# (_parseParagraphAsFloatingAction) and the soft-return path
# (_parseSoftReturnParagraphActions). Twin [TST]: gts-mt39.
#
# Only the text-email regression guard (test_ogev_soft_return_text_email_
# assignee_unchanged) retired gts-oaw1/act-retire, onto
# tests/fixtures/scanner-ogev.apt.txt via tests/test_apt_scanner_lane.py.
#
# test_ogev_soft_return_person_chip_matches_fast_path stays HERE, NOT
# migrated: it needs a paragraph seeded via append_doc_paragraph_with_chip's
# insertPerson-direct construction (fast path) to compare against, so both
# sides of the comparison are built the same mechanical way. gts-i0gk
# (filed live during the gts-oaw1 migration, since RESOLVED 2026-08-31) had
# found a PERSON chip on a soft-return CONTINUATION line came back
# unassigned via BOTH construction paths — decodeAptIntoDoc's chip-offset
# math (_aptBuildInsertPayload/_aptApplyPayloadViaRest) and the soft-return
# scanner's own chip lookup (_personChipAtParaOffset,
# _parseSoftReturnParagraphActions). Both are confirmed correct as of
# v0.2.3.69 — see test_mt39_soft_return_multi_token_person_chip_parity
# below, which proves the decodeAptIntoDoc path directly. This test is kept
# on its own construction path anyway, per the frozen AC's own wording
# ("matching the single-token fast path's output for the SAME chip").
# ---------------------------------------------------------------------------

# A real Google contact resolvable by the Docs REST API's insertPerson (same
# account used as a chip target elsewhere, e.g. test_view_b.py's CALLER_EMAIL).
_OGEV_CHIP_EMAIL = "stuart.donaldson@gmail.com"


def test_ogev_soft_return_person_chip_matches_fast_path(settings, request):
    """gts-ogev frozen AC: a PERSON chip placed immediately after the token in
    a multi-line (soft-return) paragraph resolves assignee_email/assignee_name
    from the chip, matching what the single-token fast path resolves for the
    SAME chip email — the frozen AC's own wording ("matching the single-token
    fast path's output for the same chip"), so the assertion compares the two
    paths directly rather than hard-coding Google's contact-resolved display
    name.
    """
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture("append_doc_paragraph_with_chip", {
            "token": "ACT-80:", "email": _OGEV_CHIP_EMAIL, "after": "fast path chip parity",
        })
        scn._post_fixture("append_doc_soft_paragraph_with_chip", {
            "before": "context intro", "token": "ACT-81:",
            "email": _OGEV_CHIP_EMAIL, "after": "soft return chip parity",
        })
        scn.sync()

        fast_row = _find_by_global_id(scn, f"{scn.doc_id}/ACT-80")
        soft_row = _find_by_global_id(scn, f"{scn.doc_id}/ACT-81")

        assert fast_row.assignee == _OGEV_CHIP_EMAIL, (
            f"fast path did not resolve the chip email: {fast_row.assignee!r}"
        )
        assert soft_row.assignee == _OGEV_CHIP_EMAIL, (
            f"soft-return path lost the chip's assignee email (pre-fix behavior): "
            f"{soft_row.assignee!r}"
        )
        assert soft_row.assignee_name == fast_row.assignee_name, (
            f"soft-return path's chip-resolved name {soft_row.assignee_name!r} does not "
            f"match the fast path's {fast_row.assignee_name!r} for the same chip"
        )
        assert soft_row.action == "soft return chip parity"
    finally:
        scn.close()


# ---------------------------------------------------------------------------
# gts-mt39 — twin [TST] for gts-ogev. Pre-code contract: entry point
# syncDocument(); log tag sync.complete; output schema unchanged
# (assigneeEmail/assigneeName populated from the chip).
#
# Frozen AC: a soft-return paragraph carrying TWO AI-N: tokens, each with its
# own PERSON chip immediately after it, resolves BOTH actions' assignee
# fields from their respective chips — not just a token immediately after
# the paragraph's own first line (that half is gts-ogev's own test above).
# A parallel case with the existing text-email assignee form (no chip)
# confirms that shape is unchanged (regression guard).
#
# Built via decode_reference_document (decodeAptIntoDoc), not the insertPerson
# fixture gts-ogev's test uses: gts-i0gk found and this suite's own re-check
# (2026-08-31) confirms decodeAptIntoDoc resolves a PERSON chip on a
# non-first soft-return line correctly as of v0.2.3.69, so this is now the
# simplest construction for a two-chip, two-token paragraph.
# ---------------------------------------------------------------------------

_MT39_CHIP_EMAIL_A = "stuart.donaldson@gmail.com"
_MT39_CHIP_EMAIL_B = "stuart.donaldson@gmail.com"  # same resolvable contact; distinct tokens still assert independently


def test_mt39_soft_return_multi_token_person_chip_parity(settings, request):
    apt = (
        "AI-90: {{chip:" + _MT39_CHIP_EMAIL_A + "}}\n"
        "AI-91: {{chip:" + _MT39_CHIP_EMAIL_B + "}} second token continuation\n"
        "\n"
        "AI-92: jane.mt39@example.com\n"
        "AI-93: john.mt39@example.com second token text email\n"
    )
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        resp = scn._post_fixture("decode_reference_document", {"apt": apt})
        assert (resp.get("data") or {}).get("ok"), f"decode_reference_document failed: {resp}"
        scn.sync()

        first_chip  = _find_by_global_id(scn, f"{scn.doc_id}/AI-90")
        second_chip = _find_by_global_id(scn, f"{scn.doc_id}/AI-91")
        assert first_chip.assignee == _MT39_CHIP_EMAIL_A, (
            f"first token in a multi-token soft-return paragraph lost its chip assignee: "
            f"{first_chip.assignee!r}"
        )
        assert second_chip.assignee == _MT39_CHIP_EMAIL_B, (
            f"second token in a multi-token soft-return paragraph lost its chip assignee: "
            f"{second_chip.assignee!r}"
        )
        assert second_chip.assignee_name == first_chip.assignee_name, (
            "both chips resolve the same contact; their resolved display names must match"
        )
        assert second_chip.action == "second token continuation"

        # Regression guard: the existing text-email form on the same
        # two-token-per-paragraph shape is unchanged by the chip fix.
        first_text  = _find_by_global_id(scn, f"{scn.doc_id}/AI-92")
        second_text = _find_by_global_id(scn, f"{scn.doc_id}/AI-93")
        assert first_text.assignee == "jane.mt39@example.com"
        assert second_text.assignee == "john.mt39@example.com"
        assert second_text.action == "second token text email"
    finally:
        scn.close()
