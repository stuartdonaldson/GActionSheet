"""
test_floating_action_scanner.py — floating action scanner: table cells,
bulleted lists, mixed placement, tracker-table exclusion (GTaskSheet-dq6t
AC-1 through AC-6), and soft-return single-AI-per-paragraph model
(GTaskSheet-cn5v AC-T1 through AC-T4).

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
# AC-1/AC-2 — bulleted list, body level
# ---------------------------------------------------------------------------

def test_bulleted_list_body_level_action_detected(settings, request):
    """A bare AI: token in a body-level bulleted list item is assigned a
    number by _assignPlaceholderTokens and produces a correct AI-N: row."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        action_text = "dq6t bulleted list body-level action"
        scn._post_fixture("append_doc_list_item", {"text": f"AI: {action_text}"})
        scn.sync()

        row = _find_action(scn, action_text)
        assert row.action_id is not None
    finally:
        scn.close()


# ---------------------------------------------------------------------------
# AC-3 — table, multiple cells, distinct actionText
# ---------------------------------------------------------------------------

def test_table_cell_actions_distinct(settings, request):
    """A 2x2 table with AI: tokens in cell(0,0) and cell(1,1) produces two
    distinct rows after sync — the scanner does not confuse the two cells."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        scn._post_fixture("append_doc_table", {"rows": [
            [{"text": "AI: cell-0-0 task"}, {"text": ""}],
            [{"text": ""}, {"text": "AI: cell-1-1 task"}],
        ]})
        scn.sync()

        row00 = _find_action(scn, "cell-0-0 task")
        row11 = _find_action(scn, "cell-1-1 task")
        assert row00.global_id != row11.global_id
    finally:
        scn.close()


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
# AC-5 — bulleted list item inside a table cell
# ---------------------------------------------------------------------------

def test_list_item_inside_table_cell_detected(settings, request):
    """A list-item paragraph inside a table cell with an AI: token is scanned
    and produces a sheet row (exercises the LIST_ITEM branch in
    _collectTableCellActions)."""
    scn = ScenarioSession.new_doc(settings, request=request)
    try:
        action_text = "dq6t list-item inside table cell"
        scn._post_fixture("append_doc_table", {"rows": [
            [{"text": f"AI: {action_text}", "listItem": True}, {"text": ""}],
        ]})
        scn.sync()

        row = _find_action(scn, action_text)
        assert row.action_id is not None
    finally:
        scn.close()


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
            "AI-1: dr8j soft flush\nline two\nline three (Open)", "sync flush"
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
            "AI-1: dr8j soft flush\nline two\nline three (Done)", "sidebar flush"
        )

        # And the round trip closes: rescanning the flushed doc yields the same
        # action text it started with, so a further sync/flush is stable.
        scn.sync()
        row = _find_action(scn, action_text)
        assert row.status == "Done"
        assert_doc_paragraph(
            "AI-1: dr8j soft flush\nline two\nline three (Done)", "resync flush"
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
