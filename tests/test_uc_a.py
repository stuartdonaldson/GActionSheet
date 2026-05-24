"""
UC-A end-to-end tests: Capture and track a new action.

Setup is fully automated — no manual doc prep required:
  The GAS fixture (uc_a_clear) clears the ActionSheet, removes named ranges,
  clears the doc body, and inserts a chip-led list item via the Docs REST API
  batchUpdate (insertPerson + createParagraphBullets).

Acceptance criteria (from docs/CONTEXT.md §UC-A):
  AC1. After Sync, a chip-led list item appears in the ActionSheet
       with the assignee email resolved from the chip and Status = Open.
  AC2. The action's anchor survives a second Sync — no duplicate row.
  AC3. A second Sync with no further edits produces no writes to the doc or
       the ActionSheet.

Sync is triggered via the GAS "Test: Sync Document" menu item (same underlying
syncDocument() call as the sidebar "Sync now" button).  Workspace Add-on card
iframes are sandboxed and not reliably automatable via Playwright.

Each test uses setup_and_sync to combine fixture setup and the first sync into
a single browser session, reducing Playwright overhead.
"""

from tests.helpers.download import download_xlsx, download_docx
from tests.helpers.gas_invoke import setup_and_sync, sync_document
from tests.helpers.gas_log import clear_logs, wait_for_log
from tests.helpers.sheet_inspect import load_sheet, rows_for_doc
from tests.helpers.doc_inspect import load_doc, floating_actions


def _first_sync(gas_log_dir: str) -> None:
    """Run uc_a_clear fixture + first sync in one GAS/browser invocation."""
    clear_logs(gas_log_dir)
    setup_and_sync("uc_a_clear")
    entry = wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.complete",
                         timeout_s=180)
    # If the fixture step failed the error is in the fixture.uc_a_clear log entry;
    # sync would still complete (with 0 rows) so check explicitly.
    import os, json
    for fname in sorted(os.listdir(gas_log_dir)):
        if not fname.endswith(".log"):
            continue
        with open(os.path.join(gas_log_dir, fname)) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if e.get("tag") == "fixture.uc_a_clear" and e.get("data", {}).get("error"):
                    raise RuntimeError(
                        f"[uc_a fixture] insertPerson failed in GAS: {e['data']['error']}"
                    )


def _second_sync(test_doc_id: str, gas_log_dir: str) -> None:
    """Invoke a second sync via GAS menu and wait for sync.complete."""
    clear_logs(gas_log_dir)
    sync_document(test_doc_id)
    wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.complete", timeout_s=120)


# ---------------------------------------------------------------------------
# AC1 — action appears in ActionSheet after first Sync
# ---------------------------------------------------------------------------

def test_uc_a_ac1_action_appears_after_sync(test_sheet_id, test_doc_id, gas_log_dir):
    """AC1: After Sync, the chip-led item appears in ActionSheet with Status=Open."""
    _first_sync(gas_log_dir)

    xlsx_bytes = download_xlsx(test_sheet_id)
    ws = load_sheet(xlsx_bytes, sheet_name="Actions")
    rows = rows_for_doc(ws, test_doc_id)

    assert len(rows) >= 1, (
        "[uc_a AC1] Expected at least one ActionSheet row after sync, got 0. "
        "Chip-led list item was not discovered by the scanner."
    )

    row = rows[0]
    assert row.get("Status") == "Open", (
        "[uc_a AC1] Expected Status='Open', got {!r}".format(row.get("Status"))
    )
    assert row.get("NamedRangeId") not in (None, ""), (
        "[uc_a AC1] Expected NamedRangeId to be set (action anchored), got empty"
    )
    assert row.get("Assignee Email") not in (None, ""), (
        "[uc_a AC1] Expected Assignee Email to be resolved from chip, got empty"
    )


# ---------------------------------------------------------------------------
# AC2 — anchor survives second Sync — no duplicate row
# ---------------------------------------------------------------------------

def test_uc_a_ac2_no_duplicate_after_second_sync(test_sheet_id, test_doc_id, gas_log_dir):
    """AC2: Second Sync produces no duplicate ActionSheet row."""
    _first_sync(gas_log_dir)

    xlsx1 = download_xlsx(test_sheet_id)
    ws1 = load_sheet(xlsx1, sheet_name="Actions")
    rows1 = rows_for_doc(ws1, test_doc_id)
    assert len(rows1) >= 1, "[uc_a AC2] No rows after first sync — prerequisite for AC2 not met"
    named_range_id_after_first = rows1[0].get("NamedRangeId")

    _second_sync(test_doc_id, gas_log_dir)

    xlsx2 = download_xlsx(test_sheet_id)
    ws2 = load_sheet(xlsx2, sheet_name="Actions")
    rows2 = rows_for_doc(ws2, test_doc_id)

    assert len(rows2) == len(rows1), (
        "[uc_a AC2] Row count changed on second sync: first={}, second={}. "
        "Duplicate row created — named range anchor not survived or re-anchor failed.".format(
            len(rows1), len(rows2))
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
    _first_sync(gas_log_dir)

    xlsx1 = download_xlsx(test_sheet_id)
    docx1 = download_docx(test_doc_id)

    _second_sync(test_doc_id, gas_log_dir)

    xlsx2 = download_xlsx(test_sheet_id)
    docx2 = download_docx(test_doc_id)

    ws1 = load_sheet(xlsx1, sheet_name="Actions")
    ws2 = load_sheet(xlsx2, sheet_name="Actions")
    rows1 = rows_for_doc(ws1, test_doc_id)
    rows2 = rows_for_doc(ws2, test_doc_id)

    assert rows1 == rows2, (
        "[uc_a AC3] ActionSheet rows changed on second sync — not idempotent.\n"
        "  Before: {}\n  After:  {}".format(rows1, rows2)
    )

    doc1 = load_doc(docx1)
    doc2 = load_doc(docx2)
    fa1 = floating_actions(doc1)
    fa2 = floating_actions(doc2)
    assert fa1 == fa2, (
        "[uc_a AC3] Floating actions in doc changed on second sync — not idempotent.\n"
        "  Before: {}\n  After:  {}".format(fa1, fa2)
    )
