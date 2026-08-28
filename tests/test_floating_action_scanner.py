"""
test_floating_action_scanner.py — floating action scanner: table cells,
bulleted lists, mixed placement, tracker-table exclusion (GTaskSheet-dq6t
AC-4 and AC-6; AC-1/AC-2/AC-3/AC-5 retired gts-45fg/act-retire, see below),
and soft-return single-AI-per-paragraph model (GTaskSheet-cn5v AC-T1
through AC-T4).

AC-1/AC-2 (bulleted list, body level), AC-3 (table, multiple cells,
distinct actionText) and AC-5 (list item inside a table cell) are
structural container-detection cases, retired gts-45fg/act-retire in favor
of tests/fixtures/list-and-table-containers.apt.txt (Cases 1/3/3b) run
through tests/test_apt_corpus_check.py — decode into a fresh doc, sync,
diff clean against the golden. See the removal notes inline below.

AC-7/AC-8 (@create mid-cell caret placement, Playwright-driven) need a new
UiDriver capability for placing the caret inside a specific table cell —
split into a follow-up issue (bd comment on GTaskSheet-dq6t) since they
exercise UI precision, not the scanner's detection surface this file covers.

Doc-seeding uses the append_doc_table / append_doc_list_item /
append_doc_soft_paragraph / append_tracker_cell_text TestFixtures.js cases
added alongside these tests.

Note on AC-4's "prefix" sub-case: _parseParagraphAsFloatingAction and
_collectTokenParagraphs both anchor the AI:/AI-N: token at the START of the
paragraph text (^AI-?). A token with a word BEFORE it ("prefix AI: task") is
therefore never recognized as a floating action at all -- not body-level,
not in a table cell. This test documents that current (anchored-only)
behavior rather than the ticket's "syncs correctly" wording, which does not
match the shipped scanner.
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
# AC-4 — table cell, surrounding text
# ---------------------------------------------------------------------------

def test_table_cell_action_suffix_text_parses(settings, request):
    """'AI: task suffix' in a cell parses correctly: actionText = 'task suffix'."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture("append_doc_table", {"rows": [
            [{"text": "AI: task suffix"}, {"text": ""}],
        ]})
        scn.sync()

        _find_action(scn, "task suffix")
    finally:
        scn.close()


def test_table_cell_action_prefix_text_not_detected(settings, request):
    """'prefix AI: task' in a cell is NOT detected — the token is not anchored
    at the start of the paragraph (see module docstring)."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture("append_doc_table", {"rows": [
            [{"text": "prefix AI: task"}, {"text": ""}],
        ]})
        scn.sync()

        _assert_action_absent(scn, "task")
        _assert_action_absent(scn, "prefix AI: task")
    finally:
        scn.close()


# ---------------------------------------------------------------------------
# AC-5 (bulleted list item inside a table cell) retired gts-45fg/act-retire:
# structural container detection, now covered by tests/fixtures/list-and-
# table-containers.apt.txt Case 3b (<LI> nested inside <CELL>) via
# tests/test_apt_corpus_check.py::TestScenarioRoundTrip — same rationale as
# the AC-1/AC-2/AC-3 pair above.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# AC-6 — tracker table exclusion
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
# Soft-return paragraphs — one AI: token per paragraph (GTaskSheet-cn5v)
# ---------------------------------------------------------------------------

def test_soft_return_context_before_token(settings, request):
    """AC-T1: A paragraph whose text has contextual text on the first line and
    AI-1: on the second line (soft return) is detected; the contextual line
    does not appear in any sheet row."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture("append_doc_soft_paragraph",
                          {"text": "contextual text here\nAI-1: d7z8 context before token"})
        scn.sync()

        row = _find_action(scn, "d7z8 context before token")
        assert row.global_id.endswith("/AI-1")
        _assert_action_absent(scn, "contextual text here")
    finally:
        scn.close()


def test_soft_return_continuation_in_action_text(settings, request):
    """AC-T2: Soft-return continuation lines after the token are part of action
    text (to end of paragraph)."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture("append_doc_soft_paragraph",
                          {"text": "context\nAI-1: action text\ncontinuation line"})
        scn.sync()

        row = _find_action(scn, "action text\ncontinuation line")
        assert row.global_id.endswith("/AI-1")
    finally:
        scn.close()


def test_soft_return_bare_ai_with_continuation(settings, request):
    """AC-T3: A bare AI: token followed by soft-return continuation lines
    produces one row with the continuation included in action text; the bare
    token is assigned a number by _assignPlaceholderTokens."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture("append_doc_soft_paragraph",
                          {"text": "context\nAI: bare action\ncontinuation"})
        scn.sync()

        row = _find_action(scn, "bare action\ncontinuation")
        assert row.global_id is not None
    finally:
        scn.close()


def test_soft_return_context_and_multiline_action(settings, request):
    """AC-T4: Context intro before the token is excluded; all soft-return lines
    after the token through end of paragraph are included in action text."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture("append_doc_soft_paragraph",
                          {"text": "context intro\nAI-1: main action\nline 2\nline 3"})
        scn.sync()

        row = _find_action(scn, "main action\nline 2\nline 3")
        assert row.global_id.endswith("/AI-1")
        _assert_action_absent(scn, "context intro")
    finally:
        scn.close()


# ---------------------------------------------------------------------------
# gts-dr8j — soft returns survive the sheet -> doc flush (write-back direction)
# ---------------------------------------------------------------------------

def test_soft_return_survives_sidebar_status_flush(settings, request):
    """gts-dr8j: soft-return continuation lines round-trip through a flush.

    Preserving the line breaks on the way INTO the sheet (the three AC-T tests
    above) is only half the round trip — the write-back has to reinsert a real
    soft return, or the next flush silently destroys what the scan preserved.
    The sidebar status-set path is the flush call site that matters most here:
    it rescans the LIVE doc and pushes that raw text straight back through the
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
# continuation line into action_text (twin [TST]: gts-jav4)
# ---------------------------------------------------------------------------

def _find_by_global_id(scn, global_id):
    rows = scn.find_sheet_actions()
    row = next((r for r in rows if r.global_id == global_id), None)
    assert row is not None, (
        f"global_id {global_id!r} not found after sync; "
        f"rows={[(r.global_id, r.action) for r in rows]!r}"
    )
    return row


def test_jxrw_bare_token_with_continuation_yields_empty_action_text(settings, request):
    """gts-jxrw frozen AC: 'AI-N: ' (bare, trailing space, nothing else on that
    line) followed by a soft-return continuation line yields action_text=''
    for that action — the continuation line is NOT merged in. This is the
    live-reported repro shape (a following line under a bare token got
    absorbed and round-tripped back into the doc as one merged line)."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture(
            "append_doc_soft_paragraph",
            {"text": "AI-91: \nFollowing line item that must NOT be absorbed"},
        )
        scn.sync()

        row = _find_by_global_id(scn, f"{scn.doc_id}/AI-91")
        assert row.action == "", (
            f"expected empty action_text for bare token, got {row.action!r}"
        )
        _assert_action_absent(scn, "Following line item that must NOT be absorbed")
    finally:
        scn.close()


def test_jxrw_bare_token_alone_yields_empty_action_text(settings, request):
    """gts-jxrw frozen AC: 'AI-N: ' with no continuation at all still yields
    action_text=''. (Simplest instance of the same rule — no round trip
    needed to demonstrate it, but included as the AC's literal example.)"""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture("append_doc_soft_paragraph", {"text": "AI-92: "})
        scn.sync()

        row = _find_by_global_id(scn, f"{scn.doc_id}/AI-92")
        assert row.action == ""
    finally:
        scn.close()


def test_jxrw_adjacent_separate_list_items_unaffected(settings, request):
    """gts-jxrw negative test (from the bead's own investigation): two
    SEPARATE list items, each with their own AI-N: token, are NOT merged —
    the soft-return-continuation fix must not touch this case, which the bead
    author already confirmed live was not the trigger."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture("append_doc_list_item", {"text": "AI-93: first separate item"})
        scn._post_fixture("append_doc_list_item", {"text": "AI-94: second separate item"})
        scn.sync()

        row93 = _find_by_global_id(scn, f"{scn.doc_id}/AI-93")
        row94 = _find_by_global_id(scn, f"{scn.doc_id}/AI-94")
        assert row93.action == "first separate item"
        assert row94.action == "second separate item"
    finally:
        scn.close()


# ---------------------------------------------------------------------------
# gts-v0py — status token followed by trailing user text (twin [TST]: gts-jav4)
# ---------------------------------------------------------------------------

def test_v0py_status_token_with_trailing_text_parses_and_preserves_trailing(settings, request):
    """gts-v0py frozen AC: 'AI-N: text (Status) trailing' parses
    status='Status' and does not embed the literal '(Status)' token inside
    action_text. Documented decision: trailing text is PRESERVED (joined with
    the text before the token), not dropped."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture(
            "append_doc_soft_paragraph",
            {"text": "AI-95: Confirm Wednesdays work for Peter (Open) - done"},
        )
        scn.sync()

        row = _find_by_global_id(scn, f"{scn.doc_id}/AI-95")
        assert row.status == "Open"
        assert "(Open)" not in row.action
        assert row.action == "Confirm Wednesdays work for Peter - done", (
            f"trailing text after the status token was not preserved: {row.action!r}"
        )
    finally:
        scn.close()


def test_v0py_flush_does_not_double_status_token(settings, request):
    """gts-v0py frozen AC: a flush of a status-token-with-trailing-text action
    does not append a second '(Status)' to the document. Before the fix, the
    trailing-text case wasn't recognized as an explicit status at all, so the
    flush appended a status token on top of the ALREADY-present literal one,
    doubling it in the doc."""
    from tests.helpers.doc_inspect import load_doc, paragraph_texts_with_breaks
    from tests.helpers.download import download_docx

    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture(
            "append_doc_soft_paragraph",
            {"text": "AI-96: Confirm Wednesdays work for Peter (Open) - done"},
        )
        scn.sync()  # scan, then syncDocument's batch flush rewrites the paragraph

        paras = paragraph_texts_with_breaks(load_doc(download_docx(scn.doc_id)))
        hits = [p for p in paras if "Confirm Wednesdays work for Peter" in p]
        assert len(hits) == 1, f"expected exactly one matching paragraph, got {hits!r}"
        assert hits[0].count("(Open)") == 1, (
            f"expected exactly one '(Open)' token after flush, got: {hits[0]!r}"
        )
    finally:
        scn.close()


# ---------------------------------------------------------------------------
# ADR-0027 rule 6 / gts-xvlu — unparseable-action-paragraph is reported, not
# silently skipped. Repro is the gts-tis pipe-delimited spelling that used to
# vanish with no trace: _parseParagraphAsFloatingAction's token regex needs a
# trailing colon, so a bare "ACT-2 | ..." never matched at all.
# ---------------------------------------------------------------------------

def _run_verify_consistency(scn):
    resp = scn._post_fixture("verify_consistency")
    return resp.get("data") or {}


def test_xvlu_token_without_colon_reported_unparseable(settings, request):
    """A paragraph beginning with a token but missing the colon (token present,
    grammar incomplete) is reported by verify_consistency as
    'unparseable-action-paragraph', carrying the body index and leading text,
    and is not written to the ActionSheet."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture("append_doc_soft_paragraph",
                          {"text": "ACT-2 | someone | do the thing"})
        scn.sync()

        _assert_action_absent(scn, "do the thing")

        data = _run_verify_consistency(scn)
        assert not data.get("ok"), f"expected verify_consistency to report an issue: {data!r}"
        issues = data.get("issues") or []
        matches = [i for i in issues if "does not parse" in i]
        assert matches, f"expected an unparseable-action-paragraph issue, got: {issues!r}"
        assert "ACT-2 | someone | do the thing" in matches[0]
        assert data.get("counts", {}).get("unparseable") == 1
    finally:
        scn.close()


def test_xvlu_well_formed_action_not_reported(settings, request):
    """A well-formed action (token + colon) is not reported as unparseable."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture("append_doc_soft_paragraph",
                          {"text": "ACT-3: a perfectly normal action"})
        scn.sync()

        data = _run_verify_consistency(scn)
        issues = data.get("issues") or []
        assert not any("does not parse" in i for i in issues), f"unexpected unparseable report: {issues!r}"
        assert data.get("counts", {}).get("unparseable") == 0
    finally:
        scn.close()


def test_xvlu_prose_paragraph_not_reported(settings, request):
    """A plain prose paragraph with no action-token-like prefix is not an
    action and is not reported as unparseable."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture("append_doc_soft_paragraph",
                          {"text": "just some ordinary paragraph text, nothing to see here"})
        scn.sync()

        data = _run_verify_consistency(scn)
        issues = data.get("issues") or []
        assert not any("does not parse" in i for i in issues), f"unexpected unparseable report: {issues!r}"
        assert data.get("counts", {}).get("unparseable") == 0
    finally:
        scn.close()


# ---------------------------------------------------------------------------
# gts-ogev — PERSON-chip parity between the single-token fast path
# (_parseParagraphAsFloatingAction) and the soft-return path
# (_parseSoftReturnParagraphActions). Twin [TST]: gts-mt39.
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


def test_ogev_soft_return_text_email_assignee_unchanged(settings, request):
    """gts-ogev frozen AC regression guard: the soft-return path's existing
    text-based email assignee detection (no PERSON chip involved) is
    unchanged by the chip-detection fix."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture("append_doc_soft_paragraph", {
            "text": "context intro\nACT-82: jane.doe@example.com text email continuation",
        })
        scn.sync()

        row = _find_by_global_id(scn, f"{scn.doc_id}/ACT-82")
        assert row.assignee == "jane.doe@example.com"
        assert row.assignee_name == "Jane Doe"
        assert row.action == "text email continuation"
    finally:
        scn.close()
