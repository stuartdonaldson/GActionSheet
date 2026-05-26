"""
UC-A end-to-end tests: Capture and track a new action.

Setup is fully automated — no manual doc prep required:
  The GAS fixture (uc_a_clear) appends scenario-prefixed action items to the
  clone doc via the Docs REST API, then syncs.  Items accumulate across scenarios
  within a session; assertions filter by action text prefix (AC1:, Perm:) so
  earlier scenarios' rows are invisible to each test.

Detection forms tested:
  - PERSON chip at start of list item (uc_a_clear, AC1:)
  - Email address at start of list item (uc_a_clear, AC1:)

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
_EMAIL_ITEM_ACTION = "AC1: Approve the project proposal"
_EMAIL_ITEM_STATUS = "In Progress"

_CHIP_ITEM_ACTION  = "AC1: Review the project budget"
_CHIP_ITEM_STATUS  = "Open"

# Permutation coverage constants (test_uc_a_ac1_permutation_coverage)
_PERM_CHIP_ACTION         = "Perm: Schedule the kickoff"
_PERM_CHIP_STATUS         = "Done"

_PERM_NO_STATUS_EMAIL     = "jane.smith@example.com"
_PERM_NO_STATUS_NAME      = "Jane Smith"
_PERM_NO_STATUS_ACTION    = "Perm: Draft the committee agenda"
_PERM_NO_STATUS_STATUS    = "Open"

_PERM_UNDERSCORE_EMAIL    = "bob_jones@example.com"
_PERM_UNDERSCORE_NAME     = "Bob Jones"
_PERM_UNDERSCORE_ACTION   = "Perm: Review the meeting minutes"


def _run_setup_and_sync(scenario: str, error_tag: str, gas_log_dir: str,
                        test_doc_id: str | None = None,
                        timeout_s: float = 180.0) -> None:
    """Run a named fixture scenario + sync; raise if GAS reports a fixture error."""
    import os, json
    _clear_logs_stable(gas_log_dir)
    setup_and_sync(scenario)
    # Filter on docId to avoid matching stale sync.complete{scenario} entries
    # that arrive late from Drive after the previous test's setupAndSync flush.
    def _match(e: dict) -> bool:
        if e.get("tag") != "sync.complete":
            return False
        if test_doc_id is None:
            return True
        return e.get("data", {}).get("docId") == test_doc_id
    wait_for_log(gas_log_dir, _match, timeout_s=timeout_s)
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
                if e.get("tag") == error_tag and e.get("data", {}).get("error"):
                    raise RuntimeError(
                        f"[{error_tag}] step failed in GAS: {e['data']['error']}"
                    )


def _first_sync(gas_log_dir: str, test_doc_id: str | None = None) -> None:
    """Run uc_a_clear fixture + first sync in one GAS/browser invocation."""
    _run_setup_and_sync("uc_a_clear", "fixture.uc_a_clear", gas_log_dir, test_doc_id=test_doc_id)


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
    _first_sync(gas_log_dir, test_doc_id)

    xlsx_bytes = download_xlsx(test_sheet_id)
    ws = load_sheet(xlsx_bytes, sheet_name="Actions")
    rows = rows_for_doc(ws, test_doc_id)
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
    """AC2: Second Sync produces no duplicate rows, preserves anchors, leaves content unchanged.

    Relies on test_uc_a_ac1_multi_format_detection having run first (same session clone).
    Does not re-run fixture setup — asserts idempotency of the state left by AC1.
    """
    xlsx1  = download_xlsx(test_sheet_id)
    docx1  = download_docx(test_doc_id)
    ws1    = load_sheet(xlsx1, sheet_name="Actions")
    rows1  = rows_for_doc(ws1, test_doc_id)
    ac1_rows1 = [r for r in rows1 if "AC1:" in (r.get("Action") or "")]

    assert len(ac1_rows1) == 2, (
        f"[uc_a AC2] Expected 2 AC1: rows before second sync, got {len(ac1_rows1)} — "
        "prerequisite: test_uc_a_ac1_multi_format_detection must run first"
    )

    nr_ids_1 = {r["Assignee Email"]: r["NamedRangeId"] for r in ac1_rows1}

    _second_sync(test_doc_id, gas_log_dir)

    xlsx2  = download_xlsx(test_sheet_id)
    docx2  = download_docx(test_doc_id)
    ws2    = load_sheet(xlsx2, sheet_name="Actions")
    rows2  = rows_for_doc(ws2, test_doc_id)
    ac1_rows2 = [r for r in rows2 if "AC1:" in (r.get("Action") or "")]

    # No duplicates
    assert len(ac1_rows2) == len(ac1_rows1), (
        f"[uc_a AC2] AC1: row count changed: {len(ac1_rows1)} → {len(ac1_rows2)}. "
        "Duplicate rows created or rows lost on second sync."
    )

    # Named range IDs preserved for each row
    nr_ids_2 = {r["Assignee Email"]: r["NamedRangeId"] for r in ac1_rows2}
    for email, nrid in nr_ids_1.items():
        assert nr_ids_2.get(email) == nrid, (
            f"[uc_a AC2] NamedRangeId changed for {email!r}: "
            f"{nrid!r} → {nr_ids_2.get(email)!r}"
        )

    # All fields for AC1 rows unchanged — including Date Modified (fix: GTaskSheet-6rn)
    assert ac1_rows1 == ac1_rows2, (
        "[uc_a AC2] AC1: ActionSheet rows changed on second sync — not idempotent.\n"
        f"  Before: {ac1_rows1}\n  After:  {ac1_rows2}"
    )

    # Doc floating actions for AC1 items unchanged
    fa1 = [f for f in floating_actions(load_doc(docx1)) if "AC1:" in f.get("action", "")]
    fa2 = [f for f in floating_actions(load_doc(docx2)) if "AC1:" in f.get("action", "")]
    assert fa1 == fa2, (
        "[uc_a AC2] AC1: floating actions in doc changed on second sync — not idempotent.\n"
        f"  Before: {fa1}\n  After:  {fa2}"
    )


# ---------------------------------------------------------------------------
# AC1 extended — all detection permutations in one Sync
# ---------------------------------------------------------------------------

def test_uc_a_ac1_permutation_coverage(test_sheet_id, test_doc_id, gas_log_dir, settings):
    """AC1 permutations: chip+status-token, email+no-status, underscore-email, plain-text negative."""
    _run_setup_and_sync("uc_a_permutations", "fixture.uc_a_permutations", gas_log_dir, test_doc_id=test_doc_id)

    xlsx_bytes = download_xlsx(test_sheet_id)
    ws   = load_sheet(xlsx_bytes, sheet_name="Actions")
    rows = rows_for_doc(ws, test_doc_id)
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

    # Chip item WITH explicit "(Done)" status token
    assert chip_row.get("Status") == _PERM_CHIP_STATUS, (
        f"[uc_a permutations] Chip row Status: expected {_PERM_CHIP_STATUS!r}, "
        f"got {chip_row.get('Status')!r}"
    )
    assert _PERM_CHIP_ACTION in (chip_row.get("Action") or ""), (
        f"[uc_a permutations] Chip row Action: expected to contain {_PERM_CHIP_ACTION!r}, "
        f"got {chip_row.get('Action')!r}"
    )
    assert chip_row.get("NamedRangeId") not in (None, ""), (
        "[uc_a permutations] Chip row NamedRangeId not set — anchor not created"
    )

    # Email item with NO status token → defaults to Open
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
    assert jane_row.get("NamedRangeId") not in (None, ""), (
        "[uc_a permutations] Jane row NamedRangeId not set — anchor not created"
    )

    # Email with underscore username → name derivation (punctuation→space, title-case)
    assert bob_row.get("Assignee Name") == _PERM_UNDERSCORE_NAME, (
        f"[uc_a permutations] Bob row Assignee Name: expected {_PERM_UNDERSCORE_NAME!r}, "
        f"got {bob_row.get('Assignee Name')!r}"
    )
    assert _PERM_UNDERSCORE_ACTION in (bob_row.get("Action") or ""), (
        f"[uc_a permutations] Bob row Action: expected to contain {_PERM_UNDERSCORE_ACTION!r}, "
        f"got {bob_row.get('Action')!r}"
    )
    assert bob_row.get("NamedRangeId") not in (None, ""), (
        "[uc_a permutations] Bob row NamedRangeId not set — anchor not created"
    )
