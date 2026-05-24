"""
UC-B end-to-end tests: Update an action from either side and converge.

Fixture flow (two GAS invocations per test):
  1. setup_fixture('uc_b_<scenario>') — GAS builds the canonical 7-item doc,
     runs an intermediate sync (UC-A anchoring), then applies mutations.
     Python waits for the fixture log tag before proceeding.
  2. sync_document(test_doc_id) — triggers the final convergence sync.
     Python waits for 'sync.complete'.

Canonical floating action variants (shared doc fixture):
  Var 1: chip  + "Review the budget report (Open)"      testAssigneeEmail
  Var 2: chip  + "Draft the Q3 plan (In Review)"        testAssigneeEmail
  Var 3: chip  + "Update the meeting notes"  (→ Open)   testAssigneeEmail
  Var 4: email + "Schedule the follow-up (Done)"        jane.smith@example.com
  Var 5: email + "Approve the budget proposal"  (→ Open) jane.smith@example.com
  Var 6: email + "Review the Q2 report"  (→ Open)       bob_jones@example.com
  Var 7: plain text (negative — must never appear in ActionSheet)

All three tests are xfail (strict): UC-B bidirectional sync is not yet
implemented (implementation tracked in GTaskSheet-mol-dyu).

Acceptance criteria (from docs/CONTEXT.md §UC-B):
  AC1. A doc edit to the floating action (status token, action text) propagates
       to the ActionSheet after Sync; later Last Modified wins.
  AC2. A sheet edit to Status, Action, or Assignee propagates to the floating
       action paragraph after Sync; later Last Modified wins.
  AC3. The named-range anchor survives every edit type; no duplicate rows created.
  AC4. Variant 7 (plain list item, no assignee) is absent from ActionSheet
       after every sync.
"""

import pathlib
import time

import pytest

from tests.helpers.download import download_xlsx, download_docx
from tests.helpers.gas_invoke import setup_fixture, sync_document
from tests.helpers.gas_log import clear_logs, wait_for_log
from tests.helpers.sheet_inspect import load_sheet, rows_for_doc
from tests.helpers.doc_inspect import load_doc, floating_actions

# ---------------------------------------------------------------------------
# Constants — mirrors canonical fixture in TestFixtures.js
# ---------------------------------------------------------------------------

_JANE_EMAIL       = "jane.smith@example.com"
_BOB_EMAIL        = "bob_jones@example.com"

# Variant 1 (chip, testAssigneeEmail)
_VAR1_ACTION_ORIG = "Review the budget report"
_VAR1_STATUS_ORIG = "Open"
_VAR1_STATUS_MUT  = "Done"         # doc mutation for uc_b_doc_wins

# Variant 2 (chip, testAssigneeEmail)
_VAR2_ACTION_ORIG = "Draft the Q3 plan"
_VAR2_STATUS_ORIG = "In Review"
_VAR2_ACTION_MUT  = "Draft the revised Q3 plan"   # doc mutation for uc_b_doc_wins

# Variant 3 (chip, testAssigneeEmail — no initial status → Open)
_VAR3_ACTION_ORIG = "Update the meeting notes"
_VAR3_STATUS_ORIG = "Open"
_VAR3_STATUS_MUT  = "In Progress"  # doc mutation for uc_b_doc_wins (adds status token)

# Variant 4 (email, jane.smith)
_VAR4_ACTION      = "Schedule the follow-up"
_VAR4_STATUS_ORIG = "Done"
_VAR4_STATUS_MUT  = "Closed"       # sheet mutation for uc_b_sheet_wins

# Variant 5 (email, jane.smith — no initial status → Open)
_VAR5_ACTION_ORIG = "Approve the budget proposal"
_VAR5_STATUS_ORIG = "Open"
_VAR5_ACTION_MUT  = "Approve the revised budget"  # sheet mutation for uc_b_sheet_wins

# Variant 6 (email, bob_jones — no initial status → Open)
_VAR6_ACTION      = "Review the Q2 report"
_VAR6_STATUS_ORIG = "Open"
_VAR6_STATUS_MUT  = "In Review"    # sheet mutation for uc_b_sheet_wins

# Negative (plain text, no chip/email)
_VAR7_ACTION      = "Complete the project documentation"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _clear_logs_stable(log_dir: str, timeout_s: float = 15.0) -> None:
    """Clear logs and re-delete any files that reappear from Drive re-sync."""
    clear_logs(log_dir)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        remaining = list(pathlib.Path(log_dir).glob("*.log"))
        if not remaining:
            return
        for f in remaining:
            f.unlink(missing_ok=True)
        time.sleep(0.5)


def _run_fixture(scenario: str, fixture_tag: str, gas_log_dir: str,
                 timeout_s: float = 240.0) -> None:
    """
    Invoke a UC-B fixture scenario and wait until GAS logs the fixture tag.

    The fixture builds the canonical 7-item state, runs the intermediate
    UC-A sync internally, then applies scenario-specific mutations.
    """
    _clear_logs_stable(gas_log_dir)
    setup_fixture(scenario)
    wait_for_log(gas_log_dir,
                 lambda e: e.get("tag") == fixture_tag,
                 timeout_s=timeout_s)


def _run_final_sync(test_doc_id: str, gas_log_dir: str,
                    timeout_s: float = 120.0) -> None:
    """Clear logs, trigger the convergence sync, wait for sync.complete."""
    _clear_logs_stable(gas_log_dir)
    sync_document(test_doc_id)
    wait_for_log(gas_log_dir,
                 lambda e: (e.get("tag") == "sync.complete" and
                            e.get("data", {}).get("docId") == test_doc_id),
                 timeout_s=timeout_s)


# ---------------------------------------------------------------------------
# AC4 assertion (shared across scenarios)
# ---------------------------------------------------------------------------

def _assert_negative_absent(rows: list, context: str) -> None:
    """Variant 7 (plain text, no assignee) must not appear in any sheet row."""
    plain_rows = [r for r in rows if (r.get("Action") or "").strip() == _VAR7_ACTION]
    assert not plain_rows, (
        f"[{context}] Variant 7 (plain text) must not appear in ActionSheet after sync. "
        f"Found: {plain_rows}"
    )


# ---------------------------------------------------------------------------
# Test 1 — doc wins (variants 1–3 mutated on doc side)
# ---------------------------------------------------------------------------


def test_uc_b_doc_wins(test_sheet_id, test_doc_id, gas_log_dir, settings):
    """
    AC1 + AC3 + AC4: Doc-side mutations to variants 1–3 propagate to ActionSheet
    after Sync; named-range anchors preserved; no duplicates; variant 7 absent.

    Mutations applied by the fixture before the final sync:
      Var 1: status token (Open) → (Done)
      Var 2: action text "Draft the Q3 plan" → "Draft the revised Q3 plan"
      Var 3: status token added "(In Progress)" to previously statusless item
    """
    chip_email = settings["testAssigneeEmail"]

    _run_fixture("uc_b_doc_wins", "fixture.uc_b_doc_wins", gas_log_dir)
    _run_final_sync(test_doc_id, gas_log_dir)

    xlsx_bytes = download_xlsx(test_sheet_id)
    ws   = load_sheet(xlsx_bytes, sheet_name="Actions")
    rows = rows_for_doc(ws, test_doc_id)

    # Exactly 6 rows (variants 1–6); variant 7 absent
    assert len(rows) == 6, (
        f"[uc_b_doc_wins] Expected 6 sheet rows, got {len(rows)}.\n  Rows: {rows}"
    )
    _assert_negative_absent(rows, "uc_b_doc_wins")

    chip_rows = [r for r in rows if r.get("Assignee Email") == chip_email]
    assert len(chip_rows) == 3, (
        f"[uc_b_doc_wins] Expected 3 chip rows for {chip_email!r}, got {len(chip_rows)}."
    )

    # Verify all chip rows still have NamedRangeIds (anchors preserved)
    for row in chip_rows:
        assert row.get("NamedRangeId") not in (None, ""), (
            f"[uc_b_doc_wins] NamedRangeId missing after doc mutation — anchor lost. Row: {row}"
        )

    # Var 1: Status must be updated to the mutated value
    var1_rows = [r for r in chip_rows
                 if (r.get("Action") or "").strip() == _VAR1_ACTION_ORIG]
    assert len(var1_rows) == 1, (
        f"[uc_b_doc_wins] Variant 1 row not found by action text {_VAR1_ACTION_ORIG!r}. "
        f"Chip rows: {chip_rows}"
    )
    assert var1_rows[0].get("Status") == _VAR1_STATUS_MUT, (
        f"[uc_b_doc_wins] Var 1 Status: expected {_VAR1_STATUS_MUT!r}, "
        f"got {var1_rows[0].get('Status')!r}"
    )

    # Var 2: Action text must be updated
    var2_rows = [r for r in chip_rows
                 if (r.get("Action") or "").strip() == _VAR2_ACTION_MUT]
    assert len(var2_rows) == 1, (
        f"[uc_b_doc_wins] Variant 2 row not found by mutated action text {_VAR2_ACTION_MUT!r}. "
        f"Chip rows: {chip_rows}"
    )
    assert var2_rows[0].get("Status") == _VAR2_STATUS_ORIG, (
        f"[uc_b_doc_wins] Var 2 Status should be unchanged: expected {_VAR2_STATUS_ORIG!r}, "
        f"got {var2_rows[0].get('Status')!r}"
    )

    # Var 3: Status must reflect the newly-added status token
    var3_rows = [r for r in chip_rows
                 if (r.get("Action") or "").strip() == _VAR3_ACTION_ORIG]
    assert len(var3_rows) == 1, (
        f"[uc_b_doc_wins] Variant 3 row not found by action text {_VAR3_ACTION_ORIG!r}. "
        f"Chip rows: {chip_rows}"
    )
    assert var3_rows[0].get("Status") == _VAR3_STATUS_MUT, (
        f"[uc_b_doc_wins] Var 3 Status: expected {_VAR3_STATUS_MUT!r}, "
        f"got {var3_rows[0].get('Status')!r}"
    )

    # Variants 4–6 unchanged
    jane_rows = [r for r in rows if r.get("Assignee Email") == _JANE_EMAIL]
    assert len(jane_rows) == 2, (
        f"[uc_b_doc_wins] Expected 2 Jane rows, got {len(jane_rows)}."
    )


# ---------------------------------------------------------------------------
# Test 2 — sheet wins (variants 4–6 mutated on sheet side)
# ---------------------------------------------------------------------------


def test_uc_b_sheet_wins(test_sheet_id, test_doc_id, gas_log_dir, settings):
    """
    AC2 + AC3 + AC4: Sheet-side mutations to variants 4–6 propagate to the
    floating action paragraphs after Sync; named-range anchors preserved;
    no duplicates; variant 7 absent.

    Mutations applied by the fixture before the final sync:
      Var 4: Status Done → Closed
      Var 5: Action "Approve the budget proposal" → "Approve the revised budget"
      Var 6: Status Open → In Review
    """
    chip_email = settings["testAssigneeEmail"]

    _run_fixture("uc_b_sheet_wins", "fixture.uc_b_sheet_wins", gas_log_dir)
    _run_final_sync(test_doc_id, gas_log_dir)

    # Assert sheet unchanged for variants 1–3 (doc side not mutated)
    xlsx_bytes = download_xlsx(test_sheet_id)
    ws   = load_sheet(xlsx_bytes, sheet_name="Actions")
    rows = rows_for_doc(ws, test_doc_id)

    assert len(rows) == 6, (
        f"[uc_b_sheet_wins] Expected 6 sheet rows, got {len(rows)}.\n  Rows: {rows}"
    )
    _assert_negative_absent(rows, "uc_b_sheet_wins")

    # All rows must still have NamedRangeIds (AC3)
    for row in rows:
        assert row.get("NamedRangeId") not in (None, ""), (
            f"[uc_b_sheet_wins] NamedRangeId missing — anchor lost. Row: {row}"
        )

    # Assert doc floating actions reflect the mutated sheet values
    docx_bytes = download_docx(test_doc_id)
    doc = load_doc(docx_bytes)
    fa  = floating_actions(doc)

    # Var 4: status must be "Closed" in the doc paragraph
    var4_fa = [a for a in fa
               if a.get("assignee_email") == _JANE_EMAIL
               and _VAR4_ACTION in (a.get("action") or "")]
    assert len(var4_fa) == 1, (
        f"[uc_b_sheet_wins] Variant 4 floating action not found for {_JANE_EMAIL!r} "
        f"with action containing {_VAR4_ACTION!r}. All FAs: {fa}"
    )
    assert var4_fa[0].get("status") == _VAR4_STATUS_MUT, (
        f"[uc_b_sheet_wins] Var 4 FA status: expected {_VAR4_STATUS_MUT!r}, "
        f"got {var4_fa[0].get('status')!r}"
    )

    # Var 5: action text must be updated in the doc paragraph
    var5_fa = [a for a in fa
               if a.get("assignee_email") == _JANE_EMAIL
               and _VAR5_ACTION_MUT in (a.get("action") or "")]
    assert len(var5_fa) == 1, (
        f"[uc_b_sheet_wins] Variant 5 floating action not found with mutated text "
        f"{_VAR5_ACTION_MUT!r}. All FAs: {fa}"
    )

    # Var 6: status must be "In Review" in the doc paragraph
    var6_fa = [a for a in fa
               if a.get("assignee_email") == _BOB_EMAIL
               and _VAR6_ACTION in (a.get("action") or "")]
    assert len(var6_fa) == 1, (
        f"[uc_b_sheet_wins] Variant 6 floating action not found for {_BOB_EMAIL!r}. "
        f"All FAs: {fa}"
    )
    assert var6_fa[0].get("status") == _VAR6_STATUS_MUT, (
        f"[uc_b_sheet_wins] Var 6 FA status: expected {_VAR6_STATUS_MUT!r}, "
        f"got {var6_fa[0].get('status')!r}"
    )

    # Variants 1–3 chip paragraphs must remain unchanged in the doc
    chip_fa = [a for a in fa if a.get("assignee_email") == chip_email]
    assert len(chip_fa) == 3, (
        f"[uc_b_sheet_wins] Expected 3 chip FAs for {chip_email!r}, got {len(chip_fa)}."
    )
    var1_fa = [a for a in chip_fa if _VAR1_ACTION_ORIG in (a.get("action") or "")]
    assert len(var1_fa) == 1 and var1_fa[0].get("status") == _VAR1_STATUS_ORIG, (
        f"[uc_b_sheet_wins] Var 1 FA should be unchanged. Got: {var1_fa}"
    )


# ---------------------------------------------------------------------------
# Test 3 — conflict resolution (doc wins for var 1, sheet wins for var 4)
# ---------------------------------------------------------------------------


def test_uc_b_conflict_resolution(test_sheet_id, test_doc_id, gas_log_dir, settings):
    """
    AC1 + AC2 + AC3: When both sides diverge, the later Last Modified wins.

    Conflict fixture setup:
      Var 1 (chip): sheet Date Modified forced to 2020-01-01; doc mutated to
                    (In Progress) — doc is "newer" → doc values propagate to sheet.
      Var 4 (email): sheet Status mutated to Closed; sheet Date Modified is the
                     sync timestamp (~now) and no doc change was made — sheet is
                     "newer" → sheet Status propagates to doc paragraph.

    No duplicate rows created; all NamedRangeIds preserved (AC3).
    """
    chip_email = settings["testAssigneeEmail"]

    _run_fixture("uc_b_conflict", "fixture.uc_b_conflict", gas_log_dir)
    _run_final_sync(test_doc_id, gas_log_dir)

    xlsx_bytes = download_xlsx(test_sheet_id)
    ws   = load_sheet(xlsx_bytes, sheet_name="Actions")
    rows = rows_for_doc(ws, test_doc_id)

    assert len(rows) == 6, (
        f"[uc_b_conflict] Expected 6 sheet rows (no duplicates), got {len(rows)}.\n  Rows: {rows}"
    )
    _assert_negative_absent(rows, "uc_b_conflict")

    # All rows must still have NamedRangeIds (AC3)
    for row in rows:
        assert row.get("NamedRangeId") not in (None, ""), (
            f"[uc_b_conflict] NamedRangeId missing — anchor lost. Row: {row}"
        )

    # Var 1: doc wins — sheet row Status must reflect the doc mutation (In Progress)
    chip_rows = [r for r in rows if r.get("Assignee Email") == chip_email]
    var1_rows = [r for r in chip_rows
                 if (r.get("Action") or "").strip() == _VAR1_ACTION_ORIG]
    assert len(var1_rows) == 1, (
        f"[uc_b_conflict] Variant 1 row not found. Chip rows: {chip_rows}"
    )
    assert var1_rows[0].get("Status") == "In Progress", (
        f"[uc_b_conflict] Var 1 (doc wins): expected Status='In Progress', "
        f"got {var1_rows[0].get('Status')!r}"
    )

    # Var 4: sheet wins — doc paragraph status must reflect the sheet mutation (Closed)
    docx_bytes = download_docx(test_doc_id)
    doc = load_doc(docx_bytes)
    fa  = floating_actions(doc)

    var4_fa = [a for a in fa
               if a.get("assignee_email") == _JANE_EMAIL
               and _VAR4_ACTION in (a.get("action") or "")]
    assert len(var4_fa) == 1, (
        f"[uc_b_conflict] Variant 4 floating action not found. All FAs: {fa}"
    )
    assert var4_fa[0].get("status") == "Closed", (
        f"[uc_b_conflict] Var 4 (sheet wins): expected FA status='Closed', "
        f"got {var4_fa[0].get('status')!r}"
    )
