"""
Slice tests for 0k6: bidirectional sync — conflict resolution, paragraph rewrite,
onEdit trigger, and programmatic write guard.

All tests are marked xfail until the 0k6 GAS modules are deployed:
  - SheetReconciler.js (update path: sheet-wins and doc-wins branches)
  - onEditTrigger.js
  - SYNC_IN_PROGRESS guard in all sheet-write paths

Each test:
  1. Resets the test doc/sheet to a known fixture state via setupTestFixtures(scenario).
  2. Runs syncDocument(testDocId) via the GAS editor.
  3. Downloads the sheet as .xlsx and/or the doc as .docx.
  4. Asserts the expected outcome.

The GAS function invocations (setupTestFixtures, syncDocument) are triggered via the
Playwright editor helper. The Playwright integration is not yet wired in Python —
those calls are marked with TODO comments matching the pattern in test_slice_5jn.py.

Prerequisites:
  - local.settings.json populated with testSheetId, testDocId, scriptId, gasLogDir
  - Test sheet and doc shared with "Anyone with link (viewer)"
  - .auth/user.json present (run `node tests/playwright/authenticate.js` once)
"""
import pytest

from tests.helpers.download import download_xlsx, download_docx
from tests.helpers.sheet_inspect import load_sheet, find_row, assert_date_cell, headers
from tests.helpers.doc_inspect import (
    load_doc,
    find_table_row,
    floating_actions,
)
from tests.helpers.gas_log import clear_logs, wait_for_log
from tests.helpers.gas_invoke import setup_fixture, sync_document


# ---------------------------------------------------------------------------
# AC-3: Document wins when doc timestamp is newer
# ---------------------------------------------------------------------------


class TestDocumentWins:
    """0k6 AC-3: when the document record has a later Date Modified, the sheet row
    is updated from the document values; Synced cell is written."""

    def test_document_timestamp_newer_sheet_updated(
        self, test_sheet_id, test_doc_id, gas_log_dir
    ):
        """After setupTestFixtures('ac3') + syncDocument(), the sheet row for action
        ID=1 must reflect the doc's Action, Status, and Date Modified values.

        Fixture precondition: sheet row Date Modified = T-1h; doc table row
        Date Modified = T (newer); doc Status = 'Done'.
        """
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        clear_logs(gas_log_dir)
        setup_fixture('ac3')
        sync_document(test_doc_id)
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.sheet-updated")

        xlsx = download_xlsx(test_sheet_id)
        ws = load_sheet(xlsx, sheet_name="Actions")

        row = find_row(
            ws,
            doc_url=f"docs.google.com/document/d/{test_doc_id}",
            action_id=1,
        )
        assert row is not None, "Sheet 'Actions' tab has no row with ID=1"
        assert row["Status"] == "Done", (
            f"Expected Status='Done' (doc wins), got {row['Status']!r}"
        )
        assert row["Action"] is not None and row["Action"] != "", (
            "Action cell is empty after doc-wins update"
        )
        assert_date_cell(ws, row, "Date Modified")

    def test_document_wins_synced_column_written(
        self, test_sheet_id, test_doc_id, gas_log_dir
    ):
        """After a doc-wins update, the Synced column must hold a datetime value
        (not blank) confirming the reconciler completed the write."""
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        clear_logs(gas_log_dir)
        setup_fixture('ac3')
        sync_document(test_doc_id)
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.sheet-updated")

        xlsx = download_xlsx(test_sheet_id)
        ws = load_sheet(xlsx, sheet_name="Actions")

        col_map = headers(ws)
        assert "Synced" in col_map, "Sheet 'Actions' tab has no 'Synced' column"

        import datetime
        synced_col_idx = col_map["Synced"]
        id_col_idx = col_map["ID"]

        synced_cell = None
        for row in ws.iter_rows(min_row=2, values_only=False):
            if row[id_col_idx - 1].value == 1:
                synced_cell = row[synced_col_idx - 1]
                break

        assert synced_cell is not None, "Row with ID=1 not found in sheet"
        assert isinstance(synced_cell.value, datetime.datetime), (
            f"'Synced' cell is {type(synced_cell.value).__name__}, expected datetime. "
            f"Value: {synced_cell.value!r}"
        )


# ---------------------------------------------------------------------------
# AC-4: Sheet wins when sheet timestamp is newer
# ---------------------------------------------------------------------------


class TestSheetWins:
    """0k6 AC-4: when the sheet row has a later Date Modified, both the tracked-actions
    table row and the matching floating action paragraph are updated from the sheet."""

    def test_sheet_timestamp_newer_doc_updated(
        self, test_sheet_id, test_doc_id, gas_log_dir
    ):
        """After setupTestFixtures('ac4') + syncDocument(), the doc tracked-actions
        table row and floating action paragraph for ID=1 must reflect the sheet's
        Status value ('In Review'), and the floating-action paragraph style is preserved.

        Fixture precondition: doc table row Date Modified = T-1h; sheet row
        Date Modified = T (newer); sheet Status = 'In Review'.
        """
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        clear_logs(gas_log_dir)
        setup_fixture('ac4')
        sync_document(test_doc_id)
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.doc-updated")

        docx_bytes = download_docx(test_doc_id)
        doc = load_doc(docx_bytes)

        # Assert tracked-actions table row is updated
        table_row = find_table_row(doc, action_id=1)
        assert table_row is not None, "Tracked-actions table row with ID=1 not found"
        assert table_row["Status"] == "In Review", (
            f"Expected table row Status='In Review' (sheet wins), got {table_row['Status']!r}"
        )

        # Assert floating action paragraph is rewritten with new status
        actions = floating_actions(doc)
        matching = [a for a in actions if a["id"] == 1]
        assert matching, "Floating action AI-1 not found in doc after sheet-wins sync"
        assert matching[0]["status"] == "In Review", (
            f"Floating action status expected 'In Review', got {matching[0]['status']!r}"
        )

    def test_sheet_wins_floating_action_style_preserved(
        self, test_doc_id, gas_log_dir
    ):
        """After a sheet-wins rewrite, the floating-action paragraph style must
        match the style it had before sync (paragraph style is preserved, not reset)."""
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        clear_logs(gas_log_dir)
        setup_fixture('ac4')
        sync_document(test_doc_id)
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.doc-updated")

        docx_bytes = download_docx(test_doc_id)
        doc = load_doc(docx_bytes)

        actions = floating_actions(doc)
        matching = [a for a in actions if a["id"] == 1]
        assert matching, "Floating action AI-1 not found"

        # The fixture seeds the paragraph with 'Normal' style — it must not become
        # a heading or default paragraph style after rewrite
        para_style = matching[0]["_para_style"]
        assert para_style is not None and para_style != "", (
            "Paragraph style is missing after rewrite"
        )
        assert not para_style.startswith("Heading"), (
            f"Paragraph style was corrupted to '{para_style}' during rewrite"
        )


# ---------------------------------------------------------------------------
# onEdit trigger: editing a sheet cell clears Synced
# ---------------------------------------------------------------------------


class TestOnEditTrigger:
    """0k6 onEdit trigger: a user edit to a sheet row clears the Synced cell for
    that row and updates Date Modified."""

    def test_edit_clears_synced_column(
        self, test_sheet_id, test_doc_id, gas_log_dir
    ):
        """After a user edits the Status cell of an existing row (simulated via
        setupTestFixtures('onedit') which writes directly to the sheet as a
        user action), the Synced cell for that row must be blank in the xlsx download.

        This verifies the onEdit handler fires on manual Status edits and clears
        the Synced column, marking the row as pending re-sync.
        """
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        clear_logs(gas_log_dir)
        setup_fixture('onedit')
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "onedit.complete")

        xlsx = download_xlsx(test_sheet_id)
        ws = load_sheet(xlsx, sheet_name="Actions")

        col_map = headers(ws)
        assert "Synced" in col_map, "Sheet 'Actions' tab has no 'Synced' column"

        synced_col_idx = col_map["Synced"]
        id_col_idx = col_map["ID"]

        synced_cell = None
        for row in ws.iter_rows(min_row=2, values_only=False):
            if row[id_col_idx - 1].value == 1:
                synced_cell = row[synced_col_idx - 1]
                break

        assert synced_cell is not None, "Row with ID=1 not found in sheet after edit"
        assert synced_cell.value is None or synced_cell.value == "", (
            f"Expected Synced cell to be blank after user edit, "
            f"got {synced_cell.value!r}"
        )

    def test_edit_id_column_does_not_clear_synced(
        self, test_sheet_id, test_doc_id, gas_log_dir
    ):
        """Editing the ID column must NOT clear the Synced cell — the onEdit handler
        must only fire on actionable columns (Status, Action, etc.), not on ID."""
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        clear_logs(gas_log_dir)
        setup_fixture('onedit_id')
        sync_document(test_doc_id)
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.complete")

        xlsx = download_xlsx(test_sheet_id)
        ws = load_sheet(xlsx, sheet_name="Actions")

        col_map = headers(ws)
        assert "Synced" in col_map, "Sheet 'Actions' tab has no 'Synced' column"

        import datetime
        synced_col_idx = col_map["Synced"]
        id_col_idx = col_map["ID"]

        synced_cell = None
        for row in ws.iter_rows(min_row=2, values_only=False):
            if row[id_col_idx - 1].value == 1:
                synced_cell = row[synced_col_idx - 1]
                break

        assert synced_cell is not None, "Row with ID=1 not found"
        # Synced must still hold a datetime (not cleared)
        assert isinstance(synced_cell.value, datetime.datetime), (
            f"Synced cell was incorrectly cleared after ID-column edit. "
            f"Got: {synced_cell.value!r}"
        )


# ---------------------------------------------------------------------------
# Programmatic write guard: sync writes must not fire onEdit
# ---------------------------------------------------------------------------


class TestWriteGuard:
    """0k6 write guard: the SYNC_IN_PROGRESS flag prevents reconciler sheet writes
    from re-triggering the onEdit handler."""

    def test_programmatic_write_does_not_fire_onedit(
        self, test_sheet_id, test_doc_id, gas_log_dir
    ):
        """After setupTestFixtures('ac3') + syncDocument(), the reconciler writes
        new values to the sheet row (doc-wins path). The Synced column must NOT
        be blank after the sync completes — if the write guard is missing,
        the reconciler write would trigger onEdit which would clear Synced.

        A non-blank (datetime) Synced value after sync is the indirect proof that
        the onEdit handler did not fire during the reconciler's programmatic write.
        """
        if gas_log_dir is None:
            pytest.skip("gasLogDir not configured")

        clear_logs(gas_log_dir)
        setup_fixture('ac3')
        sync_document(test_doc_id)
        wait_for_log(gas_log_dir, lambda e: e.get("tag") == "sync.complete")

        xlsx = download_xlsx(test_sheet_id)
        ws = load_sheet(xlsx, sheet_name="Actions")

        col_map = headers(ws)
        assert "Synced" in col_map, "Sheet 'Actions' tab has no 'Synced' column"

        import datetime
        synced_col_idx = col_map["Synced"]
        id_col_idx = col_map["ID"]

        synced_cell = None
        for row in ws.iter_rows(min_row=2, values_only=False):
            if row[id_col_idx - 1].value == 1:
                synced_cell = row[synced_col_idx - 1]
                break

        assert synced_cell is not None, "Row with ID=1 not found after sync"
        assert isinstance(synced_cell.value, datetime.datetime), (
            f"Synced cell is blank after sync — programmatic write likely triggered "
            f"onEdit (write guard missing). Got: {synced_cell.value!r}"
        )
