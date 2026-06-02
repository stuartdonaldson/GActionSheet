"""
UC-C end-to-end tests: Insert / refresh the in-doc tracker table.
GTaskSheet-mol-bgq / GTaskSheet-ly5 (Sync Status column).

Playwright sessions
-------------------
This module uses exactly TWO Playwright browser launches (plus the two
session-level launches in conftest.py for begin/end_test_session):

  uc_c_state        (module fixture) — one batch call fires all UC-C scenario
                    fixtures in sequence; browser opens once, closes after the
                    last awaitTag is received.

  sync_status_state (module fixture) — one batch call fires all Sync Status
                    scenario fixtures; browser opens once, closes after all tags.

Individual tests receive pre-downloaded XLSX/DOCX bytes from the fixture and
perform only local assertions — zero per-test Playwright calls.

GAS fixture contracts
---------------------
Every scenario fixture listed below must be self-contained: it performs setup,
triggers its own GAS operation internally, and logs the completion tag.

UC-C scenarios (accumulate-without-reset on the clone doc):
  uc_c_first_insert  → UCC-FIRST: prefix  → logs fixture.uc_c_first_insert
  uc_c_refresh       → UCC-REFRESH: prefix → logs fixture.uc_c_refresh
  uc_c_view_only     → UCC-VIEWONLY: prefix → logs fixture.uc_c_view_only

Sync Status scenarios:
  sync_status_migration      → logs fixture.sync_status_migration
  sync_status_deleted        → SS-DEL: prefix  → logs fixture.sync_status_deleted
  sync_status_doc_not_found  → SS-NF: prefix   → logs fixture.sync_status_doc_not_found
  sync_status_recovery       → SS-REC: prefix  → logs fixture.sync_status_recovery
  sync_status_on_edit        → SS-EDIT: prefix → logs fixture.sync_status_on_edit
                               with data.sentinelDateModified
  sync_status_archive        → SS-ARCH: prefix → logs fixture.sync_status_archive

Tests are written in red phase (ATDD): GAS implementation does not yet exist.
GTaskSheet-mol-bgq / GTaskSheet-ly5.
"""

import pytest
from datetime import datetime, timezone

from tests.helpers.download import download_xlsx, download_docx
from tests.helpers.fixture_invoke import invoke_fixture
from tests.helpers.sheet_inspect import load_sheet, rows_for_doc, rows_as_dicts, headers
from tests.helpers.doc_inspect import (
    load_doc, floating_actions, tracked_actions_table, _iter_block_items,
    verify_doc_chip_integrity,
)


def _dates_match(dt_val, iso_str, tol_seconds: int = 2) -> bool:
    """Compare an XLSX datetime (naive, spreadsheet-local) with a GAS UTC ISO string.

    Google Sheets exports XLSX dates in the spreadsheet's local timezone as naive
    datetimes, while GAS JSON.stringify(date) produces UTC ISO strings.  Common
    timezones have whole-hour offsets, so minute+second+microsecond are
    timezone-invariant.  Comparing those sub-hour components avoids needing to
    know the spreadsheet's UTC offset.

    Tolerance of 2 s covers sub-second rounding in XLSX export.
    """
    if dt_val is None or iso_str is None:
        return False
    if not isinstance(dt_val, datetime):
        try:
            dt_val = datetime.fromisoformat(str(dt_val).replace('Z', '+00:00'))
        except ValueError:
            return False
    iso_dt = datetime.fromisoformat(str(iso_str).replace('Z', '+00:00'))

    def _sub_hour(dt: datetime) -> float:
        return dt.minute * 60 + dt.second + dt.microsecond / 1_000_000

    return abs(_sub_hour(dt_val) - _sub_hour(iso_dt)) <= tol_seconds

# ---------------------------------------------------------------------------
# Scenario prefixes
# ---------------------------------------------------------------------------

_FIRST_PREFIX    = "UCC-FIRST: "
_REFRESH_PREFIX  = "UCC-REFRESH: "
_VIEWONLY_PREFIX = "UCC-VIEWONLY: "
_DEL_PREFIX      = "SS-DEL: "
_NF_PREFIX       = "SS-NF: "
_REC_PREFIX      = "SS-REC: "
_EDIT_PREFIX     = "SS-EDIT: "
_ARCH_PREFIX     = "SS-ARCH: "

# ---------------------------------------------------------------------------
# Module-scoped batch fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def uc_c_state(settings, test_sheet_id, test_doc_id):
    """Run all UC-C scenario fixtures via HTTP (no browser), download once.

    Yields a dict with keys: docx_bytes, xlsx_bytes, doc_id.
    """
    invoke_fixture("uc_c_first_insert", test_doc_id, settings)
    assert verify_doc_chip_integrity(test_doc_id, settings) == [], \
        "chip integrity violations after uc_c_first_insert"
    invoke_fixture("uc_c_refresh",      test_doc_id, settings)
    assert verify_doc_chip_integrity(test_doc_id, settings) == [], \
        "chip integrity violations after uc_c_refresh"
    invoke_fixture("uc_c_view_only",    test_doc_id, settings)
    assert verify_doc_chip_integrity(test_doc_id, settings) == [], \
        "chip integrity violations after uc_c_view_only"

    yield {
        "docx_bytes": download_docx(test_doc_id),
        "xlsx_bytes": download_xlsx(test_sheet_id),
        "doc_id": test_doc_id,
    }


@pytest.fixture(scope="module")
def sync_status_state(settings, test_sheet_id, test_doc_id):
    """Run all Sync Status scenario fixtures via HTTP (no browser), download once.

    Yields a dict with keys: xlsx_bytes, doc_id, sentinel_date_modified.
    Archive scenario runs last because it moves rows from Actions → Archive sheet.
    """
    invoke_fixture("sync_status_migration",     test_doc_id, settings)
    invoke_fixture("sync_status_deleted",       test_doc_id, settings)
    invoke_fixture("sync_status_doc_not_found", test_doc_id, settings)
    invoke_fixture("sync_status_recovery",      test_doc_id, settings)

    on_edit_result = invoke_fixture("sync_status_on_edit", test_doc_id, settings)
    sentinel = (on_edit_result.get("data") or {}).get("sentinelDateModified")

    invoke_fixture("sync_status_archive", test_doc_id, settings)

    yield {
        "xlsx_bytes": download_xlsx(test_sheet_id),
        "doc_id": test_doc_id,
        "sentinel_date_modified": sentinel,
    }


# ---------------------------------------------------------------------------
# Shared assertion helpers
# ---------------------------------------------------------------------------

def _assert_instructional_paragraph(doc, context: str = "") -> None:
    """Assert a read-only notice exists between the section heading and the table."""
    prefix = f"[{context}] " if context else ""
    found_heading = False
    for block in _iter_block_items(doc):
        if hasattr(block, "text"):
            if block.text.strip() == "=== Tracked Actions ===":
                found_heading = True
                continue
            if found_heading:
                if "read-only" in block.text.lower() or "read only" in block.text.lower():
                    return
        elif found_heading and hasattr(block, "rows"):
            break
    assert False, (
        f"{prefix}No read-only notice found between '=== Tracked Actions ===' "
        "heading and tracker table."
    )


def _verify_full_consistency(doc_fas: list, sheet_rows: list,
                             tracker_rows: list | None = None,
                             context: str = "") -> None:
    """Assert full three-way consistency: floating actions ↔ sheet rows ↔ tracker rows.

    FA ↔ sheet: matched by (assignee_email, action_text).
    FA ↔ tracker: matched by action_text; Status and Action must agree.
    Exactly one tracker row per floating action (no stale rows, no missing rows).
    """
    prefix = f"[{context}] " if context else ""

    def _fa_key(fa):
        return (
            (fa.get("assignee_email") or "").strip().lower(),
            (fa.get("action") or "").strip(),
        )

    def _row_key(row):
        return (
            (row.get("Assignee Email") or "").strip().lower(),
            (row.get("Action") or "").strip(),
        )

    fa_by_key  = {_fa_key(fa): fa  for fa  in doc_fas}
    row_by_key = {_row_key(r):  r  for r   in sheet_rows}
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
        if (fa.get("status") or "Open").strip() != (row.get("Status") or "").strip():
            mismatches.append(
                f"  status mismatch {key}: "
                f"FA={(fa.get('status') or 'Open')!r} sheet={row.get('Status')!r}"
            )
        if not (row.get("globalId") or "").strip():
            mismatches.append(f"  globalId empty for {key}")
    assert not mismatches, f"{prefix}FA ↔ sheet violations:\n" + "\n".join(mismatches)

    if tracker_rows is None:
        return

    tracker_by_action = {}
    for tr in tracker_rows:
        key = (tr.get("Action") or "").strip()
        if key in tracker_by_action:
            mismatches.append(f"  duplicate tracker row for action {key!r}")
        else:
            tracker_by_action[key] = tr

    assert not mismatches, f"{prefix}Tracker duplicates:\n" + "\n".join(mismatches)

    fa_actions      = {(fa.get("action") or "").strip() for fa in doc_fas}
    tracker_actions = set(tracker_by_action)

    orphaned_tracker = [tracker_by_action[k] for k in tracker_actions - fa_actions]
    missing_tracker  = [fa for fa in doc_fas
                        if (fa.get("action") or "").strip() not in tracker_actions]

    assert not orphaned_tracker, (
        f"{prefix}Stale tracker rows (no matching FA): {orphaned_tracker}"
    )
    assert not missing_tracker, (
        f"{prefix}FAs with no tracker row: {missing_tracker}"
    )

    for action_text, tr in tracker_by_action.items():
        fa = next(
            (f for f in doc_fas if (f.get("action") or "").strip() == action_text), None
        )
        if fa is None:
            continue
        fa_status = (fa.get("status") or "Open").strip()
        tr_status = (tr.get("Status") or "").strip()
        if fa_status != tr_status:
            mismatches.append(
                f"  tracker status mismatch for {action_text!r}: "
                f"FA={fa_status!r} tracker={tr_status!r}"
            )

    assert not mismatches, f"{prefix}FA ↔ tracker violations:\n" + "\n".join(mismatches)


# ---------------------------------------------------------------------------
# UC-C AC1 — first insert produces N-row table in document order
# ---------------------------------------------------------------------------

def test_uc_c_first_insert(uc_c_state):
    """
    AC1: First click produces instructional paragraph + N-row table, anchored.
    AC4 (partial): instructional paragraph contains a read-only notice.
    """
    doc  = load_doc(uc_c_state["docx_bytes"])
    ws   = load_sheet(uc_c_state["xlsx_bytes"], sheet_name="Actions")
    rows = [r for r in rows_for_doc(ws, uc_c_state["doc_id"])
            if (r.get("Action") or "").startswith(_FIRST_PREFIX)]
    fa   = [a for a in floating_actions(doc)
            if (a.get("action") or "").startswith(_FIRST_PREFIX)]

    tracker_all   = tracked_actions_table(doc)
    assert tracker_all is not None, (
        "[uc_c_first_insert] Tracker table not found in document."
    )
    tracker_first = [tr for tr in tracker_all
                     if (tr.get("Action") or "").startswith(_FIRST_PREFIX)]

    assert len(tracker_first) == len(fa), (
        f"[uc_c_first_insert] Tracker row count {len(tracker_first)} != "
        f"floating action count {len(fa)}."
    )
    _assert_instructional_paragraph(doc, context="uc_c_first_insert")
    _verify_full_consistency(fa, rows, tracker_first, context="uc_c_first_insert")


# ---------------------------------------------------------------------------
# UC-C AC2 + AC3 — refresh reflects changes; row values match
# ---------------------------------------------------------------------------

def test_uc_c_refresh(uc_c_state):
    """
    AC2: Refresh after close+add reflects both changes in place; no stale rows.
    AC3: Each tracker row's Action and Status match the FA and sheet row.
    """
    doc  = load_doc(uc_c_state["docx_bytes"])
    ws   = load_sheet(uc_c_state["xlsx_bytes"], sheet_name="Actions")
    rows = [r for r in rows_for_doc(ws, uc_c_state["doc_id"])
            if (r.get("Action") or "").startswith(_REFRESH_PREFIX)]
    fa   = [a for a in floating_actions(doc)
            if (a.get("action") or "").startswith(_REFRESH_PREFIX)]

    tracker_all     = tracked_actions_table(doc)
    assert tracker_all is not None, (
        "[uc_c_refresh] Tracker table not found after refresh."
    )
    tracker_refresh = [tr for tr in tracker_all
                       if (tr.get("Action") or "").startswith(_REFRESH_PREFIX)]

    _assert_instructional_paragraph(doc, context="uc_c_refresh")
    _verify_full_consistency(fa, rows, tracker_refresh, context="uc_c_refresh")


# ---------------------------------------------------------------------------
# UC-C AC4 — tracker cell edits discarded on next refresh
# ---------------------------------------------------------------------------

def test_uc_c_view_only(uc_c_state):
    """
    AC4: Direct cell edits in the tracker table are discarded on the next refresh;
    rendered values match the floating actions and ActionSheet.
    """
    doc  = load_doc(uc_c_state["docx_bytes"])
    ws   = load_sheet(uc_c_state["xlsx_bytes"], sheet_name="Actions")
    rows = [r for r in rows_for_doc(ws, uc_c_state["doc_id"])
            if (r.get("Action") or "").startswith(_VIEWONLY_PREFIX)]
    fa   = [a for a in floating_actions(doc)
            if (a.get("action") or "").startswith(_VIEWONLY_PREFIX)]

    tracker_all      = tracked_actions_table(doc)
    assert tracker_all is not None, (
        "[uc_c_view_only] Tracker table not found after refresh."
    )
    tracker_viewonly = [tr for tr in tracker_all
                        if (tr.get("Action") or "").startswith(_VIEWONLY_PREFIX)]

    _assert_instructional_paragraph(doc, context="uc_c_view_only")
    _verify_full_consistency(fa, rows, tracker_viewonly, context="uc_c_view_only")


# ===========================================================================
# Sync Status column tests (GTaskSheet-ly5)
# ===========================================================================

# ---------------------------------------------------------------------------
# ly5 AC1 — 'Sync Status' header present on fresh sheet
# ---------------------------------------------------------------------------

def test_sync_status_header_present(sync_status_state):
    """ly5 AC1: Actions sheet col 10 header is 'Sync Status'."""
    ws          = load_sheet(sync_status_state["xlsx_bytes"], sheet_name="Actions")
    col_headers = headers(ws)

    assert "Sync Status" in col_headers, (
        f"[sync_status_header] 'Sync Status' column not found. Headers: {list(col_headers)}"
    )
    assert col_headers["Sync Status"] == 10, (
        f"[sync_status_header] 'Sync Status' expected at col 10, "
        f"found at col {col_headers['Sync Status']}."
    )


# ---------------------------------------------------------------------------
# ly5 AC2 — header restored after migration on legacy sheet
# ---------------------------------------------------------------------------

def test_sync_status_migration(sync_status_state):
    """ly5 AC2: 'Sync Status' header present after migration from a legacy sheet."""
    ws          = load_sheet(sync_status_state["xlsx_bytes"], sheet_name="Actions")
    col_headers = headers(ws)

    assert "Sync Status" in col_headers, (
        f"[sync_status_migration] 'Sync Status' header not restored after migration. "
        f"Headers: {list(col_headers)}"
    )


# ---------------------------------------------------------------------------
# ly5 AC3 — 'Deleted' written when named range removed before sync
# ---------------------------------------------------------------------------

def test_sync_status_deleted(sync_status_state):
    """ly5 AC3: Sync Status = 'Deleted' when floating action removed from doc before sync."""
    ws   = load_sheet(sync_status_state["xlsx_bytes"], sheet_name="Actions")
    # Filter to the current session's doc to avoid stale rows from previous runs.
    rows = [r for r in rows_for_doc(ws, sync_status_state["doc_id"])
            if (r.get("Action") or "").startswith(_DEL_PREFIX)]

    assert rows, "[sync_status_deleted] No SS-DEL: rows found for current doc in Actions sheet."
    for row in rows:
        assert row.get("Sync Status") == "Deleted", (
            f"[sync_status_deleted] Expected 'Deleted', "
            f"got {row.get('Sync Status')!r}. Row: {row}"
        )


# ---------------------------------------------------------------------------
# ly5 AC4 — 'Doc Not Found' written when document is inaccessible
# ---------------------------------------------------------------------------

def test_sync_status_doc_not_found(sync_status_state):
    """ly5 AC4: Sync Status = 'Doc Not Found' when document is inaccessible."""
    ws   = load_sheet(sync_status_state["xlsx_bytes"], sheet_name="Actions")
    rows = [r for r in rows_as_dicts(ws)
            if (r.get("Action") or "").startswith(_NF_PREFIX)]

    assert rows, "[sync_status_doc_not_found] No SS-NF: rows found in Actions sheet."
    for row in rows:
        assert row.get("Sync Status") == "Doc Not Found", (
            f"[sync_status_doc_not_found] Expected 'Doc Not Found', "
            f"got {row.get('Sync Status')!r}. Row: {row}"
        )


# ---------------------------------------------------------------------------
# ly5 AC5 — blank written when previously-flagged row syncs successfully
# ---------------------------------------------------------------------------

def test_sync_status_recovery(sync_status_state):
    """ly5 AC5: Sync Status blank after successful sync of a previously-flagged row."""
    ws   = load_sheet(sync_status_state["xlsx_bytes"], sheet_name="Actions")
    rows = [r for r in rows_as_dicts(ws)
            if (r.get("Action") or "").startswith(_REC_PREFIX)]

    assert rows, "[sync_status_recovery] No SS-REC: rows found in Actions sheet."
    for row in rows:
        sync_status = row.get("Sync Status") or ""
        assert sync_status == "", (
            f"[sync_status_recovery] Expected blank after recovery, "
            f"got {sync_status!r}. Row: {row}"
        )


# ---------------------------------------------------------------------------
# ly5 AC6 — onEdit does not update Date Modified when col 10 is edited
# ---------------------------------------------------------------------------

def test_sync_status_on_edit_no_date_change(sync_status_state):
    """ly5 AC6: Editing Sync Status cell (col 10) does not trigger Date Modified update."""
    sentinel = sync_status_state["sentinel_date_modified"]
    assert sentinel is not None, (
        "[sync_status_on_edit] Fixture did not log sentinelDateModified. "
        "Check GAS fixture.sync_status_on_edit implementation."
    )

    ws   = load_sheet(sync_status_state["xlsx_bytes"], sheet_name="Actions")
    # Filter to the current session's doc to avoid stale SS-EDIT: rows from prior runs.
    rows = [r for r in rows_for_doc(ws, sync_status_state["doc_id"])
            if (r.get("Action") or "").startswith(_EDIT_PREFIX)]

    assert rows, "[sync_status_on_edit] No SS-EDIT: rows found for current doc in Actions sheet."
    for row in rows:
        date_modified = row.get("Date Modified")
        assert _dates_match(date_modified, sentinel), (
            f"[sync_status_on_edit] Date Modified changed after col-10 edit — "
            f"onEdit fired incorrectly. "
            f"Before (sentinel): {sentinel!r}, After: {date_modified!r}."
        )


# ---------------------------------------------------------------------------
# ly5 AC7 — archive preserves Sync Status value
# ---------------------------------------------------------------------------

def test_sync_status_archive_preserved(sync_status_state):
    """ly5 AC7: Archived row retains its Sync Status value; removed from Actions sheet."""
    xlsx_bytes = sync_status_state["xlsx_bytes"]

    ws_archive   = load_sheet(xlsx_bytes, sheet_name="Archive")
    archive_rows = [r for r in rows_as_dicts(ws_archive)
                    if (r.get("Action") or "").startswith(_ARCH_PREFIX)]

    assert archive_rows, (
        "[sync_status_archive] No SS-ARCH: rows found in Archive sheet."
    )
    for row in archive_rows:
        assert row.get("Sync Status") == "Deleted", (
            f"[sync_status_archive] Sync Status not preserved. "
            f"Expected 'Deleted', got {row.get('Sync Status')!r}. Row: {row}"
        )

    doc_id = sync_status_state["doc_id"]
    ws_actions  = load_sheet(xlsx_bytes, sheet_name="Actions")
    still_active = [r for r in rows_as_dicts(ws_actions)
                    if (r.get("Action") or "").startswith(_ARCH_PREFIX)
                    and doc_id in (r.get("Document") or "")]
    assert not still_active, (
        f"[sync_status_archive] SS-ARCH: rows still in Actions after archive: {still_active}"
    )
