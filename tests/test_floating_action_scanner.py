"""
test_floating_action_scanner.py — floating action scanner: table cells,
bulleted lists, mixed placement, tracker-table exclusion (GTaskSheet-dq6t
AC-1 through AC-6).

AC-7/AC-8 (@create mid-cell caret placement, Playwright-driven) need a new
UiDriver capability for placing the caret inside a specific table cell —
split into a follow-up issue (bd comment on GTaskSheet-dq6t) since they
exercise UI precision, not the scanner's detection surface this file covers.

Doc-seeding uses the append_doc_table / append_doc_list_item /
append_tracker_cell_text TestFixtures.js cases added alongside this test —
append_doc_paragraph (the only prior doc-seeding fixture) only supports a
body-level plain paragraph, with no way to reach table cells or list items.

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
