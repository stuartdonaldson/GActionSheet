"""
UC sidebar mutation tests: status update and delete from the sidebar.

Sidebar mutations are complete round-trips — each GAS function updates both
the floating action in the doc and the ActionSheet row without requiring a
separate Sync now step.

Setup:
  - uc_a_clear: inserts a chip-led action and an email-led action, clears prior state.
  - sync_document: anchors both actions and writes ActionSheet rows (AC1 baseline).

Mutations tested:
  - sidebar_set_status: changes the chip-led action from "Open" → "Done";
    expects both the floating action paragraph and the ActionSheet row to
    reflect "Done" immediately (no further sync required).
  - sidebar_delete_action: removes the email-led action; expects it absent
    from both floating actions and ActionSheet rows immediately.

Acceptance criteria (from GTaskSheet-cw5.6):
  AC1. sidebar_set_status updates the floating action paragraph status token
       AND the ActionSheet row Status column; no additional sync required.
  AC2. sidebar_delete_action removes the floating action from the doc AND
       removes the ActionSheet row; no additional sync required.
"""

import pytest

from tests.helpers.download import download_xlsx, download_docx
from tests.helpers.fixture_invoke import invoke_fixture
from tests.helpers.sheet_inspect import load_sheet, rows_for_doc
from tests.helpers.doc_inspect import load_doc, floating_actions

# ---------------------------------------------------------------------------
# Constants — must match uc_a_clear fixture output
# ---------------------------------------------------------------------------

_CHIP_ACTION    = "AC1: Review the project budget"
_CHIP_STATUS_ORIG = "Open"
_CHIP_STATUS_NEW  = "Done"       # sidebar_set_status fixture targets this action

_EMAIL_ACTION   = "AC1: Approve the project proposal"
_EMAIL_EMAIL    = "jane.smith@example.com"


# ---------------------------------------------------------------------------
# Module fixture — setup once, two mutations in sequence
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def sidebar_mutation_state(test_sheet_id, test_doc_id, settings):
    """Set up AC1 baseline, then run both sidebar mutations.

    sidebar_set_status and sidebar_delete_action are expected to complete the
    full round-trip (doc + ActionSheet) without a separate sync_document call.
    """
    # AC1 baseline
    invoke_fixture("uc_a_clear",    test_doc_id, settings, timeout=300)
    invoke_fixture("sync_document", test_doc_id, settings, timeout=180)

    # Mutation 1 — set status on chip action
    invoke_fixture("sidebar_set_status",    test_doc_id, settings, timeout=60)
    xlsx_after_set  = download_xlsx(test_sheet_id)
    docx_after_set  = download_docx(test_doc_id)

    # Mutation 2 — delete the email-led action
    invoke_fixture("sidebar_delete_action", test_doc_id, settings, timeout=60)
    xlsx_after_del  = download_xlsx(test_sheet_id)
    docx_after_del  = download_docx(test_doc_id)

    yield {
        "xlsx_after_set":  xlsx_after_set,
        "docx_after_set":  docx_after_set,
        "xlsx_after_del":  xlsx_after_del,
        "docx_after_del":  docx_after_del,
        "doc_id":          test_doc_id,
    }


# ---------------------------------------------------------------------------
# AC1 — set status
# ---------------------------------------------------------------------------

def test_sidebar_set_status_updates_doc(sidebar_mutation_state, settings):
    """AC1a: floating action paragraph reflects the new status immediately."""
    doc = load_doc(sidebar_mutation_state["docx_after_set"])
    fas = floating_actions(doc)

    chip_email = settings["testAssigneeEmail"]
    target = [
        fa for fa in fas
        if fa.get("action") == _CHIP_ACTION
        and fa.get("assignee_email") == chip_email
    ]

    assert len(target) == 1, (
        f"[sidebar set_status] Expected exactly 1 floating action with text "
        f"{_CHIP_ACTION!r}, found {len(target)}. All FAs: {fas}"
    )
    assert target[0].get("status") == _CHIP_STATUS_NEW, (
        f"[sidebar set_status] Doc floating action status: "
        f"expected {_CHIP_STATUS_NEW!r}, got {target[0].get('status')!r}"
    )


def test_sidebar_set_status_updates_sheet(sidebar_mutation_state, settings):
    """AC1b: ActionSheet row reflects the new status immediately."""
    ws   = load_sheet(sidebar_mutation_state["xlsx_after_set"], sheet_name="Actions")
    rows = rows_for_doc(ws, sidebar_mutation_state["doc_id"])

    chip_email  = settings["testAssigneeEmail"]
    target = [
        r for r in rows
        if r.get("Action") == _CHIP_ACTION
        and r.get("Assignee Email") == chip_email
    ]

    assert len(target) == 1, (
        f"[sidebar set_status] Expected 1 ActionSheet row for {_CHIP_ACTION!r}, "
        f"found {len(target)}. Rows: {rows}"
    )
    assert target[0].get("Status") == _CHIP_STATUS_NEW, (
        f"[sidebar set_status] ActionSheet Status: "
        f"expected {_CHIP_STATUS_NEW!r}, got {target[0].get('Status')!r}"
    )


# ---------------------------------------------------------------------------
# AC2 — delete action
# ---------------------------------------------------------------------------

def test_sidebar_delete_action_removes_from_doc(sidebar_mutation_state):
    """AC2a: deleted floating action is absent from the doc immediately."""
    doc = load_doc(sidebar_mutation_state["docx_after_del"])
    fas = floating_actions(doc)

    remaining = [
        fa for fa in fas
        if fa.get("action") == _EMAIL_ACTION
        and fa.get("assignee_email") == _EMAIL_EMAIL
    ]

    assert len(remaining) == 0, (
        f"[sidebar delete] Email-led action {_EMAIL_ACTION!r} still present in "
        f"floating actions after delete. FAs: {fas}"
    )


def test_sidebar_delete_action_removes_from_sheet(sidebar_mutation_state):
    """AC2b: deleted action's ActionSheet row is absent immediately."""
    ws   = load_sheet(sidebar_mutation_state["xlsx_after_del"], sheet_name="Actions")
    rows = rows_for_doc(ws, sidebar_mutation_state["doc_id"])

    remaining = [
        r for r in rows
        if r.get("Action") == _EMAIL_ACTION
        and r.get("Assignee Email") == _EMAIL_EMAIL
    ]

    assert len(remaining) == 0, (
        f"[sidebar delete] ActionSheet row for {_EMAIL_ACTION!r} / "
        f"{_EMAIL_EMAIL!r} still present after delete. Rows: {rows}"
    )


def test_sidebar_delete_preserves_other_actions(sidebar_mutation_state, settings):
    """AC2c: other actions are not affected by the delete."""
    ws   = load_sheet(sidebar_mutation_state["xlsx_after_del"], sheet_name="Actions")
    rows = rows_for_doc(ws, sidebar_mutation_state["doc_id"])

    chip_email = settings["testAssigneeEmail"]
    chip_rows  = [
        r for r in rows
        if r.get("Action") == _CHIP_ACTION
        and r.get("Assignee Email") == chip_email
    ]

    assert len(chip_rows) == 1, (
        f"[sidebar delete] Chip action {_CHIP_ACTION!r} should survive the delete "
        f"of the email-led action. Found {len(chip_rows)} rows. All rows: {rows}"
    )
