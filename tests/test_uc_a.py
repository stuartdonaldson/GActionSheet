"""
UC-A end-to-end tests: Capture and track a new action.

Setup runs once per module via HTTP fixture invocation (no browser):
  Step 1: uc_a_clear setup+sync — post-first-sync state (AC1 baseline, AC2 before-state).
  Step 2: second sync + uc_a_permutations setup+sync — final state (AC2 after-state,
          permutation coverage).  AC1 rows are untouched by permutations, so comparing
          xlsx_first vs xlsx_final is a stronger idempotency check than one extra sync.

Detection forms tested:
  - PERSON chip at start of list item (uc_a_clear, AC1:)
  - Email address at start of list item (uc_a_clear, AC1:)

Acceptance criteria (from docs/CONTEXT.md §UC-A):
  AC1. After Sync, all floating-action list items appear in the ActionSheet
       with correct assignee, action text, status, and a globalId anchor.
  AC2. A second Sync produces no duplicate rows, preserves named range IDs,
       and leaves the ActionSheet and doc content unchanged (idempotent).
"""

import re
import pytest

from tests.helpers.download import download_xlsx, download_docx
from tests.helpers.fixture_invoke import invoke_fixture
from tests.helpers.sheet_inspect import load_sheet, rows_for_doc
from tests.helpers.doc_inspect import load_doc, floating_actions

# globalId must be "{docFileId}/AI-{N}" — Drive file IDs are base64url, 25–44 chars
_GLOBAL_ID_RE = re.compile(r'^[A-Za-z0-9_-]{25,44}/AI-\d+$')


def _assert_global_id_format(value: str, context: str) -> None:
    assert _GLOBAL_ID_RE.match(value or ""), (
        f"[{context}] globalId / globalId format invalid: {value!r} "
        "(expected '{docId}/AI-{N}')"
    )

_EMAIL_ITEM_EMAIL  = "jane.smith@example.com"
_EMAIL_ITEM_NAME   = "Jane Smith"
_EMAIL_ITEM_ACTION = "AC1: Approve the project proposal"
_EMAIL_ITEM_STATUS = "In Progress"

_CHIP_ITEM_ACTION  = "AC1: Review the project budget"
_CHIP_ITEM_STATUS  = "Open"

_PERM_CHIP_ACTION         = "Perm: Schedule the kickoff"
_PERM_CHIP_STATUS         = "Done"

_PERM_NO_STATUS_EMAIL     = "jane.smith@example.com"
_PERM_NO_STATUS_NAME      = "Jane Smith"
_PERM_NO_STATUS_ACTION    = "Perm: Draft the committee agenda"
_PERM_NO_STATUS_STATUS    = "Open"

_PERM_UNDERSCORE_EMAIL    = "bob_jones@example.com"
_PERM_UNDERSCORE_NAME     = "Bob Jones"
_PERM_UNDERSCORE_ACTION   = "Perm: Review the meeting minutes"


# ---------------------------------------------------------------------------
# Module fixture — HTTP fixture invocation, no browser needed
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def uc_a_state(test_sheet_id, test_doc_id, settings):
    # Setup + first sync (uc_a_clear baseline)
    invoke_fixture("uc_a_clear",     test_doc_id, settings, timeout=300)
    invoke_fixture("sync_document",  test_doc_id, settings, timeout=180)
    xlsx_first = download_xlsx(test_sheet_id)
    docx_first = download_docx(test_doc_id)

    # Second sync (idempotency) + permutations + sync
    invoke_fixture("sync_document",      test_doc_id, settings, timeout=180)
    invoke_fixture("uc_a_permutations",  test_doc_id, settings, timeout=300)
    invoke_fixture("sync_document",      test_doc_id, settings, timeout=180)
    xlsx_final = download_xlsx(test_sheet_id)
    docx_final = download_docx(test_doc_id)

    yield {
        "xlsx_first": xlsx_first,
        "docx_first": docx_first,
        "xlsx_final": xlsx_final,
        "docx_final": docx_final,
        "doc_id": test_doc_id,
    }


# ---------------------------------------------------------------------------
# AC1 — both detection forms appear in the ActionSheet after first Sync
# ---------------------------------------------------------------------------

def test_uc_a_ac1_multi_format_detection(uc_a_state, settings):
    """AC1: After Sync, chip-led and email-led items both appear in ActionSheet."""
    ws = load_sheet(uc_a_state["xlsx_first"], sheet_name="Actions")
    rows = rows_for_doc(ws, uc_a_state["doc_id"])
    ac1_rows = [r for r in rows if "AC1:" in (r.get("Action") or "")]

    assert len(ac1_rows) == 2, (
        f"[uc_a AC1] Expected 2 AC1: rows (chip + email-led), got {len(ac1_rows)}.\n"
        f"  AC1 rows: {ac1_rows}"
    )

    chip_email = settings["testAssigneeEmail"]
    chip_rows  = [r for r in ac1_rows if r.get("Assignee Email") == chip_email]
    email_rows = [r for r in ac1_rows if r.get("Assignee Email") == _EMAIL_ITEM_EMAIL]

    assert len(chip_rows) == 1, (
        f"[uc_a AC1] Chip row not found for {chip_email!r}. AC1 rows: {ac1_rows}"
    )
    assert len(email_rows) == 1, (
        f"[uc_a AC1] Email-led row not found for {_EMAIL_ITEM_EMAIL!r}. AC1 rows: {ac1_rows}"
    )

    chip_row  = chip_rows[0]
    email_row = email_rows[0]

    assert chip_row.get("Status") == _CHIP_ITEM_STATUS, (
        f"[uc_a AC1] Chip row Status: expected {_CHIP_ITEM_STATUS!r}, got {chip_row.get('Status')!r}"
    )
    assert chip_row.get("globalId") not in (None, ""), (
        "[uc_a AC1] Chip row globalId not set — anchor not created"
    )
    _assert_global_id_format(chip_row.get("globalId"), "uc_a AC1 chip")
    assert _CHIP_ITEM_ACTION in (chip_row.get("Action") or ""), (
        f"[uc_a AC1] Chip row Action: expected to contain {_CHIP_ITEM_ACTION!r}, "
        f"got {chip_row.get('Action')!r}"
    )

    assert email_row.get("Status") == _EMAIL_ITEM_STATUS, (
        f"[uc_a AC1] Email row Status: expected {_EMAIL_ITEM_STATUS!r}, "
        f"got {email_row.get('Status')!r}"
    )
    assert email_row.get("globalId") not in (None, ""), (
        "[uc_a AC1] Email row globalId not set — anchor not created"
    )
    _assert_global_id_format(email_row.get("globalId"), "uc_a AC1 email")
    assert email_row.get("Assignee Name") == _EMAIL_ITEM_NAME, (
        f"[uc_a AC1] Email row Assignee Name: expected {_EMAIL_ITEM_NAME!r}, "
        f"got {email_row.get('Assignee Name')!r}"
    )
    assert _EMAIL_ITEM_ACTION in (email_row.get("Action") or ""), (
        f"[uc_a AC1] Email row Action: expected to contain {_EMAIL_ITEM_ACTION!r}, "
        f"got {email_row.get('Action')!r}"
    )


# ---------------------------------------------------------------------------
# AC2 — second Sync is idempotent: no duplicates, no content changes
# ---------------------------------------------------------------------------

def test_uc_a_ac2_idempotent_second_sync(uc_a_state):
    """AC2: Multiple syncs produce no duplicate rows, preserve anchors, leave content unchanged.

    Uses xlsx_first (post-uc_a_clear) as the baseline and xlsx_final (post-second-sync
    and post-permutations) as the after-state.  AC1: rows are not touched by the
    permutations scenario, so this verifies idempotency across multiple syncs.
    """
    ws1    = load_sheet(uc_a_state["xlsx_first"], sheet_name="Actions")
    rows1  = rows_for_doc(ws1, uc_a_state["doc_id"])
    ac1_rows1 = [r for r in rows1 if "AC1:" in (r.get("Action") or "")]

    assert len(ac1_rows1) == 2, (
        f"[uc_a AC2] Expected 2 AC1: rows in first-sync state, got {len(ac1_rows1)}"
    )
    nr_ids_1 = {r["Assignee Email"]: r["globalId"] for r in ac1_rows1}

    ws2    = load_sheet(uc_a_state["xlsx_final"], sheet_name="Actions")
    rows2  = rows_for_doc(ws2, uc_a_state["doc_id"])
    ac1_rows2 = [r for r in rows2 if "AC1:" in (r.get("Action") or "")]

    assert len(ac1_rows2) == len(ac1_rows1), (
        f"[uc_a AC2] AC1: row count changed: {len(ac1_rows1)} → {len(ac1_rows2)}. "
        "Duplicate rows created or rows lost on subsequent syncs."
    )

    nr_ids_2 = {r["Assignee Email"]: r["globalId"] for r in ac1_rows2}
    for email, nrid in nr_ids_1.items():
        assert nr_ids_2.get(email) == nrid, (
            f"[uc_a AC2] globalId changed for {email!r}: "
            f"{nrid!r} → {nr_ids_2.get(email)!r}"
        )

    assert ac1_rows1 == ac1_rows2, (
        "[uc_a AC2] AC1: ActionSheet rows changed on subsequent syncs — not idempotent.\n"
        f"  Before: {ac1_rows1}\n  After:  {ac1_rows2}"
    )

    fa1 = [f for f in floating_actions(load_doc(uc_a_state["docx_first"])) if "AC1:" in f.get("action", "")]
    fa2 = [f for f in floating_actions(load_doc(uc_a_state["docx_final"])) if "AC1:" in f.get("action", "")]
    assert fa1 == fa2, (
        "[uc_a AC2] AC1: floating actions in doc changed on subsequent syncs — not idempotent.\n"
        f"  Before: {fa1}\n  After:  {fa2}"
    )


# ---------------------------------------------------------------------------
# AC1 extended — all detection permutations in one Sync
# ---------------------------------------------------------------------------

def test_uc_a_ac1_permutation_coverage(uc_a_state, settings):
    """AC1 permutations: chip+status-token, email+no-status, underscore-email, plain-text negative."""
    ws   = load_sheet(uc_a_state["xlsx_final"], sheet_name="Actions")
    rows = rows_for_doc(ws, uc_a_state["doc_id"])
    perm_rows = [r for r in rows if "Perm:" in (r.get("Action") or "")]

    assert len(perm_rows) == 3, (
        f"[uc_a permutations] Expected 3 Perm: rows (chip+status, email+no-status, "
        f"underscore-email), got {len(perm_rows)}.\n  Perm rows: {perm_rows}"
    )

    chip_email = settings["testAssigneeEmail"]
    chip_rows  = [r for r in perm_rows if r.get("Assignee Email") == chip_email]
    jane_rows  = [r for r in perm_rows if r.get("Assignee Email") == _PERM_NO_STATUS_EMAIL]
    bob_rows   = [r for r in perm_rows if r.get("Assignee Email") == _PERM_UNDERSCORE_EMAIL]

    assert len(chip_rows) == 1, f"[uc_a permutations] Chip row not found. Perm rows: {perm_rows}"
    assert len(jane_rows) == 1, f"[uc_a permutations] Jane row not found. Perm rows: {perm_rows}"
    assert len(bob_rows)  == 1, f"[uc_a permutations] Bob row not found. Perm rows: {perm_rows}"

    chip_row = chip_rows[0]
    jane_row = jane_rows[0]
    bob_row  = bob_rows[0]

    assert chip_row.get("Status") == _PERM_CHIP_STATUS, (
        f"[uc_a permutations] Chip row Status: expected {_PERM_CHIP_STATUS!r}, "
        f"got {chip_row.get('Status')!r}"
    )
    assert _PERM_CHIP_ACTION in (chip_row.get("Action") or ""), (
        f"[uc_a permutations] Chip row Action: expected to contain {_PERM_CHIP_ACTION!r}, "
        f"got {chip_row.get('Action')!r}"
    )
    assert chip_row.get("globalId") not in (None, ""), (
        "[uc_a permutations] Chip row globalId not set — anchor not created"
    )
    _assert_global_id_format(chip_row.get("globalId"), "uc_a perm chip")

    assert jane_row.get("Status") == _PERM_NO_STATUS_STATUS, (
        f"[uc_a permutations] Jane row Status: expected {_PERM_NO_STATUS_STATUS!r} (default), "
        f"got {jane_row.get('Status')!r}"
    )
    assert jane_row.get("Assignee Name") == _PERM_NO_STATUS_NAME, (
        f"[uc_a permutations] Jane row Assignee Name: expected {_PERM_NO_STATUS_NAME!r}, "
        f"got {jane_row.get('Assignee Name')!r}"
    )
    assert _PERM_NO_STATUS_ACTION in (jane_row.get("Action") or ""), (
        f"[uc_a permutations] Jane row Action: expected to contain {_PERM_NO_STATUS_ACTION!r}, "
        f"got {jane_row.get('Action')!r}"
    )
    assert jane_row.get("globalId") not in (None, ""), (
        "[uc_a permutations] Jane row globalId not set — anchor not created"
    )
    _assert_global_id_format(jane_row.get("globalId"), "uc_a perm jane")

    assert bob_row.get("Assignee Name") == _PERM_UNDERSCORE_NAME, (
        f"[uc_a permutations] Bob row Assignee Name: expected {_PERM_UNDERSCORE_NAME!r}, "
        f"got {bob_row.get('Assignee Name')!r}"
    )
    assert _PERM_UNDERSCORE_ACTION in (bob_row.get("Action") or ""), (
        f"[uc_a permutations] Bob row Action: expected to contain {_PERM_UNDERSCORE_ACTION!r}, "
        f"got {bob_row.get('Action')!r}"
    )
    assert bob_row.get("globalId") not in (None, ""), (
        "[uc_a permutations] Bob row globalId not set — anchor not created"
    )
    _assert_global_id_format(bob_row.get("globalId"), "uc_a perm bob")
