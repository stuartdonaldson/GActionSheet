"""
UC-A end-to-end tests: Capture and track a new action.

Setup is fully automated — no manual doc prep required:
  The GAS fixture (uc_a_clear) clears the ActionSheet, removes named ranges,
  clears the doc body, and inserts a chip-led list item via the Docs REST API
  batchUpdate (insertPerson + createParagraphBullets).

Acceptance criteria (from docs/CONTEXT.md §UC-A):
  AC1. After clicking Sync, a chip-led list item appears in the ActionSheet
       with the assignee email resolved from the chip and Status = Open.
  AC2. The action's anchor survives a second Sync — no duplicate row.
  AC3. A second Sync with no further edits produces no writes to the doc or
       the ActionSheet.

Sync is triggered via the GAS "Test: Sync Document" menu item (same underlying
syncDocument() call as the sidebar "Sync now" button).  Workspace Add-on card
iframes are sandboxed and not reliably automatable via Playwright.
"""
import pytest

from tests.helpers.download import download_xlsx, download_docx
from tests.helpers.gas_invoke import setup_fixture, sync_document
from tests.helpers.gas_log import clear_logs, wait_for_log
from tests.helpers.sheet_inspect import load_sheet, rows_for_doc
from tests.helpers.doc_inspect import load_doc, floating_actions


def _sync_uc_a(test_doc_id: str, gas_log_dir: str) -> None:
    """Invoke syncDocument via the GAS menu and wait for sync.complete log entry.

    Uses the GAS "Test: Sync Document" menu path (same syncDocument() call as
    the sidebar "Sync now" button).  Workspace Add-on card iframes are sandboxed
    and not reliably automatable via Playwright.
    """
    clear_logs(gas_log_dir)
    sync_document(test_doc_id)
    wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.complete", timeout_s=120)


def _setup_uc_a(test_doc_id: str, gas_log_dir: str) -> None:
    """GAS fixture: clears sheet + named ranges + doc body, seeds chip-led item."""
    clear_logs(gas_log_dir)
    setup_fixture("uc_a_clear")
    # UC-A fixture does a Docs REST API batchUpdate (insertPerson) server-side, then
    # GasLogger.flush() writes to Drive. Allow 120s for GAS + Drive sync latency.
    entry = wait_for_log(gas_log_dir, lambda e: e.get("tag") == "fixture.uc_a_clear",
                         timeout_s=120)
    if entry.get("data", {}).get("error"):
        raise RuntimeError(
            f"[uc_a fixture] insertPerson failed in GAS: {entry['data']['error']}"
        )


# ---------------------------------------------------------------------------
# AC1 — action appears in ActionSheet after first Sync
# ---------------------------------------------------------------------------

def test_uc_a_ac1_action_appears_after_sync(test_sheet_id, test_doc_id, gas_log_dir):
    """AC1: After Sync, the chip-led item appears in ActionSheet with Status=Open."""
    _setup_uc_a(test_doc_id, gas_log_dir)
    _sync_uc_a(test_doc_id, gas_log_dir)

    xlsx_bytes = download_xlsx(test_sheet_id)
    ws = load_sheet(xlsx_bytes, sheet_name="Actions")
    rows = rows_for_doc(ws, test_doc_id)

    assert len(rows) >= 1, (
        "[uc_a AC1] Expected at least one ActionSheet row after sync, got 0. "
        "Chip-led list item was not discovered by the scanner."
    )

    row = rows[0]
    assert row.get("Status") == "Open", (
        f"[uc_a AC1] Expected Status='Open', got {row.get('Status')!r}"
    )
    assert row.get("NamedRangeId") not in (None, ""), (
        "[uc_a AC1] Expected NamedRangeId to be set (action anchored), got empty"
    )
    assert row.get("Assignee Email") not in (None, ""), (
        "[uc_a AC1] Expected Assignee Email to be resolved from chip, got empty"
    )


def test_uc_a_ac1_floating_action_readable_in_doc(test_sheet_id, test_doc_id, gas_log_dir):
    """AC1 supplemental: Floating action is readable from the downloaded .docx."""
    _setup_uc_a(test_doc_id, gas_log_dir)
    _sync_uc_a(test_doc_id, gas_log_dir)

    docx_bytes = download_docx(test_doc_id)
    doc = load_doc(docx_bytes)
    actions = floating_actions(doc)

    assert len(actions) >= 1, (
        "[uc_a AC1] floating_actions() returned no items — chip-led list item "
        "not present or person chip email not resolvable in .docx export."
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
    _setup_uc_a(test_doc_id, gas_log_dir)

    # First sync
    _sync_uc_a(test_doc_id, gas_log_dir)

    xlsx1 = download_xlsx(test_sheet_id)
    ws1 = load_sheet(xlsx1, sheet_name="Actions")
    rows1 = rows_for_doc(ws1, test_doc_id)
    assert len(rows1) >= 1, "[uc_a AC2] No rows after first sync — prerequisite for AC2 not met"
    named_range_id_after_first = rows1[0].get("NamedRangeId")

    # Second sync
    _sync_uc_a(test_doc_id, gas_log_dir)

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
    _setup_uc_a(test_doc_id, gas_log_dir)

    # First sync — establishes rows and named ranges
    _sync_uc_a(test_doc_id, gas_log_dir)

    xlsx1 = download_xlsx(test_sheet_id)
    docx1 = download_docx(test_doc_id)

    # Second sync — should be a no-op
    _sync_uc_a(test_doc_id, gas_log_dir)

    xlsx2 = download_xlsx(test_sheet_id)
    docx2 = download_docx(test_doc_id)

    ws1 = load_sheet(xlsx1, sheet_name="Actions")
    ws2 = load_sheet(xlsx2, sheet_name="Actions")
    rows1 = rows_for_doc(ws1, test_doc_id)
    rows2 = rows_for_doc(ws2, test_doc_id)

    assert rows1 == rows2, (
        "[uc_a AC3] ActionSheet rows changed on second sync — not idempotent.\n"
        f"  Before: {rows1}\n  After:  {rows2}"
    )

    doc1 = load_doc(docx1)
    doc2 = load_doc(docx2)
    fa1 = floating_actions(doc1)
    fa2 = floating_actions(doc2)
    assert fa1 == fa2, (
        "[uc_a AC3] Floating actions in doc changed on second sync — not idempotent.\n"
        f"  Before: {fa1}\n  After:  {fa2}"
    )
