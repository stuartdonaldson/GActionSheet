"""
UC-A end-to-end tests: Capture and track a new action.

Setup is fully automated — no manual doc prep required:
  The GAS fixture (uc_a_clear) clears the ActionSheet, removes named ranges,
  clears the doc body, inserts a chip-led list item via the Docs REST API
  batchUpdate, then appends an email-led list item via DocumentApp.

Detection forms tested (both in a single doc, one Sync):
  - PERSON chip at start of list item
  - Email address at start of list item (email-at-start)

Acceptance criteria (from docs/CONTEXT.md §UC-A):
  AC1. After Sync, all floating-action list items appear in the ActionSheet
       with correct assignee, action text, status, and a NamedRangeId anchor.
  AC2. A second Sync produces no duplicate rows, preserves named range IDs,
       and leaves the ActionSheet and doc content unchanged (idempotent).

Sync is triggered via the GAS "Test: Sync Document" menu item (same underlying
syncDocument() call as the sidebar "Sync now" button).
"""

import pathlib
import time

from tests.helpers.download import download_xlsx, download_docx
from tests.helpers.gas_invoke import setup_and_sync, sync_document
from tests.helpers.gas_log import clear_logs, wait_for_log
from tests.helpers.sheet_inspect import load_sheet, rows_for_doc
from tests.helpers.doc_inspect import load_doc, floating_actions

def _clear_logs_stable(log_dir: str, timeout_s: float = 15.0) -> None:
    """Clear logs and re-delete any files that reappear from Drive re-sync.

    invoke_gas.js exits 1 second after clicking — GAS runs async.  The final
    GasLogger.flush() from the previous test can still be syncing from Drive to
    the local directory when this test's clear_logs runs.  Keep deleting until
    the directory is empty so wait_for_log only sees fresh entries.
    """
    clear_logs(log_dir)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        remaining = list(pathlib.Path(log_dir).glob("*.log"))
        if not remaining:
            return
        for f in remaining:
            f.unlink(missing_ok=True)
        time.sleep(0.5)


_EMAIL_ITEM_EMAIL  = "jane.smith@example.com"
_EMAIL_ITEM_NAME   = "Jane Smith"
_EMAIL_ITEM_ACTION = "Approve the budget proposal"
_EMAIL_ITEM_STATUS = "In Progress"

_CHIP_ITEM_ACTION  = "Review the budget report"
_CHIP_ITEM_STATUS  = "Open"


def _first_sync(gas_log_dir: str) -> None:
    """Run uc_a_clear fixture + first sync in one GAS/browser invocation."""
    _clear_logs_stable(gas_log_dir)
    setup_and_sync("uc_a_clear")
    wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.complete",
                 timeout_s=180)
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
                        f"[uc_a fixture] step failed in GAS: {e['data']['error']}"
                    )


def _second_sync(test_doc_id: str, gas_log_dir: str) -> None:
    """Invoke a second sync via GAS menu and wait for sync.complete."""
    _clear_logs_stable(gas_log_dir)
    sync_document(test_doc_id)
    wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.complete", timeout_s=120)


# ---------------------------------------------------------------------------
# AC1 — both detection forms appear in the ActionSheet after first Sync
# ---------------------------------------------------------------------------

def test_uc_a_ac1_multi_format_detection(test_sheet_id, test_doc_id, gas_log_dir, settings):
    """AC1: After Sync, chip-led and email-led items both appear in ActionSheet."""
    _first_sync(gas_log_dir)

    xlsx_bytes = download_xlsx(test_sheet_id)
    ws = load_sheet(xlsx_bytes, sheet_name="Actions")
    rows = rows_for_doc(ws, test_doc_id)

    assert len(rows) == 2, (
        f"[uc_a AC1] Expected 2 rows (chip + email-led), got {len(rows)}.\n"
        f"  Rows: {rows}"
    )

    chip_email = settings["testAssigneeEmail"]
    chip_rows  = [r for r in rows if r.get("Assignee Email") == chip_email]
    email_rows = [r for r in rows if r.get("Assignee Email") == _EMAIL_ITEM_EMAIL]

    assert len(chip_rows) == 1, (
        f"[uc_a AC1] Chip row not found for {chip_email!r}. Rows: {rows}"
    )
    assert len(email_rows) == 1, (
        f"[uc_a AC1] Email-led row not found for {_EMAIL_ITEM_EMAIL!r}. Rows: {rows}"
    )

    chip_row  = chip_rows[0]
    email_row = email_rows[0]

    # Chip row
    assert chip_row.get("Status") == _CHIP_ITEM_STATUS, (
        f"[uc_a AC1] Chip row Status: expected {_CHIP_ITEM_STATUS!r}, got {chip_row.get('Status')!r}"
    )
    assert chip_row.get("NamedRangeId") not in (None, ""), (
        "[uc_a AC1] Chip row NamedRangeId not set — anchor not created"
    )
    assert _CHIP_ITEM_ACTION in (chip_row.get("Action") or ""), (
        f"[uc_a AC1] Chip row Action: expected to contain {_CHIP_ITEM_ACTION!r}, "
        f"got {chip_row.get('Action')!r}"
    )

    # Email-led row
    assert email_row.get("Status") == _EMAIL_ITEM_STATUS, (
        f"[uc_a AC1] Email row Status: expected {_EMAIL_ITEM_STATUS!r}, "
        f"got {email_row.get('Status')!r}"
    )
    assert email_row.get("NamedRangeId") not in (None, ""), (
        "[uc_a AC1] Email row NamedRangeId not set — anchor not created"
    )
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

def test_uc_a_ac2_idempotent_second_sync(test_sheet_id, test_doc_id, gas_log_dir):
    """AC2: Second Sync produces no duplicate rows, preserves anchors, leaves content unchanged."""
    _first_sync(gas_log_dir)

    xlsx1  = download_xlsx(test_sheet_id)
    docx1  = download_docx(test_doc_id)
    ws1    = load_sheet(xlsx1, sheet_name="Actions")
    rows1  = rows_for_doc(ws1, test_doc_id)

    assert len(rows1) == 2, (
        f"[uc_a AC2] Expected 2 rows after first sync, got {len(rows1)} — "
        "prerequisite for AC2 not met"
    )

    nr_ids_1 = {r["Assignee Email"]: r["NamedRangeId"] for r in rows1}

    _second_sync(test_doc_id, gas_log_dir)

    xlsx2  = download_xlsx(test_sheet_id)
    docx2  = download_docx(test_doc_id)
    ws2    = load_sheet(xlsx2, sheet_name="Actions")
    rows2  = rows_for_doc(ws2, test_doc_id)

    # No duplicates
    assert len(rows2) == len(rows1), (
        f"[uc_a AC2] Row count changed: {len(rows1)} → {len(rows2)}. "
        "Duplicate rows created or rows lost on second sync."
    )

    # Named range IDs preserved for each row
    nr_ids_2 = {r["Assignee Email"]: r["NamedRangeId"] for r in rows2}
    for email, nrid in nr_ids_1.items():
        assert nr_ids_2.get(email) == nrid, (
            f"[uc_a AC2] NamedRangeId changed for {email!r}: "
            f"{nrid!r} → {nr_ids_2.get(email)!r}"
        )

    # Sheet content unchanged
    assert rows1 == rows2, (
        "[uc_a AC2] ActionSheet rows changed on second sync — not idempotent.\n"
        f"  Before: {rows1}\n  After:  {rows2}"
    )

    # Doc floating actions unchanged
    fa1 = floating_actions(load_doc(docx1))
    fa2 = floating_actions(load_doc(docx2))
    assert fa1 == fa2, (
        "[uc_a AC2] Floating actions in doc changed on second sync — not idempotent.\n"
        f"  Before: {fa1}\n  After:  {fa2}"
    )
