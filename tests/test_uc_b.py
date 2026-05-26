"""
UC-B end-to-end tests: Update an action from either side and converge.

Setup runs once per module via a single batch Playwright session (6 GAS commands,
1 browser launch).  Each scenario appends scenario-prefixed items (UCB-DW:, UCB-SW:,
UCB-CF:) to the shared clone doc so scenarios accumulate without collision.
Assertions filter by the scenario prefix so earlier scenarios' rows are invisible.

Fixture flow per scenario:
  1. Test: Setup Fixture (<scenario>) — GAS builds the canonical 7-item doc,
     runs an intermediate sync (UC-A anchoring), then applies mutations.
     Batch runner waits for the fixture log tag before proceeding.
  2. Test: Sync Document — triggers the final convergence sync.
     Batch runner waits for sync.complete before the next scenario begins.

Canonical floating action variants per scenario (base text; prefix prepended in fixture):
  Var 1: chip  + "<prefix>Review the budget report (Open)"      testAssigneeEmail
  Var 2: chip  + "<prefix>Draft the Q3 plan (In Review)"        testAssigneeEmail
  Var 3: chip  + "<prefix>Update the meeting notes"  (→ Open)   testAssigneeEmail
  Var 4: email + "<prefix>Schedule the follow-up (Done)"        jane.smith@example.com
  Var 5: email + "<prefix>Approve the budget proposal"  (→ Open) jane.smith@example.com
  Var 6: email + "<prefix>Review the Q2 report"  (→ Open)       bob_jones@example.com
  Var 7: plain text (negative — must never appear in ActionSheet)

Tests are active; UC-B bidirectional sync is implemented (GTaskSheet-5vk).

Acceptance criteria (from docs/CONTEXT.md §UC-B):
  AC1. A doc edit to the floating action (status token, action text) propagates
       to the ActionSheet after Sync; later Last Modified wins.
  AC2. A sheet edit to Status, Action, or Assignee propagates to the floating
       action paragraph after Sync; later Last Modified wins.
  AC3. The named-range anchor survives every edit type; no duplicate rows created.
  AC4. Variant 7 (plain list item, no assignee) is absent from ActionSheet
       after every sync.
"""

import pytest

from tests.helpers.download import download_xlsx, download_docx
from tests.helpers.gas_invoke import batch_invoke
from tests.helpers.sheet_inspect import load_sheet, rows_for_doc
from tests.helpers.doc_inspect import load_doc, floating_actions

# ---------------------------------------------------------------------------
# Scenario prefixes — must match ucbPrefix logic in TestFixtures.js
# ---------------------------------------------------------------------------

_DW_PREFIX = "UCB-DW: "   # uc_b_doc_wins scenario
_SW_PREFIX = "UCB-SW: "   # uc_b_sheet_wins scenario
_CF_PREFIX = "UCB-CF: "   # uc_b_conflict scenario

# ---------------------------------------------------------------------------
# Constants — base action texts (prefix is prepended per scenario in GAS)
# ---------------------------------------------------------------------------

_JANE_EMAIL       = "jane.smith@example.com"
_BOB_EMAIL        = "bob_jones@example.com"

_VAR1_ACTION_BASE = "Review the budget report"
_VAR1_STATUS_ORIG = "Open"
_VAR1_STATUS_MUT  = "Done"

_VAR2_ACTION_BASE     = "Draft the Q3 plan"
_VAR2_ACTION_MUT_BASE = "Draft the revised Q3 plan"
_VAR2_STATUS_ORIG = "In Review"

_VAR3_ACTION_BASE = "Update the meeting notes"
_VAR3_STATUS_ORIG = "Open"
_VAR3_STATUS_MUT  = "In Progress"

_VAR4_ACTION_BASE = "Schedule the follow-up"
_VAR4_STATUS_ORIG = "Done"
_VAR4_STATUS_MUT  = "Closed"

_VAR5_ACTION_BASE     = "Approve the budget proposal"
_VAR5_ACTION_MUT_BASE = "Approve the revised budget"
_VAR5_STATUS_ORIG = "Open"

_VAR6_ACTION_BASE = "Review the Q2 report"
_VAR6_STATUS_ORIG = "Open"
_VAR6_STATUS_MUT  = "In Review"

_VAR7_ACTION_BASE = "Complete the project documentation"


# ---------------------------------------------------------------------------
# Module fixture — one browser session covers all three UC-B scenarios
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def uc_b_state(test_sheet_id, test_doc_id):
    batch_invoke([
        {"menuItem": "Test: Setup Fixture", "arg": "uc_b_doc_wins",
         "awaitTag": "fixture.uc_b_doc_wins", "timeoutMs": 300000},
        {"menuItem": "Test: Sync Document", "arg": test_doc_id,
         "awaitTag": "sync.complete", "timeoutMs": 180000},
        {"menuItem": "Test: Setup Fixture", "arg": "uc_b_sheet_wins",
         "awaitTag": "fixture.uc_b_sheet_wins", "timeoutMs": 300000},
        {"menuItem": "Test: Sync Document", "arg": test_doc_id,
         "awaitTag": "sync.complete", "timeoutMs": 180000},
        {"menuItem": "Test: Setup Fixture", "arg": "uc_b_conflict",
         "awaitTag": "fixture.uc_b_conflict", "timeoutMs": 300000},
        {"menuItem": "Test: Sync Document", "arg": test_doc_id,
         "awaitTag": "sync.complete", "timeoutMs": 180000},
    ])
    yield {
        "xlsx_bytes": download_xlsx(test_sheet_id),
        "docx_bytes": download_docx(test_doc_id),
        "doc_id": test_doc_id,
    }


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _verify_consistency(doc_fas: list, sheet_rows: list,
                        tracker_rows: list | None = None,
                        context: str = "") -> None:
    """Assert full-state consistency between floating actions and ActionSheet rows.

    Matches pairs by (assignee_email, action_text). Raises on orphaned entries
    or field mismatches. tracker_rows is reserved for UC-C (not yet asserted).
    """
    prefix = f"[{context}] " if context else ""

    def _fa_key(fa: dict) -> tuple:
        return (
            (fa.get("assignee_email") or "").strip().lower(),
            (fa.get("action") or "").strip(),
        )

    def _row_key(row: dict) -> tuple:
        return (
            (row.get("Assignee Email") or "").strip().lower(),
            (row.get("Action") or "").strip(),
        )

    fa_by_key  = {_fa_key(fa): fa   for fa  in doc_fas}
    row_by_key = {_row_key(r):  r   for r   in sheet_rows}
    fa_keys    = set(fa_by_key)
    row_keys   = set(row_by_key)

    orphaned_fas  = [fa_by_key[k]  for k in fa_keys  - row_keys]
    orphaned_rows = [row_by_key[k] for k in row_keys - fa_keys]
    assert not orphaned_fas, (
        f"{prefix}Floating actions with no matching sheet row: {orphaned_fas}"
    )
    assert not orphaned_rows, (
        f"{prefix}Sheet rows with no matching floating action: {orphaned_rows}"
    )

    mismatches = []
    for key in fa_keys & row_keys:
        fa  = fa_by_key[key]
        row = row_by_key[key]
        fa_status  = (fa.get("status")          or "Open").strip()
        row_status = (row.get("Status")         or "").strip()
        if fa_status != row_status:
            mismatches.append(
                f"  status mismatch {key}: FA={fa_status!r} sheet={row_status!r}"
            )
        if not (row.get("NamedRangeId") or "").strip():
            mismatches.append(f"  NamedRangeId empty for {key}")

    assert not mismatches, (
        f"{prefix}Consistency violations:\n" + "\n".join(mismatches)
    )


def _assert_negative_absent(rows: list, context: str) -> None:
    """Variant 7 (plain text, no assignee) must not appear in any sheet row."""
    plain_rows = [r for r in rows
                  if _VAR7_ACTION_BASE in (r.get("Action") or "")]
    assert not plain_rows, (
        f"[{context}] Variant 7 (plain text) must not appear in ActionSheet after sync. "
        f"Found: {plain_rows}"
    )


# ---------------------------------------------------------------------------
# Test 1 — doc wins (variants 1–3 mutated on doc side)
# ---------------------------------------------------------------------------

def test_uc_b_doc_wins(uc_b_state, settings):
    """
    AC1 + AC3 + AC4: Doc-side mutations to variants 1–3 propagate to ActionSheet
    after Sync; named-range anchors preserved; no duplicates; variant 7 absent.

    Mutations applied by the fixture before the final sync:
      Var 1: status token (Open) → (Done)
      Var 2: action text "Draft the Q3 plan" → "Draft the revised Q3 plan"
      Var 3: status token added "(In Progress)" to previously statusless item
    """
    chip_email = settings["testAssigneeEmail"]

    ws   = load_sheet(uc_b_state["xlsx_bytes"], sheet_name="Actions")
    all_rows = rows_for_doc(ws, uc_b_state["doc_id"])
    rows = [r for r in all_rows if (r.get("Action") or "").startswith(_DW_PREFIX)]

    assert len(rows) == 6, (
        f"[uc_b_doc_wins] Expected 6 UCB-DW: rows, got {len(rows)}.\n  Rows: {rows}"
    )
    _assert_negative_absent(rows, "uc_b_doc_wins")

    chip_rows = [r for r in rows if r.get("Assignee Email") == chip_email]
    assert len(chip_rows) == 3, (
        f"[uc_b_doc_wins] Expected 3 chip rows for {chip_email!r}, got {len(chip_rows)}."
    )

    for row in chip_rows:
        assert row.get("NamedRangeId") not in (None, ""), (
            f"[uc_b_doc_wins] NamedRangeId missing after doc mutation — anchor lost. Row: {row}"
        )

    var1_rows = [r for r in chip_rows
                 if _VAR1_ACTION_BASE in (r.get("Action") or "")]
    assert len(var1_rows) == 1, (
        f"[uc_b_doc_wins] Variant 1 row not found by action text {_VAR1_ACTION_BASE!r}. "
        f"Chip rows: {chip_rows}"
    )
    assert var1_rows[0].get("Status") == _VAR1_STATUS_MUT, (
        f"[uc_b_doc_wins] Var 1 Status: expected {_VAR1_STATUS_MUT!r}, "
        f"got {var1_rows[0].get('Status')!r}"
    )

    var2_rows = [r for r in chip_rows
                 if _VAR2_ACTION_MUT_BASE in (r.get("Action") or "")]
    assert len(var2_rows) == 1, (
        f"[uc_b_doc_wins] Variant 2 row not found by mutated action text {_VAR2_ACTION_MUT_BASE!r}. "
        f"Chip rows: {chip_rows}"
    )
    assert var2_rows[0].get("Status") == _VAR2_STATUS_ORIG, (
        f"[uc_b_doc_wins] Var 2 Status should be unchanged: expected {_VAR2_STATUS_ORIG!r}, "
        f"got {var2_rows[0].get('Status')!r}"
    )

    var3_rows = [r for r in chip_rows
                 if _VAR3_ACTION_BASE in (r.get("Action") or "")]
    assert len(var3_rows) == 1, (
        f"[uc_b_doc_wins] Variant 3 row not found by action text {_VAR3_ACTION_BASE!r}. "
        f"Chip rows: {chip_rows}"
    )
    assert var3_rows[0].get("Status") == _VAR3_STATUS_MUT, (
        f"[uc_b_doc_wins] Var 3 Status: expected {_VAR3_STATUS_MUT!r}, "
        f"got {var3_rows[0].get('Status')!r}"
    )

    jane_rows = [r for r in rows if r.get("Assignee Email") == _JANE_EMAIL]
    assert len(jane_rows) == 2, (
        f"[uc_b_doc_wins] Expected 2 Jane rows, got {len(jane_rows)}."
    )

    doc = load_doc(uc_b_state["docx_bytes"])
    fa_all = floating_actions(doc)
    fa = [a for a in fa_all if (a.get("action") or "").startswith(_DW_PREFIX)]
    _verify_consistency(fa, rows, context="uc_b_doc_wins")


# ---------------------------------------------------------------------------
# Test 2 — sheet wins (variants 4–6 mutated on sheet side)
# ---------------------------------------------------------------------------

def test_uc_b_sheet_wins(uc_b_state, settings):
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

    ws   = load_sheet(uc_b_state["xlsx_bytes"], sheet_name="Actions")
    all_rows = rows_for_doc(ws, uc_b_state["doc_id"])
    rows = [r for r in all_rows if (r.get("Action") or "").startswith(_SW_PREFIX)]

    assert len(rows) == 6, (
        f"[uc_b_sheet_wins] Expected 6 UCB-SW: rows, got {len(rows)}.\n  Rows: {rows}"
    )
    _assert_negative_absent(rows, "uc_b_sheet_wins")

    for row in rows:
        assert row.get("NamedRangeId") not in (None, ""), (
            f"[uc_b_sheet_wins] NamedRangeId missing — anchor lost. Row: {row}"
        )

    doc = load_doc(uc_b_state["docx_bytes"])
    fa_all = floating_actions(doc)
    fa = [a for a in fa_all if (a.get("action") or "").startswith(_SW_PREFIX)]

    var4_fa = [a for a in fa
               if a.get("assignee_email") == _JANE_EMAIL
               and _VAR4_ACTION_BASE in (a.get("action") or "")]
    assert len(var4_fa) == 1, (
        f"[uc_b_sheet_wins] Variant 4 floating action not found for {_JANE_EMAIL!r} "
        f"with action containing {_VAR4_ACTION_BASE!r}. SW FAs: {fa}"
    )
    assert var4_fa[0].get("status") == _VAR4_STATUS_MUT, (
        f"[uc_b_sheet_wins] Var 4 FA status: expected {_VAR4_STATUS_MUT!r}, "
        f"got {var4_fa[0].get('status')!r}"
    )

    var5_fa = [a for a in fa
               if a.get("assignee_email") == _JANE_EMAIL
               and _VAR5_ACTION_MUT_BASE in (a.get("action") or "")]
    assert len(var5_fa) == 1, (
        f"[uc_b_sheet_wins] Variant 5 floating action not found with mutated text "
        f"{_VAR5_ACTION_MUT_BASE!r}. SW FAs: {fa}"
    )
    assert var5_fa[0].get("status") == _VAR5_STATUS_ORIG, (
        f"[uc_b_sheet_wins] Var 5 FA status: expected {_VAR5_STATUS_ORIG!r}, "
        f"got {var5_fa[0].get('status')!r}"
    )
    assert var5_fa[0].get("has_explicit_status") is True, (
        f"[uc_b_sheet_wins] Var 5 FA should have an explicit status token after sync. Got: {var5_fa[0]}"
    )

    var6_fa = [a for a in fa
               if a.get("assignee_email") == _BOB_EMAIL
               and _VAR6_ACTION_BASE in (a.get("action") or "")]
    assert len(var6_fa) == 1, (
        f"[uc_b_sheet_wins] Variant 6 floating action not found for {_BOB_EMAIL!r}. "
        f"SW FAs: {fa}"
    )
    assert var6_fa[0].get("status") == _VAR6_STATUS_MUT, (
        f"[uc_b_sheet_wins] Var 6 FA status: expected {_VAR6_STATUS_MUT!r}, "
        f"got {var6_fa[0].get('status')!r}"
    )
    assert var6_fa[0].get("has_explicit_status") is True, (
        f"[uc_b_sheet_wins] Var 6 FA should have an explicit status token after sync. Got: {var6_fa[0]}"
    )

    chip_fa = [a for a in fa if a.get("assignee_email") == chip_email]
    assert len(chip_fa) == 3, (
        f"[uc_b_sheet_wins] Expected 3 SW chip FAs for {chip_email!r}, got {len(chip_fa)}."
    )
    var1_fa = [a for a in chip_fa if _VAR1_ACTION_BASE in (a.get("action") or "")]
    assert len(var1_fa) == 1 and var1_fa[0].get("status") == _VAR1_STATUS_ORIG, (
        f"[uc_b_sheet_wins] Var 1 FA should be unchanged. Got: {var1_fa}"
    )

    var3_fa = [a for a in chip_fa if _VAR3_ACTION_BASE in (a.get("action") or "")]
    assert len(var3_fa) == 1, (
        f"[uc_b_sheet_wins] Variant 3 floating action not found. Got: {chip_fa}"
    )
    assert var3_fa[0].get("status") == _VAR3_STATUS_ORIG, (
        f"[uc_b_sheet_wins] Var 3 FA status: expected {_VAR3_STATUS_ORIG!r}, "
        f"got {var3_fa[0].get('status')!r}"
    )
    assert var3_fa[0].get("has_explicit_status") is True, (
        f"[uc_b_sheet_wins] Var 3 FA should have an explicit status token after sync. Got: {var3_fa[0]}"
    )

    _verify_consistency(fa, rows, context="uc_b_sheet_wins")


# ---------------------------------------------------------------------------
# Test 3 — conflict resolution (doc wins for var 1, sheet wins for var 4)
# ---------------------------------------------------------------------------

def test_uc_b_conflict_resolution(uc_b_state, settings):
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

    ws   = load_sheet(uc_b_state["xlsx_bytes"], sheet_name="Actions")
    all_rows = rows_for_doc(ws, uc_b_state["doc_id"])
    rows = [r for r in all_rows if (r.get("Action") or "").startswith(_CF_PREFIX)]

    assert len(rows) == 6, (
        f"[uc_b_conflict] Expected 6 UCB-CF: rows (no duplicates), got {len(rows)}.\n  Rows: {rows}"
    )
    _assert_negative_absent(rows, "uc_b_conflict")

    for row in rows:
        assert row.get("NamedRangeId") not in (None, ""), (
            f"[uc_b_conflict] NamedRangeId missing — anchor lost. Row: {row}"
        )

    chip_rows = [r for r in rows if r.get("Assignee Email") == chip_email]
    var1_rows = [r for r in chip_rows
                 if _VAR1_ACTION_BASE in (r.get("Action") or "")]
    assert len(var1_rows) == 1, (
        f"[uc_b_conflict] Variant 1 row not found. Chip rows: {chip_rows}"
    )
    assert var1_rows[0].get("Status") == "In Progress", (
        f"[uc_b_conflict] Var 1 (doc wins): expected Status='In Progress', "
        f"got {var1_rows[0].get('Status')!r}"
    )

    doc = load_doc(uc_b_state["docx_bytes"])
    fa_all = floating_actions(doc)
    fa = [a for a in fa_all if (a.get("action") or "").startswith(_CF_PREFIX)]

    var4_fa = [a for a in fa
               if a.get("assignee_email") == _JANE_EMAIL
               and _VAR4_ACTION_BASE in (a.get("action") or "")]
    assert len(var4_fa) == 1, (
        f"[uc_b_conflict] Variant 4 floating action not found. CF FAs: {fa}"
    )
    assert var4_fa[0].get("status") == "Closed", (
        f"[uc_b_conflict] Var 4 (sheet wins): expected FA status='Closed', "
        f"got {var4_fa[0].get('status')!r}"
    )

    _verify_consistency(fa, rows, context="uc_b_conflict")
