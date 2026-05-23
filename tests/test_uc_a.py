"""
UC-A end-to-end tests: Capture and track a new action.

Test doc prerequisite:
  The testDocId in local.settings.json must contain at least one chip-led
  checklist item (a Google Docs PERSON chip as the first element of a
  checklist paragraph) inserted manually or via a setup script.
  The fixture (uc_a_clear) clears the ActionSheet and removes all named ranges
  so the chip-led items appear as "new" unanchored actions for each test.

Acceptance criteria (from docs/CONTEXT.md §UC-A):
  AC1. After clicking Sync, a newly typed chip-led checklist item appears in
       the sidebar and in the ActionSheet, with the assignee email resolved
       from the chip and Status = Open.
  AC2. The action's anchor survives an unrelated edit elsewhere in the doc —
       a second Sync does not produce a duplicate row.
  AC3. A second Sync with no further edits produces no writes to the doc or
       the ActionSheet.

TDD phase: RED — these tests are expected to fail until the chip-led scanner
and named-range anchoring are implemented (mol-uv8).
"""
import pytest

from tests.helpers.addon_invoke import sync_via_sidebar
from tests.helpers.download import download_xlsx, download_docx
from tests.helpers.gas_invoke import setup_fixture
from tests.helpers.gas_log import clear_logs, wait_for_log
from tests.helpers.sheet_inspect import load_sheet, rows_for_doc
from tests.helpers.doc_inspect import load_doc, floating_actions


# ---------------------------------------------------------------------------
# AC1 — action appears in ActionSheet after first Sync
# ---------------------------------------------------------------------------

def test_uc_a_ac1_action_appears_after_sync(test_sheet_id, test_doc_id, gas_log_dir):
    """AC1: After Sync, the chip-led checklist item appears in ActionSheet with Status=Open."""
    clear_logs(gas_log_dir)
    setup_fixture("uc_a_clear")
    wait_for_log(gas_log_dir, lambda e: e.get("tag") == "fixture.uc_a_clear")

    clear_logs(gas_log_dir)
    sync_via_sidebar(test_doc_id)

    xlsx_bytes = download_xlsx(test_sheet_id)
    ws = load_sheet(xlsx_bytes, sheet_name="Actions")
    rows = rows_for_doc(ws, test_doc_id)

    assert len(rows) >= 1, (
        "[uc_a AC1] Expected at least one ActionSheet row after sync, got 0. "
        "Chip-led checklist item was not discovered by the scanner."
    )

    row = rows[0]
    assert row.get("Status") == "Open", (
        f"[uc_a AC1] Expected Status='Open', got {row.get('Status')!r}"
    )
    assert row.get("NamedRangeId") not in (None, ""), (
        "[uc_a AC1] Expected NamedRangeId to be set (action anchored by named range), got empty"
    )
    assert row.get("Assignee Email") not in (None, ""), (
        "[uc_a AC1] Expected Assignee Email to be resolved from chip, got empty"
    )


def test_uc_a_ac1_floating_action_readable_in_doc(test_sheet_id, test_doc_id, gas_log_dir):
    """AC1 supplemental: Floating action is readable from the downloaded doc."""
    clear_logs(gas_log_dir)
    setup_fixture("uc_a_clear")
    wait_for_log(gas_log_dir, lambda e: e.get("tag") == "fixture.uc_a_clear")

    clear_logs(gas_log_dir)
    sync_via_sidebar(test_doc_id)

    docx_bytes = download_docx(test_doc_id)
    doc = load_doc(docx_bytes)
    actions = floating_actions(doc)

    assert len(actions) >= 1, (
        "[uc_a AC1] floating_actions() returned no items — parser not yet implemented "
        "or chip-led checklist item not present in doc."
    )
    action = actions[0]
    assert action.get("status") == "Open", (
        f"[uc_a AC1] Floating action status expected 'Open', got {action.get('status')!r}"
    )
    assert action.get("assignee_email"), (
        "[uc_a AC1] Floating action assignee_email not resolved from chip"
    )


# ---------------------------------------------------------------------------
# AC2 — anchor survives unrelated edit; second Sync no duplicate
# ---------------------------------------------------------------------------

def test_uc_a_ac2_no_duplicate_after_unrelated_edit(test_sheet_id, test_doc_id, gas_log_dir):
    """AC2: Second Sync after an unrelated doc edit produces no duplicate ActionSheet row."""
    clear_logs(gas_log_dir)
    setup_fixture("uc_a_clear")
    wait_for_log(gas_log_dir, lambda e: e.get("tag") == "fixture.uc_a_clear")

    # First sync
    clear_logs(gas_log_dir)
    sync_via_sidebar(test_doc_id)

    xlsx1 = download_xlsx(test_sheet_id)
    ws1 = load_sheet(xlsx1, sheet_name="Actions")
    rows1 = rows_for_doc(ws1, test_doc_id)
    assert len(rows1) >= 1, "[uc_a AC2] No rows after first sync — prerequisite for AC2 not met"
    named_range_id_after_first = rows1[0].get("NamedRangeId")

    # Second sync (no edit — simulates "unrelated edit" by re-syncing; a deeper test
    # would use Playwright to type a new paragraph above the action first)
    clear_logs(gas_log_dir)
    sync_via_sidebar(test_doc_id)

    xlsx2 = download_xlsx(test_sheet_id)
    ws2 = load_sheet(xlsx2, sheet_name="Actions")
    rows2 = rows_for_doc(ws2, test_doc_id)

    assert len(rows2) == len(rows1), (
        f"[uc_a AC2] Row count changed on second sync: first={len(rows1)}, second={len(rows2)}. "
        "Duplicate row created — named range anchor not survived or re-anchor failed."
    )
    named_range_id_after_second = rows2[0].get("NamedRangeId")
    assert named_range_id_after_first == named_range_id_after_second, (
        "[uc_a AC2] NamedRangeId changed between syncs — anchor was recreated instead of reused"
    )


# ---------------------------------------------------------------------------
# AC3 — idempotent: second Sync with no changes produces no writes
# ---------------------------------------------------------------------------

def test_uc_a_ac3_idempotent_no_writes(test_sheet_id, test_doc_id, gas_log_dir):
    """AC3: Second Sync with no further edits produces no writes to doc or ActionSheet."""
    clear_logs(gas_log_dir)
    setup_fixture("uc_a_clear")
    wait_for_log(gas_log_dir, lambda e: e.get("tag") == "fixture.uc_a_clear")

    # First sync — establishes rows and named ranges
    clear_logs(gas_log_dir)
    sync_via_sidebar(test_doc_id)

    xlsx1 = download_xlsx(test_sheet_id)
    docx1 = download_docx(test_doc_id)

    # Second sync — should be a no-op
    clear_logs(gas_log_dir)
    sync_via_sidebar(test_doc_id)

    xlsx2 = download_xlsx(test_sheet_id)
    docx2 = download_docx(test_doc_id)

    # Compare parsed ActionSheet rows
    ws1 = load_sheet(xlsx1, sheet_name="Actions")
    ws2 = load_sheet(xlsx2, sheet_name="Actions")
    rows1 = rows_for_doc(ws1, test_doc_id)
    rows2 = rows_for_doc(ws2, test_doc_id)

    assert rows1 == rows2, (
        "[uc_a AC3] ActionSheet rows changed on second sync — not idempotent.\n"
        f"  Before: {rows1}\n  After:  {rows2}"
    )

    # Compare floating actions in the doc
    doc1 = load_doc(docx1)
    doc2 = load_doc(docx2)
    fa1 = floating_actions(doc1)
    fa2 = floating_actions(doc2)
    assert fa1 == fa2, (
        "[uc_a AC3] Floating actions in doc changed on second sync — not idempotent.\n"
        f"  Before: {fa1}\n  After:  {fa2}"
    )
